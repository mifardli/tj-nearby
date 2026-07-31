from pathlib import Path

from tj_nearby.config import AppConfig
from tj_nearby.location import get_location


def test_manual_location(tmp_path: Path):
    config = AppConfig(
        raw={"location": {"mode": "manual", "manual_latitude": -6.2, "manual_longitude": 106.8}},
        path=tmp_path / "config.yaml",
    )
    fix = get_location(config)
    assert fix.latitude == -6.2
    assert fix.longitude == 106.8
    assert fix.source == "manual"


def test_set_location_mode_persists(tmp_path: Path):
    from tj_nearby.config import load_config, set_config_value

    path = tmp_path / "config.yaml"
    path.write_text("location:\n  mode: manual\n", encoding="utf-8")
    config = load_config(path)
    set_config_value(config, "location.mode", "auto")
    assert load_config(path).get("location.mode") == "auto"


def test_auto_mode_does_not_silently_use_manual_fallback(tmp_path: Path, monkeypatch):
    import tj_nearby.location as location_module

    config = AppConfig(
        raw={
            "location": {
                "mode": "auto",
                "manual_latitude": -6.2,
                "manual_longitude": 106.8,
                "allow_manual_fallback": False,
            }
        },
        path=tmp_path / "config.yaml",
    )
    monkeypatch.setattr(location_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        location_module,
        "_core_location_fix",
        lambda _timeout: (_ for _ in ()).throw(location_module.LocationError("denied")),
    )
    try:
        location_module.get_location(config)
    except location_module.LocationError as exc:
        assert "denied" in str(exc)
    else:
        raise AssertionError("auto mode unexpectedly used manual fallback")


def test_objc_lookup_reuses_registered_class():
    from tj_nearby.location import _lookup_objc_class

    sentinel = object()

    class FakeObjC:
        @staticmethod
        def lookUpClass(name):
            assert name == "TJNearbyLocationDelegate"
            return sentinel

    assert _lookup_objc_class(FakeObjC, "TJNearbyLocationDelegate") is sentinel


def test_objc_lookup_returns_none_for_unregistered_class():
    from tj_nearby.location import _lookup_objc_class

    class FakeObjC:
        @staticmethod
        def lookUpClass(_name):
            raise RuntimeError("no such class")

    assert _lookup_objc_class(FakeObjC, "TJNearbyLocationDelegate") is None


def _install_fake_winrt(monkeypatch):
    import sys
    import types
    from datetime import datetime, timezone

    runtime = types.ModuleType("winrt.runtime")

    class ApartmentType:
        SINGLE_THREADED = 1
        MULTI_THREADED = 2

    runtime.ApartmentType = ApartmentType
    runtime.init_apartment = lambda _kind: None

    geolocation = types.ModuleType("winrt.windows.devices.geolocation")

    class Access:
        name = "ALLOWED"

        def __eq__(self, other):
            return isinstance(other, Access)

    class GeolocationAccessStatus:
        ALLOWED = Access()

    class PositionAccuracy:
        HIGH = 1

    class Coordinate:
        latitude = -6.21
        longitude = 106.87
        accuracy = 18.0
        timestamp = datetime.now(timezone.utc)

    class Position:
        coordinate = Coordinate()

    class Geolocator:
        desired_accuracy = None
        desired_accuracy_in_meters = None

        @staticmethod
        async def request_access_async():
            return GeolocationAccessStatus.ALLOWED

        async def get_geoposition_async(self, *_args):
            return Position()

    geolocation.GeolocationAccessStatus = GeolocationAccessStatus
    geolocation.Geolocator = Geolocator
    geolocation.PositionAccuracy = PositionAccuracy

    modules = {
        "winrt": types.ModuleType("winrt"),
        "winrt.runtime": runtime,
        "winrt.windows": types.ModuleType("winrt.windows"),
        "winrt.windows.devices": types.ModuleType("winrt.windows.devices"),
        "winrt.windows.devices.geolocation": geolocation,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_windows_location_permission_and_fix(monkeypatch):
    import tj_nearby.location as location_module

    _install_fake_winrt(monkeypatch)
    monkeypatch.setattr(location_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(location_module, "_WINDOWS_ACCESS_GRANTED", False)
    monkeypatch.setattr(location_module, "_WINDOWS_ACCESS_STATUS", "not-requested")

    assert location_module.request_windows_location_access() == "allowed"
    fix = location_module._windows_location_fix(5)
    assert fix.source == "windows-location"
    assert fix.latitude == -6.21
    assert fix.longitude == 106.87
    assert fix.accuracy_m == 18.0
