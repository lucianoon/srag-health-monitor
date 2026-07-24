"""Testes dos guardrails (src/guardrails/validators.py)."""

import unittest

import tests.conftest  # noqa: F401  garante src/ no sys.path
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

    def test_sanitize_search_query(self):
        query = "SRAG <script>alert('xss')</script>"
        sanitized = InputValidator.sanitize_search_query(query)
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)


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


class TestRateLimiter(unittest.TestCase):
    def test_rate_limiter_allows_calls(self):
        limiter = RateLimiter(max_calls_per_minute=10)
        for _ in range(5):
            allowed, _ = limiter.check_rate_limit()
            self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
