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

from agents.orchestrator import SRAGReportOrchestrator
from guardrails.validators import InputValidator, OutputValidator, DataPrivacyGuard
from guardrails.audit_logger import audit_logger, execution_tracker


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
    
    print("="*80)
    print("SRAG Health Monitor - Sistema de Monitoramento Inteligente")
    print("="*80)
    print(f"\nData/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Modelo LLM: {args.model}")
    print(f"Diretório de Saída: {args.output_dir}\n")
    
    # Verificar variável de ambiente
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ ERRO: Variável de ambiente OPENAI_API_KEY não configurada")
        print("Configure com: export OPENAI_API_KEY='sua-chave-api'")
        sys.exit(1)
    
    # Criar orquestrador
    print("🤖 Inicializando orquestrador...")
    orchestrator = SRAGReportOrchestrator(model_name=args.model)
    execution_id = orchestrator.execution_id
    
    # Iniciar rastreamento
    execution_tracker.start_execution(execution_id)
    
    try:
        # Registrar início
        audit_logger.log_agent_decision(
            decision="Iniciar geração de relatório",
            reasoning="Execução solicitada via script principal",
            execution_id=execution_id,
            metadata={"model": args.model}
        )
        
        print(f"📋 ID de Execução: {execution_id}\n")
        
        # Executar geração de relatório
        print("⚙️  Gerando relatório...")
        start_time = datetime.now()
        
        report = orchestrator.run()
        
        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        # Validar relatório
        print("\n🔍 Validando relatório...")
        valid, message = OutputValidator.validate_report_content(report)
        
        if not valid:
            print(f"❌ Validação falhou: {message}")
            audit_logger.log_validation(
                validation_type="report_content",
                valid=False,
                message=message,
                execution_id=execution_id
            )
            sys.exit(1)
        
        print("✅ Relatório validado com sucesso")
        
        # Verificar PII (não deve haver em relatórios agregados)
        has_pii, pii_types = DataPrivacyGuard.check_for_pii(report)
        if has_pii:
            print(f"⚠️  AVISO: PII detectado no relatório: {pii_types}")
            print("   Anonimizando automaticamente...")
            report = DataPrivacyGuard.anonymize_text(report)
        
        # Finalizar rastreamento
        summary = execution_tracker.end_execution(execution_id)
        
        print("\n" + "="*80)
        print("RELATÓRIO GERADO COM SUCESSO")
        print("="*80)
        print(f"\n📄 Arquivo: outputs/reports/relatorio_{execution_id}.md")
        print(f"⏱️  Duração: {duration_ms:.2f}ms")
        print(f"🔧 Ferramentas utilizadas: {summary['total_tool_calls']}")
        print(f"✓  Validações: {summary['total_validations']}")
        
        # Registrar sucesso
        audit_logger.log_report_generation(
            execution_id=execution_id,
            metrics=orchestrator.collect_metrics(),
            news_count=5,
            charts_generated=2,
            report_path=f"outputs/reports/relatorio_{execution_id}.md",
            duration_ms=duration_ms
        )
        
        print("\n📊 Sumário da Execução:")
        print(f"   - Sucesso: {summary['success']}")
        print(f"   - Erros: {summary['total_errors']}")
        print(f"   - Validações falhadas: {summary['failed_validations']}")
        
        print("\n✨ Execução concluída com sucesso!")
        
    except Exception as e:
        print(f"\n❌ ERRO durante execução: {e}")
        
        # Registrar erro
        audit_logger.log_error(
            error_type=type(e).__name__,
            error_message=str(e),
            execution_id=execution_id,
            stack_trace=None
        )
        
        execution_tracker.add_error(execution_id, type(e).__name__)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
