from __future__ import annotations

from compiler.vm_events import (
    CoroutineCompleted,
    CoroutineCreated,
    CoroutineResumed,
    CoroutineYielded,
)


def format_coroutine_event(event: object) -> str:
    if isinstance(event, CoroutineCreated):
        name = event.function_name or "<function>"
        return f"created #{event.coroutine_id} ({name})"
    if isinstance(event, CoroutineResumed):
        return f"resume #{event.coroutine_id} args={list(event.args)}"
    if isinstance(event, CoroutineYielded):
        return f"yield #{event.coroutine_id} values={list(event.values)} pc={event.pc}"
    if isinstance(event, CoroutineCompleted):
        if event.error:
            return f"#{event.coroutine_id} error: {event.error}"
        return f"#{event.coroutine_id} completed values={list(event.values)}"
    return str(event)


__all__ = ["format_coroutine_event"]
