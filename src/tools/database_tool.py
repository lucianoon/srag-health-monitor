"""Ferramenta de consulta ao banco de dados de SRAG."""

from dataclasses import dataclass
from typing import Dict, Any, Optional

from database.db_manager import SRAGDatabase
from utils.paths import DEFAULT_DB_PATH, resolve_path
from .base import ToolBase


@dataclass
class DatabaseQueryInput:
    """Estrutura simples de entrada para documentação da ferramenta."""

    query_type: str
    days: int = 30
    months: int = 12


class DatabaseQueryTool(ToolBase):
    """Ferramenta para consultar o banco de dados de SRAG."""
    
    name: str = "database_query"
    description: str = (
        "Consulta o banco de dados de SRAG para obter métricas e dados. "
        "Use 'metrics' para obter todas as métricas principais (taxa de aumento de casos, "
        "taxa de mortalidade, taxa de ocupação de UTI, taxa de vacinação). "
        "Use 'daily_cases' para obter casos diários dos últimos N dias. "
        "Use 'monthly_cases' para obter casos mensais dos últimos N meses."
    )
    args_schema: type[DatabaseQueryInput] = DatabaseQueryInput

    def __init__(self, db_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        resolved = resolve_path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path = str(resolved)
    
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
        with SRAGDatabase(self.db_path) as db:
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

        return result
    
    async def _arun(self, query_type: str, days: int = 30, months: int = 12) -> Dict[str, Any]:
        """Versão assíncrona (não implementada)."""
        raise NotImplementedError("Versão assíncrona não implementada")


# Função auxiliar para criar a ferramenta
def create_database_tool(db_path: Optional[str] = None) -> DatabaseQueryTool:
    """Cria e retorna uma instância da ferramenta de banco de dados."""
    return DatabaseQueryTool(db_path=db_path)


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
