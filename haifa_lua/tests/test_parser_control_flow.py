from haifa_lua.ast import BreakStmt, DoStmt, IfStmt, RepeatStmt, ReturnStmt
from haifa_lua.parser import LuaParser


def _first_statement(source: str):
    chunk = LuaParser.parse(source)
    assert chunk.body.statements, "expected at least one statement"
    return chunk.body.statements[0]


def test_if_statement_collects_elseif_clauses():
    src = """
    if a then
        return 1
    elseif b then
        return 2
    elseif c then
        return 3
    else
        return 4
    end
    """
    stmt = _first_statement(src)
    assert isinstance(stmt, IfStmt)
    assert len(stmt.elseif_branches) == 2
    for clause in stmt.elseif_branches:
        assert isinstance(clause.body.statements[0], ReturnStmt)
    assert stmt.else_branch is not None
    assert isinstance(stmt.else_branch.statements[0], ReturnStmt)


def test_repeat_until_forms_dedicated_node():
    src = """
    repeat
        x = x + 1
    until x > 5
    """
    stmt = _first_statement(src)
    assert isinstance(stmt, RepeatStmt)
    assert len(stmt.body.statements) == 1


def test_do_block_wraps_inner_statements():
    src = """
    do
        return 42
    end
    """
    stmt = _first_statement(src)
    assert isinstance(stmt, DoStmt)
    assert len(stmt.body.statements) == 1
    assert isinstance(stmt.body.statements[0], ReturnStmt)


def test_break_statement_node():
    stmt = _first_statement("break")
    assert isinstance(stmt, BreakStmt)
