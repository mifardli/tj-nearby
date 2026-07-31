from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

SERVICE_BRT = "brt"
SERVICE_NON_BRT = "non_brt"
SERVICE_JAKLINGKO = "jaklingko"
SERVICE_ORDER = (SERVICE_BRT, SERVICE_NON_BRT, SERVICE_JAKLINGKO)

# Main TransJakarta corridor codes. A stop group that serves one of these routes
# is treated as a BRT-access stop. Operators can extend/override this list in
# config without changing the application code.
DEFAULT_BRT_ROUTE_CODES = tuple(str(number) for number in range(1, 15))
DEFAULT_JAKLINGKO_PREFIXES = ("JAK",)


def normalize_route_code(value: str) -> str:
    """Normalize route codes across labels such as ``JAK 81`` and ``JAK.81``."""
    return re.sub(r"[^0-9A-Z]+", "", str(value or "").upper())


def _configured_values(config: Any, path: str, default: Iterable[str]) -> tuple[str, ...]:
    values = config.get(path, None) if config is not None else None
    if values is None:
        values = default
    if isinstance(values, str):
        values = [values]
    return tuple(str(value).strip() for value in values if str(value).strip())


def classify_route_code(route_code: str, config: Any = None) -> str:
    """Classify a route using stable code patterns plus configurable overrides.

    Classification is intentionally conservative:
    - JAK-prefixed routes are JakLingko/Mikrotrans.
    - Exact main-corridor codes 1-14 are BRT.
    - Every other route is non-BRT.

    Stop groups can contain multiple classes. For example, a BRT platform may
    serve a main corridor and several non-BRT routes at the same public stop.
    """
    normalized = normalize_route_code(route_code)
    if not normalized:
        return SERVICE_NON_BRT

    exact_jaklingko = {
        normalize_route_code(value)
        for value in _configured_values(
            config,
            "nearby.classification.jaklingko_routes",
            (),
        )
    }
    jaklingko_prefixes = tuple(
        normalize_route_code(value)
        for value in _configured_values(
            config,
            "nearby.classification.jaklingko_prefixes",
            DEFAULT_JAKLINGKO_PREFIXES,
        )
    )
    if normalized in exact_jaklingko or any(
        prefix and normalized.startswith(prefix) for prefix in jaklingko_prefixes
    ):
        return SERVICE_JAKLINGKO

    brt_routes = {
        normalize_route_code(value)
        for value in _configured_values(
            config,
            "nearby.classification.brt_routes",
            DEFAULT_BRT_ROUTE_CODES,
        )
    }
    numeric_normalized = str(int(normalized)) if normalized.isdigit() else normalized
    if normalized in brt_routes or numeric_normalized in brt_routes:
        return SERVICE_BRT

    return SERVICE_NON_BRT


def classify_route_codes(route_codes: Iterable[str], config: Any = None) -> tuple[str, ...]:
    present = {classify_route_code(code, config) for code in route_codes if str(code).strip()}
    return tuple(service for service in SERVICE_ORDER if service in present)


def primary_service_class(service_classes: Iterable[str]) -> str:
    classes = set(service_classes)
    for service in SERVICE_ORDER:
        if service in classes:
            return service
    return SERVICE_NON_BRT


def service_label(service_class: str) -> str:
    return {
        SERVICE_BRT: "BRT",
        SERVICE_NON_BRT: "non-BRT",
        SERVICE_JAKLINGKO: "JakLingko",
    }.get(service_class, service_class)
