"""Agente de ingestão de dados oficiais de SRAG."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from config import AppConfig
from services.data_ingestion_service import DataIngestionResult, DataIngestionService
from tools.database_tool import create_database_tool
from tools.news_tool import create_news_tool


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DataSnapshot:
    """Pacote de dados coletados para análise epidemiológica."""

    metrics: dict
    daily_cases: dict
    monthly_cases: dict
    news: dict
    source: dict


class SUSDataIngestionAgent:
    """Coleta e valida dados de SRAG.

    A implementação atual usa o SQLite local como cache curado. O contrato já
    separa a etapa de ingestão para plugar APIs oficiais ou downloads
    OpenDATASUS sem alterar a análise nem o relatório.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.database_tool = create_database_tool(db_path=str(config.db_path))
        self.news_tool = create_news_tool(feeds=config.news_feeds)

    def collect(self, days: int = 30, months: int = 12, news_limit: int = 5) -> DataSnapshot:
        """Coleta métricas, séries temporais, notícias e metadados da fonte."""
        data = self.collect_data(days=days, months=months)
        news = self.collect_news(news_limit=news_limit)
        return DataSnapshot(**data, **news)

    def collect_data(self, days: int = 30, months: int = 12) -> dict:
        """Coleta métricas, séries temporais e metadados da fonte oficial.

        Etapa independente da coleta de notícias — as duas podem rodar em
        paralelo no blackboard do pipeline.
        """
        logger.info("Agente de ingestão coletando dados de SRAG")
        self._ensure_source_available()

        metrics = self.database_tool._run(query_type="metrics")
        self._raise_if_tool_error(metrics, "Falha ao coletar métricas")

        daily_cases = self.database_tool._run(query_type="daily_cases", days=days)
        self._raise_if_tool_error(daily_cases, "Falha ao coletar casos diários")

        monthly_cases = self.database_tool._run(query_type="monthly_cases", months=months)
        self._raise_if_tool_error(monthly_cases, "Falha ao coletar casos mensais")

        return {
            "metrics": metrics,
            "daily_cases": daily_cases,
            "monthly_cases": monthly_cases,
            "source": self._source_metadata(),
        }

    def collect_news(self, news_limit: int = 5) -> dict:
        """Coleta notícias recentes sobre SRAG nos feeds configurados."""
        logger.info("Agente de ingestão coletando notícias de SRAG")
        news = self.news_tool._run(max_results=news_limit)
        self._raise_if_tool_error(news, "Falha ao coletar notícias")
        return {"news": news}

    def refresh_cache(
        self,
        *,
        source_url: Optional[str] = None,
        nrows: Optional[int] = None,
    ) -> DataIngestionResult:
        """Atualiza o cache local a partir de uma fonte oficial configurada."""
        logger.info("Agente de ingestão atualizando cache local de dados SUS")
        return DataIngestionService(self.config).run(
            source_url=source_url,
            nrows=nrows,
        )

    def _ensure_source_available(self) -> None:
        if not self.config.db_path.exists():
            raise RuntimeError(
                "Banco de dados não encontrado em "
                f"{self.config.db_path}. Execute o pipeline de ingestão SUS "
                "antes de gerar relatórios."
            )

    def _source_metadata(self) -> dict:
        db_path = Path(self.config.db_path)
        updated_at: Optional[str] = None
        if db_path.exists():
            updated_at = datetime.fromtimestamp(db_path.stat().st_mtime).isoformat()

        return {
            "provider": "DATASUS/SIVEP-Gripe",
            "source_type": "sqlite_cache",
            "db_path": str(db_path),
            "updated_at": updated_at,
            "source_url": self.config.sus_data_url,
        }

    @staticmethod
    def _raise_if_tool_error(result: dict, context: str) -> None:
        if result.get("error"):
            raise RuntimeError(f"{context}: {result['error']}")
