from __future__ import annotations

import subprocess
import threading
import traceback
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, load_config, set_config_value
from .engine import TJNearbyEngine
from .location import authorization_status_name, request_location_authorization
from .notify import Notifier


def authorization_blocks_automatic_polling(status: str) -> bool:
    """Only explicit denial/restriction should stop background checks.

    On some macOS/PyObjC combinations the static authorization API can remain
    `not-determined` even though Core Location already returns valid fixes.
    """
    return status in {"denied", "restricted"}


def main() -> None:
    try:
        import rumps
    except ImportError as exc:
        raise SystemExit("rumps is required. Install with: pip install -e '.[mac]'") from exc

    class MenuBarApp(rumps.App):
        def __init__(self):
            super().__init__("🚌", title="🚌", quit_button=None)
            self.config = load_config(DEFAULT_CONFIG_PATH)
            self.engine: TJNearbyEngine | None = None
            self.paused = False
            self.busy = False
            self.lock = threading.Lock()
            self.ui_lock = threading.Lock()
            self.pending_status_title: str | None = None
            self.pending_location_title: str | None = None
            self.permission_manager = None
            self.permission_delegate = None
            self.feedback_notifier = Notifier("TJ Nearby")

            self.status_item = rumps.MenuItem("Starting…")
            self.location_item = rumps.MenuItem(self._location_label())
            self.pause_item = rumps.MenuItem("Pause", callback=self.toggle_pause)
            self.menu = [
                self.status_item,
                self.location_item,
                None,
                rumps.MenuItem("Check now", callback=self.check_now),
                rumps.MenuItem("Test notification", callback=self.test_notification),
                self.pause_item,
                None,
                rumps.MenuItem("Enable automatic location", callback=self.enable_auto_location),
                rumps.MenuItem("Use saved manual location", callback=self.enable_manual_location),
                rumps.MenuItem("Open Location Services", callback=self.open_location_settings),
                None,
                rumps.MenuItem("Open config", callback=self.open_config),
                rumps.MenuItem("Run doctor in Terminal", callback=self.run_doctor),
                rumps.MenuItem("Export app diagnostic", callback=self.export_diagnostic),
                None,
                rumps.MenuItem("Quit", callback=self.quit_app),
            ]

            poll_seconds = max(15, int(self.config.get("realtime.poll_seconds", 30)))
            self.timer = rumps.Timer(self.timer_tick, poll_seconds)
            self.timer.start()
            self.startup_timer = rumps.Timer(self.startup_tick, 1)
            self.startup_timer.start()
            # All AppKit/rumps mutations are flushed from this timer on the
            # application main loop. Worker threads only update plain Python
            # strings, avoiding NSMenu deadlocks while the menu is open.
            self.ui_timer = rumps.Timer(self.flush_ui_updates, 0.5)
            self.ui_timer.start()

        def _set_status_title(self, title: str) -> None:
            title = str(title)[:140]
            if threading.current_thread() is threading.main_thread():
                self.status_item.title = title
                return
            with self.ui_lock:
                self.pending_status_title = title

        def _set_location_title(self, title: str) -> None:
            title = str(title)[:100]
            if threading.current_thread() is threading.main_thread():
                self.location_item.title = title
                return
            with self.ui_lock:
                self.pending_location_title = title

        def flush_ui_updates(self, _sender) -> None:
            # rumps.Timer callbacks run on the app's main event loop. Never
            # touch NSMenuItem objects directly from a polling worker thread.
            with self.ui_lock:
                status_title = self.pending_status_title
                location_title = self.pending_location_title
                self.pending_status_title = None
                self.pending_location_title = None
            if status_title is not None:
                self.status_item.title = status_title
            if location_title is not None:
                self.location_item.title = location_title

        def _begin_work(self) -> bool:
            with self.lock:
                if self.paused or self.busy:
                    return False
                self.busy = True
                return True

        def _finish_work(self) -> None:
            with self.lock:
                self.busy = False

        def _is_busy(self) -> bool:
            with self.lock:
                return self.busy

        def _location_label(self) -> str:
            mode = str(self.config.get("location.mode", "auto")).lower()
            if mode == "manual":
                return "Location: saved manual coordinates"
            return f"Location: automatic ({authorization_status_name()})"

        def _ensure_engine(self) -> TJNearbyEngine:
            if self.engine is None:
                self.engine = TJNearbyEngine(self.config)
            return self.engine

        def _reload(self) -> bool:
            if self._is_busy():
                self._set_status_title("Please wait until the current check finishes")
                return False
            if self.engine is not None:
                self.engine.close()
            self.config = load_config(DEFAULT_CONFIG_PATH)
            self.engine = None
            self._set_location_title(self._location_label())
            return True

        def startup_tick(self, _sender) -> None:
            self.startup_timer.stop()
            if str(self.config.get("location.mode", "auto")).lower() == "auto":
                self._request_permission_then_check()
            else:
                self._run_check()

        def _request_permission_then_check(self, *, show_feedback: bool = False) -> None:
            try:
                # The authorization prompt must be requested while the packaged
                # application is active. This call runs on the app's main loop.
                from AppKit import NSApplication

                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass

            def changed(status: str) -> None:
                self._set_location_title(f"Location: automatic ({status})")
                if status == "denied":
                    self._set_status_title("Location denied · open Location Services")
                elif status == "restricted":
                    self._set_status_title("Location restricted by macOS")
                elif status.startswith("authorized"):
                    self._set_status_title("Location allowed · checking buses…")
                    self._run_check(show_feedback=show_feedback)

            try:
                # Keep one manager/delegate while macOS is deciding. Some macOS /
                # PyObjC combinations continue returning a valid location fix while
                # the static authorizationStatus API remains `not-determined`.
                # Therefore we only block explicit denied/restricted states and let
                # the actual location request be the source of truth otherwise.
                status = authorization_status_name()
                if self.permission_manager is None or status != "not-determined":
                    self.permission_manager, self.permission_delegate = request_location_authorization(changed)
                status = authorization_status_name()
                self._set_location_title(f"Location: automatic ({status})")
                if status == "denied":
                    self._set_status_title("Location denied · open Location Services")
                    return
                if status == "restricted":
                    self._set_status_title("Location restricted by macOS")
                    return
                self._set_status_title("Checking location and buses…")
                self._run_check(show_feedback=show_feedback)
            except Exception as exc:
                self._set_status_title(f"Location setup error: {str(exc)[:55]}")

        def _run_check(self, *, show_feedback: bool = False) -> None:
            if not self._begin_work():
                return
            self._set_status_title("Checking…")

            def worker() -> None:
                try:
                    engine = self._ensure_engine()
                    result = engine.check_once()
                    if result.status == "ok":
                        if result.arrivals:
                            first = next(
                                (
                                    arrival
                                    for arrival in result.arrivals
                                    if arrival.confidence == "high"
                                    and not arrival.direction_ambiguous
                                ),
                                result.arrivals[0],
                            )
                            direction = first.route_headsign.strip() or f"arah {first.direction_id}"
                            if first.direction_ambiguous:
                                direction = "⚠ arah belum pasti"
                            elif first.direction_status == "estimated":
                                direction = f"perkiraan {direction}"
                            favorite_mark = "★ " if first.is_favorite_route else ""
                            text = (
                                f"Tracking {len(result.arrivals)} · {favorite_mark}{first.route_code} → {direction} · "
                                f"{first.eta_minutes:.0f}m · {first.stop_name}"
                            )
                        else:
                            text = f"Tracking 0 arrivals · {result.bus_count} buses nearby"
                    else:
                        text = f"{result.status}: {result.message[:60]}"
                    self._set_status_title(text)
                    if show_feedback:
                        if result.status == "ok":
                            self.feedback_notifier.send("TJ Nearby", text, subtitle="Check complete")
                        else:
                            self.feedback_notifier.send("TJ Nearby", text, subtitle="Check failed")
                except Exception as exc:
                    text = f"Error: {str(exc)[:70]}"
                    self._set_status_title(text)
                    if show_feedback:
                        self.feedback_notifier.send("TJ Nearby", text, subtitle="Check failed")
                finally:
                    self._finish_work()

            threading.Thread(target=worker, daemon=True, name="tj-nearby-check").start()

        def timer_tick(self, _sender) -> None:
            if str(self.config.get("location.mode", "auto")).lower() == "auto":
                status = authorization_status_name()
                self._set_location_title(f"Location: automatic ({status})")
                if authorization_blocks_automatic_polling(status):
                    return
            self._run_check()

        def check_now(self, _sender) -> None:
            if str(self.config.get("location.mode", "auto")).lower() == "auto":
                status = authorization_status_name()
                if status in {"denied", "restricted", "not-determined"}:
                    self._request_permission_then_check(show_feedback=True)
                    return
            self._run_check(show_feedback=True)

        def test_notification(self, _sender) -> None:
            self.feedback_notifier.send(
                "TJ Nearby",
                "Kalau pesan ini terlihat, notifikasi macOS sudah aktif.",
                subtitle="Notification test",
            )
            self._set_status_title("Test notification sent")

        def toggle_pause(self, _sender) -> None:
            self.paused = not self.paused
            self.pause_item.title = "Resume" if self.paused else "Pause"
            self._set_status_title("Paused" if self.paused else "Ready")
            if not self.paused:
                self._run_check()

        def enable_auto_location(self, _sender) -> None:
            set_config_value(self.config, "location.mode", "auto")
            if not self._reload():
                return
            self._set_status_title("Automatic location enabled")
            self._request_permission_then_check()

        def enable_manual_location(self, _sender) -> None:
            lat = self.config.get("location.manual_latitude")
            lon = self.config.get("location.manual_longitude")
            if lat is None or lon is None:
                self._set_status_title("Manual coordinates are not configured")
                return
            set_config_value(self.config, "location.mode", "manual")
            if not self._reload():
                return
            self._set_status_title("Using saved manual coordinates")
            self._run_check()

        def open_location_settings(self, _sender) -> None:
            subprocess.run(
                [
                    "/usr/bin/open",
                    "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices",
                ],
                check=False,
            )

        def open_config(self, _sender) -> None:
            DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["/usr/bin/open", str(DEFAULT_CONFIG_PATH)], check=False)

        def run_doctor(self, _sender) -> None:
            command = (
                f"tj-nearby --config '{DEFAULT_CONFIG_PATH}' doctor; echo; "
                "read -n 1 -s -r -p 'Press any key to close'"
            )
            escaped = command.replace(chr(34), chr(92) + chr(34))
            script = f'tell application "Terminal" to do script "{escaped}"'
            subprocess.run(["/usr/bin/osascript", "-e", script], check=False)

        def export_diagnostic(self, _sender) -> None:
            if not self._begin_work():
                return
            self._set_status_title("Exporting diagnostic…")

            def worker() -> None:
                destination = Path.home() / "Desktop" / "tj-nearby-app-diagnostic.txt"
                try:
                    engine = self._ensure_engine()
                    result = engine.check_once(dry_run=True, notify=False)
                    lines = [
                        "TJ Nearby app diagnostic",
                        f"location_mode: {self.config.get('location.mode', 'auto')}",
                        f"authorization: {authorization_status_name()}",
                        f"paused: {self.paused}",
                        f"automatic_poll_seconds: {max(15, int(self.config.get('realtime.poll_seconds', 30)))}",
                        f"notification_enabled: {bool(self.config.get('notification.enabled', True))}",
                        f"nearby_selection_mode: {self.config.get('nearby.selection_mode', 'smart')}",
                        "nearby_smart_group_limit: unlimited (legacy smart_max_groups ignored)",
                        f"favorite_routes: {','.join(sorted(self.config.favorite_routes)) or '-'}",
                        f"brt_search_radius_m: {float(self.config.get('nearby.services.brt.search_radius_m', 1000))}",
                        f"brt_notification_radius_m: {float(self.config.get('nearby.services.brt.notification_radius_m', 800))}",
                        f"non_brt_search_radius_m: {float(self.config.get('nearby.services.non_brt.search_radius_m', 800))}",
                        f"non_brt_notification_radius_m: {float(self.config.get('nearby.services.non_brt.notification_radius_m', 600))}",
                        f"jaklingko_search_radius_m: {float(self.config.get('nearby.services.jaklingko.search_radius_m', 500))}",
                        f"jaklingko_notification_radius_m: {float(self.config.get('nearby.services.jaklingko.notification_radius_m', 400))}",
                        f"notification_mode: {engine.notification_mode()}",
                        f"ready_notification_intensity: {engine.notification_intensity()}",
                        f"ready_enabled_stages: {','.join(engine.ready_enabled_stages())}",
                        f"ready_notify_lead_bus_only: {bool(self.config.get('notification.ready_notify_lead_bus_only', True))}",
                        f"ready_min_seconds_between_stages: {float(self.config.get('notification.ready_min_seconds_between_stages', 90))}",
                        f"ready_always_send_final_stage: {bool(self.config.get('notification.ready_always_send_final_stage', True))}",
                        f"ready_min_margin_minutes: {float(self.config.get('notification.ready_min_margin_minutes', 2))}",
                        f"ready_max_stop_distance_m: {float(self.config.get('notification.ready_max_stop_distance_m', 500))}",
                        f"ready_max_bus_data_age_seconds: {float(self.config.get('notification.ready_max_bus_data_age_seconds', 90))}",
                        f"notification_min_eta_minutes: {float(self.config.get('notification.min_eta_minutes', 2))}",
                        f"notification_max_eta_minutes: {float(self.config.get('notification.max_eta_minutes', 15))}",
                        f"notification_leave_buffer_minutes: {float(self.config.get('notification.leave_buffer_minutes', 3))}",
                        f"notification_timing_too_late_margin_minutes: {float(self.config.get('notification.timing_too_late_margin_minutes', 1))}",
                        f"notification_timing_leave_now_margin_minutes: {float(self.config.get('notification.timing_leave_now_margin_minutes', 5))}",
                        f"notification_max_per_cycle: {int(self.config.get('notification.max_notifications_per_cycle', 0))}",
                        f"notification_cooldown_minutes: {float(self.config.get('notification.cooldown_minutes', 180))}",
                        f"notification_minimum_direction_confidence: {self.config.get('notification.minimum_direction_confidence', 'high')}",
                        f"direction_ambiguity_score_margin: {int(self.config.get('direction.ambiguity_score_margin', 20))}",
                        f"journey_turnaround_tracking: {bool(self.config.get('direction.track_turnarounds', True))}",
                        f"journey_state_max_age_hours: {float(self.config.get('direction.journey_state_max_age_hours', 12))}",
                        f"status: {result.status}",
                        f"message: {result.message}",
                    ]
                    if result.location:
                        loc = result.location
                        lines.append(
                            f"location: {loc.latitude:.6f}, {loc.longitude:.6f}; "
                            f"accuracy={loc.accuracy_m:.0f}m; source={loc.source}"
                        )
                    lines.append(f"nearby_stop_groups: {len(result.nearby_stop_groups)}")
                    for group in result.nearby_stop_groups:
                        ids = ",".join(member.stop.stop_id for member in group.members)
                        lines.append(
                            f"- {group.name}; distance={group.distance_m:.0f}m; "
                            f"service={group.primary_service_class}; "
                            f"service_classes={','.join(group.service_classes)}; "
                            f"routes={','.join(group.route_codes)}; "
                            f"favorite_routes={','.join(group.favorite_route_codes) or '-'}; gtfs_ids={ids}"
                        )
                    lines.append(f"realtime_buses: {result.bus_count}")
                    lines.append(f"arrivals: {len(result.arrivals)}")
                    for arrival in result.arrivals[:50]:
                        eligible, reason = engine.notification_eligibility(arrival)
                        margin = arrival.eta_minutes - arrival.walking_minutes
                        timing_code, timing_label = engine.notification_label(arrival)
                        lines.append(
                            f"- {arrival.route_code} -> {arrival.route_headsign}; "
                            f"stop={arrival.stop_name}; service={arrival.service_class}; "
                            f"favorite_route={'yes' if arrival.is_favorite_route else 'no'}; "
                            f"eta={arrival.eta_minutes:.1f}m; "
                            f"walk={arrival.walking_minutes:.1f}m; margin={margin:.1f}m; "
                            f"stops_away={arrival.stops_away}; stops_source={arrival.stops_away_source}; "
                            f"notification_stage={engine.ready_stage(arrival) or '-'}; "
                            f"bus_data_age={arrival.bus_data_age_seconds:.0f}s; "
                            f"tracking_status={timing_code}; tracking_label={timing_label}; "
                            f"notify_eligible={'yes' if eligible else 'no'}; reason={reason}; "
                            f"confidence={arrival.confidence}; direction_status={arrival.direction_status}; "
                            f"direction_score={arrival.direction_score}; "
                            f"direction_ambiguous={'yes' if arrival.direction_ambiguous else 'no'}; "
                            f"direction_source={arrival.direction_source}; "
                            f"api_headsign={arrival.live_headsign or '-'}; "
                            f"journey_epoch={arrival.journey_epoch}; "
                            f"journey_transition={arrival.journey_transition}; "
                            f"previous_direction={arrival.previous_direction_label or '-'}; "
                            f"evidence={','.join(arrival.direction_evidence)}"
                        )
                    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    self._set_status_title("Diagnostic exported")
                    subprocess.run(["/usr/bin/open", "-R", str(destination)], check=False)
                except Exception as exc:
                    details = [
                        "TJ Nearby app diagnostic",
                        f"location_mode: {self.config.get('location.mode', 'auto')}",
                        f"authorization: {authorization_status_name()}",
                        f"exception_type: {type(exc).__name__}",
                        f"exception: {exc}",
                    ]
                    if isinstance(exc, FileNotFoundError):
                        details.append(f"missing_filename: {exc.filename}")
                    details.extend(["", "traceback:", traceback.format_exc()])
                    destination.write_text("\n".join(details) + "\n", encoding="utf-8")
                    self._set_status_title(f"Diagnostic error: {str(exc)[:50]}")
                    subprocess.run(["/usr/bin/open", "-R", str(destination)], check=False)
                finally:
                    self._finish_work()

            threading.Thread(target=worker, daemon=True, name="tj-nearby-diagnostic").start()

        def quit_app(self, _sender) -> None:
            self.paused = True
            self.timer.stop()
            self.ui_timer.stop()
            if self.engine and not self._is_busy():
                self.engine.close()
            rumps.quit_application()

    MenuBarApp().run()
