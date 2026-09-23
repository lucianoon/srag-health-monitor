"""Testes da API HTTP (src/api/app.py)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.job_store import InMemoryJobStore, JobStatus
from tests.conftest import offline_news_guard  # também garante src/ no sys.path
from tests.test_config import UNSAFE_PATHS

# Mantém o módulo offline: POST /reports/sync executa o pipeline completo,
# incluindo a coleta de notícias.
setUpModule, tearDownModule = offline_news_guard()


class TestApi(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from api import app as api_app

        self.api_app = api_app
        self.original_job_store = api_app.job_store
        self.store = InMemoryJobStore()
        api_app.job_store = self.store
        self.client = TestClient(api_app.app)

        # Artefatos só são servidos de dentro de SRAG_OUTPUT_DIR.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_root = Path(tmp.name)
        self.reports_dir = self.tmp_root / "reports"
        self.reports_dir.mkdir()
        env = mock.patch.dict(
            os.environ, {"SRAG_OUTPUT_DIR": str(self.reports_dir)}, clear=False
        )
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.api_app.job_store = self.original_job_store
        os.environ.pop("SRAG_API_KEY", None)

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready_endpoint(self):
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["status"], {"ready", "not_ready"})
        self.assertIn("jobs_db_accessible", body)
        self.assertIn("srag_db_exists", body)

    def test_create_report_job_returns_status_url(self):
        response = self.client.post(
            "/reports",
            json={"db_path": "missing.db", "output_dir": "equipe-a"},
        )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertIn("job_id", body)
        self.assertIn("status_url", body)

        status_response = self.client.get(body["status_url"])
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "queued")

    def test_create_report_job_rejects_path_traversal(self):
        for field in ("db_path", "output_dir"):
            for value in UNSAFE_PATHS:
                with self.subTest(field=field, value=value):
                    response = self.client.post("/reports", json={field: value})
                    self.assertEqual(response.status_code, 422)

        self.assertEqual(self.store.list_recent(), [])

    def test_create_report_job_rejects_symlink_escaping_data_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            outside = Path(tmpdir) / "fora"
            outside.mkdir()
            try:
                (data_dir / "atalho").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink indisponível neste ambiente: {exc}")

            with mock.patch.dict(os.environ, {"SRAG_DATA_DIR": str(data_dir)}, clear=False):
                response = self.client.post("/reports", json={"db_path": "atalho/srag.db"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.store.list_recent(), [])

    def test_sync_report_rejects_path_traversal_without_touching_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir) / "base" / "reports"
            env = {
                "SRAG_DATA_DIR": str(Path(tmpdir) / "base" / "data"),
                "SRAG_OUTPUT_DIR": str(reports_dir),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                response = self.client.post(
                    "/reports/sync",
                    json={"output_dir": "../../escapou"},
                )

            self.assertFalse((Path(tmpdir) / "escapou").exists())

        self.assertEqual(response.status_code, 422)

    def test_list_report_jobs_endpoint(self):
        self.store.create()

        response = self.client.get("/reports?limit=5")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertGreaterEqual(len(response.json()), 1)

    def test_list_report_jobs_filters_by_status(self):
        self.store.create()
        failed = self.store.create()
        self.store.mark_failed(failed.job_id, "boom")

        response = self.client.get("/reports?status=failed")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["job_id"], failed.job_id)
        self.assertEqual(body[0]["status"], JobStatus.FAILED.value)

    def test_get_unknown_report_job_returns_404(self):
        response = self.client.get("/reports/nao-existe")

        self.assertEqual(response.status_code, 404)

    def test_metrics_endpoint_counts_jobs(self):
        self.store.create()
        failed = self.store.create()
        self.store.mark_failed(failed.job_id, "boom")

        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_jobs"], 2)
        self.assertEqual(body["jobs_by_status"]["queued"], 1)
        self.assertEqual(body["jobs_by_status"]["failed"], 1)
        self.assertEqual(body["recent_failures"][0]["job_id"], failed.job_id)

    def test_download_report_artifact(self):
        report_path = self.reports_dir / "equipe-a" / "report.md"
        report_path.parent.mkdir()
        report_path.write_text("# Relatório\n", encoding="utf-8")
        job_id = self._mark_succeeded_with_artifact(report_path)

        response = self.client.get(f"/reports/{job_id}/artifact")

        self.assertEqual(response.status_code, 200)
        self.assertIn("# Relatório", response.text)

    def test_download_report_artifact_rejects_paths_outside_reports_dir(self):
        # Jobs antigos no store podem ter report_path em qualquer lugar.
        outside = self.tmp_root / "fora.md"
        outside.write_text("# Segredo\n", encoding="utf-8")
        for stored in (
            outside,                                    # absoluto fora da base
            self.reports_dir / ".." / "fora.md",        # ".." a partir da base
            "../fora.md",                               # relativo com ".."
        ):
            with self.subTest(stored=str(stored)):
                job_id = self._mark_succeeded_with_artifact(stored)

                response = self.client.get(f"/reports/{job_id}/artifact")

                self.assertEqual(response.status_code, 403)
                self.assertNotIn("Segredo", response.text)

    def test_download_report_artifact_rejects_symlink_escaping_reports_dir(self):
        outside = self.tmp_root / "fora.md"
        outside.write_text("# Segredo\n", encoding="utf-8")
        link = self.reports_dir / "atalho.md"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink indisponível neste ambiente: {exc}")
        job_id = self._mark_succeeded_with_artifact(link)

        response = self.client.get(f"/reports/{job_id}/artifact")

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Segredo", response.text)

    def test_download_report_artifact_rejects_unfinished_job(self):
        job = self.store.create()

        response = self.client.get(f"/reports/{job.job_id}/artifact")

        self.assertEqual(response.status_code, 409)

    def _mark_succeeded_with_artifact(self, report_path: Path | str) -> str:
        job = self.store.create()
        self.store.mark_succeeded(
            job.job_id,
            execution_id="exec-1",
            report_path=str(report_path),
            duration_ms=10.0,
            pii_detected=False,
            pii_types=[],
            summary={"success": True},
        )
        return job.job_id

    def test_download_report_artifact_rejects_non_markdown(self):
        artifact = self.reports_dir / "report.txt"
        artifact.write_text("conteudo", encoding="utf-8")
        job_id = self._mark_succeeded_with_artifact(artifact)

        response = self.client.get(f"/reports/{job_id}/artifact")

        self.assertEqual(response.status_code, 403)

    def test_download_report_artifact_missing_file_returns_404(self):
        job_id = self._mark_succeeded_with_artifact(self.reports_dir / "inexistente.md")

        response = self.client.get(f"/reports/{job_id}/artifact")

        self.assertEqual(response.status_code, 404)

    def test_sync_report_returns_500_when_database_is_missing(self):
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            mock.patch.dict(
                os.environ,
                {
                    "SRAG_DATA_DIR": tmpdir,
                    "SRAG_OUTPUT_DIR": str(Path(tmpdir) / "reports"),
                },
                clear=False,
            ),
        ):
            response = self.client.post(
                "/reports/sync",
                json={"db_path": "missing.db"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn("Banco de dados não encontrado", response.json()["detail"])

    def test_retry_failed_job_creates_job_with_same_execution_id(self):
        job = self.store.create(payload={"db_path": "srag.db"})
        self.store.set_execution_id(job.job_id, "exec-42")
        self.store.mark_failed(job.job_id, "boom")

        response = self.client.post(f"/reports/{job.job_id}/retry")

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertNotEqual(body["job_id"], job.job_id)
        self.assertEqual(body["status"], "queued")

        retry_job = self.store.get(body["job_id"])
        self.assertEqual(retry_job.payload["execution_id"], "exec-42")
        self.assertEqual(retry_job.payload["db_path"], "srag.db")

    def test_retry_rejects_job_that_did_not_fail(self):
        job = self.store.create()

        response = self.client.post(f"/reports/{job.job_id}/retry")

        self.assertEqual(response.status_code, 409)

    def test_retry_unknown_job_returns_404(self):
        response = self.client.post("/reports/nao-existe/retry")

        self.assertEqual(response.status_code, 404)

    def test_api_key_is_required_when_configured(self):
        os.environ["SRAG_API_KEY"] = "secret-token"
        self.store.create()

        public_response = self.client.get("/health")
        unauthorized_response = self.client.get("/reports")
        authorized_response = self.client.get(
            "/reports",
            headers={"X-API-Key": "secret-token"},
        )

        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(unauthorized_response.status_code, 401)
        self.assertEqual(authorized_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
