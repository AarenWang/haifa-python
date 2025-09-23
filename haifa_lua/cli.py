from __future__ import annotations

import argparse
import sys
from typing import Optional

from .runtime import run_source, run_script


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="pylua", description="Run Lua scripts on the core VM")
    parser.add_argument("script", nargs="?", help="Path to Lua script (.lua)")
    parser.add_argument("-e", "--execute", dest="inline", help="Execute Lua code string")
    parser.add_argument("--print-output", action="store_true", help="Print VM output array")
    args = parser.parse_args(argv)

    try:
        if args.inline:
            output = run_source(args.inline)
        elif args.script:
            output = run_script(args.script)
        else:
            parser.error("missing script or --execute")
            return 1
        if args.print_output:
            for item in output:
                print(item)
        return 0
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"Lua execution failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
