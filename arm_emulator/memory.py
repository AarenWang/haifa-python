"""AArch64 统一字节寻址内存模型。

使用 bytearray 作为底层存储，小端序（little-endian）。
支持 8/16/32/64 位读写，无符号与有符号。
"""

from __future__ import annotations

MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1
MASK16 = (1 << 16) - 1
MASK8 = (1 << 8) - 1


class MemoryError(Exception):
    """内存访问错误。"""


class Memory:
    """统一字节寻址线性内存空间。

    - 底层为 bytearray，小端序
    - 支持 8/16/32/64 位读写
    - 教学版默认不抛对齐异常，但提供 is_aligned 查询
    """

    def __init__(self, size: int = 65536) -> None:
        if size <= 0:
            raise ValueError(f"memory size must be positive, got {size}")
        self._data = bytearray(size)
        self.size = size

    # ---- 边界检查 ----

    def _check_bounds(self, addr: int, length: int) -> None:
        if addr < 0 or addr + length > self.size:
            raise MemoryError(
                f"memory access out of bounds: addr=0x{addr:x}, "
                f"len={length}, size=0x{self.size:x}"
            )

    # ---- 原始字节读写 ----

    def read_bytes(self, addr: int, length: int) -> bytes:
        """读取 length 个字节。"""
        self._check_bounds(addr, length)
        return bytes(self._data[addr : addr + length])

    def write_bytes(self, addr: int, data: bytes | bytearray) -> None:
        """写入字节序列。"""
        self._check_bounds(addr, len(data))
        self._data[addr : addr + len(data)] = data

    # ---- 无符号读 ----

    def read_u8(self, addr: int) -> int:
        self._check_bounds(addr, 1)
        return self._data[addr]

    def read_u16(self, addr: int) -> int:
        return int.from_bytes(self.read_bytes(addr, 2), "little")

    def read_u32(self, addr: int) -> int:
        return int.from_bytes(self.read_bytes(addr, 4), "little")

    def read_u64(self, addr: int) -> int:
        return int.from_bytes(self.read_bytes(addr, 8), "little")

    # ---- 无符号写 ----

    def write_u8(self, addr: int, value: int) -> None:
        self._check_bounds(addr, 1)
        self._data[addr] = value & MASK8

    def write_u16(self, addr: int, value: int) -> None:
        self.write_bytes(addr, (value & MASK16).to_bytes(2, "little"))

    def write_u32(self, addr: int, value: int) -> None:
        self.write_bytes(addr, (value & MASK32).to_bytes(4, "little"))

    def write_u64(self, addr: int, value: int) -> None:
        self.write_bytes(addr, (value & MASK64).to_bytes(8, "little"))

    # ---- 有符号读 ----

    def read_i8(self, addr: int) -> int:
        value = self.read_u8(addr)
        return value - 256 if value & 0x80 else value

    def read_i16(self, addr: int) -> int:
        value = self.read_u16(addr)
        return value - (1 << 16) if value & 0x8000 else value

    def read_i32(self, addr: int) -> int:
        value = self.read_u32(addr)
        return value - (1 << 32) if value & 0x80000000 else value

    def read_i64(self, addr: int) -> int:
        value = self.read_u64(addr)
        return value - (1 << 64) if value & (1 << 63) else value

    # ---- 指令读取 ----

    def read_word(self, addr: int) -> int:
        """读取 4 字节指令（小端序），用于 fetch。"""
        return self.read_u32(addr)

    # ---- 程序加载 ----

    def load_program(self, addr: int, data: bytes | bytearray) -> None:
        """将二进制程序加载到指定地址。"""
        self.write_bytes(addr, data)

    # ---- 对齐查询 ----

    @staticmethod
    def is_aligned(addr: int, alignment: int) -> bool:
        """检查地址是否按 alignment 字节对齐。"""
        return addr % alignment == 0

    # ---- 填充 ----

    def fill(self, addr: int, length: int, value: int = 0) -> None:
        """用 value 填充 [addr, addr+length) 区域。"""
        self._check_bounds(addr, length)
        for i in range(length):
            self._data[addr + i] = value & MASK8

    # ---- 十六进制转储 ----

    def hexdump(self, addr: int, length: int) -> str:
        """生成 [addr, addr+length) 区域的十六进制转储文本。"""
        data = self.read_bytes(addr, length)
        lines = []
        for offset in range(0, len(data), 16):
            chunk = data[offset : offset + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{addr + offset:08x}  {hex_part:<48}  {ascii_part}")
        return "\n".join(lines)
