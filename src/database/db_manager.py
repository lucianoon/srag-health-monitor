"""
Módulo de gerenciamento do banco de dados SQLite para dados de SRAG.
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
        self.db_path = db_path
        self.conn = None

    def connect(self):
        logger.info(f"Conectando ao banco de dados: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Conexão com banco de dados fechada")

    def create_tables(self):
        logger.info("Criando tabelas do banco de dados")
        cursor = self.conn.cursor()

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

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dt_notific ON casos_srag(dt_notific)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sg_uf ON casos_srag(sg_uf)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_obito ON casos_srag(obito)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_uti ON casos_srag(internou_uti)")

        self.conn.commit()
        logger.info("Tabelas criadas com sucesso")

    def load_data_from_csv(self, csv_path: str):
        logger.info(f"Carregando dados de {csv_path}")
        df = pd.read_csv(csv_path)

        df_db = pd.DataFrame({
            'dt_notific': pd.to_datetime(df['DT_NOTIFIC'], errors='coerce'),
            'dt_sin_pri': pd.to_datetime(df.get('DT_SIN_PRI'), errors='coerce'),
            'sg_uf': df.get('SG_UF'),
            'co_mun_res': df.get('CO_MUN_RES'),
            'cs_sexo': df.get('CS_SEXO'),
            'idade_anos': df.get('IDADE_ANOS'),
            'evolucao': df.get('EVOLUCAO'),
            'obito': df.get('OBITO'),
            'uti': df.get('UTI'),
            'internou_uti': df.get('INTERNOU_UTI'),
            'dt_entuti': pd.to_datetime(df.get('DT_ENTUTI'), errors='coerce'),
            'dt_saiduti': pd.to_datetime(df.get('DT_SAIDUTI'), errors='coerce'),
            'vacina': df.get('VACINA'),
            'vacina_cov': df.get('VACINA_COV'),
            'vacinado': df.get('VACINADO'),
            'dt_evoluca': pd.to_datetime(df.get('DT_EVOLUCA'), errors='coerce'),
            'dt_interna': pd.to_datetime(df.get('DT_INTERNA'), errors='coerce'),
            'hospitalizado': df.get('HOSPITAL'),
            'febre': df.get('FEBRE'),
            'tosse': df.get('TOSSE'),
            'dispneia': df.get('DISPNEIA'),
            'saturacao': df.get('SATURACAO'),
        })

        df_db.to_sql('casos_srag', self.conn, if_exists='append', index=False)

        logger.info(f"{len(df_db)} registros inseridos no banco de dados")

    def _fetch_one(self, cursor) -> Optional[Tuple]:
        """Helper para fetchone seguro que trata None."""
        row = cursor.fetchone()
        return row if row is not None else None

    def get_total_cases(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM casos_srag")
        row = self._fetch_one(cursor)
        return int(row[0]) if row and row[0] is not None else 0

    def get_mortality_rate(self) -> float:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(obito) as obitos
            FROM casos_srag
        """)
        row = self._fetch_one(cursor)
        if not row or row[0] is None:
            return 0.0
        total, obitos = row
        if total == 0:
            return 0.0
        # proteger divisão por None
        obitos = obitos or 0
        return (obitos / total) * 100

    def get_uti_occupation_rate(self) -> float:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(internou_uti) as uti_cases
            FROM casos_srag
        """)
        row = self._fetch_one(cursor)
        if not row or row[0] is None:
            return 0.0
        total, uti_cases = row
        if total == 0:
            return 0.0
        uti_cases = uti_cases or 0
        return (uti_cases / total) * 100

    def get_vaccination_rate(self) -> float:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(vacinado) as vacinados
            FROM casos_srag
        """)
        row = self._fetch_one(cursor)
        if not row or row[0] is None:
            return 0.0
        total, vacinados = row
        if total == 0:
            return 0.0
        vacinados = vacinados or 0
        return (vacinados / total) * 100

    def get_growth_rate(self, period_days: int = 30) -> float:
        cursor = self.conn.cursor()

        cursor.execute("SELECT MAX(dt_notific) FROM casos_srag")
        row = self._fetch_one(cursor)
        max_date_str = row[0] if row and row[0] is not None else None
        if not max_date_str:
            return 0.0

        # usar pandas para parse robusto
        max_date = pd.to_datetime(max_date_str, errors='coerce')
        if pd.isna(max_date):
            return 0.0

        current_start = max_date - timedelta(days=period_days)

        cursor.execute("""
            SELECT COUNT(*) 
            FROM casos_srag 
            WHERE dt_notific >= ?
        """, (current_start.strftime('%Y-%m-%d'),))
        current_row = self._fetch_one(cursor)
        current_cases = int(current_row[0]) if current_row and current_row[0] is not None else 0

        previous_start = current_start - timedelta(days=period_days)
        previous_end = current_start
        cursor.execute("""
            SELECT COUNT(*) 
            FROM casos_srag 
            WHERE dt_notific >= ? AND dt_notific < ?
        """, (previous_start.strftime('%Y-%m-%d'), previous_end.strftime('%Y-%m-%d')))
        previous_row = self._fetch_one(cursor)
        previous_cases = int(previous_row[0]) if previous_row and previous_row[0] is not None else 0

        if previous_cases == 0:
            return 0.0

        return ((current_cases - previous_cases) / previous_cases) * 100

    def get_daily_cases(self, last_n_days: int = 30) -> List[Tuple[str, int]]:
        cursor = self.conn.cursor()

        cursor.execute("SELECT MAX(dt_notific) FROM casos_srag")
        row = self._fetch_one(cursor)
        max_date_str = row[0] if row and row[0] is not None else None
        if not max_date_str:
            return []

        max_date = pd.to_datetime(max_date_str, errors='coerce')
        if pd.isna(max_date):
            return []

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
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM casos_srag")
        row = self._fetch_one(cursor)
        total_rows = int(row[0]) if row and row[0] is not None else 0
        if total_rows == 0:
            return []

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
        return {
            'taxa_aumento_casos': self.get_growth_rate(),
            'taxa_mortalidade': self.get_mortality_rate(),
            'taxa_ocupacao_uti': self.get_uti_occupation_rate(),
            'taxa_vacinacao': self.get_vaccination_rate(),
            'total_casos': self.get_total_cases()
        }
"},
"message":"fix(database): make DB date parsing robust and handle empty tables"}
