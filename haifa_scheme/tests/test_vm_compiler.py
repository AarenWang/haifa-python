from __future__ import annotations

import importlib
import sys
import types

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


def test_scheme_compiler_rejects_phase_3_unsupported_forms():
    compiler = SchemeCompiler()

    try:
        compiler.compile_source("(lambda (x) x)")
    except Exception as exc:
        assert "unsupported" in str(exc).lower() or "phase" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected compile failure for lambda before phase 4")
