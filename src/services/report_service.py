"""
Caso de uso de geração de relatório.

Esta camada separa a lógica de aplicação das interfaces de entrada, como CLI,
API HTTP ou workers assíncronos.
"""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import List, Optional

from agents.report_pipeline import SRAGMultiAgentReportOrchestrator
from config import AppConfig
from guardrails.audit_logger import AuditLogger, ExecutionTracker
from guardrails.validators import DataPrivacyGuard, OutputValidator


@dataclass(frozen=True)
class GenerateReportResult:
    """Resultado estruturado da geração de relatório."""

    execution_id: str
    report: str
    report_path: Path
    duration_ms: float
    summary: dict
    pii_detected: bool
    pii_types: List[str]


class GenerateReportService:
    """Executa o caso de uso completo de geração de relatório."""

    def __init__(
        self,
        config: AppConfig,
        audit_logger: AuditLogger,
        execution_tracker: ExecutionTracker,
    ):
        self.config = config
        self.audit_logger = audit_logger
        self.execution_tracker = execution_tracker

    def run(self, execution_id: Optional[str] = None) -> GenerateReportResult:
        """Gera, valida, audita e retorna um relatório de SRAG.

        Passar o execution_id de uma execução que falhou retoma o pipeline
        do ponto da falha (estado persistido por etapa no blackboard).
        """
        orchestrator = SRAGMultiAgentReportOrchestrator(
            config=self.config,
            execution_id=execution_id,
        )
        execution_id = orchestrator.execution_id
        self.execution_tracker.start_execution(execution_id)

        self.audit_logger.log_agent_decision(
            decision="Iniciar geração de relatório",
            reasoning="Execução solicitada pela camada de aplicação",
            execution_id=execution_id,
            metadata={
                "model": self.config.model_name,
                "llm_enabled": bool(self.config.openai_api_key),
            }
        )

        started_at = perf_counter()

        try:
            report = orchestrator.run()
            duration_ms = (perf_counter() - started_at) * 1000

            valid, message = OutputValidator.validate_report_content(report)
            self.audit_logger.log_validation(
                validation_type="report_content",
                valid=valid,
                message=message,
                execution_id=execution_id
            )
            self.execution_tracker.add_validation(execution_id, "report_content", valid)

            if not valid:
                raise ValueError(message)

            pii_detected, pii_types = DataPrivacyGuard.check_for_pii(report)
            if pii_detected:
                report = DataPrivacyGuard.anonymize_text(report)
                orchestrator.report_path.write_text(report, encoding="utf-8")

            summary = self.execution_tracker.end_execution(execution_id)

            self.audit_logger.log_report_generation(
                execution_id=execution_id,
                metrics=orchestrator.last_metrics,
                news_count=len(orchestrator.last_news.get("news", [])),
                charts_generated=sum(
                    1 for chart in orchestrator.last_charts.values()
                    if chart.get("success")
                ),
                report_path=str(orchestrator.report_path),
                duration_ms=duration_ms
            )

            return GenerateReportResult(
                execution_id=execution_id,
                report=report,
                report_path=orchestrator.report_path,
                duration_ms=duration_ms,
                summary=summary,
                pii_detected=pii_detected,
                pii_types=pii_types,
            )

        except Exception as exc:
            self.audit_logger.log_error(
                error_type=type(exc).__name__,
                error_message=str(exc),
                execution_id=execution_id,
                stack_trace=None
            )
            self.execution_tracker.add_error(execution_id, type(exc).__name__)
            self.execution_tracker.end_execution(execution_id)
            raise
