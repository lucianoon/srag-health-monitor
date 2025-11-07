"""
Sistema de Auditoria e Logging Estruturado.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import uuid

class AuditLogger:
    """Logger de auditoria para rastreamento de operações."""

    def __init__(self, log_dir: str = None):
        # usar valor do config se não for passado
        if log_dir is None:
            from src.config import LOGS_DIR
            log_dir = str(LOGS_DIR)

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Configurar logger
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # evitar propagação duplicada

        log_file = self.log_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter('%(message)s'))

        # Adicionar handler de arquivo apenas se ainda não houver um handler para este arquivo
        existing_file_handlers = [
            h for h in self.logger.handlers
            if isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(log_file)
        ]
        if not existing_file_handlers:
            self.logger.addHandler(handler)

        # Handler para console - adicionar apenas se não houver handler de console equivalente
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - AUDIT - %(message)s')
        )
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            self.logger.addHandler(console_handler)

    def log_event(self, event_type: str, data: Dict[str, Any],
                  execution_id: Optional[str] = None):
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
        data = {
            "decision": decision,
            "reasoning": reasoning,
            "metadata": metadata or {}
        }
        self.log_event("agent_decision", data, execution_id)

    def log_tool_call(self, tool_name: str, inputs: Dict, outputs: Dict,
                     execution_id: str, duration_ms: float):
        data = {
            "tool_name": tool_name,
            "inputs": inputs,
            "outputs": outputs,
            "duration_ms": duration_ms
        }
        self.log_event("tool_call", data, execution_id)

    def log_validation(self, validation_type: str, valid: bool,
                      message: str, execution_id: str):
        data = {
            "validation_type": validation_type,
            "valid": valid,
            "message": message
        }
        self.log_event("validation", data, execution_id)

    def log_error(self, error_type: str, error_message: str,
                 execution_id: str, stack_trace: Optional[str] = None):
        data = {
            "error_type": error_type,
            "error_message": error_message,
            "stack_trace": stack_trace
        }
        self.log_event("error", data, execution_id)

    def log_report_generation(self, execution_id: str, metrics: Dict,
                             news_count: int, charts_generated: int,
                             report_path: str, duration_ms: float):
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
        self.executions = {}

    def start_execution(self, execution_id: str) -> Dict[str, Any]:
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
        if execution_id in self.executions:
            self.executions[execution_id]["tool_calls"].append({
                "tool": tool_name,
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat()
            })

    def add_validation(self, execution_id: str, validation_type: str, valid: bool):
        if execution_id in self.executions:
            self.executions[execution_id]["validations"].append({
                "type": validation_type,
                "valid": valid,
                "timestamp": datetime.now().isoformat()
            })

    def add_error(self, execution_id: str, error_type: str):
        if execution_id in self.executions:
            self.executions[execution_id]["errors"].append({
                "type": error_type,
                "timestamp": datetime.now().isoformat()
            })

    def end_execution(self, execution_id: str) -> Dict[str, Any]:
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
auditor_logger = AuditLogger()
execution_tracker = ExecutionTracker()
