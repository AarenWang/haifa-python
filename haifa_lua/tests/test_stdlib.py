import math
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
    local letters = {"a", 7, "c"}
    local joined = table.concat(letters)
    local sliced = table.concat(letters, "-", 2, 3)
    local numbers = {5, 1, 3}
    table.sort(numbers)
    local words = {"aa", "bbbb", "c"}
    table.sort(words, function(a, b) return #a > #b end)
    return joined, sliced, numbers[1], numbers[2], numbers[3], words[1], words[2], words[3]
    """
    result = run_source(src)
    assert result == ["a7c", "7-c", 1, 3, 5, "bbbb", "aa", "c"]


def test_error_and_assertions():
    with pytest.raises(LuaRuntimeError) as excinfo:
        run_source("error('boom')")
    assert "boom" in str(excinfo.value)
    assert excinfo.value.traceback.startswith("stack traceback")

    src = """
    local ok, msg, extra = assert(true, "ok", 5)
    return ok, msg, extra
    """
    assert run_source(src) == [True, "ok", 5]

    with pytest.raises(LuaRuntimeError) as excinfo2:
        run_source("assert(false, 'fail')")
    assert "fail" in str(excinfo2.value)
    assert excinfo2.value.traceback.startswith("stack traceback")


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


def test_pcall_wraps_errors_with_metadata():
    src = """
    local function safe_add(a, b)
        return a + b
    end

    local function explode()
        local function inner()
            error(\"kaboom\")
        end
        inner()
    end

    local ok1, sum = pcall(safe_add, 2, 3)
    local ok2, err = pcall(explode)
    local frame = err.frames[1]
    local top_name = nil
    if frame ~= nil then
        top_name = frame[\"function\"]
    end
    return ok1, sum, ok2, err.message, err.traceback, top_name, err[\"type\"]
    """
    result = run_source(src)
    assert result[0:2] == [True, 5]
    assert result[2] is False
    assert "kaboom" in result[3]
    assert result[4].startswith("stack traceback")
    assert isinstance(result[5], str) and result[5]
    assert result[6] == "VMRuntimeError"


def test_xpcall_invokes_handler_on_failure():
    src = """
    local function join(a, b)
        return a .. b
    end

    local function explode()
        error(\"kapow\")
    end

    local function handler(err)
        return \"handled:\" .. err.message
    end

    local ok1, value = xpcall(join, handler, \"ha\", \"ifa\")
    local ok2, handled = xpcall(explode, handler)
    local prefix = string.sub(handled, 1, string.len(\"handled:\"))
    return ok1, value, ok2, prefix
    """
    result = run_source(src)
    assert result == [True, "haifa", False, "handled:"]


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


def test_coroutine_status_running_and_isyieldable():
    src = """
    local co
    local info = {}
    local function worker(value)
        local thread, is_main_thread = coroutine.running()
        info.running_equals = thread == co
        info.running_is_main = is_main_thread
        info.yieldable_inside = coroutine.isyieldable()
        coroutine.yield(value + 1)
        return coroutine.status(co)
    end

    co = coroutine.create(worker)
    local main_thread, main_is_main = coroutine.running()
    local main_status = coroutine.status(main_thread)
    local main_yieldable_before = coroutine.isyieldable()
    local initial_status = coroutine.status(co)
    local ok, yielded = coroutine.resume(co, 10)
    local status_after_yield = coroutine.status(co)
    local main_yieldable_after = coroutine.isyieldable()
    local ok2, inner_status = coroutine.resume(co, 99)
    local final_status = coroutine.status(co)
    local main_status_after = coroutine.status(main_thread)
    return main_is_main,
        main_status,
        main_yieldable_before,
        initial_status,
        ok,
        yielded,
        status_after_yield,
        info.running_equals,
        info.running_is_main,
        info.yieldable_inside,
        main_yieldable_after,
        ok2,
        inner_status,
        final_status,
        main_status_after
    """
    result = run_source(src)
    assert result == [
        True,
        "running",
        False,
        "suspended",
        True,
        11,
        "suspended",
        True,
        False,
        True,
        False,
        True,
        "running",
        "dead",
        "running",
    ]


def test_coroutine_wrap_handles_values_and_errors():
    src = """
    local wrapped = coroutine.wrap(function(a, b)
        local x, y = coroutine.yield(a + b, a - b)
        return "done", x, y
    end)

    local first_a, first_b = wrapped(5, 3)
    local second_a, second_b, second_c = wrapped(9, 4)

    local ok, err = pcall(function()
        local failing = coroutine.wrap(function()
            error("boom")
        end)
        failing()
    end)

    local err_text = err
    if type(err) == "table" then
        err_text = err.message
    end

    return first_a,
        first_b,
        second_a,
        second_b,
        second_c,
        ok,
        type(err_text),
        err_text and string.find(err_text, "boom", 1, true) ~= nil
    """
    result = run_source(src)
    assert result == [8, 2, "done", 9, 4, False, "string", True]


def test_coroutine_yield_across_pcall_reports_error():
    src = """
    local info = {}
    local function attempt()
        info.inside = coroutine.isyieldable()
        coroutine.yield("blocked")
    end

    local co = coroutine.create(function()
        local ok, err = pcall(attempt)
        return ok, err, info.inside, coroutine.isyieldable()
    end)

    local ok, protected_ok, message, inside_flag, after_flag = coroutine.resume(co)
    local text = message
    if type(message) == "table" then
        text = message.message
    end
    local has_marker = false
    if type(text) == "string" then
        has_marker = string.find(text, "C-call", 1, true) ~= nil
    end
    return ok, protected_ok, text, has_marker, inside_flag, after_flag
    """
    ok, protected_ok, message, contains_marker, inside_flag, after_flag = run_source(src)
    assert ok is True
    assert protected_ok is False
    assert inside_flag is False
    assert after_flag is False
    assert contains_marker is True
    assert "attempt to yield across a C-call boundary" in message


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
    assert coro_snapshot.is_main is False
    assert coro_snapshot.yieldable is False


def test_string_pattern_and_formatting():
    src = """
    local text = "haifa 2024!"
    local start_idx, end_idx, digits = string.find(text, "(%d+)")
    local replaced, count = string.gsub(text, "%d", "#")
    local word = string.match("user:abc42", "user:(%w+)")
    local formatted = string.format("Hello %s #%02d %.2f %%", "Lua", 7, 3.14159)
    local plain_start, plain_end = string.find("abcabc", "bc", 3, true)
    local upper = string.gsub("mixed case", "%w+", function(value)
        return string.upper(value)
    end)
    return start_idx, end_idx, digits, replaced, count, word, formatted, plain_start, plain_end, upper
    """
    result = run_source(src)
    assert result == [
        7,
        10,
        "2024",
        "haifa ####!",
        4,
        "abc42",
        "Hello Lua #07 3.14 %",
        5,
        6,
        "MIXED CASE",
    ]


def test_table_pack_unpack_and_move():
    src = """
    local packed = table.pack(10, 20, 30)
    local first, second, third = table.unpack(packed)
    local target = {0, 0, 0, 0}
    table.move(packed, 1, packed.n, 2, target)
    table.move(target, 2, 4, 1)
    return packed.n, first, second, third, target[1], target[2], target[3], target[4]
    """
    result = run_source(src)
    assert result == [3, 10, 20, 30, 10, 20, 30, 30]


def test_math_trig_random_and_modf():
    src = """
    math.randomseed(42)
    local r1 = math.random()
    local r2 = math.random(5)
    local r3 = math.random(2, 4)
    local sinv = math.sin(math.rad(90))
    local degv = math.deg(math.pi)
    local radv = math.rad(180)
    local atanv = math.atan(1, 1)
    local int_part, frac_part = math.modf(3.25)
    return r1, r2, r3, sinv, degv, radv, atanv, int_part, frac_part, math.huge > 1e308
    """
    result = run_source(src)
    assert result[0] == pytest.approx(0.6394267984578837)
    assert result[1:] == [
        1.0,
        4.0,
        pytest.approx(1.0),
        180.0,
        pytest.approx(math.pi),
        pytest.approx(math.pi / 4),
        3.0,
        pytest.approx(0.25),
        True,
    ]


def test_os_date_time_and_difftime():
    src = """
    local stamp = os.time({ year = 2024, month = 1, day = 2, hour = 12, min = 34, sec = 56, isdst = false })
    local t = os.date("*t", stamp)
    local iso = os.date("!%Y-%m-%d", stamp)
    local diff = os.difftime(stamp + 10, stamp)
    local clk = os.clock()
    return t.year, t.month, t.day, t.hour, t.min, t.sec, t.isdst, iso, diff, type(clk), clk >= 0
    """
    result = run_source(src)
    assert result[0:7] == [2024, 1, 2, 12, 34, 56, False]
    assert result[7] == "2024-01-02"
    assert result[8] == pytest.approx(10.0)
    assert result[9] == "number"
    assert result[10] is True


def test_io_streams_and_debug_traceback():
    env = create_default_environment()
    script = """
    local handle = io.write("hi")
    local again = handle:write(" there")
    io.stderr:write("err")
    result_stream = handle == io.stdout
    chained_stream = again == io.stdout
    stream_type = io.type(io.stdout)
    """
    output = run_source(script, env)
    assert output == ["hi", " there", "err"]
    assert env["result_stream"] is True
    assert env["chained_stream"] is True
    assert env["stream_type"] == "file"


def test_debug_traceback_returns_message_and_stack():
    src = """
    local function inner()
        return debug.traceback("marker")
    end
    return inner()
    """
    result = run_source(src)
    trace = result[0]
    assert "marker" in trace
    assert "stack traceback" in trace


def test_debug_traceback_supports_coroutines():
    src = """
    local trace_main = debug.traceback("main")
    local co
    local function inner()
        return debug.traceback("inner")
    end
    co = coroutine.create(function()
        local trace = inner()
        coroutine.yield(trace)
        error("boom")
    end)

    local ok, inner_trace = coroutine.resume(co)
    local suspended_trace = debug.traceback(co)
    local ok2, err = coroutine.resume(co)
    return trace_main,
        ok,
        inner_trace,
        suspended_trace,
        ok2,
        err
    """
    trace_main, ok, inner_trace, suspended_trace, ok2, err = run_source(src)
    assert "main" in trace_main
    assert "stack traceback" in trace_main
    assert ok is True
    assert "inner" in inner_trace
    assert "stack traceback" in inner_trace
    assert "stack traceback" in suspended_trace
    assert ok2 is False
    assert err.startswith("<string>:")

