# TJ Nearby v0.4.0 — Windows Monitor Alpha

## Scope

Versi ini mengubah TJ Nearby dari utility menu bar menjadi monitor desktop Windows yang tetap GPS-first dan berjalan di background.

## Fitur baru

1. **Monitor gaya halte**
   - Header halte terdekat.
   - Tabel Rute, Arah, No. Bus, dan Estimasi.
   - Status kesiapan tampil di bawah ETA.
   - Empty state saat tidak ada bus.
   - Jam dan waktu pembaruan terakhir.

2. **Warna rute GTFS**
   - Membaca `route_color` dan `route_text_color` dari `routes.txt`.
   - Memilih warna teks otomatis bila GTFS tidak menyediakannya.
   - Fallback warna deterministik bila feed tidak memiliki warna.

3. **Favorit rute dari GUI**
   - Klik bintang pada baris.
   - Favorit tetap berbasis kode rute, bukan nomor bodi.
   - Favorit tidak melewati batas radius GPS.

4. **Windows Location Service**
   - Memakai `Windows.Devices.Geolocation.Geolocator` melalui PyWinRT.
   - Permintaan izin dijalankan dari foreground UI thread sebelum polling background.
   - Manual location dan fallback lama tetap tersedia.

5. **System tray Windows**
   - Buka Monitor.
   - Refresh.
   - Pause/Lanjutkan.
   - Senyapkan satu jam.
   - Keluar.
   - Close-to-tray.

6. **Pengaturan sederhana**
   - Smart atau BRT saja.
   - Minimal/balanced/complete.
   - Autostart Windows per-user.

7. **Packaging Windows**
   - Installer berbasis virtual environment.
   - Shortcut Desktop dan Start Menu.
   - PyInstaller spec dan one-click build batch.
   - ICO/PNG aplikasi.
   - GUI demo offline.

## Fondasi yang dipertahankan

- Smart Stop Selection v0.3.4.
- BRT terdekat tidak tersingkir banyak JakLingko.
- Radius per kelas layanan.
- Tracking seluruh bus relevan.
- Pemisahan arah dan journey epoch turnaround.
- Lead-bus notifications, dedupe, freshness, dan cooldown.

## Catatan validasi

Build dan unit test dilakukan di lingkungan Linux. UI Tk diuji melalui X virtual display. Executable Windows harus dibangun pada Windows karena PyInstaller bukan cross-compiler. Windows Location, tray notification, autostart registry, dan DPI scaling masih perlu smoke test pada perangkat Windows nyata.
