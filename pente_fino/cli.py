"""Linha de comando: python3 -m pente_fino PASTA"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pente_fino import relatorio
from pente_fino.demo import criar_demo
from pente_fino.pente import pentear

EXEMPLOS = """exemplos (no Windows, troque python3 por python ou py):
  python3 -m pente_fino ~/Downloads/teste-tecnico      olha a pasta antes de abrir
  python3 -m pente_fino . --json                       saída pra outras ferramentas
  python3 -m pente_fino --demo /tmp/vaga-dos-sonhos     cria um falso teste técnico INOFENSIVO pra testar

código de saída: 0 = sem perigo · 1 = achou perigo (com --estrito: qualquer coisa que não seja "limpo")
                 2 = uso errado · 3 = erro do próprio pente-fino"""


def main(argv: list[str] | None = None) -> int:
    for saida in (sys.stdout, sys.stderr):  # no Windows, o terminal pode não ser UTF-8: não quebra por acento
        if hasattr(saida, "reconfigure"):
            saida.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        prog="pente-fino",
        description="Pente-fino do Garoto;  —  olha uma pasta de código ANTES de você abrir no editor ou rodar "
        "qualquer coisa. Só lê: não executa nada e não acessa a internet.",
        epilog=EXEMPLOS,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pasta", nargs="?", default=".", type=Path, help="a pasta pra olhar (padrão: a atual)")
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    parser.add_argument("--tudo", action="store_true", help="olha também node_modules, dist, .venv e companhia")
    parser.add_argument("--sem-info", action="store_true", help="esconde os achados só informativos")
    parser.add_argument("--estrito", action="store_true", help="sai com erro em qualquer coisa que não seja limpo")
    parser.add_argument("--demo", action="store_true", help="cria na PASTA um falso teste técnico inofensivo")
    args = parser.parse_args(argv)

    if args.demo:
        if args.pasta.exists() and (not args.pasta.is_dir() or any(args.pasta.iterdir())):
            parser.error(f"{args.pasta} já existe e não é uma pasta vazia")
        criar_demo(args.pasta)
        print(f"Criei um falso teste técnico em {args.pasta} (tudo inofensivo: os comandos só dão echo).")
        print(f"Agora passa o pente:  python3 -m pente_fino {args.pasta}")
        return 0
    if not args.pasta.is_dir():
        parser.error(f"não achei a pasta {args.pasta}")

    try:
        resultado = pentear(args.pasta, tudo=args.tudo)
    except Exception as erro:  # bug meu: avisa com código próprio, pra não parecer "achou perigo"
        print(f"O pente-fino quebrou ({type(erro).__name__}: {erro}). Isso é bug meu: abre uma issue?", file=sys.stderr)
        return 3
    if args.json:
        print(relatorio.como_json(resultado))
    else:
        cor = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        print(relatorio.texto(resultado, cor=cor, sem_info=args.sem_info), end="")
    veredito = relatorio.veredito(resultado)
    return 1 if veredito == "PERIGO" or (args.estrito and veredito != "LIMPO") else 0
