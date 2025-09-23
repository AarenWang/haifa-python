from __future__ import annotations

from typing import List

from .jq_bytecode import Instruction, JQOpcode
from .jq_ast import (
    Field,
    Identity,
    IndexAll,
    JQNode,
    Literal,
    FunctionCall,
    ObjectLiteral,
    UnaryOp,
    BinaryOp,
    Index,
    Slice,
    VarRef,
    AsBinding,
    flatten_pipe,
)

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
        self.instructions.append(Instruction(JQOpcode.MOV, [CURRENT_REGISTER, INPUT_REGISTER]))

        stages = flatten_pipe(node)
        self._compile_pipeline(stages, CURRENT_REGISTER)
        self.instructions.append(Instruction(JQOpcode.HALT, []))
        return list(self.instructions)

    def _compile_pipeline(self, stages: List[JQNode], current_reg: str) -> None:
        if not stages:
            self.instructions.append(Instruction(JQOpcode.EMIT, [current_reg]))
            return

        stage, rest = stages[0], stages[1:]

        if isinstance(stage, Identity):
            self._compile_pipeline(rest, current_reg)
            return

        if isinstance(stage, Literal):
            dest = self._new_temp()
            self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [dest, stage.value]))
            self._compile_pipeline(rest, dest)
            return

        if isinstance(stage, Field):
            dest = self._eval_expression(stage, current_reg)
            self._compile_pipeline(rest, dest)
            return

        if isinstance(stage, ObjectLiteral):
            dest = self._eval_expression(stage, current_reg)
            self._compile_pipeline(rest, dest)
            return
        if isinstance(stage, AsBinding):
            value_reg = self._eval_expression(stage.source, current_reg)
            var_reg = self._var_reg(stage.name)
            self.instructions.append(Instruction(JQOpcode.MOV, [var_reg, value_reg]))
            self._compile_pipeline(rest, current_reg)
            return
        # Generic expression stage limited to expression nodes
        if isinstance(stage, (UnaryOp, BinaryOp, Index, Slice, VarRef)):
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

            self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [index_reg, 0]))
            self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [length_reg, source_reg]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [loop_label]))
            self.instructions.append(Instruction(JQOpcode.LT, [cond_reg, index_reg, length_reg]))
            self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, end_label]))
            self.instructions.append(Instruction(JQOpcode.GET_INDEX, [elem_reg, source_reg, index_reg]))

            self._compile_pipeline(rest, elem_reg)

            self.instructions.append(Instruction(JQOpcode.ADD, [index_reg, index_reg, "1"]))
            self.instructions.append(Instruction(JQOpcode.JMP, [loop_label]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [end_label]))
            return

        if isinstance(stage, FunctionCall):
            # Milestone 6: string/regex tools
            if stage.name == "tostring" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.TOSTRING, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "tonumber" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.TONUMBER, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "split" and len(stage.args) == 1:
                sep_reg = self._eval_expression(stage.args[0], current_reg)
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.SPLIT, [dest, current_reg, sep_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "gsub" and len(stage.args) == 2:
                pat_reg = self._eval_expression(stage.args[0], current_reg)
                repl_reg = self._eval_expression(stage.args[1], current_reg)
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.GSUB, [dest, current_reg, pat_reg, repl_reg]))
                self._compile_pipeline(rest, dest)
                return
            # Milestone 4: sort & aggregation
            if stage.name == "sort" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.SORT, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "sort_by" and len(stage.args) == 1:
                array_reg = self._eval_expression(Identity(), current_reg)
                keys_buf = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [keys_buf, []]))
                # iterate items
                index_reg = self._new_temp()
                length_reg = self._new_temp()
                cond_reg = self._new_temp()
                elem_reg = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [index_reg, 0]))
                self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [length_reg, array_reg]))
                loop_label = self._new_label("jq_sort_by_loop")
                end_label = self._new_label("jq_sort_by_end")
                self.instructions.append(Instruction(JQOpcode.LABEL, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LT, [cond_reg, index_reg, length_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, end_label]))
                self.instructions.append(Instruction(JQOpcode.GET_INDEX, [elem_reg, array_reg, index_reg]))
                # compute key for element
                key_reg = self._eval_expression(stage.args[0], elem_reg)
                self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [keys_buf]))
                self.instructions.append(Instruction(JQOpcode.EMIT, [key_reg]))
                self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))
                self.instructions.append(Instruction(JQOpcode.ADD, [index_reg, index_reg, "1"]))
                self.instructions.append(Instruction(JQOpcode.JMP, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [end_label]))
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.SORT_BY, [dest, array_reg, keys_buf]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "unique" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.UNIQUE, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "unique_by" and len(stage.args) == 1:
                array_reg = self._eval_expression(Identity(), current_reg)
                keys_buf = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [keys_buf, []]))
                index_reg = self._new_temp()
                length_reg = self._new_temp()
                cond_reg = self._new_temp()
                elem_reg = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [index_reg, 0]))
                self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [length_reg, array_reg]))
                loop_label = self._new_label("jq_unique_by_loop")
                end_label = self._new_label("jq_unique_by_end")
                self.instructions.append(Instruction(JQOpcode.LABEL, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LT, [cond_reg, index_reg, length_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, end_label]))
                self.instructions.append(Instruction(JQOpcode.GET_INDEX, [elem_reg, array_reg, index_reg]))
                key_reg = self._eval_expression(stage.args[0], elem_reg)
                self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [keys_buf]))
                self.instructions.append(Instruction(JQOpcode.EMIT, [key_reg]))
                self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))
                self.instructions.append(Instruction(JQOpcode.ADD, [index_reg, index_reg, "1"]))
                self.instructions.append(Instruction(JQOpcode.JMP, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [end_label]))
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.UNIQUE_BY, [dest, array_reg, keys_buf]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "min" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.MIN, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "max" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.MAX, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "min_by" and len(stage.args) == 1:
                array_reg = self._eval_expression(Identity(), current_reg)
                keys_buf = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [keys_buf, []]))
                index_reg = self._new_temp()
                length_reg = self._new_temp()
                cond_reg = self._new_temp()
                elem_reg = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [index_reg, 0]))
                self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [length_reg, array_reg]))
                loop_label = self._new_label("jq_min_by_loop")
                end_label = self._new_label("jq_min_by_end")
                self.instructions.append(Instruction(JQOpcode.LABEL, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LT, [cond_reg, index_reg, length_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, end_label]))
                self.instructions.append(Instruction(JQOpcode.GET_INDEX, [elem_reg, array_reg, index_reg]))
                key_reg = self._eval_expression(stage.args[0], elem_reg)
                self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [keys_buf]))
                self.instructions.append(Instruction(JQOpcode.EMIT, [key_reg]))
                self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))
                self.instructions.append(Instruction(JQOpcode.ADD, [index_reg, index_reg, "1"]))
                self.instructions.append(Instruction(JQOpcode.JMP, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [end_label]))
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.MIN_BY, [dest, array_reg, keys_buf]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "max_by" and len(stage.args) == 1:
                array_reg = self._eval_expression(Identity(), current_reg)
                keys_buf = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [keys_buf, []]))
                index_reg = self._new_temp()
                length_reg = self._new_temp()
                cond_reg = self._new_temp()
                elem_reg = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [index_reg, 0]))
                self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [length_reg, array_reg]))
                loop_label = self._new_label("jq_max_by_loop")
                end_label = self._new_label("jq_max_by_end")
                self.instructions.append(Instruction(JQOpcode.LABEL, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LT, [cond_reg, index_reg, length_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, end_label]))
                self.instructions.append(Instruction(JQOpcode.GET_INDEX, [elem_reg, array_reg, index_reg]))
                key_reg = self._eval_expression(stage.args[0], elem_reg)
                self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [keys_buf]))
                self.instructions.append(Instruction(JQOpcode.EMIT, [key_reg]))
                self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))
                self.instructions.append(Instruction(JQOpcode.ADD, [index_reg, index_reg, "1"]))
                self.instructions.append(Instruction(JQOpcode.JMP, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [end_label]))
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.MAX_BY, [dest, array_reg, keys_buf]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "group_by" and len(stage.args) == 1:
                array_reg = self._eval_expression(Identity(), current_reg)
                keys_buf = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [keys_buf, []]))
                index_reg = self._new_temp()
                length_reg = self._new_temp()
                cond_reg = self._new_temp()
                elem_reg = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [index_reg, 0]))
                self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [length_reg, array_reg]))
                loop_label = self._new_label("jq_group_by_loop")
                end_label = self._new_label("jq_group_by_end")
                self.instructions.append(Instruction(JQOpcode.LABEL, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LT, [cond_reg, index_reg, length_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, end_label]))
                self.instructions.append(Instruction(JQOpcode.GET_INDEX, [elem_reg, array_reg, index_reg]))
                key_reg = self._eval_expression(stage.args[0], elem_reg)
                self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [keys_buf]))
                self.instructions.append(Instruction(JQOpcode.EMIT, [key_reg]))
                self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))
                self.instructions.append(Instruction(JQOpcode.ADD, [index_reg, index_reg, "1"]))
                self.instructions.append(Instruction(JQOpcode.JMP, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [end_label]))
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.GROUP_BY, [dest, array_reg, keys_buf]))
                self._compile_pipeline(rest, dest)
                return
            # Milestone 3 core filters
            if stage.name == "keys" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.KEYS, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "has" and len(stage.args) == 1:
                needle = self._eval_expression(stage.args[0], current_reg)
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.HAS, [dest, current_reg, needle]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "contains" and len(stage.args) == 1:
                needle = self._eval_expression(stage.args[0], current_reg)
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.CONTAINS, [dest, current_reg, needle]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "add" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.AGG_ADD, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "join" and len(stage.args) in (0, 1):
                if stage.args:
                    sep = self._eval_expression(stage.args[0], current_reg)
                else:
                    sep = self._new_temp()
                    self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [sep, ""]))
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.JOIN, [dest, current_reg, sep]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "reverse" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.REVERSE, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "first" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.FIRST, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "last" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LAST, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "any" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.ANY, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "all" and len(stage.args) == 0:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.ALL, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "length" and not stage.args:
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [dest, current_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "flatten":
                if stage.args:
                    array_reg = self._eval_expression(stage.args[0], current_reg)
                else:
                    array_reg = current_reg
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.FLATTEN, [dest, array_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "reduce":
                array_expr = Identity()
                op_literal = None
                init_expr = None
                arg_count = len(stage.args)
                if arg_count == 0:
                    pass
                elif arg_count == 1:
                    if isinstance(stage.args[0], Literal) and isinstance(stage.args[0].value, str):
                        op_literal = stage.args[0]
                    else:
                        array_expr = stage.args[0]
                elif arg_count == 2:
                    array_expr = stage.args[0]
                    op_literal = stage.args[1]
                else:
                    array_expr = stage.args[0]
                    op_literal = stage.args[1]
                    init_expr = stage.args[2]

                array_reg = self._eval_expression(array_expr, current_reg)
                op_name = "sum"
                if op_literal is not None:
                    if isinstance(op_literal, Literal) and isinstance(op_literal.value, str):
                        op_name = op_literal.value.lower()
                    else:
                        raise NotImplementedError("reduce aggregator must be a string literal")
                init_reg = ""
                if init_expr is not None:
                    init_reg = self._eval_expression(init_expr, current_reg)

                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.REDUCE, [dest, array_reg, op_name, init_reg]))
                self._compile_pipeline(rest, dest)
                return
            if stage.name == "map" and len(stage.args) == 1:
                result_reg = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [result_reg, []]))
                self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [result_reg]))

                source_reg = self._eval_expression(Identity(), current_reg)
                index_reg = self._new_temp()
                length_reg = self._new_temp()
                cond_reg = self._new_temp()
                elem_reg = self._new_temp()
                loop_label = self._new_label("jq_map_loop")
                end_label = self._new_label("jq_map_end")

                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [index_reg, 0]))
                self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [length_reg, source_reg]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LT, [cond_reg, index_reg, length_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, end_label]))
                self.instructions.append(Instruction(JQOpcode.GET_INDEX, [elem_reg, source_reg, index_reg]))

                expr_stages = flatten_pipe(stage.args[0])
                self._compile_pipeline(expr_stages, elem_reg)

                self.instructions.append(Instruction(JQOpcode.ADD, [index_reg, index_reg, "1"]))
                self.instructions.append(Instruction(JQOpcode.JMP, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [end_label]))
                self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))
                self._compile_pipeline(rest, result_reg)
                return

            if stage.name == "select" and len(stage.args) == 1:
                cond_buffer = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [cond_buffer, []]))
                self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [cond_buffer]))
                expr_stages = flatten_pipe(stage.args[0])
                self._compile_pipeline(expr_stages, current_reg)
                self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))

                # Flatten one level so that array results (e.g., from map(.))
                # become multiple items for truth checking.
                flat_buffer = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.FLATTEN, [flat_buffer, cond_buffer]))

                len_reg = self._new_temp()
                index_reg = self._new_temp()
                cond_reg = self._new_temp()
                item_reg = self._new_temp()
                truth_reg = self._new_temp()
                loop_label = self._new_label("jq_select_loop")
                skip_item_label = self._new_label("jq_select_skip_item")
                done_label = self._new_label("jq_select_done")
                skip_label = self._new_label("jq_select_skip")
                cont_label = self._new_label("jq_select_cont")

                self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [len_reg, flat_buffer]))
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [truth_reg, 0]))
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [index_reg, 0]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LT, [cond_reg, index_reg, len_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, done_label]))
                self.instructions.append(Instruction(JQOpcode.GET_INDEX, [item_reg, flat_buffer, index_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [item_reg, skip_item_label]))
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [truth_reg, 1]))
                self.instructions.append(Instruction(JQOpcode.JMP, [done_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [skip_item_label]))
                self.instructions.append(Instruction(JQOpcode.ADD, [index_reg, index_reg, "1"]))
                self.instructions.append(Instruction(JQOpcode.JMP, [loop_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [done_label]))
                self.instructions.append(Instruction(JQOpcode.JZ, [truth_reg, skip_label]))
                self._compile_pipeline(rest, current_reg)
                self.instructions.append(Instruction(JQOpcode.JMP, [cont_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [skip_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [cont_label]))
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

    def _var_reg(self, name: str) -> str:
        return f"__jq_var_{name}"

    def _eval_expression(self, node: JQNode, base_reg: str) -> str:
        if isinstance(node, Identity):
            return base_reg
        if isinstance(node, Literal):
            dest = self._new_temp()
            self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [dest, node.value]))
            return dest
        if isinstance(node, VarRef):
            return self._var_reg(node.name)
        if isinstance(node, UnaryOp):
            operand = self._eval_expression(node.operand, base_reg)
            dest = self._new_temp()
            if node.op == "-":
                self.instructions.append(Instruction(JQOpcode.NEG, [dest, operand]))
                return dest
            if node.op == "not":
                self.instructions.append(Instruction(JQOpcode.NOT, [dest, operand]))
                return dest
            raise NotImplementedError(f"Unsupported unary operator: {node.op}")
        if isinstance(node, BinaryOp):
            # Arithmetic and logic directly mapped
            if node.op in {"+", "-", "*", "/", "%", "==", ">", "<", "and", "or"}:
                left = self._eval_expression(node.left, base_reg)
                right = self._eval_expression(node.right, base_reg)
                dest = self._new_temp()
                opmap = {
                    "+": JQOpcode.ADD,
                    "-": JQOpcode.SUB,
                    "*": JQOpcode.MUL,
                    "/": JQOpcode.DIV,
                    "%": JQOpcode.MOD,
                    "==": JQOpcode.EQ,
                    ">": JQOpcode.GT,
                    "<": JQOpcode.LT,
                    "and": JQOpcode.AND,
                    "or": JQOpcode.OR,
                }
                self.instructions.append(Instruction(opmap[node.op], [dest, left, right]))
                return dest
            # Derived comparisons: !=, >=, <=
            if node.op == "!=":
                eq_reg = self._eval_expression(BinaryOp("==", node.left, node.right), base_reg)
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.NOT, [dest, eq_reg]))
                return dest
            if node.op == ">=":
                # not (left < right)
                lt_reg = self._eval_expression(BinaryOp("<", node.left, node.right), base_reg)
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.NOT, [dest, lt_reg]))
                return dest
            if node.op == "<=":
                # not (left > right)
                gt_reg = self._eval_expression(BinaryOp(">", node.left, node.right), base_reg)
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.NOT, [dest, gt_reg]))
                return dest
            if node.op == "//":
                # Coalesce: return left if not null, else right
                left_reg = self._eval_expression(node.left, base_reg)
                dest = self._new_temp()
                null_reg = self._new_temp()
                cond_reg = self._new_temp()
                notnull_label = self._new_label("jq_coalesce_use_left")
                done_label = self._new_label("jq_coalesce_done")
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [null_reg, None]))
                self.instructions.append(Instruction(JQOpcode.EQ, [cond_reg, left_reg, null_reg]))
                self.instructions.append(Instruction(JQOpcode.JZ, [cond_reg, notnull_label]))
                right_reg = self._eval_expression(node.right, base_reg)
                self.instructions.append(Instruction(JQOpcode.MOV, [dest, right_reg]))
                self.instructions.append(Instruction(JQOpcode.JMP, [done_label]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [notnull_label]))
                self.instructions.append(Instruction(JQOpcode.MOV, [dest, left_reg]))
                self.instructions.append(Instruction(JQOpcode.LABEL, [done_label]))
                return dest
            raise NotImplementedError(f"Unsupported binary operator: {node.op}")
        if isinstance(node, Field):
            names: List[str] = []
            source = node
            while isinstance(source, Field):
                names.append(source.name)
                source = source.source

            current = self._eval_expression(source, base_reg)
            for name in reversed(names):
                dest = self._new_temp()
                self.instructions.append(Instruction(JQOpcode.OBJ_GET, [dest, current, name]))
                current = dest
            return current
        if isinstance(node, ObjectLiteral):
            obj_reg = self._new_temp()
            self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [obj_reg, {}]))
            for key, value_expr in node.pairs:
                value_reg = self._eval_expression(value_expr, base_reg)
                self.instructions.append(Instruction(JQOpcode.OBJ_SET, [obj_reg, key, value_reg]))
            return obj_reg
        if isinstance(node, Index):
            container = self._eval_expression(node.source, base_reg)
            idx = self._eval_expression(node.index, base_reg)
            dest = self._new_temp()
            self.instructions.append(Instruction(JQOpcode.GET_INDEX, [dest, container, idx]))
            return dest
        if isinstance(node, Slice):
            src = self._eval_expression(node.source, base_reg)
            result = self._new_temp()
            self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [result, []]))

            length = self._new_temp()
            self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [length, src]))

            start_reg = self._new_temp()
            if node.start is None:
                self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [start_reg, 0]))
            else:
                start_val = self._eval_expression(node.start, base_reg)
                self.instructions.append(Instruction(JQOpcode.MOV, [start_reg, start_val]))

            end_reg = self._new_temp()
            if node.end is None:
                self.instructions.append(Instruction(JQOpcode.MOV, [end_reg, length]))
            else:
                end_val = self._eval_expression(node.end, base_reg)
                self.instructions.append(Instruction(JQOpcode.MOV, [end_reg, end_val]))

            # Normalize start: if start < 0 => start += length; clamp to [0, length]
            zero = "0"
            cond = self._new_temp()
            neg_label = self._new_label("jq_slice_start_neg")
            cont1 = self._new_label("jq_slice_start_cont1")
            self.instructions.append(Instruction(JQOpcode.LT, [cond, start_reg, zero]))
            self.instructions.append(Instruction(JQOpcode.JZ, [cond, cont1]))
            self.instructions.append(Instruction(JQOpcode.ADD, [start_reg, start_reg, length]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [cont1]))
            # start < 0 => start = 0
            cont2 = self._new_label("jq_slice_start_cont2")
            self.instructions.append(Instruction(JQOpcode.LT, [cond, start_reg, zero]))
            self.instructions.append(Instruction(JQOpcode.JZ, [cond, cont2]))
            self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [start_reg, 0]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [cont2]))
            # start > length => start = length
            cont3 = self._new_label("jq_slice_start_cont3")
            self.instructions.append(Instruction(JQOpcode.GT, [cond, start_reg, length]))
            self.instructions.append(Instruction(JQOpcode.JZ, [cond, cont3]))
            self.instructions.append(Instruction(JQOpcode.MOV, [start_reg, length]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [cont3]))

            # Normalize end: if end < 0 => end += length; clamp to [0, length]
            cont4 = self._new_label("jq_slice_end_cont1")
            self.instructions.append(Instruction(JQOpcode.LT, [cond, end_reg, zero]))
            self.instructions.append(Instruction(JQOpcode.JZ, [cond, cont4]))
            self.instructions.append(Instruction(JQOpcode.ADD, [end_reg, end_reg, length]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [cont4]))
            cont5 = self._new_label("jq_slice_end_cont2")
            self.instructions.append(Instruction(JQOpcode.LT, [cond, end_reg, zero]))
            self.instructions.append(Instruction(JQOpcode.JZ, [cond, cont5]))
            self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [end_reg, 0]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [cont5]))
            cont6 = self._new_label("jq_slice_end_cont3")
            self.instructions.append(Instruction(JQOpcode.GT, [cond, end_reg, length]))
            self.instructions.append(Instruction(JQOpcode.JZ, [cond, cont6]))
            self.instructions.append(Instruction(JQOpcode.MOV, [end_reg, length]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [cont6]))

            # Loop i from start to end-1
            i = self._new_temp()
            self.instructions.append(Instruction(JQOpcode.MOV, [i, start_reg]))
            self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [result]))
            loop = self._new_label("jq_slice_loop")
            done = self._new_label("jq_slice_done")
            self.instructions.append(Instruction(JQOpcode.LABEL, [loop]))
            self.instructions.append(Instruction(JQOpcode.LT, [cond, i, end_reg]))
            self.instructions.append(Instruction(JQOpcode.JZ, [cond, done]))
            item = self._new_temp()
            self.instructions.append(Instruction(JQOpcode.GET_INDEX, [item, src, i]))
            self.instructions.append(Instruction(JQOpcode.EMIT, [item]))
            self.instructions.append(Instruction(JQOpcode.ADD, [i, i, "1"]))
            self.instructions.append(Instruction(JQOpcode.JMP, [loop]))
            self.instructions.append(Instruction(JQOpcode.LABEL, [done]))
            self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))
            return result
        return self._compile_expression(node, base_reg)

    def _compile_expression(self, expr: JQNode, base_reg: str) -> str:
        buffer_reg = self._new_temp()
        self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [buffer_reg, []]))
        self.instructions.append(Instruction(JQOpcode.PUSH_EMIT, [buffer_reg]))
        stages = flatten_pipe(expr)
        self._compile_pipeline(stages, base_reg)
        self.instructions.append(Instruction(JQOpcode.POP_EMIT, []))

        len_reg = self._new_temp()
        index_reg = self._new_temp()
        value_reg = self._new_temp()
        empty_label = self._new_label("jq_expr_empty")
        done_label = self._new_label("jq_expr_done")

        self.instructions.append(Instruction(JQOpcode.LEN_VALUE, [len_reg, buffer_reg]))
        self.instructions.append(Instruction(JQOpcode.JZ, [len_reg, empty_label]))
        self.instructions.append(Instruction(JQOpcode.SUB, [index_reg, len_reg, "1"]))
        self.instructions.append(Instruction(JQOpcode.GET_INDEX, [value_reg, buffer_reg, index_reg]))
        self.instructions.append(Instruction(JQOpcode.JMP, [done_label]))
        self.instructions.append(Instruction(JQOpcode.LABEL, [empty_label]))
        self.instructions.append(Instruction(JQOpcode.LOAD_CONST, [value_reg, None]))
        self.instructions.append(Instruction(JQOpcode.LABEL, [done_label]))
        return value_reg


def compile_to_bytecode(node: JQNode) -> List[Instruction]:
    return JQCompiler().compile(node)


__all__ = ["JQCompiler", "compile_to_bytecode", "INPUT_REGISTER", "CURRENT_REGISTER"]
