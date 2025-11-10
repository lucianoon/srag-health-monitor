"""
Sistema de Auditoria e Logging Estruturado.

Este módulo implementa um sistema completo de auditoria para rastrear
todas as decisões e operações do agente.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import uuid


class AuditLogger:
    """Logger de auditoria para rastreamento de operações."""

    def __init__(self, log_dir: str = "/home/ubuntu/srag-health-monitor/outputs/logs"):
        """
        Inicializa o audit logger.

        Args:
            log_dir: Diretório para salvar logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Configurar logger
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)

        # Handler para arquivo JSON
        log_file = self.log_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)

        # Handler para console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - AUDIT - %(message)s')
        )
        self.logger.addHandler(console_handler)

    def log_event(self, event_type: str, data: Dict[str, Any],
                  execution_id: Optional[str] = None):
        """
        Registra um evento de auditoria.

        Args:
            event_type: Tipo do evento
            data: Dados do evento
            execution_id: ID da execução (opcional)
        """
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "execution_id": execution_id,
            "data": data
        }

        self.logger.info(json.dumps(event, ensure_ascii=False))

    def log_agent_decision(self, decision: str, reasoning: str,
                           execution_id: str, metadata: Optional[Dict] = None):
        """
        Registra uma decisão do agente.

        Args:
            decision: Decisão tomada
            reasoning: Raciocínio da decisão
            execution_id: ID da execução
            metadata: Metadados adicionais
        """
        data = {
            "decision": decision,
            "reasoning": reasoning,
            "metadata": metadata or {}
        }

        self.log_event("agent_decision", data, execution_id)

    def log_tool_call(self, tool_name: str, inputs: Dict, outputs: Dict,
                      execution_id: str, duration_ms: float):
        """
        Registra uma chamada de ferramenta.

        Args:
            tool_name: Nome da ferramenta
            inputs: Parâmetros de entrada
            outputs: Resultados da ferramenta
            execution_id: ID da execução
            duration_ms: Duração em milissegundos
        """
        data = {
            "tool_name": tool_name,
            "inputs": inputs,
            "outputs": outputs,
            "duration_ms": duration_ms
        }

        self.log_event("tool_call", data, execution_id)

    def log_validation(self, validation_type: str, valid: bool,
                       message: str, execution_id: str):
        """
        Registra uma validação.

        Args:
            validation_type: Tipo de validação
            valid: Se passou na validação
            message: Mensagem da validação
            execution_id: ID da execução
        """
        data = {
            "validation_type": validation_type,
            "valid": valid,
            "message": message
        }

        self.log_event("validation", data, execution_id)

    def log_error(self, error_type: str, error_message: str,
                  execution_id: str, stack_trace: Optional[str] = None):
        """
        Registra um erro.

        Args:
            error_type: Tipo do erro
            error_message: Mensagem de erro
            execution_id: ID da execução
            stack_trace: Stack trace (opcional)
        """
        data = {
            "error_type": error_type,
            "error_message": error_message,
            "stack_trace": stack_trace
        }

        self.log_event("error", data, execution_id)

    def log_report_generation(self, execution_id: str, metrics: Dict,
                              news_count: int, charts_generated: int,
                              report_path: str, duration_ms: float):
        """
        Registra a geração de um relatório.

        Args:
            execution_id: ID da execução
            metrics: Métricas utilizadas
            news_count: Número de notícias consultadas
            charts_generated: Número de gráficos gerados
            report_path: Caminho do relatório
            duration_ms: Duração total em milissegundos
        """
        data = {
            "metrics": metrics,
            "news_count": news_count,
            "charts_generated": charts_generated,
            "report_path": report_path,
            "duration_ms": duration_ms
        }

        self.log_event("report_generation", data, execution_id)


class ExecutionTracker:
    """Rastreador de execução para métricas de performance."""

    def __init__(self):
        """Inicializa o tracker."""
        self.executions = {}

    def start_execution(self, execution_id: str) -> Dict[str, Any]:
        """
        Inicia o rastreamento de uma execução.

        Args:
            execution_id: ID da execução

        Returns:
            Dicionário com informações da execução
        """
        execution = {
            "execution_id": execution_id,
            "start_time": datetime.now(),
            "tool_calls": [],
            "validations": [],
            "errors": []
        }

        self.executions[execution_id] = execution
        return execution

    def add_tool_call(self, execution_id: str, tool_name: str, duration_ms: float):
        """
        Adiciona uma chamada de ferramenta ao rastreamento.

        Args:
            execution_id: ID da execução
            tool_name: Nome da ferramenta
            duration_ms: Duração em milissegundos
        """
        if execution_id in self.executions:
            self.executions[execution_id]["tool_calls"].append({
                "tool": tool_name,
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat()
            })

    def add_validation(self, execution_id: str, validation_type: str, valid: bool):
        """
        Adiciona uma validação ao rastreamento.

        Args:
            execution_id: ID da execução
            validation_type: Tipo de validação
            valid: Se passou na validação
        """
        if execution_id in self.executions:
            self.executions[execution_id]["validations"].append({
                "type": validation_type,
                "valid": valid,
                "timestamp": datetime.now().isoformat()
            })

    def add_error(self, execution_id: str, error_type: str):
        """
        Adiciona um erro ao rastreamento.

        Args:
            execution_id: ID da execução
            error_type: Tipo do erro
        """
        if execution_id in self.executions:
            self.executions[execution_id]["errors"].append({
                "type": error_type,
                "timestamp": datetime.now().isoformat()
            })

    def end_execution(self, execution_id: str) -> Dict[str, Any]:
        """
        Finaliza o rastreamento de uma execução.

        Args:
            execution_id: ID da execução

        Returns:
            Sumário da execução
        """
        if execution_id not in self.executions:
            return {}

        execution = self.executions[execution_id]
        execution["end_time"] = datetime.now()
        execution["duration_ms"] = (
            execution["end_time"] - execution["start_time"]
        ).total_seconds() * 1000

        summary = {
            "execution_id": execution_id,
            "duration_ms": execution["duration_ms"],
            "total_tool_calls": len(execution["tool_calls"]),
            "total_validations": len(execution["validations"]),
            "failed_validations": sum(1 for v in execution["validations"] if not v["valid"]),
            "total_errors": len(execution["errors"]),
            "success": len(execution["errors"]) == 0
        }

        return summary


# Instâncias globais
audit_logger = AuditLogger()
execution_tracker = ExecutionTracker()


if __name__ == "__main__":
    # Teste do sistema de auditoria
    print("\n=== Teste: Sistema de Auditoria ===")

    execution_id = "test_20251106_001"

    # Iniciar execução
    execution_tracker.start_execution(execution_id)

    # Simular eventos
    audit_logger.log_agent_decision(
        decision="Gerar relatório de SRAG",
        reasoning="Solicitação do usuário para análise epidemiológica",
        execution_id=execution_id,
        metadata={"user": "system"}
    )

    audit_logger.log_tool_call(
        tool_name="database_query",
        inputs={"query_type": "metrics"},
        outputs={"taxa_mortalidade": 7.67},
        execution_id=execution_id,
        duration_ms=150.5
    )

    execution_tracker.add_tool_call(execution_id, "database_query", 150.5)

    audit_logger.log_validation(
        validation_type="metrics_validation",
        valid=True,
        message="Métricas dentro do range esperado",
        execution_id=execution_id
    )

    execution_tracker.add_validation(execution_id, "metrics_validation", True)

    # Finalizar execução
    summary = execution_tracker.end_execution(execution_id)

    print("\n=== Sumário da Execução ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
