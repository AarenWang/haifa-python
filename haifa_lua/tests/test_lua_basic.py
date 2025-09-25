import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from haifa_lua.debug import LuaRuntimeError
from haifa_lua.runtime import run_source


def test_arithmetic_and_assignment():
    src = """
    x = 10
    y = 20
    z = x + y * 2
    return z
    """
    output = run_source(src)
    assert output == [50]


def test_if_else():
    src = """
    x = 10
    if x > 5 then
        y = 1
    else
        y = 2
    end
    return y
    """
    assert run_source(src) == [1]


def test_while_loop():
    src = """
    x = 0
    while x < 5 do
        x = x + 1
    end
    return x
    """
    assert run_source(src) == [5]


def test_function_call():
    src = """
    function add(a, b)
        return a + b
    end

    result = add(3, 4)
    return result
    """
    assert run_source(src) == [7]


def test_print_function_as_global():
    src = """
    function identity(x)
        return x
    end

    value = identity(42)
    return value
    """
    assert run_source(src) == [42]


def test_closure_captures_local():
    src = """
    function make_counter()
        local x = 0
        return function()
            x = x + 1
            return x
        end
    end

    local c = make_counter()
    local a = c()
    local b = c()
    return b
    """
    assert run_source(src) == [2]


def test_closure_independent_instances():
    src = """
    function make_counter()
        local x = 0
        return function()
            x = x + 1
            return x
        end
    end

    local c1 = make_counter()
    local c2 = make_counter()
    local a = c1()
    local b = c1()
    local c = c2()
    return a + b * 10 + c * 100
    """
    assert run_source(src) == [121]


def test_multi_return_basic():
    src = """
    function pair()
        return 1, 2
    end

    return pair()
    """
    assert run_source(src) == [1, 2]


def test_vararg_passthrough():
    src = """
    function pass_through(...)
        return ...
    end

    return pass_through(1, 2, 3)
    """
    assert run_source(src) == [1, 2, 3]


def test_vararg_return_with_prefix():
    src = """
    function mix(...)
        return 1, ...
    end

    return mix(2, 3)
    """
    assert run_source(src) == [1, 2, 3]


def test_vararg_return_non_last():
    src = """
    function head(...)
        return ..., 99
    end

    return head(7, 8)
    """
    assert run_source(src) == [7, 99]


def test_numeric_for_accumulates_sum():
    src = """
    local sum = 0
    for i = 1, 5 do
        sum = sum + i
    end
    return sum
    """
    assert run_source(src) == [15]


def test_numeric_for_negative_step():
    src = """
    local total = 0
    for i = 5, 1, -2 do
        total = total + i
    end
    return total
    """
    assert run_source(src) == [9]


def test_numeric_for_loop_variable_scope():
    src = """
    local value = 42
    for value = 1, 3 do
    end
    return value
    """
    assert run_source(src) == [42]


def test_numeric_for_loop_variable_capture():
    src = """
    local f
    for i = 1, 3 do
        f = function()
            return i
        end
    end
    return f()
    """
    assert run_source(src) == [4]


def test_generic_for_iterates_custom_iterator():
    src = """
    function counter(limit)
        local function iter(state, last)
            local next = last + 1
            if next > state then
                return nil
            end
            return next, next * 2
        end
        return iter, limit, 0
    end

    local total = 0
    for value, doubled in counter(3) do
        total = total + value + doubled
    end
    return total
    """
    assert run_source(src) == [18]


def test_generic_for_loop_variable_scope():
    src = """
    function counter(limit)
        local function iter(state, last)
            local next = last + 1
            if next > state then
                return nil
            end
            return next
        end
        return iter, limit, 0
    end

    local outer = 10
    for inner in counter(2) do
    end
    return outer
    """
    assert run_source(src) == [10]


def test_generic_for_loop_variable_capture():
    src = """
    function counter(limit)
        local function iter(state, last)
            local next = last + 1
            if next > state then
                return nil
            end
            return next
        end
        return iter, limit, 0
    end

    local f
    for value in counter(2) do
        f = function()
            return value
        end
    end
    return f()
    """
    assert run_source(src) == [2]


def test_call_expands_last_argument():
    src = """
    function pair()
        return 4, 5
    end

    function gather(...)
        return ...
    end

    return gather(1, pair())
    """
    assert run_source(src) == [1, 4, 5]


def test_call_collapses_nonlast_vararg():
    src = """
    function gather(...)
        return ...
    end

    function wrap(...)
        return gather(..., 42)
    end

    return wrap(8, 9)
    """
    assert run_source(src) == [8, 42]


def test_vararg_assignment_first_value():
    src = """
    function first(...)
        local x = ...
        return x
    end

    return first(10, 11)
    """
    assert run_source(src) == [10]


def test_local_multi_declaration_defaults_nil():
    src = """
    local a, b
    return a, b
    """
    assert run_source(src) == [None, None]


def test_multi_assignment_basic():
    src = """
    local a, b = 1, 2, 3
    return a, b
    """
    assert run_source(src) == [1, 2]


def test_multi_assignment_expands_call_results():
    src = """
    function trio()
        return 1, 2, 3
    end

    local x, y, z, w = trio()
    return x, y, z, w
    """
    assert run_source(src) == [1, 2, 3, None]


def test_multi_assignment_expands_vararg():
    src = """
    function take(...)
        local a, b, c = ...
        return a, b, c
    end

    return take(7, 8)
    """
    assert run_source(src) == [7, 8, None]


def test_table_constructor_and_field_updates():
    src = """
    local t = {10, answer = 42, [3] = 99}
    t.extra = 7
    t[2] = 20
    return t[1], t.answer, t[2], t[3], t.extra
    """
    assert run_source(src) == [10, 42, 20, 99, 7]


def test_table_length_and_insert():
    src = """
    local t = {}
    t[1] = "a"
    t[2] = "b"
    t[2] = nil
    table.insert(t, "c")
    return #t, t[1], t[2]
    """
    assert run_source(src) == [2, "a", "c"]


def test_table_constructor_expands_last_call():
    src = """
    function produce()
        return 1, 2, 3
    end

    local t = {0, produce()}
    return #t, t[1], t[2], t[3], t[4]
    """
    assert run_source(src) == [4, 0, 1, 2, 3]


def test_string_concatenation_operator():
    src = """
    local greeting = "hello"
    local value = 42
    return greeting .. " " .. value
    """
    assert run_source(src) == ["hello 42"]


def test_length_operator_for_string_and_table():
    src = """
    local t = {1, 2, 3}
    local s = "abc"
    return #t, #s
    """
    assert run_source(src) == [3, 3]


def test_repeat_until_loop_executes_until_condition():
    src = """
    local x = 0
    repeat
        x = x + 1
    until x >= 4
    return x
    """
    assert run_source(src) == [4]


def test_repeat_until_condition_sees_block_locals():
    src = """
    local result = 0
    repeat
        local next = result + 1
        result = next
    until next >= 3
    return result
    """
    assert run_source(src) == [3]


def test_break_exits_only_innermost_loop():
    src = """
    local total = 0
    for i = 1, 3 do
        for j = 1, 3 do
            if j == 2 then
                break
            end
            total = total + 10 * i + j
        end
    end
    return total
    """
    assert run_source(src) == [63]


def test_break_from_repeat_loop():
    src = """
    local count = 0
    repeat
        count = count + 1
        if count == 2 then
            break
        end
    until count > 10
    return count
    """
    assert run_source(src) == [2]


def test_do_block_creates_isolated_scope():
    src = """
    local value = 1
    do
        local value = 5
        value = value + 1
    end
    return value
    """
    assert run_source(src) == [1]


def test_runtime_error_reports_lua_style_location():
    src = """
    local x = 1
    return x + nil
    """

    with pytest.raises(LuaRuntimeError) as excinfo:
        run_source(src)

    message = str(excinfo.value)
    assert message.startswith("<string>:3:")
