from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Optional

from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError, SchemeSyntaxError, SchemeVMRuntimeError
from haifa_scheme.runtime import run_source
from haifa_scheme.stdlib import create_global_environment
from haifa_scheme.values import to_scheme_string
from haifa_scheme.compiler import SchemeCompiler
from haifa_scheme.reader import parse_source_with_locations
from haifa_scheme.vm_runtime import SchemeVMRuntime


class ReplSession:
    MAIN_PROMPT = "scheme> "

    def __init__(self, environment: Environment | None = None) -> None:
        self.environment = environment or create_global_environment()

    def run(self) -> None:
        while True:
            try:
                line = input(self.MAIN_PROMPT)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            if self.process_line(line):
                break

    def process_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if stripped in {":quit", ":q"}:
            return True
        if stripped == ":help":
            print("Commands:")
            print("  :help      Show this help message")
            print("  :quit/:q   Exit the REPL")
            return False

        try:
            output = run_source(line, self.environment, input=sys.stdin, output=sys.stdout)
        except (SchemeRuntimeError, SchemeSyntaxError) as exc:
            print(f"Scheme execution failed: {exc}", file=sys.stderr)
            return False
        _print_values(output, skip_void=True)
        return False


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="pyscheme", description="Run Scheme source")
    parser.add_argument("script", nargs="?", help="Path to Scheme script (.scm)")
    parser.add_argument("-e", "--execute", dest="inline", help="Execute Scheme code string")
    parser.add_argument("--print-output", action="store_true", help="Print expression results")
    parser.add_argument("--repl", action="store_true", help="Start an interactive REPL session")
    parser.add_argument(
        "--backend",
        choices=("interpreter", "vm"),
        default="interpreter",
        help="Execution backend to use",
    )
    parser.add_argument("--trace", action="store_true", help="Trace VM instructions")
    parser.add_argument("--stack", action="store_true", help="Print stack traceback on errors")
    parser.add_argument(
        "--break-on-error",
        action="store_true",
        help="Break into visualizer when VM runtime error occurs",
    )
    parser.add_argument(
        "--visualize",
        choices=("gui", "curses"),
        help="Run with bytecode VM visualizer",
    )
    args = parser.parse_args(argv)

    if args.inline and args.script:
        parser.error("cannot use script path and --execute together")
    if args.repl and (args.inline or args.script):
        parser.error("--repl cannot be combined with script or --execute")
    if args.backend == "interpreter" and (args.trace or args.stack or args.break_on_error or args.visualize):
        parser.error("debug options are only supported with --backend vm")

    try:
        if args.repl or (not args.inline and not args.script and sys.stdin.isatty()):
            ReplSession().run()
            return 0

        source_name = "<stdin>"
        if args.inline:
            source = args.inline
            source_name = "<input>"
        elif args.script:
            script_path = pathlib.Path(args.script)
            source = script_path.read_text(encoding="utf-8")
            source_name = str(script_path)
        else:
            source = sys.stdin.read()

        if args.backend == "vm":
            output = _run_vm_cli(
                source,
                source_name=source_name,
                print_trace=args.trace,
                visualize=args.visualize,
                break_on_error=args.break_on_error,
            )
        else:
            if args.inline:
                output = run_source(source, input=sys.stdin, output=sys.stdout)
            elif args.script:
                output = run_source(source, input=sys.stdin, output=sys.stdout)
            else:
                output = run_source(source, output=sys.stdout)

        if args.print_output:
            _print_values(output)
        return 0
    except OSError as exc:
        print(f"Failed to read Scheme source: {exc}", file=sys.stderr)
        return 1
    except (SchemeRuntimeError, SchemeSyntaxError, SchemeVMRuntimeError) as exc:
        if isinstance(exc, SchemeVMRuntimeError) and args.stack and exc.frames:
            print(_format_stack_trace(exc.frames), file=sys.stderr)
        print(f"Scheme execution failed: {exc}", file=sys.stderr)
        return 1


def _print_values(values: list[object], *, skip_void: bool = False) -> None:
    for value in values:
        if skip_void and value is None:
            continue
        print(to_scheme_string(value))


def _format_stack_trace(frames: list[object]) -> str:
    lines = ["Stack traceback:"]
    for frame in frames:
        file = getattr(frame, "file", "<unknown>")
        line = getattr(frame, "line", 0)
        column = getattr(frame, "column", 0)
        function = getattr(frame, "function_name", "<chunk>")
        lines.append(f"  at {function} ({file}:{line}:{column})")
    return "\n".join(lines)


def _run_vm_cli(
    source: str,
    *,
    source_name: str,
    print_trace: bool,
    visualize: str | None,
    break_on_error: bool,
) -> list[object]:
    from compiler.vm_errors import VMRuntimeError

    expressions = parse_source_with_locations(source, source_name=source_name)
    if not expressions:
        return []

    runtime = SchemeVMRuntime()
    compiler = SchemeCompiler(runtime)
    instructions = compiler.compile_expressions(expressions, source_name=source_name)
    vm = runtime.create_vm(instructions)
    vm.index_labels()

    if visualize:
        if break_on_error:
            try:
                if print_trace:
                    _run_vm_with_trace(vm)
                else:
                    vm.run()
            except VMRuntimeError as exc:
                _launch_visualizer(visualize, vm, source, source_name)
                raise _as_scheme_vm_error(exc) from exc
        _launch_visualizer(visualize, vm, source, source_name)
        return []

    try:
        if print_trace:
            _run_vm_with_trace(vm)
        else:
            vm.run()
    except VMRuntimeError as exc:
        raise _as_scheme_vm_error(exc) from exc

    runtime.sync_from_vm(vm)
    return [vm.registers.get(register) for register in compiler.result_registers]


def _run_vm_with_trace(vm) -> None:
    while True:
        if vm.pc >= len(vm.instructions):
            break
        inst = vm.instructions[vm.pc]
        debug = inst.debug
        if debug is None:
            location = "<unknown>:0:0"
            function = "<chunk>"
        else:
            location = f"{debug.location.file}:{debug.location.line}:{debug.location.column}"
            function = debug.function_name
        print(f"{vm.pc:04d} {inst.opcode.name} {inst.args} {location} {function}", file=sys.stderr)
        control = vm.step()
        if control == "halt":
            break


def _as_scheme_vm_error(exc) -> SchemeVMRuntimeError:
    head = next((frame for frame in exc.frames if getattr(frame, "file", None) and getattr(frame, "line", 0)), None)
    if head is None:
        return SchemeVMRuntimeError(str(exc), frames=list(getattr(exc, "frames", [])))
    return SchemeVMRuntimeError(
        f"{head.file}:{head.line}: {exc}", frames=list(getattr(exc, "frames", []))
    )


def _launch_visualizer(mode: str, vm, source: str, source_name: str) -> None:
    if mode == "curses":
        from compiler.vm_visualizer_headless import VMVisualizer

        VMVisualizer(vm, source_text=source, source_name=source_name).run()
        return
    if mode == "gui":
        from compiler.vm_visualizer import VMVisualizer

        VMVisualizer(vm, source_text=source, source_name=source_name).run()
        return
    raise ValueError(f"unknown visualizer mode: {mode}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
