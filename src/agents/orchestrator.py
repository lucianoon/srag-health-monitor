"""
Agente Orquestrador para geração de relatórios de SRAG.

Este agente coordena as ferramentas disponíveis para gerar relatórios
automatizados sobre a situação de SRAG no Brasil.
"""

from tools.chart_tool import create_chart_tool
from tools.news_tool import create_news_tool
from tools.database_tool import create_database_tool
from config import AppConfig
from typing import Optional, TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
import operator
import os
import sys
import json
import logging
from datetime import datetime

# Adicionar path do projeto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """Estado do agente durante a execução."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    metrics: dict
    daily_cases: dict
    monthly_cases: dict
    news: dict
    charts: dict
    report: str
    execution_id: str
    timestamp: str


class SRAGReportOrchestrator:
    """Orquestrador para geração de relatórios de SRAG."""

    def __init__(self, model_name: Optional[str] = None, config: Optional[AppConfig] = None):
        """
        Inicializa o orquestrador.

        Args:
            model_name: Nome do modelo LLM a usar
        """
        self.config = config or AppConfig.from_env(model_name=model_name)
        self.config.ensure_runtime_dirs()
        self.model_name = self.config.model_name
        self.llm = (
            ChatOpenAI(model=self.model_name, temperature=0.3)
            if self.config.openai_api_key
            else None
        )

        # Criar ferramentas
        self.database_tool = create_database_tool(db_path=str(self.config.db_path))
        self.news_tool = create_news_tool(feeds=self.config.news_feeds)
        self.chart_tool = create_chart_tool()

        # ID de execução
        self.execution_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.last_metrics = {}
        self.last_daily_cases = {}
        self.last_monthly_cases = {}
        self.last_news = {}
        self.last_charts = {}
        self.report_path = self.config.reports_dir / f"relatorio_{self.execution_id}.md"

        logger.info(f"Orquestrador inicializado com modelo {self.model_name}")

    def collect_metrics(self) -> dict:
        """Coleta métricas do banco de dados."""
        logger.info("Coletando métricas do banco de dados")
        result = self.database_tool._run(query_type="metrics")
        return result

    def collect_daily_cases(self, days: int = 30) -> dict:
        """Coleta casos diários."""
        logger.info(f"Coletando casos diários (últimos {days} dias)")
        result = self.database_tool._run(query_type="daily_cases", days=days)
        return result

    def collect_monthly_cases(self, months: int = 12) -> dict:
        """Coleta casos mensais."""
        logger.info(f"Coletando casos mensais (últimos {months} meses)")
        result = self.database_tool._run(query_type="monthly_cases", months=months)
        return result

    def collect_news(self, max_results: int = 5) -> dict:
        """Coleta notícias recentes."""
        logger.info("Coletando notícias recentes sobre SRAG")
        result = self.news_tool._run(max_results=max_results)
        return result

    @staticmethod
    def _raise_if_tool_error(result: dict, context: str) -> None:
        """Interrompe a execução quando uma ferramenta reporta erro."""
        if result.get("error"):
            raise RuntimeError(f"{context}: {result['error']}")

    def generate_charts(self, daily_data: dict, monthly_data: dict) -> dict:
        """Gera gráficos de visualização."""
        logger.info("Gerando gráficos de visualização")

        charts = {}

        # Gráfico diário
        if 'daily_cases' in daily_data:
            daily_result = self.chart_tool._run(
                chart_type="daily",
                data=json.dumps(daily_data['daily_cases']),
                output_path=str(self.config.reports_dir)
            )
            charts['daily'] = daily_result

        # Gráfico mensal
        if 'monthly_cases' in monthly_data:
            monthly_result = self.chart_tool._run(
                chart_type="monthly",
                data=json.dumps(monthly_data['monthly_cases']),
                output_path=str(self.config.reports_dir)
            )
            charts['monthly'] = monthly_result

        return charts

    def generate_report(self, metrics: dict, news: dict, charts: dict) -> str:
        """
        Gera o relatório final em Markdown.

        Args:
            metrics: Métricas coletadas
            news: Notícias coletadas
            charts: Informações dos gráficos gerados

        Returns:
            Relatório em formato Markdown
        """
        logger.info("Gerando relatório final")

        report = f"""# Relatório de Monitoramento de SRAG
## Síndrome Respiratória Aguda Grave - Brasil

**Data do Relatório:** {datetime.now().strftime("%d/%m/%Y %H:%M")}
**ID de Execução:** {self.execution_id}

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

Com base nos dados mais recentes do DATASUS, foram registrados **{metrics.get('total_casos', 0):,}** casos de SRAG em 2024.
"""

        # Adicionar análise da taxa de crescimento
        taxa_crescimento = metrics.get('taxa_aumento_casos', 0)
        if taxa_crescimento > 0:
            report += f"\nObserva-se uma **tendência de crescimento** de {taxa_crescimento:.2f}% nos casos, indicando necessidade de atenção reforçada às medidas preventivas.\n"
        elif taxa_crescimento < 0:
            report += f"\nObserva-se uma **tendência de redução** de {abs(taxa_crescimento):.2f}% nos casos, sinalizando possível controle da situação epidemiológica.\n"
        else:
            report += "\nOs casos mantêm-se **estáveis** em relação ao período anterior.\n"

        # Adicionar notícias
        report += "\n### 2.2 Notícias Recentes\n\n"

        if news.get('news'):
            for i, news_item in enumerate(news['news'], 1):
                report += f"**{i}. {news_item['title']}**  \n"
                report += f"*{news_item['source']} - {news_item['date']}*  \n"
                report += f"{news_item['summary']}\n\n"
        else:
            report += "Nenhuma notícia recente disponível.\n\n"

        # Adicionar referências aos gráficos
        report += "---\n\n## 3. Visualizações\n\n"

        if charts.get('daily', {}).get('success'):
            report += "### 3.1 Casos Diários (Últimos 30 Dias)\n\n"
            report += f"![Casos Diários]({charts['daily']['filename']})\n\n"

        if charts.get('monthly', {}).get('success'):
            report += "### 3.2 Casos Mensais (Últimos 12 Meses)\n\n"
            report += f"![Casos Mensais]({charts['monthly']['filename']})\n\n"

        # Adicionar conclusão
        report += "---\n\n## 4. Conclusões e Recomendações\n\n"

        # Análise da mortalidade
        taxa_mort = metrics.get('taxa_mortalidade', 0)
        if taxa_mort > 10:
            report += "- A taxa de mortalidade está **acima da média histórica**, exigindo revisão dos protocolos de atendimento.\n"
        elif taxa_mort < 5:
            report += "- A taxa de mortalidade está **abaixo da média histórica**, indicando eficácia dos protocolos de tratamento.\n"
        else:
            report += "- A taxa de mortalidade está **dentro da faixa esperada** para SRAG.\n"

        # Análise da UTI
        taxa_uti = metrics.get('taxa_ocupacao_uti', 0)
        if taxa_uti > 30:
            report += "- A taxa de ocupação de UTI está **elevada**, recomenda-se monitoramento da capacidade hospitalar.\n"
        else:
            report += "- A taxa de ocupação de UTI está **controlada**.\n"

        # Análise da vacinação
        taxa_vac = metrics.get('taxa_vacinacao', 0)
        if taxa_vac < 60:
            report += "- A taxa de vacinação está **abaixo do ideal**, recomenda-se intensificar campanhas de imunização.\n"
        else:
            report += "- A taxa de vacinação está **satisfatória**, contribuindo para o controle de casos graves.\n"

        report += "\n---\n\n"
        report += f"**Relatório gerado automaticamente pelo Sistema de Monitoramento de SRAG**  \n"
        report += f"*Fonte de dados: DATASUS/SIVEP-Gripe*  \n"
        report += f"*Data de geração: {datetime.now().strftime('%d/%m/%Y às %H:%M')}*\n"

        return report

    def run(self) -> str:
        """
        Executa o processo completo de geração de relatório.

        Returns:
            Relatório em formato Markdown
        """
        logger.info(f"Iniciando geração de relatório - ID: {self.execution_id}")

        try:
            # 1. Coletar métricas
            metrics = self.collect_metrics()
            self._raise_if_tool_error(metrics, "Falha ao coletar métricas")
            self.last_metrics = metrics

            # 2. Coletar dados para gráficos
            daily_cases = self.collect_daily_cases(days=30)
            self._raise_if_tool_error(daily_cases, "Falha ao coletar casos diários")
            self.last_daily_cases = daily_cases
            monthly_cases = self.collect_monthly_cases(months=12)
            self._raise_if_tool_error(monthly_cases, "Falha ao coletar casos mensais")
            self.last_monthly_cases = monthly_cases

            # 3. Coletar notícias
            news = self.collect_news(max_results=5)
            self._raise_if_tool_error(news, "Falha ao coletar notícias")
            self.last_news = news

            # 4. Gerar gráficos
            charts = self.generate_charts(daily_cases, monthly_cases)
            for chart_name, chart_result in charts.items():
                self._raise_if_tool_error(chart_result, f"Falha ao gerar gráfico {chart_name}")
            self.last_charts = charts

            # 5. Gerar relatório
            report = self.generate_report(metrics, news, charts)

            # 6. Salvar relatório
            with open(self.report_path, 'w', encoding='utf-8') as f:
                f.write(report)

            logger.info(f"Relatório salvo em: {self.report_path}")

            return report

        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}")
            raise


if __name__ == "__main__":
    # Teste do orquestrador
    orchestrator = SRAGReportOrchestrator()
    report = orchestrator.run()

    print("\n" + "=" * 80)
    print("RELATÓRIO GERADO")
    print("=" * 80)
    print(report[:500] + "...")
