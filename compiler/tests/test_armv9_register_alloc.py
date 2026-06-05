from compiler.armv9_register_alloc import (
    ArmV9RegisterAllocationReport,
    analyze_armv9_liveness,
)
from compiler.bytecode import Instruction, Opcode


def test_liveness_tracks_virtual_registers_but_not_constants_or_labels():
    instructions = [
        Instruction(Opcode.LOAD_CONST, ["key", "answer"]),
        Instruction(Opcode.LOAD_IMM, ["value", 42]),
        Instruction(Opcode.TABLE_NEW, ["tbl"]),
        Instruction(Opcode.TABLE_SET, ["tbl", "key", "value"]),
        Instruction(Opcode.JMP, ["done"]),
        Instruction(Opcode.LABEL, ["done"]),
        Instruction(Opcode.TABLE_GET, ["out", "tbl", "key"]),
        Instruction(Opcode.PRINT, ["out"]),
        Instruction(Opcode.HALT, []),
    ]

    liveness = analyze_armv9_liveness(instructions)

    assert liveness.defined_registers == frozenset({"key", "value", "tbl", "out"})
    assert "answer" not in liveness.defined_registers
    assert "done" not in liveness.defined_registers
    assert liveness.uses_by_index[3] == ("tbl", "key", "value")
    assert liveness.uses_by_index[6] == ("tbl", "key")
    assert liveness.last_use == {"tbl": 6, "key": 6, "value": 3, "out": 7}


def test_disabled_register_allocation_report_is_readable():
    report = ArmV9RegisterAllocationReport.disabled()

    assert report.enabled is False
    assert report.readable_text() == "register allocation: disabled (stack-slot-only lowering)"
