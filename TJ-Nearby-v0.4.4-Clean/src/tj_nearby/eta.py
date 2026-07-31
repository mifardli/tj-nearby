from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import AppConfig
from .geo import haversine_m, project_progress_m
from .gtfs import GtfsFeed
from .models import Arrival, Bus, NearbyStop, RouteVariant
from .service import normalize_route_code


def _normalize_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^0-9a-zà-ÿ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(v) for v in value)
    return str(value)


def _target_mentioned(bus: Bus, stop_id: str, stop_name: str) -> bool | None:
    text = _flatten_text(bus.next_stops).casefold().strip()
    if not text:
        return None
    normalized_name = re.sub(r"\s+", " ", stop_name.casefold()).strip()
    return stop_id.casefold() in text or normalized_name in text


def _nearest_stop_index(bus: Bus, variant: RouteVariant, feed: GtfsFeed) -> int | None:
    best_index: int | None = None
    best_distance = float("inf")
    for index, stop_id in enumerate(variant.stop_ids):
        stop = feed.stops.get(stop_id)
        if not stop:
            continue
        distance = haversine_m(bus.latitude, bus.longitude, stop.latitude, stop.longitude)
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index


def _stops_away(bus: Bus, stop_id: str, variant: RouteVariant, feed: GtfsFeed) -> int | None:
    try:
        target_index = variant.stop_ids.index(stop_id)
    except ValueError:
        return None
    bus_index = _nearest_stop_index(bus, variant, feed)
    if bus_index is None or target_index < bus_index:
        return None
    return target_index - bus_index


def _route_matches(bus: Bus, variant: RouteVariant) -> bool:
    bus_code = normalize_route_code(bus.route_code)
    candidates = {
        normalize_route_code(variant.route_short_name),
        normalize_route_code(variant.route_id),
    }
    return bool(bus_code and bus_code in candidates)


def _variant_signature(variant: RouteVariant) -> tuple[str, int, str]:
    return (
        normalize_route_code(variant.route_short_name or variant.route_id),
        int(variant.direction_id),
        _normalize_text(variant.headsign),
    )


def _parse_live_direction(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value in {0, 1}:
        return value
    if isinstance(value, float) and value in {0.0, 1.0}:
        return int(value)
    text = _normalize_text(value)
    if text in {"0", "direction 0", "dir 0", "outbound"}:
        return 0
    if text in {"1", "direction 1", "dir 1", "inbound"}:
        return 1
    return None


def _extract_label(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for nested in ("name", "stop_name", "label", "value", "headsign", "destination"):
            nested_value = value.get(nested)
            if isinstance(nested_value, str) and nested_value.strip():
                return nested_value.strip()
    return ""


def _extract_live_destination(bus: Bus) -> tuple[str, str]:
    """Return the API destination label and its source in strict priority order.

    The real-time API is authoritative for what is shown to the user. GTFS
    headsigns are used only to match/validate a route variant or as a fallback
    when the API sends no usable destination label.
    """
    prioritized_keys = (
        ("trip_headsign", "api-trip-headsign"),
        ("headsign", "api-headsign"),
        ("destination", "api-destination"),
        ("destination_name", "api-destination-name"),
        ("route_destination", "api-route-destination"),
        ("direction_name", "api-direction-name"),
        ("end_stop", "api-end-stop"),
        ("terminal", "api-terminal"),
    )
    for key, source in prioritized_keys:
        label = _extract_label(bus.raw.get(key))
        if label:
            return label, source
    return "", "gtfs-fallback"


def _text_tokens(value: str) -> set[str]:
    ignored = {
        "arah",
        "halte",
        "terminal",
        "menuju",
        "via",
        "dan",
        "ke",
        "dari",
        "transjakarta",
        "bus",
        "rute",
    }
    return {token for token in _normalize_text(value).split() if len(token) > 1 and token not in ignored}


def _destination_relation(live_destination: str, headsign: str) -> str:
    """Return match, conflict, or unknown for live-vs-GTFS destination text."""
    live = _normalize_text(live_destination)
    static = _normalize_text(headsign)
    if not live or not static:
        return "unknown"
    if live == static or live in static or static in live:
        return "match"
    live_tokens = _text_tokens(live)
    static_tokens = _text_tokens(static)
    if not live_tokens or not static_tokens:
        return "unknown"
    overlap = len(live_tokens & static_tokens) / max(1, min(len(live_tokens), len(static_tokens)))
    if overlap >= 0.6:
        return "match"
    # Only call it a conflict when both labels carry enough semantic content.
    if len(live_tokens) >= 1 and len(static_tokens) >= 1 and not (live_tokens & static_tokens):
        return "conflict"
    return "unknown"


def _ordered_stop_refs(value: Any) -> list[str]:
    """Extract ordered stop references from heterogeneous live API payloads."""
    refs: list[str] = []
    if value is None:
        return refs
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return refs
        if text[:1] in {"[", "{"}:
            try:
                return _ordered_stop_refs(json.loads(text))
            except Exception:
                pass
        refs.append(text)
        return refs
    if isinstance(value, (list, tuple)):
        for item in value:
            refs.extend(_ordered_stop_refs(item))
        return refs
    if isinstance(value, dict):
        parts: list[str] = []
        for key in (
            "stop_id",
            "stopId",
            "id",
            "code",
            "stop_code",
            "stop_name",
            "stopName",
            "name",
            "label",
        ):
            candidate = value.get(key)
            if candidate is not None and not isinstance(candidate, (dict, list, tuple)):
                parts.append(str(candidate))
        if parts:
            refs.append(" ".join(parts))
        # Preserve ordering in common nested containers without flattening every
        # unrelated metadata field into a fake stop reference.
        for key in ("stops", "data", "items", "results", "next_stops", "previous_stops"):
            if key in value:
                refs.extend(_ordered_stop_refs(value[key]))
        return refs
    refs.append(str(value))
    return refs




def _ref_matches_target(ref: str, stop_id: str, stop_name: str) -> bool:
    raw = str(ref).casefold()
    normalized = _normalize_text(ref)
    normalized_name = _normalize_text(stop_name)
    return bool(
        (stop_id and stop_id.casefold() in raw)
        or (normalized_name and (normalized_name == normalized or normalized_name in normalized))
    )


def _live_stops_away_from_refs(
    refs: list[str], stop_id: str, stop_name: str
) -> int | None:
    """Count upcoming stops through the target using API order.

    The first element of ``next_stops`` is treated as the next stop the bus will
    reach. Therefore a target at index 0 is presented as "1 halte lagi", while
    a target at index 1 is "2 halte lagi".
    """
    for index, ref in enumerate(refs):
        if _ref_matches_target(ref, stop_id, stop_name):
            return index + 1
    return None


def _variant_ref_indices(refs: list[str], variant: RouteVariant, feed: GtfsFeed) -> list[int]:
    aliases: list[tuple[int, str, str]] = []
    for index, stop_id in enumerate(variant.stop_ids):
        stop = feed.stops.get(stop_id)
        aliases.append((index, stop_id.casefold(), _normalize_text(stop.name if stop else "")))

    matched: list[int] = []
    for ref in refs:
        raw = str(ref).casefold()
        normalized = _normalize_text(ref)
        choices: list[int] = []
        for index, stop_id, stop_name in aliases:
            if stop_id and stop_id in raw:
                choices.append(index)
                continue
            if stop_name and (stop_name == normalized or stop_name in normalized):
                choices.append(index)
        if choices:
            # Repeated public names can exist on loops. Preserve forward order by
            # choosing the first index after the previous match when possible.
            previous = matched[-1] if matched else -1
            forward = [index for index in choices if index >= previous]
            matched.append(min(forward) if forward else min(choices))
    return matched


def _is_monotonic_non_decreasing(values: list[int]) -> bool:
    return all(left <= right for left, right in zip(values, values[1:]))


@dataclass(slots=True)
class _Candidate:
    arrival: Arrival
    score: int
    evidence: tuple[str, ...]
    hard_evidence: frozenset[str]


def _candidate_for_variant(
    *,
    feed: GtfsFeed,
    nearby: NearbyStop,
    bus: Bus,
    variant: RouteVariant,
    config: AppConfig,
    walking_minutes: float,
    metres_per_minute: float,
    dwell_minutes: float,
) -> _Candidate | None:
    stop = nearby.stop
    if not _route_matches(bus, variant):
        return None

    score = 0
    evidence: list[str] = []
    hard: set[str] = set()

    trip_variant = feed.variant_for_trip(bus.trip_id)
    if trip_variant is not None:
        if _variant_signature(trip_variant) != _variant_signature(variant):
            return None
        score += 120
        evidence.append("exact-live-trip")
        hard.add("exact-live-trip")

    live_direction = _parse_live_direction(bus.direction)
    if live_direction is not None:
        if live_direction != variant.direction_id:
            return None
        score += 55
        evidence.append("live-direction-id")
        hard.add("live-direction-id")

    live_destination, live_destination_source = _extract_live_destination(bus)
    relation = _destination_relation(live_destination, variant.headsign)
    decisive_variant_signal = bool(
        hard.intersection({"exact-live-trip", "live-direction-id"})
    )
    if relation == "conflict":
        # The API label remains authoritative for display, but a conflicting
        # GTFS branch is accepted only when trip_id/direction_id independently
        # identifies that branch. Otherwise rejecting it avoids a wrong-way alert.
        if not decisive_variant_signal:
            return None
        score += 20
        evidence.append(f"{live_destination_source}-gtfs-conflict")
    elif relation == "match":
        if live_destination_source == "api-trip-headsign":
            score += 90
        else:
            score += 65
        evidence.append("live-destination")
        evidence.append(live_destination_source)
        hard.add(live_destination_source)
    elif live_destination and decisive_variant_signal:
        # Wording can differ between API and GTFS. Once the live trip/direction
        # has selected the branch, keep the exact API label shown to the user.
        score += 45
        evidence.append("live-destination")
        evidence.append(f"{live_destination_source}-via-live-variant")
        hard.add(live_destination_source)

    mention = _target_mentioned(bus, stop.stop_id, stop.name)
    # A non-match does not mean the bus is wrong-way: the live endpoint may only
    # publish a short horizon of upcoming stops. Keep tracking and let trip,
    # direction, shape, and recognised stop order decide whether the target is
    # still ahead.
    if mention is True:
        score += 25
        evidence.append("target-in-live-next-stops")

    try:
        target_index = variant.stop_ids.index(stop.stop_id)
    except ValueError:
        return None

    next_refs = _ordered_stop_refs(bus.next_stops)
    next_indices = _variant_ref_indices(next_refs, variant, feed)
    if next_indices:
        if not _is_monotonic_non_decreasing(next_indices):
            return None
        if max(next_indices) < target_index:
            # This is useful but not fully decisive: all recognised upcoming
            # stops lie before the target on this GTFS direction.
            score += 18
            evidence.append("live-next-stops-before-target")
        elif target_index in next_indices:
            score += 60 if len(next_indices) >= 2 else 25
            evidence.append("live-next-stop-sequence")
            hard.add("live-next-stop-sequence")
        elif min(next_indices) > target_index:
            # Live upcoming stops are all after the target, so this target was
            # already passed on this direction.
            return None

    live_stops_away = _live_stops_away_from_refs(
        next_refs, stop.stop_id, stop.name
    )

    previous_refs = _ordered_stop_refs(bus.previous_stops)
    previous_indices = _variant_ref_indices(previous_refs, variant, feed)
    if previous_indices:
        if max(previous_indices) >= target_index:
            return None
        score += 20
        evidence.append("live-previous-stops")
        hard.add("live-previous-stops")

    distance_along: float | None = None
    shape_forward = False
    if variant.shape_points:
        bus_progress, bus_off_route, _ = project_progress_m(
            bus.latitude, bus.longitude, variant.shape_points
        )
        stop_progress, stop_off_route, _ = project_progress_m(
            stop.latitude, stop.longitude, variant.shape_points
        )
        if bus_off_route > 800 or stop_off_route > 300:
            return None
        distance_along = stop_progress - bus_progress
        if distance_along <= 50:
            # At terminals or short loops, a bus may already sit on the boarding
            # platform when the API flips it to the return direction. Preserve
            # that new journey only when the live stop order says this target is
            # immediate and the live trip/direction/destination confirms the
            # branch. This is route-agnostic and avoids hard-coding 4D.
            live_branch_confirmed = bool(
                decisive_variant_signal
                or relation == "match"
                or "live-next-stop-sequence" in hard
            )
            if (
                live_stops_away == 1
                and live_branch_confirmed
                and abs(distance_along) <= 150
            ):
                distance_along = max(100.0, abs(distance_along))
                score += 30
                evidence.append("live-immediate-stop-at-terminal")
                hard.add("live-immediate-stop-at-terminal")
            else:
                return None
        shape_forward = True
        score += 20
        evidence.append("shape-forward")
    else:
        straight = haversine_m(bus.latitude, bus.longitude, stop.latitude, stop.longitude)
        if mention is not True and straight > 2_000:
            return None
        distance_along = straight
        score += 4
        evidence.append("straight-line-fallback")

    if live_stops_away is not None:
        stops_away = live_stops_away
        stops_away_source = "api-next-stops"
        score += 18
        evidence.append("api-stops-away")
    else:
        stops_away = _stops_away(bus, stop.stop_id, variant, feed)
        stops_away_source = "gtfs-nearest-stop"

    if stops_away is None and mention is not True:
        # Exact trip/direction and forward shape can still track a bus even when
        # neither API nor GTFS proximity can express a reliable stop count.
        if not (decisive_variant_signal and shape_forward):
            return None
        stops_away_source = "unknown"
    if stops_away is not None:
        score += 8
        evidence.append("gtfs-stop-order-forward")

    eta = distance_along / metres_per_minute
    if "live-immediate-stop-at-terminal" in hard:
        eta = max(1.0, eta)
    if stops_away is not None:
        eta += max(0, stops_away - 1) * dwell_minutes
    if eta <= 0 or eta > float(config.get("notification.all_arrivals_max_eta_minutes", 120)):
        return None

    # High confidence requires an independent live direction signal plus a
    # forward route geometry/order check. Shape alone is never enough to claim
    # a destination on overlapping or branching corridors.
    confirmed = bool(
        "exact-live-trip" in hard
        or (
            shape_forward
            and hard.intersection(
                {
                    "live-direction-id",
                    "api-trip-headsign",
                    "api-headsign",
                    "api-destination",
                    "api-destination-name",
                    "api-route-destination",
                    "api-direction-name",
                    "api-end-stop",
                    "api-terminal",
                    "live-next-stop-sequence",
                    "live-previous-stops",
                }
            )
        )
    )
    confidence = "high" if confirmed else ("medium" if shape_forward else "low")
    status = "confirmed" if confirmed else "estimated"

    use_api_headsign = bool(
        live_destination
        and (
            relation == "match"
            or decisive_variant_signal
        )
    )
    display_headsign = live_destination if use_api_headsign else variant.headsign
    direction_source = live_destination_source if use_api_headsign else "gtfs-fallback"

    arrival = Arrival(
        bus_id=bus.bus_id,
        route_code=variant.route_short_name,
        stop_id=stop.stop_id,
        stop_name=stop.name,
        stop_distance_m=nearby.distance_m,
        walking_minutes=walking_minutes,
        eta_minutes=eta,
        route_headsign=display_headsign,
        direction_id=variant.direction_id,
        stops_away=stops_away,
        confidence=confidence,
        distance_along_route_m=distance_along,
        trip_id=bus.trip_id,
        direction_status=status,
        direction_evidence=tuple(evidence),
        direction_score=score,
        direction_ambiguous=False,
        direction_source=direction_source,
        live_headsign=live_destination,
        stops_away_source=stops_away_source,
        bus_data_age_seconds=max(
            0.0,
            (datetime.now(timezone.utc) - (bus.observed_at or datetime.now(timezone.utc))).total_seconds(),
        ),
    )
    return _Candidate(arrival=arrival, score=score, evidence=tuple(evidence), hard_evidence=frozenset(hard))


def _resolve_candidate_group(candidates: list[_Candidate], ambiguity_margin: int) -> Arrival | None:
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            -item.score,
            item.arrival.eta_minutes,
            item.arrival.stop_distance_m,
        )
    )
    top = candidates[0]
    top_signature = (
        top.arrival.direction_id,
        _normalize_text(top.arrival.route_headsign),
    )
    competitor = next(
        (
            item
            for item in candidates[1:]
            if (item.arrival.direction_id, _normalize_text(item.arrival.route_headsign))
            != top_signature
        ),
        None,
    )
    if competitor is not None and top.score - competitor.score < ambiguity_margin:
        # Do not expose a guessed terminal as fact. The arrival remains visible
        # for diagnostics/menu status, but notification policy suppresses it.
        original = top.arrival
        evidence = tuple(original.direction_evidence) + (
            f"competing-direction:{competitor.arrival.route_headsign}",
        )
        return Arrival(
            bus_id=original.bus_id,
            route_code=original.route_code,
            stop_id=original.stop_id,
            stop_name=original.stop_name,
            stop_distance_m=original.stop_distance_m,
            walking_minutes=original.walking_minutes,
            eta_minutes=original.eta_minutes,
            route_headsign="Arah belum pasti",
            direction_id=original.direction_id,
            stops_away=original.stops_away,
            confidence="low",
            distance_along_route_m=original.distance_along_route_m,
            trip_id=original.trip_id,
            direction_status="ambiguous",
            direction_evidence=evidence,
            direction_score=original.direction_score,
            direction_ambiguous=True,
            direction_source="ambiguous",
            live_headsign=original.live_headsign,
            stops_away_source=original.stops_away_source,
            bus_data_age_seconds=original.bus_data_age_seconds,
        )
    return top.arrival


def estimate_arrivals(
    feed: GtfsFeed,
    nearby_stops: Iterable[NearbyStop],
    buses: Iterable[Bus],
    config: AppConfig,
) -> list[Arrival]:
    preferred = config.preferred_routes
    stale_after = float(config.get("realtime.stale_after_seconds", 300))
    effective_speed_kmh = float(config.get("realtime.effective_speed_kmh", 18))
    dwell_minutes = float(config.get("realtime.dwell_minutes_per_stop", 0.35))
    walking_speed = float(config.get("notification.walking_speed_m_per_minute", 70))
    ambiguity_margin = int(config.get("direction.ambiguity_score_margin", 20))
    now = datetime.now(timezone.utc)

    valid_buses: list[Bus] = []
    for bus in buses:
        if bus.observed_at:
            observed = bus.observed_at
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            bus.observed_at = observed
            if (now - observed).total_seconds() > stale_after:
                continue
        valid_buses.append(bus)

    candidate_groups: dict[tuple[str, str, str], list[_Candidate]] = defaultdict(list)
    metres_per_minute = max(1.0, effective_speed_kmh * 1000.0 / 60.0)

    for nearby in nearby_stops:
        stop = nearby.stop
        walking_minutes = nearby.distance_m / max(1.0, walking_speed)
        for bus in valid_buses:
            bus_code = normalize_route_code(bus.route_code)
            if preferred and bus_code not in preferred:
                continue
            for variant in feed.variants_for_stop(stop.stop_id):
                candidate = _candidate_for_variant(
                    feed=feed,
                    nearby=nearby,
                    bus=bus,
                    variant=variant,
                    config=config,
                    walking_minutes=walking_minutes,
                    metres_per_minute=metres_per_minute,
                    dwell_minutes=dwell_minutes,
                )
                if candidate is None:
                    continue
                key = (bus.bus_id, bus_code, stop.name.casefold())
                candidate_groups[key].append(candidate)

    resolved: list[Arrival] = []
    for candidates in candidate_groups.values():
        arrival = _resolve_candidate_group(candidates, ambiguity_margin)
        if arrival is not None:
            resolved.append(arrival)

    # One bus can match multiple GTFS platform records for the same public stop.
    # Deduplicate only within the same resolved direction. Opposite directions are
    # deliberately separate so terminal turnarounds and bidirectional platforms
    # cannot erase each other before the notification policy sees them.
    deduplicated: dict[tuple[str, str, str, int, str, str], Arrival] = {}
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    for arrival in resolved:
        key = (
            arrival.bus_id,
            normalize_route_code(arrival.route_code),
            arrival.stop_name.casefold(),
            arrival.direction_id,
            _normalize_text(arrival.route_headsign),
            _normalize_text(arrival.trip_id),
        )
        current = deduplicated.get(key)
        score = (
            confidence_rank.get(arrival.confidence, 3),
            -arrival.direction_score,
            arrival.eta_minutes,
        )
        if current is None:
            deduplicated[key] = arrival
            continue
        current_score = (
            confidence_rank.get(current.confidence, 3),
            -current.direction_score,
            current.eta_minutes,
        )
        if score < current_score:
            deduplicated[key] = arrival

    # The same physical vehicle can legitimately project onto several nearby
    # stops that appear later in its stop sequence. The monitor should show that
    # vehicle once, targeted to the closest still-upcoming boarding stop for the
    # user. Distinct routes, directions, headsigns, or live trips remain separate.
    boarding_targets: dict[tuple[str, str, int, str, str], Arrival] = {}
    for arrival in deduplicated.values():
        key = (
            arrival.bus_id,
            normalize_route_code(arrival.route_code),
            arrival.direction_id,
            _normalize_text(arrival.route_headsign),
            _normalize_text(arrival.trip_id),
        )
        current = boarding_targets.get(key)
        score = (
            1 if arrival.direction_ambiguous else 0,
            confidence_rank.get(arrival.confidence, 3),
            arrival.stop_distance_m,
            arrival.eta_minutes,
            arrival.stop_name.casefold(),
        )
        if current is None:
            boarding_targets[key] = arrival
            continue
        current_score = (
            1 if current.direction_ambiguous else 0,
            confidence_rank.get(current.confidence, 3),
            current.stop_distance_m,
            current.eta_minutes,
            current.stop_name.casefold(),
        )
        if score < current_score:
            boarding_targets[key] = arrival

    return sorted(boarding_targets.values(), key=lambda item: item.eta_minutes)
