"""
Suite de Testes para o SRAG Health Monitor.

Este módulo contém testes isolados para validar os principais componentes do sistema,
usando diretórios temporários e bancos de dados em memória para reprodutibilidade.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import unittest
import tempfile
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import json

# Configurar variável de ambiente para diretório temporário antes de importar config
temp_base = tempfile.mkdtemp(prefix='srag_test_')
os.environ['SRAG_BASE_DIR'] = temp_base

from database.db_manager import SRAGDatabase
from tools.database_tool import create_database_tool
from tools.news_tool import create_news_tool
from tools.chart_tool import create_chart_tool
from guardrails.validators import (
    InputValidator, OutputValidator, DataPrivacyGuard, RateLimiter
)
from guardrails.audit_logger import AuditLogger, ExecutionTracker


class TestDatabaseManagerIsolated(unittest.TestCase):
    """Testes isolados para o gerenciador de banco de dados."""
    
    def setUp(self):
        """Configuração antes de cada teste com banco temporário."""
        self.temp_dir = tempfile.mkdtemp(prefix='test_db_')
        self.db_path = os.path.join(self.temp_dir, 'test_srag.db')
        self.db = SRAGDatabase(self.db_path)
        self.db.connect()
        self.db.create_tables()
        
        # Popular com dados de teste
        self._populate_test_data()
    
    def tearDown(self):
        """Limpeza após cada teste."""
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _populate_test_data(self):
        """Popula o banco com dados de teste."""
        cursor = self.db.conn.cursor()
        
        # Adicionar 100 casos de teste
        base_date = datetime.now() - timedelta(days=60)
        for i in range(100):
            dt_notific = (base_date + timedelta(days=i % 60)).strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO casos_srag 
                (dt_notific, obito, internou_uti, vacinado, cs_sexo, idade_anos)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (dt_notific, i % 10 == 0, i % 5 == 0, i % 3 == 0, 1, 50.0))
        
        self.db.conn.commit()
    
    def test_get_total_cases(self):
        """Testa consulta de total de casos."""
        total = self.db.get_total_cases()
        self.assertEqual(total, 100, "Total de casos deve ser 100")
    
    def test_get_mortality_rate(self):
        """Testa cálculo de taxa de mortalidade."""
        rate = self.db.get_mortality_rate()
        self.assertGreaterEqual(rate, 0, "Taxa deve ser >= 0")
        self.assertLessEqual(rate, 100, "Taxa deve ser <= 100")
        # Com dados de teste, 10% dos casos são óbitos (i % 10 == 0)
        self.assertAlmostEqual(rate, 10.0, delta=1.0)
    
    def test_get_uti_occupation_rate(self):
        """Testa cálculo de taxa de ocupação de UTI."""
        rate = self.db.get_uti_occupation_rate()
        self.assertGreaterEqual(rate, 0, "Taxa deve ser >= 0")
        self.assertLessEqual(rate, 100, "Taxa deve ser <= 100")
        # Com dados de teste, 20% internaram em UTI (i % 5 == 0)
        self.assertAlmostEqual(rate, 20.0, delta=1.0)
    
    def test_get_vaccination_rate(self):
        """Testa cálculo de taxa de vacinação."""
        rate = self.db.get_vaccination_rate()
        self.assertGreaterEqual(rate, 0, "Taxa deve ser >= 0")
        self.assertLessEqual(rate, 100, "Taxa deve ser <= 100")
    
    def test_empty_table_handling(self):
        """Testa comportamento com tabela vazia."""
        # Criar novo DB vazio
        empty_db_path = os.path.join(self.temp_dir, 'empty.db')
        empty_db = SRAGDatabase(empty_db_path)
        empty_db.connect()
        empty_db.create_tables()
        
        # Verificar que retorna valores padrão sem erros
        self.assertEqual(empty_db.get_total_cases(), 0)
        self.assertEqual(empty_db.get_mortality_rate(), 0.0)
        self.assertEqual(empty_db.get_uti_occupation_rate(), 0.0)
        self.assertEqual(empty_db.get_vaccination_rate(), 0.0)
        self.assertEqual(empty_db.get_growth_rate(), 0.0)
        self.assertEqual(empty_db.get_daily_cases(), [])
        self.assertEqual(empty_db.get_monthly_cases(), [])
        
        empty_db.close()


class TestDatabaseTool(unittest.TestCase):
    """Testes para a ferramenta de consulta ao banco."""
    
    @classmethod
    def setUpClass(cls):
        """Configuração única para todos os testes."""
        cls.temp_dir = tempfile.mkdtemp(prefix='test_tool_')
        cls.db_path = os.path.join(cls.temp_dir, 'test_tool.db')
        
        # Criar e popular banco
        db = SRAGDatabase(cls.db_path)
        db.connect()
        db.create_tables()
        
        # Popular com dados
        cursor = db.conn.cursor()
        base_date = datetime.now() - timedelta(days=60)
        for i in range(50):
            dt_notific = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO casos_srag 
                (dt_notific, obito, internou_uti, vacinado)
                VALUES (?, ?, ?, ?)
            """, (dt_notific, i % 10 == 0, i % 5 == 0, i % 3 == 0))
        
        db.conn.commit()
        db.close()
        
        # Configurar variável de ambiente para a tool
        os.environ['SRAG_DB_PATH'] = cls.db_path
    
    @classmethod
    def tearDownClass(cls):
        """Limpeza após todos os testes."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
    
    def setUp(self):
        """Configuração antes de cada teste."""
        # Criar tool configurada para usar o DB de teste
        from tools.database_tool import DatabaseQueryTool, DatabaseQueryInput
        self.tool = DatabaseQueryTool()
        self.tool.db_path = self.__class__.db_path
    
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


class TestChartTool(unittest.TestCase):
    """Testes para a ferramenta de geração de gráficos."""
    
    def setUp(self):
        """Configuração antes de cada teste."""
        self.temp_dir = tempfile.mkdtemp(prefix='test_charts_')
        self.tool = create_chart_tool()
    
    def tearDown(self):
        """Limpeza após cada teste."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_daily_chart(self):
        """Testa geração de gráfico diário."""
        data = [
            {"date": "2024-12-01", "cases": 100},
            {"date": "2024-12-02", "cases": 150}
        ]
        
        result = self.tool._run(
            chart_type="daily",
            data=json.dumps(data),
            output_path=self.temp_dir
        )
        
        self.assertTrue(result.get('success'), f"Chart generation failed: {result.get('error')}")
        self.assertIn('filename', result)
        self.assertTrue(os.path.exists(result['filename']))
        # Verificar que timestamp está no nome do arquivo
        self.assertRegex(os.path.basename(result['filename']), r'casos_diarios_\d{8}_\d{6}\.png')
    
    def test_generate_monthly_chart(self):
        """Testa geração de gráfico mensal."""
        data = [
            {"month": "2024-10", "cases": 1000},
            {"month": "2024-11", "cases": 1200}
        ]
        
        result = self.tool._run(
            chart_type="monthly",
            data=json.dumps(data),
            output_path=self.temp_dir
        )
        
        self.assertTrue(result.get('success'), f"Chart generation failed: {result.get('error')}")
        self.assertIn('filename', result)
        self.assertTrue(os.path.exists(result['filename']))
        # Verificar que timestamp está no nome do arquivo
        self.assertRegex(os.path.basename(result['filename']), r'casos_mensais_\d{8}_\d{6}\.png')


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
        self.assertLessEqual(len(result['news']), 3)
    
    def test_news_structure(self):
        """Testa estrutura das notícias retornadas."""
        result = self.tool._run(max_results=1)
        
        if result['news']:
            news_item = result['news'][0]
            self.assertIn('title', news_item)
            self.assertIn('summary', news_item)
            self.assertIn('source', news_item)
            self.assertIn('date', news_item)


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
        self.assertNotIn("'", sanitized)
        self.assertEqual(sanitized, "SRAG scriptalertxss/script")


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


class TestAuditLogger(unittest.TestCase):
    """Testes para audit logger."""
    
    def setUp(self):
        """Configuração antes de cada teste."""
        self.temp_dir = tempfile.mkdtemp(prefix='test_audit_')
    
    def tearDown(self):
        """Limpeza após cada teste."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_audit_logger_initialization(self):
        """Testa inicialização do audit logger."""
        logger = AuditLogger(log_dir=self.temp_dir)
        self.assertIsNotNone(logger)
        self.assertTrue(os.path.exists(self.temp_dir))
    
    def test_audit_logger_idempotent(self):
        """Testa que audit logger é idempotente (não duplica handlers)."""
        logger1 = AuditLogger(log_dir=self.temp_dir)
        handler_count1 = len(logger1.logger.handlers)
        
        logger2 = AuditLogger(log_dir=self.temp_dir)
        handler_count2 = len(logger2.logger.handlers)
        
        # Deve ter o mesmo número de handlers (não duplicar)
        self.assertEqual(handler_count1, handler_count2)
    
    def test_log_event(self):
        """Testa registro de evento."""
        logger = AuditLogger(log_dir=self.temp_dir)
        logger.log_event("test_event", {"key": "value"}, "exec_123")
        
        # Verificar que o log foi criado
        log_files = list(Path(self.temp_dir).glob("audit_*.jsonl"))
        self.assertGreater(len(log_files), 0)


class TestExecutionTracker(unittest.TestCase):
    """Testes para execution tracker."""
    
    def setUp(self):
        """Configuração antes de cada teste."""
        self.tracker = ExecutionTracker()
    
    def test_start_execution(self):
        """Testa início de execução."""
        exec_id = "test_exec_001"
        execution = self.tracker.start_execution(exec_id)
        
        self.assertEqual(execution['execution_id'], exec_id)
        self.assertIn('start_time', execution)
    
    def test_end_execution(self):
        """Testa finalização de execução."""
        exec_id = "test_exec_002"
        self.tracker.start_execution(exec_id)
        summary = self.tracker.end_execution(exec_id)
        
        self.assertEqual(summary['execution_id'], exec_id)
        self.assertIn('duration_ms', summary)
        self.assertTrue(summary['success'])


def run_tests():
    """Executa todos os testes."""
    print("\n" + "="*80)
    print("EXECUTANDO SUITE DE TESTES ISOLADOS - SRAG Health Monitor")
    print("="*80 + "\n")
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Adicionar testes
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseManagerIsolated))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseTool))
    suite.addTests(loader.loadTestsFromTestCase(TestChartTool))
    suite.addTests(loader.loadTestsFromTestCase(TestNewsTool))
    suite.addTests(loader.loadTestsFromTestCase(TestInputValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestOutputValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestDataPrivacyGuard))
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestAuditLogger))
    suite.addTests(loader.loadTestsFromTestCase(TestExecutionTracker))
    
    # Executar testes
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Sumário
    print("\n" + "="*80)
    print("SUMÁRIO DOS TESTES")
    print("="*80)
    print(f"Total de testes: {result.testsRun}")
    print(f"Sucessos: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Falhas: {len(result.failures)}")
    print(f"Erros: {len(result.errors)}")
    print("="*80 + "\n")
    
    # Limpar diretório temporário da classe
    if hasattr(TestDatabaseManagerIsolated, 'temp_base'):
        shutil.rmtree(temp_base, ignore_errors=True)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
