"""Errors raised by the Scheme frontend."""


class SchemeSyntaxError(Exception):
    """Raised when Scheme source cannot be tokenized or parsed."""


class SchemeRuntimeError(Exception):
    """Raised when Scheme evaluation fails."""
