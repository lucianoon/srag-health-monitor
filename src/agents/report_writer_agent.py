"""Agente de escrita de relatórios epidemiológicos."""

from datetime import datetime
import json
import logging

from agents.epidemiology_analysis_agent import EpidemiologyAnalysis
from config import AppConfig
from tools.chart_tool import create_chart_tool


logger = logging.getLogger(__name__)


class ReportWriterAgent:
    """Gera gráficos e relatório final em Markdown."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.chart_tool = create_chart_tool()

    def generate_charts(self, analysis: EpidemiologyAnalysis) -> dict:
        logger.info("Agente de relatório gerando gráficos")
        charts = {}

        if "daily_cases" in analysis.daily_cases:
            charts["daily"] = self.chart_tool._run(
                chart_type="daily",
                data=json.dumps(analysis.daily_cases["daily_cases"]),
                output_path=str(self.config.reports_dir),
            )

        if "monthly_cases" in analysis.monthly_cases:
            charts["monthly"] = self.chart_tool._run(
                chart_type="monthly",
                data=json.dumps(analysis.monthly_cases["monthly_cases"]),
                output_path=str(self.config.reports_dir),
            )

        for chart_name, chart_result in charts.items():
            if chart_result.get("error"):
                raise RuntimeError(f"Falha ao gerar gráfico {chart_name}: {chart_result['error']}")

        return charts

    def write(
        self,
        analysis: EpidemiologyAnalysis,
        charts: dict,
        execution_id: str,
    ) -> str:
        logger.info("Agente de relatório escrevendo narrativa final")
        metrics = analysis.metrics
        news = analysis.news

        report = f"""# Relatório de Monitoramento de SRAG
## Síndrome Respiratória Aguda Grave - Brasil

**Data do Relatório:** {datetime.now().strftime("%d/%m/%Y %H:%M")}
**ID de Execução:** {execution_id}
**Nível de Risco:** {analysis.risk_level.upper()}

---

## 1. Métricas Principais

### 1.1 Taxa de Aumento de Casos
**{metrics.get('taxa_aumento_casos', 0):.2f}%** nos últimos 30 dias em relação ao período anterior.

### 1.2 Taxa de Mortalidade
**{metrics.get('taxa_mortalidade', 0):.2f}%** dos casos registrados resultaram em óbito.

### 1.3 Taxa de Ocupação de UTI
**{metrics.get('taxa_ocupacao_uti', 0):.2f}%** dos casos necessitaram de internação em UTI.

### 1.4 Taxa de Vacinação
**{metrics.get('taxa_vacinacao', 0):.2f}%** dos pacientes registrados possuíam vacinação prévia.

---

## 2. Análise Contextual

### 2.1 Cenário Atual

Com base nos dados mais recentes do DATASUS, foram registrados **{metrics.get('total_casos', 0):,}** casos de SRAG.
"""

        report += self._growth_text(metrics.get("taxa_aumento_casos", 0))
        report += "\n### 2.2 Achados Epidemiológicos\n\n"
        for finding in analysis.findings:
            report += f"- **{finding['severity'].capitalize()}**: {finding['message']}\n"

        report += "\n### 2.3 Notícias Recentes\n\n"
        if news.get("news"):
            for index, news_item in enumerate(news["news"], 1):
                report += f"**{index}. {news_item['title']}**  \n"
                report += f"*{news_item['source']} - {news_item['date']}*  \n"
                report += f"{news_item['summary']}\n\n"
        else:
            report += "Nenhuma notícia recente disponível.\n\n"

        report += "---\n\n## 3. Visualizações\n\n"
        if charts.get("daily", {}).get("success"):
            report += "### 3.1 Casos Diários (Últimos 30 Dias)\n\n"
            report += f"![Casos Diários]({charts['daily']['filename']})\n\n"

        if charts.get("monthly", {}).get("success"):
            report += "### 3.2 Casos Mensais (Últimos 12 Meses)\n\n"
            report += f"![Casos Mensais]({charts['monthly']['filename']})\n\n"

        report += "---\n\n## 4. Conclusões e Recomendações\n\n"
        report += self._recommendations(metrics)
        report += "\n---\n\n## 5. Fonte e Rastreabilidade\n\n"
        report += f"- Fonte: {analysis.source.get('provider', 'DATASUS/SIVEP-Gripe')}\n"
        report += f"- Tipo de fonte: {analysis.source.get('source_type', 'não informado')}\n"
        report += f"- Última atualização local: {analysis.source.get('updated_at') or 'não informada'}\n"

        report += "\n---\n\n"
        report += "**Relatório gerado automaticamente pelo Sistema de Monitoramento de SRAG**  \n"
        report += "*Fonte de dados: DATASUS/SIVEP-Gripe*  \n"
        report += f"*Data de geração: {datetime.now().strftime('%d/%m/%Y às %H:%M')}*\n"

        return report

    @staticmethod
    def _growth_text(taxa_crescimento: float) -> str:
        if taxa_crescimento > 0:
            return (
                f"\nObserva-se uma **tendência de crescimento** de "
                f"{taxa_crescimento:.2f}% nos casos, indicando necessidade "
                "de atenção reforçada às medidas preventivas.\n"
            )
        if taxa_crescimento < 0:
            return (
                f"\nObserva-se uma **tendência de redução** de "
                f"{abs(taxa_crescimento):.2f}% nos casos, sinalizando "
                "possível controle da situação epidemiológica.\n"
            )
        return "\nOs casos mantêm-se **estáveis** em relação ao período anterior.\n"

    @staticmethod
    def _recommendations(metrics: dict) -> str:
        recommendations = []

        if metrics.get("taxa_mortalidade", 0) > 10:
            recommendations.append(
                "- A taxa de mortalidade está **acima da média histórica**, "
                "exigindo revisão dos protocolos de atendimento."
            )
        elif metrics.get("taxa_mortalidade", 0) < 5:
            recommendations.append(
                "- A taxa de mortalidade está **abaixo da média histórica**, "
                "indicando eficácia dos protocolos de tratamento."
            )
        else:
            recommendations.append(
                "- A taxa de mortalidade está **dentro da faixa esperada** para SRAG."
            )

        if metrics.get("taxa_ocupacao_uti", 0) > 30:
            recommendations.append(
                "- A taxa de ocupação de UTI está **elevada**, recomenda-se "
                "monitoramento da capacidade hospitalar."
            )
        else:
            recommendations.append("- A taxa de ocupação de UTI está **controlada**.")

        if metrics.get("taxa_vacinacao", 0) < 60:
            recommendations.append(
                "- A taxa de vacinação está **abaixo do ideal**, recomenda-se "
                "intensificar campanhas de imunização."
            )
        else:
            recommendations.append(
                "- A taxa de vacinação está **satisfatória**, contribuindo para "
                "o controle de casos graves."
            )

        return "\n".join(recommendations) + "\n"
