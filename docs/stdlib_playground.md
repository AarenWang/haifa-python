# Lua Stdlib Playground

Small, focused scripts that exercise the Lua standard library in this repo.
Run them with `pylua` to verify behavior or demo the runtime.

## How to Run

- `pylua examples/stdlib_math.lua --print-output`
- `pylua examples/stdlib_string.lua --print-output`
- `pylua examples/stdlib_table.lua --print-output`

To visualize execution:

- `pylua examples/stdlib_math.lua --visualize`
- `pylua examples/stdlib_string.lua --visualize curses`

## What Each Script Covers

- `examples/stdlib_math.lua`: `math.abs`, `math.floor`, `math.ceil`, `math.min`, `math.max`, `math.deg`
- `examples/stdlib_string.lua`: `string.len`, `string.sub`, `string.find`, `string.gsub`
- `examples/stdlib_table.lua`: `table.insert`, `table.sort`, `table.concat`, `table.remove`, `table.pack`

## Notes

- Output is written via `print` and shown when `--print-output` is used.
- Scripts are intentionally short so they are easy to step through in the visualizers.
