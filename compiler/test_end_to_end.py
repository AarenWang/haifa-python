from parser import parse
from compiler import ASTCompiler
from bytecode_vm import BytecodeVM

import unittest

class TestVMFeatures(unittest.TestCase):

    def test_end_to_end_basic_expression(self):
        # 类汇编脚本
        script = [
            "MOV a 6",
            "MOV b 4",
            "ADD c a b",  # c = a + b = 10
            "MOV two 2",
            "MUL d c two",  # d = c * 2 = 20
            "PRINT d"
        ]

        # 步骤 1：类汇编转 AST
        ast = parse(script)

        # 步骤 2：AST 编译为字节码
        bytecode = ASTCompiler().compile(ast)

        # 步骤 3：执行字节码
        vm = BytecodeVM(bytecode)
        output = vm.run(debug=True)

        # 验证输出
        assert output == [20]
        print("✅ End-to-end test passed.")