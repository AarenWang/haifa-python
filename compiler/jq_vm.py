from __future__ import annotations

"""JQ-specific VM facade layer.

Stage 1 decoupling: Provide a JQVM that (for now) reuses the core
BytecodeVM implementation and its handlers, while establishing a separate
entry point for jq_runtime to depend on. In later stages, JQ-specific
handlers will migrate here and be removed from the core VM.
"""

from .bytecode_vm import BytecodeVM


class JQVM(BytecodeVM):
    """VM for jq bytecode. Currently inherits core VM behavior.

    Future work will slim down core VM and move JQ-only handlers here.
    """

    def __init__(self, instructions):
        super().__init__(instructions)
        # Placeholder for JQ-only customizations/dispatch overrides later.


__all__ = ["JQVM"]

