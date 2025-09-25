from __future__ import annotations

import pathlib
from contextlib import contextmanager
from typing import Iterator, List, Mapping, Optional, Sequence

from compiler.bytecode_vm import BytecodeVM
from compiler.vm_errors import VMRuntimeError

from .compiler import LuaCompiler
from .debug import as_lua_error
from .environment import BuiltinFunction, LuaEnvironment, LuaMultiReturn
from .parser import LuaParser
from .table import LuaTable


class LuaModuleSystem:
    """Runtime module loader compatible with Lua's package/require model."""

    def __init__(self, env: LuaEnvironment) -> None:
        self.root_env = env
        self.package_table = LuaTable()
        self.loaded = LuaTable()
        self.preload = LuaTable()
        self.searchers = LuaTable()
        self.package_table.raw_set("loaded", self.loaded)
        self.package_table.raw_set("preload", self.preload)
        self.package_table.raw_set("searchers", self.searchers)
        self.package_table.raw_set("path", "./?.lua;./?/init.lua")
        self.package_table.raw_set("config", "/\n;\n?\n!\n-")
        self.package_table.raw_set(
            "sandbox",
            BuiltinFunction("package.sandbox", self._lua_package_sandbox),
        )
        self.base_path = pathlib.Path.cwd()
        self.module_envs: dict[str, LuaEnvironment] = {}
        self._install_default_searchers()

    # ------------------------------------------------------------------ helpers
    def attach_environment(self, env: LuaEnvironment) -> None:
        env.module_system = self  # type: ignore[attr-defined]
        env.register("package", self.package_table)
        env.register("require", BuiltinFunction("require", self._lua_require))
        env.register("dofile", BuiltinFunction("dofile", self._lua_dofile))
        env.register("load", BuiltinFunction("load", self._lua_load))
        env.register("loadfile", BuiltinFunction("loadfile", self._lua_loadfile))

    def _sync_vm_globals(self, vm: BytecodeVM, env: LuaEnvironment) -> None:
        if env is not vm.lua_env:
            return
        snapshot = env.snapshot()
        stale = [key for key in vm.registers if key.startswith("G_") and key[2:] not in snapshot]
        for key in stale:
            vm.registers.pop(key, None)
        for name, value in snapshot.items():
            vm.registers[f"G_{name}"] = value

    def set_base_path(self, path: pathlib.Path) -> None:
        if path.is_file():
            path = path.parent
        self.base_path = path

    @contextmanager
    def _scoped_base_path(self, path: pathlib.Path) -> Iterator[None]:
        previous = self.base_path
        self.set_base_path(path)
        try:
            yield
        finally:
            self.base_path = previous

    # ------------------------------------------------------------------ loaders
    def _compile(self, source: str, *, source_name: str) -> List:
        chunk = LuaParser.parse(source)
        return LuaCompiler.compile_chunk(chunk, source_name=source_name)

    def _run_instructions(
        self,
        instructions: Sequence,
        env: LuaEnvironment,
        args: Sequence[object],
    ) -> List[object]:
        vm = BytecodeVM(list(instructions))
        vm.lua_env = env
        vm.registers.update(env.to_vm_registers())
        env.bind_vm(vm)
        vm.param_stack = list(args)
        vm.pending_params = []
        try:
            vm.run()
        except VMRuntimeError as exc:  # pragma: no cover - propagated as Lua error
            raise as_lua_error(exc) from exc
        finally:
            env.unbind_vm()
        env.sync_from_vm(vm.registers)
        if vm.last_return:
            return list(vm.last_return)
        if vm.return_value is not None:
            return [vm.return_value]
        return []

    # ------------------------------------------------------------------ API
    def load_string(
        self,
        chunk: str,
        *,
        chunkname: str,
        base_env: LuaEnvironment,
        env_override: Optional[object] = None,
    ) -> BuiltinFunction:
        instructions = self._compile(chunk, source_name=chunkname)
        target_env = self._resolve_environment(env_override, base_env)

        def _chunk(args: Sequence[object], vm: BytecodeVM) -> LuaMultiReturn:
            result = self._run_instructions(instructions, target_env, args)
            self._sync_vm_globals(vm, target_env)
            return LuaMultiReturn(result)

        return BuiltinFunction(f"load:{chunkname}", _chunk)

    def load_file(
        self,
        filename: str,
        base_env: LuaEnvironment,
        env_override: Optional[object] = None,
    ) -> BuiltinFunction:
        path = self._resolve_path(filename)
        source = path.read_text(encoding="utf-8")
        instructions = self._compile(source, source_name=str(path))
        target_env = self._resolve_environment(env_override, base_env)

        def _chunk(args: Sequence[object], vm: BytecodeVM) -> LuaMultiReturn:
            with self._scoped_base_path(path):
                result = self._run_instructions(instructions, target_env, args)
            self._sync_vm_globals(vm, target_env)
            return LuaMultiReturn(result)

        return BuiltinFunction(f"loadfile:{path}", _chunk)

    def require(self, name: str, vm: BytecodeVM) -> object:
        cached = self.loaded.raw_get(name)
        if cached is not None:
            return cached

        searchers = self._get_searchers()
        errors: List[str] = []
        for index in range(1, searchers.lua_len() + 1):
            searcher = searchers.raw_get(index)
            if searcher is None:
                continue
            result = vm.call_callable(searcher, [name])
            if not result:
                continue
            loader = result[0]
            extra = result[1] if len(result) > 1 else None
            if loader:
                module_env = self._module_environment(name, vm.lua_env)
                self.loaded.raw_set(name, True)
                try:
                    values = vm.call_callable(loader, [name])
                except Exception as exc:  # noqa: BLE001
                    self.loaded.raw_set(name, None)
                    raise exc
                self._sync_vm_globals(vm, module_env)
                module_value = values[0] if values else None
                if module_value is None:
                    module_value = True
                self.loaded.raw_set(name, module_value)
                return module_value
            if extra:
                errors.append(str(extra))

        message = f"module '{name}' not found"
        if errors:
            message += ": " + "; ".join(errors)
        raise RuntimeError(message)

    # ------------------------------------------------------------------ searchers
    def _install_default_searchers(self) -> None:
        self.searchers.raw_set(1, BuiltinFunction("searcher.preload", self._search_preload))
        self.searchers.raw_set(2, BuiltinFunction("searcher.lua", self._search_lua_file))

    def _get_searchers(self) -> LuaTable:
        table = self.package_table.raw_get("searchers")
        if isinstance(table, LuaTable):
            return table
        return self.searchers

    def _search_preload(self, args: Sequence[object], vm: BytecodeVM) -> LuaMultiReturn:
        name = str(args[0]) if args else ""
        loader = self.preload.raw_get(name)
        if loader is not None:
            return LuaMultiReturn([loader, f"preload:{name}"])
        return LuaMultiReturn([None, f"no field package.preload['{name}']"])

    def _search_lua_file(self, args: Sequence[object], vm: BytecodeVM) -> LuaMultiReturn:
        name = str(args[0]) if args else ""
        module_path = name.replace(".", "/")
        path_value = self.package_table.raw_get("path")
        path_string = str(path_value) if path_value else "./?.lua;./?/init.lua"
        for pattern in path_string.split(";"):
            pattern = pattern.strip()
            if not pattern:
                continue
            candidate = pattern.replace("?", module_path)
            resolved = self.base_path / candidate
            if resolved.is_file():
                loader = BuiltinFunction(
                    f"module.loader[{name}]",
                    lambda loader_args, loader_vm, path=resolved: self._execute_module(
                        path, name, loader_vm
                    ),
                )
                return LuaMultiReturn([loader, str(resolved)])
        return LuaMultiReturn([None, f"no file '{module_path}'" ])

    def _execute_module(self, path: pathlib.Path, name: str, vm: BytecodeVM) -> LuaMultiReturn:
        source = path.read_text(encoding="utf-8")
        instructions = self._compile(source, source_name=str(path))
        module_env = self._module_environment(name, vm.lua_env)
        with self._scoped_base_path(path):
            result = self._run_instructions(instructions, module_env, [name])
        self._sync_vm_globals(vm, module_env)
        return LuaMultiReturn(result)

    # ------------------------------------------------------------------ environments
    def _module_environment(self, name: str, base_env: LuaEnvironment) -> LuaEnvironment:
        env = self.module_envs.get(name)
        if env is None:
            env = base_env
        self.attach_environment(env)
        return env

    def _resolve_environment(
        self,
        override: Optional[object],
        base_env: LuaEnvironment,
    ) -> LuaEnvironment:
        if override is None:
            return base_env
        if isinstance(override, LuaEnvironment):
            self.attach_environment(override)
            return override
        if isinstance(override, Mapping):
            env = LuaEnvironment(override)
        elif isinstance(override, LuaTable):
            mapping = {key: value for key, value in override.iter_items() if isinstance(key, str)}
            env = LuaEnvironment(mapping)
        else:
            raise RuntimeError("environment must be table or environment")
        self.attach_environment(env)
        return env

    def register_module_environment(
        self,
        name: str,
        env_value: object,
        *,
        inherit: bool,
    ) -> None:
        if isinstance(env_value, LuaEnvironment):
            env = env_value
        elif isinstance(env_value, LuaTable):
            mapping = {key: value for key, value in env_value.iter_items() if isinstance(key, str)}
            env = LuaEnvironment(mapping)
        elif isinstance(env_value, Mapping):
            env = LuaEnvironment(env_value)
        else:
            raise RuntimeError("sandbox environment must be table")
        if inherit:
            for key, value in self.root_env.snapshot().items():
                if key in {"_G", "_ENV"}:
                    continue
                env.register(key, value)
        self.attach_environment(env)
        self.module_envs[name] = env

    # ------------------------------------------------------------------ builtins
    def _lua_require(self, args: Sequence[object], vm: BytecodeVM) -> object:
        if not args:
            raise RuntimeError("require expects module name")
        name = str(args[0])
        return self.require(name, vm)

    def _lua_dofile(self, args: Sequence[object], vm: BytecodeVM) -> LuaMultiReturn:
        if not args:
            raise RuntimeError("dofile expects filename")
        filename = str(args[0])
        result = self.load_file(filename, vm.lua_env)
        values = vm.call_callable(result, [])
        return LuaMultiReturn(values)

    def _lua_load(self, args: Sequence[object], vm: BytecodeVM) -> LuaMultiReturn:
        if not args:
            raise RuntimeError("load expects chunk string")
        chunk = args[0]
        if not isinstance(chunk, str):
            raise RuntimeError("load only supports string chunks")
        chunkname = "<load>"
        env_override = None
        if len(args) >= 2 and args[1] is not None:
            chunkname = str(args[1])
        if len(args) == 3:
            env_override = args[2]
        elif len(args) >= 4:
            env_override = args[3]
        try:
            func = self.load_string(chunk, chunkname=chunkname, base_env=vm.lua_env, env_override=env_override)
        except Exception as exc:  # noqa: BLE001
            return LuaMultiReturn([None, str(exc)])
        return LuaMultiReturn([func])

    def _lua_loadfile(self, args: Sequence[object], vm: BytecodeVM) -> LuaMultiReturn:
        if not args:
            raise RuntimeError("loadfile expects filename")
        filename = str(args[0])
        env_override = None
        if len(args) >= 2:
            env_override = args[1]
        try:
            func = self.load_file(filename, vm.lua_env, env_override=env_override)
        except Exception as exc:  # noqa: BLE001
            return LuaMultiReturn([None, str(exc)])
        return LuaMultiReturn([func])

    def _lua_package_sandbox(self, args: Sequence[object], vm: BytecodeVM) -> None:
        if len(args) < 2:
            raise RuntimeError("package.sandbox expects module name and environment")
        name = str(args[0])
        env_value = args[1]
        inherit = bool(args[2]) if len(args) >= 3 else False
        self.register_module_environment(name, env_value, inherit=inherit)
        return None

    # ------------------------------------------------------------------ path utils
    def _resolve_path(self, filename: str) -> pathlib.Path:
        path = pathlib.Path(filename)
        if not path.is_absolute():
            path = (self.base_path / filename).resolve()
        return path


__all__ = ["LuaModuleSystem"]
