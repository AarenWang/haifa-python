from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Mapping, Sequence

from .bytecode import SourceLocation


class ArmV9Opcode(Enum):
    # Data movement
    MOV = auto()
    MOVI = auto()
    LDR = auto()
    STR = auto()
    LDRC = auto()
    ADR = auto()

    # Arithmetic and bitwise operations
    ADD = auto()
    SUB = auto()
    MUL = auto()
    SDIV = auto()
    MOD = auto()
    NEG = auto()
    AND = auto()
    ORR = auto()
    EOR = auto()
    LSL = auto()
    LSR = auto()
    ASR = auto()

    # Comparison and condition flags
    CMP = auto()
    CMPI = auto()
    CSET = auto()

    # Control flow
    LABEL = auto()
    B = auto()
    B_EQ = auto()
    B_NE = auto()
    B_LT = auto()
    B_GT = auto()
    BL = auto()
    BR = auto()
    RET = auto()
    HALT = auto()

    # Haifa runtime pseudo-ops
    NEW_TABLE = auto()
    TABLE_GET = auto()
    TABLE_SET = auto()
    NEW_CELL = auto()
    NEW_CLOSURE = auto()
    CELL_GET = auto()
    CELL_SET = auto()
    BIND_UPVALUE = auto()
    PARAM = auto()
    PARAM_EXPAND = auto()
    ARG = auto()
    VARARG = auto()
    VARARG_FIRST = auto()
    LIST_GET = auto()
    CALL_VALUE = auto()
    RETURN_VALUE = auto()
    RETURN_MULTI = auto()
    RESULT = auto()
    RESULT_MULTI = auto()
    RESULT_LIST = auto()
    CALL_RUNTIME = auto()


_DISPLAY_NAMES: Mapping[ArmV9Opcode, str] = {
    ArmV9Opcode.B_EQ: "B.EQ",
    ArmV9Opcode.B_NE: "B.NE",
    ArmV9Opcode.B_LT: "B.LT",
    ArmV9Opcode.B_GT: "B.GT",
}


@dataclass(frozen=True)
class ArmV9Debug:
    """Source/debug metadata for an ARMv9-style instruction."""

    location: SourceLocation | None = None
    function_name: str | None = None
    source_opcode: str | None = None
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.location is not None:
            data["location"] = {
                "file": self.location.file,
                "line": self.location.line,
                "column": self.location.column,
            }
        if self.function_name is not None:
            data["function_name"] = self.function_name
        if self.source_opcode is not None:
            data["source_opcode"] = self.source_opcode
        if self.comment is not None:
            data["comment"] = self.comment
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ArmV9Debug | None:
        if not data:
            return None
        location_data = data.get("location")
        location = None
        if location_data is not None:
            location = SourceLocation(
                str(location_data["file"]),
                int(location_data["line"]),
                int(location_data["column"]),
            )
        return cls(
            location=location,
            function_name=data.get("function_name"),
            source_opcode=data.get("source_opcode"),
            comment=data.get("comment"),
        )


@dataclass(frozen=True)
class ArmV9Instruction:
    opcode: ArmV9Opcode
    args: tuple[Any, ...] = ()
    debug: ArmV9Debug | None = None

    def __str__(self) -> str:
        return format_armv9_instruction(self)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "opcode": self.opcode.name,
            "args": list(self.args),
        }
        if self.debug is not None:
            data["debug"] = self.debug.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ArmV9Instruction:
        return cls(
            ArmV9Opcode[str(data["opcode"])],
            tuple(data.get("args", ())),
            ArmV9Debug.from_dict(data.get("debug")),
        )


def armv9_inst(
    opcode: ArmV9Opcode,
    *args: Any,
    debug: ArmV9Debug | None = None,
) -> ArmV9Instruction:
    return ArmV9Instruction(opcode, tuple(args), debug)


def format_armv9_opcode(opcode: ArmV9Opcode) -> str:
    return _DISPLAY_NAMES.get(opcode, opcode.name)


def format_armv9_instruction(instruction: ArmV9Instruction) -> str:
    opcode = format_armv9_opcode(instruction.opcode)
    if not instruction.args:
        return opcode
    return f"{opcode} {', '.join(_format_arg(arg) for arg in instruction.args)}"


def serialize_armv9_program(
    instructions: Sequence[ArmV9Instruction],
) -> list[dict[str, Any]]:
    return [instruction.to_dict() for instruction in instructions]


def deserialize_armv9_program(
    data: Sequence[Mapping[str, Any]],
) -> list[ArmV9Instruction]:
    return [ArmV9Instruction.from_dict(item) for item in data]


def _format_arg(arg: Any) -> str:
    if isinstance(arg, (tuple, list)) and len(arg) == 2:
        base, offset = arg
        return f"[{base}, {offset}]"
    if isinstance(arg, str):
        return arg
    return repr(arg)
