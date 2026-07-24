"""Armazenamento simples de jobs para execução assíncrona."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import json
import sqlite3
from threading import Lock
from typing import Dict, Iterator, List, Optional, Protocol, Union
from uuid import uuid4


class JobStatus(str, Enum):
    """Estados possíveis de um job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class ReportJob:
    """Representa o estado de uma geração de relatório."""

    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    execution_id: Optional[str] = None
    report_path: Optional[str] = None
    duration_ms: Optional[float] = None
    pii_detected: bool = False
    pii_types: List[str] = field(default_factory=list)
    summary: Optional[dict] = None
    error: Optional[str] = None
    payload: dict = field(default_factory=dict)


class JobStore(Protocol):
    """Contrato de persistência para jobs."""

    def create(self, payload: Optional[dict] = None) -> ReportJob:
        """Cria um job pendente."""

    def get(self, job_id: str) -> Optional[ReportJob]:
        """Retorna um job pelo id."""

    def mark_running(self, job_id: str) -> None:
        """Marca o job como em execução."""

    def set_execution_id(self, job_id: str, execution_id: str) -> None:
        """Registra o execution_id no início da execução (permite retry)."""

    def mark_succeeded(
        self,
        job_id: str,
        *,
        execution_id: str,
        report_path: str,
        duration_ms: float,
        pii_detected: bool,
        pii_types: List[str],
        summary: dict,
    ) -> None:
        """Marca o job como concluído."""

    def mark_failed(self, job_id: str, error: str) -> None:
        """Marca o job como falho."""

    def claim_next(self) -> Optional[ReportJob]:
        """Reserva o próximo job pendente para execução."""

    def list_recent(
        self,
        limit: int = 20,
        status: Optional[JobStatus] = None,
    ) -> List[ReportJob]:
        """Lista jobs recentes."""

    def status_counts(self) -> Dict[JobStatus, int]:
        """Conta jobs por status."""


class InMemoryJobStore:
    """Store em memória para jobs.

    Serve como contrato inicial. Em produção, a mesma interface pode ser
    implementada com Redis, Postgres ou um backend de filas.
    """

    def __init__(self):
        self._jobs: Dict[str, ReportJob] = {}
        self._lock = Lock()

    def create(self, payload: Optional[dict] = None) -> ReportJob:
        """Cria um job pendente."""
        now = datetime.now()
        job = ReportJob(
            job_id=str(uuid4()),
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            payload=payload or {},
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[ReportJob]:
        """Retorna um job pelo id."""
        with self._lock:
            return self._jobs.get(job_id)

    def mark_running(self, job_id: str) -> None:
        """Marca o job como em execução."""
        self._update(job_id, status=JobStatus.RUNNING)

    def set_execution_id(self, job_id: str, execution_id: str) -> None:
        """Registra o execution_id no início da execução (permite retry)."""
        self._update(job_id, execution_id=execution_id)

    def mark_succeeded(
        self,
        job_id: str,
        *,
        execution_id: str,
        report_path: str,
        duration_ms: float,
        pii_detected: bool,
        pii_types: List[str],
        summary: dict,
    ) -> None:
        """Marca o job como concluído com sucesso."""
        self._update(
            job_id,
            status=JobStatus.SUCCEEDED,
            execution_id=execution_id,
            report_path=report_path,
            duration_ms=duration_ms,
            pii_detected=pii_detected,
            pii_types=pii_types,
            summary=summary,
            error=None,
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        """Marca o job como falho."""
        self._update(job_id, status=JobStatus.FAILED, error=error)

    def claim_next(self) -> Optional[ReportJob]:
        """Reserva o próximo job pendente para execução."""
        with self._lock:
            queued_jobs = [
                job for job in self._jobs.values()
                if job.status == JobStatus.QUEUED
            ]
            if not queued_jobs:
                return None
            job = sorted(queued_jobs, key=lambda item: item.created_at)[0]
            job.status = JobStatus.RUNNING
            job.updated_at = datetime.now()
            return job

    def list_recent(
        self,
        limit: int = 20,
        status: Optional[JobStatus] = None,
    ) -> List[ReportJob]:
        """Lista jobs recentes."""
        with self._lock:
            jobs = list(self._jobs.values())
            if status is not None:
                jobs = [job for job in jobs if job.status == status]
            return sorted(
                jobs,
                key=lambda item: item.created_at,
                reverse=True,
            )[:limit]

    def status_counts(self) -> Dict[JobStatus, int]:
        """Conta jobs por status."""
        with self._lock:
            counts = {status: 0 for status in JobStatus}
            for job in self._jobs.values():
                counts[job.status] += 1
            return counts

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = datetime.now()


class SQLiteJobStore:
    """Store persistente de jobs em SQLite."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()

    def create(self, payload: Optional[dict] = None) -> ReportJob:
        """Cria um job pendente."""
        now = datetime.now()
        job = ReportJob(
            job_id=str(uuid4()),
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            payload=payload or {},
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO report_jobs (
                    job_id, status, created_at, updated_at, pii_detected,
                    pii_types, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.status.value,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                    int(job.pii_detected),
                    json.dumps(job.pii_types),
                    json.dumps(job.payload),
                ),
            )
        return job

    def get(self, job_id: str) -> Optional[ReportJob]:
        """Retorna um job pelo id."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM report_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def mark_running(self, job_id: str) -> None:
        """Marca o job como em execução."""
        self._update(job_id, status=JobStatus.RUNNING.value)

    def set_execution_id(self, job_id: str, execution_id: str) -> None:
        """Registra o execution_id no início da execução (permite retry)."""
        self._update(job_id, execution_id=execution_id)

    def mark_succeeded(
        self,
        job_id: str,
        *,
        execution_id: str,
        report_path: str,
        duration_ms: float,
        pii_detected: bool,
        pii_types: List[str],
        summary: dict,
    ) -> None:
        """Marca o job como concluído com sucesso."""
        self._update(
            job_id,
            status=JobStatus.SUCCEEDED.value,
            execution_id=execution_id,
            report_path=report_path,
            duration_ms=duration_ms,
            pii_detected=int(pii_detected),
            pii_types=json.dumps(pii_types),
            summary=json.dumps(summary),
            error=None,
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        """Marca o job como falho."""
        self._update(job_id, status=JobStatus.FAILED.value, error=error)

    def claim_next(self) -> Optional[ReportJob]:
        """Reserva o próximo job pendente para execução."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM report_jobs
                WHERE status = ?
                ORDER BY created_at
                LIMIT 1
                """,
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None

            updated_at = datetime.now().isoformat()
            conn.execute(
                """
                UPDATE report_jobs
                SET status = ?, updated_at = ?
                WHERE job_id = ? AND status = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    updated_at,
                    row["job_id"],
                    JobStatus.QUEUED.value,
                ),
            )

            claimed = conn.execute(
                "SELECT * FROM report_jobs WHERE job_id = ?",
                (row["job_id"],),
            ).fetchone()

        return self._row_to_job(claimed) if claimed else None

    def list_recent(
        self,
        limit: int = 20,
        status: Optional[JobStatus] = None,
    ) -> List[ReportJob]:
        """Lista jobs recentes."""
        bounded_limit = max(1, min(limit, 100))
        query = "SELECT * FROM report_jobs"
        params: list = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(bounded_limit)

        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def status_counts(self) -> Dict[JobStatus, int]:
        """Conta jobs por status."""
        counts = {status: 0 for status in JobStatus}
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM report_jobs
                GROUP BY status
                """
            ).fetchall()

        for row in rows:
            counts[JobStatus(row["status"])] = row["total"]
        return counts

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS report_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    execution_id TEXT,
                    report_path TEXT,
                    duration_ms REAL,
                    pii_detected INTEGER NOT NULL DEFAULT 0,
                    pii_types TEXT NOT NULL DEFAULT '[]',
                    summary TEXT,
                    error TEXT,
                    payload TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(report_jobs)").fetchall()
            }
            if "payload" not in existing_columns:
                conn.execute(
                    "ALTER TABLE report_jobs ADD COLUMN payload TEXT NOT NULL DEFAULT '{}'"
                )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_report_jobs_status
                ON report_jobs(status)
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Abre uma conexão com commit/rollback e fechamento determinísticos.

        ``sqlite3.Connection`` como context manager gerencia apenas a
        transação; sem o ``close()`` explícito a conexão ficava aberta e
        mantinha o arquivo travado (falhas de remoção no Windows).
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _update(self, job_id: str, **changes) -> None:
        changes["updated_at"] = datetime.now().isoformat()
        columns = ", ".join(f"{key} = ?" for key in changes)
        values = list(changes.values()) + [job_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE report_jobs SET {columns} WHERE job_id = ?",
                values,
            )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> ReportJob:
        return ReportJob(
            job_id=row["job_id"],
            status=JobStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            execution_id=row["execution_id"],
            report_path=row["report_path"],
            duration_ms=row["duration_ms"],
            pii_detected=bool(row["pii_detected"]),
            pii_types=json.loads(row["pii_types"] or "[]"),
            summary=json.loads(row["summary"]) if row["summary"] else None,
            error=row["error"],
            payload=json.loads(row["payload"] or "{}"),
        )
