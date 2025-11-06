"""
Ferramenta de busca de notícias sobre SRAG para o agente de IA.

Esta ferramenta permite que o agente busque notícias recentes sobre SRAG.
"""

from langchain.tools import BaseTool
from typing import Dict, Any, List
from pydantic import BaseModel, Field
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NewsSearchInput(BaseModel):
    """Input para a ferramenta de busca de notícias."""
    query: str = Field(
        default="SRAG síndrome respiratória aguda grave Brasil",
        description="Termo de busca para notícias (padrão: SRAG)"
    )
    max_results: int = Field(
        default=5,
        description="Número máximo de resultados (padrão: 5)"
    )


class NewsSearchTool(BaseTool):
    """Ferramenta para buscar notícias sobre SRAG."""
    
    name: str = "news_search"
    description: str = (
        "Busca notícias recentes sobre SRAG (Síndrome Respiratória Aguda Grave) "
        "e outros temas relacionados a saúde pública no Brasil. "
        "Retorna título, resumo, fonte e data das notícias encontradas."
    )
    args_schema: type[BaseModel] = NewsSearchInput
    
    def _search_google_news(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Busca notícias usando Google News (simulado).
        
        Args:
            query: Termo de busca
            max_results: Número máximo de resultados
            
        Returns:
            Lista de notícias encontradas
        """
        # Simulação de notícias (em produção, usar API real ou web scraping)
        # Para PoC, retornar notícias simuladas baseadas em contexto real
        
        news = [
            {
                "title": "Casos de SRAG aumentam em todo o Brasil durante inverno",
                "summary": "O Ministério da Saúde registrou aumento de 15% nos casos de Síndrome Respiratória Aguda Grave (SRAG) nas últimas semanas, especialmente nas regiões Sul e Sudeste. Autoridades recomendam vacinação e cuidados preventivos.",
                "source": "Ministério da Saúde",
                "date": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                "url": "https://www.gov.br/saude"
            },
            {
                "title": "Taxa de ocupação de UTIs por SRAG preocupa especialistas",
                "summary": "Especialistas alertam para o aumento da taxa de ocupação de leitos de UTI por pacientes com SRAG. A taxa atual está em torno de 28%, acima da média histórica. Hospitais reforçam protocolos de atendimento.",
                "source": "Fiocruz",
                "date": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                "url": "https://portal.fiocruz.br"
            },
            {
                "title": "Vacinação contra gripe e COVID-19 é reforçada em campanha nacional",
                "summary": "O governo federal lançou nova campanha de vacinação contra gripe e COVID-19, visando aumentar a cobertura vacinal e reduzir casos graves de SRAG. Meta é vacinar 90% da população prioritária.",
                "source": "Agência Brasil",
                "date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "url": "https://agenciabrasil.ebc.com.br"
            },
            {
                "title": "Mortalidade por SRAG mantém-se estável em 2024",
                "summary": "Dados do DATASUS mostram que a taxa de mortalidade por SRAG em 2024 está em 7,6%, similar ao ano anterior. Especialistas atribuem estabilidade ao aumento da vacinação e melhoria nos protocolos de tratamento.",
                "source": "DATASUS",
                "date": (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
                "url": "https://datasus.saude.gov.br"
            },
            {
                "title": "Vigilância epidemiológica intensifica monitoramento de vírus respiratórios",
                "summary": "A Secretaria de Vigilância em Saúde ampliou o monitoramento de vírus respiratórios em todo o país. Além de influenza e COVID-19, também são monitorados VSR, parainfluenza e outros patógenos.",
                "source": "SVS/MS",
                "date": (datetime.now() - timedelta(days=12)).strftime("%Y-%m-%d"),
                "url": "https://www.gov.br/saude/pt-br/composicao/svsa"
            }
        ]
        
        return news[:max_results]
    
    def _run(self, query: str = "SRAG síndrome respiratória aguda grave Brasil", 
             max_results: int = 5) -> Dict[str, Any]:
        """
        Executa a busca de notícias.
        
        Args:
            query: Termo de busca
            max_results: Número máximo de resultados
            
        Returns:
            Dicionário com as notícias encontradas
        """
        logger.info(f"Buscando notícias sobre: {query}")
        
        try:
            news = self._search_google_news(query, max_results)
            
            result = {
                "query": query,
                "total_results": len(news),
                "news": news,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"{len(news)} notícias encontradas")
            return result
            
        except Exception as e:
            logger.error(f"Erro ao buscar notícias: {e}")
            return {
                "error": str(e),
                "query": query,
                "news": []
            }
    
    async def _arun(self, query: str = "SRAG", max_results: int = 5) -> Dict[str, Any]:
        """Versão assíncrona (não implementada)."""
        raise NotImplementedError("Versão assíncrona não implementada")


def create_news_tool() -> NewsSearchTool:
    """Cria e retorna uma instância da ferramenta de notícias."""
    return NewsSearchTool()


if __name__ == "__main__":
    # Teste da ferramenta
    tool = create_news_tool()
    
    print("\n=== Teste: Busca de Notícias sobre SRAG ===")
    result = tool._run(max_results=3)
    
    print(f"\nQuery: {result['query']}")
    print(f"Total de resultados: {result['total_results']}\n")
    
    for i, news_item in enumerate(result['news'], 1):
        print(f"{i}. {news_item['title']}")
        print(f"   Fonte: {news_item['source']} | Data: {news_item['date']}")
        print(f"   {news_item['summary'][:100]}...")
        print()
