"""Armazenamento simples de jobs para execução assíncrona."""

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import uuid4

DEFAULT_LEASE_SECONDS = 60.0
"""Duração do lease de um job em execução, renovado pelo heartbeat do worker."""

DEFAULT_MAX_ATTEMPTS = 3
"""Quantas vezes um job pode ser reivindicado antes de ser dado como falho."""


def _lease_exhausted_error(attempts: int, max_attempts: int) -> str:
    return (
        f"Lease expirado sem heartbeat após {attempts} tentativa(s) "
        f"(limite de {max_attempts}): o worker provavelmente caiu durante a "
        "execução. Use POST /reports/{job_id}/retry para tentar de novo."
    )


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
    execution_id: str | None = None
    report_path: str | None = None
    duration_ms: float | None = None
    pii_detected: bool = False
    pii_types: list[str] = field(default_factory=list)
    summary: dict | None = None
    error: str | None = None
    payload: dict = field(default_factory=dict)
    attempts: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None


class JobStore(Protocol):
    """Contrato de persistência para jobs."""

    def create(self, payload: dict | None = None) -> ReportJob:
        """Cria um job pendente."""

    def get(self, job_id: str) -> ReportJob | None:
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
        pii_types: list[str],
        summary: dict,
    ) -> None:
        """Marca o job como concluído."""

    def mark_failed(self, job_id: str, error: str) -> None:
        """Marca o job como falho."""

    def claim_next(self) -> ReportJob | None:
        """Reserva o próximo job pendente (ou órfão com lease expirado)."""

    def heartbeat(self, job_id: str, lease_owner: str) -> bool:
        """Renova o lease do job; ``False`` se o lease não é mais deste dono."""

    def list_recent(
        self,
        limit: int = 20,
        status: JobStatus | None = None,
    ) -> list[ReportJob]:
        """Lista jobs recentes."""

    def status_counts(self) -> dict[JobStatus, int]:
        """Conta jobs por status."""


class InMemoryJobStore:
    """Store em memória para jobs.

    Serve como contrato inicial. Em produção, a mesma interface pode ser
    implementada com Redis, Postgres ou um backend de filas.
    """

    def __init__(
        self,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self._jobs: dict[str, ReportJob] = {}
        self._lock = Lock()
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self._clock = clock

    def create(self, payload: dict | None = None) -> ReportJob:
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

    def get(self, job_id: str) -> ReportJob | None:
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
        pii_types: list[str],
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
            lease_owner=None,
            lease_expires_at=None,
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        """Marca o job como falho."""
        self._update(
            job_id,
            status=JobStatus.FAILED,
            error=error,
            lease_owner=None,
            lease_expires_at=None,
        )

    def claim_next(self) -> ReportJob | None:
        """Reserva o próximo job pendente ou órfão (mesma regra do SQLite)."""
        with self._lock:
            now = self._clock()

            def expired(job: ReportJob) -> bool:
                return job.status == JobStatus.RUNNING and (
                    job.lease_expires_at is None or job.lease_expires_at <= now
                )

            for job in self._jobs.values():
                if expired(job) and job.attempts >= self.max_attempts:
                    job.status = JobStatus.FAILED
                    job.error = _lease_exhausted_error(job.attempts, self.max_attempts)
                    job.lease_owner = None
                    job.lease_expires_at = None
                    job.updated_at = now

            candidates = [
                job for job in self._jobs.values()
                if job.status == JobStatus.QUEUED or expired(job)
            ]
            if not candidates:
                return None
            job = sorted(candidates, key=lambda item: item.created_at)[0]
            job.status = JobStatus.RUNNING
            job.attempts += 1
            job.lease_owner = str(uuid4())
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.updated_at = now
            return job

    def heartbeat(self, job_id: str, lease_owner: str) -> bool:
        """Renova o lease do job se ele ainda pertence a ``lease_owner``."""
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                job is None
                or job.status != JobStatus.RUNNING
                or job.lease_owner != lease_owner
            ):
                return False
            now = self._clock()
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.updated_at = now
            return True

    def list_recent(
        self,
        limit: int = 20,
        status: JobStatus | None = None,
    ) -> list[ReportJob]:
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

    def status_counts(self) -> dict[JobStatus, int]:
        """Conta jobs por status."""
        with self._lock:
            counts = dict.fromkeys(JobStatus, 0)
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
    """Store persistente de jobs em SQLite.

    Jobs em execução carregam um *lease* (``lease_owner`` +
    ``lease_expires_at``) que o worker renova com :meth:`heartbeat`. Se o
    worker cai, o heartbeat para, o lease expira e o próximo
    :meth:`claim_next` reivindica o job de novo (mesmo ``execution_id``,
    retomando do blackboard). Cada reivindicação conta uma tentativa; ao
    atingir ``max_attempts`` com o lease expirado, o job vira ``failed``.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        clock: Callable[[], datetime] = datetime.now,
    ):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds deve ser positivo")
        if max_attempts < 1:
            raise ValueError("max_attempts deve ser >= 1")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self._clock = clock
        self._lock = Lock()
        self._initialize()

    def create(self, payload: dict | None = None) -> ReportJob:
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

    def get(self, job_id: str) -> ReportJob | None:
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
        pii_types: list[str],
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
            lease_owner=None,
            lease_expires_at=None,
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        """Marca o job como falho."""
        self._update(
            job_id,
            status=JobStatus.FAILED.value,
            error=error,
            lease_owner=None,
            lease_expires_at=None,
        )

    def claim_next(self) -> ReportJob | None:
        """Reserva o próximo job pendente ou órfão para execução.

        O claim é atômico entre processos, não só entre threads: o ``Lock``
        protege apenas o processo atual. Por isso a reserva roda numa
        transação ``BEGIN IMMEDIATE`` (a trava de escrita do SQLite é obtida
        antes do SELECT, então dois workers não escolhem o mesmo job) e o
        UPDATE repete a condição de elegibilidade: ``rowcount`` diferente de
        1 significa que o job não foi reservado por esta chamada, e nada é
        devolvido (o worker tenta de novo no próximo poll).

        São elegíveis jobs ``queued`` e jobs ``running`` cujo lease expirou
        (ou que não têm lease: órfãos de versões anteriores à migração).
        Antes da escolha, órfãos que já esgotaram ``max_attempts`` são
        marcados ``failed`` com erro explícito, na mesma transação.
        """
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = self._clock()
            now_iso = self._ts(now)
            expired = (
                "status = ? AND (lease_expires_at IS NULL OR lease_expires_at <= ?)"
            )
            expired_params = (JobStatus.RUNNING.value, now_iso)

            exhausted = conn.execute(
                f"SELECT job_id, attempts FROM report_jobs "
                f"WHERE {expired} AND attempts >= ?",
                (*expired_params, self.max_attempts),
            ).fetchall()
            for job in exhausted:
                conn.execute(
                    f"""
                    UPDATE report_jobs
                    SET status = ?, error = ?, lease_owner = NULL,
                        lease_expires_at = NULL, updated_at = ?
                    WHERE job_id = ? AND {expired}
                    """,
                    (
                        JobStatus.FAILED.value,
                        _lease_exhausted_error(job["attempts"], self.max_attempts),
                        now_iso,
                        job["job_id"],
                        *expired_params,
                    ),
                )

            eligible = f"(status = ? OR ({expired}))"
            eligible_params = (JobStatus.QUEUED.value, *expired_params)
            row = conn.execute(
                f"""
                SELECT job_id FROM report_jobs
                WHERE {eligible}
                ORDER BY created_at
                LIMIT 1
                """,
                eligible_params,
            ).fetchone()
            if row is None:
                return None

            cursor = conn.execute(
                f"""
                UPDATE report_jobs
                SET status = ?, attempts = attempts + 1, lease_owner = ?,
                    lease_expires_at = ?, updated_at = ?
                WHERE job_id = ? AND {eligible}
                """,
                (
                    JobStatus.RUNNING.value,
                    str(uuid4()),
                    self._ts(now + timedelta(seconds=self.lease_seconds)),
                    now_iso,
                    row["job_id"],
                    *eligible_params,
                ),
            )
            if cursor.rowcount != 1:
                return None

            claimed = conn.execute(
                "SELECT * FROM report_jobs WHERE job_id = ?",
                (row["job_id"],),
            ).fetchone()

        return self._row_to_job(claimed)

    def heartbeat(self, job_id: str, lease_owner: str) -> bool:
        """Renova o lease do job se ele ainda pertence a ``lease_owner``.

        Devolve ``False`` quando o job já não está ``running`` sob este dono
        (lease expirado e reivindicado por outro worker, ou job finalizado):
        o worker não deve estender um lease que perdeu.
        """
        now = self._clock()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE report_jobs
                SET lease_expires_at = ?, updated_at = ?
                WHERE job_id = ? AND status = ? AND lease_owner = ?
                """,
                (
                    self._ts(now + timedelta(seconds=self.lease_seconds)),
                    self._ts(now),
                    job_id,
                    JobStatus.RUNNING.value,
                    lease_owner,
                ),
            )
            return cursor.rowcount == 1

    def list_recent(
        self,
        limit: int = 20,
        status: JobStatus | None = None,
    ) -> list[ReportJob]:
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

    def status_counts(self) -> dict[JobStatus, int]:
        """Conta jobs por status."""
        counts = dict.fromkeys(JobStatus, 0)
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
                    payload TEXT NOT NULL DEFAULT '{}',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at TEXT
                )
                """
            )
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(report_jobs)").fetchall()
            }
            # Migração aditiva: bancos criados por versões anteriores ganham
            # as colunas que faltam, sem recriar a tabela.
            migrations = {
                "payload": "payload TEXT NOT NULL DEFAULT '{}'",
                "attempts": "attempts INTEGER NOT NULL DEFAULT 0",
                "lease_owner": "lease_owner TEXT",
                "lease_expires_at": "lease_expires_at TEXT",
            }
            for column, definition in migrations.items():
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE report_jobs ADD COLUMN {definition}")
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

    @staticmethod
    def _ts(value: datetime) -> str:
        # Precisão fixa: as comparações de lease são feitas como texto no SQL.
        return value.isoformat(timespec="microseconds")

    def _update(self, job_id: str, **changes) -> None:
        changes["updated_at"] = self._ts(self._clock())
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
            attempts=row["attempts"],
            lease_owner=row["lease_owner"],
            lease_expires_at=(
                datetime.fromisoformat(row["lease_expires_at"])
                if row["lease_expires_at"]
                else None
            ),
        )
