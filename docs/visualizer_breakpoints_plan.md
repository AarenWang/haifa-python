## VM Visualizer Plan: Breakpoints

### Goal
Allow users to pause execution at specific instruction indices in both the GUI and curses visualizers.

### Scope
- GUI visualizer (`compiler/vm_visualizer.py`)
- Curses visualizer (`compiler/vm_visualizer_headless.py`)
- No VM/bytecode changes

### UX Decisions
- Toggle breakpoint at the current PC using `b`.
- Auto-run pauses before executing a breakpointed instruction.
- Breakpoints are indicated inline in the instruction list with a `B` marker.

### Implementation Steps
1. Track breakpoint indices in each visualizer instance.
2. Add key handling to toggle the breakpoint at the current PC.
3. When auto-running, pause if the current PC is a breakpoint.
4. Render instruction rows with a `B` marker for breakpoints.

### Acceptance Criteria
- Breakpoints can be set/cleared with `b`.
- Auto-run halts at a breakpoint before executing it.
- Breakpoints are visible in the instruction list.
