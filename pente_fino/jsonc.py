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
CHAVES = re.compile(STRING + r"|[\[\]{}]")
# config de verdade não passa de uns 10 níveis; o limite é nosso (e não o do Python, que muda de máquina pra máquina)
PROFUNDIDADE_MAXIMA = 200


def sem_comentarios(texto: str) -> str:
    return COMENTARIO.sub(lambda m: m.group(1) or "", texto)


def fundo_demais(texto: str) -> bool:
    """Tem colchete/chave aninhado mais fundo que PROFUNDIDADE_MAXIMA (fora das strings)? Anda sempre pra frente."""
    nivel = 0
    for m in CHAVES.finditer(texto):
        if m.group(1):  # string inteira: colchete lá dentro é texto
            continue
        nivel += 1 if m.group(0) in "[{" else -1
        if nivel > PROFUNDIDADE_MAXIMA:
            return True
    return False


def ler(texto: str) -> object | None:
    """O conteúdo do arquivo, ou None se não der pra ler (inclusive JSON aninhado fundo demais)."""
    limpo = VIRGULA_SOBRANDO.sub(lambda m: m.group(1) or "", sem_comentarios(texto))
    limpo = limpo.replace(chr(0x2028), "\n").replace(chr(0x2029), "\n")  # pro VS Code, é espaço comum
    if fundo_demais(limpo):
        return None
    try:
        return json.loads(limpo)
    except (ValueError, RecursionError):
        return None
