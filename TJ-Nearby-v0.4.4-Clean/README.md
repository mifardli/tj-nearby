# TJ Nearby

**TJ Nearby** adalah monitor desktop ringan berbasis lokasi untuk melihat kendaraan TransJakarta yang sedang menuju halte-halte di sekitar pengguna.

> **Status:** Windows Alpha · versi **0.4.4**  
> Membutuhkan Python 3.11+ pada paket distribusi saat ini.

## Fitur utama

- Menggunakan lokasi laptop untuk menentukan halte yang realistis dijangkau.
- Memantau seluruh halte berjadwal dalam radius layanan, tanpa batas delapan grup.
- Mempertahankan `stop_id`, platform, arah, dan urutan halte secara terpisah.
- Menampilkan seluruh kendaraan realtime yang masih akan mendatangi halte terpantau.
- Mencegah satu kendaraan tampil berulang pada beberapa halte berurutan.
- Menyediakan refresh otomatis, system tray, favorit rute, activity log, diagnostic, dan recovery watchdog.

```text
GPS pengguna
→ seluruh halte berjadwal dalam radius
→ cocokkan rute, trip, arah, dan stop sequence
→ pilih halte terdekat yang belum dilewati setiap kendaraan
→ tampilkan arrival dan kirim pengingat
```

## Instalasi Windows

1. Unduh paket pengguna dari **GitHub Releases**.
2. Ekstrak ZIP ke folder biasa.
3. Pastikan Python 3.11+ 64-bit sudah terpasang dan tersedia di PATH.
4. Jalankan `Install Windows.bat`.
5. Izinkan Windows Location Services untuk aplikasi desktop.

Dokumentasi lengkap tersedia di [`docs/Panduan-Pengguna-TJ-Nearby-v0.4.4-Windows.docx`](docs/Panduan-Pengguna-TJ-Nearby-v0.4.4-Windows.docx).

## Menjalankan dari source

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[test]"
pytest
```

GUI Windows:

```bash
pip install -e ".[windows]"
python -m tj_nearby.windows_gui
```

## Sumber data

TJ Nearby menggabungkan:

- GTFS statis TransJakarta untuk halte, rute, trip, arah, dan stop sequence;
- interface realtime TransJakarta untuk posisi kendaraan;
- Windows Location Service untuk lokasi perangkat;
- pengolahan ETA dan deduplikasi secara lokal di perangkat.

Rincian teknis tersedia di [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

## Privasi

- Riwayat lokasi tidak disimpan secara default.
- Koordinat pada log dibulatkan sesuai konfigurasi.
- Token guest dan device ID dibuat saat runtime dan tidak disertakan di repository.
- Jangan unggah `config.yaml`, activity log, diagnostic, cache GTFS, token, atau data lokasi pribadi ke issue publik.

## Batasan versi 0.4.4

- Notifikasi Windows masih memakai backend legacy; banner dapat bertuliskan **Python** dan belum tentu tersimpan di Notification Center.
- Distribusi utama belum berupa standalone EXE.
- ETA adalah perkiraan dan dapat berubah karena kondisi lalu lintas atau operasional.
- Interface realtime bersifat reverse-engineered dan dapat berubah tanpa pemberitahuan.
- Proyek ini tidak berafiliasi atau didukung secara resmi oleh PT Transportasi Jakarta.

## Pengujian

Checkpoint v0.4.4 memiliki **100 automated tests**. Hasil pengujian terakhir tersedia di [`docs/TEST_REPORT_v0.4.4.txt`](docs/TEST_REPORT_v0.4.4.txt).

## Kontribusi dan pelaporan masalah

Baca [`CONTRIBUTING.md`](CONTRIBUTING.md) sebelum mengirim pull request. Untuk bug, ekspor diagnostic dari aplikasi, hapus koordinat atau informasi pribadi yang tidak perlu, lalu gunakan issue template.

## Lisensi

Dirilis dengan [MIT License](LICENSE). Hak cipta tetap dimiliki oleh Miftahul Ardli; pengguna diperbolehkan memakai, memodifikasi, dan mendistribusikan kode dengan tetap menyertakan pemberitahuan lisensi.
