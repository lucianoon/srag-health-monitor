"""Testes dos guardrails (src/guardrails): validadores e auditoria."""

import json
import tempfile
import unittest
from pathlib import Path

import tests.conftest  # noqa: F401  garante src/ no sys.path
from guardrails.audit_logger import AuditLogger, ExecutionTracker
from guardrails.validators import (
    DataPrivacyGuard,
    InputValidator,
    OutputValidator,
    RateLimiter,
)


class TestInputValidator(unittest.TestCase):
    def test_validate_query_type_valid(self):
        valid, _ = InputValidator.validate_query_type("metrics")
        self.assertTrue(valid)

    def test_validate_query_type_invalid(self):
        valid, _ = InputValidator.validate_query_type("invalid")
        self.assertFalse(valid)

    def test_validate_days_parameter_valid(self):
        valid, _ = InputValidator.validate_days_parameter(30)
        self.assertTrue(valid)

    def test_validate_days_parameter_invalid(self):
        valid, _ = InputValidator.validate_days_parameter(500)
        self.assertFalse(valid)

    def test_validate_months_parameter_valid(self):
        valid, _ = InputValidator.validate_months_parameter(12)
        self.assertTrue(valid)

    def test_validate_months_parameter_invalid(self):
        valid, _ = InputValidator.validate_months_parameter(48)
        self.assertFalse(valid)

    def test_sanitize_search_query(self):
        query = "SRAG <script>alert('xss')</script>"
        sanitized = InputValidator.sanitize_search_query(query)
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)

    def test_sanitize_search_query_limits_length(self):
        sanitized = InputValidator.sanitize_search_query("a" * 500)
        self.assertEqual(len(sanitized), 200)


class TestOutputValidator(unittest.TestCase):
    def test_validate_metrics_valid(self):
        metrics = {
            "taxa_aumento_casos": 5.0,
            "taxa_mortalidade": 7.5,
            "taxa_ocupacao_uti": 25.0,
            "taxa_vacinacao": 50.0,
        }
        valid, _ = OutputValidator.validate_metrics(metrics)
        self.assertTrue(valid)

    def test_validate_metrics_invalid_range(self):
        metrics = {
            "taxa_aumento_casos": 5.0,
            "taxa_mortalidade": 150.0,
            "taxa_ocupacao_uti": 25.0,
            "taxa_vacinacao": 50.0,
        }
        valid, _ = OutputValidator.validate_metrics(metrics)
        self.assertFalse(valid)

    def test_validate_metrics_missing_required_key(self):
        metrics = {
            "taxa_aumento_casos": 5.0,
            "taxa_mortalidade": 7.5,
            "taxa_ocupacao_uti": 25.0,
        }
        valid, message = OutputValidator.validate_metrics(metrics)
        self.assertFalse(valid)
        self.assertIn("taxa_vacinacao", message)

    def test_validate_report_content(self):
        report = """
        # Relatório de SRAG
        ## Métricas Principais
        Taxa de Mortalidade: 7.5%
        Taxa de Ocupação de UTI: 25%
        Taxa de Vacinação: 50%
        """
        valid, _ = OutputValidator.validate_report_content(report)
        self.assertTrue(valid)

    def test_validate_report_content_rejects_short_report(self):
        valid, message = OutputValidator.validate_report_content("curto demais")
        self.assertFalse(valid)
        self.assertIn("curto", message)

    def test_validate_report_content_rejects_missing_section(self):
        report = (
            "# Relatório de SRAG\n"
            "## Métricas Principais\n"
            "Taxa de Mortalidade: 7.5%\n"
            "Taxa de Ocupação de UTI: 25%\n"
        ) + "x" * 100
        valid, message = OutputValidator.validate_report_content(report)
        self.assertFalse(valid)
        self.assertIn("Taxa de Vacinação", message)


class TestDataPrivacyGuard(unittest.TestCase):
    def test_check_for_pii_with_cpf(self):
        text = "Paciente com CPF 123.456.789-00"
        has_pii, types = DataPrivacyGuard.check_for_pii(text)
        self.assertTrue(has_pii)
        self.assertIn("CPF", types)

    def test_check_for_pii_without_pii(self):
        text = "Taxa de mortalidade é de 7.5%"
        has_pii, types = DataPrivacyGuard.check_for_pii(text)
        self.assertFalse(has_pii)
        self.assertEqual(len(types), 0)

    def test_anonymize_text(self):
        text = "CPF 123.456.789-00 e telefone (11) 98765-4321"
        anonymized = DataPrivacyGuard.anonymize_text(text)
        self.assertNotIn("123.456.789-00", anonymized)
        self.assertNotIn("98765-4321", anonymized)
        self.assertIn("***.***.***-**", anonymized)

    def test_check_and_anonymize_email(self):
        text = "Contato: paciente@example.com"
        has_pii, types = DataPrivacyGuard.check_for_pii(text)
        self.assertTrue(has_pii)
        self.assertIn("Email", types)

        anonymized = DataPrivacyGuard.anonymize_text(text)
        self.assertNotIn("paciente@example.com", anonymized)


class TestRateLimiter(unittest.TestCase):
    def test_rate_limiter_allows_calls(self):
        limiter = RateLimiter(max_calls_per_minute=10)
        for _ in range(5):
            allowed, _ = limiter.check_rate_limit()
            self.assertTrue(allowed)

    def test_rate_limiter_blocks_calls_over_limit(self):
        limiter = RateLimiter(max_calls_per_minute=2)
        self.assertTrue(limiter.check_rate_limit()[0])
        self.assertTrue(limiter.check_rate_limit()[0])

        allowed, message = limiter.check_rate_limit()

        self.assertFalse(allowed)
        self.assertIn("excedida", message)


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.log_dir = Path(self.tmpdir.name) / "logs"

    def test_log_event_writes_structured_jsonl(self):
        audit_logger = AuditLogger(self.log_dir)
        self.addCleanup(audit_logger.close)

        audit_logger.log_event("tipo_teste", {"chave": "valor"}, execution_id="exec-1")

        log_files = list(self.log_dir.glob("audit_*.jsonl"))
        self.assertEqual(len(log_files), 1)
        event = json.loads(
            log_files[0].read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertEqual(event["event_type"], "tipo_teste")
        self.assertEqual(event["execution_id"], "exec-1")
        self.assertEqual(event["data"], {"chave": "valor"})
        self.assertIn("event_id", event)
        self.assertIn("timestamp", event)

    def test_close_releases_log_file(self):
        # Regressão: o handler de arquivo ficava aberto no logger global
        # "audit" e travava o arquivo de log no Windows.
        audit_logger = AuditLogger(self.log_dir)
        audit_logger.log_event("tipo_teste", {}, execution_id="exec-2")

        audit_logger.close()

        log_file = next(self.log_dir.glob("audit_*.jsonl"))
        log_file.unlink()  # falharia com o handler ainda aberto
        self.assertFalse(log_file.exists())


class TestExecutionTracker(unittest.TestCase):
    def test_summary_counts_tool_calls_validations_and_errors(self):
        tracker = ExecutionTracker()
        tracker.start_execution("exec-1")
        tracker.add_tool_call("exec-1", "database_query", 10.0)
        tracker.add_validation("exec-1", "metrics", True)
        tracker.add_validation("exec-1", "report_content", False)
        tracker.add_error("exec-1", "RuntimeError")

        summary = tracker.end_execution("exec-1")

        self.assertEqual(summary["execution_id"], "exec-1")
        self.assertEqual(summary["total_tool_calls"], 1)
        self.assertEqual(summary["total_validations"], 2)
        self.assertEqual(summary["failed_validations"], 1)
        self.assertEqual(summary["total_errors"], 1)
        self.assertFalse(summary["success"])

    def test_end_unknown_execution_returns_empty_summary(self):
        self.assertEqual(ExecutionTracker().end_execution("nao-existe"), {})


if __name__ == "__main__":
    unittest.main()
