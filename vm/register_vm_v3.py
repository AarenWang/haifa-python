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


class Sub(Expression):
    def __init__(self, dst, lhs, rhs):
        self.dst = dst
        self.lhs = lhs
        self.rhs = rhs

    def interpret(self, context: Context):
        context.registers[self.dst] = context.val(self.lhs) - context.val(self.rhs)


class Mul(Expression):
    def __init__(self, dst, lhs, rhs):
        self.dst = dst
        self.lhs = lhs
        self.rhs = rhs

    def interpret(self, context: Context):
        context.registers[self.dst] = context.val(self.lhs) * context.val(self.rhs)


class Lt(Expression):
    def __init__(self, dst, lhs, rhs):
        self.dst = dst
        self.lhs = lhs
        self.rhs = rhs

    def interpret(self, context: Context):
        context.registers[self.dst] = int(context.val(self.lhs) < context.val(self.rhs))


class Jz(Expression):
    def __init__(self, cond, label):
        self.cond = cond
        self.label = label

    def interpret(self, context: Context):
        if context.val(self.cond) == 0:
            context.pc = context.labels[self.label] - 1


class Label(Expression):
    def __init__(self, name):
        self.name = name

    def interpret(self, context: Context):
        pass


class Func(Expression):
    def __init__(self, name):
        self.name = name

    def interpret(self, context: Context):
        pass  # function position already handled in parse()


class EndFunc(Expression):
    def interpret(self, context: Context):
        if context.call_stack:
            context.pc, saved_registers, saved_param_stack = context.call_stack.pop()
            # Restore register state and param stack
            context.registers = saved_registers
            context.param_stack = saved_param_stack
            context.pc -= 1


class Call(Expression):
    def __init__(self, name):
        self.name = name

    def interpret(self, context: Context):
        # Save current register state
        saved_registers = dict(context.registers)
        # Save current n value
        current_n = context.registers.get('n', 0)
        # Don't save param stack, it should be empty at this point
        context.call_stack.append((context.pc + 1, saved_registers, current_n))
        context.pc = context.functions[self.name] - 1


class Param(Expression):
    def __init__(self, value):
        self.value = value

    def interpret(self, context: Context):
        context.param_stack.append(context.val(self.value))


class Arg(Expression):
    def __init__(self, dst):
        self.dst = dst

    def interpret(self, context: Context):
        if context.param_stack:
            context.registers[self.dst] = context.param_stack.pop(0)


class Return(Expression):
    def __init__(self, value):
        self.value = value

    def interpret(self, context: Context):
        context.return_value = context.val(self.value)
        print(f"Returning value: {context.return_value}")
        if context.call_stack:
            context.pc, saved_registers, saved_n = context.call_stack.pop()
            # Restore register state
            context.registers = saved_registers
            # Restore n value
            context.registers['n'] = saved_n
            context.pc -= 1


class Result(Expression):
    def __init__(self, dst):
        self.dst = dst

    def interpret(self, context: Context):
        print(f"Setting {self.dst} to return value: {context.return_value}")
        context.registers[self.dst] = context.return_value


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
        for i, line in enumerate(lines):
            parts = line.strip().split()
            if not parts:
                expressions.append(NoOp())
                continue
            op = parts[0].upper()
            args = parts[1:]
            expr = self.create_expression(op, args)
            expressions.append(expr)
        # After expressions parsed, collect function/label addresses
        for idx, expr in enumerate(expressions):
            if isinstance(expr, Func):
                self.context.functions[expr.name] = idx + 1
            elif isinstance(expr, Label):
                self.context.labels[expr.name] = idx
        return expressions

    def create_expression(self, op, args):
        if op == "MOV": return Mov(*args)
        elif op == "ADD": return Add(*args)
        elif op == "SUB": return Sub(*args)
        elif op == "MUL": return Mul(*args)
        elif op == "LT": return Lt(*args)
        elif op == "JZ": return Jz(*args)
        elif op == "LABEL": return Label(*args)
        elif op == "FUNC": return Func(*args)
        elif op == "ENDFUNC": return EndFunc()
        elif op == "CALL": return Call(*args)
        elif op == "PARAM": return Param(*args)
        elif op == "ARG": return Arg(*args)
        elif op == "RETURN": return Return(*args)
        elif op == "RESULT": return Result(*args)
        elif op == "PRINT": return Print(*args)
        else: return NoOp()

    def run(self):
        while self.context.pc < len(self.instructions):
            instr = self.instructions[self.context.pc]
            print(f"PC: {self.context.pc}, Instruction: {instr.__class__.__name__}")
            print(f"Registers: {self.context.registers}")
            print(f"Param Stack: {self.context.param_stack}")
            print(f"Call Stack: {self.context.call_stack}")
            instr.interpret(self.context)
            self.context.pc += 1
            print("---")
        return self.context.output


if __name__ == "__main__":
    script = [
        "FUNC fact",
        "ARG n",
        "MOV one 1",
        "LT cond n one",
        "JZ cond recurse",
        "MOV ret 1",
        "RETURN ret",
        "LABEL recurse",
        "SUB n1 n one",
        "PARAM n1",
        "CALL fact",
        "RESULT res",
        "MUL ret res n",
        "RETURN ret",
        "ENDFUNC",
        "MOV x 5",
        "PARAM x",
        "CALL fact",
        "RESULT y",
        "PRINT y"
    ]
    interpreter = Interpreter(script)
    output = interpreter.run()
    print(f"Output: {output}")
