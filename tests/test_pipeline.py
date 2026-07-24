"""Testes do pipeline multiagente coordenado por blackboard.

Cobre o blackboard genérico (src/services/report_blackboard.py), o
orquestrador (src/agents/report_pipeline.py) e os agentes de ingestão,
análise e escrita de relatório.
"""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.conftest import (  # também garante src/ no sys.path
    TempSRAGDatabaseMixin,
    make_app_config,
    offline_news_guard,
)
from agents.data_ingestion_agent import DataSnapshot, SUSDataIngestionAgent
from agents.epidemiology_analysis_agent import EpidemiologyAnalysisAgent
from agents.report_pipeline import SRAGMultiAgentReportOrchestrator
from agents.report_writer_agent import ReportNarrative, ReportWriterAgent
from guardrails.validators import OutputValidator
from services.report_blackboard import ReportBlackboard, Step, StepExecutionError

# Mantém o módulo offline: o pipeline coleta notícias como parte da execução.
setUpModule, tearDownModule = offline_news_guard()


class TestReportBlackboard(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.state_path = Path(self.tmpdir.name) / "state.json"

    def test_independent_steps_run_in_parallel(self):
        # O Barrier só libera quando as duas etapas estão rodando ao mesmo
        # tempo; execução sequencial estoura o timeout e falha o teste.
        barrier = threading.Barrier(2, timeout=5)

        def step_a(artifacts):
            barrier.wait()
            return {"a": 1}

        def step_b(artifacts):
            barrier.wait()
            return {"b": 2}

        def join(artifacts):
            return {"total": artifacts["a"] + artifacts["b"]}

        board = ReportBlackboard(
            [
                Step(name="a", run=step_a),
                Step(name="b", run=step_b),
                Step(name="join", run=join, requires=("a", "b")),
            ]
        )

        artifacts = board.run()

        self.assertEqual(artifacts["total"], 3)

    def test_resume_skips_done_steps_and_retries_failed(self):
        calls = {"a": 0, "b": 0}

        def step_a(artifacts):
            calls["a"] += 1
            return {"a": 1}

        def failing_b(artifacts):
            calls["b"] += 1
            raise RuntimeError("primeira tentativa falha")

        def fixed_b(artifacts):
            calls["b"] += 1
            return {"b": artifacts["a"] + 1}

        def build_steps(b_run):
            return [
                Step(name="a", run=step_a),
                Step(name="b", run=b_run, requires=("a",)),
            ]

        with self.assertRaises(StepExecutionError):
            ReportBlackboard(build_steps(failing_b), state_path=self.state_path).run()

        artifacts = ReportBlackboard(
            build_steps(fixed_b), state_path=self.state_path
        ).run()

        self.assertEqual(calls["a"], 1)  # etapa concluída não re-executa
        self.assertEqual(calls["b"], 2)  # etapa falha é re-tentada
        self.assertEqual(artifacts["b"], 2)

    def test_unknown_precondition_is_rejected(self):
        with self.assertRaises(ValueError):
            ReportBlackboard(
                [Step(name="a", run=lambda artifacts: {}, requires=("fantasma",))]
            )


class TestMultiAgentPipeline(TempSRAGDatabaseMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.config = make_app_config(self.tmpdir.name, db_path=self.db_path)

    def test_pipeline_resumes_without_repeating_completed_steps(self):
        first = SRAGMultiAgentReportOrchestrator(config=self.config)
        first.writer_agent.write = mock.Mock(
            side_effect=RuntimeError("falha simulada na escrita")
        )

        with self.assertRaises(StepExecutionError):
            first.run()
        self.assertTrue(first.state_path.exists())

        resumed = SRAGMultiAgentReportOrchestrator(
            config=self.config,
            execution_id=first.execution_id,
        )
        # Se a retomada refizesse coleta, análise ou gráficos, quebraria aqui.
        resumed.ingestion_agent = None
        resumed.analysis_agent = None
        resumed.writer_agent.generate_charts = None

        report = resumed.run()

        self.assertIn("Relatório de Monitoramento de SRAG", report)
        self.assertTrue(resumed.report_path.exists())
        self.assertFalse(resumed.state_path.exists())  # estado limpo ao concluir

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


if __name__ == "__main__":
    unittest.main()
