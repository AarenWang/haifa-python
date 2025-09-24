from __future__ import annotations

from typing import Sequence

from .vm_events import TraceFrame


class VMRuntimeError(RuntimeError):
    """Runtime error raised by the bytecode VM with attached traceback frames."""

    def __init__(self, message: str, frames: Sequence[TraceFrame]):
        super().__init__(message)
        self.frames = list(frames)


__all__ = ["VMRuntimeError"]
