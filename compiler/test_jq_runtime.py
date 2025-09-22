import unittest

from jq_runtime import run_filter


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


if __name__ == "__main__":
    unittest.main()
