"""
Ferramenta de geração de gráficos para o agente de IA.

Esta ferramenta permite que o agente gere gráficos de visualização de dados.
"""

from langchain.tools import BaseTool
from typing import Dict, Any, List
from pydantic import BaseModel, Field
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from pathlib import Path
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChartGenerationInput(BaseModel):
    """Input para a ferramenta de geração de gráficos."""
    chart_type: str = Field(
        description="Tipo de gráfico: 'daily' para casos diários, 'monthly' para casos mensais"
    )
    data: str = Field(
        description="Dados em formato JSON string para o gráfico"
    )
    output_path: str = Field(
        default=str(Path(os.getenv("SRAG_OUTPUT_DIR", Path.cwd() / "outputs" / "reports"))),
        description="Caminho para salvar o gráfico"
    )


class ChartGenerationTool(BaseTool):
    """Ferramenta para gerar gráficos de visualização."""

    name: str = "chart_generation"
    description: str = (
        "Gera gráficos de visualização de dados de SRAG. "
        "Use 'daily' para gerar gráfico de casos diários (últimos 30 dias). "
        "Use 'monthly' para gerar gráfico de casos mensais (últimos 12 meses). "
        "Os dados devem ser fornecidos em formato JSON."
    )
    args_schema: type[BaseModel] = ChartGenerationInput

    def _generate_daily_chart(self, data: List[Dict], output_path: str) -> str:
        """
        Gera gráfico de casos diários.

        Args:
            data: Lista de dicionários com 'date' e 'cases'
            output_path: Caminho para salvar o gráfico

        Returns:
            Caminho do arquivo gerado
        """
        dates = [datetime.strptime(item['date'], '%Y-%m-%d') for item in data]
        cases = [item['cases'] for item in data]

        plt.figure(figsize=(12, 6))
        plt.plot(dates, cases, marker='o', linewidth=2, markersize=4, color='#2E86AB')

        plt.title('Casos Diários de SRAG - Últimos 30 Dias', fontsize=16, fontweight='bold')
        plt.xlabel('Data', fontsize=12)
        plt.ylabel('Número de Casos', fontsize=12)

        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
        plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=5))
        plt.xticks(rotation=45)

        plt.grid(True, alpha=0.3, linestyle='--')
        plt.tight_layout()

        filename = os.path.join(output_path, 'casos_diarios.png')
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Gráfico diário salvo em: {filename}")
        return filename

    def _generate_monthly_chart(self, data: List[Dict], output_path: str) -> str:
        """
        Gera gráfico de casos mensais.

        Args:
            data: Lista de dicionários com 'month' e 'cases'
            output_path: Caminho para salvar o gráfico

        Returns:
            Caminho do arquivo gerado
        """
        months = [item['month'] for item in data]
        cases = [item['cases'] for item in data]

        plt.figure(figsize=(12, 6))
        plt.bar(months, cases, color='#A23B72', alpha=0.8, edgecolor='black', linewidth=0.5)

        plt.title('Casos Mensais de SRAG - Últimos 12 Meses', fontsize=16, fontweight='bold')
        plt.xlabel('Mês', fontsize=12)
        plt.ylabel('Número de Casos', fontsize=12)

        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3, linestyle='--', axis='y')
        plt.tight_layout()

        filename = os.path.join(output_path, 'casos_mensais.png')
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Gráfico mensal salvo em: {filename}")
        return filename

    def _run(self, chart_type: str, data: str,
             output_path: str | None = None) -> Dict[str, Any]:
        """
        Executa a geração de gráfico.

        Args:
            chart_type: Tipo de gráfico
            data: Dados em formato JSON string
            output_path: Caminho para salvar

        Returns:
            Dicionário com informações do gráfico gerado
        """
        import json

        logger.info(f"Gerando gráfico tipo: {chart_type}")

        try:
            # Converter JSON string para objeto
            data_obj = json.loads(data) if isinstance(data, str) else data

            if output_path is None:
                output_path = str(Path(os.getenv("SRAG_OUTPUT_DIR", Path.cwd() / "outputs" / "reports")))

            # Criar diretório se não existir
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
        """Versão assíncrona (não implementada)."""
        raise NotImplementedError("Versão assíncrona não implementada")


def create_chart_tool() -> ChartGenerationTool:
    """Cria e retorna uma instância da ferramenta de gráficos."""
    return ChartGenerationTool()


if __name__ == "__main__":
    import json

    # Teste da ferramenta
    tool = create_chart_tool()

    # Dados de teste para gráfico diário
    daily_data = [
        {"date": "2024-12-24", "cases": 298},
        {"date": "2024-12-25", "cases": 209},
        {"date": "2024-12-26", "cases": 719},
        {"date": "2024-12-27", "cases": 614},
        {"date": "2024-12-28", "cases": 261},
        {"date": "2024-12-29", "cases": 202},
        {"date": "2024-12-30", "cases": 697},
    ]

    # Dados de teste para gráfico mensal
    monthly_data = [
        {"month": "2024-10", "cases": 19915},
        {"month": "2024-11", "cases": 17564},
        {"month": "2024-12", "cases": 16920}
    ]

    print("\n=== Teste: Gráfico Diário ===")
    result = tool._run(chart_type="daily", data=json.dumps(daily_data))
    print(result)

    print("\n=== Teste: Gráfico Mensal ===")
    result = tool._run(chart_type="monthly", data=json.dumps(monthly_data))
    print(result)
