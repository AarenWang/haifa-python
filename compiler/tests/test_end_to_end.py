from ..parser import parse
from ..compiler import ASTCompiler
from ..bytecode_vm import BytecodeVM

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

    def test_end_to_end_structured_max_of_array(self):
        script = [
            # 函数 max(a, b): return a if a > b else b
            "FUNC max2",
            "ARG a",
            "ARG b",
            "GT cond a b",
            "IF cond",
            "RETURN a",
            "ELSE",
            "RETURN b",
            "ENDIF",
            "ENDFUNC",

            # 初始化数组
            "ARR_INIT arr 5",
            "ARR_SET arr 0 5",
            "ARR_SET arr 1 12",
            "ARR_SET arr 2 7",
            "ARR_SET arr 3 3",
            "ARR_SET arr 4 9",
            "MOV i 0",
            "MOV len 5",
            "ARR_GET max arr 0",  # 初始最大值

            # while loop
            "LABEL loop",
            "LT cond i len",
            "JZ cond end",
            "ARR_GET val arr i",
            "PARAM max",
            "PARAM val",
            "CALL max2",
            "RESULT max",
            "ADD i i 1",
            "JMP loop",
            "LABEL end",
            # 输出最大值
            "PRINT max"
        ]

        ast = parse(script)
        bytecode = ASTCompiler().compile(ast)
        vm = BytecodeVM(bytecode)
        output = vm.run(debug=True)
        print("test_end_to_end_structured_max_of_array output: ", output)
        assert output == [12]
        print("✅ End-to-end structured test passed.")

if __name__ == '__main__':
    unittest.main()