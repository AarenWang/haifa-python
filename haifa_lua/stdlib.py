from __future__ import annotations

import math
from typing import Any, Sequence

from compiler.bytecode_vm import LuaYield
from compiler.vm_errors import VMRuntimeError

from .coroutines import CoroutineError, LuaCoroutine
from .environment import BuiltinFunction, LuaEnvironment, LuaMultiReturn
from .debug import format_lua_error, format_traceback
from .table import LuaTable


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


def _ensure_table(value: Any) -> LuaTable:
    if isinstance(value, LuaTable):
        return value
    raise RuntimeError("expected table")


def _ensure_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise RuntimeError("expected string")


def _wrap_frames(frames) -> LuaTable:
    table = LuaTable()
    for index, frame in enumerate(frames, start=1):
        entry = LuaTable()
        entry.raw_set("function", frame.function_name)
        entry.raw_set("file", frame.file)
        entry.raw_set("line", frame.line)
        entry.raw_set("pc", frame.pc)
        if frame.coroutine_id is not None:
            entry.raw_set("coroutine", frame.coroutine_id)
        table.raw_set(index, entry)
    return table


def _create_error_object(error: Exception) -> LuaTable:
    table = LuaTable()
    if isinstance(error, VMRuntimeError):
        frames = error.frames
        message = format_lua_error(str(error), frames[0] if frames else None)
        table.raw_set("traceback", format_traceback(frames) if frames else "")
        table.raw_set("frames", _wrap_frames(frames))
    else:
        message = str(error) or error.__class__.__name__
        table.raw_set("traceback", "")
        table.raw_set("frames", LuaTable())
    table.raw_set("message", message)
    table.raw_set("type", error.__class__.__name__)
    return table


def _is_lua_truthy(value: Any) -> bool:
    return not (value is None or value is False)


def _is_lua_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _lua_setmetatable(args: Sequence[Any], vm: Any) -> LuaTable:  # noqa: ANN401
    _ensure_args(args, 2, 2)
    table = _ensure_table(args[0])
    metatable_value = args[1]
    if metatable_value is None:
        table.set_metatable(None)
        return table
    metatable = _ensure_table(metatable_value)
    table.set_metatable(metatable)
    return table


def _lua_getmetatable(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 1, 1)
    table = _ensure_table(args[0])
    return table.get_metatable()


def _lua_rawget(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 2, 2)
    table = _ensure_table(args[0])
    return table.raw_get(args[1])


def _lua_rawset(args: Sequence[Any], vm: Any) -> LuaTable:  # noqa: ANN401
    _ensure_args(args, 3, 3)
    table = _ensure_table(args[0])
    table.raw_set(args[1], args[2])
    return table


def _lua_rawequal(args: Sequence[Any], vm: Any) -> bool:  # noqa: ANN401
    _ensure_args(args, 2, 2)
    left, right = args
    if left is right:
        return True
    if left is None or right is None:
        return False
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if _is_lua_number(left) and _is_lua_number(right):
        return float(left) == float(right)
    if isinstance(left, LuaTable) and isinstance(right, LuaTable):
        return left is right
    return left == right


def _lua_type(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401 - VM is dynamic
    _ensure_args(args, 1, 1)
    value = args[0]
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "boolean"
    if _is_lua_number(value):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, LuaTable):
        return "table"
    if isinstance(value, LuaCoroutine):
        return "thread"
    if isinstance(value, dict) and "label" in value:
        return "function"
    if getattr(value, "__lua_builtin__", False):
        return "function"
    if callable(value):
        return "function"
    return "userdata"


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


def _lua_next(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 1, 2)
    table = _ensure_table(args[0])
    keys = [key for key, _ in table.iter_items()]
    if not keys:
        return LuaMultiReturn([None])

    if len(args) == 1 or args[1] is None:
        next_key = keys[0]
    else:
        current = args[1]
        next_key = None
        seen = False
        for key in keys:
            if seen:
                next_key = key
                break
            if key == current:
                seen = True
        if not seen or next_key is None:
            return LuaMultiReturn([None])
    return LuaMultiReturn([next_key, table.raw_get(next_key)])


def _create_pairs_builtin(next_builtin: BuiltinFunction) -> BuiltinFunction:
    def _pairs(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
        _ensure_args(args, 1, 1)
        table = _ensure_table(args[0])
        return LuaMultiReturn([next_builtin, table, None])

    return BuiltinFunction("pairs", _pairs)


def _ipairs_iter(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 2, 2)
    table = _ensure_table(args[0])
    index = int(_ensure_number(args[1]))
    next_index = index + 1
    value = table.raw_get(next_index)
    if value is None:
        return LuaMultiReturn([None])
    return LuaMultiReturn([next_index, value])


def _create_ipairs_builtin(iterator: BuiltinFunction) -> BuiltinFunction:
    def _ipairs(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
        _ensure_args(args, 1, 1)
        table = _ensure_table(args[0])
        return LuaMultiReturn([iterator, table, 0])

    return BuiltinFunction("ipairs", _ipairs)


def _lua_tonumber(args: Sequence[Any], vm: Any) -> float | None:  # noqa: ANN401
    _ensure_args(args, 1, 2)
    value = args[0]
    if len(args) == 1:
        if value is None:
            return None
        if _is_lua_number(value):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return None
        return None

    base = int(_ensure_number(args[1]))
    if base < 2 or base > 36:
        raise RuntimeError("base out of range")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(int(text, base))
        except ValueError:
            return None
    raise RuntimeError("tonumber base conversion expects string")


def _lua_tostring_builtin(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    return _lua_tostring(args[0])


def _lua_error(args: Sequence[Any], vm: Any) -> None:  # noqa: ANN401
    _ensure_args(args, 0, 2)
    if args:
        message = _lua_tostring(args[0])
    else:
        message = "error"
    raise RuntimeError(message)


def _lua_assert(args: Sequence[Any], vm: Any) -> LuaMultiReturn | Any:  # noqa: ANN401
    _ensure_args(args, 1)
    condition = args[0]
    if not _is_lua_truthy(condition):
        message = args[1] if len(args) > 1 else "assertion failed!"
        raise RuntimeError(_lua_tostring(message))
    if len(args) == 1:
        return condition
    return LuaMultiReturn(list(args))


def _lua_pcall(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 1)
    func = args[0]
    call_args = list(args[1:])
    try:
        result = vm.call_callable(func, call_args)
    except Exception as exc:  # noqa: BLE001 - needs to catch VMRuntimeError and RuntimeError
        error_obj = _create_error_object(exc)
        return LuaMultiReturn([False, error_obj])
    return LuaMultiReturn([True, *result])


def _lua_xpcall(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 2)
    func = args[0]
    handler = args[1]
    call_args = list(args[2:])
    try:
        result = vm.call_callable(func, call_args)
        return LuaMultiReturn([True, *result])
    except Exception as exc:  # noqa: BLE001 - needs to catch VMRuntimeError and RuntimeError
        error_obj = _create_error_object(exc)
        handler_result = vm.call_callable(handler, [error_obj])
        return LuaMultiReturn([False, *handler_result])


def _string_sub(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401
    _ensure_args(args, 2, 3)
    value = _ensure_string(args[0])
    start = int(_ensure_number(args[1]))
    end = None
    if len(args) >= 3 and args[2] is not None:
        end = int(_ensure_number(args[2]))
    length = len(value)
    if start < 0:
        start = length + start + 1
    if start < 1:
        start = 1
    if end is None:
        end = length
    else:
        if end < 0:
            end = length + end + 1
        if end > length:
            end = length
    if start > end or start > length:
        return ""
    if end < 1:
        return ""
    return value[start - 1 : end]


def _string_upper(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    return _ensure_string(args[0]).upper()


def _string_lower(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    return _ensure_string(args[0]).lower()


def _table_concat(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401
    _ensure_args(args, 1, 4)
    table = _ensure_table(args[0])
    separator = ""
    if len(args) >= 2 and args[1] is not None:
        separator = _ensure_string(args[1])
    if len(args) >= 3 and args[2] is not None:
        start = int(_ensure_number(args[2]))
    else:
        start = 1
    if len(args) >= 4 and args[3] is not None:
        stop = int(_ensure_number(args[3]))
    else:
        stop = table.lua_len()
    length = table.lua_len()
    if start < 1:
        start = 1
    if stop > length:
        stop = length
    if stop < start:
        return ""
    parts = []
    for index in range(start, stop + 1):
        value = table.raw_get(index)
        if value is None:
            raise RuntimeError("table element is nil")
        parts.append(_lua_tostring(value))
    return separator.join(parts)


def _table_sort(args: Sequence[Any], vm: Any) -> None:  # noqa: ANN401
    _ensure_args(args, 1, 2)
    table = _ensure_table(args[0])
    comparator = args[1] if len(args) == 2 else None
    length = table.lua_len()
    values = []
    for index in range(1, length + 1):
        value = table.raw_get(index)
        if value is None:
            raise RuntimeError("table contains nil value")
        values.append(value)

    def compare(left, right):
        if comparator is None:
            try:
                if left < right:
                    return -1
                if left > right:
                    return 1
                return 0
            except TypeError as exc:  # pragma: no cover - defensive branch
                raise RuntimeError("attempt to compare incompatible values") from exc
        first = vm.call_callable(comparator, [left, right])
        cond_left = bool(first[0]) if first else False
        if cond_left:
            return -1
        second = vm.call_callable(comparator, [right, left])
        cond_right = bool(second[0]) if second else False
        if cond_right:
            return 1
        return 0

    for i in range(1, len(values)):
        key = values[i]
        j = i - 1
        while j >= 0 and compare(values[j], key) > 0:
            values[j + 1] = values[j]
            j -= 1
        values[j + 1] = key

    for idx, value in enumerate(values, start=1):
        table.raw_set(idx, value)

def _string_len(args: Sequence[Any], vm: Any) -> int:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    return len(_ensure_string(args[0]))


def _ensure_coroutine(value: Any) -> LuaCoroutine:
    if isinstance(value, LuaCoroutine):
        return value
    raise RuntimeError("expected coroutine")


def _table_insert(args: Sequence[Any], vm: Any) -> None:  # noqa: ANN401
    _ensure_args(args, 2, 3)
    target = _ensure_table(args[0])
    if len(args) == 2:
        target.append(args[1])
        return None
    index = int(_ensure_number(args[1]))
    value = args[2]
    target.insert(index, value)
    return None


def _table_remove(args: Sequence[Any], vm: Any) -> Any:  # noqa: ANN401
    _ensure_args(args, 1, 2)
    target = _ensure_table(args[0])
    if len(args) == 1:
        return target.remove()
    index = int(_ensure_number(args[1]))
    return target.remove(index)



def _coroutine_create(args: Sequence[Any], vm: Any) -> LuaCoroutine:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    try:
        return LuaCoroutine(args[0], vm)
    except CoroutineError as exc:
        raise RuntimeError(str(exc)) from exc


def _coroutine_resume(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 1)
    coroutine = _ensure_coroutine(args[0])
    resume_args = args[1:]
    result = coroutine.resume(resume_args)
    values = [result.success]
    values.extend(result.values)
    return LuaMultiReturn(values)


def _coroutine_yield(args: Sequence[Any], vm: Any) -> LuaYield:  # noqa: ANN401
    return LuaYield(args)



def install_core_stdlib(env: LuaEnvironment) -> LuaEnvironment:
    env.register("print", BuiltinFunction("print", _lua_print, "Write values to the VM output buffer."))

    type_builtin = BuiltinFunction("type", _lua_type, "Return the type of a Lua value.")
    next_builtin = BuiltinFunction("next", _lua_next, "Iterate to the next key in a table.")
    tonumber_builtin = BuiltinFunction("tonumber", _lua_tonumber, "Convert a value to a number.")
    tostring_builtin = BuiltinFunction("tostring", _lua_tostring_builtin, "Convert a value to a string.")
    error_builtin = BuiltinFunction("error", _lua_error, "Raise a Lua error.")
    assert_builtin = BuiltinFunction("assert", _lua_assert, "Assert that a value is truthy.")
    pcall_builtin = BuiltinFunction("pcall", _lua_pcall, "Call a function in protected mode.")
    xpcall_builtin = BuiltinFunction("xpcall", _lua_xpcall, "Protected call with custom handler.")
    ipairs_iterator = BuiltinFunction("ipairs_iterator", _ipairs_iter)

    env.register("type", type_builtin)
    env.register("next", next_builtin)
    env.register("pairs", _create_pairs_builtin(next_builtin))
    env.register("ipairs", _create_ipairs_builtin(ipairs_iterator))
    env.register("tonumber", tonumber_builtin)
    env.register("tostring", tostring_builtin)
    env.register("error", error_builtin)
    env.register("assert", assert_builtin)
    env.register("pcall", pcall_builtin)
    env.register("xpcall", xpcall_builtin)
    env.register("setmetatable", BuiltinFunction("setmetatable", _lua_setmetatable))
    env.register("getmetatable", BuiltinFunction("getmetatable", _lua_getmetatable))
    env.register("rawget", BuiltinFunction("rawget", _lua_rawget))
    env.register("rawset", BuiltinFunction("rawset", _lua_rawset))
    env.register("rawequal", BuiltinFunction("rawequal", _lua_rawequal))

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
        "concat": BuiltinFunction("table.concat", _table_concat),
        "sort": BuiltinFunction("table.sort", _table_sort),
    }
    env.register_library("table", table_members)

    string_members = {
        "len": BuiltinFunction("string.len", _string_len),
        "sub": BuiltinFunction("string.sub", _string_sub),
        "upper": BuiltinFunction("string.upper", _string_upper),
        "lower": BuiltinFunction("string.lower", _string_lower),
    }
    env.register_library("string", string_members)

    coroutine_members = {
        "create": BuiltinFunction("coroutine.create", _coroutine_create),
        "resume": BuiltinFunction("coroutine.resume", _coroutine_resume),
        "yield": BuiltinFunction("coroutine.yield", _coroutine_yield),
    }
    env.register_library("coroutine", coroutine_members)

    return env


def create_default_environment() -> LuaEnvironment:
    env = LuaEnvironment()
    install_core_stdlib(env)
    return env


__all__ = ["create_default_environment", "install_core_stdlib"]
