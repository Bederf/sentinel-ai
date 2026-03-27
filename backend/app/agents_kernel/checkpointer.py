"""Checkpointer boundary for advisory kernel threads.

Checkpointed state is short-term thread continuity only. It is not
long-term agent memory and must never be treated as such.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver


class KernelCheckpointerFactory(ABC):
    """Boundary for production-safe checkpointer adapters."""

    @abstractmethod
    def build(self):
        """Return a LangGraph-compatible checkpointer instance."""


class InMemoryKernelCheckpointerFactory(KernelCheckpointerFactory):
    """Development-safe in-memory checkpointer."""

    def build(self):
        return MemorySaver()


def get_default_checkpointer():
    """Return the default dev-time checkpointer."""

    return InMemoryKernelCheckpointerFactory().build()


def get_thread_id(conversation_id: str | None = None) -> str:
    """Map conversation identity to a LangGraph thread identifier."""

    if conversation_id:
        return conversation_id
    return f"kernel-thread-{uuid4().hex}"


def get_thread_config(conversation_id: str | None = None) -> dict[str, dict[str, str]]:
    """Return the LangGraph config payload for a thread."""

    return {"configurable": {"thread_id": get_thread_id(conversation_id)}}
