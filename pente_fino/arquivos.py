"""Ler a pasta SEM executar nada: lista os arquivos, separa texto de binário e responde perguntas sobre eles.

Cuidados que um repositório malicioso tenta explorar:
- atalho (symlink) pra FORA do projeto nunca é seguido; atalho pra DENTRO é lido com o nome do atalho
  (porque é assim que o editor vê);
- só arquivo comum é aberto (um FIFO travaria a leitura) e no máximo LIMITE bytes;
- pasta ou arquivo que não dá pra ler vira aviso, nunca silêncio.
"""

from __future__ import annotations

import codecs
import os
import re
import stat
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from functools import cached_property
from pathlib import Path, PurePosixPath

LIMITE = 5 * 1024 * 1024  # de cada arquivo, só os primeiros 5 MB são lidos
# pastas baixadas (dependências) ou geradas (build): puladas e avisadas, a não ser com --tudo
PESADAS = {
    "node_modules", ".venv", "venv", "target", ".tox", ".next", ".nuxt", ".svelte-kit", ".turbo", ".angular",
    ".expo", ".dart_tool", ".gradle", "pods", "dist", "build", "out", "coverage", "ephemeral",
}  # fmt: skip
PESADAS_CAMINHO = (".claude/worktrees",)  # cópias do projeto que o Claude Code cria pra trabalhar em paralelo
TETO_DE_PASTAS = 50_000
CACHES = {"__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}  # puladas sem aviso (com --tudo, não)

CODIGO = {
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx", ".vue", ".svelte", ".astro", ".html", ".htm",
    ".svg", ".py", ".pyw", ".ipynb", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".bat", ".cmd", ".vbs",
    ".hta", ".rb", ".php", ".go", ".rs", ".java", ".kt", ".kts", ".gradle", ".groovy", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".cs", ".lua", ".pl", ".swift", ".dart", ".json", ".jsonc", ".toml", ".yaml", ".yml", ".xml",
}  # fmt: skip
SEM_EXTENSAO = {"makefile", "dockerfile", "jenkinsfile", "rakefile", "gemfile", "vagrantfile", "justfile"}
TEXTO = CODIGO | {".md", ".mdc", ".txt", ".rst", ".ini", ".cfg", ".conf", ".env", ".css", ".scss", ".csv", ".lock"}
GERADOS = ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", ".map")

# arquivos que a IA do editor lê junto com o seu pedido (e costuma seguir)
INSTRUCOES_DE_IA = {
    "claude.md", "claude.local.md", "agents.md", "agent.md", "gemini.md", "qwen.md", "crush.md", "conventions.md",
    ".cursorrules", ".windsurfrules", ".clinerules", ".roorules", ".goosehints", ".rules", "copilot-instructions.md",
    "skill.md", "guidelines.md",
}  # fmt: skip
PASTAS_DE_INSTRUCAO = (
    ".cursor/rules/",
    ".cursor/commands/",
    ".claude/commands/",
    ".claude/agents/",
    ".claude/rules/",
    ".claude/output-styles/",
    ".claude/skills/",
    ".github/instructions/",
    ".github/prompts/",
    ".github/agents/",
    ".github/chatmodes/",
    ".windsurf/rules/",
    ".clinerules/",
    ".roo/rules/",
    ".kiro/steering/",
    ".junie/",
    ".amazonq/rules/",
    ".continue/rules/",
    ".trae/rules/",
    ".augment/rules/",
)
# arquivos que editor, agente ou instalador obedecem: atalho, tamanho ou formato estranho neles pesa mais
PASTAS_SENSIVEIS = (
    ".vscode/",
    ".claude/",
    ".cursor/",
    ".gemini/",
    ".codex/",
    ".github/hooks/",
    ".devcontainer/",
    ".cargo/",
    ".idea/",
    ".zed/",
    ".qwen/",
    ".kiro/",
    ".roo/",
    ".windsurf/",
    ".junie/",
    ".continue/",
    ".amazonq/",
    ".husky/",
)
NOMES_SENSIVEIS = {
    "package.json", ".npmrc", ".yarnrc.yml", ".mcp.json", "mcp.json", ".devcontainer.json", "devcontainer.json",
    "setup.py", "pyproject.toml", "build.rs", ".pnpmfile.cjs", "binding.gyp", ".envrc", "opencode.json", ".git",
}  # fmt: skip
IMPORTA = re.compile(r"(?:^|\s)@((?:\.{1,2}/)?[\w.-]+(?:/[\w.-]+)*\.(?:md|mdc|txt))\b", re.M)


@dataclass(eq=False)
class Arquivo:
    raiz: Path  # a pasta que está sendo varrida
    rel: str  # caminho relativo, sempre com "/" (é o nome que aparece no relatório)
    link_para: str | None = None  # se for atalho: pra onde aponta (como está escrito no atalho)
    ler_de: Path | None = None  # atalho pra dentro do projeto: o arquivo de verdade que é lido
    especial: bool = False  # FIFO, socket, dispositivo: nunca é aberto
    varredura: Varredura | None = field(default=None, repr=False)

    @property
    def nome(self) -> str:
        return self.rel.rsplit("/", 1)[-1]

    @property
    def extensao(self) -> str:
        return PurePosixPath(self.nome.lower()).suffix

    @property
    def atalho_pra_fora(self) -> bool:
        return self.link_para is not None and self.ler_de is None

    @cached_property
    def dados(self) -> bytes | None:
        """Os primeiros LIMITE + 1 bytes (o +1 diz se passou do limite), ou None se não deu pra ler."""
        if self.atalho_pra_fora or self.especial:
            return b""
        return _ler_seguro(self.ler_de or self.raiz / self.rel)

    @property
    def ilegivel(self) -> bool:
        return self.dados is None

    @property
    def grande_demais(self) -> bool:
        return self.dados is not None and len(self.dados) > LIMITE

    @property
    def deveria_ser_texto(self) -> bool:
        nome = self.nome.lower()
        return self.extensao in TEXTO or nome in SEM_EXTENSAO or nome.startswith(".") or self.eh_instrucao_de_ia

    @property
    def tem_byte_nulo(self) -> bool:
        return bool(self.dados) and b"\0" in self.dados and not self.dados.startswith(_BOMS_UTF16)

    @cached_property
    def texto(self) -> str | None:
        """O conteúdo como texto (só os primeiros LIMITE bytes), ou None se for binário de verdade."""
        if self.dados is None or self.atalho_pra_fora or self.especial:
            return None  # o que eu não abri não tem texto
        dados = self.dados[:LIMITE]
        if dados.startswith(_BOMS_UTF16):
            return dados.decode("utf-16", errors="replace")
        if b"\0" in dados[:8192] and not self.deveria_ser_texto:
            return None
        # bytes inválidos viram "?" (como o editor faz), em vez de trocar a leitura inteira de formato
        texto = dados.decode("utf-8-sig", errors="replace")
        if not self.deveria_ser_texto and texto.count(chr(0xFFFD)) > len(texto) // 100:
            return None  # mais de 1% de bytes inválidos num arquivo que nem é de texto: é binário (imagem, .ai…)
        return texto

    @property
    def eh_codigo(self) -> bool:
        if self.extensao in CODIGO or self.nome.lower() in SEM_EXTENSAO:
            return True
        return self.extensao == "" and (self.texto or "").startswith("#!")

    @property
    def eh_gerado(self) -> bool:
        """Arquivo que ferramenta escreve (lockfile, mapa de código): ninguém lê, mas também ninguém edita."""
        return self.nome.lower().endswith(GERADOS)

    @cached_property
    def eh_minificado(self) -> bool:
        if ".min." in self.nome.lower():
            return True
        texto = self.texto or ""
        return len(texto) > 2000 and len(texto) / (texto.count("\n") + 1) > 300  # linhas enormes, em média

    @property
    def eh_instrucao_de_ia(self) -> bool:
        importado = self.varredura is not None and self.rel in self.varredura.importados_por_instrucao
        return self.instrucao_pelo_nome or importado

    @property
    def instrucao_pelo_nome(self) -> bool:
        rel = "/" + self.rel.lower()
        return (
            self.nome.lower() in INSTRUCOES_DE_IA
            or rel.endswith((".instructions.md", ".prompt.md", ".agent.md", ".chatmode.md"))
            or any(f"/{pasta}" in rel for pasta in PASTAS_DE_INSTRUCAO)
        )

    @property
    def eh_sensivel(self) -> bool:
        """Arquivo que editor, agente, git ou instalador obedecem."""
        rel = "/" + self.rel.lower()
        return (
            self.nome.lower() in NOMES_SENSIVEIS
            or self.nome.lower().endswith(".code-workspace")
            or any(f"/{pasta}" in rel for pasta in PASTAS_SENSIVEIS)
            or self.pasta_do_git is not None
            or self.eh_instrucao_de_ia
        )

    @property
    def pasta_do_git(self) -> str | None:
        """Se o arquivo está dentro de uma pasta do git (.git, submódulo, gitdir:), o caminho dentro dela."""
        return self.varredura.dentro_do_git(self.rel) if self.varredura else None

    @property
    def ignorado_pelo_git(self) -> bool:
        return bool(self.varredura) and self.varredura.ignorado(self.rel)


_BOMS_UTF16 = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)


def _ler_seguro(caminho: Path) -> bytes | None:
    """Abre SEM seguir atalho e SEM esperar (FIFO), confere que é arquivo comum e lê no máximo LIMITE + 1."""
    modo = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        descritor = os.open(caminho, modo)
    except OSError:
        return None
    with os.fdopen(descritor, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            return None
        try:
            return f.read(LIMITE + 1)
        except OSError:
            return None


@dataclass
class Varredura:
    raiz: Path
    arquivos: list[Arquivo] = field(default_factory=list)
    puladas: list[str] = field(default_factory=list)  # pastas pesadas que não foram varridas
    sem_acesso: list[str] = field(default_factory=list)  # pastas e arquivos que não deu pra abrir
    atalhos_de_pasta: list[tuple[str, str]] = field(default_factory=list)  # (atalho, destino) pra dentro do projeto
    pastas_git: set[str] = field(default_factory=set)  # pastas que o git usa como "o .git" (rel)
    _gitignores: dict[str, list[tuple[str, bool, bool, bool]]] = field(default_factory=dict, repr=False)

    @cached_property
    def por_caminho(self) -> dict[str, Arquivo]:
        return {a.rel: a for a in self.arquivos}

    @cached_property
    def importados_por_instrucao(self) -> set[str]:
        """Arquivos puxados com @caminho de dentro de um CLAUDE.md/AGENTS.md: a IA lê o conteúdo deles também."""
        importados = set()
        for arq in self.arquivos:
            if arq.instrucao_pelo_nome and arq.texto:
                pasta = PurePosixPath(arq.rel).parent
                for m in IMPORTA.finditer(arq.texto[:200_000]):
                    importados.add(os.path.normpath(pasta / m.group(1)).replace(os.sep, "/"))
        return importados

    def dentro_do_git(self, rel: str) -> str | None:
        partes = rel.split("/")
        for i in range(len(partes) - 1, 0, -1):
            pasta = "/".join(partes[:i])
            if partes[i - 1].lower() == ".git" or pasta in self.pastas_git:
                return "/".join(partes[i:])
        return None

    def ignorado(self, rel: str) -> bool:
        """O .gitignore manda ignorar? Segue o git no essencial: ordem, negação (!), âncora (/) e pasta (dir/)."""
        partes = rel.split("/")
        resposta = False
        for i in range(len(partes)):  # do .gitignore da raiz até o da pasta do arquivo
            pasta = "/".join(partes[:i])
            for padrao, nega, so_pasta, ancorado in self._regras_do_gitignore(pasta):
                for j in range(i, len(partes)):  # o próprio arquivo e cada pasta acima dele
                    eh_pasta = j < len(partes) - 1
                    caminho = "/".join(partes[i : j + 1])
                    alvo = caminho if ancorado else partes[j]
                    if (eh_pasta or not so_pasta) and fnmatchcase(alvo, padrao):
                        resposta = not nega
        return resposta

    def _regras_do_gitignore(self, pasta: str) -> list[tuple[str, bool, bool, bool]]:
        if pasta not in self._gitignores:
            arquivo = self.por_caminho.get(f"{pasta}/.gitignore" if pasta else ".gitignore")
            regras = []
            for linha in ((arquivo.texto or "") if arquivo else "").splitlines():
                linha = linha.strip()
                if not linha or linha.startswith("#"):
                    continue
                nega = linha.startswith("!")
                linha = linha.removeprefix("!")
                so_pasta = linha.endswith("/")
                linha = linha.rstrip("/")
                ancorado = "/" in linha and not linha.startswith("**/")  # "/x" ou "a/b": só a partir desta pasta
                regras.append((linha.lstrip("/").removeprefix("**/"), nega, so_pasta, ancorado))
            self._gitignores[pasta] = regras
        return self._gitignores[pasta]


def listar(pasta: Path, tudo: bool = False) -> Varredura:
    """Todos os arquivos da pasta, em ordem. Atalho pra fora vira um Arquivo com `link_para` (e não é lido)."""
    raiz = Path(pasta)
    real_da_raiz = Path(os.path.realpath(raiz))
    varredura = Varredura(raiz)
    # cada item: (pasta, nome dela no relatório, pastas reais acima dela). Atalho que volta pra uma pasta
    # de cima (círculo) não é seguido, e há um teto de pastas: atalhos em cascata não travam a varredura.
    pilha: list[tuple[Path, str, frozenset[str]]] = [(raiz, "", frozenset())]
    pastas_vistas = 0
    while pilha:
        real, rel, acima = pilha.pop()
        real_dela = os.path.realpath(real)
        if real_dela in acima:
            continue
        pastas_vistas += 1
        if pastas_vistas > TETO_DE_PASTAS:
            varredura.sem_acesso.append(f"{rel or '.'} (parei: mais de {TETO_DE_PASTAS} pastas)")
            break
        acima = acima | {real_dela}
        try:
            entradas = sorted(os.scandir(real), key=lambda e: e.name, reverse=True)
        except OSError:
            varredura.sem_acesso.append(rel or ".")
            continue
        for entrada in entradas:
            rel_dela = f"{rel}/{entrada.name}" if rel else entrada.name
            if not _interessa(rel_dela, varredura):
                continue
            try:
                info = os.lstat(entrada.path)
            except OSError:
                varredura.sem_acesso.append(rel_dela)
                continue
            if stat.S_ISLNK(info.st_mode):
                _atalho(varredura, entrada.path, rel_dela, real_da_raiz, pilha, acima)
            elif stat.S_ISDIR(info.st_mode):
                nome = entrada.name.lower()
                if nome in CACHES and not tudo:
                    continue
                if not tudo and (nome in PESADAS or rel_dela.lower().endswith(PESADAS_CAMINHO)):
                    varredura.puladas.append(rel_dela)
                    continue
                pilha.append((Path(entrada.path), rel_dela, acima))
            else:
                varredura.arquivos.append(Arquivo(raiz, rel_dela, especial=not stat.S_ISREG(info.st_mode)))
    varredura.arquivos.sort(key=lambda a: a.rel)
    varredura.puladas.sort()
    for arquivo in varredura.arquivos:
        arquivo.varredura = varredura
    _ponteiros_do_git(varredura, real_da_raiz)
    return varredura


def _interessa(rel: str, varredura: Varredura) -> bool:
    """Dentro de uma pasta do git, só interessa o que o git EXECUTA: config, hooks e submódulos."""
    dentro = varredura.dentro_do_git(rel)
    if dentro is None:
        return True
    partes = dentro.lower().split("/")
    if partes[0] == "modules":  # .git/modules/<submódulo>/... é outra pasta do git inteira
        partes = partes[2:] if len(partes) > 2 else []
    return not partes or partes[0] in ("config", "config.worktree", "hooks", "modules")


def _atalho(varredura: Varredura, caminho: str, rel: str, real_da_raiz: Path, pilha: list, acima: frozenset) -> None:
    try:
        escrito = os.readlink(caminho)
        alvo = Path(os.path.realpath(caminho))
    except (OSError, RuntimeError):
        varredura.sem_acesso.append(rel)
        return
    dentro = alvo == real_da_raiz or real_da_raiz in alvo.parents
    if dentro and alvo.is_dir():
        varredura.atalhos_de_pasta.append((rel, escrito))
        pilha.append((alvo, rel, acima))  # pasta-atalho pra dentro: varre o conteúdo com o nome do atalho
    elif dentro and alvo.is_file():
        varredura.arquivos.append(Arquivo(varredura.raiz, rel, link_para=escrito, ler_de=alvo))
    else:
        varredura.arquivos.append(Arquivo(varredura.raiz, rel, link_para=escrito))


def _ponteiros_do_git(varredura: Varredura, real_da_raiz: Path) -> None:
    """Um arquivo `.git` com "gitdir: caminho" diz ao git que a pasta dele está em outro lugar."""
    for arquivo in varredura.arquivos:
        if arquivo.nome.lower() != ".git" or not (arquivo.texto or "").lower().startswith("gitdir:"):
            continue
        destino = (arquivo.texto or "").split(":", 1)[1].strip()
        pasta = PurePosixPath(arquivo.rel).parent
        alvo = Path(os.path.realpath(varredura.raiz / pasta / destino))
        if real_da_raiz in alvo.parents:
            varredura.pastas_git.add(alvo.relative_to(real_da_raiz).as_posix())


def termina_em(rel: str, *alvos: str) -> bool:
    """O arquivo é um desses? Sem ligar pra maiúscula (no Mac e no Windows, `.VSCode` também vale)."""
    rel = rel.lower()
    return any(rel == alvo or rel.endswith("/" + alvo) for alvo in alvos)


def linha_da_posicao(texto: str, posicao: int) -> tuple[int, str]:
    """Número da linha (1, 2, …) e o conteúdo da linha onde fica a `posicao`."""
    posicao = max(posicao, 0)
    comeco = texto.rfind("\n", 0, posicao) + 1
    fim = texto.find("\n", posicao)
    return texto.count("\n", 0, posicao) + 1, texto[comeco : None if fim < 0 else fim].strip()


def linha_do_termo(texto: str, termo: str) -> tuple[int | None, str]:
    """Linha e conteúdo da primeira vez que `termo` aparece, sem ligar pra maiúscula (ou None, '')."""
    posicao = texto.lower().find(termo.lower())
    return linha_da_posicao(texto, posicao) if posicao >= 0 else (None, "")


def dict_ou_vazio(valor: object) -> dict:
    return valor if isinstance(valor, dict) else {}


def lista_ou_vazia(valor: object) -> list:
    return valor if isinstance(valor, list) else []
