from __future__ import annotations

import argparse
from collections import Counter
import os
import platform
import queue
import sys
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

import tkinter as tk
from tkinter import messagebox, ttk

from .activity_log import activity_log_path, setup_activity_logger, tail_activity_log
from .config import DEFAULT_CONFIG_PATH, AppConfig, ConfigError, load_config, set_config_value
from .engine import CheckResult, TJNearbyEngine
from .location import LocationError, request_windows_location_access
from .models import Arrival, LocationFix, NearbyStop, NearbyStopGroup, Stop
from .route_style import route_badge_style
from .service import normalize_route_code, service_label
from .windows_autostart import is_enabled as autostart_is_enabled
from .windows_autostart import set_enabled as set_autostart_enabled
from .single_instance import SingleInstanceGuard, activate_existing_window

APP_NAME = "TJ Nearby"
APP_VERSION = "0.4.4"

BG = "#F5F7FB"
PANEL = "#FFFFFF"
HEADER = "#EDEBFA"
HEADER_TEXT = "#2C285B"
DARK = "#24233B"
MUTED = "#6D7280"
LINE = "#D8DCE6"
ACCENT = "#5E4DB2"
ACCENT_LIGHT = "#EEEAFE"
SUCCESS = "#177A52"
WARNING = "#A15C00"
DANGER = "#B42318"


def _set_windows_dpi_awareness() -> None:
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def format_eta(minutes: float) -> str:
    if minutes < 1:
        return "< 1 menit"
    if minutes < 60:
        return f"{max(1, round(minutes))} menit"
    hours = int(minutes // 60)
    remainder = int(round(minutes % 60))
    return f"{hours}j {remainder}m"


def display_status(engine: TJNearbyEngine | None, arrival: Arrival) -> tuple[str, str]:
    if engine is None:
        if arrival.stops_away == 1:
            return "Bus sangat dekat", DANGER
        if arrival.eta_minutes <= 5:
            return "Berangkat sekarang", WARNING
        return "Masih dipantau", MUTED
    code, label = engine.notification_label(arrival)
    color = MUTED
    if code in {"target_is_next", "likely_missed"}:
        color = DANGER
    elif code in {"one_stop_before", "leave_now", "eta_fallback"}:
        color = WARNING
    elif code in {"two_stops_before", "plenty_time"}:
        color = SUCCESS
    return label.capitalize(), color


def unique_display_arrivals(arrivals: Iterable[Arrival], *, limit: int | None = None) -> list[Arrival]:
    """Keep every distinct live arrival projection shown by the engine.

    v0.4.0 accidentally used a UI-only key that could collapse opposite
    directions for the same physical bus/route/stop.  The monitor now mirrors
    the complete engine snapshot and only removes exact duplicate projections.
    """
    seen: set[tuple[object, ...]] = set()
    rows: list[Arrival] = []
    for arrival in arrivals:
        key = (
            arrival.bus_id,
            normalize_route_code(arrival.route_code),
            arrival.stop_id,
            arrival.direction_id,
            " ".join((arrival.route_headsign or "").casefold().split()),
            arrival.trip_id or "",
            arrival.journey_epoch,
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(arrival)
        if limit is not None and limit > 0 and len(rows) >= limit:
            break
    return rows


def demo_result() -> CheckResult:
    now = datetime.now(timezone.utc)
    location = LocationFix(-6.2082, 106.8698, 22, now, "demo-windows-location")
    stop = Stop("DEMO-1", "Flyover Jatinegara", -6.2080, 106.8700)
    nearby = NearbyStop(stop, 145)
    group = NearbyStopGroup(
        name="Flyover Jatinegara",
        distance_m=145,
        members=[nearby],
        route_codes=("4D", "6H", "JAK 81"),
        service_classes=("brt", "non_brt", "jaklingko"),
        primary_service_class="brt",
        favorite_route_codes=("4D", "JAK 81"),
    )
    base = dict(
        stop_id=stop.stop_id,
        stop_name=stop.name,
        stop_distance_m=145,
        walking_minutes=2.1,
        direction_id=0,
        confidence="high",
        distance_along_route_m=800,
        direction_status="confirmed",
        bus_data_age_seconds=8,
    )
    arrivals = [
        Arrival(
            bus_id="DMR-240193",
            route_code="4D",
            eta_minutes=3.2,
            route_headsign="Pulo Gadung",
            stops_away=2,
            is_favorite_route=True,
            service_class="non_brt",
            route_color="#7447B8",
            route_text_color="#FFFFFF",
            **base,
        ),
        Arrival(
            bus_id="MYS-17030",
            route_code="6H",
            eta_minutes=7.4,
            route_headsign="Senen",
            stops_away=3,
            service_class="non_brt",
            route_color="#D94A88",
            route_text_color="#FFFFFF",
            **base,
        ),
        Arrival(
            bus_id="JAK-81-026",
            route_code="JAK 81",
            eta_minutes=11.0,
            route_headsign="Kampung Melayu",
            stops_away=5,
            is_favorite_route=True,
            service_class="jaklingko",
            route_color="#2476B8",
            route_text_color="#FFFFFF",
            **base,
        ),
    ]
    return CheckResult(
        location=location,
        nearby_stops=[nearby],
        nearby_stop_groups=[group],
        bus_count=87,
        arrivals=arrivals,
        status="ok",
        message="Demo monitor",
    )


class TrayNotifier:
    def __init__(self, tray_supplier: Callable[[], object | None], logger=None):
        self._tray_supplier = tray_supplier
        self._logger = logger

    def send(self, title: str, message: str, subtitle: str = "") -> bool:
        tray = self._tray_supplier()
        text = f"{subtitle}\n{message}" if subtitle else message
        if self._logger is not None:
            self._logger.info("toast.attempt title=%s subtitle=%s", title, subtitle)
        if tray is not None and getattr(tray, "HAS_NOTIFICATION", False):
            try:
                tray.notify(text, title)
                if self._logger is not None:
                    self._logger.info("toast.delivered backend=pystray title=%s", title)
                return True
            except Exception as exc:
                if self._logger is not None:
                    self._logger.exception("toast.failed backend=pystray error=%s", exc)
        if self._logger is not None:
            self._logger.error(
                "toast.unavailable tray_present=%s has_notification=%s title=%s",
                tray is not None,
                bool(getattr(tray, "HAS_NOTIFICATION", False)) if tray is not None else False,
                title,
            )
        print(f"[NOTIFICATION] {title}: {text}")
        return False


class MonitorApp:
    def __init__(
        self,
        root: tk.Tk,
        config: AppConfig,
        *,
        demo: bool = False,
        background: bool = False,
    ):
        self.root = root
        self.config = config
        self.demo = demo
        self.background = background
        if self.demo and not self.config.favorite_routes:
            self.config.raw.setdefault("routes", {})["favorites"] = ["4D", "JAK 81"]
        self.activity_logger = setup_activity_logger(self.config.state_dir)
        self.activity_logger.info(
            "app.start version=%s platform=%s config=%s demo=%s background=%s",
            APP_VERSION,
            platform.platform(),
            self.config.path,
            demo,
            background,
        )
        self.engine: TJNearbyEngine | None = None
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.checking = False
        self.paused = False
        self.muted_until: datetime | None = None
        self.last_result: CheckResult | None = None
        self.last_successful_result: CheckResult | None = None
        self.last_success_at: datetime | None = None
        self.last_notification_sent_count = 0
        self._notify_after_apply = False
        self._check_token = 0
        self.tray_icon = None
        self._tray_thread: threading.Thread | None = None
        self._closing = False
        self._hide_tip_shown = False
        self._poll_after_id: str | None = None
        self._watchdog_after_id: str | None = None
        self._check_started_at: datetime | None = None
        self._consecutive_timeouts = 0

        self._configure_root()
        self._build_ui()
        self._start_tray()

        if self.demo:
            self._apply_result(demo_result())
        else:
            # Permission must be requested after the window exists and is foregrounded.
            self.root.after(350, self._request_location_then_initialize)

        self.root.after(120, self._drain_queue)
        self.root.after(1000, self._tick_clock)
        if background:
            self.root.after(1500, self.hide_window)

    def _configure_root(self) -> None:
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.configure(bg=BG)
        self.root.geometry("1080x620")
        self.root.minsize(860, 500)
        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)
        try:
            icon_path = Path(__file__).resolve().parent / "assets" / "tj_nearby.ico"
            if icon_path.exists():
                self.root.iconbitmap(default=str(icon_path))
        except Exception:
            pass

    def _build_ui(self) -> None:
        top = tk.Frame(self.root, bg=HEADER, height=100)
        top.pack(fill="x")
        top.pack_propagate(False)

        title_block = tk.Frame(top, bg=HEADER)
        title_block.pack(side="left", fill="both", expand=True, padx=28, pady=15)
        self.stop_title = tk.Label(
            title_block,
            text="Mencari halte terdekat…",
            bg=HEADER,
            fg=HEADER_TEXT,
            font=("Segoe UI Semibold", 20),
            anchor="w",
        )
        self.stop_title.pack(fill="x")
        self.stop_subtitle = tk.Label(
            title_block,
            text="GPS sedang menyiapkan lokasi Windows",
            bg=HEADER,
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.stop_subtitle.pack(fill="x", pady=(4, 0))

        controls = tk.Frame(top, bg=HEADER)
        controls.pack(side="right", padx=22, pady=18)
        self.refresh_button = tk.Button(
            controls,
            text="↻  Refresh",
            command=self.refresh,
            relief="flat",
            bg=PANEL,
            fg=HEADER_TEXT,
            activebackground=ACCENT_LIGHT,
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=8,
            cursor="hand2",
        )
        self.refresh_button.pack(side="left", padx=4)
        self.pause_button = tk.Button(
            controls,
            text="Ⅱ  Pause",
            command=self.toggle_pause,
            relief="flat",
            bg=PANEL,
            fg=HEADER_TEXT,
            activebackground=ACCENT_LIGHT,
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=8,
            cursor="hand2",
        )
        self.pause_button.pack(side="left", padx=4)
        settings = tk.Button(
            controls,
            text="⚙",
            command=self.open_settings,
            relief="flat",
            bg=PANEL,
            fg=HEADER_TEXT,
            activebackground=ACCENT_LIGHT,
            font=("Segoe UI", 14),
            width=3,
            cursor="hand2",
        )
        settings.pack(side="left", padx=4)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(18, 12))

        info = tk.Frame(body, bg=PANEL, width=205, highlightbackground=LINE, highlightthickness=1)
        info.pack(side="left", fill="y", padx=(0, 14))
        info.pack_propagate(False)
        tk.Label(info, text="TJ NEARBY", bg=PANEL, fg=ACCENT, font=("Segoe UI Semibold", 13)).pack(
            anchor="w", padx=18, pady=(20, 4)
        )
        tk.Label(
            info,
            text="Pengingat bus desktop\nberbasis halte terdekat.",
            justify="left",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=18)

        self.gps_chip = tk.Label(
            info,
            text="●  GPS menunggu",
            bg="#FFF7E8",
            fg=WARNING,
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=7,
        )
        self.gps_chip.pack(anchor="w", padx=18, pady=(24, 8))
        self.sync_chip = tk.Label(
            info,
            text="●  Menunggu data",
            bg="#FFF7E8",
            fg=WARNING,
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=7,
        )
        self.sync_chip.pack(anchor="w", padx=18, pady=(0, 8))
        self.stop_count_label = tk.Button(
            info,
            text="0 halte terpantau  ›",
            command=self.show_monitored_stops,
            relief="flat",
            borderwidth=0,
            bg=PANEL,
            activebackground=ACCENT_LIGHT,
            fg=DARK,
            font=("Segoe UI Semibold", 10),
            cursor="hand2",
            anchor="w",
            padx=0,
        )
        self.stop_count_label.pack(fill="x", padx=18, pady=4)
        self.service_count_label = tk.Label(
            info,
            text="BRT 0 · Non-BRT 0 · JakLingko 0",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.service_count_label.pack(fill="x", padx=18, pady=(0, 2))
        self.bus_count_label = tk.Label(
            info,
            text="0 posisi bus diterima",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.bus_count_label.pack(anchor="w", padx=18, pady=2)
        self.arrival_count_label = tk.Label(
            info,
            text="0 kendaraan menuju halte",
            bg=PANEL,
            fg=DARK,
            font=("Segoe UI Semibold", 9),
        )
        self.arrival_count_label.pack(anchor="w", padx=18, pady=2)
        self.notification_count_label = tk.Label(
            info,
            text="0 notifikasi dikirim",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.notification_count_label.pack(anchor="w", padx=18, pady=2)
        self.mode_label = tk.Label(
            info,
            text="Mode: Smart Nearby",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.mode_label.pack(anchor="w", padx=18, pady=2)

        tk.Frame(info, bg=LINE, height=1).pack(fill="x", padx=18, pady=18)
        tk.Label(info, text="Rute favorit", bg=PANEL, fg=DARK, font=("Segoe UI Semibold", 10)).pack(
            anchor="w", padx=18
        )
        self.favorite_summary = tk.Label(
            info,
            text="Belum ada",
            justify="left",
            wraplength=165,
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.favorite_summary.pack(anchor="w", padx=18, pady=(6, 0))

        tk.Frame(info, bg=LINE, height=1).pack(fill="x", padx=18, pady=(18, 12))
        tk.Button(
            info,
            text="Uji notifikasi",
            command=self.test_notification,
            relief="flat",
            bg=ACCENT_LIGHT,
            fg=HEADER_TEXT,
            activebackground="#E1DCF7",
            font=("Segoe UI Semibold", 9),
            cursor="hand2",
            padx=10,
            pady=7,
        ).pack(fill="x", padx=18, pady=(0, 7))
        tk.Button(
            info,
            text="Ekspor activity log",
            command=self.export_activity_diagnostic,
            relief="flat",
            bg=PANEL,
            fg=HEADER_TEXT,
            activebackground=ACCENT_LIGHT,
            font=("Segoe UI Semibold", 9),
            cursor="hand2",
            padx=10,
            pady=7,
        ).pack(fill="x", padx=18)

        monitor = tk.Frame(body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        monitor.pack(side="left", fill="both", expand=True)

        table_header = tk.Frame(monitor, bg="#F3F1FA", height=50)
        table_header.pack(fill="x")
        table_header.pack_propagate(False)
        self._header_cell(table_header, "RUTE", 0, 2)
        self._header_cell(table_header, "ARAH", 1, 3)
        self._header_cell(table_header, "HALTE", 2, 3)
        self._header_cell(table_header, "NO. BUS", 3, 2)
        self._header_cell(table_header, "ESTIMASI", 4, 2)
        table_header.grid_columnconfigure(0, weight=2, uniform="route")
        table_header.grid_columnconfigure(1, weight=3, uniform="route")
        table_header.grid_columnconfigure(2, weight=3, uniform="route")
        table_header.grid_columnconfigure(3, weight=2, uniform="route")
        table_header.grid_columnconfigure(4, weight=2, uniform="route")

        canvas_frame = tk.Frame(monitor, bg=PANEL)
        canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.rows_frame = tk.Frame(self.canvas, bg=PANEL)
        self.rows_frame.bind(
            "<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>", lambda event: self.canvas.itemconfigure(self.canvas_window, width=event.width)
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.empty = tk.Frame(self.rows_frame, bg=PANEL)
        tk.Label(
            self.empty,
            text="Belum ada bus yang terdeteksi",
            bg=PANEL,
            fg=DARK,
            font=("Segoe UI Semibold", 15),
        ).pack(pady=(70, 8))
        self.empty_detail = tk.Label(
            self.empty,
            text="TJ Nearby tetap memantau halte sekitar secara otomatis.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 10),
        )
        self.empty_detail.pack()
        self.empty.pack(fill="both", expand=True)

        footer = tk.Frame(self.root, bg=DARK, height=45)
        footer.pack(fill="x")
        footer.pack_propagate(False)
        self.footer_status = tk.Label(
            footer,
            text="Menyiapkan TJ Nearby…",
            bg=DARK,
            fg="#FFFFFF",
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.footer_status.pack(side="left", fill="x", expand=True, padx=20)
        self.clock_label = tk.Label(
            footer,
            text="",
            bg=DARK,
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 10),
        )
        self.clock_label.pack(side="right", padx=20)

    @staticmethod
    def _header_cell(parent: tk.Frame, text: str, column: int, weight: int) -> None:
        label = tk.Label(
            parent,
            text=text,
            bg="#F3F1FA",
            fg=HEADER_TEXT,
            font=("Segoe UI Semibold", 10),
            anchor="w",
        )
        label.grid(row=0, column=column, sticky="nsew", padx=18)

    def _request_location_then_initialize(self) -> None:
        if platform.system() == "Windows" and str(self.config.get("location.mode", "auto")).lower() == "auto":
            self._set_busy(True, "Meminta izin Location services dari Windows…")
            try:
                request_windows_location_access()
            except LocationError as exc:
                self.stop_title.configure(text="Izin lokasi diperlukan")
                self.stop_subtitle.configure(text=str(exc))
                self.gps_chip.configure(text="●  GPS belum diizinkan", bg="#FFF0EE", fg=DANGER)
                self.footer_status.configure(text=str(exc))
        self._initialize_engine_async()

    def _initialize_engine_async(self) -> None:
        self._set_busy(True, "Mengunduh/memuat GTFS dan menyiapkan engine…")

        def task() -> None:
            try:
                self.activity_logger.info("engine.initialize start")
                engine = TJNearbyEngine(self.config)
                engine.notifier = TrayNotifier(lambda: self.tray_icon, self.activity_logger)
                self.result_queue.put(("engine", engine))
            except Exception as exc:
                self.activity_logger.exception("engine.initialize failed error=%s", exc)
                self.result_queue.put(("engine_error", exc))

        threading.Thread(target=task, name="tj-engine-init", daemon=True).start()

    def refresh(self) -> None:
        if self._poll_after_id is not None:
            try:
                self.root.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None
        if self.demo:
            self._apply_result(demo_result())
            return
        if self.paused or self.engine is None:
            return
        if self.checking:
            self.footer_status.configure(text="Pemeriksaan masih berjalan; hasil terbaru akan langsung ditampilkan.")
            return
        self.checking = True
        self._check_token += 1
        token = self._check_token
        self._check_started_at = datetime.now(timezone.utc)
        self.activity_logger.info(
            "gui.refresh.start token=%d muted=%s paused=%s",
            token,
            self._is_muted(),
            self.paused,
        )
        self._set_busy(True, "Memeriksa GPS, semua halte terpantau, dan bus realtime…")
        self._set_sync_state("updating")
        notify = not self._is_muted()

        def task() -> None:
            try:
                # Notifications are deliberately sent only after the exact same
                # snapshot has been rendered by Tk on the main thread.  This
                # prevents a new toast appearing while the monitor stays stale.
                result = self.engine.check_once(notify=False)
                self.result_queue.put(("result", (token, result, notify)))
            except Exception as exc:
                self.result_queue.put(("check_error", (token, exc)))

        threading.Thread(target=task, name=f"tj-check-{token}", daemon=True).start()
        self._arm_check_watchdog(token)

    def _arm_check_watchdog(self, token: int) -> None:
        self._cancel_check_watchdog()
        seconds = max(25, int(self.config.get("desktop.check_timeout_seconds", 55)))
        self._watchdog_after_id = self.root.after(
            seconds * 1000,
            lambda: self._on_check_timeout(token, seconds),
        )

    def _cancel_check_watchdog(self) -> None:
        if self._watchdog_after_id is None:
            return
        try:
            self.root.after_cancel(self._watchdog_after_id)
        except Exception:
            pass
        self._watchdog_after_id = None

    def _on_check_timeout(self, token: int, seconds: int) -> None:
        self._watchdog_after_id = None
        if not self.checking or token != self._check_token or self._closing:
            return
        self.activity_logger.error(
            "gui.refresh.timeout token=%d timeout_s=%d", token, seconds
        )
        # Invalidate the late worker result. A fresh engine is created because a
        # stalled HTTP/location client must not keep the board stuck forever.
        self._check_token += 1
        self.checking = False
        self._set_busy(False)
        self._consecutive_timeouts += 1
        self._set_sync_state("stale" if self.last_successful_result else "error")
        self.footer_status.configure(
            text=(
                f"Pembaruan timeout setelah {seconds} detik. Data terakhir tetap tampil; "
                "engine sedang dimuat ulang otomatis."
            )
        )
        self.engine = None
        self._initialize_engine_async()

    def _notify_snapshot_async(self, arrivals: list[Arrival], *, token: int) -> None:
        if self.engine is None or token != self._check_token:
            return

        snapshot = list(arrivals)

        def task() -> None:
            try:
                sent = self.engine.notify_due(snapshot)
                self.activity_logger.info(
                    "gui.notify.finish token=%d arrivals=%d sent=%d",
                    token,
                    len(snapshot),
                    len(sent),
                )
                self.result_queue.put(("notify_done", (token, len(sent))))
            except Exception as exc:
                self.activity_logger.exception("gui.notify.failed token=%d error=%s", token, exc)
                self.result_queue.put(("notify_error", exc))

        threading.Thread(
            target=task,
            name=f"tj-notify-{token}",
            daemon=True,
        ).start()

    def _schedule_next_check(self) -> None:
        if self.paused or self._closing:
            return
        if self._poll_after_id is not None:
            try:
                self.root.after_cancel(self._poll_after_id)
            except Exception:
                pass
        seconds = int(self.config.get("realtime.poll_seconds", 30))
        self._poll_after_id = self.root.after(max(5, seconds) * 1000, self.refresh)

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                try:
                    if kind == "engine":
                        self.engine = payload  # type: ignore[assignment]
                        self.activity_logger.info("engine.initialize ready")
                        self._set_busy(False, "Engine siap. Memulai pemantauan otomatis.")
                        self.refresh()
                    elif kind == "engine_error":
                        self.checking = False
                        self._show_error("Engine gagal dimuat", payload)
                    elif kind == "result":
                        token, result, notify = payload  # type: ignore[misc]
                        if token != self._check_token:
                            continue
                        self._cancel_check_watchdog()
                        self.checking = False
                        self._consecutive_timeouts = 0
                        self._set_busy(False)
                        self.activity_logger.info(
                            "gui.refresh.result token=%d status=%s buses=%d arrivals=%d",
                            token,
                            result.status,
                            result.bus_count,
                            len(result.arrivals),
                        )
                        self._apply_result(result)
                        self._schedule_next_check()
                        if notify and result.status == "ok" and result.arrivals:
                            self._notify_snapshot_async(result.arrivals, token=token)
                    elif kind == "check_error":
                        token, error = payload  # type: ignore[misc]
                        if token != self._check_token:
                            continue
                        self._cancel_check_watchdog()
                        self.checking = False
                        self._set_busy(False)
                        self.activity_logger.error(
                            "gui.refresh.error token=%d error=%s", token, error
                        )
                        self._show_error("Pemeriksaan gagal", error)
                        self._set_sync_state("error")
                        self._schedule_next_check()
                    elif kind == "notify_done":
                        token, sent_count = payload  # type: ignore[misc]
                        if token == self._check_token:
                            self.last_notification_sent_count = int(sent_count)
                            self.notification_count_label.configure(
                                text=f"{sent_count} notifikasi dikirim siklus ini",
                                fg=SUCCESS if sent_count else MUTED,
                            )
                    elif kind == "notify_error":
                        self.activity_logger.error("gui.notify.error error=%s", payload)
                        self.notification_count_label.configure(text="Notifikasi gagal", fg=DANGER)
                        self.footer_status.configure(
                            text=f"Monitor tetap aktif; notifikasi gagal: {payload}"
                        )
                except Exception as exc:
                    # Tkinter used to lose the whole 120 ms queue pump when one
                    # result-rendering callback raised. Keep the pump alive and
                    # log the real exception so Refresh can recover automatically.
                    self.activity_logger.exception(
                        "gui.queue_handler.failed kind=%s error=%s", kind, exc
                    )
                    if kind == "result":
                        try:
                            token = payload[0]
                            if token == self._check_token:
                                self._cancel_check_watchdog()
                                self.checking = False
                                self._set_busy(False)
                                self._set_sync_state("error")
                                self.footer_status.configure(
                                    text=f"Tampilan gagal diperbarui: {exc}. Mencoba lagi otomatis."
                                )
                                self._schedule_next_check()
                        except Exception:
                            pass
        except queue.Empty:
            pass
        finally:
            if not self._closing:
                self.root.after(120, self._drain_queue)

    def _apply_result(self, result: CheckResult) -> None:
        self.last_result = result
        self.activity_logger.info(
            "gui.apply status=%s groups=%d buses=%d arrivals=%d message=%s",
            result.status,
            len(result.nearby_stop_groups),
            result.bus_count,
            len(result.arrivals),
            result.message,
        )
        transient_error = result.status in {
            "location_error",
            "inaccurate_location",
            "realtime_error",
        }
        display_result = result
        if transient_error and self.last_successful_result is not None:
            # Keep the latest successful board visible during a temporary GPS/API
            # failure.  A clear stale marker is safer than an empty monitor that
            # looks like there are no buses.
            display_result = self.last_successful_result

        groups = display_result.nearby_stop_groups
        nearest = groups[0] if groups else None
        if nearest:
            self.stop_title.configure(text=f"Halte terdekat: {nearest.name}")
            self.stop_subtitle.configure(
                text=(
                    f"{nearest.distance_m:.0f} m dari lokasi · "
                    f"{service_label(nearest.primary_service_class)} · "
                    f"memantau {len(groups)} halte sekitar"
                )
            )
        elif result.status == "location_error":
            self.stop_title.configure(text="Lokasi Windows belum tersedia")
            self.stop_subtitle.configure(text=result.message)
        else:
            self.stop_title.configure(text="Belum menemukan halte terdekat")
            self.stop_subtitle.configure(text=result.message or "Pemantauan akan mencoba kembali.")

        location = result.location or display_result.location
        if location:
            self.gps_chip.configure(
                text=f"●  GPS aktif · ±{location.accuracy_m:.0f} m",
                bg="#E9F8F0",
                fg=SUCCESS,
            )
        else:
            self.gps_chip.configure(text="●  GPS bermasalah", bg="#FFF0EE", fg=DANGER)

        service_counts = {"brt": 0, "non_brt": 0, "jaklingko": 0}
        for group in groups:
            primary = group.primary_service_class
            if primary in service_counts:
                service_counts[primary] += 1
        self.stop_count_label.configure(text=f"{len(groups)} halte terpantau  ›")
        self.service_count_label.configure(
            text=(
                f"BRT {service_counts['brt']} · "
                f"Non-BRT {service_counts['non_brt']} · "
                f"JakLingko {service_counts['jaklingko']}"
            )
        )
        self.bus_count_label.configure(text=f"{display_result.bus_count} posisi bus diterima")
        display_arrivals = unique_display_arrivals(display_result.arrivals, limit=10_000)
        self.arrival_count_label.configure(
            text=f"{len(display_arrivals)} kendaraan menuju halte"
        )
        eligible_count = 0
        if self.engine is not None:
            eligible_count = sum(
                1 for arrival in display_arrivals if self.engine.notification_eligibility(arrival)[0]
            )
        self.notification_count_label.configure(
            text=f"{eligible_count} lolos aturan notifikasi",
            fg=SUCCESS if eligible_count else MUTED,
        )
        self._update_favorite_summary()

        if result.status == "ok":
            self.last_successful_result = result
            self.last_success_at = datetime.now(timezone.utc)
            self._render_arrivals(result.arrivals)
            self._set_sync_state("live")
            now = self.last_success_at.astimezone().strftime("%H:%M:%S")
            displayed = len(unique_display_arrivals(result.arrivals, limit=10_000))
            self.footer_status.configure(
                text=(
                    f"Semua halte diperiksa · {displayed} kendaraan ditampilkan · "
                    f"{eligible_count} lolos aturan notifikasi · diperbarui {now}"
                )
            )
            return

        if transient_error and self.last_successful_result is not None:
            self._set_sync_state("stale")
            last_text = (
                self.last_success_at.astimezone().strftime("%H:%M:%S")
                if self.last_success_at
                else "sebelumnya"
            )
            self.footer_status.configure(
                text=(
                    f"Pembaruan gagal ({result.status}); data terakhir {last_text} "
                    "tetap ditampilkan dan akan dicoba lagi otomatis."
                )
            )
            return

        self._render_arrivals(result.arrivals)
        self._set_sync_state("error" if result.status != "ok" else "live")
        self.footer_status.configure(text=f"{result.status}: {result.message}")

    def _render_arrivals(self, arrivals: list[Arrival]) -> None:
        for child in self.rows_frame.winfo_children():
            child.destroy()
        if not arrivals:
            empty = tk.Frame(self.rows_frame, bg=PANEL)
            tk.Label(
                empty,
                text="Belum ada bus yang terdeteksi",
                bg=PANEL,
                fg=DARK,
                font=("Segoe UI Semibold", 15),
            ).pack(pady=(70, 8))
            tk.Label(
                empty,
                text="Semua halte terpantau tetap diperiksa otomatis setiap siklus.",
                bg=PANEL,
                fg=MUTED,
                font=("Segoe UI", 10),
            ).pack()
            empty.pack(fill="both", expand=True)
            return

        # v0.4.4 intentionally renders the complete engine snapshot. Older
        # configs may still contain desktop.max_arrival_rows: 60, but that
        # legacy cap must not hide valid nearby vehicles.
        rows = unique_display_arrivals(arrivals)
        for index, arrival in enumerate(rows):
            self._build_arrival_row(arrival, index)

    def _build_arrival_row(self, arrival: Arrival, index: int) -> None:
        row_bg = PANEL if index % 2 == 0 else "#FBFCFE"
        row = tk.Frame(self.rows_frame, bg=row_bg, height=82)
        row.pack(fill="x")
        row.pack_propagate(False)
        row.grid_columnconfigure(0, weight=2, uniform="row")
        row.grid_columnconfigure(1, weight=3, uniform="row")
        row.grid_columnconfigure(2, weight=3, uniform="row")
        row.grid_columnconfigure(3, weight=2, uniform="row")
        row.grid_columnconfigure(4, weight=2, uniform="row")

        route_cell = tk.Frame(row, bg=row_bg)
        route_cell.grid(row=0, column=0, sticky="nsew", padx=16, pady=13)
        star = tk.Button(
            route_cell,
            text="★" if arrival.is_favorite_route else "☆",
            command=lambda code=arrival.route_code: self.toggle_favorite(code),
            relief="flat",
            borderwidth=0,
            bg=row_bg,
            activebackground=row_bg,
            fg="#E2A900" if arrival.is_favorite_route else "#A7ACB7",
            font=("Segoe UI Symbol", 15),
            cursor="hand2",
        )
        star.pack(side="left", padx=(0, 6))
        bg, fg = route_badge_style(
            arrival.route_code,
            arrival.route_color,
            arrival.route_text_color,
        )
        badge = tk.Label(
            route_cell,
            text=arrival.route_code,
            bg=bg,
            fg=fg,
            font=("Segoe UI Semibold", 12),
            padx=10,
            pady=7,
        )
        badge.pack(side="left")

        direction = tk.Frame(row, bg=row_bg)
        direction.grid(row=0, column=1, sticky="nsew", padx=18, pady=12)
        tk.Label(
            direction,
            text=arrival.route_headsign or "Arah belum tersedia",
            bg=row_bg,
            fg=DARK,
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            direction,
            text=(
                f"Arah {arrival.direction_id}"
                if arrival.direction_id is not None
                else "Arah sedang dicocokkan"
            ),
            bg=row_bg,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        stop_cell = tk.Frame(row, bg=row_bg)
        stop_cell.grid(row=0, column=2, sticky="nsew", padx=18, pady=11)
        tk.Label(
            stop_cell,
            text=arrival.stop_name or "Halte belum tersedia",
            bg=row_bg,
            fg=DARK,
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            stop_cell,
            text=(
                f"{arrival.stop_distance_m:.0f} m · "
                f"{service_label(arrival.service_class)}"
            ),
            bg=row_bg,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        tk.Label(
            row,
            text=arrival.bus_id or "—",
            bg=row_bg,
            fg=DARK,
            font=("Segoe UI", 11),
            anchor="w",
        ).grid(row=0, column=3, sticky="nsew", padx=18)

        estimate = tk.Frame(row, bg=row_bg)
        estimate.grid(row=0, column=4, sticky="nsew", padx=18, pady=10)
        tk.Label(
            estimate,
            text=format_eta(arrival.eta_minutes),
            bg=row_bg,
            fg=HEADER_TEXT,
            font=("Segoe UI Semibold", 15),
            anchor="w",
        ).pack(fill="x")
        status, status_color = display_status(self.engine, arrival)
        tk.Label(
            estimate,
            text=status,
            bg=row_bg,
            fg=status_color,
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", pady=(3, 0))

        tk.Frame(self.rows_frame, bg=LINE, height=1).pack(fill="x")

    def toggle_favorite(self, route_code: str) -> None:
        normalized = normalize_route_code(route_code)
        current = list(self.config.get("routes.favorites", []) or [])
        if isinstance(current, str):
            current = [current]
        by_normalized = {
            normalize_route_code(value): str(value).strip().upper()
            for value in current
            if str(value).strip()
        }
        if normalized in by_normalized:
            del by_normalized[normalized]
        else:
            by_normalized[normalized] = str(route_code).strip().upper()
        set_config_value(self.config, "routes.favorites", list(by_normalized.values()))
        self._update_favorite_summary()
        if self.last_result:
            updated = [
                replace(
                    arrival,
                    is_favorite_route=normalize_route_code(arrival.route_code) in self.config.favorite_routes,
                )
                for arrival in self.last_result.arrivals
            ]
            updated.sort(key=lambda item: (0 if item.is_favorite_route else 1, item.eta_minutes))
            self.last_result.arrivals = updated
            self._render_arrivals(updated)

    def _update_favorite_summary(self) -> None:
        values = sorted(self.config.favorite_routes)
        self.favorite_summary.configure(text=", ".join(values) if values else "Belum ada")

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.configure(text="▶  Lanjut" if self.paused else "Ⅱ  Pause")
        if self.paused:
            if self._poll_after_id is not None:
                try:
                    self.root.after_cancel(self._poll_after_id)
                except Exception:
                    pass
                self._poll_after_id = None
            self.footer_status.configure(text="Pemantauan dijeda. Notifikasi tidak dikirim.")
        else:
            self.footer_status.configure(text="Pemantauan dilanjutkan.")
            self.refresh()
        self._update_tray_menu()

    def mute_one_hour(self) -> None:
        self.muted_until = datetime.now(timezone.utc) + timedelta(hours=1)
        self.footer_status.configure(text="Notifikasi disenyapkan selama 1 jam; monitor tetap diperbarui.")

    def _is_muted(self) -> bool:
        if self.muted_until is None:
            return False
        if datetime.now(timezone.utc) >= self.muted_until:
            self.muted_until = None
            return False
        return True

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Pengaturan TJ Nearby")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=BG)
        dialog.geometry("480x440")
        dialog.resizable(False, False)

        frame = tk.Frame(dialog, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(frame, text="Pengaturan sederhana", bg=PANEL, fg=DARK, font=("Segoe UI Semibold", 16)).pack(
            anchor="w", padx=20, pady=(20, 4)
        )
        tk.Label(
            frame,
            text="Layar utama tetap simpel; detail teknis disimpan di config.yaml.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20)

        tk.Label(frame, text="Mode layanan", bg=PANEL, fg=DARK, font=("Segoe UI Semibold", 10)).pack(
            anchor="w", padx=20, pady=(24, 6)
        )
        current_brt_only = (
            bool(self.config.get("nearby.services.brt.enabled", True))
            and not bool(self.config.get("nearby.services.non_brt.enabled", True))
            and not bool(self.config.get("nearby.services.jaklingko.enabled", True))
        )
        service_mode = tk.StringVar(value="brt" if current_brt_only else "smart")
        tk.Radiobutton(
            frame,
            text="Smart — BRT, non-BRT, dan JakLingko terdekat",
            variable=service_mode,
            value="smart",
            bg=PANEL,
            activebackground=PANEL,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=24)
        tk.Radiobutton(
            frame,
            text="BRT saja",
            variable=service_mode,
            value="brt",
            bg=PANEL,
            activebackground=PANEL,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=24)

        tk.Label(frame, text="Intensitas notifikasi", bg=PANEL, fg=DARK, font=("Segoe UI Semibold", 10)).pack(
            anchor="w", padx=20, pady=(20, 6)
        )
        intensity = tk.StringVar(
            value=str(self.config.get("notification.ready_notification_intensity", "balanced"))
        )
        combo = ttk.Combobox(
            frame,
            textvariable=intensity,
            state="readonly",
            values=("minimal", "balanced", "complete"),
            width=22,
        )
        combo.pack(anchor="w", padx=24)

        autostart = tk.BooleanVar(value=autostart_is_enabled())
        tk.Checkbutton(
            frame,
            text="Mulai otomatis saat login Windows",
            variable=autostart,
            bg=PANEL,
            activebackground=PANEL,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=20, pady=(22, 0))

        def save() -> None:
            brt_only = service_mode.get() == "brt"
            set_config_value(self.config, "nearby.selection_mode", "smart")
            set_config_value(self.config, "nearby.services.brt.enabled", True)
            set_config_value(self.config, "nearby.services.non_brt.enabled", not brt_only)
            set_config_value(self.config, "nearby.services.jaklingko.enabled", not brt_only)
            set_config_value(
                self.config,
                "notification.ready_notification_intensity",
                intensity.get(),
            )
            try:
                set_autostart_enabled(autostart.get())
            except Exception as exc:
                messagebox.showwarning(APP_NAME, f"Autostart belum bisa diubah:\n{exc}", parent=dialog)
            self.mode_label.configure(text="Mode: BRT saja" if brt_only else "Mode: Smart Nearby")
            dialog.destroy()
            self.refresh()

        tk.Button(
            frame,
            text="Simpan",
            command=save,
            relief="flat",
            bg=ACCENT,
            fg="#FFFFFF",
            activebackground="#4C3B9E",
            activeforeground="#FFFFFF",
            font=("Segoe UI Semibold", 10),
            padx=22,
            pady=9,
            cursor="hand2",
        ).pack(anchor="e", padx=20, pady=22)

    def test_notification(self) -> None:
        notifier = TrayNotifier(lambda: self.tray_icon, self.activity_logger)
        delivered = notifier.send(
            "TJ Nearby — uji notifikasi",
            "Notifikasi Windows berhasil dipanggil. Activity log mencatat backend yang dipakai.",
            subtitle="Tes manual v0.4.4",
        )
        if delivered:
            self.footer_status.configure(text="Uji notifikasi dikirim. Cek Notification Center Windows.")
        else:
            self.footer_status.configure(
                text="Backend toast Windows tidak tersedia. Ekspor activity log untuk diagnosis."
            )

    def _diagnostic_report(self) -> str:
        result = self.last_successful_result or self.last_result
        lines = [
            "TJ Nearby Windows activity diagnostic",
            f"version: {APP_VERSION}",
            f"generated_at: {datetime.now().astimezone().isoformat()}",
            f"platform: {platform.platform()}",
            f"config: {self.config.path}",
            f"activity_log: {activity_log_path(self.config.state_dir)}",
            f"checking: {self.checking}",
            f"paused: {self.paused}",
            f"muted: {self._is_muted()}",
            f"selection_mode: {self.config.get('nearby.selection_mode', 'smart')}",
            f"favorites: {sorted(self.config.favorite_routes)}",
            f"legacy_preferred: {sorted(self.config.legacy_preferred_routes)}",
            f"strict_filter_enabled: {bool(self.config.get('routes.strict_filter_enabled', False))}",
            f"strict_filter_routes: {sorted(self.config.preferred_routes)}",
            f"notification_enabled: {bool(self.config.get('notification.enabled', True))}",
            f"notification_mode: {self.config.get('notification.mode', 'ready_window')}",
            f"notification_intensity: {self.config.get('notification.ready_notification_intensity', 'balanced')}",
            f"poll_seconds: {self.config.get('realtime.poll_seconds', 30)}",
            f"check_timeout_seconds: {self.config.get('desktop.check_timeout_seconds', 55)}",
            "",
            "LAST SNAPSHOT",
        ]
        if result is None:
            lines.append("(belum ada snapshot)")
        else:
            lines.extend(
                [
                    f"status: {result.status}",
                    f"message: {result.message}",
                    f"raw_bus_positions: {result.bus_count}",
                    f"nearby_stop_groups: {len(result.nearby_stop_groups)}",
                    f"resolved_arrivals: {len(result.arrivals)}",
                ]
            )
            if result.location:
                decimals = int(self.config.get("privacy.log_coordinate_decimals", 3))
                lines.append(
                    "location: "
                    f"{result.location.latitude:.{decimals}f},"
                    f"{result.location.longitude:.{decimals}f}; "
                    f"accuracy={result.location.accuracy_m:.0f}m; source={result.location.source}"
                )
            lines.append("stops:")
            for group in result.nearby_stop_groups:
                lines.append(
                    f"- {group.name}; distance={group.distance_m:.0f}m; "
                    f"service={group.primary_service_class}; routes={','.join(group.route_codes)}"
                )
            route_counts = Counter(normalize_route_code(a.route_code) for a in result.arrivals)
            lines.append(
                "arrival_routes: "
                + (", ".join(f"{route}={count}" for route, count in route_counts.items()) or "(none)")
            )
            lines.append(
                "scheduled_routes_at_monitored_stops: "
                + (", ".join(result.scheduled_route_codes) or "(none)")
            )
            lines.append(
                "realtime_routes_at_monitored_stops: "
                + (
                    ", ".join(result.realtime_route_codes_at_monitored_stops)
                    or "(none)"
                )
            )
            lines.append(
                "matched_routes: "
                + (", ".join(result.matched_route_codes) or "(none)")
            )
            lines.append(
                "unresolved_realtime_routes: "
                + (", ".join(result.unresolved_realtime_route_codes) or "(none)")
            )
            lines.append("arrivals_and_notification_reasons:")
            for arrival in result.arrivals:
                if self.engine is not None:
                    eligible, reason = self.engine.notification_eligibility(arrival)
                    stage = self.engine.ready_stage(arrival)
                else:
                    eligible, reason, stage = False, "engine-unavailable", None
                lines.append(
                    f"- {arrival.route_code} -> {arrival.route_headsign}; bus={arrival.bus_id}; "
                    f"stop={arrival.stop_name}; eta={arrival.eta_minutes:.1f}m; "
                    f"stops_away={arrival.stops_away}; confidence={arrival.confidence}; "
                    f"age={arrival.bus_data_age_seconds:.0f}s; stage={stage}; "
                    f"notify_eligible={eligible}; reason={reason}"
                )
        lines.extend(["", "ACTIVITY LOG (latest 800 lines)", tail_activity_log(self.config.state_dir, max_lines=800)])
        return "\n".join(lines) + "\n"

    def export_activity_diagnostic(self) -> None:
        desktop = Path.home() / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = desktop / f"tj-nearby-activity-diagnostic-{stamp}.txt"
        try:
            destination.write_text(self._diagnostic_report(), encoding="utf-8")
            self.activity_logger.info("diagnostic.exported path=%s", destination)
            self.footer_status.configure(text=f"Activity log diekspor: {destination.name}")
            messagebox.showinfo(
                APP_NAME,
                f"Activity log dan diagnostic berhasil diekspor ke:\n{destination}",
                parent=self.root,
            )
        except Exception as exc:
            self.activity_logger.exception("diagnostic.export_failed error=%s", exc)
            messagebox.showerror(APP_NAME, f"Gagal mengekspor diagnostic:\n{exc}", parent=self.root)

    def show_monitored_stops(self) -> None:
        result = self.last_successful_result or self.last_result
        groups = result.nearby_stop_groups if result else []
        if not groups:
            messagebox.showinfo(
                APP_NAME,
                "Belum ada daftar halte. Tunggu pembaruan GPS berikutnya.",
                parent=self.root,
            )
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Halte yang dipantau")
        dialog.transient(self.root)
        dialog.configure(bg=BG)
        dialog.geometry("650x480")
        dialog.minsize(520, 360)

        tk.Label(
            dialog,
            text=f"{len(groups)} halte sekitar yang dipantau",
            bg=BG,
            fg=DARK,
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(
            dialog,
            text="Tabel utama menampilkan semua kendaraan realtime yang menuju halte-halte ini.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=(0, 12))

        frame = tk.Frame(dialog, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        text = tk.Text(
            frame,
            wrap="word",
            relief="flat",
            bg=PANEL,
            fg=DARK,
            font=("Segoe UI", 10),
            padx=14,
            pady=12,
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for index, group in enumerate(groups, start=1):
            services = ", ".join(service_label(value) for value in group.service_classes)
            routes = ", ".join(group.route_codes) or "rute belum tersedia"
            text.insert(
                "end",
                f"{index}. {group.name} — {group.distance_m:.0f} m\n"
                f"   Layanan: {services}\n"
                f"   Rute: {routes}\n\n",
            )
        text.configure(state="disabled")

    def _set_sync_state(self, state: str) -> None:
        now_text = datetime.now().astimezone().strftime("%H:%M:%S")
        if state == "live":
            self.sync_chip.configure(
                text=f"●  Live · {now_text}",
                bg="#E9F8F0",
                fg=SUCCESS,
            )
        elif state == "updating":
            self.sync_chip.configure(
                text="↻  Memperbarui…",
                bg="#EEF3FF",
                fg=ACCENT,
            )
        elif state == "stale":
            last = (
                self.last_success_at.astimezone().strftime("%H:%M:%S")
                if self.last_success_at
                else "belum ada"
            )
            self.sync_chip.configure(
                text=f"●  Data lama · {last}",
                bg="#FFF7E8",
                fg=WARNING,
            )
        else:
            self.sync_chip.configure(
                text="●  Pembaruan gagal",
                bg="#FFF0EE",
                fg=DANGER,
            )

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self.refresh_button.configure(state="disabled" if busy else "normal")
        if message:
            self.footer_status.configure(text=message)

    def _show_error(self, title: str, error: object) -> None:
        text = str(error)
        self.footer_status.configure(text=f"{title}: {text}")
        if self.last_result is None:
            self.stop_title.configure(text=title)
            self.stop_subtitle.configure(text=text)

    def _tick_clock(self) -> None:
        self.clock_label.configure(text=datetime.now().astimezone().strftime("%H:%M:%S  |  %d %b %Y"))
        if self.last_success_at is not None and not self.checking and not self.paused:
            age = (datetime.now(timezone.utc) - self.last_success_at).total_seconds()
            poll_seconds = max(5, int(self.config.get("realtime.poll_seconds", 30)))
            if age > max(75, poll_seconds * 2.5):
                self._set_sync_state("stale")
        if not self._closing:
            self.root.after(1000, self._tick_clock)

    def _start_tray(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            return

        icon_path = Path(__file__).resolve().parent / "assets" / "tj_nearby.png"
        if icon_path.exists():
            image = Image.open(icon_path)
        else:
            image = Image.new("RGBA", (64, 64), ACCENT)
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((4, 8, 60, 54), radius=12, fill=ACCENT)
            draw.ellipse((13, 45, 24, 56), fill="white")
            draw.ellipse((40, 45, 51, 56), fill="white")
            draw.rectangle((15, 17, 49, 38), fill="white")

        menu = pystray.Menu(
            pystray.MenuItem("Buka Monitor", lambda _icon, _item: self.root.after(0, self.show_window), default=True),
            pystray.MenuItem("Refresh", lambda _icon, _item: self.root.after(0, self.refresh)),
            pystray.MenuItem(
                lambda _item: "Lanjutkan" if self.paused else "Pause",
                lambda _icon, _item: self.root.after(0, self.toggle_pause),
            ),
            pystray.MenuItem("Senyapkan 1 jam", lambda _icon, _item: self.root.after(0, self.mute_one_hour)),
            pystray.MenuItem("Uji notifikasi", lambda _icon, _item: self.root.after(0, self.test_notification)),
            pystray.MenuItem(
                "Ekspor activity log",
                lambda _icon, _item: self.root.after(0, self.export_activity_diagnostic),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Keluar", lambda _icon, _item: self.root.after(0, self.quit)),
        )
        self.tray_icon = pystray.Icon("tj-nearby", image, APP_NAME, menu)
        self._tray_thread = threading.Thread(target=self.tray_icon.run, name="tj-tray", daemon=True)
        self._tray_thread.start()

    def _update_tray_menu(self) -> None:
        if self.tray_icon is not None:
            try:
                self.tray_icon.update_menu()
            except Exception:
                pass

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_window(self) -> None:
        self.root.withdraw()

    def on_window_close(self) -> None:
        if self.tray_icon is not None:
            self.hide_window()
            if not self._hide_tip_shown:
                self._hide_tip_shown = True
                try:
                    self.tray_icon.notify(
                        "TJ Nearby tetap memantau bus di background. Klik ikon tray untuk membuka monitor.",
                        APP_NAME,
                    )
                except Exception:
                    pass
        else:
            self.quit()

    def quit(self) -> None:
        self._closing = True
        self._cancel_check_watchdog()
        self.activity_logger.info("app.quit")
        if self.engine is not None:
            try:
                self.engine.close()
            except Exception:
                pass
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()


def _ensure_config(path: Path) -> AppConfig:
    if path.exists():
        return load_config(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Prefer a config bundled beside the source tree; PyInstaller places it in
    # _MEIPASS and the build spec copies it there.
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "config.example.yaml",
        Path(__file__).resolve().parent / "assets" / "config.example.yaml",
        Path(__file__).resolve().parents[2] / "config.example.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            path.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
            return load_config(path)
    raise ConfigError(f"Config example not found; expected {path}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TJ Nearby Windows desktop monitor")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--demo", action="store_true", help="Show the GUI with sample arrivals")
    parser.add_argument("--background", action="store_true", help="Start hidden in the system tray")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _set_windows_dpi_awareness()

    guard = SingleInstanceGuard("TJNearbyWindows")
    try:
        acquired = guard.acquire()
    except OSError as exc:
        print(f"WARNING: single-instance guard unavailable: {exc}", file=sys.stderr)
        acquired = True
    if not acquired:
        if not activate_existing_window(APP_NAME):
            duplicate_root = tk.Tk()
            duplicate_root.withdraw()
            messagebox.showinfo(
                APP_NAME,
                "TJ Nearby sudah berjalan di system tray. Klik ikon TJ Nearby dekat jam Windows.",
                parent=duplicate_root,
            )
            duplicate_root.destroy()
        guard.release()
        return 0

    try:
        try:
            config = _ensure_config(Path(args.config).expanduser())
        except ConfigError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        root = tk.Tk()
        MonitorApp(root, config, demo=args.demo, background=args.background)
        root.mainloop()
        return 0
    finally:
        guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
