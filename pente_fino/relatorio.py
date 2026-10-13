"""A saída: no terminal (com a voz do Garoto) ou em JSON (pra CI e outras ferramentas).

Regra de ouro: NADA que veio do repositório vai pra tela cru. Caractere invisível e código de terminal (ANSI)
viram marcador visível. Senão um arquivo malicioso poderia apagar ou reescrever o próprio aviso de perigo.
"""

from __future__ import annotations

import json

from pente_fino import __version__, invisiveis
from pente_fino.achado import Achado, Nivel
from pente_fino.pente import Resultado

ETIQUETAS = {
    Nivel.PERIGO: ("PERIGO ", "1;97;41"),
    Nivel.ATENCAO: ("ATENÇÃO", "1;30;43"),
    Nivel.INFO: ("INFO   ", "1;97;44"),
}
VEREDITOS = {
    "PERIGO": (
        "NÃO ABRA NO EDITOR. E NÃO RODE NADA.",
        "1;91",
        "Achei coisa que roda sozinha ou que se esconde de você. Se isso é teste técnico de vaga, desconfie da "
        "vaga também: empresa séria não manda você rodar código de estranho na sua máquina.",
    ),
    "ATENCAO": (
        "ABRA COM CUIDADO.",
        "1;93",
        "Nada roda sozinho no que eu sei olhar, mas tem coisa que roda quando VOCÊ mandar (instalar, compilar) "
        "ou que eu não consegui ler. Leia os achados antes.",
    ),
    "INCOMPLETO": (
        "NÃO CONSEGUI OLHAR TUDO.",
        "1;96",
        "No que eu olhei, nada suspeito. Mas pulei pastas ou não li arquivos inteiros (veja os INFO): rode de "
        "novo com --tudo antes de confiar.",
    ),
    "LIMPO": (
        "NADA SUSPEITO NO QUE EU SEI OLHAR.",
        "1;92",
        "Não é atestado de santidade: eu procuro os truques conhecidos, não leio mente. Código de quem você não "
        "conhece, rode numa máquina descartável.",
    ),
}
COMO_OLHAR = (
    "Pra olhar sem risco: passe o pente DE FORA da pasta (nunca dê `cd` nela antes). No VS Code, escolha NÃO confiar "
    "quando ele perguntar (Modo Restrito). O Cursor, segundo a documentação dele, vem com esse aviso desligado: "
    "ligue em `security.workspace.trust.enabled`. Instale dependências só com `npm install --ignore-scripts` e, se "
    "precisar rodar, use uma máquina virtual ou um container descartável, sem as suas chaves."
)


def veredito(resultado: Resultado) -> str:
    if resultado.pior in (Nivel.PERIGO, Nivel.ATENCAO):
        return resultado.pior.name
    return "INCOMPLETO" if resultado.incompleto else "LIMPO"


def visivel(texto: str, limite: int = 160) -> str:
    """Troca invisíveis e controles por ⟦U+XXXX⟧ e encurta pelo MEIO (o fim de um comando importa)."""
    saida, fileira = [], []

    def fecha_fileira() -> None:
        if len(fileira) > 3:
            saida.append(f"⟦{len(fileira)} invisíveis⟧")
        else:
            saida.extend(f"⟦U+{ord(c):04X}⟧" for c in fileira)
        fileira.clear()

    for c in texto[:20_000]:
        if c == "\t":
            c = " "
        if invisiveis.some_na_tela(c):
            fileira.append(c)
            continue
        if fileira:
            fecha_fileira()
        saida.append(c)
    if fileira:
        fecha_fileira()
    limpo = "".join(saida)
    if len(limpo) <= limite:
        return limpo
    fim = limite // 3
    return limpo[: limite - fim - 1] + "…" + limpo[-fim:]


def texto(resultado: Resultado, cor: bool = False, sem_info: bool = False) -> str:
    def pinta(s: str, codigo: str) -> str:
        return f"\033[{codigo}m{s}\033[0m" if cor else s

    linhas = [
        "",
        pinta(f" PENTE-FINO do Garoto;  v{__version__} ", "1;30;47"),
        f"pasta: {visivel(str(resultado.pasta))}  ·  {resultado.lidos} arquivos vistos  ·  "
        "nada foi executado, nada saiu da sua máquina",
        "",
    ]
    for item in resultado.achados:
        if sem_info and item.nivel == Nivel.INFO:
            continue
        rotulo, codigo = ETIQUETAS[item.nivel]
        local = visivel(item.arquivo, 100) + (f":{item.linha}" if item.linha else "")
        linhas.append(f"{pinta(f' {rotulo} ', codigo)}  {pinta(local, '1')}")
        linhas.append(f"           {visivel(item.titulo, 200)}")
        if item.trecho:
            linhas.append(pinta(f"           │ {visivel(item.trecho)}", "2"))
        if item.porque:
            linhas.append(f"           {visivel(item.porque, 1000)}")
        linhas.append("")
    titulo, codigo, explicacao = VEREDITOS[veredito(resultado)]
    contagem = "  ·  ".join(
        f"{resultado.quantos(n)} {nome}"
        for n, nome in ((Nivel.PERIGO, "perigo(s)"), (Nivel.ATENCAO, "atenção(ões)"), (Nivel.INFO, "info(s)"))
    )
    linhas += ["─" * 72, f"VEREDITO: {pinta(titulo, codigo)}   ({contagem})", explicacao]
    if resultado.pior in (Nivel.PERIGO, Nivel.ATENCAO):
        linhas.append(COMO_OLHAR)
    return "\n".join(linhas) + "\n"


def como_json(resultado: Resultado) -> str:
    def item(a: Achado) -> dict:
        return {
            "nivel": a.nivel.name,
            "regra": a.regra,
            "arquivo": visivel(a.arquivo, 1000),
            "linha": a.linha,
            "titulo": visivel(a.titulo, 1000),
            "porque": visivel(a.porque, 2000),
            "trecho": visivel(a.trecho, 1000),
        }

    return json.dumps(
        {
            "versao": __version__,
            "pasta": visivel(str(resultado.pasta), 1000),
            "arquivos_vistos": resultado.lidos,
            "veredito": veredito(resultado),
            "veredito_texto": VEREDITOS[veredito(resultado)][0],
            "contagem": {n.name: resultado.quantos(n) for n in Nivel},
            "achados": [item(a) for a in resultado.achados],
        },
        ensure_ascii=False,
        indent=2,
    )
