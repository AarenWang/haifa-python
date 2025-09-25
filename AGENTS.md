# AGENTS.md — Working Conventions for haifa-python

This file gives agents practical guidance for making changes in this repo. Follow these rules when reading, writing, or refactoring code here.

## Scope & Priorities
- Keep changes minimal and focused on the requested task. Prefer surgical edits over broad refactors.
- Fix issues at the root cause; avoid superficial patches that mask underlying bugs.
- Preserve existing public behavior unless a change is explicitly requested and documented.
- Update documentation and tests alongside code changes when behavior or APIs evolve.

## Project Structure
- `compiler/`: Core bytecode VM, instruction set, jq layer, visualizers, and CLI for jq.
- `haifa_lua/`: Lua front-end (lexer/parser/compiler), runtime, stdlib, coroutines, and CLI `pylua`.
- `docs/`: User/developer docs (guides, design notes, milestones).
- `examples/`: Sample scripts for jq and Lua.
- `benchmark/`: Bench scripts, runner, and stored results.
- `knowledge/`: Deep-dive design/architecture notes and plans.
- `vm/`: Early VM experiments (reference material).

## Python Coding Conventions
- Python 3.11+. Use typing and dataclasses where suitable.
- Prefer explicit, descriptive names. Avoid single-letter identifiers.
- Keep modules cohesive. Avoid adding unrelated helpers across layers.
- Raise precise exceptions. For VM/Lua errors, convert `VMRuntimeError` with `haifa_lua.debug.as_lua_error` to preserve Lua-style messages and tracebacks.
- Follow existing patterns for value types and helpers rather than inventing new ones.

## Lua Runtime & Stdlib Conventions
- Stdlib functions live in `haifa_lua/stdlib.py` and are registered via `BuiltinFunction(name, func)`.
- Stdlib function signatures are `func(args: Sequence[Any], vm: BytecodeVM) -> Any`. Validate arguments with `_ensure_*` helpers and return Python values (numbers/booleans/strings), `LuaTable`, `LuaMultiReturn`, or `LuaYield` as appropriate.
- Use `LuaMultiReturn(values)` to return multiple values; printing and `return` sites already understand it.
- Keep error text Lua-style and consistent with existing tests (see `haifa_lua/tests/test_stdlib.py`).
- When adding library members, register them under a dedicated table via `env.register_library("name", members)` and keep names Lua-compatible.

## Coroutines & VM Events
- Coroutines are implemented in `haifa_lua/coroutines.py` and surfaced via stdlib (`create`, `resume`, `yield`).
- Emit coroutine lifecycle events using `base_vm.emit_event(...)` with dataclasses in `compiler/vm_events.py`.
- Keep `CoroutineSnapshot` up to date by calling `set_coroutine_snapshot(...)` and ensure snapshots include `status`, `last_yield`, `last_error`, `function_name`, `last_resume_args`, and runtime state when available.
- If you add new coroutine APIs (e.g., `status`, `wrap`), implement them in stdlib, write tests, and update docs (see Milestone 12 in `docs/lua_sprint.md`).
- If you extend event/snapshot fields, also update:
  - Renderers: `compiler/vm_visualizer.py`, `compiler/vm_visualizer_headless.py`
  - CLI trace formatting in `haifa_lua/cli.py`

## Compiler/VM Integration (Lua)
- Keep the pipeline consistent: `lexer -> parser -> compiler -> BytecodeVM`. Map AST nodes to core opcodes without embedding Lua semantics in the VM when avoidable.
- Use existing opcodes and patterns for closures, upvalues, varargs, and multi-return (see `docs/lua_sprint.md` Milestones 2A/2B).
- Preserve source mapping (`InstructionDebug`) so Lua-style error locations and tracebacks remain useful.

## Testing
- Test runner: `pytest` (configured in `pytest.ini`). Place tests under `haifa_lua/tests/` or `compiler/tests/` as appropriate.
- Prefer black-box tests using `haifa_lua.runtime.run_source` or CLI-level tests only when necessary.
- When extending stdlib or semantics, add unit tests mirroring current style (see `haifa_lua/tests/test_stdlib.py`).
- Use `pytest.raises(LuaRuntimeError)` for Lua-level error assertions and verify message/traceback prefix formats used in existing tests.

## CLI & Debugging
- Lua CLI entry: `pylua` (see `haifa_lua/cli.py`). Support inline execution (`-e/--execute`), script files, `--print-output`, and trace filters (`--trace` with `all` or `coroutine`).
- When changing coroutine events or error surfaces, update CLI trace formatting and maintain backward compatibility of flags and output shapes where possible.

## Documentation
- Roadmap/milestones: `docs/lua_sprint.md`. Reflect feature additions or plan changes here.
- User guide: `docs/lua_guide.md`. Add or adjust examples when APIs change.
- Design/architecture notes: add deep dives to `knowledge/` rather than overloading user docs.

## Benchmarks
- Bench scripts live in `benchmark/scripts/`. Use `benchmark/benchmark_runner.py` to run suites and write results under `benchmark/results/`.
- Do not check in large datasets or external binaries. Keep results small and textual (JSON/Markdown) like existing files.

## Style & Hygiene
- Keep diffs small and isolated. Match surrounding style (imports, error messages, helper usage).
- Do not add license headers to files.
- Avoid introducing new dependencies. The project mainly uses the standard library and `pytest`.
- Update error messages and docs in the same change when modifying user-visible behavior.

## When in Doubt
- Search for similar patterns in the codebase and mirror them (e.g., how `table.*` or `string.*` functions validate and return values).
- If a change touches coroutines or events, run through these checkpoints: event emission, snapshot content, visualizer formatting, CLI trace, tests, docs.

