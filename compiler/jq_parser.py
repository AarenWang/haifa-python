from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional

from jq_ast import (
    Field,
    FunctionCall,
    Identity,
    IndexAll,
    JQNode,
    Literal,
    Pipe,
)

_TOKEN_REGEX = re.compile(
    r"""
    (?P<WS>\s+)
  | (?P<PIPE>\|)
  | (?P<DOT>\.)
  | (?P<LBRACKET>\[)
  | (?P<RBRACKET>\])
  | (?P<LPAREN>\()
  | (?P<RPAREN>\))
  | (?P<COMMA>,)
  | (?P<NUMBER>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<STRING>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)

_KEYWORDS = {"true": True, "false": False, "null": None}


@dataclass(frozen=True)
class Token:
    type: str
    value: str
    position: int


class JQSyntaxError(ValueError):
    pass


def _tokenize(source: str) -> List[Token]:
    pos = 0
    tokens: List[Token] = []
    length = len(source)
    while pos < length:
        match = _TOKEN_REGEX.match(source, pos)
        if not match:
            raise JQSyntaxError(f"Unexpected character at position {pos}: {source[pos]!r}")
        kind = match.lastgroup
        text = match.group()
        pos = match.end()
        if kind == "WS":
            continue
        tokens.append(Token(kind, text, match.start()))
    tokens.append(Token("EOF", "", pos))
    return tokens


class JQParser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.index = 0

    @classmethod
    def parse(cls, source: str) -> JQNode:
        parser = cls(_tokenize(source))
        expr = parser._parse_expression()
        parser._expect("EOF")
        return expr

    # Parsing helpers -------------------------------------------------
    def _current(self) -> Token:
        return self.tokens[self.index]

    def _advance(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _match(self, *types: str) -> Optional[Token]:
        if self._current().type in types:
            return self._advance()
        return None

    def _expect(self, type_: str) -> Token:
        token = self._current()
        if token.type != type_:
            raise JQSyntaxError(f"Expected {type_} at position {token.position}, got {token.type}")
        return self._advance()

    # Grammar ---------------------------------------------------------
    def _parse_expression(self) -> JQNode:
        node = self._parse_pipe()
        return node

    def _parse_pipe(self) -> JQNode:
        node = self._parse_term()
        while self._match("PIPE"):
            right = self._parse_term()
            node = Pipe(node, right)
        return node

    def _parse_term(self) -> JQNode:
        return self._parse_postfix()

    def _parse_postfix(self) -> JQNode:
        node = self._parse_primary()
        while True:
            if self._match("DOT"):
                ident = self._expect("IDENT")
                node = Field(ident.value, node)
                continue
            if (
                self._current().type == "IDENT"
                and self._current().value not in _KEYWORDS
                and isinstance(node, Identity)
            ):
                ident = self._advance()
                node = Field(ident.value, node)
                continue
            if self._match("LBRACKET"):
                self._expect("RBRACKET")
                node = IndexAll(node)
                continue
            break
        return node

    def _parse_primary(self) -> JQNode:
        token = self._current()
        if token.type == "DOT":
            self._advance()
            return Identity()
        if token.type == "IDENT" and token.value not in _KEYWORDS:
            ident = self._advance()
            if self._match("LPAREN"):
                args = self._parse_arguments()
                self._expect("RPAREN")
                return FunctionCall(ident.value, args)
            return Field(ident.value, Identity())
        if token.type in {"NUMBER", "STRING"} or token.value in _KEYWORDS:
            literal_token = self._advance()
            value = self._parse_literal_value(literal_token)
            return Literal(value)
        if token.type == "LPAREN":
            self._advance()
            expr = self._parse_expression()
            self._expect("RPAREN")
            return expr
        raise JQSyntaxError(f"Unexpected token {token.type} at position {token.position}")

    def _parse_arguments(self) -> List[JQNode]:
        args: List[JQNode] = []
        if self._current().type == "RPAREN":
            return args
        while True:
            args.append(self._parse_expression())
            if not self._match("COMMA"):
                break
        return args

    def _parse_literal_value(self, token: Token):
        if token.type == "NUMBER" or token.type == "STRING":
            try:
                return json.loads(token.value)
            except json.JSONDecodeError as exc:
                raise JQSyntaxError(f"Invalid literal {token.value!r}") from exc
        lowered = token.value.lower()
        if lowered in _KEYWORDS:
            return _KEYWORDS[lowered]
        raise JQSyntaxError(f"Unsupported literal token {token.value!r}")


def parse(source: str) -> JQNode:
    """Parse a jq expression into an AST."""
    return JQParser.parse(source)


__all__ = ["parse", "JQParser", "JQSyntaxError"]
