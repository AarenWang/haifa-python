import unittest

from .jq_runtime import run_filter


class TestJQCoreFilters(unittest.TestCase):
    def test_keys_object(self):
        data = {"obj": {"b": 2, "a": 1}}
        out = run_filter(".obj | keys()", data)
        self.assertEqual(out, [["a", "b"]])

    def test_keys_array(self):
        data = {"arr": [10, 20, 30]}
        self.assertEqual(run_filter(".arr | keys()", data), [[0, 1, 2]])

    def test_has(self):
        data = {"obj": {"a": None}, "arr": [0, 1]}
        self.assertEqual(run_filter(".obj | has('a')", data), [1])
        self.assertEqual(run_filter(".obj | has('b')", data), [0])
        self.assertEqual(run_filter(".arr | has(1)", data), [1])
        self.assertEqual(run_filter(".arr | has(2)", data), [0])

    def test_contains(self):
        data = {"s": "hello", "arr": [1, 2, 3], "o": {"a": 1, "b": 2}}
        self.assertEqual(run_filter(".s | contains('ell')", data), [1])
        self.assertEqual(run_filter(".arr | contains(2)", data), [1])
        self.assertEqual(run_filter(".o | contains({a: 1})", data), [1])

    def test_add(self):
        self.assertEqual(run_filter(".arr | add()", {"arr": [1, 2, 3]}), [6])
        self.assertEqual(run_filter(".arr | add()", {"arr": ["a", "b"]}), ["ab"])
        self.assertEqual(run_filter(".arr | add()", {"arr": [[1], [2, 3]]}), [[1, 2, 3]])

    def test_join(self):
        self.assertEqual(run_filter(".arr | join(',')", {"arr": ["a", "b", "c"]}), ["a,b,c"])

    def test_reverse(self):
        self.assertEqual(run_filter(".arr | reverse()", {"arr": [1, 2, 3]}), [[3, 2, 1]])
        self.assertEqual(run_filter(".s | reverse()", {"s": "abc"}), ["cba"])

    def test_first_last(self):
        self.assertEqual(run_filter(".arr | first()", {"arr": [1, 2, 3]}), [1])
        self.assertEqual(run_filter(".arr | last()", {"arr": [1, 2, 3]}), [3])
        self.assertEqual(run_filter(".s | first()", {"s": "abc"}), ["a"])
        self.assertEqual(run_filter(".s | last()", {"s": "abc"}), ["c"])

    def test_any_all(self):
        self.assertEqual(run_filter(".flags | any()", {"flags": [0, 1, 0]}), [1])
        self.assertEqual(run_filter(".flags | all()", {"flags": [1, 1]}), [1])
        self.assertEqual(run_filter(".flags | all()", {"flags": [1, 0]}), [0])


if __name__ == "__main__":
    unittest.main()

