# TJ Nearby v0.4.1 — Windows Live Monitor Sync Hotfix

Tanggal: 31 Juli 2026

## Masalah yang diperbaiki

Pada v0.4.0, toast Windows dapat muncul dari snapshot baru sebelum thread GUI sempat mengganti tabel. Akibatnya, notifikasi bisa menyebut bus/arah terbaru sementara monitor masih menampilkan baris lama. Pemanggilan notifikasi tray juga berpotensi menahan penyelesaian satu siklus polling.

Selain itu, tabel v0.4.0 kurang tegas membedakan halte terdekat sebagai header dan seluruh halte yang sebenarnya dipantau. Deduplikasi khusus UI juga belum memasukkan arah, tujuan, trip, dan journey epoch sehingga beberapa proyeksi kedatangan yang berbeda bisa terlipat menjadi satu baris.

## Perbaikan v0.4.1

- Snapshot bus selalu diterapkan ke GUI terlebih dahulu, baru notifikasi dikirim dari thread terpisah.
- Kegagalan atau kelambatan toast tidak lagi menghentikan polling dan pembaruan monitor.
- Seluruh kedatangan realtime unik dari semua halte terpantau ditampilkan, sampai 60 baris secara default.
- Kunci deduplikasi GUI kini memasukkan bus, rute, halte, arah, tujuan, trip, dan journey epoch.
- Kolom **HALTE** ditambahkan sebagai kolom tersendiri.
- Header kini menjelaskan **Halte terdekat** serta jumlah seluruh halte sekitar yang dipantau.
- Klik jumlah halte di panel kiri untuk melihat daftar halte, jenis layanan, dan rute yang dilayani.
- Penanda sinkronisasi baru: **Memperbarui**, **Live**, **Data lama**, atau **Pembaruan gagal**.
- Saat GPS/API gagal sementara, snapshot sukses terakhir tetap terlihat dengan tanda data lama; layar tidak langsung menjadi kosong.
- Panel kiri membedakan jumlah posisi bus yang diterima API dengan jumlah kendaraan yang benar-benar menuju halte terpantau.
- Instance ganda dicegah agar dua proses tidak saling berebut state, polling, dan tray.
- Shortcut Windows kini langsung memanggil `pythonw.exe`, sehingga pembukaan normal tidak memunculkan jendela CMD tambahan.
- Installer melakukan upgrade paket lokal secara paksa sambil tetap mempertahankan config pengguna.

## Yang tidak diubah

- Smart Stop Selection BRT/non-BRT/JakLingko.
- Radius GPS per layanan.
- Favorit rute.
- Pemisahan arah dan turnaround journey epoch.
- Kebijakan notifikasi minimal/balanced/complete dan anti-spam.

## Instalasi upgrade

1. Keluar dari TJ Nearby v0.4.0 melalui ikon tray.
2. Ekstrak ZIP v0.4.1.
3. Jalankan `Install Windows.bat`.
4. Config, favorit, cache GTFS, dan state notifikasi lama dipertahankan.

Tidak perlu uninstall atau menghapus folder `.tj-nearby`.
