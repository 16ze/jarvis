"""
Bridge hand gestures from the frontend MediaPipe tracker to OS input.

The frontend owns camera access and hand landmark detection. This module only
receives normalized gesture events and performs small, bounded OS actions:
mouse move, click, drag, scroll, and window switching shortcuts.
"""

from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass
from typing import Any


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _screen_bounds() -> tuple[int, int, int, int]:
    """Return the full virtual desktop bounds: left, top, width, height."""
    if platform.system() == "Darwin":
        try:
            out = subprocess.run(
                ["osascript", "-e", 'tell application "Finder" to get bounds of window of desktop'],
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout.strip()
            parts = [p.strip() for p in out.split(",")]
            left, top, right, bottom = (int(part) for part in parts[:4])
            return left, top, right - left, bottom - top
        except Exception:
            pass
    return 0, 0, 1440, 900


@dataclass
class HandGestureOsStatus:
    enabled: bool
    ok: bool
    message: str


class HandGestureOsController:
    def __init__(self) -> None:
        self.enabled = False
        self._mouse = None
        self._button = None
        self._keyboard = None
        self._key = None
        self._ready_error = ""
        self._screen_left, self._screen_top, self._screen_w, self._screen_h = _screen_bounds()
        self._last_click_at = 0.0
        self._last_nav_at = 0.0
        self._last_event_at = 0.0
        self._last_debug_at = 0.0
        self._smoothed_x: float | None = None
        self._smoothed_y: float | None = None
        self._mouse_is_down = False
        self._grabbed_window: Any | None = None
        self._grabbed_window_pos: tuple[float, float] | None = None
        self._grab_pointer_pos: tuple[int, int] | None = None
        self._last_pointer_pos: tuple[int, int] | None = None
        self._warned_ax_unavailable = False

    def _ensure_input(self) -> bool:
        if self._mouse and self._keyboard:
            return True
        try:
            from pynput import keyboard, mouse

            self._mouse = mouse.Controller()
            self._button = mouse.Button
            self._keyboard = keyboard.Controller()
            self._key = keyboard.Key
            return True
        except Exception as exc:
            self._ready_error = str(exc)
            return False

    def set_enabled(self, enabled: bool) -> HandGestureOsStatus:
        if enabled and not self._ensure_input():
            self.enabled = False
            return HandGestureOsStatus(
                enabled=False,
                ok=False,
                message=(
                    "Hand OS control unavailable. Install/enable pynput and grant "
                    "Accessibility permissions to the Python/Electron process."
                ),
            )

        self.enabled = enabled
        self._screen_left, self._screen_top, self._screen_w, self._screen_h = _screen_bounds()
        print(
            "[HandOS] desktop bounds="
            f"left:{self._screen_left} top:{self._screen_top} "
            f"width:{self._screen_w} height:{self._screen_h}"
        )
        self._smoothed_x = None
        self._smoothed_y = None
        self._release_grabbed_window()
        if not enabled and self._mouse_is_down and self._mouse:
            self._mouse.release(self._button.left)
            self._mouse_is_down = False
        return HandGestureOsStatus(
            enabled=self.enabled,
            ok=True,
            message="Hand OS control enabled" if enabled else "Hand OS control disabled",
        )

    def handle_event(self, data: dict[str, Any]) -> None:
        if not self.enabled or not self._ensure_input():
            return

        now = time.monotonic()
        event_type = str(data.get("type", "move"))
        if event_type == "move":
            if now - self._last_event_at < 0.025:
                return
            self._last_event_at = now

        if now - self._last_debug_at > 1.0:
            self._last_debug_at = now
            print(f"[HandOS] event={event_type} data={data}")
        if event_type == "move":
            self._move_pointer(data)
        elif event_type == "click":
            self._click()
        elif event_type == "mouse_down":
            self._mouse_down()
        elif event_type == "mouse_up":
            self._mouse_up()
        elif event_type == "scroll":
            self._scroll(data)
        elif event_type == "window_switch":
            self._switch_window(str(data.get("direction", "next")))
        elif event_type == "nav":
            self._navigate(str(data.get("direction", "")))

    def _move_pointer(self, data: dict[str, Any]) -> None:
        x = _clamp(float(data.get("x", 0.5)), 0.0, 1.0)
        y = _clamp(float(data.get("y", 0.5)), 0.0, 1.0)
        target_x = int(self._screen_left + x * self._screen_w)
        target_y = int(self._screen_top + y * self._screen_h)
        self._last_pointer_pos = (target_x, target_y)

        if self._smoothed_x is None or self._smoothed_y is None:
            self._smoothed_x = target_x
            self._smoothed_y = target_y
        else:
            smoothing = 0.35
            self._smoothed_x += (target_x - self._smoothed_x) * smoothing
            self._smoothed_y += (target_y - self._smoothed_y) * smoothing

        self._mouse.position = (int(self._smoothed_x), int(self._smoothed_y))
        self._move_grabbed_window(target_x, target_y)

    def _click(self) -> None:
        now = time.monotonic()
        if now - self._last_click_at < 0.45:
            return
        self._last_click_at = now
        self._release_grabbed_window()
        if self._mouse_is_down:
            self._mouse.release(self._button.left)
            self._mouse_is_down = False
        self._mouse.click(self._button.left, 1)

    def _mouse_down(self) -> None:
        if self._start_window_grab():
            return
        if not self._mouse_is_down:
            self._mouse.press(self._button.left)
            self._mouse_is_down = True

    def _mouse_up(self) -> None:
        self._release_grabbed_window()
        if self._mouse_is_down:
            self._mouse.release(self._button.left)
            self._mouse_is_down = False

    def _scroll(self, data: dict[str, Any]) -> None:
        amount = int(_clamp(float(data.get("dy", 0.0)), -8.0, 8.0))
        if amount:
            self._mouse.scroll(0, amount)

    def _navigate(self, direction: str) -> None:
        now = time.monotonic()
        if now - self._last_nav_at < 1.0:
            return
        self._last_nav_at = now

        if direction == "back":
            self._hotkey("left")
        elif direction == "forward":
            self._hotkey("right")

    def _hotkey(self, arrow: str) -> None:
        modifier = self._key.cmd if platform.system() == "Darwin" else self._key.alt
        key = self._key.left if arrow == "left" else self._key.right
        with self._keyboard.pressed(modifier):
            self._keyboard.press(key)
            self._keyboard.release(key)

    def _switch_window(self, direction: str) -> None:
        now = time.monotonic()
        if now - self._last_nav_at < 0.9:
            return
        self._last_nav_at = now

        if self._mouse_is_down:
            self._mouse.release(self._button.left)
            self._mouse_is_down = False
        self._release_grabbed_window()

        if platform.system() == "Darwin":
            modifier = self._key.cmd
        else:
            modifier = self._key.alt

        with self._keyboard.pressed(modifier):
            if direction == "previous":
                with self._keyboard.pressed(self._key.shift):
                    self._keyboard.press(self._key.tab)
                    self._keyboard.release(self._key.tab)
            else:
                self._keyboard.press(self._key.tab)
                self._keyboard.release(self._key.tab)

    def _start_window_grab(self) -> bool:
        """Grab the visible macOS window under the pointer, not just its title bar."""
        if platform.system() != "Darwin":
            return False

        pointer = self._last_pointer_pos
        if pointer is None and self._mouse:
            pointer = tuple(int(v) for v in self._mouse.position)
        if pointer is None:
            return False

        window = self._window_at_point(*pointer)
        if not window:
            return False

        ax_window = self._ax_window_for_cg_window(window)
        if ax_window is None:
            if not self._warned_ax_unavailable:
                self._warned_ax_unavailable = True
                print(
                    "[HandOS] macOS Accessibility window move unavailable; "
                    "falling back to regular mouse drag."
                )
            return False

        pos = self._ax_get_point(ax_window, "AXPosition")
        if pos is None:
            return False

        self._grabbed_window = ax_window
        self._grabbed_window_pos = pos
        self._grab_pointer_pos = pointer
        return True

    def _release_grabbed_window(self) -> None:
        self._grabbed_window = None
        self._grabbed_window_pos = None
        self._grab_pointer_pos = None

    def _move_grabbed_window(self, pointer_x: int, pointer_y: int) -> None:
        if not self._grabbed_window or not self._grabbed_window_pos or not self._grab_pointer_pos:
            return
        start_x, start_y = self._grab_pointer_pos
        win_x, win_y = self._grabbed_window_pos
        self._ax_set_point(
            self._grabbed_window,
            "AXPosition",
            (win_x + pointer_x - start_x, win_y + pointer_y - start_y),
        )

    def _window_at_point(self, x: int, y: int) -> dict[str, Any] | None:
        try:
            import os
            import Quartz

            options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
            windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
            own_pid = os.getpid()
            for window in windows:
                if int(window.get("kCGWindowLayer", 1)) != 0:
                    continue
                if int(window.get("kCGWindowOwnerPID", -1)) == own_pid:
                    continue
                bounds = window.get("kCGWindowBounds") or {}
                left = float(bounds.get("X", 0))
                top = float(bounds.get("Y", 0))
                width = float(bounds.get("Width", 0))
                height = float(bounds.get("Height", 0))
                if width < 80 or height < 60:
                    continue
                if left <= x <= left + width and top <= y <= top + height:
                    return window
        except Exception as exc:
            if not self._warned_ax_unavailable:
                self._warned_ax_unavailable = True
                print(f"[HandOS] unable to inspect macOS windows: {exc}")
        return None

    def _ax_window_for_cg_window(self, cg_window: dict[str, Any]) -> Any | None:
        try:
            from ApplicationServices import (
                AXIsProcessTrusted,
                AXUIElementCopyAttributeValue,
                AXUIElementCreateApplication,
                kAXWindowsAttribute,
            )

            if not AXIsProcessTrusted():
                return None

            pid = int(cg_window.get("kCGWindowOwnerPID", -1))
            cg_bounds = cg_window.get("kCGWindowBounds") or {}
            cg_title = str(cg_window.get("kCGWindowName") or "")
            app = AXUIElementCreateApplication(pid)
            err, windows = AXUIElementCopyAttributeValue(app, kAXWindowsAttribute, None)
            if err != 0 or not windows:
                return None

            best = None
            best_score = float("inf")
            for ax_window in windows:
                pos = self._ax_get_point(ax_window, "AXPosition")
                size = self._ax_get_size(ax_window, "AXSize")
                if pos is None or size is None:
                    continue

                score = abs(pos[0] - float(cg_bounds.get("X", 0))) + abs(pos[1] - float(cg_bounds.get("Y", 0)))
                score += abs(size[0] - float(cg_bounds.get("Width", 0))) * 0.25
                score += abs(size[1] - float(cg_bounds.get("Height", 0))) * 0.25

                title = self._ax_get_string(ax_window, "AXTitle")
                if cg_title and title and cg_title != title:
                    score += 75

                if score < best_score:
                    best = ax_window
                    best_score = score

            return best if best_score < 180 else None
        except Exception as exc:
            if not self._warned_ax_unavailable:
                self._warned_ax_unavailable = True
                print(f"[HandOS] unable to access macOS window controls: {exc}")
            return None

    def _ax_get_point(self, ax_element: Any, attr: str) -> tuple[float, float] | None:
        try:
            from ApplicationServices import AXUIElementCopyAttributeValue, AXValueGetValue, kAXValueCGPointType

            err, value = AXUIElementCopyAttributeValue(ax_element, attr, None)
            if err != 0 or value is None:
                return None
            ok, point = AXValueGetValue(value, kAXValueCGPointType, None)
            if not ok:
                return None
            return float(point.x), float(point.y)
        except Exception:
            return None

    def _ax_get_size(self, ax_element: Any, attr: str) -> tuple[float, float] | None:
        try:
            from ApplicationServices import AXUIElementCopyAttributeValue, AXValueGetValue, kAXValueCGSizeType

            err, value = AXUIElementCopyAttributeValue(ax_element, attr, None)
            if err != 0 or value is None:
                return None
            ok, size = AXValueGetValue(value, kAXValueCGSizeType, None)
            if not ok:
                return None
            return float(size.width), float(size.height)
        except Exception:
            return None

    def _ax_get_string(self, ax_element: Any, attr: str) -> str | None:
        try:
            from ApplicationServices import AXUIElementCopyAttributeValue

            err, value = AXUIElementCopyAttributeValue(ax_element, attr, None)
            if err != 0 or value is None:
                return None
            return str(value)
        except Exception:
            return None

    def _ax_set_point(self, ax_element: Any, attr: str, point: tuple[float, float]) -> bool:
        try:
            import Quartz
            from ApplicationServices import AXUIElementSetAttributeValue, AXValueCreate, kAXValueCGPointType

            value = AXValueCreate(kAXValueCGPointType, Quartz.CGPoint(point[0], point[1]))
            return AXUIElementSetAttributeValue(ax_element, attr, value) == 0
        except Exception:
            return False
