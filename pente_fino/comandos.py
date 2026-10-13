"""Quando um arquivo manda rodar um comando: o que nesse comando tem cara de golpe."""

from __future__ import annotations

import re

SINAIS = (
    (
        re.compile(r"\b(curl|wget|iwr|irm|Invoke-WebRequest|Invoke-RestMethod|certutil|bitsadmin)\b", re.I),
        "baixa coisa da internet",
    ),
    (
        re.compile(r"\|\s*(sudo\s+)?(ba|z|da|k)?sh\b|\|\s*(python3?|node|perl|ruby|iex)\b|\$\(\s*(curl|wget)\b", re.I),
        "joga o que recebeu direto pra rodar",
    ),
    (
        re.compile(r"base64|\batob\b|FromBase64String|\s-e(nc|ncodedcommand)?\s", re.I),
        "usa texto codificado (pra você não ler)",
    ),
    (
        re.compile(
            r"\b(node|deno|bun)\s+(-e|--eval|-p)\b|\bpython3?\s+-c\b|\b(ba|z)?sh\s+-c\b|\bpowershell\b|\bpwsh\b"
            r"|\bmshta\b|\beval\b|\bInvoke-Expression\b",
            re.I,
        ),
        "roda código escrito ali mesmo, como texto",
    ),
    (re.compile(r"\b(nc|ncat|netcat|socat)\b|/dev/tcp/", re.I), "abre conexão de rede direta"),
    (re.compile(r"\bnohup\b|&\s*$|\bdisown\b|\bstart\s+/b\b", re.I), "fica rodando escondido em segundo plano"),
)


def sinais(comando: str) -> list[str]:
    """Os motivos pra desconfiar desse comando (lista vazia = nada óbvio)."""
    comando = comando[:5000]  # comando de verdade é curto; isso também limita o tempo das buscas
    return [motivo for padrao, motivo in SINAIS if padrao.search(comando)]


def explica(comando: str) -> str:
    """Frase pronta pro relatório: ' E o comando baixa coisa da internet e …' (ou vazio)."""
    motivos = sinais(comando)
    return f" E o comando {' e '.join(motivos)}." if motivos else ""


def como_texto(valor: object) -> str:
    """Comando escrito de qualquer jeito (texto, lista de partes, dicionário de vários) vira uma linha só."""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, list):
        return " ".join(como_texto(v) for v in valor)
    if isinstance(valor, dict):
        return " ; ".join(como_texto(v) for v in valor.values())
    return "" if valor is None else str(valor)
