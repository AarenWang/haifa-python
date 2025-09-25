import unittest

from ..jq_runtime import run_filter


class TestJQStringTools(unittest.TestCase):
    def test_tostring(self):
        self.assertEqual(run_filter("tostring()", 123), ["123"])
        self.assertEqual(run_filter("tostring()", True), ["true"])
        self.assertEqual(run_filter("tostring()", None), ["null"])
        self.assertEqual(run_filter("tostring()", {"a": 1}), ['{"a": 1}'])

    def test_tonumber(self):
        self.assertEqual(run_filter("tonumber()", "123"), [123])
        self.assertEqual(run_filter("tonumber()", "3.14"), [3.14])
        self.assertEqual(run_filter("tonumber()", True), [1])
        self.assertEqual(run_filter("tonumber()", ""), [None])

    def test_split(self):
        data = {"s": "a,b,c"}
        self.assertEqual(run_filter(".s | split(',')", data), [["a", "b", "c"]])
        self.assertEqual(run_filter(".s | split(';')", data), [["a,b,c"]])

    def test_gsub(self):
        data = {"s": "ababa"}
        # Our parser uses comma-separated args rather than jq's semicolon
        self.assertEqual(run_filter(".s | gsub('ab', 'X')", data), ["XXa"])


if __name__ == "__main__":
    unittest.main()
