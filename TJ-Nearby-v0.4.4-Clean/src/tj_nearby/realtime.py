from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import AppConfig
from .models import Bus
from .state import StateStore


class RealtimeError(RuntimeError):
    pass


def _resolve_ca_bundle() -> str | bool:
    """Return a usable CA bundle for normal and py2app-frozen execution.

    py2app can package the ``certifi`` Python module without its ``cacert.pem``
    data file. Passing an explicit bundled resource path prevents httpx from
    failing during client construction with ``FileNotFoundError``.
    """
    try:
        import certifi

        candidate = Path(certifi.where())
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass

    candidates: list[Path] = []
    resource_env = os.environ.get("TJ_NEARBY_RESOURCE_DIR")
    if resource_env:
        candidates.append(Path(resource_env) / "cacert.pem")

    executable = Path(sys.executable).resolve()
    # Typical py2app layout: App.app/Contents/MacOS/<executable>
    if len(executable.parents) >= 2:
        candidates.append(executable.parents[1] / "Resources" / "cacert.pem")

    try:
        from Foundation import NSBundle

        resource_path = NSBundle.mainBundle().resourcePath()
        if resource_path:
            candidates.append(Path(str(resource_path)) / "cacert.pem")
    except Exception:
        pass

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    # On regular Python installations, system defaults remain a valid fallback.
    # The packaged app includes cacert.pem, so reaching this branch there is an
    # actionable packaging error rather than a silent TLS downgrade.
    if getattr(sys, "frozen", False):
        searched = ", ".join(str(path) for path in candidates) or "no resource paths"
        raise RealtimeError(f"Bundled CA certificate not found; searched: {searched}")
    return True


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, OSError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _parse_datetime(int(text))
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_token(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("token", "access_token", "jwt"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = _find_token(value)
            if found:
                return found
    return None


def _jwt_expiry(token: str) -> float:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        return float(decoded.get("exp", 0))
    except Exception:
        return 0


class TjApiClient:
    def __init__(self, config: AppConfig, state: StateStore):
        self.config = config
        self.state = state
        self.api_base = str(config.get("realtime.api_base", "https://tijeapi.transjakarta.co.id")).rstrip("/")
        self.timeout = float(config.get("realtime.request_timeout_seconds", 20))
        self.device_id = state.get_or_create_device_id()
        self.token: str | None = None
        self.token_expiry = 0.0
        self.app_version: str | None = None
        self.client = httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            verify=_resolve_ca_bundle(),
        )

    def close(self) -> None:
        self.client.close()

    def _headers(self, version: str, authenticated: bool = True) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "okhttp/4.12.0",
            "X-App-OS": "android",
            "X-App-Version": version,
            "X-Device-ID": self.device_id,
        }
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def authenticate(self, force: bool = False) -> str:
        now = datetime.now(timezone.utc).timestamp()
        if not force and self.token and now < self.token_expiry - 60:
            return self.token
        versions = [str(value) for value in (self.config.get("realtime.app_versions", []) or [])]
        if self.app_version:
            versions = [self.app_version] + [v for v in versions if v != self.app_version]
        if not versions:
            versions = ["3.0.0", "2.10.2"]
        errors: list[str] = []
        for version in versions:
            try:
                response = self.client.post(
                    f"{self.api_base}/v1/auth/login/guest",
                    headers=self._headers(version, authenticated=False),
                    json={"device_id": self.device_id},
                )
                response.raise_for_status()
                payload = response.json()
                token = _find_token(payload)
                if not token:
                    raise RealtimeError("Guest login returned no token")
                self.token = str(token)
                self.token_expiry = _jwt_expiry(self.token) or (now + 86400)
                self.app_version = version
                return self.token
            except Exception as exc:
                errors.append(f"{version}: {exc}")
        raise RealtimeError("Guest authentication failed; " + " | ".join(errors))

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        self.authenticate()
        version = self.app_version or "3.0.0"
        response = self.client.get(
            f"{self.api_base}{path}",
            params=params,
            headers=self._headers(version),
        )
        if response.status_code == 401:
            self.authenticate(force=True)
            version = self.app_version or version
            response = self.client.get(
                f"{self.api_base}{path}",
                params=params,
                headers=self._headers(version),
            )
        response.raise_for_status()
        return response.json()

    def get_buses(self, latitude: float, longitude: float, radius_km: float) -> list[Bus]:
        payload = self._get(
            "/v1/bus",
            {"latitude": latitude, "longitude": longitude, "radius": radius_km},
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise RealtimeError("Unexpected /v1/bus response structure")
        buses: list[Bus] = []
        retrieved_at = datetime.now(timezone.utc)
        for row in rows:
            if not isinstance(row, dict):
                continue
            lat = _to_float(row.get("latitude") or row.get("lat"))
            lon = _to_float(row.get("longitude") or row.get("lng") or row.get("lon"))
            if lat is None or lon is None:
                continue
            bus_id = str(
                row.get("bus_body_no")
                or row.get("body_no")
                or row.get("vehicle_id")
                or row.get("id")
                or ""
            ).strip()
            route_code = str(
                row.get("route_code")
                or row.get("route_short_name")
                or row.get("route")
                or ""
            ).strip()
            if not bus_id or not route_code:
                continue
            observed = None
            for key in ("timestamp", "gps_time", "updated_at", "last_update", "last_updated"):
                observed = _parse_datetime(row.get(key))
                if observed:
                    break
            buses.append(
                Bus(
                    bus_id=bus_id,
                    route_code=route_code,
                    latitude=lat,
                    longitude=lon,
                    direction=(
                        row.get("direction_id")
                        if row.get("direction_id") is not None
                        else row.get("direction")
                    ),
                    trip_id=(str(row.get("trip_id")).strip() if row.get("trip_id") else None),
                    next_stops=row.get("next_stops"),
                    previous_stops=row.get("prev_stops") or row.get("previous_stops"),
                    observed_at=observed or retrieved_at,
                    raw={key: value for key, value in row.items() if key != "stops"},
                )
            )
        return buses
