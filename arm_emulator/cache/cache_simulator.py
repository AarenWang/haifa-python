from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .cache_set import CacheSet
from .report import CacheReport, CacheStats


@dataclass(frozen=True)
class AddressBreakdown:
    """CS:APP address breakdown into Tag, Set index, and Block offset."""

    address: int
    tag: int
    set_index: int
    block_offset: int
    block_aligned_address: int


class CacheSimulator:
    """CS:APP parameterized cache hierarchy simulator (S, E, B, m).

    Parameters:
      num_sets: S = 2^s (number of cache sets)
      associativity: E (lines per set)
      block_size: B = 2^b (bytes per cache block)
      address_bits: m (default 64)
      backing_read: callback(aligned_addr, size) -> bytes to read from memory
      backing_write: callback(aligned_addr, data) -> None to write to memory
    """

    def __init__(
        self,
        *,
        num_sets: int = 32,
        associativity: int = 4,
        block_size: int = 64,
        address_bits: int = 64,
        backing_read: Callable[[int, int], bytes | bytearray] | None = None,
        backing_write: Callable[[int, bytes | bytearray], None] | None = None,
    ) -> None:
        if num_sets < 1 or (num_sets & (num_sets - 1)) != 0:
            raise ValueError(f"num_sets must be a power of 2 >= 1, got {num_sets}")
        if block_size < 1 or (block_size & (block_size - 1)) != 0:
            raise ValueError(f"block_size must be a power of 2 >= 1, got {block_size}")
        if associativity < 1:
            raise ValueError(f"associativity must be >= 1, got {associativity}")

        self.num_sets = num_sets
        self.associativity = associativity
        self.block_size = block_size
        self.address_bits = address_bits

        self.s_bits = (num_sets - 1).bit_length()
        self.b_bits = (block_size - 1).bit_length()
        self.t_bits = address_bits - self.s_bits - self.b_bits
        if self.t_bits < 0:
            raise ValueError("s_bits + b_bits exceeds address_bits")

        self.block_offset_mask = (1 << self.b_bits) - 1
        self.set_index_mask = (1 << self.s_bits) - 1

        self.sets = [CacheSet(associativity, block_size) for _ in range(num_sets)]
        self.stats = CacheStats()
        self.clock = 0

        self.backing_read = backing_read or (lambda addr, sz: bytes(sz))
        self.backing_write = backing_write or (lambda addr, data: None)

    @property
    def total_capacity_bytes(self) -> int:
        return self.num_sets * self.associativity * self.block_size

    def break_down_address(self, address: int) -> AddressBreakdown:
        """Break down a physical address into (tag, set_index, block_offset)."""
        offset = address & self.block_offset_mask
        set_index = (address >> self.b_bits) & self.set_index_mask
        tag = address >> (self.b_bits + self.s_bits)
        aligned = address & ~self.block_offset_mask
        return AddressBreakdown(
            address=address,
            tag=tag,
            set_index=set_index,
            block_offset=offset,
            block_aligned_address=aligned,
        )

    def read(self, address: int, size: int) -> bytes:
        """Read bytes from cache, fetching missing blocks via backing_read."""
        if size <= 0:
            return b""

        bd = self.break_down_address(address)
        # Check if the read crosses cache block boundary
        space_in_block = self.block_size - bd.block_offset
        if size <= space_in_block:
            return self._read_single_block(bd, size)

        # Cross-block read
        first_part = self._read_single_block(bd, space_in_block)
        remaining = self.read(address + space_in_block, size - space_in_block)
        return first_part + remaining

    def _read_single_block(self, bd: AddressBreakdown, size: int) -> bytes:
        target_set = self.sets[bd.set_index]
        line = target_set.find_line(bd.tag)

        if line is not None:
            # Read Hit
            self.clock += 1
            line.last_access_time = self.clock
            self.stats.read_hits += 1
            return bytes(line.data[bd.block_offset : bd.block_offset + size])

        # Read Miss
        self.stats.read_misses += 1
        victim = target_set.find_free_line()
        if victim is None:
            # Need eviction
            victim = target_set.find_lru_victim()
            self.stats.evictions += 1
            if victim.dirty:
                self.stats.dirty_writebacks += 1
                victim_aligned = (victim.tag << (self.s_bits + self.b_bits)) | (bd.set_index << self.b_bits)
                self.backing_write(victim_aligned, bytes(victim.data))

        # Fill block from backing store
        block_data = self.backing_read(bd.block_aligned_address, self.block_size)
        victim.valid = True
        victim.dirty = False
        victim.tag = bd.tag
        victim.data[:] = block_data

        self.clock += 1
        victim.last_access_time = self.clock
        return bytes(victim.data[bd.block_offset : bd.block_offset + size])

    def write(self, address: int, data: bytes | bytearray) -> None:
        """Write bytes to cache using Write-Back + Write-Allocate policy."""
        if not data:
            return

        size = len(data)
        bd = self.break_down_address(address)
        space_in_block = self.block_size - bd.block_offset

        if size <= space_in_block:
            self._write_single_block(bd, data)
            return

        # Cross-block write
        self._write_single_block(bd, data[:space_in_block])
        self.write(address + space_in_block, data[space_in_block:])

    def _write_single_block(self, bd: AddressBreakdown, data: bytes | bytearray) -> None:
        target_set = self.sets[bd.set_index]
        line = target_set.find_line(bd.tag)

        if line is not None:
            # Write Hit
            self.clock += 1
            line.last_access_time = self.clock
            line.data[bd.block_offset : bd.block_offset + len(data)] = data
            line.dirty = True
            self.stats.write_hits += 1
            return

        # Write Miss: Write-Allocate
        self.stats.write_misses += 1
        victim = target_set.find_free_line()
        if victim is None:
            victim = target_set.find_lru_victim()
            self.stats.evictions += 1
            if victim.dirty:
                self.stats.dirty_writebacks += 1
                victim_aligned = (victim.tag << (self.s_bits + self.b_bits)) | (bd.set_index << self.b_bits)
                self.backing_write(victim_aligned, bytes(victim.data))

        # Load block from backing store
        block_data = self.backing_read(bd.block_aligned_address, self.block_size)
        victim.valid = True
        victim.tag = bd.tag
        victim.data[:] = block_data

        # Apply write to cached line
        victim.data[bd.block_offset : bd.block_offset + len(data)] = data
        victim.dirty = True
        self.clock += 1
        victim.last_access_time = self.clock

    def flush(self) -> int:
        """Flush all dirty blocks back to backing memory. Returns number of flushed blocks."""
        flushed_count = 0
        for set_index, target_set in enumerate(self.sets):
            for line in target_set.lines:
                if line.valid and line.dirty:
                    line_aligned = (line.tag << (self.s_bits + self.b_bits)) | (set_index << self.b_bits)
                    self.backing_write(line_aligned, bytes(line.data))
                    line.dirty = False
                    flushed_count += 1
        return flushed_count

    def get_report(self) -> CacheReport:
        """Generate a CacheReport summary."""
        return CacheReport(
            num_sets=self.num_sets,
            associativity=self.associativity,
            block_size=self.block_size,
            total_capacity_bytes=self.total_capacity_bytes,
            stats=self.stats,
        )
