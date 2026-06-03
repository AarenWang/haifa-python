"""Minimal tree-walking evaluator for Scheme expressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.macros import SyntaxRulesMacro, parse_syntax_rules
from haifa_scheme.reader import DottedList, Symbol, parse_source
from haifa_scheme.stdlib import BuiltinContext, BuiltinFunction, create_global_environment
from haifa_scheme.values import Pair, Vector, equal_value, make_list


@dataclass(frozen=True)
class Procedure:
    params: list[Symbol]
    body: list[object]
    environment: Environment

    def __call__(self, args: Sequence[Any]) -> Any:
        if len(args) != len(self.params):
            raise SchemeRuntimeError(
                f"procedure expected {len(self.params)} argument(s), got {len(args)}"
            )

        local_env = Environment(parent=self.environment)
        for name, value in zip(self.params, args):
            local_env.define(name, value)
        return _eval_sequence(self.body, local_env)


@dataclass(frozen=True)
class _UninitializedBinding:
    name: Symbol


@dataclass(frozen=True)
class _TailExpression:
    expression: object
    environment: Environment


class _ContinuationJump(Exception):
    def __init__(self, value: Any, token: object) -> None:
        super().__init__()
        self.value = value
        self.token = token


@dataclass
class _EscapeContinuation:
    token: object
    active: bool = True

    def apply(self, args: Sequence[Any]) -> Any:
        if len(args) != 1:
            raise SchemeRuntimeError(
                f"continuation expected 1 argument(s), got {len(args)}"
            )
        if not self.active:
            raise SchemeRuntimeError("continuation has escaped")
        raise _ContinuationJump(args[0], self.token)


def run_source(source: str, environment: Environment | None = None) -> list[object]:
    """Evaluate all top-level expressions in ``source`` and return their values."""

    runtime_env = environment if environment is not None else create_global_environment()
    return [_eval(expression, runtime_env) for expression in parse_source(source)]


def _eval(expression: object, environment: Environment) -> Any:
    while True:
        result = _eval_once(expression, environment)
        if isinstance(result, _TailExpression):
            expression = result.expression
            environment = result.environment
            continue
        return result


def _eval_once(expression: object, environment: Environment) -> Any:
    if isinstance(expression, Symbol):
        value = environment.lookup(expression)
        if isinstance(value, _UninitializedBinding):
            raise SchemeRuntimeError(f"letrec binding '{value.name}' read before initialization")
        return value
    if isinstance(expression, list):
        return _eval_list(expression, environment)
    return expression


def _eval_list(expression: list[object], environment: Environment) -> Any:
    if not expression:
        raise SchemeRuntimeError("cannot evaluate empty list")

    operator = expression[0]
    if isinstance(operator, Symbol):
        if operator == "quote":
            return _eval_quote(expression)
        if operator == "if":
            return _eval_if(expression, environment)
        if operator == "define":
            return _eval_define(expression, environment)
        if operator == "define-syntax":
            return _eval_define_syntax(expression, environment)
        if operator == "lambda":
            return _eval_lambda(expression, environment)
        if operator == "begin":
            return _eval_sequence(expression[1:], environment)
        if operator == "set!":
            return _eval_set(expression, environment)
        if operator == "let":
            return _eval_let(expression, environment)
        if operator == "let*":
            return _eval_let_star(expression, environment)
        if operator == "letrec":
            return _eval_letrec(expression, environment)
        if operator == "and":
            return _eval_and(expression, environment)
        if operator == "or":
            return _eval_or(expression, environment)
        if operator == "cond":
            return _eval_cond(expression, environment)
        if operator == "case":
            return _eval_case(expression, environment)
        if operator == "do":
            return _eval_do(expression, environment)

        macro = _lookup_macro(operator, environment)
        if macro is not None:
            return _TailExpression(macro.expand(expression), environment)

    procedure = _eval(operator, environment)
    args = [_eval(arg, environment) for arg in expression[1:]]
    return _apply(procedure, args)


def _eval_quote(expression: list[object]) -> object:
    _ensure_form_length(expression, 2, "quote")
    return _quote_to_value(expression[1])


def _eval_if(expression: list[object], environment: Environment) -> Any:
    if len(expression) < 3 or len(expression) > 4:
        actual = len(expression) - 1
        raise SchemeRuntimeError(f"if expected 2 or 3 argument(s), got {actual}")
    condition = _eval(expression[1], environment)
    if not _is_truthy(condition) and len(expression) == 3:
        return None
    branch = expression[2] if _is_truthy(condition) else expression[3]
    return _TailExpression(branch, environment)


def _eval_define(expression: list[object], environment: Environment) -> None:
    if len(expression) < 3:
        raise SchemeRuntimeError("define expected a target and value")

    target = expression[1]
    if isinstance(target, Symbol):
        _ensure_form_length(expression, 3, "define")
        environment.define(target, _eval(expression[2], environment))
        return None

    if isinstance(target, list) and target and isinstance(target[0], Symbol):
        name = target[0]
        params = _parse_params(target[1:], "define")
        if len(expression) < 3:
            raise SchemeRuntimeError("define function expected a body")
        environment.define(name, Procedure(params, expression[2:], environment))
        return None

    raise SchemeRuntimeError("define expected a symbol or function signature")


def _eval_define_syntax(expression: list[object], environment: Environment) -> None:
    _ensure_form_length(expression, 3, "define-syntax")
    name = expression[1]
    if not isinstance(name, Symbol):
        raise SchemeRuntimeError("define-syntax expected a symbol name")
    environment.define(name, parse_syntax_rules(name, expression[2]))
    return None


def _eval_lambda(expression: list[object], environment: Environment) -> Procedure:
    if len(expression) < 3:
        raise SchemeRuntimeError("lambda expected parameters and body")
    params_expr = expression[1]
    if not isinstance(params_expr, list):
        raise SchemeRuntimeError("lambda expected parameter list")
    return Procedure(_parse_params(params_expr, "lambda"), expression[2:], environment)


def _eval_set(expression: list[object], environment: Environment) -> None:
    _ensure_form_length(expression, 3, "set!")
    target = expression[1]
    if not isinstance(target, Symbol):
        raise SchemeRuntimeError("set! expected a symbol")
    environment.set(target, _eval(expression[2], environment))
    return None


def _eval_let(expression: list[object], environment: Environment) -> Any:
    if len(expression) >= 2 and isinstance(expression[1], Symbol):
        return _eval_named_let(expression, environment)

    bindings = _parse_bindings_form(expression, "let")
    values = [(name, _eval(value_expr, environment)) for name, value_expr in bindings]
    local_env = Environment(parent=environment)
    for name, value in values:
        local_env.define(name, value)
    return _eval_sequence(expression[2:], local_env)


def _eval_named_let(expression: list[object], environment: Environment) -> Any:
    if len(expression) < 4:
        raise SchemeRuntimeError("named let expected name, bindings, and body")

    name = expression[1]
    if not isinstance(name, Symbol):
        raise SchemeRuntimeError("named let expected a symbol name")

    bindings = _parse_bindings(expression[2], "named let")
    params = [binding_name for binding_name, _ in bindings]
    args = [_eval(value_expr, environment) for _, value_expr in bindings]

    local_env = Environment(parent=environment)
    procedure = Procedure(params, expression[3:], local_env)
    local_env.define(name, procedure)
    return _apply(procedure, args)


def _eval_let_star(expression: list[object], environment: Environment) -> Any:
    bindings = _parse_bindings_form(expression, "let*")
    local_env = Environment(parent=environment)
    for name, value_expr in bindings:
        local_env.define(name, _eval(value_expr, local_env))
    return _eval_sequence(expression[2:], local_env)


def _eval_letrec(expression: list[object], environment: Environment) -> Any:
    bindings = _parse_bindings_form(expression, "letrec")
    local_env = Environment(parent=environment)
    for name, _ in bindings:
        local_env.define(name, _UninitializedBinding(name))
    for name, value_expr in bindings:
        local_env.set(name, _eval(value_expr, local_env))
    return _eval_sequence(expression[2:], local_env)


def _eval_and(expression: list[object], environment: Environment) -> Any:
    items = expression[1:]
    if not items:
        return True
    for item in items[:-1]:
        result = _eval(item, environment)
        if not _is_truthy(result):
            return False
    return _TailExpression(items[-1], environment)


def _eval_or(expression: list[object], environment: Environment) -> Any:
    items = expression[1:]
    if not items:
        return False
    for item in items[:-1]:
        result = _eval(item, environment)
        if _is_truthy(result):
            return result
    return _TailExpression(items[-1], environment)


def _eval_cond(expression: list[object], environment: Environment) -> Any:
    for index, clause in enumerate(expression[1:], start=1):
        if not isinstance(clause, list) or not clause:
            raise SchemeRuntimeError("cond clauses must be non-empty lists")
        test_expr = clause[0]
        is_else = isinstance(test_expr, Symbol) and test_expr == "else"
        if is_else:
            if index != len(expression) - 1:
                raise SchemeRuntimeError("cond else clause must be last")
            if len(clause) == 1:
                raise SchemeRuntimeError("cond else clause expected a body")
            return _eval_sequence(clause[1:], environment)

        test_value = _eval(test_expr, environment)
        if _is_truthy(test_value):
            if len(clause) == 1:
                return test_value
            return _eval_sequence(clause[1:], environment)
    return None


def _eval_case(expression: list[object], environment: Environment) -> Any:
    if len(expression) < 2:
        raise SchemeRuntimeError("case expected a key expression")

    key_value = _eval(expression[1], environment)
    clauses = expression[2:]
    for index, clause in enumerate(clauses):
        if not isinstance(clause, list) or not clause:
            raise SchemeRuntimeError("case clauses must be non-empty lists")

        datum_expr = clause[0]
        is_else = isinstance(datum_expr, Symbol) and datum_expr == "else"
        if is_else:
            if index != len(clauses) - 1:
                raise SchemeRuntimeError("case else clause must be last")
            if len(clause) == 1:
                raise SchemeRuntimeError("case else clause expected a body")
            return _eval_sequence(clause[1:], environment)

        if not isinstance(datum_expr, list):
            raise SchemeRuntimeError("case clause expected a datum list")
        if len(clause) == 1:
            raise SchemeRuntimeError("case clause expected a body")

        for datum in datum_expr:
            if equal_value(key_value, _quote_to_value(datum)):
                return _eval_sequence(clause[1:], environment)

    return None


def _eval_do(expression: list[object], environment: Environment) -> Any:
    if len(expression) < 3:
        raise SchemeRuntimeError("do expected variable specs and a termination clause")

    bindings = _parse_do_bindings(expression[1])
    termination = expression[2]
    if not isinstance(termination, list) or not termination:
        raise SchemeRuntimeError("do termination clause must be a non-empty list")

    initial_values = [
        (name, _eval(init_expr, environment), step_expr)
        for name, init_expr, step_expr in bindings
    ]
    loop_env = Environment(parent=environment)
    for name, value, _ in initial_values:
        loop_env.define(name, value)

    test_expr = termination[0]
    result_exprs = termination[1:]
    body_exprs = expression[3:]

    while True:
        if _is_truthy(_eval(test_expr, loop_env)):
            if not result_exprs:
                return None
            return _eval_sequence(result_exprs, loop_env)

        for body_expr in body_exprs:
            _eval(body_expr, loop_env)

        next_values: list[tuple[Symbol, Any]] = []
        for name, _, step_expr in bindings:
            if step_expr is None:
                next_values.append((name, loop_env.lookup(name)))
            else:
                next_values.append((name, _eval(step_expr, loop_env)))

        for name, value in next_values:
            loop_env.set(name, value)


def _eval_sequence(expressions: Sequence[object], environment: Environment) -> Any:
    if not expressions:
        raise SchemeRuntimeError("expected at least one expression")

    for expression in expressions[:-1]:
        _eval(expression, environment)
    return _TailExpression(expressions[-1], environment)


def _apply(procedure: Any, args: Sequence[Any]) -> Any:
    if isinstance(procedure, BuiltinFunction):
        return procedure(
            args,
            BuiltinContext(
                _apply_resolved,
                _is_procedure,
                _call_with_current_continuation,
            ),
        )
    if isinstance(procedure, Procedure):
        return procedure(args)
    if isinstance(procedure, _EscapeContinuation):
        return procedure.apply(args)
    raise SchemeRuntimeError(f"attempted to call non-procedure: {procedure!r}")


def _call_with_current_continuation(procedure: Any) -> Any:
    token = object()
    continuation = _EscapeContinuation(token)
    try:
        return _apply_resolved(procedure, [continuation])
    except _ContinuationJump as jump:
        if jump.token is token:
            return jump.value
        raise
    finally:
        continuation.active = False


def _lookup_macro(name: Symbol, environment: Environment) -> SyntaxRulesMacro | None:
    try:
        value = environment.lookup(name)
    except SchemeRuntimeError:
        return None
    if isinstance(value, SyntaxRulesMacro):
        return value
    return None


def _apply_resolved(procedure: Any, args: Sequence[Any]) -> Any:
    result = _apply(procedure, args)
    if isinstance(result, _TailExpression):
        return _eval(result.expression, result.environment)
    return result


def _is_procedure(value: Any) -> bool:
    return isinstance(value, (BuiltinFunction, Procedure, _EscapeContinuation))


def _parse_params(params: Sequence[object], form_name: str) -> list[Symbol]:
    parsed: list[Symbol] = []
    seen: set[Symbol] = set()
    for param in params:
        if not isinstance(param, Symbol):
            raise SchemeRuntimeError(f"{form_name} parameters must be symbols")
        if param in seen:
            raise SchemeRuntimeError(f"{form_name} duplicate parameter: {param}")
        seen.add(param)
        parsed.append(param)
    return parsed


def _parse_bindings_form(
    expression: Sequence[object], form_name: str
) -> list[tuple[Symbol, object]]:
    if len(expression) < 3:
        raise SchemeRuntimeError(f"{form_name} expected bindings and body")
    return _parse_bindings(expression[1], form_name)


def _parse_bindings(bindings_expr: object, form_name: str) -> list[tuple[Symbol, object]]:
    if not isinstance(bindings_expr, list):
        raise SchemeRuntimeError(f"{form_name} expected binding list")

    bindings: list[tuple[Symbol, object]] = []
    seen: set[Symbol] = set()
    for binding in bindings_expr:
        if not isinstance(binding, list) or len(binding) != 2:
            raise SchemeRuntimeError(f"{form_name} bindings must be (name value) pairs")
        name, value_expr = binding
        if not isinstance(name, Symbol):
            raise SchemeRuntimeError(f"{form_name} binding names must be symbols")
        if name in seen:
            raise SchemeRuntimeError(f"{form_name} duplicate binding: {name}")
        seen.add(name)
        bindings.append((name, value_expr))
    return bindings


def _parse_do_bindings(bindings_expr: object) -> list[tuple[Symbol, object, object | None]]:
    if not isinstance(bindings_expr, list):
        raise SchemeRuntimeError("do variable specs must be a list")

    bindings: list[tuple[Symbol, object, object | None]] = []
    seen: set[Symbol] = set()
    for binding in bindings_expr:
        if not isinstance(binding, list) or len(binding) not in (2, 3):
            raise SchemeRuntimeError("do variable specs must be (var init step?) lists")
        name = binding[0]
        if not isinstance(name, Symbol):
            raise SchemeRuntimeError("do variable names must be symbols")
        if name in seen:
            raise SchemeRuntimeError(f"do duplicate variable: {name}")
        seen.add(name)
        step_expr = binding[2] if len(binding) == 3 else None
        bindings.append((name, binding[1], step_expr))
    return bindings


def _ensure_form_length(expression: Sequence[object], expected: int, form_name: str) -> None:
    if len(expression) != expected:
        actual = len(expression) - 1
        expected_args = expected - 1
        raise SchemeRuntimeError(
            f"{form_name} expected {expected_args} argument(s), got {actual}"
        )


def _is_truthy(value: object) -> bool:
    return value is not False


def _quote_to_value(expression: object) -> object:
    if isinstance(expression, Vector):
        return Vector(tuple(_quote_to_value(item) for item in expression.items))
    if isinstance(expression, DottedList):
        tail = _quote_to_value(expression.tail)
        for item in reversed(expression.items):
            tail = Pair(_quote_to_value(item), tail)
        return tail
    if isinstance(expression, list):
        return make_list(_quote_to_value(item) for item in expression)
    return expression
