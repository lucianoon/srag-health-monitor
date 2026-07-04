#!/usr/bin/env python3.11
"""
Script principal para execução do SRAG Health Monitor.

Este script coordena todo o fluxo de geração de relatórios,
incluindo validações, auditoria e tratamento de erros.
"""

import os
import sys
from datetime import datetime
import argparse

# Adicionar src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config import AppConfig
from guardrails.audit_logger import create_audit_logger, execution_tracker


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='SRAG Health Monitor - Sistema de Monitoramento Inteligente de SRAG'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='gpt-4.1-mini',
        help='Modelo LLM a utilizar (padrão: gpt-4.1-mini)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='outputs/reports',
        help='Diretório para salvar relatórios (padrão: outputs/reports)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("SRAG Health Monitor - Sistema de Monitoramento Inteligente")
    print("=" * 80)
    print(f"\nData/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    config = AppConfig.from_env(model_name=args.model, output_dir=args.output_dir)
    config.ensure_runtime_dirs()

    print(f"Modelo LLM: {config.model_name}")
    print(f"Banco de Dados: {config.db_path}")
    print(f"Diretório de Saída: {config.reports_dir}\n")

    audit_logger = create_audit_logger(config.logs_dir)

    if not config.openai_api_key:
        print("⚠️  OPENAI_API_KEY não configurada; o relatório será gerado no modo determinístico.")

    from services.report_service import GenerateReportService

    print("🤖 Inicializando serviço de relatório...")
    service = GenerateReportService(
        config=config,
        audit_logger=audit_logger,
        execution_tracker=execution_tracker,
    )

    try:
        # Executar geração de relatório
        print("⚙️  Gerando relatório...")
        result = service.run()

        print(f"📋 ID de Execução: {result.execution_id}")
        print("✅ Relatório validado com sucesso")

        if result.pii_detected:
            print(f"⚠️  PII detectada e anonimizada: {result.pii_types}")

        print("\n" + "=" * 80)
        print("RELATÓRIO GERADO COM SUCESSO")
        print("=" * 80)
        print(f"\n📄 Arquivo: {result.report_path}")
        print(f"⏱️  Duração: {result.duration_ms:.2f}ms")
        print(f"🔧 Ferramentas utilizadas: {result.summary['total_tool_calls']}")
        print(f"✓  Validações: {result.summary['total_validations']}")

        print("\n📊 Sumário da Execução:")
        print(f"   - Sucesso: {result.summary['success']}")
        print(f"   - Erros: {result.summary['total_errors']}")
        print(f"   - Validações falhadas: {result.summary['failed_validations']}")

        print("\n✨ Execução concluída com sucesso!")

    except Exception as e:
        print(f"\n❌ ERRO durante execução: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
