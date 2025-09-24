import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler.bytecode_vm import BytecodeVM
from compiler.vm_events import (
    CoroutineCompleted,
    CoroutineCreated,
    CoroutineResumed,
    CoroutineYielded,
)

from haifa_lua import BuiltinFunction, create_default_environment, run_source
from haifa_lua.debug import LuaRuntimeError
from haifa_lua.runtime import compile_source


def test_print_builtin_appends_output():
    src = "print(1, 2, 3)"
    assert run_source(src) == ["1\t2\t3"]


def test_math_and_string_builtins():
    src = "return math.max(1, -8, 5), string.len(\"haifa\")"
    result = run_source(src)
    assert result == [5.0, 5]


def test_table_insert_and_remove_roundtrip():
    env = create_default_environment()
    env.register("arr", [])
    script = """
    table.insert(arr, 1)
    table.insert(arr, 2)
    local removed = table.remove(arr)
    return removed
    """
    result = run_source(script, env)
    assert result == [2]
    assert env["arr"] == [1]


def test_environment_hot_update():
    env = create_default_environment()
    captured = []

    def capture(args, vm):
        captured.append(tuple(args))
        return None

    env.register("print", BuiltinFunction("print", capture))
    run_source("print(1, 2)", env)
    assert captured == [(1, 2)]


def test_builtin_with_closure_and_multi_return():
    src = """
    function make_adder(x)
        return function(...)
            local max_val = math.max(...)
            return max_val + x, string.len(\"ok\")
        end
    end

    local add = make_adder(10)
    return add(1, 7, 3)
    """
    result = run_source(src)
    assert result == [17.0, 2]


def test_print_handles_multi_return():
    src = """
    function spread(...)
        return ...
    end

    print(spread(1, 2))
    """
    result = run_source(src)
    assert result == ["1\t2"]


def test_coroutine_yield_and_resume_roundtrip():
    env = create_default_environment()
    setup = """
    function worker(a)
        local inc = coroutine.yield(a + 1)
        return a + inc, a
    end

    return coroutine.create(worker)
    """
    coroutine_obj = run_source(setup, env)[0]
    env.register("co", coroutine_obj)

    first = run_source("return coroutine.resume(co, 10)", env)
    second = run_source("return coroutine.resume(co, 5)", env)
    assert first == [True, 11]
    assert second == [True, 15, 10]


def test_coroutine_resume_after_completion():
    env = create_default_environment()
    setup = """
    function once()
        return 99
    end

    return coroutine.create(once)
    """
    co = run_source(setup, env)[0]
    env.register("co", co)

    first = run_source("return coroutine.resume(co)", env)
    assert first == [True, 99]

    second = run_source("return coroutine.resume(co)", env)
    assert second[0] is False
    assert isinstance(second[1], str)


def test_coroutine_yield_outside_context_raises():
    with pytest.raises(LuaRuntimeError):
        run_source("return coroutine.yield(1)")


def test_coroutine_resume_reports_lua_style_error_message():
    script = """
    function boom()
        local x = coroutine.yield(1)
        return x + nil
    end

    local co = coroutine.create(boom)
    coroutine.resume(co, 1)
    return coroutine.resume(co, 2)
    """

    result = run_source(script)
    assert result[0] is False
    assert isinstance(result[1], str)
    assert result[1].startswith("<string>:4:")


def test_coroutine_event_sequence():
    source = """
    function worker(a)
        local inc = coroutine.yield(a + 1)
        return inc * 2
    end

    local co = coroutine.create(worker)
    coroutine.resume(co, 10)
    coroutine.resume(co, 5)
    """

    instructions = list(compile_source(source, source_name="<test>"))
    env = create_default_environment()
    vm = BytecodeVM(instructions)
    vm.lua_env = env
    vm.registers.update(env.to_vm_registers())
    vm.run()
    events = vm.drain_events()

    kinds = [type(event) for event in events]
    assert kinds == [
        CoroutineCreated,
        CoroutineResumed,
        CoroutineYielded,
        CoroutineResumed,
        CoroutineCompleted,
    ]

    created = events[0]
    assert isinstance(created, CoroutineCreated)
    assert created.parent_id is None

    resumed = events[1]
    assert isinstance(resumed, CoroutineResumed)
    assert list(resumed.args) == [10]

    yielded = events[2]
    assert isinstance(yielded, CoroutineYielded)
    assert list(yielded.values) == [11]

    completed = events[-1]
    assert isinstance(completed, CoroutineCompleted)
    assert list(completed.values) == [10]


def test_coroutine_snapshot_contains_runtime_state():
    source = """
    function worker(a)
        local inc = coroutine.yield(a + 1)
        return inc * 2
    end

    local co = coroutine.create(worker)
    coroutine.resume(co, 10)
    """

    instructions = list(compile_source(source, source_name="<snapshot>"))
    env = create_default_environment()
    vm = BytecodeVM(instructions)
    vm.lua_env = env
    vm.registers.update(env.to_vm_registers())
    vm.run()

    snapshot = vm.snapshot_state()
    assert snapshot.coroutines, "expected coroutine snapshot to be recorded"

    coro_snapshot = snapshot.coroutines[0]
    assert coro_snapshot.status == "suspended"
    assert coro_snapshot.last_resume_args == [10]
    assert coro_snapshot.last_yield == [11]
    assert coro_snapshot.function_name == "worker"
    assert coro_snapshot.registers is not None
    assert isinstance(coro_snapshot.registers, dict)
    assert coro_snapshot.call_stack, "call stack should contain at least the current frame"
    assert coro_snapshot.upvalues is not None
    assert coro_snapshot.current_pc is not None
