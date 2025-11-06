"""Utility helpers for resolving project paths."""
from __future__ import annotations

from pathlib import Path
from typing import Union

ROOT_DIR: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = ROOT_DIR / "data"
OUTPUTS_DIR: Path = ROOT_DIR / "outputs"
REPORTS_DIR: Path = OUTPUTS_DIR / "reports"
LOGS_DIR: Path = OUTPUTS_DIR / "logs"
RAW_DATA_DIR: Path = DATA_DIR / "raw"
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
DEFAULT_DB_PATH: Path = DATA_DIR / "srag.db"

PathLike = Union[str, Path]

def resolve_path(path: PathLike | None) -> Path:
    """Resolve *path* relative to the project root.

    Args:
        path: Path provided by the caller. When *None*, the project root is
            returned.

    Returns:
        A ``Path`` object pointing to the requested location. Relative paths are
        interpreted from the repository root.
    """
    if path is None:
        return ROOT_DIR

    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return candidate


def ensure_directory(path: PathLike) -> Path:
    """Create *path* (if needed) and return it as a ``Path`` instance."""
    directory = resolve_path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory
