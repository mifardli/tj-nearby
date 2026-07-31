# TJ Nearby v0.4.2 — Activity Log & Windows Recovery Hotfix

## Fokus

v0.4.2 dibuat untuk menangani tiga laporan pemakaian nyata di Windows:

1. monitor berhenti pada status **Memperbarui…**;
2. tabel terlihat hanya menampilkan satu rute/kendaraan;
3. tidak jelas mengapa notifikasi dikirim atau ditahan.

## Perbaikan

- Activity log berputar otomatis di `%USERPROFILE%\.tj-nearby\logs\tj-nearby-activity.log`.
- Tombol dan menu tray **Ekspor activity log** membuat satu diagnostic lengkap di Desktop.
- Diagnostic mencatat fase GPS, halte terpilih, jumlah posisi bus mentah, rute bus mentah, hasil pencocokan arrival, dan alasan notifikasi lolos/ditahan.
- Tombol dan menu tray **Uji notifikasi** untuk membedakan masalah backend toast Windows dari aturan notifikasi.
- Watchdog 55 detik mencegah GUI macet permanen pada `Memperbarui…` dan memuat ulang engine otomatis.
- Snapshot terakhir tetap ditampilkan saat siklus timeout atau API/GPS gagal sementara.
- Config lama `routes.preferred` tidak lagi diam-diam menjadi filter ketat. Nilainya diperlakukan sebagai favorit agar rute lain di halte sekitar tetap muncul.
- Filter rute ketat hanya aktif bila `routes.strict_filter_enabled: true` disetel secara eksplisit.
- Panel kiri menampilkan jumlah kendaraan yang lolos aturan notifikasi dan jumlah toast yang benar-benar dikirim pada siklus terakhir.
- Kegagalan backend toast tidak lagi menandai occurrence sebagai sudah dinotifikasi, sehingga aplikasi dapat mencoba lagi pada siklus berikutnya.

## Upgrade

1. Keluar dari TJ Nearby lewat ikon tray.
2. Ekstrak ZIP v0.4.2.
3. Jalankan `Install Windows.bat`.

Config, favorit, state, dan cache lama dipertahankan.

## Bila masalah masih muncul

Klik **Ekspor activity log**, lalu kirim file `tj-nearby-activity-diagnostic-*.txt` dari Desktop. File tersebut menunjukkan apakah penyebabnya adalah filter config lama, GPS, API realtime, pencocokan arah, cooldown, ready-window, atau backend toast Windows.
