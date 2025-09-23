import copy

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

            # 数据加载与运算
            if op == Opcode.LOAD_IMM:
                self.registers[args[0]] = int(args[1])
            elif op == Opcode.MOV:
                self.registers[args[0]] = self.val(args[1])
            elif op == Opcode.LOAD_CONST:
                value = args[1]
                if isinstance(value, (list, dict)):
                    value = copy.deepcopy(value)
                self.registers[args[0]] = value
            elif op == Opcode.ADD:
                self.registers[args[0]] = self.val(args[1]) + self.val(args[2])
            elif op == Opcode.SUB:
                self.registers[args[0]] = self.val(args[1]) - self.val(args[2])
            elif op == Opcode.MUL:
                self.registers[args[0]] = self.val(args[1]) * self.val(args[2])
            elif op == Opcode.DIV:
                # 保持与现有测试一致：整数整除
                self.registers[args[0]] = self.val(args[1]) // self.val(args[2])
            elif op == Opcode.MOD:
                self.registers[args[0]] = self.val(args[1]) % self.val(args[2])
            elif op == Opcode.NEG:
                self.registers[args[0]] = -self.val(args[1])

            # 逻辑运算
            elif op == Opcode.EQ:
                self.registers[args[0]] = int(self.val(args[1]) == self.val(args[2]))
            elif op == Opcode.GT:
                self.registers[args[0]] = int(self.val(args[1]) > self.val(args[2]))
            elif op == Opcode.LT:
                self.registers[args[0]] = int(self.val(args[1]) < self.val(args[2]))
            elif op == Opcode.AND:
                self.registers[args[0]] = int(bool(self.val(args[1])) and bool(self.val(args[2])))
            elif op == Opcode.OR:
                self.registers[args[0]] = int(bool(self.val(args[1])) or bool(self.val(args[2])))
            elif op == Opcode.NOT:
                self.registers[args[0]] = int(not bool(self.val(args[1])))

            # 位运算
            elif op == Opcode.AND_BIT:
                self.registers[args[0]] = self.val(args[1]) & self.val(args[2])
            elif op == Opcode.OR_BIT:
                self.registers[args[0]] = self.val(args[1]) | self.val(args[2])
            elif op == Opcode.XOR:
                self.registers[args[0]] = self.val(args[1]) ^ self.val(args[2])
            elif op == Opcode.NOT_BIT:
                self.registers[args[0]] = ~self.val(args[1])
            elif op == Opcode.SHL:
                self.registers[args[0]] = self.val(args[1]) << self.val(args[2])
            elif op == Opcode.SHR:
                self.registers[args[0]] = (self.val(args[1]) % (1 << 32)) >> self.val(args[2])
            elif op == Opcode.SAR:
                self.registers[args[0]] = self.val(args[1]) >> self.val(args[2])

            # 控制流
            elif op == Opcode.JMP:
                self.pc = self.labels[args[0]]
                continue
            elif op == Opcode.JZ:
                # 统一真值语义：Python falsy 视为跳转（False/None/0/""/[]/{}/...）
                if not bool(self.val(args[0])):
                    self.pc = self.labels[args[1]]
                    continue
            elif op == Opcode.LABEL:
                pass
            elif op == Opcode.OBJ_GET:
                source = self.val(args[1])
                key = args[2]
                if isinstance(source, dict) and key in source:
                    self.registers[args[0]] = source[key]
                else:
                    self.registers[args[0]] = None
            elif op == Opcode.GET_INDEX:
                container = self.val(args[1])
                index = int(self.val(args[2]))
                value = None
                if isinstance(container, (list, tuple)) and -len(container) <= index < len(container):
                    value = container[index]
                self.registers[args[0]] = value
            elif op == Opcode.LEN_VALUE:
                value = self.val(args[1])
                try:
                    self.registers[args[0]] = len(value)
                except (TypeError, ValueError):
                    self.registers[args[0]] = 0
            elif op == Opcode.OBJ_SET:
                obj = self.registers.get(args[0])
                if not isinstance(obj, dict):
                    obj = {}
                    self.registers[args[0]] = obj
                obj[args[1]] = self.val(args[2])
            elif op == Opcode.FLATTEN:
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
            elif op == Opcode.REDUCE:
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
            elif op == Opcode.PUSH_EMIT:
                self.emit_stack.append(args[0])
            elif op == Opcode.POP_EMIT:
                if self.emit_stack:
                    self.emit_stack.pop()
            elif op == Opcode.EMIT:
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
            elif op == Opcode.PARAM:
                self.param_stack.append(self.val(args[0]))
            elif op == Opcode.ARG:
                if self.param_stack:
                    self.registers[args[0]] = self.param_stack.pop(0)
            elif op == Opcode.CALL:
                target = args[0]
                saved_params = self.param_stack
                self.call_stack.append((self.pc + 1, saved_params, self.registers))
                self.registers = dict(self.registers)
                self.param_stack = list(saved_params)
                saved_params.clear()
                self.pc = self.labels[target]
                continue
            elif op == Opcode.RETURN:
                self.return_value = self.val(args[0]) if args else None
                if self.call_stack:
                    self.pc, self.param_stack, self.registers = self.call_stack.pop()
                    continue
            elif op == Opcode.RESULT:
                self.registers[args[0]] = self.return_value

            # 数组操作
            elif op == Opcode.ARR_INIT:
                size = int(self.val(args[1]))
                self.arrays[args[0]] = [0] * size
            elif op == Opcode.ARR_SET:
                array = self.arrays.setdefault(args[0], [])
                index = int(self.val(args[1]))
                value = self.val(args[2])
                if 0 <= index < len(array):
                    array[index] = value
            elif op == Opcode.ARR_GET:
                array = self.arrays.get(args[1], [])
                index = int(self.val(args[2]))
                value = array[index] if 0 <= index < len(array) else None
                self.registers[args[0]] = value
            elif op == Opcode.LEN:
                array = self.arrays.get(args[1], [])
                self.registers[args[0]] = len(array)

            # 输出
            elif op == Opcode.PRINT:
                self.output.append(self.val(args[0]))
            elif op == Opcode.HALT:
                break

            self.pc += 1

        return self.output
