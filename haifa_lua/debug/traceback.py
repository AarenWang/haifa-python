from typing import Sequence

from compiler.vm_errors import VMRuntimeError
from compiler.vm_events import TraceFrame


def format_lua_error(message: str, frame: TraceFrame | None) -> str:
    if frame is None:
        return message
    return f"{frame.file}:{frame.line}: {message}"


def format_traceback(frames: Sequence[TraceFrame]) -> str:
    lines = ["stack traceback:"]
    for frame in frames:
        location = f"{frame.file}:{frame.line}"
        lines.append(f"\t{location}: in function '{frame.function_name}'")
    return "\n".join(lines)


class LuaRuntimeError(VMRuntimeError):
    """Specialized runtime error that formats messages like Lua."""

    def __init__(self, message: str, frames: Sequence[TraceFrame]):
        super().__init__(message, frames)
        top = frames[0] if frames else None
        self.lua_message = format_lua_error(message, top)

    def __str__(self) -> str:
        return self.lua_message


def as_lua_error(error: VMRuntimeError) -> LuaRuntimeError:
    return LuaRuntimeError(str(error), error.frames)


__all__ = ["LuaRuntimeError", "format_lua_error", "format_traceback", "as_lua_error"]
