"""Escondido: o que está no arquivo mas você NÃO vê.

- caracteres invisíveis: a IA e o computador leem, você não. Quando dá, o pente-fino REVELA o texto;
- Trojan Source: caracteres que trocam a ordem do texto na tela (o que você lê não é o que roda);
- código empurrado pra fora da tela (centenas de espaços) ou pra baixo (centenas de linhas em branco);
- texto codificado que é decodificado e executado;
- blocos enormes de base64 no meio do código.

Todas as buscas andam só pra frente (sem volta pra trás): arquivo feito pra travar o pente-fino não trava.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterator

from pente_fino import invisiveis
from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import Arquivo, linha_da_posicao

achado = achador("escondido")

# espaços que empurram: espaço, tab, espaço sem quebra e os espaços largos do Unicode
_ESPACOS = " \t" + "".join(map(chr, [0xA0, *range(0x2000, 0x200B), 0x202F, 0x205F, 0x3000]))
EMPURRADO = re.compile(f"(?<![{_ESPACOS}])[{_ESPACOS}]{{150,}}(?=[^\\s{_ESPACOS}])")
LINHAS_EM_BRANCO = re.compile(r"(?<=\S)[ \t]*\n(?:[ \t]*\n){150,}(?=[ \t]*\S)")
# executores chamados direto, com call/apply/bind, com ?. ou pelo constructor; e o pickle.loads do Python
CHAMADA = r"\s*(\?\.|\.call|\.apply|\.bind)?\s*\("
EXECUTA = (
    r"(\b(eval|exec|execSync|execFile|spawn|spawnSync|Function|system|popen|__import__|runInNewContext|"
    r"runInThisContext|setTimeout|setInterval|loads)|\.constructor)" + CHAMADA
)
# executa CÓDIGO escrito como texto (não um programa): é isso que transforma texto decodificado em ação
# (o `.exec(` de expressão regular e o `re.compile(` não executam código: ficam de fora)
CODIGO_DINAMICO = (
    r"((?<![.\w])(eval|exec|Function|__import__)|\b(runInNewContext|runInThisContext)|\.constructor)" + CHAMADA
)
DECODIFICA = (
    r"\b(atob|b64decode|b32decode|a85decode|fromCharCode|unhexlify|decompress|inflateSync|gunzipSync|unescape|"
    r"decodeURIComponent|fromhex)\b|\bcodecs\.decode\b|\bmarshal\.loads\b|\bBuffer\.from\s*\([^)]{0,200}"
    r"['\"](base64|hex)['\"]"
)
# "executa" com "decodifica" logo depois, dentro do mesmo comando (pode quebrar linha, como o Black faz)
COLADOS = re.compile(
    EXECUTA + r"[^;)]{0,80}?(" + DECODIFICA + r"|['\"]base64['\"])"
    r"|\bimport\s*\(\s*['\"`]data:[^'\"`\n]{0,60};base64,"  # importa um módulo escrito em base64
)
SO_DINAMICO = re.compile(CODIGO_DINAMICO)
SO_DECODIFICA = re.compile(DECODIFICA + r"|['\"]base64['\"]")
# pra "duas pistas no mesmo arquivo", só decodificação de verdade (fromCharCode e cia. estão em toda biblioteca)
DECODIFICA_FORTE = re.compile(
    r"\b(atob|b64decode|b32decode|a85decode|unhexlify)\b|\bcodecs\.decode\b|\bmarshal\.loads\b|"
    r"\bBuffer\.from\s*\([^)]{0,200}['\"](base64|hex)['\"]"
)
# chamar uma função pelo nome montado em pedaços, ou escrito com código de escape: jeito de esconder um eval
INDIRETO = re.compile(
    r"\(\s*0\s*,\s*eval\s*\)|[\w)\]]\s*\[\s*['\"`][^'\"`\n]{0,20}['\"`]\s*\+\s*['\"`]|"
    r"\bgetattr\s*\(\s*\w+\s*,\s*['\"][^'\"\n]{0,20}['\"]\s*\+|\bgetattr\s*\(\s*(__builtins__|builtins)\b|"
    r"\b[A-Za-z_]*\x5cu00[4-7][0-9a-fA-F][A-Za-z_]*\s*\(|\bimport\s*\(\s*['\"`]data:|\beval\s*\(\s*[\w$.]+\s*\("
)
# nos scripts de terminal: decodifica e roda, ou baixa e roda
TERMINAL_ESCONDIDO = re.compile(
    r"base64\s+(-d|--decode|-D)\b[^\n]{0,100}\|\s*(sudo\s+)?(ba|z|da)?sh\b|FromBase64String|"
    r"\s-e(nc|ncodedcommand)?\s+[A-Za-z0-9+/=]{8,}",
    re.I,
)
TERMINAL_BAIXA_E_RODA = re.compile(
    r"\b(curl|wget|iwr|irm)\b[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z|da)?sh\b|\b(iwr|irm)\b[^\n]{0,200}\|\s*iex\b", re.I
)
SCRIPT_DE_TERMINAL = {".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".bat", ".cmd"}
BASE64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{400,}={0,2}")

TITULOS = {
    "tag": "texto ESCONDIDO em caracteres invisíveis",
    "seletor": "dados escondidos em caracteres invisíveis (seletores de variação)",
    "bidi": "caracteres que reordenam o texto na tela (Trojan Source)",
    "preenchedor": 'caractere "vazio" que vira nome de variável invisível',
    "largura_zero": "caracteres de largura zero (invisíveis)",
    "uso_privado": "fileira de caracteres sem desenho (área de uso privado)",
}
PORQUES = {
    "tag": "Você não vê nada, mas o computador lê cada letra, e algumas IAs também. É um jeito de esconder uma "
    "ordem pra IA num arquivo que parece inocente.",
    "seletor": "Caracteres invisíveis grudados em letras normais carregam bytes escondidos. Já foi usado pra "
    "esconder código em pacotes e extensões maliciosos.",
    "bidi": "O que você LÊ não é o que o computador processa: esses caracteres reordenam o texto na tela. É "
    "normal em texto árabe ou hebraico; em código ou em instrução de IA, desconfie.",
    "preenchedor": "Parece espaço em branco, mas a linguagem aceita como nome de variável. Dá pra esconder um "
    "parâmetro inteiro na sua frente.",
    "largura_zero": "Não aparecem na tela. Às vezes é sujeira de copiar e colar; em instrução de IA ou código, "
    "pode separar palavras pra driblar filtro ou esconder recado.",
    "uso_privado": "Esses caracteres não têm desenho padrão (fonte de ícone usa), mas uma fileira deles no meio "
    "do código é um jeito de carregar dados que ninguém lê.",
}
SEM_ICONE = {".css", ".scss", ".sass", ".less", ".svg", ".html", ".htm", ".json", ".yaml", ".yml", ".xml"}


def verificar(arq: Arquivo) -> Iterator[Achado]:
    texto = arq.texto
    if not texto or arq.eh_gerado:
        return
    yield from _invisiveis(arq, texto)
    if arq.eh_codigo:
        yield from _codigo_escondido(arq, texto)


def _invisiveis(arq: Arquivo, texto: str) -> Iterator[Achado]:
    if texto.isascii():
        return
    contexto = _Contexto(arq, texto)
    marcas: dict[str, list[re.Match]] = defaultdict(list)
    for m in invisiveis.INVISIVEL.finditer(texto):
        if not contexto.uso_legitimo(m):
            for tipo in {invisiveis.tipo(c) for c in m.group()}:
                marcas[tipo].append(m)
    for tipo, achadas in marcas.items():
        quantos = sum(sum(invisiveis.tipo(c) == tipo for c in m.group()) for m in achadas)
        nivel = contexto.nivel(tipo, achadas, quantos)
        if nivel is None:
            continue
        revelado = _revela(tipo, achadas)
        linha, trecho = linha_da_posicao(texto, achadas[0].start())
        yield achado(
            nivel,
            arq,
            f"{TITULOS[tipo]} ({quantos})",
            PORQUES[tipo],
            linha=linha,
            trecho=f"revelado: {revelado}" if revelado else trecho,
        )


class _Contexto:
    """O que é normal em cada tipo de arquivo: emoji, bandeira, escrita persa, texto em árabe, coreano…"""

    def __init__(self, arq: Arquivo, texto: str) -> None:
        self.arq, self.texto = arq, texto
        self.instrucao = arq.eh_instrucao_de_ia
        self.codigo = arq.eh_codigo
        self.sensivel = self.codigo or self.instrucao
        self.tem_rtl = re.search("[" + chr(0x0590) + "-" + chr(0x08FF) + "]", texto) is not None
        self.tem_coreano = re.search("[" + chr(0xAC00) + "-" + chr(0xD7A3) + "]", texto) is not None

    def uso_legitimo(self, m: re.Match) -> bool:
        marca, texto = m.group(), self.texto
        pontos = {ord(c) for c in marca}
        antes = texto[m.start() - 1] if m.start() else ""
        depois = texto[m.end()] if m.end() < len(texto) else ""
        # cola de emoji: junta vários num só (família), escolhe a versão colorida (coração), forma a tecla (1)
        emoji = _eh_emoji(antes) or _eh_emoji(depois) or ((antes.isdigit() or antes in "#*") and depois == chr(0x20E3))
        if len(marca) <= 2 and pontos <= {0x200D, 0xFE0E, 0xFE0F} and emoji:
            return True
        if pontos <= {0x200B, 0x200C, 0x200D} and (_escrita_que_junta(antes) or _escrita_que_junta(depois)):
            return True  # persa, hindi, tailandês, khmer… usam isso pra juntar ou separar letras e palavras
        if antes == chr(0x1F3F4) and _bandeira_de_regiao(marca):
            return True  # bandeira da Inglaterra, Escócia, País de Gales: bandeira preta + tags
        if len(marca) == 1 and 0xE0100 <= ord(marca) <= 0xE01EF and _eh_ideograma(antes):
            return True  # variante de ideograma chinês/japonês
        if pontos == {0xFEFF} and not self.instrucao:
            return True  # BOM: no meio do código, é o truque pro Excel abrir CSV com acento
        if pontos <= invisiveis.BIDI_MARCA and self.tem_rtl:
            return True  # marcas de direção em arquivo com árabe/hebraico: tradução, i18n
        if pontos <= invisiveis.FAIXAS_BIDI and self._linha_tem_rtl(m.start()):
            return True  # direção numa linha que TEM árabe/hebraico: tradução. Trojan Source fica em código ASCII
        if len(marca) == 1 and antes and antes in "'\"`" and depois == antes:
            return True  # um invisível sozinho entre aspas: é uma constante ('\u200d' escrito direto)
        if pontos <= {0x00AD} and antes.isalpha() and not self.instrucao:
            return True  # hífen invisível grudado numa palavra: separa sílaba
        if not self.sensivel and (pontos <= {0x00AD} or (pontos <= {0x3164, 0x115F, 0x1160} and self.tem_coreano)):
            return True  # hífen invisível em texto corrido; letra vazia em texto coreano
        return len(marca) < 8 and all(0xE000 <= p <= 0xF8FF for p in pontos)  # ícone de fonte (Font Awesome e cia.)

    def _linha_tem_rtl(self, posicao: int) -> bool:
        comeco = self.texto.rfind("\n", 0, posicao) + 1
        fim = self.texto.find("\n", posicao)
        linha = self.texto[comeco : None if fim < 0 else fim]
        return re.search("[" + chr(0x0590) + "-" + chr(0x08FF) + "]", linha) is not None

    def nivel(self, tipo: str, achadas: list[re.Match], quantos: int) -> Nivel | None:
        if tipo in ("tag", "seletor"):
            return Nivel.PERIGO if tipo == "tag" or quantos >= 4 else None
        if tipo == "uso_privado":
            return Nivel.PERIGO if self.codigo and self.arq.extensao not in SEM_ICONE else None
        if tipo == "bidi":
            troca = any(ord(c) in invisiveis.BIDI_TROCA_ORDEM for m in achadas for c in m.group())
            return Nivel.PERIGO if troca and self.sensivel else Nivel.ATENCAO
        if tipo == "preenchedor":
            return Nivel.PERIGO if self.sensivel else Nivel.ATENCAO
        if self.arq.eh_minificado:
            return None  # código minificado de biblioteca usa largura zero em expressões regulares
        return Nivel.PERIGO if self.instrucao else Nivel.ATENCAO


def _eh_emoji(c: str) -> bool:
    return bool(c) and (
        ord(c) >= 0x1F000 or 0x2190 <= ord(c) <= 0x2BFF or ord(c) in (0xA9, 0xAE, 0x203C, 0x2049, 0x2122)
    )


def _escrita_que_junta(c: str) -> bool:
    return bool(c) and (
        0x0600 <= ord(c) <= 0x06FF
        or 0x0900 <= ord(c) <= 0x0DFF
        or 0x0E00 <= ord(c) <= 0x109F
        or 0x1780 <= ord(c) <= 0x17FF
    )


def _eh_ideograma(c: str) -> bool:
    return bool(c) and unicodedata.name(c, "").startswith("CJK")


def _bandeira_de_regiao(marca: str) -> bool:
    """Só a sequência exata de bandeira (ex.: gbeng + fim). Qualquer outra coisa em tags é texto escondido."""
    letras = "".join(chr(ord(c) - 0xE0000) for c in marca[:-1])
    return marca.endswith(chr(0xE007F)) and letras.isalnum() and letras.islower() and 4 <= len(letras) <= 6


def _revela(tipo: str, achadas: list[re.Match]) -> str:
    """Desfaz o disfarce: tags viram letras ASCII; seletores viram bytes (o truque do "emoji contrabandista")."""
    if tipo == "tag":
        return " ".join(
            "".join(chr(ord(c) - 0xE0000) for c in m.group() if 0xE0020 <= ord(c) <= 0xE007E) for m in achadas
        ).strip()
    if tipo == "seletor":
        valores = [_byte_do_seletor(ord(c)) for m in achadas for c in m.group() if invisiveis.tipo(c) == "seletor"]
        decodificado = bytes(valores).decode("utf-8", errors="replace")
        legivel = sum(c.isprintable() for c in decodificado)
        return decodificado if legivel >= 0.8 * max(len(decodificado), 1) else ""
    return ""


def _byte_do_seletor(cp: int) -> int:
    return cp - 0xFE00 if cp <= 0xFE0F else cp - 0xE0100 + 16


def _codigo_escondido(arq: Arquivo, texto: str) -> Iterator[Achado]:
    dados = arq.extensao in (".json", ".jsonc", ".yaml", ".yml", ".toml", ".xml")  # dado, não programa
    m = next((m for m in EMPURRADO.finditer(texto) if not texto.startswith(("#", "//"), m.end())), None)
    if m:  # (espaço de alinhamento antes de um comentário de linha é inofensivo)
        linha, _ = linha_da_posicao(texto, m.end())
        fim = texto.find("\n", m.end())
        depois = texto[m.end() : None if fim < 0 else fim]
        yield achado(
            Nivel.ATENCAO if dados else Nivel.PERIGO,
            arq,
            f"código empurrado pra fora da tela ({len(m.group())} espaços)",
            "Na tela a linha parece terminar normal. Lá no fim, depois de centenas de espaços, tem mais "
            "coisa. Truque visto em pacotes npm maliciosos.",
            linha=linha,
            trecho=f"…[{len(m.group())} espaços]… {depois}",
        )
    if m := LINHAS_EM_BRANCO.search(texto):
        linha, trecho = linha_da_posicao(texto, m.end())
        yield achado(
            Nivel.ATENCAO,
            arq,
            f"código escondido lá embaixo ({m.group().count(chr(10))} linhas em branco)",
            "Quem abre o arquivo vê o começo e acha que acabou. O resto está centenas de linhas abaixo.",
            linha=linha,
            trecho=trecho,
        )
    if arq.extensao in SCRIPT_DE_TERMINAL or (arq.extensao == "" and texto.startswith("#!")):
        yield from _script_de_terminal(arq, texto)
    yield from _decodifica_e_executa(arq, texto)


def _script_de_terminal(arq: Arquivo, texto: str) -> Iterator[Achado]:
    if m := TERMINAL_ESCONDIDO.search(texto):
        linha, trecho = linha_da_posicao(texto, m.start())
        yield achado(
            Nivel.PERIGO,
            arq,
            "script que decodifica um texto escondido e RODA no terminal",
            "Comando em base64 (ou -EncodedCommand do PowerShell) é o jeito de rodar algo sem que você "
            "consiga ler o que é.",
            linha=linha,
            trecho=trecho,
        )
    elif m := TERMINAL_BAIXA_E_RODA.search(texto):
        linha, trecho = linha_da_posicao(texto, m.start())
        yield achado(
            Nivel.ATENCAO,
            arq,
            "script que baixa outro script da internet e roda",
            "Você não sabe o que vem desse endereço hoje (nem amanhã). Instalador oficial às vezes faz isso; "
            "projeto de teste técnico não tem motivo.",
            linha=linha,
            trecho=trecho,
        )


def _decodifica_e_executa(arq: Arquivo, texto: str) -> Iterator[Achado]:
    blob = (
        None
        if arq.eh_minificado
        else next(
            (m for m in BASE64.finditer(texto) if "base64," not in texto[max(0, m.start() - 12) : m.start()]), None
        )
    )
    decodifica = SO_DECODIFICA.search(texto)
    if (decodifica or ";base64," in texto) and (m := COLADOS.search(texto)):
        linha, trecho = linha_da_posicao(texto, m.start())
        yield achado(
            Nivel.PERIGO,
            arq,
            "decodifica um texto escondido e EXECUTA",
            "Código legítimo não precisa se disfarçar. Decodificar e executar no mesmo comando é a "
            "assinatura clássica de quem não quer que você leia o que roda.",
            linha=linha,
            trecho=trecho,
        )
        return
    indireto = INDIRETO.search(texto)
    dinamico = indireto or SO_DINAMICO.search(texto)
    forte = DECODIFICA_FORTE.search(texto)
    if dinamico and (forte or blob or indireto) and not (arq.eh_minificado and not forte):
        linha, trecho = linha_da_posicao(texto, dinamico.start())
        # em arquivo gigante (biblioteca empacotada), as duas pistas soltas são comuns: fica em atenção
        perigo = bool(forte or blob) and not arq.eh_minificado and len(texto) < 200_000
        titulo = "chama função pelo nome disfarçado" if indireto else "decodifica e executa no mesmo arquivo"
        porque = (
            "Montar o nome da função em pedaços (ou com código de escape) é um jeito de esconder um eval de quem lê "
            "e de ferramenta de segurança. Biblioteca às vezes faz isso; código de teste técnico não tem motivo."
            if indireto
            else "Esse arquivo decodifica texto e executa como código. Pode ser legítimo, mas é a receita de quem "
            "esconde um programa." + (" E tem um bloco enorme de base64 junto." if blob else "")
        )
        yield achado(Nivel.PERIGO if perigo else Nivel.ATENCAO, arq, titulo, porque, linha=linha, trecho=trecho)
        return
    if blob:
        linha, _ = linha_da_posicao(texto, blob.start())
        yield achado(
            Nivel.INFO,
            arq,
            f"bloco enorme codificado em base64 ({len(blob.group())} caracteres)",
            "Um texto que ninguém consegue ler no meio do código. Geralmente é dado gerado por ferramenta "
            "(ORM, ícone, fonte); se ninguém souber explicar o que é, desconfie.",
            linha=linha,
            trecho=blob.group()[:60] + "…",
        )
