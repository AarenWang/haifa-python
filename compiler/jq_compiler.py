from __future__ import annotations

from typing import List

from bytecode import Instruction, Opcode
from jq_ast import Field, Identity, JQNode, Literal, flatten_pipe

INPUT_REGISTER = "__jq_input"
CURRENT_REGISTER = "__jq_curr"


class JQCompiler:
    """Compile jq AST nodes into bytecode instructions for the BytecodeVM."""

    def __init__(self) -> None:
        self.instructions: List[Instruction] = []
        self._temp_counter = 0

    def compile(self, node: JQNode) -> List[Instruction]:
        self.instructions.clear()
        self._temp_counter = 0

        # Seed the current register with the input JSON.
        self.instructions.append(Instruction(Opcode.MOV, [CURRENT_REGISTER, INPUT_REGISTER]))

        stages = flatten_pipe(node)
        current_reg = CURRENT_REGISTER
        for stage in stages:
            current_reg = self._compile_stage(stage, current_reg)

        self.instructions.append(Instruction(Opcode.PRINT, [current_reg]))
        self.instructions.append(Instruction(Opcode.HALT, []))
        return list(self.instructions)

    def _compile_stage(self, node: JQNode, current_reg: str) -> str:
        if isinstance(node, Identity):
            return current_reg
        if isinstance(node, Field):
            src_reg = self._compile_stage(node.source, current_reg)
            dest = self._new_temp()
            self.instructions.append(Instruction(Opcode.OBJ_GET, [dest, src_reg, node.name]))
            return dest
        if isinstance(node, Literal):
            dest = self._new_temp()
            self.instructions.append(Instruction(Opcode.LOAD_CONST, [dest, node.value]))
            return dest
        raise NotImplementedError(f"Unsupported jq construct: {type(node).__name__}")

    def _new_temp(self) -> str:
        name = f"__jq_tmp{self._temp_counter}"
        self._temp_counter += 1
        return name


def compile_to_bytecode(node: JQNode) -> List[Instruction]:
    return JQCompiler().compile(node)


__all__ = ["JQCompiler", "compile_to_bytecode", "INPUT_REGISTER", "CURRENT_REGISTER"]
