from __future__ import annotations

from collections import Counter
import logging
from dataclasses import dataclass, field, replace
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .activity_log import setup_activity_logger
from .config import AppConfig
from .eta import estimate_arrivals
from .gtfs import GtfsFeed
from .location import LocationError, get_location
from .models import Arrival, LocationFix, NearbyStop, NearbyStopGroup
from .notify import Notifier
from .realtime import TjApiClient
from .selection import nearby_stop_groups_for_location, service_notification_radius_m
from .service import normalize_route_code
from .state import StateStore


@dataclass(slots=True)
class CheckResult:
    location: LocationFix | None = None
    nearby_stops: list[NearbyStop] = field(default_factory=list)
    nearby_stop_groups: list[NearbyStopGroup] = field(default_factory=list)
    bus_count: int = 0
    arrivals: list[Arrival] = field(default_factory=list)
    notified: list[Arrival] = field(default_factory=list)
    scheduled_route_codes: tuple[str, ...] = ()
    realtime_route_codes_at_monitored_stops: tuple[str, ...] = ()
    matched_route_codes: tuple[str, ...] = ()
    unresolved_realtime_route_codes: tuple[str, ...] = ()
    status: str = "ok"
    message: str = ""


class TJNearbyEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.state = StateStore(config.state_dir / "state.sqlite")
        self.feed = GtfsFeed(config)
        self.feed.load()
        self.api = TjApiClient(config, self.state)
        self.notifier = Notifier(str(config.get("app.name", "TJ Nearby")))
        self.activity_logger = setup_activity_logger(config.state_dir)
        self.activity_logger.info(
            "engine.init version_config=%s selection_mode=%s favorites=%s "
            "legacy_preferred=%s strict_filter=%s",
            config.path,
            config.get("nearby.selection_mode", "smart"),
            sorted(config.favorite_routes),
            sorted(config.legacy_preferred_routes),
            bool(config.get("routes.strict_filter_enabled", False)),
        )

    def close(self) -> None:
        self.api.close()

    def is_active_now(self) -> bool:
        windows = self.config.get("schedule.active_windows", []) or []
        if not windows:
            return True
        timezone_name = str(self.config.get("app.timezone", "Asia/Jakarta"))
        now = datetime.now(ZoneInfo(timezone_name)).time()
        for window in windows:
            try:
                start_text, end_text = str(window).split("-", 1)
                start = datetime.strptime(start_text.strip(), "%H:%M").time()
                end = datetime.strptime(end_text.strip(), "%H:%M").time()
            except ValueError:
                continue
            if start <= end and start <= now <= end:
                return True
            if start > end and (now >= start or now <= end):
                return True
        return False

    def check_once(self, *, dry_run: bool = False, notify: bool = True) -> CheckResult:
        started = time.monotonic()
        self.activity_logger.info(
            "cycle.start notify=%s mode=%s strict_routes=%s",
            notify,
            self.notification_mode(),
            sorted(self.config.preferred_routes),
        )
        if not self.is_active_now():
            self.activity_logger.info("cycle.inactive outside configured active windows")
            return CheckResult(status="inactive", message="Outside configured active windows")

        try:
            location = get_location(self.config)
        except LocationError as exc:
            self.activity_logger.error("cycle.location_error error=%s", exc)
            return CheckResult(status="location_error", message=str(exc))
        self.activity_logger.info(
            "cycle.location source=%s accuracy_m=%.0f lat=%.4f lon=%.4f",
            location.source,
            location.accuracy_m,
            location.latitude,
            location.longitude,
        )

        max_accuracy = float(self.config.get("location.max_accuracy_m", 250))
        if location.accuracy_m > max_accuracy:
            self.activity_logger.warning(
                "cycle.inaccurate_location accuracy_m=%.0f limit_m=%.0f",
                location.accuracy_m,
                max_accuracy,
            )
            return CheckResult(
                location=location,
                status="inaccurate_location",
                message=f"Location accuracy {location.accuracy_m:.0f} m exceeds limit {max_accuracy:.0f} m",
            )

        stop_groups = nearby_stop_groups_for_location(
            self.feed,
            self.config,
            location.latitude,
            location.longitude,
        )
        nearby_stops = [member for group in stop_groups for member in group.members]
        self.activity_logger.info(
            "cycle.stops groups=%d gtfs_stop_records=%d groups_detail=%s",
            len(stop_groups),
            len(nearby_stops),
            "; ".join(
                f"{group.name}:{group.distance_m:.0f}m:{group.primary_service_class}:"
                f"{','.join(group.route_codes[:12])}"
                for group in stop_groups
            ),
        )
        result = CheckResult(
            location=location,
            nearby_stops=nearby_stops,
            nearby_stop_groups=stop_groups,
        )
        if not nearby_stops:
            result.status = "no_stops"
            result.message = "No GTFS stops found inside the configured radius"
            self.activity_logger.warning("cycle.no_stops")
            return result

        if not bool(self.config.get("realtime.enabled", True)):
            result.status = "static_only"
            result.message = "Realtime API is disabled"
            return result

        try:
            buses = self.api.get_buses(
                location.latitude,
                location.longitude,
                float(self.config.get("realtime.search_radius_km", 3)),
            )
        except Exception as exc:
            result.status = "realtime_error"
            result.message = str(exc)
            self.activity_logger.exception("cycle.realtime_error error=%s", exc)
            return result

        result.bus_count = len(buses)
        raw_routes = Counter(normalize_route_code(bus.route_code) or "(blank)" for bus in buses)
        self.activity_logger.info(
            "cycle.realtime buses=%d routes=%s",
            len(buses),
            ",".join(f"{route}:{count}" for route, count in raw_routes.most_common(40)),
        )
        # All matching buses remain in result.arrivals. Notification filtering is
        # deliberately separate so the application can keep tracking everything.
        result.arrivals = estimate_arrivals(self.feed, nearby_stops, buses, self.config)
        result.arrivals = self._attach_stop_context(result.arrivals, stop_groups)
        result.arrivals = self._attach_journey_state(result.arrivals)

        scheduled_routes = {
            normalize_route_code(route_code)
            for group in stop_groups
            for route_code in group.route_codes
            if normalize_route_code(route_code)
        }
        realtime_routes = set(raw_routes) - {"(blank)"}
        matched_routes = {
            normalize_route_code(arrival.route_code)
            for arrival in result.arrivals
            if normalize_route_code(arrival.route_code)
        }
        realtime_at_monitored_stops = scheduled_routes & realtime_routes
        unresolved_realtime_routes = realtime_at_monitored_stops - matched_routes
        result.scheduled_route_codes = tuple(sorted(scheduled_routes))
        result.realtime_route_codes_at_monitored_stops = tuple(
            sorted(realtime_at_monitored_stops)
        )
        result.matched_route_codes = tuple(sorted(matched_routes))
        result.unresolved_realtime_route_codes = tuple(
            sorted(unresolved_realtime_routes)
        )
        self.activity_logger.info(
            "cycle.coverage monitored_groups=%d monitored_stop_ids=%d "
            "scheduled_routes=%s realtime_routes_at_monitored_stops=%s "
            "matched_routes=%s unresolved_realtime_routes=%s",
            len(stop_groups),
            len(nearby_stops),
            ",".join(sorted(scheduled_routes)) or "(none)",
            ",".join(sorted(realtime_at_monitored_stops)) or "(none)",
            ",".join(sorted(matched_routes)) or "(none)",
            ",".join(sorted(unresolved_realtime_routes)) or "(none)",
        )
        result.arrivals.sort(
            key=lambda arrival: (
                0 if arrival.is_favorite_route else 1,
                arrival.eta_minutes,
                arrival.stop_distance_m,
            )
        )
        arrival_routes = Counter(normalize_route_code(item.route_code) for item in result.arrivals)
        self.activity_logger.info(
            "cycle.arrivals count=%d routes=%s elapsed_s=%.2f",
            len(result.arrivals),
            ",".join(f"{route}:{count}" for route, count in arrival_routes.most_common(40)),
            time.monotonic() - started,
        )
        if notify and bool(self.config.get("notification.enabled", True)):
            result.notified = self._notify_due(result.arrivals, dry_run=dry_run)
        self.activity_logger.info(
            "cycle.finish status=%s arrivals=%d notified=%d elapsed_s=%.2f",
            result.status,
            len(result.arrivals),
            len(result.notified),
            time.monotonic() - started,
        )
        return result

    def _attach_stop_context(
        self,
        arrivals: list[Arrival],
        stop_groups: list[NearbyStopGroup],
    ) -> list[Arrival]:
        """Attach service and route-favorite context for notifications and GUI output."""
        service_by_stop_id: dict[str, str] = {}
        for group in stop_groups:
            for member in group.members:
                service_by_stop_id[member.stop.stop_id] = group.primary_service_class
        favorites = self.config.favorite_routes
        updated: list[Arrival] = []
        for arrival in arrivals:
            route_color, route_text_color = self.feed.route_style_for_code(arrival.route_code)
            updated.append(
                replace(
                    arrival,
                    service_class=service_by_stop_id.get(arrival.stop_id, "non_brt"),
                    is_favorite_route=normalize_route_code(arrival.route_code) in favorites,
                    route_color=route_color,
                    route_text_color=route_text_color,
                )
            )
        return updated

    def notify_due(self, arrivals: list[Arrival], *, dry_run: bool = False) -> list[Arrival]:
        """Send notifications for an already-rendered arrival snapshot.

        Desktop GUIs call this after applying the same snapshot to the screen so
        a toast can never represent newer data than the visible monitor.
        """
        if not bool(self.config.get("notification.enabled", True)):
            return []
        return self._notify_due(arrivals, dry_run=dry_run)

    def notification_stop_radius_m(self, arrival: Arrival) -> float:
        """Return the walkable notification radius for the arrival's stop class."""
        if str(self.config.get("nearby.selection_mode", "smart")).strip().lower() == "nearest":
            return float(self.config.get("notification.ready_max_stop_distance_m", 500))
        return service_notification_radius_m(self.config, arrival.service_class)

    def _attach_journey_state(self, arrivals: list[Arrival]) -> list[Arrival]:
        """Attach a persistent journey epoch to every tracked arrival.

        The resolver is route-agnostic: it works for 4D, 6H, B25, or any other
        route. One representative per physical bus + route updates the persistent
        state, then the same epoch is copied to every nearby-stop projection of
        that bus. Opposite directions from different buses remain independent.
        """
        if (
            not arrivals
            or not bool(self.config.get("direction.track_turnarounds", True))
            or not hasattr(self.state, "resolve_vehicle_journey")
        ):
            return arrivals

        groups: dict[tuple[str, str], list[Arrival]] = {}
        for arrival in arrivals:
            key = (arrival.bus_id, arrival.route_code.casefold())
            groups.setdefault(key, []).append(arrival)

        updated: list[Arrival] = []
        confidence_rank = {"high": 0, "medium": 1, "low": 2}
        max_age_hours = float(
            self.config.get("direction.journey_state_max_age_hours", 12)
        )
        for group in groups.values():
            representative = min(
                group,
                key=lambda item: (
                    1 if item.direction_ambiguous else 0,
                    confidence_rank.get(item.confidence, 3),
                    -item.direction_score,
                    item.bus_data_age_seconds,
                    item.eta_minutes,
                ),
            )
            resolution = self.state.resolve_vehicle_journey(
                bus_id=representative.bus_id,
                route_code=representative.route_code,
                trip_id=representative.trip_id,
                direction_id=representative.direction_id,
                headsign=representative.route_headsign,
                max_state_age_hours=max_age_hours,
            )
            representative_signature = (
                representative.direction_id,
                " ".join(representative.route_headsign.casefold().split()),
            )
            for arrival in group:
                signature = (
                    arrival.direction_id,
                    " ".join(arrival.route_headsign.casefold().split()),
                )
                transition = resolution.transition
                # A single physical bus cannot actively travel in two opposite
                # directions in the same poll. Keep the weaker projection visible
                # for diagnostics, but prevent it from becoming a banner.
                if signature != representative_signature:
                    transition = "competing-direction-same-vehicle"
                updated.append(
                    replace(
                        arrival,
                        journey_epoch=resolution.epoch,
                        journey_transition=transition,
                        previous_direction_label=resolution.previous_direction_label,
                    )
                )
        return sorted(updated, key=lambda item: item.eta_minutes)

    def notification_mode(self) -> str:
        mode = str(self.config.get("notification.mode", "ready_window")).strip().lower()
        supported = {"ready_window", "all_arrivals", "leave_now"}
        return mode if mode in supported else "ready_window"

    def notification_intensity(self) -> str:
        """Return the ready-window preset used until the GUI is available."""
        value = str(
            self.config.get("notification.ready_notification_intensity", "balanced")
        ).strip().lower()
        supported = {"minimal", "balanced", "complete"}
        return value if value in supported else "balanced"

    def ready_enabled_stages(self) -> tuple[str, ...]:
        """Resolve the three user-facing alert stages.

        ``stops_away`` counts the target stop itself. Therefore:
        - 3 = two intermediate stops remain before the target;
        - 2 = one intermediate stop remains before the target;
        - 1 = the target is the next stop.
        """
        custom = self.config.get("notification.ready_enabled_stages", None)
        aliases = {
            "two_stops_before": "two_stops_before",
            "two_before": "two_stops_before",
            "2": "two_stops_before",
            "one_stop_before": "one_stop_before",
            "one_before": "one_stop_before",
            "1": "one_stop_before",
            "target_is_next": "target_is_next",
            "target_next": "target_is_next",
            "next": "target_is_next",
        }
        if isinstance(custom, (list, tuple)) and custom:
            resolved: list[str] = []
            for item in custom:
                stage = aliases.get(str(item).strip().lower())
                if stage and stage not in resolved:
                    resolved.append(stage)
            if resolved:
                return tuple(resolved)

        presets = {
            "minimal": ("target_is_next",),
            "balanced": ("two_stops_before", "target_is_next"),
            "complete": (
                "two_stops_before",
                "one_stop_before",
                "target_is_next",
            ),
        }
        return presets[self.notification_intensity()]

    @staticmethod
    def ready_stage(arrival: Arrival) -> str | None:
        if arrival.stops_away == 3:
            return "two_stops_before"
        if arrival.stops_away == 2:
            return "one_stop_before"
        if arrival.stops_away == 1:
            return "target_is_next"
        if arrival.stops_away is None:
            return "eta_fallback"
        return None

    def _direction_eligibility(self, arrival: Arrival) -> tuple[bool, str]:
        if arrival.journey_transition == "competing-direction-same-vehicle":
            return False, "competing-direction-same-vehicle"
        if arrival.direction_ambiguous or arrival.direction_status == "ambiguous":
            return False, "direction-ambiguous"
        minimum_confidence = str(
            self.config.get("notification.minimum_direction_confidence", "high")
        ).strip().lower()
        confidence_rank = {"low": 0, "medium": 1, "high": 2}
        required_rank = confidence_rank.get(minimum_confidence, 2)
        if confidence_rank.get(arrival.confidence, 0) < required_rank:
            return False, "direction-confidence-below-minimum"
        return True, "direction-confirmed"

    def _ready_base_eligibility(self, arrival: Arrival) -> tuple[bool, str]:
        direction_ok, direction_reason = self._direction_eligibility(arrival)
        if not direction_ok:
            return False, direction_reason

        max_stop_distance = self.notification_stop_radius_m(arrival)
        if arrival.stop_distance_m > max_stop_distance:
            return False, "target-stop-too-far-to-walk"

        max_data_age = float(
            self.config.get("notification.ready_max_bus_data_age_seconds", 90)
        )
        if arrival.bus_data_age_seconds > max_data_age:
            return False, "bus-position-too-old"

        if arrival.stops_away is not None and arrival.stops_away < 1:
            return False, "target-at-stop-or-passed"
        return True, "ready-base-confirmed"

    def notification_eligibility(self, arrival: Arrival) -> tuple[bool, str]:
        """Return whether an arrival should produce a macOS banner.

        Tracking is not affected by this decision. Every resolved arrival remains
        available to the menu status, CLI, and diagnostics.
        """
        direction_ok, direction_reason = self._direction_eligibility(arrival)
        if not direction_ok:
            return False, direction_reason

        mode = self.notification_mode()
        if mode == "all_arrivals":
            maximum = float(self.config.get("notification.all_arrivals_max_eta_minutes", 120))
            if arrival.eta_minutes > maximum:
                return False, "eta-above-all-arrivals-maximum"
            return True, "new-confirmed-approaching-bus"

        if mode == "leave_now":
            min_eta = float(self.config.get("notification.min_eta_minutes", 2))
            max_eta = float(self.config.get("notification.max_eta_minutes", 15))
            buffer_minutes = float(self.config.get("notification.leave_buffer_minutes", 3))
            margin = arrival.eta_minutes - arrival.walking_minutes
            if arrival.eta_minutes < min_eta:
                return False, "eta-below-minimum"
            if arrival.eta_minutes > max_eta:
                return False, "eta-above-maximum"
            if margin < 0:
                return False, "too-late-to-walk"
            if margin > buffer_minutes:
                return False, "too-early-to-leave"
            return True, "due-now"

        base_ok, base_reason = self._ready_base_eligibility(arrival)
        if not base_ok:
            return False, base_reason

        stage = self.ready_stage(arrival)
        margin = arrival.eta_minutes - arrival.walking_minutes
        if stage and stage != "eta_fallback":
            if stage not in self.ready_enabled_stages():
                return False, f"ready-stage-disabled:{stage}"
            if stage == "two_stops_before":
                minimum_margin = float(
                    self.config.get("notification.ready_min_margin_minutes", 2)
                )
                if margin < minimum_margin:
                    return False, "two-stops-before-walking-margin-too-small"
            if stage == "target_is_next":
                return True, "target-is-next-last-chance"
            return True, f"ready-stage:{stage}"

        if arrival.stops_away is not None:
            return False, "outside-three-stage-window"

        if not bool(
            self.config.get("notification.ready_fallback_to_eta_when_stops_unknown", True)
        ):
            return False, "stops-away-unknown"

        fallback_min_margin = float(
            self.config.get("notification.ready_fallback_min_margin_minutes", 2)
        )
        fallback_max_margin = float(
            self.config.get("notification.ready_fallback_max_margin_minutes", 8)
        )
        fallback_max_eta = float(
            self.config.get("notification.ready_fallback_max_eta_minutes", 15)
        )
        if arrival.eta_minutes > fallback_max_eta:
            return False, "eta-fallback-too-early"
        if margin < fallback_min_margin:
            return False, "eta-fallback-too-late"
        if margin > fallback_max_margin:
            return False, "eta-fallback-too-early"
        return True, "ready-window-eta-fallback"

    def arrival_timing_status(self, arrival: Arrival) -> tuple[str, str]:
        """Legacy all-arrivals wording based on ETA minus walking time."""
        margin = arrival.eta_minutes - arrival.walking_minutes
        too_late_margin = float(
            self.config.get("notification.timing_too_late_margin_minutes", 1)
        )
        leave_now_margin = float(
            self.config.get("notification.timing_leave_now_margin_minutes", 5)
        )
        if leave_now_margin < too_late_margin:
            leave_now_margin = too_late_margin

        if margin <= too_late_margin:
            return "likely_missed", "kemungkinan tidak terkejar"
        if margin <= leave_now_margin:
            return "leave_now", "berangkat sekarang"
        return "plenty_time", "masih cukup jauh"

    def arrival_ready_status(self, arrival: Arrival) -> tuple[str, str]:
        """Describe a tracked bus under the v0.3.2 three-stage policy."""
        eligible, reason = self.notification_eligibility(arrival)
        if arrival.direction_ambiguous:
            return "direction_ambiguous", "arah belum pasti"
        if reason == "bus-position-too-old":
            return "stale", "data posisi sudah lama"

        stage = self.ready_stage(arrival)
        if stage == "two_stops_before":
            if eligible:
                return "two_stops_before", "bersiap-siap"
            return "two_stops_before_tracking", "2 halte perantara — dipantau"
        if stage == "one_stop_before":
            if eligible:
                return "one_stop_before", "berangkat sekarang"
            return "one_stop_before_tracking", "1 halte perantara — dipantau"
        if stage == "target_is_next":
            if eligible:
                return "target_is_next", "bus sudah sangat dekat"
            return "target_is_next_tracking", "pemberhentian berikutnya — dipantau"
        if arrival.stops_away is not None and arrival.stops_away > 3:
            return "tracking", "masih dipantau"
        if eligible and reason == "ready-window-eta-fallback":
            return "eta_fallback", "bersiap berangkat"
        return "tracking", "masih dipantau"

    def notification_label(self, arrival: Arrival) -> tuple[str, str]:
        if self.notification_mode() == "ready_window":
            return self.arrival_ready_status(arrival)
        return self.arrival_timing_status(arrival)

    @staticmethod
    def _occurrence_base_key(arrival: Arrival) -> str:
        trip = arrival.trip_id or "no-trip"
        headsign = " ".join(arrival.route_headsign.casefold().split())
        stop_name = " ".join(arrival.stop_name.casefold().split())
        return "|".join(
            [
                arrival.bus_id,
                f"journey:{arrival.journey_epoch}",
                trip,
                arrival.route_code.casefold(),
                str(arrival.direction_id),
                headsign,
                stop_name,
            ]
        )

    def _occurrence_key(self, arrival: Arrival) -> str:
        base = self._occurrence_base_key(arrival)
        if self.notification_mode() == "ready_window":
            stage = self.ready_stage(arrival) or "tracking"
            return f"{base}|stage:{stage}"
        return base

    @staticmethod
    def _physical_occurrence_key(arrival: Arrival) -> str:
        trip = arrival.trip_id or "no-trip"
        headsign = " ".join(arrival.route_headsign.casefold().split())
        return "|".join(
            [
                arrival.bus_id,
                arrival.route_code.casefold(),
                f"journey:{arrival.journey_epoch}",
                trip,
                str(arrival.direction_id),
                headsign,
            ]
        )

    @staticmethod
    def _lead_group_key(arrival: Arrival) -> str:
        headsign = " ".join(arrival.route_headsign.casefold().split())
        stop_name = " ".join(arrival.stop_name.casefold().split())
        return "|".join(
            [
                arrival.route_code.casefold(),
                str(arrival.direction_id),
                headsign,
                stop_name,
            ]
        )

    def _notification_candidates(self, arrivals: list[Arrival]) -> list[Arrival]:
        """Choose a clean set of banner candidates while tracking remains complete."""
        selected: dict[str, Arrival] = {}
        confidence_rank = {"high": 0, "medium": 1, "low": 2}
        for arrival in arrivals:
            key = self._physical_occurrence_key(arrival)
            current = selected.get(key)
            score = (
                confidence_rank.get(arrival.confidence, 3),
                arrival.stop_distance_m,
                arrival.eta_minutes,
            )
            if current is None:
                selected[key] = arrival
                continue
            current_score = (
                confidence_rank.get(current.confidence, 3),
                current.stop_distance_m,
                current.eta_minutes,
            )
            if score < current_score:
                selected[key] = arrival

        physical = list(selected.values())
        if self.notification_mode() != "ready_window" or not bool(
            self.config.get("notification.ready_notify_lead_bus_only", True)
        ):
            return sorted(
                physical,
                key=lambda item: (0 if item.is_favorite_route else 1, item.eta_minutes),
            )

        leads: dict[str, Arrival] = {}
        for arrival in physical:
            base_ok, _reason = self._ready_base_eligibility(arrival)
            if not base_ok:
                continue
            key = self._lead_group_key(arrival)
            current = leads.get(key)
            stop_rank = arrival.stops_away if arrival.stops_away is not None else 999
            score = (stop_rank, arrival.eta_minutes)
            if current is None:
                leads[key] = arrival
                continue
            current_rank = current.stops_away if current.stops_away is not None else 999
            current_score = (current_rank, current.eta_minutes)
            if score < current_score:
                leads[key] = arrival
        return sorted(
            leads.values(),
            key=lambda item: (0 if item.is_favorite_route else 1, item.eta_minutes),
        )

    def _stage_interval_allows(self, arrival: Arrival) -> bool:
        if self.notification_mode() != "ready_window":
            return True
        stage = self.ready_stage(arrival)
        if not stage or stage == "eta_fallback":
            return True
        if stage == "target_is_next" and bool(
            self.config.get("notification.ready_always_send_final_stage", True)
        ):
            return True

        minimum_seconds = float(
            self.config.get("notification.ready_min_seconds_between_stages", 90)
        )
        if minimum_seconds <= 0:
            return True
        seconds_since = None
        if hasattr(self.state, "seconds_since_latest"):
            prefix = f"{self._occurrence_base_key(arrival)}|stage:"
            seconds_since = self.state.seconds_since_latest(prefix)
        return seconds_since is None or seconds_since >= minimum_seconds

    def _notification_message(self, arrival: Arrival) -> str:
        stage = self.ready_stage(arrival) if self.notification_mode() == "ready_window" else None
        distance_text = (
            f"{arrival.stop_distance_m:.0f} m dari lokasi lo "
            f"(jalan ±{arrival.walking_minutes:.0f} menit)."
        )
        if stage == "two_stops_before":
            return f"2 halte perantara sebelum Halte {arrival.stop_name} · {distance_text}"
        if stage == "one_stop_before":
            return f"1 halte perantara sebelum Halte {arrival.stop_name} · {distance_text}"
        if stage == "target_is_next":
            return (
                f"Pemberhentian berikutnya Halte {arrival.stop_name} · "
                f"kesempatan terakhir · {distance_text}"
            )
        if arrival.stops_away is None:
            return f"Menuju Halte {arrival.stop_name} · {distance_text}"
        if arrival.stops_away <= 1:
            return f"1 halte lagi · Menuju Halte {arrival.stop_name} · {distance_text}"
        return (
            f"{arrival.stops_away} halte lagi · Menuju Halte {arrival.stop_name} · "
            f"{distance_text}"
        )

    def _notify_due(self, arrivals: list[Arrival], *, dry_run: bool) -> list[Arrival]:
        cooldown = float(self.config.get("notification.cooldown_minutes", 180))
        maximum = int(self.config.get("notification.max_notifications_per_cycle", 0))
        sent: list[Arrival] = []
        candidates = self._notification_candidates(arrivals)
        activity_logger = getattr(self, "activity_logger", logging.getLogger("tj_nearby.activity.null"))
        activity_logger.info(
            "notify.start arrivals=%d candidates=%d mode=%s intensity=%s enabled=%s",
            len(arrivals),
            len(candidates),
            self.notification_mode(),
            self.notification_intensity(),
            bool(self.config.get("notification.enabled", True)),
        )

        candidate_ids = {id(item) for item in candidates}
        for arrival in arrivals[:30]:
            eligible, reason = self.notification_eligibility(arrival)
            activity_logger.info(
                "notify.inspect route=%s bus=%s stop=%s eta=%.1f stops_away=%s "
                "confidence=%s candidate=%s eligible=%s reason=%s age_s=%.0f",
                arrival.route_code,
                arrival.bus_id,
                arrival.stop_name,
                arrival.eta_minutes,
                arrival.stops_away,
                arrival.confidence,
                id(arrival) in candidate_ids,
                eligible,
                reason,
                arrival.bus_data_age_seconds,
            )

        for arrival in candidates:
            eligible, reason = self.notification_eligibility(arrival)
            if not eligible:
                activity_logger.info(
                    "notify.skip route=%s bus=%s reason=%s",
                    arrival.route_code,
                    arrival.bus_id,
                    reason,
                )
                continue
            key = self._occurrence_key(arrival)
            if not self.state.can_notify(key, cooldown):
                activity_logger.info(
                    "notify.skip route=%s bus=%s reason=cooldown key=%s",
                    arrival.route_code,
                    arrival.bus_id,
                    key,
                )
                continue
            if not self._stage_interval_allows(arrival):
                activity_logger.info(
                    "notify.skip route=%s bus=%s reason=stage-interval",
                    arrival.route_code,
                    arrival.bus_id,
                )
                continue

            direction = arrival.route_headsign.strip() or f"arah {arrival.direction_id}"
            if arrival.direction_status == "estimated":
                direction = f"perkiraan {direction}"
            title = f"{arrival.route_code} → {direction} · {arrival.eta_minutes:.0f} menit"
            _status_code, status_label = self.notification_label(arrival)
            subtitle = f"Bus {arrival.bus_id} · {status_label}"
            message = self._notification_message(arrival)

            if dry_run:
                print(f"[DRY RUN] {title} — {subtitle}: {message}")
            else:
                delivered = self.notifier.send(title, message, subtitle=subtitle)
                if delivered is False:
                    activity_logger.error(
                        "notify.delivery_failed route=%s bus=%s",
                        arrival.route_code,
                        arrival.bus_id,
                    )
                    continue
                self.state.mark_notified(key)
            sent.append(arrival)
            activity_logger.info(
                "notify.sent route=%s bus=%s stop=%s stage=%s dry_run=%s",
                arrival.route_code,
                arrival.bus_id,
                arrival.stop_name,
                self.ready_stage(arrival),
                dry_run,
            )
            if maximum > 0 and len(sent) >= maximum:
                break
        activity_logger.info("notify.finish sent=%d", len(sent))
        return sent
