"""Scheme bytecode compiler for the VM backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from compiler.bytecode import Instruction, InstructionDebug, Opcode, SourceLocation
from compiler.vm_errors import VMRuntimeError
from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError, SchemeVMRuntimeError
from haifa_scheme.macros import SyntaxRulesMacro, parse_syntax_rules
from haifa_scheme.reader import DottedList, LocatedDatum, Symbol, parse_source_with_locations
from haifa_scheme.values import EMPTY_LIST, Pair, Vector
from haifa_scheme.vm_runtime import (
    SchemeVMRuntime,
    _LETREC_UNINITIALIZED,
    mangle_global_name,
    mangle_internal_name,
)


@dataclass
class VarBinding:
    storage: str
    is_cell: bool = False
    read_guard_name: str | None = None


class SchemeCompileError(RuntimeError):
    pass


class SchemeCompiler:
    def __init__(
        self,
        runtime: SchemeVMRuntime | None = None,
        *,
        parent: "SchemeCompiler | None" = None,
        function_name: str = "<chunk>",
    ) -> None:
        self.runtime = runtime or SchemeVMRuntime()
        self.parent_compiler = parent
        self.root = parent.root if parent is not None else self
        self.instructions: list[Instruction] = []
        self.function_blocks: list[Instruction] = []
        self.temp_counter = 0
        self.source_name = "<input>"
        self.function_name = function_name
        self.scope_stack: list[dict[str, VarBinding]] = []
        self._upvalue_bindings: dict[str, VarBinding] = {}
        self._upvalue_order: list[str] = []
        self._upvalue_source_cells: list[str] = []
        self.result_registers: list[str] = []
        if parent is None:
            self._known_globals = {
                name[len("G_SCHEME_") :]
                for name in self.runtime.to_vm_registers().keys()
                if name.startswith("G_SCHEME_")
            }
            self._macro_env: dict[str, SyntaxRulesMacro] = {}
            self._function_counter = 0

    def compile_source(self, source: str, *, source_name: str = "<input>") -> list[Instruction]:
        expressions = parse_source_with_locations(source, source_name=source_name)
        return self.compile_expressions(expressions, source_name=source_name)

    def compile_expressions(
        self, expressions: Sequence[LocatedDatum], *, source_name: str = "<input>"
    ) -> list[Instruction]:
        self.instructions = []
        self.function_blocks = []
        self.temp_counter = 0
        self.result_registers = []
        self.source_name = source_name
        self.scope_stack = [{}]

        if not expressions:
            self._emit(Opcode.HALT, [], None)
            return list(self.instructions)

        for index, expression in enumerate(expressions):
            result_reg = self._compile_expression(expression)
            stored_reg = f"SCHEME_RESULT_{index}"
            self.result_registers.append(stored_reg)
            self._emit(Opcode.MOV, [stored_reg, result_reg], expression)

        self._emit(Opcode.RETURN, [self.result_registers[-1]], expressions[-1])
        self.instructions.extend(self.function_blocks)
        return list(self.instructions)

    def _compile_expression(self, expression: LocatedDatum) -> str:
        expression = self._macro_expand(expression)
        value = expression.value
        if isinstance(value, list):
            return self._compile_list_expression(expression)
        if isinstance(value, Symbol):
            return self._read_symbol(str(value), expression)
        return self._emit_literal(self._literal_to_runtime_value(expression), expression)

    def _compile_list_expression(self, expression: LocatedDatum) -> str:
        items = expression.value
        if not items:
            raise SchemeCompileError("cannot evaluate empty list")

        operator = items[0]
        operator_value = self._unwrap(operator)
        if isinstance(operator_value, Symbol):
            if operator_value == "quote":
                return self._compile_quote(items, expression)
            if operator_value == "begin":
                return self._compile_begin(items, expression)
            if operator_value == "define":
                return self._compile_define(items, expression)
            if operator_value == "set!":
                return self._compile_set(items, expression)
            if operator_value == "lambda":
                return self._compile_lambda(items, expression)
            if operator_value == "if":
                return self._compile_if(items, expression)
            if operator_value == "let":
                return self._compile_let(items, expression)
            if operator_value == "let*":
                return self._compile_let_star(items, expression)
            if operator_value == "letrec":
                return self._compile_letrec(items, expression)
            if operator_value == "and":
                return self._compile_and(items, expression)
            if operator_value == "or":
                return self._compile_or(items, expression)
            if operator_value == "cond":
                return self._compile_cond(items, expression)
            if operator_value == "case":
                return self._compile_case(items, expression)
            if operator_value == "do":
                return self._compile_do(items, expression)
            if operator_value == "define-syntax":
                return self._compile_define_syntax(items, expression)
        return self._compile_call(items, expression)

    def _compile_define_syntax(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) != 3:
            raise SchemeCompileError("define-syntax expected a name and transformer")
        if self.parent_compiler is not None:
            raise SchemeCompileError("internal define-syntax is unsupported in Phase 7 VM backend")
        name_value = self._unwrap(items[1])
        if not isinstance(name_value, Symbol):
            raise SchemeCompileError("define-syntax expected an identifier name")
        transformer_plain = self._to_plain_datum(items[2])
        try:
            macro = parse_syntax_rules(Symbol(str(name_value)), transformer_plain)
        except SchemeRuntimeError as exc:
            raise SchemeCompileError(
                f"{expression.span.file}:{expression.span.line}: {exc}"
            ) from exc
        self.root._macro_env[str(name_value)] = macro
        return self._emit_literal(None, expression)

    def _compile_quote(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) != 2:
            actual = len(items) - 1
            raise SchemeCompileError(f"quote expected 1 argument(s), got {actual}")
        value = self._datum_to_runtime_value(items[1])
        return self._emit_literal(value, expression)

    def _compile_begin(self, items: Sequence[object], expression: LocatedDatum) -> str:
        body = items[1:]
        if not body:
            raise SchemeCompileError("begin expected at least one expression")
        for subexpression in body[:-1]:
            self._compile_expression(self._as_located(subexpression))
        return self._compile_expression(self._as_located(body[-1]))

    def _compile_define(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) < 3:
            raise SchemeCompileError("define expected a target and value")
        target = self._unwrap(items[1])
        if isinstance(target, Symbol):
            if len(items) != 3:
                raise SchemeCompileError("define expected a target and value")
            value_reg = self._compile_expression(self._as_located(items[2]))
            self._define_symbol(str(target), value_reg, expression)
            return self._emit_literal(None, expression)
        if isinstance(target, list) and target and isinstance(self._unwrap(target[0]), Symbol):
            name = str(self._unwrap(target[0]))
            self.root._known_globals.add(name)
            value_reg = self._compile_lambda_parts(
                params_expr=target[1:],
                body=self._located_tail(items[2:]),
                expression=expression,
                function_name=name,
            )
            self._emit(Opcode.MOV, [mangle_global_name(name), value_reg], expression)
            return self._emit_literal(None, expression)
        raise SchemeCompileError("define expected a symbol or function signature")

    def _compile_set(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) != 3:
            raise SchemeCompileError("set! expected a symbol and value")
        target = self._unwrap(items[1])
        if not isinstance(target, Symbol):
            raise SchemeCompileError("set! expected a symbol")
        value_reg = self._compile_expression(self._as_located(items[2]))
        self._write_symbol(str(target), value_reg, expression)
        return self._emit_literal(None, expression)

    def _compile_lambda(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) < 3:
            raise SchemeCompileError("lambda expected parameters and body")
        params_expr = self._unwrap(items[1])
        if not isinstance(params_expr, list):
            raise SchemeCompileError("lambda expected parameter list")
        return self._compile_lambda_parts(
            params_expr=params_expr,
            body=self._located_tail(items[2:]),
            expression=expression,
            function_name=f"<lambda:{expression.span.line}>",
        )

    def _compile_lambda_parts(
        self,
        *,
        params_expr: Sequence[object],
        body: Sequence[LocatedDatum],
        expression: LocatedDatum,
        function_name: str,
    ) -> str:
        params = self._parse_params(params_expr, function_name)
        if not body:
            raise SchemeCompileError("lambda expected at least one body expression")

        label = self.root._new_function_label()
        child = SchemeCompiler(self.runtime, parent=self, function_name=function_name)
        child.source_name = self.source_name
        child.scope_stack = [{}]
        child._emit(Opcode.LABEL, [label], expression)
        for param in params:
            child._bind_parameter(param, expression)
        for subexpression in body[:-1]:
            child._compile_expression(subexpression)
        result_reg = child._compile_expression(body[-1])
        child._emit(Opcode.RETURN, [result_reg], body[-1])
        self.function_blocks.extend(child.instructions)
        self.function_blocks.extend(child.function_blocks)

        dst = self._new_temp()
        self._emit(Opcode.CLOSURE, [dst, label, *child._upvalue_source_cells], expression)
        return dst

    def _compile_if(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) not in (3, 4):
            actual = len(items) - 1
            raise SchemeCompileError(f"if expected 2 or 3 argument(s), got {actual}")
        cond_reg = self._compile_expression(self._as_located(items[1]))
        else_label = f"__scheme_if_else_{self.root._new_function_label()}"
        end_label = f"__scheme_if_end_{self.root._new_function_label()}"
        result_reg = self._new_temp()

        self._branch_if_false(cond_reg, else_label, expression)
        then_reg = self._compile_expression(self._as_located(items[2]))
        self._emit(Opcode.MOV, [result_reg, then_reg], self._as_located(items[2]))
        self._emit(Opcode.JMP, [end_label], expression)
        self._emit(Opcode.LABEL, [else_label], expression)
        if len(items) == 4:
            else_reg = self._compile_expression(self._as_located(items[3]))
            self._emit(Opcode.MOV, [result_reg, else_reg], self._as_located(items[3]))
        else:
            void_reg = self._emit_literal(None, expression)
            self._emit(Opcode.MOV, [result_reg, void_reg], expression)
        self._emit(Opcode.LABEL, [end_label], expression)
        return result_reg

    def _compile_let(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) < 3:
            raise SchemeCompileError("let expected bindings and body")
        if isinstance(self._unwrap(items[1]), Symbol):
            return self._compile_named_let(items, expression)
        bindings_expr = self._unwrap(items[1])
        if not isinstance(bindings_expr, list):
            raise SchemeCompileError("let expected binding list")

        seen: set[str] = set()
        compiled_bindings: list[tuple[str, str]] = []
        for binding in bindings_expr:
            binding_value = self._unwrap(binding)
            if not isinstance(binding_value, list) or len(binding_value) != 2:
                raise SchemeCompileError("let bindings must be (name value) pairs")
            name = self._unwrap(binding_value[0])
            if not isinstance(name, Symbol):
                raise SchemeCompileError("let binding names must be symbols")
            name_text = str(name)
            if name_text in seen:
                raise SchemeCompileError(f"let duplicate binding: {name}")
            seen.add(name_text)
            value_reg = self._compile_expression(self._as_located(binding_value[1]))
            compiled_bindings.append((name_text, value_reg))

        self._push_scope()
        try:
            for name, value_reg in compiled_bindings:
                self.scope_stack[-1][name] = VarBinding(value_reg)
            for subexpression in items[2:-1]:
                self._compile_expression(self._as_located(subexpression))
            return self._compile_expression(self._as_located(items[-1]))
        finally:
            self._pop_scope()

    def _compile_let_star(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) < 3:
            raise SchemeCompileError("let* expected bindings and body")
        bindings_expr = self._unwrap(items[1])
        if not isinstance(bindings_expr, list):
            raise SchemeCompileError("let* expected binding list")

        self._push_scope()
        try:
            seen: set[str] = set()
            for binding in bindings_expr:
                binding_value = self._unwrap(binding)
                if not isinstance(binding_value, list) or len(binding_value) != 2:
                    raise SchemeCompileError("let* bindings must be (name value) pairs")
                name = self._unwrap(binding_value[0])
                if not isinstance(name, Symbol):
                    raise SchemeCompileError("let* binding names must be symbols")
                name_text = str(name)
                if name_text in seen:
                    raise SchemeCompileError(f"let* duplicate binding: {name}")
                seen.add(name_text)
                value_reg = self._compile_expression(self._as_located(binding_value[1]))
                self.scope_stack[-1][name_text] = VarBinding(value_reg)
            for subexpression in items[2:-1]:
                self._compile_expression(self._as_located(subexpression))
            return self._compile_expression(self._as_located(items[-1]))
        finally:
            self._pop_scope()

    def _compile_named_let(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) < 4:
            raise SchemeCompileError("named let expected name, bindings, and body")
        name = self._unwrap(items[1])
        if not isinstance(name, Symbol):
            raise SchemeCompileError("named let expected a symbol name")
        bindings_expr = self._unwrap(items[2])
        if not isinstance(bindings_expr, list):
            raise SchemeCompileError("named let expected binding list")

        params: list[LocatedDatum] = []
        inits: list[LocatedDatum] = []
        seen: set[str] = set()
        for binding in bindings_expr:
            binding_value = self._unwrap(binding)
            if not isinstance(binding_value, list) or len(binding_value) != 2:
                raise SchemeCompileError("named let bindings must be (name value) pairs")
            param = self._unwrap(binding_value[0])
            if not isinstance(param, Symbol):
                raise SchemeCompileError("named let binding names must be symbols")
            param_name = str(param)
            if param_name in seen:
                raise SchemeCompileError(f"named let duplicate binding: {param}")
            seen.add(param_name)
            params.append(self._synthetic(param, expression))
            inits.append(self._as_located(binding_value[1]))

        lambda_expr = self._synthetic(
            [Symbol("lambda"), params, *self._located_tail(items[3:])],
            expression,
        )
        letrec_expr = self._synthetic(
            [
                Symbol("letrec"),
                [[self._synthetic(name, expression), lambda_expr]],
                [self._synthetic(name, expression), *inits],
            ],
            expression,
        )
        return self._compile_expression(letrec_expr)

    def _compile_letrec(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) < 3:
            raise SchemeCompileError("letrec expected bindings and body")
        bindings_expr = self._unwrap(items[1])
        if not isinstance(bindings_expr, list):
            raise SchemeCompileError("letrec expected binding list")

        self._push_scope()
        try:
            ordered_bindings: list[tuple[str, LocatedDatum]] = []
            seen: set[str] = set()
            for binding in bindings_expr:
                binding_value = self._unwrap(binding)
                if not isinstance(binding_value, list) or len(binding_value) != 2:
                    raise SchemeCompileError("letrec bindings must be (name value) pairs")
                name = self._unwrap(binding_value[0])
                if not isinstance(name, Symbol):
                    raise SchemeCompileError("letrec binding names must be symbols")
                name_text = str(name)
                if name_text in seen:
                    raise SchemeCompileError(f"letrec duplicate binding: {name}")
                seen.add(name_text)
                placeholder_reg = self._emit_literal(_LETREC_UNINITIALIZED, expression)
                cell_reg = self._alloc_cell_reg(name_text)
                self._emit(Opcode.MAKE_CELL, [cell_reg, placeholder_reg], expression)
                self.scope_stack[-1][name_text] = VarBinding(
                    cell_reg, is_cell=True, read_guard_name=name_text
                )
                ordered_bindings.append((name_text, self._as_located(binding_value[1])))

            for name_text, value_expr in ordered_bindings:
                value_reg = self._compile_expression(value_expr)
                self._emit(
                    Opcode.CELL_SET,
                    [self.scope_stack[-1][name_text].storage, value_reg],
                    value_expr,
                )

            for subexpression in items[2:-1]:
                self._compile_expression(self._as_located(subexpression))
            return self._compile_expression(self._as_located(items[-1]))
        finally:
            self._pop_scope()

    def _compile_and(self, items: Sequence[object], expression: LocatedDatum) -> str:
        operands = [self._as_located(item) for item in items[1:]]
        if not operands:
            return self._emit_literal(True, expression)
        if len(operands) == 1:
            return self._compile_expression(operands[0])

        end_label = f"__scheme_and_end_{self.root._new_function_label()}"
        result_reg = self._new_temp()
        for operand in operands[:-1]:
            value_reg = self._compile_expression(operand)
            self._emit(Opcode.MOV, [result_reg, value_reg], operand)
            self._branch_if_false(value_reg, end_label, operand)
        last_reg = self._compile_expression(operands[-1])
        self._emit(Opcode.MOV, [result_reg, last_reg], operands[-1])
        self._emit(Opcode.LABEL, [end_label], expression)
        return result_reg

    def _compile_or(self, items: Sequence[object], expression: LocatedDatum) -> str:
        operands = [self._as_located(item) for item in items[1:]]
        if not operands:
            return self._emit_literal(False, expression)
        if len(operands) == 1:
            return self._compile_expression(operands[0])

        end_label = f"__scheme_or_end_{self.root._new_function_label()}"
        result_reg = self._new_temp()
        for operand in operands[:-1]:
            value_reg = self._compile_expression(operand)
            self._emit(Opcode.MOV, [result_reg, value_reg], operand)
            false_label = f"__scheme_or_next_{self.root._new_function_label()}"
            self._branch_if_false(value_reg, false_label, operand)
            self._emit(Opcode.JMP, [end_label], operand)
            self._emit(Opcode.LABEL, [false_label], operand)
        last_reg = self._compile_expression(operands[-1])
        self._emit(Opcode.MOV, [result_reg, last_reg], operands[-1])
        self._emit(Opcode.LABEL, [end_label], expression)
        return result_reg

    def _compile_cond(self, items: Sequence[object], expression: LocatedDatum) -> str:
        clauses = items[1:]
        if not clauses:
            return self._emit_literal(None, expression)

        result_reg = self._new_temp()
        void_reg = self._emit_literal(None, expression)
        self._emit(Opcode.MOV, [result_reg, void_reg], expression)
        end_label = f"__scheme_cond_end_{self.root._new_function_label()}"
        for index, clause in enumerate(clauses):
            clause_expr = self._as_located(clause)
            clause_value = self._unwrap(clause)
            if not isinstance(clause_value, list) or not clause_value:
                raise SchemeCompileError("cond clauses must be non-empty lists")
            test_expr = self._as_located(clause_value[0])
            test_value = self._unwrap(clause_value[0])
            is_else = isinstance(test_value, Symbol) and test_value == "else"
            if is_else:
                if index != len(clauses) - 1:
                    raise SchemeCompileError("cond else clause must be last")
                if len(clause_value) == 1:
                    raise SchemeCompileError("cond else clause expected a body")
                body_reg = self._compile_sequence(
                    [self._as_located(part) for part in clause_value[1:]],
                    clause_expr,
                )
                self._emit(Opcode.MOV, [result_reg, body_reg], clause_expr)
                self._emit(Opcode.JMP, [end_label], clause_expr)
                break

            next_label = f"__scheme_cond_next_{self.root._new_function_label()}"
            test_reg = self._compile_expression(test_expr)
            self._branch_if_false(test_reg, next_label, test_expr)
            if len(clause_value) == 1:
                self._emit(Opcode.MOV, [result_reg, test_reg], clause_expr)
            else:
                body_reg = self._compile_sequence(
                    [self._as_located(part) for part in clause_value[1:]],
                    clause_expr,
                )
                self._emit(Opcode.MOV, [result_reg, body_reg], clause_expr)
            self._emit(Opcode.JMP, [end_label], clause_expr)
            self._emit(Opcode.LABEL, [next_label], clause_expr)

        self._emit(Opcode.LABEL, [end_label], expression)
        return result_reg

    def _compile_case(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) < 2:
            raise SchemeCompileError("case expected a key expression")
        key_reg = self._compile_expression(self._as_located(items[1]))
        result_reg = self._new_temp()
        void_reg = self._emit_literal(None, expression)
        self._emit(Opcode.MOV, [result_reg, void_reg], expression)
        end_label = f"__scheme_case_end_{self.root._new_function_label()}"
        clauses = items[2:]
        for index, clause in enumerate(clauses):
            clause_expr = self._as_located(clause)
            clause_value = self._unwrap(clause)
            if not isinstance(clause_value, list) or not clause_value:
                raise SchemeCompileError("case clauses must be non-empty lists")
            datum_expr = self._as_located(clause_value[0])
            datum_value = self._unwrap(clause_value[0])
            is_else = isinstance(datum_value, Symbol) and datum_value == "else"
            if is_else:
                if index != len(clauses) - 1:
                    raise SchemeCompileError("case else clause must be last")
                if len(clause_value) == 1:
                    raise SchemeCompileError("case else clause expected a body")
                body_reg = self._compile_sequence(
                    [self._as_located(part) for part in clause_value[1:]],
                    clause_expr,
                )
                self._emit(Opcode.MOV, [result_reg, body_reg], clause_expr)
                self._emit(Opcode.JMP, [end_label], clause_expr)
                break

            if not isinstance(datum_value, list):
                raise SchemeCompileError("case clause expected a datum list")
            if len(clause_value) == 1:
                raise SchemeCompileError("case clause expected a body")

            clause_matched = f"__scheme_case_match_{self.root._new_function_label()}"
            next_label = f"__scheme_case_next_{self.root._new_function_label()}"
            for datum in datum_value:
                matches_reg = self._compile_internal_equal_value_call(
                    key_reg, self._emit_literal(self._datum_to_runtime_value(datum), datum_expr), datum_expr
                )
                self._emit(Opcode.JNZ, [matches_reg, clause_matched], datum_expr)
            self._emit(Opcode.JMP, [next_label], clause_expr)
            self._emit(Opcode.LABEL, [clause_matched], clause_expr)
            body_reg = self._compile_sequence(
                [self._as_located(part) for part in clause_value[1:]],
                clause_expr,
            )
            self._emit(Opcode.MOV, [result_reg, body_reg], clause_expr)
            self._emit(Opcode.JMP, [end_label], clause_expr)
            self._emit(Opcode.LABEL, [next_label], clause_expr)

        self._emit(Opcode.LABEL, [end_label], expression)
        return result_reg

    def _compile_do(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) < 3:
            raise SchemeCompileError("do expected variable specs and a termination clause")
        bindings_expr = self._unwrap(items[1])
        termination_expr = self._unwrap(items[2])
        if not isinstance(bindings_expr, list):
            raise SchemeCompileError("do variable specs must be a list")
        if not isinstance(termination_expr, list) or not termination_expr:
            raise SchemeCompileError("do termination clause must be a non-empty list")

        loop_name = Symbol(f"__do_loop_{self.root._new_function_label()}")
        params: list[LocatedDatum] = []
        inits: list[LocatedDatum] = []
        steps: list[LocatedDatum] = []
        init_bindings: list[LocatedDatum] = []
        seen: set[str] = set()
        for binding in bindings_expr:
            binding_value = self._unwrap(binding)
            if not isinstance(binding_value, list) or len(binding_value) not in (2, 3):
                raise SchemeCompileError("do variable specs must be (var init step?) lists")
            name = self._unwrap(binding_value[0])
            if not isinstance(name, Symbol):
                raise SchemeCompileError("do variable names must be symbols")
            name_text = str(name)
            if name_text in seen:
                raise SchemeCompileError(f"do duplicate variable: {name}")
            seen.add(name_text)
            params.append(self._synthetic(name, expression))
            inits.append(self._as_located(binding_value[1]))
            init_bindings.append(
                self._synthetic([self._synthetic(name, expression), self._as_located(binding_value[1])], expression)
            )
            if len(binding_value) == 3:
                steps.append(self._as_located(binding_value[2]))
            else:
                steps.append(self._synthetic(name, expression))

        test_expr = self._as_located(termination_expr[0])
        result_exprs = [self._as_located(part) for part in termination_expr[1:]]
        body_exprs = [self._as_located(part) for part in items[3:]]
        done_expr: LocatedDatum
        if result_exprs:
            done_expr = self._synthetic([Symbol("begin"), *result_exprs], expression)
        else:
            done_expr = self._synthetic([Symbol("if"), False, 1], expression)
        recur_call = self._synthetic([loop_name, *steps], expression)
        loop_body = self._synthetic(
            [Symbol("if"), test_expr, done_expr, [Symbol("begin"), *body_exprs, recur_call]],
            expression,
        )
        named_let_expr = self._synthetic([Symbol("let"), loop_name, init_bindings, loop_body], expression)
        return self._compile_expression(named_let_expr)

    def _compile_call(self, items: Sequence[object], expression: LocatedDatum) -> str:
        operator = self._as_located(items[0])
        callee_reg = self._compile_expression(operator)

        argument_regs: list[tuple[str, LocatedDatum]] = []
        for argument in items[1:]:
            argument_expr = self._as_located(argument)
            argument_reg = self._compile_expression(argument_expr)
            argument_regs.append((argument_reg, argument_expr))
        for argument_reg, argument_expr in argument_regs:
            self._emit(Opcode.PARAM, [argument_reg], argument_expr)
        self._emit(Opcode.CALL_VALUE, [callee_reg], operator)
        result_reg = self._new_temp()
        self._emit(Opcode.RESULT, [result_reg], expression)
        return result_reg

    def _read_symbol(self, name: str, expression: LocatedDatum) -> str:
        binding = self._lookup_binding(name)
        if binding is not None:
            return self._binding_read(binding, expression)
        if self.parent_compiler is not None:
            upvalue_binding = self._bind_parent_symbol(name, expression)
            if upvalue_binding is not None:
                return self._binding_read(upvalue_binding, expression)
        if name in self.root._known_globals:
            return mangle_global_name(name)
        return self._compile_lookup_global(name, expression)

    def _write_symbol(self, name: str, value_reg: str, expression: LocatedDatum) -> None:
        binding = self._lookup_binding(name)
        if binding is not None:
            self._binding_write(binding, value_reg, expression)
            return
        if self.parent_compiler is not None:
            upvalue_binding = self._bind_parent_symbol(name, expression)
            if upvalue_binding is not None:
                self._binding_write(upvalue_binding, value_reg, expression)
                return
        if name in self.root._known_globals:
            self._emit(Opcode.MOV, [mangle_global_name(name), value_reg], expression)
            return
        raise SchemeRuntimeError(f"unbound symbol: {name}")

    def _bind_parent_symbol(self, name: str, expression: LocatedDatum) -> VarBinding | None:
        existing = self._upvalue_bindings.get(name)
        if existing is not None:
            return existing
        source_binding = self.parent_compiler._ensure_capture_binding(name, expression)
        if source_binding is None:
            return None
        index = len(self._upvalue_order)
        binding = VarBinding(
            self._alloc_cell_reg(name),
            is_cell=True,
            read_guard_name=source_binding.read_guard_name,
        )
        self._upvalue_bindings[name] = binding
        self._upvalue_order.append(name)
        self._upvalue_source_cells.append(source_binding.storage)
        self.scope_stack[0][name] = binding
        self._emit(Opcode.BIND_UPVALUE, [binding.storage, str(index)], expression)
        return binding

    def _ensure_capture_binding(self, name: str, expression: LocatedDatum) -> VarBinding | None:
        binding = self._lookup_binding(name)
        if binding is not None:
            if not binding.is_cell:
                cell_reg = self._alloc_cell_reg(name)
                self._emit(Opcode.MAKE_CELL, [cell_reg, binding.storage], expression)
                binding.storage = cell_reg
                binding.is_cell = True
            return binding
        if self.parent_compiler is not None:
            upvalue_binding = self._bind_parent_symbol(name, expression)
            if upvalue_binding is not None:
                return upvalue_binding
        return None

    def _define_symbol(self, name: str, value_reg: str, expression: LocatedDatum) -> None:
        if self.parent_compiler is None:
            self.root._known_globals.add(name)
            self._emit(Opcode.MOV, [mangle_global_name(name), value_reg], expression)
            return

        current_scope = self.scope_stack[-1]
        existing = current_scope.get(name)
        if existing is not None:
            self._binding_write(existing, value_reg, expression)
            return
        current_scope[name] = VarBinding(value_reg)

    def _binding_read(self, binding: VarBinding, expression: LocatedDatum) -> str:
        if binding.is_cell:
            dst = self._new_temp()
            self._emit(Opcode.CELL_GET, [dst, binding.storage], expression)
        else:
            dst = binding.storage
        if binding.read_guard_name is None:
            return dst
        name_reg = self._emit_literal(binding.read_guard_name, expression)
        self._emit(Opcode.PARAM, [dst], expression)
        self._emit(Opcode.PARAM, [name_reg], expression)
        self._emit(Opcode.CALL_VALUE, [mangle_internal_name("ensure_initialized")], expression)
        guarded_reg = self._new_temp()
        self._emit(Opcode.RESULT, [guarded_reg], expression)
        return guarded_reg

    def _binding_write(self, binding: VarBinding, value_reg: str, expression: LocatedDatum) -> None:
        if binding.is_cell:
            self._emit(Opcode.CELL_SET, [binding.storage, value_reg], expression)
        else:
            self._emit(Opcode.MOV, [binding.storage, value_reg], expression)

    def _bind_parameter(self, name: Symbol, expression: LocatedDatum) -> None:
        reg = self._alloc_local_reg(str(name))
        self.scope_stack[-1][str(name)] = VarBinding(reg)
        self._emit(Opcode.ARG, [reg], expression)

    def _compile_equal_call(self, left_reg: str, right_reg: str, expression: LocatedDatum) -> str:
        self._emit(Opcode.PARAM, [left_reg], expression)
        self._emit(Opcode.PARAM, [right_reg], expression)
        self._emit(Opcode.CALL_VALUE, [mangle_global_name("equal?")], expression)
        result_reg = self._new_temp()
        self._emit(Opcode.RESULT, [result_reg], expression)
        return result_reg

    def _compile_internal_equal_value_call(
        self, left_reg: str, right_reg: str, expression: LocatedDatum
    ) -> str:
        self._emit(Opcode.PARAM, [left_reg], expression)
        self._emit(Opcode.PARAM, [right_reg], expression)
        self._emit(Opcode.CALL_VALUE, [mangle_internal_name("equal_value")], expression)
        result_reg = self._new_temp()
        self._emit(Opcode.RESULT, [result_reg], expression)
        return result_reg

    def _compile_lookup_global(self, name: str, expression: LocatedDatum) -> str:
        name_reg = self._emit_literal(name, expression)
        self._emit(Opcode.PARAM, [name_reg], expression)
        self._emit(Opcode.CALL_VALUE, [mangle_internal_name("lookup_global")], expression)
        result_reg = self._new_temp()
        self._emit(Opcode.RESULT, [result_reg], expression)
        return result_reg

    def _branch_if_false(self, value_reg: str, false_label: str, expression: LocatedDatum) -> None:
        self._emit(Opcode.PARAM, [value_reg], expression)
        self._emit(Opcode.CALL_VALUE, [mangle_internal_name("is_false")], expression)
        is_false = self._new_temp()
        self._emit(Opcode.RESULT, [is_false], expression)
        self._emit(Opcode.JNZ, [is_false, false_label], expression)

    def _compile_sequence(
        self, expressions: Sequence[LocatedDatum], fallback_expression: LocatedDatum
    ) -> str:
        if not expressions:
            return self._emit_literal(None, fallback_expression)
        for subexpression in expressions[:-1]:
            self._compile_expression(subexpression)
        return self._compile_expression(expressions[-1])

    def _lookup_binding(self, name: str) -> VarBinding | None:
        for scope in reversed(self.scope_stack):
            binding = scope.get(name)
            if binding is not None:
                return binding
        return None

    def _push_scope(self) -> None:
        self.scope_stack.append({})

    def _pop_scope(self) -> None:
        self.scope_stack.pop()

    def _emit_literal(self, value: object, expression: LocatedDatum) -> str:
        target = self._new_temp()
        if isinstance(value, int) and not isinstance(value, bool):
            self._emit(Opcode.LOAD_IMM, [target, value], expression)
        else:
            self._emit(Opcode.LOAD_CONST, [target, value], expression)
        return target

    def _emit(self, opcode: Opcode, args: Sequence[object], expression: LocatedDatum | None) -> None:
        self.instructions.append(Instruction(opcode, list(args), self._debug_for(expression)))

    def _debug_for(self, expression: LocatedDatum | None) -> InstructionDebug | None:
        if expression is None:
            return None
        return InstructionDebug(
            SourceLocation(
                expression.span.file,
                expression.span.line,
                expression.span.column,
            ),
            self.function_name,
        )

    def _literal_to_runtime_value(self, expression: LocatedDatum) -> object:
        value = expression.value
        if isinstance(value, Vector):
            return Vector(tuple(self._datum_to_runtime_value(item) for item in value.items))
        return value

    def _datum_to_runtime_value(self, datum: object) -> object:
        datum = self._unwrap(datum)
        if isinstance(datum, Vector):
            return Vector(tuple(self._datum_to_runtime_value(item) for item in datum.items))
        if isinstance(datum, DottedList):
            tail = self._datum_to_runtime_value(datum.tail)
            for item in reversed(list(self._iter_dotted_head(datum.items))):
                tail = Pair(self._datum_to_runtime_value(item), tail)
            return tail
        if isinstance(datum, list):
            tail: object = EMPTY_LIST
            for item in reversed(datum):
                tail = Pair(self._datum_to_runtime_value(item), tail)
            return tail
        return datum

    def _new_temp(self) -> str:
        target = f"S_{self.temp_counter}"
        self.temp_counter += 1
        return target

    def _alloc_local_reg(self, name: str) -> str:
        return f"L_{name}_{self._new_temp()}"

    def _alloc_cell_reg(self, name: str) -> str:
        return f"C_{name}_{self._new_temp()}"

    def _new_function_label(self) -> str:
        label = f"__scheme_func_{self.root._function_counter}"
        self.root._function_counter += 1
        return label

    @staticmethod
    def _iter_dotted_head(items: Iterable[object]) -> Iterable[object]:
        return items

    @staticmethod
    def _parse_params(params_expr: Sequence[object], form_name: str) -> list[Symbol]:
        params: list[Symbol] = []
        seen: set[Symbol] = set()
        for param in params_expr:
            param_value = SchemeCompiler._unwrap(param)
            if not isinstance(param_value, Symbol):
                raise SchemeCompileError(f"{form_name} parameters must be symbols")
            if param_value in seen:
                raise SchemeCompileError(f"{form_name} duplicate parameter: {param_value}")
            seen.add(param_value)
            params.append(param_value)
        return params

    @staticmethod
    def _unwrap(value: object) -> object:
        if isinstance(value, LocatedDatum):
            return value.value
        return value

    @staticmethod
    def _as_located(value: object) -> LocatedDatum:
        assert isinstance(value, LocatedDatum)
        return value

    @staticmethod
    def _located_tail(values: Sequence[object]) -> list[LocatedDatum]:
        return [SchemeCompiler._as_located(value) for value in values]

    @staticmethod
    def _synthetic(value: object, template: LocatedDatum) -> LocatedDatum:
        if isinstance(value, LocatedDatum):
            return value
        if isinstance(value, list):
            return LocatedDatum(
                [SchemeCompiler._synthetic(item, template) for item in value],
                template.span,
            )
        return LocatedDatum(value, template.span)

    def _macro_expand(self, expression: LocatedDatum) -> LocatedDatum:
        if self.parent_compiler is not None:
            macro_env = self.root._macro_env
        else:
            macro_env = self._macro_env

        expanded = expression
        for _ in range(128):
            value = expanded.value
            if not isinstance(value, list) or not value:
                return expanded
            head_value = self._unwrap(value[0])
            if not isinstance(head_value, Symbol):
                return expanded
            head_name = str(head_value)
            if head_name == "define-syntax":
                return expanded
            macro = macro_env.get(head_name)
            if macro is None:
                return expanded
            call_plain = self._to_plain_datum(expanded)
            assert isinstance(call_plain, list)
            try:
                result_plain = macro.expand(call_plain)
            except SchemeRuntimeError as exc:
                raise SchemeCompileError(
                    f"{expanded.span.file}:{expanded.span.line}: {exc}"
                ) from exc
            expanded = self._synthetic(result_plain, expanded)
        raise SchemeCompileError(
            f"{expression.span.file}:{expression.span.line}: macro expansion exceeded limit"
        )

    def _to_plain_datum(self, value: object) -> object:
        value = self._unwrap(value)
        if isinstance(value, list):
            return [self._to_plain_datum(item) for item in value]
        if isinstance(value, DottedList):
            return DottedList(
                [self._to_plain_datum(item) for item in value.items],
                self._to_plain_datum(value.tail),
            )
        if isinstance(value, Vector):
            return Vector(tuple(self._to_plain_datum(item) for item in value.items))
        return value


def compile_source(source: str, *, source_name: str = "<input>") -> list[Instruction]:
    return SchemeCompiler().compile_source(source, source_name=source_name)


def run_source_vm(
    source: str,
    runtime: SchemeVMRuntime | None = None,
    *,
    environment: Environment | None = None,
    source_name: str = "<input>",
) -> list[object]:
    expressions = parse_source_with_locations(source, source_name=source_name)
    if not expressions:
        return []

    runtime = runtime or SchemeVMRuntime(environment=environment)
    compiler = SchemeCompiler(runtime)
    instructions = compiler.compile_expressions(expressions, source_name=source_name)
    vm = runtime.create_vm(instructions)
    try:
        vm.run()
    except VMRuntimeError as exc:
        head = next((frame for frame in exc.frames if frame.file and frame.line), None)
        if head is None:
            raise SchemeVMRuntimeError(str(exc), frames=list(exc.frames)) from exc
        frame_names = [
            frame.function_name
            for frame in exc.frames
            if frame.function_name and frame.function_name != "<chunk>"
        ]
        suffix = f" [traceback: {' -> '.join(frame_names)}]" if frame_names else ""
        raise SchemeVMRuntimeError(
            f"{head.file}:{head.line}: {exc}{suffix}", frames=list(exc.frames)
        ) from exc
    runtime.sync_from_vm(vm)
    return [vm.registers.get(register) for register in compiler.result_registers]


__all__ = ["SchemeCompiler", "SchemeCompileError", "compile_source", "run_source_vm"]
