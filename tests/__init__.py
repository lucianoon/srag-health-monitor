"""Pacote de testes do SRAG Health Monitor.

Garante que ``src/`` esteja no ``sys.path`` antes de qualquer import dos
módulos de teste — funciona tanto com ``python -m unittest discover`` (CI)
quanto com ``pytest``.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = str(PROJECT_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
