from __future__ import annotations

from typing import Any, Iterable, List

from .bytecode_vm import BytecodeVM
from .jq_compiler import INPUT_REGISTER, compile_to_bytecode
from .jq_parser import parse_jq_program


def run_filter(expression: str, data: Any) -> List[Any]:
    """Run a jq expression against a JSON value and return the results list."""
    ast = parse_jq_program(expression)
    instructions = compile_to_bytecode(ast)

    vm = BytecodeVM(instructions)
    vm.registers[INPUT_REGISTER] = data
    return vm.run()


def run_filter_many(expression: str, inputs: Iterable[Any]) -> List[Any]:
    results: List[Any] = []
    for item in inputs:
        results.extend(run_filter(expression, item))
    return results


__all__ = ["run_filter", "run_filter_many"]
