"""Testes do caso de uso de geração de relatório (src/services/report_service.py)."""

import unittest
from pathlib import Path

from tests.conftest import (  # também garante src/ no sys.path
    TempSRAGDatabaseMixin,
    make_app_config,
    offline_news_guard,
)
from guardrails.audit_logger import AuditLogger, ExecutionTracker
from services.report_service import GenerateReportService

# Mantém o módulo offline: o serviço executa o pipeline completo, incluindo
# a coleta de notícias.
setUpModule, tearDownModule = offline_news_guard()


class TestGenerateReportService(TempSRAGDatabaseMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.config = make_app_config(self.tmpdir.name, db_path=self.db_path)
        self.log_dir = self.config.logs_dir

    def _make_audit_logger(self):
        audit_logger = AuditLogger(self.log_dir)
        self.addCleanup(audit_logger.close)
        return audit_logger

    def test_generate_report_success(self):
        service = GenerateReportService(
            config=self.config,
            audit_logger=self._make_audit_logger(),
            execution_tracker=ExecutionTracker(),
        )

        result = service.run()

        self.assertIn("Relatório de Monitoramento de SRAG", result.report)
        self.assertIn("Nível de Risco", result.report)
        self.assertIn("Fonte e Rastreabilidade", result.report)
        self.assertTrue(result.report_path.exists())
        self.assertEqual(result.summary["total_errors"], 0)

    def test_generate_report_missing_database_fails(self):
        missing_config = make_app_config(
            self.tmpdir.name,
            db_path=Path(self.tmpdir.name) / "missing.db",
        )
        service = GenerateReportService(
            config=missing_config,
            audit_logger=self._make_audit_logger(),
            execution_tracker=ExecutionTracker(),
        )

        with self.assertRaises(RuntimeError):
            service.run()


if __name__ == "__main__":
    unittest.main()
