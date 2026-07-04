#!/usr/bin/env python3.11
"""Processo worker para executar jobs de relatório."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from config import AppConfig
from services.job_store import SQLiteJobStore
from services.report_worker import ReportWorker


def main():
    parser = argparse.ArgumentParser(
        description="SRAG Health Monitor - Worker de relatórios"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa no máximo um job pendente e encerra",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Intervalo de polling em segundos (padrão: 2.0)",
    )
    args = parser.parse_args()

    config = AppConfig.from_env()
    config.ensure_runtime_dirs()
    store = SQLiteJobStore(config.jobs_db_path)
    worker = ReportWorker(store, poll_interval_seconds=args.poll_interval)

    if args.once:
        job = worker.run_once()
        if job is None:
            print("Nenhum job pendente.")
            return
        print(f"Job {job.job_id}: {job.status.value}")
        return

    print(f"Worker iniciado. Jobs DB: {config.jobs_db_path}")
    worker.run_forever()


if __name__ == "__main__":
    main()
