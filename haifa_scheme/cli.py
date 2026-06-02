from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Optional

from haifa_scheme.environment import Environment
from haifa_scheme.errors import SchemeRuntimeError, SchemeSyntaxError
from haifa_scheme.runtime import run_source
from haifa_scheme.stdlib import create_global_environment
from haifa_scheme.values import to_scheme_string


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
            output = run_source(line, self.environment)
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
    args = parser.parse_args(argv)

    if args.inline and args.script:
        parser.error("cannot use script path and --execute together")
    if args.repl and (args.inline or args.script):
        parser.error("--repl cannot be combined with script or --execute")

    try:
        if args.repl or (not args.inline and not args.script and sys.stdin.isatty()):
            ReplSession().run()
            return 0

        if args.inline:
            output = run_source(args.inline)
        elif args.script:
            source = pathlib.Path(args.script).read_text(encoding="utf-8")
            output = run_source(source)
        else:
            output = run_source(sys.stdin.read())

        if args.print_output:
            _print_values(output)
        return 0
    except OSError as exc:
        print(f"Failed to read Scheme source: {exc}", file=sys.stderr)
        return 1
    except (SchemeRuntimeError, SchemeSyntaxError) as exc:
        print(f"Scheme execution failed: {exc}", file=sys.stderr)
        return 1


def _print_values(values: list[object], *, skip_void: bool = False) -> None:
    for value in values:
        if skip_void and value is None:
            continue
        print(to_scheme_string(value))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
