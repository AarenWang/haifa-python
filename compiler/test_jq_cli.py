import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from .jq_cli import main


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

    def test_cli_reports_runtime_error_without_debug(self):
        payload = {"items": [1, 2]}
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name
        stderr_buffer = io.StringIO()
        try:
            with redirect_stderr(stderr_buffer):
                exit_code = main(["reduce(.items, 'noop')", "--input", tmp_path])
        finally:
            os.remove(tmp_path)
        self.assertNotEqual(exit_code, 0)
        self.assertIn("jq execution failed", stderr_buffer.getvalue())

    def test_cli_reports_runtime_error_with_debug(self):
        payload = {"items": [1, 2]}
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name
        stderr_buffer = io.StringIO()
        try:
            with redirect_stderr(stderr_buffer):
                exit_code = main([
                    "reduce(.items, 'noop')",
                    "--input",
                    tmp_path,
                    "--debug",
                ])
        finally:
            os.remove(tmp_path)
        self.assertNotEqual(exit_code, 0)
        err = stderr_buffer.getvalue()
        self.assertIn("Traceback", err)
        self.assertIn("JQRuntimeError", err)

    def test_cli_visualize_curses_mode(self):
        with mock.patch("compiler.vm_visualizer_headless.VMVisualizer") as mock_vis:
            mock_vis.return_value.run.return_value = None
            exit_code = main([".", "--visualize", "curses", "-n"])
        self.assertEqual(exit_code, 0)
        mock_vis.assert_called_once()


if __name__ == "__main__":
    unittest.main()
