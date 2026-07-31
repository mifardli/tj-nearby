from __future__ import annotations

import ctypes
import platform
from dataclasses import dataclass

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9


def mutex_name(app_name: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in app_name).strip("_")
    return f"Local\\{safe or 'TJNearby'}"


@dataclass
class SingleInstanceGuard:
    """Windows named-mutex guard.

    On non-Windows platforms this is a no-op so the module remains testable.
    Keep the guard alive for the process lifetime; releasing it closes the mutex.
    """

    app_name: str
    already_running: bool = False
    _handle: int | None = None

    def acquire(self) -> bool:
        if platform.system() != "Windows":
            self.already_running = False
            return True

        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, mutex_name(self.app_name))
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
        self._handle = int(handle)
        self.already_running = int(kernel32.GetLastError()) == ERROR_ALREADY_EXISTS
        return not self.already_running

    def release(self) -> None:
        if self._handle is None or platform.system() != "Windows":
            return
        try:
            ctypes.windll.kernel32.CloseHandle(self._handle)
        finally:
            self._handle = None


def activate_existing_window(title_prefix: str = "TJ Nearby") -> bool:
    """Bring the first visible TJ Nearby window to the foreground on Windows."""

    if platform.system() != "Windows":
        return False

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if buffer.value.startswith(title_prefix):
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        return False
    hwnd = found[0]
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True
