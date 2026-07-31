import csv
import io
import zipfile
from pathlib import Path

from tj_nearby.config import AppConfig
from tj_nearby.gtfs import GtfsFeed


def write_csv(zf: zipfile.ZipFile, name: str, rows: list[dict[str, str]]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    zf.writestr(name, buffer.getvalue())


def make_feed(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        write_csv(
            zf,
            "stops.txt",
            [
                {"stop_id": "A", "stop_name": "Stop A", "stop_lat": "0", "stop_lon": "0", "parent_station": ""},
                {"stop_id": "B", "stop_name": "Stop B", "stop_lat": "0", "stop_lon": "0.01", "parent_station": ""},
            ],
        )
        write_csv(
            zf,
            "routes.txt",
            [{"route_id": "R1", "route_short_name": "5C", "route_long_name": "A-B", "route_type": "3", "route_color": "7447B8", "route_text_color": "FFFFFF"}],
        )
        write_csv(
            zf,
            "trips.txt",
            [{"route_id": "R1", "service_id": "S", "trip_id": "T1", "trip_headsign": "B", "direction_id": "0", "shape_id": "SH1"}],
        )
        write_csv(
            zf,
            "stop_times.txt",
            [
                {"trip_id": "T1", "arrival_time": "00:00:00", "departure_time": "00:00:00", "stop_id": "A", "stop_sequence": "1"},
                {"trip_id": "T1", "arrival_time": "00:10:00", "departure_time": "00:10:00", "stop_id": "B", "stop_sequence": "2"},
            ],
        )
        write_csv(
            zf,
            "shapes.txt",
            [
                {"shape_id": "SH1", "shape_pt_lat": "0", "shape_pt_lon": "0", "shape_pt_sequence": "1"},
                {"shape_id": "SH1", "shape_pt_lat": "0", "shape_pt_lon": "0.01", "shape_pt_sequence": "2"},
            ],
        )


def test_load_and_nearest(tmp_path: Path):
    feed_path = tmp_path / "gtfs.zip"
    make_feed(feed_path)
    config = AppConfig(
        raw={"gtfs": {"cache_path": str(feed_path), "refresh_hours": 9999}},
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    feed.load()
    assert len(feed.stops) == 2
    assert len(feed.routes) == 1
    assert len(feed.variants) == 1
    assert feed.route_style_for_code("5C") == ("#7447B8", "#FFFFFF")
    nearby = feed.nearest_stops(0, 0.0001, radius_m=2_000, limit=2)
    assert nearby[0].stop.stop_id == "A"
    assert feed.variants_for_stop("B")


def test_nearby_groups_merge_same_named_platforms(tmp_path: Path):
    config = AppConfig(raw={}, path=tmp_path / "config.yaml")
    feed = GtfsFeed(config)
    from tj_nearby.models import RouteVariant, Stop

    feed.stops = {
        "A1": Stop("A1", "Kuningan Madya", -6.2, 106.8),
        "A2": Stop("A2", "Kuningan Madya", -6.20005, 106.80005),
        "B": Stop("B", "Kuningan Madya 2", -6.201, 106.801),
        "EMPTY": Stop("EMPTY", "Unused Stop", -6.2, 106.8001),
    }
    variant_6h = RouteVariant("R1", "6H", "", 0, "Senen", "T1", None, ["A1"], [])
    variant_6 = RouteVariant("R2", "6", "", 1, "Ragunan", "T2", None, ["A2"], [])
    variant_b14 = RouteVariant("R3", "B14", "", 0, "Bekasi", "T3", None, ["B"], [])
    feed.variants_by_stop["A1"] = [variant_6h]
    feed.variants_by_stop["A2"] = [variant_6]
    feed.variants_by_stop["B"] = [variant_b14]

    groups = feed.nearest_stop_groups(-6.2, 106.8, radius_m=500, limit=5, cluster_radius_m=35)
    assert [group.name for group in groups] == ["Kuningan Madya", "Kuningan Madya 2"]
    assert {member.stop.stop_id for member in groups[0].members} == {"A1", "A2"}
    assert groups[0].route_codes == ("6", "6H")
    assert all(member.stop.stop_id != "EMPTY" for group in groups for member in group.members)


def test_nearby_groups_can_return_all_groups_without_merging_distinct_names(tmp_path: Path):
    config = AppConfig(raw={}, path=tmp_path / "config.yaml")
    feed = GtfsFeed(config)
    from tj_nearby.models import RouteVariant, Stop

    feed.stops = {
        "TOP": Stop("TOP", "Flyover Jatinegara Atas", -6.2130, 106.8755),
        "BOTTOM": Stop("BOTTOM", "Flyover Jatinegara Bawah", -6.2131, 106.8756),
        "BRT": Stop("BRT", "Flyover Jatinegara", -6.2132, 106.8757),
    }
    for stop_id, route in (("TOP", "11M"), ("BOTTOM", "B25"), ("BRT", "10")):
        feed.variants_by_stop[stop_id] = [
            RouteVariant(route, route, "", 0, "Tujuan", f"T-{route}", None, [stop_id], [])
        ]

    groups = feed.nearest_stop_groups(
        -6.2130,
        106.8755,
        radius_m=1_000,
        limit=None,
        cluster_radius_m=35,
    )
    assert [group.name for group in groups] == [
        "Flyover Jatinegara Atas",
        "Flyover Jatinegara Bawah",
        "Flyover Jatinegara",
    ]
    assert {route for group in groups for route in group.route_codes} == {"10", "11M", "B25"}
