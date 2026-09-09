from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CacheStats:
    """Statistics counters for cache accesses."""

    read_hits: int = 0
    read_misses: int = 0
    write_hits: int = 0
    write_misses: int = 0
    evictions: int = 0
    dirty_writebacks: int = 0

    @property
    def total_reads(self) -> int:
        return self.read_hits + self.read_misses

    @property
    def total_writes(self) -> int:
        return self.write_hits + self.write_misses

    @property
    def total_accesses(self) -> int:
        return self.total_reads + self.total_writes

    @property
    def total_hits(self) -> int:
        return self.read_hits + self.write_hits

    @property
    def total_misses(self) -> int:
        return self.read_misses + self.write_misses

    @property
    def hit_rate(self) -> float:
        if self.total_accesses == 0:
            return 0.0
        return self.total_hits / self.total_accesses

    @property
    def miss_rate(self) -> float:
        if self.total_accesses == 0:
            return 0.0
        return self.total_misses / self.total_accesses


@dataclass
class CacheReport:
    """Human-readable teaching report for cache hierarchy simulation."""

    num_sets: int
    associativity: int
    block_size: int
    total_capacity_bytes: int
    stats: CacheStats = field(default_factory=CacheStats)
    hit_latency_cycles: int = 1
    miss_latency_cycles: int = 50

    @property
    def estimated_cycles(self) -> int:
        return (
            self.stats.total_hits * self.hit_latency_cycles
            + self.stats.total_misses * (self.hit_latency_cycles + self.miss_latency_cycles)
            + self.stats.dirty_writebacks * self.miss_latency_cycles
        )

    def readable_text(self) -> str:
        s = self.stats
        lines = [
            "=== CS:APP Cache Simulation Report ===",
            f"Configuration: {self.num_sets} sets, {self.associativity}-way associative, {self.block_size}-byte block size",
            f"Total Capacity: {self.total_capacity_bytes} bytes",
            f"Total Accesses: {s.total_accesses}",
            f"  Reads: {s.total_reads} (Hits: {s.read_hits}, Misses: {s.read_misses})",
            f"  Writes: {s.total_writes} (Hits: {s.write_hits}, Misses: {s.write_misses})",
            f"Overall Hit Rate: {s.hit_rate * 100:.2f}%",
            f"Overall Miss Rate: {s.miss_rate * 100:.2f}%",
            f"Evictions: {s.evictions} (Dirty Writebacks: {s.dirty_writebacks})",
            f"Estimated Memory Latency: {self.estimated_cycles} cycles",
        ]
        return "\n".join(lines)
