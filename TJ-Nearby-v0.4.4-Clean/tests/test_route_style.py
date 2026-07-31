from tj_nearby.route_style import (
    fallback_route_color,
    normalize_hex_color,
    readable_text_color,
    route_badge_style,
)


def test_normalize_gtfs_color_accepts_optional_hash():
    assert normalize_hex_color("#aabbcc") == "AABBCC"
    assert normalize_hex_color(" 112233 ") == "112233"


def test_invalid_gtfs_color_uses_default():
    assert normalize_hex_color("purple", "ABCDEF") == "ABCDEF"


def test_fallback_route_colors_are_stable_and_distinct_for_common_routes():
    assert fallback_route_color("4D") == fallback_route_color(" 4d ")
    assert fallback_route_color("4D") != fallback_route_color("6H")


def test_readable_text_color_switches_for_light_and_dark_backgrounds():
    assert readable_text_color("FFFFFF") == "000000"
    assert readable_text_color("000000") == "FFFFFF"


def test_official_gtfs_style_wins_over_fallback():
    assert route_badge_style("4D", "7447B8", "FFFFFF") == ("#7447B8", "#FFFFFF")
