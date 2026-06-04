"""Scheme runtime helpers for executing bytecode on BytecodeVM."""

from __future__ import annotations

import io
from typing import Any, Sequence

from compiler.bytecode_vm import BytecodeVM
from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.reader import Symbol
from haifa_scheme.stdlib import BuiltinContext, BuiltinFunction, create_global_environment
from haifa_scheme.values import TextPort


def mangle_global_name(name: str) -> str:
    return f"G_SCHEME_{name}"


class SchemeBuiltinAdapter:
    """Adapts Scheme builtins to the VM's builtin calling convention."""

    __lua_builtin__ = True

    def __init__(self, builtin: BuiltinFunction, runtime: "SchemeVMRuntime") -> None:
        self.builtin = builtin
        self.runtime = runtime

    def __call__(self, args: Sequence[object], vm: BytecodeVM) -> object:
        return self.builtin(args, self.runtime.build_builtin_context(vm))

    def __repr__(self) -> str:
        return f"<SchemeBuiltinAdapter {self.builtin.name}>"


class SchemeVMRuntime:
    def __init__(
        self,
        environment: Environment | None = None,
        *,
        input_port: TextPort | None = None,
        output_port: TextPort | None = None,
    ) -> None:
        self.environment = environment if environment is not None else create_global_environment()
        self.input_port = input_port or TextPort.input(io.StringIO(""), "current-input")
        self.output_port = output_port or TextPort.output(io.StringIO(), "current-output")
        self._builtin_adapters: dict[str, SchemeBuiltinAdapter] = {}

    def to_vm_registers(self) -> dict[str, object]:
        registers: dict[str, object] = {}
        for name, value in self._flatten_environment_values().items():
            if isinstance(value, BuiltinFunction):
                registers[mangle_global_name(str(name))] = self._get_builtin_adapter(value)
            else:
                registers[mangle_global_name(str(name))] = value
        return registers

    def install_into_vm(self, vm: BytecodeVM) -> BytecodeVM:
        vm.registers.update(self.to_vm_registers())
        vm.scheme_runtime = self
        return vm

    def create_vm(self, instructions: Sequence[object]) -> BytecodeVM:
        vm = BytecodeVM(list(instructions))
        self.install_into_vm(vm)
        return vm

    def sync_from_vm(self, vm: BytecodeVM) -> None:
        for name, value in vm.registers.items():
            if not name.startswith("G_SCHEME_"):
                continue
            if isinstance(value, SchemeBuiltinAdapter):
                continue
            symbol_name = name[len("G_SCHEME_") :]
            self.environment.define(Symbol(symbol_name), value)

    def build_builtin_context(self, vm: BytecodeVM) -> BuiltinContext:
        return BuiltinContext(
            apply_func=lambda procedure, args: self._apply_func(vm, procedure, args),
            is_procedure_func=self._is_procedure,
            call_cc_func=self._call_cc_unsupported,
            current_input_port=self.input_port,
            current_output_port=self.output_port,
        )

    def _apply_func(self, vm: BytecodeVM, procedure: Any, args: Sequence[Any]) -> Any:
        callable_value = procedure
        if isinstance(procedure, BuiltinFunction):
            callable_value = self._get_builtin_adapter(procedure)
        values = vm.call_callable(callable_value, list(args))
        return values[0] if values else None

    def _is_procedure(self, value: Any) -> bool:
        return isinstance(value, (BuiltinFunction, SchemeBuiltinAdapter)) or getattr(
            value, "__lua_builtin__", False
        ) or callable(value) or (isinstance(value, dict) and "label" in value)

    @staticmethod
    def _call_cc_unsupported(procedure: Any) -> Any:
        raise SchemeRuntimeError("call/cc is not supported by the Scheme VM backend yet")

    def _get_builtin_adapter(self, builtin: BuiltinFunction) -> SchemeBuiltinAdapter:
        adapter = self._builtin_adapters.get(builtin.name)
        if adapter is None:
            adapter = SchemeBuiltinAdapter(builtin, self)
            self._builtin_adapters[builtin.name] = adapter
        return adapter

    def _flatten_environment_values(self) -> dict[Symbol, object]:
        chain: list[Environment] = []
        current: Environment | None = self.environment
        while current is not None:
            chain.append(current)
            current = current.parent

        flattened: dict[Symbol, object] = {}
        for environment in reversed(chain):
            flattened.update(environment.values)
        return flattened


__all__ = ["SchemeBuiltinAdapter", "SchemeVMRuntime", "mangle_global_name"]
