from pathlib import Path

import pytest

from tj_nearby import realtime


def test_resolve_ca_bundle_uses_existing_certifi_file():
    result = realtime._resolve_ca_bundle()
    assert result is True or Path(result).is_file()


def test_resolve_ca_bundle_reports_missing_resource_when_frozen(monkeypatch, tmp_path):
    import certifi
    import sys

    monkeypatch.setattr(certifi, "where", lambda: str(tmp_path / "missing-certifi.pem"))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Fake.app/Contents/MacOS/TJ Nearby"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("TJ_NEARBY_RESOURCE_DIR", raising=False)

    with pytest.raises(realtime.RealtimeError, match="Bundled CA certificate not found"):
        realtime._resolve_ca_bundle()


def test_get_buses_preserves_zero_direction(tmp_path, monkeypatch):
    from tj_nearby.config import AppConfig
    from tj_nearby.realtime import TjApiClient
    from tj_nearby.state import StateStore

    config = AppConfig(
        raw={"realtime": {"api_base": "https://example.invalid", "request_timeout_seconds": 1}},
        path=tmp_path / "config.yaml",
    )
    client = TjApiClient(config, StateStore(tmp_path / "state.sqlite"))
    monkeypatch.setattr(
        client,
        "_get",
        lambda *_args, **_kwargs: {
            "data": [
                {
                    "bus_body_no": "BUS-0",
                    "route_code": "4D",
                    "latitude": -6.2,
                    "longitude": 106.8,
                    "direction": 90,
                    "direction_id": 0,
                }
            ]
        },
    )
    try:
        buses = client.get_buses(-6.2, 106.8, 3)
    finally:
        client.close()
    assert len(buses) == 1
    assert buses[0].direction == 0
