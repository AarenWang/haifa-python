from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .table import LuaTable


@dataclass
class LuaMultiReturn:
    values: Sequence[Any]


class BuiltinFunction:
    __slots__ = ("name", "func", "doc", "__lua_builtin__")

    def __init__(self, name: str, func: Callable[[Sequence[Any], Any], Any], doc: str = "") -> None:
        self.name = name
        self.func = func
        self.doc = doc
        self.__lua_builtin__ = True  # marker for the VM

    def __call__(self, args: Sequence[Any], vm: Any) -> Any:  # noqa: ANN401 - VM is dynamic
        return self.func(args, vm)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<BuiltinFunction {self.name}>"


class LuaEnvironment:
    def __init__(self, initial: Optional[Mapping[str, Any]] = None) -> None:
        self._globals: Dict[str, Any] = {}
        if initial:
            self.merge(initial)

    def register(self, name: str, value: Any) -> None:
        self._globals[name] = value

    def register_library(self, namespace: str, members: Mapping[str, Any]) -> None:
        if not namespace:
            for key, value in members.items():
                self.register(key, value)
            return
        existing = self._globals.get(namespace)
        if isinstance(existing, LuaTable):
            table = existing
        else:
            table = LuaTable()
            self._globals[namespace] = table
        for key, value in members.items():
            table.raw_set(key, value)

    def merge(self, other: Mapping[str, Any]) -> None:
        for key, value in other.items():
            self.register(key, value)

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._globals)

    def to_vm_registers(self) -> Dict[str, Any]:
        return {f"G_{k}": v for k, v in self._globals.items()}

    def sync_from_vm(self, registers: Mapping[str, Any]) -> None:
        for key, value in registers.items():
            if key.startswith("G_"):
                self._globals[key[2:]] = value

    def clear(self) -> None:
        self._globals.clear()

    def __getitem__(self, name: str) -> Any:
        return self._globals[name]

    def __setitem__(self, name: str, value: Any) -> None:
        self.register(name, value)

    def __contains__(self, name: str) -> bool:
        return name in self._globals

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"LuaEnvironment({self._globals!r})"


__all__ = ["BuiltinFunction", "LuaEnvironment", "LuaMultiReturn"]
