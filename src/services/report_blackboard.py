"""Blackboard de etapas para pipelines coordenados por estado.

Em vez de um fluxo fixo de chamadas (A chama B, que chama C), cada etapa
declara pré-condições sobre o estado compartilhado. O loop observa o estado,
executa em paralelo tudo que estiver pronto e persiste o progresso após cada
onda — uma nova execução com o mesmo arquivo de estado retoma do ponto exato
da falha, sem refazer etapas concluídas.

Contrato: os artefatos trocados entre etapas devem ser serializáveis em JSON.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence
import json
import logging


logger = logging.getLogger(__name__)


class StepStatus(str, Enum):
    """Estados possíveis de uma etapa no blackboard."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Step:
    """Etapa observadora: executa quando todas as `requires` estão DONE.

    `run` recebe uma cópia dos artefatos atuais e retorna um dict com os
    novos artefatos a mesclar no estado compartilhado.
    """

    name: str
    run: Callable[[dict], dict]
    requires: Sequence[str] = ()


class StepExecutionError(RuntimeError):
    """Falha de uma etapa, preservando qual etapa e a causa original."""

    def __init__(self, step_name: str, cause: BaseException):
        super().__init__(f"Etapa '{step_name}' falhou: {cause}")
        self.step_name = step_name
        self.cause = cause


class ReportBlackboard:
    """Executa etapas guiadas pelo estado, com persistência opcional em JSON."""

    def __init__(self, steps: List[Step], state_path: Optional[Path] = None):
        names = [step.name for step in steps]
        if len(names) != len(set(names)):
            raise ValueError("Etapas com nomes duplicados no blackboard.")
        unknown = {req for step in steps for req in step.requires} - set(names)
        if unknown:
            raise ValueError(f"Pré-condições desconhecidas: {sorted(unknown)}")

        self.steps = {step.name: step for step in steps}
        self.state_path = state_path
        self.status: Dict[str, StepStatus] = {name: StepStatus.PENDING for name in names}
        self.artifacts: dict = {}
        self._load_state()

    @property
    def ready_steps(self) -> List[Step]:
        """Etapas pendentes com todas as pré-condições DONE."""
        return [
            step
            for step in self.steps.values()
            if self.status[step.name] == StepStatus.PENDING
            and all(self.status[req] == StepStatus.DONE for req in step.requires)
        ]

    def run(self) -> dict:
        """Executa até esgotar as etapas prontas e retorna os artefatos.

        Etapas prontas na mesma onda rodam em paralelo. Se uma falha, as
        irmãs concluídas ainda são persistidas antes de propagar o erro —
        é isso que torna a retomada granular.
        """
        while True:
            ready = self.ready_steps
            if not ready:
                break
            logger.info(
                "Blackboard executando etapas prontas: %s",
                [step.name for step in ready],
            )
            with ThreadPoolExecutor(max_workers=len(ready)) as pool:
                futures = {
                    step: pool.submit(step.run, dict(self.artifacts))
                    for step in ready
                }
            failures = []
            for step, future in futures.items():
                error = future.exception()
                if error is not None:
                    self.status[step.name] = StepStatus.FAILED
                    failures.append((step.name, error))
                else:
                    self.artifacts.update(future.result() or {})
                    self.status[step.name] = StepStatus.DONE
            self._persist()
            if failures:
                step_name, error = failures[0]
                raise StepExecutionError(step_name, error)

        incomplete = [
            name for name, status in self.status.items() if status != StepStatus.DONE
        ]
        if incomplete:
            raise RuntimeError(
                "Pipeline bloqueado: etapas sem pré-condição satisfazível: "
                f"{incomplete}"
            )
        return self.artifacts

    def clear_state(self) -> None:
        """Remove o arquivo de estado (execução concluída não precisa dele)."""
        if self.state_path is not None:
            self.state_path.unlink(missing_ok=True)

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        for name, raw_status in data.get("steps", {}).items():
            if name not in self.status:
                continue
            status = StepStatus(raw_status)
            # FAILED volta a PENDING: retomada re-tenta a etapa que falhou.
            self.status[name] = (
                StepStatus.DONE if status == StepStatus.DONE else StepStatus.PENDING
            )
        self.artifacts = data.get("artifacts", {})

    def _persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "steps": {name: status.value for name, status in self.status.items()},
            "artifacts": self.artifacts,
        }
        self.state_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
