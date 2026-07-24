"""Helpers e fixtures compartilhados pela suíte de testes.

Os testes usam banco SQLite temporário para evitar caminhos absolutos e tornar
a suíte reprodutível em qualquer ambiente/CI. Todo recurso aberto (conexões,
handlers de log) é registrado via ``addCleanup`` para fechamento determinístico
antes da remoção dos diretórios temporários (obrigatório no Windows).
"""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union

import requests

from tests import PROJECT_ROOT
from config import AppConfig
from database.db_manager import SRAGDatabase
from tools.news_tool import NewsSearchTool

__all__ = [
    "PROJECT_ROOT",
    "TempSRAGDatabaseMixin",
    "make_app_config",
    "offline_news_guard",
]


def offline_news_guard():
    """Cria o par (setUpModule, tearDownModule) que mantém o módulo offline.

    O fetch real de notícias é desabilitado na classe ``NewsSearchTool``.
    Testes que exercitam parsing/ranking injetam seu próprio fetch por
    instância (o atributo de instância sombreia o stub de classe).

    Uso, no topo do módulo de teste::

        setUpModule, tearDownModule = offline_news_guard()
    """
    original = {}

    def _offline_fetch(self, url):
        raise requests.RequestException("rede desabilitada em testes")

    def set_up_module():
        original["fetch"] = NewsSearchTool._fetch_feed
        NewsSearchTool._fetch_feed = _offline_fetch

    def tear_down_module():
        NewsSearchTool._fetch_feed = original.pop("fetch")

    return set_up_module, tear_down_module


def make_app_config(
    base_dir: Union[str, Path],
    db_path: Optional[Union[str, Path]] = None,
    **overrides,
) -> AppConfig:
    """Cria um AppConfig apontando todos os caminhos para um diretório de teste."""
    base = Path(base_dir)
    params = dict(
        project_root=PROJECT_ROOT,
        data_dir=base,
        db_path=Path(db_path) if db_path else base / "srag.db",
        jobs_db_path=base / "jobs.db",
        reports_dir=base / "reports",
        logs_dir=base / "logs",
        model_name="gpt-4.1-mini",
        openai_api_key=None,
    )
    params.update(overrides)
    return AppConfig(**params)


class TempSRAGDatabaseMixin:
    """Cria um banco SRAG temporário com dados determinísticos."""

    def setUp(self):
        # addCleanup em vez de tearDown: cleanups rodam em ordem LIFO, então
        # tudo que os testes registrarem depois (ex.: fechar conexões/handlers)
        # executa ANTES da remoção do diretório temporário.
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db_path = os.path.join(self.tmpdir.name, "srag.db")
        self.db = SRAGDatabase(self.db_path)
        self.db.connect()
        self.addCleanup(self.db.close)
        self.db.create_tables()
        self._insert_sample_rows()

    def _insert_sample_rows(self):
        cursor = self.db.conn.cursor()
        base = datetime(2024, 12, 1)
        rows = []
        for i in range(12):
            date = base + timedelta(days=i)
            rows.append((
                date.strftime("%Y-%m-%d %H:%M:%S"),
                "SP",
                1 if i % 4 == 0 else 0,   # obito
                1 if i % 3 == 0 else 0,   # internou_uti
                1 if i % 2 == 0 else 0,   # vacinado
            ))
        cursor.executemany(
            """
            INSERT INTO casos_srag (
                dt_notific, sg_uf, obito, internou_uti, vacinado
            ) VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.db.conn.commit()
