from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config, set_config_value
from .engine import CheckResult, TJNearbyEngine
from .gtfs import GtfsFeed
from .location import get_location
from .realtime import TjApiClient
from .selection import nearby_stop_groups_for_location
from .service import normalize_route_code, service_label
from .state import StateStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tj-nearby", description="TransJakarta nearby bus notifier")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to YAML config")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="Download and validate the GTFS feed")
    sub.add_parser("doctor", help="Check GTFS, location, authentication, and bus API")
    sub.add_parser("nearby", help="Print nearby public-stop groups from the current location")
    sub.add_parser("location-auto", help="Use Windows Location Service or macOS Core Location")
    sub.add_parser("location-manual", help="Use the saved manual coordinates")
    sub.add_parser("notification-ready-window", help="Track every bus and enable the balanced three-stage policy")
    sub.add_parser("notification-all", help="Notify once for every newly detected approaching bus")
    sub.add_parser("notification-leave-now", help="Only notify when it is time to walk to the stop")
    favorite = sub.add_parser("favorite-route", help="Add a route favorite such as 4D or JAK 81")
    favorite.add_argument("route_code")
    unfavorite = sub.add_parser("unfavorite-route", help="Remove a route favorite")
    unfavorite.add_argument("route_code")
    sub.add_parser("list-favorites", help="List route favorites")
    once = sub.add_parser("once", help="Run one complete arrival/notifier cycle")
    once.add_argument("--dry-run", action="store_true", help="Print notifications without sending them")
    run = sub.add_parser("run", help="Run continuously in the foreground")
    run.add_argument("--dry-run", action="store_true", help="Print notifications without sending them")
    return parser


def _print_result(result: CheckResult) -> None:
    print(f"status: {result.status}")
    if result.message:
        print(f"message: {result.message}")
    if result.location:
        loc = result.location
        print(
            f"location: {loc.latitude:.5f}, {loc.longitude:.5f} "
            f"accuracy={loc.accuracy_m:.0f}m source={loc.source}"
        )
    if result.nearby_stop_groups:
        print("nearby stops:")
        for group in result.nearby_stop_groups:
            routes = ", ".join(group.route_codes) or "no scheduled routes"
            ids = ",".join(member.stop.stop_id for member in group.members)
            suffix = f" | {len(group.members)} GTFS IDs" if len(group.members) > 1 else ""
            favorite = f" | favorites: {', '.join(group.favorite_route_codes)}" if group.favorite_route_codes else ""
            print(
                f"  - {group.name} [{ids}] — {group.distance_m:.0f} m | "
                f"service: {service_label(group.primary_service_class)} | routes: {routes}{favorite}{suffix}"
            )
    elif result.nearby_stops:
        print("nearby stops:")
        for item in result.nearby_stops:
            print(f"  - {item.stop.name} [{item.stop.stop_id}] — {item.distance_m:.0f} m")
    print(f"realtime buses: {result.bus_count}")
    if result.arrivals:
        print("top arrivals:")
        for arrival in result.arrivals[:10]:
            stops = "?" if arrival.stops_away is None else str(arrival.stops_away)
            favorite_mark = "★ " if arrival.is_favorite_route else ""
            print(
                f"  - {favorite_mark}{arrival.route_code} → {arrival.route_headsign} | "
                f"{arrival.stop_name} ({service_label(arrival.service_class)}) | "
                f"ETA {arrival.eta_minutes:.1f}m | walk {arrival.walking_minutes:.1f}m | "
                f"{stops} stops ({arrival.stops_away_source}) | "
                f"{arrival.confidence}/{arrival.direction_status} | age={arrival.bus_data_age_seconds:.0f}s | "
                f"score={arrival.direction_score} | evidence={','.join(arrival.direction_evidence)}"
            )
    print(f"notifications this cycle: {len(result.notified)}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


    if args.command == "location-auto":
        set_config_value(config, "location.mode", "auto")
        # Existing manual coordinates remain available for explicit debugging,
        # but are never used silently while automatic mode is selected.
        set_config_value(config, "location.allow_manual_fallback", False)
        set_config_value(config, "nearby.cluster_radius_m", 35)
        print(f"Automatic location enabled in {config.path}")
        print("Open the TJ Nearby desktop app and allow Location Services when prompted.")
        return 0

    if args.command == "location-manual":
        set_config_value(config, "location.mode", "manual")
        print(f"Saved manual location enabled in {config.path}")
        return 0

    if args.command == "notification-ready-window":
        set_config_value(config, "notification.mode", "ready_window")
        set_config_value(config, "notification.ready_notification_intensity", "balanced")
        set_config_value(config, "notification.ready_notify_lead_bus_only", True)
        set_config_value(config, "notification.ready_min_seconds_between_stages", 90)
        set_config_value(config, "notification.ready_always_send_final_stage", True)
        set_config_value(config, "notification.ready_min_margin_minutes", 2)
        set_config_value(config, "notification.ready_max_stop_distance_m", 500)
        set_config_value(config, "notification.ready_max_bus_data_age_seconds", 90)
        set_config_value(config, "notification.ready_fallback_to_eta_when_stops_unknown", True)
        set_config_value(config, "notification.ready_fallback_min_margin_minutes", 2)
        set_config_value(config, "notification.ready_fallback_max_margin_minutes", 8)
        set_config_value(config, "notification.ready_fallback_max_eta_minutes", 15)
        set_config_value(config, "notification.cooldown_minutes", 180)
        set_config_value(config, "notification.max_notifications_per_cycle", 0)
        set_config_value(config, "notification.minimum_direction_confidence", "high")
        set_config_value(config, "direction.ambiguity_score_margin", 20)
        print(
            f"Ready-window balanced enabled: all buses tracked, lead bus alerts at "
            f"preparation and final stages: {config.path}"
        )
        return 0

    if args.command == "notification-all":
        set_config_value(config, "notification.mode", "all_arrivals")
        set_config_value(config, "notification.all_arrivals_max_eta_minutes", 120)
        set_config_value(config, "notification.cooldown_minutes", 180)
        set_config_value(config, "notification.max_notifications_per_cycle", 0)
        set_config_value(config, "notification.minimum_direction_confidence", "high")
        set_config_value(config, "direction.ambiguity_score_margin", 20)
        print(f"Every newly detected approaching bus will notify once: {config.path}")
        return 0

    if args.command == "notification-leave-now":
        set_config_value(config, "notification.mode", "leave_now")
        set_config_value(config, "notification.max_notifications_per_cycle", 1)
        print(f"Leave-now notification mode enabled: {config.path}")
        return 0


    if args.command in {"favorite-route", "unfavorite-route", "list-favorites"}:
        stored = config.get("routes.favorites", []) or []
        if isinstance(stored, str):
            stored = [stored]
        display_by_normalized = {
            normalize_route_code(value): str(value).strip().upper()
            for value in stored
            if str(value).strip()
        }
        if args.command == "favorite-route":
            normalized = normalize_route_code(args.route_code)
            if not normalized:
                print("Route code cannot be empty", file=sys.stderr)
                return 2
            display_by_normalized[normalized] = str(args.route_code).strip().upper()
            set_config_value(config, "routes.favorites", list(display_by_normalized.values()))
            print(f"Favorite route added: {display_by_normalized[normalized]}")
            return 0
        if args.command == "unfavorite-route":
            normalized = normalize_route_code(args.route_code)
            removed = display_by_normalized.pop(normalized, None)
            set_config_value(config, "routes.favorites", list(display_by_normalized.values()))
            print(f"Favorite route removed: {removed or str(args.route_code).strip().upper()}")
            return 0
        if not display_by_normalized:
            print("No favorite routes configured")
            return 0
        print("Favorite routes:")
        for value in display_by_normalized.values():
            print(f"  - {value}")
        return 0

    if args.command == "bootstrap":
        feed = GtfsFeed(config)
        path = feed.ensure_downloaded(force=True)
        feed.load()
        print(f"GTFS ready: {path}")
        print(f"stops={len(feed.stops)} routes={len(feed.routes)} variants={len(feed.variants)}")
        return 0

    if args.command == "doctor":
        failures = 0
        print("[1/4] GTFS")
        try:
            feed = GtfsFeed(config)
            feed.load()
            print(f"  OK — {len(feed.stops)} stops, {len(feed.routes)} routes")
        except Exception as exc:
            failures += 1
            print(f"  FAIL — {exc}")
        print("[2/4] Location")
        try:
            location = get_location(config)
            print(
                f"  OK — {location.latitude:.5f}, {location.longitude:.5f}; "
                f"accuracy {location.accuracy_m:.0f} m"
            )
        except Exception as exc:
            location = None
            failures += 1
            print(f"  FAIL — {exc}")
        print("[3/4] Realtime authentication")
        state = StateStore(config.state_dir / "state.sqlite")
        api = TjApiClient(config, state)
        try:
            api.authenticate()
            print(f"  OK — app version {api.app_version}")
        except Exception as exc:
            failures += 1
            print(f"  FAIL — {exc}")
        print("[4/4] Nearby buses")
        try:
            if location is None:
                raise RuntimeError("Skipped because location failed")
            buses = api.get_buses(
                location.latitude,
                location.longitude,
                float(config.get("realtime.search_radius_km", 3)),
            )
            print(f"  OK — {len(buses)} buses returned")
        except Exception as exc:
            failures += 1
            print(f"  FAIL — {exc}")
        finally:
            api.close()
        return 1 if failures else 0

    if args.command == "nearby":
        feed = GtfsFeed(config)
        feed.load()
        location = get_location(config)
        nearby = nearby_stop_groups_for_location(
            feed,
            config,
            location.latitude,
            location.longitude,
        )
        print(
            f"Location: {location.latitude:.5f}, {location.longitude:.5f} "
            f"(accuracy {location.accuracy_m:.0f} m)"
        )
        for group in nearby:
            ids = ", ".join(member.stop.stop_id for member in group.members)
            suffix = f" | GTFS IDs: {ids}" if len(group.members) > 1 else ""
            favorite = f" | favorites: {', '.join(group.favorite_route_codes)}" if group.favorite_route_codes else ""
            print(
                f"- {group.name}: {group.distance_m:.0f} m | "
                f"service: {service_label(group.primary_service_class)} | "
                f"routes: {', '.join(group.route_codes[:20])}{favorite}{suffix}"
            )
        return 0

    engine = TJNearbyEngine(config)
    try:
        if args.command == "once":
            result = engine.check_once(dry_run=args.dry_run)
            _print_result(result)
            return 0 if result.status in {"ok", "static_only", "inactive"} else 1

        interval = max(15, int(config.get("realtime.poll_seconds", 30)))
        print(f"TJ Nearby running every {interval}s. Press Ctrl+C to stop.")
        while True:
            result = engine.check_once(dry_run=args.dry_run)
            _print_result(result)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    finally:
        engine.close()


def install_example_config(destination: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "config.example.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
