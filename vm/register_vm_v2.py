class RegisterVMFinalSafe():
    
    def __init__(self):
        self.registers = {}
        self.arrays = {}
        self.functions = {}
        self.labels = {}
        self.pc = 0
        self.script = []
        self.call_stack = []
        self.param_stack = []
        self.output = []
        self.return_value = None
        self.loop_stack = []

    def preprocess(self):
        """Preprocess the script to set up labels and functions"""
        for i, instr in enumerate(self.script):
            parts = instr.strip().split()
            if not parts:
                continue
            op = parts[0].upper()
            if op == "LABEL":
                self.labels[parts[1]] = i
            elif op == "FUNC":
                self.functions[parts[1]] = i

    def val(self, x):
        """根据参数内容返回值：立即数或寄存器内容"""
        if x.lstrip('-').isdigit():  # 支持负数
            return int(x)
        return self.registers.get(x, 0)


    def run(self, script):
        self.registers.clear()
        self.arrays.clear()
        self.functions.clear()
        self.pc = 0
        self.script = script
        self.call_stack.clear()
        self.output.clear()
        self.param_stack.clear()
        self.return_value = None
        self.labels.clear()
        self.loop_stack.clear()
        self.preprocess()

        while self.pc < len(self.script):
            instr = self.script[self.pc]
            parts = instr.strip().split()
            if not parts:
                self.pc += 1
                continue

            op = parts[0].upper()
            args = parts[1:]

            if op == "MOV":
                self.registers[args[0]] = self.val(args[1])
            elif op == "ADD":
                self.registers[args[0]] = self.val(args[1]) + self.val(args[2])
            elif op == "SUB":
                self.registers[args[0]] = self.val(args[1]) - self.val(args[2])
            elif op == "MUL":
                self.registers[args[0]] = self.val(args[1]) * self.val(args[2])
            elif op == "DIV":
                self.registers[args[0]] = int(self.val(args[1]) / self.val(args[2]))
            elif op == "MOD":
                self.registers[args[0]] = self.val(args[1]) % self.val(args[2])
            elif op == "NEG":
                self.registers[args[0]] = -self.val(args[1])
            elif op == "EQ":
                self.registers[args[0]] = int(self.val(args[1]) == self.val(args[2]))
            elif op == "GT":
                self.registers[args[0]] = int(self.val(args[1]) > self.val(args[2]))
            elif op == "LT":
                self.registers[args[0]] = int(self.val(args[1]) < self.val(args[2]))
            elif op == "AND":
                self.registers[args[0]] = int(bool(self.val(args[1])) and bool(self.val(args[2])))
            elif op == "OR":
                self.registers[args[0]] = int(bool(self.val(args[1])) or bool(self.val(args[2])))
            elif op == "NOT":
                self.registers[args[0]] = int(not bool(self.val(args[1])))

            elif op == "JMP":
                self.pc = self.labels[args[0]]
                continue
            elif op == "JZ":
                if self.val(args[0]) == 0:
                    self.pc = self.labels[args[1]]
                    continue
            elif op == "LABEL":
                pass
            elif op == "ARR_INIT":
                self.arrays[args[0]] = [0] * int(args[1])
            elif op == "ARR_SET":
                self.arrays[args[0]][self.val(args[1])] = self.val(args[2])
            elif op == "ARR_GET":
                self.registers[args[0]] = self.arrays[args[1]][self.val(args[2])]
            elif op == "LEN":
                self.registers[args[0]] = len(self.arrays[args[1]])

            elif op == "FUNC":
                pass
            elif op == "CALL":
                self.call_stack.append((self.pc + 1, list(self.param_stack)))
                self.pc = self.functions[args[0]]
                continue
            elif op == "PARAM":
                self.param_stack.append(self.val(args[0]))
            elif op == "ARG":
                if self.param_stack:
                    self.registers[args[0]] = self.param_stack.pop(0)
            elif op == "RETURN":
                self.return_value = self.val(args[0])
                if self.call_stack:
                    self.pc, self.param_stack = self.call_stack.pop()
                    continue
            elif op == "RESULT":
                self.registers[args[0]] = self.return_value
            elif op == "ENDFUNC":
                if self.call_stack:
                    self.pc, self.param_stack = self.call_stack.pop()
                    continue

            elif op == "IF":
                if not self.val(args[0]):
                    self.pc = self.find_matching(self.pc, "IF", ["ELSE", "ENDIF"])
                    continue
            elif op == "ELSE":
                self.pc = self.find_matching(self.pc, "ELSE", ["ENDIF"])
                continue
            elif op == "ENDIF":
                pass
            elif op == "WHILE":
                if not self.val(args[0]):
                    self.pc = self.find_matching(self.pc, "WHILE", ["ENDWHILE"])
                    continue
                self.loop_stack.append(self.pc)
            elif op == "ENDWHILE":
                self.pc = self.loop_stack.pop() - 1
            elif op == "BREAK":
                end = self.find_matching(self.pc, "WHILE", ["ENDWHILE"])
                self.pc = end
                continue
            elif op == "PRINT":
                self.output.append(self.registers.get(args[0], 0))
            elif op == "DUMP":
                self.output.append({"registers": dict(self.registers), "arrays": dict(self.arrays)})

            self.pc += 1

        return self.output



def run_test_case(vm, script, expected_output=None, expected_registers=None, expected_arrays=None):
    result = vm.run(script)
    
    if expected_output is not None:
        assert result[:len(expected_output)] == expected_output, f"Output mismatch: {result}"

    if expected_registers is not None:
        for key, val in expected_registers.items():
            assert vm.registers.get(key) == val, f"Register {key} expected {val}, got {vm.registers.get(key)}"

    if expected_arrays is not None:
        for name, array in expected_arrays.items():
            assert vm.arrays.get(name) == array, f"Array {name} expected {array}, got {vm.arrays.get(name)}"

    print("Test passed ✅")



if __name__ == "__main__":
    vm = RegisterVMFinalSafe()
    script = [
        "MOV a 10",
        "MOV b 20", 
        "ADD c a b",
        "PRINT c",
        "MUL d a b",
        "PRINT d"
    ]
    output = vm.run(script)
    print(f"Output: {output}")

