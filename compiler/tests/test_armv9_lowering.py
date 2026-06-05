import pytest

from compiler.armv9_bytecode import ArmV9Opcode
from compiler.armv9_lowering import lower_to_armv9
from compiler.armv9_vm import HaifaArmV9VM
from compiler.bytecode import Instruction, Opcode
from compiler.bytecode_vm import BytecodeVM
from haifa_lua.runtime import compile_source


def run_bytecode_vm(instructions):
    vm = BytecodeVM(instructions)
    output = vm.run()
    return vm, output


def run_armv9_lowered(instructions, *, stack_size=128):
    result = lower_to_armv9(instructions)
    vm = HaifaArmV9VM(
        result.instructions,
        stack_size=stack_size,
        const_pool=result.const_pool,
    )
    output = vm.run()
    return result, vm, output


def test_lowering_arithmetic_print_matches_bytecode_vm():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["a", 2]),
        Instruction(Opcode.LOAD_IMM, ["b", 3]),
        Instruction(Opcode.ADD, ["sum", "a", "b"]),
        Instruction(Opcode.PRINT, ["sum"]),
        Instruction(Opcode.HALT, []),
    ]

    _, bytecode_output = run_bytecode_vm(instructions)
    result, _, arm_output = run_armv9_lowered(instructions)

    assert bytecode_output == [5]
    assert arm_output == bytecode_output
    assert result.stack_slots == {"a": -1, "b": -2, "sum": -3}
    assert [instruction.opcode for instruction in result.instructions][-2:] == [
        ArmV9Opcode.CALL_RUNTIME,
        ArmV9Opcode.HALT,
    ]


def test_lowering_conditional_branch_matches_bytecode_vm():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["a", 2]),
        Instruction(Opcode.LOAD_IMM, ["b", 3]),
        Instruction(Opcode.LT, ["cond", "a", "b"]),
        Instruction(Opcode.JZ, ["cond", "else"]),
        Instruction(Opcode.LOAD_IMM, ["out", 1]),
        Instruction(Opcode.JMP, ["done"]),
        Instruction(Opcode.LABEL, ["else"]),
        Instruction(Opcode.LOAD_IMM, ["out", 0]),
        Instruction(Opcode.LABEL, ["done"]),
        Instruction(Opcode.PRINT, ["out"]),
        Instruction(Opcode.HALT, []),
    ]

    _, bytecode_output = run_bytecode_vm(instructions)
    _, _, arm_output = run_armv9_lowered(instructions)

    assert bytecode_output == [1]
    assert arm_output == bytecode_output


def test_lowering_load_const_and_debug_metadata():
    instructions = [
        Instruction(Opcode.LOAD_CONST, ["value", "hello"]),
        Instruction(Opcode.PRINT, ["value"]),
        Instruction(Opcode.HALT, []),
    ]

    result, _, arm_output = run_armv9_lowered(instructions)

    assert result.const_pool == ["hello"]
    assert arm_output == ["hello"]
    assert result.instructions[0].opcode == ArmV9Opcode.LDRC
    assert result.instructions[0].debug is not None
    assert result.instructions[0].debug.source_opcode == "LOAD_CONST"


def test_lowering_table_ops_match_bytecode_vm_output():
    instructions = [
        Instruction(Opcode.TABLE_NEW, ["tbl"]),
        Instruction(Opcode.LOAD_CONST, ["key", "answer"]),
        Instruction(Opcode.LOAD_IMM, ["value", 42]),
        Instruction(Opcode.TABLE_SET, ["tbl", "key", "value"]),
        Instruction(Opcode.TABLE_GET, ["out", "tbl", "key"]),
        Instruction(Opcode.PRINT, ["out"]),
        Instruction(Opcode.HALT, []),
    ]

    _, bytecode_output = run_bytecode_vm(instructions)
    result, arm_vm, arm_output = run_armv9_lowered(instructions)

    assert bytecode_output == [42]
    assert arm_output == bytecode_output
    assert ArmV9Opcode.NEW_TABLE in [inst.opcode for inst in result.instructions]
    assert arm_vm.snapshot()["memory"]["heap"] == {1: {"answer": 42}}


def test_lowering_lua_compiled_arithmetic_matches_bytecode_register():
    instructions = list(compile_source("local x = 2 + 3", source_name="<test>"))
    bytecode_vm, _ = run_bytecode_vm(instructions)

    result, arm_vm, _ = run_armv9_lowered(instructions)
    slot = result.stack_slots["L_1_x_3"]
    stack_value = arm_vm.snapshot()["memory"]["stack"][arm_vm.read_reg("FP") + slot]

    assert bytecode_vm.registers["L_1_x_3"] == 5
    assert stack_value == bytecode_vm.registers["L_1_x_3"]


def test_lowering_lua_compiled_table_field_matches_bytecode_register():
    instructions = list(
        compile_source("local t = {a = 42}; local x = t.a", source_name="<test>")
    )
    bytecode_vm, _ = run_bytecode_vm(instructions)

    result, arm_vm, _ = run_armv9_lowered(instructions)
    slot = result.stack_slots["L_1_x_6"]
    snapshot = arm_vm.snapshot()
    stack_value = snapshot["memory"]["stack"][arm_vm.read_reg("FP") + slot]

    assert bytecode_vm.registers["L_1_x_6"] == 42
    assert stack_value == 42
    assert snapshot["memory"]["heap"] == {1: {"a": 42}}


def test_lowering_rejects_unsupported_opcodes():
    with pytest.raises(NotImplementedError, match="DIV"):
        lower_to_armv9([Instruction(Opcode.DIV, ["out", "a", "b"])])
