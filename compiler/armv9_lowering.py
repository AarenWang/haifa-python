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
    SCRATCH_REGISTERS = ("X9", "X10", "X11", "X12", "X13", "X14", "X15")

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
            self._load_operand(instruction, callee, "X0")
            self._emit(instruction, ArmV9Opcode.CALL_VALUE, "X0")
            return
        if opcode == Opcode.RETURN:
            (src,) = self._expect_args(instruction, 1)
            self._load_operand(instruction, src, "X0")
            self._emit(instruction, ArmV9Opcode.RETURN_VALUE, "X0")
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
            return
        if opcode == Opcode.RESULT:
            (dst,) = self._expect_args(instruction, 1)
            self._emit(instruction, ArmV9Opcode.RESULT, self.SCRATCH0)
            self._store_register(instruction, str(dst), self.SCRATCH0)
            return
        if opcode == Opcode.RESULT_MULTI:
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
