"""
Suite de testes para o SRAG Health Monitor.

Os testes usam banco SQLite temporário para evitar caminhos absolutos e tornar a
suíte reprodutível em qualquer ambiente/CI.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from database.db_manager import SRAGDatabase
from guardrails.validators import (
    DataPrivacyGuard,
    InputValidator,
    OutputValidator,
    RateLimiter,
)
from tools.chart_tool import create_chart_tool
from tools.database_tool import DatabaseQueryTool
from tools.news_tool import create_news_tool


class TempSRAGDatabaseMixin:
    """Cria um banco SRAG temporário com dados determinísticos."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "srag.db")
        self.db = SRAGDatabase(self.db_path)
        self.db.connect()
        self.db.create_tables()
        self._insert_sample_rows()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _insert_sample_rows(self):
        cursor = self.db.conn.cursor()
        base = datetime(2024, 12, 1)
        rows = []
        for i in range(12):
            date = base + timedelta(days=i)
            rows.append((
                date.strftime("%Y-%m-%d %H:%M:%S"),
                "SP",
                1 if i % 4 == 0 else 0,   # obito
                1 if i % 3 == 0 else 0,   # internou_uti
                1 if i % 2 == 0 else 0,   # vacinado
            ))
        cursor.executemany(
            """
            INSERT INTO casos_srag (
                dt_notific, sg_uf, obito, internou_uti, vacinado
            ) VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.db.conn.commit()


class TestDatabaseManager(TempSRAGDatabaseMixin, unittest.TestCase):
    """Testes para o gerenciador de banco de dados."""

    def test_get_total_cases(self):
        total = self.db.get_total_cases()
        self.assertEqual(total, 12)

    def test_get_mortality_rate(self):
        rate = self.db.get_mortality_rate()
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)

    def test_get_uti_occupation_rate(self):
        rate = self.db.get_uti_occupation_rate()
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)

    def test_get_vaccination_rate(self):
        rate = self.db.get_vaccination_rate()
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)


class TestDatabaseTool(TempSRAGDatabaseMixin, unittest.TestCase):
    """Testes para a ferramenta de consulta ao banco."""

    def setUp(self):
        super().setUp()
        self.tool = DatabaseQueryTool(db_path=self.db_path)

    def test_query_metrics(self):
        result = self.tool._run(query_type="metrics")
        self.assertIn("taxa_aumento_casos", result)
        self.assertIn("taxa_mortalidade", result)
        self.assertIn("taxa_ocupacao_uti", result)
        self.assertIn("taxa_vacinacao", result)

    def test_query_daily_cases(self):
        result = self.tool._run(query_type="daily_cases", days=7)
        self.assertIn("daily_cases", result)
        self.assertIsInstance(result["daily_cases"], list)

    def test_query_monthly_cases(self):
        result = self.tool._run(query_type="monthly_cases", months=3)
        self.assertIn("monthly_cases", result)
        self.assertIsInstance(result["monthly_cases"], list)


class TestNewsTool(unittest.TestCase):
    def setUp(self):
        self.tool = create_news_tool()

    def test_search_news(self):
        result = self.tool._run(max_results=3)
        self.assertIn("news", result)
        self.assertIn("total_results", result)
        self.assertEqual(len(result["news"]), 3)

    def test_news_structure(self):
        result = self.tool._run(max_results=1)
        news_item = result["news"][0]
        self.assertIn("title", news_item)
        self.assertIn("summary", news_item)
        self.assertIn("source", news_item)
        self.assertIn("date", news_item)


class TestChartTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmpdir.name)
        self.tool = create_chart_tool()

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmpdir.cleanup()

    def test_generate_daily_chart(self):
        import json
        data = [
            {"date": "2024-12-01", "cases": 100},
            {"date": "2024-12-02", "cases": 150},
        ]
        result = self.tool._run(chart_type="daily", data=json.dumps(data))
        self.assertTrue(result["success"])
        self.assertIn("filename", result)

    def test_generate_monthly_chart(self):
        import json
        data = [
            {"month": "2024-10", "cases": 1000},
            {"month": "2024-11", "cases": 1200},
        ]
        result = self.tool._run(chart_type="monthly", data=json.dumps(data))
        self.assertTrue(result["success"])
        self.assertIn("filename", result)


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


def run_tests():
    loader = unittest.TestLoader()
    suite = loader.discover(str(PROJECT_ROOT / "tests"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
