import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from jq_cli import main


class TestJQCLI(unittest.TestCase):
    def test_cli_reads_from_stdin(self):
        stdin_data = '{"items": [1, 2, 3]}\n'
        stdout_buffer = io.StringIO()
        with mock.patch.object(json, "loads", wraps=json.loads) as loads_mock:
            with mock.patch("sys.stdin", io.StringIO(stdin_data)):
                with redirect_stdout(stdout_buffer):
                    exit_code = main([".items[]"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_buffer.getvalue().strip().splitlines(), ["1", "2", "3"])
        self.assertGreaterEqual(loads_mock.call_count, 1)

    def test_cli_reads_from_file(self):
        payload = {"items": [{"v": 1}, {"v": 2}]}
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name
        stdout_buffer = io.StringIO()
        try:
            with redirect_stdout(stdout_buffer):
                exit_code = main([".items | map(.v)", "--input", tmp_path])
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout_buffer.getvalue().strip(), "[1, 2]")
        finally:
            os.remove(tmp_path)

    def test_cli_reports_json_error(self):
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("not-json")):
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exit_code = main(["."])
        self.assertNotEqual(exit_code, 0)
        self.assertIn("Failed to parse JSON", stderr_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
