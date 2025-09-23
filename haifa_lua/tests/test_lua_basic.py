import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
