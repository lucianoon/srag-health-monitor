"""Testes do worker de jobs de relatório (src/services/report_worker.py)."""

import os
import unittest
from pathlib import Path
from unittest import mock

from agents.data_ingestion_agent import SUSDataIngestionAgent
from agents.report_writer_agent import ReportWriterAgent
from services.job_store import JobStatus, SQLiteJobStore
from services.report_worker import ReportWorker
from tests.conftest import (  # também garante src/ no sys.path
    TempSRAGDatabaseMixin,
    offline_news_guard,
)

# Mantém o módulo offline: o worker executa o pipeline completo, incluindo
# a coleta de notícias.
setUpModule, tearDownModule = offline_news_guard()


class TestReportWorker(TempSRAGDatabaseMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # Caminhos do payload são relativos às bases do servidor: o banco
        # de teste (srag.db) fica em SRAG_DATA_DIR.
        env = mock.patch.dict(
            os.environ,
            {
                "SRAG_DATA_DIR": self.tmpdir.name,
                "SRAG_OUTPUT_DIR": str(Path(self.tmpdir.name) / "reports"),
            },
            clear=False,
        )
        env.start()
        self.addCleanup(env.stop)

    def test_worker_runs_queued_job_successfully(self):
        output_dir = Path(self.tmpdir.name) / "reports" / "equipe-a"
        store = SQLiteJobStore(Path(self.tmpdir.name) / "jobs.db")
        job = store.create(payload={"db_path": "srag.db", "output_dir": "equipe-a"})
        worker = ReportWorker(store, poll_interval_seconds=0.01)

        result = worker.run_once()

        self.assertEqual(result.job_id, job.job_id)
        self.assertEqual(result.status, JobStatus.SUCCEEDED)
        self.assertTrue(Path(result.report_path).exists())
        self.assertEqual(Path(result.report_path).parent, output_dir.resolve())

    def test_worker_rejects_legacy_payload_with_unsafe_paths(self):
        # Jobs enfileirados antes da validação (ou via retry) podem carregar
        # caminhos absolutos: o worker falha o job sem usá-los.
        outside = Path(self.tmpdir.name).parent / "fora_da_base"
        store = SQLiteJobStore(Path(self.tmpdir.name) / "jobs.db")
        for payload in (
            {"db_path": self.db_path},
            {"output_dir": str(outside)},
            {"output_dir": "../../fora_da_base"},
        ):
            with self.subTest(payload=payload):
                job = store.create(payload=payload)
                result = ReportWorker(store, poll_interval_seconds=0.01).run_once()

                self.assertEqual(result.job_id, job.job_id)
                self.assertEqual(result.status, JobStatus.FAILED)
                self.assertRegex(result.error, r"absolutos|'\.\.'|fora do diret")
                self.assertIsNone(result.report_path)
        self.assertFalse(outside.exists())

    def test_worker_marks_job_failed_when_database_is_missing(self):
        store = SQLiteJobStore(Path(self.tmpdir.name) / "jobs.db")
        job = store.create(payload={"db_path": "missing.db"})
        worker = ReportWorker(store, poll_interval_seconds=0.01)

        result = worker.run_once()

        self.assertEqual(result.job_id, job.job_id)
        self.assertEqual(result.status, JobStatus.FAILED)
        self.assertIn("Banco de dados não encontrado", result.error)

    def test_failed_job_records_execution_id(self):
        store = SQLiteJobStore(Path(self.tmpdir.name) / "jobs.db")
        store.create(payload={"db_path": "missing.db"})
        worker = ReportWorker(store, poll_interval_seconds=0.01)

        result = worker.run_once()

        self.assertEqual(result.status, JobStatus.FAILED)
        self.assertIsNotNone(result.execution_id)

    def test_retry_job_resumes_from_persisted_state(self):
        store = SQLiteJobStore(Path(self.tmpdir.name) / "jobs.db")
        payload = {"db_path": "srag.db"}
        worker = ReportWorker(store, poll_interval_seconds=0.01)

        store.create(payload=payload)
        with mock.patch.object(
            ReportWriterAgent,
            "write",
            side_effect=RuntimeError("falha simulada na escrita"),
        ):
            failed = worker.run_once()

        self.assertEqual(failed.status, JobStatus.FAILED)
        self.assertIsNotNone(failed.execution_id)
        state_path = (
            Path(self.tmpdir.name) / "pipeline_state" / f"{failed.execution_id}.json"
        )
        self.assertTrue(state_path.exists())

        # Mesmo fluxo do endpoint de retry: payload original + execution_id.
        store.create(payload={**failed.payload, "execution_id": failed.execution_id})
        with mock.patch.object(
            SUSDataIngestionAgent,
            "collect_data",
            side_effect=AssertionError("retomada não deveria recoletar dados"),
        ):
            retried = worker.run_once()

        self.assertEqual(retried.status, JobStatus.SUCCEEDED)
        self.assertEqual(retried.execution_id, failed.execution_id)
        self.assertTrue(Path(retried.report_path).exists())
        self.assertFalse(state_path.exists())


if __name__ == "__main__":
    unittest.main()
