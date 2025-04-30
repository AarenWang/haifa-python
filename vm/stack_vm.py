class StackVM:
    def __init__(self):
        self.stack = []
        self.pc = 0
        self.script = []

    def run(self, script):
        self.stack.clear()
        self.script = script
        self.pc = 0
        outputs = []

        while self.pc < len(self.script):
            instr = self.script[self.pc]

            if isinstance(instr, str):
                parts = instr.strip().split()
                op = parts[0].upper()
                args = parts[1:]

                # Arithmetic / Logic
                if op == "PUSH":
                    self.stack.append(int(args[0]))
                elif op == "ADD":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(a + b)
                elif op == "SUB":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(a - b)
                elif op == "MUL":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(a * b)
                elif op == "DIV":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(int(a / b))
                elif op == "MOD":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(a % b)
                elif op == "NEG":
                    a = self.stack.pop()
                    self.stack.append(-a)
                elif op == "EQ":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(int(a == b))
                elif op == "GT":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(int(a > b))
                elif op == "LT":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(int(a < b))
                elif op == "AND":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(int(bool(a) and bool(b)))
                elif op == "OR":
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.append(int(bool(a) or bool(b)))
                elif op == "NOT":
                    a = self.stack.pop()
                    self.stack.append(int(not bool(a)))

                # Stack ops
                elif op == "DUP":
                    self.stack.append(self.stack[-1])
                elif op == "DROP":
                    self.stack.pop()
                elif op == "SWAP":
                    self.stack[-1], self.stack[-2] = self.stack[-2], self.stack[-1]
                elif op == "OVER":
                    self.stack.append(self.stack[-2])
                elif op == "ROT":
                    self.stack[-3], self.stack[-2], self.stack[-1] = \
                        self.stack[-2], self.stack[-1], self.stack[-3]

                # Output
                elif op == "PRINT":
                    outputs.append(self.stack.pop())
                elif op == "DUMP":
                    outputs.append(f"Stack: {self.stack.copy()}")

                # Control flow
                elif op == "IF":
                    condition = self.stack.pop()
                    if not condition:
                        self.pc = self.find_matching(["ELSE", "ENDIF"])
                elif op == "ELSE":
                    self.pc = self.find_matching(["ENDIF"])
                elif op == "ENDIF":
                    pass

                else:
                    raise ValueError(f"Unknown instruction: {op}")
            self.pc += 1
        return outputs

    def find_matching(self, targets):
        level = 0
        for i in range(self.pc + 1, len(self.script)):
            token = self.script[i].strip().split()[0].upper()
            if token == "IF":
                level += 1
            elif token in targets:
                if level == 0:
                    return i
                level -= 1
        raise ValueError("Unmatched control structure")

