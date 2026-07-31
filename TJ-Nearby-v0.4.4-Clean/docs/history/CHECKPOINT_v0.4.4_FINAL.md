# TJ Nearby — Final Source Checkpoint v0.4.4

## Identity

- Version: **0.4.4**
- Release name: **All Nearby Stops Coverage**
- Checkpoint date: **31 July 2026**
- Primary platform: **Windows 10/11**
- Field validation platform: **Windows 11 (10.0.26200)**
- License: **MIT**
- Author: **Miftahul Ardli**

## Frozen product behavior

```text
GPS
→ every routed stop inside the service-specific radius
→ preserve stop ID, public name, direction, and platform
→ match live trip/direction/upcoming stop sequence
→ show every valid vehicle
→ deduplicate one physical vehicle to its closest still-upcoming nearby stop
```

### Invariants

1. Smart Nearby **does not cap stop groups at eight**.
2. `Flyover Jatinegara`, `Flyover Jatinegara Atas`, and `Flyover Jatinegara Bawah` remain distinct stops unless GTFS itself defines otherwise.
3. No route or stop is hardcoded for B25, 11M, JAK.41, or any other service.
4. Favorites affect ordering/priority only; they do not hide other routes.
5. One vehicle may match multiple sequential stops but is displayed once.
6. GUI shows the full engine snapshot; legacy `desktop.max_arrival_rows` is ignored.
7. A failed GPS/API cycle preserves the last successful snapshot and marks it stale.
8. A 55-second watchdog recovers a stuck engine cycle.
9. GUI errors are written to the activity log and must not permanently stop queue processing.
10. Notification processing occurs after the same snapshot has been applied to the monitor.

## Default service radii

| Service | Search radius | Notification radius |
|---|---:|---:|
| BRT | 1000 m | 800 m |
| non-BRT | 800 m | 600 m |
| JakLingko | 500 m | 400 m |

## Important modules

| Module | Responsibility |
|---|---|
| `config.py` | configuration loading, compatibility, defaults |
| `location.py` | Windows/macOS location providers |
| `gtfs.py` | GTFS cache, stops, routes, trips, stop sequence |
| `realtime.py` | reverse-engineered TJ realtime position retrieval |
| `selection.py` | all-nearby-stop selection and service classification |
| `eta.py` | trip/direction matching and ETA resolution |
| `engine.py` | end-to-end cycle, state, notification eligibility |
| `windows_gui.py` | monitor board, tray, refresh queue, diagnostic controls |
| `notify.py` | current pystray/legacy notification backend |
| `activity_log.py` | persistent log and exported diagnostic |
| `single_instance.py` | prevents duplicate Windows application instances |
| `windows_autostart.py` | per-user login autostart |

## Activity-log coverage audit

The exported diagnostic must expose:

- `raw_bus_positions`
- `nearby_stop_groups`
- `resolved_arrivals`
- monitored stop details
- scheduled routes at monitored stops
- realtime routes relevant to monitored stops
- matched arrival routes
- unresolved realtime routes
- notification eligibility and rejection reasons
- GUI exception, timeout, and recovery records

## Validation state

- **100 automated tests pass** with:

```bash
PYTHONPATH=src python -m pytest -q
```

- Wheel install/import smoke test was completed for the v0.4.4 build.
- Windows 11 field validation confirmed:
  - GPS acquisition;
  - realtime data retrieval;
  - multiple mixed routes shown simultaneously;
  - refresh/polling updates;
  - GUI queue/render recovery after the v0.4.3 fix;
  - activity-log export;
  - test notification banner.

## Known limitations / deferred work

### P0 — Native Windows notifications

Current notifications use a pystray/balloon fallback. Consequences:

- Windows may label the sender as `Python`;
- banners may not remain in Notification Center history;
- click activation and application identity are not native.

Target solution: Windows App Notification + stable AppUserModelID such as `TJNearby.Desktop`, while keeping pystray only for the system-tray icon and fallback.

### P1 — Standalone distribution

The current user package requires Python 3.11+ and internet access during installation. Next packaging target:

- PyInstaller Windows EXE build;
- installer or portable bundle;
- app icon and metadata identity;
- preferably code signing when distribution expands.

### P1 — Broad route-coverage field validation

The generalized algorithm is implemented, but broad field validation should continue across:

- BRT platforms in both directions;
- non-BRT stops sharing names with BRT facilities;
- terminal/station complexes;
- dense JakLingko stop clusters;
- loop routes, short turns, and detours;
- routes with missing or inconsistent realtime trip IDs.

## Windows installation layout

```text
%LOCALAPPDATA%\TJNearby\venv
%LOCALAPPDATA%\TJNearby\Start TJ Nearby.cmd
%USERPROFILE%\.tj-nearby\config.yaml
%USERPROFILE%\.tj-nearby\gtfs.zip
%USERPROFILE%\.tj-nearby\logs\tj-nearby-activity.log
```

Uninstall removes application files, shortcuts, and autostart, but preserves `%USERPROFILE%\.tj-nearby` unless the user deletes it manually.

## Release artifacts

The handoff consists of:

1. `TJ-Nearby-v0.4.4-Windows-User-Package.zip` — clean package for Windows users.
2. `Panduan-Pengguna-TJ-Nearby-v0.4.4-Windows.docx` — full user documentation.
3. `README-TJ-Nearby-v0.4.4-Windows.md` — quick-start documentation.
4. `TJ-Nearby-v0.4.4-Source-Checkpoint.zip` — full source, tests, reports, wheel, and documentation.
5. SHA-256 files generated beside each archive.

## Resume point

Development should resume from this v0.4.4 source checkpoint. Do not revert to the eight-stop-group selector. The next recommended version is **v0.4.5 — Native Windows Notifications & App Identity**.
