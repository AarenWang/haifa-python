"""Scheme runtime values and formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from haifa_scheme.reader import Symbol


@dataclass(frozen=True)
class EmptyList:
    """The Scheme empty list value."""


EMPTY_LIST = EmptyList()


@dataclass(frozen=True)
class Pair:
    car: Any
    cdr: Any


@dataclass(frozen=True)
class Char:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or len(self.value) != 1:
            raise ValueError("Scheme character value must be a single Python character")


@dataclass(frozen=True)
class Vector:
    items: tuple[Any, ...]


def make_list(values: Iterable[Any]) -> Pair | EmptyList:
    result: Pair | EmptyList = EMPTY_LIST
    for value in reversed(list(values)):
        result = Pair(value, result)
    return result


def is_proper_list(value: Any) -> bool:
    seen: set[int] = set()
    current = value
    while isinstance(current, Pair):
        current_id = id(current)
        if current_id in seen:
            return False
        seen.add(current_id)
        current = current.cdr
    return current is EMPTY_LIST


def equal_value(left: Any, right: Any) -> bool:
    if isinstance(left, Pair) and isinstance(right, Pair):
        return equal_value(left.car, right.car) and equal_value(left.cdr, right.cdr)
    if left is EMPTY_LIST or right is EMPTY_LIST:
        return left is right
    if _is_number(left) and _is_number(right):
        return left == right
    if type(left) is not type(right):
        return False
    return left == right


def to_scheme_string(value: Any) -> str:
    if value is EMPTY_LIST:
        return "()"
    if isinstance(value, Pair):
        return _pair_to_scheme_string(value)
    if isinstance(value, Char):
        return _char_to_scheme_string(value)
    if isinstance(value, Vector):
        return _vector_to_scheme_string(value)
    if isinstance(value, Symbol):
        return str(value)
    if isinstance(value, bool):
        return "#t" if value else "#f"
    if isinstance(value, str):
        return _string_literal(value)
    if value is None:
        return "#<void>"
    return str(value)


def _pair_to_scheme_string(value: Pair) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: Any = value

    while isinstance(current, Pair):
        current_id = id(current)
        if current_id in seen:
            parts.append(". #<cycle>")
            return f"({' '.join(parts)})"
        seen.add(current_id)
        parts.append(to_scheme_string(current.car))
        current = current.cdr

    if current is not EMPTY_LIST:
        parts.append(".")
        parts.append(to_scheme_string(current))

    return f"({' '.join(parts)})"


def _string_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _char_to_scheme_string(value: Char) -> str:
    names = {
        " ": "space",
        "\n": "newline",
        "\t": "tab",
    }
    return f"#\\{names.get(value.value, value.value)}"


def _vector_to_scheme_string(value: Vector) -> str:
    return f"#({' '.join(to_scheme_string(item) for item in value.items)})"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
