import unittest

from ..jq_runtime import run_filter


class TestJQExpressions(unittest.TestCase):
    def test_add_mul_precedence(self):
        data = {"a": 2, "b": 3}
        self.assertEqual(run_filter(".a + .b * 2", data), [8])

    def test_parentheses(self):
        data = {"a": 2, "b": 3}
        self.assertEqual(run_filter("(.a + .b) * 2", data), [10])

    def test_division(self):
        data = {"x": 1}
        # VM DIV 为整除，与现有 VM 语义一致
        self.assertEqual(run_filter(".x / 2", data), [0])

    def test_comparisons(self):
        data = {"a": 3, "b": 5}
        self.assertEqual(run_filter(".a == 3", data), [1])
        self.assertEqual(run_filter(".a != 3", data), [0])
        self.assertEqual(run_filter(".b >= 5", data), [1])
        self.assertEqual(run_filter(".b <= 4", data), [0])

    def test_logic(self):
        data = {"a": 1, "b": 0}
        self.assertEqual(run_filter("(.a == 1) and (.b == 0)", data), [1])
        self.assertEqual(run_filter("(.a == 0) or (.b == 0)", data), [1])
        self.assertEqual(run_filter("not(.a == 1)", data), [0])

    def test_coalesce(self):
        data = {"b": 7}
        self.assertEqual(run_filter(".a // .b", data), [7])
        data2 = {"a": 1, "b": 7}
        self.assertEqual(run_filter(".a // .b", data2), [1])


if __name__ == "__main__":
    unittest.main()
