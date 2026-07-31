from dataclasses import replace

from tj_nearby.windows_gui import demo_result, format_eta, unique_display_arrivals


def test_format_eta_is_human_readable():
    assert format_eta(0.4) == "< 1 menit"
    assert format_eta(3.2) == "3 menit"
    assert format_eta(65) == "1j 5m"


def test_demo_result_contains_colored_distinct_routes_and_favorites():
    result = demo_result()
    assert result.status == "ok"
    assert {arrival.route_code for arrival in result.arrivals} == {"4D", "6H", "JAK 81"}
    assert len({arrival.route_color for arrival in result.arrivals}) == 3
    favorites = {arrival.route_code for arrival in result.arrivals if arrival.is_favorite_route}
    assert favorites == {"4D", "JAK 81"}


def test_unique_display_arrivals_keeps_opposite_directions():
    base = demo_result().arrivals[0]
    opposite = replace(
        base,
        direction_id=1,
        route_headsign="Kuningan",
        trip_id="return-trip",
    )
    rows = unique_display_arrivals([base, opposite, base])
    assert len(rows) == 2
    assert {row.route_headsign for row in rows} == {"Pulo Gadung", "Kuningan"}


def test_unique_display_arrivals_does_not_limit_to_one_vehicle_type():
    arrivals = demo_result().arrivals
    rows = unique_display_arrivals(arrivals)
    assert [row.route_code for row in rows] == ["4D", "6H", "JAK 81"]
    assert {row.service_class for row in rows} == {"non_brt", "jaklingko"}

from tj_nearby.windows_gui import display_status


class _NotificationLabelOnlyEngine:
    def notification_label(self, arrival):
        return "target_is_next", "bus sudah sangat dekat"


def test_display_status_uses_existing_engine_notification_label_contract():
    arrival = demo_result().arrivals[0]
    label, _color = display_status(_NotificationLabelOnlyEngine(), arrival)
    assert label == "Bus sudah sangat dekat"


def test_unique_display_arrivals_has_no_default_row_cap():
    base = demo_result().arrivals[0]
    arrivals = [replace(base, bus_id=f"BUS-{index}") for index in range(75)]
    assert len(unique_display_arrivals(arrivals)) == 75
    assert len(unique_display_arrivals(arrivals, limit=60)) == 60
