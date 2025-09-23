from .parser import parse
from .compiler import ASTCompiler
from .bytecode_vm import BytecodeVM
from .bytecode import Opcode, Instruction

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


    def test_extended_core_opcodes(self):
        instructions = [
            Instruction(Opcode.LOAD_IMM, ['a', 5]),
            Instruction(Opcode.CLR, ['zero']),
            Instruction(Opcode.CMP_IMM, ['cmp_eq', 'a', '5']),
            Instruction(Opcode.CMP_IMM, ['cmp_gt', 'a', '3']),
            Instruction(Opcode.CMP_IMM, ['cmp_lt', 'a', '10']),
            Instruction(Opcode.JNZ, ['cmp_gt', 'gt_true']),
            Instruction(Opcode.LOAD_IMM, ['flag', 0]),
            Instruction(Opcode.JMP_REL, ['2']),
            Instruction(Opcode.LABEL, ['gt_true']),
            Instruction(Opcode.LOAD_IMM, ['flag', 1]),
            Instruction(Opcode.PUSH, ['a']),
            Instruction(Opcode.LOAD_IMM, ['a', 99]),
            Instruction(Opcode.POP, ['restored']),
            Instruction(Opcode.ARR_INIT, ['src', '4']),
            Instruction(Opcode.ARR_SET, ['src', '0', '1']),
            Instruction(Opcode.ARR_SET, ['src', '1', '2']),
            Instruction(Opcode.ARR_SET, ['src', '2', '3']),
            Instruction(Opcode.ARR_SET, ['src', '3', '4']),
            Instruction(Opcode.ARR_COPY, ['dst', 'src', '1', '2']),
            Instruction(Opcode.ARR_GET, ['dst_item0', 'dst', '0']),
            Instruction(Opcode.ARR_GET, ['dst_item1', 'dst', '1']),
            Instruction(Opcode.LEN, ['dst_len', 'dst']),
            Instruction(Opcode.LOAD_CONST, ['obj', {'k': 42}]),
            Instruction(Opcode.LOAD_CONST, ['arr_val', [1, 2]]),
            Instruction(Opcode.LOAD_CONST, ['nil', None]),
            Instruction(Opcode.IS_OBJ, ['is_obj', 'obj']),
            Instruction(Opcode.IS_ARR, ['is_arr', 'arr_val']),
            Instruction(Opcode.IS_NULL, ['is_null', 'nil']),
            Instruction(Opcode.COALESCE, ['coal1', 'nil', 'arr_val']),
            Instruction(Opcode.COALESCE, ['coal2', 'obj', 'arr_val']),
            Instruction(Opcode.LOAD_IMM, ['jump_test', 0]),
            Instruction(Opcode.JMP_REL, ['2']),
            Instruction(Opcode.LOAD_IMM, ['jump_test', 1]),
            Instruction(Opcode.LOAD_IMM, ['jump_test', 2]),
            Instruction(Opcode.PRINT, ['zero']),
            Instruction(Opcode.PRINT, ['cmp_eq']),
            Instruction(Opcode.PRINT, ['cmp_gt']),
            Instruction(Opcode.PRINT, ['cmp_lt']),
            Instruction(Opcode.PRINT, ['flag']),
            Instruction(Opcode.PRINT, ['restored']),
            Instruction(Opcode.PRINT, ['dst_len']),
            Instruction(Opcode.PRINT, ['dst_item0']),
            Instruction(Opcode.PRINT, ['dst_item1']),
            Instruction(Opcode.PRINT, ['is_obj']),
            Instruction(Opcode.PRINT, ['is_arr']),
            Instruction(Opcode.PRINT, ['is_null']),
            Instruction(Opcode.PRINT, ['coal1']),
            Instruction(Opcode.PRINT, ['coal2']),
            Instruction(Opcode.PRINT, ['jump_test']),
            Instruction(Opcode.HALT, []),
        ]

        vm = BytecodeVM(instructions)
        output = vm.run()
        assert output == [
            0,
            0,
            1,
            -1,
            1,
            5,
            2,
            2,
            3,
            1,
            1,
            1,
            [1, 2],
            {'k': 42},
            2,
        ]

    def test_closure_opcodes(self):
        instructions = [
            Instruction(Opcode.LOAD_IMM, ['val', 1]),
            Instruction(Opcode.MAKE_CELL, ['cell', 'val']),
            Instruction(Opcode.CLOSURE, ['clos', 'adder', 'cell']),
            Instruction(Opcode.CALL_VALUE, ['clos']),
            Instruction(Opcode.RESULT, ['result']),
            Instruction(Opcode.PRINT, ['result']),
            Instruction(Opcode.HALT, []),
            Instruction(Opcode.LABEL, ['adder']),
            Instruction(Opcode.BIND_UPVALUE, ['up', '0']),
            Instruction(Opcode.CELL_GET, ['tmp', 'up']),
            Instruction(Opcode.ADD, ['tmp2', 'tmp', '1']),
            Instruction(Opcode.CELL_SET, ['up', 'tmp2']),
            Instruction(Opcode.RETURN, ['tmp2']),
            Instruction(Opcode.RETURN, ['0']),
        ]
        vm = BytecodeVM(instructions)
        output = vm.run()
        assert output == [2]
