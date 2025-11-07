from langchain.tools import BaseTool
from typing import Dict, Any, List
from pydantic import BaseModel, Field
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChartGenerationInput(BaseModel):
    chart_type: str = Field(
        description="Tipo de gráfico: 'daily' para casos diários, 'monthly' para casos mensais"
    )
    data: str = Field(
        description="Dados em formato JSON string para o gráfico"
    )
    output_path: str = Field(
        default="/home/ubuntu/srag-health-monitor/outputs/reports/",
        description="Caminho para salvar o gráfico"
    )


class ChartGenerationTool(BaseTool):
    name: str = "chart_generation"
    description: str = (
        "Gera gráficos de visualização de dados de SRAG. "
        "Use 'daily' para gerar gráfico de casos diários (últimos 30 dias). "
        "Use 'monthly' para gerar gráfico de casos mensais (últimos 12 meses). "
        "Os dados devem ser fornecidos em formato JSON."
    )
    args_schema: type[BaseModel] = ChartGenerationInput

    def _generate_daily_chart(self, data: List[Dict], output_path: str) -> str:
        dates = [datetime.strptime(item['date'], '%Y-%m-%d') for item in data]
        cases = [item['cases'] for item in data]

        plt.figure(figsize=(12, 6))
        plt.plot(dates, cases, marker='o', linewidth=2, markersize=4, color='#2E86AB')

        plt.title('Casos Diários de SRAG - últimos 30 Dias', fontsize=16, fontweight='bold')
        plt.xlabel('Data', fontsize=12)
        plt.ylabel('Número de Casos', fontsize=12)

        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
        plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=5))
        plt.xticks(rotation=45)

        plt.grid(True, alpha=0.3, linestyle='--')
        plt.tight_layout()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(output_path, f'casos_diarios_{timestamp}.png')
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Gráfico diário salvo em: {filename}")
        return filename

    def _generate_monthly_chart(self, data: List[Dict], output_path: str) -> str:
        months = [item['month'] for item in data]
        cases = [item['cases'] for item in data]

        plt.figure(figsize=(12, 6))
        plt.bar(months, cases, color='#A23B72', alpha=0.8, edgecolor='black', linewidth=0.5)

        plt.title('Casos Mensais de SRAG - últimos 12 Meses', fontsize=16, fontweight='bold')
        plt.xlabel('Mês', fontsize=12)
        plt.ylabel('Número de Casos', fontsize=12)

        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3, linestyle='--', axis='y')
        plt.tight_layout()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(output_path, f'casos_mensais_{timestamp}.png')
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Gráfico mensal salvo em: {filename}")
        return filename

    def _run(self, chart_type: str, data: str,
             output_path: str = "/home/ubuntu/srag-health-monitor/outputs/reports/") -> Dict[str, Any]:
        import json

        logger.info(f"Gerando gráfico tipo: {chart_type}")

        try:
            data_obj = json.loads(data) if isinstance(data, str) else data

            os.makedirs(output_path, exist_ok=True)

            if chart_type == "daily":
                filename = self._generate_daily_chart(data_obj, output_path)
            elif chart_type == "monthly":
                filename = self._generate_monthly_chart(data_obj, output_path)
            else:
                return {"error": f"Tipo de gráfico inválido: {chart_type}"}

            return {
                "success": True,
                "chart_type": chart_type,
                "filename": filename,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Erro ao gerar gráfico: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _arun(self, chart_type: str, data: str, output_path: str = "") -> Dict[str, Any]:
        raise NotImplementedError("Versão assíncrona não implementada")


def create_chart_tool() -> ChartGenerationTool:
    return ChartGenerationTool()