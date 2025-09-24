from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Sequence, TYPE_CHECKING

from compiler.bytecode_vm import BytecodeVM
from compiler.vm_errors import VMRuntimeError
from compiler.vm_events import (
    CoroutineCompleted,
    CoroutineCreated,
    CoroutineResumed,
    CoroutineYielded,
)

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from .environment import LuaEnvironment

from .debug import as_lua_error

class CoroutineError(RuntimeError):
    pass


@dataclass
class ResumeResult:
    success: bool
    values: List[object]


class LuaCoroutine:
    __slots__ = (
        "closure",
        "base_vm",
        "instructions",
        "env",
        "vm",
        "status",
        "started",
        "awaiting_resume",
        "last_yield",
        "last_error",
        "coroutine_id",
        "debug_name",
        "last_resume_args",
    )

    def __init__(self, closure: dict, base_vm: BytecodeVM) -> None:
        if not isinstance(closure, dict) or "label" not in closure:
            raise CoroutineError("coroutine.create expects a function or closure")
        self.closure = closure
        self.base_vm = base_vm
        self.instructions = base_vm.instructions
        self.env: LuaEnvironment | None = getattr(base_vm, "lua_env", None)
        self.vm: BytecodeVM | None = None
        self.status = "suspended"
        self.started = False
        self.awaiting_resume = False
        self.last_yield: List[object] = []
        self.last_error: str | None = None
        self.coroutine_id = base_vm.allocate_coroutine_id()
        self.debug_name = closure.get("debug_name") or closure.get("label")
        self.last_resume_args: List[object] = []
        base_vm.set_coroutine_snapshot(
            self.coroutine_id,
            status=self.status,
            last_yield=self.last_yield,
            last_error=self.last_error,
        )
        parent_id = getattr(base_vm.current_coroutine, "coroutine_id", None)
        base_vm.emit_event(
            CoroutineCreated(
                coroutine_id=self.coroutine_id,
                parent_id=parent_id,
                function_name=self.debug_name,
                args=(),
                timestamp=time.time(),
            )
        )

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
        merged_globals: dict[str, object] = {}
        if self.env is not None:
            merged_globals.update(self.env.to_vm_registers())
        for key, value in self.base_vm.registers.items():
            if key.startswith("G_"):
                merged_globals[key] = value

        if not merged_globals:
            return

        for key in list(vm.registers.keys()):
            if key.startswith("G_"):
                del vm.registers[key]
        vm.registers.update(merged_globals)

    def _sync_globals(self, vm: BytecodeVM) -> None:
        if self.env is None:
            return
        self.env.sync_from_vm(vm.registers)

    def _set_yield(self, values: Iterable[object]) -> None:
        self.last_yield = list(values)
        self.awaiting_resume = True
        self._update_snapshot()

    def _set_result(self, values: Iterable[object]) -> None:
        self.last_yield = list(values)
        self.awaiting_resume = False
        if self.vm:
            self.vm.current_coroutine = None
        self._update_snapshot()

    def _update_snapshot(self) -> None:
        registers = None
        upvalues = None
        call_stack = None
        current_pc = None
        if self.vm is not None:
            try:
                vm_snapshot = self.vm.snapshot_state()
            except Exception:  # pragma: no cover - snapshot best effort
                registers = dict(self.vm.registers)
                call_stack = []
                current_pc = getattr(self.vm, "pc", None)
            else:
                registers = vm_snapshot.registers
                call_stack = vm_snapshot.call_stack
                current_pc = vm_snapshot.pc
            upvalues = list(getattr(self.vm, "current_upvalues", []))
        else:
            upvalues = list(self.closure.get("upvalues", []))

        self.base_vm.set_coroutine_snapshot(
            self.coroutine_id,
            status=self.status,
            last_yield=self.last_yield,
            last_error=self.last_error,
            function_name=self.debug_name,
            last_resume_args=self.last_resume_args,
            registers=registers,
            upvalues=upvalues,
            call_stack=call_stack,
            current_pc=current_pc,
        )

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
            self.last_resume_args = list(args)
            vm.current_coroutine = self
            self._update_snapshot()
            self.base_vm.emit_event(
                CoroutineResumed(
                    coroutine_id=self.coroutine_id,
                    args=list(self.last_resume_args),
                    timestamp=time.time(),
                )
            )
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
        except VMRuntimeError as exc:
            lua_error = as_lua_error(exc)
            self.status = "dead"
            self.last_error = str(lua_error)
            if vm.current_coroutine is self:
                vm.current_coroutine = None
            self._update_snapshot()
            self.base_vm.emit_event(
                CoroutineCompleted(
                    coroutine_id=self.coroutine_id,
                    values=(),
                    error=self.last_error,
                    timestamp=time.time(),
                )
            )
            return ResumeResult(False, [self.last_error])

        if vm.last_event == "yield":
            self.status = "suspended"
            self._update_snapshot()
            self.base_vm.emit_event(
                CoroutineYielded(
                    coroutine_id=self.coroutine_id,
                    values=list(self.last_yield),
                    pc=vm.pc,
                    timestamp=time.time(),
                )
            )
            return ResumeResult(True, list(self.last_yield))

        self.status = "dead"
        self._update_snapshot()
        self.base_vm.emit_event(
            CoroutineCompleted(
                coroutine_id=self.coroutine_id,
                values=list(vm.last_return),
                error=None,
                timestamp=time.time(),
            )
        )
        return ResumeResult(True, list(vm.last_return))

    def status_string(self) -> str:
        return self.status

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LuaCoroutine status={self.status}>"


__all__ = ["CoroutineError", "LuaCoroutine", "ResumeResult"]
