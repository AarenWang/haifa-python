"""寄存器文件与 PSTATE 条件标志的单元测试。"""

from __future__ import annotations

import pytest

from arm_emulator.registers import PSTATE, RegisterFile, MASK64, MASK32


# ============================================================
# PSTATE 标志位测试
# ============================================================

class TestPSTATEAdd:
    """ADDS 标志位更新。"""

    def test_add_no_overflow_64(self):
        ps = PSTATE()
        ps.update_add(1, 2, width=64)
        assert ps.z is False
        assert ps.n is False
        assert ps.c is False
        assert ps.v is False

    def test_add_zero_result(self):
        ps = PSTATE()
        ps.update_add(0, 0, width=64)
        assert ps.z is True
        assert ps.n is False
        assert ps.c is False
        assert ps.v is False

    def test_add_carry_64(self):
        """0xFFFFFFFFFFFFFFFF + 1 → 进位。"""
        ps = PSTATE()
        ps.update_add(MASK64, 1, width=64)
        assert ps.z is True       # 结果为 0
        assert ps.c is True       # 进位
        assert ps.v is False      # 无符号溢出但不影响 V（同号相加）

    def test_add_signed_overflow_positive(self):
        """正 + 正 = 负 → 有符号溢出。"""
        ps = PSTATE()
        sign_bit = 1 << 63
        ps.update_add(sign_bit, sign_bit, width=64)
        assert ps.v is True
        assert ps.n is False  # 结果最高位为 0

    def test_add_signed_overflow_negative(self):
        """负 + 负 = 正 → 有符号溢出。"""
        ps = PSTATE()
        a = (1 << 63) | 1  # 负数
        b = (1 << 63) | 1  # 负数
        ps.update_add(a, b, width=64)
        assert ps.v is True

    def test_add_32_bit_width(self):
        ps = PSTATE()
        ps.update_add(MASK32, 1, width=32)
        assert ps.z is True
        assert ps.c is True


class TestPSTATESub:
    """SUBS 标志位更新。"""

    def test_sub_equal(self):
        ps = PSTATE()
        ps.update_sub(5, 5, width=64)
        assert ps.z is True
        assert ps.c is True   # a >= b → C=1
        assert ps.v is False

    def test_sub_greater(self):
        ps = PSTATE()
        ps.update_sub(10, 3, width=64)
        assert ps.z is False
        assert ps.c is True

    def test_sub_borrow(self):
        ps = PSTATE()
        ps.update_sub(3, 10, width=64)
        assert ps.c is False  # 借位
        assert ps.n is True   # 结果为负

    def test_sub_signed_overflow(self):
        """正 - 负 = 负 → 有符号溢出。"""
        ps = PSTATE()
        sign_bit = 1 << 63
        a = sign_bit - 1   # 最大正数
        b = sign_bit        # 最小负数
        ps.update_sub(a, b, width=64)
        assert ps.v is True

    def test_sub_signed_overflow_2(self):
        """负 - 正 = 正 → 有符号溢出。"""
        ps = PSTATE()
        sign_bit = 1 << 63
        a = sign_bit        # 最小负数
        b = 1               # 正数
        ps.update_sub(a, b, width=64)
        assert ps.v is True


class TestPSTATELogical:
    """逻辑运算标志位更新。"""

    def test_logical_zero(self):
        ps = PSTATE()
        ps.update_logical(0, width=64)
        assert ps.z is True
        assert ps.n is False
        assert ps.c is False
        assert ps.v is False

    def test_logical_negative(self):
        ps = PSTATE()
        ps.update_logical(1 << 63, width=64)
        assert ps.n is True
        assert ps.z is False


class TestPSTATECondition:
    """条件码判断。"""

    def test_eq(self):
        ps = PSTATE()
        ps.z = True
        assert ps.condition_holds("EQ") is True
        assert ps.condition_holds("NE") is False

    def test_ne(self):
        ps = PSTATE()
        ps.z = False
        assert ps.condition_holds("NE") is True
        assert ps.condition_holds("EQ") is False

    def test_cs_cc(self):
        ps = PSTATE()
        ps.c = True
        assert ps.condition_holds("CS") is True
        assert ps.condition_holds("CC") is False

    def test_ge_lt(self):
        ps = PSTATE()
        ps.n = True
        ps.v = True
        assert ps.condition_holds("GE") is True  # n == v
        assert ps.condition_holds("LT") is False

    def test_gt_le(self):
        ps = PSTATE()
        ps.z = False
        ps.n = False
        ps.v = False
        assert ps.condition_holds("GT") is True
        assert ps.condition_holds("LE") is False

    def test_al(self):
        ps = PSTATE()
        assert ps.condition_holds("AL") is True

    def test_invalid_condition(self):
        ps = PSTATE()
        with pytest.raises(ValueError, match="unknown condition"):
            ps.condition_holds("XX")


# ============================================================
# RegisterFile 测试
# ============================================================

class TestRegisterFileReadWrite:
    """64 位 / 32 位读写与截断。"""

    def test_write_read_x(self):
        rf = RegisterFile()
        rf.write_x(0, 42)
        assert rf.read_x(0) == 42

    def test_write_x_truncates_to_64_bit(self):
        rf = RegisterFile()
        rf.write_x(1, MASK64 + 1)
        assert rf.read_x(1) == 0

    def test_write_w_clears_high_32(self):
        rf = RegisterFile()
        rf.write_x(2, 0xDEAD_BEEF_CAFE_BABE)
        rf.write_w(2, 0x1234_5678)
        assert rf.read_x(2) == 0x1234_5678
        assert rf.read_w(2) == 0x1234_5678

    def test_read_w_zero_extends(self):
        rf = RegisterFile()
        rf.write_x(3, 0xFFFF_FFFF_FFFF_FFFF)
        assert rf.read_w(3) == 0xFFFF_FFFF

    def test_write_w_truncates_to_32(self):
        rf = RegisterFile()
        rf.write_w(4, 0x1_0000_0000)
        assert rf.read_w(4) == 0


class TestRegisterFileZeroRegister:
    """XZR / WZR 零寄存器。"""

    def test_read_xzr(self):
        rf = RegisterFile()
        assert rf.read_x(31) == 0

    def test_write_xzr_discarded(self):
        rf = RegisterFile()
        rf.write_x(31, 99)
        assert rf.read_x(31) == 0

    def test_read_wzr(self):
        rf = RegisterFile()
        assert rf.read_w(31) == 0

    def test_write_wzr_discarded(self):
        rf = RegisterFile()
        rf.write_w(31, 99)
        assert rf.read_w(31) == 0


class TestRegisterFileSPPC:
    """SP / PC 寄存器。"""

    def test_sp_read_write(self):
        rf = RegisterFile()
        rf.write_sp(0x1000)
        assert rf.read_sp() == 0x1000

    def test_sp_truncates(self):
        rf = RegisterFile()
        rf.write_sp(MASK64 + 1)
        assert rf.read_sp() == 0

    def test_pc_read_write(self):
        rf = RegisterFile()
        rf.write_pc(0x2000)
        assert rf.read_pc() == 0x2000


class TestRegisterFileParseName:
    """寄存器名称解析。"""

    def test_parse_x_registers(self):
        assert RegisterFile.parse_name("X0") == ("X", 0)
        assert RegisterFile.parse_name("X30") == ("X", 30)
        assert RegisterFile.parse_name("x5") == ("X", 5)

    def test_parse_w_registers(self):
        assert RegisterFile.parse_name("W0") == ("W", 0)
        assert RegisterFile.parse_name("W30") == ("W", 30)

    def test_parse_special(self):
        assert RegisterFile.parse_name("SP") == ("SP", 0)
        assert RegisterFile.parse_name("PC") == ("PC", 0)
        assert RegisterFile.parse_name("XZR") == ("X", 31)
        assert RegisterFile.parse_name("WZR") == ("W", 31)
        assert RegisterFile.parse_name("LR") == ("X", 30)
        assert RegisterFile.parse_name("FP") == ("X", 29)

    def test_parse_invalid(self):
        with pytest.raises(ValueError, match="unknown register name"):
            RegisterFile.parse_name("R0")

    def test_parse_out_of_range(self):
        with pytest.raises(ValueError, match="unknown register name"):
            RegisterFile.parse_name("X31")


class TestRegisterFileByName:
    """按名称读写。"""

    def test_read_write_by_name_x(self):
        rf = RegisterFile()
        rf.write_by_name("X0", 100)
        assert rf.read_by_name("X0") == 100

    def test_read_write_by_name_w(self):
        rf = RegisterFile()
        rf.write_by_name("W1", 0xABCD)
        assert rf.read_by_name("W1") == 0xABCD
        assert rf.read_by_name("X1") == 0xABCD  # 高位被清零

    def test_read_write_by_name_sp(self):
        rf = RegisterFile()
        rf.write_by_name("SP", 0x8000)
        assert rf.read_by_name("SP") == 0x8000

    def test_read_write_by_name_lr(self):
        rf = RegisterFile()
        rf.write_by_name("LR", 0x4000)
        assert rf.read_by_name("LR") == 0x4000
        assert rf.read_by_name("X30") == 0x4000

    def test_read_write_xzr_by_name(self):
        rf = RegisterFile()
        rf.write_by_name("XZR", 42)
        assert rf.read_by_name("XZR") == 0


class TestRegisterFileSnapshot:
    """快照功能。"""

    def test_snapshot_contains_all_registers(self):
        rf = RegisterFile()
        snap = rf.snapshot()
        regs = snap["registers"]
        assert "X0" in regs
        assert "X30" in regs
        assert "SP" in regs
        assert "PC" in regs
        assert "pstate" in snap

    def test_snapshot_pstate(self):
        rf = RegisterFile()
        rf.pstate.z = True
        snap = rf.snapshot()
        assert snap["pstate"]["Z"] is True
