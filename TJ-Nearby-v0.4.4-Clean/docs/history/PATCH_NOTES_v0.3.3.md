# TJ Nearby v0.3.3 — Menu Bar Stability Hotfix

## Masalah yang diperbaiki

Pada v0.3.2, worker thread lokasi/API dapat mengubah judul `NSMenuItem` secara langsung. Jika hasil atau error lokasi datang ketika menu bar sedang dibuka, AppKit dapat mengalami race/deadlock dan menampilkan beach ball.

## Perubahan

- Semua perubahan UI rumps/AppKit sekarang hanya diterapkan pada main event loop.
- Worker thread hanya menaruh teks status ke antrean Python yang thread-safe.
- Polling, check manual, dan diagnostic memakai lock `busy` yang sama.
- Reload engine tidak dilakukan ketika pemeriksaan masih aktif.
- Thread pemeriksaan diberi nama agar lebih mudah diperiksa pada crash sample.
- Logika tracking, arah bolak-balik, dan notifikasi v0.3.2 tidak diubah.

## Catatan validasi

Automated tests dan kompilasi dapat memeriksa regresi kode, tetapi perbaikan beach ball tetap harus diuji langsung pada macOS dengan membuka menu berulang kali saat lokasi berhasil, timeout, dan error.
