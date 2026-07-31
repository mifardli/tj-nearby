# Patch Notes v0.2.7

## API-first route direction

Arah/tujuan yang terlihat pada menu bar dan notifikasi sekarang mengikuti prioritas berikut:

1. `trip_headsign` dari objek bus API real-time.
2. `headsign`, `destination`, `destination_name`, `route_destination`, `direction_name`, `end_stop`, atau `terminal` dari API.
3. `trip_headsign` GTFS sebagai fallback jika API tidak memberi label tujuan.

GTFS tidak dihapus dari proses. `trip_id`, `direction_id`, urutan `next_stops`/`previous_stops`, dan shape tetap dipakai untuk memastikan bus memang bergerak menuju halte serta untuk menolak varian arah yang salah. Bila API dan GTFS berbeda kata tetapi `trip_id` atau `direction_id` live sudah memastikan cabangnya, label API tetap ditampilkan dan konflik dicatat dalam diagnostic.

## Diagnostic

Setiap arrival kini mencatat:

- `direction_source`
- `api_headsign`
- evidence validasi arah

## Tests

Ditambahkan pengujian bahwa `trip_headsign` API mengalahkan label API lain dan GTFS, serta GTFS tetap menjadi fallback saat API kosong.
