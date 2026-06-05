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


@dataclass(frozen=True)
class ArmV9HeapRef:
    object_id: int

    def __str__(self) -> str:
        return f"heap:{self.object_id}"


@dataclass
class ArmV9CallFrame:
    label: str
    return_pc: int
    caller_fp: int
    caller_sp: int
    caller_lr: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "return_pc": self.return_pc,
            "caller_fp": self.caller_fp,
            "caller_sp": self.caller_sp,
            "caller_lr": self.caller_lr,
        }


class HaifaArmV9VM:
    """A small ARMv9-style VM target for Haifa lowering experiments."""

    FRAME_STRIDE = 16
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
        self.frames: list[ArmV9CallFrame] = []
        self._next_heap_id = 1
        self.regs["SP"] = stack_size
        self.regs["FP"] = stack_size
        self.regs["LR"] = None
        self.regs["PC"] = 0
        self._handlers: dict[ArmV9Opcode, Callable[[ArmV9Instruction], None]] = {
            ArmV9Opcode.MOVI: self._op_MOVI,
            ArmV9Opcode.MOV: self._op_MOV,
            ArmV9Opcode.LDRC: self._op_LDRC,
            ArmV9Opcode.ADD: self._op_ADD,
            ArmV9Opcode.SUB: self._op_SUB,
            ArmV9Opcode.MUL: self._op_MUL,
            ArmV9Opcode.LDR: self._op_LDR,
            ArmV9Opcode.STR: self._op_STR,
            ArmV9Opcode.CMP: self._op_CMP,
            ArmV9Opcode.CSET: self._op_CSET,
            ArmV9Opcode.LABEL: self._op_LABEL,
            ArmV9Opcode.B: self._op_B,
            ArmV9Opcode.B_EQ: self._op_B_EQ,
            ArmV9Opcode.B_NE: self._op_B_NE,
            ArmV9Opcode.B_LT: self._op_B_LT,
            ArmV9Opcode.B_GT: self._op_B_GT,
            ArmV9Opcode.BL: self._op_BL,
            ArmV9Opcode.RET: self._op_RET,
            ArmV9Opcode.NEW_TABLE: self._op_NEW_TABLE,
            ArmV9Opcode.TABLE_GET: self._op_TABLE_GET,
            ArmV9Opcode.TABLE_SET: self._op_TABLE_SET,
            ArmV9Opcode.CALL_RUNTIME: self._op_CALL_RUNTIME,
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
            "registers": self._snapshot_mapping(self.regs),
            "nzcv": self.nzcv.to_dict(),
            "memory": self._memory_snapshot(),
            "frames": [frame.to_dict() for frame in self.frames],
            "output": [self._snapshot_value(value) for value in self.output],
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

    def _op_LDRC(self, instruction: ArmV9Instruction) -> None:
        dst, const_id = self._expect_args(instruction, 2)
        index = self._as_int(const_id, "const id")
        if index < 0 or index >= len(self.memory.const_pool):
            raise ArmV9RuntimeError(f"constant index out of bounds: {index}")
        self.write_reg(str(dst), self.memory.const_pool[index])

    def _op_ADD(self, instruction: ArmV9Instruction) -> None:
        dst, lhs, rhs = self._expect_args(instruction, 3)
        self.write_reg(str(dst), self._int_reg(lhs) + self._int_reg(rhs))

    def _op_SUB(self, instruction: ArmV9Instruction) -> None:
        dst, lhs, rhs = self._expect_args(instruction, 3)
        self.write_reg(str(dst), self._int_reg(lhs) - self._int_reg(rhs))

    def _op_MUL(self, instruction: ArmV9Instruction) -> None:
        dst, lhs, rhs = self._expect_args(instruction, 3)
        self.write_reg(str(dst), self._int_reg(lhs) * self._int_reg(rhs))

    def _op_LDR(self, instruction: ArmV9Instruction) -> None:
        dst, address = self._expect_args(instruction, 2)
        self.write_reg(str(dst), self.memory.stack[self._stack_address(address)])

    def _op_STR(self, instruction: ArmV9Instruction) -> None:
        src, address = self._expect_args(instruction, 2)
        self.memory.stack[self._stack_address(address)] = self.read_reg(str(src))

    def _op_CMP(self, instruction: ArmV9Instruction) -> None:
        lhs, rhs = self._expect_args(instruction, 2)
        self.nzcv.update_from_subtraction(self._int_reg(lhs), self._int_reg(rhs))

    def _op_CSET(self, instruction: ArmV9Instruction) -> None:
        dst, condition = self._expect_args(instruction, 2)
        self.write_reg(str(dst), int(self._condition_holds(str(condition))))

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

    def _op_B_LT(self, instruction: ArmV9Instruction) -> None:
        (label,) = self._expect_args(instruction, 1)
        if self.nzcv.n != self.nzcv.v:
            self._branch_to(str(label))

    def _op_B_GT(self, instruction: ArmV9Instruction) -> None:
        (label,) = self._expect_args(instruction, 1)
        if not self.nzcv.z and self.nzcv.n == self.nzcv.v:
            self._branch_to(str(label))

    def _op_BL(self, instruction: ArmV9Instruction) -> None:
        (label,) = self._expect_args(instruction, 1)
        return_pc = self.pc + 1
        caller_fp = self._as_int(self.read_reg("FP"), "FP")
        caller_sp = self._as_int(self.read_reg("SP"), "SP")
        caller_lr = self.read_reg("LR")
        frame_sp = caller_sp - self.FRAME_STRIDE
        if frame_sp < 0:
            raise ArmV9RuntimeError("stack overflow while creating call frame")
        self.memory.stack[frame_sp] = caller_fp
        self.memory.stack[frame_sp + 1] = return_pc
        self.regs["FP"] = frame_sp
        self.regs["SP"] = frame_sp
        self.regs["LR"] = return_pc
        self.frames.append(
            ArmV9CallFrame(
                label=str(label),
                return_pc=return_pc,
                caller_fp=caller_fp,
                caller_sp=caller_sp,
                caller_lr=caller_lr,
            )
        )
        self._branch_to(str(label))

    def _op_RET(self, instruction: ArmV9Instruction) -> None:
        if not self.frames:
            self.halted = True
            return
        frame = self.frames.pop()
        self.regs["FP"] = frame.caller_fp
        self.regs["SP"] = frame.caller_sp
        self.regs["LR"] = frame.caller_lr
        self.pc = frame.return_pc

    def _op_NEW_TABLE(self, instruction: ArmV9Instruction) -> None:
        (dst,) = self._expect_args(instruction, 1)
        ref = self._allocate_heap_object({})
        self.write_reg(str(dst), ref)

    def _op_TABLE_GET(self, instruction: ArmV9Instruction) -> None:
        dst, table_reg, key_reg = self._expect_args(instruction, 3)
        table = self._table_from_ref(self.read_reg(str(table_reg)))
        self.write_reg(str(dst), table.get(self.read_reg(str(key_reg))))

    def _op_TABLE_SET(self, instruction: ArmV9Instruction) -> None:
        table_reg, key_reg, value_reg = self._expect_args(instruction, 3)
        table = self._table_from_ref(self.read_reg(str(table_reg)))
        table[self.read_reg(str(key_reg))] = self.read_reg(str(value_reg))

    def _op_CALL_RUNTIME(self, instruction: ArmV9Instruction) -> None:
        name, *args = instruction.args
        if name == "print":
            if len(args) != 1:
                raise ArmV9RuntimeError("CALL_RUNTIME print expects one register")
            self.output.append(self.read_reg(str(args[0])))
            return
        raise ArmV9RuntimeError(f"unknown runtime call: {name}")

    def _op_HALT(self, instruction: ArmV9Instruction) -> None:
        self.halted = True

    def _branch_to(self, label: str) -> None:
        if label not in self.labels:
            raise ArmV9RuntimeError(f"unknown label: {label}")
        self.pc = self.labels[label]

    def _condition_holds(self, condition: str) -> bool:
        normalized = condition.upper()
        if normalized == "EQ":
            return self.nzcv.z
        if normalized == "NE":
            return not self.nzcv.z
        if normalized == "LT":
            return self.nzcv.n != self.nzcv.v
        if normalized == "GT":
            return not self.nzcv.z and self.nzcv.n == self.nzcv.v
        raise ArmV9RuntimeError(f"unknown condition: {condition}")

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

    def _stack_address(self, address: Any) -> int:
        if not isinstance(address, (tuple, list)) or len(address) != 2:
            raise ArmV9RuntimeError(
                f"stack address must be a (base, offset) pair, got {address!r}"
            )
        base, offset = address
        base_value = self._as_int(self.read_reg(str(base)), str(base))
        offset_value = self._as_int(offset, "stack offset")
        index = base_value + offset_value
        if index < 0 or index >= len(self.memory.stack):
            raise ArmV9RuntimeError(f"stack address out of bounds: {index}")
        return index

    def _allocate_heap_object(self, value: Any) -> ArmV9HeapRef:
        object_id = self._next_heap_id
        self._next_heap_id += 1
        self.memory.heap[object_id] = value
        return ArmV9HeapRef(object_id)

    def _table_from_ref(self, value: Any) -> dict[Any, Any]:
        if not isinstance(value, ArmV9HeapRef):
            raise ArmV9RuntimeError(f"expected heap table reference, got {value!r}")
        table = self.memory.heap.get(value.object_id)
        if not isinstance(table, dict):
            raise ArmV9RuntimeError(f"heap object is not a table: {value}")
        return table

    def _memory_snapshot(self) -> dict[str, Any]:
        return {
            "const_pool": [self._snapshot_value(value) for value in self.memory.const_pool],
            "stack": [self._snapshot_value(value) for value in self.memory.stack],
            "heap": {
                object_id: self._snapshot_value(value)
                for object_id, value in self.memory.heap.items()
            },
            "globals": self._snapshot_mapping(self.memory.globals),
        }

    def _snapshot_mapping(self, mapping: Mapping[str, Any]) -> dict[str, Any]:
        return {key: self._snapshot_value(value) for key, value in mapping.items()}

    def _snapshot_value(self, value: Any) -> Any:
        if isinstance(value, ArmV9HeapRef):
            return str(value)
        if isinstance(value, dict):
            return {
                self._snapshot_value(key): self._snapshot_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._snapshot_value(item) for item in value]
        return value

    def _normalize_register(self, name: str) -> str:
        register = name.upper()
        if register not in self.VALID_REGISTERS:
            raise ArmV9RuntimeError(f"unknown register: {name}")
        return register

    def _sync_pc_register(self) -> None:
        self.regs["PC"] = self.pc
