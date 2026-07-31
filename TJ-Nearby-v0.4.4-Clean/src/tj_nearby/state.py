from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _normalize(value: object) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^0-9a-zà-ÿ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _headsigns_conflict(previous: str, current: str) -> bool:
    """Return True only for clearly different destinations.

    API labels may alternate between e.g. ``Pulo Gadung`` and
    ``Pulo Gadung via Pramuka``. Such enrichment is not a turnaround.
    """
    left = _normalize(previous)
    right = _normalize(current)
    if not left or not right or left == right or left in right or right in left:
        return False
    ignored = {"arah", "halte", "terminal", "menuju", "via", "dan", "ke", "dari"}
    left_tokens = {token for token in left.split() if token not in ignored}
    right_tokens = {token for token in right.split() if token not in ignored}
    if not left_tokens or not right_tokens:
        return False
    return not bool(left_tokens & right_tokens)


@dataclass(frozen=True, slots=True)
class JourneyResolution:
    epoch: int
    transition: str
    previous_direction_label: str = ""


class StateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    key TEXT PRIMARY KEY,
                    notified_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vehicle_journeys (
                    vehicle_key TEXT PRIMARY KEY,
                    journey_epoch INTEGER NOT NULL,
                    trip_id TEXT NOT NULL DEFAULT '',
                    direction_id TEXT NOT NULL DEFAULT '',
                    headsign TEXT NOT NULL DEFAULT '',
                    last_seen TEXT NOT NULL
                )
                """
            )

    def get_or_create_device_id(self) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key='device_id'").fetchone()
            if row:
                return str(row[0])
            value = f"tj-nearby-{uuid.uuid4().hex}"
            conn.execute("INSERT INTO meta(key, value) VALUES('device_id', ?)", (value,))
            return value

    def can_notify(self, key: str, cooldown_minutes: float) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT notified_at FROM notifications WHERE key=?", (key,)
            ).fetchone()
        if not row:
            return True
        previous = datetime.fromisoformat(str(row[0]))
        now = datetime.now(timezone.utc)
        return now - previous >= timedelta(minutes=cooldown_minutes)

    def seconds_since_latest(self, key_prefix: str) -> float | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT notified_at
                FROM notifications
                WHERE key LIKE ?
                ORDER BY notified_at DESC
                LIMIT 1
                """,
                (f"{key_prefix}%",),
            ).fetchone()
        if not row:
            return None
        previous = datetime.fromisoformat(str(row[0]))
        return max(0.0, (datetime.now(timezone.utc) - previous).total_seconds())

    def mark_notified(self, key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO notifications(key, notified_at) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET notified_at=excluded.notified_at
                """,
                (key, now),
            )

    def resolve_vehicle_journey(
        self,
        *,
        bus_id: str,
        route_code: str,
        trip_id: str | None,
        direction_id: int | str | None,
        headsign: str,
        max_state_age_hours: float = 12,
    ) -> JourneyResolution:
        """Resolve a stable journey epoch for one physical bus body.

        The same bus body may finish an inbound trip and immediately start the
        outbound trip. API providers also sometimes reuse a trip ID. A persistent
        epoch therefore changes whenever strong live identity changes: trip,
        direction, or destination. Missing values enrich the current state but do
        not create a false turnaround.
        """
        vehicle_key = f"{_normalize(bus_id)}|{_normalize(route_code)}"
        current_trip = _normalize(trip_id)
        current_direction = "" if direction_id is None else str(direction_id).strip()
        current_headsign = _normalize(headsign)
        now = datetime.now(timezone.utc)

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT journey_epoch, trip_id, direction_id, headsign, last_seen
                FROM vehicle_journeys
                WHERE vehicle_key=?
                """,
                (vehicle_key,),
            ).fetchone()

            if row is None:
                epoch = 1
                conn.execute(
                    """
                    INSERT INTO vehicle_journeys(
                        vehicle_key, journey_epoch, trip_id, direction_id, headsign, last_seen
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vehicle_key,
                        epoch,
                        current_trip,
                        current_direction,
                        current_headsign,
                        now.isoformat(),
                    ),
                )
                return JourneyResolution(epoch=epoch, transition="first-seen")

            previous_epoch = int(row[0])
            previous_trip = str(row[1] or "")
            previous_direction = str(row[2] or "")
            previous_headsign = str(row[3] or "")
            previous_seen = datetime.fromisoformat(str(row[4]))
            if previous_seen.tzinfo is None:
                previous_seen = previous_seen.replace(tzinfo=timezone.utc)

            state_expired = now - previous_seen > timedelta(hours=max(0.1, max_state_age_hours))
            trip_changed = bool(previous_trip and current_trip and previous_trip != current_trip)
            direction_changed = bool(
                previous_direction
                and current_direction
                and previous_direction != current_direction
            )
            headsign_changed = _headsigns_conflict(
                previous_headsign, current_headsign
            )

            transition = "continuing"
            epoch = previous_epoch
            if state_expired:
                epoch += 1
                transition = "state-expired-new-journey"
            elif direction_changed or headsign_changed:
                epoch += 1
                transition = "turnaround-detected"
            elif trip_changed:
                epoch += 1
                transition = "new-trip-detected"

            # Do not erase a strong previous value just because one API payload
            # temporarily omits it. This prevents false direction flips.
            stored_trip = current_trip or previous_trip
            stored_direction = current_direction or previous_direction
            stored_headsign = current_headsign or previous_headsign
            conn.execute(
                """
                UPDATE vehicle_journeys
                SET journey_epoch=?, trip_id=?, direction_id=?, headsign=?, last_seen=?
                WHERE vehicle_key=?
                """,
                (
                    epoch,
                    stored_trip,
                    stored_direction,
                    stored_headsign,
                    now.isoformat(),
                    vehicle_key,
                ),
            )

        previous_label = previous_headsign or (
            f"direction {previous_direction}" if previous_direction else ""
        )
        return JourneyResolution(
            epoch=epoch,
            transition=transition,
            previous_direction_label=previous_label,
        )
