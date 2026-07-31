from __future__ import annotations

import asyncio
import platform
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .config import AppConfig
from .models import LocationFix


class LocationError(RuntimeError):
    pass


_LOCATION_DELEGATE_CLASS = None
_AUTHORIZATION_DELEGATE_CLASS = None
_WINDOWS_ACCESS_GRANTED = False
_WINDOWS_ACCESS_STATUS = "not-requested"


def _manual_fix(config: AppConfig, source: str = "manual") -> LocationFix:
    lat = config.get("location.manual_latitude")
    lon = config.get("location.manual_longitude")
    if lat is None or lon is None:
        raise LocationError("Manual location coordinates are not configured")
    return LocationFix(
        latitude=float(lat),
        longitude=float(lon),
        accuracy_m=0.0,
        captured_at=datetime.now(timezone.utc),
        source=source,
    )


def get_location(config: AppConfig) -> LocationFix:
    mode = str(config.get("location.mode", "auto")).lower()
    if mode == "manual":
        return _manual_fix(config)

    system = platform.system()
    timeout = float(config.get("location.timeout_seconds", 20))
    try:
        if system == "Darwin":
            return _core_location_fix(timeout)
        if system == "Windows":
            if not _WINDOWS_ACCESS_GRANTED and threading.current_thread() is threading.main_thread():
                request_windows_location_access()
            return _windows_location_fix(timeout)
        return _manual_fix(config, source="manual-unsupported-platform")
    except Exception as exc:
        lat = config.get("location.manual_latitude")
        lon = config.get("location.manual_longitude")
        allow_fallback = bool(config.get("location.allow_manual_fallback", False))
        if allow_fallback and lat is not None and lon is not None:
            return _manual_fix(config, source="manual-fallback")
        if isinstance(exc, LocationError):
            raise
        provider = "Core Location" if system == "Darwin" else "Windows Location"
        raise LocationError(f"{provider} failed: {exc}") from exc


def request_windows_location_access() -> str:
    """Request Windows location permission from the foreground UI thread.

    Microsoft requires ``Geolocator.RequestAccessAsync`` to run while the app is
    foregrounded and from its UI thread. The Windows monitor calls this once at
    startup, before background polling begins.
    """

    global _WINDOWS_ACCESS_GRANTED, _WINDOWS_ACCESS_STATUS
    if platform.system() != "Windows":
        return "unsupported-platform"
    if threading.current_thread() is not threading.main_thread():
        raise LocationError("Windows location permission must be requested from the UI thread")
    try:
        from winrt.runtime import ApartmentType, init_apartment
        from winrt.windows.devices.geolocation import GeolocationAccessStatus, Geolocator
    except ImportError as exc:
        raise LocationError(
            "Windows location support is not installed. Run Install Windows.bat "
            "or: pip install -e '.[windows]'"
        ) from exc
    try:
        init_apartment(ApartmentType.SINGLE_THREADED)
    except Exception:
        # The thread may already be initialized by Tk or another component.
        pass

    async def resolve():
        return await Geolocator.request_access_async()

    try:
        access = asyncio.run(resolve())
    except OSError as exc:
        _WINDOWS_ACCESS_STATUS = "request-failed"
        raise LocationError(
            "Windows could not request location access. Turn on Settings > "
            "Privacy & security > Location and allow desktop apps."
        ) from exc
    _WINDOWS_ACCESS_GRANTED = access == GeolocationAccessStatus.ALLOWED
    _WINDOWS_ACCESS_STATUS = getattr(access, "name", str(access)).replace("_", "-").lower()
    if not _WINDOWS_ACCESS_GRANTED:
        raise LocationError(
            f"Windows location access is {_WINDOWS_ACCESS_STATUS}. Open Settings > "
            "Privacy & security > Location, enable Location services, and allow desktop apps."
        )
    return _WINDOWS_ACCESS_STATUS


def _windows_location_fix(timeout_seconds: float) -> LocationFix:
    """Read the current Windows Location Service position through PyWinRT.

    This runs from the engine's worker thread, so ``asyncio.run`` does not
    interfere with the Tk main loop. Windows can derive a position from GNSS,
    Wi-Fi, cellular, IP, or the configured default location.
    """

    async def resolve() -> LocationFix:
        try:
            from winrt.windows.devices.geolocation import (
                Geolocator,
                PositionAccuracy,
            )
        except ImportError as exc:
            raise LocationError(
                "Windows location support is not installed. Run Install Windows.bat "
                "or: pip install -e '.[windows]'"
            ) from exc

        if not _WINDOWS_ACCESS_GRANTED:
            raise LocationError(
                "Windows location permission has not been granted for this session. "
                "Open the TJ Nearby monitor so Windows can request permission."
            )

        try:
            from winrt.runtime import ApartmentType, init_apartment
            init_apartment(ApartmentType.MULTI_THREADED)
        except Exception:
            pass

        locator = Geolocator()
        locator.desired_accuracy = PositionAccuracy.HIGH
        try:
            locator.desired_accuracy_in_meters = 100
        except Exception:
            pass

        try:
            position = await locator.get_geoposition_async(
                timedelta(seconds=0),
                timedelta(seconds=max(1.0, timeout_seconds)),
            )
        except TypeError:
            # Some SDK projections expose only the parameterless overload.
            position = await locator.get_geoposition_async()
        except OSError as exc:
            raise LocationError(
                "Windows Location Service did not return a position. Check Location "
                "services, Wi-Fi, and the default location in Windows Settings."
            ) from exc

        coordinate = position.coordinate
        latitude = getattr(coordinate, "latitude", None)
        longitude = getattr(coordinate, "longitude", None)
        if latitude is None or longitude is None:
            point = coordinate.point.position
            latitude = point.latitude
            longitude = point.longitude
        accuracy = float(getattr(coordinate, "accuracy", 100.0) or 100.0)
        timestamp = getattr(coordinate, "timestamp", None) or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return LocationFix(
            latitude=float(latitude),
            longitude=float(longitude),
            accuracy_m=accuracy,
            captured_at=timestamp,
            source="windows-location",
        )

    try:
        return asyncio.run(resolve())
    except LocationError:
        raise
    except Exception as exc:
        raise LocationError(f"Unexpected Windows location error: {exc}") from exc


def _windows_authorization_status_name() -> str:
    try:
        import winrt.windows.devices.geolocation  # noqa: F401
    except ImportError:
        return "pywinrt-missing"
    return _WINDOWS_ACCESS_STATUS


def _lookup_objc_class(objc_module, class_name: str):
    """Return an existing Objective-C class, or None when it is not registered.

    PyObjC registers every NSObject subclass globally in the Objective-C runtime.
    Defining a same-named delegate inside a function on every poll therefore raises
    "overriding existing Objective-C class". Looking up and reusing the registered
    class makes repeated location checks safe.
    """
    try:
        return objc_module.lookUpClass(class_name)
    except Exception:
        return None


def _get_location_delegate_class():
    global _LOCATION_DELEGATE_CLASS
    if _LOCATION_DELEGATE_CLASS is not None:
        return _LOCATION_DELEGATE_CLASS

    import objc
    from Foundation import NSObject

    existing = _lookup_objc_class(objc, "TJNearbyLocationDelegate")
    if existing is not None:
        _LOCATION_DELEGATE_CLASS = existing
        return existing

    class TJNearbyLocationDelegate(NSObject):
        def init(self):  # type: ignore[no-untyped-def]
            self = objc.super(TJNearbyLocationDelegate, self).init()
            if self is None:
                return None
            self.latest = None
            self.error = None
            return self

        def locationManager_didUpdateLocations_(self, manager, locations):  # type: ignore[no-untyped-def]
            if locations and len(locations) > 0:
                self.latest = locations[-1]

        def locationManager_didFailWithError_(self, manager, error):  # type: ignore[no-untyped-def]
            self.error = error

    _LOCATION_DELEGATE_CLASS = TJNearbyLocationDelegate
    return TJNearbyLocationDelegate


def _get_authorization_delegate_class():
    global _AUTHORIZATION_DELEGATE_CLASS
    if _AUTHORIZATION_DELEGATE_CLASS is not None:
        return _AUTHORIZATION_DELEGATE_CLASS

    import objc
    from Foundation import NSObject

    existing = _lookup_objc_class(objc, "TJNearbyAuthorizationDelegate")
    if existing is not None:
        _AUTHORIZATION_DELEGATE_CLASS = existing
        return existing

    class TJNearbyAuthorizationDelegate(NSObject):
        def initWithCallback_(self, handler):  # type: ignore[no-untyped-def]
            self = objc.super(TJNearbyAuthorizationDelegate, self).init()
            if self is None:
                return None
            self.handler = handler
            return self

        def _report(self, manager):  # type: ignore[no-untyped-def]
            if self.handler is not None:
                try:
                    self.handler(authorization_status_name())
                except Exception:
                    pass

        def locationManagerDidChangeAuthorization_(self, manager):  # type: ignore[no-untyped-def]
            self._report(manager)

        def locationManager_didChangeAuthorizationStatus_(self, manager, status):  # type: ignore[no-untyped-def]
            self._report(manager)

    _AUTHORIZATION_DELEGATE_CLASS = TJNearbyAuthorizationDelegate
    return TJNearbyAuthorizationDelegate


def _core_location_fix(timeout_seconds: float) -> LocationFix:
    try:
        import CoreLocation
        from Foundation import NSDate, NSRunLoop
    except ImportError as exc:
        raise LocationError(
            "PyObjC CoreLocation is not installed. Run: pip install -e '.[mac]'"
        ) from exc

    if not CoreLocation.CLLocationManager.locationServicesEnabled():
        raise LocationError("macOS Location Services are disabled")

    DelegateClass = _get_location_delegate_class()
    delegate = DelegateClass.alloc().init()
    manager = CoreLocation.CLLocationManager.alloc().init()
    manager.setDelegate_(delegate)
    manager.setDesiredAccuracy_(CoreLocation.kCLLocationAccuracyHundredMeters)

    status = None
    if hasattr(manager, "authorizationStatus"):
        status = int(manager.authorizationStatus())
    elif hasattr(CoreLocation.CLLocationManager, "authorizationStatus"):
        status = int(CoreLocation.CLLocationManager.authorizationStatus())

    denied_values = {
        int(getattr(CoreLocation, "kCLAuthorizationStatusDenied", 2)),
        int(getattr(CoreLocation, "kCLAuthorizationStatusRestricted", 1)),
    }
    if status in denied_values:
        raise LocationError(
            "Location permission is denied or restricted. Open System Settings > "
            "Privacy & Security > Location Services and allow TJ Nearby. For Terminal "
            "testing, set location.mode to manual."
        )

    if hasattr(manager, "requestWhenInUseAuthorization"):
        manager.requestWhenInUseAuthorization()
    manager.startUpdatingLocation()

    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.25))
            if delegate.error is not None:
                error = delegate.error
                code = None
                try:
                    code = int(error.code())
                except Exception:
                    pass
                if code == 1:
                    raise LocationError(
                        "Core Location permission denied (kCLErrorDenied). Terminal/Python "
                        "does not have a valid macOS location authorization context. Use "
                        "manual mode for testing, or run the packaged TJ Nearby.app and "
                        "allow Location Services."
                    )
                raise LocationError(str(error))
            if delegate.latest is not None:
                location: Any = delegate.latest
                coordinate = location.coordinate()
                accuracy = float(location.horizontalAccuracy())
                if accuracy >= 0:
                    return LocationFix(
                        latitude=float(coordinate.latitude),
                        longitude=float(coordinate.longitude),
                        accuracy_m=accuracy,
                        captured_at=datetime.now(timezone.utc),
                        source="core-location",
                    )
    finally:
        manager.stopUpdatingLocation()
        manager.setDelegate_(None)
    raise LocationError("Timed out waiting for a macOS location fix")


def authorization_status_name() -> str:
    """Return a readable platform location authorization status."""
    system = platform.system()
    if system == "Windows":
        return _windows_authorization_status_name()
    if system != "Darwin":
        return "unsupported-platform"
    try:
        import CoreLocation
    except ImportError:
        return "pyobjc-missing"
    try:
        if hasattr(CoreLocation.CLLocationManager, "authorizationStatus"):
            status = int(CoreLocation.CLLocationManager.authorizationStatus())
        else:
            manager = CoreLocation.CLLocationManager.alloc().init()
            status = int(manager.authorizationStatus())
    except Exception:
        return "unknown"
    mapping = {
        int(getattr(CoreLocation, "kCLAuthorizationStatusNotDetermined", 0)): "not-determined",
        int(getattr(CoreLocation, "kCLAuthorizationStatusRestricted", 1)): "restricted",
        int(getattr(CoreLocation, "kCLAuthorizationStatusDenied", 2)): "denied",
        int(getattr(CoreLocation, "kCLAuthorizationStatusAuthorizedAlways", 3)): "authorized-always",
        int(getattr(CoreLocation, "kCLAuthorizationStatusAuthorizedWhenInUse", 4)): "authorized-when-in-use",
        int(getattr(CoreLocation, "kCLAuthorizationStatusAuthorized", 3)): "authorized",
    }
    return mapping.get(status, f"status-{status}")


def request_location_authorization(callback: Callable[[str], None] | None = None):
    """Request location permission from the packaged app's main thread.

    The manager and delegate must be retained by the caller until the callback
    arrives. The Objective-C delegate class is registered once and reused across
    repeated button presses and polling cycles.
    """
    if platform.system() != "Darwin":
        raise LocationError("Automatic location authorization requires macOS")
    try:
        import CoreLocation
    except ImportError as exc:
        raise LocationError("PyObjC CoreLocation is not installed") from exc

    DelegateClass = _get_authorization_delegate_class()
    delegate = DelegateClass.alloc().initWithCallback_(callback)
    manager = CoreLocation.CLLocationManager.alloc().init()
    manager.setDelegate_(delegate)
    status = authorization_status_name()
    if status == "not-determined":
        manager.requestWhenInUseAuthorization()
    elif callback is not None:
        callback(status)
    return manager, delegate
