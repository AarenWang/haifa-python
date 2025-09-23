import unittest

from jq_ast import Field, Identity, IndexAll, Literal, ObjectLiteral, Pipe, flatten_pipe
from jq_parser import JQSyntaxError, parse


class TestJQParser(unittest.TestCase):
    def assertField(self, node, name, source_type=Identity):  # noqa: N802
        self.assertIsInstance(node, Field)
        self.assertEqual(node.name, name)
        self.assertIsInstance(node.source, source_type)

    def test_identity(self):
        node = parse(".")
        self.assertIsInstance(node, Identity)

    def test_field_chain(self):
        node = parse(".foo.bar")
        self.assertIsInstance(node, Field)
        self.assertEqual(node.name, "bar")
        self.assertField(node.source, "foo")

    def test_index_all(self):
        node = parse(".items[]")
        self.assertIsInstance(node, IndexAll)
        self.assertField(node.source, "items")

    def test_pipe_sequence(self):
        node = parse(".items[] | .name")
        self.assertIsInstance(node, Pipe)
        stages = flatten_pipe(node)
        self.assertEqual(len(stages), 2)
        self.assertIsInstance(stages[0], IndexAll)
        self.assertIsInstance(stages[1], Field)
        self.assertField(stages[1], "name")

    def test_literal_string(self):
        node = parse('"hello"')
        self.assertIsInstance(node, Literal)
        self.assertEqual(node.value, "hello")

    def test_function_call(self):
        node = parse("length()")
        self.assertEqual(node.name, "length")
        self.assertEqual(node.args, [])

    def test_invalid_expression(self):
        with self.assertRaises(JQSyntaxError):
            parse(".foo | | .bar")

    def test_object_literal(self):
        node = parse("{name: .foo, label: .bar}")
        self.assertIsInstance(node, ObjectLiteral)
        self.assertEqual(len(node.pairs), 2)
        self.assertEqual(node.pairs[0][0], "name")
        self.assertIsInstance(node.pairs[0][1], Field)

    def test_arithmetic_and_precedence(self):
        node = parse(".a + .b * 2")
        # Smoke test: should parse without error
        self.assertIsNotNone(node)

    def test_comparison_and_logic(self):
        node = parse("(.x + 1) >= 3 and .y < 5")
        self.assertIsNotNone(node)

    def test_coalesce(self):
        node = parse(".a // .b")
        self.assertIsNotNone(node)


if __name__ == "__main__":
    unittest.main()
