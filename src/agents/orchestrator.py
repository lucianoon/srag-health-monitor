from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import operator
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# Adicionar path do projeto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.database_tool import create_database_tool
from tools.news_tool import create_news_tool
from tools.chart_tool import create_chart_tool

# Import config central (novo)
try:
    from config import REPORTS_DIR  # when running from src/
except Exception:
    from src.config import REPORTS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentState(TypedDict):
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
    def __init__(self, model_name: str = "gpt-4.1-mini"):
        self.model_name = model_name
        self.llm = ChatOpenAI(model=model_name, temperature=0.3)

        self.database_tool = create_database_tool()
        self.news_tool = create_news_tool()
        self.chart_tool = create_chart_tool()

        self.execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"Orquestrador inicializado com modelo {model_name}")

    def collect_metrics(self) -> dict:
        logger.info("Coletando métricas do banco de dados")
        result = self.database_tool._run(query_type="metrics")
        return result

    def collect_daily_cases(self, days: int = 30) -> dict:
        logger.info(f"Coletando casos diários (últimos {days} dias)")
        result = self.database_tool._run(query_type="daily_cases", days=days)
        return result

    def collect_monthly_cases(self, months: int = 12) -> dict:
        logger.info(f"Coletando casos mensais (últimos {months} meses)")
        result = self.database_tool._run(query_type="monthly_cases", months=months)
        return result

    def collect_news(self, max_results: int = 5) -> dict:
        logger.info("Coletando notícias recentes sobre SRAG")
        result = self.news_tool._run(max_results=max_results)
        return result

    def generate_charts(self, daily_data: dict, monthly_data: dict) -> dict:
        logger.info("Gerando gráficos de visualização")

        charts = {}

        if 'daily_cases' in daily_data:
            daily_result = self.chart_tool._run(
                chart_type="daily",
                data=json.dumps(daily_data['daily_cases'])
            )
            charts['daily'] = daily_result

        if 'monthly_cases' in monthly_data:
            monthly_result = self.chart_tool._run(
                chart_type="monthly",
                data=json.dumps(monthly_data['monthly_cases'])
            )
            charts['monthly'] = monthly_result

        return charts

    def generate_report(self, metrics: dict, news: dict, charts: dict) -> str:
        logger.info("Gerando relatório final")

        report = f"""# Relatório de Monitoramento de SRAG
## Síndrome Respiratória Aguda Grave - Brasil

**Data do Relatório:** {datetime.now().strftime("%d/%m/%Y %H:%M")}
**ID de Execução:** {self.execution_id}

---

## 1. Métricas Principais

... (restante do conteúdo do relatório segue como no original)
"""

        return report

    def run(self) -> str:
        logger.info(f"Iniciando geração de relatório - ID: {self.execution_id}")

        try:
            metrics = self.collect_metrics()

            daily_cases = self.collect_daily_cases(days=30)
            monthly_cases = self.collect_monthly_cases(months=12)

            news = self.collect_news(max_results=5)

            charts = self.generate_charts(daily_cases, monthly_cases)

            report = self.generate_report(metrics, news, charts)

            # Salvar relatório usando REPORTS_DIR do config
            report_dir = Path(REPORTS_DIR)
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"relatorio_{self.execution_id}.md"
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)

            logger.info(f"Relatório salvo em: {report_path}")

            return report

        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}")
            raise


if __name__ == "__main__":
    orchestrator = SRAGReportOrchestrator()
    report = orchestrator.run()

    print("\n" + "="*80)
    print("RELATÓRIO GERADO")
    print("="*80)
    print(report[:500] + "...")
