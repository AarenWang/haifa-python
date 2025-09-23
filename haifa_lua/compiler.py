from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional

from compiler.bytecode import Instruction, Opcode

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
    FunctionExpr,
    FunctionStmt,
    Identifier,
    IfStmt,
    NilLiteral,
    NumberLiteral,
    ReturnStmt,
    StringLiteral,
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
    def __init__(self, closure_map: Dict[int, FunctionInfo], function_info: FunctionInfo, upvalue_names: Optional[List[str]] = None):
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

    # ------------------------------------------------------------------
    @classmethod
    def compile_chunk(cls, chunk: Chunk) -> List[Instruction]:
        closure_map, root_info = analyze(chunk)
        compiler = cls(closure_map, root_info, root_info.upvalues)
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
        self.instructions.append(Instruction(Opcode.JMP, [self.exit_label]))
        self.instructions.extend(self.function_blocks)
        self.instructions.append(Instruction(Opcode.LABEL, [self.exit_label]))
        self.instructions.append(Instruction(Opcode.HALT, []))
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
            self.instructions.append(Instruction(Opcode.BIND_UPVALUE, [cell_reg, str(idx)]))

    def _setup_parameters(self, params: List[str], info: FunctionInfo, is_vararg: bool):
        scope = self.scope_stack[-1]
        for param in params:
            captured = param in info.captured_locals
            reg = self._alloc_local_reg(param)
            scope[param] = VarBinding(reg, False)
            self.instructions.append(Instruction(Opcode.ARG, [reg]))
            if captured:
                cell_reg = self._alloc_cell_reg(param)
                scope[param] = VarBinding(cell_reg, True)
                self.instructions.append(Instruction(Opcode.MAKE_CELL, [cell_reg, reg]))
        if is_vararg:
            var_reg = self._alloc_local_reg("__vararg")
            captured = "..." in info.captured_locals
            scope["..."] = VarBinding(var_reg, False, True)
            self.instructions.append(Instruction(Opcode.VARARG, [var_reg]))
            if captured:
                cell_reg = self._alloc_cell_reg("vararg")
                scope["..."] = VarBinding(cell_reg, True, True)
                self.instructions.append(Instruction(Opcode.MAKE_CELL, [cell_reg, var_reg]))

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
        value_reg = self._compile_expr(stmt.value)
        binding = self._lookup_binding(stmt.target.name)
        if stmt.is_local:
            captured = stmt.target.name in self.function_info.captured_locals
            if captured:
                cell_reg = self._alloc_cell_reg(stmt.target.name)
                self.scope_stack[-1][stmt.target.name] = VarBinding(cell_reg, True)
                self.instructions.append(Instruction(Opcode.MAKE_CELL, [cell_reg, value_reg]))
            else:
                reg = self._alloc_local_reg(stmt.target.name)
                self.scope_stack[-1][stmt.target.name] = VarBinding(reg, False)
                self.instructions.append(Instruction(Opcode.MOV, [reg, value_reg]))
            return

        if binding:
            if binding.is_cell:
                self.instructions.append(Instruction(Opcode.CELL_SET, [binding.storage, value_reg]))
            else:
                self.instructions.append(Instruction(Opcode.MOV, [binding.storage, value_reg]))
        else:
            self.instructions.append(Instruction(Opcode.MOV, [f"G_{stmt.target.name}", value_reg]))

    def _compile_if(self, stmt: IfStmt):
        cond_reg = self._compile_expr(stmt.condition)
        else_label = f"__else_{self._new_temp()}"
        end_label = f"__endif_{self._new_temp()}"
        self.instructions.append(Instruction(Opcode.JZ, [cond_reg, else_label]))
        self._compile_block(stmt.then_branch)
        self.instructions.append(Instruction(Opcode.JMP, [end_label]))
        self.instructions.append(Instruction(Opcode.LABEL, [else_label]))
        if stmt.else_branch:
            self._compile_block(stmt.else_branch)
        self.instructions.append(Instruction(Opcode.LABEL, [end_label]))

    def _compile_while(self, stmt: WhileStmt):
        start_label = f"__while_start_{self._new_temp()}"
        end_label = f"__while_end_{self._new_temp()}"
        self.instructions.append(Instruction(Opcode.LABEL, [start_label]))
        cond_reg = self._compile_expr(stmt.condition)
        self.instructions.append(Instruction(Opcode.JZ, [cond_reg, end_label]))
        self._compile_block(stmt.body)
        self.instructions.append(Instruction(Opcode.JMP, [start_label]))
        self.instructions.append(Instruction(Opcode.LABEL, [end_label]))

    def _compile_return(self, stmt: ReturnStmt):
        if not stmt.values:
            self.instructions.append(Instruction(Opcode.RETURN, ["0"]))
        else:
            regs: List[str] = []
            total = len(stmt.values)
            for idx, expr in enumerate(stmt.values):
                last = idx == total - 1
                if isinstance(expr, CallExpr) and last:
                    reg = self._compile_call(expr, want_list=True)
                elif isinstance(expr, VarargExpr):
                    reg = self._compile_vararg_expr(multi=last)
                else:
                    reg = self._compile_expr(expr)
                regs.append(reg)
            if len(regs) == 1 and not isinstance(stmt.values[0], (CallExpr, VarargExpr)):
                self.instructions.append(Instruction(Opcode.RETURN, [regs[0]]))
            else:
                self.instructions.append(Instruction(Opcode.RETURN_MULTI, regs))
        if self.is_top_level:
            self.instructions.append(Instruction(Opcode.JMP, [self.exit_label]))

    def _compile_function_stmt(self, stmt: FunctionStmt):
        # treat as global function binding
        func_label = stmt.name.name
        info = self.closure_map.get(id(stmt), FunctionInfo())
        compiler = LuaCompiler(self.closure_map, info, info.upvalues)
        compiler.instructions.append(Instruction(Opcode.LABEL, [func_label]))
        compiler.scope_stack = [{}]
        compiler._bind_upvalues()
        compiler._setup_parameters(stmt.params, info, stmt.vararg)
        compiler._compile_block(stmt.body)
        compiler.instructions.append(Instruction(Opcode.RETURN, ["0"]))
        self.function_blocks.extend(compiler.instructions)
        self.function_blocks.extend(compiler.function_blocks)
        self.instructions.append(Instruction(Opcode.CLOSURE, [f"G_{func_label}", func_label]))

    # ------------------------------------------------------------------ Expressions
    def _compile_expr(self, expr: Expr) -> str:
        if isinstance(expr, NumberLiteral):
            return self._emit_literal(expr.value)
        if isinstance(expr, StringLiteral):
            return self._emit_literal(expr.value)
        if isinstance(expr, BooleanLiteral):
            return self._emit_literal(int(expr.value))
        if isinstance(expr, NilLiteral):
            return self._emit_literal(None)
        if isinstance(expr, Identifier):
            return self._read_identifier(expr.name)
        if isinstance(expr, UnaryOp):
            operand = self._compile_expr(expr.operand)
            dst = self._new_temp()
            if expr.op == "-":
                self.instructions.append(Instruction(Opcode.NEG, [dst, operand]))
            elif expr.op == "not":
                self.instructions.append(Instruction(Opcode.NOT, [dst, operand]))
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
            return self._compile_vararg_expr(multi=False)
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
            self.instructions.append(Instruction(table[op], [dst, left, right]))
            return dst
        comp_table = {
            "==": Opcode.EQ,
            "<": Opcode.LT,
            ">": Opcode.GT,
        }
        if op in comp_table:
            self.instructions.append(Instruction(comp_table[op], [dst, left, right]))
            return dst
        if op == "~=":
            tmp = self._new_temp()
            self.instructions.append(Instruction(Opcode.EQ, [tmp, left, right]))
            self.instructions.append(Instruction(Opcode.NOT, [dst, tmp]))
            return dst
        if op == "<=":
            tmp = self._new_temp()
            self.instructions.append(Instruction(Opcode.GT, [tmp, left, right]))
            self.instructions.append(Instruction(Opcode.NOT, [dst, tmp]))
            return dst
        if op == ">=":
            tmp = self._new_temp()
            self.instructions.append(Instruction(Opcode.LT, [tmp, left, right]))
            self.instructions.append(Instruction(Opcode.NOT, [dst, tmp]))
            return dst
        if op == "and":
            tmp = self._new_temp()
            self.instructions.append(Instruction(Opcode.AND, [tmp, left, right]))
            self.instructions.append(Instruction(Opcode.MOV, [dst, tmp]))
            return dst
        if op == "or":
            tmp = self._new_temp()
            self.instructions.append(Instruction(Opcode.OR, [tmp, left, right]))
            self.instructions.append(Instruction(Opcode.MOV, [dst, tmp]))
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
                arg_reg = self._compile_vararg_expr(multi=True)
                prepared_args.append((arg_reg, True))
            else:
                if isinstance(arg, VarargExpr):
                    arg_reg = self._compile_vararg_expr(multi=False)
                else:
                    arg_reg = self._compile_expr(arg)
                prepared_args.append((arg_reg, False))
        for reg, expand in prepared_args:
            opcode = Opcode.PARAM_EXPAND if expand else Opcode.PARAM
            self.instructions.append(Instruction(opcode, [reg]))
        self.instructions.append(Instruction(Opcode.CALL_VALUE, [callee_reg]))
        if want_list:
            dst = self._new_temp()
            self.instructions.append(Instruction(Opcode.RESULT_LIST, [dst]))
            return dst
        dst = self._new_temp()
        self.instructions.append(Instruction(Opcode.RESULT, [dst]))
        return dst

    def _compile_function_expr(self, expr: FunctionExpr) -> str:
        label = f"__func_{next(_FUNC_LABEL_COUNTER)}"
        info = self.closure_map.get(id(expr), FunctionInfo())
        child = LuaCompiler(self.closure_map, info, info.upvalues)
        child.instructions.append(Instruction(Opcode.LABEL, [label]))
        child.scope_stack = [{}]
        child._bind_upvalues()
        child._setup_parameters(expr.params, info, expr.vararg)
        child._compile_block(expr.body)
        child.instructions.append(Instruction(Opcode.RETURN, ["0"]))
        self.function_blocks.extend(child.instructions)
        self.function_blocks.extend(child.function_blocks)

        dst = self._new_temp()
        upvalue_cells = [self._binding_cell(name) for name in info.upvalues]
        args = [dst, label] + upvalue_cells
        self.instructions.append(Instruction(Opcode.CLOSURE, args))
        return dst

    def _compile_vararg_expr(self, multi: bool) -> str:
        binding = self._lookup_binding("...")
        if not binding or not binding.is_vararg:
            raise CompileError("`...` used outside a vararg function")
        dst = self._new_temp()
        if binding.is_cell:
            self.instructions.append(Instruction(Opcode.CELL_GET, [dst, binding.storage]))
        else:
            self.instructions.append(Instruction(Opcode.MOV, [dst, binding.storage]))
        if multi:
            return dst
        head = self._new_temp()
        self.instructions.append(Instruction(Opcode.VARARG_FIRST, [head, dst]))
        return head

    # ------------------------------------------------------------------ Helpers
    def _binding_cell(self, name: str) -> str:
        binding = self._lookup_binding(name)
        if not binding or not binding.is_cell:
            raise CompileError(f"Expected captured variable '{name}' to be a cell")
        return binding.storage

    def _emit_literal(self, value, hint: Optional[str] = None) -> str:
        dst = hint or self._new_temp()
        if isinstance(value, int):
            self.instructions.append(Instruction(Opcode.LOAD_IMM, [dst, value]))
        else:
            self.instructions.append(Instruction(Opcode.LOAD_CONST, [dst, value]))
        return dst

    def _read_identifier(self, name: str) -> str:
        binding = self._lookup_binding(name)
        if binding:
            if binding.is_cell:
                dst = self._new_temp()
                self.instructions.append(Instruction(Opcode.CELL_GET, [dst, binding.storage]))
                return dst
            return binding.storage
        return f"G_{name}"

__all__ = ["LuaCompiler", "CompileError"]
