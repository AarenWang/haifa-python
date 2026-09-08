# Lua VM Teaching Demo

This directory contains a static, browser-based walkthrough for Haifa's Lua
VMs. It is designed for beginners who want to connect Lua source code to:

- high-level Haifa BytecodeVM instructions and named registers
- ARMv9 lowering instructions
- `X0`-`X15`, `SP`, `FP`, `LR`, `PC`, `NZCV`
- stack slots, heap objects, globals, and constant pool memory

Open `index.html` directly in a browser. The page uses `demo-data.js`, so it
does not need a local web server.

## ARMv9 Mode

Switch the *VM* dropdown to **Haifa ARMv9** to replay the exact same Lua source
as fixed `X0`-`X15` registers, `SP`/`FP`/`LR`/`PC`, and the `NZCV` flag panel.
The memory panel shows the real `const_pool`, stack slots, heap objects, and
globals recorded from `HaifaArmV9VM` via the debug adapter. Use the bytecode
view side-by-side to see how a high-level Haifa instruction lowers to ARMv9
instructions (`LDR`/`STR` stack traffic, `CMP`/`CSET` flag setting, branches).

The `NZCV` panel renders each flag as `0`/`1` and highlights set flags; it is
only populated in ARMv9 mode.

## Regenerate The Demo Data

From the repository root:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python docs\lua-vm-demo\export_demo.py
```

The exporter compiles each built-in Lua example, steps through the real
`BytecodeVM`, lowers the same bytecode through `compiler.armv9_lowering`, steps
through the real `HaifaArmV9VM`, records snapshots from the ARMv9 debug adapter,
and writes:

- `demo-data.json` for inspection
- `demo-data.js` for direct browser loading

## Files

- `export_demo.py`: records real BytecodeVM and HaifaArmV9VM execution snapshots
- `index.html`: static page shell
- `styles.css`: layout and visual styling
- `app.js`: playback controls and rendering logic
- `demo-data.json` / `demo-data.js`: generated VM trace data
