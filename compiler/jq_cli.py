import argparse
import json
import sys
from typing import Iterable, List, Optional

from jq_runtime import run_filter_many


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
    args = parser.parse_args(argv)

    try:
        raw = _load_json_from_source(args.input_path)
        inputs = _prepare_inputs(raw, args.slurp)
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
