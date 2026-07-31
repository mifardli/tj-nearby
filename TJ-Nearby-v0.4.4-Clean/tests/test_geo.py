from tj_nearby.geo import haversine_m, project_progress_m


def test_haversine_zero():
    assert haversine_m(-6.2, 106.8, -6.2, 106.8) == 0


def test_haversine_reasonable():
    distance = haversine_m(0, 0, 0, 0.01)
    assert 1_100 < distance < 1_120


def test_polyline_progress():
    line = [(0.0, 0.0), (0.0, 0.01), (0.0, 0.02)]
    progress, off_route, total = project_progress_m(0.0, 0.015, line)
    assert 1_650 < progress < 1_680
    assert off_route < 1
    assert 2_200 < total < 2_240
