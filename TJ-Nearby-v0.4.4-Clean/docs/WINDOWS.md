# TJ Nearby v0.4.4 — Windows Monitor Alpha


> v0.4.4 memantau seluruh halte berjadwal di dalam radius layanan, tanpa kuota delapan grup. Lihat `PATCH_NOTES_v0.4.4.md`.

TJ Nearby adalah pengingat desktop berbasis GPS untuk TransJakarta. Aplikasi membaca lokasi laptop, mencari halte yang realistis dijangkau, menampilkan bus yang menuju halte tersebut, dan tetap memberi notifikasi tanpa pengguna harus membuka aplikasi TJ di ponsel.

## Yang baru

- GUI Windows bergaya papan informasi halte.
- Kolom utama: **Rute, Arah, Halte, No. Bus, Estimasi**.
- Kode rute memakai `route_color` dan `route_text_color` dari GTFS bila tersedia.
- Warna fallback tetap membedakan rute apabila GTFS tidak menyediakan warna.
- Favorit berupa **rute** seperti `4D` dan `JAK 81`, bukan nomor bodi bus.
- Windows Location Service melalui WinRT.
- System tray: buka monitor, refresh, pause, senyapkan 1 jam, keluar.
- Menutup jendela tidak mematikan pemantauan.
- Smart Nearby tidak lagi membuang halte setelah delapan grup terpilih.
- Semua stop ID berjadwal di dalam radius layanan diperiksa, tanpa hardcode rute atau halte tertentu.
- Satu kendaraan yang cocok ke beberapa halte berurutan ditampilkan sekali pada halte terdekat yang masih akan didatanginya.
- Activity log mencatat audit cakupan rute terjadwal, rute realtime, rute terpetakan, dan rute yang belum menghasilkan arrival.
- Semua kedatangan unik dari seluruh halte terpantau ditampilkan, bukan hanya satu jenis kendaraan.
- Notifikasi dikirim setelah snapshot yang sama sudah muncul di monitor.
- Penanda live/stale menjelaskan apakah data benar-benar terus diperbarui.
- Klik jumlah halte untuk melihat semua halte, kelas layanan, dan rutenya.
- Snapshot terakhir dipertahankan saat API/GPS gagal sementara.
- Instance ganda dicegah dan shortcut normal tidak membuka CMD tambahan.
- Watchdog 55 detik memulihkan engine bila status `Memperbarui…` terlalu lama.
- Activity log dan diagnostic dapat diekspor langsung dari GUI atau tray.
- Uji notifikasi manual membedakan masalah toast Windows dari aturan ready-window/cooldown.
- Config lama `routes.preferred` tidak lagi menyembunyikan semua rute lain secara default.

## Instalasi paling mudah

1. Ekstrak ZIP.
2. Klik dua kali **Install Windows.bat**.
3. Izinkan Location services ketika Windows meminta izin.
4. Shortcut **TJ Nearby** akan dibuat di Desktop dan Start Menu.

Installer membuat virtual environment di:

```text
%LOCALAPPDATA%\TJNearby\venv
```

Config, state, dan cache tetap berada di:

```text
%USERPROFILE%\.tj-nearby
```

Konfigurasi dan favorit versi lama dipertahankan. Upgrade dari v0.4.0 cukup dengan keluar dari tray lalu menjalankan installer ini; tidak perlu uninstall.

## Preview tanpa data realtime

Setelah instalasi, jalankan:

```text
Preview Windows GUI.bat
```

Preview menampilkan contoh rute `4D`, `6H`, dan `JAK 81` agar desain GUI dapat dicek meskipun tidak ada bus yang sedang lewat.

## Build EXE lokal

Python/PyInstaller tidak dapat menghasilkan executable Windows dari Linux atau macOS. Jalankan pada Windows:

```text
Build Windows EXE.bat
```

Hasilnya:

```text
dist-windows\TJ Nearby\TJ Nearby.exe
```

Kemudian jalankan **Install Built EXE.bat**.

## Pengaturan utama

Klik tombol gear pada monitor:

- Smart: BRT, non-BRT, dan JakLingko terdekat.
- BRT saja.
- Notifikasi minimal, balanced, atau complete.
- Autostart saat login Windows.

Klik bintang pada baris untuk menambah atau menghapus rute favorit.

## GPS Windows

TJ Nearby memakai Windows Location Service. Pastikan:

```text
Settings > Privacy & security > Location
```

- Location services aktif.
- Let apps access your location aktif bila tersedia.
- Let desktop apps access your location aktif.

Lokasi dapat berasal dari GNSS, Wi-Fi, jaringan, IP, atau default location Windows. Akurasinya bergantung perangkat dan lingkungan.


## Activity log dan diagnostic

Klik **Ekspor activity log** pada panel kiri atau ikon tray. File berikut dibuat di Desktop:

```text
tj-nearby-activity-diagnostic-YYYYMMDD-HHMMSS.txt
```

Isinya mencakup:

- status GPS dan akurasi;
- daftar halte terpantau dan rutenya;
- jumlah/rute posisi bus mentah dari API;
- jumlah arrival yang berhasil dicocokkan;
- alasan notifikasi lolos, tertahan ready-window, direction confidence, stale data, radius, cooldown, atau stage interval;
- hasil backend toast Windows;
- riwayat timeout dan pemulihan engine.

Activity log mentah berada di:

```text
%USERPROFILE%\.tj-nearby\logs\tj-nearby-activity.log
```

Klik **Uji notifikasi** untuk memastikan Windows dapat menerima toast tanpa menunggu bus.

Bila GUI benar-benar tidak dapat dibuka, jalankan `Export Raw Activity Log.bat` dari folder paket untuk menyalin log mentah ke Desktop.

## Cara membaca jumlah data

Panel kiri menampilkan dua angka berbeda:

- **posisi bus diterima**: seluruh bus yang dikembalikan API dalam radius realtime;
- **kendaraan menuju halte**: bus yang berhasil dicocokkan dengan seluruh halte sekitar yang sedang dipantau dan ditampilkan di tabel.

Jadi ratusan posisi bus dapat menghasilkan hanya beberapa baris apabila hanya beberapa bus yang benar-benar sedang menuju halte sekitar laptop.

## Batas alpha

- Source, installer Python, GUI demo, dan script build EXE telah diuji di lingkungan pengembangan.
- Akses Windows Location, notifikasi tray, autostart registry, scaling, dan EXE PyInstaller perlu divalidasi langsung pada Windows 10/11.
- API realtime TJ masih merupakan interface reverse-engineered dan dapat berubah.
- GUI macOS belum masuk v0.4.4; engine macOS v0.3.4 tetap tersedia.
