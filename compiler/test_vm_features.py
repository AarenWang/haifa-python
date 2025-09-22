from parser import parse
from compiler import ASTCompiler
from bytecode_vm import BytecodeVM

import unittest

class TestVMFeatures(unittest.TestCase):

    def run_script(self,script_lines):
        ast = parse(script_lines)
        bytecode = ASTCompiler().compile(ast)
        vm = BytecodeVM(bytecode)
        return vm.run(debug = True)


    def test_arithmetic(self):
        script = [
            "MOV a 10",
            "MOV b 3",
            "ADD c a b",
            "SUB d a b",
            "MUL e a b",
            "DIV f a b",
            "MOD g a b",
            "NEG h b",
            "PRINT c",  # 13
            "PRINT d",  # 7
            "PRINT e",  # 30
            "PRINT f",  # 3
            "PRINT g",  # 1
            "PRINT h"   # -3
        ]
        output = self.run_script(script)
        assert output == [13, 7, 30, 3, 1, -3]


    def test_logic_and_comparison(self):
        script = [
            "MOV x 7",
            "MOV y 5",
            "EQ r1 x y",
            "GT r2 x y",
            "LT r3 x y",
            "AND r4 x y",
            "OR  r5 x y",
            "NOT r6 x",
            "PRINT r1",  # 0
            "PRINT r2",  # 1
            "PRINT r3",  # 0
            "PRINT r4",  # 1
            "PRINT r5",  # 1
            "PRINT r6"   # 0
        ]
        assert self.run_script(script) == [0, 1, 0, 1, 1, 0]


    def test_bitwise_operations(self):
        script = [
            "MOV a 6",    # 0110
            "MOV b 3",    # 0011
            "AND_BIT r1 a b",
            "OR_BIT  r2 a b",
            "XOR     r3 a b",
            "NOT_BIT r4 a",
            "SHL     r5 a b",
            "SHR     r6 a b",
            "SAR     r7 a b",
            "PRINT r1",  # 2
            "PRINT r2",  # 7
            "PRINT r3",  # 5
            "PRINT r4",  # -7
            "PRINT r5",  # 48
            "PRINT r6",  # 0
            "PRINT r7"   # 0
        ]
        assert self.run_script(script) == [2, 7, 5, -7, 48, 0, 0]


    def test_if_else(self):
        script = [
            "MOV x 5",
            "MOV y 10",
            "GT cond y x",
            "IF cond",
            "MOV z 100",
            "ELSE",
            "MOV z 200",
            "ENDIF",
            "PRINT z"
        ]
        assert self.run_script(script) == [100]


    def test_while_and_break(self):
        script = [
            "ARR_INIT arr 5",
            "MOV i 0",
            "MOV sum 0",
            "WHILE i",
            "BREAK",
            "ENDWHILE",
            "ARR_SET arr 0 1",
            "ARR_SET arr 1 2",
            "ARR_SET arr 2 3",
            "ARR_SET arr 3 4",
            "ARR_SET arr 4 5",
            "MOV i 0",
            "MOV len 5",
            "LABEL loop",
            "LT cond i len",
            "JZ cond end",
            "ARR_GET val arr i",
            "ADD sum sum val",
            "ADD i i 1",
            "JMP loop",
            "LABEL end",
            "PRINT sum"
        ]
        assert self.run_script(script) == [15]


    def test_function_recursive_fib(self):
        script = [
            "FUNC fib",
            "ARG n",
            "MOV one 1",
            "MOV threshold 3",
            "LT cond n threshold",
            "JZ cond recurse",
            "MOV ret 1",
            "RETURN ret",
            "LABEL recurse",
            "SUB n1 n one",
            "SUB n2 n 2",
            "PARAM n1",
            "CALL fib",
            "RESULT r1",
            "PARAM n2",
            "CALL fib",
            "RESULT r2",
            "ADD ret r1 r2",
            "RETURN ret",
            "ENDFUNC",
            "MOV x 7",
            "PARAM x",
            "CALL fib",
            "RESULT res",
            "PRINT res"
        ]
        output = self.run_script(script)
        assert output == [13]
