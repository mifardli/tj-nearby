from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .gtfs import GtfsFeed
from .models import NearbyStopGroup
from .service import SERVICE_BRT, SERVICE_JAKLINGKO, SERVICE_NON_BRT, SERVICE_ORDER

DEFAULT_SEARCH_RADII_M = {
    SERVICE_BRT: 1000.0,
    SERVICE_NON_BRT: 800.0,
    SERVICE_JAKLINGKO: 500.0,
}
DEFAULT_NOTIFICATION_RADII_M = {
    SERVICE_BRT: 800.0,
    SERVICE_NON_BRT: 600.0,
    SERVICE_JAKLINGKO: 400.0,
}
def service_setting(config: Any, service: str, key: str, default: float | int | bool) -> Any:
    return config.get(f"nearby.services.{service}.{key}", default)


def service_enabled(config: Any, service: str) -> bool:
    return bool(service_setting(config, service, "enabled", True))


def service_search_radius_m(config: Any, service: str) -> float:
    if service not in DEFAULT_SEARCH_RADII_M:
        service = SERVICE_NON_BRT
    return float(
        service_setting(
            config,
            service,
            "search_radius_m",
            DEFAULT_SEARCH_RADII_M[service],
        )
    )


def service_notification_radius_m(config: Any, service: str) -> float:
    if service not in DEFAULT_NOTIFICATION_RADII_M:
        service = SERVICE_NON_BRT
    return float(
        service_setting(
            config,
            service,
            "notification_radius_m",
            DEFAULT_NOTIFICATION_RADII_M[service],
        )
    )


def _eligible_for_service(group: NearbyStopGroup, config: Any, service: str) -> bool:
    return (
        service_enabled(config, service)
        and service in group.service_classes
        and group.distance_m <= service_search_radius_m(config, service)
    )


def _eligible_any(group: NearbyStopGroup, config: Any) -> bool:
    return any(_eligible_for_service(group, config, service) for service in SERVICE_ORDER)


def select_smart_stop_groups(
    groups: Iterable[NearbyStopGroup],
    config: Any,
    *,
    limit: int | None = None,
) -> list[NearbyStopGroup]:
    """Return every eligible nearby stop group inside the service radii.

    v0.4.4 deliberately removes the old eight-group quota. A GPS-first monitor
    must not discard a valid boarding stop before realtime matching merely
    because several closer stops already occupied the selection slots. Every
    stop keeps its own GTFS stop ID, direction, platform, and public name; only
    exact colocated records already grouped by :meth:`GtfsFeed.nearest_stop_groups`
    share a display group.

    ``limit`` is retained only for API compatibility with older callers and is
    intentionally ignored in smart mode. Display components may paginate or
    scroll, but the monitoring engine receives the complete eligible set.
    """
    del limit
    candidates = [group for group in groups if _eligible_any(group, config)]
    return sorted(candidates, key=lambda group: (group.distance_m, group.name.casefold()))


def nearby_stop_groups_for_location(
    feed: GtfsFeed,
    config: Any,
    latitude: float,
    longitude: float,
) -> list[NearbyStopGroup]:
    mode = str(config.get("nearby.selection_mode", "smart")).strip().lower()
    cluster_radius = float(config.get("nearby.cluster_radius_m", 35))

    if mode == "nearest":
        return feed.nearest_stop_groups(
            latitude,
            longitude,
            radius_m=float(config.get("nearby.search_radius_m", 700)),
            limit=int(config.get("nearby.max_stops", 5)),
            cluster_radius_m=cluster_radius,
        )

    enabled_radii = [
        service_search_radius_m(config, service)
        for service in SERVICE_ORDER
        if service_enabled(config, service)
    ]
    if not enabled_radii:
        return []

    # Fetch every routed GTFS stop inside the largest enabled service radius.
    # Service-specific radii are then applied per group. There is no group quota:
    # a valid B25/11M platform cannot be hidden by eight slightly closer stops.
    groups = feed.nearest_stop_groups(
        latitude,
        longitude,
        radius_m=max(enabled_radii),
        limit=None,
        cluster_radius_m=cluster_radius,
    )
    return select_smart_stop_groups(groups, config)
