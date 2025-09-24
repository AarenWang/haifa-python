from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Sequence


@dataclass(frozen=True)
class TraceFrame:
    """Represents a single frame in a Lua-style traceback."""

    function_name: str
    file: str
    line: int
    column: int
    pc: int
    coroutine_id: int | None = None


@dataclass(frozen=True)
class CoroutineCreated:
    coroutine_id: int
    parent_id: int | None
    function_name: str | None
    args: Sequence[Any]
    timestamp: float


@dataclass(frozen=True)
class CoroutineResumed:
    coroutine_id: int
    args: Sequence[Any]
    timestamp: float


@dataclass(frozen=True)
class CoroutineYielded:
    coroutine_id: int
    values: Sequence[Any]
    pc: int
    timestamp: float


@dataclass(frozen=True)
class CoroutineCompleted:
    coroutine_id: int
    values: Sequence[Any]
    error: str | None
    timestamp: float


CoroutineEvent = CoroutineCreated | CoroutineResumed | CoroutineYielded | CoroutineCompleted


@dataclass
class CoroutineSnapshot:
    coroutine_id: int
    status: str
    last_yield: List[Any]
    last_error: str | None
    last_resume_args: List[Any] = field(default_factory=list)
    awaiting_resume: bool = False


@dataclass
class VMStateSnapshot:
    pc: int
    current_coroutine: int | None
    registers: Mapping[str, Any]
    stack: Sequence[Any]
    call_stack: Sequence[TraceFrame]
    coroutines: Sequence[CoroutineSnapshot] = field(default_factory=list)
    active_coroutines: Sequence[int] = field(default_factory=list)


__all__ = [
    "CoroutineCreated",
    "CoroutineResumed",
    "CoroutineYielded",
    "CoroutineCompleted",
    "CoroutineEvent",
    "CoroutineSnapshot",
    "TraceFrame",
    "VMStateSnapshot",
]
