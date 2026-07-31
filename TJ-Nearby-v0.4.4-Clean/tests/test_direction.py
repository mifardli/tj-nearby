from datetime import datetime, timezone
from pathlib import Path

from tj_nearby.config import AppConfig
from tj_nearby.eta import estimate_arrivals
from tj_nearby.gtfs import GtfsFeed
from tj_nearby.models import Bus, NearbyStop, Route, RouteVariant, Stop


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        raw={
            "realtime": {
                "stale_after_seconds": 300,
                "effective_speed_kmh": 18,
                "dwell_minutes_per_stop": 0.35,
            },
            "notification": {
                "walking_speed_m_per_minute": 70,
                "all_arrivals_max_eta_minutes": 120,
            },
            "direction": {"ambiguity_score_margin": 20},
            "routes": {"preferred": []},
        },
        path=tmp_path / "config.yaml",
    )


def make_branching_feed(config: AppConfig) -> tuple[GtfsFeed, Stop]:
    feed = GtfsFeed(config)
    a = Stop("A", "Awal", 0.0, 0.0)
    b = Stop("B", "Kuningan Madya", 0.0, 0.01)
    c = Stop("C", "Pulo Gadung", 0.0, 0.02)
    d = Stop("D", "Patra Kuningan", 0.01, 0.02)
    feed.stops = {stop.stop_id: stop for stop in (a, b, c, d)}
    feed.routes = {"R4D": Route("R4D", "4D", "Branching route")}
    pulo = RouteVariant(
        "R4D", "4D", "", 0, "Pulo Gadung", "T-PULO", "S-PULO",
        ["A", "B", "C"], [(0.0, 0.0), (0.0, 0.01), (0.0, 0.02)],
    )
    kuningan = RouteVariant(
        "R4D", "4D", "", 1, "Patra Kuningan", "T-KUN", "S-KUN",
        ["A", "B", "D"], [(0.0, 0.0), (0.0, 0.01), (0.01, 0.02)],
    )
    feed.variants = [pulo, kuningan]
    feed.variants_by_stop["B"] = [pulo, kuningan]
    feed.variants_by_trip = {"LIVE-PULO": pulo, "LIVE-KUN": kuningan}
    return feed, b


def live_bus(**kwargs) -> Bus:
    values = dict(
        bus_id="BUS-4D",
        route_code="4D",
        latitude=0.0,
        longitude=0.005,
        observed_at=datetime.now(timezone.utc),
    )
    values.update(kwargs)
    return Bus(**values)


def test_live_direction_id_rejects_opposite_direction(tmp_path: Path):
    config = make_config(tmp_path)
    feed, target = make_branching_feed(config)
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(target, 100)],
        [live_bus(direction=0, next_stops=["B"])],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Pulo Gadung"
    assert arrivals[0].confidence == "high"
    assert "live-direction-id" in arrivals[0].direction_evidence


def test_exact_live_trip_is_decisive(tmp_path: Path):
    config = make_config(tmp_path)
    feed, target = make_branching_feed(config)
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(target, 100)],
        [live_bus(trip_id="LIVE-KUN", next_stops=["B"])],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Patra Kuningan"
    assert arrivals[0].direction_status == "confirmed"
    assert "exact-live-trip" in arrivals[0].direction_evidence


def test_ordered_next_stops_choose_correct_branch(tmp_path: Path):
    config = make_config(tmp_path)
    feed, target = make_branching_feed(config)
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(target, 100)],
        [live_bus(next_stops=[{"stop_id": "B"}, {"stop_id": "C"}])],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Pulo Gadung"
    assert arrivals[0].confidence == "high"
    assert "live-next-stop-sequence" in arrivals[0].direction_evidence


def test_shared_segment_without_direction_evidence_is_ambiguous(tmp_path: Path):
    config = make_config(tmp_path)
    feed, target = make_branching_feed(config)
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(target, 100)],
        [live_bus(next_stops=["B"])],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Arah belum pasti"
    assert arrivals[0].direction_ambiguous is True
    assert arrivals[0].confidence == "low"


def test_live_destination_text_chooses_direction(tmp_path: Path):
    config = make_config(tmp_path)
    feed, target = make_branching_feed(config)
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(target, 100)],
        [live_bus(next_stops=["B"], raw={"destination": "Pulo Gadung"})],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Pulo Gadung"
    assert arrivals[0].confidence == "high"
    assert "live-destination" in arrivals[0].direction_evidence


def test_api_trip_headsign_is_primary_display_label(tmp_path: Path):
    config = make_config(tmp_path)
    feed, target = make_branching_feed(config)
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(target, 100)],
        [
            live_bus(
                direction=0,
                next_stops=["B"],
                raw={
                    "trip_headsign": "Pulo Gadung via Pramuka",
                    "destination": "Patra Kuningan",
                },
            )
        ],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Pulo Gadung via Pramuka"
    assert arrivals[0].direction_source == "api-trip-headsign"
    assert arrivals[0].live_headsign == "Pulo Gadung via Pramuka"
    assert "api-trip-headsign" in arrivals[0].direction_evidence


def test_gtfs_headsign_is_fallback_when_api_has_no_destination(tmp_path: Path):
    config = make_config(tmp_path)
    feed, target = make_branching_feed(config)
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(target, 100)],
        [live_bus(direction=1, next_stops=["B"], raw={})],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Patra Kuningan"
    assert arrivals[0].direction_source == "gtfs-fallback"
    assert arrivals[0].live_headsign == ""


def test_api_trip_headsign_overrides_gtfs_wording_after_exact_trip_match(tmp_path: Path):
    config = make_config(tmp_path)
    feed, target = make_branching_feed(config)
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(target, 100)],
        [
            live_bus(
                trip_id="LIVE-PULO",
                next_stops=["B"],
                raw={"trip_headsign": "Pulo Gadung 2"},
            )
        ],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Pulo Gadung 2"
    assert arrivals[0].direction_source == "api-trip-headsign"
    assert arrivals[0].direction_status == "confirmed"
