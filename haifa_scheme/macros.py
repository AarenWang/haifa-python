"""Small ``syntax-rules`` macro support for the Scheme runtime."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Any

from haifa_scheme.errors import SchemeRuntimeError
from haifa_scheme.reader import DottedList, Symbol
from haifa_scheme.values import Vector


ELLIPSIS = Symbol("...")
WILDCARD = Symbol("_")
SPECIAL_FORM_NAMES = {
    "and",
    "begin",
    "case",
    "cond",
    "define",
    "define-syntax",
    "do",
    "else",
    "if",
    "lambda",
    "let",
    "let*",
    "letrec",
    "or",
    "quote",
    "set!",
    "syntax-rules",
}

_SCOPE_COUNTER = count(1)


@dataclass(frozen=True)
class SyntaxRule:
    pattern: object
    template: object


@dataclass(frozen=True)
class SyntaxRulesMacro:
    name: Symbol
    literals: frozenset[Symbol]
    rules: tuple[SyntaxRule, ...]

    def expand(self, expression: list[object]) -> object:
        for rule in self.rules:
            bindings: MatchBindings = {}
            if _match(rule.pattern, expression, self.name, self.literals, bindings, is_root=True):
                expanded = _expand_template(rule.template, bindings)
                return _unwrap_pattern_syntax(_apply_hygiene(expanded, {}))
        raise SchemeRuntimeError(f"syntax-rules macro '{self.name}' found no matching rule")


@dataclass(frozen=True)
class RepeatedBinding:
    values: tuple[object, ...]


@dataclass(frozen=True)
class PatternSyntax:
    """Syntax inserted from the macro call site, not introduced by the macro."""

    value: object


MatchBindings = dict[Symbol, object | RepeatedBinding]


def parse_syntax_rules(name: Symbol, expression: object) -> SyntaxRulesMacro:
    if not isinstance(expression, list) or len(expression) < 3:
        raise SchemeRuntimeError("define-syntax expected a syntax-rules transformer")
    if not isinstance(expression[0], Symbol) or expression[0] != Symbol("syntax-rules"):
        raise SchemeRuntimeError("define-syntax expected a syntax-rules transformer")

    literals_expr = expression[1]
    if not isinstance(literals_expr, list):
        raise SchemeRuntimeError("syntax-rules expected a literal identifier list")

    literals: set[Symbol] = set()
    for literal in literals_expr:
        if not isinstance(literal, Symbol):
            raise SchemeRuntimeError("syntax-rules literals must be identifiers")
        if literal == ELLIPSIS:
            raise SchemeRuntimeError("syntax-rules ellipsis cannot be a literal identifier")
        literals.add(literal)

    rules: list[SyntaxRule] = []
    for rule_expr in expression[2:]:
        if not isinstance(rule_expr, list) or len(rule_expr) != 2:
            raise SchemeRuntimeError("syntax-rules rules must be (pattern template) pairs")
        pattern, template = rule_expr
        _validate_pattern(pattern, name, frozenset(literals))
        _validate_template(template)
        rules.append(SyntaxRule(pattern, template))

    if not rules:
        raise SchemeRuntimeError("syntax-rules expected at least one rule")
    return SyntaxRulesMacro(name, frozenset(literals), tuple(rules))


def _match(
    pattern: object,
    expression: object,
    macro_name: Symbol,
    literals: frozenset[Symbol],
    bindings: MatchBindings,
    *,
    is_root: bool = False,
) -> bool:
    if isinstance(pattern, Symbol):
        if pattern == WILDCARD:
            return True
        if is_root and pattern == macro_name:
            return isinstance(expression, Symbol) and expression == macro_name
        if pattern in literals:
            return isinstance(expression, Symbol) and expression == pattern
        existing = bindings.get(pattern)
        if existing is None and pattern not in bindings:
            bindings[pattern] = expression
            return True
        if isinstance(existing, RepeatedBinding):
            raise SchemeRuntimeError(
                f"syntax-rules repeated pattern variable used outside ellipsis: {pattern}"
            )
        return _syntax_equal(existing, expression)

    if isinstance(pattern, list):
        return _match_list(pattern, expression, macro_name, literals, bindings, is_root=is_root)

    return _syntax_equal(pattern, expression)


def _match_list(
    pattern: list[object],
    expression: object,
    macro_name: Symbol,
    literals: frozenset[Symbol],
    bindings: MatchBindings,
    *,
    is_root: bool,
) -> bool:
    if not isinstance(expression, list):
        return False

    ellipsis_index = _single_ellipsis_index(pattern, "pattern")
    if ellipsis_index is None:
        if len(pattern) != len(expression):
            return False
        for index, (pattern_item, expression_item) in enumerate(zip(pattern, expression)):
            item_is_root = is_root and index == 0
            if not _match(
                pattern_item,
                expression_item,
                macro_name,
                literals,
                bindings,
                is_root=item_is_root,
            ):
                return False
        return True

    prefix = pattern[:ellipsis_index]
    repeated_pattern = pattern[ellipsis_index]
    suffix = pattern[ellipsis_index + 2 :]
    minimum_length = len(prefix) + len(suffix)
    if len(expression) < minimum_length:
        return False

    for index, pattern_item in enumerate(prefix):
        item_is_root = is_root and index == 0
        if not _match(
            pattern_item,
            expression[index],
            macro_name,
            literals,
            bindings,
            is_root=item_is_root,
        ):
            return False

    suffix_start = len(expression) - len(suffix)
    for offset, pattern_item in enumerate(suffix):
        if not _match(
            pattern_item,
            expression[suffix_start + offset],
            macro_name,
            literals,
            bindings,
        ):
            return False

    repeated_variables = _pattern_variable_names(repeated_pattern, macro_name, literals)
    repeated_values: dict[Symbol, list[object]] = {
        variable: [] for variable in repeated_variables
    }
    for expression_item in expression[len(prefix) : suffix_start]:
        local_bindings: MatchBindings = {}
        if not _match(repeated_pattern, expression_item, macro_name, literals, local_bindings):
            return False
        for variable in repeated_variables:
            value = local_bindings.get(variable)
            if isinstance(value, RepeatedBinding):
                raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
            if variable not in local_bindings:
                raise SchemeRuntimeError(
                    f"syntax-rules repeated pattern did not bind variable: {variable}"
                )
            repeated_values[variable].append(value)

    for variable, values in repeated_values.items():
        bindings[variable] = RepeatedBinding(tuple(values))
    return True


def _expand_template(template: object, bindings: MatchBindings) -> object:
    if isinstance(template, Symbol):
        if template in bindings:
            value = bindings[template]
            if isinstance(value, RepeatedBinding):
                raise SchemeRuntimeError(
                    f"syntax-rules template variable requires ellipsis: {template}"
                )
            return PatternSyntax(_copy_syntax(value))
        return template
    if isinstance(template, list):
        return _expand_template_list(template, bindings)
    if isinstance(template, DottedList):
        return DottedList(
            [_expand_template(item, bindings) for item in template.items],
            _expand_template(template.tail, bindings),
        )
    if isinstance(template, Vector):
        return Vector(tuple(_expand_template(item, bindings) for item in template.items))
    return template


def _expand_template_list(template: list[object], bindings: MatchBindings) -> list[object]:
    result: list[object] = []
    index = 0
    while index < len(template):
        item = template[index]
        if item == ELLIPSIS:
            raise SchemeRuntimeError("syntax-rules ellipsis must follow a template item")
        if index + 1 < len(template) and template[index + 1] == ELLIPSIS:
            result.extend(_expand_repeated_template(item, bindings))
            index += 2
            continue
        result.append(_expand_template(item, bindings))
        index += 1
    return result


def _expand_repeated_template(item: object, bindings: MatchBindings) -> list[object]:
    repeated_variables = _template_repeated_variables(item, bindings)
    if not repeated_variables:
        raise SchemeRuntimeError(
            "syntax-rules template ellipsis must contain a repeated pattern variable"
        )

    lengths = {
        len(bindings[variable].values)
        for variable in repeated_variables
        if isinstance(bindings[variable], RepeatedBinding)
    }
    if len(lengths) != 1:
        raise SchemeRuntimeError("syntax-rules template ellipsis variable lengths differ")

    length = next(iter(lengths))
    return [_expand_template_at_index(item, bindings, index) for index in range(length)]


def _expand_template_at_index(
    template: object, bindings: MatchBindings, repetition_index: int
) -> object:
    if isinstance(template, Symbol):
        if template == ELLIPSIS:
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        if template in bindings:
            value = bindings[template]
            if isinstance(value, RepeatedBinding):
                return PatternSyntax(_copy_syntax(value.values[repetition_index]))
            return PatternSyntax(_copy_syntax(value))
        return template
    if isinstance(template, list):
        if _has_ellipsis(template):
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        return [_expand_template_at_index(item, bindings, repetition_index) for item in template]
    if isinstance(template, DottedList):
        if _contains_ellipsis(template):
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        return DottedList(
            [_expand_template_at_index(item, bindings, repetition_index) for item in template.items],
            _expand_template_at_index(template.tail, bindings, repetition_index),
        )
    if isinstance(template, Vector):
        if _contains_ellipsis(template):
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        return Vector(
            tuple(_expand_template_at_index(item, bindings, repetition_index) for item in template.items)
        )
    return template


def _validate_pattern(pattern: object, macro_name: Symbol, literals: frozenset[Symbol]) -> None:
    if not isinstance(pattern, list) or not pattern:
        raise SchemeRuntimeError("syntax-rules pattern must be a non-empty list")
    variables: set[Symbol] = set()
    _collect_pattern_variables(pattern, macro_name, literals, variables, is_root=True)


def _collect_pattern_variables(
    pattern: object,
    macro_name: Symbol,
    literals: frozenset[Symbol],
    variables: set[Symbol],
    *,
    is_root: bool = False,
) -> None:
    if isinstance(pattern, Symbol):
        if pattern == ELLIPSIS:
            raise SchemeRuntimeError("syntax-rules ellipsis must follow a pattern item")
        if pattern == WILDCARD or pattern in literals or (is_root and pattern == macro_name):
            return
        if pattern in variables:
            raise SchemeRuntimeError(f"syntax-rules duplicate pattern variable: {pattern}")
        variables.add(pattern)
        return

    if isinstance(pattern, list):
        index = 0
        while index < len(pattern):
            item = pattern[index]
            if item == ELLIPSIS:
                raise SchemeRuntimeError("syntax-rules ellipsis must follow a pattern item")
            if index + 1 < len(pattern) and pattern[index + 1] == ELLIPSIS:
                if _contains_ellipsis(item):
                    raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
                _collect_pattern_variables(
                    item,
                    macro_name,
                    literals,
                    variables,
                    is_root=is_root and index == 0,
                )
                index += 2
                continue
            _collect_pattern_variables(
                item,
                macro_name,
                literals,
                variables,
                is_root=is_root and index == 0,
            )
            index += 1


def _validate_template(template: object) -> None:
    if isinstance(template, Symbol):
        if template == ELLIPSIS:
            raise SchemeRuntimeError("syntax-rules ellipsis must follow a template item")
        return
    if isinstance(template, list):
        index = 0
        while index < len(template):
            item = template[index]
            if item == ELLIPSIS:
                raise SchemeRuntimeError("syntax-rules ellipsis must follow a template item")
            if index + 1 < len(template) and template[index + 1] == ELLIPSIS:
                if _contains_ellipsis(item):
                    raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
                _validate_template(item)
                index += 2
                continue
            _validate_template(item)
            index += 1
        return
    if isinstance(template, DottedList):
        for item in template.items:
            _validate_template(item)
        _validate_template(template.tail)
        return
    if isinstance(template, Vector):
        for item in template.items:
            _validate_template(item)


def _single_ellipsis_index(items: list[object], context: str) -> int | None:
    ellipsis_indices: list[int] = []
    for index, item in enumerate(items):
        if item == ELLIPSIS:
            if index == 0:
                raise SchemeRuntimeError(f"syntax-rules ellipsis must follow a {context} item")
            ellipsis_indices.append(index - 1)

    if not ellipsis_indices:
        return None
    if len(ellipsis_indices) > 1:
        raise SchemeRuntimeError(f"syntax-rules supports one ellipsis per {context} list")
    return ellipsis_indices[0]


def _pattern_variable_names(
    pattern: object, macro_name: Symbol, literals: frozenset[Symbol], *, is_root: bool = False
) -> set[Symbol]:
    variables: set[Symbol] = set()
    if isinstance(pattern, Symbol):
        if pattern == WILDCARD or pattern in literals or (is_root and pattern == macro_name):
            return variables
        if pattern == ELLIPSIS:
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        variables.add(pattern)
        return variables
    if isinstance(pattern, list):
        for index, item in enumerate(pattern):
            variables.update(
                _pattern_variable_names(
                    item,
                    macro_name,
                    literals,
                    is_root=is_root and index == 0,
                )
            )
    elif isinstance(pattern, DottedList):
        for item in pattern.items:
            variables.update(_pattern_variable_names(item, macro_name, literals))
        variables.update(_pattern_variable_names(pattern.tail, macro_name, literals))
    elif isinstance(pattern, Vector):
        for item in pattern.items:
            variables.update(_pattern_variable_names(item, macro_name, literals))
    return variables


def _template_repeated_variables(template: object, bindings: MatchBindings) -> set[Symbol]:
    variables: set[Symbol] = set()
    if isinstance(template, Symbol):
        if template == ELLIPSIS:
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        value = bindings.get(template)
        if isinstance(value, RepeatedBinding):
            variables.add(template)
        return variables
    if isinstance(template, list):
        if _has_ellipsis(template):
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        for item in template:
            variables.update(_template_repeated_variables(item, bindings))
    elif isinstance(template, DottedList):
        if _contains_ellipsis(template):
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        for item in template.items:
            variables.update(_template_repeated_variables(item, bindings))
        variables.update(_template_repeated_variables(template.tail, bindings))
    elif isinstance(template, Vector):
        if _contains_ellipsis(template):
            raise SchemeRuntimeError("syntax-rules nested ellipsis is not supported")
        for item in template.items:
            variables.update(_template_repeated_variables(item, bindings))
    return variables


def _contains_ellipsis(expression: object) -> bool:
    if expression == ELLIPSIS:
        return True
    if isinstance(expression, list):
        return any(_contains_ellipsis(item) for item in expression)
    if isinstance(expression, DottedList):
        return any(_contains_ellipsis(item) for item in expression.items) or _contains_ellipsis(
            expression.tail
        )
    if isinstance(expression, Vector):
        return any(_contains_ellipsis(item) for item in expression.items)
    return False


def _has_ellipsis(items: list[object]) -> bool:
    return any(item == ELLIPSIS for item in items)


def _copy_syntax(expression: object) -> object:
    if isinstance(expression, list):
        return [_copy_syntax(item) for item in expression]
    if isinstance(expression, DottedList):
        return DottedList(
            [_copy_syntax(item) for item in expression.items],
            _copy_syntax(expression.tail),
        )
    if isinstance(expression, Vector):
        return Vector(tuple(_copy_syntax(item) for item in expression.items))
    return expression


def _apply_hygiene(expression: object, renames: dict[Symbol, Symbol]) -> object:
    if isinstance(expression, PatternSyntax):
        return expression
    if isinstance(expression, Symbol):
        return renames.get(expression, expression)
    if isinstance(expression, list):
        return _apply_list_hygiene(expression, renames)
    if isinstance(expression, DottedList):
        return DottedList(
            [_apply_hygiene(item, renames) for item in expression.items],
            _apply_hygiene(expression.tail, renames),
        )
    if isinstance(expression, Vector):
        return Vector(tuple(_apply_hygiene(item, renames) for item in expression.items))
    return expression


def _apply_list_hygiene(expression: list[object], renames: dict[Symbol, Symbol]) -> list[object]:
    if not expression:
        return []

    operator = expression[0]
    if isinstance(operator, Symbol):
        if operator == Symbol("lambda"):
            return _apply_lambda_hygiene(expression, renames)
        if operator in {Symbol("let"), Symbol("let*"), Symbol("letrec")}:
            return _apply_let_hygiene(expression, renames, str(operator))

    return [_apply_hygiene(item, renames) for item in expression]


def _apply_lambda_hygiene(expression: list[object], renames: dict[Symbol, Symbol]) -> list[object]:
    if len(expression) < 2 or not isinstance(expression[1], list):
        return [_apply_hygiene(item, renames) for item in expression]

    body_renames = dict(renames)
    params: list[object] = []
    for param in expression[1]:
        scoped_param = _fresh_binding_symbol(param)
        params.append(scoped_param)
        if isinstance(param, Symbol) and isinstance(scoped_param, Symbol):
            body_renames[param] = scoped_param

    return [
        expression[0],
        params,
        *[_apply_hygiene(item, body_renames) for item in expression[2:]],
    ]


def _apply_let_hygiene(
    expression: list[object], renames: dict[Symbol, Symbol], form_name: str
) -> list[object]:
    if form_name == "let" and len(expression) >= 3 and isinstance(expression[1], Symbol):
        return _apply_named_let_hygiene(expression, renames)
    if len(expression) < 2 or not isinstance(expression[1], list):
        return [_apply_hygiene(item, renames) for item in expression]

    if form_name == "let":
        bindings, body_renames = _fresh_parallel_bindings(expression[1], renames)
        return [
            expression[0],
            bindings,
            *[_apply_hygiene(item, body_renames) for item in expression[2:]],
        ]
    if form_name == "let*":
        bindings: list[object] = []
        current_renames = dict(renames)
        for binding in expression[1]:
            scoped_binding, binding_renames = _fresh_single_binding(binding, current_renames)
            bindings.append(scoped_binding)
            current_renames.update(binding_renames)
        return [
            expression[0],
            bindings,
            *[_apply_hygiene(item, current_renames) for item in expression[2:]],
        ]

    bindings, body_renames = _fresh_parallel_bindings(expression[1], renames)
    bindings = [
        [binding[0], _apply_hygiene(binding[1], body_renames)]
        if isinstance(binding, list) and len(binding) == 2
        else binding
        for binding in bindings
    ]
    return [
        expression[0],
        bindings,
        *[_apply_hygiene(item, body_renames) for item in expression[2:]],
    ]


def _apply_named_let_hygiene(expression: list[object], renames: dict[Symbol, Symbol]) -> list[object]:
    if len(expression) < 3 or not isinstance(expression[2], list):
        return [_apply_hygiene(item, renames) for item in expression]

    name = _fresh_binding_symbol(expression[1])
    body_renames = dict(renames)
    if isinstance(expression[1], Symbol) and isinstance(name, Symbol):
        body_renames[expression[1]] = name

    bindings, body_renames = _fresh_parallel_bindings(expression[2], body_renames)
    return [
        expression[0],
        name,
        bindings,
        *[_apply_hygiene(item, body_renames) for item in expression[3:]],
    ]


def _fresh_parallel_bindings(
    bindings: list[object], renames: dict[Symbol, Symbol]
) -> tuple[list[object], dict[Symbol, Symbol]]:
    body_renames = dict(renames)
    scoped_bindings: list[object] = []
    pending: list[tuple[Symbol, Symbol]] = []

    for binding in bindings:
        if not isinstance(binding, list) or len(binding) != 2:
            scoped_bindings.append(_apply_hygiene(binding, renames))
            continue
        name, value_expr = binding
        scoped_name = _fresh_binding_symbol(name)
        scoped_bindings.append([scoped_name, _apply_hygiene(value_expr, renames)])
        if isinstance(name, Symbol) and isinstance(scoped_name, Symbol):
            pending.append((name, scoped_name))

    for name, scoped_name in pending:
        body_renames[name] = scoped_name
    return scoped_bindings, body_renames


def _fresh_single_binding(
    binding: object, renames: dict[Symbol, Symbol]
) -> tuple[object, dict[Symbol, Symbol]]:
    if not isinstance(binding, list) or len(binding) != 2:
        return _apply_hygiene(binding, renames), {}

    name, value_expr = binding
    scoped_name = _fresh_binding_symbol(name)
    scoped_binding = [scoped_name, _apply_hygiene(value_expr, renames)]
    if isinstance(name, Symbol) and isinstance(scoped_name, Symbol):
        return scoped_binding, {name: scoped_name}
    return scoped_binding, {}


def _fresh_binding_symbol(expression: object) -> object:
    if isinstance(expression, PatternSyntax):
        return expression
    if not isinstance(expression, Symbol):
        return _apply_hygiene(expression, {})
    if expression.scope is not None or str(expression) in SPECIAL_FORM_NAMES:
        return expression
    return Symbol(str(expression), next(_SCOPE_COUNTER))


def _unwrap_pattern_syntax(expression: object) -> object:
    if isinstance(expression, PatternSyntax):
        return _copy_syntax(expression.value)
    if isinstance(expression, list):
        return [_unwrap_pattern_syntax(item) for item in expression]
    if isinstance(expression, DottedList):
        return DottedList(
            [_unwrap_pattern_syntax(item) for item in expression.items],
            _unwrap_pattern_syntax(expression.tail),
        )
    if isinstance(expression, Vector):
        return Vector(tuple(_unwrap_pattern_syntax(item) for item in expression.items))
    return expression


def _syntax_equal(left: Any, right: Any) -> bool:
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _syntax_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if isinstance(left, DottedList) and isinstance(right, DottedList):
        return _syntax_equal(left.items, right.items) and _syntax_equal(left.tail, right.tail)
    if isinstance(left, Vector) and isinstance(right, Vector):
        return _syntax_equal(list(left.items), list(right.items))
    return type(left) is type(right) and left == right
