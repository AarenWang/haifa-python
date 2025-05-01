from bytecode import Opcode, Instruction

class BytecodeVM:
    def __init__(self, instructions):
        self.instructions = instructions
        self.labels = {}
        self.registers = {}
        self.stack = []
        self.pc = 0
        self.output = []

    def val(self, x):
        return int(x) if x.lstrip('-').isdigit() else self.registers.get(x, 0)

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

            # 输出
            elif op == Opcode.PRINT:
                self.output.append(self.val(args[0]))
            elif op == Opcode.HALT:
                break

            self.pc += 1

        return self.output
