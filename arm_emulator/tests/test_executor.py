"""执行引擎的单元测试。"""

from __future__ import annotations

import pytest

from arm_emulator.executor import ExecutionError, Executor
from arm_emulator.encoder import assemble
from arm_emulator.registers import MASK64


def run_source(code: str, *, max_steps=10000, trace=False) -> tuple[Executor, list]:
    """汇编并执行，返回 (executor, output)。"""
    result = assemble(code)
    ex = Executor.from_assemble_result(result, trace_enabled=trace)
    output = ex.run(max_steps=max_steps)
    return ex, output


class TestBasicArithmetic:
    def test_add_immediate(self):
        ex, _ = run_source("""
            MOVZ X0, #10
            MOVZ X1, #20
            ADD X2, X0, X1
            HALT
        """)
        assert ex.regs.read_x(2) == 30

    def test_sub_immediate(self):
        ex, _ = run_source("""
            MOVZ X0, #50
            MOVZ X1, #15
            SUB X2, X0, X1
            HALT
        """)
        assert ex.regs.read_x(2) == 35

    def test_add_register(self):
        ex, _ = run_source("""
            MOVZ X0, #5
            MOVZ X1, #7
            ADD X2, X0, X1
            HALT
        """)
        assert ex.regs.read_x(2) == 12

    def test_mul(self):
        ex, _ = run_source("""
            MOVZ X0, #6
            MOVZ X1, #7
            MUL X2, X0, X1
            HALT
        """)
        assert ex.regs.read_x(2) == 42

    def test_subs_sets_flags(self):
        ex, _ = run_source("""
            MOVZ X0, #5
            SUBS X1, X0, #5
            HALT
        """)
        assert ex.regs.read_x(1) == 0
        assert ex.regs.pstate.z is True


class TestCmpAndBranch:
    def test_cmp_equal(self):
        ex, _ = run_source("""
            MOVZ X0, #5
            CMP X0, #5
            HALT
        """)
        assert ex.regs.pstate.z is True

    def test_b_cond_taken(self):
        ex, _ = run_source("""
            MOVZ X0, #1
            CMP X0, #1
            B.EQ skip
            MOVZ X0, #0
            skip:
            HALT
        """)
        assert ex.regs.read_x(0) == 1

    def test_b_cond_not_taken(self):
        ex, _ = run_source("""
            MOVZ X0, #1
            MOVZ X1, #2
            CMP X0, X1
            B.EQ skip
            MOVZ X0, #99
            skip:
            HALT
        """)
        assert ex.regs.read_x(0) == 99


class TestLoop:
    def test_loop_count_100(self):
        ex, _ = run_source("""
            MOVZ X0, #0
            MOVZ X1, #100
            loop:
            SUBS X1, X1, #1
            ADD X0, X0, #1
            B.NE loop
            HALT
        """)
        assert ex.regs.read_x(0) == 100
        assert ex.regs.read_x(1) == 0
        assert ex.regs.pstate.z is True

    def test_loop_sum_1_to_10(self):
        """1+2+...+10 = 55, using register ADD."""
        ex, _ = run_source("""
            MOVZ X0, #0
            MOVZ X1, #10
            loop:
            ADD X0, X0, X1
            SUBS X1, X1, #1
            B.NE loop
            HALT
        """)
        assert ex.regs.read_x(0) == 55

    def test_loop_sum_1_to_100(self):
        """1+2+...+100 = 5050, using register ADD."""
        ex, _ = run_source("""
            MOVZ X0, #0
            MOVZ X1, #100
            loop:
            ADD X0, X0, X1
            SUBS X1, X1, #1
            B.NE loop
            HALT
        """)
        assert ex.regs.read_x(0) == 5050


class TestLogicalOps:
    def test_and(self):
        ex, _ = run_source("""
            MOVZ X0, #0xFF
            MOVZ X1, #0x0F
            AND X2, X0, X1
            HALT
        """)
        assert ex.regs.read_x(2) == 0x0F

    def test_orr(self):
        ex, _ = run_source("""
            MOVZ X0, #0xF0
            MOVZ X1, #0x0F
            ORR X2, X0, X1
            HALT
        """)
        assert ex.regs.read_x(2) == 0xFF

    def test_eor(self):
        ex, _ = run_source("""
            MOVZ X0, #0xFF
            MOVZ X1, #0x0F
            EOR X2, X0, X1
            HALT
        """)
        assert ex.regs.read_x(2) == 0xF0

    def test_mov(self):
        ex, _ = run_source("""
            MOVZ X0, #42
            MOV X1, X0
            HALT
        """)
        assert ex.regs.read_x(1) == 42

    def test_mvn(self):
        ex, _ = run_source("""
            MOVZ X0, #0
            MVN X1, X0
            HALT
        """)
        assert ex.regs.read_x(1) == MASK64


class TestLoadStore:
    def test_str_ldr(self):
        ex, _ = run_source("""
            MOVZ X0, #42
            STR X0, [SP, #-16]
            MOVZ X0, #0
            LDR X1, [SP, #-16]
            HALT
        """)
        assert ex.regs.read_x(1) == 42

    def test_str_ldr_offset_zero(self):
        ex, _ = run_source("""
            MOVZ X0, #99
            STR X0, [SP]
            MOVZ X0, #0
            LDR X1, [SP]
            HALT
        """)
        assert ex.regs.read_x(1) == 99


class TestFunctionCall:
    def test_bl_ret(self):
        ex, _ = run_source("""
            MOVZ X0, #10
            BL func
            HALT
            func:
            ADD X0, X0, #5
            RET
        """)
        assert ex.regs.read_x(0) == 15

    def test_recursive_factorial(self):
        """5! = 120 using recursion."""
        code = """
            MOVZ X0, #5
            BL fact
            HALT

            fact:
            STR X30, [SP, #-16]!
            STR X0,  [SP, #-16]!
            MOVZ X1, #2
            CMP X0, X1
            B.LT base
            SUB X0, X0, #1
            BL fact
            LDR X1, [SP], #16
            MUL X0, X0, X1
            LDR X30, [SP], #16
            RET

            base:
            MOVZ X0, #1
            LDR X0,  [SP], #16
            LDR X30, [SP], #16
            RET
        """
        ex, _ = run_source(code, max_steps=50000)
        assert ex.regs.read_x(0) == 120


class TestCselCset:
    def test_cset_eq(self):
        ex, _ = run_source("""
            MOVZ X0, #5
            CMP X0, #5
            CSET X1, EQ
            HALT
        """)
        assert ex.regs.read_x(1) == 1

    def test_cset_ne(self):
        ex, _ = run_source("""
            MOVZ X0, #5
            CMP X0, #3
            CSET X1, NE
            HALT
        """)
        assert ex.regs.read_x(1) == 1

    def test_csel(self):
        ex, _ = run_source("""
            MOVZ X0, #10
            MOVZ X1, #20
            MOVZ X2, #5
            CMP X2, #3
            CSEL X3, X0, X1, GT
            HALT
        """)
        assert ex.regs.read_x(3) == 10  # GT true -> X0


class TestOverflowFlags:
    def test_adds_overflow(self):
        ex, _ = run_source("""
            MOVZ X0, #0
            MOVK X0, #0xFFFF, LSL #16
            MOVK X0, #0xFFFF, LSL #32
            MOVK X0, #0x7FFF, LSL #48
            ADDS X0, X0, X0
            HALT
        """)
        assert ex.regs.pstate.v is True
        assert ex.regs.pstate.n is True

    def test_subs_no_overflow(self):
        ex, _ = run_source("""
            MOVZ X0, #100
            SUBS X1, X0, #1
            HALT
        """)
        assert ex.regs.pstate.v is False
        assert ex.regs.pstate.n is False


class TestTrace:
    def test_trace_records_steps(self):
        ex, _ = run_source("""
            MOVZ X0, #1
            HALT
        """, trace=True)
        assert len(ex.trace) == 2
        assert ex.trace[0].instruction.mnemonic.name == "MOVZ"
        assert ex.trace[1].instruction.mnemonic.name == "HALT"


class TestErrors:
    def test_infinite_loop_max_steps(self):
        with pytest.raises(ExecutionError, match="maximum step count"):
            run_source("loop:\nB loop\n", max_steps=10)
