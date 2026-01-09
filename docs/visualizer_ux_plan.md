## VM Visualizer UX Plan: Curses Register Change Highlight

### Goal
Make it easier to spot state changes in the curses visualizer by highlighting registers whose values changed on the latest step.

### Scope
- Curses visualizer only (`compiler/vm_visualizer_headless.py`)
- No change to VM semantics or execution behavior
- No new key bindings

### Plan
1. Track previous register snapshots inside the curses visualizer.
2. Compare current vs. previous register values during render.
3. Mark changed registers with a leading `*` and a warning color.
4. Reset the change tracker on VM reset.

### Acceptance Criteria
- Registers that changed since the last draw are visually distinct.
- First render does not highlight every register as "changed."
- Reset clears the change tracking state.
