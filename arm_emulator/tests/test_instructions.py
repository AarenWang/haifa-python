"""指令定义与位域工具的单元测试。"""

from __future__ import annotations

import pytest

from arm_emulator.instructions import (
    Condition,
    EncodingFormat,
    ExtendType,
    ImmediateOperand,
    Instruction,
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
    decode_register,
    encode_register,
    extract_bits,
    insert_bits,
    mask_bits,
    sign_extend,
)


# ============================================================
# bit-field 工具函数测试
# ============================================================

class TestExtractBits:
    def test_basic_extract(self):
        assert extract_bits(0b10110, 1, 3) == 0b011

    def test_extract_from_zero(self):
        assert extract_bits(0, 0, 8) == 0

    def test_extract_full_width(self):
        assert extract_bits(0xDEADBEEF, 0, 32) == 0xDEADBEEF

    def test_extract_single_bit(self):
        assert extract_bits(0b1000, 3, 1) == 1
        assert extract_bits(0b1000, 2, 1) == 0


class TestInsertBits:
    def test_basic_insert(self):
        assert insert_bits(0b10000, 0, 3, 0b111) == 0b10111

    def test_insert_clears_old(self):
        assert insert_bits(0b11111, 0, 3, 0b000) == 0b11000

    def test_insert_high_bits(self):
        assert insert_bits(0, 16, 4, 0xF) == 0xF0000

    def test_insert_preserves_surrounding(self):
        assert insert_bits(0b10101010, 2, 4, 0b0000) == 0b10000010


class TestSignExtend:
    def test_positive(self):
        assert sign_extend(0b0111, 4) == 7

    def test_negative(self):
        assert sign_extend(0b1111, 4) == -1

    def test_negative_large(self):
        assert sign_extend(0x80000000, 32) == -(1 << 31)

    def test_positive_max(self):
        assert sign_extend(0x7FFFFFFF, 32) == (1 << 31) - 1

    def test_64bit_negative(self):
        assert sign_extend(1 << 63, 64) == -(1 << 63)

    def test_zero(self):
        assert sign_extend(0, 8) == 0


class TestMaskBits:
    def test_mask_8(self):
        assert mask_bits(8) == 0xFF

    def test_mask_32(self):
        assert mask_bits(32) == 0xFFFFFFFF

    def test_mask_64(self):
        assert mask_bits(64) == (1 << 64) - 1


# ============================================================
# 寄存器编号工具测试
# ============================================================

class TestEncodeRegister:
    def test_encode_x0(self):
        assert encode_register("X0") == 0

    def test_encode_x30(self):
        assert encode_register("X30") == 30

    def test_encode_w15(self):
        assert encode_register("W15") == 15

    def test_encode_xzr(self):
        assert encode_register("XZR") == 31

    def test_encode_wzr(self):
        assert encode_register("WZR") == 31

    def test_encode_sp(self):
        assert encode_register("SP") == 31

    def test_encode_lowercase(self):
        assert encode_register("x5") == 5

    def test_encode_invalid(self):
        with pytest.raises(ValueError, match="cannot encode"):
            encode_register("R0")


class TestDecodeRegister:
    def test_decode_x0(self):
        assert decode_register(0, True) == "X0"

    def test_decode_w0(self):
        assert decode_register(0, False) == "W0"

    def test_decode_x30(self):
        assert decode_register(30, True) == "X30"

    def test_decode_xzr(self):
        assert decode_register(31, True) == "XZR"

    def test_decode_wzr(self):
        assert decode_register(31, False) == "WZR"

    def test_decode_out_of_range(self):
        with pytest.raises(ValueError):
            decode_register(32, True)


# ============================================================
# 条件码枚举测试
# ============================================================

class TestCondition:
    def test_eq_code(self):
        assert Condition.EQ.code == 0x0

    def test_nv_code(self):
        assert Condition.NV.code == 0xF

    def test_from_name_eq(self):
        assert Condition.from_name("EQ") == Condition.EQ

    def test_from_name_hs_is_cs(self):
        assert Condition.from_name("HS") == Condition.CS

    def test_from_name_lo_is_cc(self):
        assert Condition.from_name("LO") == Condition.CC

    def test_from_code(self):
        assert Condition.from_code(0xC) == Condition.GT

    def test_from_name_invalid(self):
        with pytest.raises(ValueError, match="unknown condition"):
            Condition.from_name("XX")

    def test_all_16_conditions(self):
        assert len(list(Condition)) == 16


# ============================================================
# 移位类型枚举测试
# ============================================================

class TestShiftType:
    def test_lsl_code(self):
        assert ShiftType.LSL.value == 0x0

    def test_ror_code(self):
        assert ShiftType.ROR.value == 0x3

    def test_from_name(self):
        assert ShiftType.from_name("ASR") == ShiftType.ASR

    def test_from_code(self):
        assert ShiftType.from_code(1) == ShiftType.LSR


# ============================================================
# 扩展类型枚举测试
# ============================================================

class TestExtendType:
    def test_uxtb_code(self):
        assert ExtendType.UXTB.value == 0x0

    def test_sxtw_code(self):
        assert ExtendType.SXTW.value == 0x6

    def test_from_name(self):
        assert ExtendType.from_name("SXTX") == ExtendType.SXTX


# ============================================================
# 操作数类型测试
# ============================================================

class TestOperands:
    def test_register_operand_str(self):
        op = RegisterOperand(0, True)
        assert str(op) == "X0"
        op32 = RegisterOperand(5, False)
        assert str(op32) == "W5"

    def test_immediate_operand_str(self):
        assert str(ImmediateOperand(42)) == "#42"
        assert str(ImmediateOperand(-1)) == "#-1"

    def test_shifted_operand_no_shift(self):
        op = ShiftedOperand(RegisterOperand(1, True), ShiftType.LSL, 0)
        assert str(op) == "X1"

    def test_shifted_operand_with_shift(self):
        op = ShiftedOperand(RegisterOperand(1, True), ShiftType.LSL, 4)
        assert str(op) == "X1, LSL #4"

    def test_memory_operand_base_only(self):
        op = MemoryOperand(RegisterOperand(0, True))
        assert str(op) == "[X0]"

    def test_memory_operand_with_offset(self):
        op = MemoryOperand(RegisterOperand(0, True), offset=16)
        assert str(op) == "[X0, #16]"

    def test_memory_operand_pre_indexed(self):
        op = MemoryOperand(RegisterOperand(0, True), offset=16, pre_indexed=True)
        assert str(op) == "[X0, #16]!"

    def test_memory_operand_post_indexed(self):
        op = MemoryOperand(RegisterOperand(0, True), offset=16, post_indexed=True)
        assert str(op) == "[X0], #16"

    def test_memory_operand_index_reg(self):
        op = MemoryOperand(RegisterOperand(0, True), index_reg=RegisterOperand(1, True))
        assert str(op) == "[X0, X1]"

    def test_label_operand(self):
        assert str(LabelOperand("loop")) == "loop"


# ============================================================
# 指令数据类测试
# ============================================================

class TestInstruction:
    def test_simple_instruction_str(self):
        inst = Instruction(Mnemonic.ADD, (
            RegisterOperand(0, True),
            RegisterOperand(1, True),
            RegisterOperand(2, True),
        ))
        assert str(inst) == "ADD X0, X1, X2"

    def test_b_cond_instruction_str(self):
        inst = Instruction(
            Mnemonic.B_COND,
            (LabelOperand("loop"),),
            condition=Condition.EQ,
        )
        assert str(inst) == "B.EQ loop"

    def test_halt_instruction_str(self):
        inst = Instruction(Mnemonic.HALT)
        assert str(inst) == "HALT"


# ============================================================
# 编码辅助函数测试
# ============================================================

class TestBuildAddSubImmediate:
    def test_add_x0_x1_0x10(self):
        """ADD X0, X1, #0x10 (64-bit, no flags)."""
        word = build_add_sub_immediate(0, 1, 0x10, is_sub=False, set_flags=False, is_64bit=True)
        # sf=1, op=0, S=0, 100010, sh=0, imm12=0x010, Rn=1, Rd=0
        assert extract_bits(word, 31, 1) == 1   # sf=1
        assert extract_bits(word, 30, 1) == 0   # op=0 (ADD)
        assert extract_bits(word, 29, 1) == 0   # S=0
        assert extract_bits(word, 23, 6) == 0b100010
        assert extract_bits(word, 10, 12) == 0x10
        assert extract_bits(word, 5, 5) == 1     # Rn=X1
        assert extract_bits(word, 0, 5) == 0     # Rd=X0

    def test_subs_w0_w1_1(self):
        """SUBS W0, W1, #1 (32-bit, set flags)."""
        word = build_add_sub_immediate(0, 1, 1, is_sub=True, set_flags=True, is_64bit=False)
        assert extract_bits(word, 31, 1) == 0   # sf=0 (32-bit)
        assert extract_bits(word, 30, 1) == 1   # op=1 (SUB)
        assert extract_bits(word, 29, 1) == 1   # S=1
        assert extract_bits(word, 10, 12) == 1

    def test_add_with_shift(self):
        """ADD X0, X1, #0x1000 (shifted immediate, sh=1)."""
        word = build_add_sub_immediate(0, 1, 1, is_sub=False, set_flags=False, is_64bit=True, shift=True)
        assert extract_bits(word, 22, 1) == 1   # sh=1


class TestBuildMovz:
    def test_movz_x0_0x1234(self):
        """MOVZ X0, #0x1234."""
        word = build_movz(0, 0x1234, hw=0, is_64bit=True)
        assert extract_bits(word, 31, 1) == 1   # sf=1
        assert extract_bits(word, 29, 2) == 0b10  # MOVZ
        assert extract_bits(word, 23, 6) == 0b100101
        assert extract_bits(word, 21, 2) == 0    # hw=0
        assert extract_bits(word, 5, 16) == 0x1234
        assert extract_bits(word, 0, 5) == 0     # Rd=X0

    def test_movz_x0_0x1_lsl16(self):
        """MOVZ X0, #0x1, LSL #16 (hw=1)."""
        word = build_movz(0, 1, hw=1, is_64bit=True)
        assert extract_bits(word, 21, 2) == 1    # hw=1
        assert extract_bits(word, 5, 16) == 1

    def test_movz_32bit(self):
        """MOVZ W0, #42 (32-bit)."""
        word = build_movz(0, 42, hw=0, is_64bit=False)
        assert extract_bits(word, 31, 1) == 0   # sf=0


class TestBuildBranches:
    def test_b_offset_16(self):
        """B +16 (4 instructions forward)."""
        word = build_b(16)
        assert extract_bits(word, 26, 6) == 0b000101  # B opcode
        assert extract_bits(word, 0, 26) == 4  # 16/4 = 4

    def test_b_negative_offset(self):
        """B -8 (2 instructions back)."""
        word = build_b(-8)
        imm26 = extract_bits(word, 0, 26)
        # -8/4 = -2, as 26-bit signed = (1<<26)-2
        assert imm26 == (1 << 26) - 2

    def test_b_unaligned_rejected(self):
        with pytest.raises(ValueError, match="4-byte aligned"):
            build_b(6)

    def test_bl_offset_20(self):
        """BL +20."""
        word = build_bl(20)
        assert extract_bits(word, 26, 6) == 0b100101  # BL opcode
        assert extract_bits(word, 0, 26) == 5  # 20/4

    def test_b_cond_eq_offset_8(self):
        """B.EQ +8."""
        word = build_b_cond(Condition.EQ.code, 8)
        assert extract_bits(word, 0, 4) == 0x0  # EQ
        assert extract_bits(word, 5, 19) == 2   # 8/4 = 2

    def test_b_cond_ne_offset_neg4(self):
        """B.NE -4."""
        word = build_b_cond(Condition.NE.code, -4)
        assert extract_bits(word, 0, 4) == 0x1  # NE
        imm19 = extract_bits(word, 5, 19)
        assert sign_extend(imm19, 19) == -1  # -4/4 = -1
