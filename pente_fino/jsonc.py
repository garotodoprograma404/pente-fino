"""JSON "do jeito do VS Code": aceita // comentário, /* bloco */ e vírgula sobrando.

Cada passada é uma expressão regular que anda sempre pra frente: um arquivo feito pra travar o leitor não trava.
"""

from __future__ import annotations

import json
import re

STRING = r'("(?:[^"\\\n\r]|\\.)*")'  # uma string inteira: o que está dentro dela nunca é comentário nem vírgula
# fim de linha, como o leitor do VS Code entende: inclui os separadores de linha do Unicode (U+2028 e U+2029)
FIM_DE_LINHA = "\n\r" + chr(0x2028) + chr(0x2029)
COMENTARIO = re.compile(STRING + f"|//[^{FIM_DE_LINHA}]*" + r"|/\*.*?(?:\*/|\Z)", re.S)
VIRGULA_SOBRANDO = re.compile(STRING + r"|,(?=\s*[}\]])")


def sem_comentarios(texto: str) -> str:
    return COMENTARIO.sub(lambda m: m.group(1) or "", texto)


def ler(texto: str) -> object | None:
    """O conteúdo do arquivo, ou None se não der pra ler (inclusive JSON aninhado fundo demais)."""
    limpo = VIRGULA_SOBRANDO.sub(lambda m: m.group(1) or "", sem_comentarios(texto))
    limpo = limpo.replace(chr(0x2028), "\n").replace(chr(0x2029), "\n")  # pro VS Code, é espaço comum
    try:
        return json.loads(limpo)
    except (ValueError, RecursionError):
        return None
