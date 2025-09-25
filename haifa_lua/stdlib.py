from __future__ import annotations

import math
import random
import re
import time
from functools import lru_cache
from typing import Any, Sequence

from compiler.bytecode_vm import LuaYield
from compiler.vm_errors import VMRuntimeError

from .coroutines import CoroutineError, LuaCoroutine
from .environment import BuiltinFunction, LuaEnvironment, LuaMultiReturn
from .debug import format_lua_error, format_traceback
from .module_system import LuaModuleSystem
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


def _ensure_int(value: Any) -> int:
    number = _ensure_number(value)
    return int(number)


_LUA_PATTERN_CLASS_MAP = {
    "a": "[A-Za-z]",
    "A": "[^A-Za-z]",
    "d": r"\d",
    "D": r"\D",
    "s": r"\s",
    "S": r"\S",
    "w": r"[A-Za-z0-9_]",
    "W": r"[^A-Za-z0-9_]",
    "l": "[a-z]",
    "L": "[^a-z]",
    "u": "[A-Z]",
    "U": "[^A-Z]",
    "p": r"[!\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]",
    "P": r"[^!\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]",
    "c": r"[\x00-\x1F\x7F]",
    "C": r"[^\x00-\x1F\x7F]",
    "g": r"[^\s]",
    "G": r"\s",
    "x": r"[0-9A-Fa-f]",
    "X": r"[^0-9A-Fa-f]",
    "z": r"\x00",
    "Z": r"[^\x00]",
    "%": "%",
}

_LUA_CLASS_SET_MAP = {
    "a": "A-Za-z",
    "d": "0-9",
    "l": "a-z",
    "u": "A-Z",
    "w": "A-Za-z0-9_",
    "x": "0-9A-Fa-f",
    "s": r"\s",
    "z": r"\x00",
}


def _translate_lua_pattern(pattern: str) -> str:
    result: list[str] = []
    length = len(pattern)
    i = 0
    while i < length:
        char = pattern[i]
        if char == "%":
            i += 1
            if i >= length:
                result.append("%")
                break
            code = pattern[i]
            if code.isdigit():
                result.append(f"\\{code}")
            elif code == "b":
                raise RuntimeError("pattern %b is not supported")
            elif code == "f":
                raise RuntimeError("pattern %f is not supported")
            else:
                mapped = _LUA_PATTERN_CLASS_MAP.get(code)
                if mapped is not None:
                    result.append(mapped)
                else:
                    result.append(re.escape(code))
        elif char == "[":
            j = i + 1
            negate = False
            if j < length and pattern[j] == "^":
                negate = True
                j += 1
            parts: list[str] = []
            while j < length and pattern[j] != "]":
                current = pattern[j]
                if current == "%":
                    j += 1
                    if j >= length:
                        break
                    code = pattern[j]
                    mapped = _LUA_CLASS_SET_MAP.get(code)
                    if mapped is None:
                        mapped = _LUA_PATTERN_CLASS_MAP.get(code)
                        if mapped is None:
                            mapped = re.escape(code)
                        elif mapped.startswith("[") and mapped.endswith("]"):
                            mapped = mapped[1:-1]
                        else:
                            if mapped.startswith("[^"):
                                raise RuntimeError("unsupported character class complement in set")
                    parts.append(mapped)
                else:
                    parts.append(re.escape(current))
                j += 1
            if j >= length:
                result.append(re.escape("["))
            else:
                content = "".join(parts)
                prefix = "^" if negate else ""
                result.append("[" + prefix + content + "]")
                i = j
        elif char in "().^$":
            result.append(char)
        elif char == "-":
            result.append("*?")
        elif char in "*+?":
            result.append(char)
        elif char == ".":
            result.append(".")
        else:
            result.append(re.escape(char))
        i += 1
    return "".join(result)


@lru_cache(maxsize=128)
def _compile_lua_pattern(pattern: str) -> re.Pattern[str]:
    translated = _translate_lua_pattern(pattern)
    return re.compile(translated)


def _normalize_start(length: int, init: Any | None) -> int:
    if init is None:
        return 0
    index = int(_ensure_number(init))
    if index > 0:
        if index > length + 1:
            return length
        return index - 1
    if index == 0:
        return 0
    computed = length + index + 1
    if computed < 1:
        return 0
    if computed > length + 1:
        computed = length + 1
    return computed - 1


def _collect_match_groups(match: re.Match[str]) -> list[Any]:
    groups = list(match.groups())
    if groups:
        return [group if group is not None else None for group in groups]
    return [match.group(0)]


def _expand_replacement(template: str, match: re.Match[str]) -> str:
    pieces: list[str] = []
    i = 0
    length = len(template)
    while i < length:
        char = template[i]
        if char != "%":
            pieces.append(char)
            i += 1
            continue
        i += 1
        if i >= length:
            pieces.append("%")
            break
        code = template[i]
        if code == "%":
            pieces.append("%")
        elif code.isdigit():
            group_index = int(code)
            try:
                value = match.group(group_index)
            except IndexError:
                value = ""
            pieces.append(value or "")
        else:
            pieces.append(code)
        i += 1
    return "".join(pieces)


def _match_replacement_value(value: Any) -> str:
    if value is None:
        return ""
    return _lua_tostring(value)


def _resolve_gsub_replacement(match: re.Match[str], repl: Any, vm: Any) -> str:  # noqa: ANN401
    if isinstance(repl, str):
        return _expand_replacement(repl, match)
    if isinstance(repl, LuaTable):
        groups = match.groups()
        key = groups[0] if groups else match.group(0)
        value = repl.raw_get(key)
        if value is None:
            return match.group(0)
        return _match_replacement_value(value)
    values = vm.call_callable(repl, _collect_match_groups(match))
    if not values:
        return match.group(0)
    replacement = values[0]
    if replacement is None:
        return match.group(0)
    return _match_replacement_value(replacement)


_RANDOM_GENERATOR = random.Random()
IO_STREAM_MARKER = "__lua_io_stream__"


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


def _math_deg(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    return math.degrees(_ensure_number(args[0]))


def _math_rad(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    return math.radians(_ensure_number(args[0]))


def _math_log(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 1, 2)
    value = _ensure_number(args[0])
    if len(args) == 2:
        base = _ensure_number(args[1])
        return math.log(value, base)
    return math.log(value)


def _math_exp(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    return math.exp(_ensure_number(args[0]))


def _math_modf(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    value = _ensure_number(args[0])
    integer = math.trunc(value)
    fractional = value - integer
    return LuaMultiReturn([float(integer), fractional])


def _math_random(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    count = len(args)
    if count == 0:
        return _RANDOM_GENERATOR.random()
    if count == 1:
        upper = int(_ensure_number(args[0]))
        if upper < 1:
            raise RuntimeError("interval is empty")
        return float(_RANDOM_GENERATOR.randint(1, upper))
    if count == 2:
        lower = int(_ensure_number(args[0]))
        upper = int(_ensure_number(args[1]))
        if lower > upper:
            raise RuntimeError("interval is empty")
        return float(_RANDOM_GENERATOR.randint(lower, upper))
    raise RuntimeError("wrong number of arguments")


def _math_randomseed(args: Sequence[Any], vm: Any) -> None:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    seed = int(_ensure_number(args[0]))
    _RANDOM_GENERATOR.seed(seed)
    return None


def _math_atan(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 1, 2)
    y = _ensure_number(args[0])
    if len(args) == 2:
        x = _ensure_number(args[1])
        return math.atan2(y, x)
    return math.atan(y)


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


def _string_find(args: Sequence[Any], vm: Any) -> LuaMultiReturn | None:  # noqa: ANN401
    _ensure_args(args, 2, 4)
    text = _ensure_string(args[0])
    pattern = _ensure_string(args[1])
    init = args[2] if len(args) >= 3 else None
    plain = bool(args[3]) if len(args) >= 4 and args[3] is not None else False
    start_index = _normalize_start(len(text), init)
    if start_index > len(text):
        return None
    segment = text[start_index:]
    if plain:
        position = segment.find(pattern)
        if position == -1:
            return None
        start = start_index + position + 1
        end = start + len(pattern) - 1
        return LuaMultiReturn([start, end])
    try:
        regex = _compile_lua_pattern(pattern)
    except RuntimeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(str(exc)) from exc
    match = regex.search(segment)
    if not match:
        return None
    start = start_index + match.start() + 1
    end = start_index + match.end()
    captures = [group if group is not None else None for group in match.groups()]
    return LuaMultiReturn([start, end, *captures])


def _string_match(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 2, 3)
    text = _ensure_string(args[0])
    pattern = _ensure_string(args[1])
    init = args[2] if len(args) >= 3 else None
    start_index = _normalize_start(len(text), init)
    if start_index > len(text):
        return None
    segment = text[start_index:]
    try:
        regex = _compile_lua_pattern(pattern)
    except RuntimeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(str(exc)) from exc
    match = regex.search(segment)
    if not match:
        return None
    captures = [group if group is not None else None for group in match.groups()]
    if captures:
        if len(captures) == 1:
            return captures[0]
        return LuaMultiReturn(captures)
    return match.group(0)


def _string_gsub(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 3, 4)
    text = _ensure_string(args[0])
    pattern = _ensure_string(args[1])
    replacement = args[2]
    limit = None
    if len(args) >= 4 and args[3] is not None:
        limit_value = int(_ensure_number(args[3]))
        if limit_value <= 0:
            return LuaMultiReturn([text, 0])
        limit = limit_value
    try:
        regex = _compile_lua_pattern(pattern)
    except RuntimeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(str(exc)) from exc
    result_parts: list[str] = []
    last_end = 0
    replacements = 0
    position = 0
    text_length = len(text)
    while True:
        match = regex.search(text, position)
        if not match:
            break
        if limit is not None and replacements >= limit:
            break
        start, end = match.span()
        if start == end:
            if start >= text_length:
                break
            result_parts.append(text[last_end:start + 1])
            position = start + 1
            last_end = position
            continue
        result_parts.append(text[last_end:start])
        replacement_text = _resolve_gsub_replacement(match, replacement, vm)
        result_parts.append(replacement_text)
        replacements += 1
        position = end
        last_end = end
    result_parts.append(text[last_end:])
    return LuaMultiReturn(["".join(result_parts), replacements])


def _string_format(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401, unused vm
    _ensure_args(args, 1)
    template = _ensure_string(args[0])
    values = iter(args[1:])
    output: list[str] = []
    length = len(template)
    index = 0
    while index < length:
        char = template[index]
        if char != "%":
            output.append(char)
            index += 1
            continue
        index += 1
        if index < length and template[index] == "%":
            output.append("%")
            index += 1
            continue
        flags = ""
        while index < length and template[index] in "-+ #0":
            flags += template[index]
            index += 1
        width = ""
        while index < length and template[index].isdigit():
            width += template[index]
            index += 1
        precision = ""
        if index < length and template[index] == ".":
            index += 1
            while index < length and template[index].isdigit():
                precision += template[index]
                index += 1
        if index < length and template[index] in "hlL":
            index += 1
        if index >= length:
            raise RuntimeError("incomplete format specifier")
        specifier = template[index]
        index += 1
        try:
            value = next(values)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise RuntimeError("not enough arguments for string.format") from exc
        if specifier in "diu":
            py_spec = "%" + flags + width
            if precision:
                py_spec += "." + precision
            py_spec += "d"
            formatted = py_spec % _ensure_int(value)
        elif specifier in "oOxX":
            py_spec = "%" + flags + width
            if precision:
                py_spec += "." + precision
            py_spec += specifier
            formatted = py_spec % _ensure_int(value)
        elif specifier in "eEfFgG":
            py_spec = "%" + flags + width
            if precision:
                py_spec += "." + precision
            py_spec += specifier
            formatted = py_spec % float(_ensure_number(value))
        elif specifier == "c":
            char_code = _ensure_int(value)
            text = chr(char_code)
            if width or flags:
                fmt = "%" + flags + width + "s"
                formatted = fmt % text
            else:
                formatted = text
        elif specifier == "s":
            py_spec = "%" + flags + width
            if precision:
                py_spec += "." + precision
            py_spec += "s"
            formatted = py_spec % _lua_tostring(value)
        elif specifier == "q":
            escaped = _ensure_string(value)
            escaped = (
                escaped.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            formatted = f'"{escaped}"'
        else:  # pragma: no cover - defensive
            raise RuntimeError(f"unsupported format specifier %{specifier}")
        output.append(formatted)
    return "".join(output)


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



def _table_pack(args: Sequence[Any], vm: Any) -> LuaTable:  # noqa: ANN401
    table = LuaTable()
    for index, value in enumerate(args, start=1):
        table.raw_set(index, value)
    table.raw_set("n", len(args))
    return table


def _table_unpack(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 1, 3)
    table = _ensure_table(args[0])
    start = int(_ensure_number(args[1])) if len(args) >= 2 and args[1] is not None else 1
    if len(args) >= 3 and args[2] is not None:
        stop = int(_ensure_number(args[2]))
    else:
        stop = table.lua_len()
    if stop < start:
        return LuaMultiReturn([])
    values = [table.raw_get(index) for index in range(start, stop + 1)]
    return LuaMultiReturn(values)


def _table_move(args: Sequence[Any], vm: Any) -> LuaTable:  # noqa: ANN401
    _ensure_args(args, 4, 5)
    source = _ensure_table(args[0])
    start = int(_ensure_number(args[1]))
    finish = int(_ensure_number(args[2]))
    dest_index = int(_ensure_number(args[3]))
    destination = source
    if len(args) == 5 and args[4] is not None:
        destination = _ensure_table(args[4])
    count = finish - start + 1
    if count <= 0:
        return destination
    if destination is source and dest_index > start and dest_index <= start + count - 1:
        for offset in range(count - 1, -1, -1):
            value = source.raw_get(start + offset)
            destination.raw_set(dest_index + offset, value)
    else:
        for offset in range(count):
            value = source.raw_get(start + offset)
            destination.raw_set(dest_index + offset, value)
    return destination


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



def _os_clock(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 0, 0)
    return time.process_time()


def _os_time(args: Sequence[Any], vm: Any) -> int:  # noqa: ANN401
    _ensure_args(args, 0, 1)
    if not args:
        return int(time.time())
    table = _ensure_table(args[0])
    year = _ensure_int(table.raw_get("year"))
    month = _ensure_int(table.raw_get("month"))
    day = _ensure_int(table.raw_get("day"))
    hour_value = table.raw_get("hour")
    minute_value = table.raw_get("min")
    second_value = table.raw_get("sec")
    isdst_value = table.raw_get("isdst")
    hour = _ensure_int(hour_value) if hour_value is not None else 12
    minute = _ensure_int(minute_value) if minute_value is not None else 0
    second = _ensure_int(second_value) if second_value is not None else 0
    isdst = -1
    if isdst_value is not None:
        isdst = 1 if _is_lua_truthy(isdst_value) else 0
    tm_tuple = (year, month, day, hour, minute, second, 0, 0, isdst)
    return int(time.mktime(tm_tuple))


def _os_date(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 0, 2)
    format_string = "%c"
    timestamp = None
    if args:
        if args[0] is not None:
            format_string = _ensure_string(args[0])
    if len(args) >= 2 and args[1] is not None:
        timestamp = float(_ensure_number(args[1]))
    if timestamp is None:
        timestamp = time.time()
    use_utc = False
    if format_string.startswith("!"):
        use_utc = True
        format_string = format_string[1:]
    struct = time.gmtime(timestamp) if use_utc else time.localtime(timestamp)
    if format_string == "*t":
        table = LuaTable()
        table.raw_set("year", struct.tm_year)
        table.raw_set("month", struct.tm_mon)
        table.raw_set("day", struct.tm_mday)
        table.raw_set("hour", struct.tm_hour)
        table.raw_set("min", struct.tm_min)
        table.raw_set("sec", struct.tm_sec)
        table.raw_set("wday", struct.tm_wday + 1)
        table.raw_set("yday", struct.tm_yday)
        table.raw_set("isdst", struct.tm_isdst > 0)
        return table
    if not format_string:
        format_string = "%c"
    try:
        return time.strftime(format_string, struct)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def _os_difftime(args: Sequence[Any], vm: Any) -> float:  # noqa: ANN401
    _ensure_args(args, 1, 2)
    later = _ensure_number(args[0])
    earlier = _ensure_number(args[1]) if len(args) == 2 else 0.0
    return float(later - earlier)


def _io_write_callable(default_stream: LuaTable):
    def _io_write(args: Sequence[Any], vm: Any):  # noqa: ANN401
        stream = default_stream
        values = args
        if values and isinstance(values[0], LuaTable) and values[0].raw_get(IO_STREAM_MARKER):
            stream = values[0]
            values = values[1:]
        text = "".join(_lua_tostring(value) for value in values)
        if text:
            vm.output.append(text)
        return stream


    return _io_write


def _io_flush(args: Sequence[Any], vm: Any):  # noqa: ANN401
    stream = args[0] if args else None
    if isinstance(stream, LuaTable) and stream.raw_get(IO_STREAM_MARKER):
        return stream
    return True


def _io_type(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 1, 1)
    value = args[0]
    if isinstance(value, LuaTable) and value.raw_get(IO_STREAM_MARKER):
        return "file"
    return None


def _io_read_disabled(args: Sequence[Any], vm: Any):  # noqa: ANN401
    raise RuntimeError("io.read is not available in this environment")


def _debug_traceback(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401
    arg_index = 0
    if args and isinstance(args[0], LuaCoroutine):
        raise RuntimeError("debug.traceback does not support thread arguments yet")
    message = ""
    level = 1
    if arg_index < len(args) and args[arg_index] is not None:
        message = _lua_tostring(args[arg_index])
        arg_index += 1
    if arg_index < len(args):
        level = int(_ensure_number(args[arg_index]))
    frames = vm.snapshot_state().call_stack
    skip = max(level - 1, 0)
    if skip:
        frames = frames[skip:]
    trace = format_traceback(frames)
    if message:
        return f"{message}\n{trace}"
    return trace


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

    os_members = {
        "clock": BuiltinFunction("os.clock", _os_clock),
        "time": BuiltinFunction("os.time", _os_time),
        "date": BuiltinFunction("os.date", _os_date),
        "difftime": BuiltinFunction("os.difftime", _os_difftime),
    }

    stdout_stream = LuaTable()
    stdout_stream.raw_set(IO_STREAM_MARKER, True)
    stderr_stream = LuaTable()
    stderr_stream.raw_set(IO_STREAM_MARKER, True)
    stdout_write_callable = _io_write_callable(stdout_stream)
    stderr_write_callable = _io_write_callable(stderr_stream)
    io_write_builtin = BuiltinFunction("io.write", stdout_write_callable)
    stdout_stream.raw_set("write", BuiltinFunction("io.stdout.write", stdout_write_callable))
    stdout_stream.raw_set("flush", BuiltinFunction("io.stdout.flush", _io_flush))
    stderr_stream.raw_set("write", BuiltinFunction("io.stderr.write", stderr_write_callable))
    stderr_stream.raw_set("flush", BuiltinFunction("io.stderr.flush", _io_flush))
    io_members = {
        "write": io_write_builtin,
        "flush": BuiltinFunction("io.flush", _io_flush),
        "type": BuiltinFunction("io.type", _io_type),
        "read": BuiltinFunction("io.read", _io_read_disabled),
        "stdout": stdout_stream,
        "stderr": stderr_stream,
    }

    debug_members = {
        "traceback": BuiltinFunction("debug.traceback", _debug_traceback),
    }

    math_members = {
        "abs": BuiltinFunction("math.abs", _math_unary(lambda x: abs(x))),
        "sqrt": BuiltinFunction("math.sqrt", _math_unary(lambda x: math.sqrt(x))),
        "floor": BuiltinFunction("math.floor", _math_unary(lambda x: math.floor(x))),
        "ceil": BuiltinFunction("math.ceil", _math_unary(lambda x: math.ceil(x))),
        "min": BuiltinFunction("math.min", _math_min),
        "max": BuiltinFunction("math.max", _math_max),
        "sin": BuiltinFunction("math.sin", _math_unary(lambda x: math.sin(x))),
        "cos": BuiltinFunction("math.cos", _math_unary(lambda x: math.cos(x))),
        "tan": BuiltinFunction("math.tan", _math_unary(lambda x: math.tan(x))),
        "asin": BuiltinFunction("math.asin", _math_unary(lambda x: math.asin(x))),
        "acos": BuiltinFunction("math.acos", _math_unary(lambda x: math.acos(x))),
        "atan": BuiltinFunction("math.atan", _math_atan),
        "deg": BuiltinFunction("math.deg", _math_deg),
        "rad": BuiltinFunction("math.rad", _math_rad),
        "exp": BuiltinFunction("math.exp", _math_exp),
        "log": BuiltinFunction("math.log", _math_log),
        "modf": BuiltinFunction("math.modf", _math_modf),
        "random": BuiltinFunction("math.random", _math_random),
        "randomseed": BuiltinFunction("math.randomseed", _math_randomseed),
        "pi": math.pi,
        "huge": float("inf"),
    }
    env.register_library("math", math_members)

    table_members = {
        "insert": BuiltinFunction("table.insert", _table_insert),
        "remove": BuiltinFunction("table.remove", _table_remove),
        "concat": BuiltinFunction("table.concat", _table_concat),
        "sort": BuiltinFunction("table.sort", _table_sort),
        "pack": BuiltinFunction("table.pack", _table_pack),
        "unpack": BuiltinFunction("table.unpack", _table_unpack),
        "move": BuiltinFunction("table.move", _table_move),
    }
    env.register_library("table", table_members)

    string_members = {
        "len": BuiltinFunction("string.len", _string_len),
        "sub": BuiltinFunction("string.sub", _string_sub),
        "upper": BuiltinFunction("string.upper", _string_upper),
        "lower": BuiltinFunction("string.lower", _string_lower),
        "find": BuiltinFunction("string.find", _string_find),
        "match": BuiltinFunction("string.match", _string_match),
        "gsub": BuiltinFunction("string.gsub", _string_gsub),
        "format": BuiltinFunction("string.format", _string_format),
    }
    env.register_library("string", string_members)
    env.register_library("os", os_members)
    env.register_library("io", io_members)
    env.register_library("debug", debug_members)

    coroutine_members = {
        "create": BuiltinFunction("coroutine.create", _coroutine_create),
        "resume": BuiltinFunction("coroutine.resume", _coroutine_resume),
        "yield": BuiltinFunction("coroutine.yield", _coroutine_yield),
    }
    env.register_library("coroutine", coroutine_members)

    module_system = getattr(env, "module_system", None)
    if not isinstance(module_system, LuaModuleSystem):
        module_system = LuaModuleSystem(env)
    module_system.attach_environment(env)
    env.mark_stdlib_ready()

    return env


def create_default_environment() -> LuaEnvironment:
    env = LuaEnvironment()
    install_core_stdlib(env)
    return env


__all__ = ["create_default_environment", "install_core_stdlib"]
