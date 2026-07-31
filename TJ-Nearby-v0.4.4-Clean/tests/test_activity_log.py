from pathlib import Path

from tj_nearby.activity_log import activity_log_path, setup_activity_logger, tail_activity_log


def test_activity_log_is_rotating_and_tail_is_readable(tmp_path: Path):
    logger = setup_activity_logger(tmp_path)
    logger.info("cycle.start token=1")
    logger.info("cycle.finish arrivals=3")
    path = activity_log_path(tmp_path)
    assert path.exists()
    tail = tail_activity_log(tmp_path, max_lines=20)
    assert "cycle.start token=1" in tail
    assert "cycle.finish arrivals=3" in tail


def test_tail_activity_log_handles_missing_file(tmp_path: Path):
    text = tail_activity_log(tmp_path, max_lines=20)
    assert "belum tersedia" in text
