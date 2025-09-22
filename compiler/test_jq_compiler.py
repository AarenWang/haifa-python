import unittest

from jq_compiler import CURRENT_REGISTER, INPUT_REGISTER, JQCompiler
from jq_parser import parse
from bytecode import Opcode


class TestJQCompiler(unittest.TestCase):
    def compile(self, expression):
        compiler = JQCompiler()
        return compiler.compile(parse(expression))

    def test_literal_expression_generates_load_const(self):
        instructions = self.compile('"hello"')
        self.assertEqual(instructions[0].opcode, Opcode.MOV)
        self.assertEqual(instructions[0].args, [CURRENT_REGISTER, INPUT_REGISTER])
        self.assertEqual(instructions[1].opcode, Opcode.LOAD_CONST)
        self.assertEqual(instructions[1].args[1], "hello")
        self.assertEqual(instructions[-2].opcode, Opcode.PRINT)
        self.assertEqual(instructions[-1].opcode, Opcode.HALT)

    def test_field_lookup_generates_obj_get(self):
        instructions = self.compile(".foo.bar")
        opcodes = [inst.opcode for inst in instructions]
        self.assertIn(Opcode.OBJ_GET, opcodes)
        obj_gets = [inst for inst in instructions if inst.opcode == Opcode.OBJ_GET]
        self.assertEqual(len(obj_gets), 2)
        self.assertEqual(obj_gets[0].args[2], "foo")
        self.assertEqual(obj_gets[1].args[2], "bar")


if __name__ == "__main__":
    unittest.main()
