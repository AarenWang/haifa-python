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
        self.assertEqual(instructions[-2].opcode, Opcode.EMIT)
        self.assertEqual(instructions[-1].opcode, Opcode.HALT)

    def test_field_lookup_generates_obj_get(self):
        instructions = self.compile(".foo.bar")
        opcodes = [inst.opcode for inst in instructions]
        self.assertIn(Opcode.OBJ_GET, opcodes)
        obj_gets = [inst for inst in instructions if inst.opcode == Opcode.OBJ_GET]
        self.assertEqual(len(obj_gets), 2)
        self.assertEqual(obj_gets[0].args[2], "foo")
        self.assertEqual(obj_gets[1].args[2], "bar")

    def test_index_all_generates_loop(self):
        instructions = self.compile(".items[]")
        opcodes = [inst.opcode for inst in instructions]
        self.assertIn(Opcode.GET_INDEX, opcodes)
        self.assertIn(Opcode.LEN_VALUE, opcodes)
        labels = [inst.args[0] for inst in instructions if inst.opcode == Opcode.LABEL]
        self.assertTrue(any(label.startswith("__jq_loop_") for label in labels))

    def test_length_function(self):
        instructions = self.compile(".items | length()")
        self.assertIn(Opcode.LEN_VALUE, [inst.opcode for inst in instructions])

    def test_map_generates_emit_capture(self):
        instructions = self.compile(".items | map(.x)")
        opcodes = [inst.opcode for inst in instructions]
        self.assertIn(Opcode.PUSH_EMIT, opcodes)
        self.assertIn(Opcode.POP_EMIT, opcodes)
        self.assertIn(Opcode.GET_INDEX, opcodes)

    def test_select_generates_skip_labels(self):
        instructions = self.compile(".items[] | select(.flag)")
        labels = [inst.args[0] for inst in instructions if inst.opcode == Opcode.LABEL]
        self.assertTrue(any(label.startswith("__jq_select_skip") for label in labels))
        self.assertTrue(any(label.startswith("__jq_select_cont") for label in labels))


if __name__ == "__main__":
    unittest.main()
