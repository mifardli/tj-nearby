# TJ Nearby v0.4.4 — All Nearby Stops Coverage Hotfix

## Perubahan perilaku utama

- Smart Nearby tidak lagi membatasi pemantauan ke delapan grup halte.
- Semua stop GTFS yang memiliki rute dan berada di dalam radius layanan dipantau.
- Stop ID, arah, platform, serta nama publik tetap dipertahankan; Flyover Jatinegara Atas dan Bawah tidak digabung.
- Semua kendaraan realtime yang masih akan mendatangi salah satu halte terpantau dapat masuk ke engine dan GUI.
- Satu kendaraan yang cocok dengan beberapa halte berurutan ditampilkan sekali pada halte terdekat yang belum dilewatinya.
- Batas 60 baris GUI dihapus; kunci lama `desktop.max_arrival_rows` diabaikan agar config lama tidak menyembunyikan kendaraan.
- Activity log menambahkan audit cakupan rute terjadwal, rute realtime pada halte terpantau, rute yang berhasil dipetakan, dan rute realtime yang belum menghasilkan arrival.

## Prinsip algoritma

`GPS -> seluruh halte dalam radius layanan -> stop sequence/trip/direction -> seluruh kendaraan valid`

Tidak ada hardcode B25, 11M, atau Flyover Jatinegara. Perbaikan berlaku untuk seluruh jaringan yang tersedia pada GTFS.

## Upgrade

Keluar dari versi sebelumnya, ekstrak ZIP v0.4.4, lalu jalankan `Install Windows.bat`. Config dan favorit lama dipertahankan. Kunci lama `nearby.smart_max_groups` tetap dibaca untuk kompatibilitas tetapi tidak lagi membatasi Smart Nearby.
