import unittest

from .value_utils import resolve_value, try_parse_literal


class TestValueUtils(unittest.TestCase):
    def test_try_parse_numeric_literal(self):
        self.assertEqual(try_parse_literal("42"), 42)
        self.assertAlmostEqual(try_parse_literal("3.14"), 3.14)

    def test_try_parse_boolean_and_null(self):
        self.assertIs(try_parse_literal("true"), True)
        self.assertIs(try_parse_literal("false"), False)
        self.assertIsNone(try_parse_literal("null"))

    def test_try_parse_string_literals(self):
        self.assertEqual(try_parse_literal('"hello"'), "hello")
        self.assertEqual(try_parse_literal("'world'"), "world")

    def test_resolve_value_falls_back_to_lookup(self):
        lookup = {"var": 99}
        result = resolve_value("var", lambda name: lookup.get(name, None))
        self.assertEqual(result, 99)

    def test_resolve_value_handles_literals_before_lookup(self):
        calls = []

        def lookup(name):
            calls.append(name)
            return name

        value = resolve_value("123", lookup)
        self.assertEqual(value, 123)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
