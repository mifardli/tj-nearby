from pathlib import Path

from tj_nearby.config import AppConfig
from tj_nearby.engine import TJNearbyEngine
from tj_nearby.models import Arrival


def make_arrival(*, eta: float, walk: float) -> Arrival:
    return Arrival(
        bus_id="BUS1",
        route_code="6",
        stop_id="G00295",
        stop_name="Kuningan Madya",
        stop_distance_m=140,
        walking_minutes=walk,
        eta_minutes=eta,
        route_headsign="Ragunan",
        direction_id=0,
        stops_away=1,
        confidence="high",
        distance_along_route_m=500,
    )


def make_engine(tmp_path: Path) -> TJNearbyEngine:
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={
            "notification": {
                "mode": "leave_now",
                "min_eta_minutes": 2,
                "max_eta_minutes": 15,
                "leave_buffer_minutes": 3,
            }
        },
        path=tmp_path / "config.yaml",
    )
    return engine


def test_notification_due_now(tmp_path: Path):
    engine = make_engine(tmp_path)
    assert engine.notification_eligibility(make_arrival(eta=5, walk=3)) == (True, "due-now")


def test_notification_too_late_to_walk(tmp_path: Path):
    engine = make_engine(tmp_path)
    assert engine.notification_eligibility(make_arrival(eta=1.5, walk=2)) == (
        False,
        "eta-below-minimum",
    )


def test_notification_too_far_away(tmp_path: Path):
    engine = make_engine(tmp_path)
    assert engine.notification_eligibility(make_arrival(eta=31.9, walk=4)) == (
        False,
        "eta-above-maximum",
    )


def test_all_arrivals_mode_notifies_regardless_of_walking_margin(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={
            "notification": {
                "mode": "all_arrivals",
                "all_arrivals_max_eta_minutes": 120,
            }
        },
        path=tmp_path / "config.yaml",
    )
    assert engine.notification_eligibility(make_arrival(eta=1.5, walk=2)) == (
        True,
        "new-confirmed-approaching-bus",
    )
    assert engine.notification_eligibility(make_arrival(eta=31.9, walk=4)) == (
        True,
        "new-confirmed-approaching-bus",
    )


def test_one_notification_candidate_per_bus_occurrence_uses_nearest_stop(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(raw={"notification": {"mode": "all_arrivals"}}, path=tmp_path / "c.yaml")
    farther = make_arrival(eta=3, walk=4)
    nearer = Arrival(
        bus_id="BUS1", route_code="6", stop_id="B", stop_name="Closer Stop",
        stop_distance_m=50, walking_minutes=1, eta_minutes=8, route_headsign="Ragunan",
        direction_id=0, stops_away=2, confidence="high", distance_along_route_m=800,
    )
    candidates = engine._notification_candidates([farther, nearer])
    assert len(candidates) == 1
    assert candidates[0].stop_name == "Closer Stop"


def test_different_buses_are_all_notification_candidates(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(raw={"notification": {"mode": "all_arrivals"}}, path=tmp_path / "c.yaml")
    first = make_arrival(eta=7, walk=2)
    second = Arrival(
        bus_id="BUS2", route_code="6", stop_id="G00295", stop_name="Kuningan Madya",
        stop_distance_m=140, walking_minutes=2, eta_minutes=9, route_headsign="Ragunan",
        direction_id=0, stops_away=3, confidence="high", distance_along_route_m=900,
    )
    assert len(engine._notification_candidates([first, second])) == 2


def test_all_arrivals_sends_only_direction_confirmed_buses(tmp_path: Path):
    class FakeState:
        def __init__(self):
            self.marked = []

        def can_notify(self, _key, _cooldown):
            return True

        def mark_notified(self, key):
            self.marked.append(key)

    class FakeNotifier:
        def __init__(self):
            self.calls = []

        def send(self, title, message, subtitle=""):
            self.calls.append((title, message, subtitle))

    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={
            "notification": {
                "mode": "all_arrivals",
                "all_arrivals_max_eta_minutes": 120,
                "cooldown_minutes": 180,
                "max_notifications_per_cycle": 0,
            }
        },
        path=tmp_path / "c.yaml",
    )
    engine.state = FakeState()
    engine.notifier = FakeNotifier()
    first = make_arrival(eta=7, walk=2)
    second = Arrival(
        bus_id="BUS2", route_code="6Q", stop_id="B02494P", stop_name="Multivision Tower",
        stop_distance_m=279, walking_minutes=4, eta_minutes=31.9,
        route_headsign="Casablanca dan Galunggung via Epicentrum Raya", direction_id=1,
        stops_away=4, confidence="medium", distance_along_route_m=3500, trip_id="T2",
    )
    sent = engine._notify_due([first, second], dry_run=False)
    assert len(sent) == 1
    assert len(engine.notifier.calls) == 1
    assert "6 →" in engine.notifier.calls[0][0]
    assert "Ragunan" in engine.notifier.calls[0][0]
    assert "Menuju Halte" in engine.notifier.calls[0][1]


def test_ambiguous_direction_never_notifies(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={"notification": {"mode": "all_arrivals", "minimum_direction_confidence": "high"}},
        path=tmp_path / "c.yaml",
    )
    arrival = Arrival(
        bus_id="BUS-X", route_code="4D", stop_id="B", stop_name="Kuningan Madya",
        stop_distance_m=100, walking_minutes=2, eta_minutes=7,
        route_headsign="Arah belum pasti", direction_id=0, stops_away=2,
        confidence="low", distance_along_route_m=700, direction_status="ambiguous",
        direction_ambiguous=True,
    )
    assert engine.notification_eligibility(arrival) == (False, "direction-ambiguous")


def test_occurrence_key_changes_when_direction_changes(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={"notification": {"mode": "all_arrivals"}},
        path=tmp_path / "c.yaml",
    )
    first = make_arrival(eta=7, walk=2)
    opposite = Arrival(
        bus_id=first.bus_id, route_code=first.route_code, stop_id=first.stop_id,
        stop_name=first.stop_name, stop_distance_m=first.stop_distance_m,
        walking_minutes=first.walking_minutes, eta_minutes=8, route_headsign="Pulo Gadung",
        direction_id=1, stops_away=3, confidence="high", distance_along_route_m=900,
    )
    assert engine._occurrence_key(first) != engine._occurrence_key(opposite)
    # Opposite directions are no longer collapsed before journey validation.
    # The journey-state layer later suppresses an inconsistent second projection
    # for the same physical bus, while real buses on opposite directions survive.
    assert len(engine._notification_candidates([first, opposite])) == 2


def test_timing_status_likely_missed(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(raw={"notification": {}}, path=tmp_path / "c.yaml")
    assert engine.arrival_timing_status(make_arrival(eta=2, walk=2)) == (
        "likely_missed",
        "kemungkinan tidak terkejar",
    )


def test_timing_status_leave_now(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(raw={"notification": {}}, path=tmp_path / "c.yaml")
    assert engine.arrival_timing_status(make_arrival(eta=5, walk=2)) == (
        "leave_now",
        "berangkat sekarang",
    )


def test_timing_status_plenty_time(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(raw={"notification": {}}, path=tmp_path / "c.yaml")
    assert engine.arrival_timing_status(make_arrival(eta=10, walk=2)) == (
        "plenty_time",
        "masih cukup jauh",
    )


def test_all_arrivals_notification_uses_timing_label_and_stop_count(tmp_path: Path):
    class FakeState:
        def can_notify(self, _key, _cooldown):
            return True

        def mark_notified(self, _key):
            pass

    class FakeNotifier:
        def __init__(self):
            self.calls = []

        def send(self, title, message, subtitle=""):
            self.calls.append((title, message, subtitle))

    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={
            "notification": {
                "mode": "all_arrivals",
                "all_arrivals_max_eta_minutes": 120,
                "cooldown_minutes": 180,
                "max_notifications_per_cycle": 0,
            }
        },
        path=tmp_path / "c.yaml",
    )
    engine.state = FakeState()
    engine.notifier = FakeNotifier()
    arrival = Arrival(
        bus_id="MYS-17030",
        route_code="L13E",
        stop_id="G00295",
        stop_name="Kuningan Madya",
        stop_distance_m=120,
        walking_minutes=2,
        eta_minutes=2,
        route_headsign="Puri Beta",
        direction_id=1,
        stops_away=1,
        confidence="high",
        distance_along_route_m=100,
        trip_id="TRIP-1",
        direction_status="confirmed",
    )
    sent = engine._notify_due([arrival], dry_run=False)
    assert sent == [arrival]
    title, message, subtitle = engine.notifier.calls[0]
    assert title == "L13E → Puri Beta · 2 menit"
    assert subtitle == "Bus MYS-17030 · kemungkinan tidak terkejar"
    assert "1 halte lagi · Menuju Halte Kuningan Madya" in message
    assert "120 m dari lokasi lo" in message


def make_ready_engine(tmp_path: Path, *, intensity: str = "balanced") -> TJNearbyEngine:
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={
            "notification": {
                "mode": "ready_window",
                "ready_notification_intensity": intensity,
                "ready_notify_lead_bus_only": True,
                "ready_min_seconds_between_stages": 90,
                "ready_always_send_final_stage": True,
                "ready_min_margin_minutes": 2,
                "ready_max_stop_distance_m": 500,
                "ready_max_bus_data_age_seconds": 90,
                "ready_fallback_to_eta_when_stops_unknown": True,
                "ready_fallback_min_margin_minutes": 2,
                "ready_fallback_max_margin_minutes": 8,
                "ready_fallback_max_eta_minutes": 15,
                "minimum_direction_confidence": "high",
            }
        },
        path=tmp_path / "ready.yaml",
    )
    return engine


def ready_arrival(
    *, stops: int | None, eta: float, walk: float = 2, bus_id: str = "BUS-READY",
    route_code: str = "4D", headsign: str = "Pulo Gadung",
) -> Arrival:
    return Arrival(
        bus_id=bus_id,
        route_code=route_code,
        stop_id="G00295",
        stop_name="Kuningan Madya",
        stop_distance_m=140,
        walking_minutes=walk,
        eta_minutes=eta,
        route_headsign=headsign,
        direction_id=0,
        stops_away=stops,
        confidence="high",
        distance_along_route_m=500,
        direction_status="confirmed",
        stops_away_source="api-next-stops" if stops is not None else "unknown",
        bus_data_age_seconds=10,
    )


def test_ready_stage_semantics_are_unambiguous(tmp_path: Path):
    engine = make_ready_engine(tmp_path)
    assert engine.ready_stage(ready_arrival(stops=3, eta=8)) == "two_stops_before"
    assert engine.ready_stage(ready_arrival(stops=2, eta=5)) == "one_stop_before"
    assert engine.ready_stage(ready_arrival(stops=1, eta=2)) == "target_is_next"


def test_balanced_preset_uses_preparation_and_final_stage(tmp_path: Path):
    engine = make_ready_engine(tmp_path, intensity="balanced")
    assert engine.ready_enabled_stages() == ("two_stops_before", "target_is_next")
    assert engine.notification_eligibility(ready_arrival(stops=3, eta=7)) == (
        True,
        "ready-stage:two_stops_before",
    )
    assert engine.notification_eligibility(ready_arrival(stops=2, eta=5)) == (
        False,
        "ready-stage-disabled:one_stop_before",
    )
    assert engine.notification_eligibility(ready_arrival(stops=1, eta=1, walk=3)) == (
        True,
        "target-is-next-last-chance",
    )


def test_complete_preset_enables_all_three_stages(tmp_path: Path):
    engine = make_ready_engine(tmp_path, intensity="complete")
    assert engine.ready_enabled_stages() == (
        "two_stops_before",
        "one_stop_before",
        "target_is_next",
    )
    assert engine.notification_eligibility(ready_arrival(stops=2, eta=4)) == (
        True,
        "ready-stage:one_stop_before",
    )


def test_minimal_preset_only_enables_final_stage(tmp_path: Path):
    engine = make_ready_engine(tmp_path, intensity="minimal")
    assert engine.notification_eligibility(ready_arrival(stops=3, eta=7)) == (
        False,
        "ready-stage-disabled:two_stops_before",
    )
    assert engine.notification_eligibility(ready_arrival(stops=1, eta=1)) == (
        True,
        "target-is-next-last-chance",
    )


def test_two_stops_before_waits_when_walking_margin_is_too_small(tmp_path: Path):
    engine = make_ready_engine(tmp_path)
    assert engine.notification_eligibility(ready_arrival(stops=3, eta=3, walk=2)) == (
        False,
        "two-stops-before-walking-margin-too-small",
    )


def test_bus_beyond_three_stage_window_is_tracking_only(tmp_path: Path):
    engine = make_ready_engine(tmp_path)
    assert engine.notification_eligibility(ready_arrival(stops=4, eta=10)) == (
        False,
        "outside-three-stage-window",
    )


def test_ready_window_unknown_stop_count_can_use_eta_fallback(tmp_path: Path):
    engine = make_ready_engine(tmp_path)
    assert engine.notification_eligibility(ready_arrival(stops=None, eta=7, walk=2)) == (
        True,
        "ready-window-eta-fallback",
    )


def test_ready_window_stale_position_does_not_notify(tmp_path: Path):
    engine = make_ready_engine(tmp_path)
    arrival = ready_arrival(stops=1, eta=1, walk=3)
    object.__setattr__(arrival, "bus_data_age_seconds", 120)
    assert engine.notification_eligibility(arrival) == (False, "bus-position-too-old")


def test_stage_is_part_of_occurrence_key(tmp_path: Path):
    engine = make_ready_engine(tmp_path, intensity="complete")
    preparation = ready_arrival(stops=3, eta=7)
    middle = ready_arrival(stops=2, eta=4)
    final = ready_arrival(stops=1, eta=1)
    keys = {engine._occurrence_key(item) for item in (preparation, middle, final)}
    assert len(keys) == 3
    assert any("stage:target_is_next" in key for key in keys)


def test_lead_bus_only_suppresses_following_bus_same_route_direction_target(tmp_path: Path):
    engine = make_ready_engine(tmp_path, intensity="complete")
    lead = ready_arrival(stops=1, eta=2, bus_id="BUS-LEAD")
    following = ready_arrival(stops=3, eta=7, bus_id="BUS-FOLLOW")
    candidates = engine._notification_candidates([following, lead])
    assert candidates == [lead]


def test_lead_bus_policy_keeps_different_routes(tmp_path: Path):
    engine = make_ready_engine(tmp_path, intensity="complete")
    first = ready_arrival(stops=1, eta=2, bus_id="BUS-4D", route_code="4D")
    second = ready_arrival(
        stops=2, eta=4, bus_id="BUS-6H", route_code="6H", headsign="Senen"
    )
    assert len(engine._notification_candidates([first, second])) == 2


def test_final_stage_bypasses_inter_stage_interval(tmp_path: Path):
    class FakeState:
        def seconds_since_latest(self, _prefix):
            return 10

    engine = make_ready_engine(tmp_path)
    engine.state = FakeState()
    assert engine._stage_interval_allows(ready_arrival(stops=1, eta=1)) is True
    assert engine._stage_interval_allows(ready_arrival(stops=3, eta=7)) is False


def test_ready_window_final_notification_wording(tmp_path: Path):
    class FakeState:
        def can_notify(self, _key, _cooldown):
            return True

        def seconds_since_latest(self, _prefix):
            return 10

        def mark_notified(self, _key):
            pass

    class FakeNotifier:
        def __init__(self):
            self.calls = []

        def send(self, title, message, subtitle=""):
            self.calls.append((title, message, subtitle))

    engine = make_ready_engine(tmp_path)
    engine.state = FakeState()
    engine.notifier = FakeNotifier()
    arrival = ready_arrival(stops=1, eta=1, walk=3)
    sent = engine._notify_due([arrival], dry_run=False)
    assert sent == [arrival]
    title, message, subtitle = engine.notifier.calls[0]
    assert title == "4D → Pulo Gadung · 1 menit"
    assert subtitle == "Bus BUS-READY · bus sudah sangat dekat"
    assert "Pemberhentian berikutnya Halte Kuningan Madya" in message
    assert "kesempatan terakhir" in message


def test_ready_window_preparation_notification_wording(tmp_path: Path):
    class FakeState:
        def can_notify(self, _key, _cooldown):
            return True

        def seconds_since_latest(self, _prefix):
            return None

        def mark_notified(self, _key):
            pass

    class FakeNotifier:
        def __init__(self):
            self.calls = []

        def send(self, title, message, subtitle=""):
            self.calls.append((title, message, subtitle))

    engine = make_ready_engine(tmp_path)
    engine.state = FakeState()
    engine.notifier = FakeNotifier()
    arrival = ready_arrival(stops=3, eta=7, walk=2)
    sent = engine._notify_due([arrival], dry_run=False)
    assert sent == [arrival]
    _title, message, subtitle = engine.notifier.calls[0]
    assert subtitle == "Bus BUS-READY · bersiap-siap"
    assert "2 halte perantara sebelum Halte Kuningan Madya" in message


def test_occurrence_key_changes_when_journey_epoch_changes(tmp_path: Path):
    engine = make_ready_engine(tmp_path, intensity="complete")
    first = ready_arrival(stops=3, eta=7)
    second = Arrival(
        bus_id=first.bus_id, route_code=first.route_code, stop_id=first.stop_id,
        stop_name=first.stop_name, stop_distance_m=first.stop_distance_m,
        walking_minutes=first.walking_minutes, eta_minutes=first.eta_minutes,
        route_headsign=first.route_headsign, direction_id=first.direction_id,
        stops_away=first.stops_away, confidence=first.confidence,
        distance_along_route_m=first.distance_along_route_m,
        direction_status=first.direction_status, bus_data_age_seconds=10,
        journey_epoch=2,
    )
    assert engine._occurrence_key(first) != engine._occurrence_key(second)


def test_lead_policy_keeps_opposite_directions_separate(tmp_path: Path):
    engine = make_ready_engine(tmp_path, intensity="complete")
    inbound = ready_arrival(
        stops=1, eta=2, bus_id="BUS-IN", route_code="B25", headsign="Bekasi"
    )
    outbound = Arrival(
        bus_id="BUS-OUT", route_code="B25", stop_id=inbound.stop_id,
        stop_name=inbound.stop_name, stop_distance_m=inbound.stop_distance_m,
        walking_minutes=inbound.walking_minutes, eta_minutes=3,
        route_headsign="Cawang", direction_id=1, stops_away=1,
        confidence="high", distance_along_route_m=600,
        direction_status="confirmed", bus_data_age_seconds=10,
    )
    candidates = engine._notification_candidates([inbound, outbound])
    assert {item.bus_id for item in candidates} == {"BUS-IN", "BUS-OUT"}


def test_attach_journey_state_detects_general_turnaround(tmp_path: Path):
    from tj_nearby.state import StateStore

    engine = make_ready_engine(tmp_path, intensity="complete")
    engine.state = StateStore(tmp_path / "state.sqlite")
    inbound = ready_arrival(
        stops=1, eta=2, bus_id="BODY-1", route_code="6H", headsign="Senen"
    )
    object.__setattr__(inbound, "trip_id", "6H-IN")
    first = engine._attach_journey_state([inbound])[0]

    outbound = Arrival(
        bus_id="BODY-1", route_code="6H", stop_id=inbound.stop_id,
        stop_name=inbound.stop_name, stop_distance_m=inbound.stop_distance_m,
        walking_minutes=inbound.walking_minutes, eta_minutes=6,
        route_headsign="Lebak Bulus", direction_id=1, stops_away=3,
        confidence="high", distance_along_route_m=900, trip_id="6H-OUT",
        direction_status="confirmed", bus_data_age_seconds=10,
    )
    second = engine._attach_journey_state([outbound])[0]
    assert second.journey_epoch == first.journey_epoch + 1
    assert second.journey_transition == "turnaround-detected"
    assert second.previous_direction_label == "senen"


def test_competing_direction_for_same_body_is_not_notification_eligible(tmp_path: Path):
    from tj_nearby.state import StateStore

    engine = make_ready_engine(tmp_path, intensity="complete")
    engine.state = StateStore(tmp_path / "state.sqlite")
    primary = ready_arrival(
        stops=1, eta=2, bus_id="BODY-X", route_code="4D", headsign="Kuningan"
    )
    opposite = Arrival(
        bus_id="BODY-X", route_code="4D", stop_id=primary.stop_id,
        stop_name=primary.stop_name, stop_distance_m=primary.stop_distance_m,
        walking_minutes=primary.walking_minutes, eta_minutes=3,
        route_headsign="Pulo Gadung", direction_id=1, stops_away=1,
        confidence="high", distance_along_route_m=600,
        direction_status="confirmed", direction_score=10, bus_data_age_seconds=10,
    )
    attached = engine._attach_journey_state([primary, opposite])
    competing = next(
        item for item in attached
        if item.journey_transition == "competing-direction-same-vehicle"
    )
    assert engine.notification_eligibility(competing) == (
        False, "competing-direction-same-vehicle"
    )


def test_smart_notification_radius_depends_on_stop_service(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(raw={"nearby": {"selection_mode": "smart"}}, path=tmp_path / "c.yaml")
    brt = make_arrival(eta=5, walk=3)
    object.__setattr__(brt, "service_class", "brt")
    jak = make_arrival(eta=5, walk=3)
    object.__setattr__(jak, "service_class", "jaklingko")
    assert engine.notification_stop_radius_m(brt) == 800
    assert engine.notification_stop_radius_m(jak) == 400


def test_route_favorite_is_notification_order_not_bus_body_favorite(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={"notification": {"mode": "all_arrivals"}},
        path=tmp_path / "c.yaml",
    )
    normal = make_arrival(eta=2, walk=1)
    favorite = Arrival(
        bus_id="ANY-BODY", route_code="4D", stop_id="B", stop_name="Nearby",
        stop_distance_m=200, walking_minutes=2, eta_minutes=8,
        route_headsign="Pulo Gadung", direction_id=0, stops_away=2,
        confidence="high", distance_along_route_m=800, is_favorite_route=True,
    )
    ordered = engine._notification_candidates([normal, favorite])
    assert ordered[0].route_code == "4D"
    assert ordered[0].bus_id == "ANY-BODY"


def test_public_notify_due_respects_notification_enabled(tmp_path: Path):
    engine = object.__new__(TJNearbyEngine)
    engine.config = AppConfig(
        raw={"notification": {"enabled": False}},
        path=tmp_path / "c.yaml",
    )
    assert engine.notify_due([make_arrival(eta=5, walk=2)]) == []
