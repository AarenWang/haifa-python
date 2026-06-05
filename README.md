# Haifa Python

English | [简体中文](README_CN.md)

Haifa Python is a teaching-oriented compiler, interpreter, and virtual machine
playground written in Python. It is designed for people who want to inspect the
full path from source code to runtime state: lexer, parser, AST, semantic
analysis, bytecode generation, VM execution, debugging, visualization, and
lowering to a lower-level VM target.

The project currently contains four connected learning tracks:

- `pyjq`: a jq-style JSON query/runtime tool
- `pylua`: a Lua subset with bytecode compilation, tables, closures, coroutines,
  tracing, and standard library support
- `pyscheme`: a small Scheme runtime and bytecode compiler with lexical scope,
  pairs, lists, vectors, control forms, closures, and REPL support
- `HaifaArmV9VM`: an ARMv9-style teaching VM target with fixed registers,
  explicit stack/heap/global memory, lowering from Haifa bytecode, debug
  snapshots, and a register-allocation teaching report

## Why This Exists

Haifa Python tries to make language implementation visible instead of mystical.
The code favors readability, small modules, runnable examples, and direct tests.
It is useful for:

- compiler and interpreter courses
- programming language self-study
- experiments with bytecode design and runtime behavior
- demonstrations of closures, cells/upvalues, tables, coroutines, varargs, and
  multi-return semantics
- comparing a high-level virtual-register VM with a lower-level ARMv9-style
  load/store VM
- jq-style JSON data transformation on top of the same VM infrastructure

## Current Capabilities

### Core Haifa BytecodeVM

- Register-style bytecode VM with named virtual registers
- Function calls, call frames, parameters, returns, tail calls, varargs, and
  multi-return values
- Closures, mutable cells, captured upvalues, and closure calls
- Lua table operations, array helpers, bitwise operations, and runtime objects
- Source/debug metadata, traceback support, coroutine events, VM snapshots, and
  visualizer support

### HaifaArmV9VM

`HaifaArmV9VM` keeps the current high-level `BytecodeVM` intact and adds a
separate ARMv9-style target for teaching lower-level execution:

- Fixed registers: `X0`-`X15`, `SP`, `FP`, `LR`, `PC`, and `NZCV`
- Explicit memory sections: constant pool, stack, heap, and globals
- Load/store execution model with `LDR` / `STR`
- `BL` / `RET` call frames and recursive function support
- Heap tables, cells, closures, and multi-return objects
- Lowering from Haifa bytecode via `compiler.armv9_lowering`
- Optional register-cache optimization and liveness/report output via
  `compiler.armv9_register_alloc`
- Unified debug snapshots through `compiler.vm_debug_adapter`

The ARMv9 target is intentionally not a full ARM CPU emulator. It is a readable
VM target inspired by AArch64/ARMv9 concepts.

### jq Runtime

- jq-style parser, compiler, VM, runtime, and CLI
- Filters such as field/index access, pipes, `map`, `select`, `flatten`,
  `reduce`, `foreach`, `paths`, `setpath`, `del`, `walk`, `input`, and `inputs`
- Object and array literals
- Runtime fallback error wrapping when system `jq` is unavailable

### Lua Runtime

- Lua lexer/parser/compiler pipeline
- Locals, globals, functions, closures, upvalues, varargs, and multi-return
- Tables, field/index access, method calls, numeric/generic loops, `break`,
  `repeat`, `do`, `goto`, and labels
- Coroutine runtime with lifecycle events and trace output
- Core standard libraries, module loading, and Lua-style errors/tracebacks

### Scheme Runtime

- Reader/parser, tree-walking runtime, and bytecode compiler path
- Lexical scope, lambdas, closures, recursion, `let`/`let*`/`letrec`, named
  `let`, `begin`, `set!`, `cond`, `case`, `and`, `or`, and `do`
- Scheme values such as symbols, pairs, lists, vectors, strings, characters,
  booleans, and numbers
- REPL and CLI support

### Debugging And Visualization

- GUI visualizer through `pygame`
- Terminal/curses visualizer where available
- Windows-safe import fallback for headless visualizer tests when `_curses` is
  unavailable
- Unified VM debug adapter snapshots for `BytecodeVM` and `HaifaArmV9VM`
- Static browser demo in [`docs/lua-vm-demo`](docs/lua-vm-demo/README.md)
  showing the same Lua examples in both BytecodeVM and ARMv9 modes

## Project Layout

- `compiler/`: core bytecode VM, ARMv9 VM, lowering, debug adapters, visualizers,
  instruction definitions, and compatibility wrappers
- `haifa_jq/`: jq AST, parser, compiler, VM, runtime, and CLI
- `haifa_lua/`: Lua lexer, parser, compiler, runtime, stdlib, coroutines,
  modules, and CLI
- `haifa_scheme/`: Scheme reader, runtime, compiler, values, stdlib, and CLI
- `docs/`: user guides, VM references, sprint notes, and browser demos
- `knowledge/`: deeper design notes and architecture plans
- `examples/`: runnable Lua and Scheme examples
- `benchmark/`: benchmark scripts, runner, and stored results
- `vm/`: earlier VM experiments and reference material

## Quick Start

### Requirements

- Python 3.11+
- Optional: `pygame` for the GUI visualizer
- Optional: Node.js if you want to run `node --check` on the browser demo JS

### Install From Source

Unix/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install .
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install .
```

To enable the GUI visualizer:

```bash
python3 -m pip install ".[gui]"
```

### Run Tests

```bash
pytest
```

On Windows during development, prefer avoiding bytecode writes:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest compiler\tests haifa_lua\tests haifa_scheme\tests -q
```

Current full suite status after the latest iteration:

```text
541 passed
```

## Try The Runtimes

### Lua

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

### Scheme

Run a script:

```bash
python3 -m haifa_scheme.cli examples/factorial.scm --print-output
```

Run through the VM backend with tracing:

```bash
python3 -m haifa_scheme.cli examples/factorial.scm --backend vm --trace --print-output
```

Evaluate inline code:

```bash
python3 -m haifa_scheme.cli -e '(letrec ((fact (lambda (n) (if (= n 0) 1 (* n (fact (- n 1))))))) (fact 5))' --print-output
```

Start the REPL:

```bash
python3 -m haifa_scheme.cli --repl
```

### jq-style Runtime

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

After installation, the same tools are available as:

```bash
pylua --help
pyjq --help
pyscheme --help
```

## ARMv9 Lowering Example

The ARMv9 path is currently a Python API rather than a standalone CLI:

```python
from compiler.armv9_lowering import lower_to_armv9
from compiler.armv9_vm import HaifaArmV9VM
from haifa_lua.runtime import compile_source

bytecode = list(compile_source("local t = {a = 42}; return t.a"))
lowered = lower_to_armv9(bytecode)
vm = HaifaArmV9VM(lowered.instructions, const_pool=lowered.const_pool)
vm.run()
print(vm.snapshot()["registers"])
print(lowered.allocation_report.readable_text())
```

Use `lower_to_armv9(bytecode, optimize_registers=True)` to enable the teaching
register-cache optimization and report.

## Browser Teaching Demo

Open:

```text
docs/lua-vm-demo/index.html
```

The demo can be opened directly in a browser. It shows the same Lua examples in
two modes:

- high-level Haifa BytecodeVM instructions and named virtual registers
- ARMv9 lowering with fixed registers, stack slots, heap objects, globals,
  constant pool, and `NZCV`

Regenerate demo data:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python docs\lua-vm-demo\export_demo.py
```

## Learning Path

For a guided tour:

1. Run a Lua example from `examples/`.
2. Read `haifa_lua/lexer.py`, `haifa_lua/parser.py`, and
   `haifa_lua/compiler.py`.
3. Follow execution into `compiler/bytecode.py` and
   `compiler/bytecode_vm.py`.
4. Compare the jq flow in `haifa_jq/jq_parser.py`,
   `haifa_jq/jq_compiler.py`, and `haifa_jq/jq_vm.py`.
5. Compare the Scheme interpreter and compiler paths in `haifa_scheme/`.
6. Study `compiler/armv9_lowering.py` and `compiler/armv9_vm.py` to see how the
   high-level VM is lowered to ARMv9-style execution.
7. Open the browser demo or visualizer to inspect runtime state changes.

## Documentation

- [`docs/lua_guide.md`](docs/lua_guide.md): practical guide to the Lua runtime
- [`docs/scheme_guide.md`](docs/scheme_guide.md): practical guide to the Scheme runtime
- [`docs/guide.md`](docs/guide.md): jq CLI guide and examples
- [`docs/reference.md`](docs/reference.md): command reference
- [`docs/vm_instruction_set.md`](docs/vm_instruction_set.md): VM instruction set reference
- [`docs/haifa_armv9_vm_plan.md`](docs/haifa_armv9_vm_plan.md): ARMv9 VM plan and phases
- [`docs/lua-vm-demo/README.md`](docs/lua-vm-demo/README.md): browser demo notes
- [`docs/lua_sprint.md`](docs/lua_sprint.md): Lua implementation milestones
- [`docs/haifa_scheme_sprit.md`](docs/haifa_scheme_sprit.md): Scheme implementation milestones
- [`knowledge/03-bytecode-and-vm.md`](knowledge/03-bytecode-and-vm.md): bytecode/VM background
- [`knowledge/06-lua-execution-pipeline.md`](knowledge/06-lua-execution-pipeline.md): Lua execution pipeline

## Notes

- The GUI visualizer depends on `pygame`; use `--visualize curses` where a
  terminal curses backend is available.
- The Lua implementation is intentionally a subset/runtime experiment, not a
  full Lua compatibility target.
- The Scheme implementation is intentionally a teaching subset, not a full
  R5RS/R7RS compatibility target.
- `HaifaArmV9VM` is an ARMv9-style educational target, not a complete hardware
  emulator.
- The repository favors readability, inspectability, and testable iteration over
  aggressive optimization.
