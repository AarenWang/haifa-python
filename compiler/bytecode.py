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


@dataclass
class Instruction:
    opcode: Opcode
    args: list  # e.g., ['a', 'b'] or ['x', 5]

    def __str__(self):
        return f"{self.opcode.name} {' '.join(map(str, self.args))}"
