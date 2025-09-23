from __future__ import annotations

import pathlib
from typing import Iterable, List, Optional

from compiler.bytecode_vm import BytecodeVM
from compiler.bytecode import Instruction

from .compiler import LuaCompiler
from .parser import LuaParser


def compile_source(source: str) -> List[Instruction]:
    chunk = LuaParser.parse(source)
    return LuaCompiler.compile_chunk(chunk)


def run_source(source: str, globals: Optional[dict] = None) -> List[object]:
    instructions = compile_source(source)
    vm = BytecodeVM(instructions)
    if globals:
        vm.registers.update({f"G_{k}": v for k, v in globals.items()})
    output = vm.run()
    if not output and vm.last_return:
        return list(vm.last_return)
    if vm.return_value is not None and not output:
        return [vm.return_value]
    return output


def run_script(path: str, globals: Optional[dict] = None) -> List[object]:
    data = pathlib.Path(path).read_text(encoding="utf-8")
    return run_source(data, globals)

__all__ = ["compile_source", "run_source", "run_script"]
