import unittest

from .jq_runtime import run_filter


class TestJQSortAgg(unittest.TestCase):
    def test_sort_numbers(self):
        self.assertEqual(run_filter("sort()", [3, 1, 2]), [[1, 2, 3]])

    def test_sort_strings(self):
        self.assertEqual(run_filter("sort()", ["b", "a", "c"]), [["a", "b", "c"]])

    def test_sort_by_field(self):
        data = {"items": [{"v": 3}, {"v": 1}, {"v": 2}]}
        self.assertEqual(run_filter(".items | sort_by(.v)", data), [[{"v": 1}, {"v": 2}, {"v": 3}]])

    def test_min_max(self):
        data = {"xs": [3, 1, 2]}
        self.assertEqual(run_filter(".xs | min()", data), [1])
        self.assertEqual(run_filter(".xs | max()", data), [3])

    def test_min_by_max_by(self):
        data = {"items": [{"v": 3}, {"v": 1}, {"v": 2}]}
        self.assertEqual(run_filter(".items | min_by(.v)", data), [{"v": 1}])
        self.assertEqual(run_filter(".items | max_by(.v)", data), [{"v": 3}])

    def test_unique(self):
        data = {"xs": [1, 2, 2, 3, 1]}
        self.assertEqual(run_filter(".xs | unique()", data), [[1, 2, 3]])

    def test_unique_by(self):
        data = {"items": [{"k": 1}, {"k": 2}, {"k": 1}, {"k": 3}]}
        self.assertEqual(run_filter(".items | unique_by(.k)", data), [[{"k": 1}, {"k": 2}, {"k": 3}]])

    def test_group_by(self):
        data = {"items": [{"k": 2}, {"k": 1}, {"k": 2}, {"k": 1}, {"k": 3}]}
        # sort_by + group_by to mimic jq usage
        self.assertEqual(
            run_filter(".items | sort_by(.k) | group_by(.k)", data),
            [[[{"k": 1}, {"k": 1}], [{"k": 2}, {"k": 2}], [{"k": 3}]]],
        )


if __name__ == "__main__":
    unittest.main()

