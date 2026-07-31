from __future__ import annotations

import platform
import subprocess


class Notifier:
    def __init__(self, app_name: str = "TJ Nearby"):
        self.app_name = app_name

    def send(self, title: str, message: str, subtitle: str = "") -> None:
        if platform.system() != "Darwin":
            print(f"[NOTIFICATION] {title}: {message}")
            return
        try:
            import rumps

            rumps.notification(title, subtitle, message)
            return
        except Exception:
            pass

        script = (
            f'display notification "{_escape(message)}" '
            f'with title "{_escape(title)}" '
            f'subtitle "{_escape(subtitle)}"'
        )
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
