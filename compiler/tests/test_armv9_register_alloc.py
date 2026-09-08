from compiler.armv9_bytecode import ArmV9Opcode
from compiler.armv9_lowering import lower_to_armv9
from compiler.armv9_register_alloc import (
    ArmV9LinearScanAllocator,
    ArmV9LiveInterval,
    ArmV9RegisterAllocationReport,
    allocate_armv9_linear_scan,
    analyze_armv9_liveness,
    compute_armv9_live_intervals,
)
from compiler.armv9_vm import HaifaArmV9VM
from compiler.bytecode import Instruction, Opcode
from compiler.bytecode_vm import BytecodeVM


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


def test_compute_armv9_live_intervals_basic():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["a", 10]),  # 0: def a
        Instruction(Opcode.LOAD_IMM, ["b", 20]),  # 1: def b
        Instruction(Opcode.ADD, ["c", "a", "b"]),  # 2: use a, b; def c
        Instruction(Opcode.LOAD_IMM, ["unused", 99]),  # 3: def unused
        Instruction(Opcode.PRINT, ["c"]),  # 4: use c
        Instruction(Opcode.HALT, []),  # 5
    ]

    intervals = compute_armv9_live_intervals(instructions)
    intervals_map = {it.virtual_register: it for it in intervals}

    assert intervals_map["a"].start == 0
    assert intervals_map["a"].end == 2
    assert intervals_map["a"].uses == (2,)

    assert intervals_map["b"].start == 1
    assert intervals_map["b"].end == 2
    assert intervals_map["b"].uses == (2,)

    assert intervals_map["c"].start == 2
    assert intervals_map["c"].end == 4
    assert intervals_map["c"].uses == (4,)

    # Unused register: start == end
    assert intervals_map["unused"].start == 3
    assert intervals_map["unused"].end == 3
    assert intervals_map["unused"].uses == ()


def test_compute_armv9_live_intervals_with_backward_jump():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["sum", 0]),  # 0: def sum
        Instruction(Opcode.LOAD_IMM, ["i", 1]),  # 1: def i
        Instruction(Opcode.LABEL, ["loop"]),  # 2
        Instruction(Opcode.ADD, ["sum", "sum", "i"]),  # 3: use sum, i; def sum
        Instruction(Opcode.LOAD_IMM, ["limit", 10]),  # 4: def limit
        Instruction(Opcode.LT, ["cond", "i", "limit"]),  # 5: use i, limit; def cond
        Instruction(Opcode.JNZ, ["cond", "loop"]),  # 6: backward jump to label loop (idx 2)
        Instruction(Opcode.PRINT, ["sum"]),  # 7: use sum
        Instruction(Opcode.HALT, []),  # 8
    ]

    intervals = compute_armv9_live_intervals(instructions)
    intervals_map = {it.virtual_register: it for it in intervals}

    # sum is used across the loop and at index 7
    assert intervals_map["sum"].start == 0
    assert intervals_map["sum"].end >= 7

    # i is used inside loop (idx 3, 5) and live across backward jump at 6
    assert intervals_map["i"].start == 1
    assert intervals_map["i"].end >= 6


def test_linear_scan_allocates_physical_registers_without_spill():
    # 3 intervals with 2 physical registers, but two intervals do not overlap:
    # a: [0, 2]
    # b: [1, 3]
    # c: [4, 6] -> non-overlapping with a and b, can reuse register!
    intervals = [
        ArmV9LiveInterval(virtual_register="a", start=0, end=2, uses=(2,), spill_weight=0.33),
        ArmV9LiveInterval(virtual_register="b", start=1, end=3, uses=(3,), spill_weight=0.33),
        ArmV9LiveInterval(virtual_register="c", start=4, end=6, uses=(6,), spill_weight=0.33),
    ]

    allocator = ArmV9LinearScanAllocator(allocatable_registers=("X12", "X13"))
    result = allocator.allocate(intervals)

    assert result.spilled == ()
    assert "a" in result.register_map
    assert "b" in result.register_map
    assert "c" in result.register_map
    # a and b overlap, so they must have distinct physical registers
    assert result.register_map["a"] != result.register_map["b"]
    # c starts at 4 after a and b have ended, so it reuses one of their registers
    assert result.register_map["c"] in {"X12", "X13"}


def test_linear_scan_spills_furthest_ending_interval():
    # Available registers: X12, X13 (2 registers).
    # 3 overlapping intervals:
    # long_var: [0, 20] (ends latest)
    # short1: [1, 5]
    # short2: [2, 6]
    intervals = [
        ArmV9LiveInterval(virtual_register="long_var", start=0, end=20, uses=(10, 20), spill_weight=0.1),
        ArmV9LiveInterval(virtual_register="short1", start=1, end=5, uses=(5,), spill_weight=0.2),
        ArmV9LiveInterval(virtual_register="short2", start=2, end=6, uses=(6,), spill_weight=0.2),
    ]

    allocator = ArmV9LinearScanAllocator(allocatable_registers=("X12", "X13"))
    result = allocator.allocate(intervals)

    # long_var should be chosen for spilling because its end point (20) is furthest
    assert "long_var" in result.spilled
    assert "short1" in result.register_map
    assert "short2" in result.register_map


def test_linear_scan_spills_variables_crossing_calls():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["a", 10]),  # 0
        Instruction(Opcode.LOAD_IMM, ["b", 20]),  # 1
        Instruction(Opcode.PARAM, ["b"]),  # 2
        Instruction(Opcode.LOAD_CONST, ["fn", "callee"]),  # 3
        Instruction(Opcode.CALL_VALUE, ["fn"]),  # 4: function call
        Instruction(Opcode.RESULT, ["res"]),  # 5
        Instruction(Opcode.ADD, ["out", "a", "res"]),  # 6: uses a (which spanned across call at 4)
        Instruction(Opcode.PRINT, ["out"]),  # 7
        Instruction(Opcode.HALT, []),  # 8
    ]

    result = allocate_armv9_linear_scan(
        instructions,
        allocatable_registers=("X12", "X13", "X14", "X15"),
    )

    # a is live across CALL_VALUE at index 4, so it must be spilled to protect against caller-save clobber
    assert "a" in result.spilled


def test_linear_scan_report_formatting():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["x", 5]),
        Instruction(Opcode.LOAD_IMM, ["y", 6]),
        Instruction(Opcode.ADD, ["z", "x", "y"]),
        Instruction(Opcode.PRINT, ["z"]),
        Instruction(Opcode.HALT, []),
    ]

    liveness = analyze_armv9_liveness(instructions)
    scan_result = allocate_armv9_linear_scan(instructions, allocatable_registers=("X12", "X13", "X14"))
    report = ArmV9RegisterAllocationReport.linear_scan_report(
        allocated_registers=("X12", "X13", "X14"),
        liveness=liveness,
        scan_result=scan_result,
    )

    text = report.readable_text()
    assert "register allocation: linear-scan" in text
    assert "physical registers: X12, X13, X14" in text
    assert "assigned map:" in text
    assert "live intervals:" in text
    assert "spills: 0" in text


def test_lower_to_armv9_linear_scan_executes_correctly_and_reduces_memory_ops():
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["a", 7]),
        Instruction(Opcode.LOAD_IMM, ["b", 8]),
        Instruction(Opcode.ADD, ["sum", "a", "b"]),
        Instruction(Opcode.MUL, ["product", "sum", "b"]),
        Instruction(Opcode.PRINT, ["product"]),
        Instruction(Opcode.HALT, []),
    ]

    # Run on BytecodeVM
    bvm = BytecodeVM(instructions)
    expected_output = bvm.run()

    # Lower with linear-scan
    lowered = lower_to_armv9(instructions, strategy="linear-scan")
    assert lowered.allocation_report.strategy == "linear-scan"
    assert lowered.allocation_report.spills == 0
    assert lowered.allocation_report.loads_elided > 0
    assert lowered.allocation_report.stores_elided > 0

    # Execute on HaifaArmV9VM
    vm = HaifaArmV9VM(
        lowered.instructions,
        stack_size=64,
        const_pool=lowered.const_pool,
    )
    output = vm.run()

    assert output == expected_output == [120]

    # Verify no LDR/STR instructions were emitted for this straight-line code since all fit in registers
    memory_ops = [
        inst for inst in lowered.instructions
        if inst.opcode in {ArmV9Opcode.LDR, ArmV9Opcode.STR}
    ]
    assert len(memory_ops) == 0


def test_lower_to_armv9_linear_scan_handles_spill_execution():
    # Program using 5 concurrent variables, but only 4 allocatable registers:
    # All 5 variables (v1..v5) live until the final sum computation.
    instructions = [
        Instruction(Opcode.LOAD_IMM, ["v1", 1]),
        Instruction(Opcode.LOAD_IMM, ["v2", 2]),
        Instruction(Opcode.LOAD_IMM, ["v3", 3]),
        Instruction(Opcode.LOAD_IMM, ["v4", 4]),
        Instruction(Opcode.LOAD_IMM, ["v5", 5]),
        Instruction(Opcode.ADD, ["t1", "v1", "v2"]),
        Instruction(Opcode.ADD, ["t2", "t1", "v3"]),
        Instruction(Opcode.ADD, ["t3", "t2", "v4"]),
        Instruction(Opcode.ADD, ["total", "t3", "v5"]),
        Instruction(Opcode.PRINT, ["total"]),
        Instruction(Opcode.HALT, []),
    ]

    bvm = BytecodeVM(instructions)
    expected_output = bvm.run()

    lowered = lower_to_armv9(instructions, strategy="linear-scan")
    assert lowered.allocation_report.spills > 0

    vm = HaifaArmV9VM(
        lowered.instructions,
        stack_size=64,
        const_pool=lowered.const_pool,
    )
    output = vm.run()

    assert output == expected_output == [15]
