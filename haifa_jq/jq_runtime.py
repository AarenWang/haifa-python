from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional

import json
import subprocess
from functools import lru_cache

from haifa_jq.jq_vm import JQVM as _VM
from haifa_jq.jq_compiler import INPUT_REGISTER, compile_to_bytecode
from haifa_jq.jq_parser import parse_jq_program, JQSyntaxError

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
    except (JQSyntaxError, ValueError, NotImplementedError) as exc:
        yield from _system_jq_stream(expression, inputs, env, exc)
        return
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


def _system_jq_stream(
    expression: str,
    inputs: Iterable[Any],
    env: Optional[Dict[str, Any]],
    original_exc: Exception,
) -> Iterator[Any]:
    """Execute jq by invoking the system jq binary as a compatibility fallback."""

    cmd_base: list[str] = ["jq", "-c", expression]
    if env:
        for key, value in env.items():
            arg = json.dumps(value)
            cmd_base.extend(["--argjson", key, arg])

    for index, item in enumerate(inputs):
        proc = subprocess.run(
            cmd_base,
            input=(json.dumps(item) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            message = proc.stderr.decode("utf-8", errors="ignore").strip()
            raise JQRuntimeError(
                f"System jq fallback failed on input #{index}: {message or proc.returncode}"
            ) from original_exc
        for line in proc.stdout.decode("utf-8").splitlines():
            if not line:
                continue
            yield json.loads(line)
