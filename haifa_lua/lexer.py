from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional

KEYWORDS = {
    "if",
    "then",
    "else",
    "end",
    "while",
    "do",
    "function",
    "return",
    "local",
    "and",
    "or",
    "not",
    "true",
    "false",
    "nil",
}

@dataclass
class Token:
    kind: str
    value: str
    line: int
    column: int

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Token({self.kind!r}, {self.value!r}, {self.line}:{self.column})"

class LuaLexer:
    def __init__(self, source: str):
        self.source = source
        self.length = len(source)
        self.pos = 0
        self.line = 1
        self.column = 1

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while True:
            token = self._next_token()
            if token is None:
                break
            tokens.append(token)
        tokens.append(Token("EOF", "", self.line, self.column))
        return tokens

    # ------------------------------- internals ---------------------------- #
    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= self.length:
            return "\0"
        return self.source[idx]

    def _advance(self, count: int = 1) -> str:
        ch = ""
        for _ in range(count):
            if self.pos >= self.length:
                return "\0"
            ch = self.source[self.pos]
            self.pos += 1
            if ch == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1
        return ch

    def _next_token(self) -> Optional[Token]:
        while True:
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
                continue
            if ch == "-" and self._peek(1) == "-":
                self._advance(2)
                while self._peek() not in {"\n", "\0"}:
                    self._advance()
                continue
            break

        start_line, start_col = self.line, self.column
        ch = self._peek()
        if ch == "\0":
            return None

        if ch == "." and self._peek(1) == "." and self._peek(2) == ".":
            self._advance(3)
            return Token("VARARG", "...", start_line, start_col)
        if ch.isdigit() or (ch == "." and self._peek(1).isdigit()):
            return self._number(start_line, start_col)
        if ch == '"' or ch == "'":
            return self._string(start_line, start_col)
        if ch.isalpha() or ch == "_":
            return self._identifier(start_line, start_col)

        # Operators / punctuation
        two_char = ch + self._peek(1)
        if two_char in {"==", "~=", "<=", ">="}:
            self._advance(2)
            return Token("OP", two_char, start_line, start_col)
        if ch in "+-*/%=#<>":
            self._advance()
            return Token("OP", ch, start_line, start_col)
        if ch in "(){}[],;":
            self._advance()
            return Token(ch, ch, start_line, start_col)

        raise SyntaxError(f"Unexpected character {ch!r} at {start_line}:{start_col}")

    def _number(self, line: int, col: int) -> Token:
        start = self.pos
        has_dot = False
        while True:
            ch = self._peek()
            if ch == ".":
                if has_dot:
                    break
                has_dot = True
                self._advance()
            elif ch.isdigit():
                self._advance()
            else:
                break
        value = self.source[start:self.pos]
        return Token("NUMBER", value, line, col)

    def _string(self, line: int, col: int) -> Token:
        quote = self._advance()
        start = self.pos
        while True:
            ch = self._peek()
            if ch == "\0":
                raise SyntaxError(f"Unterminated string at {line}:{col}")
            if ch == quote:
                break
            if ch == "\\":
                self._advance()
            self._advance()
        value = self.source[start:self.pos]
        self._advance()  # closing quote
        return Token("STRING", value, line, col)

    def _identifier(self, line: int, col: int) -> Token:
        start = self.pos
        while True:
            ch = self._peek()
            if not (ch.isalnum() or ch == "_"):
                break
            self._advance()
        value = self.source[start:self.pos]
        kind = value if value in KEYWORDS else "IDENT"
        return Token(kind, value, line, col)

__all__ = ["LuaLexer", "Token", "KEYWORDS"]
