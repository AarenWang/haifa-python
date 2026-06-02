"""Reader for a small Scheme subset.

The reader turns source text into simple Python values:

- numbers become ``int`` or ``float``
- booleans become ``bool``
- string literals become ``str``
- symbols become ``Symbol``
- lists become Python ``list``
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from haifa_scheme.errors import SchemeSyntaxError


class Symbol(str):
    """A Scheme symbol, distinct from a Scheme string literal."""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: Any
    position: int


_INT_RE = re.compile(r"[+-]?\d+")
_FLOAT_RE = re.compile(
    r"[+-]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+[eE][+-]?\d+)|(?:\d+\.\d*[eE][+-]?\d+)|(?:\.\d+[eE][+-]?\d+))"
)


def parse_source(source: str) -> list[object]:
    """Parse all top-level Scheme expressions from ``source``."""

    parser = _Parser(_tokenize(source))
    return parser.parse_all()


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    length = len(source)

    while index < length:
        char = source[index]

        if char.isspace():
            index += 1
            continue

        if char == ";":
            while index < length and source[index] != "\n":
                index += 1
            continue

        if char == "(":
            tokens.append(_Token("open", char, index))
            index += 1
            continue

        if char == ")":
            tokens.append(_Token("close", char, index))
            index += 1
            continue

        if char == "'":
            tokens.append(_Token("quote", char, index))
            index += 1
            continue

        if char == '"':
            start = index
            value, index = _read_string(source, index)
            tokens.append(_Token("literal", value, start))
            continue

        start = index
        while index < length and not source[index].isspace() and source[index] not in "();'":
            index += 1
        atom = source[start:index]
        tokens.append(_Token("literal", _parse_atom(atom), start))

    return tokens


def _read_string(source: str, start: int) -> tuple[str, int]:
    chars: list[str] = []
    index = start + 1
    length = len(source)

    while index < length:
        char = source[index]
        if char == '"':
            return "".join(chars), index + 1
        if char == "\\":
            index += 1
            if index >= length:
                raise SchemeSyntaxError(f"unterminated string starting at character {start}")
            chars.append(_escape_char(source[index]))
            index += 1
            continue
        chars.append(char)
        index += 1

    raise SchemeSyntaxError(f"unterminated string starting at character {start}")


def _escape_char(char: str) -> str:
    escapes = {
        '"': '"',
        "\\": "\\",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    return escapes.get(char, char)


def _parse_atom(atom: str) -> object:
    if atom == "#t":
        return True
    if atom == "#f":
        return False
    if _INT_RE.fullmatch(atom):
        return int(atom)
    if _FLOAT_RE.fullmatch(atom):
        return float(atom)
    return Symbol(atom)


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._position = 0

    def parse_all(self) -> list[object]:
        expressions: list[object] = []
        while not self._is_at_end():
            expressions.append(self._parse_expression())
        return expressions

    def _parse_expression(self) -> object:
        if self._is_at_end():
            raise SchemeSyntaxError("unexpected end of input")

        token = self._advance()
        if token.kind == "literal":
            return token.value
        if token.kind == "open":
            return self._parse_list(token.position)
        if token.kind == "quote":
            if self._is_at_end():
                raise SchemeSyntaxError(f"quote at character {token.position} has no expression")
            return [Symbol("quote"), self._parse_expression()]
        if token.kind == "close":
            raise SchemeSyntaxError(f"unexpected ')' at character {token.position}")

        raise SchemeSyntaxError(f"unexpected token at character {token.position}")

    def _parse_list(self, start_position: int) -> list[object]:
        items: list[object] = []
        while not self._is_at_end():
            if self._peek().kind == "close":
                self._advance()
                return items
            items.append(self._parse_expression())

        raise SchemeSyntaxError(f"unclosed '(' at character {start_position}")

    def _is_at_end(self) -> bool:
        return self._position >= len(self._tokens)

    def _peek(self) -> _Token:
        return self._tokens[self._position]

    def _advance(self) -> _Token:
        token = self._tokens[self._position]
        self._position += 1
        return token
