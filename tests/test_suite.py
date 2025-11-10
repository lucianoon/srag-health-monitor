"""
Suite de Testes para o SRAG Health Monitor.

Este módulo contém testes para validar os principais componentes do sistema.
"""

from guardrails.validators import (
    InputValidator, OutputValidator, DataPrivacyGuard, RateLimiter
)
from tools.chart_tool import create_chart_tool
from tools.news_tool import create_news_tool
from tools.database_tool import create_database_tool
from database.db_manager import SRAGDatabase
from datetime import datetime
import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestDatabaseManager(unittest.TestCase):
    """Testes para o gerenciador de banco de dados."""

    def setUp(self):
        """Configuração antes de cada teste."""
        self.db_path = "/home/ubuntu/srag-health-monitor/data/srag.db"
        self.db = SRAGDatabase(self.db_path)
        self.db.connect()

    def tearDown(self):
        """Limpeza após cada teste."""
        self.db.close()

    def test_get_total_cases(self):
        """Testa consulta de total de casos."""
        total = self.db.get_total_cases()
        self.assertGreater(total, 0, "Total de casos deve ser maior que 0")

    def test_get_mortality_rate(self):
        """Testa cálculo de taxa de mortalidade."""
        rate = self.db.get_mortality_rate()
        self.assertGreaterEqual(rate, 0, "Taxa deve ser >= 0")
        self.assertLessEqual(rate, 100, "Taxa deve ser <= 100")

    def test_get_uti_occupation_rate(self):
        """Testa cálculo de taxa de ocupação de UTI."""
        rate = self.db.get_uti_occupation_rate()
        self.assertGreaterEqual(rate, 0, "Taxa deve ser >= 0")
        self.assertLessEqual(rate, 100, "Taxa deve ser <= 100")

    def test_get_vaccination_rate(self):
        """Testa cálculo de taxa de vacinação."""
        rate = self.db.get_vaccination_rate()
        self.assertGreaterEqual(rate, 0, "Taxa deve ser >= 0")
        self.assertLessEqual(rate, 100, "Taxa deve ser <= 100")


class TestDatabaseTool(unittest.TestCase):
    """Testes para a ferramenta de consulta ao banco."""

    def setUp(self):
        """Configuração antes de cada teste."""
        self.tool = create_database_tool()

    def test_query_metrics(self):
        """Testa consulta de métricas."""
        result = self.tool._run(query_type="metrics")

        self.assertIn('taxa_aumento_casos', result)
        self.assertIn('taxa_mortalidade', result)
        self.assertIn('taxa_ocupacao_uti', result)
        self.assertIn('taxa_vacinacao', result)

    def test_query_daily_cases(self):
        """Testa consulta de casos diários."""
        result = self.tool._run(query_type="daily_cases", days=7)

        self.assertIn('daily_cases', result)
        self.assertIsInstance(result['daily_cases'], list)

    def test_query_monthly_cases(self):
        """Testa consulta de casos mensais."""
        result = self.tool._run(query_type="monthly_cases", months=3)

        self.assertIn('monthly_cases', result)
        self.assertIsInstance(result['monthly_cases'], list)


class TestNewsTool(unittest.TestCase):
    """Testes para a ferramenta de busca de notícias."""

    def setUp(self):
        """Configuração antes de cada teste."""
        self.tool = create_news_tool()

    def test_search_news(self):
        """Testa busca de notícias."""
        result = self.tool._run(max_results=3)

        self.assertIn('news', result)
        self.assertIn('total_results', result)
        self.assertEqual(len(result['news']), 3)

    def test_news_structure(self):
        """Testa estrutura das notícias retornadas."""
        result = self.tool._run(max_results=1)

        news_item = result['news'][0]
        self.assertIn('title', news_item)
        self.assertIn('summary', news_item)
        self.assertIn('source', news_item)
        self.assertIn('date', news_item)


class TestChartTool(unittest.TestCase):
    """Testes para a ferramenta de geração de gráficos."""

    def setUp(self):
        """Configuração antes de cada teste."""
        self.tool = create_chart_tool()

    def test_generate_daily_chart(self):
        """Testa geração de gráfico diário."""
        import json

        data = [
            {"date": "2024-12-01", "cases": 100},
            {"date": "2024-12-02", "cases": 150}
        ]

        result = self.tool._run(
            chart_type="daily",
            data=json.dumps(data)
        )

        self.assertTrue(result['success'])
        self.assertIn('filename', result)

    def test_generate_monthly_chart(self):
        """Testa geração de gráfico mensal."""
        import json

        data = [
            {"month": "2024-10", "cases": 1000},
            {"month": "2024-11", "cases": 1200}
        ]

        result = self.tool._run(
            chart_type="monthly",
            data=json.dumps(data)
        )

        self.assertTrue(result['success'])
        self.assertIn('filename', result)


class TestInputValidator(unittest.TestCase):
    """Testes para validação de entrada."""

    def test_validate_query_type_valid(self):
        """Testa validação de tipo de consulta válido."""
        valid, msg = InputValidator.validate_query_type("metrics")
        self.assertTrue(valid)

    def test_validate_query_type_invalid(self):
        """Testa validação de tipo de consulta inválido."""
        valid, msg = InputValidator.validate_query_type("invalid")
        self.assertFalse(valid)

    def test_validate_days_parameter_valid(self):
        """Testa validação de parâmetro de dias válido."""
        valid, msg = InputValidator.validate_days_parameter(30)
        self.assertTrue(valid)

    def test_validate_days_parameter_invalid(self):
        """Testa validação de parâmetro de dias inválido."""
        valid, msg = InputValidator.validate_days_parameter(500)
        self.assertFalse(valid)

    def test_sanitize_search_query(self):
        """Testa sanitização de query de busca."""
        query = "SRAG <script>alert('xss')</script>"
        sanitized = InputValidator.sanitize_search_query(query)

        self.assertNotIn('<', sanitized)
        self.assertNotIn('>', sanitized)


class TestOutputValidator(unittest.TestCase):
    """Testes para validação de saída."""

    def test_validate_metrics_valid(self):
        """Testa validação de métricas válidas."""
        metrics = {
            'taxa_aumento_casos': 5.0,
            'taxa_mortalidade': 7.5,
            'taxa_ocupacao_uti': 25.0,
            'taxa_vacinacao': 50.0
        }

        valid, msg = OutputValidator.validate_metrics(metrics)
        self.assertTrue(valid)

    def test_validate_metrics_invalid_range(self):
        """Testa validação de métricas com valores fora do range."""
        metrics = {
            'taxa_aumento_casos': 5.0,
            'taxa_mortalidade': 150.0,  # Inválido
            'taxa_ocupacao_uti': 25.0,
            'taxa_vacinacao': 50.0
        }

        valid, msg = OutputValidator.validate_metrics(metrics)
        self.assertFalse(valid)

    def test_validate_report_content(self):
        """Testa validação de conteúdo de relatório."""
        report = """
        # Relatório de SRAG

        ## Métricas Principais
        Taxa de Mortalidade: 7.5%
        Taxa de Ocupação de UTI: 25%
        Taxa de Vacinação: 50%
        """

        valid, msg = OutputValidator.validate_report_content(report)
        self.assertTrue(valid)


class TestDataPrivacyGuard(unittest.TestCase):
    """Testes para proteção de dados."""

    def test_check_for_pii_with_cpf(self):
        """Testa detecção de CPF."""
        text = "Paciente com CPF 123.456.789-00"
        has_pii, types = DataPrivacyGuard.check_for_pii(text)

        self.assertTrue(has_pii)
        self.assertIn('CPF', types)

    def test_check_for_pii_without_pii(self):
        """Testa texto sem PII."""
        text = "Taxa de mortalidade é de 7.5%"
        has_pii, types = DataPrivacyGuard.check_for_pii(text)

        self.assertFalse(has_pii)
        self.assertEqual(len(types), 0)

    def test_anonymize_text(self):
        """Testa anonimização de texto."""
        text = "CPF 123.456.789-00 e telefone (11) 98765-4321"
        anonymized = DataPrivacyGuard.anonymize_text(text)

        self.assertNotIn('123.456.789-00', anonymized)
        self.assertNotIn('98765-4321', anonymized)
        self.assertIn('***.***.***-**', anonymized)


class TestRateLimiter(unittest.TestCase):
    """Testes para rate limiter."""

    def test_rate_limiter_allows_calls(self):
        """Testa que rate limiter permite chamadas."""
        limiter = RateLimiter(max_calls_per_minute=10)

        for _ in range(5):
            allowed, msg = limiter.check_rate_limit()
            self.assertTrue(allowed)


def run_tests():
    """Executa todos os testes."""
    print("\n" + "=" * 80)
    print("EXECUTANDO SUITE DE TESTES - SRAG Health Monitor")
    print("=" * 80 + "\n")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Adicionar testes
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseManager))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseTool))
    suite.addTests(loader.loadTestsFromTestCase(TestNewsTool))
    suite.addTests(loader.loadTestsFromTestCase(TestChartTool))
    suite.addTests(loader.loadTestsFromTestCase(TestInputValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestOutputValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestDataPrivacyGuard))
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiter))

    # Executar testes
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Sumário
    print("\n" + "=" * 80)
    print("SUMÁRIO DOS TESTES")
    print("=" * 80)
    print(f"Total de testes: {result.testsRun}")
    print(f"Sucessos: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Falhas: {len(result.failures)}")
    print(f"Erros: {len(result.errors)}")
    print("=" * 80 + "\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
