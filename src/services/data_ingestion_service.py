"""Serviço de ingestão de dados oficiais do SUS."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Optional
from urllib.parse import urlparse
import json
import logging

import requests

from config import AppConfig
from database.db_manager import SRAGDatabase
from utils.data_processor import SRAGDataProcessor


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DataIngestionResult:
    """Resultado estruturado da ingestão de dados."""

    source_url: str
    raw_path: Path
    processed_path: Path
    db_path: Path
    metadata_path: Path
    rows_processed: int
    duration_ms: float


class DataIngestionService:
    """Baixa, processa e carrega dados SRAG publicados pelo SUS."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.config.ensure_runtime_dirs()

    def run(
        self,
        *,
        source_url: Optional[str] = None,
        nrows: Optional[int] = None,
    ) -> DataIngestionResult:
        """Executa ingestão completa para o cache SQLite local."""
        resolved_source_url = source_url or self.config.sus_data_url
        if not resolved_source_url:
            raise ValueError(
                "Fonte SUS não configurada. Informe --source-url ou SRAG_SUS_DATA_URL."
            )

        started_at = perf_counter()
        raw_path = self._download_source(resolved_source_url)
        processed_path, rows_processed = self._process_source(
            raw_path=raw_path,
            nrows=nrows if nrows is not None else self.config.sus_ingest_nrows,
        )
        self._load_processed_data(processed_path)
        duration_ms = (perf_counter() - started_at) * 1000
        metadata_path = self._write_metadata(
            source_url=resolved_source_url,
            raw_path=raw_path,
            processed_path=processed_path,
            rows_processed=rows_processed,
            duration_ms=duration_ms,
        )

        return DataIngestionResult(
            source_url=resolved_source_url,
            raw_path=raw_path,
            processed_path=processed_path,
            db_path=self.config.db_path,
            metadata_path=metadata_path,
            rows_processed=rows_processed,
            duration_ms=duration_ms,
        )

    def _download_source(self, source_url: str) -> Path:
        raw_dir = self.config.data_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / self._filename_from_url(source_url)

        logger.info("Baixando dados SUS de %s", source_url)
        response = requests.get(source_url, stream=True, timeout=120)
        response.raise_for_status()

        with raw_path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_obj.write(chunk)

        return raw_path

    def _process_source(
        self,
        *,
        raw_path: Path,
        nrows: Optional[int],
    ) -> tuple[Path, int]:
        processed_dir = self.config.data_dir / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        processed_path = processed_dir / "srag_processed.csv"

        processor = SRAGDataProcessor(str(raw_path))
        processor.load_data(nrows=nrows)
        processed = processor.clean_data()
        processor.save_processed_data(str(processed_path))

        return processed_path, len(processed)

    def _load_processed_data(self, processed_path: Path) -> None:
        db = SRAGDatabase(str(self.config.db_path))
        db.connect()
        try:
            db.create_tables()
            db.clear_cases()
            db.load_data_from_csv(str(processed_path))
        finally:
            db.close()

    def _write_metadata(
        self,
        *,
        source_url: str,
        raw_path: Path,
        processed_path: Path,
        rows_processed: int,
        duration_ms: float,
    ) -> Path:
        metadata_path = self.config.data_dir / "ingestion_metadata.json"
        metadata = {
            "provider": "DATASUS/SIVEP-Gripe",
            "source_url": source_url,
            "raw_path": str(raw_path),
            "processed_path": str(processed_path),
            "db_path": str(self.config.db_path),
            "rows_processed": rows_processed,
            "duration_ms": duration_ms,
            "ingested_at": datetime.now().isoformat(),
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return metadata_path

    @staticmethod
    def _filename_from_url(source_url: str) -> str:
        parsed = urlparse(source_url)
        filename = Path(parsed.path).name
        if not filename:
            return "srag_source.csv"
        return filename
