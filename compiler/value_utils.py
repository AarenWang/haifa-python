import json
from typing import Any, Callable

_SENTINEL = object()


def try_parse_literal(token: Any) -> Any:
    """Attempt to interpret a token as a JSON literal.

    Returns `_SENTINEL` when the token should be treated as an identifier.
    """
    if isinstance(token, (int, float, bool)) or token is None:
        return token
    if not isinstance(token, str):
        return token

    stripped = token.strip()
    if not stripped:
        return _SENTINEL

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        if stripped[0] == stripped[-1] == "'":
            inner = stripped[1:-1].replace("\\'", "'")
            return inner
        return _SENTINEL


def resolve_value(token: Any, lookup: Callable[[str], Any]) -> Any:
    """Resolve a token to a runtime value using `lookup` for identifiers.

    `lookup` should return the value for identifiers or a default when missing.
    """
    literal = try_parse_literal(token)
    if literal is not _SENTINEL:
        return literal
    return lookup(token)


__all__ = ["resolve_value", "try_parse_literal"]
