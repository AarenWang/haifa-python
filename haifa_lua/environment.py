from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .table import LuaTable


class EnvironmentTable(LuaTable):
    """Lua table that keeps a LuaEnvironment in sync with global mutations."""

    __slots__ = ("_env", "_syncing")

    def __init__(self, env: "LuaEnvironment", base: Optional[LuaTable] = None) -> None:
        if base is not None:
            super().__init__(base.array, base.map)
        else:
            super().__init__()
        self._env = env
        self._syncing = False

    def raw_set(self, key: Any, value: Any) -> None:  # noqa: ANN401 - Lua style
        super().raw_set(key, value)
        if self._syncing:
            return
        if isinstance(key, str):
            if value is None:
                self._env._globals.pop(key, None)
            else:
                self._env._globals[key] = value
            active_vm = self._env._active_vm
            if active_vm is not None:
                reg = f"G_{key}"
                if value is None:
                    active_vm.registers.pop(reg, None)
                else:
                    active_vm.registers[reg] = value

    def set_from_env(self, key: str, value: Any) -> None:
        self._syncing = True
        try:
            super().raw_set(key, value)
        finally:
            self._syncing = False


@dataclass
class LuaMultiReturn:
    values: Sequence[Any]


class BuiltinFunction:
    __slots__ = ("name", "func", "doc", "__lua_builtin__", "allow_yield", "yield_probe")

    def __init__(
        self,
        name: str,
        func: Callable[[Sequence[Any], Any], Any],
        doc: str = "",
        *,
        allow_yield: bool = False,
        yield_probe: bool = False,
    ) -> None:
        self.name = name
        self.func = func
        self.doc = doc
        self.__lua_builtin__ = True  # marker for the VM
        self.allow_yield = allow_yield
        self.yield_probe = yield_probe

    def __call__(self, args: Sequence[Any], vm: Any) -> Any:  # noqa: ANN401 - VM is dynamic
        return self.func(args, vm)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<BuiltinFunction {self.name}>"


class LuaEnvironment:
    def __init__(
        self,
        initial: Optional[Mapping[str, Any]] = None,
        *,
        global_table: Optional[LuaTable] = None,
    ) -> None:
        self._globals: Dict[str, Any] = {}
        self._global_table = EnvironmentTable(self, global_table)
        self._active_vm = None
        self._stdlib_ready = False
        self.module_system = None  # type: ignore[attr-defined]
        self._bind_environment_table()
        if initial:
            self.merge(initial)

    def register(self, name: str, value: Any) -> None:
        self._set_global(name, value)

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
            self._set_global(namespace, table)
        for key, value in members.items():
            table.raw_set(key, value)

    def merge(self, other: Mapping[str, Any]) -> None:
        for key, value in other.items():
            self._set_global(key, value)

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._globals)

    def to_vm_registers(self) -> Dict[str, Any]:
        return {f"G_{k}": v for k, v in self._globals.items()}

    def sync_from_vm(self, registers: Mapping[str, Any]) -> None:
        for key, value in registers.items():
            if key.startswith("G_"):
                name = key[2:]
                self._globals[name] = value
                self._global_table.set_from_env(name, value)

    def clear(self) -> None:
        self._globals.clear()
        self._global_table = EnvironmentTable(self)
        self._bind_environment_table()

    def __getitem__(self, name: str) -> Any:
        return self._globals[name]

    def __setitem__(self, name: str, value: Any) -> None:
        self._set_global(name, value)

    def __contains__(self, name: str) -> bool:
        return name in self._globals

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"LuaEnvironment({self._globals!r})"

    # ------------------------------------------------------------------ helpers
    def _set_global(self, name: str, value: Any) -> None:
        if value is None:
            self._globals.pop(name, None)
        else:
            self._globals[name] = value
        self._global_table.set_from_env(name, value)

    def _bind_environment_table(self) -> None:
        self._global_table.set_from_env("_G", self._global_table)
        self._global_table.set_from_env("_ENV", self._global_table)
        self._globals.setdefault("_G", self._global_table)
        self._globals.setdefault("_ENV", self._global_table)

    def global_table(self) -> LuaTable:
        return self._global_table

    def bind_vm(self, vm: Any) -> None:  # noqa: ANN401 - vm is dynamic
        self._active_vm = vm

    def unbind_vm(self) -> None:
        self._active_vm = None

    @property
    def stdlib_ready(self) -> bool:
        return self._stdlib_ready

    def mark_stdlib_ready(self) -> None:
        self._stdlib_ready = True


__all__ = [
    "BuiltinFunction",
    "EnvironmentTable",
    "LuaEnvironment",
    "LuaMultiReturn",
]
