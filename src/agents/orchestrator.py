"""Coordenador para geração de relatórios de SRAG."""

from typing import Optional
import json
import logging
from datetime import datetime
from pathlib import Path

from tools.database_tool import create_database_tool
from tools.news_tool import create_news_tool
from tools.chart_tool import create_chart_tool
from utils.paths import REPORTS_DIR, ensure_directory, resolve_path

logger = logging.getLogger(__name__)


class SRAGReportOrchestrator:
    """Orquestrador para geração de relatórios de SRAG."""

    def __init__(self, output_dir: Optional[str | Path] = None):
        """Inicializa o orquestrador."""
        self.database_tool = create_database_tool()
        self.news_tool = create_news_tool()
        self.chart_tool = create_chart_tool()

        # ID de execução
        self.execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = resolve_path(output_dir) if output_dir is not None else REPORTS_DIR
        self.last_run: Optional[dict] = None

        logger.info("Orquestrador inicializado para geração de relatório")
    
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
    
    def generate_charts(
        self,
        daily_data: dict,
        monthly_data: dict,
        output_dir: Optional[Path] = None
    ) -> dict:
        """Gera gráficos de visualização."""
        logger.info("Gerando gráficos de visualização")
        
        charts = {}
        output_location = ensure_directory(output_dir or self.output_dir)
        
        # Gráfico diário
        if 'daily_cases' in daily_data:
            daily_result = self.chart_tool._run(
                chart_type="daily",
                data=json.dumps(daily_data['daily_cases']),
                output_path=str(output_location)
            )
            charts['daily'] = daily_result
        
        # Gráfico mensal
        if 'monthly_cases' in monthly_data:
            monthly_result = self.chart_tool._run(
                chart_type="monthly",
                data=json.dumps(monthly_data['monthly_cases']),
                output_path=str(output_location)
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
    
    def run(self, output_dir: Optional[str | Path] = None) -> dict:
        """
        Executa o processo completo de geração de relatório.
        
        Returns:
            Dicionário com o relatório gerado e dados auxiliares
        """
        logger.info(f"Iniciando geração de relatório - ID: {self.execution_id}")
        
        try:
            # 1. Coletar métricas
            metrics = self.collect_metrics()
            
            # 2. Coletar dados para gráficos
            daily_cases = self.collect_daily_cases(days=30)
            monthly_cases = self.collect_monthly_cases(months=12)
            
            # 3. Coletar notícias
            news = self.collect_news(max_results=5)
            
            # 4. Gerar gráficos
            report_directory = ensure_directory(output_dir or self.output_dir)

            charts = self.generate_charts(daily_cases, monthly_cases, report_directory)

            # 5. Gerar relatório
            report = self.generate_report(metrics, news, charts)

            # 6. Salvar relatório
            report_path = report_directory / f"relatorio_{self.execution_id}.md"
            report_path.write_text(report, encoding='utf-8')

            logger.info(f"Relatório salvo em: {report_path}")

            self.last_run = {
                "report": report,
                "metrics": metrics,
                "daily_cases": daily_cases,
                "monthly_cases": monthly_cases,
                "news": news,
                "charts": charts,
                "report_path": str(report_path),
            }

            return self.last_run
            
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}")
            raise


if __name__ == "__main__":
    # Teste do orquestrador
    orchestrator = SRAGReportOrchestrator()
    result = orchestrator.run()

    print("\n" + "="*80)
    print("RELATÓRIO GERADO")
    print("="*80)
    print(result["report"][:500] + "...")
