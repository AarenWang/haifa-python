"""Reader for a small Scheme subset.

The reader turns source text into simple Python values:

- numbers become ``int`` or ``float``
- booleans become ``bool``
- character literals become ``Char``
- vector literals become ``Vector``
- string literals become ``str``
- symbols become ``Symbol``
- lists become Python ``list``
- dotted lists become ``DottedList``
- reader syntax expands quote/quasiquote/unquote forms into lists
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from haifa_scheme.errors import SchemeSyntaxError


class Symbol(str):
    """A Scheme symbol, distinct from a Scheme string literal."""


@dataclass(frozen=True)
class DottedList:
    """A Scheme dotted list such as ``(a b . c)``."""

    items: list[object]
    tail: object


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

        if index + 1 < length and source[index : index + 2] == "#(":
            tokens.append(_Token("vector-open", "#(", index))
            index += 2
            continue

        if char == ")":
            tokens.append(_Token("close", char, index))
            index += 1
            continue

        if char == "'":
            tokens.append(_Token("quote", char, index))
            index += 1
            continue

        if char == "`":
            tokens.append(_Token("quasiquote", char, index))
            index += 1
            continue

        if char == ",":
            if index + 1 < length and source[index + 1] == "@":
                tokens.append(_Token("unquote-splicing", ",@", index))
                index += 2
                continue
            tokens.append(_Token("unquote", char, index))
            index += 1
            continue

        if char == '"':
            start = index
            value, index = _read_string(source, index)
            tokens.append(_Token("literal", value, start))
            continue

        start = index
        while index < length and not source[index].isspace() and source[index] not in "();'`,":
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
    if atom.startswith("#\\"):
        return _parse_character(atom)
    if _INT_RE.fullmatch(atom):
        return int(atom)
    if _FLOAT_RE.fullmatch(atom):
        return float(atom)
    return Symbol(atom)


def _parse_character(atom: str) -> object:
    from haifa_scheme.values import Char

    value = atom[2:]
    named_characters = {
        "space": " ",
        "newline": "\n",
        "tab": "\t",
    }
    if value in named_characters:
        return Char(named_characters[value])
    if len(value) == 1:
        return Char(value)
    raise SchemeSyntaxError(f"malformed character literal: {atom}")


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
        if token.kind == "vector-open":
            return self._parse_vector(token.position)
        if token.kind in {"quote", "quasiquote", "unquote", "unquote-splicing"}:
            return self._parse_reader_form(token)
        if token.kind == "close":
            raise SchemeSyntaxError(f"unexpected ')' at character {token.position}")

        raise SchemeSyntaxError(f"unexpected token at character {token.position}")

    def _parse_reader_form(self, token: _Token) -> list[object]:
        if self._is_at_end():
            raise SchemeSyntaxError(f"{token.kind} at character {token.position} has no expression")
        return [Symbol(token.kind), self._parse_expression()]

    def _parse_list(self, start_position: int) -> list[object] | DottedList:
        items: list[object] = []
        while not self._is_at_end():
            if self._peek().kind == "close":
                self._advance()
                return items
            if self._is_dot_token(self._peek()):
                dot_token = self._advance()
                if not items:
                    raise SchemeSyntaxError(
                        f"dotted list at character {dot_token.position} must have a head"
                    )
                if self._is_at_end() or self._peek().kind == "close":
                    raise SchemeSyntaxError(
                        f"dotted list at character {dot_token.position} must have a tail"
                    )

                tail = self._parse_expression()
                if self._is_at_end():
                    raise SchemeSyntaxError(f"unclosed '(' at character {start_position}")
                if self._peek().kind != "close":
                    raise SchemeSyntaxError(
                        f"dotted list at character {dot_token.position} must have exactly one tail"
                    )
                self._advance()
                return DottedList(items, tail)
            items.append(self._parse_expression())

        raise SchemeSyntaxError(f"unclosed '(' at character {start_position}")

    def _parse_vector(self, start_position: int) -> object:
        from haifa_scheme.values import Vector

        items: list[object] = []
        while not self._is_at_end():
            if self._peek().kind == "close":
                self._advance()
                return Vector(tuple(items))
            items.append(self._parse_expression())

        raise SchemeSyntaxError(f"unclosed vector literal at character {start_position}")

    def _is_at_end(self) -> bool:
        return self._position >= len(self._tokens)

    def _peek(self) -> _Token:
        return self._tokens[self._position]

    def _advance(self) -> _Token:
        token = self._tokens[self._position]
        self._position += 1
        return token

    @staticmethod
    def _is_dot_token(token: _Token) -> bool:
        return token.kind == "literal" and token.value == Symbol(".")
