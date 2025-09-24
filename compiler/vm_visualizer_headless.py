from __future__ import annotations

import curses
import datetime
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

try:
    from .bytecode_vm import BytecodeVM, Instruction
    from .vm_events import (
        CoroutineCompleted,
        CoroutineCreated,
        CoroutineEvent,
        CoroutineResumed,
        CoroutineYielded,
    )
except Exception:  # pragma: no cover - fallback when run as script bundle
    from compiler.bytecode_vm import BytecodeVM, Instruction  # type: ignore
    from compiler.vm_events import (  # type: ignore
        CoroutineCompleted,
        CoroutineCreated,
        CoroutineEvent,
        CoroutineResumed,
        CoroutineYielded,
    )

try:
    from haifa_lua.environment import LuaEnvironment  # type: ignore
    from haifa_lua.stdlib import create_default_environment  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    LuaEnvironment = None  # type: ignore
    create_default_environment = None  # type: ignore


@dataclass
class _VMState:
    vm: BytecodeVM
    step: int = 0
    halted: bool = False


class VMVisualizer:
    """Curses-based headless visualizer for BytecodeVM/JQVM.

    Controls:
      - SPACE / p : toggle auto-run
      - n / →     : single-step
      - r         : reset VM state
      - e         : toggle coroutine event log visibility
      - q         : quit

    Designed for environments without pygame but with a terminal.
    """

    def __init__(self, vm: BytecodeVM, max_steps: Optional[int] = None):
        self._vm_cls = type(vm)
        self._program: List[Instruction] = list(vm.instructions)
        self.state = _VMState(vm=vm)
        (
            self._initial_env_snapshot,
            self._initial_global_registers,
        ) = self._ensure_vm_environment(self.state.vm)
        self.max_steps = max_steps
        self.auto_run = False
        self.message = "Press SPACE to run/pause, n to step, q to quit."
        self.state.vm.index_labels()
        self.event_log: List[str] = []
        self._event_entries: List[dict[str, Any]] = []
        self.show_events = True

    # ---------------------------- public API ----------------------------- #
    def run(self) -> None:  # pragma: no cover - interactive utility
        curses.wrapper(self._main)

    # --------------------------- internal helpers ------------------------ #
    def _main(self, stdscr: "curses._CursesWindow") -> None:
        curses.curs_set(0)
        stdscr.nodelay(False)
        while True:
            self._draw(stdscr)
            stdscr.timeout(120 if (self.auto_run and not self.state.halted) else -1)
            key = stdscr.getch()
            if key == -1:
                if self.auto_run and not self.state.halted:
                    self._advance(auto=True)
                continue

            if key in (ord("q"), ord("Q")):
                break
            if key in (ord(" "), ord("p"), ord("P")):
                if self.state.halted:
                    self.message = "Program halted. Press r to reset or q to quit."
                else:
                    self.auto_run = not self.auto_run
                    self.message = "Running..." if self.auto_run else "Paused."
                continue
            if key in (ord("n"), curses.KEY_RIGHT):
                self._advance(auto=False)
                continue
            if key in (ord("r"), ord("R")):
                self._reset()
                continue
            if key in (ord("e"), ord("E")):
                self.show_events = not self.show_events
                self.message = "Events visible." if self.show_events else "Events hidden."
                continue
            # Unhandled keys update message briefly
            if key != -1:
                self.message = f"Unhandled key: {key}."

    def _advance(self, auto: bool) -> None:
        if self.state.halted:
            self.auto_run = False
            return
        if self.max_steps is not None and self.state.step >= self.max_steps:
            self.auto_run = False
            self.message = "Reached max steps; press r to reset or q to quit."
            return

        control = self.state.vm.step()
        self.state.step += 1

        if control == "halt" or self.state.vm.pc >= len(self._program):
            self.state.halted = True
            self.auto_run = False
            self.message = "Halted. Press r to reset or q to quit."
        elif auto:
            self.message = "Running..."

    def _consume_events(self) -> None:
        events = self.state.vm.drain_events()
        for event in events:
            label = self._format_event(event)
            self.event_log.append(label)
            self._event_entries.append(
                {
                    "event": event,
                    "label": label,
                    "timestamp": getattr(event, "timestamp", None),
                }
            )
        if len(self.event_log) > 200:
            self.event_log = self.event_log[-200:]
            self._event_entries = self._event_entries[-200:]

    def _format_event(self, event: CoroutineEvent) -> str:
        if isinstance(event, CoroutineCreated):
            name = event.function_name or "<function>"
            args = self._fmt(list(event.args)) if event.args else "[]"
            return f"created #{event.coroutine_id} ({name}) args={args}"
        if isinstance(event, CoroutineResumed):
            return f"resume #{event.coroutine_id} args={self._fmt(list(event.args))}"
        if isinstance(event, CoroutineYielded):
            return f"yield #{event.coroutine_id} values={self._fmt(list(event.values))} pc={event.pc}"
        if isinstance(event, CoroutineCompleted):
            if event.error:
                return f"#{event.coroutine_id} error: {event.error}"
            return f"#{event.coroutine_id} completed values={self._fmt(list(event.values))}"
        return str(event)

    def _reset(self) -> None:
        self.state = _VMState(vm=self._vm_cls(self._program))
        self._apply_initial_environment(self.state.vm)
        self.state.vm.index_labels()
        self.auto_run = False
        self.message = "Reset. Press SPACE to run or n to step."
        self.event_log.clear()
        self._event_entries.clear()

    def _ensure_vm_environment(
        self, vm: BytecodeVM
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        def has_globals(registers: Mapping[str, Any]) -> bool:
            return any(name.startswith("G_") for name in registers)

        env = getattr(vm, "lua_env", None)

        if env is not None and LuaEnvironment is not None:
            try:
                env.sync_from_vm(vm.registers)
            except AttributeError:
                pass
            if not has_globals(vm.registers):
                try:
                    vm.registers.update(env.to_vm_registers())
                except AttributeError:
                    pass
            snapshot = env.snapshot() if hasattr(env, "snapshot") else None
            globals_map = (
                env.to_vm_registers() if hasattr(env, "to_vm_registers") else {}
            )
            return (snapshot if snapshot else None, dict(globals_map))

        if env is None and has_globals(vm.registers) and LuaEnvironment is not None:
            try:
                env = LuaEnvironment()
                env.sync_from_vm(vm.registers)
                vm.lua_env = env
                snapshot = env.snapshot()
                globals_map = env.to_vm_registers()
                return (snapshot if snapshot else None, dict(globals_map))
            except Exception:
                pass

        if env is None and not has_globals(vm.registers) and create_default_environment:
            try:
                env = create_default_environment()
                vm.lua_env = env
                globals_map = env.to_vm_registers()
                vm.registers.update(globals_map)
                snapshot = env.snapshot()
                return (snapshot if snapshot else None, dict(globals_map))
            except Exception:
                pass

        globals_map = {
            name: value for name, value in vm.registers.items() if name.startswith("G_")
        }
        if env is None and not globals_map and create_default_environment:
            try:
                env = create_default_environment()
                globals_map = env.to_vm_registers()
                vm.registers.update(globals_map)
                vm.lua_env = env
                snapshot = env.snapshot()
                return (snapshot if snapshot else None, dict(globals_map))
            except Exception:
                pass

        return (None, dict(globals_map))

    def _apply_initial_environment(self, vm: BytecodeVM) -> None:
        if self._initial_env_snapshot and LuaEnvironment is not None:
            try:
                env = LuaEnvironment(self._initial_env_snapshot)
                vm.lua_env = env
                vm.registers.update(env.to_vm_registers())
                return
            except Exception:
                pass
        if self._initial_global_registers:
            vm.registers.update(self._initial_global_registers)


    def _draw(self, stdscr: "curses._CursesWindow") -> None:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        self._write(stdscr, 0, 0, "Bytecode Instructions (SPACE: run/pause, n: step, r: reset, q: quit)")

        inst_view_height = min(10, max(1, height - 10))
        if self._program:
            pc_index = min(self.state.vm.pc, len(self._program) - 1)
        else:
            pc_index = 0
        if self.state.halted:
            cursor_index = pc_index
        else:
            cursor_index = self.state.vm.pc if self.state.vm.pc < len(self._program) else pc_index
        start = max(0, pc_index - inst_view_height // 2)
        end = min(len(self._program), start + inst_view_height)
        row = 2
        if self._program:
            for idx in range(start, end):
                is_cursor = idx == cursor_index
                prefix = "→" if is_cursor else " "
                line = f"{prefix}{idx:03d} {self._program[idx]}"
                attr = curses.A_REVERSE if is_cursor else curses.A_NORMAL
                self._write(stdscr, row, 0, line, attr)
                row += 1
        else:
            self._write(stdscr, row, 0, "<no instructions>")
            row += 1

        row += 1
        self._write(stdscr, row, 0, f"Step: {self.state.step} | PC: {self.state.vm.pc} | Auto: {self.auto_run} | Halted: {self.state.halted}")

        snapshot = self.state.vm.snapshot_state()
        self._consume_events()

        row += 2
        self._write(stdscr, row, 0, "Registers:")
        for i, (name, value) in enumerate(sorted(snapshot.registers.items())):
            display = self._fmt(value)
            self._write(stdscr, row + 1 + i, 2, f"{name} = {display}")

        row = min(height - 6, row + 3 + len(snapshot.registers))
        self._write(stdscr, row, 0, "Call stack:")
        for i, frame in enumerate(snapshot.call_stack):
            self._write(
                stdscr,
                row + 1 + i,
                2,
                f"{frame.function_name} @ {frame.file}:{frame.line} (pc={frame.pc})",
            )

        row = min(height - 6, row + 3 + len(snapshot.call_stack))
        self._write(stdscr, row, 0, "Upvalues:")
        upvalue_repr = ", ".join(self._fmt(value) for value in snapshot.upvalues)
        self._write(stdscr, row + 1, 2, upvalue_repr or "<empty>")

        row = min(height - 6, row + 3)
        self._write(stdscr, row, 0, "Coroutines:")
        if snapshot.coroutines:
            for i, coro in enumerate(snapshot.coroutines):
                prefix = "*" if snapshot.current_coroutine == coro.coroutine_id else "-"
                resume_text = self._fmt(coro.last_resume_args)
                yield_text = self._fmt(coro.last_yield)
                name_text = f" fn={coro.function_name}" if coro.function_name else ""
                pc_text = f" pc={coro.current_pc}" if getattr(coro, "current_pc", None) is not None else ""
                line = (
                    f"{prefix} #{coro.coroutine_id} {coro.status} "
                    f"resume={resume_text} yield={yield_text}{pc_text}{name_text}"
                )
                if coro.last_error:
                    line += f" error={coro.last_error}"
                self._write(stdscr, row + 1 + i, 2, line)
            row += 1 + len(snapshot.coroutines)
        else:
            self._write(stdscr, row + 1, 2, "<none>")
            row += 2

        if self.show_events:
            recent_events = list(reversed(self.event_log[-5:]))
            self._write(stdscr, row, 40, "Events:")
            for i, line in enumerate(recent_events):
                self._write(stdscr, row + 1 + i, 42, line)
            events_block = 1 + len(recent_events) + 1
        else:
            self._write(stdscr, row, 40, "Events: <hidden>")
            events_block = 2

        detail_lines = self._event_detail_lines()
        for i, text in enumerate(detail_lines):
            if row + events_block + i < height - 4:
                self._write(stdscr, row + events_block + i, 40, text)

        row = min(height - 6, row + events_block + len(detail_lines))
        self._write(stdscr, row, 0, "Emit stack:")
        emit_repr = ", ".join(self._fmt(e) for e in snapshot.emit_stack)
        self._write(stdscr, row + 1, 2, emit_repr or "<empty>")

        row += 3
        self._write(stdscr, row, 0, "Output:")
        output_repr = ", ".join(self._fmt(o) for o in snapshot.output)
        self._write(stdscr, row + 1, 2, output_repr or "<empty>")

        self._write(stdscr, height - 2, 0, self.message[: width - 1])
        stdscr.refresh()

    def _event_detail_lines(self) -> List[str]:
        if not self._event_entries:
            return []
        entry = self._event_entries[-1]
        event = entry["event"]
        lines = [f"Last event: {entry['label']}"]
        timestamp = entry.get("timestamp")
        if timestamp is not None:
            iso = datetime.datetime.fromtimestamp(timestamp).isoformat(timespec="milliseconds")
            lines.append(f"  time={iso}")
        if isinstance(event, CoroutineCreated):
            if event.parent_id is not None:
                lines.append(f"  parent=#{event.parent_id}")
            if event.function_name:
                lines.append(f"  function={event.function_name}")
            if event.args:
                lines.append(f"  args={self._fmt(list(event.args))}")
        elif isinstance(event, CoroutineResumed):
            lines.append(f"  args={self._fmt(list(event.args))}")
        elif isinstance(event, CoroutineYielded):
            lines.append(f"  values={self._fmt(list(event.values))}")
            lines.append(f"  pc={event.pc}")
        elif isinstance(event, CoroutineCompleted):
            if event.error:
                lines.append(f"  error={event.error}")
            else:
                lines.append(f"  values={self._fmt(list(event.values))}")
        return lines

    def _write(self, stdscr: "curses._CursesWindow", y: int, x: int, text: str, attr: int = curses.A_NORMAL) -> None:
        height, width = stdscr.getmaxyx()
        if 0 <= y < height:
            try:
                stdscr.addnstr(y, x, text, max(0, width - x - 1), attr)
            except curses.error:
                pass

    def _fmt(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
