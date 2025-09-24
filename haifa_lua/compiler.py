from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional

from compiler.bytecode import Instruction, InstructionDebug, Opcode, SourceLocation

from .analysis import FunctionInfo, analyze
from .ast import (
    Assignment,
    BinaryOp,
    Block,
    BooleanLiteral,
    CallExpr,
    Chunk,
    Expr,
    ExprStmt,
    FieldAccess,
    FunctionExpr,
    FunctionStmt,
    Identifier,
    IfStmt,
    IndexExpr,
    MethodCallExpr,
    NilLiteral,
    NumberLiteral,
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
        if top_level:
            self.is_top_level = True
        else:
            self.is_top_level = False
        self._push_scope()
        for stmt in block.statements:
            if isinstance(stmt, Assignment):
                self._compile_assignment(stmt)
            elif isinstance(stmt, IfStmt):
                self._compile_if(stmt)
            elif isinstance(stmt, WhileStmt):
                self._compile_while(stmt)
            elif isinstance(stmt, ReturnStmt):
                self._compile_return(stmt)
            elif isinstance(stmt, FunctionStmt):
                self._compile_function_stmt(stmt)
            elif isinstance(stmt, ExprStmt):
                self._compile_expr(stmt.expr)
            else:
                raise CompileError(f"Unsupported statement: {stmt}")
        self._pop_scope()
        self.is_top_level = prev_top

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
        if isinstance(expr, CallExpr):
            return self._compile_call(expr)
        if isinstance(expr, VarargExpr):
            return self._compile_vararg_expr(multi=False, node=expr)
        return self._compile_expr(expr)

    def _eval_last_assignment_expr(self, expr: Expr, needed: int) -> List[str]:
        if needed <= 0:
            self._eval_assignment_expr(expr)
            return []
        if isinstance(expr, CallExpr):
            if needed == 1:
                return [self._compile_call(expr)]
            list_reg = self._compile_call(expr, want_list=True)
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
        raise CompileError("Assignment target type is not supported yet")

    def _compile_if(self, stmt: IfStmt):
        cond_reg = self._compile_expr(stmt.condition)
        else_label = f"__else_{self._new_temp()}"
        end_label = f"__endif_{self._new_temp()}"
        self._emit(Opcode.JZ, [cond_reg, else_label], node=stmt)
        self._compile_block(stmt.then_branch)
        self._emit(Opcode.JMP, [end_label], node=stmt)
        self._emit(Opcode.LABEL, [else_label], node=stmt)
        if stmt.else_branch:
            self._compile_block(stmt.else_branch)
        self._emit(Opcode.LABEL, [end_label], node=stmt)

    def _compile_while(self, stmt: WhileStmt):
        start_label = f"__while_start_{self._new_temp()}"
        end_label = f"__while_end_{self._new_temp()}"
        self._emit(Opcode.LABEL, [start_label], node=stmt)
        cond_reg = self._compile_expr(stmt.condition)
        self._emit(Opcode.JZ, [cond_reg, end_label], node=stmt)
        self._compile_block(stmt.body)
        self._emit(Opcode.JMP, [start_label], node=stmt)
        self._emit(Opcode.LABEL, [end_label], node=stmt)

    def _compile_return(self, stmt: ReturnStmt):
        if not stmt.values:
            self._emit(Opcode.RETURN, ["0"], node=stmt)
        else:
            regs: List[str] = []
            total = len(stmt.values)
            for idx, expr in enumerate(stmt.values):
                last = idx == total - 1
                if isinstance(expr, CallExpr) and last:
                    reg = self._compile_call(expr, want_list=True)
                elif isinstance(expr, VarargExpr):
                    reg = self._compile_vararg_expr(multi=last, node=expr)
                else:
                    reg = self._compile_expr(expr)
                regs.append(reg)
            if len(regs) == 1 and not isinstance(stmt.values[0], (CallExpr, VarargExpr)):
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
            return self._emit_literal(int(expr.value), expr)
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
        if isinstance(expr, (MethodCallExpr, IndexExpr, TableConstructor)):
            raise CompileError("Unsupported expression: tables and method calls are not implemented yet")
        raise CompileError(f"Unsupported expression: {expr}")

    def _compile_binary(self, expr: BinaryOp) -> str:
        left = self._compile_expr(expr.left)
        right = self._compile_expr(expr.right)
        dst = self._new_temp()
        op = expr.op
        table = {
            "+": Opcode.ADD,
            "-": Opcode.SUB,
            "*": Opcode.MUL,
            "/": Opcode.DIV,
            "%": Opcode.MOD,
        }
        if op in table:
            self._emit(table[op], [dst, left, right], node=expr)
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
        if op == "and":
            tmp = self._new_temp()
            self._emit(Opcode.AND, [tmp, left, right], node=expr)
            self._emit(Opcode.MOV, [dst, tmp], node=expr)
            return dst
        if op == "or":
            tmp = self._new_temp()
            self._emit(Opcode.OR, [tmp, left, right], node=expr)
            self._emit(Opcode.MOV, [dst, tmp], node=expr)
            return dst
        raise CompileError(f"Unsupported binary operator {op}")

    def _compile_call(self, expr: CallExpr, want_list: bool = False) -> str:
        callee_reg = self._compile_expr(expr.callee)
        total_args = len(expr.args)
        prepared_args = []
        for idx, arg in enumerate(expr.args):
            last = idx == total_args - 1
            if last and isinstance(arg, CallExpr):
                arg_reg = self._compile_call(arg, want_list=True)
                prepared_args.append((arg_reg, True))
            elif last and isinstance(arg, VarargExpr):
                arg_reg = self._compile_vararg_expr(multi=True, node=arg)
                prepared_args.append((arg_reg, True))
            else:
                if isinstance(arg, VarargExpr):
                    arg_reg = self._compile_vararg_expr(multi=False, node=arg)
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
    def _binding_cell(self, name: str) -> str:
        binding = self._lookup_binding(name)
        if not binding or not binding.is_cell:
            raise CompileError(f"Expected captured variable '{name}' to be a cell")
        return binding.storage

    def _emit_literal(self, value, node: Expr, hint: Optional[str] = None) -> str:
        dst = hint or self._new_temp()
        if isinstance(value, int):
            self._emit(Opcode.LOAD_IMM, [dst, value], node=node)
        else:
            self._emit(Opcode.LOAD_CONST, [dst, value], node=node)
        return dst

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
        chain = self._field_chain(expr)
        if not chain:
            raise CompileError("Field access on non-identifier bases is not supported yet")
        base_name = chain[0]
        binding = self._lookup_binding(base_name)
        if binding is not None:
            raise CompileError("Field access on local tables is not implemented yet")
        full_name = ".".join(chain)
        return f"G_{full_name}"

    def _field_chain(self, expr: FieldAccess) -> Optional[List[str]]:
        parts: List[str] = [expr.field]
        current: Expr = expr.table
        while isinstance(current, FieldAccess):
            parts.insert(0, current.field)
            current = current.table
        if isinstance(current, Identifier):
            parts.insert(0, current.name)
            return parts
        return None

__all__ = ["LuaCompiler", "CompileError"]
