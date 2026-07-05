"""
Configuração central da aplicação.

Este módulo concentra caminhos e opções de runtime para evitar acoplamento a
um ambiente específico. Variáveis de ambiente continuam tendo precedência.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union
from urllib.parse import urlparse
import json
import logging
import os


logger = logging.getLogger(__name__)


# Feeds oficiais/reconhecidos em vigilância epidemiológica no Brasil.
# Agência Fiocruz carrega os boletins InfoGripe (referência nacional de SRAG).
DEFAULT_NEWS_FEEDS: List[dict] = [
    {"name": "Agência Fiocruz de Notícias", "url": "https://agencia.fiocruz.br/rss.xml"},
    {
        "name": "Agência Brasil - Saúde",
        "url": "https://agenciabrasil.ebc.com.br/rss/saude/feed.xml",
    },
]


def _parse_news_feeds(raw: Optional[str]) -> List[dict]:
    """Interpreta SRAG_NEWS_FEEDS; volta ao default se ausente ou inválido.

    Aceita um JSON: lista de objetos {"name", "url"} ou lista de URLs (string).
    """
    if not raw or not raw.strip():
        return [dict(feed) for feed in DEFAULT_NEWS_FEEDS]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("SRAG_NEWS_FEEDS inválido (JSON); usando feeds padrão")
        return [dict(feed) for feed in DEFAULT_NEWS_FEEDS]

    feeds: List[dict] = []
    for entry in parsed if isinstance(parsed, list) else []:
        if isinstance(entry, str):
            url = entry.strip()
            if url:
                feeds.append({"name": urlparse(url).netloc or url, "url": url})
        elif isinstance(entry, dict) and entry.get("url"):
            url = str(entry["url"]).strip()
            feeds.append({"name": str(entry.get("name") or urlparse(url).netloc), "url": url})

    if not feeds:
        logger.warning("SRAG_NEWS_FEEDS sem entradas válidas; usando feeds padrão")
        return [dict(feed) for feed in DEFAULT_NEWS_FEEDS]
    return feeds


@dataclass(frozen=True)
class AppConfig:
    """Configuração de execução do SRAG Health Monitor."""

    project_root: Path
    data_dir: Path
    db_path: Path
    jobs_db_path: Path
    reports_dir: Path
    logs_dir: Path
    model_name: str
    openai_api_key: Optional[str]
    api_key: Optional[str] = None
    sus_data_url: Optional[str] = None
    sus_ingest_nrows: Optional[int] = None
    news_feeds: List[dict] = field(default_factory=lambda: [dict(f) for f in DEFAULT_NEWS_FEEDS])

    @classmethod
    def from_env(
        cls,
        *,
        model_name: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        db_path: Optional[Union[str, Path]] = None,
        jobs_db_path: Optional[Union[str, Path]] = None,
        log_dir: Optional[Union[str, Path]] = None,
    ) -> "AppConfig":
        """Cria configuração a partir de defaults e variáveis de ambiente."""
        project_root = Path(__file__).resolve().parents[1]
        data_dir = Path(os.getenv("SRAG_DATA_DIR", project_root / "data"))

        resolved_db_path = Path(
            db_path
            or os.getenv("SRAG_DB_PATH")
            or data_dir / "srag.db"
        )
        resolved_jobs_db_path = Path(
            jobs_db_path
            or os.getenv("SRAG_JOBS_DB_PATH")
            or data_dir / "jobs.db"
        )
        reports_dir = Path(
            output_dir
            or os.getenv("SRAG_OUTPUT_DIR")
            or project_root / "outputs" / "reports"
        )
        logs_dir = Path(
            log_dir
            or os.getenv("SRAG_LOG_DIR")
            or project_root / "outputs" / "logs"
        )

        return cls(
            project_root=project_root,
            data_dir=data_dir,
            db_path=resolved_db_path,
            jobs_db_path=resolved_jobs_db_path,
            reports_dir=reports_dir,
            logs_dir=logs_dir,
            model_name=model_name or os.getenv("SRAG_MODEL", "gpt-4.1-mini"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            api_key=os.getenv("SRAG_API_KEY"),
            sus_data_url=os.getenv("SRAG_SUS_DATA_URL"),
            sus_ingest_nrows=cls._optional_int(os.getenv("SRAG_SUS_INGEST_NROWS")),
            news_feeds=_parse_news_feeds(os.getenv("SRAG_NEWS_FEEDS")),
        )

    def ensure_runtime_dirs(self) -> None:
        """Garante que diretórios usados em runtime existam."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _optional_int(value: Optional[str]) -> Optional[int]:
        if value in (None, ""):
            return None
        return int(value)
