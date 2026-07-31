from __future__ import annotations

import csv
import io
import os
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import httpx

from .config import AppConfig
from .geo import haversine_m
from .models import NearbyStop, NearbyStopGroup, Route, RouteVariant, Stop
from .route_style import normalize_hex_color, route_badge_style
from .service import (
    classify_route_codes,
    normalize_route_code,
    primary_service_class,
)


REQUIRED_GTFS_FILES = {"stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}


class GtfsError(RuntimeError):
    pass


def _read_csv_from_zip(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    try:
        raw = zf.read(name)
    except KeyError as exc:
        raise GtfsError(f"GTFS file missing: {name}") from exc
    text = raw.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


class GtfsFeed:
    def __init__(self, config: AppConfig):
        self.config = config
        self.cache_path = config.gtfs_cache_path
        self.stops: dict[str, Stop] = {}
        self.routes: dict[str, Route] = {}
        self.routes_by_short_name: dict[str, list[Route]] = defaultdict(list)
        self.variants: list[RouteVariant] = []
        self.variants_by_stop: dict[str, list[RouteVariant]] = defaultdict(list)
        self.variants_by_trip: dict[str, RouteVariant] = {}

    def ensure_downloaded(self, force: bool = False) -> Path:
        refresh_hours = float(self.config.get("gtfs.refresh_hours", 24))
        if self.cache_path.exists() and not force:
            age_hours = (time.time() - self.cache_path.stat().st_mtime) / 3600
            if age_hours < refresh_hours:
                self._validate_zip(self.cache_path)
                return self.cache_path

        urls: list[str] = [str(self.config.get("gtfs.url", ""))]
        urls.extend(str(url) for url in (self.config.get("gtfs.fallback_urls", []) or []))
        urls = [url for url in urls if url]
        if not urls:
            raise GtfsError("No GTFS URL configured")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for url in urls:
            tmp_path = self.cache_path.with_suffix(".download")
            try:
                with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
                    response.raise_for_status()
                    with tmp_path.open("wb") as fh:
                        for chunk in response.iter_bytes():
                            fh.write(chunk)
                self._validate_zip(tmp_path)
                os.replace(tmp_path, self.cache_path)
                return self.cache_path
            except Exception as exc:  # continue to fallback URL
                last_error = exc
                tmp_path.unlink(missing_ok=True)
        raise GtfsError(f"Unable to download GTFS feed: {last_error}")

    @staticmethod
    def _validate_zip(path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
        except (zipfile.BadZipFile, OSError) as exc:
            raise GtfsError(f"Invalid GTFS zip: {path}") from exc
        missing = REQUIRED_GTFS_FILES - names
        if missing:
            raise GtfsError(f"GTFS zip missing required files: {sorted(missing)}")

    def load(self) -> None:
        path = self.ensure_downloaded()
        with zipfile.ZipFile(path) as zf:
            stop_rows = _read_csv_from_zip(zf, "stops.txt")
            route_rows = _read_csv_from_zip(zf, "routes.txt")
            trip_rows = _read_csv_from_zip(zf, "trips.txt")
            stop_time_rows = _read_csv_from_zip(zf, "stop_times.txt")
            shape_rows = _read_csv_from_zip(zf, "shapes.txt") if "shapes.txt" in zf.namelist() else []

        self.stops = {}
        for row in stop_rows:
            try:
                stop = Stop(
                    stop_id=row["stop_id"].strip(),
                    name=(row.get("stop_name") or row["stop_id"]).strip(),
                    latitude=float(row["stop_lat"]),
                    longitude=float(row["stop_lon"]),
                    parent_station=(row.get("parent_station") or "").strip() or None,
                )
            except (KeyError, ValueError):
                continue
            self.stops[stop.stop_id] = stop

        self.routes = {}
        for row in route_rows:
            route_id = (row.get("route_id") or "").strip()
            if not route_id:
                continue
            self.routes[route_id] = Route(
                route_id=route_id,
                short_name=(row.get("route_short_name") or route_id).strip(),
                long_name=(row.get("route_long_name") or "").strip(),
                route_type=(row.get("route_type") or "3").strip(),
                color=normalize_hex_color(row.get("route_color"), "") or "",
                text_color=normalize_hex_color(row.get("route_text_color"), "") or "",
            )

        self.routes_by_short_name = defaultdict(list)
        for route in self.routes.values():
            self.routes_by_short_name[normalize_route_code(route.short_name)].append(route)

        trips: dict[str, dict[str, str]] = {}
        for row in trip_rows:
            trip_id = (row.get("trip_id") or "").strip()
            if trip_id:
                trips[trip_id] = row

        stop_times_by_trip: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for row in stop_time_rows:
            trip_id = (row.get("trip_id") or "").strip()
            stop_id = (row.get("stop_id") or "").strip()
            if not trip_id or stop_id not in self.stops:
                continue
            try:
                sequence = int(float(row.get("stop_sequence") or 0))
            except ValueError:
                sequence = 0
            stop_times_by_trip[trip_id].append((sequence, stop_id))

        shapes: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
        for row in shape_rows:
            shape_id = (row.get("shape_id") or "").strip()
            if not shape_id:
                continue
            try:
                seq = int(float(row.get("shape_pt_sequence") or 0))
                lat = float(row["shape_pt_lat"])
                lon = float(row["shape_pt_lon"])
            except (KeyError, ValueError):
                continue
            shapes[shape_id].append((seq, lat, lon))

        shape_points: dict[str, list[tuple[float, float]]] = {
            shape_id: [(lat, lon) for _, lat, lon in sorted(points)]
            for shape_id, points in shapes.items()
        }

        # A route can have many scheduled trips. For this MVP, retain the longest
        # representative trip for each route + direction + headsign combination.
        representatives: dict[tuple[str, int, str], RouteVariant] = {}
        representative_key_by_trip: dict[str, tuple[str, int, str]] = {}
        for trip_id, row in trips.items():
            route_id = (row.get("route_id") or "").strip()
            route = self.routes.get(route_id)
            if not route:
                continue
            try:
                direction_id = int(row.get("direction_id") or 0)
            except ValueError:
                direction_id = 0
            headsign = (row.get("trip_headsign") or route.long_name or route.short_name).strip()
            shape_id = (row.get("shape_id") or "").strip() or None
            stop_ids = [stop_id for _, stop_id in sorted(stop_times_by_trip.get(trip_id, []))]
            if not stop_ids:
                continue
            variant = RouteVariant(
                route_id=route_id,
                route_short_name=route.short_name,
                route_long_name=route.long_name,
                direction_id=direction_id,
                headsign=headsign,
                trip_id=trip_id,
                shape_id=shape_id,
                stop_ids=stop_ids,
                shape_points=shape_points.get(shape_id or "", []),
            )
            key = (route_id, direction_id, headsign.casefold())
            representative_key_by_trip[trip_id] = key
            current = representatives.get(key)
            if current is None or len(variant.stop_ids) > len(current.stop_ids):
                representatives[key] = variant

        self.variants = list(representatives.values())
        self.variants_by_trip = {
            trip_id: representatives[key]
            for trip_id, key in representative_key_by_trip.items()
            if key in representatives
        }
        self.variants_by_stop = defaultdict(list)
        for variant in self.variants:
            for stop_id in set(variant.stop_ids):
                self.variants_by_stop[stop_id].append(variant)


    def route_style_for_code(self, route_code: str) -> tuple[str, str]:
        """Return GUI-ready badge colors, preferring official GTFS colors."""
        matches = self.routes_by_short_name.get(normalize_route_code(route_code), [])
        selected = next((route for route in matches if route.color), matches[0] if matches else None)
        return route_badge_style(
            route_code,
            selected.color if selected else None,
            selected.text_color if selected else None,
        )

    def variant_for_trip(self, trip_id: str | None) -> RouteVariant | None:
        if not trip_id:
            return None
        return self.variants_by_trip.get(str(trip_id).strip())

    def nearest_stops(
        self,
        latitude: float,
        longitude: float,
        radius_m: float,
        limit: int | None,
        *,
        require_routes: bool = False,
    ) -> list[NearbyStop]:
        candidates: list[NearbyStop] = []
        for stop in self.stops.values():
            if require_routes and not self.variants_by_stop.get(stop.stop_id):
                continue
            distance = haversine_m(latitude, longitude, stop.latitude, stop.longitude)
            if distance <= radius_m:
                candidates.append(NearbyStop(stop=stop, distance_m=distance))
        candidates.sort(key=lambda item: item.distance_m)
        return candidates if limit is None else candidates[: max(0, limit)]

    def nearest_stop_groups(
        self,
        latitude: float,
        longitude: float,
        radius_m: float,
        limit: int | None,
        *,
        cluster_radius_m: float = 35.0,
    ) -> list[NearbyStopGroup]:
        """Return clean public-stop clusters while preserving GTFS member IDs.

        Records are clustered only when their normalized public names match and
        their coordinates are close. Different names such as ``Kuningan Madya``
        and ``Kuningan Madya 2`` intentionally remain separate. Stops without a
        scheduled route are excluded because they cannot produce arrivals.
        """
        raw = self.nearest_stops(
            latitude,
            longitude,
            radius_m,
            limit=None if limit is None else max(100, limit * 20),
            require_routes=True,
        )
        groups: list[NearbyStopGroup] = []
        group_keys: list[str] = []

        for item in raw:
            key = _normalize_stop_name(item.stop.name)
            target_index: int | None = None
            for index, group in enumerate(groups):
                if group_keys[index] != key:
                    continue
                anchor = group.members[0].stop
                separation = haversine_m(
                    item.stop.latitude,
                    item.stop.longitude,
                    anchor.latitude,
                    anchor.longitude,
                )
                if separation <= cluster_radius_m:
                    target_index = index
                    break

            if target_index is None:
                groups.append(
                    NearbyStopGroup(
                        name=item.stop.name,
                        distance_m=item.distance_m,
                        members=[item],
                    )
                )
                group_keys.append(key)
            else:
                group = groups[target_index]
                group.members.append(item)
                group.distance_m = min(group.distance_m, item.distance_m)

        for group in groups:
            routes = {
                variant.route_short_name.strip()
                for member in group.members
                for variant in self.variants_for_stop(member.stop.stop_id)
                if variant.route_short_name.strip()
            }
            group.route_codes = tuple(sorted(routes, key=_natural_route_key))
            group.service_classes = classify_route_codes(group.route_codes, self.config)
            group.primary_service_class = primary_service_class(group.service_classes)
            favorites = self.config.favorite_routes
            group.favorite_route_codes = tuple(
                route_code
                for route_code in group.route_codes
                if normalize_route_code(route_code) in favorites
            )
            group.members.sort(key=lambda member: member.distance_m)

        groups.sort(key=lambda group: group.distance_m)
        return groups if limit is None else groups[: max(0, limit)]

    def variants_for_stop(self, stop_id: str) -> Iterable[RouteVariant]:
        return self.variants_by_stop.get(stop_id, [])


def _normalize_stop_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _natural_route_key(value: str) -> tuple[int, str]:
    digits = "".join(ch for ch in value if ch.isdigit())
    return (int(digits) if digits else 10**9, value.casefold())
