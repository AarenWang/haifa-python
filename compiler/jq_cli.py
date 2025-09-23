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
    from compiler.jq_runtime import run_filter_many  # type: ignore
else:
    from .jq_runtime import run_filter_many


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
    parser.add_argument("--visualize", action="store_true", help="Visualize VM execution")
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
            if _RUNNING_AS_SCRIPT:
                from compiler.jq_parser import parse_jq_program  # type: ignore
                from compiler.jq_compiler import compile_to_bytecode, INPUT_REGISTER  # type: ignore
                from compiler.jq_vm import JQVM  # type: ignore
            else:
                from .jq_parser import parse_jq_program
                from .jq_compiler import compile_to_bytecode, INPUT_REGISTER
                from .jq_vm import JQVM
            # Try GUI visualizer first; fallback to headless if pygame not available
            VMVisualizer = None
            gui_exc = None
            try:
                if _RUNNING_AS_SCRIPT:
                    from compiler.vm_visualizer import VMVisualizer as _GUIVisualizer  # type: ignore
                else:
                    from .vm_visualizer import VMVisualizer as _GUIVisualizer
                VMVisualizer = _GUIVisualizer
            except Exception as e:
                gui_exc = e
                try:
                    if _RUNNING_AS_SCRIPT:
                        from compiler.vm_visualizer_headless import VMVisualizer as _HeadlessVisualizer  # type: ignore
                    else:
                        from .vm_visualizer_headless import VMVisualizer as _HeadlessVisualizer
                    VMVisualizer = _HeadlessVisualizer
                except Exception as headless_exc:
                    print(
                        "Visualizer unavailable. GUI error: "
                        f"{gui_exc}; Headless error: {headless_exc}",
                        file=sys.stderr,
                    )
                    return 1

            if not inputs:
                print("Cannot visualize with empty input.", file=sys.stderr)
                return 1
            
            # For visualization, we run one input at a time.
            # Using the first input for simplicity.
            first_input = next(iter(inputs), None)

            ast = parse_jq_program(args.filter)
            bytecode = compile_to_bytecode(ast)
            
            vm = JQVM(bytecode)
            vm.registers[INPUT_REGISTER] = first_input
            
            visualizer = VMVisualizer(vm)
            visualizer.run()
            return 0

        results = run_filter_many(filter_expr, inputs, env=env)
        for item in results:
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
    except Exception as exc:  # pragma: no cover - defensive
        print(f"jq execution failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
