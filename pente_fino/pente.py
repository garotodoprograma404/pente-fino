"""O maestro: lista a pasta, passa cada arquivo por cada regra, liga os pontos e dá o veredito."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import NOMES_SENSIVEIS, PASTAS_SENSIVEIS, Arquivo, listar
from pente_fino.regras import REGRAS

achado = achador("varredura")
CAMINHO = re.compile(r"[\w.${}@~%/\\-]+")  # pedaços de comando que podem ser um caminho de arquivo
PREFIXOS = (
    "${workspaceFolder}/",
    "${workspaceRoot}/",
    "$PWD/",
    "${PWD}/",
    "$CLAUDE_PROJECT_DIR/",
    "${CLAUDE_PROJECT_DIR}/",
    "%cd%/",
    "./",
)


@dataclass
class Resultado:
    pasta: Path
    lidos: int  # quantos arquivos passaram pelo pente
    achados: list[Achado]

    @property
    def pior(self) -> Nivel | None:
        return max((a.nivel for a in self.achados), default=None)

    def quantos(self, nivel: Nivel) -> int:
        return sum(a.nivel == nivel for a in self.achados)

    @property
    def incompleto(self) -> bool:
        """Ficou alguma coisa sem olhar (pasta pulada, arquivo não lido inteiro)?"""
        return any(a.regra == "varredura" or a.titulo.startswith("arquivo grande") for a in self.achados)


def pentear(pasta: Path, tudo: bool = False) -> Resultado:
    """Varre a pasta inteira. Só lê: não executa nada, não instala nada, não acessa a internet."""
    varredura = listar(Path(pasta), tudo=tudo)
    achados = [a for arquivo in varredura.arquivos for regra in REGRAS for a in _aplica(regra, arquivo)]
    for rel in varredura.puladas:
        achados.append(
            achado(
                Nivel.INFO,
                rel,
                "pasta pulada (dependências baixadas ou resultado de build)",
                "Normalmente é gerada na sua máquina, não escrita por alguém. Num projeto recebido, "
                "ela já vir pronta é estranho: use --tudo pra olhar ela também.",
            )
        )
    for rel in varredura.sem_acesso:
        achados.append(
            achado(
                Nivel.ATENCAO,
                rel,
                "pasta ou arquivo que eu não consegui abrir",
                "Sem permissão de leitura (ou sumiu no meio da varredura). Se eu não olhei, não posso "
                "dizer que está limpo.",
            )
        )
    for rel, destino in varredura.atalhos_de_pasta:
        nome = rel.rsplit("/", 1)[-1].lower()
        if f"{nome}/" in PASTAS_SENSIVEIS or nome in NOMES_SENSIVEIS:
            achados.append(
                achado(
                    Nivel.ATENCAO,
                    rel,
                    "pasta de configuração disfarçada de atalho",
                    "O editor e o agente leem a pasta de destino como se fosse esta. Eu também li (os "
                    "achados dela aparecem com este nome), mas não é normal.",
                    trecho=f"→ {destino}",
                )
            )
    achados = liga_os_pontos(achados)
    achados.sort(key=lambda a: (-a.nivel, a.arquivo, a.linha or 0))
    return Resultado(Path(pasta), len(varredura.arquivos), achados)


def _aplica(regra: Callable[[Arquivo], Iterable[Achado]], arquivo: Arquivo) -> list[Achado]:
    """Roda uma regra num arquivo. Se der erro, vira um achado: arquivo malicioso não derruba o pente-fino."""
    achados: list[Achado] = []
    try:
        achados.extend(regra(arquivo))  # o que a regra já tinha achado antes do erro não se perde
    except Exception as erro:
        achados.append(
            achado(
                Nivel.PERIGO,
                arquivo,
                "arquivo que derrubou uma das minhas regras",
                f"Uma regra tropeçou nele ({type(erro).__name__}). Arquivo feito pra confundir "
                "ferramenta de segurança merece uma olhada sua.",
            )
        )
    return achados


def liga_os_pontos(achados: list[Achado]) -> list[Achado]:
    """Uma pista leva à outra: se um comando cita um arquivo que já é PERIGO, o comando vira PERIGO também.

    Ex.: o `postinstall` roda scripts/prepara.js (atenção)… e é justamente o prepara.js que decodifica e executa
    um texto escondido (perigo). Sozinhas, duas pistas; juntas, o golpe inteiro.
    """
    perigosos = {a.arquivo for a in achados if a.nivel == Nivel.PERIGO}
    ligados = []
    for item in achados:
        if item.nivel < Nivel.PERIGO and item.trecho and (alvo := _arquivo_citado(item, perigosos)):
            item = replace(
                item, nivel=Nivel.PERIGO, porque=f"{item.porque} E isso leva a {alvo}, que eu marquei como PERIGO."
            )
        ligados.append(item)
    return ligados


def _arquivo_citado(item: Achado, perigosos: set[str]) -> str | None:
    """Algum pedaço do trecho é o caminho de um arquivo perigoso (a partir da raiz ou da pasta do achado)?"""
    pasta = posixpath.dirname(item.arquivo)
    for pedaco in CAMINHO.findall(item.trecho.replace("\\", "/")):
        for prefixo in PREFIXOS:
            pedaco = pedaco.removeprefix(prefixo)
        for candidato in (posixpath.normpath(pedaco), posixpath.normpath(posixpath.join(pasta, pedaco))):
            if candidato in perigosos and candidato != item.arquivo:
                return candidato
    return None
