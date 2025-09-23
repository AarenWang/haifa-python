"""Lua interpreter package built on top of the core VM."""

from .runtime import run_script, run_source

__all__ = ["run_script", "run_source"]
