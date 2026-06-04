"""Minimal Scheme bytecode compiler for the Phase 2 VM backend."""

from __future__ import annotations

from typing import Iterable, Sequence

from compiler.bytecode import Instruction, InstructionDebug, Opcode, SourceLocation
from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.reader import DottedList, LocatedDatum, Symbol, parse_source_with_locations
from haifa_scheme.values import EMPTY_LIST, Pair, Vector
from haifa_scheme.vm_runtime import SchemeVMRuntime, mangle_global_name


class SchemeCompileError(RuntimeError):
    pass


class SchemeCompiler:
    def __init__(self, runtime: SchemeVMRuntime | None = None) -> None:
        self.runtime = runtime or SchemeVMRuntime()
        self.instructions: list[Instruction] = []
        self.temp_counter = 0
        self.source_name = "<input>"
        self.function_name = "<chunk>"
        self._known_globals = {
            name[len("G_SCHEME_") :]
            for name in self.runtime.to_vm_registers().keys()
            if name.startswith("G_SCHEME_")
        }

    def compile_source(self, source: str, *, source_name: str = "<input>") -> list[Instruction]:
        expressions = parse_source_with_locations(source, source_name=source_name)
        return self.compile_expressions(expressions, source_name=source_name)

    def compile_expressions(
        self, expressions: Sequence[LocatedDatum], *, source_name: str = "<input>"
    ) -> list[Instruction]:
        self.instructions = []
        self.temp_counter = 0
        self.source_name = source_name

        if not expressions:
            self._emit(Opcode.HALT, [], None)
            return list(self.instructions)

        for expression in expressions[:-1]:
            self._compile_expression(expression)
        result_reg = self._compile_expression(expressions[-1])
        self._emit(Opcode.RETURN, [result_reg], expressions[-1])
        self._emit(Opcode.HALT, [], expressions[-1])
        return list(self.instructions)

    def compile_expression_chunk(
        self, expression: LocatedDatum, *, source_name: str = "<input>"
    ) -> list[Instruction]:
        return self.compile_expressions([expression], source_name=source_name)

    def _compile_expression(self, expression: LocatedDatum) -> str:
        value = expression.value
        if isinstance(value, list):
            return self._compile_list_expression(expression)
        if isinstance(value, Symbol):
            symbol_name = str(value)
            if symbol_name in self._known_globals:
                return mangle_global_name(symbol_name)
            raise SchemeRuntimeError(f"unbound symbol: {value}")
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
            if operator_value in {"lambda", "if", "define-syntax"}:
                raise SchemeCompileError(
                    f"unsupported special form in Phase 3 VM backend: {operator_value}"
                )
        return self._compile_call(items, expression)

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
        if len(items) != 3:
            raise SchemeCompileError("define expected a target and value")
        target = self._unwrap(items[1])
        if not isinstance(target, Symbol):
            raise SchemeCompileError("Phase 3 only supports variable define")
        value_reg = self._compile_expression(self._as_located(items[2]))
        global_name = str(target)
        self._known_globals.add(global_name)
        self._emit(Opcode.MOV, [mangle_global_name(global_name), value_reg], expression)
        return self._emit_literal(None, expression)

    def _compile_set(self, items: Sequence[object], expression: LocatedDatum) -> str:
        if len(items) != 3:
            raise SchemeCompileError("set! expected a symbol and value")
        target = self._unwrap(items[1])
        if not isinstance(target, Symbol):
            raise SchemeCompileError("set! expected a symbol")
        target_name = str(target)
        if target_name not in self._known_globals:
            raise SchemeRuntimeError(f"unbound symbol: {target}")
        value_reg = self._compile_expression(self._as_located(items[2]))
        self._emit(Opcode.MOV, [mangle_global_name(target_name), value_reg], expression)
        return self._emit_literal(None, expression)

    def _compile_call(self, items: Sequence[object], expression: LocatedDatum) -> str:
        operator = self._as_located(items[0])
        callee_reg = self._compile_expression(operator)

        for argument in items[1:]:
            argument_reg = self._compile_expression(self._as_located(argument))
            self._emit(Opcode.PARAM, [argument_reg], self._as_located(argument))
        self._emit(Opcode.CALL_VALUE, [callee_reg], operator)
        result_reg = self._new_temp()
        self._emit(Opcode.RESULT, [result_reg], expression)
        return result_reg

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

    @staticmethod
    def _iter_dotted_head(items: Iterable[object]) -> Iterable[object]:
        return items

    @staticmethod
    def _unwrap(value: object) -> object:
        if isinstance(value, LocatedDatum):
            return value.value
        return value

    @staticmethod
    def _as_located(value: object) -> LocatedDatum:
        assert isinstance(value, LocatedDatum)
        return value

    def _new_temp(self) -> str:
        target = f"S_{self.temp_counter}"
        self.temp_counter += 1
        return target


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
    results: list[object] = []
    for expression in expressions:
        instructions = compiler.compile_expression_chunk(expression, source_name=source_name)
        vm = runtime.create_vm(instructions)
        vm.run()
        runtime.sync_from_vm(vm)
        results.append(vm.return_value)
    return results


__all__ = ["SchemeCompiler", "SchemeCompileError", "compile_source", "run_source_vm"]
