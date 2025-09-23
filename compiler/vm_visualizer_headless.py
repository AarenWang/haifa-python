import json
from typing import Any, List

try:
    from .bytecode_vm import BytecodeVM
except Exception:  # pragma: no cover - fallback
    from compiler.bytecode_vm import BytecodeVM  # type: ignore


class VMVisualizer:
    """Headless (text) VM visualizer for environments without pygame.

    Prints instructions and steps through execution, showing PC, registers,
    emit stack and output after each step. Intended for quick diagnostics.
    """

    def __init__(self, vm: BytecodeVM, max_steps: int | None = None):
        self.vm = vm
        self.max_steps = max_steps

    def _fmt(self, v: Any) -> str:
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)

    def run(self) -> None:  # pragma: no cover - interactive utility
        print("=== Bytecode ===")
        for i, inst in enumerate(self.vm.instructions):
            print(f"{i:03d}: {inst}")
        print("================\n")

        self.vm.index_labels()
        step = 0
        while True:
            if self.max_steps is not None and step >= self.max_steps:
                print("[Stopped] Reached max steps limit.")
                break
            if self.vm.pc >= len(self.vm.instructions):
                print("[Halt] PC at end of program.")
                break
            inst = self.vm.instructions[self.vm.pc]
            print(f"STEP {step} | PC={self.vm.pc} | {inst}")
            ctl = self.vm.step()
            print(f"  REGISTERS: { {k: self._fmt(v) for k, v in sorted(self.vm.registers.items())} }")
            print(f"  EMIT_STACK: {self.vm.emit_stack}")
            print(f"  OUTPUT: {self.vm.output}\n")
            if ctl == "halt":
                print("[Halt] Reached HALT.")
                break
            step += 1

