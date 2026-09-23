"""Worker de execução de jobs de relatório."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread
from time import sleep

from agents.report_pipeline import new_execution_id
from config import AppConfig
from guardrails.audit_logger import ExecutionTracker, create_audit_logger
from services.job_store import DEFAULT_LEASE_SECONDS, JobStore, ReportJob
from services.report_service import GenerateReportService

logger = logging.getLogger(__name__)


class ReportWorker:
    """Executa jobs pendentes do store.

    Enquanto um job executa, uma thread de heartbeat renova o lease dele a
    cada ``heartbeat_interval_seconds``. Se o processo cai, o heartbeat para
    e o lease expira: outro worker (ou este, ao reiniciar) reivindica o job
    e retoma do blackboard pelo mesmo ``execution_id``.
    """

    def __init__(
        self,
        job_store: JobStore,
        poll_interval_seconds: float = 2.0,
        heartbeat_interval_seconds: float | None = None,
    ):
        self.job_store = job_store
        self.poll_interval_seconds = poll_interval_seconds
        if heartbeat_interval_seconds is None:
            # Três renovações por lease: tolera um heartbeat perdido.
            lease_seconds = getattr(job_store, "lease_seconds", DEFAULT_LEASE_SECONDS)
            heartbeat_interval_seconds = lease_seconds / 3
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds deve ser positivo")
        self.heartbeat_interval_seconds = heartbeat_interval_seconds

    def run_once(self) -> ReportJob | None:
        """Executa um único job pendente (ou órfão recuperado), se existir."""
        job = self.job_store.claim_next()
        if job is None:
            return None

        if job.attempts > 1:
            logger.warning(
                "Recuperando job órfão %s (tentativa %d, execution_id=%s)",
                job.job_id,
                job.attempts,
                job.execution_id,
            )
        else:
            logger.info("Executando job de relatório: %s", job.job_id)

        # Registrado antes de executar: um job que falhar (ou cujo worker
        # cair) carrega o execution_id necessário para retomar do ponto da
        # falha. Um job recuperado já tem o execution_id da tentativa
        # anterior e continua o mesmo blackboard.
        execution_id = (
            job.payload.get("execution_id") or job.execution_id or new_execution_id()
        )
        self.job_store.set_execution_id(job.job_id, execution_id)

        audit_logger = None
        try:
            with self._heartbeat(job):
                # Payload vem de cliente (API/retry): caminhos presos às bases
                # do servidor, inclusive para jobs antigos já enfileirados.
                config = AppConfig.for_client_request(
                    model_name=job.payload.get("model"),
                    output_dir=job.payload.get("output_dir"),
                    db_path=job.payload.get("db_path"),
                )
                config.ensure_runtime_dirs()

                audit_logger = create_audit_logger(config.logs_dir)
                service = GenerateReportService(
                    config=config,
                    audit_logger=audit_logger,
                    execution_tracker=ExecutionTracker(),
                )
                result = service.run(execution_id=execution_id)

        except Exception as exc:
            self.job_store.mark_failed(job.job_id, str(exc))
            logger.exception("Job de relatório falhou: %s", job.job_id)
            return self.job_store.get(job.job_id)

        finally:
            if audit_logger is not None:
                audit_logger.close()

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

    @contextmanager
    def _heartbeat(self, job: ReportJob) -> Iterator[None]:
        """Renova o lease de ``job`` em segundo plano enquanto o bloco roda."""
        if job.lease_owner is None:
            yield
            return

        lease_owner = job.lease_owner
        stop = Event()

        def beat() -> None:
            while not stop.wait(self.heartbeat_interval_seconds):
                try:
                    renewed = self.job_store.heartbeat(job.job_id, lease_owner)
                except Exception:
                    # Falha transitória (ex.: banco travado): tenta de novo no
                    # próximo intervalo; o lease ainda tem folga.
                    logger.exception("Heartbeat falhou para o job %s", job.job_id)
                    continue
                if not renewed:
                    logger.warning(
                        "Lease do job %s foi perdido; heartbeat encerrado",
                        job.job_id,
                    )
                    return

        thread = Thread(target=beat, name=f"heartbeat-{job.job_id}", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join()

    def run_forever(self) -> None:
        """Executa continuamente, aguardando jobs pendentes."""
        while True:
            job = self.run_once()
            if job is None:
                sleep(self.poll_interval_seconds)
