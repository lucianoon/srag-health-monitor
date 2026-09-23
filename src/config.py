"""
Configuração central da aplicação.

Este módulo concentra caminhos e opções de runtime para evitar acoplamento a
um ambiente específico. Variáveis de ambiente continuam tendo precedência.
"""

import json
import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Feeds oficiais/reconhecidos em vigilância epidemiológica no Brasil.
# Agência Fiocruz carrega os boletins InfoGripe (referência nacional de SRAG).
DEFAULT_NEWS_FEEDS: list[dict] = [
    {"name": "Agência Fiocruz de Notícias", "url": "https://agencia.fiocruz.br/rss.xml"},
    {
        "name": "Agência Brasil - Saúde",
        "url": "https://agenciabrasil.ebc.com.br/rss/saude/feed.xml",
    },
]


def _parse_news_feeds(raw: str | None) -> list[dict]:
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

    feeds: list[dict] = []
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


class UnsafePathError(ValueError):
    """Caminho vindo de cliente que escaparia do diretório base do servidor."""


def check_relative_path(value: str) -> str:
    """Validação sintática de um caminho vindo de cliente.

    Aceita apenas caminhos relativos, sem ``..``, sem raiz, drive ou UNC
    (em qualquer convenção de separador) e sem byte nulo. Não toca o
    sistema de arquivos; a contenção real é feita por ``resolve_within``.
    """
    if not isinstance(value, str) or not value.strip():
        raise UnsafePathError("caminho vazio ou inválido não é aceito")
    if "\x00" in value:
        raise UnsafePathError("caminho com byte nulo não é aceito")

    normalized = value.replace("\\", "/")
    windows_path = PureWindowsPath(value)
    if (
        PurePosixPath(normalized).is_absolute()
        or windows_path.drive
        or windows_path.root
    ):
        raise UnsafePathError("caminhos absolutos não são aceitos")
    if ".." in PurePosixPath(normalized).parts:
        raise UnsafePathError("segmentos '..' não são aceitos")
    return value


def resolve_within(base: str | Path, value: str) -> Path:
    """Resolve ``value`` relativo a ``base`` garantindo que fique dentro dela.

    Além da checagem sintática, o caminho é resolvido (seguindo symlinks
    existentes) e comparado com a base resolvida: um symlink dentro da base
    que aponte para fora dela também é rejeitado.
    """
    check_relative_path(value)
    base_resolved = Path(base).resolve()
    candidate = (base_resolved / value.replace("\\", "/")).resolve()
    if not candidate.is_relative_to(base_resolved):
        raise UnsafePathError("caminho fora do diretório base permitido")
    return candidate


def ensure_within(base: str | Path, path: str | Path) -> Path:
    """Garante que um caminho gravado pelo servidor esteja dentro de ``base``.

    Para caminhos persistidos (ex.: ``report_path`` de jobs, inclusive
    antigos): absolutos são aceitos desde que, resolvidos (seguindo
    symlinks), fiquem dentro da base; relativos passam por
    ``resolve_within``. Segmentos ``..`` são rejeitados em qualquer caso.
    """
    raw = str(path)
    if not raw.strip() or "\x00" in raw:
        raise UnsafePathError("caminho vazio ou inválido")
    candidate = Path(raw)
    if not candidate.is_absolute():
        return resolve_within(base, raw)
    if ".." in PurePosixPath(raw.replace("\\", "/")).parts:
        raise UnsafePathError("segmentos '..' não são aceitos")
    base_resolved = Path(base).resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base_resolved):
        raise UnsafePathError("caminho fora do diretório base permitido")
    return resolved


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
    openai_api_key: str | None
    api_key: str | None = None
    sus_data_url: str | None = None
    sus_ingest_nrows: int | None = None
    job_lease_seconds: float = 60.0
    job_max_attempts: int = 3
    news_feeds: list[dict] = field(default_factory=lambda: [dict(f) for f in DEFAULT_NEWS_FEEDS])

    @classmethod
    def from_env(
        cls,
        *,
        model_name: str | None = None,
        output_dir: str | Path | None = None,
        db_path: str | Path | None = None,
        jobs_db_path: str | Path | None = None,
        log_dir: str | Path | None = None,
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
            model_name=model_name or os.getenv("SRAG_MODEL") or "gpt-4.1-mini",
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            api_key=os.getenv("SRAG_API_KEY"),
            sus_data_url=os.getenv("SRAG_SUS_DATA_URL"),
            sus_ingest_nrows=cls._optional_int(os.getenv("SRAG_SUS_INGEST_NROWS")),
            job_lease_seconds=float(os.getenv("SRAG_JOB_LEASE_SECONDS") or 60.0),
            job_max_attempts=int(os.getenv("SRAG_JOB_MAX_ATTEMPTS") or 3),
            news_feeds=_parse_news_feeds(os.getenv("SRAG_NEWS_FEEDS")),
        )

    @classmethod
    def for_client_request(
        cls,
        *,
        model_name: str | None = None,
        output_dir: str | None = None,
        db_path: str | None = None,
    ) -> "AppConfig":
        """Cria configuração a partir de parâmetros vindos de clientes (API/jobs).

        Diferente de ``from_env`` (usado pela CLI, que é confiável), os
        caminhos aqui ficam presos aos diretórios base definidos pelo
        servidor: ``db_path`` é relativo a ``data_dir`` (``SRAG_DATA_DIR``) e
        ``output_dir`` é um subdiretório de ``reports_dir``
        (``SRAG_OUTPUT_DIR``). Caminhos absolutos, ``..`` e symlinks para
        fora da base levantam ``UnsafePathError``.
        """
        base = cls.from_env(model_name=model_name)
        return replace(
            base,
            db_path=(
                resolve_within(base.data_dir, db_path)
                if db_path is not None
                else base.db_path
            ),
            reports_dir=(
                resolve_within(base.reports_dir, output_dir)
                if output_dir is not None
                else base.reports_dir
            ),
        )

    def ensure_runtime_dirs(self) -> None:
        """Garante que diretórios usados em runtime existam."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _optional_int(value: str | None) -> int | None:
        if value in (None, ""):
            return None
        return int(value)
