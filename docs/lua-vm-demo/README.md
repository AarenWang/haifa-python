# Lua Bytecode VM Teaching Demo

This directory contains a static, browser-based walkthrough for Haifa's Lua
bytecode VM. It is designed for beginners who want to connect Lua source code
to VM instructions, registers, call frames, and upvalues.

Open `index.html` directly in a browser. The page uses `demo-data.js`, so it
does not need a local web server.

## Regenerate The Demo Data

From the repository root:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python docs\lua-vm-demo\export_demo.py
```

The exporter compiles each built-in Lua example, steps through the real
`BytecodeVM`, records snapshots, and writes:

- `demo-data.json` for inspection
- `demo-data.js` for direct browser loading

## Files

- `export_demo.py`: records real VM execution snapshots
- `index.html`: static page shell
- `styles.css`: layout and visual styling
- `app.js`: playback controls and rendering logic
- `demo-data.json` / `demo-data.js`: generated VM trace data
