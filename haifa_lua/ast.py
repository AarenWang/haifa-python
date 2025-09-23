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
class FunctionExpr(Expr):
    params: List[str]
    body: "Block"

# Statement nodes

@dataclass
class Stmt:
    line: int
    column: int

@dataclass
class Assignment(Stmt):
    target: Identifier
    value: Expr
    is_local: bool = False

@dataclass
class IfStmt(Stmt):
    condition: Expr
    then_branch: "Block"
    else_branch: Optional["Block"] = None

@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: "Block"

@dataclass
class ReturnStmt(Stmt):
    value: Optional[Expr]

@dataclass
class FunctionStmt(Stmt):
    name: Identifier
    params: List[str]
    body: "Block"

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
    "FunctionExpr",
    "Stmt",
    "Assignment",
    "IfStmt",
    "WhileStmt",
    "ReturnStmt",
    "FunctionStmt",
    "ExprStmt",
    "Block",
    "Chunk",
]
