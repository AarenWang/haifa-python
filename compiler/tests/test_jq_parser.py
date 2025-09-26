import unittest

from ..jq_ast import (
    Field,
    Identity,
    IfElse,
    IndexAll,
    Literal,
    ObjectLiteral,
    Pipe,
    Sequence,
    TryCatch,
    flatten_pipe,
)
from ..jq_parser import JQSyntaxError, parse_jq_program
from ..jq_ast import Index, Slice


class TestJQParser(unittest.TestCase):
    def assertField(self, node, name, source_type=Identity):  # noqa: N802
        self.assertIsInstance(node, Field)
        self.assertEqual(node.name, name)
        self.assertIsInstance(node.source, source_type)

    def test_identity(self):
        node = parse_jq_program(".")
        self.assertIsInstance(node, Identity)

    def test_field_chain(self):
        node = parse_jq_program(".foo.bar")
        self.assertIsInstance(node, Field)
        self.assertEqual(node.name, "bar")
        self.assertField(node.source, "foo")

    def test_index_all(self):
        node = parse_jq_program(".items[]")
        self.assertIsInstance(node, IndexAll)
        self.assertField(node.source, "items")

    def test_pipe_sequence(self):
        node = parse_jq_program(".items[] | .name")
        self.assertIsInstance(node, Pipe)
        stages = flatten_pipe(node)
        self.assertEqual(len(stages), 2)
        self.assertIsInstance(stages[0], IndexAll)
        self.assertIsInstance(stages[1], Field)
        self.assertField(stages[1], "name")

    def test_literal_string(self):
        node = parse_jq_program('"hello"')
        self.assertIsInstance(node, Literal)
        self.assertEqual(node.value, "hello")

    def test_function_call(self):
        node = parse_jq_program("length()")
        self.assertEqual(node.name, "length")
        self.assertEqual(node.args, [])

    def test_invalid_expression(self):
        with self.assertRaises(JQSyntaxError):
            parse_jq_program(".foo | | .bar")

    def test_object_literal(self):
        node = parse_jq_program("{name: .foo, label: .bar}")
        self.assertIsInstance(node, ObjectLiteral)
        self.assertEqual(len(node.pairs), 2)
        self.assertEqual(node.pairs[0][0], "name")
        self.assertIsInstance(node.pairs[0][1], Field)

    def test_arithmetic_and_precedence(self):
        node = parse_jq_program(".a + .b * 2")
        # Smoke test: should parse without error
        self.assertIsNotNone(node)

    def test_comparison_and_logic(self):
        node = parse_jq_program("(.x + 1) >= 3 and .y < 5")
        self.assertIsNotNone(node)

    def test_coalesce(self):
        node = parse_jq_program(".a // .b")
        self.assertIsNotNone(node)

    def test_index_literal(self):
        node = parse_jq_program(".items[0]")
        self.assertIsInstance(node, Index)
        self.assertIsInstance(node.source, Field)
        self.assertEqual(node.source.name, "items")

    def test_slice_basic(self):
        node = parse_jq_program(".items[1:3]")
        self.assertIsInstance(node, Slice)
        self.assertIsInstance(node.source, Field)
        self.assertEqual(node.source.name, "items")

    def test_slice_open_ended(self):
        self.assertIsInstance(parse_jq_program(".items[:2]"), Slice)
        self.assertIsInstance(parse_jq_program(".items[1:]"), Slice)

    def test_comma_sequence(self):
        node = parse_jq_program(".a, .b | .c")
        self.assertIsInstance(node, Sequence)
        self.assertEqual(len(node.expressions), 2)
        self.assertIsInstance(node.expressions[0], Field)
        self.assertIsInstance(node.expressions[1], Pipe)

    def test_if_else_structure(self):
        node = parse_jq_program("if .flag then .value else .alt end")
        self.assertIsInstance(node, IfElse)
        self.assertIsInstance(node.then_branch, Field)
        self.assertIsInstance(node.else_branch, Field)

    def test_try_catch_structure(self):
        node = parse_jq_program("try (.a / .b) catch 'fail'")
        self.assertIsInstance(node, TryCatch)
        self.assertIsNotNone(node.catch_expr)

    def test_def_inlines_body(self):
        node = parse_jq_program("def greet: .name; greet")
        self.assertIsInstance(node, Field)
        self.assertEqual(node.name, "name")


if __name__ == "__main__":
    unittest.main()
