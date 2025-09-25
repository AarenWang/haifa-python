from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from compiler.bytecode import Instruction, InstructionDebug, Opcode, SourceLocation

from .analysis import FunctionInfo, analyze
from .ast import (
    Assignment,
    BreakStmt,
    BinaryOp,
    Block,
    BooleanLiteral,
    CallExpr,
    Chunk,
    DoStmt,
    Expr,
    ExprStmt,
    FieldAccess,
    FunctionExpr,
    FunctionStmt,
    GotoStmt,
    Identifier,
    IfStmt,
    ForNumericStmt,
    ForGenericStmt,
    IndexExpr,
    LabelStmt,
    MethodCallExpr,
    NilLiteral,
    NumberLiteral,
    RepeatStmt,
    ReturnStmt,
    StringLiteral,
    TableConstructor,
    UnaryOp,
    WhileStmt,
    VarargExpr,
)


@dataclass
class VarBinding:
    storage: str
    is_cell: bool = False
    is_vararg: bool = False


class CompileError(RuntimeError):
    pass


_FUNC_LABEL_COUNTER = itertools.count()


class LuaCompiler:
    def __init__(
        self,
        closure_map: Dict[int, FunctionInfo],
        function_info: FunctionInfo,
        upvalue_names: Optional[List[str]] = None,
        *,
        source_name: str = "<stdin>",
        function_name: str = "<chunk>",
    ):
        self.closure_map = closure_map
        self.function_info = function_info
        self.upvalue_names = upvalue_names or []

        self.instructions: List[Instruction] = []
        self.function_blocks: List[Instruction] = []
        self.scope_stack: List[Dict[str, VarBinding]] = []
        self.temp_counter = 0
        self.func_counter = 0
        self.exit_label = "__lua_exit"
        self.is_top_level = False
        self.vararg_flag = function_info.vararg
        self.source_name = source_name
        self.function_name = function_name
        self._last_debug: InstructionDebug | None = None
        self.loop_stack: List[str] = []
        self.label_definitions: Dict[str, Tuple[str, int, object]] = {}
        self.pending_gotos: List[Tuple[str, int, object]] = []

    # ------------------------------------------------------------------
    @classmethod
    def compile_chunk(cls, chunk: Chunk, *, source_name: str = "<stdin>") -> List[Instruction]:
        closure_map, root_info = analyze(chunk)
        compiler = cls(
            closure_map,
            root_info,
            root_info.upvalues,
            source_name=source_name,
            function_name="<chunk>",
        )
        return compiler._compile_chunk(chunk)

    def _compile_chunk(self, chunk: Chunk) -> List[Instruction]:
        self.instructions.clear()
        self.function_blocks.clear()
        self.temp_counter = 0
        self.func_counter = 0
        self.scope_stack = [{}]
        self.is_top_level = True
        self._bind_upvalues()
        self._compile_block(chunk.body, top_level=True)
        self._finalize_labels()
        self._emit(Opcode.JMP, [self.exit_label], node=chunk.body.statements[-1] if chunk.body.statements else None)
        self.instructions.extend(self.function_blocks)
        self._emit(Opcode.LABEL, [self.exit_label])
        self._emit(Opcode.HALT, [])
        return list(self.instructions)

    # ------------------------------------------------------------------
    def _push_scope(self):
        self.scope_stack.append({})

    def _pop_scope(self):
        self.scope_stack.pop()

    def _new_temp(self) -> str:
        name = f"__t{self.temp_counter}"
        self.temp_counter += 1
        return name

    def _alloc_local_reg(self, name: str) -> str:
        reg = f"L_{len(self.scope_stack)-1}_{name}_{self.temp_counter}"
        self.temp_counter += 1
        return reg

    def _alloc_cell_reg(self, name: str) -> str:
        reg = f"C_{len(self.scope_stack)-1}_{name}_{self.temp_counter}"
        self.temp_counter += 1
        return reg

    def _debug_for(self, node: object | None) -> InstructionDebug | None:
        if node is None:
            return None
        line = int(getattr(node, "line", 0) or 0)
        column = int(getattr(node, "column", 0) or 0)
        location = SourceLocation(self.source_name, line, column)
        return InstructionDebug(location, self.function_name)

    def _emit(self, opcode: Opcode, args, *, node: object | None = None) -> Instruction:
        if isinstance(args, (list, tuple)):
            arg_list = list(args)
        else:
            arg_list = [args]
        debug = self._debug_for(node)
        if debug is not None:
            self._last_debug = debug
        elif self._last_debug is not None:
            debug = self._last_debug
        inst = Instruction(opcode, arg_list, debug)
        self.instructions.append(inst)
        return inst

    def _lookup_binding(self, name: str) -> Optional[VarBinding]:
        for scope in reversed(self.scope_stack):
            if name in scope:
                return scope[name]
        return None

    def _bind_upvalues(self):
        if not self.upvalue_names:
            return
        scope = self.scope_stack[-1]
        for idx, name in enumerate(self.upvalue_names):
            cell_reg = self._alloc_cell_reg(name)
            scope[name] = VarBinding(storage=cell_reg, is_cell=True)
            self._emit(Opcode.BIND_UPVALUE, [cell_reg, str(idx)])

    def _setup_parameters(self, params: List[str], info: FunctionInfo, is_vararg: bool, node: object):
        scope = self.scope_stack[-1]
        for param in params:
            captured = param in info.captured_locals
            reg = self._alloc_local_reg(param)
            scope[param] = VarBinding(reg, False)
            self._emit(Opcode.ARG, [reg], node=node)
            if captured:
                cell_reg = self._alloc_cell_reg(param)
                scope[param] = VarBinding(cell_reg, True)
                self._emit(Opcode.MAKE_CELL, [cell_reg, reg], node=node)
        if is_vararg:
            var_reg = self._alloc_local_reg("__vararg")
            captured = "..." in info.captured_locals
            scope["..."] = VarBinding(var_reg, False, True)
            self._emit(Opcode.VARARG, [var_reg], node=node)
            if captured:
                cell_reg = self._alloc_cell_reg("vararg")
                scope["..."] = VarBinding(cell_reg, True, True)
                self._emit(Opcode.MAKE_CELL, [cell_reg, var_reg], node=node)

    # ------------------------------------------------------------------ Statements
    def _compile_block(self, block: Block, top_level: bool = False):
        prev_top = self.is_top_level
        self.is_top_level = bool(top_level)
        self._push_scope()
        try:
            self._compile_block_statements(block)
        finally:
            self._pop_scope()
            self.is_top_level = prev_top

    def _compile_block_statements(self, block: Block) -> None:
        for stmt in block.statements:
            if isinstance(stmt, Assignment):
                self._compile_assignment(stmt)
            elif isinstance(stmt, IfStmt):
                self._compile_if(stmt)
            elif isinstance(stmt, WhileStmt):
                self._compile_while(stmt)
            elif isinstance(stmt, ForNumericStmt):
                self._compile_numeric_for(stmt)
            elif isinstance(stmt, ForGenericStmt):
                self._compile_generic_for(stmt)
            elif isinstance(stmt, RepeatStmt):
                self._compile_repeat(stmt)
            elif isinstance(stmt, DoStmt):
                self._compile_block(stmt.body)
            elif isinstance(stmt, BreakStmt):
                self._compile_break(stmt)
            elif isinstance(stmt, GotoStmt):
                self._compile_goto(stmt)
            elif isinstance(stmt, LabelStmt):
                self._compile_label(stmt)
            elif isinstance(stmt, ReturnStmt):
                self._compile_return(stmt)
            elif isinstance(stmt, FunctionStmt):
                self._compile_function_stmt(stmt)
            elif isinstance(stmt, ExprStmt):
                self._compile_expr(stmt.expr)
            else:
                raise CompileError(f"Unsupported statement: {stmt}")

    def _compile_assignment(self, stmt: Assignment):
        target_count = len(stmt.targets)
        value_regs = self._collect_assignment_values(stmt.values, target_count, stmt)

        if stmt.is_local:
            for idx, target in enumerate(stmt.targets):
                if not isinstance(target, Identifier):
                    raise CompileError("local declarations require identifier targets")
                name = target.name
                value_reg = value_regs[idx] if idx < len(value_regs) else self._emit_literal(None, stmt)
                captured = name in self.function_info.captured_locals
                if captured:
                    cell_reg = self._alloc_cell_reg(name)
                    self.scope_stack[-1][name] = VarBinding(cell_reg, True)
                    self._emit(Opcode.MAKE_CELL, [cell_reg, value_reg], node=stmt)
                else:
                    reg = self._alloc_local_reg(name)
                    self.scope_stack[-1][name] = VarBinding(reg, False)
                    self._emit(Opcode.MOV, [reg, value_reg], node=stmt)
            return

        for target, value_reg in zip(stmt.targets, value_regs):
            self._store_assignment_target(target, value_reg, stmt)

    def _collect_assignment_values(self, values: List[Expr], target_count: int, node: Assignment) -> List[str]:
        if target_count == 0:
            return []

        regs: List[str] = []
        if not values:
            for _ in range(target_count):
                regs.append(self._emit_literal(None, node))
            return regs

        total = len(values)
        for idx, expr in enumerate(values):
            is_last = idx == total - 1
            if is_last:
                needed = target_count - len(regs)
                regs.extend(self._eval_last_assignment_expr(expr, needed))
            else:
                result = self._eval_assignment_expr(expr)
                if len(regs) < target_count:
                    regs.append(result)

        while len(regs) < target_count:
            regs.append(self._emit_literal(None, node))

        if len(regs) > target_count:
            return regs[:target_count]
        return regs

    def _eval_assignment_expr(self, expr: Expr) -> str:
        if isinstance(expr, (CallExpr, MethodCallExpr)):
            return self._compile_call_like(expr)
        if isinstance(expr, VarargExpr):
            return self._compile_vararg_expr(multi=False, node=expr)
        return self._compile_expr(expr)

    def _eval_last_assignment_expr(self, expr: Expr, needed: int) -> List[str]:
        if needed <= 0:
            self._eval_assignment_expr(expr)
            return []
        if isinstance(expr, (CallExpr, MethodCallExpr)):
            if needed == 1:
                return [self._compile_call_like(expr)]
            list_reg = self._compile_call_like(expr, want_list=True)
            return self._unpack_list(list_reg, needed, expr)
        if isinstance(expr, VarargExpr):
            if needed == 1:
                return [self._compile_vararg_expr(multi=False, node=expr)]
            list_reg = self._compile_vararg_expr(multi=True, node=expr)
            return self._unpack_list(list_reg, needed, expr)
        return [self._compile_expr(expr)]

    def _unpack_list(self, list_reg: str, count: int, node: Expr) -> List[str]:
        regs: List[str] = []
        for index in range(count):
            dst = self._new_temp()
            self._emit(Opcode.LIST_GET, [dst, list_reg, index], node=node)
            regs.append(dst)
        return regs

    def _store_assignment_target(self, target: Expr, value_reg: str, node: Assignment):
        if isinstance(target, Identifier):
            binding = self._lookup_binding(target.name)
            if binding:
                if binding.is_cell:
                    self._emit(Opcode.CELL_SET, [binding.storage, value_reg], node=node)
                else:
                    self._emit(Opcode.MOV, [binding.storage, value_reg], node=node)
            else:
                self._emit(Opcode.MOV, [f"G_{target.name}", value_reg], node=node)
            return
        if isinstance(target, FieldAccess):
            table_reg = self._compile_expr(target.table)
            key_reg = self._emit_literal(target.field, target, hint=self._new_temp())
            self._emit(Opcode.TABLE_SET, [table_reg, key_reg, value_reg], node=node)
            return
        if isinstance(target, IndexExpr):
            table_reg = self._compile_expr(target.table)
            index_reg = self._compile_expr(target.index)
            self._emit(Opcode.TABLE_SET, [table_reg, index_reg, value_reg], node=node)
            return
        raise CompileError("Assignment target type is not supported yet")

    def _compile_if(self, stmt: IfStmt):
        branches = [(stmt.condition, stmt.then_branch)]
        for clause in stmt.elseif_branches:
            branches.append((clause.condition, clause.body))

        end_label = f"__endif_{self._new_temp()}"

        for idx, (condition, block) in enumerate(branches):
            has_following = idx < len(branches) - 1 or stmt.else_branch is not None
            false_label = (
                f"__if_next_{self._new_temp()}" if has_following else end_label
            )
            cond_reg = self._compile_expr(condition)
            self._emit(Opcode.JZ, [cond_reg, false_label], node=stmt)
            self._compile_block(block)
            self._emit(Opcode.JMP, [end_label], node=stmt)
            if has_following:
                self._emit(Opcode.LABEL, [false_label], node=stmt)

        if stmt.else_branch:
            self._compile_block(stmt.else_branch)

        self._emit(Opcode.LABEL, [end_label], node=stmt)

    def _compile_while(self, stmt: WhileStmt):
        start_label = f"__while_start_{self._new_temp()}"
        end_label = f"__while_end_{self._new_temp()}"
        self._emit(Opcode.LABEL, [start_label], node=stmt)
        cond_reg = self._compile_expr(stmt.condition)
        self._emit(Opcode.JZ, [cond_reg, end_label], node=stmt)
        self.loop_stack.append(end_label)
        self._compile_block(stmt.body)
        self.loop_stack.pop()
        self._emit(Opcode.JMP, [start_label], node=stmt)
        self._emit(Opcode.LABEL, [end_label], node=stmt)

    def _compile_numeric_for(self, stmt: ForNumericStmt):
        start_value = self._compile_expr(stmt.start)
        start_reg = self._new_temp()
        self._emit(Opcode.MOV, [start_reg, start_value], node=stmt.start)

        limit_value = self._compile_expr(stmt.limit)
        limit_reg = self._new_temp()
        self._emit(Opcode.MOV, [limit_reg, limit_value], node=stmt.limit)

        if stmt.step is not None:
            step_value = self._compile_expr(stmt.step)
            step_reg = self._new_temp()
            self._emit(Opcode.MOV, [step_reg, step_value], node=stmt.step)
        else:
            step_reg = self._emit_literal(1, stmt, hint=self._new_temp())

        zero_reg = self._emit_literal(0, stmt, hint=self._new_temp())
        positive_reg = self._new_temp()
        self._emit(Opcode.GT, [positive_reg, step_reg, zero_reg], node=stmt)

        self._push_scope()
        loop_scope = self.scope_stack[-1]
        captured = stmt.var in self.function_info.captured_locals
        if captured:
            cell_reg = self._alloc_cell_reg(stmt.var)
            loop_scope[stmt.var] = VarBinding(cell_reg, True)
            self._emit(Opcode.MAKE_CELL, [cell_reg, start_reg], node=stmt)
        else:
            var_reg = self._alloc_local_reg(stmt.var)
            loop_scope[stmt.var] = VarBinding(var_reg, False)
            self._emit(Opcode.MOV, [var_reg, start_reg], node=stmt)

        var_binding = loop_scope[stmt.var]
        end_label = f"__for_end_{self._new_temp()}"
        loop_label = f"__for_loop_{self._new_temp()}"
        negative_label = f"__for_neg_{self._new_temp()}"
        after_check = f"__for_after_{self._new_temp()}"
        cond_reg = self._new_temp()

        self._emit(Opcode.JZ, [positive_reg, negative_label], node=stmt)
        initial_val = self._binding_read(var_binding, stmt)
        tmp_gt = self._new_temp()
        self._emit(Opcode.GT, [tmp_gt, initial_val, limit_reg], node=stmt)
        self._emit(Opcode.NOT, [cond_reg, tmp_gt], node=stmt)
        self._emit(Opcode.JMP, [after_check], node=stmt)

        self._emit(Opcode.LABEL, [negative_label], node=stmt)
        initial_val_neg = self._binding_read(var_binding, stmt)
        tmp_lt = self._new_temp()
        self._emit(Opcode.LT, [tmp_lt, initial_val_neg, limit_reg], node=stmt)
        self._emit(Opcode.NOT, [cond_reg, tmp_lt], node=stmt)
        self._emit(Opcode.LABEL, [after_check], node=stmt)
        self._emit(Opcode.JZ, [cond_reg, end_label], node=stmt)

        self._emit(Opcode.LABEL, [loop_label], node=stmt)
        self.loop_stack.append(end_label)
        self._compile_block(stmt.body)
        self.loop_stack.pop()
        current_val = self._binding_read(var_binding, stmt)
        next_val = self._new_temp()
        self._emit(Opcode.ADD, [next_val, current_val, step_reg], node=stmt)
        self._binding_write(var_binding, next_val, stmt)

        negative_label2 = f"__for_neg_{self._new_temp()}"
        after_check2 = f"__for_after_{self._new_temp()}"
        cond_reg2 = self._new_temp()

        self._emit(Opcode.JZ, [positive_reg, negative_label2], node=stmt)
        pos_val = self._binding_read(var_binding, stmt)
        tmp_gt2 = self._new_temp()
        self._emit(Opcode.GT, [tmp_gt2, pos_val, limit_reg], node=stmt)
        self._emit(Opcode.NOT, [cond_reg2, tmp_gt2], node=stmt)
        self._emit(Opcode.JMP, [after_check2], node=stmt)

        self._emit(Opcode.LABEL, [negative_label2], node=stmt)
        neg_val = self._binding_read(var_binding, stmt)
        tmp_lt2 = self._new_temp()
        self._emit(Opcode.LT, [tmp_lt2, neg_val, limit_reg], node=stmt)
        self._emit(Opcode.NOT, [cond_reg2, tmp_lt2], node=stmt)
        self._emit(Opcode.LABEL, [after_check2], node=stmt)
        self._emit(Opcode.JNZ, [cond_reg2, loop_label], node=stmt)

        self._emit(Opcode.LABEL, [end_label], node=stmt)
        self._pop_scope()

    def _compile_generic_for(self, stmt: ForGenericStmt):
        values = self._collect_assignment_values(stmt.iter_exprs, 3, stmt)
        while len(values) < 3:
            values.append(self._emit_literal(None, stmt))

        iter_func_reg = self._new_temp()
        self._emit(Opcode.MOV, [iter_func_reg, values[0]], node=stmt)
        state_reg = self._new_temp()
        self._emit(Opcode.MOV, [state_reg, values[1]], node=stmt)
        control_reg = self._new_temp()
        self._emit(Opcode.MOV, [control_reg, values[2]], node=stmt)

        self._push_scope()
        loop_scope = self.scope_stack[-1]
        bindings: List[VarBinding] = []
        nil_reg = self._emit_literal(None, stmt, hint=self._new_temp())
        for name in stmt.names:
            captured = name in self.function_info.captured_locals
            if captured:
                cell_reg = self._alloc_cell_reg(name)
                loop_scope[name] = VarBinding(cell_reg, True)
                self._emit(Opcode.MAKE_CELL, [cell_reg, nil_reg], node=stmt)
            else:
                reg = self._alloc_local_reg(name)
                loop_scope[name] = VarBinding(reg, False)
                self._emit(Opcode.MOV, [reg, nil_reg], node=stmt)
            bindings.append(loop_scope[name])

        loop_label = f"__forgen_loop_{self._new_temp()}"
        end_label = f"__forgen_end_{self._new_temp()}"

        self._emit(Opcode.LABEL, [loop_label], node=stmt)
        self._emit(Opcode.PARAM, [state_reg], node=stmt)
        self._emit(Opcode.PARAM, [control_reg], node=stmt)
        self._emit(Opcode.CALL_VALUE, [iter_func_reg], node=stmt)
        result_list = self._new_temp()
        self._emit(Opcode.RESULT_LIST, [result_list], node=stmt)
        first_value = self._new_temp()
        self._emit(Opcode.LIST_GET, [first_value, result_list, 0], node=stmt)
        self._emit(Opcode.MOV, [control_reg, first_value], node=stmt)
        nil_check = self._new_temp()
        self._emit(Opcode.IS_NULL, [nil_check, first_value], node=stmt)
        self._emit(Opcode.JNZ, [nil_check, end_label], node=stmt)

        for idx, binding in enumerate(bindings):
            if idx == 0:
                value_reg = first_value
            else:
                value_reg = self._new_temp()
                self._emit(Opcode.LIST_GET, [value_reg, result_list, idx], node=stmt)
            self._binding_write(binding, value_reg, stmt)

        self.loop_stack.append(end_label)
        self._compile_block(stmt.body)
        self.loop_stack.pop()
        self._emit(Opcode.JMP, [loop_label], node=stmt)

        self._emit(Opcode.LABEL, [end_label], node=stmt)
        self._pop_scope()

    def _compile_repeat(self, stmt: RepeatStmt):
        start_label = f"__repeat_start_{self._new_temp()}"
        end_label = f"__repeat_end_{self._new_temp()}"
        self._emit(Opcode.LABEL, [start_label], node=stmt)
        self.loop_stack.append(end_label)
        self._push_scope()
        prev_top = self.is_top_level
        self.is_top_level = False
        cond_reg = None
        try:
            self._compile_block_statements(stmt.body)
            cond_reg = self._compile_expr(stmt.condition)
            self._emit(Opcode.JZ, [cond_reg, start_label], node=stmt)
        finally:
            self.is_top_level = prev_top
            self._pop_scope()
            self.loop_stack.pop()
        self._emit(Opcode.LABEL, [end_label], node=stmt)

    def _compile_break(self, stmt: BreakStmt):
        if not self.loop_stack:
            raise CompileError("`break` used outside of a loop")
        target = self.loop_stack[-1]
        self._emit(Opcode.JMP, [target], node=stmt)

    def _compile_goto(self, stmt: GotoStmt):
        symbol = self._label_symbol(stmt.label)
        depth = len(self.scope_stack)
        self.pending_gotos.append((stmt.label, depth, stmt))
        self._emit(Opcode.JMP, [symbol], node=stmt)

    def _compile_label(self, stmt: LabelStmt):
        if stmt.name in self.label_definitions:
            raise CompileError(f"duplicate label '{stmt.name}'")
        symbol = self._label_symbol(stmt.name)
        depth = len(self.scope_stack)
        self.label_definitions[stmt.name] = (symbol, depth, stmt)
        self._emit(Opcode.LABEL, [symbol], node=stmt)

    def _compile_return(self, stmt: ReturnStmt):
        if not stmt.values:
            self._emit(Opcode.RETURN, ["0"], node=stmt)
        else:
            regs: List[str] = []
            total = len(stmt.values)
            for idx, expr in enumerate(stmt.values):
                last = idx == total - 1
                if isinstance(expr, (CallExpr, MethodCallExpr)) and last:
                    reg = self._compile_call_like(expr, want_list=True)
                elif isinstance(expr, VarargExpr):
                    reg = self._compile_vararg_expr(multi=last, node=expr)
                else:
                    reg = self._compile_expr(expr)
                regs.append(reg)
            if len(regs) == 1 and not isinstance(stmt.values[0], (CallExpr, MethodCallExpr, VarargExpr)):
                self._emit(Opcode.RETURN, [regs[0]], node=stmt)
            else:
                self._emit(Opcode.RETURN_MULTI, regs, node=stmt)
        if self.is_top_level:
            self._emit(Opcode.JMP, [self.exit_label], node=stmt)

    def _compile_function_stmt(self, stmt: FunctionStmt):
        # treat as global function binding
        func_label = stmt.name.name
        info = self.closure_map.get(id(stmt), FunctionInfo())
        compiler = LuaCompiler(
            self.closure_map,
            info,
            info.upvalues,
            source_name=self.source_name,
            function_name=func_label,
        )
        compiler._emit(Opcode.LABEL, [func_label], node=stmt)
        compiler.scope_stack = [{}]
        compiler._bind_upvalues()
        compiler._setup_parameters(stmt.params, info, stmt.vararg, stmt)
        compiler._compile_block(stmt.body)
        compiler._finalize_labels()
        compiler._emit(Opcode.RETURN, ["0"], node=stmt)
        self.function_blocks.extend(compiler.instructions)
        self.function_blocks.extend(compiler.function_blocks)
        self._emit(Opcode.CLOSURE, [f"G_{func_label}", func_label], node=stmt)

    # ------------------------------------------------------------------ Expressions
    def _compile_expr(self, expr: Expr) -> str:
        if isinstance(expr, NumberLiteral):
            return self._emit_literal(expr.value, expr)
        if isinstance(expr, StringLiteral):
            return self._emit_literal(expr.value, expr)
        if isinstance(expr, BooleanLiteral):
            return self._emit_literal(expr.value, expr)
        if isinstance(expr, NilLiteral):
            return self._emit_literal(None, expr)
        if isinstance(expr, Identifier):
            return self._read_identifier(expr)
        if isinstance(expr, UnaryOp):
            operand = self._compile_expr(expr.operand)
            dst = self._new_temp()
            if expr.op == "-":
                self._emit(Opcode.NEG, [dst, operand], node=expr)
            elif expr.op == "not":
                self._emit(Opcode.NOT, [dst, operand], node=expr)
            elif expr.op == "#":
                self._emit(Opcode.LEN, [dst, operand], node=expr)
            elif expr.op == "~":
                self._emit(Opcode.NOT_BIT, [dst, operand], node=expr)
            else:
                raise CompileError(f"Unsupported unary operator {expr.op}")
            return dst
        if isinstance(expr, BinaryOp):
            return self._compile_binary(expr)
        if isinstance(expr, CallExpr):
            return self._compile_call(expr)
        if isinstance(expr, FunctionExpr):
            return self._compile_function_expr(expr)
        if isinstance(expr, VarargExpr):
            return self._compile_vararg_expr(multi=False, node=expr)
        if isinstance(expr, FieldAccess):
            return self._compile_field_access(expr)
        if isinstance(expr, IndexExpr):
            return self._compile_index_expr(expr)
        if isinstance(expr, TableConstructor):
            return self._compile_table_constructor(expr)
        if isinstance(expr, MethodCallExpr):
            return self._compile_method_call(expr)
        raise CompileError(f"Unsupported expression: {expr}")

    def _compile_binary(self, expr: BinaryOp) -> str:
        op = expr.op
        if op == "and":
            left = self._compile_expr(expr.left)
            result = self._new_temp()
            self._emit(Opcode.MOV, [result, left], node=expr.left)
            skip_label = f"__logic_skip_{self._new_temp()}"
            self._emit(Opcode.JZ, [left, skip_label], node=expr)
            right = self._compile_expr(expr.right)
            self._emit(Opcode.MOV, [result, right], node=expr.right)
            self._emit(Opcode.LABEL, [skip_label], node=expr)
            return result
        if op == "or":
            left = self._compile_expr(expr.left)
            result = self._new_temp()
            self._emit(Opcode.MOV, [result, left], node=expr.left)
            skip_label = f"__logic_skip_{self._new_temp()}"
            self._emit(Opcode.JNZ, [left, skip_label], node=expr)
            right = self._compile_expr(expr.right)
            self._emit(Opcode.MOV, [result, right], node=expr.right)
            self._emit(Opcode.LABEL, [skip_label], node=expr)
            return result

        left = self._compile_expr(expr.left)
        right = self._compile_expr(expr.right)
        dst = self._new_temp()

        arithmetic = {
            "+": Opcode.ADD,
            "-": Opcode.SUB,
            "*": Opcode.MUL,
            "/": Opcode.DIV,
            "%": Opcode.MOD,
            "//": Opcode.IDIV,
            "^": Opcode.POW,
            "..": Opcode.CONCAT,
        }
        if op in arithmetic:
            self._emit(arithmetic[op], [dst, left, right], node=expr)
            return dst

        bitwise = {
            "&": Opcode.AND_BIT,
            "|": Opcode.OR_BIT,
            "~": Opcode.XOR,
            "<<": Opcode.SHL,
            ">>": Opcode.SAR,
        }
        if op in bitwise:
            self._emit(bitwise[op], [dst, left, right], node=expr)
            return dst

        comp_table = {
            "==": Opcode.EQ,
            "<": Opcode.LT,
            ">": Opcode.GT,
        }
        if op in comp_table:
            self._emit(comp_table[op], [dst, left, right], node=expr)
            return dst
        if op == "~=":
            tmp = self._new_temp()
            self._emit(Opcode.EQ, [tmp, left, right], node=expr)
            self._emit(Opcode.NOT, [dst, tmp], node=expr)
            return dst
        if op == "<=":
            tmp = self._new_temp()
            self._emit(Opcode.GT, [tmp, left, right], node=expr)
            self._emit(Opcode.NOT, [dst, tmp], node=expr)
            return dst
        if op == ">=":
            tmp = self._new_temp()
            self._emit(Opcode.LT, [tmp, left, right], node=expr)
            self._emit(Opcode.NOT, [dst, tmp], node=expr)
            return dst
        raise CompileError(f"Unsupported binary operator {op}")

    def _compile_call_like(self, expr: Expr, want_list: bool = False) -> str:
        if isinstance(expr, CallExpr):
            return self._compile_call(expr, want_list=want_list)
        if isinstance(expr, MethodCallExpr):
            return self._compile_method_call(expr, want_list=want_list)
        raise CompileError("Expected call expression")

    def _compile_call(self, expr: CallExpr, want_list: bool = False) -> str:
        callee_reg = self._compile_expr(expr.callee)
        total_args = len(expr.args)
        prepared_args = []
        for idx, arg in enumerate(expr.args):
            last = idx == total_args - 1
            if last and isinstance(arg, (CallExpr, MethodCallExpr)):
                arg_reg = self._compile_call_like(arg, want_list=True)
                prepared_args.append((arg_reg, True))
            elif last and isinstance(arg, VarargExpr):
                arg_reg = self._compile_vararg_expr(multi=True, node=arg)
                prepared_args.append((arg_reg, True))
            else:
                if isinstance(arg, VarargExpr):
                    arg_reg = self._compile_vararg_expr(multi=False, node=arg)
                elif isinstance(arg, MethodCallExpr):
                    arg_reg = self._compile_method_call(arg)
                elif isinstance(arg, CallExpr):
                    arg_reg = self._compile_call(arg)
                else:
                    arg_reg = self._compile_expr(arg)
                prepared_args.append((arg_reg, False))
        for reg, expand in prepared_args:
            opcode = Opcode.PARAM_EXPAND if expand else Opcode.PARAM
            self._emit(opcode, [reg], node=expr)
        self._emit(Opcode.CALL_VALUE, [callee_reg], node=expr)
        if want_list:
            dst = self._new_temp()
            self._emit(Opcode.RESULT_LIST, [dst], node=expr)
            return dst
        dst = self._new_temp()
        self._emit(Opcode.RESULT, [dst], node=expr)
        return dst

    def _compile_method_call(self, expr: MethodCallExpr, want_list: bool = False) -> str:
        receiver_reg = self._compile_expr(expr.receiver)
        key_reg = self._emit_literal(expr.method, expr, hint=self._new_temp())
        callee_reg = self._new_temp()
        self._emit(Opcode.TABLE_GET, [callee_reg, receiver_reg, key_reg], node=expr)

        prepared_args: List[tuple[str, bool]] = [(receiver_reg, False)]
        total_args = len(expr.args)
        for idx, arg in enumerate(expr.args):
            last = idx == total_args - 1
            if last and isinstance(arg, (CallExpr, MethodCallExpr)):
                arg_reg = self._compile_call_like(arg, want_list=True)
                prepared_args.append((arg_reg, True))
            elif last and isinstance(arg, VarargExpr):
                arg_reg = self._compile_vararg_expr(multi=True, node=arg)
                prepared_args.append((arg_reg, True))
            else:
                if isinstance(arg, VarargExpr):
                    arg_reg = self._compile_vararg_expr(multi=False, node=arg)
                elif isinstance(arg, MethodCallExpr):
                    arg_reg = self._compile_method_call(arg)
                elif isinstance(arg, CallExpr):
                    arg_reg = self._compile_call(arg)
                else:
                    arg_reg = self._compile_expr(arg)
                prepared_args.append((arg_reg, False))
        for reg, expand in prepared_args:
            opcode = Opcode.PARAM_EXPAND if expand else Opcode.PARAM
            self._emit(opcode, [reg], node=expr)
        self._emit(Opcode.CALL_VALUE, [callee_reg], node=expr)
        if want_list:
            dst = self._new_temp()
            self._emit(Opcode.RESULT_LIST, [dst], node=expr)
            return dst
        dst = self._new_temp()
        self._emit(Opcode.RESULT, [dst], node=expr)
        return dst

    def _compile_function_expr(self, expr: FunctionExpr) -> str:
        label = f"__func_{next(_FUNC_LABEL_COUNTER)}"
        info = self.closure_map.get(id(expr), FunctionInfo())
        func_name = f"<anonymous:{expr.line}>"
        child = LuaCompiler(
            self.closure_map,
            info,
            info.upvalues,
            source_name=self.source_name,
            function_name=func_name,
        )
        child._emit(Opcode.LABEL, [label], node=expr)
        child.scope_stack = [{}]
        child._bind_upvalues()
        child._setup_parameters(expr.params, info, expr.vararg, expr)
        child._compile_block(expr.body)
        child._finalize_labels()
        child._emit(Opcode.RETURN, ["0"], node=expr)
        self.function_blocks.extend(child.instructions)
        self.function_blocks.extend(child.function_blocks)

        dst = self._new_temp()
        upvalue_cells = [self._binding_cell(name) for name in info.upvalues]
        args = [dst, label] + upvalue_cells
        self._emit(Opcode.CLOSURE, args, node=expr)
        return dst

    def _compile_vararg_expr(self, multi: bool, node: VarargExpr) -> str:
        binding = self._lookup_binding("...")
        if not binding or not binding.is_vararg:
            raise CompileError("`...` used outside a vararg function")
        dst = self._new_temp()
        if binding.is_cell:
            self._emit(Opcode.CELL_GET, [dst, binding.storage], node=node)
        else:
            self._emit(Opcode.MOV, [dst, binding.storage], node=node)
        if multi:
            return dst
        head = self._new_temp()
        self._emit(Opcode.VARARG_FIRST, [head, dst], node=node)
        return head

    # ------------------------------------------------------------------ Helpers
    def _binding_read(self, binding: VarBinding, node: object) -> str:
        if binding.is_cell:
            dst = self._new_temp()
            self._emit(Opcode.CELL_GET, [dst, binding.storage], node=node)
            return dst
        return binding.storage

    def _binding_write(self, binding: VarBinding, value_reg: str, node: object) -> None:
        if binding.is_cell:
            self._emit(Opcode.CELL_SET, [binding.storage, value_reg], node=node)
        else:
            self._emit(Opcode.MOV, [binding.storage, value_reg], node=node)

    def _binding_cell(self, name: str) -> str:
        binding = self._lookup_binding(name)
        if not binding or not binding.is_cell:
            raise CompileError(f"Expected captured variable '{name}' to be a cell")
        return binding.storage

    def _emit_literal(self, value, node: Expr, hint: Optional[str] = None) -> str:
        dst = hint or self._new_temp()
        if isinstance(value, bool):
            self._emit(Opcode.LOAD_CONST, [dst, value], node=node)
        elif isinstance(value, int):
            self._emit(Opcode.LOAD_IMM, [dst, value], node=node)
        else:
            self._emit(Opcode.LOAD_CONST, [dst, value], node=node)
        return dst

    def _label_symbol(self, name: str) -> str:
        return f"__lua_label_{name}"

    def _finalize_labels(self) -> None:
        for target, depth, node in self.pending_gotos:
            info = self.label_definitions.get(target)
            if info is None:
                raise CompileError(
                    f"undefined label '{target}' referenced at {getattr(node, 'line', '?')}:{getattr(node, 'column', '?')}"
                )
            _, label_depth, _ = info
            if depth < label_depth:
                raise CompileError(
                    f"goto '{target}' jumps into the scope of local variables"
                )
        self.pending_gotos.clear()

    def _read_identifier(self, expr: Identifier) -> str:
        name = expr.name
        binding = self._lookup_binding(name)
        if binding:
            if binding.is_cell:
                dst = self._new_temp()
                self._emit(Opcode.CELL_GET, [dst, binding.storage], node=expr)
                return dst
            return binding.storage
        return f"G_{name}"

    def _compile_field_access(self, expr: FieldAccess) -> str:
        table_reg = self._compile_expr(expr.table)
        key_reg = self._emit_literal(expr.field, expr, hint=self._new_temp())
        dst = self._new_temp()
        self._emit(Opcode.TABLE_GET, [dst, table_reg, key_reg], node=expr)
        return dst

    def _compile_index_expr(self, expr: IndexExpr) -> str:
        table_reg = self._compile_expr(expr.table)
        index_reg = self._compile_expr(expr.index)
        dst = self._new_temp()
        self._emit(Opcode.TABLE_GET, [dst, table_reg, index_reg], node=expr)
        return dst

    def _compile_table_constructor(self, expr: TableConstructor) -> str:
        table_reg = self._new_temp()
        self._emit(Opcode.TABLE_NEW, [table_reg], node=expr)
        total = len(expr.fields)
        for idx, field in enumerate(expr.fields):
            value_node = field.value
            if field.key is not None:
                key_reg = self._compile_expr(field.key)
                value_reg = self._compile_expr(field.value)
                self._emit(Opcode.TABLE_SET, [table_reg, key_reg, value_reg], node=value_node)
                continue
            if field.name is not None:
                key_reg = self._emit_literal(field.name, value_node, hint=self._new_temp())
                value_reg = self._compile_expr(field.value)
                self._emit(Opcode.TABLE_SET, [table_reg, key_reg, value_reg], node=value_node)
                continue
            is_last = idx == total - 1
            if is_last and isinstance(field.value, (CallExpr, MethodCallExpr)):
                list_reg = self._compile_call_like(field.value, want_list=True)
                self._emit(Opcode.TABLE_EXTEND, [table_reg, list_reg], node=value_node)
                continue
            if is_last and isinstance(field.value, VarargExpr):
                list_reg = self._compile_vararg_expr(multi=True, node=field.value)
                self._emit(Opcode.TABLE_EXTEND, [table_reg, list_reg], node=value_node)
                continue
            if isinstance(field.value, (CallExpr, MethodCallExpr)):
                value_reg = self._compile_call_like(field.value)
            elif isinstance(field.value, VarargExpr):
                value_reg = self._compile_vararg_expr(multi=False, node=field.value)
            else:
                value_reg = self._compile_expr(field.value)
            self._emit(Opcode.TABLE_APPEND, [table_reg, value_reg], node=value_node)
        return table_reg

__all__ = ["LuaCompiler", "CompileError"]
