"""Agente de análise epidemiológica de SRAG."""

from dataclasses import dataclass
import logging

from agents.data_ingestion_agent import DataSnapshot


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EpidemiologyAnalysis:
    """Resultado analítico usado pelo agente de relatório."""

    metrics: dict
    daily_cases: dict
    monthly_cases: dict
    news: dict
    source: dict
    findings: list
    risk_level: str


class EpidemiologyAnalysisAgent:
    """Calcula achados, risco e recomendações a partir dos dados coletados."""

    def analyze(self, snapshot: DataSnapshot) -> EpidemiologyAnalysis:
        logger.info("Agente epidemiológico analisando dados de SRAG")
        metrics = snapshot.metrics
        findings = [
            self._growth_finding(metrics.get("taxa_aumento_casos", 0.0)),
            self._mortality_finding(metrics.get("taxa_mortalidade", 0.0)),
            self._uti_finding(metrics.get("taxa_ocupacao_uti", 0.0)),
            self._vaccination_finding(metrics.get("taxa_vacinacao", 0.0)),
        ]

        return EpidemiologyAnalysis(
            metrics=metrics,
            daily_cases=snapshot.daily_cases,
            monthly_cases=snapshot.monthly_cases,
            news=snapshot.news,
            source=snapshot.source,
            findings=findings,
            risk_level=self._risk_level(metrics),
        )

    @staticmethod
    def _growth_finding(value: float) -> dict:
        if value > 10:
            return {
                "kind": "growth",
                "severity": "high",
                "message": "Crescimento relevante de casos no período recente.",
            }
        if value < -10:
            return {
                "kind": "growth",
                "severity": "low",
                "message": "Redução relevante de casos no período recente.",
            }
        return {
            "kind": "growth",
            "severity": "moderate",
            "message": "Casos relativamente estáveis no período recente.",
        }

    @staticmethod
    def _mortality_finding(value: float) -> dict:
        severity = "high" if value > 10 else "moderate" if value >= 5 else "low"
        return {
            "kind": "mortality",
            "severity": severity,
            "message": f"Taxa de mortalidade observada: {value:.2f}%.",
        }

    @staticmethod
    def _uti_finding(value: float) -> dict:
        severity = "high" if value > 30 else "moderate" if value >= 20 else "low"
        return {
            "kind": "uti",
            "severity": severity,
            "message": f"Taxa de internação em UTI observada: {value:.2f}%.",
        }

    @staticmethod
    def _vaccination_finding(value: float) -> dict:
        severity = "high" if value < 50 else "moderate" if value < 70 else "low"
        return {
            "kind": "vaccination",
            "severity": severity,
            "message": f"Taxa de vacinação observada: {value:.2f}%.",
        }

    @staticmethod
    def _risk_level(metrics: dict) -> str:
        score = 0
        if metrics.get("taxa_aumento_casos", 0.0) > 10:
            score += 2
        if metrics.get("taxa_mortalidade", 0.0) > 10:
            score += 2
        if metrics.get("taxa_ocupacao_uti", 0.0) > 30:
            score += 1
        if metrics.get("taxa_vacinacao", 0.0) < 50:
            score += 1

        if score >= 4:
            return "alto"
        if score >= 2:
            return "moderado"
        return "baixo"
