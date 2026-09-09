#!/usr/bin/env python3
"""Dump Haifa intermediate bytecode for a Lua source file to text.

Usage:
    python -m haifa_lua.dump_bytecode <script.lua> [output.txt]
    python -m haifa_lua.dump_bytecode examples/sum_1_to_100.lua
"""

from __future__ import annotations

import sys
from pathlib import Path

from .runtime import compile_source


def dump_bytecode(source: str, *, source_name: str = "<stdin>") -> str:
    """Compile Lua source to Haifa intermediate bytecode and format as text."""
    instructions = list(compile_source(source, source_name=source_name))
    lines: list[str] = []
    for index, instruction in enumerate(instructions):
        line = f"{index:04d}  {instruction}"
        debug = getattr(instruction, "debug", None)
        if debug is not None and getattr(debug, "location", None) is not None:
            location = debug.location
            line += f"    ; {location.file}:{location.line}:{location.column}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    script_path = Path(sys.argv[1])
    if not script_path.exists():
        print(f"error: script not found: {script_path}", file=sys.stderr)
        return 1

    source = script_path.read_text(encoding="utf-8")
    text = dump_bytecode(source, source_name=str(script_path))

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
        output_path.write_text(text, encoding="utf-8")
        print(f"bytecode dumped to {output_path}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
