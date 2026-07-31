from pathlib import Path

from tj_nearby.config import AppConfig
from tj_nearby.service import (
    SERVICE_BRT,
    SERVICE_JAKLINGKO,
    SERVICE_NON_BRT,
    classify_route_code,
    classify_route_codes,
    normalize_route_code,
    primary_service_class,
)


def test_default_route_classification(tmp_path: Path):
    config = AppConfig(raw={}, path=tmp_path / "config.yaml")
    assert classify_route_code("6", config) == SERVICE_BRT
    assert classify_route_code("06", config) == SERVICE_BRT
    assert classify_route_code("4D", config) == SERVICE_NON_BRT
    assert classify_route_code("JAK 81", config) == SERVICE_JAKLINGKO
    assert normalize_route_code(" jak 81 ") == "JAK81"
    assert normalize_route_code("JAK.81") == "JAK81"


def test_stop_group_can_expose_multiple_service_classes(tmp_path: Path):
    config = AppConfig(raw={}, path=tmp_path / "config.yaml")
    classes = classify_route_codes(["6", "6H", "JAK 81"], config)
    assert classes == (SERVICE_BRT, SERVICE_NON_BRT, SERVICE_JAKLINGKO)
    assert primary_service_class(classes) == SERVICE_BRT


def test_classification_can_be_overridden(tmp_path: Path):
    config = AppConfig(
        raw={
            "nearby": {
                "classification": {
                    "brt_routes": ["BRT-X"],
                    "jaklingko_prefixes": ["MIKRO"],
                }
            }
        },
        path=tmp_path / "config.yaml",
    )
    assert classify_route_code("BRT-X", config) == SERVICE_BRT
    assert classify_route_code("MIKRO 01", config) == SERVICE_JAKLINGKO
    assert classify_route_code("6", config) == SERVICE_NON_BRT


def test_favorite_routes_are_normalized_and_legacy_preferred_is_migrated(tmp_path: Path):
    config = AppConfig(
        raw={"routes": {"favorites": ["JAK 81"], "preferred": ["4d"]}},
        path=tmp_path / "config.yaml",
    )
    assert config.favorite_routes == {"JAK81", "4D"}
    # Old preferred routes become favorites by default and no longer hide all
    # other nearby routes in the desktop monitor.
    assert config.preferred_routes == set()


def test_strict_route_filter_requires_explicit_opt_in(tmp_path: Path):
    config = AppConfig(
        raw={
            "routes": {
                "preferred": ["4d"],
                "strict_filter_enabled": True,
            }
        },
        path=tmp_path / "config.yaml",
    )
    assert config.preferred_routes == {"4D"}
