from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class DebugInstruction:
    index: int
    opcode: str
    args: list[Any]
    text: str
    debug: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "index": self.index,
            "opcode": self.opcode,
            "args": self.args,
            "text": self.text,
        }
        if self.debug is not None:
            data["debug"] = self.debug
        return data


@dataclass(frozen=True)
class VMDebugSnapshot:
    vm_kind: str
    instructions: list[DebugInstruction]
    pc: int
    registers: dict[str, Any]
    memory_sections: dict[str, Any]
    call_stack: list[Any]
    output: list[Any]
    events: list[Any] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def current_instruction(self) -> DebugInstruction | None:
        if 0 <= self.pc < len(self.instructions):
            return self.instructions[self.pc]
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vm_kind": self.vm_kind,
            "instructions": [instruction.to_dict() for instruction in self.instructions],
            "pc": self.pc,
            "registers": self.registers,
            "memory_sections": self.memory_sections,
            "call_stack": self.call_stack,
            "output": self.output,
            "events": self.events,
            "extra": self.extra,
        }


@runtime_checkable
class VMDebugAdapter(Protocol):
    def snapshot(self) -> VMDebugSnapshot:
        """Return a unified, read-only debugger snapshot for the VM."""


class BytecodeVMDebugAdapter:
    """Expose the existing high-level Haifa BytecodeVM as a debugger snapshot."""

    vm_kind = "bytecode"

    def __init__(self, vm: Any) -> None:
        self.vm = vm

    def snapshot(self) -> VMDebugSnapshot:
        return VMDebugSnapshot(
            vm_kind=self.vm_kind,
            instructions=_instruction_list(self.vm.instructions),
            pc=int(getattr(self.vm, "pc", 0)),
            registers=_snapshot_mapping(getattr(self.vm, "registers", {})),
            memory_sections={
                "stack": _snapshot_value(getattr(self.vm, "stack", [])),
                "arrays": _snapshot_mapping(getattr(self.vm, "arrays", {})),
                "param_stack": _snapshot_value(getattr(self.vm, "param_stack", [])),
                "pending_params": _snapshot_value(
                    getattr(self.vm, "pending_params", [])
                ),
                "upvalues": _snapshot_value(getattr(self.vm, "current_upvalues", [])),
                "emit_stack": _snapshot_value(getattr(self.vm, "emit_stack", [])),
                "try_stack": _snapshot_value(getattr(self.vm, "try_stack", [])),
            },
            call_stack=[
                _bytecode_frame_snapshot(frame)
                for frame in getattr(self.vm, "call_stack", [])
            ],
            output=_snapshot_value(getattr(self.vm, "output", [])),
            events=_snapshot_value(getattr(self.vm, "_event_buffer", [])),
            extra={
                "last_event": _snapshot_value(getattr(self.vm, "last_event", None)),
                "return_value": _snapshot_value(
                    getattr(self.vm, "return_value", None)
                ),
                "last_return": _snapshot_value(getattr(self.vm, "last_return", [])),
                "yield_values": _snapshot_value(
                    getattr(self.vm, "yield_values", [])
                ),
                "awaiting_resume": bool(
                    getattr(self.vm, "awaiting_resume", False)
                ),
                "current_coroutine": _snapshot_value(
                    getattr(self.vm, "current_coroutine", None)
                ),
                "coroutines": _snapshot_value(
                    list(getattr(self.vm, "_coroutine_snapshots", {}).values())
                ),
            },
        )


class ArmV9VMDebugAdapter:
    """Expose HaifaArmV9VM state through the same debugger snapshot contract."""

    vm_kind = "armv9"

    def __init__(self, vm: Any) -> None:
        self.vm = vm

    def snapshot(self) -> VMDebugSnapshot:
        raw = self.vm.snapshot()
        registers = dict(raw["registers"])
        registers["NZCV"] = raw["nzcv"]
        return VMDebugSnapshot(
            vm_kind=self.vm_kind,
            instructions=_instruction_list(self.vm.instructions),
            pc=int(raw["pc"]),
            registers=registers,
            memory_sections={
                "const_pool": raw["memory"].get("const_pool", []),
                "stack": raw["memory"].get("stack", []),
                "heap": raw["memory"].get("heap", {}),
                "globals": raw["memory"].get("globals", {}),
            },
            call_stack=list(raw.get("frames", [])),
            output=list(raw.get("output", [])),
            events=[],
            extra={
                "halted": bool(raw.get("halted", False)),
                "nzcv": raw["nzcv"],
                "frames": list(raw.get("frames", [])),
                "upvalues": list(raw.get("upvalues", [])),
                "param_stack": list(raw.get("param_stack", [])),
                "pending_params": list(raw.get("pending_params", [])),
                "last_return": list(raw.get("last_return", [])),
                "return_value": raw.get("return_value"),
            },
        )


def create_debug_adapter(vm: Any) -> VMDebugAdapter:
    """Pick the built-in debug adapter for a supported Haifa VM instance."""

    if hasattr(vm, "regs") and hasattr(vm, "memory") and hasattr(vm, "nzcv"):
        return ArmV9VMDebugAdapter(vm)
    if hasattr(vm, "registers") and hasattr(vm, "call_stack"):
        return BytecodeVMDebugAdapter(vm)
    raise TypeError(f"unsupported VM type for debug adapter: {type(vm).__name__}")


def _instruction_list(instructions: Sequence[Any]) -> list[DebugInstruction]:
    return [
        DebugInstruction(
            index=index,
            opcode=_opcode_name(instruction),
            args=_snapshot_value(getattr(instruction, "args", [])),
            text=str(instruction),
            debug=_debug_snapshot(getattr(instruction, "debug", None)),
        )
        for index, instruction in enumerate(instructions)
    ]


def _opcode_name(instruction: Any) -> str:
    opcode = getattr(instruction, "opcode", None)
    return str(getattr(opcode, "name", opcode))


def _debug_snapshot(debug: Any) -> dict[str, Any] | None:
    if debug is None:
        return None
    to_dict = getattr(debug, "to_dict", None)
    if callable(to_dict):
        return _snapshot_value(to_dict())
    location = getattr(debug, "location", None)
    data: dict[str, Any] = {}
    if location is not None:
        data["location"] = {
            "file": getattr(location, "file", None),
            "line": getattr(location, "line", None),
            "column": getattr(location, "column", None),
        }
    function_name = getattr(debug, "function_name", None)
    if function_name is not None:
        data["function_name"] = function_name
    return data or _snapshot_value(debug)


def _bytecode_frame_snapshot(frame: Any) -> dict[str, Any]:
    return {
        "return_pc": _snapshot_value(getattr(frame, "return_pc", None)),
        "param_stack": _snapshot_value(getattr(frame, "param_stack", [])),
        "registers": _snapshot_mapping(getattr(frame, "registers", {})),
        "upvalues": _snapshot_value(getattr(frame, "upvalues", [])),
        "pending_params": _snapshot_value(getattr(frame, "pending_params", [])),
        "caller_debug": _debug_snapshot(getattr(frame, "caller_debug", None)),
    }


def _snapshot_mapping(mapping: Mapping[Any, Any]) -> dict[str, Any]:
    return {str(key): _snapshot_value(value) for key, value in mapping.items()}


def _snapshot_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_snapshot_value(item) for item in value]
    if isinstance(value, Mapping):
        return _snapshot_mapping(value)
    if _is_lua_table(value):
        return {
            "type": "lua_table",
            "array": _snapshot_value(getattr(value, "array", [])),
            "map": _snapshot_mapping(getattr(value, "map", {})),
        }
    if is_dataclass(value):
        data = _snapshot_value(asdict(value))
        if isinstance(data, dict):
            data.setdefault("type", value.__class__.__name__)
        return data
    if callable(value):
        return repr(value)
    return repr(value)


def _is_lua_table(value: Any) -> bool:
    return bool(getattr(value, "__lua_table__", False))
