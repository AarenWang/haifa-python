from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional


class JQNode:
    """Base class for jq AST nodes."""


@dataclass(frozen=True)
class Identity(JQNode):
    pass


@dataclass(frozen=True)
class Literal(JQNode):
    value: object


@dataclass(frozen=True)
class Field(JQNode):
    name: str
    source: JQNode


@dataclass(frozen=True)
class IndexAll(JQNode):
    source: JQNode


@dataclass(frozen=True)
class FunctionCall(JQNode):
    name: str
    args: List[JQNode]


@dataclass(frozen=True)
class Pipe(JQNode):
    left: JQNode
    right: JQNode


@dataclass(frozen=True)
class Sequence(JQNode):
    expressions: List[JQNode]


@dataclass(frozen=True)
class IfElse(JQNode):
    condition: JQNode
    then_branch: JQNode
    else_branch: Optional[JQNode]


@dataclass(frozen=True)
class TryCatch(JQNode):
    try_expr: JQNode
    catch_expr: Optional[JQNode]


@dataclass(frozen=True)
class ObjectLiteral(JQNode):
    pairs: List[Tuple[str, JQNode]]


@dataclass(frozen=True)
class UnaryOp(JQNode):
    op: str  # "-" or "not"
    operand: JQNode


@dataclass(frozen=True)
class BinaryOp(JQNode):
    op: str  # "+", "-", "*", "/", "%", "==", "!=", ">", ">=", "<", "<=", "and", "or", "//"
    left: JQNode
    right: JQNode


@dataclass(frozen=True)
class UpdateAssignment(JQNode):
    target: JQNode
    op: str  # currently "|=" for generic form
    expr: JQNode


@dataclass(frozen=True)
class Index(JQNode):
    source: JQNode
    index: JQNode


@dataclass(frozen=True)
class Slice(JQNode):
    source: JQNode
    start: Optional[JQNode]
    end: Optional[JQNode]


@dataclass(frozen=True)
class VarRef(JQNode):
    name: str  # without leading '$'


@dataclass(frozen=True)
class AsBinding(JQNode):
    source: JQNode  # expression to evaluate and bind
    name: str       # variable name without leading '$'


@dataclass(frozen=True)
class Reduce(JQNode):
    source: JQNode
    var_name: str
    init: JQNode
    update: JQNode


@dataclass(frozen=True)
class Foreach(JQNode):
    source: JQNode
    var_name: str
    init: JQNode
    update: JQNode
    extract: Optional[JQNode]


def flatten_pipe(expr: JQNode) -> List[JQNode]:
    """Expand a pipe tree into a flat left-to-right list."""
    if isinstance(expr, Pipe):
        return flatten_pipe(expr.left) + flatten_pipe(expr.right)
    return [expr]


__all__ = [
    "JQNode",
    "Identity",
    "Literal",
    "Field",
    "IndexAll",
    "FunctionCall",
    "Pipe",
    "Sequence",
    "IfElse",
    "TryCatch",
    "ObjectLiteral",
    "UnaryOp",
    "BinaryOp",
    "UpdateAssignment",
    "Index",
    "Slice",
    "VarRef",
    "AsBinding",
    "Reduce",
    "Foreach",
    "flatten_pipe",
]
