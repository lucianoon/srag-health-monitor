"""Testes dos stores de jobs (src/services/job_store.py)."""

import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import tests.conftest  # noqa: F401  garante src/ no sys.path
from services.job_store import InMemoryJobStore, JobStatus, SQLiteJobStore


def _drain_queue(db_path: str, start: threading.Barrier | None = None) -> list[str]:
    """Reserva jobs até a fila esvaziar, como faria um processo worker.

    Cada chamada abre seu próprio ``SQLiteJobStore`` (e, portanto, seu
    próprio ``Lock``): a única coordenação possível é a do SQLite.
    """
    store = SQLiteJobStore(db_path)
    if start is not None:
        start.wait()
    claimed: list[str] = []
    empty_polls = 0
    while empty_polls < 3:
        job = store.claim_next()
        if job is None:
            empty_polls += 1
            continue
        empty_polls = 0
        claimed.append(job.job_id)
    return claimed


class TestJobStore(unittest.TestCase):
    def test_job_lifecycle_success(self):
        store = InMemoryJobStore()
        job = store.create(payload={"db_path": "/tmp/srag.db"})

        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.payload, {"db_path": "/tmp/srag.db"})

        claimed = store.claim_next()
        self.assertEqual(claimed.job_id, job.job_id)
        self.assertEqual(store.get(job.job_id).status, JobStatus.RUNNING)

        store.mark_succeeded(
            job.job_id,
            execution_id="exec-1",
            report_path="/tmp/report.md",
            duration_ms=12.5,
            pii_detected=False,
            pii_types=[],
            summary={"success": True},
        )

        completed = store.get(job.job_id)
        self.assertEqual(completed.status, JobStatus.SUCCEEDED)
        self.assertEqual(completed.execution_id, "exec-1")
        self.assertEqual(completed.report_path, "/tmp/report.md")

    def test_job_lifecycle_failure(self):
        store = InMemoryJobStore()
        job = store.create()

        store.mark_failed(job.job_id, "boom")

        failed = store.get(job.job_id)
        self.assertEqual(failed.status, JobStatus.FAILED)
        self.assertEqual(failed.error, "boom")

    def test_sqlite_store_persists_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            store = SQLiteJobStore(db_path)
            job = store.create(payload={"db_path": "/tmp/srag.db"})
            store.mark_succeeded(
                job.job_id,
                execution_id="exec-2",
                report_path="/tmp/report.md",
                duration_ms=20.0,
                pii_detected=True,
                pii_types=["CPF"],
                summary={"success": True},
            )

            reloaded_store = SQLiteJobStore(db_path)
            persisted = reloaded_store.get(job.job_id)

        self.assertEqual(persisted.status, JobStatus.SUCCEEDED)
        self.assertEqual(persisted.execution_id, "exec-2")
        self.assertEqual(persisted.pii_types, ["CPF"])
        self.assertEqual(persisted.summary, {"success": True})
        self.assertEqual(persisted.payload, {"db_path": "/tmp/srag.db"})

    def test_sqlite_store_claim_next_marks_running(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteJobStore(Path(tmpdir) / "jobs.db")
            job = store.create()

            claimed = store.claim_next()

            self.assertEqual(claimed.job_id, job.job_id)
            self.assertEqual(claimed.status, JobStatus.RUNNING)
            self.assertIsNone(store.claim_next())

    def test_sqlite_claim_is_exclusive_across_store_instances(self):
        # Regressão: o claim conferia só o Lock do processo; stores
        # independentes (workers distintos) podiam reservar o mesmo job.
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "jobs.db")
            seed = SQLiteJobStore(db_path)
            job_ids = {seed.create().job_id for _ in range(40)}

            workers = 4
            start = threading.Barrier(workers)
            results: list[list[str]] = [[] for _ in range(workers)]

            def run(index: int) -> None:
                results[index] = _drain_queue(db_path, start)

            threads = [
                threading.Thread(target=run, args=(index,)) for index in range(workers)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)

            claimed = [job_id for result in results for job_id in result]
            counts = seed.status_counts()

        self.assertEqual(len(claimed), len(set(claimed)), "job reservado mais de uma vez")
        self.assertEqual(set(claimed), job_ids)
        self.assertEqual(counts[JobStatus.RUNNING], len(job_ids))
        self.assertEqual(counts[JobStatus.QUEUED], 0)

    def test_sqlite_claim_is_exclusive_across_processes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "jobs.db")
            seed = SQLiteJobStore(db_path)
            job_ids = {seed.create().job_id for _ in range(30)}

            with ProcessPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_drain_queue, db_path) for _ in range(2)]
                claimed = [job_id for future in futures for job_id in future.result()]

        self.assertEqual(len(claimed), len(set(claimed)), "job reservado mais de uma vez")
        self.assertEqual(set(claimed), job_ids)

    def test_sqlite_claim_skips_job_taken_by_another_connection(self):
        # Outro worker reservou o job entre a criação e o nosso claim: a
        # linha já não está queued e o claim não pode devolvê-la.
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            ours = SQLiteJobStore(db_path)
            theirs = SQLiteJobStore(db_path)
            job = ours.create()

            self.assertEqual(theirs.claim_next().job_id, job.job_id)
            self.assertIsNone(ours.claim_next())

    def test_list_recent_filters_by_status(self):
        store = InMemoryJobStore()
        queued = store.create()
        failed = store.create()
        store.mark_failed(failed.job_id, "boom")

        queued_jobs = store.list_recent(status=JobStatus.QUEUED)
        failed_jobs = store.list_recent(status=JobStatus.FAILED)

        self.assertEqual([job.job_id for job in queued_jobs], [queued.job_id])
        self.assertEqual([job.job_id for job in failed_jobs], [failed.job_id])

    def test_claim_next_returns_none_when_queue_is_empty(self):
        self.assertIsNone(InMemoryJobStore().claim_next())

    def test_sqlite_store_releases_file_handles(self):
        # Regressão: conexões SQLite não fechadas mantinham jobs.db travado
        # (PermissionError ao remover o arquivo no Windows).
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            store = SQLiteJobStore(db_path)
            job = store.create()
            store.claim_next()
            store.mark_failed(job.job_id, "boom")
            store.list_recent()
            store.status_counts()

            db_path.unlink()  # falharia com conexões ainda abertas

            self.assertFalse(db_path.exists())

    def test_sqlite_store_status_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteJobStore(Path(tmpdir) / "jobs.db")
            store.create()
            failed = store.create()
            store.mark_failed(failed.job_id, "boom")

            counts = store.status_counts()

        self.assertEqual(counts[JobStatus.QUEUED], 1)
        self.assertEqual(counts[JobStatus.FAILED], 1)
        self.assertEqual(counts[JobStatus.RUNNING], 0)


class FakeClock:
    """Relógio controlável: o lease é testado sem ``sleep``."""

    def __init__(self, start: datetime | None = None):
        self.now = start or datetime(2026, 1, 1, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class TestJobLease(unittest.TestCase):
    """Lease com heartbeat e recuperação de jobs órfãos (worker caiu)."""

    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.db_path = Path(tmpdir.name) / "jobs.db"
        self.clock = FakeClock()

    def _store(self, **kwargs) -> SQLiteJobStore:
        kwargs.setdefault("lease_seconds", 60)
        kwargs.setdefault("max_attempts", 3)
        return SQLiteJobStore(self.db_path, clock=self.clock, **kwargs)

    def test_claim_sets_lease_and_counts_attempt(self):
        store = self._store()
        job = store.create()

        claimed = store.claim_next()

        self.assertEqual(claimed.job_id, job.job_id)
        self.assertEqual(claimed.attempts, 1)
        self.assertIsNotNone(claimed.lease_owner)
        self.assertEqual(claimed.lease_expires_at, self.clock.now + timedelta(seconds=60))

    def test_expired_lease_is_reclaimed_with_same_execution_id(self):
        crashed_worker = self._store()
        job = crashed_worker.create(payload={"db_path": "srag.db"})
        first = crashed_worker.claim_next()
        crashed_worker.set_execution_id(job.job_id, "exec-orfao")
        # O worker cai: nenhum heartbeat, o lease vence.
        self.clock.advance(61)

        recovered = self._store().claim_next()

        self.assertEqual(recovered.job_id, job.job_id)
        self.assertEqual(recovered.status, JobStatus.RUNNING)
        self.assertEqual(recovered.attempts, 2)
        self.assertEqual(recovered.execution_id, "exec-orfao")
        self.assertEqual(recovered.payload, {"db_path": "srag.db"})
        self.assertNotEqual(recovered.lease_owner, first.lease_owner)
        # O dono antigo perdeu o lease: não consegue mais renová-lo.
        self.assertFalse(crashed_worker.heartbeat(job.job_id, first.lease_owner))

    def test_valid_lease_is_not_stolen(self):
        owner = self._store()
        owner.create()
        owner.claim_next()
        self.clock.advance(59)

        self.assertIsNone(self._store().claim_next())
        self.assertEqual(owner.status_counts()[JobStatus.RUNNING], 1)

    def test_queued_job_is_claimed_while_other_lease_is_valid(self):
        store = self._store()
        running = store.create()
        store.claim_next()
        self.clock.advance(1)
        queued = store.create()

        claimed = self._store().claim_next()

        self.assertEqual(claimed.job_id, queued.job_id)
        self.assertEqual(store.get(running.job_id).attempts, 1)

    def test_heartbeat_renews_lease(self):
        store = self._store()
        store.create()
        claimed = store.claim_next()

        self.clock.advance(50)
        self.assertTrue(store.heartbeat(claimed.job_id, claimed.lease_owner))
        renewed = store.get(claimed.job_id)
        self.assertEqual(renewed.lease_expires_at, self.clock.now + timedelta(seconds=60))

        # Sem o heartbeat o lease teria vencido em t0+60; renovado, vale
        # até t0+110.
        self.clock.advance(20)
        self.assertIsNone(self._store().claim_next())
        self.clock.advance(41)
        self.assertEqual(self._store().claim_next().job_id, claimed.job_id)

    def test_heartbeat_rejects_foreign_owner_and_finished_jobs(self):
        store = self._store()
        job = store.create()
        claimed = store.claim_next()

        self.assertFalse(store.heartbeat(job.job_id, "outro-worker"))
        store.mark_failed(job.job_id, "boom")
        self.assertFalse(store.heartbeat(job.job_id, claimed.lease_owner))
        self.assertIsNone(store.get(job.job_id).lease_owner)

    def test_attempt_limit_marks_job_failed(self):
        store = self._store(max_attempts=2)
        job = store.create()
        for _ in range(2):
            self.assertEqual(store.claim_next().job_id, job.job_id)
            self.clock.advance(61)

        self.assertIsNone(store.claim_next())

        failed = store.get(job.job_id)
        self.assertEqual(failed.status, JobStatus.FAILED)
        self.assertEqual(failed.attempts, 2)
        self.assertIn("Lease expirado", failed.error)
        self.assertIn("limite de 2", failed.error)
        self.assertIsNone(failed.lease_owner)

    def test_attempt_limit_does_not_block_other_jobs(self):
        store = self._store(max_attempts=1)
        orphan = store.create()
        store.claim_next()
        self.clock.advance(61)
        queued = store.create()

        self.assertEqual(store.claim_next().job_id, queued.job_id)
        self.assertEqual(store.get(orphan.job_id).status, JobStatus.FAILED)

    def test_legacy_database_is_migrated_and_orphans_recovered(self):
        # Banco criado antes do lease: sem as colunas novas e com um job
        # preso em running por um worker que caiu.
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE report_jobs (
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
                        error TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO report_jobs (job_id, status, created_at, updated_at,"
                    " execution_id) VALUES ('legado', 'running', ?, ?, 'exec-legado')",
                    ("2025-12-31T10:00:00", "2025-12-31T10:00:00"),
                )
        finally:
            conn.close()

        store = self._store()

        conn = sqlite3.connect(self.db_path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(report_jobs)")}
        finally:
            conn.close()
        self.assertTrue(
            {"payload", "attempts", "lease_owner", "lease_expires_at"} <= columns
        )

        recovered = store.claim_next()
        self.assertEqual(recovered.job_id, "legado")
        self.assertEqual(recovered.execution_id, "exec-legado")
        self.assertEqual(recovered.attempts, 1)
        self.assertEqual(recovered.payload, {})

    def test_in_memory_store_follows_same_lease_rules(self):
        store = InMemoryJobStore(lease_seconds=60, max_attempts=2, clock=self.clock)
        job = store.create()
        first = store.claim_next()

        self.clock.advance(59)
        self.assertIsNone(store.claim_next())
        self.assertTrue(store.heartbeat(job.job_id, first.lease_owner))

        self.clock.advance(61)
        second = store.claim_next()
        self.assertEqual(second.attempts, 2)
        self.assertFalse(store.heartbeat(job.job_id, "dono-antigo"))

        self.clock.advance(61)
        self.assertIsNone(store.claim_next())
        self.assertEqual(store.get(job.job_id).status, JobStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
