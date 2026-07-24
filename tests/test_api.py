"""Testes da API HTTP (src/api/app.py)."""

import os
import tempfile
import unittest
from pathlib import Path

import tests.conftest  # noqa: F401  garante src/ no sys.path
from services.job_store import InMemoryJobStore


class TestApi(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from api import app as api_app

        self.api_app = api_app
        self.original_job_store = api_app.job_store
        self.store = InMemoryJobStore()
        api_app.job_store = self.store
        self.client = TestClient(api_app.app)

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
        with tempfile.TemporaryDirectory() as tmpdir:
            response = self.client.post(
                "/reports",
                json={
                    "db_path": str(Path(tmpdir) / "missing.db"),
                    "output_dir": str(Path(tmpdir) / "reports"),
                },
            )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertIn("job_id", body)
        self.assertIn("status_url", body)

        status_response = self.client.get(body["status_url"])
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "queued")

    def test_list_report_jobs_endpoint(self):
        self.store.create()

        response = self.client.get("/reports?limit=5")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertGreaterEqual(len(response.json()), 1)

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
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.md"
            report_path.write_text("# Relatório\n", encoding="utf-8")
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

            response = self.client.get(f"/reports/{job.job_id}/artifact")

        self.assertEqual(response.status_code, 200)
        self.assertIn("# Relatório", response.text)

    def test_download_report_artifact_rejects_unfinished_job(self):
        job = self.store.create()

        response = self.client.get(f"/reports/{job.job_id}/artifact")

        self.assertEqual(response.status_code, 409)

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
