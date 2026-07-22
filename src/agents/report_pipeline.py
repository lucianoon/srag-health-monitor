"""Orquestrador multiagente para relatórios de SRAG.

Coordenação por estado (blackboard), não por fluxo de chamadas: cada etapa
declara pré-condições sobre o estado compartilhado e executa quando elas são
satisfeitas. Consequências práticas:

- coleta de dados e de notícias rodam em paralelo (nenhuma depende da outra);
- o progresso é persistido por etapa — recriar o orquestrador com o mesmo
  execution_id retoma do ponto da falha sem refazer etapas concluídas;
- adicionar uma etapa nova (ex.: verificação de qualidade de dados) é declarar
  um novo observador, sem tocar nas demais.
"""

from dataclasses import asdict
from datetime import datetime
import logging
from typing import List, Optional

from agents.data_ingestion_agent import DataSnapshot, SUSDataIngestionAgent
from agents.epidemiology_analysis_agent import (
    EpidemiologyAnalysis,
    EpidemiologyAnalysisAgent,
)
from agents.report_writer_agent import ReportWriterAgent
from config import AppConfig
from services.report_blackboard import ReportBlackboard, Step


logger = logging.getLogger(__name__)


class SRAGMultiAgentReportOrchestrator:
    """Coordena ingestão, análise epidemiológica e escrita de relatório."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        execution_id: Optional[str] = None,
    ):
        self.config = config or AppConfig.from_env()
        self.config.ensure_runtime_dirs()
        # Reaproveitar um execution_id retoma a execução do ponto da falha.
        self.execution_id = execution_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.report_path = self.config.reports_dir / f"relatorio_{self.execution_id}.md"
        self.state_path = (
            self.config.data_dir / "pipeline_state" / f"{self.execution_id}.json"
        )

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
        """Executa o pipeline multiagente guiado pelo blackboard."""
        logger.info(
            "Iniciando pipeline multiagente de relatório - ID: %s",
            self.execution_id,
        )
        blackboard = ReportBlackboard(self._build_steps(), state_path=self.state_path)
        artifacts = blackboard.run()

        self.last_metrics = artifacts["metrics"]
        self.last_daily_cases = artifacts["daily_cases"]
        self.last_monthly_cases = artifacts["monthly_cases"]
        self.last_news = artifacts["news"]
        self.last_source = artifacts["source"]
        self.last_charts = artifacts["charts"]
        self.last_analysis = EpidemiologyAnalysis(**artifacts["analysis"])
        self.last_narrative_mode = artifacts["narrative_mode"]

        blackboard.clear_state()
        logger.info("Relatório salvo em: %s", self.report_path)
        return artifacts["report"]

    def _build_steps(self) -> List[Step]:
        return [
            Step(name="collect_data", run=self._collect_data),
            Step(name="collect_news", run=self._collect_news),
            Step(
                name="analyze",
                run=self._analyze,
                requires=("collect_data", "collect_news"),
            ),
            Step(name="generate_charts", run=self._generate_charts, requires=("analyze",)),
            Step(
                name="write_report",
                run=self._write_report,
                requires=("analyze", "generate_charts"),
            ),
        ]

    def _collect_data(self, artifacts: dict) -> dict:
        return self.ingestion_agent.collect_data()

    def _collect_news(self, artifacts: dict) -> dict:
        return self.ingestion_agent.collect_news()

    def _analyze(self, artifacts: dict) -> dict:
        snapshot = DataSnapshot(
            metrics=artifacts["metrics"],
            daily_cases=artifacts["daily_cases"],
            monthly_cases=artifacts["monthly_cases"],
            news=artifacts["news"],
            source=artifacts["source"],
        )
        analysis = self.analysis_agent.analyze(snapshot)
        return {"analysis": asdict(analysis)}

    def _generate_charts(self, artifacts: dict) -> dict:
        analysis = EpidemiologyAnalysis(**artifacts["analysis"])
        return {"charts": self.writer_agent.generate_charts(analysis)}

    def _write_report(self, artifacts: dict) -> dict:
        analysis = EpidemiologyAnalysis(**artifacts["analysis"])
        report = self.writer_agent.write(
            analysis=analysis,
            charts=artifacts["charts"],
            execution_id=self.execution_id,
        )
        self.report_path.write_text(report, encoding="utf-8")
        return {
            "report": report,
            "narrative_mode": self.writer_agent.narrative_mode,
        }
