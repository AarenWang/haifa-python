import argparse
import json
import sys
from typing import Iterable, List, Optional

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
    parser.add_argument("filter", help="jq filter expression")
    parser.add_argument("--input", "-f", dest="input_path", help="Path to JSON input file")
    parser.add_argument("--slurp", action="store_true", help="Treat the entire JSON document as a single input value")
    parser.add_argument("--visualize", action="store_true", help="Visualize VM execution")
    args = parser.parse_args(argv)

    try:
        raw = _load_json_from_source(args.input_path)
        inputs = _prepare_inputs(raw, args.slurp)
        
        if args.visualize:
            # Prefer package-relative imports for core pieces
            from .jq_parser import parse_jq_program
            from .jq_compiler import compile_to_bytecode, INPUT_REGISTER
            from .bytecode_vm import BytecodeVM
            # Try GUI visualizer first; fallback to headless if pygame not available
            VMVisualizer = None
            gui_exc = None
            try:
                from .vm_visualizer import VMVisualizer as _GUIVisualizer
                VMVisualizer = _GUIVisualizer
            except Exception as e:
                gui_exc = e
                try:
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
            
            vm = BytecodeVM(bytecode)
            vm.registers[INPUT_REGISTER] = first_input
            
            visualizer = VMVisualizer(vm)
            visualizer.run()
            return 0

        results = run_filter_many(args.filter, inputs)
        for item in results:
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
