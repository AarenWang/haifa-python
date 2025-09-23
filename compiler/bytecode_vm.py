import copy
import json

from bytecode import Opcode, Instruction
from value_utils import resolve_value

class BytecodeVM:
    def __init__(self, instructions):
        self.instructions = instructions
        self.labels = {}
        self.registers = {}
        self.stack = []
        self.arrays = {}
        self.call_stack = []
        self.param_stack = []
        self.return_value = None
        self.emit_stack = []
        self.pc = 0
        self.output = []
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
            Opcode.OBJ_GET: self._op_OBJ_GET,
            Opcode.GET_INDEX: self._op_GET_INDEX,
            Opcode.LEN_VALUE: self._op_LEN_VALUE,
            Opcode.OBJ_SET: self._op_OBJ_SET,
            Opcode.FLATTEN: self._op_FLATTEN,
            Opcode.REDUCE: self._op_REDUCE,
            Opcode.PUSH_EMIT: self._op_PUSH_EMIT,
            Opcode.POP_EMIT: self._op_POP_EMIT,
            Opcode.EMIT: self._op_EMIT,
            Opcode.PARAM: self._op_PARAM,
            Opcode.ARG: self._op_ARG,
            Opcode.CALL: self._op_CALL,
            Opcode.RETURN: self._op_RETURN,
            Opcode.RESULT: self._op_RESULT,
            Opcode.ARR_INIT: self._op_ARR_INIT,
            Opcode.ARR_SET: self._op_ARR_SET,
            Opcode.ARR_GET: self._op_ARR_GET,
            Opcode.LEN: self._op_LEN,
            Opcode.KEYS: self._op_KEYS,
            Opcode.HAS: self._op_HAS,
            Opcode.CONTAINS: self._op_CONTAINS,
            Opcode.JOIN: self._op_JOIN,
            Opcode.REVERSE: self._op_REVERSE,
            Opcode.FIRST: self._op_FIRST,
            Opcode.LAST: self._op_LAST,
            Opcode.ANY: self._op_ANY,
            Opcode.ALL: self._op_ALL,
            Opcode.AGG_ADD: self._op_AGG_ADD,
            Opcode.SORT: self._op_SORT,
            Opcode.SORT_BY: self._op_SORT_BY,
            Opcode.UNIQUE: self._op_UNIQUE,
            Opcode.UNIQUE_BY: self._op_UNIQUE_BY,
            Opcode.MIN: self._op_MIN,
            Opcode.MAX: self._op_MAX,
            Opcode.MIN_BY: self._op_MIN_BY,
            Opcode.MAX_BY: self._op_MAX_BY,
            Opcode.GROUP_BY: self._op_GROUP_BY,
            Opcode.PRINT: self._op_PRINT,
            Opcode.HALT: self._op_HALT,
        }

    def val(self, x):
        return resolve_value(x, lambda name: self.registers.get(name, 0))

    def index_labels(self):
        for i, inst in enumerate(self.instructions):
            if inst.opcode == Opcode.LABEL:
                self.labels[inst.args[0]] = i

    def run(self, debug=False):
        self.index_labels()
        while self.pc < len(self.instructions):
            inst = self.instructions[self.pc]
            op = inst.opcode
            args = inst.args

            if debug:
                print(f"[PC={self.pc}] EXEC: {inst}")
                print(f"  REGISTERS: {self.registers}")
                print(f"  OUTPUT: {self.output}\n")

            handler = self._handlers.get(op)
            if handler is None:
                raise RuntimeError(f"No handler for opcode: {op}")
            control = handler(args)
            if control == "jump":
                continue
            if control == "halt":
                break
            self.pc += 1

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
        self.registers[args[0]] = int(self.val(args[1]) == self.val(args[2]))

    def _op_GT(self, args):
        self.registers[args[0]] = int(self.val(args[1]) > self.val(args[2]))

    def _op_LT(self, args):
        self.registers[args[0]] = int(self.val(args[1]) < self.val(args[2]))

    def _op_AND(self, args):
        self.registers[args[0]] = int(bool(self.val(args[1])) and bool(self.val(args[2])))

    def _op_OR(self, args):
        self.registers[args[0]] = int(bool(self.val(args[1])) or bool(self.val(args[2])))

    def _op_NOT(self, args):
        self.registers[args[0]] = int(not bool(self.val(args[1])))

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

    def _op_LABEL(self, args):
        pass

    # 访问与长度/集合
    def _op_OBJ_GET(self, args):
        source = self.val(args[1])
        key = args[2]
        if isinstance(source, dict) and key in source:
            self.registers[args[0]] = source[key]
        else:
            self.registers[args[0]] = None

    def _op_GET_INDEX(self, args):
        container = self.val(args[1])
        index = int(self.val(args[2]))
        value = None
        if isinstance(container, (list, tuple)) and -len(container) <= index < len(container):
            value = container[index]
        self.registers[args[0]] = value

    def _op_LEN_VALUE(self, args):
        value = self.val(args[1])
        try:
            self.registers[args[0]] = len(value)
        except (TypeError, ValueError):
            self.registers[args[0]] = 0

    def _op_OBJ_SET(self, args):
        obj = self.registers.get(args[0])
        if not isinstance(obj, dict):
            obj = {}
            self.registers[args[0]] = obj
        obj[args[1]] = self.val(args[2])

    def _op_FLATTEN(self, args):
        value = self.val(args[1])
        if isinstance(value, list):
            flattened = []
            for item in value:
                if isinstance(item, list):
                    flattened.extend(item)
                else:
                    flattened.append(item)
        elif value is None:
            flattened = []
        else:
            flattened = value
        self.registers[args[0]] = flattened

    def _op_REDUCE(self, args):
        items_source = self.val(args[1])
        if isinstance(items_source, (list, tuple)):
            items = list(items_source)
        elif items_source is None:
            items = []
        else:
            items = [items_source]
        op_name = str(args[2]).lower()
        has_initial = len(args) > 3 and args[3] not in (None, "")
        initial_value = self.val(args[3]) if has_initial else None

        if op_name == "sum":
            acc = initial_value if has_initial else 0
            for item in items:
                if item is not None:
                    acc += item
        elif op_name == "product":
            acc = initial_value if has_initial else 1
            for item in items:
                if item is not None:
                    acc *= item
        elif op_name == "min":
            if has_initial:
                acc = initial_value
            elif items:
                acc = items[0]
                items = items[1:]
            else:
                acc = None
            for item in items:
                if acc is None or (item is not None and item < acc):
                    acc = item
        elif op_name == "max":
            if has_initial:
                acc = initial_value
            elif items:
                acc = items[0]
                items = items[1:]
            else:
                acc = None
            for item in items:
                if acc is None or (item is not None and item > acc):
                    acc = item
        elif op_name == "concat":
            if has_initial:
                acc = initial_value
            else:
                acc = []
            if acc is None:
                acc = []
            if not isinstance(acc, list):
                acc = [acc]
            for item in items:
                if isinstance(item, list):
                    acc.extend(item)
                elif item is not None:
                    acc.append(item)
        else:
            raise RuntimeError(f"Unsupported reduce operation: {op_name}")
        self.registers[args[0]] = acc

    # Emit 栈
    def _op_PUSH_EMIT(self, args):
        self.emit_stack.append(args[0])

    def _op_POP_EMIT(self, args):
        if self.emit_stack:
            self.emit_stack.pop()

    def _op_EMIT(self, args):
        value = self.val(args[0])
        if self.emit_stack:
            target = self.emit_stack[-1]
            container = self.registers.get(target)
            if not isinstance(container, list):
                container = [] if container is None else list(container if isinstance(container, list) else [container])
            container.append(value)
            self.registers[target] = container
        else:
            self.output.append(value)

    # 函数调用
    def _op_PARAM(self, args):
        self.param_stack.append(self.val(args[0]))

    def _op_ARG(self, args):
        if self.param_stack:
            self.registers[args[0]] = self.param_stack.pop(0)

    def _op_CALL(self, args):
        target = args[0]
        saved_params = self.param_stack
        self.call_stack.append((self.pc + 1, saved_params, self.registers))
        self.registers = dict(self.registers)
        self.param_stack = list(saved_params)
        saved_params.clear()
        self.pc = self.labels[target]
        return "jump"

    def _op_RETURN(self, args):
        self.return_value = self.val(args[0]) if args else None
        if self.call_stack:
            self.pc, self.param_stack, self.registers = self.call_stack.pop()
            return "jump"

    def _op_RESULT(self, args):
        self.registers[args[0]] = self.return_value

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
        array = self.arrays.get(args[1], [])
        self.registers[args[0]] = len(array)

    # jq core filters
    def _op_KEYS(self, args):
        src = self.val(args[1])
        keys = []
        if isinstance(src, dict):
            try:
                keys = sorted(list(src.keys()))
            except Exception:
                keys = list(src.keys())
        elif isinstance(src, (list, tuple)):
            keys = list(range(len(src)))
        self.registers[args[0]] = keys

    def _op_HAS(self, args):
        container = self.val(args[1])
        needle = self.val(args[2])
        result = False
        if isinstance(container, dict) and isinstance(needle, str):
            result = needle in container
        elif isinstance(container, (list, tuple)):
            try:
                idx = int(needle)
                result = -len(container) <= idx < len(container)
            except Exception:
                result = False
        self.registers[args[0]] = int(result)

    def _op_CONTAINS(self, args):
        container = self.val(args[1])
        needle = self.val(args[2])
        result = False
        if isinstance(container, str) and isinstance(needle, str):
            result = needle in container
        elif isinstance(container, list):
            try:
                result = any(item == needle for item in container)
            except Exception:
                result = False
        elif isinstance(container, dict):
            if isinstance(needle, str):
                result = needle in container
            elif isinstance(needle, dict):
                result = all(k in container and container[k] == v for k, v in needle.items())
        self.registers[args[0]] = int(result)

    def _op_JOIN(self, args):
        arr = self.val(args[1])
        sep = str(self.val(args[2]))
        if isinstance(arr, list):
            try:
                s = sep.join(str(x) if x is not None else "null" for x in arr)
            except Exception:
                s = sep.join(map(str, arr))
            self.registers[args[0]] = s
        else:
            self.registers[args[0]] = ""

    def _op_REVERSE(self, args):
        val = self.val(args[1])
        if isinstance(val, list):
            self.registers[args[0]] = list(reversed(val))
        elif isinstance(val, str):
            self.registers[args[0]] = val[::-1]
        else:
            self.registers[args[0]] = val

    def _op_FIRST(self, args):
        val = self.val(args[1])
        out = None
        if isinstance(val, list):
            out = val[0] if val else None
        elif isinstance(val, str):
            out = val[0] if val else None
        self.registers[args[0]] = out

    def _op_LAST(self, args):
        val = self.val(args[1])
        out = None
        if isinstance(val, list):
            out = val[-1] if val else None
        elif isinstance(val, str):
            out = val[-1] if val else None
        self.registers[args[0]] = out

    def _op_ANY(self, args):
        val = self.val(args[1])
        if isinstance(val, list):
            self.registers[args[0]] = int(any(bool(x) for x in val))
        else:
            self.registers[args[0]] = int(bool(val))

    def _op_ALL(self, args):
        val = self.val(args[1])
        if isinstance(val, list):
            self.registers[args[0]] = int(all(bool(x) for x in val))
        else:
            self.registers[args[0]] = int(bool(val))

    def _op_AGG_ADD(self, args):
        val = self.val(args[1])
        out = None
        if isinstance(val, list):
            if all(isinstance(x, (int, float, bool)) for x in val):
                s = 0
                for x in val:
                    if x is not None:
                        s += x
                out = s
            elif all(isinstance(x, str) for x in val):
                out = "".join(val)
            elif all(isinstance(x, list) for x in val):
                res = []
                for x in val:
                    res.extend(x)
                out = res
        self.registers[args[0]] = out

    # ---------- Sorting & aggregation family ----------
    def _sort_key(self, x):
        # Provide a robust key for mixed types: (rank, value)
        # Ranks: None < bool < number < string < list < dict < other
        if x is None:
            return (0, 0)
        if isinstance(x, bool):
            return (1, int(x))
        if isinstance(x, (int, float)):
            return (2, x)
        if isinstance(x, str):
            return (3, x)
        if isinstance(x, list):
            try:
                return (4, [self._sort_key(v) for v in x])
            except Exception:
                return (4, len(x))
        if isinstance(x, dict):
            try:
                items = sorted((str(k), x[k]) for k in x.keys())
                return (5, [(k, self._sort_key(v)) for k, v in items])
            except Exception:
                # Fallback to JSON string for stability
                return (5, json.dumps(x, sort_keys=True, ensure_ascii=False))
        return (6, str(x))

    def _op_SORT(self, args):
        src = self.val(args[1])
        if isinstance(src, list):
            out = sorted(src, key=self._sort_key)
        else:
            out = src
        self.registers[args[0]] = out

    def _op_SORT_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        if isinstance(src, list) and isinstance(keys, list):
            pairs = list(zip(keys, src))
            pairs.sort(key=lambda kv: self._sort_key(kv[0]))
            out = [v for _, v in pairs]
        else:
            out = src
        self.registers[args[0]] = out

    def _op_UNIQUE(self, args):
        src = self.val(args[1])
        if isinstance(src, list):
            seen = []
            out = []
            for v in src:
                if not any(v == s for s in seen):
                    seen.append(v)
                    out.append(v)
        else:
            out = src
        self.registers[args[0]] = out

    def _op_UNIQUE_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        if isinstance(src, list) and isinstance(keys, list):
            seen = []
            out = []
            for k, v in zip(keys, src):
                sk = self._sort_key(k)
                if sk not in seen:
                    seen.append(sk)
                    out.append(v)
        else:
            out = src
        self.registers[args[0]] = out

    def _op_MIN(self, args):
        src = self.val(args[1])
        out = None
        if isinstance(src, list) and src:
            out = min(src, key=self._sort_key)
        self.registers[args[0]] = out

    def _op_MAX(self, args):
        src = self.val(args[1])
        out = None
        if isinstance(src, list) and src:
            out = max(src, key=self._sort_key)
        self.registers[args[0]] = out

    def _op_MIN_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        out = None
        if isinstance(src, list) and isinstance(keys, list) and src:
            idx = min(range(len(src)), key=lambda i: self._sort_key(keys[i]))
            out = src[idx]
        self.registers[args[0]] = out

    def _op_MAX_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        out = None
        if isinstance(src, list) and isinstance(keys, list) and src:
            idx = max(range(len(src)), key=lambda i: self._sort_key(keys[i]))
            out = src[idx]
        self.registers[args[0]] = out

    def _op_GROUP_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        out = []
        if isinstance(src, list) and isinstance(keys, list):
            # stable sort by key then group contiguous equal keys
            pairs = list(zip(keys, src))
            pairs.sort(key=lambda kv: self._sort_key(kv[0]))
            current_key = object()
            bucket = []
            for k, v in pairs:
                sk = self._sort_key(k)
                if bucket and sk != current_key:
                    out.append(bucket)
                    bucket = []
                current_key = sk
                bucket.append(v)
            if bucket:
                out.append(bucket)
        self.registers[args[0]] = out

    # 输出/终止
    def _op_PRINT(self, args):
        self.output.append(self.val(args[0]))

    def _op_HALT(self, args):
        return "halt"
