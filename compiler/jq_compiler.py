from __future__ import annotations

from typing import List

from bytecode import Instruction, Opcode
from jq_ast import Field, Identity, IndexAll, JQNode, Literal, FunctionCall, flatten_pipe

INPUT_REGISTER = "__jq_input"
CURRENT_REGISTER = "__jq_curr"


class JQCompiler:
    """Compile jq AST nodes into bytecode instructions for the BytecodeVM."""

    def __init__(self) -> None:
        self.instructions: List[Instruction] = []
        self._temp_counter = 0
        self._label_counter = 0

    def compile(self, node: JQNode) -> List[Instruction]:
        self.instructions.clear()
        self._temp_counter = 0
        self._label_counter = 0

        # Seed the current register with the input JSON.
        self.instructions.append(Instruction(Opcode.MOV, [CURRENT_REGISTER, INPUT_REGISTER]))

        stages = flatten_pipe(node)
        self._compile_pipeline(stages, CURRENT_REGISTER)
        self.instructions.append(Instruction(Opcode.HALT, []))
        return list(self.instructions)

    def _compile_pipeline(self, stages: List[JQNode], current_reg: str) -> None:
        if not stages:
            self.instructions.append(Instruction(Opcode.PRINT, [current_reg]))
            return

        stage, rest = stages[0], stages[1:]

        if isinstance(stage, Identity):
            self._compile_pipeline(rest, current_reg)
            return

        if isinstance(stage, Literal):
            dest = self._new_temp()
            self.instructions.append(Instruction(Opcode.LOAD_CONST, [dest, stage.value]))
            self._compile_pipeline(rest, dest)
            return

        if isinstance(stage, Field):
            dest = self._eval_expression(stage, current_reg)
            self._compile_pipeline(rest, dest)
            return

        if isinstance(stage, IndexAll):
            source_reg = self._eval_expression(stage.source, current_reg)
            index_reg = self._new_temp()
            length_reg = self._new_temp()
            cond_reg = self._new_temp()
            elem_reg = self._new_temp()
            loop_label = self._new_label("jq_loop")
            end_label = self._new_label("jq_end")

            self.instructions.append(Instruction(Opcode.LOAD_CONST, [index_reg, 0]))
            self.instructions.append(Instruction(Opcode.LEN_VALUE, [length_reg, source_reg]))
            self.instructions.append(Instruction(Opcode.LABEL, [loop_label]))
            self.instructions.append(Instruction(Opcode.LT, [cond_reg, index_reg, length_reg]))
            self.instructions.append(Instruction(Opcode.JZ, [cond_reg, end_label]))
            self.instructions.append(Instruction(Opcode.GET_INDEX, [elem_reg, source_reg, index_reg]))

            self._compile_pipeline(rest, elem_reg)

            self.instructions.append(Instruction(Opcode.ADD, [index_reg, index_reg, "1"]))
            self.instructions.append(Instruction(Opcode.JMP, [loop_label]))
            self.instructions.append(Instruction(Opcode.LABEL, [end_label]))
            return

        if isinstance(stage, FunctionCall):
            if stage.name == "length" and not stage.args:
                dest = self._new_temp()
                self.instructions.append(Instruction(Opcode.LEN_VALUE, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            raise NotImplementedError(f"Unsupported jq function: {stage.name}")

        raise NotImplementedError(f"Unsupported jq construct: {type(stage).__name__}")

    def _new_temp(self) -> str:
        name = f"__jq_tmp{self._temp_counter}"
        self._temp_counter += 1
        return name

    def _new_label(self, prefix: str) -> str:
        name = f"__{prefix}_{self._label_counter}"
        self._label_counter += 1
        return name

    def _eval_expression(self, node: JQNode, base_reg: str) -> str:
        if isinstance(node, Identity):
            return base_reg
        if isinstance(node, Literal):
            dest = self._new_temp()
            self.instructions.append(Instruction(Opcode.LOAD_CONST, [dest, node.value]))
            return dest
        if isinstance(node, Field):
            names: List[str] = []
            source = node
            while isinstance(source, Field):
                names.append(source.name)
                source = source.source

            current = self._eval_expression(source, base_reg)
            for name in reversed(names):
                dest = self._new_temp()
                self.instructions.append(Instruction(Opcode.OBJ_GET, [dest, current, name]))
                current = dest
            return current
        raise NotImplementedError(f"Unsupported expression in jq compiler: {type(node).__name__}")


def compile_to_bytecode(node: JQNode) -> List[Instruction]:
    return JQCompiler().compile(node)


__all__ = ["JQCompiler", "compile_to_bytecode", "INPUT_REGISTER", "CURRENT_REGISTER"]
