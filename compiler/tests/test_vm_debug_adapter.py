from compiler.armv9_bytecode import ArmV9Opcode, armv9_inst
from compiler.armv9_vm import HaifaArmV9VM
from compiler.bytecode import Instruction, InstructionDebug, Opcode, SourceLocation
from compiler.bytecode_vm import BytecodeVM
from compiler.vm_debug_adapter import (
    ArmV9VMDebugAdapter,
    BytecodeVMDebugAdapter,
    create_debug_adapter,
)
from compiler.vm_events import CoroutineCreated


def test_bytecode_debug_adapter_exports_unified_snapshot_without_draining_events():
    debug = InstructionDebug(SourceLocation("demo.lua", 1, 1), "<chunk>")
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["value", 41], debug),
        Instruction(Opcode.PUSH, ["value"], debug),
        Instruction(Opcode.PARAM, ["value"], debug),
        Instruction(Opcode.CALL, ["inc"], debug),
        Instruction(Opcode.RESULT, ["out"], debug),
        Instruction(Opcode.PRINT, ["out"], debug),
        Instruction(Opcode.HALT, [], debug),
        Instruction(Opcode.LABEL, ["inc"], debug),
        Instruction(Opcode.ARG, ["arg"], debug),
        Instruction(Opcode.LOAD_IMM, ["one", 1], debug),
        Instruction(Opcode.ADD, ["next", "arg", "one"], debug),
        Instruction(Opcode.RETURN, ["next"], debug),
    ]
    vm = BytecodeVM(instructions)
    vm.index_labels()
    vm.emit_event(CoroutineCreated(1, None, "<chunk>", [], 0.0))

    for _ in range(4):
        vm.step()

    adapter = BytecodeVMDebugAdapter(vm)
    snapshot = adapter.snapshot()

    assert snapshot.vm_kind == "bytecode"
    assert snapshot.pc == 7
    assert snapshot.current_instruction().opcode == "LABEL"
    assert snapshot.instructions[0].text == "LOAD_IMM value 41"
    assert snapshot.instructions[0].debug == {
        "location": {"file": "demo.lua", "line": 1, "column": 1},
        "function_name": "<chunk>",
    }
    assert snapshot.registers["value"] == 41
    assert snapshot.memory_sections["stack"] == [41]
    assert snapshot.memory_sections["param_stack"] == [41]
    assert snapshot.call_stack == [
        {
            "return_pc": 4,
            "param_stack": [],
            "registers": {"value": 41},
            "upvalues": [],
            "pending_params": [],
            "caller_debug": {
                "location": {"file": "demo.lua", "line": 1, "column": 1},
                "function_name": "<chunk>",
            },
        }
    ]
    assert snapshot.output == []
    assert snapshot.events == [
        {
            "coroutine_id": 1,
            "parent_id": None,
            "function_name": "<chunk>",
            "args": [],
            "timestamp": 0.0,
            "type": "CoroutineCreated",
        }
    ]
    assert len(vm.drain_events()) == 1


def test_bytecode_debug_adapter_tracks_output_and_return_values_after_run():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["value", 5]),
        Instruction(Opcode.PRINT, ["value"]),
        Instruction(Opcode.RETURN, ["value"]),
    ]
    vm = BytecodeVM(instructions)
    vm.run()

    snapshot = create_debug_adapter(vm).snapshot()

    assert snapshot.vm_kind == "bytecode"
    assert snapshot.output == [5]
    assert snapshot.extra["last_event"] == "halt"
    assert snapshot.extra["return_value"] == 5
    assert snapshot.extra["last_return"] == [5]


def test_armv9_debug_adapter_exports_registers_memory_and_live_frame():
    program = [
        armv9_inst(ArmV9Opcode.MOVI, "X0", 7),
        armv9_inst(ArmV9Opcode.NEW_CELL, "X1", "X0"),
        armv9_inst(ArmV9Opcode.NEW_CLOSURE, "X2", "inner", "X1"),
        armv9_inst(ArmV9Opcode.CALL_VALUE, "X2"),
        armv9_inst(ArmV9Opcode.HALT),
        armv9_inst(ArmV9Opcode.LABEL, "inner"),
        armv9_inst(ArmV9Opcode.BIND_UPVALUE, "X3", 0),
        armv9_inst(ArmV9Opcode.CELL_GET, "X4", "X3"),
        armv9_inst(ArmV9Opcode.RETURN_VALUE, "X4"),
    ]
    vm = HaifaArmV9VM(
        program,
        stack_size=64,
        const_pool=["constant"],
        globals={"print": "builtin"},
    )

    for _ in range(4):
        vm.step()

    snapshot = ArmV9VMDebugAdapter(vm).snapshot()

    assert snapshot.vm_kind == "armv9"
    assert snapshot.pc == 5
    assert snapshot.current_instruction().text == "LABEL inner"
    assert snapshot.registers["X0"] == 7
    assert snapshot.registers["X1"] == "heap:1"
    assert snapshot.registers["X2"] == "heap:2"
    assert snapshot.registers["NZCV"] == {
        "N": False,
        "Z": False,
        "C": False,
        "V": False,
    }
    assert snapshot.memory_sections["const_pool"] == ["constant"]
    assert len(snapshot.memory_sections["stack"]) == 64
    assert snapshot.memory_sections["heap"][1] == {"type": "cell", "value": 7}
    assert snapshot.memory_sections["heap"][2] == {
        "type": "closure",
        "label": "inner",
        "upvalues": ["heap:1"],
    }
    assert snapshot.memory_sections["globals"] == {"print": "builtin"}
    assert snapshot.call_stack == [
        {
            "label": "inner",
            "return_pc": 4,
            "caller_fp": 64,
            "caller_sp": 64,
            "caller_lr": None,
            "caller_upvalues": [],
            "caller_param_stack": [],
            "caller_pending_params": [],
        }
    ]
    assert snapshot.extra["frames"] == snapshot.call_stack
    assert snapshot.extra["upvalues"] == ["heap:1"]
    assert snapshot.extra["last_return"] == []


def test_armv9_debug_adapter_tracks_last_return_and_output_after_run():
    program = [
        armv9_inst(ArmV9Opcode.NEW_CLOSURE, "X0", "answer"),
        armv9_inst(ArmV9Opcode.CALL_VALUE, "X0"),
        armv9_inst(ArmV9Opcode.RESULT, "X1"),
        armv9_inst(ArmV9Opcode.CALL_RUNTIME, "print", "X1"),
        armv9_inst(ArmV9Opcode.HALT),
        armv9_inst(ArmV9Opcode.LABEL, "answer"),
        armv9_inst(ArmV9Opcode.MOVI, "X2", 42),
        armv9_inst(ArmV9Opcode.RETURN_VALUE, "X2"),
    ]
    vm = HaifaArmV9VM(program, stack_size=64)
    vm.run()

    snapshot = create_debug_adapter(vm).snapshot()
    payload = snapshot.to_dict()

    assert snapshot.vm_kind == "armv9"
    assert snapshot.output == [42]
    assert snapshot.extra["halted"] is True
    assert snapshot.extra["last_return"] == [42]
    assert snapshot.extra["return_value"] == 42
    assert snapshot.call_stack == []
    assert payload["instructions"][0]["opcode"] == "NEW_CLOSURE"
    assert payload["registers"]["NZCV"] == {
        "N": False,
        "Z": False,
        "C": False,
        "V": False,
    }


def test_create_debug_adapter_rejects_unknown_vm_shape():
    try:
        create_debug_adapter(object())
    except TypeError as exc:
        assert "unsupported VM type" in str(exc)
    else:
        raise AssertionError("expected TypeError")
