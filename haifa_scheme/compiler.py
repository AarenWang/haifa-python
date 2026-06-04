"""Scheme bytecode compiler for the VM backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from compiler.bytecode import Instruction, InstructionDebug, Opcode, SourceLocation
from compiler.vm_errors import VMRuntimeError
from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.reader import DottedList, LocatedDatum, Symbol, parse_source_with_locations
from haifa_scheme.values import EMPTY_LIST, Pair, Vector
from haifa_scheme.vm_runtime import SchemeVMRuntime, mangle_global_name


@dataclass
class VarBinding:
    storage: str
    is_cell: bool = False


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
            if operator_value == "define-syntax":
                raise SchemeCompileError(
                    f"unsupported special form in Phase 4 VM backend: {operator_value}"
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

        self._emit(Opcode.JZ, [cond_reg, else_label], expression)
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
        raise SchemeRuntimeError(f"unbound symbol: {name}")

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
        source_cell = self.parent_compiler._ensure_capture_cell(name, expression)
        if source_cell is None:
            return None
        index = len(self._upvalue_order)
        binding = VarBinding(self._alloc_cell_reg(name), is_cell=True)
        self._upvalue_bindings[name] = binding
        self._upvalue_order.append(name)
        self._upvalue_source_cells.append(source_cell)
        self.scope_stack[0][name] = binding
        self._emit(Opcode.BIND_UPVALUE, [binding.storage, str(index)], expression)
        return binding

    def _ensure_capture_cell(self, name: str, expression: LocatedDatum) -> str | None:
        binding = self._lookup_binding(name)
        if binding is not None:
            if not binding.is_cell:
                cell_reg = self._alloc_cell_reg(name)
                self._emit(Opcode.MAKE_CELL, [cell_reg, binding.storage], expression)
                binding.storage = cell_reg
                binding.is_cell = True
            return binding.storage
        if self.parent_compiler is not None:
            upvalue_binding = self._bind_parent_symbol(name, expression)
            if upvalue_binding is not None:
                return upvalue_binding.storage
        return None

    def _define_symbol(self, name: str, value_reg: str, expression: LocatedDatum) -> None:
        if self.parent_compiler is None:
            self.root._known_globals.add(name)
            self._emit(Opcode.MOV, [mangle_global_name(name), value_reg], expression)
            return
        raise SchemeCompileError("internal define is unsupported in Phase 4 VM backend")

    def _binding_read(self, binding: VarBinding, expression: LocatedDatum) -> str:
        if binding.is_cell:
            dst = self._new_temp()
            self._emit(Opcode.CELL_GET, [dst, binding.storage], expression)
            return dst
        return binding.storage

    def _binding_write(self, binding: VarBinding, value_reg: str, expression: LocatedDatum) -> None:
        if binding.is_cell:
            self._emit(Opcode.CELL_SET, [binding.storage, value_reg], expression)
        else:
            self._emit(Opcode.MOV, [binding.storage, value_reg], expression)

    def _bind_parameter(self, name: Symbol, expression: LocatedDatum) -> None:
        reg = self._alloc_local_reg(str(name))
        self.scope_stack[-1][str(name)] = VarBinding(reg)
        self._emit(Opcode.ARG, [reg], expression)

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
        frame_names = [frame.function_name for frame in exc.frames if frame.function_name]
        if frame_names:
            raise SchemeRuntimeError(f"{exc} [traceback: {' -> '.join(frame_names)}]") from exc
        raise
    runtime.sync_from_vm(vm)
    return [vm.registers.get(register) for register in compiler.result_registers]


__all__ = ["SchemeCompiler", "SchemeCompileError", "compile_source", "run_source_vm"]
