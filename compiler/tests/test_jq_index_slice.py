import unittest

from ..jq_runtime import run_filter


class TestJQIndexSlice(unittest.TestCase):
    def test_index_number(self):
        data = {"items": [1, 2, 3]}
        self.assertEqual(run_filter(".items[0]", data), [1])
        self.assertEqual(run_filter(".items[-1]", data), [3])

    def test_slice_basic(self):
        data = {"items": [1, 2, 3, 4]}
        # slice returns an array value
        self.assertEqual(run_filter(".items[1:3]", data), [[2, 3]])

    def test_slice_open_ended(self):
        data = {"items": [1, 2, 3, 4]}
        self.assertEqual(run_filter(".items[:2]", data), [[1, 2]])
        self.assertEqual(run_filter(".items[2:]", data), [[3, 4]])

    def test_slice_then_length(self):
        data = {"items": [1, 2, 3, 4]}
        self.assertEqual(run_filter(".items[1:3] | length()", data), [2])


if __name__ == "__main__":
    unittest.main()

