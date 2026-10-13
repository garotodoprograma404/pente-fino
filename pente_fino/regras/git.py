"""Git: o que o próprio git EXECUTA. Só aparece quando a pasta veio pronta (zip, pendrive, pasta
compartilhada), porque `git clone` não traz nem a config nem os hooks de quem fez o repositório."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import PurePosixPath

from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import Arquivo

achado = achador("git")

VEIO_PRONTA = " Se não foi você que configurou, isso veio junto com a pasta copiada pronta (o `git clone` não traz)."
CABECALHO = re.compile(r'^\s*\[\s*([A-Za-z0-9.-]+)\s*(?:"((?:[^"\\]|\\.)*)")?\s*\]')
CHAVE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s*(?:=(.*))?$")
VERDADEIRO_OU_FALSO = {"true", "false", "yes", "no", "on", "off", "1", "0", ""}
AJUDANTES_DE_SENHA = {"store", "cache", "manager", "manager-core", "osxkeychain", "libsecret", "wincred", ""}
LFS = {"git-lfs clean -- %f", "git-lfs smudge -- %f", "git-lfs filter-process"}  # o Git LFS se instala assim

# (seção, chave) -> quando o git roda esse valor como programa. "*" = qualquer chave da seção.
EXECUTA = {
    ("core", "fsmonitor"): "a cada `git status`. Editores com git embutido rodam `git status` sozinhos assim que "
    "a pasta é aberta (e confiada)",
    ("core", "hookspath"): "nos scripts dessa pasta, que viram os hooks: a cada commit, checkout, merge…",
    ("hook", "command"): "como hook configurado (Git 2.54 ou mais novo), no evento indicado",
    ("core", "sshcommand"): "no lugar do ssh, a cada push, pull ou fetch",
    ("core", "gitproxy"): "a cada conversa com servidor pelo protocolo git://",
    ("core", "askpass"): "toda vez que o git pede senha num endereço http(s)",
    ("core", "pager"): "toda vez que o git mostra uma saída longa no terminal (log, diff)",
    ("pager", "*"): "toda vez que esse comando do git mostra saída no terminal",
    ("core", "editor"): "toda vez que o git abre um editor (commit, tag, rebase)",
    ("sequence", "editor"): "no `git rebase -i`",
    ("core", "alternaterefscommand"): "a cada fetch ou push",
    ("diff", "external"): "a cada `git diff`",
    ("diff", "textconv"): "no `git diff` dos arquivos que o .gitattributes ligar a esse conversor",
    ("diff", "command"): "no `git diff` dos arquivos que o .gitattributes ligar a esse comando",
    ("difftool", "cmd"): "no `git difftool`",
    ("mergetool", "cmd"): "no `git mergetool`",
    ("merge", "driver"): "no merge dos arquivos que o .gitattributes ligar a esse driver",
    ("filter", "clean"): "no `git add` dos arquivos que o .gitattributes ligar a esse filtro",
    ("filter", "smudge"): "no checkout dos arquivos que o .gitattributes ligar a esse filtro",
    ("filter", "process"): "no add e no checkout dos arquivos que o .gitattributes ligar a esse filtro",
    ("gpg", "program"): "a cada commit ou tag assinado",
    ("interactive", "difffilter"): "no `git add -p`",
    ("trailer", "command"): "no `git interpret-trailers` (e no commit, se configurado)",
    ("trailer", "cmd"): "no `git interpret-trailers` (e no commit, se configurado)",
}
SUSPEITAS = {
    ("credential", "helper"): "decide quem guarda e entrega a sua senha do git",
    ("include", "path"): "puxa configuração de outro arquivo (que pode trazer as chaves perigosas)",
    ("includeif", "path"): "puxa configuração de outro arquivo (que pode trazer as chaves perigosas)",
    ("url", "insteadof"): "troca o endereço de onde o git baixa as coisas",
}


def verificar(arq: Arquivo) -> Iterator[Achado]:
    dentro = arq.pasta_do_git
    bare = _dentro_de_repo_bare(arq)
    caminho = (dentro or bare or "").lower()
    if not caminho:
        if arq.nome.lower() == ".git" and (arq.texto or "").lower().startswith("gitdir:"):
            yield from _ponteiro(arq)
        return
    partes = caminho.split("/")
    if "hooks" in partes[:-1] and not partes[-1].endswith(".sample"):
        primeira = (arq.texto or "").strip().split("\n", 1)[0]
        yield achado(
            Nivel.PERIGO,
            arq,
            f"hook do git: «{arq.nome}» roda sozinho",
            f"O git roda esse script automaticamente no momento indicado pelo nome ({arq.nome})." + VEIO_PRONTA,
            linha=1,
            trecho=primeira,
        )
    elif partes[-1] in ("config", "config.worktree") and arq.texto is not None:
        extra = (
            " É um repositório 'bare' escondido: o git usa essa config quando alguém roda git nessa pasta."
            if bare
            else ""
        )
        yield from _config(arq, extra)


def _dentro_de_repo_bare(arq: Arquivo) -> str | None:
    """Uma pasta com HEAD + config (sem .git) é um repositório 'bare': o git também obedece a config dela."""
    if not arq.varredura:
        return None
    partes = arq.rel.split("/")
    for i in range(len(partes) - 1, -1, -1):
        pasta = "/".join(partes[:i])
        prefixo = f"{pasta}/" if pasta else ""
        if f"{prefixo}HEAD" in arq.varredura.por_caminho and f"{prefixo}config" in arq.varredura.por_caminho:
            return "/".join(partes[i:])
    return None


def _ponteiro(arq: Arquivo) -> Iterator[Achado]:
    destino = (arq.texto or "").split(":", 1)[1].strip()
    alvo = os.path.realpath(arq.raiz / PurePosixPath(arq.rel).parent / destino)
    if not alvo.startswith(os.path.realpath(arq.raiz) + os.sep):
        yield achado(
            Nivel.ATENCAO,
            arq,
            "a pasta do git está FORA do projeto (gitdir:)",
            "Esse arquivo manda o git usar uma pasta de outro lugar do seu computador, com a config e os hooks de lá.",
            linha=1,
            trecho=destino,
        )


def ler_config(texto: str) -> Iterator[tuple[int, str, str, str]]:
    """Cada chave da config do git: (linha, seção, chave, valor), seguindo a gramática do git."""
    linhas = texto.splitlines()
    secao, i = "", 0
    while i < len(linhas):
        numero, linha = i + 1, linhas[i]
        i += 1
        while linha.rstrip().endswith("\\") and i < len(linhas):  # linha continua na de baixo
            linha = linha.rstrip()[:-1] + linhas[i]
            i += 1
        if m := CABECALHO.match(linha):
            secao = m.group(1).lower().split(".", 1)[0]  # [filter "x"] e o formato antigo [filter.x]
            linha = linha[m.end() :]  # a chave pode vir na mesma linha: [core] fsmonitor = x
        if m := CHAVE.match(_sem_comentario(linha)):
            yield numero, secao, m.group(1).lower(), (m.group(2) or "").strip().strip('"')


def _sem_comentario(linha: str) -> str:
    aspas = False
    for i, c in enumerate(linha):
        if c == '"':
            aspas = not aspas
        elif c in "#;" and not aspas:
            return linha[:i]
    return linha


def _config(arq: Arquivo, extra: str) -> Iterator[Achado]:
    for numero, secao, chave, valor in ler_config(arq.texto):
        trecho = f"{secao}.{chave} = {valor}"
        if (secao, chave) == ("core", "fsmonitor") and valor.lower() in VERDADEIRO_OU_FALSO:
            continue  # true/false = o monitor embutido do git, não é programa de ninguém
        if secao == "filter" and valor in LFS:
            continue
        quando = EXECUTA.get((secao, chave)) or EXECUTA.get((secao, "*"))
        if (secao, chave) == ("credential", "helper") and valor.split(" ")[0] not in AJUDANTES_DE_SENHA:
            quando = "toda vez que o git precisa de uma senha (não é um dos ajudantes de senha conhecidos)"
        if quando:
            yield achado(
                Nivel.PERIGO,
                arq,
                f"o git EXECUTA o valor de {secao}.{chave}",
                f"Esse programa roda {quando}." + extra + VEIO_PRONTA,
                linha=numero,
                trecho=trecho,
            )
        elif motivo := SUSPEITAS.get((secao, chave)):
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"{secao}.{chave} na config do git",
                f"Essa chave {motivo}." + extra + VEIO_PRONTA,
                linha=numero,
                trecho=trecho,
            )
        elif secao == "alias" and valor.startswith("!"):
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"atalho do git que roda comando de terminal: git {chave}",
                "Atalho com ! roda um comando do sistema quando você digita esse atalho.",
                linha=numero,
                trecho=trecho,
            )
