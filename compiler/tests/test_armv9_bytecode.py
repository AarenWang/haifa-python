from compiler.armv9_bytecode import (
    ArmV9Debug,
    ArmV9Instruction,
    ArmV9Opcode,
    armv9_inst,
    deserialize_armv9_program,
    format_armv9_instruction,
    format_armv9_opcode,
    serialize_armv9_program,
)
from compiler.bytecode import SourceLocation


def test_format_condition_branch_names():
    assert format_armv9_opcode(ArmV9Opcode.B_EQ) == "B.EQ"
    assert format_armv9_opcode(ArmV9Opcode.B_NE) == "B.NE"
    assert str(ArmV9Instruction(ArmV9Opcode.B_LT, ("done",))) == "B.LT done"


def test_format_instruction_uses_arm_style_operands():
    instruction = armv9_inst(ArmV9Opcode.LDR, "X0", "[FP, -8]")
    assert format_armv9_instruction(instruction) == "LDR X0, [FP, -8]"


def test_format_instruction_handles_structured_memory_operands():
    instruction = armv9_inst(ArmV9Opcode.STR, "X0", ("FP", -1))
    assert format_armv9_instruction(instruction) == "STR X0, [FP, -1]"


def test_instruction_helper_accepts_debug_metadata():
    debug = ArmV9Debug(
        location=SourceLocation("demo.lua", 3, 5),
        function_name="main",
        source_opcode="LOAD_IMM",
        comment="lowered from Haifa bytecode",
    )

    instruction = armv9_inst(ArmV9Opcode.MOVI, "X0", 42, debug=debug)

    assert instruction.args == ("X0", 42)
    assert instruction.debug == debug
    assert str(instruction) == "MOVI X0, 42"


def test_program_serialization_round_trip_preserves_debug_metadata():
    program = [
        armv9_inst(
            ArmV9Opcode.LABEL,
            "main",
            debug=ArmV9Debug(function_name="main"),
        ),
        armv9_inst(
            ArmV9Opcode.MOVI,
            "X0",
            7,
            debug=ArmV9Debug(
                location=SourceLocation("demo.lua", 1, 1),
                source_opcode="LOAD_IMM",
            ),
        ),
        armv9_inst(ArmV9Opcode.HALT),
    ]

    encoded = serialize_armv9_program(program)
    decoded = deserialize_armv9_program(encoded)

    assert decoded == program
    assert encoded[1]["debug"]["location"] == {
        "file": "demo.lua",
        "line": 1,
        "column": 1,
    }


def test_runtime_pseudo_ops_are_part_of_phase_one_contract():
    opcodes = {opcode.name for opcode in ArmV9Opcode}

    assert {
        "NEW_TABLE",
        "TABLE_GET",
        "TABLE_SET",
        "NEW_CELL",
        "NEW_CLOSURE",
        "CELL_GET",
        "CELL_SET",
        "BIND_UPVALUE",
        "PARAM",
        "PARAM_EXPAND",
        "ARG",
        "VARARG",
        "VARARG_FIRST",
        "LIST_GET",
        "CALL_VALUE",
        "RETURN_VALUE",
        "RETURN_MULTI",
        "RESULT",
        "RESULT_MULTI",
        "RESULT_LIST",
        "CALL_RUNTIME",
    }.issubset(opcodes)
