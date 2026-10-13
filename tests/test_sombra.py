import os
import subprocess
import sys
from pathlib import Path

from pente_fino.achado import Nivel
from tests.apoio import CasoComPasta

REPO = Path(__file__).resolve().parent.parent
# isca inofensiva: só prova que o arquivo rodou, escrevendo um marcador do lado dele
ISCA = "import pathlib\npathlib.Path(__file__).with_name('MARCADOR.txt').write_text('rodou')\n"
FALSOS = ("argparse", "json", "pathlib", "dataclasses", "unicodedata", "fnmatch")


class TestPasteDentroDaPasta(CasoComPasta):
    """A pessoa dá `cd` na pasta recebida e passa o pente de dentro: nada da pasta pode rodar antes dele."""

    def roda_de_dentro(self, *args: str) -> subprocess.CompletedProcess:
        ambiente = dict(os.environ, PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
        comando = [sys.executable, "-m", "pente_fino", str(self.pasta), *args]
        return subprocess.run(comando, cwd=self.pasta, env=ambiente, capture_output=True, text=True, timeout=60)

    def test_modulo_falso_na_pasta_nao_roda(self):
        for nome in FALSOS:
            self.escreve(f"{nome}.py", ISCA)
        resultado = self.roda_de_dentro()
        self.assertFalse((self.pasta / "MARCADOR.txt").exists(), "um arquivo da pasta rodou antes do pente")
        self.assertEqual(resultado.returncode, 1, resultado.stderr)
        self.assertIn("se passa pelo módulo", resultado.stdout)

    def test_pasta_limpa_continua_funcionando_de_dentro(self):
        self.escreve("main.py", "print('oi')\n")
        resultado = self.roda_de_dentro()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("NADA SUSPEITO", resultado.stdout)


class TestRegraSombra(CasoComPasta):
    def test_essenciais_sao_perigo_e_comuns_sao_atencao(self):
        self.escreve("argparse.py", "x = 1\n")
        self.escreve("sitecustomize.py", "x = 1\n")
        self.escreve("random.py", "x = 1\n")
        niveis = {a.arquivo: a.nivel for a in self.achados("sombra")}
        self.assertEqual(niveis, {"argparse.py": Nivel.PERIGO, "sitecustomize.py": Nivel.PERIGO,
                                  "random.py": Nivel.ATENCAO})  # fmt: skip

    def test_pacote_falso_do_proprio_pente_na_raiz(self):
        self.escreve("pente_fino/__init__.py", "x = 1\n")
        self.assertAcusa("sombra", Nivel.PERIGO, "pente_fino")

    def test_nomes_normais_e_subpastas_nao_acusam(self):
        for rel in ("main.py", "test.py", "app.py", "utils.py", "src/argparse.py", "docs/json.py", "setup.py"):
            self.escreve(rel, "x = 1\n")
        self.assertLimpo("sombra")
