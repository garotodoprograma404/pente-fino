"""Arquivos estranhos: programa compilado que ninguém consegue ler, atalho, arquivo que não dá pra ler,
arquivo de texto com byte nulo, arquivo de configuração gigante."""

from __future__ import annotations

from collections.abc import Iterator

from pente_fino.achado import Achado, Nivel, achador
from pente_fino.arquivos import LIMITE, Arquivo

achado = achador("binarios")

ASSINATURAS = (
    (b"\x7fELF", "programa de Linux"),
    (b"MZ", "programa de Windows (.exe/.dll)"),
    (b"\xcf\xfa\xed\xfe", "programa de Mac"),
    (b"\xce\xfa\xed\xfe", "programa de Mac"),
    (b"\xfe\xed\xfa\xcf", "programa de Mac"),
    (b"\xfe\xed\xfa\xce", "programa de Mac"),
    (b"\xca\xfe\xba\xbe", "programa de Mac ou Java compilado"),
    (b"\x00asm", "programa WebAssembly"),
)
EXTENSOES = {".exe", ".dll", ".so", ".dylib", ".node", ".scr", ".msi", ".jar", ".class", ".pyc", ".wasm",
             ".appimage", ".deb", ".rpm", ".com", ".pif"}  # fmt: skip
# no Windows, programa com nome de ferramenta dentro da pasta pode ser rodado NO LUGAR da ferramenta de verdade
NOME_DE_FERRAMENTA = {
    "git.exe", "node.exe", "npm.cmd", "npx.cmd", "python.exe", "python3.exe", "py.exe", "cmd.exe", "powershell.exe",
    "pwsh.exe", "code.exe", "cursor.exe", "where.exe", "bash.exe", "sh.exe",
}  # fmt: skip


def verificar(arq: Arquivo) -> Iterator[Achado]:
    if arq.link_para is not None:
        yield from _atalho(arq)
        if arq.atalho_pra_fora:
            return
    if arq.especial:
        yield achado(
            Nivel.ATENCAO,
            arq,
            "arquivo especial (FIFO, socket ou dispositivo)",
            "Não é um arquivo normal e não tem por que estar num projeto. Eu nem abri: um desses pode "
            "travar quem tenta ler.",
        )
    elif arq.ilegivel:
        yield achado(
            Nivel.ATENCAO,
            arq,
            "arquivo que eu não consegui ler",
            "Sem permissão de leitura (ou sumiu no meio da varredura). Se eu não li, não posso dizer que está limpo.",
        )
    elif arq.grande_demais:
        if arq.eh_sensivel:
            yield achado(
                Nivel.PERIGO,
                arq,
                f"arquivo de configuração GIGANTE (mais de {LIMITE // 2**20} MB)",
                "Ninguém escreve configuração desse tamanho. Eu li só o começo, e o editor lê tudo: é o "
                "jeito de esconder alguma coisa depois de um monte de enchimento.",
            )
        else:
            yield achado(Nivel.INFO, arq, f"arquivo grande: li só os primeiros {LIMITE // 2**20} MB", "")
    elif arq.tem_byte_nulo and arq.deveria_ser_texto:
        yield achado(
            Nivel.ATENCAO,
            arq,
            "arquivo de texto com byte nulo",
            "Byte nulo faz muita ferramenta achar que o arquivo é binário e pular ele. Eu li assim mesmo, "
            "mas texto normal não tem isso.",
        )
    elif arq.nome.lower() == "gradle-wrapper.jar":
        yield achado(
            Nivel.INFO,
            arq,
            "o gradlew roda este .jar",
            "Todo projeto Gradle tem um, e trocar ele por um falso é um ataque conhecido: o Gradle mantém "
            "uma validação oficial pra isso (gradle/actions/wrapper-validation). Confira antes de rodar "
            "./gradlew num projeto recebido.",
        )
    elif arq.texto is None and arq.pasta_do_git is None:
        yield from _programa(arq)


def _programa(arq: Arquivo) -> Iterator[Achado]:
    tipo = next((nome for magica, nome in ASSINATURAS if (arq.dados or b"").startswith(magica)), None)
    if arq.nome.lower() in NOME_DE_FERRAMENTA:
        yield achado(
            Nivel.PERIGO,
            arq,
            f"programa com nome de ferramenta: {arq.nome}",
            "No Windows, o editor e o terminal podem rodar o programa da pasta do projeto NO LUGAR do "
            "verdadeiro (a Mindgard mostrou isso no Cursor com um git.exe falso, em jul/2026).",
        )
    elif tipo or arq.extensao in EXTENSOES:
        yield achado(
            Nivel.ATENCAO,
            arq,
            f"{tipo or 'programa compilado'} dentro do projeto",
            "Código que já vem compilado: nem você nem eu conseguimos ler o que ele faz. Num teste técnico, "
            "não tem motivo pra existir.",
        )


def _atalho(arq: Arquivo) -> Iterator[Achado]:
    if arq.atalho_pra_fora:
        yield achado(
            Nivel.PERIGO if arq.eh_sensivel else Nivel.ATENCAO,
            arq,
            "atalho que aponta pra FORA do projeto",
            "Parece um arquivo do projeto, mas é uma porta pra outra pasta do seu computador. Quem lê esse "
            "'arquivo' (editor, agente, ferramenta) lê, na verdade, o destino. Eu não abri.",
            trecho=f"→ {arq.link_para}",
        )
    elif arq.eh_sensivel:
        yield achado(
            Nivel.ATENCAO,
            arq,
            "configuração disfarçada de atalho",
            "O editor e o agente leem o arquivo de destino como se fosse este. Eu também li (os achados "
            "dele aparecem com este nome), mas atalho em arquivo de configuração não é normal.",
            trecho=f"→ {arq.link_para}",
        )
