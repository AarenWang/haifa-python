"""解码器（反汇编器）的单元测试。"""

from __future__ import annotations

import pytest

from arm_emulator.decoder import DecodeError, decode
from arm_emulator.instructions import (
    Condition,
    ImmediateOperand,
    LabelOperand,
    MemoryOperand,
    Mnemonic,
    RegisterOperand,
    ShiftType,
    ShiftedOperand,
    build_add_sub_immediate,
    build_b,
    build_b_cond,
    build_bl,
    build_movz,
)


# ============================================================
# ADD/SUB 立即数 round-trip
# ============================================================

class TestDecodeAddSubImmediate:
    def test_add_x0_x1_0x10(self):
        word = build_add_sub_immediate(0, 1, 0x10, is_sub=False, set_flags=False, is_64bit=True)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.ADD
        assert inst.operands[0] == RegisterOperand(0, True)
        assert inst.operands[1] == RegisterOperand(1, True)
        assert inst.operands[2] == ImmediateOperand(0x10)

    def test_subs_w0_w1_1(self):
        word = build_add_sub_immediate(0, 1, 1, is_sub=True, set_flags=True, is_64bit=False)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.SUBS
        assert inst.operands[0] == RegisterOperand(0, False)
        assert inst.operands[1] == RegisterOperand(1, False)
        assert inst.operands[2] == ImmediateOperand(1)

    def test_cmp_x0_0x100(self):
        """CMP X0, #0x100 → SUBS XZR, X0, #0x100."""
        word = build_add_sub_immediate(31, 0, 0x100, is_sub=True, set_flags=True, is_64bit=True)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.CMP
        assert inst.operands[0] == RegisterOperand(0, True)
        assert inst.operands[1] == ImmediateOperand(0x100)

    def test_cmn_x0_5(self):
        """CMN X0, #5 → ADDS XZR, X0, #5."""
        word = build_add_sub_immediate(31, 0, 5, is_sub=False, set_flags=True, is_64bit=True)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.CMN

    def test_add_shifted_immediate(self):
        """ADD X0, X1, #0x1000 (shift=1 → actual imm=0x1000)."""
        word = build_add_sub_immediate(0, 1, 1, is_sub=False, set_flags=False, is_64bit=True, shift=True)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.ADD
        assert inst.operands[2] == ImmediateOperand(0x1000)


# ============================================================
# MOVZ/MOVN/MOVK round-trip
# ============================================================

class TestDecodeMovw:
    def test_movz_x0_0x1234(self):
        word = build_movz(0, 0x1234, hw=0, is_64bit=True)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.MOVZ
        assert inst.operands[0] == RegisterOperand(0, True)
        assert inst.operands[1] == ImmediateOperand(0x1234)

    def test_movz_w0_42(self):
        word = build_movz(0, 42, hw=0, is_64bit=False)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.MOVZ
        assert inst.operands[0] == RegisterOperand(0, False)
        assert inst.operands[1] == ImmediateOperand(42)

    def test_movz_lsl16(self):
        word = build_movz(0, 1, hw=1, is_64bit=True)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.MOVZ
        assert inst.operands[0] == RegisterOperand(0, True)
        assert inst.operands[1] == ImmediateOperand(1)


# ============================================================
# 分支指令 round-trip
# ============================================================

class TestDecodeBranches:
    def test_b_offset_16(self):
        word = build_b(16)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.B
        assert inst.operands[0].offset == 16

    def test_b_negative_offset(self):
        word = build_b(-8)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.B
        assert inst.operands[0].offset == -8

    def test_bl_offset_20(self):
        word = build_bl(20)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.BL
        assert inst.operands[0].offset == 20

    def test_b_cond_eq(self):
        word = build_b_cond(Condition.EQ.code, 8)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.B_COND
        assert inst.condition == Condition.EQ
        assert inst.operands[0].offset == 8

    def test_b_cond_ne_negative(self):
        word = build_b_cond(Condition.NE.code, -4)
        inst = decode(word)
        assert inst.mnemonic == Mnemonic.B_COND
        assert inst.condition == Condition.NE
        assert inst.operands[0].offset == -4

    def test_b_cond_all_conditions(self):
        """测试全部 16 种条件码都能正确解码。"""
        for cond in Condition:
            word = build_b_cond(cond.code, 4)
            inst = decode(word)
            assert inst.mnemonic == Mnemonic.B_COND
            assert inst.condition == cond


# ============================================================
# HALT 伪指令
# ============================================================

class TestDecodeHalt:
    def test_halt(self):
        inst = decode(0x00000000)
        assert inst.mnemonic == Mnemonic.HALT
        assert inst.operands == ()


# ============================================================
# 错误处理
# ============================================================

class TestDecodeError:
    def test_undefined_instruction(self):
        # 0xFFFFFFFF 不是合法的 AArch64 指令
        with pytest.raises(DecodeError) as exc_info:
            decode(0xFFFFFFFF)
        assert "0xffffffff" in str(exc_info.value).lower()

    def test_decode_error_contains_word(self):
        with pytest.raises(DecodeError) as exc_info:
            decode(0x12345678)
        assert exc_info.value.word == 0x12345678


# ============================================================
# 解码后指令文本格式
# ============================================================

class TestDecodeInstructionString:
    def test_add_str(self):
        word = build_add_sub_immediate(0, 1, 0x10, is_sub=False, set_flags=False, is_64bit=True)
        inst = decode(word)
        text = str(inst)
        assert "ADD" in text
        assert "X0" in text
        assert "X1" in text

    def test_b_cond_str(self):
        word = build_b_cond(Condition.EQ.code, 8)
        inst = decode(word)
        text = str(inst)
        assert "B.EQ" in text

    def test_movz_str(self):
        word = build_movz(0, 42, hw=0, is_64bit=True)
        inst = decode(word)
        text = str(inst)
        assert "MOVZ" in text
        assert "X0" in text
