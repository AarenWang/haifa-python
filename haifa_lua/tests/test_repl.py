from __future__ import annotations

from haifa_lua.repl import ReplSession


def test_equal_prefix_shortcut(capsys) -> None:
    session = ReplSession(enable_readline=False)
    session.process_line("=1+2")
    captured = capsys.readouterr()
    assert captured.out.strip() == "3"


def test_env_persistence_across_inputs(capsys) -> None:
    session = ReplSession(enable_readline=False)
    session.process_line("x = 10")
    capsys.readouterr()
    session.process_line("=x + 5")
    captured = capsys.readouterr()
    assert captured.out.strip() == "15"


def test_multiline_if_block(capsys) -> None:
    session = ReplSession(enable_readline=False)
    session.process_line("x = 1")
    capsys.readouterr()
    session.process_line("if x then")
    session.process_line("print('ok')")
    session.process_line("end")
    captured = capsys.readouterr()
    assert "ok" in captured.out


def test_incomplete_detected() -> None:
    session = ReplSession(enable_readline=False)
    session.process_line("function foo()");
    assert session._buffer  # type: ignore[attr-defined]


def test_trace_toggle_commands(capsys) -> None:
    session = ReplSession(enable_readline=False)
    session.process_line(":trace coroutine")
    captured = capsys.readouterr()
    assert "Trace filter set to coroutine" in captured.out

    session.process_line("co = coroutine.create(function() coroutine.yield(42) return 99 end)")
    captured = capsys.readouterr()
    assert "Coroutine events:" in captured.out
    assert "created" in captured.out

    session.process_line("_=coroutine.resume(co)")
    captured = capsys.readouterr()
    assert "true\t42" in captured.out
