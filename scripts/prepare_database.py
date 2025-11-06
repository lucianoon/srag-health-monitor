#!/usr/bin/env python3.11
"""Script utilitário para preparar o banco de dados do SRAG Health Monitor."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from utils.paths import (  # noqa: E402  # pylint: disable=C0413
    DEFAULT_DB_PATH,
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    ensure_directory,
)
from utils.data_processor import SRAGDataProcessor  # noqa: E402  # pylint: disable=C0413
from database.db_manager import SRAGDatabase  # noqa: E402  # pylint: disable=C0413


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("prepare_database")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepara o banco de dados SQLite a partir do CSV oficial do DATASUS. "
            "O script executa as etapas de processamento do arquivo bruto, gera "
            "um CSV tratado e popula o banco utilizado pelo SRAG Health Monitor."
        )
    )
    parser.add_argument(
        "--raw-csv",
        type=Path,
        default=RAW_DATA_DIR / "srag2024.csv",
        help=(
            "Caminho para o CSV bruto do DATASUS (default: data/raw/srag2024.csv). "
            "Faça o download prévio do Open DATASUS."
        ),
    )
    parser.add_argument(
        "--processed-csv",
        type=Path,
        default=PROCESSED_DATA_DIR / "srag_2024_processed.csv",
        help="Caminho de saída para o CSV processado (default: data/processed/srag_2024_processed.csv).",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Caminho do banco SQLite que receberá os dados processados (default: data/srag.db).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Quantidade de linhas a carregar do CSV bruto (útil para testes locais).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    ensure_directory(args.raw_csv.parent)
    ensure_directory(args.processed_csv.parent)
    ensure_directory(args.database.parent)

    if not args.raw_csv.exists():
        raise FileNotFoundError(
            f"Arquivo CSV bruto não encontrado em {args.raw_csv}. Faça o download do dataset no Open DATASUS e informe o caminho com --raw-csv."
        )

    logger.info("Carregando dados brutos de %s", args.raw_csv)
    processor = SRAGDataProcessor(str(args.raw_csv))
    processor.load_data(nrows=args.limit)
    df_clean = processor.clean_data()

    logger.info("Salvando CSV processado em %s", args.processed_csv)
    df_clean.to_csv(args.processed_csv, index=False)

    with SRAGDatabase(str(args.database)) as db:
        db.create_tables()
        logger.info("Importando registros para %s", args.database)
        db.load_data_from_csv(str(args.processed_csv))

    logger.info("Processamento concluído com sucesso.")


if __name__ == "__main__":
    main()
