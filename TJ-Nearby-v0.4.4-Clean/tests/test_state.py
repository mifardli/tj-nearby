from pathlib import Path

from tj_nearby.state import StateStore


def test_device_id_is_stable(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    first = store.get_or_create_device_id()
    second = store.get_or_create_device_id()
    assert first == second


def test_notification_cooldown(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    assert store.can_notify("x", 15)
    store.mark_notified("x")
    assert not store.can_notify("x", 15)


def test_seconds_since_latest_stage_prefix(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    assert store.seconds_since_latest("bus|trip|stage:") is None
    store.mark_notified("bus|trip|stage:two_stops_before")
    elapsed = store.seconds_since_latest("bus|trip|stage:")
    assert elapsed is not None
    assert 0 <= elapsed < 5


def test_journey_epoch_stays_stable_for_same_trip_and_direction(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    first = store.resolve_vehicle_journey(
        bus_id="BUS-1", route_code="4D", trip_id="T1", direction_id=0,
        headsign="Kuningan",
    )
    second = store.resolve_vehicle_journey(
        bus_id="BUS-1", route_code="4D", trip_id="T1", direction_id=0,
        headsign="Kuningan",
    )
    assert first.epoch == second.epoch == 1
    assert second.transition == "continuing"


def test_journey_epoch_increments_for_turnaround_on_any_route(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    inbound = store.resolve_vehicle_journey(
        bus_id="BODY-77", route_code="B25", trip_id="B25-I", direction_id=0,
        headsign="Bekasi",
    )
    outbound = store.resolve_vehicle_journey(
        bus_id="BODY-77", route_code="B25", trip_id="B25-O", direction_id=1,
        headsign="Cawang",
    )
    assert inbound.epoch == 1
    assert outbound.epoch == 2
    assert outbound.transition == "turnaround-detected"
    assert outbound.previous_direction_label == "bekasi"


def test_missing_live_fields_do_not_create_false_turnaround(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    first = store.resolve_vehicle_journey(
        bus_id="BUS-9", route_code="6H", trip_id="TRIP-A", direction_id=1,
        headsign="Senen",
    )
    incomplete = store.resolve_vehicle_journey(
        bus_id="BUS-9", route_code="6H", trip_id=None, direction_id=None,
        headsign="",
    )
    assert incomplete.epoch == first.epoch
    assert incomplete.transition == "continuing"


def test_new_trip_same_direction_gets_new_epoch(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    first = store.resolve_vehicle_journey(
        bus_id="BUS-2", route_code="4D", trip_id="T1", direction_id=0,
        headsign="Pulo Gadung",
    )
    second = store.resolve_vehicle_journey(
        bus_id="BUS-2", route_code="4D", trip_id="T2", direction_id=0,
        headsign="Pulo Gadung",
    )
    assert second.epoch == first.epoch + 1
    assert second.transition == "new-trip-detected"


def test_headsign_wording_enrichment_does_not_fake_turnaround(tmp_path: Path):
    store = StateStore(tmp_path / "state.sqlite")
    first = store.resolve_vehicle_journey(
        bus_id="BUS-3", route_code="4D", trip_id="T1", direction_id=0,
        headsign="Pulo Gadung",
    )
    enriched = store.resolve_vehicle_journey(
        bus_id="BUS-3", route_code="4D", trip_id="T1", direction_id=0,
        headsign="Pulo Gadung via Pramuka",
    )
    assert enriched.epoch == first.epoch
    assert enriched.transition == "continuing"
