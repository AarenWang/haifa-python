import unittest

from ..jq_runtime import (
    JQRuntimeError,
    run_filter,
    run_filter_many,
    run_filter_stream,
)


class TestJQRuntime(unittest.TestCase):
    def test_identity_returns_input(self):
        data = {"foo": 1, "bar": 2}
        self.assertEqual(run_filter(".", data), [data])

    def test_field_access(self):
        data = {"foo": {"bar": 42}}
        self.assertEqual(run_filter(".foo.bar", data), [42])

    def test_pipeline(self):
        data = {"foo": {"bar": "baz"}}
        self.assertEqual(run_filter(".foo | .bar", data), ["baz"])

    def test_missing_field_yields_null(self):
        data = {"foo": {}}
        self.assertEqual(run_filter(".foo.missing", data), [None])

    def test_index_all_iteration(self):
        data = {"items": [1, 2, 3]}
        self.assertEqual(run_filter(".items[]", data), [1, 2, 3])

    def test_index_all_with_field(self):
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        self.assertEqual(run_filter(".items[] | .name", data), ["a", "b"])

    def test_length_builtin(self):
        data = {"items": [1, 2, 3]}
        self.assertEqual(run_filter(".items | length()", data), [3])

    def test_map_function(self):
        data = {"items": [{"v": 1}, {"v": 2}, {"v": 3}]}
        self.assertEqual(run_filter(".items | map(.v)", data), [[1, 2, 3]])

    def test_select_function(self):
        data = [
            {"name": "a", "ok": True},
            {"name": "b", "ok": False},
            {"name": "c", "ok": True},
        ]
        self.assertEqual(run_filter(".[] | select(.ok) | .name", data), ["a", "c"])

    def test_flatten_function(self):
        data = {"items": [[1, 2], [3], [], [4, 5]]}
        self.assertEqual(run_filter(".items | flatten()", data), [[1, 2, 3, 4, 5]])

    def test_reduce_sum(self):
        data = {"items": [1, 2, 3]}
        self.assertEqual(run_filter(".items | reduce('sum')", data), [6])

    def test_reduce_with_array_arg(self):
        data = {"nums": [2, 3, 4]}
        self.assertEqual(run_filter("reduce(.nums, 'product')", data), [24])

    def test_select_with_multi_value_condition(self):
        data = [
            {"name": "a", "flags": [0, 1]},
            {"name": "b", "flags": [0, 0]},
            {"name": "c", "flags": [2]},
        ]
        self.assertEqual(
            run_filter(".[] | select(.flags | map(.)) | .name", data),
            ["a", "c"],
        )

    def test_object_literal(self):
        data = {"items": [{"name": "Alice", "scores": [1, 2]}, {"name": "Bob", "scores": [3]}]}
        self.assertEqual(
            run_filter(".items[] | {name: .name, count: (.scores | length())}", data),
            [{"name": "Alice", "count": 2}, {"name": "Bob", "count": 1}],
        )

    def test_run_filter_stream_handles_generators(self):
        inputs = (i for i in range(3))
        self.assertEqual(list(run_filter_stream(".", inputs)), [0, 1, 2])

    def test_run_filter_many_uses_cached_compile(self):
        # Should reuse cached bytecode; using two inputs to ensure no state leakage
        result = run_filter_many(". + 1", [1, 2])
        self.assertEqual(result, [2, 3])

    def test_run_filter_stream_wraps_execution_errors(self):
        def bad_inputs():
            yield {"items": [1, 2, 3]}
            yield {"items": ["boom"]}

        stream = run_filter_stream(".items | reduce('sum')", bad_inputs())
        self.assertEqual(next(stream), 6)
        with self.assertRaises(JQRuntimeError) as ctx:
            next(stream)
        self.assertIn("input #1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
