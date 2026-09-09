from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CacheLine:
    """Represents a single cache line (block) in an E-way set-associative cache."""

    valid: bool = False
    dirty: bool = False
    tag: int = 0
    last_access_time: int = 0
    data: bytearray = field(default_factory=bytearray)

    def is_hit(self, tag: int) -> bool:
        """Check if this line is a hit for the given tag."""
        return self.valid and self.tag == tag
