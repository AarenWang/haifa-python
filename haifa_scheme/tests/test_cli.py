from __future__ import annotations

import io
import sys
import tempfile
import types
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


def test_cli_vm_backend_executes_inline_source_with_print_output():
    stdout_buffer = io.StringIO()

    with redirect_stdout(stdout_buffer):
        exit_code = main(["-e", "(+ 1 2)", "--backend", "vm", "--print-output"])

    assert exit_code == 0
    assert stdout_buffer.getvalue().strip() == "3"


def test_cli_vm_backend_reports_runtime_errors_with_location():
    with tempfile.NamedTemporaryFile("w", suffix=".scm", delete=False, encoding="utf-8") as handle:
        handle.write("(+ missing 1)\n")
        script_path = Path(handle.name)

    stderr_buffer = io.StringIO()
    try:
        with redirect_stderr(stderr_buffer):
            exit_code = main([str(script_path), "--backend", "vm"])
    finally:
        script_path.unlink()

    assert exit_code == 1
    assert f"{script_path}:1:" in stderr_buffer.getvalue()
    assert "unbound symbol: missing" in stderr_buffer.getvalue()


def test_cli_vm_backend_stack_option_prints_traceback():
    stderr_buffer = io.StringIO()

    with redirect_stderr(stderr_buffer):
        exit_code = main(
            [
                "-e",
                "(define (explode n) (/ 1 0)) (explode 3)",
                "--backend",
                "vm",
                "--stack",
            ]
        )

    assert exit_code == 1
    output = stderr_buffer.getvalue()
    assert "Stack traceback:" in output
    assert "explode" in output


def test_cli_vm_backend_visualize_curses_does_not_crash():
    sys.modules.pop("compiler.vm_visualizer_headless", None)
    sys.modules["curses"] = types.SimpleNamespace(
        A_BOLD=1,
        A_NORMAL=0,
        A_REVERSE=2,
        KEY_RIGHT=261,
        KEY_LEFT=260,
        error=Exception,
        has_colors=lambda: False,
        wrapper=lambda func: None,
        curs_set=lambda value: None,
    )
    try:
        exit_code = main(["-e", "(+ 1 2)", "--backend", "vm", "--visualize", "curses"])
    finally:
        sys.modules.pop("curses", None)

    assert exit_code == 0


def test_cli_vm_backend_trace_option_does_not_crash():
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(["-e", "(+ 1 2)", "--backend", "vm", "--trace", "--print-output"])

    assert exit_code == 0
    assert stdout_buffer.getvalue().strip() == "3"
