from enum import Enum, auto
from dataclasses import dataclass

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

    JMP = auto()          # JMP label
    JZ = auto()           # JZ reg, label

    LABEL = auto()        # LABEL name

    OBJ_GET = auto()      # OBJ_GET dst, src, key
    GET_INDEX = auto()    # GET_INDEX dst, src, index
    LEN_VALUE = auto()    # LEN_VALUE dst, src

    PUSH_EMIT = auto()    # PUSH_EMIT target_reg
    POP_EMIT = auto()     # POP_EMIT
    EMIT = auto()         # EMIT value_reg

    OBJ_SET = auto()      # OBJ_SET obj_reg, key, value_reg
    FLATTEN = auto()      # FLATTEN dst, src
    REDUCE = auto()       # REDUCE dst, src, op, init_reg?

    CALL = auto()         # CALL name
    RETURN = auto()       # RETURN reg
    PARAM = auto()        # PARAM reg
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

    # jq core filters (Milestone 3)
    KEYS = auto()         # KEYS dst, src
    HAS = auto()          # HAS dst, container, needle
    CONTAINS = auto()     # CONTAINS dst, container, needle
    JOIN = auto()         # JOIN dst, array, sep
    REVERSE = auto()      # REVERSE dst, value
    FIRST = auto()        # FIRST dst, value
    LAST = auto()         # LAST dst, value
    ANY = auto()          # ANY dst, value
    ALL = auto()          # ALL dst, value
    AGG_ADD = auto()      # AGG_ADD dst, value (array aggregation)

    # Sorting and aggregation family (Milestone 4)
    SORT = auto()         # SORT dst, src
    SORT_BY = auto()      # SORT_BY dst, src, keys_buf
    UNIQUE = auto()       # UNIQUE dst, src
    UNIQUE_BY = auto()    # UNIQUE_BY dst, src, keys_buf
    MIN = auto()          # MIN dst, src
    MAX = auto()          # MAX dst, src
    MIN_BY = auto()       # MIN_BY dst, src, keys_buf
    MAX_BY = auto()       # MAX_BY dst, src, keys_buf
    GROUP_BY = auto()     # GROUP_BY dst, src, keys_buf


@dataclass
class Instruction:
    opcode: Opcode
    args: list  # e.g., ['a', 'b'] or ['x', 5]

    def __str__(self):
        return f"{self.opcode.name} {' '.join(map(str, self.args))}"
