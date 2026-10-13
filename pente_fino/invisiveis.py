"""A tabela única dos caracteres que NÃO aparecem na tela.

A regra `escondido` usa pra achar texto escondido, e o relatório usa pra blindar a saída. Tudo está escrito
como número (0x200B…) de propósito: este arquivo não tem nenhum caractere invisível de verdade.
"""

from __future__ import annotations

import re
import unicodedata

FAIXAS = {
    # letras ASCII disfarçadas: cada uma vale uma letra, mas nenhuma aparece
    "tag": [(0xE0000, 0xE007F)],
    # "escolhem o desenho" do caractere anterior; uma fileira deles carrega bytes escondidos
    "seletor": [(0xFE00, 0xFE0F), (0xE0100, 0xE01EF)],
    # trocam a ordem do texto na tela (Trojan Source)
    "bidi": [(0x061C, 0x061C), (0x200E, 0x200F), (0x202A, 0x202E), (0x2066, 0x2069)],
    # "letras" coreanas vazias e o braille em branco: a linguagem aceita como nome de variável
    "preenchedor": [(0x115F, 0x1160), (0x3164, 0x3164), (0xFFA0, 0xFFA0), (0x2800, 0x2800)],
    # largura zero e afins
    "largura_zero": [
        (0x00AD, 0x00AD),
        (0x034F, 0x034F),
        (0x17B4, 0x17B5),
        (0x180B, 0x180E),
        (0x200B, 0x200D),
        (0x2060, 0x2064),
        (0x206A, 0x206F),
        (0xFEFF, 0xFEFF),
        (0xFFF9, 0xFFFB),
        (0x1D173, 0x1D17A),
    ],  # fmt: skip
    # área de uso privado: sem desenho padrão (fonte de ícone usa; malware também já usou)
    "uso_privado": [(0xE000, 0xF8FF)],
}
BIDI_TROCA_ORDEM = {*range(0x202A, 0x202F), *range(0x2066, 0x206A)}  # os que embutem/forçam/isolam a direção
BIDI_MARCA = {0x061C, 0x200E, 0x200F}  # só "marcam" a direção: normais em texto árabe/hebraico
FAIXAS_BIDI = BIDI_TROCA_ORDEM | BIDI_MARCA


def _tabela() -> dict[int, str]:
    tipos = {cp: tipo for tipo, faixas in FAIXAS.items() for a, b in faixas for cp in range(a, b + 1)}
    # qualquer outro caractere de "formato" (categoria Cf) do Unicode também conta como largura zero
    for cp in [*range(0x10000), *range(0x110BD, 0x110CE), *range(0x13430, 0x13460), *range(0x1BCA0, 0x1BCA4)]:
        if unicodedata.category(chr(cp)) == "Cf":
            tipos.setdefault(cp, "largura_zero")
    return tipos


TIPO = _tabela()


def _faixas_seguidas(pontos: list[int]) -> list[tuple[int, int]]:
    faixas: list[tuple[int, int]] = []
    for cp in pontos:
        if faixas and cp == faixas[-1][1] + 1:
            faixas[-1] = (faixas[-1][0], cp)
        else:
            faixas.append((cp, cp))
    return faixas


# uma expressão regular com todas as faixas (escrita com \U0000XXXX: o padrão é texto ASCII puro)
INVISIVEL = re.compile("[" + "".join(f"\\U{a:08x}-\\U{b:08x}" for a, b in _faixas_seguidas(sorted(TIPO))) + "]+")


def tipo(c: str) -> str | None:
    """'tag', 'seletor', 'bidi', 'preenchedor', 'largura_zero', 'uso_privado' ou None (caractere visível)."""
    return TIPO.get(ord(c))


def some_na_tela(c: str) -> bool:
    """Invisível, controle de terminal ou separador de linha: tudo que pode esconder ou bagunçar a saída."""
    return ord(c) in TIPO or unicodedata.category(c) in ("Cc", "Cf", "Co", "Cs", "Zl", "Zp", "Cn")
