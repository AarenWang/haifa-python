import unittest
from register_vm_v1 import RegisterVMAdvancedSafe  # 你的 VM 实现文件

class TestRegisterVM(unittest.TestCase):

    def run_vm(self, script):
        vm = RegisterVMAdvancedSafe()
        vm.run(script)
        return vm

    def test_arithmetic(self):
        script = [
            "MOV a 4",
            "MOV b 6",
            "ADD sum a b",
            "MUL prod a b"
        ]
        vm = self.run_vm(script)
        self.assertEqual(vm.registers["sum"], 10)
        self.assertEqual(vm.registers["prod"], 24)

    def test_array_loop_sum(self):
        script = [
            "ARR_INIT nums 3",
            "ARR_SET nums 0 1",
            "ARR_SET nums 1 2",
            "ARR_SET nums 2 3",
            "MOV total 0",
            "MOV i 0",
            "LEN len nums",
            "LABEL loop",
            "LT cond i len",
            "JZ cond done",
            "ARR_GET val nums i",
            "ADD total total val",
            "ADD i i 1",
            "JMP loop",
            "LABEL done"
        ]
        vm = self.run_vm(script)
        self.assertEqual(vm.registers["total"], 6)

    def test_function_square(self):
        script = [
            "PARAM 7",
            "CALL square",
            "RESULT res",
            "FUNC square",
            "ARG x",
            "MUL result x x",
            "RETURN result",
            "ENDFUNC"
        ]
        vm = self.run_vm(script)
        self.assertEqual(vm.registers["result"], 49)
        
 

if __name__ == '__main__':
    unittest.main()
