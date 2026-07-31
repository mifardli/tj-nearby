# Sumber Data, API, dan Layanan Pendukung

## GTFS statis TransJakarta

Sumber utama:

```text
https://gtfs.transjakarta.co.id/files/file_gtfs.zip
```

Data ini digunakan untuk membaca halte, rute, trip, arah, urutan halte, jadwal, dan warna rute. File utama yang dipakai adalah `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, dan `shapes.txt` bila tersedia. Aplikasi menyimpan cache lokal dan memperbaruinya secara berkala. Konfigurasi juga menyediakan URL cadangan Mobility Database.

## Interface realtime TransJakarta

Base URL default:

```text
https://tijeapi.transjakarta.co.id
```

Endpoint yang digunakan source v0.4.4:

```text
POST /v1/auth/login/guest
GET  /v1/bus?latitude=...&longitude=...&radius=...
```

Guest login membuat token sementara menggunakan device ID acak yang disimpan lokal. Token runtime, device ID pengguna, dan response mentah tidak disertakan dalam repository.

Interface ini diperoleh melalui identifikasi komunikasi aplikasi dan bukan API publik yang dijamin stabil untuk pengembang eksternal. Endpoint, header, autentikasi, dan bentuk respons dapat berubah.

## Windows Location Service

Lokasi perangkat diperoleh melalui Windows Runtime Geolocation. Akurasi dapat berasal dari GPS, Wi-Fi, IP, atau sumber lokasi lain yang tersedia di Windows.

## Pengolahan lokal

TJ Nearby menggabungkan lokasi pengguna, GTFS, posisi kendaraan, trip, arah, dan stop sequence. ETA dihitung secara lokal dan bukan jaminan operasional. Satu kendaraan yang cocok ke beberapa halte berurutan dideduplikasi ke halte terdekat yang belum dilewati.

## Layanan yang tidak digunakan

Versi 0.4.4 tidak memerlukan Google Maps API, Google Directions API, Mapbox, atau server pengembang untuk menyimpan riwayat lokasi pengguna.
