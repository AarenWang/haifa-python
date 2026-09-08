from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .armv9_bytecode import ArmV9Debug, ArmV9Instruction, ArmV9Opcode, armv9_inst
from .armv9_register_alloc import (
    ArmV9LinearScanAllocator,
    ArmV9LinearScanResult,
    ArmV9LiveInterval,
    ArmV9Liveness,
    ArmV9RegisterAllocationReport,
    allocate_armv9_linear_scan,
    analyze_armv9_liveness,
    compute_armv9_live_intervals,
)
from .bytecode import Instruction, Opcode


@dataclass(frozen=True)
class ArmV9LoweringResult:
    instructions: list[ArmV9Instruction]
    const_pool: list[Any] = field(default_factory=list)
    stack_slots: dict[str, int] = field(default_factory=dict)
    allocation_report: ArmV9RegisterAllocationReport = field(
        default_factory=ArmV9RegisterAllocationReport.disabled
    )


class ArmV9Lowerer:
    """Conservative lowering from Haifa high-level bytecode to HaifaArmV9VM."""

    SCRATCH0 = "X9"
    SCRATCH1 = "X10"
    SCRATCH2 = "X11"
    SCRATCH_REGISTERS = ("X9", "X10", "X11", "X12", "X13", "X14", "X15")
    ALLOCATABLE_REGISTERS = ("X12", "X13", "X14", "X15")

    def __init__(
        self,
        *,
        optimize_registers: bool = False,
        strategy: str = "basic-block-cache",
    ) -> None:
        if strategy not in {"basic-block-cache", "linear-scan"}:
            raise ValueError(f"unknown register allocation strategy: {strategy}")
        if strategy == "linear-scan":
            optimize_registers = True
        self.optimize_registers = optimize_registers
        self.strategy = strategy
        self.instructions: list[ArmV9Instruction] = []
        self.const_pool: list[Any] = []
        self.stack_slots: dict[str, int] = {}
        self.allocation_report = ArmV9RegisterAllocationReport.disabled()
        self._liveness: ArmV9Liveness | None = None
        self._scan_result: ArmV9LinearScanResult | None = None
        self._current_index = -1
        self._register_cache: dict[str, str] = {}
        self._register_owner: dict[str, str] = {}
        self._dirty_registers: set[str] = set()

    @classmethod
    def lower(
        cls,
        instructions: Sequence[Instruction],
        *,
        optimize_registers: bool = False,
        strategy: str = "basic-block-cache",
    ) -> ArmV9LoweringResult:
        lowerer = cls(optimize_registers=optimize_registers, strategy=strategy)
        lowerer._lower_program(instructions)
        return ArmV9LoweringResult(
            list(lowerer.instructions),
            list(lowerer.const_pool),
            dict(lowerer.stack_slots),
            lowerer.allocation_report,
        )

    def _lower_program(self, instructions: Sequence[Instruction]) -> None:
        if self.optimize_registers:
            self._liveness = analyze_armv9_liveness(instructions)
            if self.strategy == "linear-scan":
                intervals = compute_armv9_live_intervals(instructions, self._liveness)
                allocator = ArmV9LinearScanAllocator(self.ALLOCATABLE_REGISTERS)
                self._scan_result = allocator.allocate(
                    intervals, instructions=instructions
                )
                self.allocation_report = ArmV9RegisterAllocationReport.linear_scan_report(
                    allocated_registers=self.ALLOCATABLE_REGISTERS,
                    liveness=self._liveness,
                    scan_result=self._scan_result,
                )
            else:
                self.allocation_report = ArmV9RegisterAllocationReport.enabled_report(
                    allocated_registers=self.ALLOCATABLE_REGISTERS,
                    liveness=self._liveness,
                )
        for index, instruction in enumerate(instructions):
            self._current_index = index
            if (
                self.optimize_registers
                and self.strategy == "basic-block-cache"
                and instruction.opcode == Opcode.LABEL
            ):
                self._flush_register_cache(instruction, reason="label")
            self._lower_instruction(instruction)
            if self.optimize_registers and self.strategy == "basic-block-cache":
                self._expire_dead_registers()
        if self.optimize_registers:
            if self.strategy == "basic-block-cache":
                self._flush_register_cache(
                    instructions[-1] if instructions else Instruction(Opcode.HALT, []),
                    reason="program end",
                )
                self.allocation_report.final_register_map = dict(self._register_cache)

    def _reg_or_load(self, source: Instruction, operand: Any, scratch: str) -> str:
        if self.optimize_registers and self._is_virtual_register(operand):
            virtual_register = str(operand)
            if self.strategy == "linear-scan" and self._scan_result is not None:
                phys = self._scan_result.register_map.get(virtual_register)
                if phys is not None and virtual_register not in self._scan_result.spilled:
                    self.allocation_report.loads_elided += 1
                    return phys
                # Spilled: load into scratch
                self._emit(
                    source,
                    ArmV9Opcode.LDR,
                    scratch,
                    ("FP", self._slot_for(virtual_register)),
                )
                return scratch
            cached = self._register_cache.get(virtual_register)
            if cached is not None:
                self.allocation_report.loads_elided += 1
                return cached
        self._load_operand(source, operand, scratch)
        return scratch

    def _reg_for_def(self, register: str, scratch: str) -> str:
        if (
            self.optimize_registers
            and self.strategy == "linear-scan"
            and self._scan_result is not None
        ):
            phys = self._scan_result.register_map.get(register)
            if phys is not None and register not in self._scan_result.spilled:
                return phys
        return scratch

    def _lower_instruction(self, instruction: Instruction) -> None:
        opcode = instruction.opcode
        args = instruction.args
        if opcode == Opcode.LABEL:
            self._emit(instruction, ArmV9Opcode.LABEL, str(args[0]))
            return
        if opcode == Opcode.LOAD_IMM:
            dst, value = self._expect_args(instruction, 2)
            target = self._reg_for_def(str(dst), self.SCRATCH0)
            self._emit(instruction, ArmV9Opcode.MOVI, target, int(value))
            if target == self.SCRATCH0:
                self._store_register(instruction, str(dst), self.SCRATCH0)
            else:
                self.allocation_report.stores_elided += 1
            return
        if opcode == Opcode.LOAD_CONST:
            dst, value = self._expect_args(instruction, 2)
            const_id = self._add_const(value)
            target = self._reg_for_def(str(dst), self.SCRATCH0)
            self._emit(instruction, ArmV9Opcode.LDRC, target, const_id)
            if target == self.SCRATCH0:
                self._store_register(instruction, str(dst), self.SCRATCH0)
            else:
                self.allocation_report.stores_elided += 1
            return
        if opcode == Opcode.MOV:
            dst, src = self._expect_args(instruction, 2)
            src_reg = self._reg_or_load(instruction, src, self.SCRATCH0)
            target = self._reg_for_def(str(dst), self.SCRATCH0)
            if target != src_reg:
                self._emit(instruction, ArmV9Opcode.MOV, target, src_reg)
            if target == self.SCRATCH0:
                self._store_register(instruction, str(dst), self.SCRATCH0)
            else:
                self.allocation_report.stores_elided += 1
            return
        if opcode in {Opcode.ADD, Opcode.SUB, Opcode.MUL}:
            dst, lhs, rhs = self._expect_args(instruction, 3)
            arm_opcode = {
                Opcode.ADD: ArmV9Opcode.ADD,
                Opcode.SUB: ArmV9Opcode.SUB,
                Opcode.MUL: ArmV9Opcode.MUL,
            }[opcode]
            reg_lhs = self._reg_or_load(instruction, lhs, self.SCRATCH0)
            reg_rhs = self._reg_or_load(instruction, rhs, self.SCRATCH1)
            target = self._reg_for_def(str(dst), self.SCRATCH2)
            self._emit(instruction, arm_opcode, target, reg_lhs, reg_rhs)
            if target == self.SCRATCH2:
                self._store_register(instruction, str(dst), self.SCRATCH2)
            else:
                self.allocation_report.stores_elided += 1
            return
        if opcode in {Opcode.EQ, Opcode.LT, Opcode.GT}:
            dst, lhs, rhs = self._expect_args(instruction, 3)
            condition = {
                Opcode.EQ: "EQ",
                Opcode.LT: "LT",
                Opcode.GT: "GT",
            }[opcode]
            reg_lhs = self._reg_or_load(instruction, lhs, self.SCRATCH0)
            reg_rhs = self._reg_or_load(instruction, rhs, self.SCRATCH1)
            self._emit(instruction, ArmV9Opcode.CMP, reg_lhs, reg_rhs)
            target = self._reg_for_def(str(dst), self.SCRATCH2)
            self._emit(instruction, ArmV9Opcode.CSET, target, condition)
            if target == self.SCRATCH2:
                self._store_register(instruction, str(dst), self.SCRATCH2)
            else:
                self.allocation_report.stores_elided += 1
            return
        if opcode == Opcode.TABLE_NEW:
            (dst,) = self._expect_args(instruction, 1)
            self._emit(instruction, ArmV9Opcode.NEW_TABLE, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.TABLE_SET:
            table, key, value = self._expect_args(instruction, 3)
            self._load_operand(instruction, table, self.SCRATCH0)
            self._load_operand(instruction, key, self.SCRATCH1)
            self._load_operand(instruction, value, self.SCRATCH2)
            self._emit(
                instruction,
                ArmV9Opcode.TABLE_SET,
                self.SCRATCH0,
                self.SCRATCH1,
                self.SCRATCH2,
            )
            return
        if opcode == Opcode.TABLE_GET:
            dst, table, key = self._expect_args(instruction, 3)
            self._load_operand(instruction, table, self.SCRATCH0)
            self._load_operand(instruction, key, self.SCRATCH1)
            self._emit(
                instruction,
                ArmV9Opcode.TABLE_GET,
                self.SCRATCH2,
                self.SCRATCH0,
                self.SCRATCH1,
            )
            self._store_register(instruction, str(dst), self.SCRATCH2)
            return
        if opcode == Opcode.MAKE_CELL:
            dst, src = self._expect_args(instruction, 2)
            self._load_operand(instruction, src, self.SCRATCH0)
            self._emit(instruction, ArmV9Opcode.NEW_CELL, self.SCRATCH1, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH1)
            return
        if opcode == Opcode.CELL_GET:
            dst, cell = self._expect_args(instruction, 2)
            self._load_operand(instruction, cell, self.SCRATCH0)
            self._emit(instruction, ArmV9Opcode.CELL_GET, self.SCRATCH1, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH1)
            return
        if opcode == Opcode.CELL_SET:
            cell, src = self._expect_args(instruction, 2)
            self._load_operand(instruction, cell, self.SCRATCH0)
            self._load_operand(instruction, src, self.SCRATCH1)
            self._emit(instruction, ArmV9Opcode.CELL_SET, self.SCRATCH0, self.SCRATCH1)
            return
        if opcode == Opcode.CLOSURE:
            self._flush_before_cache_clobber(instruction)
            if len(args) < 2:
                raise ValueError("CLOSURE requires destination and label")
            dst = str(args[0])
            label = str(args[1])
            upvalue_regs: list[str] = []
            for index, cell in enumerate(args[2:]):
                if index >= len(self.SCRATCH_REGISTERS):
                    raise NotImplementedError("ArmV9 lowering supports up to seven closure upvalues")
                scratch = self.SCRATCH_REGISTERS[index]
                self._load_operand(instruction, cell, scratch)
                upvalue_regs.append(scratch)
            self._emit(
                instruction,
                ArmV9Opcode.NEW_CLOSURE,
                self.SCRATCH0,
                label,
                *upvalue_regs,
            )
            self._store_register(instruction, dst, self.SCRATCH0)
            return
        if opcode == Opcode.BIND_UPVALUE:
            dst, index_arg = self._expect_args(instruction, 2)
            index = int(index_arg)
            self._emit(instruction, ArmV9Opcode.BIND_UPVALUE, self.SCRATCH0, index)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.PARAM:
            (src,) = self._expect_args(instruction, 1)
            self._load_operand(instruction, src, "X0")
            self._emit(instruction, ArmV9Opcode.PARAM, "X0")
            return
        if opcode == Opcode.PARAM_EXPAND:
            (src,) = self._expect_args(instruction, 1)
            self._load_operand(instruction, src, "X0")
            self._emit(instruction, ArmV9Opcode.PARAM_EXPAND, "X0")
            return
        if opcode == Opcode.ARG:
            (dst,) = self._expect_args(instruction, 1)
            self._emit(instruction, ArmV9Opcode.ARG, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.VARARG:
            (dst,) = self._expect_args(instruction, 1)
            self._emit(instruction, ArmV9Opcode.VARARG, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.VARARG_FIRST:
            dst, src = self._expect_args(instruction, 2)
            self._load_operand(instruction, src, "X0")
            self._emit(instruction, ArmV9Opcode.VARARG_FIRST, self.SCRATCH0, "X0")
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.LIST_GET:
            dst, src, index_arg = self._expect_args(instruction, 3)
            self._load_operand(instruction, src, "X0")
            self._load_operand(instruction, index_arg, "X1")
            self._emit(instruction, ArmV9Opcode.LIST_GET, self.SCRATCH0, "X0", "X1")
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.CALL_VALUE:
            (callee,) = self._expect_args(instruction, 1)
            self._flush_register_cache(instruction, reason="call")
            self._load_operand(instruction, callee, "X0")
            self._emit(instruction, ArmV9Opcode.CALL_VALUE, "X0")
            self._reset_register_cache()
            return
        if opcode == Opcode.RETURN:
            (src,) = self._expect_args(instruction, 1)
            self._load_operand(instruction, src, "X0")
            self._emit(instruction, ArmV9Opcode.RETURN_VALUE, "X0")
            self._reset_register_cache()
            return
        if opcode == Opcode.RETURN_MULTI:
            return_regs: list[str] = []
            for index, src in enumerate(args):
                if index >= 8:
                    raise NotImplementedError("ArmV9 lowering supports up to eight return values")
                register = f"X{index}"
                self._load_operand(instruction, src, register)
                return_regs.append(register)
            self._emit(instruction, ArmV9Opcode.RETURN_MULTI, *return_regs)
            self._reset_register_cache()
            return
        if opcode == Opcode.RESULT:
            (dst,) = self._expect_args(instruction, 1)
            self._emit(instruction, ArmV9Opcode.RESULT, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.RESULT_MULTI:
            self._flush_before_cache_clobber(instruction)
            if len(args) > len(self.SCRATCH_REGISTERS):
                raise NotImplementedError("ArmV9 lowering supports up to seven RESULT_MULTI targets")
            result_regs = list(self.SCRATCH_REGISTERS[: len(args)])
            self._emit(instruction, ArmV9Opcode.RESULT_MULTI, *result_regs)
            for dst, scratch in zip(args, result_regs):
                self._store_register(instruction, str(dst), scratch)
            return
        if opcode == Opcode.RESULT_LIST:
            (dst,) = self._expect_args(instruction, 1)
            self._emit(instruction, ArmV9Opcode.RESULT_LIST, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.JMP:
            (label,) = self._expect_args(instruction, 1)
            self._flush_register_cache(instruction, reason="branch")
            self._emit(instruction, ArmV9Opcode.B, str(label))
            self._reset_register_cache()
            return
        if opcode in {Opcode.JZ, Opcode.JNZ}:
            cond, label = self._expect_args(instruction, 2)
            self._flush_register_cache(instruction, reason="branch")
            self._load_operand(instruction, cond, self.SCRATCH0)
            self._emit(instruction, ArmV9Opcode.MOVI, self.SCRATCH1, 0)
            self._emit(instruction, ArmV9Opcode.CMP, self.SCRATCH0, self.SCRATCH1)
            branch_opcode = ArmV9Opcode.B_EQ if opcode == Opcode.JZ else ArmV9Opcode.B_NE
            self._emit(instruction, branch_opcode, str(label))
            self._reset_register_cache()
            return
        if opcode == Opcode.PRINT:
            (src,) = self._expect_args(instruction, 1)
            self._load_operand(instruction, src, "X0")
            self._emit(instruction, ArmV9Opcode.CALL_RUNTIME, "print", "X0")
            return
        if opcode == Opcode.HALT:
            self._flush_register_cache(instruction, reason="halt")
            self._emit(instruction, ArmV9Opcode.HALT)
            return
        raise NotImplementedError(f"cannot lower opcode to ArmV9: {opcode.name}")

    def _load_operand(self, source: Instruction, operand: Any, dst: str) -> None:
        if self.optimize_registers and self._is_virtual_register(operand):
            virtual_register = str(operand)
            if self.strategy == "linear-scan" and self._scan_result is not None:
                phys = self._scan_result.register_map.get(virtual_register)
                if phys is not None and virtual_register not in self._scan_result.spilled:
                    if phys != dst:
                        self._emit(source, ArmV9Opcode.MOV, dst, phys)
                    self.allocation_report.loads_elided += 1
                    return
                # Spilled virtual register: load from stack slot
                self._emit(
                    source,
                    ArmV9Opcode.LDR,
                    dst,
                    ("FP", self._slot_for(virtual_register)),
                )
                return

            cached = self._register_cache.get(virtual_register)
            if cached is None:
                cached = self._allocate_cached_register(virtual_register, source)
                self._emit(
                    source,
                    ArmV9Opcode.LDR,
                    cached,
                    ("FP", self._slot_for(virtual_register)),
                )
            else:
                self.allocation_report.loads_elided += 1
            if cached != dst:
                self._emit(source, ArmV9Opcode.MOV, dst, cached)
            return
        if isinstance(operand, str) and operand in self.stack_slots:
            self._emit(source, ArmV9Opcode.LDR, dst, ("FP", self.stack_slots[operand]))
            return
        if isinstance(operand, bool):
            self._emit(source, ArmV9Opcode.MOVI, dst, int(operand))
            return
        if isinstance(operand, int):
            self._emit(source, ArmV9Opcode.MOVI, dst, operand)
            return
        if isinstance(operand, str):
            try:
                self._emit(source, ArmV9Opcode.MOVI, dst, int(operand))
                return
            except ValueError:
                pass
        const_id = self._add_const(operand)
        self._emit(source, ArmV9Opcode.LDRC, dst, const_id)

    def _store_register(self, source: Instruction, register: str, scratch: str) -> None:
        if self.optimize_registers:
            if self.strategy == "linear-scan" and self._scan_result is not None:
                phys = self._scan_result.register_map.get(register)
                if phys is not None and register not in self._scan_result.spilled:
                    if phys != scratch:
                        self._emit(source, ArmV9Opcode.MOV, phys, scratch)
                    self.allocation_report.stores_elided += 1
                    return
                # Spilled: store to stack slot
                self._emit(
                    source,
                    ArmV9Opcode.STR,
                    scratch,
                    ("FP", self._slot_for(register)),
                )
                return

            self._slot_for(register)
            cached = self._allocate_cached_register(register, source)
            if cached != scratch:
                self._emit(source, ArmV9Opcode.MOV, cached, scratch)
            self._dirty_registers.add(register)
            self.allocation_report.stores_elided += 1
            self._update_max_cached_registers()
            return
        self._emit(source, ArmV9Opcode.STR, scratch, ("FP", self._slot_for(register)))

    def _slot_for(self, register: str) -> int:
        if register not in self.stack_slots:
            self.stack_slots[register] = -(len(self.stack_slots) + 1)
        return self.stack_slots[register]

    def _add_const(self, value: Any) -> int:
        self.const_pool.append(value)
        return len(self.const_pool) - 1

    def _emit(
        self,
        source: Instruction,
        opcode: ArmV9Opcode,
        *args: Any,
    ) -> None:
        debug = ArmV9Debug(
            location=source.debug.location if source.debug is not None else None,
            function_name=source.debug.function_name if source.debug is not None else None,
            source_opcode=source.opcode.name,
        )
        self.instructions.append(armv9_inst(opcode, *args, debug=debug))

    def _expect_args(self, instruction: Instruction, count: int) -> list[Any]:
        if len(instruction.args) != count:
            raise ValueError(
                f"{instruction.opcode.name} expects {count} args, got {len(instruction.args)}"
            )
        return instruction.args

    def _is_virtual_register(self, operand: Any) -> bool:
        return self._liveness is not None and self._liveness.is_virtual_register(operand)

    def _allocate_cached_register(self, virtual_register: str, source: Instruction) -> str:
        cached = self._register_cache.get(virtual_register)
        if cached is not None:
            return cached
        free_register = next(
            (
                register
                for register in self.ALLOCATABLE_REGISTERS
                if register not in self._register_owner
            ),
            None,
        )
        if free_register is None:
            free_register = self._spill_cached_register(source)
        self._register_cache[virtual_register] = free_register
        self._register_owner[free_register] = virtual_register
        self._update_max_cached_registers()
        return free_register

    def _spill_cached_register(self, source: Instruction) -> str:
        if not self._register_cache:
            raise RuntimeError("no cached registers available to spill")
        victim = max(
            self._register_cache,
            key=lambda virtual_register: self._future_distance(virtual_register),
        )
        register = self._register_cache[victim]
        if victim in self._dirty_registers:
            self._emit(source, ArmV9Opcode.STR, register, ("FP", self._slot_for(victim)))
            self._dirty_registers.remove(victim)
            self.allocation_report.spills += 1
        del self._register_cache[victim]
        del self._register_owner[register]
        return register

    def _future_distance(self, virtual_register: str) -> int:
        if self._liveness is None:
            return self._current_index
        return self._liveness.last_use.get(virtual_register, self._current_index)

    def _expire_dead_registers(self) -> None:
        if self._liveness is None:
            return
        for virtual_register in list(self._register_cache):
            last_use = self._liveness.last_use.get(virtual_register, -1)
            if last_use > self._current_index:
                continue
            self._dirty_registers.discard(virtual_register)
            register = self._register_cache.pop(virtual_register)
            self._register_owner.pop(register, None)

    def _flush_before_cache_clobber(self, source: Instruction) -> None:
        if self.optimize_registers and self.strategy == "basic-block-cache":
            self._flush_register_cache(source, reason="scratch clobber")

    def _flush_register_cache(self, source: Instruction, *, reason: str) -> None:
        if (
            not self.optimize_registers
            or self.strategy != "basic-block-cache"
            or not self._register_cache
        ):
            return
        dirty_count = 0
        for virtual_register, register in list(self._register_cache.items()):
            if virtual_register not in self._dirty_registers:
                continue
            self._emit(source, ArmV9Opcode.STR, register, ("FP", self._slot_for(virtual_register)))
            dirty_count += 1
        if dirty_count:
            self.allocation_report.flushes += 1
            self.allocation_report.notes.append(
                f"Flushed {dirty_count} dirty register(s) at {reason} near instruction {self._current_index}."
            )
        self._reset_register_cache()

    def _reset_register_cache(self) -> None:
        self._register_cache.clear()
        self._register_owner.clear()
        self._dirty_registers.clear()

    def _update_max_cached_registers(self) -> None:
        self.allocation_report.max_cached_registers = max(
            self.allocation_report.max_cached_registers,
            len(self._register_cache),
        )


def lower_to_armv9(
    instructions: Sequence[Instruction],
    *,
    optimize_registers: bool = False,
    strategy: str = "basic-block-cache",
) -> ArmV9LoweringResult:
    if strategy == "linear-scan":
        optimize_registers = True
    return ArmV9Lowerer.lower(
        instructions,
        optimize_registers=optimize_registers,
        strategy=strategy,
    )
