"""Orquestrador multiagente para relatórios de SRAG."""

from datetime import datetime
import logging
from typing import Optional

from agents.data_ingestion_agent import SUSDataIngestionAgent
from agents.epidemiology_analysis_agent import EpidemiologyAnalysisAgent
from agents.report_writer_agent import ReportWriterAgent
from config import AppConfig


logger = logging.getLogger(__name__)


class SRAGMultiAgentReportOrchestrator:
    """Coordena ingestão, análise epidemiológica e escrita de relatório."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig.from_env()
        self.config.ensure_runtime_dirs()
        self.execution_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.report_path = self.config.reports_dir / f"relatorio_{self.execution_id}.md"

        self.ingestion_agent = SUSDataIngestionAgent(self.config)
        self.analysis_agent = EpidemiologyAnalysisAgent()
        self.writer_agent = ReportWriterAgent(self.config)

        self.last_metrics = {}
        self.last_daily_cases = {}
        self.last_monthly_cases = {}
        self.last_news = {}
        self.last_charts = {}
        self.last_source = {}
        self.last_analysis = None
        self.last_narrative_mode = "deterministica"

    def run(self) -> str:
        """Executa o pipeline multiagente completo."""
        logger.info(
            "Iniciando pipeline multiagente de relatório - ID: %s",
            self.execution_id,
        )

        snapshot = self.ingestion_agent.collect()
        self.last_metrics = snapshot.metrics
        self.last_daily_cases = snapshot.daily_cases
        self.last_monthly_cases = snapshot.monthly_cases
        self.last_news = snapshot.news
        self.last_source = snapshot.source

        analysis = self.analysis_agent.analyze(snapshot)
        self.last_analysis = analysis

        charts = self.writer_agent.generate_charts(analysis)
        self.last_charts = charts

        report = self.writer_agent.write(
            analysis=analysis,
            charts=charts,
            execution_id=self.execution_id,
        )
        self.last_narrative_mode = self.writer_agent.narrative_mode
        self.report_path.write_text(report, encoding="utf-8")
        logger.info("Relatório salvo em: %s", self.report_path)

        return report
