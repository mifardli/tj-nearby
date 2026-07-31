from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class LocationFix:
    latitude: float
    longitude: float
    accuracy_m: float
    captured_at: datetime
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class Stop:
    stop_id: str
    name: str
    latitude: float
    longitude: float
    parent_station: str | None = None


@dataclass(frozen=True, slots=True)
class Route:
    route_id: str
    short_name: str
    long_name: str
    route_type: str = "3"
    color: str = ""
    text_color: str = ""


@dataclass(slots=True)
class RouteVariant:
    route_id: str
    route_short_name: str
    route_long_name: str
    direction_id: int
    headsign: str
    trip_id: str
    shape_id: str | None
    stop_ids: list[str] = field(default_factory=list)
    shape_points: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class NearbyStop:
    stop: Stop
    distance_m: float


@dataclass(slots=True)
class NearbyStopGroup:
    """User-facing cluster of colocated GTFS stop records.

    TransJakarta may publish multiple stop IDs for platforms, directions, or
    corridors sharing the same public stop name. Members stay separate for ETA
    matching, while this group provides a clean display representation.
    """

    name: str
    distance_m: float
    members: list[NearbyStop] = field(default_factory=list)
    route_codes: tuple[str, ...] = ()
    service_classes: tuple[str, ...] = ()
    primary_service_class: str = "non_brt"
    favorite_route_codes: tuple[str, ...] = ()

    @property
    def has_favorite_route(self) -> bool:
        return bool(self.favorite_route_codes)


@dataclass(slots=True)
class Bus:
    bus_id: str
    route_code: str
    latitude: float
    longitude: float
    direction: str | int | None = None
    trip_id: str | None = None
    next_stops: Any = None
    previous_stops: Any = None
    observed_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Arrival:
    bus_id: str
    route_code: str
    stop_id: str
    stop_name: str
    stop_distance_m: float
    walking_minutes: float
    eta_minutes: float
    route_headsign: str
    direction_id: int
    stops_away: int | None
    confidence: str
    distance_along_route_m: float | None
    trip_id: str | None = None
    direction_status: str = "estimated"
    direction_evidence: tuple[str, ...] = ()
    direction_score: int = 0
    direction_ambiguous: bool = False
    direction_source: str = "gtfs-fallback"
    live_headsign: str = ""
    stops_away_source: str = "gtfs-nearest-stop"
    bus_data_age_seconds: float = 0.0
    # Persistent identity for a physical bus journey. The epoch increments when
    # the same bus body starts another trip or reverses direction, so an outbound
    # trip can never be suppressed by the previous inbound trip.
    journey_epoch: int = 1
    journey_transition: str = "continuing"
    previous_direction_label: str = ""
    # v0.3.4 GUI-facing context. Service class comes from the selected public
    # stop group, while favorite status is route-based (for example 4D/JAK 81),
    # never a physical bus body number.
    service_class: str = "non_brt"
    is_favorite_route: bool = False
    route_color: str = ""
    route_text_color: str = ""
