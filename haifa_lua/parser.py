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
    FieldAccess,
    FunctionExpr,
    FunctionStmt,
    Identifier,
    IfStmt,
    IndexExpr,
    MethodCallExpr,
    NilLiteral,
    NumberLiteral,
    ReturnStmt,
    StringLiteral,
    TableConstructor,
    TableField,
    UnaryOp,
    VarargExpr,
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
        values: List[Expr] = []
        terminators = {"end", "else", "EOF"}
        if self._current().kind not in terminators:
            values.append(self._parse_expression())
            while self._match(","):
                values.append(self._parse_expression())
        return ReturnStmt(tok.line, tok.column, values)

    def _parse_function(self) -> FunctionStmt:
        tok = self._expect("function")
        name_tok = self._expect("IDENT")
        params, vararg = self._parse_param_list()
        body = self._parse_block(["end"])
        self._expect("end")
        return FunctionStmt(tok.line, tok.column, Identifier(name_tok.line, name_tok.column, name_tok.value), params, body, vararg)

    def _parse_param_list(self) -> Tuple[List[str], bool]:
        params: List[str] = []
        vararg = False
        self._expect("(")
        if self._current().kind != ")":
            while True:
                if self._current().kind == "VARARG":
                    self._advance()
                    vararg = True
                    break
                ident = self._expect("IDENT")
                params.append(ident.value)
                if not self._match(","):
                    break
        self._expect(")")
        return params, vararg

    def _parse_local_function(self) -> Assignment:
        local_tok = self._expect("local")
        self._expect("function")
        name_tok = self._expect("IDENT")
        params, vararg = self._parse_param_list()
        body = self._parse_block(["end"])
        self._expect("end")
        func_expr = FunctionExpr(local_tok.line, local_tok.column, params, vararg, body)
        ident = Identifier(name_tok.line, name_tok.column, name_tok.value)
        return Assignment(local_tok.line, local_tok.column, [ident], [func_expr], True)

    def _parse_local_assignment(self) -> Assignment:
        tok = self._expect("local")
        names: List[Identifier] = []
        while True:
            name_tok = self._expect("IDENT")
            names.append(Identifier(name_tok.line, name_tok.column, name_tok.value))
            if not self._match(","):
                break
        values: List[Expr] = []
        if self._current().kind == "OP" and self._current().value == "=":
            self._advance()
            values = self._parse_expression_list()
        return Assignment(tok.line, tok.column, list(names), values, True)

    def _parse_assignment_or_expression(self):
        expr = self._parse_expression()
        if self._is_assignable(expr):
            targets: List[Expr] = [expr]
            if self._match(","):
                while True:
                    next_expr = self._parse_expression()
                    if not self._is_assignable(next_expr):
                        raise ParserError("Invalid assignment target")
                    targets.append(next_expr)
                    if not self._match(","):
                        break
                self._expect_op("=")
                values = self._parse_expression_list()
                first = targets[0]
                return Assignment(first.line, first.column, targets, values, False)
            if self._current().kind == "OP" and self._current().value == "=":
                self._advance()
                values = self._parse_expression_list()
                return Assignment(expr.line, expr.column, targets, values, False)
        return ExprStmt(expr.line, expr.column, expr)

    def _parse_expression_list(self) -> List[Expr]:
        values: List[Expr] = [self._parse_expression()]
        while self._match(","):
            values.append(self._parse_expression())
        return values

    def _is_assignable(self, expr: Expr) -> bool:
        return isinstance(expr, (Identifier, FieldAccess, IndexExpr))

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
            expr: Expr = NumberLiteral(tok.line, tok.column, value)
        elif token.kind == "STRING":
            tok = self._advance()
            expr = StringLiteral(tok.line, tok.column, tok.value)
        elif token.kind == "IDENT":
            ident = self._advance()
            expr = self._make_identifier_expr(ident)
        elif token.kind in {"VARARG", "..."} or (token.kind == "OP" and token.value == "..."):
            tok = self._advance()
            expr = VarargExpr(tok.line, tok.column)
        elif token.kind == "function":
            expr = self._parse_function_expr()
        elif token.kind == "(":
            self._advance()
            expr = self._parse_expression()
            self._expect(")")
        elif token.kind == "{":
            expr = self._parse_table_constructor()
        elif token.kind == "EOF":
            raise ParserError("Unexpected EOF")
        elif token.kind == "nil":
            tok = self._advance()
            expr = NilLiteral(tok.line, tok.column)
        elif token.kind == "true":
            tok = self._advance()
            expr = BooleanLiteral(tok.line, tok.column, True)
        elif token.kind == "false":
            tok = self._advance()
            expr = BooleanLiteral(tok.line, tok.column, False)
        else:
            raise ParserError(f"Unexpected token {token.kind} at {token.line}:{token.column}")
        return self._parse_postfix(expr)

    def _parse_function_expr(self) -> FunctionExpr:
        tok = self._expect("function")
        params, vararg = self._parse_param_list()
        body = self._parse_block(["end"])
        self._expect("end")
        return FunctionExpr(tok.line, tok.column, params, vararg, body)

    def _parse_postfix(self, expr: Expr) -> Expr:
        while True:
            token = self._current()
            if token.kind == "OP" and token.value == ".":
                self._advance()
                name_tok = self._expect("IDENT")
                expr = FieldAccess(name_tok.line, name_tok.column, expr, name_tok.value)
                continue
            if token.kind == "[":
                bracket_tok = self._advance()
                index_expr = self._parse_expression()
                self._expect("]")
                expr = IndexExpr(bracket_tok.line, bracket_tok.column, expr, index_expr)
                continue
            if token.kind == ":":
                colon_tok = self._advance()
                name_tok = self._expect("IDENT")
                args = self._parse_call_arguments()
                expr = MethodCallExpr(colon_tok.line, colon_tok.column, expr, name_tok.value, args)
                continue
            if token.kind == "(":
                expr = self._finish_call(expr)
                continue
            break
        return expr

    def _finish_call(self, callee: Expr) -> CallExpr:
        lparen = self._expect("(")
        args = self._parse_call_arguments_body()
        return CallExpr(lparen.line, lparen.column, callee, args)

    def _parse_call_arguments(self) -> List[Expr]:
        self._expect("(")
        return self._parse_call_arguments_body()

    def _parse_call_arguments_body(self) -> List[Expr]:
        args: List[Expr] = []
        if self._current().kind != ")":
            while True:
                args.append(self._parse_expression())
                if not self._match(","):
                    break
        self._expect(")")
        return args

    def _make_identifier_expr(self, token: Token) -> Expr:
        parts = token.value.split(".")
        expr: Expr = Identifier(token.line, token.column, parts[0])
        for part in parts[1:]:
            expr = FieldAccess(token.line, token.column, expr, part)
        return expr

    def _parse_table_constructor(self) -> TableConstructor:
        start = self._expect("{")
        fields: List[TableField] = []
        while self._current().kind != "}":
            if self._current().kind == "[":
                self._advance()
                key_expr = self._parse_expression()
                self._expect("]")
                self._expect_op("=")
                value_expr = self._parse_expression()
                fields.append(TableField(value_expr, key=key_expr))
            elif (
                self._current().kind == "IDENT"
                and self._peek_kind(1) == "OP"
                and self.tokens[self.pos + 1].value == "="
            ):
                name_tok = self._advance()
                self._expect_op("=")
                value_expr = self._parse_expression()
                fields.append(TableField(value_expr, name=name_tok.value))
            else:
                value_expr = self._parse_expression()
                fields.append(TableField(value_expr))
            if not self._match(",") and not self._match(";"):
                break
        self._expect("}")
        return TableConstructor(start.line, start.column, fields)

__all__ = ["LuaParser", "ParserError"]
