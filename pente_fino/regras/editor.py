"""Editor (VS Code, Cursor, Windsurf…): o que roda, ou muda, só de você ABRIR a pasta."""

from __future__ import annotations

import re
from collections.abc import Iterator

from pente_fino import jsonc
from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import Arquivo, dict_ou_vazio, linha_da_posicao, linha_do_termo, lista_ou_vazia, termina_em
from pente_fino.comandos import como_texto, explica, sinais
from pente_fino.regras.comum import config_ilegivel

achado = achador("editor")

AO_ABRIR = re.compile(r'"runOn"\s*:\s*"folderOpen"', re.I)  # o VS Code compara sem ligar pra maiúscula
AO_ABRIR_PORQUE = (
    "Tarefa marcada pra rodar sozinha quando a pasta abre. No VS Code atual, depois que você confia na pasta, "
    "ele ainda pergunta uma vez se pode rodar tarefas automáticas. O Cursor, segundo a documentação dele, vem com o "
    "aviso de confiança desligado por padrão, e a Oasis Security mostrou tarefa assim rodando ao abrir a pasta lá. "
    "A Microsoft documentou esse truque no golpe do teste técnico falso (mar/2026)."
)
# o que é normal esconder da barra lateral; o resto merece uma olhada
EXCLUSOES_COMUNS = {
    ".git", ".svn", ".hg", "CVS", ".DS_Store", "Thumbs.db", "node_modules", "__pycache__", "*.pyc", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".venv", "venv", "dist", "build", "out", ".next", "coverage", "target",
}  # fmt: skip
TERMINAL = (
    "terminal.integrated.env",
    "terminal.integrated.profiles",
    "terminal.integrated.shell",
    "terminal.integrated.automationprofile",
)
IA_SEM_PERGUNTAR = (
    "chat.tools.autoapprove",
    "chat.tools.global.autoapprove",
    "chat.mcp.autostart",
    "chat.tools.terminal.autoapprove",
)
PYTHON_DO_VENV = re.compile(r"^(\$\{workspaceFolder\}/|\./)?\.?venv/(bin|Scripts)/python(3|\.exe)?$", re.I)
# arquivos de configuração que extensões do editor carregam sozinhas (ESLint, Prettier, Tailwind…)
CONFIG_JS = re.compile(
    r"^(\.?eslint(rc)?|eslint\.config|\.?prettier(rc)?|prettier\.config|tailwind\.config|postcss\.config|"
    r"babel\.config|\.babelrc|jest\.config|vitest\.config|vite\.config|next\.config|svelte\.config|nuxt\.config|"
    r"astro\.config|webpack\.config|rollup\.config|stylelint\.config|\.stylelintrc)\.(js|cjs|mjs|ts|cts|mts)$",
    re.I,
)
REDE_OU_PROCESSO = re.compile(
    r"child_process|\bexecSync\b|\bspawn(Sync)?\s*\(|\bexecFile\b|\bfetch\s*\(\s*['\"`]https?:|"
    r"require\(\s*['\"](node:)?(https?|net|dgram)['\"]\s*\)|from\s+['\"](node:)?(https?|net)['\"]"
)
CONTAINER_SENSIVEL = re.compile(
    r"\.ssh|docker\.sock|\$\{localEnv:(HOME|USERPROFILE)|source=/[,\s\"]|--privileged|--cap-add|--pid[= ]host|"
    r"--net(work)?[= ]host|--security-opt|--device|(^|\s)-v\s+/",
    re.I,
)


def verificar(arq: Arquivo) -> Iterator[Achado]:
    if arq.texto is None:
        return
    if termina_em(arq.rel, ".vscode/tasks.json"):
        yield from _tarefas(arq, jsonc.ler(arq.texto))
    elif termina_em(arq.rel, ".vscode/settings.json"):
        dados = jsonc.ler(arq.texto)
        yield from _configuracoes(arq, dados) if isinstance(dados, dict) else _ilegivel(arq, dados)
    elif arq.nome.lower().endswith(".code-workspace"):
        dados = jsonc.ler(arq.texto)
        if not isinstance(dados, dict):
            yield from _tarefas(arq, None)
            return
        yield from _tarefas(arq, dados.get("tasks", {}))
        yield from _configuracoes(arq, dict_ou_vazio(dados.get("settings")))
    elif termina_em(arq.rel, ".vscode/extensions.json"):
        yield from _extensoes(arq, dict_ou_vazio(jsonc.ler(arq.texto)))
    elif arq.nome.lower() in ("devcontainer.json", ".devcontainer.json"):
        dados = jsonc.ler(arq.texto)
        yield from _devcontainer(arq, dados) if isinstance(dados, dict) else _ilegivel(arq, dados)
    elif CONFIG_JS.match(arq.nome) and (m := REDE_OU_PROCESSO.search(arq.texto)):
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        yield achado(
            Nivel.ATENCAO,
            arq,
            "arquivo de configuração que roda programa ou acessa a internet",
            "Extensões do editor (ESLint, Prettier, Tailwind…) carregam alguns desses arquivos sozinhas, e as "
            "ferramentas de build carregam todos. Configuração não tem motivo pra rodar programa nem baixar nada.",
            linha=linha,
            trecho=trecho,
        )


def _ilegivel(arq: Arquivo, dados: object) -> Iterator[Achado]:
    if dados is None:
        yield config_ilegivel(achado, arq, ("initializeCommand", "allowAutomaticTasks", "autoApprove"))


def _tarefas(arq: Arquivo, dados: object) -> Iterator[Achado]:
    if not isinstance(dados, dict):  # o editor é tolerante: arquivo "quebrado" pra scanner ainda pode rodar
        if m := AO_ABRIR.search(arq.texto):
            linha, trecho = linha_da_posicao(arq.texto, m.start())
            yield achado(
                Nivel.PERIGO,
                arq,
                "tarefa marcada pra rodar ao abrir a pasta (num arquivo quebrado)",
                AO_ABRIR_PORQUE + " E o arquivo está num formato que eu não consegui ler inteiro, o que "
                "é mais um motivo pra desconfiar.",
                linha=linha,
                trecho=trecho,
            )
        elif dados is None:
            yield from _ilegivel(arq, dados)
        return
    for tarefa in lista_ou_vazia(dados.get("tasks")):
        tarefa = dict_ou_vazio(tarefa)
        if str(dict_ou_vazio(tarefa.get("runOptions")).get("runOn", "")).lower() != "folderopen":
            continue
        rotulo = str(tarefa.get("label", "sem nome"))
        linha, _ = linha_do_termo(arq.texto, f'"{rotulo}"')
        comando = _comando_da_tarefa(tarefa)
        yield achado(
            Nivel.PERIGO,
            arq,
            f"tarefa que roda SOZINHA quando você abre a pasta: «{rotulo}»",
            AO_ABRIR_PORQUE + explica(comando),
            linha=linha,
            trecho=comando,
        )


def _comando_da_tarefa(tarefa: dict) -> str:
    partes = []
    for fonte in (tarefa, *(dict_ou_vazio(tarefa.get(so)) for so in ("linux", "osx", "windows"))):
        comando = fonte.get("command")
        comando = comando.get("value") if isinstance(comando, dict) else comando
        if isinstance(comando, str):
            argumentos = [a.get("value") if isinstance(a, dict) else a for a in lista_ou_vazia(fonte.get("args"))]
            partes.append(" ".join([comando, *map(str, argumentos)]))
    if tarefa.get("dependsOn"):
        partes.append(f"(antes, roda a tarefa: {como_texto(tarefa['dependsOn'])})")
    return " ; ".join(partes) or "(sem comando visível)"


def _achatar(config: dict) -> dict:
    """{"task": {"allowAutomaticTasks": "on"}} vira {"task.allowAutomaticTasks": "on"} (as duas formas valem)."""
    plano = {}
    for chave, valor in config.items():
        if isinstance(valor, dict) and "." not in chave and not chave.startswith("["):
            plano.update({f"{chave}.{k}": v for k, v in valor.items()})
        else:
            plano[chave] = valor
    return plano


def _configuracoes(arq: Arquivo, config: dict) -> Iterator[Achado]:
    for chave, valor in _achatar(config).items():
        k = chave.lower()
        linha, trecho = linha_do_termo(arq.texto, chave.rsplit(".", 1)[-1])
        if k == "task.allowautomatictasks" and valor in ("on", True):
            yield achado(
                Nivel.ATENCAO,
                arq,
                "tenta ligar as tarefas automáticas do editor",
                "Desde o VS Code 1.109 (fev/2026), essa opção só vale na SUA configuração, e o editor "
                "ignora quando ela vem do projeto. Mas editores baseados em versões antigas obedecem. Por "
                "que o projeto quer isso?",
                linha=linha,
                trecho=trecho,
            )
        elif k in IA_SEM_PERGUNTAR and valor not in (False, None, {}, []):
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"tenta liberar a IA do editor pra agir sem perguntar: {chave}",
                "Liga a aprovação automática de ferramentas ou servidores MCP do assistente de IA. "
                "Junto com uma instrução maliciosa no repositório, vira execução sem você ver.",
                linha=linha,
                trecho=trecho,
            )
        elif k.startswith(TERMINAL):
            yield achado(
                Nivel.ATENCAO,
                arq,
                "mexe no terminal do editor",
                "Muda o programa ou as variáveis do terminal que abre dentro do editor. Pode trocar o "
                "comando que você digita por outro.",
                linha=linha,
                trecho=trecho,
            )
        elif _aponta_programa(k) and isinstance(valor, str) and _dentro_do_projeto(valor):
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"aponta um programa DE DENTRO do projeto: {chave}",
                "O editor ou a extensão vai rodar esse arquivo achando que é a ferramenta de verdade "
                "(Python, Node, git…). Confira o que tem nele.",
                linha=linha,
                trecho=trecho,
            )
        elif re.fullmatch(r"python\.testing\.(pytest|unittest)enabled", k) and valor is True:
            yield achado(
                Nivel.ATENCAO,
                arq,
                "liga a descoberta automática de testes do Python",
                "Pra listar os testes, a extensão do Python importa os arquivos de teste e o conftest.py, "
                "o que executa o código deles sem você mandar.",
                linha=linha,
                trecho=trecho,
            )
        elif k == "files.exclude" and isinstance(valor, dict):
            escondidos = [p for p, ligado in valor.items() if ligado and not _exclusao_comum(p)]
            if escondidos:
                yield achado(
                    Nivel.ATENCAO,
                    arq,
                    "esconde arquivos da barra lateral do editor",
                    "Você não vai ver esses arquivos na lista do editor. Por que alguém esconderia isso de você?",
                    linha=linha,
                    trecho=", ".join(escondidos),
                )


def _aponta_programa(chave: str) -> bool:
    return chave.endswith(("path", "executable", "executablepath", ".tsdk", "nodepath", "interpreter"))


def _dentro_do_projeto(valor: str) -> bool:
    if PYTHON_DO_VENV.match(valor) or "node_modules/typescript/lib" in valor.replace("\\", "/"):
        return False  # o .venv do projeto e o TypeScript do projeto: normal
    if "${workspace" in valor:
        return True
    if valor.startswith(("/", "~", "\\")) or re.match(r"^[A-Za-z]:[\\/]", valor):
        return False  # caminho absoluto, no Linux, no Mac ou no Windows
    return valor.startswith(".") or "/" in valor or "\\" in valor


def _exclusao_comum(padrao: str) -> bool:
    base = padrao.removeprefix("**/").removesuffix("/**").strip("/")
    return base in EXCLUSOES_COMUNS


def _extensoes(arq: Arquivo, dados: dict) -> Iterator[Achado]:
    sugeridas = [s for s in lista_ou_vazia(dados.get("recommendations")) if isinstance(s, str)]
    if sugeridas:
        linha, trecho = linha_do_termo(arq.texto, '"recommendations"')
        yield achado(
            Nivel.INFO,
            arq,
            f"o editor vai sugerir instalar {len(sugeridas)} extensão(ões)",
            f"{', '.join(sugeridas[:5])}. Confira o autor de cada uma na loja: extensão clonada com nome "
            "quase igual ao de uma famosa é golpe comum.",
            linha=linha,
            trecho=trecho,
        )


def _devcontainer(arq: Arquivo, dados: dict) -> Iterator[Achado]:
    if "initializeCommand" in dados:
        comando = como_texto(dados["initializeCommand"])
        linha, _ = linha_do_termo(arq.texto, '"initializeCommand"')
        yield achado(
            Nivel.PERIGO if sinais(comando) else Nivel.ATENCAO,
            arq,
            "comando que roda no SEU computador antes do container subir",
            "Quando você manda abrir o projeto no container, os outros comandos do devcontainer rodam lá "
            "dentro (o lugar certo). Esse aqui roda fora, na sua máquina, com o seu usuário." + explica(comando),
            linha=linha,
            trecho=comando,
        )
    montagens = " ".join(como_texto(dados.get(k)) for k in ("mounts", "runArgs", "workspaceMount"))
    if (m := CONTAINER_SENSIVEL.search(montagens)) or dados.get("privileged") is True:
        linha, _ = linha_do_termo(arq.texto, m.group() if m else '"privileged"')
        yield achado(
            Nivel.ATENCAO,
            arq,
            "o container enxerga partes sensíveis do seu computador",
            "Monta sua pasta pessoal, suas chaves SSH ou o Docker da máquina dentro do container, ou roda "
            "em modo privilegiado. Aí o container deixa de ser uma caixa isolada.",
            linha=linha,
            trecho=m.group() if m else "privileged: true",
        )
