from enum import Enum, auto
from dataclasses import dataclass

class Opcode(Enum):
    LOAD_IMM = auto()     # LOAD_IMM reg, value
    MOV = auto()          # MOV dst, src
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


@dataclass
class Instruction:
    opcode: Opcode
    args: list  # e.g., ['a', 'b'] or ['x', 5]

    def __str__(self):
        return f"{self.opcode.name} {' '.join(map(str, self.args))}"
