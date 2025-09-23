from __future__ import annotations

from typing import Any, Iterable, List, Optional, Dict

try:
    from .jq_vm import JQVM as _VM
except Exception:
    # Fallback to core VM; during decoupling, both behave the same
    from .bytecode_vm import BytecodeVM as _VM
from .jq_compiler import INPUT_REGISTER, compile_to_bytecode
from .jq_parser import parse_jq_program


def _var_reg(name: str) -> str:
    return f"__jq_var_{name}"


def run_filter(expression: str, data: Any, env: Optional[Dict[str, Any]] = None) -> List[Any]:
    """Run a jq expression against a JSON value and return the results list.

    env: optional variable injections, accessible as $name in filters.
    """
    ast = parse_jq_program(expression)
    instructions = compile_to_bytecode(ast)

    vm = _VM(instructions)
    vm.registers[INPUT_REGISTER] = data
    if env:
        for k, v in env.items():
            vm.registers[_var_reg(k)] = v
    return vm.run()


def run_filter_many(expression: str, inputs: Iterable[Any], env: Optional[Dict[str, Any]] = None) -> List[Any]:
    results: List[Any] = []
    for item in inputs:
        results.extend(run_filter(expression, item, env=env))
    return results


__all__ = ["run_filter", "run_filter_many"]
