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
        """Update NZCV for subtraction (lhs - rhs) with 64-bit semantics."""
        mask = (1 << 64) - 1
        sign_bit = 1 << 63
        a = lhs & mask
        b = rhs & mask
        result = (a - b) & mask
        self.n = bool(result & sign_bit)
        self.z = result == 0
        self.c = a >= b
        self.v = bool(((a ^ b) & (a ^ result)) & sign_bit)

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
class ArmV9Cell:
    value: Any


@dataclass(frozen=True)
class ArmV9Closure:
    label: str
    upvalues: tuple[ArmV9HeapRef, ...] = ()


@dataclass(frozen=True)
class ArmV9MultiReturn:
    values: tuple[Any, ...]


@dataclass
class ArmV9CallFrame:
    label: str
    return_pc: int
    caller_fp: int
    caller_sp: int
    caller_lr: Any
    caller_upvalues: list[ArmV9HeapRef] = field(default_factory=list)
    caller_param_stack: list[Any] = field(default_factory=list)
    caller_pending_params: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "return_pc": self.return_pc,
            "caller_fp": self.caller_fp,
            "caller_sp": self.caller_sp,
            "caller_lr": self.caller_lr,
            "caller_upvalues": [str(ref) for ref in self.caller_upvalues],
            "caller_param_stack": list(self.caller_param_stack),
            "caller_pending_params": list(self.caller_pending_params),
        }


class HaifaArmV9VM:
    """A small ARMv9-style VM target for Haifa lowering experiments."""

    # Each call frame reserves 16 stack slots: 2 for old FP and return PC,
    # 14 reserved for future spill slots and saved registers.
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
        self.current_upvalues: list[ArmV9HeapRef] = []
        self.param_stack: list[Any] = []
        self.pending_params: list[Any] = []
        self.last_return: list[Any] = []
        self.return_value: Any = None
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
            ArmV9Opcode.NEW_CELL: self._op_NEW_CELL,
            ArmV9Opcode.NEW_CLOSURE: self._op_NEW_CLOSURE,
            ArmV9Opcode.CELL_GET: self._op_CELL_GET,
            ArmV9Opcode.CELL_SET: self._op_CELL_SET,
            ArmV9Opcode.BIND_UPVALUE: self._op_BIND_UPVALUE,
            ArmV9Opcode.PARAM: self._op_PARAM,
            ArmV9Opcode.PARAM_EXPAND: self._op_PARAM_EXPAND,
            ArmV9Opcode.ARG: self._op_ARG,
            ArmV9Opcode.VARARG: self._op_VARARG,
            ArmV9Opcode.VARARG_FIRST: self._op_VARARG_FIRST,
            ArmV9Opcode.LIST_GET: self._op_LIST_GET,
            ArmV9Opcode.CALL_VALUE: self._op_CALL_VALUE,
            ArmV9Opcode.RETURN_VALUE: self._op_RETURN_VALUE,
            ArmV9Opcode.RETURN_MULTI: self._op_RETURN_MULTI,
            ArmV9Opcode.RESULT: self._op_RESULT,
            ArmV9Opcode.RESULT_MULTI: self._op_RESULT_MULTI,
            ArmV9Opcode.RESULT_LIST: self._op_RESULT_LIST,
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
            "upvalues": [self._snapshot_value(value) for value in self.current_upvalues],
            "param_stack": [self._snapshot_value(value) for value in self.param_stack],
            "pending_params": [self._snapshot_value(value) for value in self.pending_params],
            "last_return": [self._snapshot_value(value) for value in self.last_return],
            "return_value": self._snapshot_value(self.return_value),
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
        # Result is not masked to 64 bits; the VM stores Python ints for
        # compatibility with dynamic language semantics. 64-bit truncation
        # is deferred to the arm_emulator project.
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
                caller_upvalues=list(self.current_upvalues),
            )
        )
        self._branch_to(str(label))

    def _op_RET(self, instruction: ArmV9Instruction) -> None:
        # When there are no call frames, RET acts as program termination.
        # This is a teaching simplification; real ARM would jump to LR.
        if not self.frames:
            self.halted = True
            return
        self._restore_call_frame()

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

    def _op_NEW_CELL(self, instruction: ArmV9Instruction) -> None:
        dst, src = self._expect_args(instruction, 2)
        ref = self._allocate_heap_object(ArmV9Cell(self.read_reg(str(src))))
        self.write_reg(str(dst), ref)

    def _op_NEW_CLOSURE(self, instruction: ArmV9Instruction) -> None:
        if len(instruction.args) < 2:
            raise ArmV9RuntimeError("NEW_CLOSURE requires destination and label")
        dst = str(instruction.args[0])
        label = str(instruction.args[1])
        upvalues: list[ArmV9HeapRef] = []
        for cell_reg in instruction.args[2:]:
            cell_ref = self.read_reg(str(cell_reg))
            self._cell_from_ref(cell_ref)
            upvalues.append(cell_ref)
        ref = self._allocate_heap_object(ArmV9Closure(label=label, upvalues=tuple(upvalues)))
        self.write_reg(dst, ref)

    def _op_CELL_GET(self, instruction: ArmV9Instruction) -> None:
        dst, cell_reg = self._expect_args(instruction, 2)
        cell = self._cell_from_ref(self.read_reg(str(cell_reg)))
        self.write_reg(str(dst), cell.value)

    def _op_CELL_SET(self, instruction: ArmV9Instruction) -> None:
        cell_reg, src = self._expect_args(instruction, 2)
        cell = self._cell_from_ref(self.read_reg(str(cell_reg)))
        cell.value = self.read_reg(str(src))

    def _op_BIND_UPVALUE(self, instruction: ArmV9Instruction) -> None:
        dst, index_arg = self._expect_args(instruction, 2)
        index = self._as_int(index_arg, "upvalue index")
        if index < 0 or index >= len(self.current_upvalues):
            raise ArmV9RuntimeError(f"BIND_UPVALUE index out of range: {index}")
        self.write_reg(str(dst), self.current_upvalues[index])

    def _op_PARAM(self, instruction: ArmV9Instruction) -> None:
        (src,) = self._expect_args(instruction, 1)
        self.pending_params.append(self.read_reg(str(src)))

    def _op_PARAM_EXPAND(self, instruction: ArmV9Instruction) -> None:
        (src,) = self._expect_args(instruction, 1)
        value = self.read_reg(str(src))
        if isinstance(value, ArmV9HeapRef):
            heap_value = self.memory.heap.get(value.object_id)
            if isinstance(heap_value, ArmV9MultiReturn):
                self.pending_params.extend(heap_value.values)
                return
        if isinstance(value, list):
            self.pending_params.extend(value)
            return
        self.pending_params.append(value)

    def _op_ARG(self, instruction: ArmV9Instruction) -> None:
        (dst,) = self._expect_args(instruction, 1)
        value = self.param_stack.pop(0) if self.param_stack else None
        self.write_reg(str(dst), value)

    def _op_VARARG(self, instruction: ArmV9Instruction) -> None:
        (dst,) = self._expect_args(instruction, 1)
        self.write_reg(str(dst), list(self.param_stack))

    def _op_VARARG_FIRST(self, instruction: ArmV9Instruction) -> None:
        dst, src = self._expect_args(instruction, 2)
        value = self.read_reg(str(src))
        first = value[0] if isinstance(value, list) and value else None
        self.write_reg(str(dst), first)

    def _op_LIST_GET(self, instruction: ArmV9Instruction) -> None:
        dst, src, index_reg = self._expect_args(instruction, 3)
        values = self.read_reg(str(src))
        index = self._as_int(self.read_reg(str(index_reg)), str(index_reg))
        if isinstance(values, list) and 0 <= index < len(values):
            self.write_reg(str(dst), values[index])
            return
        self.write_reg(str(dst), None)

    def _op_CALL_VALUE(self, instruction: ArmV9Instruction) -> None:
        (callee_reg,) = self._expect_args(instruction, 1)
        closure = self._closure_from_ref(self.read_reg(str(callee_reg)))
        self._enter_call_frame(closure.label, closure.upvalues)

    def _op_RETURN_VALUE(self, instruction: ArmV9Instruction) -> None:
        (src,) = self._expect_args(instruction, 1)
        self._return_with([self.read_reg(str(src))])

    def _op_RETURN_MULTI(self, instruction: ArmV9Instruction) -> None:
        values: list[Any] = []
        for src in instruction.args:
            value = self.read_reg(str(src))
            if isinstance(value, list):
                values.extend(value)
            else:
                values.append(value)
        ref = self._allocate_heap_object(ArmV9MultiReturn(tuple(values)))
        self.write_reg("X0", ref)
        self._return_with(values, return_register_value=ref)

    def _op_RESULT(self, instruction: ArmV9Instruction) -> None:
        (dst,) = self._expect_args(instruction, 1)
        self.write_reg(str(dst), self.last_return[0] if self.last_return else None)

    def _op_RESULT_MULTI(self, instruction: ArmV9Instruction) -> None:
        for index, dst in enumerate(instruction.args):
            value = self.last_return[index] if index < len(self.last_return) else None
            self.write_reg(str(dst), value)

    def _op_RESULT_LIST(self, instruction: ArmV9Instruction) -> None:
        (dst,) = self._expect_args(instruction, 1)
        self.write_reg(str(dst), list(self.last_return))

    def _op_CALL_RUNTIME(self, instruction: ArmV9Instruction) -> None:
        name, *args = instruction.args
        if name == "print":
            if len(args) != 1:
                raise ArmV9RuntimeError("CALL_RUNTIME print expects one register")
            self.output.append(self._runtime_value(self.read_reg(str(args[0]))))
            return
        raise ArmV9RuntimeError(f"unknown runtime call: {name}")

    def _op_HALT(self, instruction: ArmV9Instruction) -> None:
        self.halted = True

    def _branch_to(self, label: str) -> None:
        if label not in self.labels:
            raise ArmV9RuntimeError(f"unknown label: {label}")
        self.pc = self.labels[label]

    def _enter_call_frame(
        self,
        label: str,
        upvalues: Sequence[ArmV9HeapRef] = (),
    ) -> None:
        args_to_pass = list(self.pending_params)
        self.pending_params.clear()
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
                label=label,
                return_pc=return_pc,
                caller_fp=caller_fp,
                caller_sp=caller_sp,
                caller_lr=caller_lr,
                caller_upvalues=list(self.current_upvalues),
                caller_param_stack=list(self.param_stack),
                caller_pending_params=list(self.pending_params),
            )
        )
        self.current_upvalues = list(upvalues)
        self.param_stack = args_to_pass
        self.pending_params = []
        self._branch_to(label)

    def _restore_call_frame(self) -> None:
        frame = self.frames.pop()
        self.regs["FP"] = frame.caller_fp
        self.regs["SP"] = frame.caller_sp
        self.regs["LR"] = frame.caller_lr
        self.current_upvalues = list(frame.caller_upvalues)
        self.param_stack = list(frame.caller_param_stack)
        self.pending_params = list(frame.caller_pending_params)
        self.pc = frame.return_pc

    def _return_with(
        self,
        values: Sequence[Any],
        *,
        return_register_value: Any | None = None,
    ) -> None:
        self.last_return = list(values)
        self.return_value = self.last_return[0] if self.last_return else None
        self.write_reg(
            "X0",
            return_register_value
            if return_register_value is not None
            else self.return_value,
        )
        if self.frames:
            self._restore_call_frame()
            return
        self.halted = True

    def _condition_holds(self, condition: str) -> bool:
        normalized = condition.upper()
        n, z, c, v = self.nzcv.n, self.nzcv.z, self.nzcv.c, self.nzcv.v
        table = {
            "EQ": z,
            "NE": not z,
            "CS": c,
            "HS": c,
            "CC": not c,
            "LO": not c,
            "MI": n,
            "PL": not n,
            "VS": v,
            "VC": not v,
            "HI": c and not z,
            "LS": not c or z,
            "GE": n == v,
            "LT": n != v,
            "GT": not z and n == v,
            "LE": z or n != v,
            "AL": True,
            "NV": False,
        }
        if normalized not in table:
            raise ArmV9RuntimeError(f"unknown condition: {condition}")
        return table[normalized]

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

    def _cell_from_ref(self, value: Any) -> ArmV9Cell:
        if not isinstance(value, ArmV9HeapRef):
            raise ArmV9RuntimeError(f"expected heap cell reference, got {value!r}")
        cell = self.memory.heap.get(value.object_id)
        if not isinstance(cell, ArmV9Cell):
            raise ArmV9RuntimeError(f"heap object is not a cell: {value}")
        return cell

    def _closure_from_ref(self, value: Any) -> ArmV9Closure:
        if not isinstance(value, ArmV9HeapRef):
            raise ArmV9RuntimeError(f"expected heap closure reference, got {value!r}")
        closure = self.memory.heap.get(value.object_id)
        if not isinstance(closure, ArmV9Closure):
            raise ArmV9RuntimeError(f"heap object is not a closure: {value}")
        return closure

    def _multi_return_from_ref(self, value: Any) -> ArmV9MultiReturn:
        if not isinstance(value, ArmV9HeapRef):
            raise ArmV9RuntimeError(f"expected heap multi-return reference, got {value!r}")
        multi_return = self.memory.heap.get(value.object_id)
        if not isinstance(multi_return, ArmV9MultiReturn):
            raise ArmV9RuntimeError(f"heap object is not a multi-return: {value}")
        return multi_return

    def _runtime_value(self, value: Any) -> Any:
        if isinstance(value, ArmV9HeapRef):
            heap_value = self.memory.heap.get(value.object_id)
            if isinstance(heap_value, ArmV9MultiReturn):
                return list(heap_value.values)
        return value

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
        if isinstance(value, ArmV9Cell):
            return {
                "type": "cell",
                "value": self._snapshot_value(value.value),
            }
        if isinstance(value, ArmV9Closure):
            return {
                "type": "closure",
                "label": value.label,
                "upvalues": [self._snapshot_value(item) for item in value.upvalues],
            }
        if isinstance(value, ArmV9MultiReturn):
            return {
                "type": "multi_return",
                "values": [self._snapshot_value(item) for item in value.values],
            }
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
