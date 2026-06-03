"""Built-in functions for the minimal Scheme runtime."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import reduce
import math
from operator import mul
from typing import Any, Protocol

from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError, SchemeSyntaxError
from haifa_scheme.reader import DottedList, Symbol, parse_source
from haifa_scheme.values import (
    EMPTY_LIST,
    EOF_OBJECT,
    Char,
    EmptyList,
    Pair,
    TextPort,
    Vector,
    equal_value,
    eqv_value,
    is_proper_list,
    make_list,
    to_scheme_string,
)


class ApplyFunc(Protocol):
    def __call__(self, procedure: Any, args: Sequence[Any]) -> Any: ...


class ProcedurePredicate(Protocol):
    def __call__(self, value: Any) -> bool: ...


class CallCcFunc(Protocol):
    def __call__(self, procedure: Any) -> Any: ...


@dataclass(frozen=True)
class BuiltinContext:
    apply_func: ApplyFunc
    is_procedure_func: ProcedurePredicate
    call_cc_func: CallCcFunc
    current_input_port: TextPort
    current_output_port: TextPort


@dataclass(frozen=True)
class BuiltinFunction:
    name: str
    func: Callable[[Sequence[Any]], Any] | Callable[[Sequence[Any], BuiltinContext], Any]
    needs_context: bool = False

    def __call__(self, args: Sequence[Any], context: BuiltinContext | None = None) -> Any:
        if self.needs_context:
            if context is None:
                raise SchemeRuntimeError(f"{self.name} requires runtime context")
            return self.func(args, context)  # type: ignore[misc]
        return self.func(args)


def create_global_environment() -> Environment:
    environment = Environment()
    for name, builtin in _BUILTINS.items():
        environment.define(Symbol(name), builtin)
    return environment


def _add(args: Sequence[Any]) -> Any:
    _ensure_numbers(args, "+")
    return sum(args)


def _subtract(args: Sequence[Any]) -> Any:
    _ensure_min_args(args, 1, "-")
    _ensure_numbers(args, "-")
    if len(args) == 1:
        return -args[0]
    return args[0] - sum(args[1:])


def _multiply(args: Sequence[Any]) -> Any:
    _ensure_numbers(args, "*")
    return reduce(mul, args, 1)


def _divide(args: Sequence[Any]) -> Any:
    _ensure_min_args(args, 1, "/")
    _ensure_numbers(args, "/")
    if _all_exact_numbers(args):
        return _divide_exact(args)
    if len(args) == 1:
        if args[0] == 0:
            raise SchemeRuntimeError("/ division by zero")
        return 1 / args[0]

    result = args[0]
    for divisor in args[1:]:
        if divisor == 0:
            raise SchemeRuntimeError("/ division by zero")
        result = result / divisor
    return result


def _numeric_equal(args: Sequence[Any]) -> bool:
    _ensure_min_args(args, 2, "=")
    _ensure_numbers(args, "=")
    first = args[0]
    return all(value == first for value in args[1:])


def _less_than(args: Sequence[Any]) -> bool:
    return _compare_adjacent(args, "<", lambda left, right: left < right)


def _greater_than(args: Sequence[Any]) -> bool:
    return _compare_adjacent(args, ">", lambda left, right: left > right)


def _cons(args: Sequence[Any]) -> Pair:
    _ensure_exact_args(args, 2, "cons")
    return Pair(args[0], args[1])


def _car(args: Sequence[Any]) -> Any:
    pair = _ensure_pair_arg(args, "car")
    return pair.car


def _cdr(args: Sequence[Any]) -> Any:
    pair = _ensure_pair_arg(args, "cdr")
    return pair.cdr


def _list(args: Sequence[Any]) -> Pair | EmptyList:
    return make_list(args)


def _length(args: Sequence[Any]) -> int:
    value = _ensure_proper_list_arg(args, "length")
    return len(_proper_list_to_python_list(value))


def _append(args: Sequence[Any]) -> Any:
    if not args:
        return EMPTY_LIST

    result = args[-1]
    for value in reversed(args[:-1]):
        if not is_proper_list(value):
            raise SchemeRuntimeError("append expected proper list arguments before final tail")
        for item in reversed(_proper_list_to_python_list(value)):
            result = Pair(item, result)
    return result


def _reverse(args: Sequence[Any]) -> Pair | EmptyList:
    value = _ensure_proper_list_arg(args, "reverse")
    return make_list(reversed(_proper_list_to_python_list(value)))


def _map(args: Sequence[Any], context: BuiltinContext) -> Pair | EmptyList:
    procedure, lists = _ensure_list_procedure_args(args, "map")
    if not context.is_procedure_func(procedure):
        raise SchemeRuntimeError("map expected procedure argument")
    return make_list(
        context.apply_func(procedure, list(items))
        for items in zip(*lists, strict=True)
    )


def _for_each(args: Sequence[Any], context: BuiltinContext) -> None:
    procedure, lists = _ensure_list_procedure_args(args, "for-each")
    if not context.is_procedure_func(procedure):
        raise SchemeRuntimeError("for-each expected procedure argument")
    for items in zip(*lists, strict=True):
        context.apply_func(procedure, list(items))
    return None


def _null_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "null?")
    return args[0] is EMPTY_LIST


def _pair_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "pair?")
    return isinstance(args[0], Pair)


def _list_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "list?")
    return is_proper_list(args[0])


def _eq_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 2, "eq?")
    left, right = args
    if isinstance(left, Pair) or isinstance(right, Pair):
        return left is right
    if left is EMPTY_LIST or right is EMPTY_LIST:
        return left is right
    return type(left) is type(right) and left == right


def _eqv_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 2, "eqv?")
    left, right = args
    if isinstance(left, Pair) or isinstance(right, Pair):
        return left is right
    if left is EMPTY_LIST or right is EMPTY_LIST:
        return left is right
    return eqv_value(left, right)


def _equal_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 2, "equal?")
    return equal_value(args[0], args[1])


def _number_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "number?")
    return _is_number(args[0])


def _integer_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "integer?")
    value = args[0]
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, Fraction):
        return value.denominator == 1
    if isinstance(value, float):
        return math.isfinite(value) and value.is_integer()
    return False


def _exact_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "exact?")
    return _is_exact_number(args[0])


def _inexact_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "inexact?")
    return _is_inexact_number(args[0])


def _rational_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "rational?")
    value = args[0]
    if isinstance(value, bool) or isinstance(value, complex):
        return False
    return isinstance(value, (int, Fraction)) or (
        isinstance(value, float) and math.isfinite(value)
    )


def _real_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "real?")
    value = args[0]
    if isinstance(value, bool):
        return False
    if isinstance(value, complex):
        return value.imag == 0
    return isinstance(value, (int, Fraction, float))


def _complex_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "complex?")
    return _is_number(args[0])


def _string_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "string?")
    return isinstance(args[0], str) and not isinstance(args[0], Symbol)


def _symbol_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "symbol?")
    return isinstance(args[0], Symbol)


def _boolean_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "boolean?")
    return isinstance(args[0], bool)


def _char_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "char?")
    return isinstance(args[0], Char)


def _vector_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "vector?")
    return isinstance(args[0], Vector)


def _apply_builtin(args: Sequence[Any], context: BuiltinContext) -> Any:
    _ensure_min_args(args, 2, "apply")
    final_arg = args[-1]
    if not is_proper_list(final_arg):
        raise SchemeRuntimeError("apply expected final argument to be a proper list")
    applied_args = [*args[1:-1], *_proper_list_to_python_list(final_arg)]
    return context.apply_func(args[0], applied_args)


def _procedure_predicate(args: Sequence[Any], context: BuiltinContext) -> bool:
    _ensure_exact_args(args, 1, "procedure?")
    return context.is_procedure_func(args[0])


def _call_cc_builtin(args: Sequence[Any], context: BuiltinContext) -> Any:
    _ensure_exact_args(args, 1, "call/cc")
    procedure = args[0]
    if not context.is_procedure_func(procedure):
        raise SchemeRuntimeError("call/cc expected procedure argument")
    return context.call_cc_func(procedure)


def _display_builtin(args: Sequence[Any], context: BuiltinContext) -> None:
    value, port = _value_and_output_port(args, "display", context)
    _write_text(port, _display_text(value), "display")
    return None


def _write_builtin(args: Sequence[Any], context: BuiltinContext) -> None:
    value, port = _value_and_output_port(args, "write", context)
    _write_text(port, to_scheme_string(value), "write")
    return None


def _newline_builtin(args: Sequence[Any], context: BuiltinContext) -> None:
    port = _optional_output_port(args, "newline", context)
    _write_text(port, "\n", "newline")
    return None


def _read_builtin(args: Sequence[Any], context: BuiltinContext) -> Any:
    port = _optional_input_port(args, "read", context)
    _ensure_open_input_port(port, "read")
    if not port.datums_loaded:
        try:
            port.pending_datums.extend(parse_source(port.stream.read()))
        except SchemeSyntaxError as exc:
            raise SchemeRuntimeError(f"read failed: {exc}") from exc
        port.datums_loaded = True
    if not port.pending_datums:
        return EOF_OBJECT
    return _datum_to_value(port.pending_datums.pop(0))


def _open_input_file(args: Sequence[Any]) -> TextPort:
    path = _ensure_string_path(args, "open-input-file")
    try:
        stream = open(path, "r", encoding="utf-8")
    except OSError as exc:
        raise SchemeRuntimeError(f"open-input-file failed: {exc}") from exc
    return TextPort.input(stream, path, close_stream=True)


def _open_output_file(args: Sequence[Any]) -> TextPort:
    path = _ensure_string_path(args, "open-output-file")
    try:
        stream = open(path, "w", encoding="utf-8")
    except OSError as exc:
        raise SchemeRuntimeError(f"open-output-file failed: {exc}") from exc
    return TextPort.output(stream, path, close_stream=True)


def _close_input_port(args: Sequence[Any]) -> None:
    _ensure_open_input_port(_ensure_port_arg(args, "close-input-port"), "close-input-port")
    args[0].close()
    return None


def _close_output_port(args: Sequence[Any]) -> None:
    _ensure_open_output_port(_ensure_port_arg(args, "close-output-port"), "close-output-port")
    args[0].close()
    return None


def _input_port_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "input-port?")
    return isinstance(args[0], TextPort) and args[0].readable


def _output_port_predicate(args: Sequence[Any]) -> bool:
    _ensure_exact_args(args, 1, "output-port?")
    return isinstance(args[0], TextPort) and args[0].writable


def _current_input_port(args: Sequence[Any], context: BuiltinContext) -> TextPort:
    _ensure_exact_args(args, 0, "current-input-port")
    return context.current_input_port


def _current_output_port(args: Sequence[Any], context: BuiltinContext) -> TextPort:
    _ensure_exact_args(args, 0, "current-output-port")
    return context.current_output_port


def _compare_adjacent(
    args: Sequence[Any], name: str, predicate: Callable[[Any, Any], bool]
) -> bool:
    _ensure_min_args(args, 2, name)
    _ensure_real_comparable_numbers(args, name)
    return all(predicate(left, right) for left, right in zip(args, args[1:]))


def _divide_exact(args: Sequence[Any]) -> Fraction:
    if len(args) == 1:
        if args[0] == 0:
            raise SchemeRuntimeError("/ division by zero")
        return Fraction(1) / Fraction(args[0])

    result = Fraction(args[0])
    for divisor in args[1:]:
        if divisor == 0:
            raise SchemeRuntimeError("/ division by zero")
        result /= Fraction(divisor)
    return result


def _ensure_min_args(args: Sequence[Any], minimum: int, name: str) -> None:
    if len(args) < minimum:
        raise SchemeRuntimeError(f"{name} expected at least {minimum} argument(s), got {len(args)}")


def _ensure_exact_args(args: Sequence[Any], expected: int, name: str) -> None:
    if len(args) != expected:
        raise SchemeRuntimeError(f"{name} expected {expected} argument(s), got {len(args)}")


def _ensure_pair_arg(args: Sequence[Any], name: str) -> Pair:
    _ensure_exact_args(args, 1, name)
    if not isinstance(args[0], Pair):
        raise SchemeRuntimeError(f"{name} expected pair argument")
    return args[0]


def _ensure_proper_list_arg(args: Sequence[Any], name: str) -> Pair | EmptyList:
    _ensure_exact_args(args, 1, name)
    if not is_proper_list(args[0]):
        raise SchemeRuntimeError(f"{name} expected proper list argument")
    return args[0]


def _ensure_list_procedure_args(
    args: Sequence[Any], name: str
) -> tuple[Any, list[list[Any]]]:
    _ensure_min_args(args, 2, name)
    lists: list[list[Any]] = []
    expected_length: int | None = None
    for value in args[1:]:
        if not is_proper_list(value):
            raise SchemeRuntimeError(f"{name} expected proper list arguments")
        items = _proper_list_to_python_list(value)
        if expected_length is None:
            expected_length = len(items)
        elif len(items) != expected_length:
            raise SchemeRuntimeError(f"{name} expected list arguments with equal length")
        lists.append(items)
    return args[0], lists


def _ensure_port_arg(args: Sequence[Any], name: str) -> TextPort:
    _ensure_exact_args(args, 1, name)
    if not isinstance(args[0], TextPort):
        raise SchemeRuntimeError(f"{name} expected port argument")
    return args[0]


def _ensure_string_path(args: Sequence[Any], name: str) -> str:
    _ensure_exact_args(args, 1, name)
    path = args[0]
    if not isinstance(path, str) or isinstance(path, Symbol):
        raise SchemeRuntimeError(f"{name} expected string path")
    return path


def _value_and_output_port(
    args: Sequence[Any], name: str, context: BuiltinContext
) -> tuple[Any, TextPort]:
    if len(args) not in (1, 2):
        raise SchemeRuntimeError(f"{name} expected 1 or 2 argument(s), got {len(args)}")
    port = context.current_output_port if len(args) == 1 else args[1]
    if not isinstance(port, TextPort):
        raise SchemeRuntimeError(f"{name} expected output port argument")
    _ensure_open_output_port(port, name)
    return args[0], port


def _optional_output_port(
    args: Sequence[Any], name: str, context: BuiltinContext
) -> TextPort:
    if len(args) > 1:
        raise SchemeRuntimeError(f"{name} expected 0 or 1 argument(s), got {len(args)}")
    port = context.current_output_port if not args else args[0]
    if not isinstance(port, TextPort):
        raise SchemeRuntimeError(f"{name} expected output port argument")
    _ensure_open_output_port(port, name)
    return port


def _optional_input_port(args: Sequence[Any], name: str, context: BuiltinContext) -> TextPort:
    if len(args) > 1:
        raise SchemeRuntimeError(f"{name} expected 0 or 1 argument(s), got {len(args)}")
    port = context.current_input_port if not args else args[0]
    if not isinstance(port, TextPort):
        raise SchemeRuntimeError(f"{name} expected input port argument")
    _ensure_open_input_port(port, name)
    return port


def _ensure_open_input_port(port: TextPort, name: str) -> None:
    if not port.readable or port.closed:
        raise SchemeRuntimeError(f"{name} expected open input port")


def _ensure_open_output_port(port: TextPort, name: str) -> None:
    if not port.writable or port.closed:
        raise SchemeRuntimeError(f"{name} expected open output port")


def _write_text(port: TextPort, text: str, name: str) -> None:
    _ensure_open_output_port(port, name)
    try:
        port.stream.write(text)
    except OSError as exc:
        raise SchemeRuntimeError(f"{name} failed: {exc}") from exc


def _display_text(value: Any) -> str:
    if isinstance(value, str) and not isinstance(value, Symbol):
        return value
    if isinstance(value, Char):
        return value.value
    return to_scheme_string(value)


def _datum_to_value(expression: object) -> object:
    if isinstance(expression, Vector):
        return Vector(tuple(_datum_to_value(item) for item in expression.items))
    if isinstance(expression, DottedList):
        tail = _datum_to_value(expression.tail)
        for item in reversed(expression.items):
            tail = Pair(_datum_to_value(item), tail)
        return tail
    if isinstance(expression, list):
        return make_list(_datum_to_value(item) for item in expression)
    return expression


def _ensure_numbers(args: Sequence[Any], name: str) -> None:
    for arg in args:
        if not _is_number(arg):
            raise SchemeRuntimeError(f"{name} expected number arguments")


def _ensure_real_comparable_numbers(args: Sequence[Any], name: str) -> None:
    for arg in args:
        if not _is_number(arg):
            raise SchemeRuntimeError(f"{name} expected number arguments")
        if isinstance(arg, complex):
            raise SchemeRuntimeError(f"{name} expected real number arguments")


def _proper_list_to_python_list(value: Any) -> list[Any]:
    result: list[Any] = []
    current = value
    while isinstance(current, Pair):
        result.append(current.car)
        current = current.cdr
    return result


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, Fraction, float, complex)) and not isinstance(value, bool)


def _is_exact_number(value: Any) -> bool:
    return isinstance(value, (int, Fraction)) and not isinstance(value, bool)


def _is_inexact_number(value: Any) -> bool:
    return isinstance(value, (float, complex)) and not isinstance(value, bool)


def _all_exact_numbers(args: Sequence[Any]) -> bool:
    return all(_is_exact_number(arg) for arg in args)


_BUILTINS: dict[str, BuiltinFunction] = {
    "+": BuiltinFunction("+", _add),
    "-": BuiltinFunction("-", _subtract),
    "*": BuiltinFunction("*", _multiply),
    "/": BuiltinFunction("/", _divide),
    "=": BuiltinFunction("=", _numeric_equal),
    "<": BuiltinFunction("<", _less_than),
    ">": BuiltinFunction(">", _greater_than),
    "cons": BuiltinFunction("cons", _cons),
    "car": BuiltinFunction("car", _car),
    "cdr": BuiltinFunction("cdr", _cdr),
    "list": BuiltinFunction("list", _list),
    "length": BuiltinFunction("length", _length),
    "append": BuiltinFunction("append", _append),
    "reverse": BuiltinFunction("reverse", _reverse),
    "map": BuiltinFunction("map", _map, needs_context=True),
    "for-each": BuiltinFunction("for-each", _for_each, needs_context=True),
    "null?": BuiltinFunction("null?", _null_predicate),
    "pair?": BuiltinFunction("pair?", _pair_predicate),
    "list?": BuiltinFunction("list?", _list_predicate),
    "eq?": BuiltinFunction("eq?", _eq_predicate),
    "eqv?": BuiltinFunction("eqv?", _eqv_predicate),
    "equal?": BuiltinFunction("equal?", _equal_predicate),
    "number?": BuiltinFunction("number?", _number_predicate),
    "integer?": BuiltinFunction("integer?", _integer_predicate),
    "exact?": BuiltinFunction("exact?", _exact_predicate),
    "inexact?": BuiltinFunction("inexact?", _inexact_predicate),
    "rational?": BuiltinFunction("rational?", _rational_predicate),
    "real?": BuiltinFunction("real?", _real_predicate),
    "complex?": BuiltinFunction("complex?", _complex_predicate),
    "string?": BuiltinFunction("string?", _string_predicate),
    "symbol?": BuiltinFunction("symbol?", _symbol_predicate),
    "boolean?": BuiltinFunction("boolean?", _boolean_predicate),
    "char?": BuiltinFunction("char?", _char_predicate),
    "vector?": BuiltinFunction("vector?", _vector_predicate),
    "apply": BuiltinFunction("apply", _apply_builtin, needs_context=True),
    "procedure?": BuiltinFunction("procedure?", _procedure_predicate, needs_context=True),
    "call/cc": BuiltinFunction("call/cc", _call_cc_builtin, needs_context=True),
    "call-with-current-continuation": BuiltinFunction(
        "call-with-current-continuation", _call_cc_builtin, needs_context=True
    ),
    "display": BuiltinFunction("display", _display_builtin, needs_context=True),
    "write": BuiltinFunction("write", _write_builtin, needs_context=True),
    "newline": BuiltinFunction("newline", _newline_builtin, needs_context=True),
    "read": BuiltinFunction("read", _read_builtin, needs_context=True),
    "open-input-file": BuiltinFunction("open-input-file", _open_input_file),
    "open-output-file": BuiltinFunction("open-output-file", _open_output_file),
    "close-input-port": BuiltinFunction("close-input-port", _close_input_port),
    "close-output-port": BuiltinFunction("close-output-port", _close_output_port),
    "input-port?": BuiltinFunction("input-port?", _input_port_predicate),
    "output-port?": BuiltinFunction("output-port?", _output_port_predicate),
    "current-input-port": BuiltinFunction(
        "current-input-port", _current_input_port, needs_context=True
    ),
    "current-output-port": BuiltinFunction(
        "current-output-port", _current_output_port, needs_context=True
    ),
}
