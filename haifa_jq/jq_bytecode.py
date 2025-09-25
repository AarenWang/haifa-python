from __future__ import annotations

"""JQOpcode placeholder for future separation.

For now, alias to the core Opcode to preserve compatibility while
gradually migrating the jq compiler to emit JQOpcode.
"""

from enum import Enum, auto
from compiler.bytecode import Instruction


class JQOpcode(Enum):
    # jq-only opcodes (handlers in JQVM)
    OBJ_GET = auto()
    GET_INDEX = auto()
    LEN_VALUE = auto()

    PUSH_EMIT = auto()
    POP_EMIT = auto()
    EMIT = auto()
    TRY_BEGIN = auto()
    TRY_END = auto()

    OBJ_SET = auto()
    FLATTEN = auto()
    REDUCE = auto()

    # jq core filters / collections
    KEYS = auto()
    HAS = auto()
    CONTAINS = auto()
    JOIN = auto()
    REVERSE = auto()
    FIRST = auto()
    LAST = auto()
    ANY = auto()
    ALL = auto()
    AGG_ADD = auto()

    # Sorting and aggregation family
    SORT = auto()
    SORT_BY = auto()
    UNIQUE = auto()
    UNIQUE_BY = auto()
    MIN = auto()
    MAX = auto()
    MIN_BY = auto()
    MAX_BY = auto()
    GROUP_BY = auto()

    # String/regex tools
    TOSTRING = auto()
    TONUMBER = auto()
    SPLIT = auto()
    GSUB = auto()

__all__ = ["JQOpcode", "Instruction"]
