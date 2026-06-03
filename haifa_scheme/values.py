"""Scheme runtime values and formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import math
from typing import Any, Iterable, TextIO

from haifa_scheme.reader import Symbol


@dataclass(frozen=True)
class EmptyList:
    """The Scheme empty list value."""


EMPTY_LIST = EmptyList()


@dataclass(frozen=True)
class EOFObject:
    """The Scheme end-of-file object."""


EOF_OBJECT = EOFObject()


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


@dataclass
class TextPort:
    stream: TextIO
    readable: bool
    writable: bool
    name: str
    close_stream: bool = False
    pending_datums: list[object] = field(default_factory=list)
    datums_loaded: bool = False
    closed: bool = False

    @classmethod
    def input(cls, stream: TextIO, name: str, *, close_stream: bool = False) -> "TextPort":
        return cls(
            stream=stream,
            readable=True,
            writable=False,
            name=name,
            close_stream=close_stream,
        )

    @classmethod
    def output(cls, stream: TextIO, name: str, *, close_stream: bool = False) -> "TextPort":
        return cls(
            stream=stream,
            readable=False,
            writable=True,
            name=name,
            close_stream=close_stream,
        )

    def close(self) -> None:
        if self.closed:
            return
        if self.close_stream:
            self.stream.close()
        self.closed = True


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
        return eqv_value(left, right)
    if type(left) is not type(right):
        return False
    return left == right


def eqv_value(left: Any, right: Any) -> bool:
    if _is_number(left) and _is_number(right):
        return _numeric_eqv(left, right)
    if type(left) is not type(right):
        return False
    return left == right


def to_scheme_string(value: Any) -> str:
    if value is EMPTY_LIST:
        return "()"
    if value is EOF_OBJECT:
        return "#<eof>"
    if isinstance(value, Pair):
        return _pair_to_scheme_string(value)
    if isinstance(value, Char):
        return _char_to_scheme_string(value)
    if isinstance(value, Vector):
        return _vector_to_scheme_string(value)
    if isinstance(value, TextPort):
        return _port_to_scheme_string(value)
    if isinstance(value, Symbol):
        return str(value)
    if isinstance(value, bool):
        return "#t" if value else "#f"
    if _is_number(value):
        return _number_to_scheme_string(value)
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


def _port_to_scheme_string(value: TextPort) -> str:
    if value.readable and value.writable:
        direction = "input-output-port"
    elif value.readable:
        direction = "input-port"
    else:
        direction = "output-port"
    status = "closed " if value.closed else ""
    return f"#<{status}{direction} {value.name}>"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, Fraction, float, complex)) and not isinstance(value, bool)


def _is_exact_number(value: Any) -> bool:
    return isinstance(value, (int, Fraction)) and not isinstance(value, bool)


def _numeric_eqv(left: Any, right: Any) -> bool:
    if _is_exact_number(left) or _is_exact_number(right):
        return _is_exact_number(left) and _is_exact_number(right) and left == right
    return type(left) is type(right) and left == right


def _number_to_scheme_string(value: int | Fraction | float | complex) -> str:
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return str(value.numerator)
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, complex):
        return _complex_to_scheme_string(value)
    return str(value)


def _complex_to_scheme_string(value: complex) -> str:
    real = 0.0 if value.real == 0 else value.real
    imag = 0.0 if value.imag == 0 else value.imag

    if real == 0:
        return f"{_signed_imaginary_to_scheme_string(imag)}i"

    sign = "+" if imag >= 0 else "-"
    return (
        f"{_float_component_to_scheme_string(real)}"
        f"{sign}{_imaginary_magnitude_to_scheme_string(abs(imag))}i"
    )


def _signed_imaginary_to_scheme_string(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{_imaginary_magnitude_to_scheme_string(abs(value))}"


def _imaginary_magnitude_to_scheme_string(value: float) -> str:
    if value == 1:
        return ""
    return _float_component_to_scheme_string(value)


def _float_component_to_scheme_string(value: float) -> str:
    if math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value)
