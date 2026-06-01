"""Built-in functions for the minimal Scheme runtime."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import reduce
from operator import mul
from typing import Any

from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.reader import Symbol


@dataclass(frozen=True)
class BuiltinFunction:
    name: str
    func: Callable[[Sequence[Any]], Any]

    def __call__(self, args: Sequence[Any]) -> Any:
        return self.func(args)


def create_global_environment() -> Environment:
    environment = Environment()
    for name, func in _BUILTINS.items():
        environment.define(Symbol(name), BuiltinFunction(name, func))
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


def _compare_adjacent(
    args: Sequence[Any], name: str, predicate: Callable[[int | float, int | float], bool]
) -> bool:
    _ensure_min_args(args, 2, name)
    _ensure_numbers(args, name)
    return all(predicate(left, right) for left, right in zip(args, args[1:]))


def _ensure_min_args(args: Sequence[Any], minimum: int, name: str) -> None:
    if len(args) < minimum:
        raise SchemeRuntimeError(f"{name} expected at least {minimum} argument(s), got {len(args)}")


def _ensure_numbers(args: Sequence[Any], name: str) -> None:
    for arg in args:
        if not _is_number(arg):
            raise SchemeRuntimeError(f"{name} expected number arguments")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


_BUILTINS: dict[str, Callable[[Sequence[Any]], Any]] = {
    "+": _add,
    "-": _subtract,
    "*": _multiply,
    "/": _divide,
    "=": _numeric_equal,
    "<": _less_than,
    ">": _greater_than,
}
