import copy

from .bytecode import Opcode, Instruction
from .value_utils import resolve_value

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
            # Extended core features; jq-only opcodes live in JQOpcode/JQVM
            Opcode.PARAM: self._op_PARAM,
            Opcode.ARG: self._op_ARG,
            Opcode.CALL: self._op_CALL,
            Opcode.RETURN: self._op_RETURN,
            Opcode.RESULT: self._op_RESULT,
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

    def step(self):
        """Executes a single instruction."""
        if self.pc >= len(self.instructions):
            return "halt"

        inst = self.instructions[self.pc]
        op = inst.opcode
        args = inst.args

        handler = self._handlers.get(op)
        if handler is None:
            raise RuntimeError(f"No handler for opcode: {op}")

        control = handler(args)
        if control == "jump":
            return None  # PC is already updated
        if control == "halt":
            return "halt"

        self.pc += 1
        return None

    def run(self, debug=False):
        self.index_labels()
        while self.pc < len(self.instructions):
            if debug:
                inst = self.instructions[self.pc]
                print(f"[PC={self.pc}] EXEC: {inst}")
                print(f"  REGISTERS: {self.registers}")
                print(f"  OUTPUT: {self.output}\n")

            if self.step() == "halt":
                break

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

    # 输出/终止
    def _op_PRINT(self, args):
        self.output.append(self.val(args[0]))

    def _op_HALT(self, args):
        return "halt"
