from __future__ import annotations

import math
from typing import Any, Sequence

from .environment import BuiltinFunction, LuaEnvironment


def _lua_tostring(value: Any) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value)


def _ensure_args(args: Sequence[Any], min_count: int, max_count: int | None = None) -> None:
    count = len(args)
    if count < min_count:
        raise RuntimeError(f"expected at least {min_count} argument(s), got {count}")
    if max_count is not None and count > max_count:
        raise RuntimeError(f"expected at most {max_count} argument(s), got {count}")


def _ensure_number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise RuntimeError("expected number")


def _ensure_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    raise RuntimeError("expected table (list)")


def _ensure_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise RuntimeError("expected string")


def _lua_print(args: Sequence[Any], vm: Any) -> None:  # noqa: ANN401
    text = "\t".join(_lua_tostring(arg) for arg in args)
    vm.output.append(text)
    return None


def _math_unary(func):
    def wrapper(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
        _ensure_args(args, 1, 1)
        return func(_ensure_number(args[0]))

    return wrapper


def _math_min(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 1)
    numbers = [_ensure_number(arg) for arg in args]
    return float(min(numbers))


def _math_max(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 1)
    numbers = [_ensure_number(arg) for arg in args]
    return float(max(numbers))


def _string_len(args: Sequence[Any], vm: Any) -> int:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    return len(_ensure_string(args[0]))


def _table_insert(args: Sequence[Any], vm: Any) -> None:  # noqa: ANN401
    _ensure_args(args, 2, 3)
    target = _ensure_list(args[0])
    if len(args) == 2:
        target.append(args[1])
        return None
    index = int(_ensure_number(args[1]))
    value = args[2]
    if index < 1:
        index = 1
    if index > len(target) + 1:
        index = len(target) + 1
    target.insert(index - 1, value)
    return None


def _table_remove(args: Sequence[Any], vm: Any) -> Any:  # noqa: ANN401
    _ensure_args(args, 1, 2)
    target = _ensure_list(args[0])
    if not target:
        return None
    if len(args) == 1:
        index = len(target)
    else:
        index = int(_ensure_number(args[1]))
    if index < 1 or index > len(target):
        return None
    return target.pop(index - 1)


def install_core_stdlib(env: LuaEnvironment) -> LuaEnvironment:
    env.register("print", BuiltinFunction("print", _lua_print, "Write values to the VM output buffer."))

    math_members = {
        "abs": BuiltinFunction("math.abs", _math_unary(lambda x: abs(x))),
        "sqrt": BuiltinFunction("math.sqrt", _math_unary(lambda x: math.sqrt(x))),
        "floor": BuiltinFunction("math.floor", _math_unary(lambda x: math.floor(x))),
        "ceil": BuiltinFunction("math.ceil", _math_unary(lambda x: math.ceil(x))),
        "min": BuiltinFunction("math.min", _math_min),
        "max": BuiltinFunction("math.max", _math_max),
        "pi": math.pi,
    }
    env.register_library("math", math_members)

    table_members = {
        "insert": BuiltinFunction("table.insert", _table_insert),
        "remove": BuiltinFunction("table.remove", _table_remove),
    }
    env.register_library("table", table_members)

    string_members = {
        "len": BuiltinFunction("string.len", _string_len),
    }
    env.register_library("string", string_members)

    return env


def create_default_environment() -> LuaEnvironment:
    env = LuaEnvironment()
    install_core_stdlib(env)
    return env


__all__ = ["create_default_environment", "install_core_stdlib"]
