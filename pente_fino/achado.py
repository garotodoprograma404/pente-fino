"""O que o pente-fino acha. Um achado = onde está, quão grave é, o que é e por que importa."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum


class Nivel(IntEnum):
    INFO = 1  # bom saber
    ATENCAO = 2  # pode ser legítimo, mas roda coisa quando VOCÊ der o comando: leia antes
    PERIGO = 3  # roda sozinho, ou esconde coisa de você


@dataclass(frozen=True)
class Achado:
    regra: str  # a família que achou: "editor", "git", "agentes"…
    nivel: Nivel
    arquivo: str  # caminho relativo à pasta varrida
    titulo: str  # uma linha: o que é
    porque: str  # por que importa e o que fazer
    linha: int | None = None
    trecho: str = ""  # o pedaço do arquivo (o relatório higieniza antes de mostrar)


Novo = Callable[..., Achado]


def achador(regra: str) -> Novo:
    """Atalho pra cada regra criar seus achados: achado(Nivel.PERIGO, arq, "título", "porquê", linha=3)."""

    def achado(
        nivel: Nivel, arq: object, titulo: str, porque: str, linha: int | None = None, trecho: str = ""
    ) -> Achado:
        return Achado(regra, nivel, getattr(arq, "rel", str(arq)), titulo, porque, linha, trecho)

    return achado
