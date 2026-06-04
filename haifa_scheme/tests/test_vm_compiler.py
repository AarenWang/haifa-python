from __future__ import annotations

import importlib
import json
import subprocess
import sys
import textwrap
import types
from pathlib import Path

from compiler.bytecode import Opcode
from compiler.bytecode_vm import BytecodeVM

from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.reader import Symbol
from haifa_scheme.stdlib import create_global_environment
from haifa_scheme.compiler import SchemeCompiler, compile_source, run_source_vm
from haifa_scheme.runtime import run_source
from haifa_scheme.values import to_scheme_string
from haifa_scheme.vm_runtime import SchemeVMRuntime


def _run_source_vm_in_subprocess(source: str, *, timeout_seconds: float = 2.0) -> list[object]:
    repo_root = Path(__file__).resolve().parents[2]
    script = textwrap.dedent(
        f"""
        import json
        from haifa_scheme.compiler import run_source_vm

        source = {source!r}
        print(json.dumps(run_source_vm(source)))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "VM subprocess failed unexpectedly:\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


def test_vm_backend_builtin_call_matches_interpreter():
    source = "(+ 1 2 3)"

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_quote_format_matches_interpreter():
    source = "'(1 2 x)"

    [interpreter_value] = run_source(source)
    [vm_value] = run_source_vm(source)

    assert to_scheme_string(vm_value) == to_scheme_string(interpreter_value)


def test_vm_backend_begin_returns_last_expression():
    assert run_source_vm("(begin 1 2 3)") == [3]


def test_vm_backend_apply_accepts_builtin_symbol_value():
    assert run_source_vm("(apply + '(1 2 3))") == [6]


def test_vm_backend_procedure_predicate_accepts_builtin_symbol_value():
    assert run_source_vm("(procedure? +)") == [True]


def test_vm_backend_map_accepts_builtin_symbol_value():
    [value] = run_source_vm("(map + '(1 2) '(10 20))")

    assert to_scheme_string(value) == "(11 22)"


def test_vm_backend_global_define_and_lookup():
    assert run_source_vm("(define x 1) x") == [None, 1]


def test_vm_backend_global_set_updates_existing_binding():
    assert run_source_vm("(define x 1) (set! x 2) x") == [None, None, 2]


def test_vm_backend_unbound_symbol_error_is_clear():
    try:
        run_source_vm("missing")
    except SchemeRuntimeError as exc:
        assert "unbound symbol: missing" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected unbound symbol failure")


def test_vm_backend_shared_environment_persists_globals_across_runs():
    environment = create_global_environment()

    assert run_source_vm("(define x 7)", environment=environment) == [None]
    assert run_source_vm("x", environment=environment) == [7]


def test_vm_backend_parent_environment_exposes_builtin_bindings():
    environment = Environment(parent=create_global_environment())

    assert run_source_vm("(+ 1 2)", environment=environment) == [3]


def test_vm_backend_parent_environment_exposes_parent_globals():
    parent = create_global_environment()
    parent.define(Symbol("x"), 7)
    environment = Environment(parent=parent)

    assert run_source_vm("x", environment=environment) == [7]


def test_vm_backend_simple_lambda_call():
    source = "((lambda (x) (* x x)) 9)"

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_function_define_shorthand_and_recursive_factorial():
    source = """
    (define (fact n)
      (if (= n 0)
          1
          (* n (fact (- n 1)))))
    (fact 5)
    """

    assert _run_source_vm_in_subprocess(source) == run_source(source)


def test_vm_backend_closure_counter():
    source = """
    (define make-counter
      (lambda ()
        (let ((x 0))
          (lambda ()
            (set! x (+ x 1))
            x))))
    (define counter (make-counter))
    (counter)
    (counter)
    """

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_set_mutation_is_visible_through_closure_capture():
    source = """
    (define bump
      (let ((x 1))
        (lambda ()
          (set! x (+ x 2))
          x)))
    (bump)
    (bump)
    """

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_traceback_shows_function_name():
    source = """
    (define (explode n)
      (/ 1 0))
    (explode 3)
    """

    try:
        run_source_vm(source)
    except Exception as exc:
        message = str(exc)
        assert "explode" in message or "traceback" in message.lower()
    else:  # pragma: no cover
        raise AssertionError("expected runtime failure")


def test_vm_backend_only_false_is_falsey():
    source = """
    (if #f 1 2)
    (if 0 1 2)
    (if '() 1 2)
    (if (if #f 10) 1 2)
    """

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_and_short_circuits_and_returns_last_value():
    source = '(and) (and 1 "ok") (and #f missing)'

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_or_short_circuits_and_returns_first_truthy_value():
    source = '(or) (or #f 0 missing) (or "value" missing)'

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_cond_clauses_match_interpreter():
    source = """
    (cond ((= 1 2) 10)
          ((= 2 2) 20)
          (else 30))
    (cond ((+ 1 2)))
    """

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_case_matches_interpreter():
    source = """
    (case 2
      ((1) 'one)
      ((2 3) 'small)
      (else 'other))
    (case '(a b)
      (((x y) (a b)) 'list-match)
      (else 'other))
    """

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_let_star_matches_interpreter():
    source = """
    (define x 10)
    (let* ((x 1)
           (y x))
      y)
    """

    assert run_source_vm(source) == run_source(source)


def test_vm_backend_named_let_factorial_matches_interpreter():
    source = """
    (let fact ((n 5)
               (acc 1))
      (if (= n 0)
          acc
          (fact (- n 1) (* acc n))))
    """

    assert _run_source_vm_in_subprocess(source) == run_source(source)


def test_vm_backend_letrec_supports_recursive_function():
    source = """
    (letrec ((fact (lambda (n)
                     (if (= n 0)
                         1
                         (* n (fact (- n 1)))))))
      (fact 5))
    """

    assert _run_source_vm_in_subprocess(source) == run_source(source)


def test_vm_backend_letrec_rejects_read_before_initialization():
    try:
        run_source_vm("(letrec ((x y) (y 1)) x)")
    except SchemeRuntimeError as exc:
        assert "read before initialization" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected letrec read-before-initialization failure")


def test_vm_backend_do_matches_interpreter():
    source = """
    (do ((i 0 (+ i 1))
         (total 0 (+ total i)))
        ((= i 5) total))
    """

    assert _run_source_vm_in_subprocess(source) == run_source(source)


def test_vm_backend_literal_values_match_interpreter():
    source = '42 "ok" #t #\\a #(1 2) \'()'

    assert run_source_vm(source) == run_source(source)


def test_scheme_compiler_emits_chunk_debug_metadata():
    instructions = compile_source("\n(+ 1 2)", source_name="phase2.scm")

    executable = [instruction for instruction in instructions if instruction.opcode != Opcode.HALT]
    call_instruction = next(
        instruction for instruction in executable if instruction.opcode == Opcode.CALL_VALUE
    )

    assert executable
    assert all(instruction.debug is not None for instruction in executable)
    assert all(instruction.debug.function_name == "<chunk>" for instruction in executable)
    assert call_instruction.debug.location.file == "phase2.scm"
    assert call_instruction.debug.location.line == 2
    assert call_instruction.debug.location.column == 2


def test_visualizer_uses_scheme_source_debug_line():
    if "compiler.vm_visualizer_headless" in sys.modules:
        del sys.modules["compiler.vm_visualizer_headless"]
    if "curses" not in sys.modules:
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
    vm_visualizer_headless = importlib.import_module("compiler.vm_visualizer_headless")
    source = "\n(+ 1 2)"
    instructions = compile_source(source, source_name="phase2.scm")
    vm = BytecodeVM(instructions)
    SchemeVMRuntime().install_into_vm(vm)

    visualizer = vm_visualizer_headless.VMVisualizer(
        vm, source_text=source, source_name="phase2.scm"
    )

    assert visualizer._current_source_line() == 2


def test_scheme_compiler_rejects_phase_4_unsupported_forms():
    compiler = SchemeCompiler()

    try:
        compiler.compile_source("(define-syntax m (syntax-rules () ((_ ) 1)))")
    except Exception as exc:
        assert "unsupported" in str(exc).lower() or "phase" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected compile failure for define-syntax in phase 4")
