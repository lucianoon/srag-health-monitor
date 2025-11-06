"""
Módulo para processamento e limpeza de dados de SRAG do DATASUS.

Este módulo é responsável por:
- Carregar dados brutos do CSV
- Selecionar colunas relevantes
- Tratar valores ausentes
- Transformar dados para análise
- Gerar estatísticas descritivas
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SRAGDataProcessor:
    """Processador de dados de SRAG do DATASUS."""
    
    # Colunas relevantes para o projeto
    RELEVANT_COLUMNS = [
        'DT_NOTIFIC',    # Data de notificação
        'DT_SIN_PRI',    # Data dos primeiros sintomas
        'SG_UF',         # UF de residência
        'CO_MUN_RES',    # Código do município de residência
        'CS_SEXO',       # Sexo
        'NU_IDADE_N',    # Idade
        'TP_IDADE',      # Tipo de idade (anos, meses, dias)
        'EVOLUCAO',      # Evolução do caso (1=Cura, 2=Óbito, 3=Óbito por outras causas)
        'UTI',           # Internação em UTI (1=Sim, 2=Não)
        'DT_ENTUTI',     # Data de entrada na UTI
        'DT_SAIDUTI',    # Data de saída da UTI
        'VACINA',        # Vacinação para gripe (1=Sim, 2=Não)
        'VACINA_COV',    # Vacinação para COVID (1=Sim, 2=Não)
        'DOSE_1_COV',    # Data da 1ª dose COVID
        'DOSE_2_COV',    # Data da 2ª dose COVID
        'DOSE_REF',      # Data da dose de reforço
        'CLASSI_FIN',    # Classificação final
        'DT_EVOLUCA',    # Data da evolução
        'DT_INTERNA',    # Data de internação
        'HOSPITAL',      # Hospitalização (1=Sim, 2=Não)
        'FEBRE',         # Sintoma: febre
        'TOSSE',         # Sintoma: tosse
        'DISPNEIA',      # Sintoma: dispneia
        'SATURACAO',     # Saturação O2 < 95%
    ]
    
    def __init__(self, raw_data_path: str):
        """
        Inicializa o processador de dados.
        
        Args:
            raw_data_path: Caminho para o arquivo CSV bruto
        """
        self.raw_data_path = raw_data_path
        self.df = None
        self.df_processed = None
        
    def load_data(self, nrows: int = None) -> pd.DataFrame:
        """
        Carrega dados do CSV.
        
        Args:
            nrows: Número de linhas a carregar (None para todas)
            
        Returns:
            DataFrame com os dados carregados
        """
        logger.info(f"Carregando dados de {self.raw_data_path}")
        
        try:
            self.df = pd.read_csv(
                self.raw_data_path,
                sep=';',
                encoding='latin1',
                usecols=self.RELEVANT_COLUMNS,
                nrows=nrows,
                low_memory=False
            )
            logger.info(f"Dados carregados: {len(self.df)} linhas, {len(self.df.columns)} colunas")
            return self.df
        except Exception as e:
            logger.error(f"Erro ao carregar dados: {e}")
            raise
    
    def clean_data(self) -> pd.DataFrame:
        """
        Limpa e trata os dados.
        
        Returns:
            DataFrame processado
        """
        logger.info("Iniciando limpeza de dados")
        
        if self.df is None:
            raise ValueError("Dados não carregados. Execute load_data() primeiro.")
        
        df = self.df.copy()
        
        # Converter datas
        date_columns = ['DT_NOTIFIC', 'DT_SIN_PRI', 'DT_EVOLUCA', 'DT_INTERNA', 
                       'DT_ENTUTI', 'DT_SAIDUTI', 'DOSE_1_COV', 'DOSE_2_COV', 'DOSE_REF']
        
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], format='%Y-%m-%d', errors='coerce')
        
        # Calcular idade em anos
        df['IDADE_ANOS'] = df.apply(self._calculate_age_years, axis=1)
        
        # Criar flag de óbito (1=Óbito, 0=Não óbito)
        df['OBITO'] = (df['EVOLUCAO'] == 2).astype(int)
        
        # Criar flag de internação em UTI
        df['INTERNOU_UTI'] = (df['UTI'] == 1).astype(int)
        
        # Criar flag de vacinação (gripe ou COVID)
        df['VACINADO'] = ((df['VACINA'] == 1) | (df['VACINA_COV'] == 1)).astype(int)
        
        # Criar flag de hospitalização
        df['HOSPITALIZADO'] = (df['HOSPITAL'] == 1).astype(int)
        
        # Remover registros sem data de notificação
        df = df.dropna(subset=['DT_NOTIFIC'])
        
        # Filtrar apenas registros de 2024
        df = df[df['DT_NOTIFIC'].dt.year == 2024]
        
        logger.info(f"Dados limpos: {len(df)} linhas após limpeza")
        
        self.df_processed = df
        return df
    
    @staticmethod
    def _calculate_age_years(row) -> float:
        """Calcula idade em anos baseado em NU_IDADE_N e TP_IDADE."""
        idade = row['NU_IDADE_N']
        tipo = row['TP_IDADE']
        
        if pd.isna(idade) or pd.isna(tipo):
            return np.nan
        
        # 1=Horas, 2=Dias, 3=Meses, 4=Anos
        if tipo == 4:
            return float(idade)
        elif tipo == 3:
            return float(idade) / 12
        elif tipo == 2:
            return float(idade) / 365
        elif tipo == 1:
            return float(idade) / (365 * 24)
        else:
            return np.nan
    
    def get_statistics(self) -> Dict:
        """
        Gera estatísticas descritivas dos dados.
        
        Returns:
            Dicionário com estatísticas
        """
        if self.df_processed is None:
            raise ValueError("Dados não processados. Execute clean_data() primeiro.")
        
        df = self.df_processed
        
        stats = {
            'total_casos': len(df),
            'total_obitos': df['OBITO'].sum(),
            'total_uti': df['INTERNOU_UTI'].sum(),
            'total_vacinados': df['VACINADO'].sum(),
            'taxa_mortalidade': (df['OBITO'].sum() / len(df)) * 100 if len(df) > 0 else 0,
            'taxa_uti': (df['INTERNOU_UTI'].sum() / len(df)) * 100 if len(df) > 0 else 0,
            'taxa_vacinacao': (df['VACINADO'].sum() / len(df)) * 100 if len(df) > 0 else 0,
            'idade_media': df['IDADE_ANOS'].mean(),
            'idade_mediana': df['IDADE_ANOS'].median(),
            'data_inicio': df['DT_NOTIFIC'].min(),
            'data_fim': df['DT_NOTIFIC'].max(),
        }
        
        return stats
    
    def get_daily_cases(self, last_n_days: int = 30) -> pd.DataFrame:
        """
        Retorna casos diários dos últimos N dias.
        
        Args:
            last_n_days: Número de dias a considerar
            
        Returns:
            DataFrame com data e número de casos
        """
        if self.df_processed is None:
            raise ValueError("Dados não processados. Execute clean_data() primeiro.")
        
        df = self.df_processed
        
        # Data de corte
        max_date = df['DT_NOTIFIC'].max()
        cutoff_date = max_date - timedelta(days=last_n_days)
        
        # Filtrar últimos N dias
        df_recent = df[df['DT_NOTIFIC'] >= cutoff_date]
        
        # Agrupar por data
        daily = df_recent.groupby('DT_NOTIFIC').size().reset_index(name='casos')
        daily = daily.sort_values('DT_NOTIFIC')
        
        return daily
    
    def get_monthly_cases(self, last_n_months: int = 12) -> pd.DataFrame:
        """
        Retorna casos mensais dos últimos N meses.
        
        Args:
            last_n_months: Número de meses a considerar
            
        Returns:
            DataFrame com ano-mês e número de casos
        """
        if self.df_processed is None:
            raise ValueError("Dados não processados. Execute clean_data() primeiro.")
        
        df = self.df_processed
        
        # Criar coluna de ano-mês
        df['ANO_MES'] = df['DT_NOTIFIC'].dt.to_period('M')
        
        # Data de corte
        max_period = df['ANO_MES'].max()
        cutoff_period = max_period - last_n_months
        
        # Filtrar últimos N meses
        df_recent = df[df['ANO_MES'] > cutoff_period]
        
        # Agrupar por mês
        monthly = df_recent.groupby('ANO_MES').size().reset_index(name='casos')
        monthly = monthly.sort_values('ANO_MES')
        monthly['ANO_MES'] = monthly['ANO_MES'].astype(str)
        
        return monthly
    
    def calculate_growth_rate(self, period_days: int = 30) -> float:
        """
        Calcula taxa de aumento de casos.
        
        Args:
            period_days: Período em dias para comparação
            
        Returns:
            Taxa de crescimento percentual
        """
        if self.df_processed is None:
            raise ValueError("Dados não processados. Execute clean_data() primeiro.")
        
        df = self.df_processed
        
        max_date = df['DT_NOTIFIC'].max()
        
        # Período atual
        current_start = max_date - timedelta(days=period_days)
        current_cases = len(df[df['DT_NOTIFIC'] >= current_start])
        
        # Período anterior
        previous_start = current_start - timedelta(days=period_days)
        previous_end = current_start
        previous_cases = len(df[(df['DT_NOTIFIC'] >= previous_start) & 
                                 (df['DT_NOTIFIC'] < previous_end)])
        
        if previous_cases == 0:
            return 0.0
        
        growth_rate = ((current_cases - previous_cases) / previous_cases) * 100
        
        return growth_rate
    
    def save_processed_data(self, output_path: str):
        """
        Salva dados processados em CSV.
        
        Args:
            output_path: Caminho para salvar o arquivo
        """
        if self.df_processed is None:
            raise ValueError("Dados não processados. Execute clean_data() primeiro.")
        
        logger.info(f"Salvando dados processados em {output_path}")
        self.df_processed.to_csv(output_path, index=False, encoding='utf-8')
        logger.info("Dados salvos com sucesso")


if __name__ == "__main__":
    # Teste do processador
    processor = SRAGDataProcessor('/home/ubuntu/srag-health-monitor/data/raw/srag_2024.csv')
    processor.load_data()
    processor.clean_data()
    
    stats = processor.get_statistics()
    print("\n=== Estatísticas dos Dados ===")
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    processor.save_processed_data('/home/ubuntu/srag-health-monitor/data/processed/srag_2024_processed.csv')
