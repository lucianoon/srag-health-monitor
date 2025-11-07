from pathlib import Path
import os

# Base do projeto (pode ser sobrescrito via variável de ambiente SRAG_BASE_DIR)
BASE_DIR = Path(os.getenv("SRAG_BASE_DIR", Path(__file__).resolve().parents[1]))

DATA_DIR = BASE_DIR / "data"
OUTPUTS_DIR = BASE_DIR / "outputs"
REPORTS_DIR = OUTPUTS_DIR / "reports"
LOGS_DIR = OUTPUTS_DIR / "logs"