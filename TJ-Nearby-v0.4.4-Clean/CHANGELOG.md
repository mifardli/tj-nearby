# Changelog

Semua perubahan penting TJ Nearby dicatat di dokumen ini.

## [0.4.4] - 2026-07-31

### Added
- Pemantauan seluruh halte berjadwal dalam radius layanan.
- Audit cakupan rute realtime terhadap halte terpantau.
- Diagnostic untuk rute terjadwal, rute realtime, rute cocok, dan rute unresolved.

### Changed
- Menghapus kuota maksimal delapan grup halte.
- Menghapus batas default 60 baris pada monitor.
- Satu kendaraan yang cocok ke beberapa halte berurutan ditampilkan sekali pada halte terdekat yang belum dilewati.

## [0.4.3] - 2026-07-31

### Fixed
- Memperbaiki pemanggilan kontrak status arrival yang salah pada GUI.
- Memperbaiki kasus tabel hanya merender satu baris lalu berhenti.
- Menjaga queue GUI tetap aktif ketika satu callback gagal.

## [0.4.2] - 2026-07-31

### Added
- Activity log, ekspor diagnostic, uji notifikasi, dan watchdog refresh.

### Fixed
- Favorit lama tidak lagi otomatis menjadi filter ketat.
- Toast gagal tidak dianggap sudah terkirim.

## [0.4.1] - 2026-07-31

### Fixed
- Sinkronisasi snapshot GUI dan notifikasi.
- Deduplikasi arrival agar arah atau perjalanan berbeda tidak terlipat.
- Penanda Live, data lama, timeout, dan pembaruan gagal.

## [0.4.0] - 2026-07-31

### Added
- Windows Live Monitor Alpha dengan GUI, system tray, GPS Windows, dan daftar arrival.

## [0.3.4] dan sebelumnya

- Smart Nearby, favorit rute, notifikasi kedatangan, menu bar macOS, GTFS, dan engine pencocokan realtime.
- Riwayat teknis rinci tersedia di `docs/history/`.
