# TJ Nearby v0.3.4 — Smart Nearby & Route Favorites

## Ringkasan

v0.3.4 memperbaiki cara aplikasi memilih halte berdasarkan GPS. Pada versi sebelumnya, lima kelompok halte terdekat diambil tanpa mempertimbangkan jenis layanan. Di area dengan banyak titik JakLingko, halte BRT terdekat dapat tersingkir walaupun masih realistis dijangkau.

Versi ini tetap mempertahankan seluruh perbaikan arah, turnaround, anti-spam, dan stabilitas menu bar dari v0.3.2–v0.3.3.

## Perubahan utama

### Smart Stop Selection

- Mengelompokkan akses halte menjadi `brt`, `non_brt`, dan `jaklingko` berdasarkan rute yang melayani kelompok GTFS tersebut.
- Memesan representasi halte terdekat untuk setiap jenis layanan yang tersedia.
- BRT yang dipilih selalu BRT terdekat di dalam radius, bukan BRT acak atau halte BRT yang lebih jauh.
- Kelompok halte campuran, misalnya koridor utama bersama rute non-BRT, tidak diduplikasi.
- Slot tersisa tetap diisi berdasarkan kedekatan GPS.

### Radius per layanan

Default awal:

| Layanan | Radius pencarian | Radius notifikasi |
|---|---:|---:|
| BRT | 1.000 m | 800 m |
| non-BRT | 800 m | 600 m |
| JakLingko | 500 m | 400 m |

Radius tersebut dapat diubah dari `config.yaml`. Mode lama tetap tersedia melalui `nearby.selection_mode: nearest`.

### Favorit rute

- Favorit ditujukan untuk kode rute seperti `4D` dan `JAK 81`.
- Nomor bodi bus tidak dapat dijadikan favorit.
- Favorit tidak menarik halte di luar radius GPS.
- Favorit mendapat bonus ringan ketika slot tambahan terbatas.
- Arrival favorit ditempatkan lebih atas pada status/diagnostic dan diproses lebih dahulu bila jumlah notifikasi per siklus dibatasi.

Perintah CLI:

```bash
tj-nearby favorite-route "4D"
tj-nearby favorite-route "JAK 81"
tj-nearby list-favorites
tj-nearby unfavorite-route "4D"
```

### Output siap GUI

Setiap arrival sekarang membawa:

- `service_class`;
- `is_favorite_route`;
- arah dan headsign yang sudah ada;
- halte target, jarak, ETA, status, dan freshness.

Ini menjadi kontrak data awal untuk GUI monitor Windows/macOS pada versi berikutnya.

### Diagnostic

Diagnostic sekarang menampilkan:

- mode pemilihan halte;
- radius pencarian dan notifikasi per layanan;
- klasifikasi setiap kelompok halte;
- rute favorit pada kelompok halte;
- service class dan status favorit setiap arrival.

## Kompatibilitas

- Konfigurasi lama tetap dapat dibaca.
- `routes.preferred` tetap berfungsi sebagai allowlist ketat dan otomatis ikut dianggap favorit untuk migrasi.
- `notification.ready_max_stop_distance_m` tetap digunakan pada mode legacy `nearest`.
- Installer menambahkan key v0.3.4 yang belum ada tanpa menimpa nilai konfigurasi pengguna.
- Instalasi yang sudah ada tidak menghapus state, cache GTFS, atau konfigurasi pengguna.

## Pengujian

- 80 automated tests lulus pada lingkungan pengembangan Linux.
- Build wheel berhasil dilakukan di lingkungan pengembangan.
- Build `.app`, Core Location, notifikasi AppKit, dan LaunchAgent tetap harus divalidasi pada Mac nyata.
