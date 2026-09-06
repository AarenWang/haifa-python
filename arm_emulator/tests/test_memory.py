"""统一字节寻址内存模型的单元测试。"""

from __future__ import annotations

import pytest

from arm_emulator.memory import Memory, MemoryError


# ============================================================
# 基本读写测试
# ============================================================

class TestMemoryUnsignedReadWrite:
    """无符号各宽度读写。"""

    def test_u8_read_write(self):
        mem = Memory(256)
        mem.write_u8(0, 0xAB)
        assert mem.read_u8(0) == 0xAB

    def test_u16_read_write(self):
        mem = Memory(256)
        mem.write_u16(0, 0xBEEF)
        assert mem.read_u16(0) == 0xBEEF

    def test_u32_read_write(self):
        mem = Memory(256)
        mem.write_u32(0, 0xDEADBEEF)
        assert mem.read_u32(0) == 0xDEADBEEF

    def test_u64_read_write(self):
        mem = Memory(256)
        mem.write_u64(0, 0x0123456789ABCDEF)
        assert mem.read_u64(0) == 0x0123456789ABCDEF


class TestMemorySignedRead:
    """有符号读取。"""

    def test_i8_positive(self):
        mem = Memory(256)
        mem.write_u8(0, 0x7F)
        assert mem.read_i8(0) == 127

    def test_i8_negative(self):
        mem = Memory(256)
        mem.write_u8(0, 0x80)
        assert mem.read_i8(0) == -128

    def test_i16_negative(self):
        mem = Memory(256)
        mem.write_u16(0, 0x8000)
        assert mem.read_i16(0) == -32768

    def test_i32_negative(self):
        mem = Memory(256)
        mem.write_u32(0, 0x80000000)
        assert mem.read_i32(0) == -(1 << 31)

    def test_i64_negative(self):
        mem = Memory(256)
        mem.write_u64(0, 1 << 63)
        assert mem.read_i64(0) == -(1 << 63)


# ============================================================
# 小端序测试
# ============================================================

class TestMemoryEndian:
    """小端序字节排列验证。"""

    def test_u16_little_endian(self):
        mem = Memory(256)
        mem.write_u16(0, 0xBEEF)
        assert mem.read_u8(0) == 0xEF   # 低字节在低地址
        assert mem.read_u8(1) == 0xBE   # 高字节在高地址

    def test_u32_little_endian(self):
        mem = Memory(256)
        mem.write_u32(0, 0xDEADBEEF)
        assert mem.read_u8(0) == 0xEF
        assert mem.read_u8(1) == 0xBE
        assert mem.read_u8(2) == 0xAD
        assert mem.read_u8(3) == 0xDE

    def test_u64_little_endian(self):
        mem = Memory(256)
        mem.write_u64(0, 0x0123456789ABCDEF)
        assert mem.read_u8(0) == 0xEF
        assert mem.read_u8(7) == 0x01


# ============================================================
# 边界检查
# ============================================================

class TestMemoryBounds:
    """越界访问检测。"""

    def test_read_out_of_bounds(self):
        mem = Memory(16)
        with pytest.raises(MemoryError, match="out of bounds"):
            mem.read_u32(14)  # 14+4 > 16

    def test_write_out_of_bounds(self):
        mem = Memory(16)
        with pytest.raises(MemoryError, match="out of bounds"):
            mem.write_u64(12, 0)  # 12+8 > 16

    def test_negative_address(self):
        mem = Memory(16)
        with pytest.raises(MemoryError, match="out of bounds"):
            mem.read_u8(-1)

    def test_read_bytes_at_boundary(self):
        mem = Memory(16)
        mem.write_u8(15, 0xFF)
        data = mem.read_bytes(15, 1)
        assert data == b"\xff"


# ============================================================
# 字节序列读写
# ============================================================

class TestMemoryBytes:
    """原始字节序列读写。"""

    def test_write_read_bytes(self):
        mem = Memory(256)
        data = b"Hello, AArch64!"
        mem.write_bytes(0, data)
        assert mem.read_bytes(0, len(data)) == data

    def test_write_bytearray(self):
        mem = Memory(256)
        mem.write_bytes(0, bytearray(b"\x01\x02\x03"))
        assert mem.read_bytes(0, 3) == b"\x01\x02\x03"

    def test_overlapping_writes(self):
        mem = Memory(256)
        mem.write_u32(0, 0x11223344)
        mem.write_u8(2, 0xFF)
        assert mem.read_u32(0) == 0x11FF3344


# ============================================================
# 程序加载与指令读取
# ============================================================

class TestMemoryProgramLoad:
    """程序加载与指令 fetch。"""

    def test_load_program(self):
        mem = Memory(256)
        program = bytes([0xEF, 0xBE, 0xAD, 0xDE, 0x00, 0x00, 0x00, 0x00])
        mem.load_program(0x40, program)
        assert mem.read_word(0x40) == 0xDEADBEEF
        assert mem.read_word(0x44) == 0

    def test_read_word(self):
        mem = Memory(256)
        mem.write_u32(0x10, 0x12345678)
        assert mem.read_word(0x10) == 0x12345678


# ============================================================
# 对齐与工具
# ============================================================

class TestMemoryAlignment:
    """对齐查询。"""

    def test_is_aligned(self):
        assert Memory.is_aligned(0, 4) is True
        assert Memory.is_aligned(8, 4) is True
        assert Memory.is_aligned(3, 4) is False
        assert Memory.is_aligned(0, 8) is True
        assert Memory.is_aligned(4, 8) is False


class TestMemoryFill:
    """填充。"""

    def test_fill_region(self):
        mem = Memory(256)
        mem.fill(0, 8, 0xFF)
        assert mem.read_bytes(0, 8) == b"\xff" * 8

    def test_fill_truncates_value(self):
        mem = Memory(256)
        mem.fill(0, 4, 0x1AB)
        assert mem.read_u8(0) == 0xAB


class TestMemoryHexdump:
    """十六进制转储。"""

    def test_hexdump_basic(self):
        mem = Memory(256)
        mem.write_bytes(0, b"AB")
        dump = mem.hexdump(0, 2)
        assert "41 42" in dump
        assert "AB" in dump

    def test_hexdump_format(self):
        mem = Memory(256)
        mem.write_u32(0, 0xDEADBEEF)
        dump = mem.hexdump(0, 4)
        assert "00000000" in dump
        assert "ef be ad de" in dump


# ============================================================
# 截断测试
# ============================================================

class TestMemoryTruncation:
    """写入值自动截断。"""

    def test_write_u8_truncates(self):
        mem = Memory(16)
        mem.write_u8(0, 0x1AB)
        assert mem.read_u8(0) == 0xAB

    def test_write_u16_truncates(self):
        mem = Memory(16)
        mem.write_u16(0, 0x1BEEF)
        assert mem.read_u16(0) == 0xBEEF

    def test_write_u32_truncates(self):
        mem = Memory(16)
        mem.write_u32(0, 0x1DEADBEEF)
        assert mem.read_u32(0) == 0xDEADBEEF
