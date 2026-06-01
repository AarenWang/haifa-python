"""Minimal tree-walking evaluator for Scheme expressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.reader import Symbol, parse_source
from haifa_scheme.stdlib import BuiltinFunction, create_global_environment
from haifa_scheme.values import make_list


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


def run_source(source: str, environment: Environment | None = None) -> list[object]:
    """Evaluate all top-level expressions in ``source`` and return their values."""

    runtime_env = environment if environment is not None else create_global_environment()
    return [_eval(expression, runtime_env) for expression in parse_source(source)]


def _eval(expression: object, environment: Environment) -> Any:
    if isinstance(expression, Symbol):
        return environment.lookup(expression)

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
        if operator == "lambda":
            return _eval_lambda(expression, environment)
        if operator == "begin":
            return _eval_sequence(expression[1:], environment)

    procedure = _eval(operator, environment)
    args = [_eval(arg, environment) for arg in expression[1:]]
    return _apply(procedure, args)


def _eval_quote(expression: list[object]) -> object:
    _ensure_form_length(expression, 2, "quote")
    return _quote_to_value(expression[1])


def _eval_if(expression: list[object], environment: Environment) -> Any:
    _ensure_form_length(expression, 4, "if")
    condition = _eval(expression[1], environment)
    branch = expression[2] if _is_truthy(condition) else expression[3]
    return _eval(branch, environment)


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


def _eval_lambda(expression: list[object], environment: Environment) -> Procedure:
    if len(expression) < 3:
        raise SchemeRuntimeError("lambda expected parameters and body")
    params_expr = expression[1]
    if not isinstance(params_expr, list):
        raise SchemeRuntimeError("lambda expected parameter list")
    return Procedure(_parse_params(params_expr, "lambda"), expression[2:], environment)


def _eval_sequence(expressions: Sequence[object], environment: Environment) -> Any:
    if not expressions:
        raise SchemeRuntimeError("expected at least one expression")

    result: Any = None
    for expression in expressions:
        result = _eval(expression, environment)
    return result


def _apply(procedure: Any, args: Sequence[Any]) -> Any:
    if isinstance(procedure, BuiltinFunction):
        return procedure(args)
    if isinstance(procedure, Procedure):
        return procedure(args)
    raise SchemeRuntimeError(f"attempted to call non-procedure: {procedure!r}")


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
    if isinstance(expression, list):
        return make_list(_quote_to_value(item) for item in expression)
    return expression
