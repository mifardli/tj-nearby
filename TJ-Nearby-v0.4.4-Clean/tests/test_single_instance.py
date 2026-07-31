from tj_nearby.single_instance import SingleInstanceGuard, mutex_name


def test_mutex_name_is_stable_and_windows_safe():
    assert mutex_name("TJ Nearby Windows") == "Local\\TJ_Nearby_Windows"


def test_single_instance_guard_is_noop_off_windows(monkeypatch):
    monkeypatch.setattr("tj_nearby.single_instance.platform.system", lambda: "Linux")
    guard = SingleInstanceGuard("TJ Nearby")
    assert guard.acquire() is True
    assert guard.already_running is False
    guard.release()
