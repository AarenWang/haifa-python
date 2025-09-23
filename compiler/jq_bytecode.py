from __future__ import annotations

"""JQOpcode placeholder for future separation.

For now, alias to the core Opcode to preserve compatibility while
gradually migrating the jq compiler to emit JQOpcode.
"""

from .bytecode import Opcode as JQOpcode, Instruction

__all__ = ["JQOpcode", "Instruction"]

