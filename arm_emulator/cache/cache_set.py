from __future__ import annotations

from typing import Sequence

from .cache_line import CacheLine


class CacheSet:
    """Represents one set in an E-way set-associative cache."""

    def __init__(self, associativity: int, block_size: int) -> None:
        if associativity < 1:
            raise ValueError(f"associativity must be >= 1, got {associativity}")
        self.associativity = associativity
        self.block_size = block_size
        self.lines: list[CacheLine] = [
            CacheLine(data=bytearray(block_size)) for _ in range(associativity)
        ]

    def find_line(self, tag: int) -> CacheLine | None:
        """Find a valid line matching the tag (Hit)."""
        for line in self.lines:
            if line.is_hit(tag):
                return line
        return None

    def find_free_line(self) -> CacheLine | None:
        """Find the first invalid line in the set."""
        for line in self.lines:
            if not line.valid:
                return line
        return None

    def find_lru_victim(self) -> CacheLine:
        """Find the least-recently used line for eviction."""
        return min(self.lines, key=lambda line: line.last_access_time)
