import unittest
from stack_vm import StackVM  # 你的 VM 实现文件


class TestStackVM(unittest.TestCase):
    def run_vm(self, script):
        vm = StackVM()
        outputs = vm.run(script)
        return vm, outputs
    
    

    def test_basic_addition(self):
# Define multiple test scripts
        test_cases = {
            "basic_addition": [
                "PUSH 2",
                "PUSH 3",
                "ADD"
            ],
            "stack_manipulation": [
                "PUSH 1",
                "PUSH 2",
                "SWAP",
                "OVER",
                "DUP",
                "DUMP"
            ],
            "logic_branch_true": [
                "PUSH 5",
                "PUSH 5",
                "EQ",
                "IF",
                "PUSH 100",
                "PRINT",
                "ELSE",
                "PUSH 200",
                "PRINT",
                "ENDIF"
            ],
            "logic_branch_false": [
                "PUSH 5",
                "PUSH 10",
                "EQ",
                "IF",
                "PUSH 100",
                "PRINT",
                "ELSE",
                "PUSH 200",
                "PRINT",
                "ENDIF"
            ],
            "math_mod_neg": [
                "PUSH 10",
                "PUSH 3",
                "MOD",
                "PUSH -5",
                "NEG",
                "ADD",
                "PRINT"
            ],
            "boolean_logic": [
                "PUSH 1",
                "PUSH 0",
                "AND",
                "PRINT",
                "PUSH 1",
                "PUSH 0",
                "OR",
                "PRINT",
                "PUSH 0",
                "NOT",
                "PRINT"
            ]
        }
        
        for name, script in test_cases.items():
            vm, outputs = self.run_vm(script)
            print(f"{name}: {vm.stack}: outputs: {outputs}")
        

# Execute all test cases

if __name__ == '__main__':
    unittest.main()    