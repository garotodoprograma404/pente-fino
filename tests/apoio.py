"""Apoio dos testes: cada caso ganha uma pasta temporária limpa.

As "iscas" dos testes são montadas em pedaços (ex.: "ev" + "al", "sk-" + "ant-") e os caracteres invisíveis são
escritos com chr(0x200B): assim o repositório do pente-fino passa limpo no próprio pente-fino.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from pente_fino.achado import Achado, Nivel
from pente_fino.pente import Resultado, pentear

EVAL, EXEC, FUNCTION, IMPORT = "ev" + "al", "ex" + "ec", "Func" + "tion", "__imp" + "ort__"
ZWSP, ZWJ, RLO, PDF, LRI, PDI = chr(0x200B), chr(0x200D), chr(0x202E), chr(0x202C), chr(0x2066), chr(0x2069)


def tags(texto: str) -> str:
    """Texto escrito com caracteres "tag" do Unicode: o computador lê, você não vê."""
    return "".join(chr(0xE0000 + ord(c)) for c in texto)


def seletores(dados: bytes) -> str:
    """Bytes escondidos em seletores de variação (cada byte vira um caractere invisível)."""
    return "".join(chr(0xFE00 + b) if b < 16 else chr(0xE0100 + b - 16) for b in dados)


class CasoComPasta(unittest.TestCase):
    def setUp(self) -> None:
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)

    def escreve(self, rel: str, conteudo: str | bytes | dict | list) -> Path:
        caminho = self.pasta / rel
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(conteudo, (dict, list)):
            conteudo = json.dumps(conteudo, ensure_ascii=False, indent=2)
        if isinstance(conteudo, bytes):
            caminho.write_bytes(conteudo)
        else:
            caminho.write_text(conteudo, encoding="utf-8")
        return caminho

    def resultado(self, tudo: bool = False) -> Resultado:
        return pentear(self.pasta, tudo=tudo)

    def achados(self, regra: str | None = None) -> list[Achado]:
        return [a for a in self.resultado().achados if regra is None or a.regra == regra]

    def niveis(self, regra: str | None = None) -> list[Nivel]:
        return [a.nivel for a in self.achados(regra)]

    def assertAcusa(self, regra: str, nivel: Nivel, contem: str) -> Achado:  # noqa: N802 (padrão do unittest)
        todos = self.achados()  # uma varredura só (a mensagem de erro usa a mesma lista)
        achados = [a for a in todos if a.regra == regra and a.nivel == nivel and contem in f"{a.titulo} {a.trecho}"]
        self.assertTrue(achados, f"esperava {nivel.name} de «{regra}» com «{contem}»; veio: {todos}")
        return achados[0]

    def assertLimpo(self, regra: str | None = None) -> None:  # noqa: N802
        self.assertEqual(self.achados(regra), [])

    def assertRapido(self, segundos: float = 3.0) -> Resultado:  # noqa: N802
        """Arquivo feito pra travar o pente-fino tem que terminar rápido."""
        comeco = time.perf_counter()
        resultado = self.resultado()
        self.assertLess(time.perf_counter() - comeco, segundos)
        return resultado
