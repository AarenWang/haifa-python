## VM Visualizer Plan: Watch List

### Goal
Allow users to track selected registers in both visualizers without scanning the full register list.

### Scope
- GUI visualizer (`compiler/vm_visualizer.py`)
- Curses visualizer (`compiler/vm_visualizer_headless.py`)
- No VM/bytecode changes

### UX Decisions
- Toggle watch by register name.
- GUI: press `w`, type name, Enter to toggle.
- Curses: press `w`, type name, Enter to toggle.
- Watch list is rendered in its own panel/section and shows `<missing>` when a name is not present.

### Implementation Steps
1. Store watched register names in each visualizer.
2. Add watch-input handling and messages.
3. Render a watch panel/section with current values.
4. Update help text to include the watch hotkey.

### Acceptance Criteria
- Watch toggles by name via `w` in both visualizers.
- Watched registers are visible with current values.
- Missing register names are shown as `<missing>` without crashing.
