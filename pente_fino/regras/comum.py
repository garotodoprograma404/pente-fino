"""Pedaços que mais de uma regra usa."""

from __future__ import annotations

from pente_fino.achado import Achado, Nivel, Novo
from pente_fino.arquivos import Arquivo


def config_ilegivel(achado: Novo, arq: Arquivo, marcadores: tuple[str, ...]) -> Achado:
    """Arquivo de configuração que o Python não conseguiu ler, mas o editor (que é tolerante) talvez leia."""
    texto = (arq.texto or "").lower()
    citados = [m for m in marcadores if m.lower() in texto]
    return achado(
        Nivel.PERIGO if citados else Nivel.ATENCAO,
        arq,
        "arquivo de configuração que eu não consegui ler",
        "O formato está quebrado (ou aninhado fundo demais), mas editor e agente costumam ler mesmo assim. "
        "Arquivo de configuração montado pra confundir ferramenta de segurança é sinal de alerta."
        + (f" E ele cita {', '.join(citados)}, que é o que faz coisa rodar sozinha." if citados else ""),
    )


def comandos_dentro(dados: object, chaves: tuple[str, ...] = ("command",)) -> list[str]:
    """Acha todo valor de `chaves` dentro de uma estrutura de hooks (sem recursão: aninhamento fundo não trava)."""
    achados, pilha = [], [dados]
    while pilha:
        atual = pilha.pop()
        if isinstance(atual, dict):
            for chave, valor in atual.items():
                if chave in chaves and isinstance(valor, (str, list)):
                    achados.append(valor if isinstance(valor, str) else " ".join(map(str, valor)))
                else:
                    pilha.append(valor)
        elif isinstance(atual, list):
            pilha.extend(reversed(atual))
    return achados
