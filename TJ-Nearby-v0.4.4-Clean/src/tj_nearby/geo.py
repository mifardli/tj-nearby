from __future__ import annotations

from math import asin, cos, hypot, radians, sin, sqrt
from typing import Iterable

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2.0) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * asin(sqrt(a))


def _xy_m(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    x = radians(lon - ref_lon) * EARTH_RADIUS_M * cos(radians(ref_lat))
    y = radians(lat - ref_lat) * EARTH_RADIUS_M
    return x, y


def project_progress_m(
    point_lat: float,
    point_lon: float,
    polyline: Iterable[tuple[float, float]],
) -> tuple[float, float, float]:
    """Return (progress along polyline, distance to polyline, total length), all metres."""
    points = list(polyline)
    if not points:
        return 0.0, float("inf"), 0.0
    if len(points) == 1:
        return 0.0, haversine_m(point_lat, point_lon, *points[0]), 0.0

    ref_lat, ref_lon = point_lat, point_lon
    px, py = 0.0, 0.0
    xy = [_xy_m(lat, lon, ref_lat, ref_lon) for lat, lon in points]
    cumulative = 0.0
    best_distance = float("inf")
    best_progress = 0.0

    for (ax, ay), (bx, by) in zip(xy, xy[1:]):
        vx, vy = bx - ax, by - ay
        seg_len_sq = vx * vx + vy * vy
        seg_len = sqrt(seg_len_sq)
        if seg_len_sq == 0:
            distance = hypot(px - ax, py - ay)
            t = 0.0
        else:
            t = ((px - ax) * vx + (py - ay) * vy) / seg_len_sq
            t = min(1.0, max(0.0, t))
            qx, qy = ax + t * vx, ay + t * vy
            distance = hypot(px - qx, py - qy)
        if distance < best_distance:
            best_distance = distance
            best_progress = cumulative + t * seg_len
        cumulative += seg_len

    return best_progress, best_distance, cumulative
