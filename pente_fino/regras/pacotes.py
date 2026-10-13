"""Pacotes: o que roda quando VOCÊ der o comando de instalar ou compilar (npm, pnpm, yarn, pip, cargo…).

Não roda sozinho ao abrir a pasta, mas é a segunda coisa que todo teste técnico pede: "rode npm install".
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urlparse

from pente_fino import jsonc
from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import Arquivo, dict_ou_vazio, linha_da_posicao, linha_do_termo, termina_em
from pente_fino.comandos import como_texto, explica, sinais
from pente_fino.regras.comum import config_ilegivel

achado = achador("pacotes")

# scripts que o npm roda sozinho no `npm install` (sem você pedir por nome)
CICLO_NPM = (
    "preinstall",
    "install",
    "postinstall",
    "preprepare",
    "prepare",
    "postprepare",
    "prepublish",
    "dependencies",
)
SECOES_NPM = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
FORA_DO_REGISTRO = re.compile(
    r"^(https?:|git(\+\w+)?:|git@|github:|gitlab:|bitbucket:|gist:)|^[\w.-]+/[\w.-]+(#.*)?$|\.(tgz|tar\.gz|zip)$"
)
CHAMA_SCRIPT = re.compile(r"\b(?:npm\s+run(?:-script)?|pnpm(?:\s+run)?|yarn(?:\s+run)?|bun\s+run)\s+([\w:.-]+)")
REGISTROS = {"registry.npmjs.org", "registry.yarnpkg.com"}
REDE_PY = re.compile(r"\b(urlopen|urlretrieve|requests\.(get|post)|http\.client\.\w+|socket\.socket|b64decode)\s*\(")
INDICE_PY = re.compile(r"^[ \t]*(--index-url|-i|--extra-index-url|--find-links|-f)(\s*=\s*|\s+)(\S+)", re.M)
LINK_PY = re.compile(r"^(?![ \t]*(#|--?\S*index-url|-i\s|--find-links|-f\s))[^\n]*?(git\+|https?://)", re.M)
CARGO = re.compile(
    r"\b(runner|rustc-wrapper|rustc-workspace-wrapper|rustc|rustdoc|linker)\b\s*=\s*(\"[^\"\n]*\"|'[^'\n]*'|\[[^\]\n]*\])"
    r"|-C\s*linker=\S+"
)


def verificar(arq: Arquivo) -> Iterator[Achado]:
    if arq.texto is None:
        return
    nome = arq.nome.lower()
    if nome == "package.json":
        dados = jsonc.ler(arq.texto)
        if isinstance(dados, dict):
            yield from _package_json(arq, dados)
        else:
            yield config_ilegivel(achado, arq, CICLO_NPM)
    elif nome == ".npmrc":
        yield from _npmrc(arq)
    elif nome in (".yarnrc.yml", ".yarnrc.yaml"):
        yield from _yarnrc(arq)
    elif nome in (".pnpmfile.cjs", ".pnpmfile.mjs", "pnpmfile.cjs"):
        yield achado(
            Nivel.ATENCAO,
            arq,
            "o pnpm roda este arquivo em todo `pnpm install`",
            "É código JavaScript que o pnpm carrega pra mexer na instalação. Leia antes de instalar.",
        )
    elif nome in (".npm-extension.mjs", ".npm-extension.cjs", ".npm-extension.js"):
        yield achado(
            Nivel.ATENCAO,
            arq,
            "o npm 12 roda este arquivo no `npm install`",
            "É uma extensão do npm: código que roda durante a instalação. O `--ignore-scripts` desliga.",
        )
    elif nome == "binding.gyp":
        yield achado(
            Nivel.ATENCAO,
            arq,
            "o `npm install` compila código nativo (node-gyp)",
            "Com esse arquivo, o npm roda o node-gyp, que executa os comandos de compilação descritos "
            "aqui. O `--ignore-scripts` desliga.",
        )
    elif nome in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock"):
        yield from _lockfile(arq)
    elif nome == "setup.py":
        yield from _setup_py(arq)
    elif nome == "pyproject.toml":
        yield from _pyproject(arq)
    elif re.fullmatch(r"(requirements|constraints).*\.(txt|in)", nome) or termina_em(
        arq.rel.rsplit("/", 1)[0], "requirements"
    ):
        yield from _requirements(arq)
    elif nome == "build.rs":
        yield achado(
            Nivel.ATENCAO,
            arq,
            "script de compilação do Rust (build.rs)",
            "O `cargo build` roda esse arquivo antes de compilar, e o rust-analyzer (a extensão de Rust do "
            "editor) roda sozinho ao abrir o projeto. É comum, mas é código rodando na sua máquina: leia.",
        )
    elif termina_em(arq.rel, ".cargo/config.toml", ".cargo/config"):
        yield from _cargo_config(arq)
    elif nome == "composer.json" and re.search(r'"(pre|post)-(install|update|autoload-dump)-cmd"', arq.texto):
        linha, trecho = linha_do_termo(arq.texto, "-cmd")
        yield achado(
            Nivel.ATENCAO,
            arq,
            "script que roda no `composer install`",
            "O Composer roda esses comandos sozinho durante a instalação.",
            linha=linha,
            trecho=trecho,
        )
    elif nome == ".envrc":
        yield achado(
            Nivel.ATENCAO,
            arq,
            "script do direnv: roda ao entrar na pasta pelo terminal",
            "Se você usa direnv e já liberou essa pasta (`direnv allow`), o terminal roda esse arquivo "
            "toda vez que você entra nela.",
        )


def _package_json(arq: Arquivo, pacote: dict) -> Iterator[Achado]:
    scripts = dict_ou_vazio(pacote.get("scripts"))
    for nome, valor in scripts.items():
        comando = _com_os_chamados(como_texto(valor), scripts)
        linha, _ = linha_do_termo(arq.texto, f'"{nome}"')
        if nome in CICLO_NPM:
            yield achado(
                Nivel.PERIGO if sinais(comando) else Nivel.ATENCAO,
                arq,
                f"script «{nome}»: roda sozinho no `npm install`",
                "Você só pediu pra instalar as dependências, e o npm roda isso junto (o npm 12 bloqueia script de "
                "dependência, mas o do próprio projeto continua rodando). Pra instalar sem rodar scripts: "
                "`npm install --ignore-scripts`." + explica(comando),
                linha=linha,
                trecho=comando,
            )
        elif sinais(comando):
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"script «{nome}» com cara de golpe (roda no `npm run {nome}`)",
                "Não roda sozinho, mas roda quando você seguir o README e mandar rodar." + explica(comando),
                linha=linha,
                trecho=comando,
            )
    dependencias = [(s, n, v) for s in SECOES_NPM for n, v in dict_ou_vazio(pacote.get(s)).items()]
    for secao in ("overrides", "resolutions"):
        dependencias += [(secao, n, v) for n, v in dict_ou_vazio(pacote.get(secao)).items()]
    dependencias += [
        ("pnpm.overrides", n, v) for n, v in dict_ou_vazio(dict_ou_vazio(pacote.get("pnpm")).get("overrides")).items()
    ]
    for secao, nome, versao in dependencias:
        if isinstance(versao, str) and FORA_DO_REGISTRO.search(versao.strip()):
            linha, trecho = linha_do_termo(arq.texto, f'"{nome}"')
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"dependência «{nome}» vem de FORA do registro do npm ({secao})",
                "Baixa direto de um link, repositório ou arquivo, sem a checagem de malware do registro, e "
                "o dono do link troca o código quando quiser. O npm 12 bloqueia isso por padrão; versões "
                "antigas, pnpm e yarn não.",
                linha=linha,
                trecho=trecho,
            )
    if pacote.get("allowScripts"):
        linha, trecho = linha_do_termo(arq.texto, '"allowScripts"')
        yield achado(
            Nivel.ATENCAO,
            arq,
            "o projeto libera scripts de dependências (allowScripts)",
            "No npm 12, script de dependência fica bloqueado até alguém aprovar. Aqui o próprio projeto "
            "já vem aprovando. Confira quais.",
            linha=linha,
            trecho=trecho,
        )


def _com_os_chamados(comando: str, scripts: dict) -> str:
    """`npm run setup` dentro de um script roda o script `setup` (e o `presetup`/`postsetup`): junta tudo."""
    extras = []
    for m in CHAMA_SCRIPT.finditer(comando):
        nome = m.group(1)
        extras += [como_texto(scripts.get(n)) for n in (f"pre{nome}", nome, f"post{nome}") if scripts.get(n)]
    return " ; ".join([comando, *extras]) if extras else comando


def _npmrc(arq: Arquivo) -> Iterator[Achado]:
    for m in re.finditer(r"^[ \t]*([@\w./:-]*?)[ \t]*=[ \t]*([^\n]*)$", arq.texto, re.M):
        chave, valor = m.group(1).lower(), m.group(2).strip()
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        if chave.endswith("registry") and (urlparse(valor).hostname or "") not in REGISTROS:
            yield achado(
                Nivel.ATENCAO,
                arq,
                "troca o registro de onde o npm baixa os pacotes",
                "Os pacotes deixam de vir do npm oficial e passam a vir desse endereço.",
                linha=linha,
                trecho=trecho,
            )
        elif chave in ("script-shell", "git"):
            yield achado(
                Nivel.PERIGO,
                arq,
                f"troca o programa que o npm chama ({chave})",
                "O npm passa a rodar ESSE programa no lugar do shell ou do git, inclusive durante o "
                "`npm install`, e o `--ignore-scripts` não impede.",
                linha=linha,
                trecho=trecho,
            )
        elif chave == "node-options" and re.search(r"(--require|-r|--import|--loader|--experimental-loader)\b", valor):
            yield achado(
                Nivel.PERIGO,
                arq,
                "faz o Node carregar um arquivo antes de tudo (node-options)",
                "Todo script que o npm rodar vai carregar esse arquivo primeiro.",
                linha=linha,
                trecho=trecho,
            )
        elif chave in ("allow-git", "allow-remote") and valor.lower() == "all":
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"libera dependência de fora do registro ({chave}=all)",
                "O npm 12 bloqueia dependência de git e de link por padrão. O projeto está desligando essa proteção.",
                linha=linha,
                trecho=trecho,
            )


def _yarnrc(arq: Arquivo) -> Iterator[Achado]:
    for m in re.finditer(r"^[ \t]*(yarnPath|plugins|npmRegistryServer)[ \t]*:[ \t]*([^\n]*)$", arq.texto, re.M):
        chave, valor = m.group(1), m.group(2).strip().strip("\"'")
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        if chave == "npmRegistryServer" and (urlparse(valor).hostname or "") in REGISTROS:
            continue
        estranho = chave == "yarnPath" and not valor.startswith(".yarn/releases/")
        yield achado(
            Nivel.PERIGO if estranho else Nivel.ATENCAO,
            arq,
            f"o yarn usa {chave} do projeto",
            "Com `yarnPath`, o yarn roda o arquivo apontado em TODO comando yarn; com `plugins`, carrega "
            "código do projeto; com `npmRegistryServer`, baixa pacotes de outro lugar."
            + (" E esse yarnPath nem está na pasta padrão (.yarn/releases)." if estranho else ""),
            linha=linha,
            trecho=trecho,
        )


def _lockfile(arq: Arquivo) -> Iterator[Achado]:
    hosts, primeira = set(), 0
    for m in re.finditer(r'"?resolved"?[ \t]*:?[ \t]*"(https?://[^"\s]+)"', arq.texto):
        host = urlparse(m.group(1)).hostname or ""
        if host not in REGISTROS:
            primeira = primeira if hosts else m.start()
            hosts.add(host)
    if hosts:
        linha, trecho = linha_da_posicao(arq.texto, primeira)
        yield achado(
            Nivel.ATENCAO,
            arq,
            f"o lockfile baixa pacotes de fora do registro ({', '.join(sorted(hosts)[:3])})",
            "O arquivo de travas diz de onde cada pacote vem, e quase ninguém revisa. Um endereço "
            "trocado aqui instala outro código com o mesmo nome.",
            linha=linha,
            trecho=trecho,
        )


def _setup_py(arq: Arquivo) -> Iterator[Achado]:
    m = REDE_PY.search(arq.texto)
    linha, trecho = linha_da_posicao(arq.texto, m.start()) if m else (None, "")
    yield achado(
        Nivel.PERIGO if m else Nivel.ATENCAO,
        arq,
        "setup.py que acessa a internet ou decodifica texto escondido"
        if m
        else "setup.py: roda inteiro no `pip install .`",
        "O `pip install .` executa esse arquivo inteiro na sua máquina, igual ao postinstall do npm."
        + (
            " E instalador não tem motivo pra baixar coisa nem decodificar código." if m else " Leia antes de instalar."
        ),
        linha=linha,
        trecho=trecho,
    )


def _pyproject(arq: Arquivo) -> Iterator[Achado]:
    if m := re.search(r"^[ \t]*backend-path[ \t]*=", arq.texto, re.M):
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        yield achado(
            Nivel.ATENCAO,
            arq,
            "o pip usa código DE DENTRO do projeto pra instalar",
            "`pip install .` vai rodar o construtor que está no próprio repositório, não um oficial.",
            linha=linha,
            trecho=trecho,
        )
    bloco = re.search(r"^\[build-system\][^\[]*", arq.texto, re.M)
    if bloco and (m := re.search(r"(git\+|https?://|file:)", bloco.group())):
        linha, trecho = linha_da_posicao(arq.texto, bloco.start() + m.start())
        yield achado(
            Nivel.ATENCAO,
            arq,
            "o construtor do pacote vem de um link",
            "O pip baixa e roda esse construtor no `pip install .`, sem passar pelo PyPI.",
            linha=linha,
            trecho=trecho,
        )


def _requirements(arq: Arquivo) -> Iterator[Achado]:
    for m in INDICE_PY.finditer(arq.texto):
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        extra = m.group(1) == "--extra-index-url"
        yield achado(
            Nivel.ATENCAO,
            arq,
            "manda o pip procurar pacote TAMBÉM fora do PyPI" if extra else "troca o lugar de onde o pip baixa",
            "Com um índice extra, um pacote com o mesmo nome de um privado pode vir de lá (confusão de dependência)."
            if extra
            else "Os pacotes deixam de vir do PyPI e passam a vir desse endereço.",
            linha=linha,
            trecho=trecho,
        )
    for m in LINK_PY.finditer(arq.texto):
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        yield achado(
            Nivel.ATENCAO,
            arq,
            "dependência baixada direto de um link",
            "Não passa pelo PyPI. Quem controla o link controla o código.",
            linha=linha,
            trecho=trecho,
        )


def _cargo_config(arq: Arquivo) -> Iterator[Achado]:
    for m in CARGO.finditer(arq.texto):
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        quando = "`cargo run`/`cargo test`" if m.group(1) == "runner" else "`cargo build` (e o rust-analyzer)"
        yield achado(
            Nivel.PERIGO if sinais(m.group()) else Nivel.ATENCAO,
            arq,
            f"o cargo roda outro programa no lugar do normal ({m.group(1) or 'linker'})",
            f"Esse programa roda a cada {quando}." + explica(m.group()),
            linha=linha,
            trecho=trecho,
        )
    if m := re.search(r"^[ \t]*replace-with[ \t]*=", arq.texto, re.M):
        linha, trecho = linha_da_posicao(arq.texto, m.start())
        yield achado(
            Nivel.ATENCAO,
            arq,
            "troca o lugar de onde o cargo baixa as dependências",
            "As dependências deixam de vir do crates.io oficial.",
            linha=linha,
            trecho=trecho,
        )
