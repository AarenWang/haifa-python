from __future__ import annotations

import copy
import json
import ast
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, List, Optional, Set


from haifa_jq.jq_ast import (
    Field,
    FunctionCall,
    Identity,
    IndexAll,
    JQNode,
    Literal,
    Sequence,
    ObjectLiteral,
    Pipe,
    UnaryOp,
    BinaryOp,
    UpdateAssignment,
    Index,
    Slice,
    VarRef,
    AsBinding,
    IfElse,
    TryCatch,
    Reduce,
    Foreach,
)

# Order matters: multi-char operators first
_TOKEN_REGEX = re.compile(
    r"""
    (?P<WS>\s+)
  | (?P<COALESCE_ASSIGN>//=)
  | (?P<COALESCE>//)
  | (?P<EQEQ>==)
  | (?P<NEQ>!=)
  | (?P<GTE>>=)
  | (?P<LTE><=)
  | (?P<PIPE_ASSIGN>\|=)
  | (?P<PIPE>\|)
  | (?P<DOT>\.)
  | (?P<LBRACKET>\[)
  | (?P<RBRACKET>\])
  | (?P<LPAREN>\()
  | (?P<RPAREN>\))
  | (?P<COMMA>,)
  | (?P<VAR>\$[A-Za-z_][A-Za-z0-9_]*)
  | (?P<PLUS_ASSIGN>\+=)
  | (?P<PLUS>\+)
  | (?P<MINUS_ASSIGN>-=)
  | (?P<MINUS>-)
  | (?P<STAR_ASSIGN>\*=)
  | (?P<STAR>\*)
  | (?P<SLASH_ASSIGN>/=)
  | (?P<SLASH>/)
  | (?P<PERCENT_ASSIGN>%=)
  | (?P<PERCENT>%)
  | (?P<GT>>)
  | (?P<LT><)
  | (?P<NUMBER>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<STRING>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<LBRACE>\{)
  | (?P<RBRACE>\})
  | (?P<COLON>:)
  | (?P<SEMICOLON>;)
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


@dataclass(frozen=True)
class FunctionDefinition:
    name: str
    params: List[str]
    body: JQNode



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
        self.definitions: Dict[str, FunctionDefinition] = {}
        self.user_function_names: Set[str] = set()
        self._stop_ident_stack: List[Set[str]] = [set()]
        self._stop_type_stack: List[Set[str]] = [set()]
        self._stop_same_depth_stack: List[Dict[str, Set[int]]] = [dict()]
        self._inlining_stack: List[str] = []
        self._nesting_depth = 0


    @classmethod
    def parse(cls, source: str) -> JQNode:
        parser = cls(_tokenize(source))
        expr = parser._parse_program()
        parser._expect("EOF")
        return expr

    def _parse_program(self) -> JQNode:
        while self._current().type == "IDENT" and self._current().value == "def":
            self._parse_definition()
        body = self._parse_expression()
        return self._inline_node(body)

    def _parse_definition(self) -> None:
        self._advance()  # consume 'def'
        name_token = self._expect("IDENT")
        params: List[str] = []
        if self._match("LPAREN"):
            if self._current().type != "RPAREN":
                while True:
                    var_token = self._expect("VAR")
                    params.append(var_token.value[1:])
                    if not self._match("SEMICOLON"):
                        break
            self._expect("RPAREN")
        self._expect("COLON")
        self.user_function_names.add(name_token.value)
        body = self._parse_expression(stop_types={"SEMICOLON"})
        self._expect("SEMICOLON")
        self.definitions[name_token.value] = FunctionDefinition(name_token.value, params, body)

    # Parsing helpers -------------------------------------------------
    def _current(self) -> Token:
        return self.tokens[self.index]

    def _peek(self, offset: int = 1) -> Token:
        idx = self.index + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _advance(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        if token.type in {"LPAREN", "LBRACKET", "LBRACE"}:
            self._nesting_depth += 1
        elif token.type in {"RPAREN", "RBRACKET", "RBRACE"}:
            self._nesting_depth = max(0, self._nesting_depth - 1)
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

    def _expect_keyword(self, keyword: str) -> Token:
        token = self._current()
        if token.type != "IDENT" or token.value != keyword:
            raise JQSyntaxError(
                f"Expected keyword '{keyword}' at position {token.position}, got {token.value!r}"
            )
        return self._advance()

    def _current_is_keyword(self, keyword: str) -> bool:
        token = self._current()
        return token.type == "IDENT" and token.value == keyword

    @contextmanager
    def _with_stop(
        self,
        stop_idents: Optional[Set[str]] = None,
        stop_types: Optional[Set[str]] = None,
        stop_same_depth_types: Optional[Set[str]] = None,
    ):
        new_idents = set(stop_idents or [])
        new_types = set(stop_types or [])
        prev_same_depth = self._stop_same_depth_stack[-1]
        new_same_depth = {tok: set(depths) for tok, depths in prev_same_depth.items()}
        if stop_same_depth_types:
            base_depth = self._nesting_depth
            for tok in stop_same_depth_types:
                new_same_depth.setdefault(tok, set()).add(base_depth)
        self._stop_ident_stack.append(self._stop_ident_stack[-1] | new_idents)
        self._stop_type_stack.append(self._stop_type_stack[-1] | new_types)
        self._stop_same_depth_stack.append(new_same_depth)
        try:
            yield
        finally:
            self._stop_ident_stack.pop()
            self._stop_type_stack.pop()
            self._stop_same_depth_stack.pop()

    def _should_stop(self) -> bool:
        token = self._current()
        if token.type in self._stop_type_stack[-1]:
            return True
        depths = self._stop_same_depth_stack[-1].get(token.type)
        if depths is not None and self._nesting_depth in depths:
            return True
        if token.type == "IDENT" and token.value in self._stop_ident_stack[-1]:
            return True
        return False

    # Grammar ---------------------------------------------------------
    def _parse_expression(
        self,
        stop_idents: Optional[Set[str]] = None,
        stop_types: Optional[Set[str]] = None,
        stop_same_depth_types: Optional[Set[str]] = None,
    ) -> JQNode:
        with self._with_stop(stop_idents, stop_types, stop_same_depth_types):
            return self._parse_union()

    def _parse_union(self) -> JQNode:
        node = self._parse_pipe()
        expressions = [node]
        while not self._should_stop() and self._match("COMMA"):
            expressions.append(self._parse_pipe())
        if len(expressions) == 1:
            return node
        return Sequence(expressions)

    def _parse_pipe(self) -> JQNode:
        node = self._parse_term()
        while True:
            if self._should_stop():
                break
            # as-binding: term 'as' $var (then continue)
            if self._current().type == "IDENT" and self._current().value == "as":
                self._advance()
                var_tok = self._expect("VAR")
                node = AsBinding(node, var_tok.value[1:])
                # Continue to allow further 'as' or pipes
                continue
            if self._match("PIPE"):
                right = self._parse_term()
                node = Pipe(node, right)
                continue
            break
        return node

    def _parse_term(self) -> JQNode:
        # Historically a placeholder; keep calling the lowest-precedence non-pipe
        return self._parse_update()

    def _parse_update(self) -> JQNode:
        node = self._parse_or()
        while True:
            if self._should_stop():
                break
            if self._match("PIPE_ASSIGN"):
                rhs = self._parse_expression(stop_same_depth_types={"PIPE"})
                node = UpdateAssignment(node, "|=", rhs)
                continue
            if self._match("PLUS_ASSIGN"):
                rhs = self._parse_expression(stop_same_depth_types={"PIPE"})
                node = UpdateAssignment(node, "|=", BinaryOp("+", Identity(), rhs))
                continue
            if self._match("MINUS_ASSIGN"):
                rhs = self._parse_expression(stop_same_depth_types={"PIPE"})
                node = UpdateAssignment(node, "|=", BinaryOp("-", Identity(), rhs))
                continue
            if self._match("STAR_ASSIGN"):
                rhs = self._parse_expression(stop_same_depth_types={"PIPE"})
                node = UpdateAssignment(node, "|=", BinaryOp("*", Identity(), rhs))
                continue
            if self._match("SLASH_ASSIGN"):
                rhs = self._parse_expression(stop_same_depth_types={"PIPE"})
                node = UpdateAssignment(node, "|=", BinaryOp("/", Identity(), rhs))
                continue
            if self._match("PERCENT_ASSIGN"):
                rhs = self._parse_expression(stop_same_depth_types={"PIPE"})
                node = UpdateAssignment(node, "|=", BinaryOp("%", Identity(), rhs))
                continue
            if self._match("COALESCE_ASSIGN"):
                rhs = self._parse_expression(stop_same_depth_types={"PIPE"})
                node = UpdateAssignment(node, "|=", BinaryOp("//", Identity(), rhs))
                continue
            break
        return node

    # Precedence climbing (low -> high)
    def _parse_or(self) -> JQNode:
        node = self._parse_and()
        while self._current().type == "IDENT" and self._current().value == "or":
            if self._should_stop():
                break
            self._advance()
            right = self._parse_and()
            node = BinaryOp("or", node, right)
        return node

    def _parse_and(self) -> JQNode:
        node = self._parse_coalesce()
        while self._current().type == "IDENT" and self._current().value == "and":
            if self._should_stop():
                break
            self._advance()
            right = self._parse_coalesce()
            node = BinaryOp("and", node, right)
        return node

    def _parse_coalesce(self) -> JQNode:
        node = self._parse_equality()
        while self._match("COALESCE"):
            if self._should_stop():
                break
            right = self._parse_equality()
            node = BinaryOp("//", node, right)
        return node

    def _parse_equality(self) -> JQNode:
        node = self._parse_comparison()
        while True:
            if self._should_stop():
                break
            if self._match("EQEQ"):
                right = self._parse_comparison()
                node = BinaryOp("==", node, right)
                continue
            if self._match("NEQ"):
                right = self._parse_comparison()
                node = BinaryOp("!=", node, right)
                continue
            break
        return node

    def _parse_comparison(self) -> JQNode:
        node = self._parse_additive()
        while True:
            if self._should_stop():
                break
            if self._match("GTE"):
                right = self._parse_additive()
                node = BinaryOp(">=", node, right)
                continue
            if self._match("LTE"):
                right = self._parse_additive()
                node = BinaryOp("<=", node, right)
                continue
            if self._match("GT"):
                right = self._parse_additive()
                node = BinaryOp(">", node, right)
                continue
            if self._match("LT"):
                right = self._parse_additive()
                node = BinaryOp("<", node, right)
                continue
            break
        return node

    def _parse_additive(self) -> JQNode:
        node = self._parse_multiplicative()
        while True:
            if self._should_stop():
                break
            if self._match("PLUS"):
                right = self._parse_multiplicative()
                node = BinaryOp("+", node, right)
                continue
            if self._match("MINUS"):
                right = self._parse_multiplicative()
                node = BinaryOp("-", node, right)
                continue
            break
        return node

    def _parse_multiplicative(self) -> JQNode:
        node = self._parse_unary()
        while True:
            if self._should_stop():
                break
            if self._match("STAR"):
                right = self._parse_unary()
                node = BinaryOp("*", node, right)
                continue
            if self._match("SLASH"):
                right = self._parse_unary()
                node = BinaryOp("/", node, right)
                continue
            if self._match("PERCENT"):
                right = self._parse_unary()
                node = BinaryOp("%", node, right)
                continue
            break
        return node

    def _parse_unary(self) -> JQNode:
        # not, unary minus
        token = self._current()
        if token.type == "IDENT" and token.value == "not":
            self._advance()
            return UnaryOp("not", self._parse_unary())
        if token.type == "MINUS":
            self._advance()
            return UnaryOp("-", self._parse_unary())
        return self._parse_postfix()

    def _parse_postfix(self) -> JQNode:
        node = self._parse_primary()
        while True:
            if self._should_stop():
                break
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
                # Empty [] means IndexAll
                if self._current().type == "RBRACKET":
                    self._advance()
                    node = IndexAll(node)
                    continue
                # Slice form with leading ':' => [:end]
                if self._current().type == "COLON":
                    self._advance()
                    end_expr = None
                    if self._current().type != "RBRACKET":
                        end_expr = self._parse_expression()
                    self._expect("RBRACKET")
                    node = Slice(node, None, end_expr)
                    continue
                # First expression
                first_expr = self._parse_expression()
                # Single index: expr]
                if self._match("RBRACKET"):
                    node = Index(node, first_expr)
                    continue
                # Otherwise must be a slice: expr : expr? ]
                self._expect("COLON")
                end_expr = None
                if self._current().type != "RBRACKET":
                    end_expr = self._parse_expression()
                self._expect("RBRACKET")
                node = Slice(node, first_expr, end_expr)
                continue
            break
        return node

    def _parse_primary(self) -> JQNode:
        token = self._current()
        if token.type == "DOT":
            self._advance()
            return Identity()
        if token.type == "VAR":
            self._advance()
            return VarRef(token.value[1:])
        if token.type == "IDENT" and token.value == "if":
            return self._parse_if()
        if token.type == "IDENT" and token.value == "try":
            return self._parse_try()
        if token.type == "IDENT" and token.value == "reduce" and self._peek().type != "LPAREN":
            return self._parse_reduce()
        if token.type == "IDENT" and token.value == "foreach":
            return self._parse_foreach()
        if token.type == "IDENT" and token.value not in _KEYWORDS:
            ident = self._advance()
            if self._match("LPAREN"):
                args = self._parse_arguments()
                self._expect("RPAREN")
                return FunctionCall(ident.value, args)
            if ident.value in self.user_function_names:
                return FunctionCall(ident.value, [])
            return Field(ident.value, Identity())
        if token.type in {"NUMBER", "STRING"} or token.value in _KEYWORDS:
            literal_token = self._advance()
            value = self._parse_literal_value(literal_token)
            return Literal(value)
        if token.type == "LBRACE":
            return self._parse_object_literal()
        if token.type == "LPAREN":
            self._advance()
            expr = self._parse_expression()
            self._expect("RPAREN")
            return expr
        raise JQSyntaxError(f"Unexpected token {token.type} at position {token.position}")

    def _parse_if(self) -> JQNode:
        self._expect_keyword("if")
        return self._parse_if_chain(expect_end=True)

    def _parse_reduce(self) -> JQNode:
        self._expect_keyword("reduce")
        source = self._parse_expression(stop_idents={"as"})
        self._expect_keyword("as")
        var_tok = self._expect("VAR")
        self._expect("LPAREN")
        init_expr = self._parse_expression(stop_same_depth_types={"SEMICOLON"})
        self._expect("SEMICOLON")
        update_expr = self._parse_expression(stop_same_depth_types={"RPAREN"})
        self._expect("RPAREN")
        return Reduce(source, var_tok.value[1:], init_expr, update_expr)

    def _parse_foreach(self) -> JQNode:
        self._expect_keyword("foreach")
        source = self._parse_expression(stop_idents={"as"})
        self._expect_keyword("as")
        var_tok = self._expect("VAR")
        self._expect("LPAREN")
        init_expr = self._parse_expression(stop_same_depth_types={"SEMICOLON"})
        self._expect("SEMICOLON")
        update_expr = self._parse_expression(stop_same_depth_types={"SEMICOLON", "RPAREN"})
        extract_expr = None
        if self._current().type == "SEMICOLON":
            self._advance()
            extract_expr = self._parse_expression(stop_same_depth_types={"RPAREN"})
        self._expect("RPAREN")
        return Foreach(source, var_tok.value[1:], init_expr, update_expr, extract_expr)

    def _parse_if_chain(self, expect_end: bool) -> JQNode:
        condition = self._parse_expression(stop_idents={"then"})
        self._expect_keyword("then")
        then_branch = self._parse_expression(stop_idents={"elif", "else", "end"})
        else_branch: Optional[JQNode] = None
        if self._current_is_keyword("elif"):
            self._advance()
            else_branch = self._parse_if_chain(expect_end=False)
        elif self._current_is_keyword("else"):
            self._advance()
            else_branch = self._parse_expression(stop_idents={"end"})
        if expect_end:
            self._expect_keyword("end")
        return IfElse(condition, then_branch, else_branch)

    def _parse_try(self) -> JQNode:
        self._expect_keyword("try")
        expr = self._parse_expression(stop_idents={"catch"})
        catch_expr = None
        if self._current_is_keyword("catch"):
            self._advance()
            catch_expr = self._parse_expression()
        return TryCatch(expr, catch_expr)


    def _parse_arguments(self) -> List[JQNode]:
        args: List[JQNode] = []
        if self._current().type == "RPAREN":
            return args
        while True:
            args.append(self._parse_expression(stop_types={"COMMA", "SEMICOLON", "RPAREN"}))
            if self._match("COMMA") or self._match("SEMICOLON"):
                continue
            break
        return args

    def _inline_node(self, node: JQNode) -> JQNode:
        if not self.definitions:
            return node
        if isinstance(node, Pipe):
            return Pipe(self._inline_node(node.left), self._inline_node(node.right))
        if isinstance(node, Sequence):
            return Sequence([self._inline_node(expr) for expr in node.expressions])
        if isinstance(node, IfElse):
            else_branch = self._inline_node(node.else_branch) if node.else_branch else None
            return IfElse(
                self._inline_node(node.condition),
                self._inline_node(node.then_branch),
                else_branch,
            )
        if isinstance(node, TryCatch):
            return TryCatch(
                self._inline_node(node.try_expr),
                self._inline_node(node.catch_expr) if node.catch_expr else None,
            )
        if isinstance(node, FunctionCall):
            inlined_args = [self._inline_node(arg) for arg in node.args]
            if node.name in self.definitions:
                definition = self.definitions[node.name]
                if len(definition.params) != len(inlined_args):
                    raise JQSyntaxError(
                        f"Function {node.name} expects {len(definition.params)} args, got {len(inlined_args)}"
                    )
                if node.name in self._inlining_stack:
                    raise NotImplementedError("Recursive function definitions are not supported")
                mapping = {param: arg for param, arg in zip(definition.params, inlined_args)}
                self._inlining_stack.append(node.name)
                try:
                    substituted = self._substitute(copy.deepcopy(definition.body), mapping)
                    return self._inline_node(substituted)
                finally:
                    self._inlining_stack.pop()
            return FunctionCall(node.name, inlined_args)
        if isinstance(node, ObjectLiteral):
            return ObjectLiteral([(key, self._inline_node(value)) for key, value in node.pairs])
        if isinstance(node, Field):
            return Field(node.name, self._inline_node(node.source))
        if isinstance(node, UnaryOp):
            return UnaryOp(node.op, self._inline_node(node.operand))
        if isinstance(node, BinaryOp):
            return BinaryOp(
                node.op,
                self._inline_node(node.left),
                self._inline_node(node.right),
            )
        if isinstance(node, UpdateAssignment):
            return UpdateAssignment(
                self._inline_node(node.target),
                node.op,
                self._inline_node(node.expr),
            )
        if isinstance(node, Index):
            return Index(self._inline_node(node.source), self._inline_node(node.index))
        if isinstance(node, Slice):
            start = self._inline_node(node.start) if node.start else None
            end = self._inline_node(node.end) if node.end else None
            return Slice(self._inline_node(node.source), start, end)
        if isinstance(node, IndexAll):
            return IndexAll(self._inline_node(node.source))
        if isinstance(node, AsBinding):
            return AsBinding(self._inline_node(node.source), node.name)
        if isinstance(node, Reduce):
            return Reduce(
                self._inline_node(node.source),
                node.var_name,
                self._inline_node(node.init),
                self._inline_node(node.update),
            )
        if isinstance(node, Foreach):
            extract = self._inline_node(node.extract) if node.extract else None
            return Foreach(
                self._inline_node(node.source),
                node.var_name,
                self._inline_node(node.init),
                self._inline_node(node.update),
                extract,
            )
        return node

    def _substitute(self, node: JQNode, mapping: Dict[str, JQNode]) -> JQNode:
        if isinstance(node, VarRef) and node.name in mapping:
            return copy.deepcopy(mapping[node.name])
        if isinstance(node, Pipe):
            return Pipe(self._substitute(node.left, mapping), self._substitute(node.right, mapping))
        if isinstance(node, Sequence):
            return Sequence([self._substitute(expr, mapping) for expr in node.expressions])
        if isinstance(node, IfElse):
            else_branch = (
                self._substitute(node.else_branch, mapping) if node.else_branch else None
            )
            return IfElse(
                self._substitute(node.condition, mapping),
                self._substitute(node.then_branch, mapping),
                else_branch,
            )
        if isinstance(node, TryCatch):
            return TryCatch(
                self._substitute(node.try_expr, mapping),
                self._substitute(node.catch_expr, mapping) if node.catch_expr else None,
            )
        if isinstance(node, FunctionCall):
            return FunctionCall(node.name, [self._substitute(arg, mapping) for arg in node.args])
        if isinstance(node, ObjectLiteral):
            return ObjectLiteral([(key, self._substitute(value, mapping)) for key, value in node.pairs])
        if isinstance(node, Field):
            return Field(node.name, self._substitute(node.source, mapping))
        if isinstance(node, UnaryOp):
            return UnaryOp(node.op, self._substitute(node.operand, mapping))
        if isinstance(node, BinaryOp):
            return BinaryOp(
                node.op,
                self._substitute(node.left, mapping),
                self._substitute(node.right, mapping),
            )
        if isinstance(node, UpdateAssignment):
            return UpdateAssignment(
                self._substitute(node.target, mapping),
                node.op,
                self._substitute(node.expr, mapping),
            )
        if isinstance(node, Index):
            return Index(self._substitute(node.source, mapping), self._substitute(node.index, mapping))
        if isinstance(node, Slice):
            start = self._substitute(node.start, mapping) if node.start else None
            end = self._substitute(node.end, mapping) if node.end else None
            return Slice(self._substitute(node.source, mapping), start, end)
        if isinstance(node, IndexAll):
            return IndexAll(self._substitute(node.source, mapping))
        if isinstance(node, AsBinding):
            return AsBinding(self._substitute(node.source, mapping), node.name)
        if isinstance(node, Reduce):
            return Reduce(
                self._substitute(node.source, mapping),
                node.var_name,
                self._substitute(node.init, mapping),
                self._substitute(node.update, mapping),
            )
        if isinstance(node, Foreach):
            extract = self._substitute(node.extract, mapping) if node.extract else None
            return Foreach(
                self._substitute(node.source, mapping),
                node.var_name,
                self._substitute(node.init, mapping),
                self._substitute(node.update, mapping),
                extract,
            )
        return node

    def _parse_literal_value(self, token: Token):
        if token.type == "NUMBER" or token.type == "STRING":
            # Accept both JSON-style (double-quoted) and single-quoted strings.
            # Fallback to ast.literal_eval for Python literal semantics.
            try:
                return json.loads(token.value)
            except json.JSONDecodeError:
                try:
                    return ast.literal_eval(token.value)
                except Exception as exc:
                    raise JQSyntaxError(f"Invalid literal {token.value!r}") from exc
        lowered = token.value.lower()
        if lowered in _KEYWORDS:
            return _KEYWORDS[lowered]
        raise JQSyntaxError(f"Unsupported literal token {token.value!r}")

    def _parse_object_literal(self) -> JQNode:
        pairs = []
        self._advance()  # consume '{'
        if self._current().type != "RBRACE":
            while True:
                key_token = self._current()
                if key_token.type == "STRING":
                    key = json.loads(key_token.value)
                    self._advance()
                elif key_token.type == "IDENT":
                    key = key_token.value
                    self._advance()
                else:
                    raise JQSyntaxError(f"Invalid object key at position {key_token.position}")
                self._expect("COLON")
                value_expr = self._parse_expression(stop_types={"COMMA", "RBRACE"})
                pairs.append((key, value_expr))
                if not self._match("COMMA"):
                    break
        self._expect("RBRACE")
        return ObjectLiteral(pairs)


def parse_jq_program(source: str) -> JQNode:
    """Parse a jq expression into an AST."""
    return JQParser.parse(source)


__all__ = ["parse_jq_program", "JQParser", "JQSyntaxError"]
