"""Sombra: arquivo na raiz da pasta que se passa por um módulo do Python (ou pelo próprio pente-fino).

Quando você dá `cd` na pasta e roda `python`, o Python procura os módulos ali primeiro. Um `argparse.py` plantado
na raiz roda no lugar do oficial, sem você ver. Por isso a regra de ouro do pente-fino: passe o pente DE FORA.
"""

from __future__ import annotations

from collections.abc import Iterator

from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import Arquivo

achado = achador("sombra")

# o Python, o pip e quase toda ferramenta carregam esses logo na largada: um falso aqui roda sempre
ESSENCIAIS = {
    "sitecustomize", "usercustomize", "site", "encodings", "argparse", "json", "re", "os", "sys", "codecs", "io",
    "abc", "pente_fino", "pip", "setuptools", "pytest",
}  # fmt: skip
# outros nomes que ferramentas importam muito: mereçam um olhar, mas projeto legítimo também erra isso
COMUNS = {
    "typing", "collections", "functools", "pathlib", "subprocess", "logging", "signal", "enum", "dataclasses",
    "fnmatch", "stat", "unicodedata", "base64", "binascii", "importlib", "runpy", "types", "string", "random", "time",
    "socket", "ssl", "http", "email", "shutil", "tempfile", "platform", "traceback", "warnings", "inspect", "copy",
    "itertools", "operator", "contextlib", "threading", "unittest", "pickle", "zipfile", "tarfile", "gzip",
    "datetime", "math", "glob", "urllib", "ctypes",
}  # fmt: skip


def verificar(arq: Arquivo) -> Iterator[Achado]:
    partes = arq.rel.split("/")
    if len(partes) == 1 and arq.nome.lower().endswith(".py"):
        nome = arq.nome[:-3]
    elif len(partes) == 2 and partes[1] == "__init__.py":
        nome = partes[0]  # uma pasta-pacote na raiz tem o mesmo efeito
    else:
        return  # só a raiz: é onde a pessoa dá `cd` e roda o Python
    if nome == "pente_fino" and _eh_o_repositorio_do_pente(arq):
        return
    if nome in ESSENCIAIS or nome in COMUNS:
        yield achado(
            Nivel.PERIGO if nome in ESSENCIAIS else Nivel.ATENCAO,
            arq,
            f"arquivo que se passa pelo módulo «{nome}» do Python",
            "Se você der `cd` nesta pasta e rodar `python`, o Python carrega ESTE arquivo no lugar do oficial, sem "
            "avisar. Passe o pente sempre DE FORA da pasta, e não rode Python aqui dentro antes de ler isto.",
        )


def _eh_o_repositorio_do_pente(arq: Arquivo) -> bool:
    """A raiz é o repositório do próprio pente-fino (a pasta `pente_fino/` ali é a verdadeira)?

    Uma cópia maliciosa poderia imitar o pyproject. Mas esta regra só roda dentro do pente verdadeiro, e a
    ameaça é outra: um `pente_fino/` falso numa pasta recebida, esperando você dar `cd` e rodar o pente instalado.
    """
    pyproject = arq.varredura.por_caminho.get("pyproject.toml") if arq.varredura else None
    return bool(pyproject and 'name = "pente-fino"' in (pyproject.texto or ""))
