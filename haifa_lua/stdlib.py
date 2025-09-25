from __future__ import annotations

import math
import os
import pathlib
import random
import re
import subprocess
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Iterator, Sequence

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


@dataclass(frozen=True)
class _BalancedGroup:
    name: str
    open_char: str
    close_char: str


@dataclass(frozen=True)
class _CompiledLuaPattern:
    regex: re.Pattern[str]
    balanced_groups: tuple[_BalancedGroup, ...]
    internal_group_indices: tuple[int, ...]


def _translate_lua_pattern(pattern: str) -> tuple[str, tuple[_BalancedGroup, ...]]:
    result: list[str] = []
    balanced: list[_BalancedGroup] = []
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
                if i + 2 >= length:
                    raise RuntimeError("pattern %b expects two delimiter characters")
                open_char = pattern[i + 1]
                close_char = pattern[i + 2]
                group_name = f"_bal_{len(balanced)}"
                piece = f"(?P<{group_name}>{re.escape(open_char)}.*?{re.escape(close_char)})"
                result.append(piece)
                balanced.append(_BalancedGroup(group_name, open_char, close_char))
                i += 2
            elif code == "f":
                if i + 1 >= length or pattern[i + 1] != "[":
                    raise RuntimeError("pattern %f expects frontier set")
                j = i + 2
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
                        mapped = _LUA_CLASS_SET_MAP.get(pattern[j])
                        if mapped is None:
                            mapped = _LUA_PATTERN_CLASS_MAP.get(pattern[j])
                            if mapped is None:
                                mapped = re.escape(pattern[j])
                            elif mapped.startswith("[") and mapped.endswith("]"):
                                mapped = mapped[1:-1]
                            else:
                                if mapped.startswith("[^"):
                                    raise RuntimeError("unsupported frontier complement")
                        parts.append(mapped)
                    else:
                        parts.append(re.escape(current))
                    j += 1
                if j >= length:
                    raise RuntimeError("unterminated frontier pattern")
                content = "".join(parts)
                if not content:
                    content = r"\s\S"
                prefix = "^" if negate else ""
                set_expr = f"[{prefix}{content}]"
                result.append(f"(?:(?<!{set_expr})(?={set_expr}))")
                i = j
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
    return "".join(result), tuple(balanced)


def _build_internal_indices(regex: re.Pattern[str], balanced: tuple[_BalancedGroup, ...]) -> tuple[int, ...]:
    groupindex = regex.groupindex
    indices: list[int] = []
    for group in balanced:
        index = groupindex.get(group.name)
        if index is not None:
            indices.append(index)
    return tuple(sorted(indices))


@lru_cache(maxsize=128)
def _compile_lua_pattern(pattern: str) -> _CompiledLuaPattern:
    translated, balanced = _translate_lua_pattern(pattern)
    regex = re.compile(translated)
    internal_indices = _build_internal_indices(regex, balanced)
    return _CompiledLuaPattern(regex=regex, balanced_groups=balanced, internal_group_indices=internal_indices)


def _is_balanced_text(text: str, open_char: str, close_char: str) -> bool:
    if not text or text[0] != open_char or text[-1] != close_char:
        return False
    depth = 0
    for character in text:
        if character == open_char:
            depth += 1
        elif character == close_char:
            depth -= 1
            if depth < 0:
                return False
        if depth == 0 and character != text[-1]:
            continue
    return depth == 0


def _match_satisfies_balanced(match: re.Match[str], compiled: _CompiledLuaPattern) -> bool:
    for group in compiled.balanced_groups:
        value = match.group(group.name)
        if value is None or not _is_balanced_text(value, group.open_char, group.close_char):
            return False
    return True


def _next_lua_match(compiled: _CompiledLuaPattern, text: str, position: int) -> re.Match[str] | None:
    regex = compiled.regex
    search_pos = position
    text_length = len(text)
    while search_pos <= text_length:
        match = regex.search(text, search_pos)
        if match is None:
            return None
        if _match_satisfies_balanced(match, compiled):
            return match
        new_pos = match.start() + 1
        if new_pos <= search_pos:
            new_pos = search_pos + 1
        search_pos = new_pos
    return None


def _extract_lua_captures(match: re.Match[str], compiled: _CompiledLuaPattern) -> list[Any]:
    values: list[Any] = []
    total = match.re.groups
    internal = set(compiled.internal_group_indices)
    for index in range(1, total + 1):
        if index in internal:
            continue
        values.append(match.group(index))
    return values


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


def _collect_match_groups(match: re.Match[str], compiled: _CompiledLuaPattern) -> list[Any]:
    captures = _extract_lua_captures(match, compiled)
    if captures:
        return [capture if capture is not None else None for capture in captures]
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


def _resolve_gsub_replacement(
    match: re.Match[str], compiled: _CompiledLuaPattern, repl: Any, vm: Any
) -> str:  # noqa: ANN401
    if isinstance(repl, str):
        return _expand_replacement(repl, match)
    if isinstance(repl, LuaTable):
        captures = _extract_lua_captures(match, compiled)
        key = captures[0] if captures else match.group(0)
        value = repl.raw_get(key)
        if value is None:
            return match.group(0)
        return _match_replacement_value(value)
    values = vm.call_callable(repl, _collect_match_groups(match, compiled))
    if not values:
        return match.group(0)
    replacement = values[0]
    if replacement is None:
        return match.group(0)
    return _match_replacement_value(replacement)


_RANDOM_GENERATOR = random.Random()
IO_STREAM_MARKER = "__lua_io_stream__"
_FILE_OBJECT_KEY = object()
_STREAM_KIND_KEY = object()
_DEFAULT_INPUT_STREAM: LuaTable | None = None
_DEFAULT_OUTPUT_STREAM: LuaTable | None = None


def _ensure_stream(value: Any) -> LuaTable:
    table = _ensure_table(value)
    if not table.raw_get(IO_STREAM_MARKER):
        raise RuntimeError("expected file")
    return table


def _stream_file_object(stream: LuaTable):
    return stream.raw_get(_FILE_OBJECT_KEY)


def _stream_kind(stream: LuaTable) -> str:
    kind = stream.raw_get(_STREAM_KIND_KEY)
    return str(kind) if kind else "file"


def _stream_is_closed(stream: LuaTable) -> bool:
    return _stream_kind(stream) == "closed"


def _mark_stream(stream: LuaTable, *, file_obj, kind: str) -> None:
    stream.raw_set(_FILE_OBJECT_KEY, file_obj)
    stream.raw_set(_STREAM_KIND_KEY, kind)


def _stream_close(stream: LuaTable) -> bool:
    kind = _stream_kind(stream)
    if kind in {"stdout", "stderr"}:
        return True
    file_obj = _stream_file_object(stream)
    if file_obj is not None:
        try:
            file_obj.close()
        except Exception:  # pragma: no cover - defensive
            pass
    _mark_stream(stream, file_obj=None, kind="closed")
    return True


def _stream_flush(stream: LuaTable) -> bool:
    file_obj = _stream_file_object(stream)
    if file_obj is not None:
        try:
            file_obj.flush()
        except Exception:  # pragma: no cover - defensive
            pass
        return True
    return _stream_kind(stream) in {"stdout", "stderr"}


def _translate_file_mode(mode: str | None) -> str:
    if not mode:
        return "r"
    cleaned = mode.replace("t", "")
    if "b" in cleaned:
        raise RuntimeError("binary file mode is not supported")
    allowed = {"r", "w", "a", "r+", "w+", "a+"}
    if cleaned not in allowed:
        raise RuntimeError("invalid file mode")
    return cleaned


def _open_file(filename: str, mode: str) -> Any:
    path = pathlib.Path(filename)
    translated = _translate_file_mode(mode)
    encoding = "utf-8"
    return path.open(translated, encoding=encoding)


def _create_stream_from_file(file_obj, *, kind: str = "file") -> LuaTable:
    stream = LuaTable()
    stream.raw_set(IO_STREAM_MARKER, True)
    _mark_stream(stream, file_obj=file_obj, kind=kind)
    return stream


def _write_to_stream(stream: LuaTable, text: str, vm: Any) -> None:  # noqa: ANN401
    file_obj = _stream_file_object(stream)
    if file_obj is None:
        if text:
            vm.output.append(text)
        return
    file_obj.write(text)


def _parse_read_modes(args: Sequence[Any]) -> list[Any]:
    if args and isinstance(args[0], LuaTable) and args[0].raw_get(IO_STREAM_MARKER):
        args = args[1:]
    if not args:
        return ["*l"]
    modes: list[Any] = []
    for value in args:
        if value is None:
            modes.append("*l")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            modes.append(int(value))
        elif isinstance(value, str):
            modes.append(value)
        else:
            modes.append(int(_ensure_number(value)))
    return modes


_NUMBER_PATTERN = re.compile(r"^[\s\u00a0]*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")


def _read_number(file_obj):
    start = file_obj.tell()
    data = file_obj.read()
    if not data:
        file_obj.seek(start)
        return None
    match = _NUMBER_PATTERN.match(data)
    if not match:
        file_obj.seek(start)
        return None
    text = match.group(1)
    file_obj.seek(start + match.end())
    try:
        return float(text)
    except ValueError:
        return None


def _read_mode(file_obj, mode) -> Any:
    if isinstance(mode, int):
        if mode <= 0:
            return ""
        data = file_obj.read(mode)
        return data if data != "" else None
    if mode == "*a":
        data = file_obj.read()
        return data if data != "" else ""
    if mode == "*l":
        line = file_obj.readline()
        if line == "":
            return None
        return line.rstrip("\r\n")
    if mode == "*L":
        line = file_obj.readline()
        if line == "":
            return None
        return line
    if mode == "*n":
        return _read_number(file_obj)
    raise RuntimeError("unsupported read mode")


def _stream_read(stream: LuaTable, modes: Sequence[Any]) -> list[Any]:
    if _stream_is_closed(stream):
        raise RuntimeError("attempt to use a closed file")
    file_obj = _stream_file_object(stream)
    if file_obj is None:
        raise RuntimeError("file is not readable")
    results: list[Any] = []
    for mode in modes:
        value = _read_mode(file_obj, mode)
        if value is None:
            if not results:
                return [None]
            break
        results.append(value)
    return results


def _stream_seek(stream: LuaTable, whence: str | None, offset: Any | None) -> int:
    if _stream_is_closed(stream):
        raise RuntimeError("attempt to use a closed file")
    file_obj = _stream_file_object(stream)
    if file_obj is None:
        raise RuntimeError("file is not seekable")
    whence_map = {"set": 0, "cur": 1, "end": 2}
    mode = 0
    if whence is not None:
        key = str(whence)
        if key not in whence_map:
            raise RuntimeError("invalid seek mode")
        mode = whence_map[key]
    offset_value = int(_ensure_number(offset)) if offset is not None else 0
    file_obj.seek(offset_value, mode)
    return file_obj.tell() + 1


def _stream_lines_callable(
    stream: LuaTable,
    *,
    close_after: bool,
    modes: Sequence[Any] | None = None,
) -> BuiltinFunction:
    state = {"closed": False}
    parsed_modes = _parse_read_modes(modes) if modes is not None else None

    def _iterator(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
        if state["closed"] or _stream_is_closed(stream):
            return LuaMultiReturn([])
        file_obj = _stream_file_object(stream)
        if file_obj is None:
            state["closed"] = True
            return LuaMultiReturn([])
        if parsed_modes is None:
            line = file_obj.readline()
            if line == "":
                if close_after:
                    _stream_close(stream)
                state["closed"] = True
                return LuaMultiReturn([])
            return LuaMultiReturn([line.rstrip("\r\n")])
        values = _stream_read(stream, parsed_modes)
        if values and values[0] is None:
            if close_after:
                _stream_close(stream)
            state["closed"] = True
            return LuaMultiReturn([])
        return LuaMultiReturn(values)

    return BuiltinFunction("io.lines.iterator", _iterator)


def _file_read_callable(stream: LuaTable):
    def _read(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
        params = args
        if params and params[0] is stream:
            params = params[1:]
        modes = _parse_read_modes(params)
        values = _stream_read(stream, modes)
        return LuaMultiReturn(values)

    return _read


def _file_write_callable(stream: LuaTable):
    def _write(args: Sequence[Any], vm: Any):  # noqa: ANN401
        values = args
        if values and values[0] is stream:
            values = values[1:]
        text = "".join(_lua_tostring(value) for value in values)
        _write_to_stream(stream, text, vm)
        return stream

    return _write


def _file_flush_callable(stream: LuaTable):
    def _flush(args: Sequence[Any], vm: Any):  # noqa: ANN401
        if args and args[0] is stream:
            args = args[1:]
        _stream_flush(stream)
        return stream

    return _flush


def _file_close_callable(stream: LuaTable):
    def _close(args: Sequence[Any], vm: Any):  # noqa: ANN401
        if args and args[0] is stream:
            args = args[1:]
        _stream_close(stream)
        return True

    return _close


def _file_seek_callable(stream: LuaTable):
    def _seek(args: Sequence[Any], vm: Any):  # noqa: ANN401
        params = args
        if params and params[0] is stream:
            params = params[1:]
        whence = params[0] if params else None
        offset = params[1] if len(params) >= 2 else None
        return _stream_seek(stream, whence if whence is not None else "cur", offset)

    return _seek


def _prepare_file_stream(stream: LuaTable) -> LuaTable:
    stream.raw_set("read", BuiltinFunction("file.read", _file_read_callable(stream)))
    stream.raw_set("write", BuiltinFunction("file.write", _file_write_callable(stream)))
    stream.raw_set("flush", BuiltinFunction("file.flush", _file_flush_callable(stream)))
    stream.raw_set("close", BuiltinFunction("file.close", _file_close_callable(stream)))
    stream.raw_set("seek", BuiltinFunction("file.seek", _file_seek_callable(stream)))
    stream.raw_set(
        "lines",
        BuiltinFunction(
            "file.lines",
            lambda args, vm: _stream_lines_callable(
                stream,
                close_after=False,
                modes=_parse_read_modes(args[1:] if args and args[0] is stream else args),
            ),
        ),
    )
    return stream


def _io_open(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 1, 2)
    filename = _ensure_string(args[0])
    mode = _ensure_string(args[1]) if len(args) >= 2 and args[1] is not None else "r"
    file_obj = _open_file(filename, mode)
    stream = _prepare_file_stream(_create_stream_from_file(file_obj))
    return stream


def _io_close(args: Sequence[Any], vm: Any):  # noqa: ANN401
    global _DEFAULT_OUTPUT_STREAM
    if args:
        stream = _ensure_stream(args[0])
    else:
        if _DEFAULT_OUTPUT_STREAM is None:
            return True
        stream = _DEFAULT_OUTPUT_STREAM
    result = _stream_close(stream)
    return result


def _io_flush(args: Sequence[Any], vm: Any):  # noqa: ANN401
    global _DEFAULT_OUTPUT_STREAM
    if args and args[0] is not None:
        stream = _ensure_stream(args[0])
    else:
        if _DEFAULT_OUTPUT_STREAM is None:
            return True
        stream = _DEFAULT_OUTPUT_STREAM
    _stream_flush(stream)
    return stream


def _io_type(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 1, 1)
    value = args[0]
    if isinstance(value, LuaTable) and value.raw_get(IO_STREAM_MARKER):
        stream = _ensure_stream(value)
        if _stream_is_closed(stream):
            return "closed file"
        return "file"
    return None


def _io_read(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    global _DEFAULT_INPUT_STREAM
    stream = None
    values = args
    if values and isinstance(values[0], LuaTable) and values[0].raw_get(IO_STREAM_MARKER):
        stream = _ensure_stream(values[0])
        values = values[1:]
    if stream is None:
        if _DEFAULT_INPUT_STREAM is None:
            raise RuntimeError("no default input stream")
        stream = _DEFAULT_INPUT_STREAM
    modes = _parse_read_modes(values)
    results = _stream_read(stream, modes)
    return LuaMultiReturn(results)


def _io_input(args: Sequence[Any], vm: Any):  # noqa: ANN401
    global _DEFAULT_INPUT_STREAM
    if not args or args[0] is None:
        if _DEFAULT_INPUT_STREAM is None:
            raise RuntimeError("no default input stream")
        return _DEFAULT_INPUT_STREAM
    target = args[0]
    if isinstance(target, str):
        stream = _prepare_file_stream(_create_stream_from_file(_open_file(target, "r")))
    else:
        stream = _ensure_stream(target)
    _DEFAULT_INPUT_STREAM = stream
    return stream


def _io_output(args: Sequence[Any], vm: Any):  # noqa: ANN401
    global _DEFAULT_OUTPUT_STREAM
    if not args or args[0] is None:
        if _DEFAULT_OUTPUT_STREAM is None:
            raise RuntimeError("no default output stream")
        return _DEFAULT_OUTPUT_STREAM
    target = args[0]
    if isinstance(target, str):
        stream = _prepare_file_stream(_create_stream_from_file(_open_file(target, "w")))
    else:
        stream = _ensure_stream(target)
    _DEFAULT_OUTPUT_STREAM = stream
    return stream


def _io_lines(args: Sequence[Any], vm: Any):  # noqa: ANN401
    global _DEFAULT_INPUT_STREAM
    if not args:
        if _DEFAULT_INPUT_STREAM is None:
            raise RuntimeError("no default input stream")
        return _stream_lines_callable(_DEFAULT_INPUT_STREAM, close_after=False, modes=None)
    target = args[0]
    modes = _parse_read_modes(args[1:]) if len(args) > 1 else None
    if isinstance(target, str):
        stream = _prepare_file_stream(_create_stream_from_file(_open_file(target, "r")))
        return _stream_lines_callable(stream, close_after=True, modes=modes)
    stream = _ensure_stream(target)
    return _stream_lines_callable(stream, close_after=False, modes=modes)


def _collect_debug_frames(thread: LuaCoroutine | None, vm: Any) -> list:  # noqa: ANN401
    if thread is None:
        return list(vm.snapshot_state().call_stack)
    coroutine = thread
    if coroutine.is_main:
        return list(coroutine.base_vm.snapshot_state().call_stack)
    coroutine_vm = coroutine.vm
    if coroutine_vm is vm:
        return list(vm.snapshot_state().call_stack)
    if coroutine_vm is not None:
        try:
            return list(coroutine_vm.snapshot_state().call_stack)
        except Exception:  # pragma: no cover - defensive
            pass
    snapshot = coroutine.base_vm.get_coroutine_snapshot(coroutine.coroutine_id)
    if snapshot is not None:
        return list(snapshot.call_stack)
    return []


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
    if plain:
        segment = text[start_index:]
        position = segment.find(pattern)
        if position == -1:
            return None
        start = start_index + position + 1
        end = start + len(pattern) - 1
        return LuaMultiReturn([start, end])
    compiled = _compile_lua_pattern(pattern)
    match = _next_lua_match(compiled, text, start_index)
    if not match:
        return None
    start = match.start() + 1
    end = match.end()
    captures = [value if value is not None else None for value in _extract_lua_captures(match, compiled)]
    return LuaMultiReturn([start, end, *captures])


def _string_match(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 2, 3)
    text = _ensure_string(args[0])
    pattern = _ensure_string(args[1])
    init = args[2] if len(args) >= 3 else None
    start_index = _normalize_start(len(text), init)
    if start_index > len(text):
        return None
    compiled = _compile_lua_pattern(pattern)
    match = _next_lua_match(compiled, text, start_index)
    if not match:
        return None
    captures = [value if value is not None else None for value in _extract_lua_captures(match, compiled)]
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
    compiled = _compile_lua_pattern(pattern)
    result_parts: list[str] = []
    last_end = 0
    replacements = 0
    position = 0
    text_length = len(text)
    while True:
        if limit is not None and replacements >= limit:
            break
        match = _next_lua_match(compiled, text, position)
        if not match:
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
        replacement_text = _resolve_gsub_replacement(match, compiled, replacement, vm)
        result_parts.append(replacement_text)
        replacements += 1
        position = end
        last_end = end
    result_parts.append(text[last_end:])
    return LuaMultiReturn(["".join(result_parts), replacements])


def _string_gmatch(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 2, 2)
    text = _ensure_string(args[0])
    pattern = _ensure_string(args[1])
    compiled = _compile_lua_pattern(pattern)
    position = 0
    text_length = len(text)

    def _iterator(iterator_args: Sequence[Any], iterator_vm: Any) -> LuaMultiReturn:  # noqa: ANN401
        nonlocal position
        match = _next_lua_match(compiled, text, position)
        if not match:
            position = text_length + 1
            return LuaMultiReturn([])
        start, end = match.span()
        if end == start:
            position = end + 1
        else:
            position = end
        captures = [value if value is not None else None for value in _extract_lua_captures(match, compiled)]
        if captures:
            return LuaMultiReturn(captures)
        return LuaMultiReturn([match.group(0)])

    return BuiltinFunction("string.gmatch.iterator", _iterator)


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


def _ensure_coroutine(value: Any, *, allow_main: bool = False) -> LuaCoroutine:
    if isinstance(value, LuaCoroutine):
        if value.is_main and not allow_main:
            raise RuntimeError("expected coroutine")
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


def _coroutine_status(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401
    _ensure_args(args, 1, 1)
    coroutine = _ensure_coroutine(args[0], allow_main=True)
    return coroutine.status_string()


def _coroutine_wrap(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 1, 1)
    try:
        coroutine = LuaCoroutine(args[0], vm)
    except CoroutineError as exc:
        raise RuntimeError(str(exc)) from exc

    def _wrapped(*values):
        result = coroutine.resume(values)
        if not result.success:
            message = result.values[0] if result.values else ""
            raise RuntimeError(message)
        count = len(result.values)
        if count == 0:
            return None
        if count == 1:
            return result.values[0]
        return LuaMultiReturn(result.values)

    return _wrapped


def _coroutine_running(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    _ensure_args(args, 0, 0)
    current = getattr(vm, "current_coroutine", None)
    if current is None:
        main = getattr(vm, "main_coroutine", None)
        if not isinstance(main, LuaCoroutine):
            main = LuaCoroutine(None, vm, is_main=True)
            vm.main_coroutine = main
        return LuaMultiReturn([main, True])
    return LuaMultiReturn([current, False])


def _coroutine_isyieldable(args: Sequence[Any], vm: Any) -> bool:  # noqa: ANN401
    _ensure_args(args, 0, 0)
    current = getattr(vm, "current_coroutine", None)
    if not isinstance(current, LuaCoroutine):
        return False
    if current.status != "running":
        return False
    inner_vm = current.vm if current.vm is not None else vm
    depth = getattr(inner_vm, "_non_yieldable_depth", 0)
    if depth > 0:
        depth -= 1
    return depth == 0



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


def _os_remove(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 1, 1)
    path = pathlib.Path(_ensure_string(args[0]))
    try:
        path.unlink()
        return True
    except IsADirectoryError:
        path.rmdir()
        return True
    except FileNotFoundError:
        return None


def _os_rename(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 2, 2)
    source = pathlib.Path(_ensure_string(args[0]))
    target = pathlib.Path(_ensure_string(args[1]))
    try:
        source.replace(target)
        return True
    except FileNotFoundError:
        return None


def _os_getenv(args: Sequence[Any], vm: Any):  # noqa: ANN401
    _ensure_args(args, 1, 1)
    name = _ensure_string(args[0])
    return os.environ.get(name)


def _os_execute(args: Sequence[Any], vm: Any) -> LuaMultiReturn:  # noqa: ANN401
    command = None
    if args and args[0] is not None:
        command = _ensure_string(args[0])
    if not command:
        return LuaMultiReturn([True, "exit", 0])
    try:
        result = subprocess.run(command, shell=True, check=False)
        code = result.returncode
    except Exception:  # pragma: no cover - defensive
        return LuaMultiReturn([False, "exit", 1])
    return LuaMultiReturn([code == 0, "exit", code])


def _io_write_callable(default_stream: LuaTable):
    def _io_write(args: Sequence[Any], vm: Any):  # noqa: ANN401
        stream = default_stream
        values = args
        if values and isinstance(values[0], LuaTable) and values[0].raw_get(IO_STREAM_MARKER):
            stream = _ensure_stream(values[0])
            values = values[1:]
        text = "".join(_lua_tostring(value) for value in values)
        _write_to_stream(stream, text, vm)
        return stream


    return _io_write


def _debug_traceback(args: Sequence[Any], vm: Any) -> str:  # noqa: ANN401
    arg_index = 0
    thread: LuaCoroutine | None = None
    if args and isinstance(args[0], LuaCoroutine):
        thread = _ensure_coroutine(args[0], allow_main=True)
        arg_index = 1
    message = ""
    if arg_index < len(args) and args[arg_index] is not None:
        message = _lua_tostring(args[arg_index])
        arg_index += 1
    level = 1
    if arg_index < len(args) and args[arg_index] is not None:
        level = int(_ensure_number(args[arg_index]))

    frames = _collect_debug_frames(thread, vm)
    skip = max(level - 1, 0)
    if skip:
        frames = frames[skip:]
    trace = format_traceback(frames)
    if message:
        return f"{message}\n{trace}"
    return trace


def _populate_info_from_frame(info: LuaTable, frame, what: str) -> None:
    if "S" in what:
        source = frame.file or "?"
        if source != "<unknown>" and not source.startswith("@"):  # match Lua-style prefix
            info.raw_set("source", f"@{source}")
        else:
            info.raw_set("source", source)
        short_src = source[1:] if source.startswith("@") else source
        info.raw_set("short_src", pathlib.Path(short_src).name if short_src else short_src)
        info.raw_set("what", "Lua")
        info.raw_set("linedefined", frame.line)
        info.raw_set("lastlinedefined", frame.line)
    if "l" in what:
        info.raw_set("currentline", frame.line)
    if "n" in what:
        name = frame.function_name or ""
        info.raw_set("name", name)
        info.raw_set("namewhat", "")
    if "u" in what:
        info.raw_set("nups", 0)
        info.raw_set("nparams", 0)
        info.raw_set("isvararg", False)


def _debug_getinfo(args: Sequence[Any], vm: Any):  # noqa: ANN401
    arg_index = 0
    thread: LuaCoroutine | None = None
    if args and isinstance(args[0], LuaCoroutine):
        thread = _ensure_coroutine(args[0], allow_main=True)
        arg_index = 1
    if arg_index >= len(args):
        raise RuntimeError("debug.getinfo expects function or level")
    target = args[arg_index]
    arg_index += 1
    what = "nSluf"
    if arg_index < len(args) and args[arg_index] is not None:
        what = _ensure_string(args[arg_index])

    info = LuaTable()
    if isinstance(target, (int, float)) and not isinstance(target, bool):
        level = int(target)
        if level < 0:
            raise RuntimeError("level out of range")
        frames = _collect_debug_frames(thread, vm)
        if level >= len(frames):
            return None
        frame = frames[level]
        _populate_info_from_frame(info, frame, what)
        if "f" in what:
            info.raw_set("func", None)
        return info

    if isinstance(target, dict) and "label" in target:
        info.raw_set("what", "Lua")
        name = target.get("debug_name", target.get("label", "?"))
        info.raw_set("source", name)
        info.raw_set("short_src", name)
        info.raw_set("linedefined", 0)
        info.raw_set("lastlinedefined", 0)
        if "n" in what:
            info.raw_set("name", name)
            info.raw_set("namewhat", "")
        if "l" in what:
            info.raw_set("currentline", 0)
        if "u" in what:
            info.raw_set("nups", len(target.get("upvalues", [])))
            info.raw_set("nparams", 0)
            info.raw_set("isvararg", False)
        if "f" in what:
            info.raw_set("func", target)
        return info

    if getattr(target, "__lua_builtin__", False) or callable(target):
        info.raw_set("what", "C")
        if "n" in what:
            info.raw_set("name", getattr(target, "__name__", ""))
            info.raw_set("namewhat", "")
        if "S" in what:
            info.raw_set("source", "=[C]")
            info.raw_set("short_src", "[C]")
            info.raw_set("linedefined", 0)
            info.raw_set("lastlinedefined", 0)
        if "l" in what:
            info.raw_set("currentline", -1)
        if "u" in what:
            info.raw_set("nups", 0)
            info.raw_set("nparams", 0)
            info.raw_set("isvararg", False)
        if "f" in what:
            info.raw_set("func", target)
        return info

    raise RuntimeError("invalid option to debug.getinfo")
def install_core_stdlib(env: LuaEnvironment) -> LuaEnvironment:
    global _DEFAULT_OUTPUT_STREAM, _DEFAULT_INPUT_STREAM
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
        "remove": BuiltinFunction("os.remove", _os_remove),
        "rename": BuiltinFunction("os.rename", _os_rename),
        "getenv": BuiltinFunction("os.getenv", _os_getenv),
        "execute": BuiltinFunction("os.execute", _os_execute),
    }

    stdout_stream = _prepare_file_stream(_create_stream_from_file(None, kind="stdout"))
    stderr_stream = _prepare_file_stream(_create_stream_from_file(None, kind="stderr"))
    stdout_write_callable = _io_write_callable(stdout_stream)
    stderr_write_callable = _io_write_callable(stderr_stream)
    stdout_stream.raw_set("write", BuiltinFunction("io.stdout.write", stdout_write_callable))
    stderr_stream.raw_set("write", BuiltinFunction("io.stderr.write", stderr_write_callable))
    io_members = {
        "write": BuiltinFunction("io.write", stdout_write_callable),
        "flush": BuiltinFunction("io.flush", _io_flush),
        "type": BuiltinFunction("io.type", _io_type),
        "read": BuiltinFunction("io.read", _io_read),
        "open": BuiltinFunction("io.open", _io_open),
        "close": BuiltinFunction("io.close", _io_close),
        "input": BuiltinFunction("io.input", _io_input),
        "output": BuiltinFunction("io.output", _io_output),
        "lines": BuiltinFunction("io.lines", _io_lines),
        "stdout": stdout_stream,
        "stderr": stderr_stream,
    }
    _DEFAULT_OUTPUT_STREAM = stdout_stream

    debug_members = {
        "traceback": BuiltinFunction("debug.traceback", _debug_traceback),
        "getinfo": BuiltinFunction("debug.getinfo", _debug_getinfo),
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
        "gmatch": BuiltinFunction("string.gmatch", _string_gmatch),
        "format": BuiltinFunction("string.format", _string_format),
    }
    env.register_library("string", string_members)
    env.register_library("os", os_members)
    env.register_library("io", io_members)
    env.register_library("debug", debug_members)

    coroutine_members = {
        "create": BuiltinFunction("coroutine.create", _coroutine_create),
        "resume": BuiltinFunction("coroutine.resume", _coroutine_resume),
        "yield": BuiltinFunction("coroutine.yield", _coroutine_yield, allow_yield=True),
        "status": BuiltinFunction("coroutine.status", _coroutine_status),
        "wrap": BuiltinFunction("coroutine.wrap", _coroutine_wrap),
        "running": BuiltinFunction("coroutine.running", _coroutine_running),
        "isyieldable": BuiltinFunction(
            "coroutine.isyieldable", _coroutine_isyieldable, yield_probe=True
        ),
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
