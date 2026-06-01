"""Lexical environments for Scheme evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.reader import Symbol


@dataclass
class Environment:
    """A lexical scope with an optional parent scope."""

    values: dict[Symbol, Any] = field(default_factory=dict)
    parent: "Environment | None" = None

    def define(self, name: Symbol, value: Any) -> None:
        self.values[name] = value

    def lookup(self, name: Symbol) -> Any:
        environment = self._find(name)
        if environment is None:
            raise SchemeRuntimeError(f"unbound symbol: {name}")
        return environment.values[name]

    def _find(self, name: Symbol) -> "Environment | None":
        if name in self.values:
            return self
        if self.parent is not None:
            return self.parent._find(name)
        return None
