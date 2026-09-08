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
    """Teaching-friendly report for ARMv9 register allocation."""

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
    intervals: dict[str, tuple[int, int]] = field(default_factory=dict)
    spilled_registers: tuple[str, ...] = ()
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

    @classmethod
    def linear_scan_report(
        cls,
        *,
        allocated_registers: Sequence[str],
        liveness: ArmV9Liveness,
        scan_result: ArmV9LinearScanResult,
    ) -> ArmV9RegisterAllocationReport:
        intervals_dict = {
            name: (it.start, it.end)
            for name, it in sorted(scan_result.intervals.items())
        }
        return cls(
            enabled=True,
            strategy="linear-scan",
            allocated_registers=tuple(allocated_registers),
            virtual_registers=tuple(sorted(liveness.defined_registers)),
            last_use=dict(sorted(liveness.last_use.items())),
            final_register_map=dict(sorted(scan_result.register_map.items())),
            spills=len(scan_result.spilled),
            spilled_registers=tuple(sorted(scan_result.spilled)),
            intervals=intervals_dict,
            notes=[
                "Global linear scan register allocation (Poletto & Sarkar).",
                f"Spilled {len(scan_result.spilled)} virtual register(s) to stack slots.",
            ],
        )

    def readable_text(self) -> str:
        if not self.enabled:
            return "register allocation: disabled (stack-slot-only lowering)"
        if self.strategy == "linear-scan":
            lines = [
                f"register allocation: {self.strategy}",
                f"physical registers: {', '.join(self.allocated_registers)}",
                f"virtual registers: {len(self.virtual_registers)}",
                f"spills: {self.spills}",
            ]
            if self.final_register_map:
                mapping = ", ".join(
                    f"{virtual}->{physical}"
                    for virtual, physical in sorted(self.final_register_map.items())
                )
                lines.append(f"assigned map: {mapping}")
            if self.spilled_registers:
                lines.append(f"spilled registers: {', '.join(self.spilled_registers)}")
            if self.intervals:
                intervals_str = ", ".join(
                    f"{v}:[{start},{end}]"
                    for v, (start, end) in sorted(self.intervals.items())
                )
                lines.append(f"live intervals: {intervals_str}")
            if self.loads_elided or self.stores_elided:
                lines.append(f"loads elided: {self.loads_elided}")
                lines.append(f"stores elided: {self.stores_elided}")
            if self.notes:
                lines.append("notes:")
                lines.extend(f"- {note}" for note in self.notes)
            return "\n".join(lines)

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


@dataclass(frozen=True)
class ArmV9LiveInterval:
    """Live interval for one Haifa virtual register."""

    virtual_register: str
    start: int
    end: int
    defs: tuple[int, ...] = ()
    uses: tuple[int, ...] = ()
    spill_weight: float = 0.0

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)


@dataclass
class ArmV9LinearScanResult:
    """Result of linear scan register allocation."""

    register_map: dict[str, str] = field(default_factory=dict)
    spilled: tuple[str, ...] = ()
    intervals: dict[str, ArmV9LiveInterval] = field(default_factory=dict)
    allocatable_registers: tuple[str, ...] = ()


def compute_armv9_live_intervals(
    instructions: Sequence[Instruction],
    liveness: ArmV9Liveness | None = None,
) -> list[ArmV9LiveInterval]:
    if liveness is None:
        liveness = analyze_armv9_liveness(instructions)

    defs_map: dict[str, list[int]] = {reg: [] for reg in liveness.defined_registers}
    uses_map: dict[str, list[int]] = {reg: [] for reg in liveness.defined_registers}
    label_indices: dict[str, int] = {}

    for idx, inst in enumerate(instructions):
        if inst.opcode == Opcode.LABEL and inst.args:
            label_indices[str(inst.args[0])] = idx
        for reg in _string_args(_defined_values(inst)):
            if reg in defs_map:
                defs_map[reg].append(idx)
        for reg in _string_args(_used_values(inst)):
            if reg in uses_map:
                uses_map[reg].append(idx)

    # Detect backward branches (loops) to extend lifetimes
    backward_jumps: list[tuple[int, int]] = []
    for idx, inst in enumerate(instructions):
        if inst.opcode in {Opcode.JMP, Opcode.JZ, Opcode.JNZ} and inst.args:
            target_label = str(inst.args[-1] if inst.opcode != Opcode.JMP else inst.args[0])
            if target_label in label_indices:
                target_idx = label_indices[target_label]
                if target_idx <= idx:
                    backward_jumps.append((target_idx, idx))

    intervals: list[ArmV9LiveInterval] = []
    for reg in sorted(liveness.defined_registers):
        reg_defs = defs_map.get(reg, [])
        reg_uses = uses_map.get(reg, [])
        start = min(reg_defs) if reg_defs else (min(reg_uses) if reg_uses else 0)
        end = max(reg_uses) if reg_uses else start

        for loop_start, loop_end in backward_jumps:
            if start <= loop_end and any(u >= loop_start for u in reg_uses):
                end = max(end, loop_end)

        use_count = len(reg_uses)
        interval_len = max(1, end - start + 1)
        spill_weight = round(use_count / interval_len, 4)

        intervals.append(
            ArmV9LiveInterval(
                virtual_register=reg,
                start=start,
                end=end,
                defs=tuple(sorted(reg_defs)),
                uses=tuple(sorted(reg_uses)),
                spill_weight=spill_weight,
            )
        )

    intervals.sort(key=lambda it: (it.start, it.end, it.virtual_register))
    return intervals


class ArmV9LinearScanAllocator:
    """Linear scan register allocator (Poletto & Sarkar 1999)."""

    def __init__(
        self,
        allocatable_registers: Sequence[str] = ("X12", "X13", "X14", "X15"),
    ) -> None:
        self.allocatable_registers = tuple(allocatable_registers)

    def allocate(
        self,
        intervals: Sequence[ArmV9LiveInterval],
        *,
        instructions: Sequence[Instruction] | None = None,
    ) -> ArmV9LinearScanResult:
        call_crossing: set[str] = set()
        if instructions:
            call_indices = {
                idx
                for idx, inst in enumerate(instructions)
                if inst.opcode in {Opcode.CALL_VALUE, Opcode.CALL}
            }
            for it in intervals:
                if any(it.start < call_idx <= it.end for call_idx in call_indices):
                    call_crossing.add(it.virtual_register)

        sorted_intervals = sorted(
            intervals, key=lambda it: (it.start, it.end, it.virtual_register)
        )
        active: list[tuple[ArmV9LiveInterval, str]] = []
        free_registers: list[str] = sorted(list(self.allocatable_registers))
        register_map: dict[str, str] = {}
        spilled: list[str] = sorted(list(call_crossing))

        for interval in sorted_intervals:
            if interval.virtual_register in call_crossing:
                continue

            # 1. Expire old intervals
            new_active: list[tuple[ArmV9LiveInterval, str]] = []
            for active_it, phys_reg in active:
                if active_it.end < interval.start:
                    free_registers.append(phys_reg)
                else:
                    new_active.append((active_it, phys_reg))
            active = new_active
            free_registers.sort()

            # 2. Check register availability
            if not free_registers:
                # Active is full: choose candidate with furthest end point to spill
                candidate = max(
                    active,
                    key=lambda pair: (
                        pair[0].end,
                        -pair[0].spill_weight,
                        pair[0].virtual_register,
                    ),
                )
                cand_it, cand_reg = candidate
                if cand_it.end > interval.end or (
                    cand_it.end == interval.end
                    and cand_it.spill_weight < interval.spill_weight
                ):
                    active.remove(candidate)
                    register_map.pop(cand_it.virtual_register, None)
                    spilled.append(cand_it.virtual_register)
                    register_map[interval.virtual_register] = cand_reg
                    active.append((interval, cand_reg))
                    active.sort(key=lambda pair: pair[0].end)
                else:
                    spilled.append(interval.virtual_register)
            else:
                phys_reg = free_registers.pop(0)
                register_map[interval.virtual_register] = phys_reg
                active.append((interval, phys_reg))
                active.sort(key=lambda pair: pair[0].end)

        return ArmV9LinearScanResult(
            register_map=register_map,
            spilled=tuple(sorted(set(spilled))),
            intervals={it.virtual_register: it for it in intervals},
            allocatable_registers=self.allocatable_registers,
        )


def allocate_armv9_linear_scan(
    instructions: Sequence[Instruction],
    *,
    allocatable_registers: Sequence[str] = ("X12", "X13", "X14", "X15"),
    liveness: ArmV9Liveness | None = None,
) -> ArmV9LinearScanResult:
    if liveness is None:
        liveness = analyze_armv9_liveness(instructions)
    intervals = compute_armv9_live_intervals(instructions, liveness)
    allocator = ArmV9LinearScanAllocator(allocatable_registers)
    return allocator.allocate(intervals, instructions=instructions)


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
