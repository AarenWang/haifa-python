from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from haifa_scheme.cli import ReplSession, main


def test_cli_executes_inline_source_with_print_output():
    stdout_buffer = io.StringIO()

    with redirect_stdout(stdout_buffer):
        exit_code = main(["-e", '(list 1 #t "ok")', "--print-output"])

    assert exit_code == 0
    assert stdout_buffer.getvalue().strip() == '(1 #t "ok")'


def test_cli_executes_script_file_with_print_output():
    with tempfile.NamedTemporaryFile("w", suffix=".scm", delete=False, encoding="utf-8") as handle:
        handle.write("(define (square x) (* x x))\n(square 6)\n")
        script_path = Path(handle.name)

    stdout_buffer = io.StringIO()
    try:
        with redirect_stdout(stdout_buffer):
            exit_code = main([str(script_path), "--print-output"])
    finally:
        script_path.unlink()

    assert exit_code == 0
    assert stdout_buffer.getvalue().strip().splitlines() == ["#<void>", "36"]


def test_cli_reports_runtime_errors():
    stderr_buffer = io.StringIO()

    with redirect_stderr(stderr_buffer):
        exit_code = main(["-e", "missing", "--print-output"])

    assert exit_code == 1
    assert "Scheme execution failed: unbound symbol: missing" in stderr_buffer.getvalue()


def test_repl_session_preserves_environment_between_lines():
    session = ReplSession()
    stdout_buffer = io.StringIO()

    with redirect_stdout(stdout_buffer):
        assert session.process_line("(define x 4)") is False
        assert session.process_line("(+ x 3)") is False

    assert stdout_buffer.getvalue().strip() == "7"
