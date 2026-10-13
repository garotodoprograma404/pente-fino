import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from pente_fino.achado import Nivel
from tests.apoio import CasoComPasta

# chaves falsas montadas em pedaços: ver tests/apoio.py
ANTHROPIC = "sk-" + "ant-" + "api03-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
AWS = "AKIA" + "Z7Q2W4E6R8T0Y1U3"
GITHUB = "ghp" + "_" + "a1B2" * 9
SUPABASE = "sb_" + "secret_" + "Ab12Cd34Ef56Gh78Ij90Kl12"


def jwt(papel: str) -> str:
    def parte(dados: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(dados).encode()).decode().rstrip("=")

    return f"{parte({'alg': 'HS256', 'typ': 'JWT'})}.{parte({'iss': 'supabase', 'role': papel})}.assinaturaFalsa123"


class TestSegredos(CasoComPasta):
    def test_acha_e_mascara(self):
        self.escreve("config.js", f'const chave = "{ANTHROPIC}";\nconst aws = "{AWS}";\n')
        achado = self.assertAcusa("segredos", Nivel.ATENCAO, "Anthropic")
        self.assertNotIn(ANTHROPIC, achado.trecho)
        self.assertTrue(achado.trecho.startswith("sk-ant-a"))
        self.assertAcusa("segredos", Nivel.ATENCAO, "AWS")

    def test_conta_repetidas_no_mesmo_arquivo(self):
        self.escreve("a.txt", f"{GITHUB}\n{GITHUB}\n{GITHUB}\n")
        self.assertAcusa("segredos", Nivel.ATENCAO, "(+2 no mesmo arquivo)")

    def test_chave_de_exemplo_e_css_nao_acusam(self):
        self.escreve("README.md", "export OPENAI_API_KEY=sk-" + "proj-your-key-goes-here-12345678901\nsk-" + "x" * 40)
        self.escreve("a.css", ".sk-three-bounce-animation-delay-and-more { }\n.task-" + "a" * 30 + " {}\n")
        self.assertLimpo()

    def test_env_no_repo(self):
        self.escreve(".env", "DEBUG=1\n")
        self.escreve(".env.example", "API_KEY=\n")
        self.assertEqual([a.arquivo for a in self.achados("segredos")], [".env"])

    def test_gitignore_de_verdade(self):
        self.escreve(".gitignore", "# segredos\n*.env\n.env*\n!prod.env\n/raiz.key\nsecrets/\n")
        for rel in (".env", "web/.env.local", "prod.env", "raiz.key", "sub/raiz.key", "secrets/k.txt", "config.js"):
            self.escreve(rel, f"KEY={GITHUB}\n")
        acusados = {a.arquivo for a in self.achados("segredos") if "chave" in a.titulo}
        self.assertEqual(acusados, {"prod.env", "sub/raiz.key", "config.js"})

    def test_chave_mestra_do_supabase(self):
        self.escreve("src/supabase.ts", f'createClient(url, "{jwt("service_role")}")\n')
        self.escreve("src/nova.ts", f'createClient(url, "{SUPABASE}")\n')
        self.escreve("src/publica.ts", f'createClient(url, "{jwt("anon")}")\n')
        perigos = {a.arquivo for a in self.achados("segredos") if a.nivel == Nivel.PERIGO}
        self.assertEqual(perigos, {"src/supabase.ts", "src/nova.ts"})


class TestBinariosEAtalhos(CasoComPasta):
    def test_programa_compilado(self):
        self.escreve("tools/helper", b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64)
        self.escreve("lib/addon.node", b"\x00\x01\x02")
        self.escreve("logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        self.assertEqual({a.arquivo for a in self.achados("binarios")}, {"tools/helper", "lib/addon.node"})

    def test_programa_com_nome_de_ferramenta(self):
        self.escreve("git.exe", b"MZ\x90\x00" + b"\x00" * 64)
        self.assertAcusa("binarios", Nivel.PERIGO, "git.exe")

    def test_gradle_wrapper_e_info(self):
        self.escreve("android/gradle/wrapper/gradle-wrapper.jar", b"PK\x03\x04\x00\x00")
        self.assertEqual(self.niveis("binarios"), [Nivel.INFO])

    def test_texto_com_byte_nulo_e_lido_assim_mesmo(self):
        self.escreve("tasks.js", b"// \x00\nconsole.log(1);\n")
        self.escreve(
            ".vscode/tasks.json", b'{"tasks": [{"label": "n", "runOptions": {"runOn": "folderOpen"}}]} /*\x00*/'
        )
        self.assertAcusa("binarios", Nivel.ATENCAO, "byte nulo")
        self.assertAcusa("editor", Nivel.PERIGO, "«n»")

    def test_utf16_e_lido(self):
        texto = '{"tasks": [{"label": "u", "runOptions": {"runOn": "folderOpen"}}]}'
        self.escreve(".vscode/tasks.json", texto.encode("utf-16"))
        self.assertAcusa("editor", Nivel.PERIGO, "«u»")

    def test_configuracao_gigante_e_perigo(self):
        enchimento = "// " + "x" * 100 + "\n"
        self.escreve(".vscode/tasks.json", enchimento * 60_000 + '{"tasks": []}')
        self.escreve("dados.csv", "a" * (5 * 1024 * 1024 + 1))
        self.assertAcusa("binarios", Nivel.PERIGO, "GIGANTE")
        self.assertAcusa("binarios", Nivel.INFO, "arquivo grande")


@unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "atalhos e FIFO: só em Linux/Mac")
class TestAtalhosEEspeciais(CasoComPasta):
    def setUp(self):
        super().setUp()
        fora = tempfile.TemporaryDirectory()
        self.addCleanup(fora.cleanup)
        self.fora = Path(fora.name)
        (self.fora / "segredo.txt").write_text("não pode ser lido")

    def test_atalho_pra_fora_do_projeto_e_nunca_lido(self):
        os.symlink(self.fora / "segredo.txt", self.pasta / "config.txt")
        os.symlink(self.fora / "segredo.txt", self.pasta / "package.json")
        niveis = {a.arquivo: a.nivel for a in self.achados()}
        self.assertEqual(niveis, {"config.txt": Nivel.ATENCAO, "package.json": Nivel.PERIGO})

    def test_atalho_pra_dentro_e_lido_com_o_nome_do_atalho(self):
        self.escreve("cfg/tarefas.json", {"tasks": [{"label": "s", "runOptions": {"runOn": "folderOpen"}}]})
        os.symlink("cfg", self.pasta / ".vscode")
        os.rename(self.pasta / "cfg/tarefas.json", self.pasta / "cfg/tasks.json")
        self.assertAcusa("editor", Nivel.PERIGO, "«s»")
        self.assertAcusa("varredura", Nivel.ATENCAO, "disfarçada de atalho")

    def test_atalho_em_circulo_nao_trava(self):
        (self.pasta / "a").mkdir()
        os.symlink("..", self.pasta / "a" / "volta")
        self.assertRapido()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "sem FIFO")
    def test_fifo_nao_trava_nem_como_gitignore(self):
        os.mkfifo(self.pasta / "armadilha.json")
        os.mkfifo(self.pasta / ".gitignore")
        self.escreve("a.txt", "oi")
        self.assertRapido()
        self.assertAcusa("binarios", Nivel.ATENCAO, "especial")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root lê tudo")
    def test_pasta_sem_permissao_vira_aviso(self):
        trancada = self.pasta / "trancada"
        trancada.mkdir()
        (trancada / "x.js").write_text("oi")
        trancada.chmod(0)
        self.addCleanup(trancada.chmod, 0o755)
        self.assertAcusa("varredura", Nivel.ATENCAO, "não consegui abrir")
