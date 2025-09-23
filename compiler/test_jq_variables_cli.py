import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from .jq_runtime import run_filter
from .jq_cli import main


class TestJQVariablesAndCLI(unittest.TestCase):
    def test_as_binding(self):
        data = {"a": 1, "b": 2}
        self.assertEqual(run_filter(".a as $x | $x", data), [1])

    def test_var_from_cli_argjson(self):
        stdout_buffer = io.StringIO()
        with redirect_stdout(stdout_buffer):
            exit_code = main(["$foo | .x", "-n", "--argjson", "foo", '{"x": 42}'])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_buffer.getvalue().strip(), "42")

    def test_raw_output(self):
        stdin_data = ' ["a", "b"]\n'
        stdout_buffer = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin_data)):
            with redirect_stdout(stdout_buffer):
                exit_code = main([".[]", "-r", "--slurp"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_buffer.getvalue().strip().splitlines(), ["a", "b"])

    def test_compact_output(self):
        data = {"x": 1, "y": 2}
        stdout_buffer = io.StringIO()
        with redirect_stdout(stdout_buffer):
            exit_code = main([".", "--input", "-", "-c"])
        # We passed no stdin; so prepare proper stdin usage
        stdout_buffer = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(data))):
            with redirect_stdout(stdout_buffer):
                exit_code = main([".", "-c"])
        self.assertEqual(exit_code, 0)
        out = stdout_buffer.getvalue().strip()
        self.assertIn(":", out)
        self.assertNotIn(": ", out)

    def test_filter_file(self):
        payload = {"items": [{"name": "a"}, {"name": "b"}]}
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
            tf.write(".items[] | .name")
            tf_path = tf.name
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as jf:
                json.dump(payload, jf)
                jf_path = jf.name
            stdout_buffer = io.StringIO()
            with redirect_stdout(stdout_buffer):
                exit_code = main(["--filter-file", tf_path, "--input", jf_path])
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout_buffer.getvalue().strip().splitlines(), ["\"a\"", "\"b\""])
        finally:
            os.remove(tf_path)
            os.remove(jf_path)

    def test_raw_input_lines(self):
        stdin_data = "foo\nbar\n"
        stdout_buffer = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin_data)):
            with redirect_stdout(stdout_buffer):
                exit_code = main([".", "-R", "-r"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_buffer.getvalue().strip().splitlines(), ["foo", "bar"])


if __name__ == "__main__":
    unittest.main()
