from pathlib import Path

from tj_nearby.config import AppConfig
from tj_nearby.models import NearbyStop, NearbyStopGroup, Stop
from tj_nearby.selection import select_smart_stop_groups
from tj_nearby.service import SERVICE_BRT, SERVICE_JAKLINGKO, SERVICE_NON_BRT


def group(
    name: str,
    distance: float,
    service_classes: tuple[str, ...],
    *,
    favorite_routes: tuple[str, ...] = (),
) -> NearbyStopGroup:
    stop = Stop(name, name, 0, 0)
    return NearbyStopGroup(
        name=name,
        distance_m=distance,
        members=[NearbyStop(stop=stop, distance_m=distance)],
        route_codes=(name,),
        service_classes=service_classes,
        primary_service_class=service_classes[0],
        favorite_route_codes=favorite_routes,
    )


def smart_config(tmp_path: Path, *, maximum: int = 5) -> AppConfig:
    return AppConfig(
        raw={"nearby": {"selection_mode": "smart", "smart_max_groups": maximum}},
        path=tmp_path / "config.yaml",
    )


def test_smart_mode_keeps_every_eligible_group_even_when_legacy_limit_is_small(tmp_path: Path):
    config = smart_config(tmp_path, maximum=2)
    groups = [
        group("JAK-A", 80, (SERVICE_JAKLINGKO,)),
        group("JAK-B", 110, (SERVICE_JAKLINGKO,)),
        group("JAK-C", 140, (SERVICE_JAKLINGKO,)),
        group("NON-A", 300, (SERVICE_NON_BRT,)),
        group("BRT-A", 720, (SERVICE_BRT,)),
    ]
    selected = select_smart_stop_groups(groups, config, limit=2)
    assert [item.name for item in selected] == [
        "JAK-A",
        "JAK-B",
        "JAK-C",
        "NON-A",
        "BRT-A",
    ]


def test_service_radius_is_still_enforced(tmp_path: Path):
    config = smart_config(tmp_path, maximum=1)
    selected = select_smart_stop_groups(
        [
            group("JAK-IN", 350, (SERVICE_JAKLINGKO,)),
            group("JAK-OUT", 550, (SERVICE_JAKLINGKO,), favorite_routes=("JAK 81",)),
            group("BRT-OUT", 1100, (SERVICE_BRT,)),
            group("NON-IN", 700, (SERVICE_NON_BRT,)),
        ],
        config,
    )
    assert {item.name for item in selected} == {"JAK-IN", "NON-IN"}


def test_favorites_do_not_hide_plain_nearby_groups(tmp_path: Path):
    config = AppConfig(
        raw={
            "nearby": {
                "selection_mode": "smart",
                "smart_max_groups": 1,
                "favorite_route_bonus_m": 150,
            }
        },
        path=tmp_path / "config.yaml",
    )
    selected = select_smart_stop_groups(
        [
            group("PLAIN", 260, (SERVICE_NON_BRT,)),
            group("FAVORITE", 350, (SERVICE_NON_BRT,), favorite_routes=("4D",)),
        ],
        config,
    )
    assert [item.name for item in selected] == ["PLAIN", "FAVORITE"]


def test_mixed_service_group_is_included_when_any_service_radius_matches(tmp_path: Path):
    config = smart_config(tmp_path)
    mixed = group("MIXED", 900, (SERVICE_BRT, SERVICE_NON_BRT))
    selected = select_smart_stop_groups([mixed], config)
    assert selected == [mixed]


def test_location_selection_returns_more_than_eight_routed_groups(tmp_path: Path):
    from tj_nearby.gtfs import GtfsFeed
    from tj_nearby.models import RouteVariant
    from tj_nearby.selection import nearby_stop_groups_for_location

    config = AppConfig(
        raw={
            "nearby": {
                "selection_mode": "smart",
                "smart_max_groups": 8,
                "services": {
                    "brt": {"enabled": True, "search_radius_m": 1000},
                    "non_brt": {"enabled": True, "search_radius_m": 1000},
                    "jaklingko": {"enabled": True, "search_radius_m": 1000},
                },
            }
        },
        path=tmp_path / "config.yaml",
    )
    feed = GtfsFeed(config)
    for index in range(11):
        stop_id = f"S{index}"
        route_code = "B25" if index == 9 else "11M" if index == 10 else f"JAK.{index}"
        stop = Stop(stop_id, f"Stop {index}", -6.2 + index * 0.00001, 106.8)
        feed.stops[stop_id] = stop
        feed.variants_by_stop[stop_id] = [
            RouteVariant(
                route_code,
                route_code,
                "",
                0,
                "Tujuan",
                f"T{index}",
                None,
                [stop_id],
                [],
            )
        ]

    selected = nearby_stop_groups_for_location(feed, config, -6.2, 106.8)
    assert len(selected) == 11
    routes = {route for group_item in selected for route in group_item.route_codes}
    assert {"B25", "11M"} <= routes
