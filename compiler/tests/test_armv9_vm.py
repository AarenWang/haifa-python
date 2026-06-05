import pytest

from compiler.armv9_bytecode import ArmV9Opcode, armv9_inst
from compiler.armv9_vm import ArmV9RuntimeError, HaifaArmV9VM


def test_armv9_vm_runs_arithmetic_program():
    program = [
        armv9_inst(ArmV9Opcode.MOVI, "X0", 10),
        armv9_inst(ArmV9Opcode.MOVI, "X1", 3),
        armv9_inst(ArmV9Opcode.ADD, "X2", "X0", "X1"),
        armv9_inst(ArmV9Opcode.SUB, "X3", "X0", "X1"),
        armv9_inst(ArmV9Opcode.HALT),
    ]

    vm = HaifaArmV9VM(program)
    vm.run()

    assert vm.read_reg("X2") == 13
    assert vm.read_reg("X3") == 7
    assert vm.halted is True


def test_armv9_vm_updates_nzcv_and_branches_on_equal():
    program = [
        armv9_inst(ArmV9Opcode.MOVI, "X0", 5),
        armv9_inst(ArmV9Opcode.MOVI, "X1", 5),
        armv9_inst(ArmV9Opcode.CMP, "X0", "X1"),
        armv9_inst(ArmV9Opcode.B_EQ, "equal"),
        armv9_inst(ArmV9Opcode.MOVI, "X2", 0),
        armv9_inst(ArmV9Opcode.B, "done"),
        armv9_inst(ArmV9Opcode.LABEL, "equal"),
        armv9_inst(ArmV9Opcode.MOVI, "X2", 1),
        armv9_inst(ArmV9Opcode.LABEL, "done"),
        armv9_inst(ArmV9Opcode.HALT),
    ]

    vm = HaifaArmV9VM(program)
    vm.run()

    assert vm.read_reg("X2") == 1
    assert vm.nzcv.to_dict() == {"N": False, "Z": True, "C": True, "V": False}


def test_armv9_vm_branches_on_not_equal():
    program = [
        armv9_inst(ArmV9Opcode.MOVI, "X0", 2),
        armv9_inst(ArmV9Opcode.MOVI, "X1", 9),
        armv9_inst(ArmV9Opcode.CMP, "X0", "X1"),
        armv9_inst(ArmV9Opcode.B_NE, "not_equal"),
        armv9_inst(ArmV9Opcode.MOVI, "X2", 0),
        armv9_inst(ArmV9Opcode.B, "done"),
        armv9_inst(ArmV9Opcode.LABEL, "not_equal"),
        armv9_inst(ArmV9Opcode.MOVI, "X2", 1),
        armv9_inst(ArmV9Opcode.LABEL, "done"),
        armv9_inst(ArmV9Opcode.HALT),
    ]

    vm = HaifaArmV9VM(program)
    vm.run()

    assert vm.read_reg("X2") == 1
    assert vm.nzcv.to_dict()["N"] is True
    assert vm.nzcv.to_dict()["Z"] is False


def test_armv9_vm_snapshot_exposes_debugger_state():
    program = [
        armv9_inst(ArmV9Opcode.MOVI, "X0", 12),
        armv9_inst(ArmV9Opcode.HALT),
    ]

    vm = HaifaArmV9VM(program, stack_size=16, const_pool=["hello"])
    vm.step()
    snapshot = vm.snapshot()

    assert snapshot["pc"] == 1
    assert snapshot["registers"]["X0"] == 12
    assert snapshot["registers"]["SP"] == 16
    assert snapshot["registers"]["FP"] == 16
    assert snapshot["registers"]["PC"] == 1
    assert snapshot["nzcv"] == {"N": False, "Z": False, "C": False, "V": False}
    assert snapshot["memory"]["const_pool"] == ["hello"]
    assert len(snapshot["memory"]["stack"]) == 16


def test_armv9_vm_loads_and_stores_stack_slots():
    program = [
        armv9_inst(ArmV9Opcode.MOVI, "X0", 33),
        armv9_inst(ArmV9Opcode.STR, "X0", ("SP", -1)),
        armv9_inst(ArmV9Opcode.MOVI, "X0", 0),
        armv9_inst(ArmV9Opcode.LDR, "X1", ("SP", -1)),
        armv9_inst(ArmV9Opcode.HALT),
    ]

    vm = HaifaArmV9VM(program, stack_size=32)
    vm.run()

    assert vm.read_reg("X1") == 33
    assert vm.snapshot()["memory"]["stack"][31] == 33


def test_armv9_vm_supports_call_frames_and_return():
    program = [
        armv9_inst(ArmV9Opcode.MOVI, "X0", 40),
        armv9_inst(ArmV9Opcode.MOVI, "X1", 2),
        armv9_inst(ArmV9Opcode.BL, "add"),
        armv9_inst(ArmV9Opcode.HALT),
        armv9_inst(ArmV9Opcode.LABEL, "add"),
        armv9_inst(ArmV9Opcode.ADD, "X0", "X0", "X1"),
        armv9_inst(ArmV9Opcode.RET),
    ]

    vm = HaifaArmV9VM(program, stack_size=64)
    vm.step()
    vm.step()
    vm.step()
    snapshot_in_call = vm.snapshot()
    vm.run()

    assert snapshot_in_call["pc"] == 4
    assert snapshot_in_call["frames"] == [
        {
            "label": "add",
            "return_pc": 3,
            "caller_fp": 64,
            "caller_sp": 64,
            "caller_lr": None,
        }
    ]
    assert snapshot_in_call["registers"]["FP"] == 48
    assert snapshot_in_call["registers"]["LR"] == 3
    assert vm.read_reg("X0") == 42
    assert vm.snapshot()["frames"] == []
    assert vm.read_reg("FP") == 64
    assert vm.read_reg("SP") == 64


def test_armv9_vm_runs_recursive_factorial_with_stack_spill():
    program = [
        armv9_inst(ArmV9Opcode.MOVI, "X0", 5),
        armv9_inst(ArmV9Opcode.BL, "fact"),
        armv9_inst(ArmV9Opcode.HALT),
        armv9_inst(ArmV9Opcode.LABEL, "fact"),
        armv9_inst(ArmV9Opcode.MOVI, "X1", 2),
        armv9_inst(ArmV9Opcode.CMP, "X0", "X1"),
        armv9_inst(ArmV9Opcode.B_LT, "base"),
        armv9_inst(ArmV9Opcode.STR, "X0", ("FP", -1)),
        armv9_inst(ArmV9Opcode.MOVI, "X1", 1),
        armv9_inst(ArmV9Opcode.SUB, "X0", "X0", "X1"),
        armv9_inst(ArmV9Opcode.BL, "fact"),
        armv9_inst(ArmV9Opcode.LDR, "X1", ("FP", -1)),
        armv9_inst(ArmV9Opcode.MUL, "X0", "X0", "X1"),
        armv9_inst(ArmV9Opcode.RET),
        armv9_inst(ArmV9Opcode.LABEL, "base"),
        armv9_inst(ArmV9Opcode.MOVI, "X0", 1),
        armv9_inst(ArmV9Opcode.RET),
    ]

    vm = HaifaArmV9VM(program, stack_size=128)
    vm.run()

    assert vm.read_reg("X0") == 120
    assert vm.read_reg("SP") == 128
    assert vm.read_reg("FP") == 128
    assert vm.snapshot()["frames"] == []


def test_armv9_vm_rejects_unknown_registers_and_labels():
    with pytest.raises(ArmV9RuntimeError, match="unknown register"):
        HaifaArmV9VM([armv9_inst(ArmV9Opcode.MOVI, "R0", 1)]).run()

    with pytest.raises(ArmV9RuntimeError, match="unknown label"):
        HaifaArmV9VM([armv9_inst(ArmV9Opcode.B, "missing")]).run()


def test_armv9_vm_rejects_infinite_programs_with_max_steps():
    program = [
        armv9_inst(ArmV9Opcode.LABEL, "loop"),
        armv9_inst(ArmV9Opcode.B, "loop"),
    ]

    with pytest.raises(ArmV9RuntimeError, match="maximum step count exceeded"):
        HaifaArmV9VM(program).run(max_steps=5)
