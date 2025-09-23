import pygame
import sys
import json
from typing import List, Dict, Any

try:
    from .bytecode import Instruction
    from .bytecode_vm import BytecodeVM
except Exception:  # fallback when run as top-level script
    from compiler.bytecode import Instruction  # type: ignore
    from compiler.bytecode_vm import BytecodeVM  # type: ignore

# Constants
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900
BACKGROUND_COLOR = (240, 240, 240)
FONT_COLOR = (10, 10, 10)
HIGHLIGHT_COLOR = (255, 255, 0)
PC_COLOR = (200, 255, 200)
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

    def _draw_text(self, text: str, x: int, y: int, color=FONT_COLOR, background=None):
        surface = self.font.render(text, True, color, background)
        self.screen.blit(surface, (x, y))

    def _draw_section(self, title: str, data: List[str], x: int, y: int, width: int, height: int, highlight_index: int = -1):
        pygame.draw.rect(self.screen, (220, 220, 220), (x, y, width, height), border_radius=5)
        pygame.draw.rect(self.screen, (180, 180, 180), (x, y, width, 30), border_radius=5)
        self._draw_text(title, x + 10, y + 5, color=(50, 50, 50))
        
        start_y = y + 40
        for i, line in enumerate(data):
            line_y = start_y + i * LINE_HEIGHT
            if line_y > y + height - LINE_HEIGHT:
                self._draw_text("...", x + 10, line_y)
                break

            bg = PC_COLOR if i == highlight_index else None
            self._draw_text(line, x + 10, line_y, background=bg)

    def _format_value(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=None)
        except TypeError:
            return str(value)

    def _prepare_data(self):
        instructions_data = [f"{i:03d}: {str(inst)}" for i, inst in enumerate(self.vm.instructions)]
        
        registers_data = [f"{reg}: {self._format_value(val)}" for reg, val in sorted(self.vm.registers.items())]
        
        stack_data = [f"PC={pc}, Params={params}, Regs=..." for pc, params, _ in self.vm.call_stack]
        
        output_data = [self._format_value(item) for item in self.vm.output]

        emit_stack_data = [str(s) for s in self.vm.emit_stack]

        return instructions_data, registers_data, stack_data, output_data, emit_stack_data

    def _draw_ui(self):
        self.screen.fill(BACKGROUND_COLOR)
        
        instructions_data, registers_data, stack_data, output_data, emit_stack_data = self._prepare_data()

        # Instructions
        self._draw_section("Instructions (PC)", instructions_data, MARGIN, MARGIN, 600, SCREEN_HEIGHT - 2 * MARGIN, self.vm.pc)

        # Registers
        self._draw_section("Registers", registers_data, 640, MARGIN, 450, 400)

        # Call Stack
        self._draw_section("Call Stack", stack_data, 640, 440, 450, 200)

        # Emit Stack
        self._draw_section("Emit Stack", emit_stack_data, 640, 660, 450, SCREEN_HEIGHT - 660 - MARGIN)

        # Output
        self._draw_section("Output", output_data, 1110, MARGIN, SCREEN_WIDTH - 1110 - MARGIN, SCREEN_HEIGHT - 2 * MARGIN)

        # Status/Help
        status_text = "PAUSED" if self.paused else "RUNNING"
        help_text = "[SPACE] to step, [P] to toggle pause/run, [Q] to quit"
        self._draw_text(f"Status: {status_text}", MARGIN, SCREEN_HEIGHT - MARGIN, color=(100, 100, 100))
        self._draw_text(help_text, 200, SCREEN_HEIGHT - MARGIN, color=(100, 100, 100))

        pygame.display.flip()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    self.running = False
                if event.key == pygame.K_SPACE:
                    self.paused = True
                    if self.vm.step() == "halt":
                        print("Execution halted.")
                if event.key == pygame.K_p:
                    self.paused = not self.paused

    def run(self):
        self.vm.index_labels()
        while self.running:
            self._handle_events()

            if not self.paused:
                if self.vm.step() == "halt":
                    self.paused = True
                    print("Execution halted.")

            self._draw_ui()
            self.clock.tick(10) # Limit frame rate

        pygame.quit()
        sys.exit()
