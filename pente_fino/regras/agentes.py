"""Agentes de IA (Claude Code, Cursor, Copilot, Gemini, Codex…): config e instruções que vêm DENTRO do repositório.

A IA do editor lê o que está no repositório junto com o seu pedido, e várias ferramentas aceitam configuração
vinda do projeto (hooks, servidores MCP). Quem fez o repositório escreve parte das regras do SEU assistente.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

from pente_fino import invisiveis, jsonc
from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import Arquivo, dict_ou_vazio, linha_da_posicao, linha_do_termo, lista_ou_vazia, termina_em
from pente_fino.comandos import como_texto, explica, sinais
from pente_fino.regras.comum import comandos_dentro, config_ilegivel

achado = achador("agentes")

MCP_JSON = (
    ".mcp.json",
    "mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
    ".gemini/settings.json",
    ".qwen/settings.json",
    ".windsurf/mcp.json",
    ".roo/mcp.json",
    ".amazonq/mcp.json",
    ".kiro/settings/mcp.json",
    ".junie/mcp/mcp.json",
    "opencode.json",
    ".zed/settings.json",
    ".vscode/settings.json",
)
GANCHOS_JSON = (".cursor/hooks.json", ".codex/hooks.json", ".gemini/settings.json", ".qwen/settings.json")
CLAUDE = (".claude/settings.json", ".claude/settings.local.json")
# scripts que o Claude Code roda sozinho pra buscar credencial
AJUDANTES = ("apiKeyHelper", "awsAuthRefresh", "awsCredentialExport", "gcpAuthRefresh", "otelHeadersHelper")
# comandos que o Claude Code roda o tempo todo pra montar a tela
COMANDOS_DE_TELA = ("statusLine", "subagentStatusLine", "fileSuggestion")
# variáveis que desviam a IA pra outro servidor, deixam interceptar a conexão, ou injetam código em tudo
ENV_PERIGOSA = re.compile(
    r"(BASE_URL|API_BASE|_ENDPOINT)$|^(HTTPS?_PROXY|ALL_PROXY|NODE_EXTRA_CA_CERTS|SSL_CERT_FILE|SSL_CERT_DIR|"
    r"REQUESTS_CA_BUNDLE|CURL_CA_BUNDLE|NODE_OPTIONS|NODE_PATH|LD_PRELOAD|LD_LIBRARY_PATH|DYLD_INSERT_LIBRARIES|"
    r"PYTHONSTARTUP|PYTHONPATH|BASH_ENV|ENV|PATH|SHELL|GIT_SSH_COMMAND|GIT_ASKPASS|ANTHROPIC_AUTH_TOKEN)$",
    re.I,
)
BASH_LIVRE = re.compile(
    r"Bash(\((\*|\*:\*|(ba|z|da)?sh|python3?|node|npx|bun|deno|perl|ruby|curl|wget|pwsh|powershell|env|eval|xargs)"
    r"([ :][^)]*)?\)|\(\s*\))?",
    re.I,
)
FRASES = tuple(
    (re.compile(padrao, re.I), motivo)
    for padrao, motivo in (
        (
            r"\bnao\s+(conte|mencione|avise|diga|informe|revele)\b[^.]{0,80}?"
            r"\b(usuario|dono|dev|desenvolvedor|programador|ninguem|humano|voce)\b",
            "pede pra IA esconder algo de você",
        ),
        (
            r"\b(do\s+not|don'?t|never)\s+(tell|mention|inform|reveal|alert|notify)\b[^.]{0,80}?"
            r"\b(user|developer|dev|owner|human|anyone)\b",
            "pede pra IA esconder algo de você",
        ),
        (
            # ("sem contar" sozinho também quer dizer "sem incluir na conta": só vale "contar ao usuário")
            r"\bsem\s+(avisar|mencionar|informar|notificar|contar\s+(ao|pro|para\s+o)\s+(usuario|dono|dev))\b|"
            r"\bwithout\s+(telling|informing|notifying|alerting)\b",
            "pede pra IA esconder algo de você",
        ),
        (
            r"\b(em\s+segredo|escondido\s+do\s+usuario|secretly|covertly|behind\s+the\s+user'?s\s+back)\b",
            "pede pra IA agir escondida",
        ),
        (
            r"\bno\s+(le\s+)?(digas|cuentes|menciones|informes)\b[^.]{0,80}?\b(usuario|desarrollador)\b",
            "pede pra IA esconder algo de você",
        ),
        (
            r"\b(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+)*(previous|prior|above|earlier|other|"
            r"preceding)\s+(instructions|guidelines|rules|directions|prompts)\b",
            "manda a IA ignorar as outras ordens",
        ),
        (r"\bforget\s+everything\s+(above|before)\b", "manda a IA ignorar as outras ordens"),
        (
            r"\b(ignore|desconsidere|esqueca|despreze|ignora)\s+(todas\s+)?(as\s+|las\s+)?(outras\s+)?"
            r"(instrucoes|instrucciones|regras|ordens|orientacoes)\b",
            "manda a IA ignorar as outras ordens",
        ),
        (
            r"\b(rode|execute|instale|rodar|executar|instalar|baixe|baixar|apague|apagar|envie|enviar|run|install|"
            r"download|delete|remove|send|upload)\b[^.]{0,80}?\b(sem\s+(perguntar|pedir|confirmar|permissao)|"
            r"without\s+(asking|confirmation|confirming|permission|approval))\b",
            "manda a IA agir sem pedir sua permissão",
        ),
        (r"\bnever\s+ask\s+(for\s+)?(confirmation|permission|approval)\b", "manda a IA agir sem pedir sua permissão"),
        (
            r"~/\.ssh|\bid_rsa\b|\bid_ed25519\b|\.aws/credentials|\.npmrc\b|\.git-credentials|\bkeychain\b|"
            r"\.config/gh\b|\.docker/config\.json|\.kube/config|wallet\.dat|\bseed\s+phrase",
            "menciona arquivos de chave e senha da sua máquina",
        ),
        (
            r"\b(curl|wget)\b[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z)?sh\b|\$\(\s*(curl|wget)\b|"
            r"base64\s+(-d|--decode)[^\n]{0,80}\|\s*(ba)?sh\b",
            "manda baixar um script e rodar",
        ),
    )
)
COMENTARIO_HTML = re.compile(r"<!--(.{0,4000}?)-->", re.S)


def verificar(arq: Arquivo) -> Iterator[Achado]:
    if arq.texto is None:
        return
    if termina_em(arq.rel, *MCP_JSON) or re.search(r"(^|/)\.continue/mcpservers/[^/]+\.ya?ml$", arq.rel.lower()):
        yield from _mcp(arq)
    if termina_em(arq.rel, ".codex/config.toml"):
        yield from _codex_toml(arq)
    if termina_em(arq.rel, *CLAUDE):
        dados = jsonc.ler(arq.texto)
        yield from (
            _claude(arq, dados) if isinstance(dados, dict) else [config_ilegivel(achado, arq, ("hooks", *AJUDANTES))]
        )
    if termina_em(arq.rel, *GANCHOS_JSON) or re.search(r"(^|/)\.github/hooks/[^/]+\.json$", arq.rel.lower()):
        dados = jsonc.ler(arq.texto)
        if dados is None and not termina_em(arq.rel, *MCP_JSON):
            yield config_ilegivel(achado, arq, ("hooks", "command"))
        inteiro = dados if arq.nome.lower() != "settings.json" else None  # hooks.json: o arquivo todo é de hooks
        yield from _ganchos(arq, dict_ou_vazio(dados).get("hooks", inteiro))
    if arq.eh_instrucao_de_ia:
        yield from _instrucoes(arq)


def _servidores(dados: object) -> dict:
    """Cada ferramenta guarda os servidores MCP numa chave diferente."""
    dados = dict_ou_vazio(dados)
    for chave in ("mcpServers", "servers", "context_servers", "mcp"):
        servidores = dict_ou_vazio(dados.get(chave))
        if chave == "mcp" and "servers" in servidores:
            servidores = dict_ou_vazio(servidores["servers"])
        if servidores:
            return servidores
    return {}


def _mcp(arq: Arquivo) -> Iterator[Achado]:
    if arq.rel.lower().endswith((".yaml", ".yml")):  # .continue/mcpServers/*.yaml: lê o "command:" na unha
        comandos = re.finditer(r"^[ \t]*command:[ \t]*(.+)$", arq.texto, re.M)
        servidores = {f"{arq.nome} #{i}": {"command": m.group(1)} for i, m in enumerate(comandos, 1)}
    else:
        dados = jsonc.ler(arq.texto)
        if dados is None and not termina_em(arq.rel, ".vscode/settings.json"):  # esse o editor já avisa
            yield config_ilegivel(achado, arq, ("command", "mcpServers"))
        servidores = _servidores(dados)
    for nome, servidor in servidores.items():
        servidor = dict_ou_vazio(servidor)
        linha, _ = linha_do_termo(arq.texto, f'"{nome}"')
        comando = " ".join([como_texto(servidor.get("command")), como_texto(servidor.get("args"))]).strip()
        if servidor.get("headersHelper"):
            comando = (comando + " ; " + como_texto(servidor["headersHelper"])).strip(" ;")
        if comando:
            yield achado(
                Nivel.PERIGO if sinais(comando) else Nivel.ATENCAO,
                arq,
                f"servidor MCP «{nome}» que liga um programa na sua máquina",
                "Quando a IA do editor carrega este projeto (normalmente depois de você confiar na pasta ou "
                "aprovar o servidor), ela sobe esse programa com o SEU usuário, com acesso aos seus arquivos e "
                "chaves. Só aprove se souber de onde ele vem." + explica(comando),
                linha=linha,
                trecho=comando,
            )
        elif url := servidor.get("url") or servidor.get("serverUrl") or servidor.get("httpUrl"):
            yield achado(
                Nivel.INFO,
                arq,
                f"servidor MCP «{nome}» na internet",
                "A IA vai conversar com esse endereço e pode mandar pra ele trechos do seu código.",
                linha=linha,
                trecho=str(url),
            )


def _codex_toml(arq: Arquivo) -> Iterator[Achado]:
    for m in re.finditer(r"^[ \t]*command[ \t]*=[ \t]*(.+)$", arq.texto, re.M):
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        yield achado(
            Nivel.PERIGO if sinais(m.group(1)) else Nivel.ATENCAO,
            arq,
            "o Codex liga um programa do projeto",
            "Servidor MCP ou hook do Codex vindo do repositório: roda na sua máquina quando você confia no "
            "projeto." + explica(m.group(1)),
            linha=linha,
            trecho=trecho,
        )


def _claude(arq: Arquivo, dados: dict) -> Iterator[Achado]:
    yield from _ganchos(arq, dados.get("hooks"))
    for chave in AJUDANTES:
        if dados.get(chave):
            linha, trecho = linha_do_termo(arq.texto, f'"{chave}"')
            yield achado(
                Nivel.PERIGO,
                arq,
                f"script que o Claude Code roda pra pegar sua credencial ({chave})",
                "O projeto decide qual programa fornece a sua chave. Quem controla esse script controla a sua chave.",
                linha=linha,
                trecho=trecho,
            )
    for chave in COMANDOS_DE_TELA:
        if comando := como_texto(dict_ou_vazio(dados.get(chave)).get("command")):
            linha, _ = linha_do_termo(arq.texto, f'"{chave}"')
            yield achado(
                Nivel.PERIGO if sinais(comando) else Nivel.ATENCAO,
                arq,
                f"comando que o Claude Code roda o tempo todo ({chave})",
                "Roda sozinho, várias vezes, enquanto você usa o Claude Code nesta pasta." + explica(comando),
                linha=linha,
                trecho=comando,
            )
    for chave, valor in dict_ou_vazio(dados.get("env")).items():
        if ENV_PERIGOSA.search(chave) and chave.upper() != "NO_PROXY":
            proxy = "PROXY" in chave.upper()  # proxy de empresa é comum: atenção, não perigo
            linha, _ = linha_do_termo(arq.texto, f'"{chave}"')
            yield achado(
                Nivel.ATENCAO if proxy else Nivel.PERIGO,
                arq,
                f"variável que desvia ou injeta: {chave}",
                "Variável de endereço (BASE_URL, PROXY) manda as conversas da IA, com a sua chave, pra outro "
                "servidor; certificado extra deixa alguém ler a conexão; as outras injetam código ou trocam "
                "programas em tudo que o agente rodar.",
                linha=linha,
                trecho=f"{chave} = {valor}",
            )
    aprova = dados.get("enableAllProjectMcpServers") is True or bool(dados.get("enabledMcpjsonServers"))
    if aprova:
        tem_mcp = bool(arq.varredura) and any(termina_em(r, ".mcp.json") for r in arq.varredura.por_caminho)
        linha, trecho = linha_do_termo(arq.texto, "McpServers")
        yield achado(
            Nivel.PERIGO if tem_mcp else Nivel.ATENCAO,
            arq,
            "aprova sozinho os servidores MCP do projeto",
            "Você não vai ser perguntado antes de cada servidor subir."
            + (" E este projeto tem um .mcp.json: os programas dele sobem direto." if tem_mcp else ""),
            linha=linha,
            trecho=trecho,
        )
    permissoes = dict_ou_vazio(dados.get("permissions"))
    if permissoes.get("defaultMode") in ("bypassPermissions", "auto"):
        linha, trecho = linha_do_termo(arq.texto, '"defaultMode"')
        yield achado(
            Nivel.ATENCAO,
            arq,
            "tenta desligar as confirmações do agente",
            "O Claude Code 2.1.257 ou mais novo ignora isso quando vem do projeto; versões antigas obedecem e "
            "fazem qualquer coisa sem perguntar.",
            linha=linha,
            trecho=trecho,
        )
    liberados = [p for p in lista_ou_vazia(permissoes.get("allow")) if isinstance(p, str) and BASH_LIVRE.fullmatch(p)]
    if liberados:
        linha, trecho = linha_do_termo(arq.texto, liberados[0])
        yield achado(
            Nivel.ATENCAO,
            arq,
            "libera comandos de terminal sem perguntar",
            "Liberar um shell, um interpretador ou o curl é o mesmo que liberar QUALQUER comando. Junto com "
            "uma instrução maliciosa no repositório, vira execução sem você ver.",
            linha=linha,
            trecho=", ".join(liberados),
        )
    if dados.get("extraKnownMarketplaces") or dados.get("enabledPlugins"):
        linha, trecho = linha_do_termo(
            arq.texto, "extraKnownMarketplaces" if dados.get("extraKnownMarketplaces") else "enabledPlugins"
        )
        yield achado(
            Nivel.ATENCAO,
            arq,
            "indica plugins pro seu Claude Code",
            "Plugin pode trazer hooks, comandos e servidores MCP. Depois que você confia na pasta, o Claude "
            "Code oferece instalar os plugins que o projeto indicar.",
            linha=linha,
            trecho=trecho,
        )


def _ganchos(arq: Arquivo, ganchos: object) -> Iterator[Achado]:
    eventos = ganchos.items() if isinstance(ganchos, dict) else [("(lista)", ganchos)] if ganchos else []
    for evento, regras in eventos:
        comandos = comandos_dentro(regras, ("command", "bash", "powershell", "url"))
        if not comandos:
            continue
        linha, _ = linha_do_termo(arq.texto, f'"{evento}"')
        comando = " ; ".join(comandos)
        yield achado(
            Nivel.PERIGO,
            arq,
            f"gancho (hook) que roda comando sozinho no evento «{evento}»",
            "Cada vez que esse evento acontece, o comando roda na sua máquina, sem perguntar (as ferramentas pedem "
            "que você confie na pasta antes). Se o projeto é seu e foi você que configurou, tudo certo; se veio de "
            "fora, leia o script antes." + explica(comando),
            linha=linha,
            trecho=comando,
        )


def _para_comparar(texto: str) -> str:
    """Sem acento, sem caractere invisível e sem letra "enfeitada": pra frase escondida não escapar.

    Texto escrito em "tags" invisíveis é traduzido de volta pra letra normal: a frase escondida também é lida.
    """
    sem_invisivel = "".join(_traduz(c) for c in texto)
    decomposto = unicodedata.normalize("NFKD", sem_invisivel)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _traduz(c: str) -> str:
    tipo = invisiveis.tipo(c)
    if tipo == "tag" and 0xE0020 <= ord(c) <= 0xE007E:
        return chr(ord(c) - 0xE0000)
    return "" if tipo else c


def _instrucoes(arq: Arquivo) -> Iterator[Achado]:
    yield achado(
        Nivel.INFO,
        arq,
        "arquivo de instruções pra IA",
        "A IA do editor lê isso junto com o seu pedido e costuma seguir. Leia antes de deixar um agente "
        "trabalhar neste projeto.",
    )
    texto = arq.texto[:500_000]
    comparar = _para_comparar(texto)
    linhas = texto.splitlines()
    for padrao, motivo in FRASES:
        if m := padrao.search(comparar):
            numero = comparar.count("\n", 0, m.start()) + 1
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"instrução suspeita: {motivo}",
                "Instrução de projeto não tem motivo pra esconder coisa de você, pular sua permissão ou "
                "mexer nas suas chaves.",
                linha=numero,
                trecho=linhas[numero - 1].strip() if numero <= len(linhas) else m.group(),
            )
    for m in COMENTARIO_HTML.finditer(texto):
        if len(m.group(1).strip()) >= 20:
            linha, _ = linha_da_posicao(texto, m.start())
            yield achado(
                Nivel.ATENCAO,
                arq,
                "comentário escondido num arquivo de instruções",
                "Comentário <!-- … --> não aparece na prévia do Markdown, mas a IA lê. Por que esconder uma "
                "parte das instruções de quem lê pela tela?",
                linha=linha,
                trecho=m.group(1).strip(),
            )
            break
    if re.search(r"(^|/)\.claude/(agents|skills)/", arq.rel.lower()) and (posicao := _gancho_no_cabecalho(texto)):
        linha, trecho = linha_da_posicao(texto, posicao)
        yield achado(
            Nivel.PERIGO,
            arq,
            "agente/skill com hook no cabeçalho",
            "O cabeçalho (frontmatter) deste agente ou skill define comandos que rodam sozinhos enquanto ele "
            "trabalha." + explica(trecho),
            linha=linha,
            trecho=trecho,
        )
    if re.search(r"(^|/)\.claude/commands/", arq.rel.lower()) and (m := re.search(r"!`([^`\n]+)`", texto)):
        linha, trecho = linha_da_posicao(texto, m.start())
        yield achado(
            Nivel.ATENCAO,
            arq,
            "comando de barra que roda terminal antes de chegar na IA",
            "Quando você chamar esse /comando, o Claude Code roda o que está entre !`…` no seu terminal."
            + explica(m.group(1)),
            linha=linha,
            trecho=trecho,
        )


def _gancho_no_cabecalho(texto: str) -> int | None:
    """Posição do primeiro `command:` dentro de `hooks:` no cabeçalho YAML (entre os dois ---), se houver."""
    cabecalho = re.match(r"---\n(.{0,20000}?)\n---", texto, re.S)
    if not cabecalho or not re.search(r"^\s*hooks\s*:", cabecalho.group(1), re.M):
        return None
    comando = re.search(r"^[ \t]*-?[ \t]*command[ \t]*:", cabecalho.group(1), re.M)
    return cabecalho.start(1) + comando.start() if comando else None
