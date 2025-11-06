"""Minimal tool base class used to avoid dependências externas pesadas."""
from __future__ import annotations

from typing import Any


class ToolBase:
    """Interface simplificada para ferramentas síncronas."""

    # Metadata attributes kept for compatibility with the original class.
    name: str = ""
    description: str = ""
    args_schema: type[Any] | None = None

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Alias used by some integrations to execute the tool."""

        return self._run(*args, **kwargs)

    def _run(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - interface
        raise NotImplementedError
