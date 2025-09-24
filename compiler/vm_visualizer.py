import datetime
import json
import sys
from typing import Any, Dict, List, Sequence, Set, Tuple

import pygame

try:
    from .bytecode import Instruction
    from .bytecode_vm import BytecodeVM
    from .vm_events import (
        CoroutineCompleted,
        CoroutineCreated,
        CoroutineEvent,
        CoroutineResumed,
        CoroutineYielded,
    )
except Exception:  # fallback when run as top-level script
    from compiler.bytecode import Instruction  # type: ignore
    from compiler.bytecode_vm import BytecodeVM  # type: ignore
    from compiler.vm_events import (  # type: ignore
        CoroutineCompleted,
        CoroutineCreated,
        CoroutineEvent,
        CoroutineResumed,
        CoroutineYielded,
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
        self.message = "Press P to run, SPACE to step, / to search."
        self.trace_log: List[Dict[str, Any]] = []
        self.event_log: List[str] = []
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

    def _stack_summary(self, stack: Sequence["TraceFrame"]) -> str:
        if not stack:
            return "∅"
        top = stack[0]
        return f"{top.function_name}@{top.file}:{top.line}"

    def _consume_events(self) -> None:
        events = self.vm.drain_events()
        for event in events:
            self.event_log.append(self._format_event(event))
        if len(self.event_log) > 200:
            self.event_log = self.event_log[-200:]

    def _format_event(self, event: CoroutineEvent) -> str:
        if isinstance(event, CoroutineCreated):
            name = event.function_name or "<function>"
            parent = f" parent={event.parent_id}" if event.parent_id is not None else ""
            stack = self._stack_summary(event.stack)
            payload = ""
            if event.upvalues:
                payload = f" upvalues={self._format_value(list(event.upvalues))}"
            return (
                f"created coroutine #{event.coroutine_id} ({name})"
                f" pc={event.pc}{parent} stack={stack}{payload}"
            )
        if isinstance(event, CoroutineResumed):
            scheduler_stack = self._stack_summary(event.stack)
            target = (
                f" next_pc={event.coroutine_pc}" if event.coroutine_pc is not None else ""
            )
            target_stack = (
                f" target={self._stack_summary(event.coroutine_stack)}"
                if event.coroutine_stack
                else ""
            )
            return (
                f"resume coroutine #{event.coroutine_id} "
                f"args={self._format_value(list(event.args))} "
                f"pc={event.pc} stack={scheduler_stack}{target}{target_stack}"
            )
        if isinstance(event, CoroutineYielded):
            values = self._format_value(list(event.values))
            stack = self._stack_summary(event.stack)
            return (
                f"yield from #{event.coroutine_id} values={values} "
                f"pc={event.pc} stack={stack}"
            )
        if isinstance(event, CoroutineCompleted):
            stack = self._stack_summary(event.stack)
            if event.error:
                return (
                    f"coroutine #{event.coroutine_id} error: {event.error} "
                    f"pc={event.pc} stack={stack}"
                )
            return (
                f"coroutine #{event.coroutine_id} done "
                f"values={self._format_value(list(event.values))} "
                f"pc={event.pc} stack={stack}"
            )
        return str(event)

    def _prepare_data(self):
        instructions_data, highlight_idx, match_highlights = self._prepare_instruction_display()

        registers_data, changed_indices = self._prepare_register_display()

        snapshot = self.vm.snapshot_state()
        stack_data = [
            f"{frame.function_name} @ {frame.file}:{frame.line} (pc={frame.pc})"
            for frame in snapshot.call_stack
        ]

        coroutine_data: List[str] = []
        current_index = -1
        for idx, coro in enumerate(snapshot.coroutines):
            status = coro.status
            yield_display = self._format_value(coro.last_yield)
            resume_display = self._format_value(coro.last_resume)
            stack_depth = len(coro.call_stack)
            stack_summary = self._stack_summary(coro.call_stack)
            line = (
                f"#{coro.coroutine_id} {status:<10} "
                f"resume={resume_display} yield={yield_display} "
                f"stack[{stack_depth}]={stack_summary}"
            )
            if coro.last_error:
                line += f" error={coro.last_error}"
            coroutine_data.append(line)
            if snapshot.current_coroutine == coro.coroutine_id:
                current_index = idx

        self._consume_events()

        output_data = [self._format_value(item) for item in self.vm.output]

        emit_stack_data = [str(s) for s in self.vm.emit_stack]

        return (
            instructions_data,
            highlight_idx,
            match_highlights,
            registers_data,
            changed_indices,
            stack_data,
            output_data,
            emit_stack_data,
            coroutine_data,
            current_index,
            list(self.event_log[-30:]),
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

    def _prepare_register_display(self) -> Tuple[List[str], Set[int]]:
        registers_data: List[str] = []
        changed_indices: Set[int] = set()
        sorted_items = sorted(self.vm.registers.items())
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
            stack_data,
            output_data,
            emit_stack_data,
            coroutine_data,
            coroutine_highlight,
            event_log,
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

        # Registers
        self._draw_section(
            "Registers",
            registers_data,
            640,
            MARGIN,
            450,
            400,
            secondary_highlights=changed_register_indices,
            secondary_color=CHANGE_COLOR,
        )

        # Call Stack
        self._draw_section("Call Stack", stack_data, 640, 440, 450, 200)

        # Emit Stack
        emit_y = 660
        emit_height = 120
        self._draw_section("Emit Stack", emit_stack_data, 640, emit_y, 450, emit_height)

        # Output below emit stack
        output_y = emit_y + emit_height + 20
        output_height = SCREEN_HEIGHT - output_y - MARGIN
        self._draw_section("Output", output_data, 640, output_y, 450, output_height)

        # Coroutines panel on right
        right_x = 1110
        right_width = SCREEN_WIDTH - right_x - MARGIN
        coroutine_height = 240
        self._draw_section(
            "Coroutines",
            coroutine_data or ["<none>"],
            right_x,
            MARGIN,
            right_width,
            coroutine_height,
            highlight_index=coroutine_highlight,
        )

        # Coroutine events below
        events_y = MARGIN + coroutine_height + 20
        events_height = SCREEN_HEIGHT - events_y - MARGIN
        self._draw_section(
            "Coroutine Events",
            list(reversed(event_log)) or ["<no events>"],
            right_x,
            events_y,
            right_width,
            events_height,
        )

        # Status/Help
        status_text = "PAUSED" if self.paused else "RUNNING"
        help_text = "[SPACE] to step, [P] to toggle pause/run, [Q] to quit"
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
        self._draw_text(f"Status: {status_text}", MARGIN, msg_y, color=(100, 100, 100))
        self._draw_text(help_text + " | [/ ] search, [L] export trace", MARGIN + 220, msg_y, color=(100, 100, 100))

        pygame.display.flip()
        # Update reference for diff detection after drawing
        self.prev_registers = dict(self.vm.registers)

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
        self.message = "VM reset."
