#!/usr/bin/env python3.11
"""CLI para ingestão de dados SRAG do SUS/OpenDATASUS."""

import argparse
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from config import AppConfig
from services.data_ingestion_service import DataIngestionService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingestão de dados SRAG a partir de fonte oficial do SUS"
    )
    parser.add_argument(
        "--source-url",
        default=None,
        help="URL do arquivo CSV SRAG publicado pelo SUS/OpenDATASUS",
    )
    parser.add_argument(
        "--nrows",
        type=int,
        default=None,
        help="Limita a quantidade de linhas lidas para smoke tests locais",
    )

    args = parser.parse_args()
    config = AppConfig.from_env()
    service = DataIngestionService(config)
    result = service.run(source_url=args.source_url, nrows=args.nrows)

    print("Ingestão concluída com sucesso")
    print(f"Fonte: {result.source_url}")
    print(f"Linhas processadas: {result.rows_processed}")
    print(f"Banco: {result.db_path}")
    print(f"Metadados: {result.metadata_path}")
    print(f"Duração: {result.duration_ms:.2f}ms")


if __name__ == "__main__":
    main()
