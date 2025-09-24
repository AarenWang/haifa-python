from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from .ast import (
    Assignment,
    Block,
    CallExpr,
    Expr,
    ExprStmt,
    FieldAccess,
    FunctionExpr,
    FunctionStmt,
    Identifier,
    IfStmt,
    IndexExpr,
    MethodCallExpr,
    ReturnStmt,
    Chunk,
    TableConstructor,
    VarargExpr,
    WhileStmt,
)

@dataclass
class FunctionInfo:
    captured_locals: Set[str] = field(default_factory=set)
    upvalues: List[str] = field(default_factory=list)
    vararg: bool = False

class Scope:
    def __init__(self, parent: 'Scope | None', info: FunctionInfo):
        self.parent = parent
        self.locals: Set[str] = set()
        self.captured: Set[str] = set()
        self.free_order: List[str] = []
        self.free_set: Set[str] = set()
        self.info = info

    def declare(self, name: str) -> None:
        self.locals.add(name)

    def use(self, name: str) -> None:
        if name in self.locals:
            return
        if name not in self.free_set:
            self.free_set.add(name)
            self.free_order.append(name)

    def propagate_child_upvalues(self, names: List[str]) -> None:
        for name in names:
            if name in self.locals:
                self.captured.add(name)
            else:
                self.use(name)


def _resolved_in_parents(scope: Scope, name: str) -> bool:
    current = scope.parent
    while current:
        if name in current.locals or name in current.captured:
            return True
        current = current.parent
    return False


def _filter_upvalues(child_scope: Scope) -> List[str]:
    resolved: List[str] = []
    for name in child_scope.free_order:
        if _resolved_in_parents(child_scope, name):
            resolved.append(name)
    return resolved


def analyze(chunk: Chunk) -> Tuple[Dict[int, FunctionInfo], FunctionInfo]:
    mapping: Dict[int, FunctionInfo] = {}
    root_info = FunctionInfo()
    scope = Scope(None, root_info)
    _analyze_block(chunk.body, scope, mapping)
    root_info.captured_locals |= scope.captured
    root_info.upvalues = []
    return mapping, root_info


def _analyze_block(block: Block, scope: Scope, mapping: Dict[int, FunctionInfo]):
    for stmt in block.statements:
        if isinstance(stmt, Assignment):
            if stmt.is_local:
                for target in stmt.targets:
                    if isinstance(target, Identifier):
                        scope.declare(target.name)
            else:
                for target in stmt.targets:
                    if not isinstance(target, Identifier):
                        _analyze_expr(target, scope, mapping)
            for value in stmt.values:
                _analyze_expr(value, scope, mapping)
        elif isinstance(stmt, ExprStmt):
            _analyze_expr(stmt.expr, scope, mapping)
        elif isinstance(stmt, IfStmt):
            _analyze_expr(stmt.condition, scope, mapping)
            _analyze_block(stmt.then_branch, scope, mapping)
            if stmt.else_branch:
                _analyze_block(stmt.else_branch, scope, mapping)
        elif isinstance(stmt, WhileStmt):
            _analyze_expr(stmt.condition, scope, mapping)
            _analyze_block(stmt.body, scope, mapping)
        elif isinstance(stmt, ReturnStmt):
            for value in stmt.values:
                _analyze_expr(value, scope, mapping)
        elif isinstance(stmt, FunctionStmt):
            # function name is treated as global assignment
            func_info = FunctionInfo()
            func_info.vararg = stmt.vararg
            child_scope = Scope(scope, func_info)
            for param in stmt.params:
                child_scope.declare(param)
            if stmt.vararg:
                child_scope.declare("...")
            _analyze_block(stmt.body, child_scope, mapping)
            func_info.captured_locals |= child_scope.captured
            func_info.upvalues = _filter_upvalues(child_scope)
            mapping[id(stmt)] = func_info
            scope.propagate_child_upvalues(func_info.upvalues)
        else:
            # Unhandled statement types can be ignored for now
            pass


def _analyze_expr(expr: Expr, scope: Scope, mapping: Dict[int, FunctionInfo]):
    from .ast import (
        BinaryOp,
        CallExpr,
        Identifier,
        IndexExpr,
        MethodCallExpr,
        NumberLiteral,
        StringLiteral,
        BooleanLiteral,
        NilLiteral,
        TableConstructor,
        UnaryOp,
        FieldAccess,
    )

    if isinstance(expr, Identifier):
        scope.use(expr.name)
    elif isinstance(expr, BinaryOp):
        _analyze_expr(expr.left, scope, mapping)
        _analyze_expr(expr.right, scope, mapping)
    elif isinstance(expr, UnaryOp):
        _analyze_expr(expr.operand, scope, mapping)
    elif isinstance(expr, CallExpr):
        _analyze_expr(expr.callee, scope, mapping)
        for arg in expr.args:
            _analyze_expr(arg, scope, mapping)
    elif isinstance(expr, MethodCallExpr):
        _analyze_expr(expr.receiver, scope, mapping)
        for arg in expr.args:
            _analyze_expr(arg, scope, mapping)
    elif isinstance(expr, FunctionExpr):
        func_info = FunctionInfo()
        func_info.vararg = expr.vararg
        child_scope = Scope(scope, func_info)
        for param in expr.params:
            child_scope.declare(param)
        if expr.vararg:
            child_scope.declare("...")
        _analyze_block(expr.body, child_scope, mapping)
        func_info.captured_locals |= child_scope.captured
        func_info.upvalues = _filter_upvalues(child_scope)
        mapping[id(expr)] = func_info
        scope.propagate_child_upvalues(func_info.upvalues)
    elif isinstance(expr, FieldAccess):
        _analyze_expr(expr.table, scope, mapping)
    elif isinstance(expr, IndexExpr):
        _analyze_expr(expr.table, scope, mapping)
        _analyze_expr(expr.index, scope, mapping)
    elif isinstance(expr, VarargExpr):
        scope.use("...")
    elif isinstance(expr, TableConstructor):
        for field in expr.fields:
            if field.key is not None:
                _analyze_expr(field.key, scope, mapping)
            _analyze_expr(field.value, scope, mapping)
    elif isinstance(expr, (NumberLiteral, StringLiteral, BooleanLiteral, NilLiteral)):
        return
    else:
        return

__all__ = ["FunctionInfo", "analyze"]
