"""Compatibility wrapper for relocated jq AST module."""
from haifa_jq.jq_ast import *  # noqa: F401,F403
from haifa_jq.jq_ast import __all__ as _HAIFA_JQ_ALL

__all__ = _HAIFA_JQ_ALL
