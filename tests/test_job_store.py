"""Testes dos stores de jobs (src/services/job_store.py)."""

import tempfile
import unittest
from pathlib import Path

import tests.conftest  # noqa: F401  garante src/ no sys.path
from services.job_store import InMemoryJobStore, JobStatus, SQLiteJobStore


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

    def test_list_recent_filters_by_status(self):
        store = InMemoryJobStore()
        queued = store.create()
        failed = store.create()
        store.mark_failed(failed.job_id, "boom")

        queued_jobs = store.list_recent(status=JobStatus.QUEUED)
        failed_jobs = store.list_recent(status=JobStatus.FAILED)

        self.assertEqual([job.job_id for job in queued_jobs], [queued.job_id])
        self.assertEqual([job.job_id for job in failed_jobs], [failed.job_id])

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


if __name__ == "__main__":
    unittest.main()
