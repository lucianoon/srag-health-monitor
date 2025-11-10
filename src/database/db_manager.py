"""
Módulo de gerenciamento do banco de dados SQLite para dados de SRAG.

Este módulo é responsável por:
- Criar e gerenciar o banco de dados SQLite
- Carregar dados processados no banco
- Fornecer interface para consultas
"""

import sqlite3
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SRAGDatabase:
    """Gerenciador do banco de dados de SRAG."""

    def __init__(self, db_path: str):
        """
        Inicializa o gerenciador do banco de dados.

        Args:
            db_path: Caminho para o arquivo do banco de dados SQLite
        """
        self.db_path = db_path
        self.conn = None

    def connect(self):
        """Estabelece conexão com o banco de dados."""
        logger.info(f"Conectando ao banco de dados: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        return self.conn

    def close(self):
        """Fecha a conexão com o banco de dados."""
        if self.conn:
            self.conn.close()
            logger.info("Conexão com banco de dados fechada")

    def create_tables(self):
        """Cria as tabelas do banco de dados."""
        logger.info("Criando tabelas do banco de dados")

        cursor = self.conn.cursor()

        # Tabela principal de casos de SRAG
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS casos_srag (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dt_notific DATE NOT NULL,
                dt_sin_pri DATE,
                sg_uf TEXT,
                co_mun_res TEXT,
                cs_sexo INTEGER,
                idade_anos REAL,
                evolucao INTEGER,
                obito INTEGER,
                uti INTEGER,
                internou_uti INTEGER,
                dt_entuti DATE,
                dt_saiduti DATE,
                vacina INTEGER,
                vacina_cov INTEGER,
                vacinado INTEGER,
                dt_evoluca DATE,
                dt_interna DATE,
                hospitalizado INTEGER,
                febre INTEGER,
                tosse INTEGER,
                dispneia INTEGER,
                saturacao INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Índices para otimizar consultas
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dt_notific ON casos_srag(dt_notific)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sg_uf ON casos_srag(sg_uf)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_obito ON casos_srag(obito)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_uti ON casos_srag(internou_uti)")

        self.conn.commit()
        logger.info("Tabelas criadas com sucesso")

    def load_data_from_csv(self, csv_path: str):
        """
        Carrega dados do CSV processado para o banco de dados.

        Args:
            csv_path: Caminho para o arquivo CSV processado
        """
        logger.info(f"Carregando dados de {csv_path}")

        # Ler CSV
        df = pd.read_csv(csv_path)

        # Mapear colunas para o banco
        df_db = pd.DataFrame({
            'dt_notific': pd.to_datetime(df['DT_NOTIFIC']),
            'dt_sin_pri': pd.to_datetime(df['DT_SIN_PRI']),
            'sg_uf': df['SG_UF'],
            'co_mun_res': df['CO_MUN_RES'],
            'cs_sexo': df['CS_SEXO'],
            'idade_anos': df['IDADE_ANOS'],
            'evolucao': df['EVOLUCAO'],
            'obito': df['OBITO'],
            'uti': df['UTI'],
            'internou_uti': df['INTERNOU_UTI'],
            'dt_entuti': pd.to_datetime(df['DT_ENTUTI']),
            'dt_saiduti': pd.to_datetime(df['DT_SAIDUTI']),
            'vacina': df['VACINA'],
            'vacina_cov': df['VACINA_COV'],
            'vacinado': df['VACINADO'],
            'dt_evoluca': pd.to_datetime(df['DT_EVOLUCA']),
            'dt_interna': pd.to_datetime(df['DT_INTERNA']),
            'hospitalizado': df['HOSPITALIZADO'],
            'febre': df.get('FEBRE'),
            'tosse': df.get('TOSSE'),
            'dispneia': df.get('DISPNEIA'),
            'saturacao': df.get('SATURACAO'),
        })

        # Inserir no banco
        df_db.to_sql('casos_srag', self.conn, if_exists='append', index=False)

        logger.info(f"{len(df_db)} registros inseridos no banco de dados")

    def get_total_cases(self) -> int:
        """Retorna o total de casos registrados."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM casos_srag")
        return cursor.fetchone()[0]

    def get_mortality_rate(self) -> float:
        """
        Calcula a taxa de mortalidade.

        Returns:
            Taxa de mortalidade em percentual
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(obito) as obitos
            FROM casos_srag
        """)
        total, obitos = cursor.fetchone()

        if total == 0:
            return 0.0

        return (obitos / total) * 100

    def get_uti_occupation_rate(self) -> float:
        """
        Calcula a taxa de ocupação de UTI.

        Returns:
            Taxa de ocupação de UTI em percentual
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(internou_uti) as uti_cases
            FROM casos_srag
        """)
        total, uti_cases = cursor.fetchone()

        if total == 0:
            return 0.0

        return (uti_cases / total) * 100

    def get_vaccination_rate(self) -> float:
        """
        Calcula a taxa de vacinação.

        Returns:
            Taxa de vacinação em percentual
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(vacinado) as vacinados
            FROM casos_srag
        """)
        total, vacinados = cursor.fetchone()

        if total == 0:
            return 0.0

        return (vacinados / total) * 100

    def get_growth_rate(self, period_days: int = 30) -> float:
        """
        Calcula a taxa de aumento de casos.

        Args:
            period_days: Período em dias para comparação

        Returns:
            Taxa de crescimento em percentual
        """
        cursor = self.conn.cursor()

        # Obter data máxima
        cursor.execute("SELECT MAX(dt_notific) FROM casos_srag")
        max_date_str = cursor.fetchone()[0]
        max_date = datetime.strptime(max_date_str, '%Y-%m-%d %H:%M:%S')

        # Período atual
        current_start = max_date - timedelta(days=period_days)
        cursor.execute("""
            SELECT COUNT(*)
            FROM casos_srag
            WHERE dt_notific >= ?
        """, (current_start.strftime('%Y-%m-%d'),))
        current_cases = cursor.fetchone()[0]

        # Período anterior
        previous_start = current_start - timedelta(days=period_days)
        previous_end = current_start
        cursor.execute("""
            SELECT COUNT(*)
            FROM casos_srag
            WHERE dt_notific >= ? AND dt_notific < ?
        """, (previous_start.strftime('%Y-%m-%d'), previous_end.strftime('%Y-%m-%d')))
        previous_cases = cursor.fetchone()[0]

        if previous_cases == 0:
            return 0.0

        return ((current_cases - previous_cases) / previous_cases) * 100

    def get_daily_cases(self, last_n_days: int = 30) -> List[Tuple[str, int]]:
        """
        Retorna casos diários dos últimos N dias.

        Args:
            last_n_days: Número de dias

        Returns:
            Lista de tuplas (data, número_de_casos)
        """
        cursor = self.conn.cursor()

        # Obter data máxima
        cursor.execute("SELECT MAX(dt_notific) FROM casos_srag")
        max_date_str = cursor.fetchone()[0]
        max_date = datetime.strptime(max_date_str, '%Y-%m-%d %H:%M:%S')

        cutoff_date = max_date - timedelta(days=last_n_days)

        cursor.execute("""
            SELECT
                DATE(dt_notific) as data,
                COUNT(*) as casos
            FROM casos_srag
            WHERE dt_notific >= ?
            GROUP BY DATE(dt_notific)
            ORDER BY data
        """, (cutoff_date.strftime('%Y-%m-%d'),))

        return cursor.fetchall()

    def get_monthly_cases(self, last_n_months: int = 12) -> List[Tuple[str, int]]:
        """
        Retorna casos mensais dos últimos N meses.

        Args:
            last_n_months: Número de meses

        Returns:
            Lista de tuplas (ano-mês, número_de_casos)
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                strftime('%Y-%m', dt_notific) as mes,
                COUNT(*) as casos
            FROM casos_srag
            GROUP BY strftime('%Y-%m', dt_notific)
            ORDER BY mes DESC
            LIMIT ?
        """, (last_n_months,))

        results = cursor.fetchall()
        return list(reversed(results))  # Ordem cronológica

    def get_all_metrics(self) -> Dict[str, float]:
        """
        Retorna todas as métricas principais.

        Returns:
            Dicionário com todas as métricas
        """
        return {
            'taxa_aumento_casos': self.get_growth_rate(),
            'taxa_mortalidade': self.get_mortality_rate(),
            'taxa_ocupacao_uti': self.get_uti_occupation_rate(),
            'taxa_vacinacao': self.get_vaccination_rate(),
            'total_casos': self.get_total_cases()
        }


if __name__ == "__main__":
    # Teste do banco de dados
    db = SRAGDatabase('/home/ubuntu/srag-health-monitor/data/srag.db')
    db.connect()
    db.create_tables()
    db.load_data_from_csv('/home/ubuntu/srag-health-monitor/data/processed/srag_2024_processed.csv')

    print("\n=== Métricas do Banco de Dados ===")
    metrics = db.get_all_metrics()
    for key, value in metrics.items():
        print(f"{key}: {value:.2f}")

    db.close()
