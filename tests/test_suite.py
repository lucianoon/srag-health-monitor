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
from agents.data_ingestion_agent import DataSnapshot, SUSDataIngestionAgent
from agents.epidemiology_analysis_agent import EpidemiologyAnalysisAgent
from agents.report_writer_agent import ReportNarrative, ReportWriterAgent
from config import AppConfig
from guardrails.validators import (
    DataPrivacyGuard,
    InputValidator,
    OutputValidator,
    RateLimiter,
)
from guardrails.audit_logger import AuditLogger, ExecutionTracker
from services.job_store import InMemoryJobStore, JobStatus, SQLiteJobStore
from services.data_ingestion_service import DataIngestionService
from services.report_service import GenerateReportService
from services.report_worker import ReportWorker
from tools.chart_tool import create_chart_tool
from tools.database_tool import DatabaseQueryTool
import requests

from tools.news_tool import NewsSearchTool, create_news_tool, parse_feed


def setUpModule():
    """Mantém o suite offline: o fetch real de notícias é desabilitado por padrão.

    Testes que exercitam o parsing/ranking injetam seu próprio fetch por
    instância (o atributo de instância sombreia este stub de classe).
    """
    def _offline_fetch(self, url):
        raise requests.RequestException("rede desabilitada em testes")

    global _ORIGINAL_FETCH_FEED
    _ORIGINAL_FETCH_FEED = NewsSearchTool._fetch_feed
    NewsSearchTool._fetch_feed = _offline_fetch


def tearDownModule():
    NewsSearchTool._fetch_feed = _ORIGINAL_FETCH_FEED


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


SAMPLE_FIOCRUZ_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Agencia Fiocruz</title>
    <item>
      <title>Nav. ed. pt Bibliotecas</title>
      <link>https://agencia.fiocruz.br/nav</link>
      <pubDate>Thu, 02 Jul 2026 18:05:40 +0000</pubDate>
      <description>menu de navegacao</description>
    </item>
    <item>
      <title>InfoGripe alerta para alta de casos de SRAG no pais</title>
      <link>https://agencia.fiocruz.br/infogripe-srag</link>
      <pubDate>Thu, 02 Jul 2026 14:07:27 +0000</pubDate>
      <description>&lt;p&gt;Boletim aponta &lt;b&gt;aumento&lt;/b&gt; de casos de SRAG.&lt;/p&gt;</description>
    </item>
    <item>
      <title>Fiocruz inaugura novo predio administrativo</title>
      <link>https://agencia.fiocruz.br/predio</link>
      <pubDate>Wed, 01 Jul 2026 10:00:00 +0000</pubDate>
      <description>Nota institucional sem relacao com epidemiologia.</description>
    </item>
  </channel>
</rss>"""


class TestNewsFeedParsing(unittest.TestCase):
    def test_parse_feed_strips_html_and_normalizes_date(self):
        items = parse_feed(SAMPLE_FIOCRUZ_FEED, "Agência Fiocruz")
        titles = [item["title"] for item in items]

        self.assertNotIn("Nav. ed. pt Bibliotecas", titles)  # item de navegação filtrado
        srag_item = next(item for item in items if "InfoGripe" in item["title"])
        self.assertEqual(srag_item["source"], "Agência Fiocruz")
        self.assertEqual(srag_item["date"], "2026-07-02")
        self.assertNotIn("<", srag_item["summary"])  # HTML removido
        self.assertIn("SRAG", srag_item["summary"])
        self.assertTrue(srag_item["url"].startswith("https://"))


class TestNewsTool(unittest.TestCase):
    def _tool_with_feed(self, content):
        tool = create_news_tool()
        tool.feeds = [{"name": "Fonte Teste", "url": "https://example.test/feed"}]
        tool._fetch_feed = lambda url: content
        return tool

    def test_search_news_ranks_relevant_items_first(self):
        tool = self._tool_with_feed(SAMPLE_FIOCRUZ_FEED)
        result = tool._run(max_results=3)

        self.assertIn("news", result)
        self.assertIn("total_results", result)
        # 2 itens válidos (o de navegação é filtrado); o de SRAG vem primeiro.
        self.assertEqual(len(result["news"]), 2)
        self.assertIn("SRAG", result["news"][0]["title"])

    def test_news_structure(self):
        tool = self._tool_with_feed(SAMPLE_FIOCRUZ_FEED)
        result = tool._run(max_results=1)
        news_item = result["news"][0]
        for key in ("title", "summary", "source", "date", "url"):
            self.assertIn(key, news_item)

    def test_search_news_degrades_gracefully_on_fetch_failure(self):
        def failing_fetch(url):
            raise requests.RequestException("rede indisponível")

        tool = create_news_tool()
        tool._fetch_feed = failing_fetch
        result = tool._run(max_results=5)

        # Sem rede, retorna lista vazia sem fabricar notícias.
        self.assertEqual(result["news"], [])
        self.assertEqual(result["total_results"], 0)


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


class TestGenerateReportService(TempSRAGDatabaseMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.output_dir = Path(self.tmpdir.name) / "reports"
        self.log_dir = Path(self.tmpdir.name) / "logs"
        self.config = AppConfig(
            project_root=PROJECT_ROOT,
            data_dir=Path(self.tmpdir.name),
            db_path=Path(self.db_path),
            jobs_db_path=Path(self.tmpdir.name) / "jobs.db",
            reports_dir=self.output_dir,
            logs_dir=self.log_dir,
            model_name="gpt-4.1-mini",
            openai_api_key=None,
        )

    def test_generate_report_success(self):
        service = GenerateReportService(
            config=self.config,
            audit_logger=AuditLogger(self.log_dir),
            execution_tracker=ExecutionTracker(),
        )

        result = service.run()

        self.assertIn("Relatório de Monitoramento de SRAG", result.report)
        self.assertIn("Nível de Risco", result.report)
        self.assertIn("Fonte e Rastreabilidade", result.report)
        self.assertTrue(result.report_path.exists())
        self.assertEqual(result.summary["total_errors"], 0)

    def test_generate_report_missing_database_fails(self):
        missing_config = AppConfig(
            project_root=PROJECT_ROOT,
            data_dir=Path(self.tmpdir.name),
            db_path=Path(self.tmpdir.name) / "missing.db",
            jobs_db_path=Path(self.tmpdir.name) / "jobs.db",
            reports_dir=self.output_dir,
            logs_dir=self.log_dir,
            model_name="gpt-4.1-mini",
            openai_api_key=None,
        )
        service = GenerateReportService(
            config=missing_config,
            audit_logger=AuditLogger(self.log_dir),
            execution_tracker=ExecutionTracker(),
        )

        with self.assertRaises(RuntimeError):
            service.run()


class TestMultiAgentPipeline(TempSRAGDatabaseMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.config = AppConfig(
            project_root=PROJECT_ROOT,
            data_dir=Path(self.tmpdir.name),
            db_path=Path(self.db_path),
            jobs_db_path=Path(self.tmpdir.name) / "jobs.db",
            reports_dir=Path(self.tmpdir.name) / "reports",
            logs_dir=Path(self.tmpdir.name) / "logs",
            model_name="gpt-4.1-mini",
            openai_api_key=None,
        )

    def test_ingestion_agent_collects_snapshot_with_source_metadata(self):
        snapshot = SUSDataIngestionAgent(self.config).collect(
            days=7,
            months=3,
            news_limit=1,
        )

        self.assertIn("total_casos", snapshot.metrics)
        self.assertIn("daily_cases", snapshot.daily_cases)
        self.assertIn("monthly_cases", snapshot.monthly_cases)
        self.assertEqual(snapshot.source["provider"], "DATASUS/SIVEP-Gripe")

    def test_analysis_agent_classifies_high_risk_when_indicators_are_bad(self):
        snapshot = DataSnapshot(
            metrics={
                "taxa_aumento_casos": 20.0,
                "taxa_mortalidade": 12.0,
                "taxa_ocupacao_uti": 35.0,
                "taxa_vacinacao": 40.0,
                "total_casos": 100,
            },
            daily_cases={"daily_cases": []},
            monthly_cases={"monthly_cases": []},
            news={"news": []},
            source={"provider": "DATASUS/SIVEP-Gripe"},
        )

        analysis = EpidemiologyAnalysisAgent().analyze(snapshot)

        self.assertEqual(analysis.risk_level, "alto")
        self.assertEqual(len(analysis.findings), 4)

    def test_report_writer_includes_source_traceability(self):
        snapshot = DataSnapshot(
            metrics={
                "taxa_aumento_casos": 0.0,
                "taxa_mortalidade": 7.0,
                "taxa_ocupacao_uti": 25.0,
                "taxa_vacinacao": 65.0,
                "total_casos": 12,
            },
            daily_cases={"daily_cases": []},
            monthly_cases={"monthly_cases": []},
            news={"news": []},
            source={
                "provider": "DATASUS/SIVEP-Gripe",
                "source_type": "sqlite_cache",
                "updated_at": "2026-07-04T00:00:00",
            },
        )
        analysis = EpidemiologyAnalysisAgent().analyze(snapshot)

        report = ReportWriterAgent(self.config).write(
            analysis=analysis,
            charts={},
            execution_id="exec-1",
        )

        self.assertIn("Fonte e Rastreabilidade", report)
        self.assertIn("sqlite_cache", report)
        self.assertIn("Narrativa: deterministica", report)

    def _build_analysis(self):
        snapshot = DataSnapshot(
            metrics={
                "taxa_aumento_casos": 0.0,
                "taxa_mortalidade": 7.0,
                "taxa_ocupacao_uti": 25.0,
                "taxa_vacinacao": 65.0,
                "total_casos": 12,
            },
            daily_cases={"daily_cases": []},
            monthly_cases={"monthly_cases": []},
            news={"news": []},
            source={"provider": "DATASUS/SIVEP-Gripe"},
        )
        return EpidemiologyAnalysisAgent().analyze(snapshot)

    def test_report_writer_uses_llm_narrative_when_available(self):
        narrative = ReportNarrative(
            cenario_atual="Cenário epidemiológico estável segundo análise do modelo.",
            conclusoes_e_recomendacoes="- Manter vigilância ativa nas regiões monitoradas.",
        )

        class FakeLLM:
            def with_structured_output(self, schema):
                return self

            def invoke(self, messages):
                return narrative

        writer = ReportWriterAgent(self.config, llm=FakeLLM())
        report = writer.write(
            analysis=self._build_analysis(),
            charts={},
            execution_id="exec-llm",
        )

        self.assertIn("Cenário epidemiológico estável segundo análise do modelo.", report)
        self.assertIn("- Manter vigilância ativa nas regiões monitoradas.", report)
        self.assertIn("Narrativa: llm (gpt-4.1-mini)", report)
        valid, message = OutputValidator.validate_report_content(report)
        self.assertTrue(valid, message)

    def test_report_writer_falls_back_when_llm_fails(self):
        class FailingLLM:
            def with_structured_output(self, schema):
                raise RuntimeError("LLM indisponível")

        writer = ReportWriterAgent(self.config, llm=FailingLLM())
        report = writer.write(
            analysis=self._build_analysis(),
            charts={},
            execution_id="exec-fallback",
        )

        self.assertIn("Narrativa: deterministica", report)
        self.assertIn("A taxa de mortalidade está", report)
        valid, message = OutputValidator.validate_report_content(report)
        self.assertTrue(valid, message)

    def test_report_writer_falls_back_when_llm_returns_empty_narrative(self):
        empty_narrative = ReportNarrative(
            cenario_atual="   ",
            conclusoes_e_recomendacoes="",
        )

        class EmptyLLM:
            def with_structured_output(self, schema):
                return self

            def invoke(self, messages):
                return empty_narrative

        writer = ReportWriterAgent(self.config, llm=EmptyLLM())
        report = writer.write(
            analysis=self._build_analysis(),
            charts={},
            execution_id="exec-empty",
        )

        self.assertIn("Narrativa: deterministica", report)
        self.assertIn("A taxa de mortalidade está", report)

    def test_report_writer_without_api_key_has_no_llm(self):
        writer = ReportWriterAgent(self.config)
        self.assertIsNone(writer.llm)


class TestDataIngestionService(unittest.TestCase):
    def test_ingestion_downloads_processes_and_loads_sqlite_cache(self):
        import unittest.mock as mock

        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(
                project_root=PROJECT_ROOT,
                data_dir=Path(tmpdir),
                db_path=Path(tmpdir) / "srag.db",
                jobs_db_path=Path(tmpdir) / "jobs.db",
                reports_dir=Path(tmpdir) / "reports",
                logs_dir=Path(tmpdir) / "logs",
                model_name="gpt-4.1-mini",
                openai_api_key=None,
                sus_data_url="https://dadosabertos.saude.gov.br/srag.csv",
            )
            csv_bytes = self._sample_srag_csv().encode("latin1")

            response = mock.Mock()
            response.raise_for_status.return_value = None
            response.iter_content.return_value = [csv_bytes]

            with mock.patch(
                "services.data_ingestion_service.requests.get",
                return_value=response,
            ):
                result = DataIngestionService(config).run()

            db = SRAGDatabase(str(config.db_path))
            db.connect()
            try:
                total_cases = db.get_total_cases()
            finally:
                db.close()

            self.assertEqual(result.rows_processed, 2)
            self.assertEqual(total_cases, 2)
            self.assertTrue(result.metadata_path.exists())

    @staticmethod
    def _sample_srag_csv() -> str:
        header = [
            "DT_NOTIFIC", "DT_SIN_PRI", "SG_UF", "CO_MUN_RES", "CS_SEXO",
            "NU_IDADE_N", "TP_IDADE", "EVOLUCAO", "UTI", "DT_ENTUTI",
            "DT_SAIDUTI", "VACINA", "VACINA_COV", "DOSE_1_COV",
            "DOSE_2_COV", "DOSE_REF", "CLASSI_FIN", "DT_EVOLUCA",
            "DT_INTERNA", "HOSPITAL", "FEBRE", "TOSSE", "DISPNEIA",
            "SATURACAO",
        ]
        rows = [
            [
                "2024-01-01", "2023-12-30", "SP", "355030", "1", "40",
                "4", "1", "2", "", "", "1", "2", "", "", "", "5",
                "2024-01-05", "2024-01-02", "1", "1", "1", "2", "2",
            ],
            [
                "2024-01-02", "2023-12-31", "RJ", "330455", "2", "70",
                "4", "2", "1", "2024-01-03", "2024-01-07", "2", "1",
                "", "", "", "5", "2024-01-08", "2024-01-02", "1",
                "1", "1", "1", "1",
            ],
        ]
        lines = [";".join(header)]
        lines.extend(";".join(row) for row in rows)
        return "\n".join(lines)


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


class TestReportWorker(TempSRAGDatabaseMixin, unittest.TestCase):
    def test_worker_runs_queued_job_successfully(self):
        output_dir = Path(self.tmpdir.name) / "reports"
        store = SQLiteJobStore(Path(self.tmpdir.name) / "jobs.db")
        job = store.create(payload={
            "db_path": self.db_path,
            "output_dir": str(output_dir),
        })
        worker = ReportWorker(store, poll_interval_seconds=0.01)

        result = worker.run_once()

        self.assertEqual(result.job_id, job.job_id)
        self.assertEqual(result.status, JobStatus.SUCCEEDED)
        self.assertTrue(Path(result.report_path).exists())

    def test_worker_marks_job_failed_when_database_is_missing(self):
        store = SQLiteJobStore(Path(self.tmpdir.name) / "jobs.db")
        job = store.create(payload={
            "db_path": str(Path(self.tmpdir.name) / "missing.db"),
            "output_dir": str(Path(self.tmpdir.name) / "reports"),
        })
        worker = ReportWorker(store, poll_interval_seconds=0.01)

        result = worker.run_once()

        self.assertEqual(result.job_id, job.job_id)
        self.assertEqual(result.status, JobStatus.FAILED)
        self.assertIn("Banco de dados não encontrado", result.error)


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


def run_tests():
    loader = unittest.TestLoader()
    suite = loader.discover(str(PROJECT_ROOT / "tests"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
