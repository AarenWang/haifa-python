import argparse
import json
import os
import sys
from typing import Iterable, List, Optional


_RUNNING_AS_SCRIPT = __package__ in (None, "")

if _RUNNING_AS_SCRIPT:
    # When bundled by PyInstaller or executed as a top-level script, ensure
    # package modules remain importable by adding the project root to sys.path.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from compiler.jq_runtime import (  # type: ignore
        JQRuntimeError,
        run_filter_stream,
    )
else:
    from .jq_runtime import JQRuntimeError, run_filter_stream


def _load_json_from_source(path: Optional[str]) -> str:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return sys.stdin.read()


def _prepare_inputs(raw: str, slurp: bool) -> Iterable[object]:
    if not raw.strip():
        return []
    data = json.loads(raw)
    if slurp or not isinstance(data, list):
        return [data]
    return data


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="haifa jq", description="Run jq filters on JSON input")
    parser.add_argument("filter", nargs="?", help="jq filter expression")
    parser.add_argument("--filter-file", "-f", dest="filter_path", help="Read filter from file path")
    parser.add_argument("--input", "-i", dest="input_path", help="Path to JSON input file")
    parser.add_argument("--slurp", action="store_true", help="Treat the entire JSON document as a single input value")
    parser.add_argument("-R", "--raw-input", action="store_true", help="Read raw lines as inputs (strings)")
    parser.add_argument("-n", "--null-input", action="store_true", help="Use null as the single input value")
    parser.add_argument("-r", "--raw-output", action="store_true", help="Output strings without JSON quotes")
    parser.add_argument("-c", "--compact-output", action="store_true", help="Compact JSON output (no spaces)")
    parser.add_argument("--arg", action="append", nargs=2, metavar=("name", "value"), help="Set variable $name to string value")
    parser.add_argument("--argjson", action="append", nargs=2, metavar=("name", "json"), help="Set variable $name to JSON value")
    parser.add_argument(
        "--visualize",
        nargs="?",
        const="gui",
        choices=["gui", "curses"],
        help="Visualize VM execution (optional mode: gui or curses)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print stack traces when jq compilation or execution fails",
    )
    args = parser.parse_args(argv)

    try:
        # Load filter
        if args.filter_path:
            with open(args.filter_path, "r", encoding="utf-8") as f:
                filter_expr = f.read().strip()
        else:
            if not args.filter:
                print("Missing filter expression (or --filter-file)", file=sys.stderr)
                return 1
            filter_expr = args.filter

        # Prepare inputs
        if args.null_input:
            inputs = [None]
        elif args.raw_input:
            # Raw input lines mode
            if args.input_path:
                with open(args.input_path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
            else:
                lines = sys.stdin.read().splitlines()
            inputs = lines
        else:
            raw = _load_json_from_source(args.input_path)
            inputs = _prepare_inputs(raw, args.slurp)

        # Environment variables
        env = {}
        if args.arg:
            for name, value in args.arg:
                env[name] = value
        if args.argjson:
            for name, value in args.argjson:
                env[name] = json.loads(value)
        
        if args.visualize:
            selected_mode = args.visualize or "gui"
            if _RUNNING_AS_SCRIPT:
                from compiler.jq_parser import parse_jq_program  # type: ignore
                from compiler.jq_compiler import compile_to_bytecode, INPUT_REGISTER  # type: ignore
                from compiler.jq_vm import JQVM  # type: ignore
            else:
                from .jq_parser import parse_jq_program
                from .jq_compiler import compile_to_bytecode, INPUT_REGISTER
                from .jq_vm import JQVM

            if not inputs:
                print("Cannot visualize with empty input.", file=sys.stderr)
                return 1

            vm_class = None
            gui_exc = None

            if selected_mode == "gui":
                try:
                    if _RUNNING_AS_SCRIPT:
                        from compiler.vm_visualizer import VMVisualizer as vm_class  # type: ignore
                    else:
                        from .vm_visualizer import VMVisualizer as vm_class
                except Exception as e:
                    gui_exc = e
                    selected_mode = "curses"

            if selected_mode == "curses":
                try:
                    if _RUNNING_AS_SCRIPT:
                        from compiler.vm_visualizer_headless import VMVisualizer as vm_class  # type: ignore
                    else:
                        from .vm_visualizer_headless import VMVisualizer as vm_class
                except Exception as headless_exc:
                    if gui_exc is not None:
                        print(
                            "Visualizer unavailable. GUI error: "
                            f"{gui_exc}; Headless error: {headless_exc}",
                            file=sys.stderr,
                        )
                    else:
                        print(f"Visualizer unavailable: {headless_exc}", file=sys.stderr)
                    return 1

            # For visualization, we run one input at a time (use first).
            first_input = next(iter(inputs), None)

            ast = parse_jq_program(filter_expr)
            bytecode = compile_to_bytecode(ast)

            vm = JQVM(bytecode)
            vm.registers[INPUT_REGISTER] = first_input

            if env:
                for name, value in env.items():
                    vm.registers[f"__jq_var_{name}"] = value

            visualizer = vm_class(vm)
            visualizer.run()
            return 0

        results_iter = run_filter_stream(filter_expr, inputs, env=env)
        for item in results_iter:
            if args.raw_output and isinstance(item, str):
                print(item)
            else:
                if args.compact_output:
                    print(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
                else:
                    print(json.dumps(item, ensure_ascii=False))
        return 0
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Failed to parse JSON input: {exc}", file=sys.stderr)
        return 1
    except JQRuntimeError as exc:
        if args.debug:
            import traceback

            traceback.print_exc()
        else:
            print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        if args.debug:
            import traceback

            traceback.print_exc()
        else:
            print(f"jq execution failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
