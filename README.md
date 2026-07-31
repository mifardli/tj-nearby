<p align="center">
  <img src="TJ-Nearby-v0.4.4-Clean/assets/tj_nearby.icog" alt="TJ Nearby logo" width="104">
</p>

<h1 align="center">TJ Nearby</h1>

<p align="center">
  Monitor desktop ringan berbasis lokasi untuk melihat kendaraan TransJakarta yang sedang menuju halte-halte di sekitar pengguna.
</p>

<p align="center">
  <img alt="Platform Windows" src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4">
  <img alt="Status Alpha" src="https://img.shields.io/badge/status-alpha-F59E0B">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB">
  <img alt="MIT License" src="https://img.shields.io/badge/license-MIT-5C4CCF">
</p>

> **Platform saat ini: Windows 10/11.** Rilis pengguna macOS sedang disiapkan dan akan menyusul setelah fondasi Windows lebih stabil. Beberapa komponen eksperimen macOS tersedia di repository, tetapi belum dianggap sebagai rilis publik yang didukung.

TJ Nearby dirancang sebagai pengingat pasif saat pengguna sedang bekerja, belajar, atau menggunakan layar kedua. Pengguna tidak perlu terus membuka aplikasi transportasi di ponsel hanya untuk mengecek apakah bus yang relevan sudah mendekat.

## Preview

<p align="center">
  <img src="docs/screenshots/tj-nearby-v0.4.4-windows-preview.png" alt="Preview TJ Nearby v0.4.4 pada Windows" width="100%">
</p>

<p align="center"><em>Preview TJ Nearby v0.4.4 pada Windows menggunakan data demo.</em></p>

## Fitur utama

- **GPS-first.** Lokasi laptop digunakan untuk menentukan halte yang realistis dijangkau.
- **All nearby stops.** Seluruh halte berjadwal dalam radius layanan dipantau; tidak lagi dibatasi delapan grup.
- **Arah dan urutan halte.** Kendaraan hanya ditampilkan bila trip realtime masih akan mendatangi halte tersebut.
- **Satu kendaraan, satu baris.** Bila satu bus cocok ke beberapa halte berurutan, aplikasi memilih halte terdekat yang belum dilewati.
- **BRT, non-BRT, dan JakLingko.** Radius pencarian disesuaikan dengan jenis layanan.
- **Desktop monitor.** Tersedia refresh otomatis, system tray, pause, favorit rute, dan autostart.
- **Activity log dan diagnostic.** Membantu membedakan masalah GPS, API, mapping, GUI, dan notifikasi.
- **Recovery watchdog.** Siklus yang macet dipulihkan tanpa langsung menghapus snapshot terakhir.

```text
GPS pengguna
→ seluruh halte berjadwal dalam radius
→ cocokkan rute, trip, arah, dan stop sequence
→ pilih halte terdekat yang belum dilewati setiap kendaraan
→ tampilkan arrival dan kirim pengingat
```

## Status platform

| Platform | Status |
|---|---|
| Windows 10/11 | **Tersedia — Alpha** |
| macOS | **Menyusul** |
| Linux | Belum menjadi target rilis pengguna |

Distribusi Windows saat ini masih membutuhkan Python 3.11+. Target berikutnya adalah notifikasi native Windows, identitas aplikasi yang benar, serta paket executable/installer mandiri. Setelah alur Windows stabil, rilis pengguna macOS akan dirapikan dan dipublikasikan.

## Instalasi Windows

1. Buka halaman **GitHub Releases** dan unduh `TJ-Nearby-v0.4.4-Windows-User-Package.zip`.
2. Ekstrak seluruh ZIP ke folder biasa. Jangan menjalankan installer langsung dari tampilan isi ZIP.
3. Pastikan Python 3.11+ 64-bit sudah terpasang dan tersedia di `PATH`.
4. Jalankan `Install Windows.bat`.
5. Aktifkan Windows Location Services untuk aplikasi desktop.
6. Buka TJ Nearby melalui shortcut Desktop atau Start Menu.

Panduan lengkap tersedia di [`docs/Panduan-Pengguna-TJ-Nearby-v0.4.4-Windows.docx`](docs/Panduan-Pengguna-TJ-Nearby-v0.4.4-Windows.docx).

## Menjalankan dari source

```bash
python -m venv .venv
```

Aktifkan virtual environment:

```bash
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

Pasang dependensi dan jalankan test:

```bash
pip install -e ".[test]"
pytest
```

Jalankan GUI Windows:

```bash
pip install -e ".[windows]"
python -m tj_nearby.windows_gui
```

Mode preview dengan data demo:

```bash
python -m tj_nearby.windows_gui --demo
```

## Cara kerja dan sumber data

TJ Nearby menggabungkan:

- **GTFS statis TransJakarta** untuk halte, rute, trip, arah, warna rute, dan urutan halte;
- **interface realtime TransJakarta** untuk posisi dan identitas kendaraan;
- **Windows Location Service** untuk lokasi perangkat;
- **mesin lokal TJ Nearby** untuk pencocokan trip, arah, deduplikasi, dan estimasi kedatangan.

Rincian teknis tersedia di [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) dan [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Privasi

- Riwayat lokasi tidak disimpan secara default.
- Koordinat pada log dibulatkan sesuai konfigurasi privasi.
- Token guest dan device ID dibuat saat runtime dan tidak disertakan dalam repository.
- Repository tidak menyertakan config pengguna, cache GTFS lokal, activity log, diagnostic, token, atau koordinat pribadi.
- Jangan mengunggah diagnostic mentah ke issue publik sebelum memeriksa dan menghapus informasi yang tidak perlu.

## Batasan versi 0.4.4

- Notifikasi Windows masih memakai backend legacy; banner dapat bertuliskan **Python** dan belum tentu tersimpan di Notification Center.
- Paket distribusi utama belum berupa standalone EXE.
- ETA merupakan perkiraan, bukan jaminan operasional.
- Interface realtime bersifat reverse-engineered dan dapat berubah tanpa pemberitahuan.
- Ketersediaan bus bergantung pada data realtime yang diterima dan kecocokan trip terhadap halte sekitar.
- Proyek ini tidak berafiliasi atau didukung secara resmi oleh PT Transportasi Jakarta.

## Roadmap

- [ ] Native Windows App Notification dan identitas `TJ Nearby`
- [ ] Standalone Windows executable/installer
- [ ] Penyempurnaan pengalaman instalasi untuk pengguna umum
- [ ] Rilis pengguna macOS
- [ ] Validasi lapangan lebih luas pada berbagai lokasi dan tipe halte

## Pengujian

Checkpoint v0.4.4 memiliki **100 automated tests**. Ringkasan pengujian tersedia di [`docs/TEST_REPORT_v0.4.4.txt`](docs/TEST_REPORT_v0.4.4.txt).

## Kontribusi dan pelaporan masalah

Baca [`CONTRIBUTING.md`](CONTRIBUTING.md) sebelum mengirim pull request. Untuk pelaporan bug, gunakan issue template dan lampirkan diagnostic yang sudah diperiksa agar tidak mengandung informasi pribadi.

Masalah keamanan sebaiknya dilaporkan mengikuti [`SECURITY.md`](SECURITY.md), bukan melalui issue publik.

## Lisensi

TJ Nearby dirilis dengan [MIT License](LICENSE).

Hak cipta tetap dimiliki oleh **Miftahul Ardli**. Pengguna diperbolehkan memakai, memodifikasi, dan mendistribusikan kode dengan tetap menyertakan pemberitahuan hak cipta dan lisensi. Perangkat lunak diberikan *sebagaimana adanya* tanpa jaminan.
