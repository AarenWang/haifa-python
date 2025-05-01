from abc import ABC, abstractmethod

class Context:
    def __init__(self, script):
        self.registers = {}
        self.arrays = {}
        self.functions = {}
        self.labels = {}
        self.call_stack = []
        self.param_stack = []
        self.output = []
        self.return_value = None
        self.loop_stack = []
        self.pc = 0
        self.script = script

    def val(self, x):
        if x.lstrip('-').isdigit():
            return int(x)
        return self.registers.get(x, 0)


class Expression(ABC):
    @abstractmethod
    def interpret(self, context: Context):
        pass


class Mov(Expression):
    def __init__(self, dst, src):
        self.dst = dst
        self.src = src

    def interpret(self, context: Context):
        context.registers[self.dst] = context.val(self.src)


class Add(Expression):
    def __init__(self, dst, lhs, rhs):
        self.dst = dst
        self.lhs = lhs
        self.rhs = rhs

    def interpret(self, context: Context):
        context.registers[self.dst] = context.val(self.lhs) + context.val(self.rhs)


class Mul(Expression):
    def __init__(self, dst, lhs, rhs):
        self.dst = dst
        self.lhs = lhs
        self.rhs = rhs

    def interpret(self, context: Context):
        context.registers[self.dst] = context.val(self.lhs) * context.val(self.rhs)


class Print(Expression):
    def __init__(self, var):
        self.var = var

    def interpret(self, context: Context):
        context.output.append(context.registers.get(self.var, 0))


class NoOp(Expression):
    def interpret(self, context: Context):
        pass


class Interpreter:
    def __init__(self, script_lines):
        self.context = Context(script_lines)
        self.instructions = self.parse(script_lines)

    def parse(self, lines):
        expressions = []
        for line in lines:
            parts = line.strip().split()
            if not parts:
                expressions.append(NoOp())
                continue
            op = parts[0].upper()
            args = parts[1:]
            expressions.append(self.create_expression(op, args))
        return expressions

    def create_expression(self, op, args):
        if op == "MOV":
            return Mov(*args)
        elif op == "ADD":
            return Add(*args)
        elif op == "MUL":
            return Mul(*args)
        elif op == "PRINT":
            return Print(*args)
        else:
            return NoOp()

    def run(self):
        while self.context.pc < len(self.instructions):
            instr = self.instructions[self.context.pc]
            instr.interpret(self.context)
            self.context.pc += 1
        return self.context.output


if __name__ == "__main__":
    script = [
        "MOV a 10",
        "MOV b 20",
        "ADD c a b",
        "PRINT c",
        "MUL d a b",
        "PRINT d"
    ]
    interpreter = Interpreter(script)
    output = interpreter.run()
    print(f"Output: {output}")
