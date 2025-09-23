from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from compiler.bytecode import Instruction, Opcode

from .ast import (
    Assignment,
    BinaryOp,
    Block,
    BooleanLiteral,
    CallExpr,
    Chunk,
    Expr,
    ExprStmt,
    FunctionStmt,
    Identifier,
    IfStmt,
    NilLiteral,
    NumberLiteral,
    ReturnStmt,
    StringLiteral,
    UnaryOp,
    WhileStmt,
)


class CompileError(RuntimeError):
    pass


class LuaCompiler:
    def __init__(self):
        self.instructions: List[Instruction] = []
        self.temp_counter = 0
        self.function_blocks: List[Instruction] = []
        self.current_scope: List[Dict[str, str]] = []
        self.exit_label = "__lua_exit"
        self._top_level_block = False

    def compile(self, chunk: Chunk) -> List[Instruction]:
        self.instructions.clear()
        self.function_blocks.clear()
        self.temp_counter = 0
        self.current_scope = [{}]
        self.exit_label = "__lua_exit"
        self._compile_block(chunk.body, top_level=True)
        self.instructions.append(Instruction(Opcode.JMP, [self.exit_label]))
        self.instructions.extend(self.function_blocks)
        self.instructions.append(Instruction(Opcode.LABEL, [self.exit_label]))
        self.instructions.append(Instruction(Opcode.HALT, []))
        return list(self.instructions)

    # ----------------------------- helpers ----------------------------- #
    def _new_temp(self) -> str:
        name = f"__t{self.temp_counter}"
        self.temp_counter += 1
        return name

    def _resolve_var(self, name: str) -> str:
        for scope in reversed(self.current_scope):
            if name in scope:
                return scope[name]
        reg = f"G_{name}"
        return reg

    def _declare_var(self, name: str) -> str:
        reg = f"L_{len(self.current_scope)-1}_{name}_{self.temp_counter}"
        self.temp_counter += 1
        self.current_scope[-1][name] = reg
        return reg

    def _load_literal(self, value, hint: Optional[str] = None) -> str:
        dst = hint or self._new_temp()
        if isinstance(value, int):
            self.instructions.append(Instruction(Opcode.LOAD_IMM, [dst, value]))
        else:
            self.instructions.append(Instruction(Opcode.LOAD_CONST, [dst, value]))
        return dst

    # ----------------------------- statements ------------------------- #
    def _compile_block(self, block: Block, top_level: bool = False):
        prev = self._top_level_block
        self._top_level_block = top_level
        self.current_scope.append({})
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
                self._compile_function(stmt)
            elif isinstance(stmt, ExprStmt):
                self._compile_expr(stmt.expr)
            else:
                raise CompileError(f"Unsupported statement: {stmt}")
        self.current_scope.pop()
        self._top_level_block = prev

    def _compile_assignment(self, stmt: Assignment):
        value_reg = self._compile_expr(stmt.value)
        if stmt.is_local:
            target_reg = self._declare_var(stmt.target.name)
        else:
            target_reg = self._resolve_var(stmt.target.name)
        self.instructions.append(Instruction(Opcode.MOV, [target_reg, value_reg]))

    def _compile_if(self, stmt: IfStmt):
        cond_reg = self._compile_expr(stmt.condition)
        else_label = f"__else_{id(stmt)}"
        end_label = f"__endif_{id(stmt)}"
        self.instructions.append(Instruction(Opcode.JZ, [cond_reg, else_label]))
        self._compile_block(stmt.then_branch)
        self.instructions.append(Instruction(Opcode.JMP, [end_label]))
        self.instructions.append(Instruction(Opcode.LABEL, [else_label]))
        if stmt.else_branch:
            self._compile_block(stmt.else_branch)
        self.instructions.append(Instruction(Opcode.LABEL, [end_label]))

    def _compile_while(self, stmt: WhileStmt):
        start_label = f"__while_start_{id(stmt)}"
        end_label = f"__while_end_{id(stmt)}"
        self.instructions.append(Instruction(Opcode.LABEL, [start_label]))
        cond_reg = self._compile_expr(stmt.condition)
        self.instructions.append(Instruction(Opcode.JZ, [cond_reg, end_label]))
        self._compile_block(stmt.body)
        self.instructions.append(Instruction(Opcode.JMP, [start_label]))
        self.instructions.append(Instruction(Opcode.LABEL, [end_label]))

    def _compile_return(self, stmt: ReturnStmt):
        if stmt.value is None:
            self.instructions.append(Instruction(Opcode.RETURN, ["0"]))
        else:
            value_reg = self._compile_expr(stmt.value)
            self.instructions.append(Instruction(Opcode.RETURN, [value_reg]))
        if self._top_level_block:
            self.instructions.append(Instruction(Opcode.JMP, [self.exit_label]))

    def _compile_function(self, stmt: FunctionStmt):
        func_label = stmt.name.name
        # store reference in globals（用于直接 CALL）
        self.instructions.append(Instruction(Opcode.LOAD_CONST, [f"G_{func_label}", func_label]))

        func_compiler = LuaCompiler()
        func_compiler.instructions.append(Instruction(Opcode.LABEL, [func_label]))
        func_compiler.current_scope = [{}]
        # 参数放在最外层作用域
        for param in stmt.params:
            reg = func_compiler._declare_var(param)
            func_compiler.instructions.append(Instruction(Opcode.ARG, [reg]))
        func_compiler._compile_block(stmt.body)
        func_compiler.instructions.append(Instruction(Opcode.RETURN, ["0"]))
        self.function_blocks.extend(func_compiler.instructions)

    # ----------------------------- expressions ------------------------ #
    def _compile_expr(self, expr: Expr) -> str:
        if isinstance(expr, NumberLiteral):
            return self._load_literal(expr.value)
        if isinstance(expr, StringLiteral):
            return self._load_literal(expr.value)
        if isinstance(expr, BooleanLiteral):
            return self._load_literal(int(expr.value))
        if isinstance(expr, NilLiteral):
            return self._load_literal(None)
        if isinstance(expr, Identifier):
            return self._resolve_var(expr.name)
        if isinstance(expr, UnaryOp):
            operand = self._compile_expr(expr.operand)
            dst = self._new_temp()
            if expr.op == "-":
                self.instructions.append(Instruction(Opcode.NEG, [dst, operand]))
                return dst
            if expr.op == "not":
                self.instructions.append(Instruction(Opcode.NOT, [dst, operand]))
                return dst
            raise CompileError(f"Unsupported unary operator {expr.op}")
        if isinstance(expr, BinaryOp):
            left = self._compile_expr(expr.left)
            right = self._compile_expr(expr.right)
            dst = self._new_temp()
            op = expr.op
            if op == "+":
                self.instructions.append(Instruction(Opcode.ADD, [dst, left, right]))
            elif op == "-":
                self.instructions.append(Instruction(Opcode.SUB, [dst, left, right]))
            elif op == "*":
                self.instructions.append(Instruction(Opcode.MUL, [dst, left, right]))
            elif op == "/":
                self.instructions.append(Instruction(Opcode.DIV, [dst, left, right]))
            elif op == "%":
                self.instructions.append(Instruction(Opcode.MOD, [dst, left, right]))
            elif op == "==":
                self.instructions.append(Instruction(Opcode.EQ, [dst, left, right]))
            elif op == "~=":
                tmp = self._new_temp()
                self.instructions.append(Instruction(Opcode.EQ, [tmp, left, right]))
                self.instructions.append(Instruction(Opcode.NOT, [dst, tmp]))
            elif op == "<":
                self.instructions.append(Instruction(Opcode.LT, [dst, left, right]))
            elif op == ">":
                self.instructions.append(Instruction(Opcode.GT, [dst, left, right]))
            elif op == "<=":
                tmp = self._new_temp()
                self.instructions.append(Instruction(Opcode.GT, [tmp, left, right]))
                self.instructions.append(Instruction(Opcode.NOT, [dst, tmp]))
            elif op == ">=":
                tmp = self._new_temp()
                self.instructions.append(Instruction(Opcode.LT, [tmp, left, right]))
                self.instructions.append(Instruction(Opcode.NOT, [dst, tmp]))
            else:
                raise CompileError(f"Unsupported binary operator {op}")
            return dst
        if isinstance(expr, CallExpr):
            if not isinstance(expr.callee, Identifier):
                raise CompileError("Only direct function calls supported in Milestone 1")
            func_name = expr.callee.name
            for arg in expr.args:
                arg_reg = self._compile_expr(arg)
                self.instructions.append(Instruction(Opcode.PARAM, [arg_reg]))
            self.instructions.append(Instruction(Opcode.CALL, [func_name]))
            dst = self._new_temp()
            self.instructions.append(Instruction(Opcode.RESULT, [dst]))
            return dst
        raise CompileError(f"Unsupported expression: {expr}")

__all__ = ["LuaCompiler", "CompileError"]
