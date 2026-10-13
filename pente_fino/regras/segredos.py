"""Segredos: chave de API, token e senha que estão no código. Sempre mostradas MASCARADAS.

No repo dos outros, é sinal de bagunça. No SEU projeto, é dinheiro: chave de IA vazada vira conta de milhares
de dólares em poucos dias. Apagar do código não basta, porque continua no histórico do git: revogue e gere outra.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Iterator

from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import Arquivo, linha_da_posicao

achado = achador("segredos")

# (nome, pedaços que TODA chave desse tipo tem, formato completo). Procurar o pedaço é instantâneo; o formato
# completo só é testado se o pedaço aparecer: filtro barato antes do caro.
CHAVES = tuple(
    (nome, pistas, re.compile(rf"(?<![A-Za-z0-9_-])(?:{padrao})"))
    for nome, pistas, padrao in (
        ("Anthropic (Claude)", ("sk-ant-",), r"sk-ant-[A-Za-z0-9_-]{20,}"),
        ("OpenAI", ("sk-",), r"sk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}"),
        ("Google (Gemini, Firebase…)", ("AIza",), r"AIza[0-9A-Za-z_-]{35}"),
        ("AWS", ("AKIA", "ASIA"), r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
        ("GitHub", ("gh", "github_pat_"), r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,}"),
        ("npm", ("npm_",), r"npm_[A-Za-z0-9]{36}"),
        ("Hugging Face", ("hf_",), r"hf_[A-Za-z0-9]{30,}"),
        ("Groq", ("gsk_",), r"gsk_[A-Za-z0-9]{40,}"),
        ("xAI (Grok)", ("xai-",), r"xai-[A-Za-z0-9]{40,}"),
        ("Stripe", ("_live_",), r"(?:sk|rk)_live_[A-Za-z0-9]{20,}"),
        ("Slack", ("xox",), r"xox[abposr]-[A-Za-z0-9-]{10,}"),
        ("chave privada", ("PRIVATE KEY",), r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
    )
)
SUPABASE_SECRETA = re.compile(r"(?<![A-Za-z0-9_-])sb_secret_[A-Za-z0-9_-]{20,}")
JWT = re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,}\.(eyJ[A-Za-z0-9_-]{10,})\.[A-Za-z0-9_-]{10,}")
EXEMPLO = re.compile(r"x{4}|your|sua_|seu_|exemplo|example|placeholder|fake|dummy", re.I)  # chave de mentirinha
ENV_DE_EXEMPLO = (".example", ".sample", ".template", ".dist", ".defaults", ".exemplo")
MESTRA = (
    "Essa chave passa por cima de todas as regras de segurança do banco: quem tem ela lê e apaga os dados de "
    "todos os usuários. Nunca pode estar no código, muito menos no front-end. Troque já no painel do Supabase."
)


def verificar(arq: Arquivo) -> Iterator[Achado]:
    texto = arq.texto
    if texto is None or arq.ignorado_pelo_git or arq.eh_gerado:
        return  # o que está no .gitignore não vai pro repositório: é o lugar certo de guardar chave
    nome = arq.nome.lower()
    eh_env = (nome == ".env" or nome.startswith(".env.")) and not nome.endswith(ENV_DE_EXEMPLO)
    if eh_env and re.search(r"^[ \t]*\w+[ \t]*=[ \t]*\S", texto, re.M):
        yield achado(
            Nivel.ATENCAO,
            arq,
            "arquivo de senhas (.env) junto do código",
            "O .env existe justamente pra NÃO ir pro repositório. Coloque no .gitignore e, se ele já "
            "subiu, troque as chaves que estão nele.",
        )
    for nome_da_chave, pistas, padrao in CHAVES:
        if not any(pista in texto for pista in pistas):
            continue
        achadas = [m for m in padrao.finditer(texto) if _parece_de_verdade(m.group())]
        if achadas:
            linha, _ = linha_da_posicao(texto, achadas[0].start())
            mais = f" (+{len(achadas) - 1} no mesmo arquivo)" if len(achadas) > 1 else ""
            yield achado(
                Nivel.ATENCAO,
                arq,
                f"chave de {nome_da_chave} exposta{mais}",
                "Se o projeto é seu: revogue essa chave no painel do serviço e gere outra (apagar do código "
                "não adianta, fica no histórico do git). Em serviço de IA, ponha limite de gasto.",
                linha=linha,
                trecho=mascara(achadas[0].group()),
            )
    mestra = ("sb_secret_" in texto and SUPABASE_SECRETA.search(texto)) or _jwt_service_role(texto)
    if mestra:
        linha, _ = linha_da_posicao(texto, mestra.start())
        yield achado(
            Nivel.PERIGO,
            arq,
            "chave MESTRA do Supabase (secreta / service_role)",
            MESTRA,
            linha=linha,
            trecho=mascara(mestra.group()),
        )


def _parece_de_verdade(chave: str) -> bool:
    """Chave de exemplo (sk-xxxx, your-key) não conta; chave de verdade mistura letras e números."""
    if EXEMPLO.search(chave):
        return False
    return chave.startswith("-----") or (any(c.isdigit() for c in chave) and any(c.isalpha() for c in chave))


def mascara(segredo: str) -> str:
    """Mostra só o começo: dá pra reconhecer qual chave é, não dá pra usar."""
    if segredo.startswith("-----BEGIN"):
        return segredo
    return f"{segredo[:8]}…  ({len(segredo)} caracteres)"


def _jwt_service_role(texto: str) -> re.Match | None:
    if "eyJ" not in texto:  # todo JWT começa assim
        return None
    return next((m for m in JWT.finditer(texto) if _papel_do_jwt(m.group(1)) == "service_role"), None)


def _papel_do_jwt(carga: str) -> str | None:
    try:
        dados = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    except (ValueError, binascii.Error, RecursionError):
        return None
    return dados.get("role") if isinstance(dados, dict) else None
