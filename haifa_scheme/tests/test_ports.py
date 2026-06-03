from __future__ import annotations

import io

import pytest

from haifa_scheme import EOF_OBJECT, SchemeRuntimeError, Symbol, run_source, to_scheme_string


def test_run_source_default_output_is_not_stdout(capsys: pytest.CaptureFixture[str]):
    assert run_source('(display "silent")') == [None]

    captured = capsys.readouterr()
    assert captured.out == ""


def test_display_write_and_newline_use_injected_output_port():
    output = io.StringIO()

    results = run_source(
        r'''
        (display "hello")
        (display #\space)
        (write "hello")
        (newline)
        (display #\newline)
        (write '(1 . 2))
        ''',
        output=output,
    )

    assert results == [None, None, None, None, None, None]
    assert output.getvalue() == 'hello "hello"\n\n(1 . 2)'


def test_output_procedures_accept_explicit_current_output_port():
    output = io.StringIO()

    run_source(
        r'''
        (define out (current-output-port))
        (display "a" out)
        (write #\space out)
        (newline out)
        ''',
        output=output,
    )

    assert output.getvalue() == r"a#\space" + "\n"


def test_read_returns_multiple_datums_then_eof():
    input_stream = io.StringIO('1 "two" (a . b) #(1 2)')

    values = run_source("(read) (read) (read) (read) (read)", input=input_stream)

    assert values[0] == 1
    assert values[1] == "two"
    assert to_scheme_string(values[2]) == "(a . b)"
    assert to_scheme_string(values[3]) == "#(1 2)"
    assert values[4] is EOF_OBJECT
    assert to_scheme_string(values[4]) == "#<eof>"


def test_read_accepts_explicit_current_input_port():
    input_stream = io.StringIO("10 20")

    assert run_source("(define in (current-input-port)) (read in) (read in)", input=input_stream) == [
        None,
        10,
        20,
    ]


def test_read_reports_syntax_errors_as_runtime_errors():
    with pytest.raises(SchemeRuntimeError, match="read failed"):
        run_source("(read)", input=io.StringIO("(1 . 2 3)"))


def test_file_output_and_input_ports_round_trip(tmp_path):
    path = tmp_path / "scheme-port.txt"
    scheme_path = path.as_posix()

    run_source(
        f'''
        (define out (open-output-file "{scheme_path}"))
        (display "one" out)
        (newline out)
        (write '(2 3) out)
        (close-output-port out)
        '''
    )
    assert path.read_text(encoding="utf-8") == "one\n(2 3)"

    values = run_source(
        f'''
        (define in (open-input-file "{scheme_path}"))
        (read in)
        (read in)
        (read in)
        (close-input-port in)
        '''
    )

    assert values[0] is None
    assert values[1] == Symbol("one")
    assert to_scheme_string(values[2]) == "(2 3)"
    assert values[3] is EOF_OBJECT
    assert values[4] is None


def test_port_predicates(tmp_path):
    path = tmp_path / "predicates.txt"
    scheme_path = path.as_posix()

    values = run_source(
        f'''
        (define out (open-output-file "{scheme_path}"))
        (input-port? (current-input-port))
        (output-port? (current-output-port))
        (output-port? out)
        (input-port? out)
        (close-output-port out)
        (output-port? out)
        (output-port? 1)
        '''
    )

    assert values == [None, True, True, True, False, None, True, False]


def test_closed_ports_reject_read_and_write(tmp_path):
    input_path = tmp_path / "input.txt"
    input_path.write_text("1", encoding="utf-8")
    output_path = tmp_path / "output.txt"

    with pytest.raises(SchemeRuntimeError, match="read expected open input port"):
        run_source(
            f'''
            (define in (open-input-file "{input_path.as_posix()}"))
            (close-input-port in)
            (read in)
            '''
        )

    with pytest.raises(SchemeRuntimeError, match="display expected open output port"):
        run_source(
            f'''
            (define out (open-output-file "{output_path.as_posix()}"))
            (close-output-port out)
            (display "x" out)
            '''
        )


def test_open_file_argument_errors_are_runtime_errors(tmp_path):
    missing_path = tmp_path / "missing.scm"

    with pytest.raises(SchemeRuntimeError, match="open-input-file failed"):
        run_source(f'(open-input-file "{missing_path.as_posix()}")')

    with pytest.raises(SchemeRuntimeError, match="open-output-file expected string path"):
        run_source("(open-output-file 'not-a-string)")
