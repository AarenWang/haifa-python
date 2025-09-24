from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


@dataclass(frozen=True)
class SourceLocation:
    file: str
    line: int
    column: int


@dataclass(frozen=True)
class InstructionDebug:
    """Metadata describing the provenance of an instruction."""

    location: SourceLocation
    function_name: str

class Opcode(Enum):
    LOAD_IMM = auto()     # LOAD_IMM reg, value
    MOV = auto()          # MOV dst, src
    LOAD_CONST = auto()   # LOAD_CONST dst, value (supports any JSON value)
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    MOD = auto()
    NEG = auto()

    EQ = auto()
    GT = auto()
    LT = auto()
    AND = auto()
    OR = auto()
    NOT = auto()

    CLR = auto()         # CLR reg -> set register to 0
    CMP_IMM = auto()     # CMP_IMM dst, src, imm -> dst = -1/0/1 comparing src to immediate
    JNZ = auto()         # JNZ reg, label
    JMP_REL = auto()     # JMP_REL offset (relative jump)
    PUSH = auto()        # PUSH src
    POP = auto()         # POP dst
    ARR_COPY = auto()    # ARR_COPY dst, src, start, length
    IS_OBJ = auto()      # IS_OBJ dst, src
    IS_ARR = auto()      # IS_ARR dst, src
    IS_NULL = auto()     # IS_NULL dst, src
    COALESCE = auto()    # COALESCE dst, lhs, rhs

    MAKE_CELL = auto()   # MAKE_CELL dst, src
    CELL_GET = auto()    # CELL_GET dst, cell
    CELL_SET = auto()    # CELL_SET cell, src
    CLOSURE = auto()     # CLOSURE dst, label, cell1, cell2, ...
    CALL_VALUE = auto()  # CALL_VALUE callee_reg
    BIND_UPVALUE = auto()# BIND_UPVALUE dst_cell, index
    VARARG = auto()      # VARARG dst
    VARARG_FIRST = auto()# VARARG_FIRST dst, src
    RETURN_MULTI = auto()# RETURN_MULTI r1, r2, ...
    RESULT_MULTI = auto()# RESULT_MULTI dst1, dst2, ...
    RESULT_LIST = auto() # RESULT_LIST dst
    LIST_GET = auto()    # LIST_GET dst, src, index
    TABLE_NEW = auto()   # TABLE_NEW dst
    TABLE_SET = auto()   # TABLE_SET table, key, value
    TABLE_GET = auto()   # TABLE_GET dst, table, key
    TABLE_APPEND = auto()# TABLE_APPEND table, value
    TABLE_EXTEND = auto()# TABLE_EXTEND table, values

    JMP = auto()          # JMP label
    JZ = auto()           # JZ reg, label

    LABEL = auto()        # LABEL name

    CALL = auto()         # CALL name
    RETURN = auto()       # RETURN reg
    PARAM = auto()        # PARAM reg
    PARAM_EXPAND = auto() # PARAM_EXPAND reg
    ARG = auto()          # ARG dst
    RESULT = auto()       # RESULT dst

    PRINT = auto()
    HALT = auto()

    # Bitwise operations
    AND_BIT = auto()
    OR_BIT = auto()
    XOR = auto()
    NOT_BIT = auto()
    SHL = auto()
    SHR = auto()
    SAR = auto()
    
        # 数组支持
    ARR_INIT = auto()
    ARR_SET = auto()
    ARR_GET = auto()
    LEN = auto()

    # 结构控制（可视化、调试用）
    STRUCT_IF = auto()
    STRUCT_ELSE = auto()
    STRUCT_ENDIF = auto()
    STRUCT_WHILE = auto()
    STRUCT_ENDWHILE = auto()
    STRUCT_BREAK = auto()

    # (JQ-specific opcodes moved to compiler/jq_bytecode.py)


@dataclass
class Instruction:
    opcode: Opcode
    args: list  # e.g., ['a', 'b'] or ['x', 5]
    debug: InstructionDebug | None = None

    def __str__(self):
        return f"{self.opcode.name} {' '.join(map(str, self.args))}"
