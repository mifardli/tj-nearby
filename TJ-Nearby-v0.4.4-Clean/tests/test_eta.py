from datetime import datetime, timezone
from pathlib import Path

from tj_nearby.config import AppConfig
from tj_nearby.eta import estimate_arrivals
from tj_nearby.gtfs import GtfsFeed
from tj_nearby.models import Bus, NearbyStop, Route, RouteVariant, Stop


def test_bus_ahead_of_route_is_estimated(tmp_path: Path):
    config = AppConfig(
        raw={
            "realtime": {
                "stale_after_seconds": 300,
                "effective_speed_kmh": 18,
                "dwell_minutes_per_stop": 0.35,
            },
            "notification": {"walking_speed_m_per_minute": 70},
            "routes": {"preferred": []},
        },
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    feed.stops = {
        "A": Stop("A", "Stop A", 0.0, 0.0),
        "B": Stop("B", "Stop B", 0.0, 0.01),
        "C": Stop("C", "Stop C", 0.0, 0.02),
    }
    feed.routes = {"R1": Route("R1", "5C", "A-C")}
    variant = RouteVariant(
        route_id="R1",
        route_short_name="5C",
        route_long_name="A-C",
        direction_id=0,
        headsign="Stop C",
        trip_id="T1",
        shape_id="S1",
        stop_ids=["A", "B", "C"],
        shape_points=[(0.0, 0.0), (0.0, 0.01), (0.0, 0.02)],
    )
    feed.variants = [variant]
    feed.variants_by_stop["C"] = [variant]
    bus = Bus(
        bus_id="BUS1",
        route_code="5C",
        latitude=0.0,
        longitude=0.005,
        next_stops=["B", "C"],
        trip_id="LIVE-T1",
        observed_at=datetime.now(timezone.utc),
    )
    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(feed.stops["C"], 140)],
        [bus],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].eta_minutes > 0
    assert arrivals[0].confidence == "high"
    assert arrivals[0].trip_id == "LIVE-T1"


def test_bus_after_target_is_rejected(tmp_path: Path):
    config = AppConfig(
        raw={
            "realtime": {"stale_after_seconds": 300, "effective_speed_kmh": 18},
            "notification": {"walking_speed_m_per_minute": 70},
        },
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    stop = Stop("B", "Stop B", 0.0, 0.01)
    feed.stops = {"B": stop}
    variant = RouteVariant("R1", "5C", "", 0, "End", "T", "S", ["B"], [(0, 0), (0, 0.02)])
    feed.variants_by_stop["B"] = [variant]
    bus = Bus("BUS1", "5C", 0.0, 0.015, observed_at=datetime.now(timezone.utc))
    assert estimate_arrivals(feed, [NearbyStop(stop, 10)], [bus], config) == []


def test_same_public_stop_platforms_are_deduplicated(tmp_path: Path):
    config = AppConfig(
        raw={
            "realtime": {"stale_after_seconds": 300, "effective_speed_kmh": 18},
            "notification": {"walking_speed_m_per_minute": 70},
            "routes": {"preferred": []},
        },
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    stop_a = Stop("A1", "Kuningan Madya", 0.0, 0.01)
    stop_b = Stop("A2", "Kuningan Madya", 0.0, 0.01002)
    feed.stops = {"A1": stop_a, "A2": stop_b}
    variant_a = RouteVariant("R1", "6H", "", 0, "Senen", "T1", "S1", ["A1"], [(0, 0), (0, 0.02)])
    variant_b = RouteVariant("R1", "6H", "", 0, "Senen", "T2", "S1", ["A2"], [(0, 0), (0, 0.02)])
    feed.variants_by_stop["A1"] = [variant_a]
    feed.variants_by_stop["A2"] = [variant_b]
    bus = Bus("BUS1", "6H", 0.0, 0.005, observed_at=datetime.now(timezone.utc))

    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(stop_a, 100), NearbyStop(stop_b, 102)],
        [bus],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].stop_name == "Kuningan Madya"


def test_api_next_stops_drives_exact_stops_away_count(tmp_path: Path):
    config = AppConfig(
        raw={
            "realtime": {"stale_after_seconds": 300, "effective_speed_kmh": 18},
            "notification": {"walking_speed_m_per_minute": 70},
            "routes": {"preferred": []},
        },
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    stops = {
        "A": Stop("A", "Stop A", 0.0, 0.0),
        "B": Stop("B", "Stop B", 0.0, 0.01),
        "C": Stop("C", "Kuningan Madya", 0.0, 0.02),
        "D": Stop("D", "Stop D", 0.0, 0.03),
    }
    feed.stops = stops
    variant = RouteVariant(
        "R4D", "4D", "", 0, "Pulo Gadung", "T4D", "S4D",
        ["A", "B", "C", "D"],
        [(0.0, 0.0), (0.0, 0.01), (0.0, 0.02), (0.0, 0.03)],
    )
    feed.variants_by_stop["C"] = [variant]
    bus = Bus(
        "BUS-4D", "4D", 0.0, 0.005, direction=0,
        next_stops=[{"stop_id": "B"}, {"stop_id": "C"}, {"stop_id": "D"}],
        observed_at=datetime.now(timezone.utc),
    )
    arrivals = estimate_arrivals(feed, [NearbyStop(stops["C"], 100)], [bus], config)
    assert len(arrivals) == 1
    assert arrivals[0].stops_away == 2
    assert arrivals[0].stops_away_source == "api-next-stops"


def test_truncated_next_stops_does_not_hide_far_bus_with_confirmed_direction(tmp_path: Path):
    config = AppConfig(
        raw={
            "realtime": {"stale_after_seconds": 300, "effective_speed_kmh": 18},
            "notification": {"walking_speed_m_per_minute": 70},
            "routes": {"preferred": []},
        },
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    stops = {
        "A": Stop("A", "Stop A", 0.0, 0.0),
        "B": Stop("B", "Stop B", 0.0, 0.01),
        "C": Stop("C", "Stop C", 0.0, 0.02),
        "D": Stop("D", "Kuningan Madya", 0.0, 0.03),
    }
    feed.stops = stops
    variant = RouteVariant(
        "R4D", "4D", "", 0, "Pulo Gadung", "T4D", "S4D",
        ["A", "B", "C", "D"],
        [(0.0, 0.0), (0.0, 0.01), (0.0, 0.02), (0.0, 0.03)],
    )
    feed.variants_by_stop["D"] = [variant]
    bus = Bus(
        "BUS-FAR", "4D", 0.0, 0.004, direction=0,
        next_stops=[{"stop_id": "B"}],
        observed_at=datetime.now(timezone.utc),
    )
    arrivals = estimate_arrivals(feed, [NearbyStop(stops["D"], 100)], [bus], config)
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Pulo Gadung"
    assert arrivals[0].stops_away is not None
    assert arrivals[0].stops_away > 2


def test_return_trip_at_terminal_is_kept_when_live_direction_flips(tmp_path: Path):
    config = AppConfig(
        raw={
            "realtime": {"stale_after_seconds": 300, "effective_speed_kmh": 18},
            "notification": {"walking_speed_m_per_minute": 70},
            "routes": {"preferred": []},
        },
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    terminal = Stop("TERM", "Terminal Bersama", 0.0, 0.01)
    next_stop = Stop("NEXT", "Stop Berikut", 0.0, 0.02)
    feed.stops = {"TERM": terminal, "NEXT": next_stop}
    return_variant = RouteVariant(
        "RB25", "B25", "", 1, "Cawang", "B25-OUT", "S-OUT",
        ["TERM", "NEXT"], [(0.0, 0.01), (0.0, 0.02)],
    )
    feed.variants_by_stop["TERM"] = [return_variant]
    feed.variants_by_trip["B25-OUT"] = return_variant
    bus = Bus(
        "BODY-77", "B25", 0.0, 0.01001, direction=1, trip_id="B25-OUT",
        next_stops=[{"stop_id": "TERM"}, {"stop_id": "NEXT"}],
        observed_at=datetime.now(timezone.utc),
        raw={"trip_headsign": "Cawang"},
    )
    arrivals = estimate_arrivals(feed, [NearbyStop(terminal, 100)], [bus], config)
    assert len(arrivals) == 1
    assert arrivals[0].route_headsign == "Cawang"
    assert arrivals[0].stops_away == 1
    assert arrivals[0].eta_minutes >= 1
    assert "live-immediate-stop-at-terminal" in arrivals[0].direction_evidence


def test_one_vehicle_matching_multiple_nearby_stops_uses_closest_upcoming_boarding_stop(tmp_path: Path):
    config = AppConfig(
        raw={
            "realtime": {"stale_after_seconds": 300, "effective_speed_kmh": 18},
            "notification": {"walking_speed_m_per_minute": 70},
            "routes": {"preferred": []},
        },
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    stops = {
        "A": Stop("A", "Stop Awal", 0.0, 0.0),
        "B": Stop("B", "Halte Lebih Jauh", 0.0, 0.01),
        "C": Stop("C", "Halte Terdekat", 0.0, 0.02),
    }
    feed.stops = stops
    variant = RouteVariant(
        "R41", "JAK.41", "", 0, "Pulo Gadung", "T41", "S41",
        ["A", "B", "C"],
        [(0.0, 0.0), (0.0, 0.01), (0.0, 0.02)],
    )
    feed.variants_by_stop["B"] = [variant]
    feed.variants_by_stop["C"] = [variant]
    bus = Bus(
        "BODY-41", "JAK.41", 0.0, 0.002, direction=0, trip_id="T41",
        next_stops=[{"stop_id": "B"}, {"stop_id": "C"}],
        observed_at=datetime.now(timezone.utc),
    )

    arrivals = estimate_arrivals(
        feed,
        [NearbyStop(stops["B"], 260), NearbyStop(stops["C"], 120)],
        [bus],
        config,
    )
    assert len(arrivals) == 1
    assert arrivals[0].bus_id == "BODY-41"
    assert arrivals[0].stop_id == "C"
    assert arrivals[0].stop_name == "Halte Terdekat"
