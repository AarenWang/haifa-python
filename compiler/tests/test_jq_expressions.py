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

    def test_update_assignment_pipe(self):
        data = {"value": 3}
        self.assertEqual(run_filter(".value |= . + 1", data), [{"value": 4}])

    def test_update_compound_plus(self):
        data = {"count": 5}
        self.assertEqual(run_filter(".count += 7", data), [{"count": 12}])

    def test_update_nested_index(self):
        data = {"items": [1, 2, 3]}
        result = run_filter(".items[1] += 5", data)
        self.assertEqual(result, [{"items": [1, 7, 3]}])

    def test_reduce_general(self):
        expr = "reduce .nums[] as $n (0; . + $n)"
        data = {"nums": [1, 2, 3]}
        self.assertEqual(run_filter(expr, data), [6])

    def test_foreach_with_extract(self):
        expr = "foreach .nums[] as $n (0; . + $n; .)"
        data = {"nums": [1, 2, 3]}
        self.assertEqual(run_filter(expr, data), [1, 3, 6])

    def test_while_loop(self):
        result = run_filter("while(. < 10; . + 3)", 1)
        self.assertEqual(result, [1, 4, 7])

    def test_until_loop(self):
        result = run_filter("until(. > 5; . + 2)", 1)
        self.assertEqual(result, [1, 3, 5, 7])


if __name__ == "__main__":
    unittest.main()
