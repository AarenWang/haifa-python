class RegisterVMAdvancedSafe():
    def __init__(self):
        self.registers = {}
        self.arrays = {}
        self.functions = {}
        self.call_stack = []
        self.param_stack = []
        self.labels = {}
        self.output = []
        self.return_register = None
        self.return_value = None
        self.script = []
        self.pc = 0
        self.local_param_stack = []

    def val(self, x):
        """Evaluate a value - either a number or register content"""
        try:
            return int(x)
        except ValueError:
            return self.registers.get(x, 0)

    def run(self, script):
        self.registers.clear()
        self.arrays.clear()
        self.functions.clear()
        self.call_stack.clear()
        self.param_stack.clear()
        self.labels.clear()
        self.output.clear()
        self.return_register = None
        self.return_value = None
        self.script = script
        self.pc = 0
        self.local_param_stack = []

        # First pass: collect labels and functions
        for i, line in enumerate(script):
            if line.startswith("FUNC "):
                name = line.split()[1]
                self.functions[name] = i
                print(f"Found function {name} at line {i}")
            elif line.startswith("LABEL "):
                name = line.split()[1]
                self.labels[name] = i

        while self.pc < len(self.script):
            instr = self.script[self.pc].strip()
            parts = instr.split()
            if not parts:
                self.pc += 1
                continue

            op = parts[0].upper()
            args = parts[1:]

            try:
                if op == "MOV":
                    dest, src = args
                    self.registers[dest] = self.val(src)
                elif op in {"ADD", "SUB", "MUL", "DIV", "MOD", "EQ", "GT", "LT", "AND", "OR"}:
                    dest, src1, src2 = args
                    a, b = self.val(src1), self.val(src2)
                    if op == "DIV" and b == 0:
                        self.registers[dest] = 0
                    elif op == "MOD" and b == 0:
                        self.registers[dest] = 0
                    else:
                        self.registers[dest] = {
                            "ADD": a + b,
                            "SUB": a - b,
                            "MUL": a * b,
                            "DIV": int(a / b),
                            "MOD": a % b,
                            "EQ": int(a == b),
                            "GT": int(a > b),
                            "LT": int(a < b),
                            "AND": int(bool(a) and bool(b)),
                            "OR": int(bool(a) or bool(b)),
                        }[op]
                elif op == "NOT":
                    dest, src = args
                    self.registers[dest] = int(not bool(self.val(src)))
                elif op == "NEG":
                    dest, src = args
                    self.registers[dest] = -self.val(src)

                # Arrays
                elif op == "ARR_INIT":
                    name, size = args
                    self.arrays[name] = [0] * int(size)
                elif op == "ARR_SET":
                    name, index, value = args
                    self.arrays[name][self.val(index)] = self.val(value)
                elif op == "ARR_GET":
                    dest, name, index = args
                    self.registers[dest] = self.arrays[name][self.val(index)]
                elif op == "LEN":
                    dest, name = args
                    self.registers[dest] = len(self.arrays[name])

                # Control
                elif op == "JMP":
                    self.pc = self.labels[args[0]]
                    continue
                elif op == "JZ":
                    cond, label = args
                    if self.val(cond) == 0:
                        self.pc = self.labels[label]
                        continue
                elif op == "LABEL":
                    pass

                # Function
                elif op == "CALL":
                    fname = args[0]
                    print(f"Calling function {fname} at line {self.pc}")
                    print(f"Current param stack: {self.param_stack}")
                    # Save current state
                    self.call_stack.append((self.pc + 1, self.return_register))
                    self.local_param_stack = self.param_stack.copy()
                    self.param_stack.clear()
                    self.return_value = None
                    # Jump to function
                    self.pc = self.functions[fname]
                    continue
                elif op == "FUNC":
                    print(f"Entering function at line {self.pc}")
                    # Skip function definition unless we're calling it
                    if not self.call_stack:
                        # Skip to ENDFUNC
                        while self.pc < len(self.script) and not self.script[self.pc].startswith("ENDFUNC"):
                            self.pc += 1
                        # Skip the ENDFUNC line too
                        self.pc += 1
                        continue
                elif op == "ENDFUNC":
                    if self.call_stack:
                        print(f"Returning from function, storing {self.return_value} in {self.return_register}")
                        # Restore state and store return value
                        self.pc, self.return_register = self.call_stack.pop()
                        if self.return_register is not None and self.return_value is not None:
                            self.registers[self.return_register] = self.return_value
                        self.return_register = None
                        self.return_value = None
                        continue
                elif op == "RET":
                    if self.call_stack:
                        self.pc, self.return_register = self.call_stack.pop()
                        if self.return_register is not None and self.return_value is not None:
                            self.registers[self.return_register] = self.return_value
                        self.return_register = None
                        self.return_value = None
                        continue
                elif op == "RETURN":
                    self.return_value = self.val(args[0])
                    print(f"Setting return value to {self.return_value}")
                elif op == "PARAM":
                    self.param_stack.append(self.val(args[0]))
                    print(f"Pushing param {self.val(args[0])} onto stack")
                elif op == "ARG":
                    dest = args[0]
                    value = self.local_param_stack.pop(0) if self.local_param_stack else 0
                    print(f"Setting {dest} to {value}")
                    self.registers[dest] = value
                elif op == "RESULT":
                    self.return_register = args[0]
                    print(f"Will store return value in {self.return_register}")
                    # If we already have a return value, store it immediately
                    if self.return_value is not None:
                        self.registers[self.return_register] = self.return_value

                # Output
                elif op == "PRINT":
                    reg = args[0]
                    self.output.append(self.registers.get(reg, 0))
                elif op == "DUMP":
                    self.output.append({"registers": dict(self.registers), "arrays": dict(self.arrays)})

            except Exception as e:
                self.output.append(f"Error at line {self.pc}: {e}")

            self.pc += 1
        return self.output




