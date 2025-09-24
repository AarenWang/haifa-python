from __future__ import annotations

from haifa_lua.ast import (
    ExprStmt,
    FieldAccess,
    Identifier,
    IndexExpr,
    MethodCallExpr,
    NumberLiteral,
    ReturnStmt,
    TableConstructor,
)
from haifa_lua.parser import LuaParser


def _first_return_expr(source: str):
    chunk = LuaParser.parse(source)
    assert chunk.body.statements, "expected at least one statement"
    stmt = chunk.body.statements[0]
    assert isinstance(stmt, ReturnStmt), "expected a return statement"
    assert stmt.values, "expected return with values"
    return stmt.values[0]


def test_table_constructor_supports_array_and_key_fields():
    expr = _first_return_expr("return {1, answer = 42, [3] = 99}")
    assert isinstance(expr, TableConstructor)
    assert len(expr.fields) == 3

    array_field, named_field, keyed_field = expr.fields

    assert array_field.key is None
    assert array_field.name is None
    assert isinstance(array_field.value, NumberLiteral)

    assert named_field.key is None
    assert named_field.name == "answer"

    assert keyed_field.name is None
    assert keyed_field.key is not None


def test_field_access_builds_nested_chain():
    expr = _first_return_expr("return foo.bar.baz")
    assert isinstance(expr, FieldAccess)
    assert expr.field == "baz"
    inner = expr.table
    assert isinstance(inner, FieldAccess)
    assert inner.field == "bar"
    base = inner.table
    assert isinstance(base, Identifier)
    assert base.name == "foo"


def test_index_expression_parses_postfix():
    expr = _first_return_expr("return items[1]")
    assert isinstance(expr, IndexExpr)
    assert isinstance(expr.table, Identifier)


def test_method_call_expression():
    chunk = LuaParser.parse("object:method(10, 20)")
    stmt = chunk.body.statements[0]
    assert isinstance(stmt, ExprStmt)
    method_call = stmt.expr
    assert isinstance(method_call, MethodCallExpr)
    assert isinstance(method_call.receiver, Identifier)
    assert method_call.method == "method"
    assert len(method_call.args) == 2
