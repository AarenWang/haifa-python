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
