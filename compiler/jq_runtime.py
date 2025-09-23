from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional

from functools import lru_cache

try:
    from .jq_vm import JQVM as _VM
except Exception:
    # Fallback to core VM; during decoupling, both behave the same
    from .bytecode_vm import BytecodeVM as _VM
from .jq_compiler import INPUT_REGISTER, compile_to_bytecode
from .jq_parser import parse_jq_program

class JQRuntimeError(RuntimeError):
    """Raised when jq compilation or execution fails."""


def _var_reg(name: str) -> str:
    return f"__jq_var_{name}"


@lru_cache(maxsize=128)
def _compile_expression(expression: str) -> List[Any]:
    ast = parse_jq_program(expression)
    return compile_to_bytecode(ast)


def run_filter_stream(
    expression: str,
    inputs: Iterable[Any],
    env: Optional[Dict[str, Any]] = None,
) -> Iterator[Any]:
    try:
        instructions = _compile_expression(expression)
    except Exception as exc:  # pragma: no cover - defensive
        raise JQRuntimeError(f"Failed to compile jq expression: {exc}") from exc

    for index, item in enumerate(inputs):
        vm = _VM(instructions)
        vm.registers[INPUT_REGISTER] = item
        if env:
            for k, v in env.items():
                vm.registers[_var_reg(k)] = v
        try:
            results = vm.run()
        except Exception as exc:  # pragma: no cover - defensive
            raise JQRuntimeError(
                f"jq execution failed on input #{index}: {exc}"
            ) from exc
        for value in results:
            yield value


def run_filter(expression: str, data: Any, env: Optional[Dict[str, Any]] = None) -> List[Any]:
    return list(run_filter_stream(expression, [data], env=env))


def run_filter_many(expression: str, inputs: Iterable[Any], env: Optional[Dict[str, Any]] = None) -> List[Any]:
    return list(run_filter_stream(expression, inputs, env=env))


__all__ = ["run_filter", "run_filter_many", "run_filter_stream", "JQRuntimeError"]
