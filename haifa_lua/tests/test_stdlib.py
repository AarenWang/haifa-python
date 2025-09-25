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

from haifa_lua import BuiltinFunction, LuaTable, create_default_environment, run_source
from haifa_lua.debug import LuaRuntimeError
from haifa_lua.runtime import compile_source


def test_print_builtin_appends_output():
    src = "print(1, 2, 3)"
    assert run_source(src) == ["1\t2\t3"]


def test_math_and_string_builtins():
    src = "return math.max(1, -8, 5), string.len(\"haifa\")"
    result = run_source(src)
    assert result == [5.0, 5]


def test_type_number_and_string_helpers():
    src = """
    local tbl = {}
    local function fn() end
    local co = coroutine.create(function() end)
    local none = tonumber(nil)
    local invalid = tonumber("oops")
    return type(nil), type(true), type(3.5), type("hi"), type(tbl), type(fn), type(co),
        tostring(nil), tostring(true), tostring(12), tostring(12.5),
        tonumber("10"), tonumber("3.5"), tonumber("10", 16), none, invalid
    """
    result = run_source(src)
    assert result == [
        "nil",
        "boolean",
        "number",
        "string",
        "table",
        "function",
        "thread",
        "nil",
        "true",
        "12",
        "12.5",
        10.0,
        3.5,
        16.0,
        None,
        None,
    ]


def test_next_pairs_and_ipairs_iteration():
    src = """
    local t = {10, 20, answer = 42}
    local k1, v1 = next(t)
    local k2, v2 = next(t, k1)
    local k3, v3 = next(t, k2)
    local k4, v4 = next(t, k3)
    local count = 0
    local sum = 0
    for _, value in pairs(t) do
        count = count + 1
        sum = sum + value
    end
    local seq = 0
    for i, value in ipairs({4, 5, 6}) do
        seq = seq + i * value
    end
    return k1, v1, k2, v2, k3, v3, k4, v4, count, sum, seq
    """
    result = run_source(src)
    assert result == [1, 10, 2, 20, "answer", 42, None, None, 3, 72, 32]


def test_string_library_functions():
    src = """
    local text = "Hello World"
    return string.sub(text, 2, 5), string.sub(text, 4), string.sub(text, -5, -1),
        string.upper(text), string.lower(text)
    """
    result = run_source(src)
    assert result == ["ello", "lo World", "World", "HELLO WORLD", "hello world"]


def test_tonumber_base_conversion_and_invalid_digits():
    src = """
    local invalid = tonumber("7", 2)
    return tonumber("ff", 16), invalid == nil
    """
    result = run_source(src)
    assert result == [255.0, True]


def test_tonumber_rejects_base_out_of_range():
    with pytest.raises(LuaRuntimeError) as excinfo:
        run_source("tonumber('10', 1)")
    assert "base out of range" in str(excinfo.value)


def test_table_concat_and_sort():
    src = """
    local letters = {"a", "b", "c"}
    local joined = table.concat(letters)
    local sliced = table.concat(letters, "-", 2, 3)
    local numbers = {5, 1, 3}
    table.sort(numbers)
    local words = {"aa", "bbbb", "c"}
    table.sort(words, function(a, b) return #a > #b end)
    return joined, sliced, numbers[1], numbers[2], numbers[3], words[1], words[2], words[3]
    """
    result = run_source(src)
    assert result == ["abc", "b-c", 1, 3, 5, "bbbb", "aa", "c"]


def test_error_and_assertions():
    with pytest.raises(LuaRuntimeError) as excinfo:
        run_source("error('boom')")
    assert "boom" in str(excinfo.value)

    src = """
    local ok, msg, extra = assert(true, "ok", 5)
    return ok, msg, extra
    """
    assert run_source(src) == [True, "ok", 5]

    with pytest.raises(LuaRuntimeError) as excinfo2:
        run_source("assert(false, 'fail')")
    assert "fail" in str(excinfo2.value)


def test_error_default_message_and_assert_varargs():
    with pytest.raises(LuaRuntimeError) as excinfo:
        run_source("error()")
    assert "error" in str(excinfo.value)

    src = """
    local a, b, c = assert(5, "keep", nil)
    return a, b, c
    """
    result = run_source(src)
    assert result == [5, "keep", None]


def test_pairs_and_ipairs_return_protocol():
    src = """
    local iter, tbl, seed = ipairs({10, 20})
    local first_index, first_value = iter(tbl, seed)
    local next_fn, next_tbl, start_key = pairs({x = 1})
    return type(iter), type(tbl), seed, first_index, first_value,
        type(next_fn), type(next_tbl), start_key
    """
    result = run_source(src)
    assert result == [
        "function",
        "table",
        0,
        1,
        10,
        "function",
        "table",
        None,
    ]


def test_table_insert_and_remove_roundtrip():
    env = create_default_environment()
    env.register("arr", LuaTable())
    script = """
    table.insert(arr, 1)
    table.insert(arr, 2)
    local removed = table.remove(arr)
    return removed
    """
    result = run_source(script, env)
    assert result == [2]
    arr = env["arr"]
    assert isinstance(arr, LuaTable)
    assert arr.lua_len() == 1
    assert arr.raw_get(1) == 1


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
