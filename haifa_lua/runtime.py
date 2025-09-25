from __future__ import annotations

import pathlib
from typing import Mapping, Optional, Sequence

from compiler.bytecode import Instruction
from compiler.bytecode_vm import BytecodeVM
from compiler.vm_errors import VMRuntimeError

from .compiler import LuaCompiler
from .debug import as_lua_error
from .environment import LuaEnvironment
from .parser import LuaParser
from .stdlib import create_default_environment, install_core_stdlib


def compile_source(source: str, *, source_name: str = "<stdin>") -> Sequence[Instruction]:
    chunk = LuaParser.parse(source)
    return LuaCompiler.compile_chunk(chunk, source_name=source_name)


def _prepare_environment(globals: Optional[object], load_stdlib: bool) -> LuaEnvironment:
    if globals is None:
        return create_default_environment() if load_stdlib else LuaEnvironment()
    if isinstance(globals, LuaEnvironment):
        if load_stdlib and not globals.stdlib_ready:
            install_core_stdlib(globals)
        return globals
    if isinstance(globals, Mapping):
        env = LuaEnvironment()
        if load_stdlib and not env.stdlib_ready:
            install_core_stdlib(env)
        env.merge(globals)
        return env
    raise TypeError("globals must be dict or LuaEnvironment")


def run_source(
    source: str,
    globals: Optional[object] = None,
    *,
    load_stdlib: bool = True,
    source_name: str = "<string>",
) -> list:
    instructions = list(compile_source(source, source_name=source_name))
    env = _prepare_environment(globals, load_stdlib)
    vm = BytecodeVM(instructions)
    vm.lua_env = env
    vm.registers.update(env.to_vm_registers())
    module_system = getattr(env, "module_system", None)
    if module_system is not None and source_name and not source_name.startswith("<"):
        module_system.set_base_path(pathlib.Path(source_name))
    env.bind_vm(vm)
    try:
        output = vm.run()
    except VMRuntimeError as exc:
        raise as_lua_error(exc) from exc
    finally:
        env.unbind_vm()
    env.sync_from_vm(vm.registers)
    if not output and vm.last_return:
        return list(vm.last_return)
    if vm.return_value is not None and not output:
        return [vm.return_value]
    return output


def run_script(path: str, globals: Optional[object] = None, *, load_stdlib: bool = True) -> list:
    data = pathlib.Path(path).read_text(encoding="utf-8")
    return run_source(data, globals, load_stdlib=load_stdlib, source_name=path)

__all__ = ["compile_source", "run_source", "run_script", "LuaEnvironment"]
