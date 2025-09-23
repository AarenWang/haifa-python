from __future__ import annotations

from typing import List, Optional

from .ast import (
    Assignment,
    BinaryOp,
    Block,
    BooleanLiteral,
    CallExpr,
    Chunk,
    Expr,
    ExprStmt,
    FunctionExpr,
    FunctionStmt,
    Identifier,
    IfStmt,
    NilLiteral,
    NumberLiteral,
    ReturnStmt,
    StringLiteral,
    UnaryOp,
    WhileStmt,
)
from .lexer import LuaLexer, Token


class ParserError(SyntaxError):
    pass


class LuaParser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    @classmethod
    def parse(cls, source: str) -> Chunk:
        lexer = LuaLexer(source)
        tokens = lexer.tokenize()
        parser = cls(tokens)
        return parser._parse_chunk()

    # ------------------------------------------------------------------
    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        token = self._current()
        if token.kind != "EOF":
            self.pos += 1
        return token

    def _peek_kind(self, offset: int = 1) -> str:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return "EOF"
        return self.tokens[idx].kind

    def _match(self, *kinds: str) -> Optional[Token]:
        if self._current().kind in kinds:
            return self._advance()
        return None

    def _expect(self, kind: str) -> Token:
        token = self._current()
        if token.kind != kind:
            raise ParserError(f"Expected {kind}, got {token.kind} at {token.line}:{token.column}")
        return self._advance()

    def _expect_op(self, symbol: str) -> Token:
        token = self._current()
        if token.kind != "OP" or token.value != symbol:
            raise ParserError(f"Expected '{symbol}', got {token.value} at {token.line}:{token.column}")
        return self._advance()

    def _parse_chunk(self) -> Chunk:
        statements: List = []
        while self._current().kind != "EOF":
            statements.append(self._parse_statement())
            self._match(";")
        return Chunk(Block(statements))

    def _parse_statement(self):
        token = self._current()
        if token.kind == "if":
            return self._parse_if()
        if token.kind == "while":
            return self._parse_while()
        if token.kind == "return":
            return self._parse_return()
        if token.kind == "function":
            return self._parse_function()
        if token.kind == "local":
            if self._peek_kind(1) == "function":
                return self._parse_local_function()
            return self._parse_local_assignment()
        return self._parse_assignment_or_expression()

    def _parse_block(self, terminators: Optional[List[str]] = None) -> Block:
        statements: List = []
        while True:
            if self._current().kind == "EOF":
                break
            if terminators and self._current().kind in terminators:
                break
            statements.append(self._parse_statement())
            self._match(";")
        return Block(statements)

    def _parse_if(self) -> IfStmt:
        if_tok = self._expect("if")
        condition = self._parse_expression()
        self._expect("then")
        then_block = self._parse_block(["else", "end"])
        else_block = None
        if self._match("else"):
            else_block = self._parse_block(["end"])
        self._expect("end")
        return IfStmt(condition.line, condition.column, condition, then_block, else_block)

    def _parse_while(self) -> WhileStmt:
        tok = self._expect("while")
        condition = self._parse_expression()
        self._expect("do")
        body = self._parse_block(["end"])
        self._expect("end")
        return WhileStmt(tok.line, tok.column, condition, body)

    def _parse_return(self) -> ReturnStmt:
        tok = self._expect("return")
        if self._current().kind in {"end", "else", "EOF"}:
            return ReturnStmt(tok.line, tok.column, None)
        value = self._parse_expression()
        return ReturnStmt(tok.line, tok.column, value)

    def _parse_function(self) -> FunctionStmt:
        tok = self._expect("function")
        name_tok = self._expect("IDENT")
        params = self._parse_param_list()
        body = self._parse_block(["end"])
        self._expect("end")
        return FunctionStmt(tok.line, tok.column, Identifier(name_tok.line, name_tok.column, name_tok.value), params, body)

    def _parse_param_list(self) -> List[str]:
        params: List[str] = []
        self._expect("(")
        if self._current().kind != ")":
            while True:
                ident = self._expect("IDENT")
                params.append(ident.value)
                if not self._match(","):
                    break
        self._expect(")")
        return params

    def _parse_local_function(self) -> Assignment:
        local_tok = self._expect("local")
        self._expect("function")
        name_tok = self._expect("IDENT")
        params = self._parse_param_list()
        body = self._parse_block(["end"])
        self._expect("end")
        func_expr = FunctionExpr(local_tok.line, local_tok.column, params, body)
        ident = Identifier(name_tok.line, name_tok.column, name_tok.value)
        return Assignment(local_tok.line, local_tok.column, ident, func_expr, True)

    def _parse_local_assignment(self) -> Assignment:
        tok = self._expect("local")
        name = self._expect("IDENT")
        self._expect_op("=")
        expr = self._parse_expression()
        return Assignment(tok.line, tok.column, Identifier(name.line, name.column, name.value), expr, True)

    def _parse_assignment_or_expression(self):
        expr = self._parse_expression()
        if isinstance(expr, Identifier) and self._current().kind == "OP" and self._current().value == "=":
            self._advance()
            value = self._parse_expression()
            return Assignment(expr.line, expr.column, expr, value, False)
        return ExprStmt(expr.line, expr.column, expr)

    # ------------------------ expression parsing ------------------------- #
    def _parse_expression(self) -> Expr:
        return self._parse_or()

    def _parse_or(self) -> Expr:
        expr = self._parse_and()
        while self._match("or"):
            op_tok = self.tokens[self.pos - 1]
            right = self._parse_and()
            expr = BinaryOp(op_tok.line, op_tok.column, expr, "or", right)
        return expr

    def _parse_and(self) -> Expr:
        expr = self._parse_comparison()
        while self._match("and"):
            op_tok = self.tokens[self.pos - 1]
            right = self._parse_comparison()
            expr = BinaryOp(op_tok.line, op_tok.column, expr, "and", right)
        return expr

    def _parse_comparison(self) -> Expr:
        expr = self._parse_term()
        while True:
            token = self._current()
            if token.kind == "OP" and token.value in {"==", "~=", "<", ">", "<=", ">="}:
                op_tok = self._advance()
                right = self._parse_term()
                expr = BinaryOp(op_tok.line, op_tok.column, expr, op_tok.value, right)
            else:
                break
        return expr

    def _parse_term(self) -> Expr:
        expr = self._parse_factor()
        while True:
            token = self._current()
            if token.kind == "OP" and token.value in {"+", "-"}:
                op_tok = self._advance()
                right = self._parse_factor()
                expr = BinaryOp(op_tok.line, op_tok.column, expr, op_tok.value, right)
            else:
                break
        return expr

    def _parse_factor(self) -> Expr:
        expr = self._parse_unary()
        while True:
            token = self._current()
            if token.kind == "OP" and token.value in {"*", "/", "%"}:
                op_tok = self._advance()
                right = self._parse_unary()
                expr = BinaryOp(op_tok.line, op_tok.column, expr, op_tok.value, right)
            else:
                break
        return expr

    def _parse_unary(self) -> Expr:
        token = self._current()
        if token.kind == "OP" and token.value == "-":
            op_tok = self._advance()
            operand = self._parse_unary()
            return UnaryOp(op_tok.line, op_tok.column, op_tok.value, operand)
        if token.kind == "not":
            op_tok = self._advance()
            operand = self._parse_unary()
            return UnaryOp(op_tok.line, op_tok.column, op_tok.value, operand)
        return self._parse_primary()

    def _parse_primary(self) -> Expr:
        token = self._current()
        if token.kind == "NUMBER":
            tok = self._advance()
            value = float(tok.value) if "." in tok.value else int(tok.value)
            return NumberLiteral(tok.line, tok.column, value)
        if token.kind == "STRING":
            tok = self._advance()
            return StringLiteral(tok.line, tok.column, tok.value)
        if token.kind == "IDENT":
            ident = self._advance()
            expr: Expr = Identifier(ident.line, ident.column, ident.value)
            if self._match("("):
                args: List[Expr] = []
                if self._current().kind != ")":
                    while True:
                        args.append(self._parse_expression())
                        if not self._match(","):
                            break
                self._expect(")")
                expr = CallExpr(ident.line, ident.column, expr, args)
            return expr
        if token.kind == "function":
            return self._parse_function_expr()
        if token.kind == "(" :
            self._advance()
            expr = self._parse_expression()
            self._expect(")")
            return expr
        if token.kind == "EOF":
            raise ParserError("Unexpected EOF")
        if token.kind == "nil":
            tok = self._advance()
            return NilLiteral(tok.line, tok.column)
        if token.kind == "true":
            tok = self._advance()
            return BooleanLiteral(tok.line, tok.column, True)
        if token.kind == "false":
            tok = self._advance()
            return BooleanLiteral(tok.line, tok.column, False)
        raise ParserError(f"Unexpected token {token.kind} at {token.line}:{token.column}")

    def _parse_function_expr(self) -> FunctionExpr:
        tok = self._expect("function")
        params = self._parse_param_list()
        body = self._parse_block(["end"])
        self._expect("end")
        return FunctionExpr(tok.line, tok.column, params, body)

__all__ = ["LuaParser", "ParserError"]
