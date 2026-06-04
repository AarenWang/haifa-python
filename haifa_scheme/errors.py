"""Errors raised by the Scheme frontend."""


class SchemeSyntaxError(Exception):
    """Raised when Scheme source cannot be tokenized or parsed."""


class SchemeRuntimeError(Exception):
    """Raised when Scheme evaluation fails."""


class SchemeVMRuntimeError(SchemeRuntimeError):
    def __init__(self, message: str, *, frames: list[object] | None = None):
        super().__init__(message)
        self.frames = list(frames or [])


__all__ = ["SchemeRuntimeError", "SchemeSyntaxError", "SchemeVMRuntimeError"]
