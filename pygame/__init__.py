"""Lightweight pygame stub for environments without the real dependency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


class error(RuntimeError):
    """Mirror pygame.error for compatibility."""


@dataclass
class _MockSurface:
    width: int

    def get_width(self) -> int:
        return max(1, self.width)

    def blit(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - GUI stub
        return None


class _MockFont:
    def __init__(self, name: str | None, size: int) -> None:
        self.name = name
        self.size = size

    def render(
        self,
        text: str,
        antialias: bool,
        color: Tuple[int, int, int],
        background: Any = None,
    ) -> _MockSurface:
        width = max(1, int(len(text) * max(1, self.size // 2 or 1)))
        return _MockSurface(width)


class font:
    Font = _MockFont

    @staticmethod
    def SysFont(name: str | None, size: int) -> _MockFont:
        return _MockFont(name, size)


class display:
    @staticmethod
    def set_mode(size: Tuple[int, int]):
        return _MockSurface(size[0])

    @staticmethod
    def set_caption(title: str) -> None:
        return None

    @staticmethod
    def update() -> None:
        return None

    @staticmethod
    def flip() -> None:
        return None


class time:
    class Clock:
        def tick(self, fps: int) -> None:
            return None


class event:
    @dataclass
    class Event:
        type: int
        key: int | None = None
        unicode: str = ""

    @staticmethod
    def get():
        return []


class key:
    @staticmethod
    def get_pressed():
        return []


class mouse:
    @staticmethod
    def get_pos():
        return 0, 0


class draw:
    @staticmethod
    def rect(surface: Any, color: Tuple[int, int, int], rect: Tuple[int, int, int, int], **kwargs: Any) -> None:
        return None


def init() -> None:
    return None


def quit() -> None:
    return None


QUIT = 256
KEYDOWN = 768
K_SLASH = ord("/")
K_q = ord("q")
K_SPACE = ord(" ")
K_p = ord("p")
K_f = ord("f")
K_UP = 273
K_DOWN = 274
K_LEFT = 276
K_RIGHT = 275
K_PAGEUP = 266
K_PAGEDOWN = 267
K_HOME = 278
K_END = 279
K_l = ord("l")
K_r = ord("r")
K_RETURN = 13
K_KP_ENTER = 271
K_ESCAPE = 27
K_BACKSPACE = 8
K_DELETE = 127


__all__ = [
    "error",
    "font",
    "display",
    "time",
    "event",
    "key",
    "mouse",
    "draw",
    "init",
    "quit",
    "QUIT",
    "KEYDOWN",
    "K_SLASH",
    "K_q",
    "K_SPACE",
    "K_p",
    "K_f",
    "K_UP",
    "K_DOWN",
    "K_LEFT",
    "K_RIGHT",
    "K_PAGEUP",
    "K_PAGEDOWN",
    "K_HOME",
    "K_END",
    "K_l",
    "K_r",
    "K_RETURN",
    "K_KP_ENTER",
    "K_ESCAPE",
    "K_BACKSPACE",
    "K_DELETE",
]
