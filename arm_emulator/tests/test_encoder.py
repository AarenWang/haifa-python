"""汇编器（编码器）的单元测试。"""

from __future__ import annotations

import pytest

from arm_emulator.encoder import AssembleError, assemble
from arm_emulator.decoder import decode
from arm_emulator.instructions import (
    Condition,
    Mnemonic,
    build_add_sub_immediate,
    build_b,
    build_b_cond,
    build_bl,
    build_movz,
)


class TestAssembleBasic:
    def test_movz(self):
        result = assemble("MOVZ X0, #42")
        assert len(result.words) == 1
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.MOVZ
        assert inst.operands[0].index == 0
        assert inst.operands[1].value == 42

    def test_movz_hex(self):
        result = assemble("MOVZ X0, #0x1234")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.MOVZ
        assert inst.operands[1].value == 0x1234

    def test_add_immediate(self):
        result = assemble("ADD X0, X1, #16")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.ADD
        assert inst.operands[0].index == 0
        assert inst.operands[1].index == 1
        assert inst.operands[2].value == 16

    def test_subs_immediate(self):
        result = assemble("SUBS X0, X1, #1")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.SUBS

    def test_cmp_immediate(self):
        result = assemble("CMP X0, #100")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.CMP
        assert inst.operands[0].index == 0

    def test_halt(self):
        result = assemble("HALT")
        assert result.words[0] == 0

    def test_nop(self):
        result = assemble("NOP")
        assert result.words[0] == 0xD503201F


class TestAssembleRegisterOps:
    def test_add_register(self):
        result = assemble("ADD X0, X1, X2")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.ADD
        assert inst.operands[0].index == 0

    def test_sub_register(self):
        result = assemble("SUB X3, X4, X5")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.SUB

    def test_mov(self):
        result = assemble("MOV X0, X1")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.MOV

    def test_mul(self):
        result = assemble("MUL X0, X1, X2")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.MUL

    def test_and(self):
        result = assemble("AND X0, X1, X2")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.AND


class TestAssembleBranches:
    def test_b_label(self):
        code = """
        B target
        HALT
        target:
        HALT
        """
        result = assemble(code)
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.B
        assert inst.operands[0].offset == 8  # skip 2 instructions (B + HALT)

    def test_bl_label(self):
        code = """
        BL func
        HALT
        func:
        RET
        """
        result = assemble(code)
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.BL
        assert inst.operands[0].offset == 8

    def test_b_cond(self):
        code = """
        B.EQ target
        HALT
        target:
        HALT
        """
        result = assemble(code)
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.B_COND
        assert inst.condition == Condition.EQ
        assert inst.operands[0].offset == 8

    def test_b_cond_ne_backwards(self):
        code = """
        loop:
        SUBS X0, X0, #1
        B.NE loop
        HALT
        """
        result = assemble(code)
        inst = decode(result.words[1])  # B.NE is instruction 1
        assert inst.mnemonic == Mnemonic.B_COND
        assert inst.condition == Condition.NE
        assert inst.operands[0].offset == -4  # back to loop

    def test_ret(self):
        result = assemble("RET")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.RET

    def test_br(self):
        result = assemble("BR X0")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.BR

    def test_blr(self):
        result = assemble("BLR X0")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.BLR


class TestAssembleLoadStore:
    def test_str(self):
        result = assemble("STR X0, [X1]")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.STR

    def test_ldr(self):
        result = assemble("LDR X0, [X1, #16]")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.LDR


class TestAssembleProgram:
    def test_loop_program(self):
        """完整循环程序汇编。"""
        code = """
        MOVZ X0, #0
        MOVZ X1, #100
        loop:
        SUBS X1, X1, #1
        ADD X0, X0, #1
        B.NE loop
        HALT
        """
        result = assemble(code)
        assert len(result.words) == 6
        assert "loop" in result.labels
        # loop 在第 2 条指令处（地址 8）
        assert result.labels["loop"] == 8

    def test_labels_collected(self):
        code = """
        start:
        MOVZ X0, #1
        end:
        HALT
        """
        result = assemble(code)
        assert result.labels["start"] == 0
        assert result.labels["end"] == 4

    def test_comment_semicolon(self):
        code = "MOVZ X0, #42 ; this is a comment"
        result = assemble(code)
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.MOVZ

    def test_comment_double_slash(self):
        code = "MOVZ X0, #42 // comment"
        result = assemble(code)
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.MOVZ

    def test_empty_lines_ignored(self):
        code = """

        MOVZ X0, #1

        HALT

        """
        result = assemble(code)
        assert len(result.words) == 2


class TestAssemblePseudo:
    def test_word(self):
        result = assemble(".word 0xDEADBEEF")
        assert result.words[0] == 0xDEADBEEF

    def test_word_multiple(self):
        result = assemble(".word 1, 2, 3")
        assert result.words == [1, 2, 3]

    def test_skip(self):
        result = assemble(".skip 12")
        assert result.words == [0, 0, 0]

    def test_string(self):
        result = assemble('.string "AB"')
        # "AB" = 0x4241, padded to 4 bytes = 0x00004241
        assert result.words[0] == 0x00004241


class TestAssembleErrors:
    def test_unknown_mnemonic(self):
        with pytest.raises(AssembleError, match="unknown mnemonic"):
            assemble("FOO X0")

    def test_invalid_register(self):
        with pytest.raises(AssembleError, match="invalid register"):
            assemble("MOVZ R0, #1")

    def test_invalid_immediate(self):
        with pytest.raises(AssembleError, match="invalid immediate"):
            assemble("MOVZ X0, #abc")

    def test_duplicate_label(self):
        with pytest.raises(AssembleError, match="duplicate label"):
            assemble("label:\nlabel:\nHALT")

    def test_unknown_label(self):
        with pytest.raises(AssembleError, match="unknown label"):
            assemble("B missing")


class TestAssembleRoundTrip:
    def test_movz_round_trip(self):
        """汇编 → 解码 → 验证。"""
        result = assemble("MOVZ X5, #0xABCD")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.MOVZ
        assert inst.operands[0].index == 5
        assert inst.operands[1].value == 0xABCD

    def test_add_imm_round_trip(self):
        result = assemble("ADD X10, X11, #255")
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.ADD
        assert inst.operands[0].index == 10
        assert inst.operands[1].index == 11
        assert inst.operands[2].value == 255

    def test_b_cond_round_trip(self):
        code = "B.GT target\nHALT\ntarget:\nHALT"
        result = assemble(code)
        inst = decode(result.words[0])
        assert inst.mnemonic == Mnemonic.B_COND
        assert inst.condition == Condition.GT

    def test_full_program_round_trip(self):
        """完整程序汇编后逐条解码验证。"""
        code = """
        MOVZ X0, #0
        MOVZ X1, #10
        loop:
        SUBS X1, X1, #1
        ADD X0, X0, #1
        B.NE loop
        HALT
        """
        result = assemble(code)
        for word in result.words:
            inst = decode(word)
            assert inst is not None
