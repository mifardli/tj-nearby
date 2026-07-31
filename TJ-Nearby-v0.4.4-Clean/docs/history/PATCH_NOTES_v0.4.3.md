# TJ Nearby v0.4.3 — Live Board Render Recovery Hotfix

## Akar masalah yang ditemukan dari activity diagnostic

Siklus realtime sebenarnya selesai dan menemukan banyak kendaraan, tetapi callback GUI berhenti saat merender baris pertama. Tampilan memanggil method engine yang tidak tersedia (`arrival_status`) sehingga Tkinter melempar exception setelah satu baris terbuat sebagian. Karena queue pump sebelumnya tidak menangkap exception tersebut, hasil siklus berikutnya tertahan di queue, tombol Refresh terlihat tidak bekerja, watchdog salah menganggap proses realtime timeout, dan notifikasi lanjutan tidak dijalankan.

## Perbaikan

- Status baris sekarang memakai kontrak engine yang benar: `notification_label()`.
- Semua kendaraan unik dari snapshot dapat dirender, bukan hanya baris pertama yang terbentuk sebagian.
- Queue pump GUI selalu dijadwalkan ulang melalui `finally`.
- Exception pada satu callback dicatat ke activity log dan tidak lagi mematikan seluruh pembaruan UI.
- Watchdog dibatalkan saat hasil diterima; Refresh dan polling otomatis tetap dapat pulih.
- Notifikasi diproses setelah snapshot yang sama berhasil diterapkan ke GUI.
- Ditambah regression test untuk kontrak status engine yang benar.

## Upgrade

Keluar dari versi sebelumnya, ekstrak ZIP v0.4.3, lalu jalankan `Install Windows.bat`. Config dan favorit lama dipertahankan.
