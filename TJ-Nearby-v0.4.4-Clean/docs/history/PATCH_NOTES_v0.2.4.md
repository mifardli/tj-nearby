# TJ Nearby v0.2.4

## Perbaikan utama

- Polling otomatis tidak lagi berhenti ketika Core Location bisa memberi koordinat tetapi API status otorisasi masih melaporkan `not-determined`.
- Saat aplikasi aktif, pemeriksaan berjalan otomatis sesuai `realtime.poll_seconds` (default 30 detik).
- `Check now` hanya untuk pemeriksaan manual segera.
- Menu baru **Test notification** untuk menguji izin notifikasi macOS secara terpisah.
- Diagnostic menampilkan interval polling, status pause, batas notifikasi, margin ETA-waktu jalan, serta alasan eligibility tiap arrival.
- Feedback `Check now` memakai notifier internal yang sama dengan alert bus.
