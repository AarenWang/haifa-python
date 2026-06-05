from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .armv9_bytecode import ArmV9Instruction, ArmV9Opcode


class ArmV9RuntimeError(RuntimeError):
    """Runtime error raised by HaifaArmV9VM."""


@dataclass
class ArmV9Flags:
    n: bool = False
    z: bool = False
    c: bool = False
    v: bool = False

    def update_from_subtraction(self, lhs: int, rhs: int) -> None:
        result = lhs - rhs
        self.n = result < 0
        self.z = result == 0
        self.c = lhs >= rhs
        self.v = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "N": self.n,
            "Z": self.z,
            "C": self.c,
            "V": self.v,
        }


@dataclass
class ArmV9Memory:
    const_pool: list[Any] = field(default_factory=list)
    stack: list[Any] = field(default_factory=list)
    heap: dict[int, Any] = field(default_factory=dict)
    globals: dict[str, Any] = field(default_factory=dict)

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "const_pool": list(self.const_pool),
            "stack": list(self.stack),
            "heap": dict(self.heap),
            "globals": dict(self.globals),
        }


class HaifaArmV9VM:
    """A small ARMv9-style VM target for Haifa lowering experiments."""

    GENERAL_REGISTERS = tuple(f"X{index}" for index in range(16))
    SPECIAL_REGISTERS = ("FP", "LR", "SP", "PC")
    VALID_REGISTERS = set(GENERAL_REGISTERS + SPECIAL_REGISTERS)

    def __init__(
        self,
        instructions: Sequence[ArmV9Instruction],
        *,
        stack_size: int = 1024,
        const_pool: Sequence[Any] | None = None,
        globals: Mapping[str, Any] | None = None,
    ) -> None:
        self.instructions = list(instructions)
        self.labels: dict[str, int] = {}
        self.regs: dict[str, Any] = {name: 0 for name in self.GENERAL_REGISTERS}
        self.memory = ArmV9Memory(
            const_pool=list(const_pool or ()),
            stack=[0] * stack_size,
            globals=dict(globals or {}),
        )
        self.nzcv = ArmV9Flags()
        self.pc = 0
        self.halted = False
        self.output: list[Any] = []
        self.frames: list[dict[str, Any]] = []
        self.regs["SP"] = stack_size
        self.regs["FP"] = stack_size
        self.regs["LR"] = None
        self.regs["PC"] = 0
        self._handlers: dict[ArmV9Opcode, Callable[[ArmV9Instruction], None]] = {
            ArmV9Opcode.MOVI: self._op_MOVI,
            ArmV9Opcode.MOV: self._op_MOV,
            ArmV9Opcode.ADD: self._op_ADD,
            ArmV9Opcode.SUB: self._op_SUB,
            ArmV9Opcode.CMP: self._op_CMP,
            ArmV9Opcode.LABEL: self._op_LABEL,
            ArmV9Opcode.B: self._op_B,
            ArmV9Opcode.B_EQ: self._op_B_EQ,
            ArmV9Opcode.B_NE: self._op_B_NE,
            ArmV9Opcode.HALT: self._op_HALT,
        }
        self.index_labels()
        self._sync_pc_register()

    def index_labels(self) -> None:
        self.labels.clear()
        for index, instruction in enumerate(self.instructions):
            if instruction.opcode == ArmV9Opcode.LABEL:
                if not instruction.args:
                    raise ArmV9RuntimeError("LABEL requires a name")
                self.labels[str(instruction.args[0])] = index

    def run(self, *, max_steps: int = 10000) -> list[Any]:
        steps = 0
        while not self.halted and self.pc < len(self.instructions):
            if steps >= max_steps:
                raise ArmV9RuntimeError(f"maximum step count exceeded: {max_steps}")
            self.step()
            steps += 1
        self._sync_pc_register()
        return list(self.output)

    def step(self) -> bool:
        if self.halted or self.pc >= len(self.instructions):
            self.halted = True
            self._sync_pc_register()
            return False

        instruction = self.instructions[self.pc]
        handler = self._handlers.get(instruction.opcode)
        if handler is None:
            raise ArmV9RuntimeError(f"unsupported ArmV9 opcode: {instruction.opcode.name}")

        old_pc = self.pc
        handler(instruction)
        if self.pc == old_pc and not self.halted:
            self.pc += 1
        self._sync_pc_register()
        return not self.halted

    def snapshot(self) -> dict[str, Any]:
        return {
            "pc": self.pc,
            "halted": self.halted,
            "registers": dict(self.regs),
            "nzcv": self.nzcv.to_dict(),
            "memory": self.memory.to_snapshot(),
            "frames": list(self.frames),
            "output": list(self.output),
        }

    def read_reg(self, name: str) -> Any:
        register = self._normalize_register(name)
        return self.regs[register]

    def write_reg(self, name: str, value: Any) -> None:
        register = self._normalize_register(name)
        if register == "PC":
            self.pc = self._as_int(value, "PC")
        self.regs[register] = value
        if register == "PC":
            self._sync_pc_register()

    def _op_MOVI(self, instruction: ArmV9Instruction) -> None:
        dst, value = self._expect_args(instruction, 2)
        self.write_reg(str(dst), value)

    def _op_MOV(self, instruction: ArmV9Instruction) -> None:
        dst, src = self._expect_args(instruction, 2)
        self.write_reg(str(dst), self.read_reg(str(src)))

    def _op_ADD(self, instruction: ArmV9Instruction) -> None:
        dst, lhs, rhs = self._expect_args(instruction, 3)
        self.write_reg(str(dst), self._int_reg(lhs) + self._int_reg(rhs))

    def _op_SUB(self, instruction: ArmV9Instruction) -> None:
        dst, lhs, rhs = self._expect_args(instruction, 3)
        self.write_reg(str(dst), self._int_reg(lhs) - self._int_reg(rhs))

    def _op_CMP(self, instruction: ArmV9Instruction) -> None:
        lhs, rhs = self._expect_args(instruction, 2)
        self.nzcv.update_from_subtraction(self._int_reg(lhs), self._int_reg(rhs))

    def _op_LABEL(self, instruction: ArmV9Instruction) -> None:
        return None

    def _op_B(self, instruction: ArmV9Instruction) -> None:
        (label,) = self._expect_args(instruction, 1)
        self._branch_to(str(label))

    def _op_B_EQ(self, instruction: ArmV9Instruction) -> None:
        (label,) = self._expect_args(instruction, 1)
        if self.nzcv.z:
            self._branch_to(str(label))

    def _op_B_NE(self, instruction: ArmV9Instruction) -> None:
        (label,) = self._expect_args(instruction, 1)
        if not self.nzcv.z:
            self._branch_to(str(label))

    def _op_HALT(self, instruction: ArmV9Instruction) -> None:
        self.halted = True

    def _branch_to(self, label: str) -> None:
        if label not in self.labels:
            raise ArmV9RuntimeError(f"unknown label: {label}")
        self.pc = self.labels[label]

    def _expect_args(
        self, instruction: ArmV9Instruction, count: int
    ) -> tuple[Any, ...]:
        if len(instruction.args) != count:
            raise ArmV9RuntimeError(
                f"{instruction.opcode.name} expects {count} args, got {len(instruction.args)}"
            )
        return instruction.args

    def _int_reg(self, name: Any) -> int:
        return self._as_int(self.read_reg(str(name)), str(name))

    def _as_int(self, value: Any, context: str) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        raise ArmV9RuntimeError(f"{context} must contain an integer, got {value!r}")

    def _normalize_register(self, name: str) -> str:
        register = name.upper()
        if register not in self.VALID_REGISTERS:
            raise ArmV9RuntimeError(f"unknown register: {name}")
        return register

    def _sync_pc_register(self) -> None:
        self.regs["PC"] = self.pc

