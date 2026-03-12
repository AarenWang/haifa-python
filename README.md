# Haifa Python

English | [简体中文](README_CN.md)

Haifa Python is a teaching-oriented compiler and virtual machine playground built in Python. It uses one core bytecode VM to support two learning tracks:

- a jq-style JSON query/runtime tool (`pyjq`)
- a Lua subset with runtime, coroutines, and tracing (`pylua`)

The project is designed for people who want to study how source code moves through the full execution pipeline: lexer, parser, AST, semantic analysis, bytecode generation, VM execution, and debugging/visualization.

## Purpose

Haifa Python exists to make language implementation easier to inspect, modify, and teach. Instead of treating compilers and interpreters as black boxes, it exposes each layer as readable Python modules with examples, tests, and visualizers.

This makes the repository useful for:

- compiler and interpreter courses
- programming languages self-study
- experiments with bytecode design and runtime behavior
- demonstrations of coroutines, closures, tables, and multi-return semantics
- jq-style data transformation on top of a reusable VM core

## Computer Science Topics Covered

The codebase maps directly to core CS and PL concepts:

- lexical analysis and parsing
- abstract syntax trees and source mapping
- semantic analysis for scopes, closures, and upvalues
- bytecode instruction design
- stack/register-style VM execution tradeoffs
- call stacks, environments, and runtime error reporting
- coroutines and event-driven execution tracing
- CLI tooling, debugging views, and execution visualization

If you are teaching or learning compiler construction, language runtimes, or virtual machines, this repository is meant to be studied as much as it is meant to be run.

## Project Layout

- `compiler/`: core bytecode VM, jq frontend/runtime, instruction set, and visualizers
- `haifa_lua/`: Lua lexer, parser, compiler, runtime, stdlib, coroutines, and CLI
- `docs/`: user guides, sprint notes, and reference material
- `knowledge/`: architecture and deep-dive notes
- `examples/`: runnable Lua and coroutine examples
- `benchmark/`: benchmark scripts, runner, and stored results

## Quick Start

### Requirements

- Python 3.11+
- Optional: `pygame` for the GUI visualizer

### Install from source

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install .
```

To enable the GUI visualizer:

```bash
python3 -m pip install ".[gui]"
```

### Run tests

```bash
pytest
```

### Try the Lua runtime

Run a script:

```bash
python3 -m haifa_lua.cli examples/hello.lua --print-output
```

Evaluate inline code:

```bash
python3 -m haifa_lua.cli -e 'x = 1; y = 2; return x + y' --print-output
```

Start the REPL:

```bash
python3 -m haifa_lua.cli --repl
```

Trace or visualize execution:

```bash
python3 -m haifa_lua.cli examples/coroutines.lua --trace coroutine
python3 -m haifa_lua.cli examples/coroutines.lua --visualize curses
```

### Try the jq-style runtime

Query a JSON file:

```bash
python3 -m haifa_jq.jq_cli '.items[] | .name' --input compiler/sample.json
```

Pipe JSON from stdin:

```bash
cat compiler/sample.json | python3 -m haifa_jq.jq_cli '.items[] | .price'
```

Use the terminal visualizer:

```bash
python3 -m haifa_jq.jq_cli '.items[] | .name' --input compiler/sample.json --visualize curses
```

After installation, the same tools are also available as:

```bash
pylua --help
pyjq --help
```

## Learning Path

For a guided tour, a practical sequence is:

1. Run a Lua example from `examples/`.
2. Read `haifa_lua/lexer.py`, `haifa_lua/parser.py`, and `haifa_lua/compiler.py`.
3. Follow execution into `compiler/bytecode.py` and `compiler/bytecode_vm.py`.
4. Compare the Lua flow with the jq flow in `haifa_jq/jq_parser.py`, `haifa_jq/jq_compiler.py`, and `haifa_jq/jq_vm.py`.
5. Open the visualizer or trace output to inspect runtime state changes.

## Documentation

- [`docs/lua_guide.md`](docs/lua_guide.md): practical guide to the Lua runtime
- [`docs/guide.md`](docs/guide.md): jq CLI guide and examples
- [`docs/reference.md`](docs/reference.md): command reference
- [`docs/lua_sprint.md`](docs/lua_sprint.md): implementation milestones and roadmap
- [`knowledge/03-bytecode-and-vm.md`](knowledge/03-bytecode-and-vm.md): bytecode/VM background
- [`knowledge/06-lua-execution-pipeline.md`](knowledge/06-lua-execution-pipeline.md): end-to-end Lua execution pipeline

## Notes

- The GUI visualizer depends on `pygame`. In non-GUI environments, use `--visualize curses`.
- The Lua implementation is intentionally a subset/runtime experiment, not a full Lua compatibility target.
- The repository favors readability and inspectability over aggressive optimization.
