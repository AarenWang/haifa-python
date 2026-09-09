from __future__ import annotations

from arm_emulator.memory import MASK8, MASK16, MASK32, MASK64, Memory
from .cache_simulator import CacheSimulator
from .report import CacheReport, CacheStats


class CachedMemory(Memory):
    """Memory wrapper that transparently routes accesses through a CacheSimulator.

    Acts as a drop-in replacement for Memory in Executor.
    """

    def __init__(
        self,
        backing_memory: Memory,
        cache: CacheSimulator | None = None,
    ) -> None:
        self.backing_memory = backing_memory
        self.size = backing_memory.size

        if cache is None:
            cache = CacheSimulator(
                num_sets=32,
                associativity=4,
                block_size=64,
                backing_read=self.backing_memory.read_bytes,
                backing_write=self.backing_memory.write_bytes,
            )
        else:
            cache.backing_read = self.backing_memory.read_bytes
            cache.backing_write = self.backing_memory.write_bytes

        self.cache = cache

    @property
    def stats(self) -> CacheStats:
        return self.cache.stats

    def flush(self) -> int:
        """Flush dirty cache blocks to backing memory."""
        return self.cache.flush()

    def get_report(self) -> CacheReport:
        """Get simulation report."""
        return self.cache.get_report()

    # ---- 原始字节读写（通过 Cache） ----

    def read_bytes(self, addr: int, length: int) -> bytes:
        self.backing_memory._check_bounds(addr, length)
        return self.cache.read(addr, length)

    def write_bytes(self, addr: int, data: bytes | bytearray) -> None:
        self.backing_memory._check_bounds(addr, len(data))
        self.cache.write(addr, data)

    # ---- 无符号读 ----

    def read_u8(self, addr: int) -> int:
        raw = self.read_bytes(addr, 1)
        return raw[0]

    def read_u16(self, addr: int) -> int:
        return int.from_bytes(self.read_bytes(addr, 2), "little")

    def read_u32(self, addr: int) -> int:
        return int.from_bytes(self.read_bytes(addr, 4), "little")

    def read_u64(self, addr: int) -> int:
        return int.from_bytes(self.read_bytes(addr, 8), "little")

    # ---- 无符号写 ----

    def write_u8(self, addr: int, value: int) -> None:
        self.write_bytes(addr, bytes([value & MASK8]))

    def write_u16(self, addr: int, value: int) -> None:
        self.write_bytes(addr, (value & MASK16).to_bytes(2, "little"))

    def write_u32(self, addr: int, value: int) -> None:
        self.write_bytes(addr, (value & MASK32).to_bytes(4, "little"))

    def write_u64(self, addr: int, value: int) -> None:
        self.write_bytes(addr, (value & MASK64).to_bytes(8, "little"))

    # ---- 程序直接加载（绕过缓存或写入主存后生效） ----

    def load_program(self, addr: int, data: bytes | bytearray) -> None:
        # Load directly to backing store and write to cache so cache stays coherent
        self.backing_memory.load_program(addr, data)
        self.cache.write(addr, data)

    def fill(self, addr: int, length: int, value: int = 0) -> None:
        self.write_bytes(addr, bytes([value & MASK8] * length))

    def hexdump(self, addr: int, length: int) -> str:
        # Read through cache to reflect any dirty modified data
        data = self.read_bytes(addr, length)
        lines = []
        for offset in range(0, len(data), 16):
            chunk = data[offset : offset + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{addr + offset:08x}  {hex_part:<48}  {ascii_part}")
        return "\n".join(lines)
