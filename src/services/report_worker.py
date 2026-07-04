"""Worker de execução de jobs de relatório."""

import logging
from time import sleep
from typing import Optional

from config import AppConfig
from guardrails.audit_logger import ExecutionTracker, create_audit_logger
from services.job_store import JobStore, ReportJob
from services.report_service import GenerateReportService

logger = logging.getLogger(__name__)


class ReportWorker:
    """Executa jobs pendentes do store."""

    def __init__(self, job_store: JobStore, poll_interval_seconds: float = 2.0):
        self.job_store = job_store
        self.poll_interval_seconds = poll_interval_seconds

    def run_once(self) -> Optional[ReportJob]:
        """Executa um único job pendente, se existir."""
        job = self.job_store.claim_next()
        if job is None:
            return None

        logger.info("Executando job de relatório: %s", job.job_id)

        try:
            config = AppConfig.from_env(
                model_name=job.payload.get("model"),
                output_dir=job.payload.get("output_dir"),
                db_path=job.payload.get("db_path"),
            )
            config.ensure_runtime_dirs()

            service = GenerateReportService(
                config=config,
                audit_logger=create_audit_logger(config.logs_dir),
                execution_tracker=ExecutionTracker(),
            )
            result = service.run()

        except Exception as exc:
            self.job_store.mark_failed(job.job_id, str(exc))
            logger.exception("Job de relatório falhou: %s", job.job_id)
            return self.job_store.get(job.job_id)

        self.job_store.mark_succeeded(
            job.job_id,
            execution_id=result.execution_id,
            report_path=str(result.report_path),
            duration_ms=result.duration_ms,
            pii_detected=result.pii_detected,
            pii_types=result.pii_types,
            summary=result.summary,
        )
        logger.info("Job de relatório concluído: %s", job.job_id)
        return self.job_store.get(job.job_id)

    def run_forever(self) -> None:
        """Executa continuamente, aguardando jobs pendentes."""
        while True:
            job = self.run_once()
            if job is None:
                sleep(self.poll_interval_seconds)
