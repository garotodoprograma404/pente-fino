import os
import sys

# O `python -m` põe a pasta ATUAL na frente da biblioteca padrão. Se a pasta atual for a suspeita, um argparse.py
# dela rodaria no lugar do oficial ANTES do pente começar. Aqui a gente tira a pasta atual do caminho dos módulos,
# antes de importar qualquer coisa (os e sys já vêm carregados pelo próprio Python).
try:
    _aqui = os.getcwd()
except OSError:  # a pasta atual foi apagada
    _aqui = ""
sys.path[:] = [p for p in sys.path if p not in ("", ".") and os.path.abspath(p) != _aqui]

from pente_fino.cli import main  # noqa: E402

raise SystemExit(main())
