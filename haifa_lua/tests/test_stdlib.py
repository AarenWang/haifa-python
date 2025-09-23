import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from haifa_lua import BuiltinFunction, create_default_environment, run_source


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
