from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .armv9_bytecode import ArmV9Debug, ArmV9Instruction, ArmV9Opcode, armv9_inst
from .bytecode import Instruction, Opcode


@dataclass(frozen=True)
class ArmV9LoweringResult:
    instructions: list[ArmV9Instruction]
    const_pool: list[Any] = field(default_factory=list)
    stack_slots: dict[str, int] = field(default_factory=dict)


class ArmV9Lowerer:
    """Conservative lowering from Haifa high-level bytecode to HaifaArmV9VM."""

    SCRATCH0 = "X9"
    SCRATCH1 = "X10"
    SCRATCH2 = "X11"

    def __init__(self) -> None:
        self.instructions: list[ArmV9Instruction] = []
        self.const_pool: list[Any] = []
        self.stack_slots: dict[str, int] = {}

    @classmethod
    def lower(cls, instructions: Sequence[Instruction]) -> ArmV9LoweringResult:
        lowerer = cls()
        lowerer._lower_program(instructions)
        return ArmV9LoweringResult(
            list(lowerer.instructions),
            list(lowerer.const_pool),
            dict(lowerer.stack_slots),
        )

    def _lower_program(self, instructions: Sequence[Instruction]) -> None:
        for instruction in instructions:
            self._lower_instruction(instruction)

    def _lower_instruction(self, instruction: Instruction) -> None:
        opcode = instruction.opcode
        args = instruction.args
        if opcode == Opcode.LABEL:
            self._emit(instruction, ArmV9Opcode.LABEL, str(args[0]))
            return
        if opcode == Opcode.LOAD_IMM:
            dst, value = self._expect_args(instruction, 2)
            self._emit(instruction, ArmV9Opcode.MOVI, self.SCRATCH0, int(value))
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.LOAD_CONST:
            dst, value = self._expect_args(instruction, 2)
            const_id = self._add_const(value)
            self._emit(instruction, ArmV9Opcode.LDRC, self.SCRATCH0, const_id)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.MOV:
            dst, src = self._expect_args(instruction, 2)
            self._load_operand(instruction, src, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode in {Opcode.ADD, Opcode.SUB, Opcode.MUL}:
            dst, lhs, rhs = self._expect_args(instruction, 3)
            arm_opcode = {
                Opcode.ADD: ArmV9Opcode.ADD,
                Opcode.SUB: ArmV9Opcode.SUB,
                Opcode.MUL: ArmV9Opcode.MUL,
            }[opcode]
            self._load_operand(instruction, lhs, self.SCRATCH0)
            self._load_operand(instruction, rhs, self.SCRATCH1)
            self._emit(instruction, arm_opcode, self.SCRATCH2, self.SCRATCH0, self.SCRATCH1)
            self._store_register(instruction, str(dst), self.SCRATCH2)
            return
        if opcode in {Opcode.EQ, Opcode.LT, Opcode.GT}:
            dst, lhs, rhs = self._expect_args(instruction, 3)
            condition = {
                Opcode.EQ: "EQ",
                Opcode.LT: "LT",
                Opcode.GT: "GT",
            }[opcode]
            self._load_operand(instruction, lhs, self.SCRATCH0)
            self._load_operand(instruction, rhs, self.SCRATCH1)
            self._emit(instruction, ArmV9Opcode.CMP, self.SCRATCH0, self.SCRATCH1)
            self._emit(instruction, ArmV9Opcode.CSET, self.SCRATCH2, condition)
            self._store_register(instruction, str(dst), self.SCRATCH2)
            return
        if opcode == Opcode.JMP:
            (label,) = self._expect_args(instruction, 1)
            self._emit(instruction, ArmV9Opcode.B, str(label))
            return
        if opcode in {Opcode.JZ, Opcode.JNZ}:
            cond, label = self._expect_args(instruction, 2)
            self._load_operand(instruction, cond, self.SCRATCH0)
            self._emit(instruction, ArmV9Opcode.MOVI, self.SCRATCH1, 0)
            self._emit(instruction, ArmV9Opcode.CMP, self.SCRATCH0, self.SCRATCH1)
            branch_opcode = ArmV9Opcode.B_EQ if opcode == Opcode.JZ else ArmV9Opcode.B_NE
            self._emit(instruction, branch_opcode, str(label))
            return
        if opcode == Opcode.PRINT:
            (src,) = self._expect_args(instruction, 1)
            self._load_operand(instruction, src, "X0")
            self._emit(instruction, ArmV9Opcode.CALL_RUNTIME, "print", "X0")
            return
        if opcode == Opcode.HALT:
            self._emit(instruction, ArmV9Opcode.HALT)
            return
        raise NotImplementedError(f"cannot lower opcode to ArmV9: {opcode.name}")

    def _load_operand(self, source: Instruction, operand: Any, dst: str) -> None:
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


def lower_to_armv9(instructions: Sequence[Instruction]) -> ArmV9LoweringResult:
    return ArmV9Lowerer.lower(instructions)

