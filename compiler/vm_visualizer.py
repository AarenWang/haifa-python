import datetime
import json
import sys
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

import pygame

try:
    from .bytecode import Instruction
    from .bytecode_vm import BytecodeVM
    from .vm_events import (
        CoroutineCompleted,
        CoroutineCreated,
        CoroutineEvent,
        CoroutineResumed,
        CoroutineSnapshot,
        CoroutineYielded,
        VMStateSnapshot,
    )
except Exception:  # fallback when run as top-level script
    from compiler.bytecode import Instruction  # type: ignore
    from compiler.bytecode_vm import BytecodeVM  # type: ignore
    from compiler.vm_events import (  # type: ignore
        CoroutineCompleted,
        CoroutineCreated,
        CoroutineEvent,
        CoroutineResumed,
        CoroutineSnapshot,
        CoroutineYielded,
        VMStateSnapshot,
    )

# Constants
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900
BACKGROUND_COLOR = (240, 240, 240)
FONT_COLOR = (10, 10, 10)
HIGHLIGHT_COLOR = (255, 255, 0)
PC_COLOR = (200, 255, 200)
CHANGE_COLOR = (255, 220, 200)
SEARCH_HIGHLIGHT_COLOR = (255, 240, 170)
CURRENT_COROUTINE_COLOR = (200, 220, 255)
TIMELINE_COROUTINE_COLOR = (225, 240, 255)
FONT_SIZE = 18
LINE_HEIGHT = 22
MARGIN = 20

class VMVisualizer:
    def __init__(self, vm: BytecodeVM):
        self.vm = vm
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Bytecode VM Visualizer")
        self.font = pygame.font.SysFont("monospace", FONT_SIZE)
        self.clock = pygame.time.Clock()
        self.running = True
        self.paused = True
        self.auto_run = False
        self.prev_registers: Dict[str, Any] = {}
        self.search_mode = False
        self.search_query = ""
        self.message = "Press P to run, SPACE to step, / to search. Use arrows to navigate."
        self.trace_log: List[Dict[str, Any]] = []
        self.event_log: List[str] = []
        self.timeline_events: List[Dict[str, Any]] = []
        self.timeline_start: Optional[float] = None
        self.selected_event_index = -1
        self.selected_coroutine_id: Optional[int] = None
        self.coroutine_selection_index = -1
        self.auto_follow_coroutine = True
        self._latest_coroutines: List[CoroutineSnapshot] = []
        self._coroutine_index_map: Dict[int, int] = {}
        self._latest_snapshot: Optional[VMStateSnapshot] = None
        self._vm_cls = type(vm)
        # Keep a frozen copy of instructions for resetting
        self._instructions = list(vm.instructions)

    def _draw_text(self, text: str, x: int, y: int, color=FONT_COLOR, background=None):
        surface = self.font.render(text, True, color, background)
        self.screen.blit(surface, (x, y))

    def _draw_section(
        self,
        title: str,
        data: List[str],
        x: int,
        y: int,
        width: int,
        height: int,
        highlight_index: int = -1,
        secondary_highlights: Set[int] | None = None,
        secondary_color=SEARCH_HIGHLIGHT_COLOR,
    ) -> None:
        pygame.draw.rect(self.screen, (220, 220, 220), (x, y, width, height), border_radius=5)
        pygame.draw.rect(self.screen, (180, 180, 180), (x, y, width, 30), border_radius=5)
        self._draw_text(title, x + 10, y + 5, color=(50, 50, 50))
        
        start_y = y + 40
        for i, line in enumerate(data):
            line_y = start_y + i * LINE_HEIGHT
            if line_y > y + height - LINE_HEIGHT:
                self._draw_text("...", x + 10, line_y)
                break

            bg = None
            if i == highlight_index:
                bg = PC_COLOR
            elif secondary_highlights and i in secondary_highlights:
                bg = secondary_color
            self._draw_text(line, x + 10, line_y, background=bg)

    def _format_value(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=None)
        except TypeError:
            return str(value)

    def _consume_events(self) -> None:
        events = self.vm.drain_events()
        if not events:
            return

        for event in events:
            label = self._format_event(event)
            timestamp = getattr(event, "timestamp", None)
            entry = {
                "event": event,
                "label": label,
                "timestamp": timestamp,
                "coroutine_id": getattr(event, "coroutine_id", None),
                "type": type(event).__name__,
            }
            self.timeline_events.append(entry)
            self.event_log.append(label)
            if isinstance(event, CoroutineResumed) and self.auto_follow_coroutine:
                self.selected_coroutine_id = event.coroutine_id
            elif (
                isinstance(event, CoroutineCreated)
                and self.selected_coroutine_id is None
            ):
                self.selected_coroutine_id = event.coroutine_id

        if self.timeline_events and self.timeline_start is None:
            first_ts = self.timeline_events[0].get("timestamp")
            if first_ts is not None:
                self.timeline_start = first_ts

        if self.timeline_events:
            self.selected_event_index = len(self.timeline_events) - 1

        max_events = 400
        if len(self.timeline_events) > max_events:
            self.timeline_events = self.timeline_events[-max_events:]
            self.event_log = self.event_log[-max_events:]
            if self.selected_event_index >= 0:
                self.selected_event_index = min(
                    len(self.timeline_events) - 1,
                    self.selected_event_index,
                )
            first_ts = self.timeline_events[0].get("timestamp")
            self.timeline_start = first_ts if first_ts is not None else self.timeline_start

    def _format_event(self, event: CoroutineEvent) -> str:
        if isinstance(event, CoroutineCreated):
            name = event.function_name or "<function>"
            return f"created coroutine #{event.coroutine_id} ({name})"
        if isinstance(event, CoroutineResumed):
            return f"resume coroutine #{event.coroutine_id} args={self._format_value(event.args)}"
        if isinstance(event, CoroutineYielded):
            values = self._format_value(event.values)
            return f"yield from #{event.coroutine_id} values={values} pc={event.pc}"
        if isinstance(event, CoroutineCompleted):
            if event.error:
                return f"coroutine #{event.coroutine_id} error: {event.error}"
            return f"coroutine #{event.coroutine_id} done values={self._format_value(event.values)}"
        return str(event)

    def _compact_value(self, value: Any, limit: int = 36) -> str:
        formatted = self._format_value(value)
        if len(formatted) > limit:
            return formatted[: limit - 3] + "..."
        return formatted

    def _format_timeline_entry(self, entry: Dict[str, Any]) -> str:
        label = entry.get("label", "<event>")
        timestamp = entry.get("timestamp")
        if timestamp is not None:
            if self.timeline_start is None:
                self.timeline_start = timestamp
            delta = timestamp - (self.timeline_start or timestamp)
            return f"+{delta:6.2f}s {label}"
        return f"   --.-s {label}"

    def _format_event_detail(self, entry: Dict[str, Any]) -> List[str]:
        event = entry["event"]
        lines = [f"type: {entry.get('type', '<unknown>')}"]
        coroutine_id = getattr(event, "coroutine_id", None)
        if coroutine_id is not None:
            lines.append(f"coroutine: #{coroutine_id}")
        timestamp = entry.get("timestamp")
        if timestamp is not None:
            iso = datetime.datetime.fromtimestamp(timestamp).isoformat(timespec="milliseconds")
            lines.append(f"time: {iso}")
        if isinstance(event, CoroutineCreated):
            if event.parent_id is not None:
                lines.append(f"parent: #{event.parent_id}")
            if event.function_name:
                lines.append(f"function: {event.function_name}")
            if event.args:
                lines.append(f"args: {self._format_value(list(event.args))}")
        elif isinstance(event, CoroutineResumed):
            lines.append(f"args: {self._format_value(list(event.args))}")
        elif isinstance(event, CoroutineYielded):
            lines.append(f"values: {self._format_value(list(event.values))}")
            lines.append(f"pc: {event.pc}")
        elif isinstance(event, CoroutineCompleted):
            if event.error:
                lines.append(f"error: {event.error}")
            else:
                lines.append(f"values: {self._format_value(list(event.values))}")
        return lines

    def _move_coroutine_selection(self, delta: int) -> None:
        if not self._latest_coroutines:
            return
        index = self.coroutine_selection_index
        if index < 0:
            index = 0 if delta >= 0 else len(self._latest_coroutines) - 1
        new_index = max(0, min(len(self._latest_coroutines) - 1, index + delta))
        if new_index == self.coroutine_selection_index:
            return
        self.coroutine_selection_index = new_index
        snapshot = self._latest_coroutines[new_index]
        self.selected_coroutine_id = snapshot.coroutine_id
        self.message = f"Selected coroutine #{snapshot.coroutine_id}"

    def _move_timeline_selection(self, delta: int) -> None:
        if not self.timeline_events:
            return
        index = self.selected_event_index
        if index < 0:
            index = len(self.timeline_events) - 1
        new_index = max(0, min(len(self.timeline_events) - 1, index + delta))
        if new_index == self.selected_event_index:
            return
        self.selected_event_index = new_index
        entry = self.timeline_events[new_index]
        label = entry.get("label", "<event>")
        coroutine_id = entry.get("coroutine_id")
        if coroutine_id in self._coroutine_index_map:
            self.selected_coroutine_id = coroutine_id
            self.coroutine_selection_index = self._coroutine_index_map[coroutine_id]
        self.message = f"Timeline → {label}"

    def _prepare_data(self):
        instructions_data, highlight_idx, match_highlights = self._prepare_instruction_display()

        snapshot = self.vm.snapshot_state()
        self._latest_snapshot = snapshot
        registers_data, changed_indices = self._prepare_register_display(snapshot.registers)

        self._consume_events()

        coroutine_snapshots = list(snapshot.coroutines)
        self._latest_coroutines = coroutine_snapshots
        self._coroutine_index_map = {
            coro.coroutine_id: idx for idx, coro in enumerate(coroutine_snapshots)
        }

        current_index = self._coroutine_index_map.get(snapshot.current_coroutine, -1)
        if (
            self.selected_coroutine_id is None
            or self.selected_coroutine_id not in self._coroutine_index_map
        ):
            if snapshot.current_coroutine in self._coroutine_index_map:
                self.selected_coroutine_id = snapshot.current_coroutine
            elif coroutine_snapshots:
                self.selected_coroutine_id = coroutine_snapshots[0].coroutine_id
            else:
                self.selected_coroutine_id = None

        selected_index = self._coroutine_index_map.get(self.selected_coroutine_id, -1)
        self.coroutine_selection_index = selected_index

        coroutine_data: List[str] = []
        for idx, coro in enumerate(coroutine_snapshots):
            resume_display = self._compact_value(coro.last_resume_args)
            yield_display = self._compact_value(coro.last_yield)
            name_part = f" fn={coro.function_name}" if coro.function_name else ""
            pc_part = f" pc={coro.current_pc}" if coro.current_pc is not None else ""
            line = (
                f"#{coro.coroutine_id:02d} {coro.status:<10} "
                f"resume={resume_display} yield={yield_display}{pc_part}{name_part}"
            )
            if coro.last_error:
                line += f" error={coro.last_error}"
            coroutine_data.append(line)

        selected_snapshot: Optional[CoroutineSnapshot]
        if selected_index != -1:
            selected_snapshot = coroutine_snapshots[selected_index]
        else:
            selected_snapshot = None

        if selected_snapshot and selected_snapshot.registers is not None:
            coroutine_registers_data = [
                f"{name}: {self._format_value(value)}"
                for name, value in sorted(selected_snapshot.registers.items())
            ]
            if not coroutine_registers_data:
                coroutine_registers_data = ["<empty>"]
        elif selected_snapshot:
            coroutine_registers_data = ["<register snapshot unavailable>"]
        else:
            coroutine_registers_data = ["<no coroutine selected>"]

        if selected_snapshot and selected_snapshot.upvalues is not None:
            coroutine_upvalues_data = [
                f"{idx}: {self._format_value(value)}"
                for idx, value in enumerate(selected_snapshot.upvalues)
            ]
            if not coroutine_upvalues_data:
                coroutine_upvalues_data = ["<empty>"]
        elif selected_snapshot:
            coroutine_upvalues_data = ["<upvalue snapshot unavailable>"]
        else:
            coroutine_upvalues_data = [
                f"{idx}: {self._format_value(value)}"
                for idx, value in enumerate(snapshot.upvalues)
            ] or ["<no upvalues>"]

        if selected_snapshot and selected_snapshot.call_stack:
            coroutine_stack_data = [
                f"{frame.function_name} @ {frame.file}:{frame.line} (pc={frame.pc})"
                for frame in selected_snapshot.call_stack
            ]
        else:
            coroutine_stack_data = [
                f"{frame.function_name} @ {frame.file}:{frame.line} (pc={frame.pc})"
                for frame in snapshot.call_stack
            ]
            if not coroutine_stack_data:
                coroutine_stack_data = ["<no call stack>"]

        emit_stack_data = [self._format_value(item) for item in snapshot.emit_stack]
        if not emit_stack_data:
            emit_stack_data = ["<empty>"]

        output_data = [self._format_value(item) for item in snapshot.output]
        if not output_data:
            output_data = ["<empty>"]

        if self.selected_event_index >= len(self.timeline_events):
            self.selected_event_index = len(self.timeline_events) - 1
        if self.selected_event_index < 0 and self.timeline_events:
            self.selected_event_index = len(self.timeline_events) - 1

        timeline_data = [self._format_timeline_entry(entry) for entry in self.timeline_events]
        timeline_highlight = self.selected_event_index
        timeline_coroutine_indices = {
            idx
            for idx, entry in enumerate(self.timeline_events)
            if entry.get("coroutine_id") == self.selected_coroutine_id
        }

        if 0 <= self.selected_event_index < len(self.timeline_events):
            event_detail_lines = self._format_event_detail(
                self.timeline_events[self.selected_event_index]
            )
        else:
            event_detail_lines = ["<no event selected>"]

        return (
            instructions_data,
            highlight_idx,
            match_highlights,
            registers_data,
            changed_indices,
            coroutine_registers_data,
            coroutine_upvalues_data,
            coroutine_stack_data,
            emit_stack_data,
            output_data,
            coroutine_data,
            selected_index,
            current_index,
            timeline_data,
            timeline_highlight,
            timeline_coroutine_indices,
            event_detail_lines,
        )

    def _prepare_instruction_display(self) -> Tuple[List[str], int, Set[int]]:
        all_instructions = [f"{i:03d}: {str(inst)}" for i, inst in enumerate(self.vm.instructions)]
        indices = list(range(len(all_instructions)))
        match_indices: Set[int] = set()

        if self.search_query:
            query = self.search_query.lower()
            matches = [i for i, text in enumerate(all_instructions) if query in text.lower()]
            if matches:
                indices = matches
                match_indices = set(range(len(indices)))  # temporary placeholder
                # ensure current PC visible
                if self.vm.pc not in matches:
                    indices.append(self.vm.pc)
                    indices = sorted(set(indices))
            else:
                # no matches; keep default but inform user
                self.message = f"No instruction matches for '{self.search_query}'."

        indices = sorted(set(indices))
        instructions_data = [all_instructions[i] for i in indices]

        highlight_idx = -1
        if self.vm.pc in indices:
            highlight_idx = indices.index(self.vm.pc)

        if self.search_query:
            query = self.search_query.lower()
            match_highlights = {
                idx for idx, instr_idx in enumerate(indices) if query in all_instructions[instr_idx].lower()
            }
        else:
            match_highlights = set()

        return instructions_data, highlight_idx, match_highlights

    def _prepare_register_display(self, registers: Mapping[str, Any]) -> Tuple[List[str], Set[int]]:
        registers_data: List[str] = []
        changed_indices: Set[int] = set()
        sorted_items = sorted(registers.items())
        for idx, (reg, val) in enumerate(sorted_items):
            display = self._format_value(val)
            registers_data.append(f"{reg}: {display}")
            prev_val = self.prev_registers.get(reg, None)
            if prev_val != val:
                changed_indices.add(idx)
        return registers_data, changed_indices

    def _draw_ui(self):
        self.screen.fill(BACKGROUND_COLOR)
        
        (
            instructions_data,
            highlight_idx,
            match_highlights,
            registers_data,
            changed_register_indices,
            coroutine_registers_data,
            coroutine_upvalues_data,
            coroutine_stack_data,
            emit_stack_data,
            output_data,
            coroutine_data,
            coroutine_selected_index,
            coroutine_current_index,
            timeline_data,
            timeline_highlight,
            timeline_secondary,
            event_detail_lines,
        ) = self._prepare_data()

        # Instructions
        self._draw_section(
            "Instructions",
            instructions_data,
            MARGIN,
            MARGIN,
            600,
            SCREEN_HEIGHT - 2 * MARGIN,
            highlight_index=highlight_idx,
            secondary_highlights=match_highlights,
            secondary_color=HIGHLIGHT_COLOR,
        )

        # VM Registers
        self._draw_section(
            "VM Registers",
            registers_data,
            640,
            MARGIN,
            450,
            210,
            secondary_highlights=changed_register_indices,
            secondary_color=CHANGE_COLOR,
        )

        # Coroutine-specific panels
        center_x = 640
        center_width = 450
        y = MARGIN + 210 + 20
        self._draw_section(
            "Coroutine Registers",
            coroutine_registers_data,
            center_x,
            y,
            center_width,
            150,
        )

        y += 150 + 20
        self._draw_section(
            "Coroutine Upvalues",
            coroutine_upvalues_data,
            center_x,
            y,
            center_width,
            110,
        )

        y += 110 + 20
        self._draw_section(
            "Coroutine Stack",
            coroutine_stack_data,
            center_x,
            y,
            center_width,
            160,
        )

        y += 160 + 20
        self._draw_section("Emit Stack", emit_stack_data, center_x, y, center_width, 80)

        y += 80 + 20
        output_height = max(60, SCREEN_HEIGHT - y - MARGIN)
        self._draw_section("Output", output_data, center_x, y, center_width, output_height)

        # Coroutines panel on right
        right_x = 1110
        right_width = SCREEN_WIDTH - right_x - MARGIN
        coroutine_height = 260
        coroutine_secondary = set()
        if (
            coroutine_current_index is not None
            and coroutine_current_index >= 0
            and coroutine_current_index != coroutine_selected_index
        ):
            coroutine_secondary.add(coroutine_current_index)
        self._draw_section(
            "Coroutines",
            coroutine_data or ["<none>"],
            right_x,
            MARGIN,
            right_width,
            coroutine_height,
            highlight_index=coroutine_selected_index,
            secondary_highlights=coroutine_secondary,
            secondary_color=CURRENT_COROUTINE_COLOR,
        )

        # Timeline and event detail panels
        events_y = MARGIN + coroutine_height + 20
        timeline_height = 300
        self._draw_section(
            "Timeline",
            timeline_data or ["<no events>"],
            right_x,
            events_y,
            right_width,
            timeline_height,
            highlight_index=timeline_highlight,
            secondary_highlights=timeline_secondary,
            secondary_color=TIMELINE_COROUTINE_COLOR,
        )

        detail_y = events_y + timeline_height + 20
        detail_height = max(120, SCREEN_HEIGHT - detail_y - MARGIN)
        self._draw_section(
            "Event Detail",
            event_detail_lines,
            right_x,
            detail_y,
            right_width,
            detail_height,
        )

        # Status/Help
        status_text = "PAUSED" if self.paused else "RUNNING"
        follow_text = "ON" if self.auto_follow_coroutine else "OFF"
        help_text = (
            "[SPACE] step [P] run/pause [Q] quit [F] follow "
            "[ARROWS] navigate [/] search [L] export"
        )
        msg_y = SCREEN_HEIGHT - MARGIN - 40
        if self.search_mode or self.search_query:
            cursor = "_" if self.search_mode else ""
            self._draw_text(
                f"Search: {self.search_query}{cursor}",
                MARGIN,
                msg_y,
                color=(80, 80, 200),
            )
            msg_y += LINE_HEIGHT
        if self.message:
            self._draw_text(f"Msg: {self.message}", MARGIN, msg_y, color=(100, 100, 100))
            msg_y += LINE_HEIGHT
        self._draw_text(
            f"Status: {status_text} | Auto-follow: {follow_text}",
            MARGIN,
            msg_y,
            color=(100, 100, 100),
        )
        self._draw_text(help_text, MARGIN + 320, msg_y, color=(100, 100, 100))

        pygame.display.flip()
        # Update reference for diff detection after drawing
        if self._latest_snapshot is not None:
            self.prev_registers = dict(self._latest_snapshot.registers)

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if self.search_mode:
                    self._handle_search_key(event)
                    continue
                if event.key == pygame.K_SLASH:
                    self.search_mode = True
                    self.search_query = ""
                    self.message = "Search mode: type to filter instructions, Enter to apply."
                    continue
                if event.key == pygame.K_q:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    self.paused = True
                    self._step_once()
                elif event.key == pygame.K_p:
                    self.paused = not self.paused
                    self.auto_run = not self.paused
                    self.message = "Running..." if not self.paused else "Paused."
                elif event.key == pygame.K_f:
                    self.auto_follow_coroutine = not self.auto_follow_coroutine
                    self.message = (
                        "Auto-follow enabled."
                        if self.auto_follow_coroutine
                        else "Auto-follow disabled."
                    )
                elif event.key == pygame.K_UP:
                    self._move_coroutine_selection(-1)
                elif event.key == pygame.K_DOWN:
                    self._move_coroutine_selection(1)
                elif event.key == pygame.K_LEFT:
                    self._move_timeline_selection(-1)
                elif event.key == pygame.K_RIGHT:
                    self._move_timeline_selection(1)
                elif event.key == pygame.K_l:
                    self._export_trace()
                elif event.key == pygame.K_r:
                    self._reset_vm()

    def run(self):
        self.vm.index_labels()
        while self.running:
            self._handle_events()

            if not self.paused:
                halted = self._step_once()
                if halted:
                    self.auto_run = False

            self._draw_ui()
            self.clock.tick(10) # Limit frame rate

        pygame.quit()
        sys.exit()

    def _step_once(self) -> bool:
        if self.vm.pc >= len(self.vm.instructions):
            self.message = "Program already complete."
            return True

        before_pc = self.vm.pc
        instruction = self.vm.instructions[before_pc]
        control = self.vm.step()
        snapshot = {
            "step": len(self.trace_log),
            "pc": before_pc,
            "instruction": str(instruction),
            "registers": dict(self.vm.registers),
            "output": list(self.vm.output),
        }
        self.trace_log.append(snapshot)

        if control == "halt":
            self.paused = True
            self.message = "Execution halted."
            return True

        return False

    def _handle_search_key(self, event: pygame.event.Event) -> None:
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.search_mode = False
            self.message = f"Search applied: '{self.search_query}'" if self.search_query else "Search cleared."
            return
        if event.key in (pygame.K_ESCAPE, pygame.K_q):
            self.search_mode = False
            self.search_query = ""
            self.message = "Search cancelled."
            return
        if event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            self.search_query = self.search_query[:-1]
            return

        char = event.unicode
        if char and char.isprintable():
            self.search_query += char

    def _export_trace(self) -> None:
        if not self.trace_log:
            self.message = "Trace log is empty; nothing exported."
            return
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"vm_trace_{timestamp}.jsonl"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                for entry in self.trace_log:
                    f.write(json.dumps(entry, ensure_ascii=False))
                    f.write("\n")
            self.message = f"Trace exported to {filename}"
        except Exception as exc:
            self.message = f"Failed to export trace: {exc}"

    def _reset_vm(self) -> None:
        self.vm = self._vm_cls(self._instructions)
        self.vm.index_labels()
        self.paused = True
        self.auto_run = False
        self.prev_registers = {}
        self.trace_log.clear()
        self.timeline_events.clear()
        self.event_log.clear()
        self.timeline_start = None
        self.selected_event_index = -1
        self.selected_coroutine_id = None
        self.coroutine_selection_index = -1
        self._latest_coroutines = []
        self._coroutine_index_map = {}
        self._latest_snapshot = None
        self.message = "VM reset."
