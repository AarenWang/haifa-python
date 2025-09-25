from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Optional

from compiler.vm_errors import VMRuntimeError
from .debug import as_lua_error, format_traceback
from .event_format import format_coroutine_event
from .repl import ReplSession
from .runtime import compile_source, run_source
from .stdlib import create_default_environment
from compiler.bytecode_vm import BytecodeVM


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="pylua", description="Run Lua scripts on the core VM")
    parser.add_argument("script", nargs="?", help="Path to Lua script (.lua)")
    parser.add_argument("-e", "--execute", dest="inline", help="Execute Lua code string")
    parser.add_argument("--print-output", action="store_true", help="Print VM output array")
    parser.add_argument("--trace", nargs="?", const="all", help="Enable execution trace (optional filter 'coroutine')")
    parser.add_argument("--stack", action="store_true", help="Print Lua-style stack traceback on error")
    parser.add_argument(
        "--break-on-error",
        action="store_true",
        help="Pause for confirmation when an error occurs",
    )
    parser.add_argument("--repl", action="store_true", help="Start an interactive REPL session")
    parser.add_argument(
        "--visualize",
        nargs="?",
        const="gui",
        choices=["gui", "curses"],
        help="Visualize VM execution (optional mode: gui or curses)",
    )
    args = parser.parse_args(argv)

    try:
        trace_filter = (args.trace or "none").lower()
        debug_enabled = args.stack or args.break_on_error or trace_filter != "none"
        if args.inline and args.script:
            parser.error("cannot use script path and --execute together")
            return 1
        if args.repl and (args.inline or args.script):
            parser.error("--repl cannot be combined with script or --execute")
            return 1
        if args.visualize and args.repl:
            parser.error("--visualize cannot be combined with --repl")
            return 1

        # Visualization path: compile source and launch GUI/headless visualizer
        if args.visualize:
            selected_mode = args.visualize or "gui"
            if args.inline:
                source = args.inline
                source_name = "<inline>"
            elif args.script:
                source_name = args.script
                source = pathlib.Path(args.script).read_text(encoding="utf-8")
            else:
                parser.error("missing script or --execute for visualization")
                return 1

            instructions = list(compile_source(source, source_name=source_name))
            env = create_default_environment()
            vm = BytecodeVM(instructions)
            vm.lua_env = env
            vm.registers.update(env.to_vm_registers())
            module_system = getattr(env, "module_system", None)
            if module_system is not None and source_name and not source_name.startswith("<"):
                module_system.set_base_path(pathlib.Path(source_name))

            vm_class = None
            gui_exc: Exception | None = None
            if selected_mode == "gui":
                try:
                    from compiler.vm_visualizer import VMVisualizer as vm_class  # type: ignore
                except Exception as e:  # pragma: no cover - pygame missing/unavailable
                    gui_exc = e
                    selected_mode = "curses"

            if selected_mode == "curses":
                try:
                    from compiler.vm_visualizer_headless import VMVisualizer as vm_class  # type: ignore
                except Exception as headless_exc:  # pragma: no cover
                    if gui_exc is not None:
                        print(
                            "Visualizer unavailable. GUI error: "
                            f"{gui_exc}; Headless error: {headless_exc}",
                            file=sys.stderr,
                        )
                    else:
                        print(f"Visualizer unavailable: {headless_exc}", file=sys.stderr)
                    return 1

            assert vm_class is not None
            visualizer = vm_class(vm)
            visualizer.run()
            return 0
        if args.repl or (not args.inline and not args.script and sys.stdin.isatty()):
            session = ReplSession(
                trace_filter=trace_filter,
                show_stack=args.stack,
                break_on_error=args.break_on_error,
            )
            session.run()
            return 0
        if debug_enabled:
            if args.inline:
                source = args.inline
                source_name = "<inline>"
            elif args.script:
                source_name = args.script
                source = pathlib.Path(args.script).read_text(encoding="utf-8")
            else:
                parser.error("missing script or --execute")
                return 1
            output = _execute_with_debug(source, source_name, trace_filter, args)
        else:
            if args.inline:
                output = run_source(args.inline, source_name="<inline>")
            elif args.script:
                source_text = pathlib.Path(args.script).read_text(encoding="utf-8")
                output = run_source(source_text, source_name=args.script)
            else:
                parser.error("missing script or --execute")
                return 1
        if args.print_output:
            for item in output:
                print(item)
        return 0
    except Exception as exc:  # pragma: no cover - CLI surface
        if isinstance(exc, VMRuntimeError) and args.stack:
            print(format_traceback(exc.frames), file=sys.stderr)
        if isinstance(exc, VMRuntimeError) and args.break_on_error:
            try:
                input("Execution paused due to error. Press Enter to exit...")
            except EOFError:
                pass
        print(f"Lua execution failed: {exc}", file=sys.stderr)
        return 1


def _execute_with_debug(source: str, source_name: str, trace_filter: str, args: argparse.Namespace) -> list:
    instructions = list(compile_source(source, source_name=source_name))
    env = create_default_environment()
    vm = BytecodeVM(instructions)
    vm.lua_env = env
    vm.registers.update(env.to_vm_registers())
    module_system = getattr(env, "module_system", None)
    if module_system is not None and source_name and not source_name.startswith("<"):
        module_system.set_base_path(pathlib.Path(source_name))
    debug = trace_filter in {"all", "instructions"}
    env.bind_vm(vm)
    try:
        vm.run(debug=debug)
    except VMRuntimeError as exc:
        raise as_lua_error(exc) from exc
    finally:
        env.unbind_vm()
    env.sync_from_vm(vm.registers)
    events = vm.drain_events()
    if trace_filter in {"all", "coroutine"}:
        _print_events(events)
    output: list = list(vm.output)
    if not output and vm.last_return:
        output = list(vm.last_return)
    if vm.return_value is not None and not output:
        output = [vm.return_value]
    return output


def _print_events(events: list) -> None:
    if not events:
        return
    print("Coroutine events:")
    for event in events:
        print(f"  - {format_coroutine_event(event)}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
