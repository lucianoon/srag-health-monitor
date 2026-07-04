"""API HTTP do SRAG Health Monitor."""

from pathlib import Path
import secrets
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import AppConfig
from guardrails.audit_logger import ExecutionTracker, create_audit_logger
from services.job_store import JobStatus, ReportJob, SQLiteJobStore
from services.report_service import GenerateReportService


class GenerateReportRequest(BaseModel):
    """Parâmetros aceitos para geração de relatório via API."""

    model: Optional[str] = Field(default=None)
    output_dir: Optional[str] = Field(default=None)
    db_path: Optional[str] = Field(default=None)


class GenerateReportResponse(BaseModel):
    """Resposta da geração síncrona de relatório."""

    execution_id: str
    report_path: str
    duration_ms: float
    pii_detected: bool
    pii_types: List[str]
    summary: dict


class CreateReportJobResponse(BaseModel):
    """Resposta da criação de um job."""

    job_id: str
    status: JobStatus
    status_url: str


class ReportJobResponse(BaseModel):
    """Resposta de status de job."""

    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    execution_id: Optional[str] = None
    report_path: Optional[str] = None
    duration_ms: Optional[float] = None
    pii_detected: bool = False
    pii_types: List[str] = Field(default_factory=list)
    summary: Optional[dict] = None
    error: Optional[str] = None


class ReadinessResponse(BaseModel):
    """Resposta de readiness operacional."""

    status: str
    jobs_db_accessible: bool
    srag_db_exists: bool
    reports_dir_writable: bool
    logs_dir_writable: bool


class MetricsResponse(BaseModel):
    """Métricas operacionais básicas."""

    total_jobs: int
    jobs_by_status: dict
    recent_failures: List[ReportJobResponse]


app = FastAPI(
    title="SRAG Health Monitor API",
    version="0.1.0",
    description="API para geração de relatórios epidemiológicos de SRAG.",
)
job_store = SQLiteJobStore(AppConfig.from_env().jobs_db_path)


@app.get("/health")
def health() -> dict:
    """Healthcheck simples para orquestradores e load balancers."""
    return {"status": "ok"}


@app.get("/ready", response_model=ReadinessResponse)
def ready() -> ReadinessResponse:
    """Readiness check com dependências locais de runtime."""
    config = AppConfig.from_env()
    config.ensure_runtime_dirs()

    jobs_db_accessible = True
    try:
        job_store.list_recent(limit=1)
    except Exception:
        jobs_db_accessible = False

    reports_dir_writable = _is_writable_dir(config.reports_dir)
    logs_dir_writable = _is_writable_dir(config.logs_dir)
    is_ready = jobs_db_accessible and reports_dir_writable and logs_dir_writable

    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        jobs_db_accessible=jobs_db_accessible,
        srag_db_exists=config.db_path.exists(),
        reports_dir_writable=reports_dir_writable,
        logs_dir_writable=logs_dir_writable,
    )


def _build_config(request: GenerateReportRequest) -> AppConfig:
    config = AppConfig.from_env(
        model_name=request.model,
        output_dir=request.output_dir,
        db_path=request.db_path,
    )
    config.ensure_runtime_dirs()
    return config


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Exige X-API-Key quando SRAG_API_KEY estiver configurada."""
    expected_api_key = AppConfig.from_env().api_key
    if not expected_api_key:
        return

    if not x_api_key or not secrets.compare_digest(x_api_key, expected_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente",
        )


def _is_writable_dir(path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def _job_response(job: ReportJob) -> ReportJobResponse:
    return ReportJobResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        execution_id=job.execution_id,
        report_path=job.report_path,
        duration_ms=job.duration_ms,
        pii_detected=job.pii_detected,
        pii_types=job.pii_types,
        summary=job.summary,
        error=job.error,
    )


def _resolve_report_artifact(job: ReportJob) -> Path:
    if job.status != JobStatus.SUCCEEDED:
        raise HTTPException(
            status_code=409,
            detail="Relatório ainda não está disponível",
        )
    if not job.report_path:
        raise HTTPException(
            status_code=404,
            detail="Artefato do relatório não registrado",
        )

    report_path = Path(job.report_path).resolve()
    if report_path.suffix.lower() != ".md":
        raise HTTPException(
            status_code=403,
            detail="Tipo de artefato não permitido",
        )
    if not report_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Artefato do relatório não encontrado",
        )
    return report_path


@app.post(
    "/reports",
    response_model=CreateReportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_report_job(
    request: GenerateReportRequest,
    _auth: None = Depends(require_api_key),
) -> CreateReportJobResponse:
    """Cria um job para geração assíncrona por worker."""
    job = job_store.create(payload=request.model_dump(exclude_none=True))

    return CreateReportJobResponse(
        job_id=job.job_id,
        status=job.status,
        status_url=f"/reports/{job.job_id}",
    )


@app.get("/reports", response_model=List[ReportJobResponse])
def list_report_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[JobStatus] = Query(default=None, alias="status"),
    _auth: None = Depends(require_api_key),
) -> List[ReportJobResponse]:
    """Lista jobs recentes, opcionalmente filtrados por status."""
    jobs = job_store.list_recent(limit=limit, status=status_filter)
    return [_job_response(job) for job in jobs]


@app.get("/metrics", response_model=MetricsResponse)
def metrics(_auth: None = Depends(require_api_key)) -> MetricsResponse:
    """Retorna métricas operacionais simples para dashboards e alertas."""
    counts = job_store.status_counts()
    failures = job_store.list_recent(limit=5, status=JobStatus.FAILED)

    return MetricsResponse(
        total_jobs=sum(counts.values()),
        jobs_by_status={status.value: total for status, total in counts.items()},
        recent_failures=[_job_response(job) for job in failures],
    )


@app.get("/reports/{job_id}", response_model=ReportJobResponse)
def get_report_job(
    job_id: str,
    _auth: None = Depends(require_api_key),
) -> ReportJobResponse:
    """Consulta status e resultado de um job."""
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return _job_response(job)


@app.get("/reports/{job_id}/artifact")
def get_report_artifact(
    job_id: str,
    _auth: None = Depends(require_api_key),
) -> FileResponse:
    """Baixa o relatório Markdown gerado por um job concluído."""
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    report_path = _resolve_report_artifact(job)
    return FileResponse(
        report_path,
        media_type="text/markdown",
        filename=report_path.name,
    )


@app.post("/reports/sync", response_model=GenerateReportResponse)
def generate_report_sync(
    request: GenerateReportRequest,
    _auth: None = Depends(require_api_key),
) -> GenerateReportResponse:
    """Gera um relatório de SRAG de forma síncrona."""
    config = _build_config(request)

    service = GenerateReportService(
        config=config,
        audit_logger=create_audit_logger(config.logs_dir),
        execution_tracker=ExecutionTracker(),
    )

    try:
        result = service.run()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return GenerateReportResponse(
        execution_id=result.execution_id,
        report_path=str(result.report_path),
        duration_ms=result.duration_ms,
        pii_detected=result.pii_detected,
        pii_types=result.pii_types,
        summary=result.summary,
    )
