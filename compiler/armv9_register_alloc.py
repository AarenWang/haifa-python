from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .bytecode import Instruction, Opcode


@dataclass(frozen=True)
class ArmV9Liveness:
    """Small liveness summary for Haifa virtual registers."""

    defined_registers: frozenset[str]
    uses_by_index: dict[int, tuple[str, ...]]
    defs_by_index: dict[int, tuple[str, ...]]
    last_use: dict[str, int]

    def is_virtual_register(self, value: Any) -> bool:
        return isinstance(value, str) and value in self.defined_registers


@dataclass
class ArmV9RegisterAllocationReport:
    """Teaching-friendly report for the optional ARMv9 register cache."""

    enabled: bool = False
    strategy: str = "stack-slot-only"
    allocated_registers: tuple[str, ...] = ()
    virtual_registers: tuple[str, ...] = ()
    last_use: dict[str, int] = field(default_factory=dict)
    final_register_map: dict[str, str] = field(default_factory=dict)
    loads_elided: int = 0
    stores_elided: int = 0
    spills: int = 0
    flushes: int = 0
    max_cached_registers: int = 0
    notes: list[str] = field(default_factory=list)

    @classmethod
    def disabled(cls) -> ArmV9RegisterAllocationReport:
        return cls()

    @classmethod
    def enabled_report(
        cls,
        *,
        allocated_registers: Sequence[str],
        liveness: ArmV9Liveness,
    ) -> ArmV9RegisterAllocationReport:
        return cls(
            enabled=True,
            strategy="basic-block-register-cache",
            allocated_registers=tuple(allocated_registers),
            virtual_registers=tuple(sorted(liveness.defined_registers)),
            last_use=dict(sorted(liveness.last_use.items())),
            notes=[
                "Caches Haifa virtual registers in ARMv9 registers inside a basic block.",
                "Flushes dirty cached registers at labels, branches, calls, returns, and HALT.",
            ],
        )

    def readable_text(self) -> str:
        if not self.enabled:
            return "register allocation: disabled (stack-slot-only lowering)"
        lines = [
            f"register allocation: {self.strategy}",
            f"physical registers: {', '.join(self.allocated_registers)}",
            f"virtual registers: {len(self.virtual_registers)}",
            f"loads elided: {self.loads_elided}",
            f"stores elided: {self.stores_elided}",
            f"spills: {self.spills}",
            f"flushes: {self.flushes}",
            f"max cached registers: {self.max_cached_registers}",
        ]
        if self.final_register_map:
            mapping = ", ".join(
                f"{virtual}->{physical}"
                for virtual, physical in sorted(self.final_register_map.items())
            )
            lines.append(f"final cache map: {mapping}")
        if self.notes:
            lines.append("notes:")
            lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines)


def analyze_armv9_liveness(instructions: Sequence[Instruction]) -> ArmV9Liveness:
    defined_registers: set[str] = set()
    defs_by_index: dict[int, tuple[str, ...]] = {}

    for index, instruction in enumerate(instructions):
        defs = tuple(_string_args(_defined_values(instruction)))
        if defs:
            defs_by_index[index] = defs
            defined_registers.update(defs)

    uses_by_index: dict[int, tuple[str, ...]] = {}
    last_use: dict[str, int] = {}
    frozen_defs = frozenset(defined_registers)
    for index, instruction in enumerate(instructions):
        uses = tuple(
            value
            for value in _string_args(_used_values(instruction))
            if value in frozen_defs
        )
        if uses:
            uses_by_index[index] = uses
            for value in uses:
                last_use[value] = index

    return ArmV9Liveness(
        defined_registers=frozen_defs,
        uses_by_index=uses_by_index,
        defs_by_index=defs_by_index,
        last_use=last_use,
    )


def _string_args(values: Sequence[Any]) -> tuple[str, ...]:
    return tuple(value for value in values if isinstance(value, str))


def _defined_values(instruction: Instruction) -> tuple[Any, ...]:
    opcode = instruction.opcode
    args = instruction.args
    if opcode in {
        Opcode.LOAD_IMM,
        Opcode.LOAD_CONST,
        Opcode.MOV,
        Opcode.ADD,
        Opcode.SUB,
        Opcode.MUL,
        Opcode.EQ,
        Opcode.LT,
        Opcode.GT,
        Opcode.TABLE_NEW,
        Opcode.TABLE_GET,
        Opcode.MAKE_CELL,
        Opcode.CELL_GET,
        Opcode.CLOSURE,
        Opcode.BIND_UPVALUE,
        Opcode.ARG,
        Opcode.VARARG,
        Opcode.VARARG_FIRST,
        Opcode.LIST_GET,
        Opcode.RESULT,
        Opcode.RESULT_LIST,
    }:
        return tuple(args[:1])
    if opcode == Opcode.RESULT_MULTI:
        return tuple(args)
    return ()


def _used_values(instruction: Instruction) -> tuple[Any, ...]:
    opcode = instruction.opcode
    args = instruction.args
    if opcode == Opcode.MOV:
        return tuple(args[1:2])
    if opcode in {Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.EQ, Opcode.LT, Opcode.GT}:
        return tuple(args[1:3])
    if opcode == Opcode.TABLE_SET:
        return tuple(args[:3])
    if opcode == Opcode.TABLE_GET:
        return tuple(args[1:3])
    if opcode == Opcode.MAKE_CELL:
        return tuple(args[1:2])
    if opcode == Opcode.CELL_GET:
        return tuple(args[1:2])
    if opcode == Opcode.CELL_SET:
        return tuple(args[:2])
    if opcode == Opcode.CLOSURE:
        return tuple(args[2:])
    if opcode in {Opcode.PARAM, Opcode.PARAM_EXPAND, Opcode.CALL_VALUE, Opcode.RETURN}:
        return tuple(args[:1])
    if opcode in {Opcode.VARARG_FIRST, Opcode.LIST_GET}:
        return tuple(args[1:])
    if opcode == Opcode.RETURN_MULTI:
        return tuple(args)
    if opcode in {Opcode.JZ, Opcode.JNZ, Opcode.PRINT}:
        return tuple(args[:1])
    return ()
