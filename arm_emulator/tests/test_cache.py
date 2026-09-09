import pytest

from arm_emulator.cache import (
    AddressBreakdown,
    CacheLine,
    CacheReport,
    CacheSet,
    CacheSimulator,
    CacheStats,
    CachedMemory,
)
from arm_emulator.encoder import assemble
from arm_emulator.executor import Executor
from arm_emulator.memory import Memory
from arm_emulator.registers import RegisterFile


def test_cache_address_breakdown():
    # S=32 sets (s=5), B=64 bytes (b=6), m=64 bits -> tag = 53 bits
    cache = CacheSimulator(num_sets=32, associativity=4, block_size=64, address_bits=64)
    addr = 0x1234_5678

    bd = cache.break_down_address(addr)

    assert bd.address == addr
    assert bd.block_offset == addr & 0x3F
    assert bd.set_index == (addr >> 6) & 0x1F
    assert bd.tag == addr >> 11
    assert bd.block_aligned_address == addr & ~0x3F


def test_cache_read_hit_and_cold_miss():
    mem = Memory(4096)
    mem.write_bytes(0x100, b"Hello CS:APP Cache!")

    cache = CacheSimulator(
        num_sets=16,
        associativity=2,
        block_size=64,
        backing_read=mem.read_bytes,
        backing_write=mem.write_bytes,
    )

    # 1. First read -> Cold Miss
    data1 = cache.read(0x100, 5)
    assert data1 == b"Hello"
    assert cache.stats.read_misses == 1
    assert cache.stats.read_hits == 0

    # 2. Second read at same address -> Read Hit
    data2 = cache.read(0x100, 5)
    assert data2 == b"Hello"
    assert cache.stats.read_misses == 1
    assert cache.stats.read_hits == 1

    # 3. Third read at nearby address (same 64B block, spatial locality) -> Read Hit
    data3 = cache.read(0x106, 6)
    assert data3 == b"CS:APP"
    assert cache.stats.read_misses == 1
    assert cache.stats.read_hits == 2


def test_cache_lru_eviction():
    # 2-way associative cache: S=2 (s=1), E=2, B=64 (b=6)
    # block size = 64, set stride = 64 * 2 = 128 bytes
    mem = Memory(4096)
    cache = CacheSimulator(
        num_sets=2,
        associativity=2,
        block_size=64,
        backing_read=mem.read_bytes,
        backing_write=mem.write_bytes,
    )

    # Addresses that map to Set 0:
    # addr0 = 0 (set 0, tag 0)
    # addr1 = 128 (set 0, tag 1)
    # addr2 = 256 (set 0, tag 2)
    addr0 = 0
    addr1 = 128
    addr2 = 256

    cache.read(addr0, 8)  # Set 0 Line 0 filled (miss)
    cache.read(addr1, 8)  # Set 0 Line 1 filled (miss)
    assert cache.stats.evictions == 0

    # Access addr0 again so addr0 becomes more recently used than addr1
    cache.read(addr0, 8)  # Hit!

    # Now access addr2: Set 0 is full, must evict LRU victim (which is addr1, not addr0!)
    cache.read(addr2, 8)  # Miss & Eviction
    assert cache.stats.evictions == 1

    # Verify addr0 is STILL in cache (Hit)
    cache.read(addr0, 8)
    assert cache.stats.read_hits == 2

    # Verify addr1 was indeed evicted (Miss)
    cache.read(addr1, 8)
    assert cache.stats.evictions == 2


def test_cache_write_back_and_write_allocate():
    mem = Memory(4096)
    cache = CacheSimulator(
        num_sets=2,
        associativity=1,  # Direct-mapped
        block_size=64,
        backing_read=mem.read_bytes,
        backing_write=mem.write_bytes,
    )

    # Write to 0x100 (maps to set 0, block aligned 0x100)
    addr = 0x100
    cache.write(addr, b"ModifiedData")
    assert cache.stats.write_misses == 1  # Write-allocate brought block into cache
    assert cache.stats.write_hits == 0

    # Read back from cache -> Hit, data is present
    assert cache.read(addr, 12) == b"ModifiedData"
    assert cache.stats.read_hits == 1

    # Backing memory does NOT have the modified data yet (Write-Back)
    assert mem.read_bytes(addr, 12) == b"\x00" * 12

    # Evict the block by accessing another address mapping to set 0 (stride = 2 * 64 = 128)
    conflict_addr = addr + 128
    cache.read(conflict_addr, 4)

    # Dirty writeback occurred during eviction
    assert cache.stats.evictions == 1
    assert cache.stats.dirty_writebacks == 1

    # Now backing memory has received the written data
    assert mem.read_bytes(addr, 12) == b"ModifiedData"


def test_cached_memory_transparent_adapter():
    backing = Memory(8192)
    cached_mem = CachedMemory(backing)

    # Write integer values through adapter
    cached_mem.write_u32(0x200, 0x12345678)
    cached_mem.write_u64(0x300, 0x0102030405060708)

    assert cached_mem.read_u32(0x200) == 0x12345678
    assert cached_mem.read_u64(0x300) == 0x0102030405060708

    assert cached_mem.stats.total_accesses >= 4

    # Flush ensures backing memory is synchronized
    cached_mem.flush()
    assert backing.read_u32(0x200) == 0x12345678
    assert backing.read_u64(0x300) == 0x0102030405060708


def test_spatial_locality_row_major_vs_col_major():
    """CS:APP Chapter 6 classic: Row-major scan has far higher hit rate than column-major scan."""
    rows = 16
    cols = 16
    elem_size = 8  # 8 bytes per uint64
    total_bytes = rows * cols * elem_size  # 2048 bytes

    backing = Memory(8192)

    # 1. Row-major scan (stride = 1 element = 8 bytes)
    # Block size = 64 bytes -> holds 8 elements per block
    # Expected: 1 cold miss every 8 elements -> ~87.5% hit rate
    cache_row = CacheSimulator(num_sets=8, associativity=2, block_size=64, backing_read=backing.read_bytes)
    for r in range(rows):
        for c in range(cols):
            addr = (r * cols + c) * elem_size
            cache_row.read(addr, elem_size)

    # 2. Column-major scan (stride = cols * 8 = 128 bytes)
    # Jumps across sets every iteration, thrashing sets
    cache_col = CacheSimulator(num_sets=8, associativity=2, block_size=64, backing_read=backing.read_bytes)
    for c in range(cols):
        for r in range(rows):
            addr = (r * cols + c) * elem_size
            cache_col.read(addr, elem_size)

    # Assert spatial locality advantage: row-major hit rate >> col-major hit rate
    assert cache_row.stats.hit_rate > cache_col.stats.hit_rate
    assert cache_row.stats.hit_rate >= 0.85
    assert cache_col.stats.hit_rate < 0.20


def test_cache_report_is_readable_for_teaching():
    cache = CacheSimulator(num_sets=16, associativity=4, block_size=64)
    cache.read(0x1000, 4)
    cache.read(0x1000, 4)
    cache.write(0x2000, b"data")

    report = cache.get_report()
    text = report.readable_text()

    assert "=== CS:APP Cache Simulation Report ===" in text
    assert "16 sets, 4-way associative, 64-byte block size" in text
    assert "Overall Hit Rate:" in text
    assert "Estimated Memory Latency:" in text


def test_executor_with_cached_memory_runs_program():
    """Verify arm_emulator.Executor works seamlessly with CachedMemory."""
    # Assembly program that computes sum 1..5 using a loop and stores to memory
    code = """
        MOVZ X0, #0
        MOVZ X1, #1
        MOVZ X2, #5
    loop:
        ADD X0, X0, X1
        ADD X1, X1, #1
        CMP X1, X2
        B.LE loop
        MOVZ X3, #0x200
        STR X0, [X3]
        HALT
    """
    res = assemble(code)
    backing = Memory(4096)
    cached_mem = CachedMemory(backing)
    for i, word in enumerate(res.words):
        cached_mem.write_u32(0 + i * 4, word & 0xFFFFFFFF)

    rf = RegisterFile()
    executor = Executor(rf, cached_mem)
    rf.write_pc(0)
    executor.run()

    # Sum of 1..5 = 15
    assert rf.read_x(0) == 15
    assert cached_mem.read_u64(0x200) == 15

    # Memory accesses took place through cache
    assert cached_mem.stats.total_accesses > 0
    cached_mem.flush()
    assert backing.read_u64(0x200) == 15
