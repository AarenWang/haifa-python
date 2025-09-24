from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple, TYPE_CHECKING

from compiler.bytecode_vm import BytecodeVM

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from .environment import LuaEnvironment


class CoroutineError(RuntimeError):
    pass


@dataclass
class ResumeResult:
    success: bool
    values: List[object]


class LuaCoroutine:
    __slots__ = (
        "closure",
        "instructions",
        "env",
        "vm",
        "status",
        "started",
        "awaiting_resume",
        "last_yield",
        "last_error",
    )

    def __init__(self, closure: dict, base_vm: BytecodeVM) -> None:
        if not isinstance(closure, dict) or "label" not in closure:
            raise CoroutineError("coroutine.create expects a function or closure")
        self.closure = closure
        self.instructions = base_vm.instructions
        self.env: LuaEnvironment | None = getattr(base_vm, "lua_env", None)
        self.vm: BytecodeVM | None = None
        self.status = "suspended"
        self.started = False
        self.awaiting_resume = False
        self.last_yield: List[object] = []
        self.last_error: str | None = None

    # ------------------------------------------------------------------ helpers
    def _ensure_vm(self) -> BytecodeVM:
        if self.vm is None:
            vm = BytecodeVM(self.instructions)
            vm.index_labels()
            label = self.closure["label"]
            vm.pc = vm.labels[label]
            vm.current_upvalues = list(self.closure.get("upvalues", []))
            vm.lua_env = self.env
            vm.current_coroutine = self
            self.vm = vm
        return self.vm

    def _apply_globals(self, vm: BytecodeVM) -> None:
        if self.env is None:
            return
        globals_snapshot = self.env.to_vm_registers()
        for key in list(vm.registers.keys()):
            if key.startswith("G_"):
                del vm.registers[key]
        vm.registers.update(globals_snapshot)

    def _sync_globals(self, vm: BytecodeVM) -> None:
        if self.env is None:
            return
        self.env.sync_from_vm(vm.registers)

    def _set_yield(self, values: Iterable[object]) -> None:
        self.last_yield = list(values)
        self.awaiting_resume = True

    def _set_result(self, values: Iterable[object]) -> None:
        self.last_yield = list(values)
        self.awaiting_resume = False
        if self.vm:
            self.vm.current_coroutine = None

    # ------------------------------------------------------------------ public API
    def resume(self, args: Sequence[object]) -> ResumeResult:
        if self.status == "dead":
            return ResumeResult(False, ["cannot resume dead coroutine"])
        if self.status == "running":
            return ResumeResult(False, ["coroutine is already running"])

        vm = self._ensure_vm()
        self._apply_globals(vm)

        try:
            self.status = "running"
            vm.current_coroutine = self
            if not self.started:
                vm.param_stack = list(args)
                vm.pending_params = []
                vm.current_upvalues = list(self.closure.get("upvalues", []))
                self.started = True
            else:
                vm.prepare_resume(args)
            vm.yield_values = []
            vm.awaiting_resume = False
            vm.run(stop_on_yield=True)
            self._sync_globals(vm)
        except RuntimeError as exc:
            self.status = "dead"
            self.last_error = str(exc)
            if vm.current_coroutine is self:
                vm.current_coroutine = None
            return ResumeResult(False, [self.last_error])

        if vm.last_event == "yield":
            self.status = "suspended"
            return ResumeResult(True, list(self.last_yield))

        self.status = "dead"
        return ResumeResult(True, list(vm.last_return))

    def status_string(self) -> str:
        return self.status

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LuaCoroutine status={self.status}>"


__all__ = ["CoroutineError", "LuaCoroutine", "ResumeResult"]
