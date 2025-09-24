from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Expression nodes

@dataclass
class Expr:
    line: int
    column: int

@dataclass
class NumberLiteral(Expr):
    value: float

@dataclass
class StringLiteral(Expr):
    value: str

@dataclass
class BooleanLiteral(Expr):
    value: bool

@dataclass
class NilLiteral(Expr):
    pass

@dataclass
class Identifier(Expr):
    name: str

@dataclass
class BinaryOp(Expr):
    left: Expr
    op: str
    right: Expr

@dataclass
class UnaryOp(Expr):
    op: str
    operand: Expr

@dataclass
class CallExpr(Expr):
    callee: Expr
    args: List[Expr]


@dataclass
class MethodCallExpr(Expr):
    receiver: Expr
    method: str
    args: List[Expr]


@dataclass
class FieldAccess(Expr):
    table: Expr
    field: str


@dataclass
class IndexExpr(Expr):
    table: Expr
    index: Expr


@dataclass
class TableField:
    value: Expr
    key: Optional[Expr] = None
    name: Optional[str] = None


@dataclass
class TableConstructor(Expr):
    fields: List[TableField]

@dataclass
class FunctionExpr(Expr):
    params: List[str]
    vararg: bool
    body: "Block"

# Statement nodes

@dataclass
class Stmt:
    line: int
    column: int

@dataclass
class Assignment(Stmt):
    targets: List[Expr]
    values: List[Expr]
    is_local: bool = False


@dataclass
class ElseIfClause:
    line: int
    column: int
    condition: Expr
    body: "Block"


@dataclass
class IfStmt(Stmt):
    condition: Expr
    then_branch: "Block"
    elseif_branches: List[ElseIfClause] = field(default_factory=list)
    else_branch: Optional["Block"] = None

@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: "Block"

@dataclass
class RepeatStmt(Stmt):
    body: "Block"
    condition: Expr


@dataclass
class DoStmt(Stmt):
    body: "Block"


@dataclass
class BreakStmt(Stmt):
    pass

@dataclass
class ForNumericStmt(Stmt):
    var: str
    start: Expr
    limit: Expr
    step: Optional[Expr]
    body: "Block"

@dataclass
class ForGenericStmt(Stmt):
    names: List[str]
    iter_exprs: List[Expr]
    body: "Block"

@dataclass
class VarargExpr(Expr):
    pass

@dataclass
class ReturnStmt(Stmt):
    values: List[Expr]

@dataclass
class FunctionStmt(Stmt):
    name: Identifier
    params: List[str]
    body: "Block"
    vararg: bool = False

@dataclass
class ExprStmt(Stmt):
    expr: Expr

@dataclass
class Block:
    statements: List[Stmt] = field(default_factory=list)

@dataclass
class Chunk:
    body: Block

__all__ = [
    "Expr",
    "NumberLiteral",
    "StringLiteral",
    "BooleanLiteral",
    "NilLiteral",
    "Identifier",
    "BinaryOp",
    "UnaryOp",
    "CallExpr",
    "MethodCallExpr",
    "FieldAccess",
    "IndexExpr",
    "TableConstructor",
    "TableField",
    "FunctionExpr",
    "VarargExpr",
    "Stmt",
    "Assignment",
    "ElseIfClause",
    "IfStmt",
    "WhileStmt",
    "RepeatStmt",
    "DoStmt",
    "BreakStmt",
    "ForNumericStmt",
    "ForGenericStmt",
    "ReturnStmt",
    "FunctionStmt",
    "ExprStmt",
    "Block",
    "Chunk",
]
