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
                self.registers[args[0]] = args[1]
            elif op == Opcode.ADD:
                self.registers[args[0]] = self.val(args[1]) + self.val(args[2])
            elif op == Opcode.SUB:
                self.registers[args[0]] = self.val(args[1]) - self.val(args[2])
            elif op == Opcode.MUL:
                self.registers[args[0]] = self.val(args[1]) * self.val(args[2])
            elif op == Opcode.DIV:
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
                if self.val(args[0]) == 0:
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
