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


def test_lowering_closure_cell_counter_matches_bytecode_vm_output():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["val", 1]),
        Instruction(Opcode.MAKE_CELL, ["cell", "val"]),
        Instruction(Opcode.CLOSURE, ["clos", "inc", "cell"]),
        Instruction(Opcode.CALL_VALUE, ["clos"]),
        Instruction(Opcode.RESULT, ["first"]),
        Instruction(Opcode.CALL_VALUE, ["clos"]),
        Instruction(Opcode.RESULT, ["second"]),
        Instruction(Opcode.PRINT, ["first"]),
        Instruction(Opcode.PRINT, ["second"]),
        Instruction(Opcode.HALT, []),
        Instruction(Opcode.LABEL, ["inc"]),
        Instruction(Opcode.BIND_UPVALUE, ["up", "0"]),
        Instruction(Opcode.CELL_GET, ["tmp", "up"]),
        Instruction(Opcode.ADD, ["next", "tmp", "1"]),
        Instruction(Opcode.CELL_SET, ["up", "next"]),
        Instruction(Opcode.RETURN, ["next"]),
    ]

    _, bytecode_output = run_bytecode_vm(instructions)
    result, arm_vm, arm_output = run_armv9_lowered(instructions, stack_size=256)

    assert bytecode_output == [2, 3]
    assert arm_output == bytecode_output
    assert {
        ArmV9Opcode.NEW_CELL,
        ArmV9Opcode.NEW_CLOSURE,
        ArmV9Opcode.CALL_VALUE,
        ArmV9Opcode.BIND_UPVALUE,
        ArmV9Opcode.CELL_GET,
        ArmV9Opcode.CELL_SET,
    }.issubset({instruction.opcode for instruction in result.instructions})
    assert arm_vm.snapshot()["memory"]["heap"][1] == {"type": "cell", "value": 3}


def test_lowering_multi_return_result_list_matches_bytecode_vm_output():
    instructions = [
        Instruction(Opcode.CLOSURE, ["pair_fn", "pair"]),
        Instruction(Opcode.CALL_VALUE, ["pair_fn"]),
        Instruction(Opcode.RESULT, ["first"]),
        Instruction(Opcode.RESULT_MULTI, ["left", "right"]),
        Instruction(Opcode.RESULT_LIST, ["values"]),
        Instruction(Opcode.PRINT, ["first"]),
        Instruction(Opcode.PRINT, ["left"]),
        Instruction(Opcode.PRINT, ["right"]),
        Instruction(Opcode.PRINT, ["values"]),
        Instruction(Opcode.HALT, []),
        Instruction(Opcode.LABEL, ["pair"]),
        Instruction(Opcode.LOAD_IMM, ["a", 7]),
        Instruction(Opcode.LOAD_IMM, ["b", 9]),
        Instruction(Opcode.RETURN_MULTI, ["a", "b"]),
    ]

    _, bytecode_output = run_bytecode_vm(instructions)
    result, arm_vm, arm_output = run_armv9_lowered(instructions, stack_size=256)

    assert bytecode_output == [7, 7, 9, [7, 9]]
    assert arm_output == bytecode_output
    assert {
        ArmV9Opcode.RETURN_MULTI,
        ArmV9Opcode.RESULT,
        ArmV9Opcode.RESULT_MULTI,
        ArmV9Opcode.RESULT_LIST,
    }.issubset({instruction.opcode for instruction in result.instructions})
    assert arm_vm.snapshot()["memory"]["heap"][2] == {
        "type": "multi_return",
        "values": [7, 9],
    }


def test_lowering_vararg_return_expansion_matches_bytecode_vm_output():
    instructions = [
        Instruction(Opcode.CLOSURE, ["collect_fn", "collect"]),
        Instruction(Opcode.LOAD_IMM, ["left_arg", 4]),
        Instruction(Opcode.PARAM, ["left_arg"]),
        Instruction(Opcode.LOAD_IMM, ["right_arg", 5]),
        Instruction(Opcode.PARAM, ["right_arg"]),
        Instruction(Opcode.CALL_VALUE, ["collect_fn"]),
        Instruction(Opcode.RESULT_LIST, ["values"]),
        Instruction(Opcode.PRINT, ["values"]),
        Instruction(Opcode.HALT, []),
        Instruction(Opcode.LABEL, ["collect"]),
        Instruction(Opcode.VARARG, ["args"]),
        Instruction(Opcode.RETURN_MULTI, ["args"]),
    ]

    _, bytecode_output = run_bytecode_vm(instructions)
    result, arm_vm, arm_output = run_armv9_lowered(instructions, stack_size=256)

    assert bytecode_output == [[4, 5]]
    assert arm_output == bytecode_output
    assert {
        ArmV9Opcode.PARAM,
        ArmV9Opcode.VARARG,
        ArmV9Opcode.RETURN_MULTI,
        ArmV9Opcode.RESULT_LIST,
    }.issubset({instruction.opcode for instruction in result.instructions})
    assert arm_vm.snapshot()["memory"]["heap"][2] == {
        "type": "multi_return",
        "values": [4, 5],
    }


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
