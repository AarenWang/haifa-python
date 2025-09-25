from __future__ import annotations

import atexit
import sys
from pathlib import Path
from typing import Iterable, Optional

from compiler.bytecode_vm import BytecodeVM
from compiler.vm_errors import VMRuntimeError

from .debug import LuaRuntimeError, as_lua_error
from .environment import LuaEnvironment
from .event_format import format_coroutine_event
from .parser import ParserError
from .runtime import compile_source
from .stdlib import _lua_tostring, create_default_environment

try:  # pragma: no cover - platform specific
    import readline  # type: ignore
except ImportError:  # pragma: no cover - Windows fallback
    readline = None  # type: ignore


_HISTORY_FILE = Path.home() / ".pylua_history"
_TRACE_FILTERS = {"none", "instructions", "coroutine", "all"}


class ReplSession:
    MAIN_PROMPT = "> "
    CONTINUATION_PROMPT = "... "

    def __init__(
        self,
        *,
        env: Optional[LuaEnvironment] = None,
        trace_filter: str = "none",
        show_stack: bool = False,
        break_on_error: bool = False,
        enable_readline: bool = True,
    ) -> None:
        self.env = env or create_default_environment()
        if trace_filter not in _TRACE_FILTERS:
            trace_filter = "none"
        self.trace_filter = trace_filter
        self.show_stack = show_stack
        self.break_on_error = break_on_error
        self._buffer: list[str] = []
        self._enable_readline = enable_readline
        self._configure_readline()

    # ------------------------------------------------------------------ public API
    def run(self) -> None:
        while True:
            prompt = self.CONTINUATION_PROMPT if self._buffer else self.MAIN_PROMPT
            try:
                line = self._read_line(prompt)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                self._buffer.clear()
                continue
            result = self.process_line(line)
            if result is True:
                break

    def process_line(self, line: str) -> Optional[bool]:
        if not self._buffer:
            command_result = self._try_command(line)
            if command_result is not None:
                return command_result
        if not self._buffer and line.lstrip().startswith("="):
            line = self.normalize_source(line)
        self._buffer.append(line)
        source = "\n".join(self._buffer)
        try:
            instructions = list(compile_source(source, source_name="<repl>"))
        except ParserError as exc:
            message = str(exc)
            if self.is_incomplete(message):
                return None
            self._print_parser_error(message)
            self._buffer.clear()
            return None
        except SyntaxError as exc:  # pragma: no cover - defensive
            self._print_parser_error(str(exc))
            self._buffer.clear()
            return None
        self._buffer.clear()
        try:
            vm = self._execute_instructions(instructions)
        except LuaRuntimeError as exc:
            self._handle_runtime_error(exc)
            return None
        self._print_vm_output(vm)
        return None

    def is_incomplete(self, message: str) -> bool:
        lower = message.lower()
        return "unexpected eof" in lower or "got eof" in lower

    def normalize_source(self, line: str) -> str:
        stripped = line.lstrip()
        if not stripped.startswith("="):
            return line
        prefix = line[: len(line) - len(stripped)]
        expression = stripped[1:].lstrip()
        return f"{prefix}return {expression}"

    def print_results(self, values: Iterable[object]) -> None:
        text = "\t".join(_lua_tostring(value) for value in values)
        print(text)

    # ------------------------------------------------------------------ helpers
    def _execute_instructions(self, instructions: list) -> BytecodeVM:
        vm = BytecodeVM(instructions)
        vm.lua_env = self.env
        vm.registers.update(self.env.to_vm_registers())
        debug = self.trace_filter in {"all", "instructions"}
        self.env.bind_vm(vm)
        try:
            vm.run(debug=debug)
        except VMRuntimeError as exc:
            raise as_lua_error(exc) from exc
        finally:
            self.env.unbind_vm()
        self.env.sync_from_vm(vm.registers)
        return vm

    def _handle_runtime_error(self, error: LuaRuntimeError) -> None:
        if self.show_stack and error.traceback:
            print(error.traceback, file=sys.stderr)
        if self.break_on_error:
            try:
                input("Execution paused due to error. Press Enter to continue...")
            except EOFError:  # pragma: no cover - interactive only
                pass
        print(error, file=sys.stderr)

    def _print_vm_output(self, vm: BytecodeVM) -> None:
        for text in vm.output:
            print(text)
        results: list[object] = []
        if vm.last_return:
            results = list(vm.last_return)
        elif vm.return_value is not None:
            results = [vm.return_value]
        if results:
            self.print_results(results)
        events = vm.drain_events()
        if events and self.trace_filter in {"all", "coroutine"}:
            self._print_events(events)

    def _print_events(self, events: list[object]) -> None:
        print("Coroutine events:")
        for event in events:
            print(f"  - {format_coroutine_event(event)}")

    def _print_parser_error(self, message: str) -> None:
        location = "<repl>"
        formatted = message
        if " at " in message:
            base, _, suffix = message.rpartition(" at ")
            if ":" in suffix:
                formatted = f"{location}:{suffix}: {base}"
            else:
                formatted = f"{location}: {base}"
        else:
            formatted = f"{location}: {message}"
        print(formatted, file=sys.stderr)

    def _try_command(self, line: str) -> Optional[bool]:
        stripped = line.strip()
        if not stripped.startswith(":"):
            return None
        parts = stripped[1:].split()
        if not parts:
            return None
        command, *args = parts
        if command in {"quit", "q"}:
            return True
        if command == "help":
            self._print_help()
            return None
        if command == "trace":
            self._handle_trace_command(args)
            return None
        if command == "env":
            self._print_environment()
            return None
        print(f"Unknown command: :{command}")
        return None

    def _handle_trace_command(self, args: list[str]) -> None:
        if not args:
            print(f"Trace filter: {self.trace_filter}")
            return
        value = args[0].lower()
        if value not in _TRACE_FILTERS:
            options = ", ".join(sorted(_TRACE_FILTERS))
            print(f"Invalid trace filter '{value}'. Available: {options}")
            return
        self.trace_filter = value
        print(f"Trace filter set to {value}")

    def _print_environment(self) -> None:
        snapshot = self.env.snapshot()
        keys = sorted(key for key in snapshot.keys() if isinstance(key, str))
        print("Globals:")
        for key in keys:
            print(f"  {key}")

    def _print_help(self) -> None:
        print("Commands:")
        print("  :help             Show this help message")
        print("  :quit / :q        Exit the REPL")
        print("  :trace <mode>     Set trace mode (none, instructions, coroutine, all)")
        print("  :env              List global environment keys")
        print("Expressions prefixed with '=' are treated as return statements.")

    def _configure_readline(self) -> None:
        if not self._enable_readline or readline is None:
            return
        if not sys.stdin.isatty():  # pragma: no cover - interactive only
            return
        try:
            readline.parse_and_bind("tab: complete")
            readline.set_completer(self._complete)
            if _HISTORY_FILE.exists():
                readline.read_history_file(str(_HISTORY_FILE))
        except Exception:  # pragma: no cover - defensive
            return
        atexit.register(self._save_history)

    def _complete(self, text: str, state: int) -> Optional[str]:
        candidates = [
            key
            for key in self.env.snapshot().keys()
            if isinstance(key, str) and key.startswith(text)
        ]
        candidates.sort()
        if state < len(candidates):
            return candidates[state]
        return None

    def _save_history(self) -> None:  # pragma: no cover - interactive only
        if readline is None:
            return
        try:
            readline.write_history_file(str(_HISTORY_FILE))
        except OSError:
            pass

    def _read_line(self, prompt: str) -> str:
        return input(prompt)


__all__ = ["ReplSession"]
