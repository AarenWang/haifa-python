import copy
import time
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence

from .bytecode import Instruction, InstructionDebug, Opcode
from .vm_errors import VMRuntimeError
from .vm_events import (
    CoroutineCompleted,
    CoroutineCreated,
    CoroutineEvent,
    CoroutineResumed,
    CoroutineSnapshot,
    CoroutineYielded,
    TraceFrame,
    VMStateSnapshot,
)

try:
    from haifa_lua.table import LuaTable  # type: ignore
except ImportError:  # pragma: no cover - Lua frontend may be absent in some contexts
    LuaTable = None  # type: ignore[misc]


class LuaYield:
    __slots__ = ("values",)

    def __init__(self, values):
        self.values = list(values)


from .value_utils import resolve_value


@dataclass
class Cell:
    value: object


@dataclass
class CallFrame:
    return_pc: int
    param_stack: List[object]
    registers: Dict[str, object]
    upvalues: List[object]
    pending_params: List[object]
    caller_debug: InstructionDebug | None

class BytecodeVM:
    def __init__(self, instructions):
        self.instructions = instructions
        self.labels = {}
        self.registers = {}
        self.stack = []
        self.arrays = {}
        self.call_stack: List[CallFrame] = []
        self.param_stack = []
        self.pending_params = []
        self.return_value = None
        self.emit_stack = []
        self.pc = 0
        self.output = []
        self.current_upvalues = []
        self.last_return: List[object] = []
        self.last_event = None
        self.yield_values: List[object] = []
        self.awaiting_resume = False
        self.current_coroutine = None
        self._event_buffer: List[CoroutineEvent] = []
        self._coroutine_snapshots: Dict[int, CoroutineSnapshot] = {}
        self._next_coroutine_id = 1
        self._function_names: Dict[str, str] = {}
        self._last_traceback: Optional[List[TraceFrame]] = None
        # Opcode dispatch table for cleaner control flow
        self._handlers = {
            Opcode.LOAD_IMM: self._op_LOAD_IMM,
            Opcode.MOV: self._op_MOV,
            Opcode.LOAD_CONST: self._op_LOAD_CONST,
            Opcode.ADD: self._op_ADD,
            Opcode.SUB: self._op_SUB,
            Opcode.MUL: self._op_MUL,
            Opcode.DIV: self._op_DIV,
            Opcode.MOD: self._op_MOD,
            Opcode.NEG: self._op_NEG,
            Opcode.EQ: self._op_EQ,
            Opcode.GT: self._op_GT,
            Opcode.LT: self._op_LT,
            Opcode.AND: self._op_AND,
            Opcode.OR: self._op_OR,
            Opcode.NOT: self._op_NOT,
            Opcode.CLR: self._op_CLR,
            Opcode.CMP_IMM: self._op_CMP_IMM,
            Opcode.JNZ: self._op_JNZ,
            Opcode.JMP_REL: self._op_JMP_REL,
            Opcode.PUSH: self._op_PUSH,
            Opcode.POP: self._op_POP,
            Opcode.ARR_COPY: self._op_ARR_COPY,
            Opcode.IS_OBJ: self._op_IS_OBJ,
            Opcode.IS_ARR: self._op_IS_ARR,
            Opcode.IS_NULL: self._op_IS_NULL,
            Opcode.COALESCE: self._op_COALESCE,
            Opcode.MAKE_CELL: self._op_MAKE_CELL,
            Opcode.CELL_GET: self._op_CELL_GET,
            Opcode.CELL_SET: self._op_CELL_SET,
            Opcode.CLOSURE: self._op_CLOSURE,
            Opcode.CALL_VALUE: self._op_CALL_VALUE,
            Opcode.BIND_UPVALUE: self._op_BIND_UPVALUE,
            Opcode.VARARG: self._op_VARARG,
            Opcode.VARARG_FIRST: self._op_VARARG_FIRST,
            Opcode.RETURN_MULTI: self._op_RETURN_MULTI,
            Opcode.RESULT_MULTI: self._op_RESULT_MULTI,
            Opcode.RESULT_LIST: self._op_RESULT_LIST,
            Opcode.LIST_GET: self._op_LIST_GET,
            Opcode.TABLE_NEW: self._op_TABLE_NEW,
            Opcode.TABLE_SET: self._op_TABLE_SET,
            Opcode.TABLE_GET: self._op_TABLE_GET,
            Opcode.TABLE_APPEND: self._op_TABLE_APPEND,
            Opcode.TABLE_EXTEND: self._op_TABLE_EXTEND,
            Opcode.AND_BIT: self._op_AND_BIT,
            Opcode.OR_BIT: self._op_OR_BIT,
            Opcode.XOR: self._op_XOR,
            Opcode.NOT_BIT: self._op_NOT_BIT,
            Opcode.SHL: self._op_SHL,
            Opcode.SHR: self._op_SHR,
            Opcode.SAR: self._op_SAR,
            Opcode.JMP: self._op_JMP,
            Opcode.JZ: self._op_JZ,
            Opcode.LABEL: self._op_LABEL,
            # Extended core features; jq-only opcodes live in JQOpcode/JQVM
            Opcode.PARAM: self._op_PARAM,
            Opcode.ARG: self._op_ARG,
            Opcode.CALL: self._op_CALL,
            Opcode.RETURN: self._op_RETURN,
            Opcode.RESULT: self._op_RESULT,
            Opcode.PARAM_EXPAND: self._op_PARAM_EXPAND,
            Opcode.ARR_INIT: self._op_ARR_INIT,
            Opcode.ARR_SET: self._op_ARR_SET,
            Opcode.ARR_GET: self._op_ARR_GET,
            Opcode.LEN: self._op_LEN,
            Opcode.PRINT: self._op_PRINT,
            Opcode.HALT: self._op_HALT,
        }

    def val(self, x):
        return resolve_value(x, lambda name: self.registers.get(name, 0))

    def index_labels(self):
        for i, inst in enumerate(self.instructions):
            if inst.opcode == Opcode.LABEL:
                self.labels[inst.args[0]] = i
        self._index_function_names()

    def _index_function_names(self) -> None:
        pending_label: Optional[str] = None
        current_name: Optional[str] = None
        for inst in self.instructions:
            if inst.opcode == Opcode.LABEL:
                pending_label = inst.args[0]
                continue
            debug = inst.debug
            if debug is not None:
                current_name = debug.function_name
                if pending_label is not None:
                    self._function_names[pending_label] = current_name
                    pending_label = None
        if pending_label is not None and current_name is not None:
            self._function_names[pending_label] = current_name
        self._function_names.setdefault("<chunk>", "<chunk>")

    # -------------------- Debug/event helpers --------------------
    def allocate_coroutine_id(self) -> int:
        cid = self._next_coroutine_id
        self._next_coroutine_id += 1
        return cid

    def emit_event(self, event: CoroutineEvent) -> None:
        self._event_buffer.append(event)

    def drain_events(self) -> List[CoroutineEvent]:
        events = list(self._event_buffer)
        self._event_buffer.clear()
        return events

    def set_coroutine_snapshot(
        self,
        coroutine_id: int,
        *,
        status: str,
        last_yield: Sequence[object],
        last_error: Optional[str],
        function_name: str | None = None,
        last_resume_args: Sequence[object] | None = None,
        registers: Mapping[str, object] | None = None,
        upvalues: Sequence[object] | None = None,
        call_stack: Sequence[TraceFrame] | None = None,
        current_pc: Optional[int] = None,
    ) -> None:
        self._coroutine_snapshots[coroutine_id] = CoroutineSnapshot(
            coroutine_id=coroutine_id,
            status=status,
            last_yield=list(last_yield),
            last_error=last_error,
            function_name=function_name,
            last_resume_args=list(last_resume_args or []),
            registers=dict(registers) if registers is not None else None,
            upvalues=list(upvalues) if upvalues is not None else None,
            call_stack=list(call_stack) if call_stack is not None else [],
            current_pc=current_pc,
        )

    def remove_coroutine_snapshot(self, coroutine_id: int) -> None:
        self._coroutine_snapshots.pop(coroutine_id, None)

    def snapshot_state(self) -> VMStateSnapshot:
        return VMStateSnapshot(
            pc=self.pc,
            current_coroutine=getattr(self.current_coroutine, "coroutine_id", None),
            registers=dict(self.registers),
            stack=list(self.stack),
            call_stack=self._capture_traceback(),
            coroutines=list(self._coroutine_snapshots.values()),
            upvalues=list(self.current_upvalues),
            emit_stack=list(self.emit_stack),
            output=list(self.output),
        )

    def _capture_traceback(self) -> List[TraceFrame]:
        frames: List[TraceFrame] = []
        coroutine_id = getattr(self.current_coroutine, "coroutine_id", None)
        frames.append(self._frame_from_debug(self._instruction_debug(self.pc), self.pc, coroutine_id))
        for frame in reversed(self.call_stack):
            pc = frame.return_pc - 1 if frame.return_pc > 0 else frame.return_pc
            frames.append(self._frame_from_debug(frame.caller_debug, pc, coroutine_id))
        self._last_traceback = frames
        return frames

    def _instruction_debug(self, pc: int) -> InstructionDebug | None:
        if 0 <= pc < len(self.instructions):
            return self.instructions[pc].debug
        return None

    def _frame_from_debug(
        self,
        debug: InstructionDebug | None,
        pc: int,
        coroutine_id: int | None,
    ) -> TraceFrame:
        if debug is None:
            return TraceFrame(
                function_name=self._function_names.get("<chunk>", "<chunk>"),
                file="<unknown>",
                line=0,
                column=0,
                pc=pc,
                coroutine_id=coroutine_id,
            )
        location = debug.location
        return TraceFrame(
            function_name=debug.function_name,
            file=location.file,
            line=location.line,
            column=location.column,
            pc=pc,
            coroutine_id=coroutine_id,
        )

    def _wrap_runtime_error(self, exc: Exception) -> VMRuntimeError:
        message = str(exc) or exc.__class__.__name__
        frames = self._capture_traceback()
        return VMRuntimeError(message, frames)

    @property
    def last_traceback(self) -> Optional[List[TraceFrame]]:
        return self._last_traceback

    def step(self):
        """Executes a single instruction."""
        if self.pc >= len(self.instructions):
            return "halt"

        inst = self.instructions[self.pc]
        op = inst.opcode
        args = inst.args

        handler = self._handlers.get(op)
        if handler is None:
            raise VMRuntimeError(f"No handler for opcode: {op}", self._capture_traceback())

        try:
            control = handler(args)
        except VMRuntimeError:
            raise
        except Exception as exc:
            raise self._wrap_runtime_error(exc) from exc
        if control == "jump":
            return None  # PC is already updated
        if control == "halt":
            return "halt"
        if control == "yield":
            self.pc += 1
            return "yield"

        self.pc += 1
        return None

    def run(self, debug=False, stop_on_yield=False):
        self.index_labels()
        self.last_event = None
        while self.pc < len(self.instructions):
            if debug:
                inst = self.instructions[self.pc]
                print(f"[PC={self.pc}] EXEC: {inst}")
                print(f"  REGISTERS: {self.registers}")
                print(f"  OUTPUT: {self.output}\n")

            status = self.step()
            if status == "halt":
                self.last_event = "halt"
                break
            if status == "yield":
                if not stop_on_yield:
                    raise self._wrap_runtime_error(
                        RuntimeError("coroutine.yield called outside coroutine")
                    )
                self.last_event = "yield"
                break

        if self.last_event is None:
            self.last_event = "halt"
        return self.output

    # -------------------- Opcode handlers --------------------
    # 数据加载与运算
    def _op_LOAD_IMM(self, args):
        self.registers[args[0]] = int(args[1])

    def _op_MOV(self, args):
        self.registers[args[0]] = self.val(args[1])

    def _op_LOAD_CONST(self, args):
        value = args[1]
        if isinstance(value, (list, dict)):
            value = copy.deepcopy(value)
        self.registers[args[0]] = value

    def _op_ADD(self, args):
        self.registers[args[0]] = self.val(args[1]) + self.val(args[2])

    def _op_SUB(self, args):
        self.registers[args[0]] = self.val(args[1]) - self.val(args[2])

    def _op_MUL(self, args):
        self.registers[args[0]] = self.val(args[1]) * self.val(args[2])

    def _op_DIV(self, args):
        # 整数整除，保持兼容
        self.registers[args[0]] = self.val(args[1]) // self.val(args[2])

    def _op_MOD(self, args):
        self.registers[args[0]] = self.val(args[1]) % self.val(args[2])

    def _op_NEG(self, args):
        self.registers[args[0]] = -self.val(args[1])

    # 逻辑运算
    def _op_EQ(self, args):
        self.registers[args[0]] = self.val(args[1]) == self.val(args[2])

    def _op_GT(self, args):
        self.registers[args[0]] = self.val(args[1]) > self.val(args[2])

    def _op_LT(self, args):
        self.registers[args[0]] = self.val(args[1]) < self.val(args[2])

    def _op_AND(self, args):
        self.registers[args[0]] = bool(self.val(args[1])) and bool(self.val(args[2]))

    def _op_OR(self, args):
        self.registers[args[0]] = bool(self.val(args[1])) or bool(self.val(args[2]))

    def _op_NOT(self, args):
        self.registers[args[0]] = not bool(self.val(args[1]))

    def _op_CLR(self, args):
        self.registers[args[0]] = 0

    def _op_CMP_IMM(self, args):
        dst, src, imm = args
        left = self.val(src)
        imm_val = self.val(imm) if isinstance(imm, str) and not imm.lstrip("-+").isdigit() else int(imm)
        if left < imm_val:
            result = -1
        elif left > imm_val:
            result = 1
        else:
            result = 0
        self.registers[dst] = result

    def _op_MAKE_CELL(self, args):
        dst, src = args
        self.registers[dst] = Cell(self.val(src))

    def _op_CELL_GET(self, args):
        dst, cell_reg = args
        cell = self.registers.get(cell_reg)
        if not isinstance(cell, Cell):
            raise self._wrap_runtime_error(RuntimeError(f"CELL_GET expects cell in {cell_reg}"))
        self.registers[dst] = cell.value

    def _op_CELL_SET(self, args):
        cell_reg, src = args
        cell = self.registers.get(cell_reg)
        if not isinstance(cell, Cell):
            raise self._wrap_runtime_error(RuntimeError(f"CELL_SET expects cell in {cell_reg}"))
        cell.value = self.val(src)

    def _op_CLOSURE(self, args):
        if len(args) < 2:
            raise self._wrap_runtime_error(RuntimeError("CLOSURE requires destination and label"))
        dst = args[0]
        label = args[1]
        upvalues = []
        for cell_reg in args[2:]:
            cell = self.registers.get(cell_reg)
            if not isinstance(cell, Cell):
                raise self._wrap_runtime_error(RuntimeError(f"CLOSURE expects cell register, got {cell_reg}"))
            upvalues.append(cell)
        debug_name = self._function_names.get(label, label)
        self.registers[dst] = {"label": label, "upvalues": upvalues, "debug_name": debug_name}

    def _op_CALL_VALUE(self, args):
        callee_reg = args[0]
        callee = self.registers.get(callee_reg)
        pending = self.pending_params
        args_to_pass = list(pending)
        pending.clear()
        if isinstance(callee, dict) and "label" in callee:
            saved_param_stack = self.param_stack
            saved_pending = pending
            frame = CallFrame(
                return_pc=self.pc + 1,
                param_stack=saved_param_stack,
                registers=self.registers,
                upvalues=self.current_upvalues,
                pending_params=saved_pending,
                caller_debug=self._instruction_debug(self.pc),
            )
            self.call_stack.append(frame)
            self.registers = dict(self.registers)
            self.param_stack = args_to_pass
            self.pending_params = []
            self.current_upvalues = list(callee.get("upvalues", []))
            self.pc = self.labels[callee["label"]]
            return "jump"
        if getattr(callee, "__lua_builtin__", False):
            result = callee(args_to_pass, self)
        elif callable(callee):
            result = callee(*args_to_pass)
        else:
            raise self._wrap_runtime_error(
                RuntimeError(f"CALL_VALUE expects callable or closure in {callee_reg}")
            )
        if isinstance(result, LuaYield):
            if self.current_coroutine is None:
                raise self._wrap_runtime_error(RuntimeError("coroutine.yield called outside coroutine"))
            self.yield_values = list(result.values)
            self.awaiting_resume = True
            self.last_return = []
            self.return_value = None
            if hasattr(self.current_coroutine, "_set_yield"):
                self.current_coroutine._set_yield(self.yield_values)
            return "yield"
        values = self._coerce_call_result(result)
        self.last_return = values
        self.return_value = values[0] if values else None
        self.awaiting_resume = False
        return None

    def _op_BIND_UPVALUE(self, args):
        dst, index_arg = args
        if isinstance(index_arg, str) and not index_arg.lstrip("-+").isdigit():
            index = int(self.val(index_arg))
        else:
            index = int(index_arg)
        if index < 0 or index >= len(self.current_upvalues):
            raise self._wrap_runtime_error(RuntimeError("BIND_UPVALUE index out of range"))
        self.registers[dst] = self.current_upvalues[index]

    def _op_VARARG(self, args):
        dst = args[0]
        self.registers[dst] = list(self.param_stack)

    def _op_VARARG_FIRST(self, args):
        dst, src = args
        values = self.val(src)
        if isinstance(values, list) and values:
            self.registers[dst] = values[0]
        else:
            self.registers[dst] = None

    def _op_RETURN_MULTI(self, args):
        values = []
        for reg in args:
            val = self.val(reg)
            if isinstance(val, list):
                values.extend(val)
            else:
                values.append(val)
        return self._return_with(values)

    def _op_RESULT_MULTI(self, args):
        for idx, dst in enumerate(args):
            value = self.last_return[idx] if idx < len(self.last_return) else None
            self.registers[dst] = value

    def _op_RESULT_LIST(self, args):
        dst = args[0]
        self.registers[dst] = list(self.last_return)

    def _op_LIST_GET(self, args):
        dst, src, index_arg = args
        values = self.val(src)
        index = int(self.val(index_arg))
        if isinstance(values, list) and 0 <= index < len(values):
            self.registers[dst] = values[index]
        else:
            self.registers[dst] = None

    def _resolve_lua_table(self):
        global LuaTable
        if LuaTable is None:
            try:
                from haifa_lua.table import LuaTable as _LuaTable  # type: ignore
            except ImportError:
                return None
            else:
                LuaTable = _LuaTable
        return LuaTable

    def _ensure_table(self, value, reg_name: object):
        table_cls = self._resolve_lua_table()
        if table_cls is None or not isinstance(value, table_cls):
            raise self._wrap_runtime_error(
                RuntimeError(f"expected table in {reg_name}")
            )
        return value

    def _op_TABLE_NEW(self, args):
        table_cls = self._resolve_lua_table()
        if table_cls is None:
            raise self._wrap_runtime_error(RuntimeError("Lua table support is unavailable"))
        dst = args[0]
        self.registers[dst] = table_cls()

    def _op_TABLE_SET(self, args):
        table_reg, key_arg, value_arg = args
        table = self._ensure_table(self.val(table_reg), table_reg)
        key = self.val(key_arg)
        value = self.val(value_arg)
        table.raw_set(key, value)

    def _op_TABLE_GET(self, args):
        dst, table_reg, key_arg = args
        table = self._ensure_table(self.val(table_reg), table_reg)
        key = self.val(key_arg)
        self.registers[dst] = table.raw_get(key)

    def _op_TABLE_APPEND(self, args):
        table_reg, value_arg = args
        table = self._ensure_table(self.val(table_reg), table_reg)
        value = self.val(value_arg)
        table.append(value)

    def _op_TABLE_EXTEND(self, args):
        table_reg, values_arg = args
        table = self._ensure_table(self.val(table_reg), table_reg)
        values = self._coerce_call_result(self.val(values_arg))
        if values:
            table.extend(values)

    def _return_with(self, values: List[object]):
        self.last_return = list(values)
        self.return_value = self.last_return[0] if self.last_return else None
        if self.call_stack:
            frame = self.call_stack.pop()
            self.pc = frame.return_pc
            self.param_stack = frame.param_stack
            self.registers = frame.registers
            self.current_upvalues = frame.upvalues
            self.pending_params = frame.pending_params
            return "jump"
        in_coroutine = self.current_coroutine is not None
        if in_coroutine and hasattr(self.current_coroutine, "_set_result"):
            self.current_coroutine._set_result(self.last_return)

        debug = self._instruction_debug(self.pc)

        self.current_upvalues = []
        self.pending_params = []
        self.awaiting_resume = False

        if not in_coroutine and debug is None:
            self.pc += 1
            return "jump"
        return "halt"

    def prepare_resume(self, values):
        self.last_return = list(values)
        self.return_value = self.last_return[0] if self.last_return else None
        self.awaiting_resume = False

    def _coerce_call_result(self, result):
        if result is None:
            return []
        if isinstance(result, list):
            return list(result)
        if isinstance(result, tuple):
            return list(result)
        values = getattr(result, "values", None)
        if values is not None:
            return list(values)
        return [result]

    def call_callable(self, func, args: Sequence[object]) -> List[object]:
        args_list = list(args)
        saved_last_return = list(self.last_return)
        saved_return_value = self.return_value
        saved_awaiting = self.awaiting_resume
        if isinstance(func, dict) and "label" in func:
            saved_pc = self.pc
            saved_registers = self.registers
            saved_param_stack = self.param_stack
            saved_pending = self.pending_params
            saved_upvalues = self.current_upvalues
            saved_call_stack = list(self.call_stack)
            target_depth = len(saved_call_stack)
            frame = CallFrame(
                return_pc=self.pc,
                param_stack=self.param_stack,
                registers=self.registers,
                upvalues=self.current_upvalues,
                pending_params=self.pending_params,
                caller_debug=self._instruction_debug(self.pc),
            )
            self.call_stack.append(frame)
            self.registers = dict(self.registers)
            self.param_stack = list(args_list)
            self.pending_params = []
            self.current_upvalues = list(func.get("upvalues", []))
            self.pc = self.labels[func["label"]]
            result: List[object] = []
            try:
                while True:
                    status = self.step()
                    if status == "yield":
                        raise self._wrap_runtime_error(
                            RuntimeError("cannot yield from builtin helper call")
                        )
                    if status == "halt":
                        break
                    if len(self.call_stack) <= target_depth:
                        break
                result = list(self.last_return)
            finally:
                self.pc = saved_pc
                self.registers = saved_registers
                self.param_stack = saved_param_stack
                self.pending_params = saved_pending
                self.current_upvalues = saved_upvalues
                self.call_stack = saved_call_stack
                self.last_return = saved_last_return
                self.return_value = saved_return_value
                self.awaiting_resume = saved_awaiting
            return result
        if getattr(func, "__lua_builtin__", False):
            result = func(args_list, self)
            values = self._coerce_call_result(result)
        elif callable(func):
            result = func(*args_list)
            values = self._coerce_call_result(result)
        else:
            raise self._wrap_runtime_error(RuntimeError("expected callable"))
        self.last_return = saved_last_return
        self.return_value = saved_return_value
        self.awaiting_resume = saved_awaiting
        return values

    # 位运算
    def _op_AND_BIT(self, args):
        self.registers[args[0]] = self.val(args[1]) & self.val(args[2])

    def _op_OR_BIT(self, args):
        self.registers[args[0]] = self.val(args[1]) | self.val(args[2])

    def _op_XOR(self, args):
        self.registers[args[0]] = self.val(args[1]) ^ self.val(args[2])

    def _op_NOT_BIT(self, args):
        self.registers[args[0]] = ~self.val(args[1])

    def _op_SHL(self, args):
        self.registers[args[0]] = self.val(args[1]) << self.val(args[2])

    def _op_SHR(self, args):
        self.registers[args[0]] = (self.val(args[1]) % (1 << 32)) >> self.val(args[2])

    def _op_SAR(self, args):
        self.registers[args[0]] = self.val(args[1]) >> self.val(args[2])

    # 控制流
    def _op_JMP(self, args):
        self.pc = self.labels[args[0]]
        return "jump"

    def _op_JZ(self, args):
        if not bool(self.val(args[0])):
            self.pc = self.labels[args[1]]
            return "jump"

    def _op_JNZ(self, args):
        if bool(self.val(args[0])):
            self.pc = self.labels[args[1]]
            return "jump"

    def _op_JMP_REL(self, args):
        offset = int(self.val(args[0]))
        self.pc += offset
        return "jump"

    def _op_LABEL(self, args):
        pass

    # 函数调用
    def _op_PARAM(self, args):
        self.pending_params.append(self.val(args[0]))

    def _op_PARAM_EXPAND(self, args):
        values = self.val(args[0])
        if isinstance(values, list):
            self.pending_params.extend(list(values))
        else:
            self.pending_params.append(values)

    def _op_ARG(self, args):
        if self.param_stack:
            self.registers[args[0]] = self.param_stack.pop(0)

    def _op_CALL(self, args):
        target = args[0]
        saved_param_stack = self.param_stack
        saved_pending = self.pending_params
        args_to_pass = list(saved_pending)
        saved_pending.clear()
        frame = CallFrame(
            return_pc=self.pc + 1,
            param_stack=saved_param_stack,
            registers=self.registers,
            upvalues=self.current_upvalues,
            pending_params=saved_pending,
            caller_debug=self._instruction_debug(self.pc),
        )
        self.call_stack.append(frame)
        self.registers = dict(self.registers)
        self.param_stack = args_to_pass
        self.pending_params = []
        self.current_upvalues = []
        self.pc = self.labels[target]
        return "jump"

    def _op_RETURN(self, args):
        value = self.val(args[0]) if args else None
        return self._return_with([value])

    def _op_RESULT(self, args):
        value = self.last_return[0] if self.last_return else None
        self.registers[args[0]] = value

    # 数组操作
    def _op_ARR_INIT(self, args):
        size = int(self.val(args[1]))
        self.arrays[args[0]] = [0] * size

    def _op_ARR_SET(self, args):
        array = self.arrays.setdefault(args[0], [])
        index = int(self.val(args[1]))
        value = self.val(args[2])
        if 0 <= index < len(array):
            array[index] = value

    def _op_ARR_GET(self, args):
        array = self.arrays.get(args[1], [])
        index = int(self.val(args[2]))
        value = array[index] if 0 <= index < len(array) else None
        self.registers[args[0]] = value

    def _op_LEN(self, args):
        dst, src = args
        value = self.val(src)
        if LuaTable is not None and isinstance(value, LuaTable):
            self.registers[dst] = value.lua_len()
            return
        if isinstance(value, (list, tuple, str)):
            self.registers[dst] = len(value)
            return
        array = self.arrays.get(src, [])
        self.registers[dst] = len(array)

    def _op_PUSH(self, args):
        self.stack.append(self.val(args[0]))

    def _op_POP(self, args):
        if not self.stack:
            self.registers[args[0]] = None
        else:
            self.registers[args[0]] = self.stack.pop()

    def _op_ARR_COPY(self, args):
        dst_name, src_name, start_arg, length_arg = args
        start = int(self.val(start_arg))
        length = int(self.val(length_arg))
        src = self.arrays.get(src_name, [])
        copy_slice = list(src[start:start + length]) if length >= 0 else []
        self.arrays[dst_name] = copy_slice

    def _op_IS_OBJ(self, args):
        self.registers[args[0]] = int(isinstance(self.val(args[1]), dict))

    def _op_IS_ARR(self, args):
        self.registers[args[0]] = int(isinstance(self.val(args[1]), list))

    def _op_IS_NULL(self, args):
        self.registers[args[0]] = int(self.val(args[1]) is None)

    def _op_COALESCE(self, args):
        dst, lhs, rhs = args
        left_val = self.val(lhs)
        if left_val is None:
            self.registers[dst] = self.val(rhs)
        else:
            self.registers[dst] = left_val

    # 输出/终止
    def _op_PRINT(self, args):
        self.output.append(self.val(args[0]))

    def _op_HALT(self, args):
        return "halt"
