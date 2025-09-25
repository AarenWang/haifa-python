from haifa_lua.ast import (
    BreakStmt,
    DoStmt,
    ForGenericStmt,
    ForNumericStmt,
    GotoStmt,
    IfStmt,
    LabelStmt,
    RepeatStmt,
    ReturnStmt,
)
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


def test_numeric_for_statement_with_step():
    src = """
    for i = 1, 5, 2 do
        return i
    end
    """
    stmt = _first_statement(src)
    assert isinstance(stmt, ForNumericStmt)
    assert stmt.var == "i"
    assert stmt.step is not None


def test_numeric_for_without_step_defaults():
    src = """
    for idx = 0, 3 do
        return idx
    end
    """
    stmt = _first_statement(src)
    assert isinstance(stmt, ForNumericStmt)
    assert stmt.step is None


def test_generic_for_parses_iterator_list():
    src = """
    for k, v in iter() do
        return k
    end
    """
    stmt = _first_statement(src)
    assert isinstance(stmt, ForGenericStmt)
    assert stmt.names == ["k", "v"]
    assert len(stmt.iter_exprs) == 1


def test_goto_and_label_statements():
    src = """
    goto skip
    ::skip::
    """
    chunk = LuaParser.parse(src)
    assert len(chunk.body.statements) == 2
    goto_stmt, label_stmt = chunk.body.statements
    assert isinstance(goto_stmt, GotoStmt)
    assert goto_stmt.label == "skip"
    assert isinstance(label_stmt, LabelStmt)
    assert label_stmt.name == "skip"
