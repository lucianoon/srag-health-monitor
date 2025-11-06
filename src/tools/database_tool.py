"""
Ferramenta de consulta ao banco de dados para o agente de IA.

Esta ferramenta permite que o agente consulte métricas e dados do banco de SRAG.
"""

from langchain.tools import BaseTool
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import sys
import os

# Adicionar path do projeto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import SRAGDatabase


class DatabaseQueryInput(BaseModel):
    """Input para a ferramenta de consulta ao banco de dados."""
    query_type: str = Field(
        description="Tipo de consulta: 'metrics' para métricas principais, "
                    "'daily_cases' para casos diários, 'monthly_cases' para casos mensais"
    )
    days: Optional[int] = Field(
        default=30,
        description="Número de dias para consultas temporais (padrão: 30)"
    )
    months: Optional[int] = Field(
        default=12,
        description="Número de meses para consultas mensais (padrão: 12)"
    )


class DatabaseQueryTool(BaseTool):
    """Ferramenta para consultar o banco de dados de SRAG."""
    
    name: str = "database_query"
    description: str = (
        "Consulta o banco de dados de SRAG para obter métricas e dados. "
        "Use 'metrics' para obter todas as métricas principais (taxa de aumento de casos, "
        "taxa de mortalidade, taxa de ocupação de UTI, taxa de vacinação). "
        "Use 'daily_cases' para obter casos diários dos últimos N dias. "
        "Use 'monthly_cases' para obter casos mensais dos últimos N meses."
    )
    args_schema: type[BaseModel] = DatabaseQueryInput
    db_path: str = "/home/ubuntu/srag-health-monitor/data/srag.db"
    
    def _run(self, query_type: str, days: int = 30, months: int = 12) -> Dict[str, Any]:
        """
        Executa a consulta ao banco de dados.
        
        Args:
            query_type: Tipo de consulta
            days: Número de dias para consultas temporais
            months: Número de meses para consultas mensais
            
        Returns:
            Dicionário com os resultados da consulta
        """
        db = SRAGDatabase(self.db_path)
        db.connect()
        
        try:
            if query_type == "metrics":
                result = db.get_all_metrics()
                
            elif query_type == "daily_cases":
                cases = db.get_daily_cases(last_n_days=days)
                result = {
                    "daily_cases": [
                        {"date": date, "cases": count} 
                        for date, count in cases
                    ]
                }
                
            elif query_type == "monthly_cases":
                cases = db.get_monthly_cases(last_n_months=months)
                result = {
                    "monthly_cases": [
                        {"month": month, "cases": count} 
                        for month, count in cases
                    ]
                }
                
            else:
                result = {"error": f"Tipo de consulta inválido: {query_type}"}
                
        finally:
            db.close()
        
        return result
    
    async def _arun(self, query_type: str, days: int = 30, months: int = 12) -> Dict[str, Any]:
        """Versão assíncrona (não implementada)."""
        raise NotImplementedError("Versão assíncrona não implementada")


# Função auxiliar para criar a ferramenta
def create_database_tool() -> DatabaseQueryTool:
    """Cria e retorna uma instância da ferramenta de banco de dados."""
    return DatabaseQueryTool()


if __name__ == "__main__":
    # Teste da ferramenta
    tool = create_database_tool()
    
    print("\n=== Teste: Consulta de Métricas ===")
    result = tool._run(query_type="metrics")
    print(result)
    
    print("\n=== Teste: Casos Diários (últimos 7 dias) ===")
    result = tool._run(query_type="daily_cases", days=7)
    print(result)
    
    print("\n=== Teste: Casos Mensais (últimos 3 meses) ===")
    result = tool._run(query_type="monthly_cases", months=3)
    print(result)
