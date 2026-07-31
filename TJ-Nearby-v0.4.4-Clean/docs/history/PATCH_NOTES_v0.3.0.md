# TJ Nearby v0.3.0 — Ready Window

## Yang baru

TJ Nearby sekarang memisahkan **tracking** dan **notifikasi**:

- semua bus real-time yang terkonfirmasi menuju halte sekitar tetap dipantau;
- bus yang masih lebih dari dua halte hanya masuk tracking;
- saat bus tinggal **dua halte**, aplikasi memberi notifikasi jika waktu berjalan masih masuk akal;
- jika bus pertama kali terdeteksi tinggal **satu halte**, aplikasi tetap memberi kesempatan terakhir meskipun sangat mepet;
- satu bus/trip/arah/halte tetap hanya mengirim satu banner.

## Hitungan halte dari API

Urutan `next_stops` API sekarang menjadi sumber utama jumlah halte tersisa. Target pada urutan pertama dibaca sebagai `1 halte lagi`; target pada urutan kedua dibaca sebagai `2 halte lagi`. GTFS dan posisi bus pada jalur dipakai sebagai fallback serta validasi.

Daftar `next_stops` yang pendek tidak lagi otomatis membuang bus yang masih jauh. Selama trip, arah, dan posisi pada jalur menunjukkan target masih berada di depan, bus tetap masuk tracking.

## Wording notifikasi

Normal:

```text
4D → Pulo Gadung · 6 menit
Bus DMR-240193 · bersiap berangkat
2 halte lagi · Menuju Halte Kuningan Madya · jalan ±2 menit.
```

Kesempatan terakhir:

```text
4D → Pulo Gadung · 1 menit
Bus DMR-240193 · sangat mepet — berangkat sekarang
1 halte lagi · Menuju Halte Kuningan Madya · jalan ±2 menit.
```

## Pengamanan

Banner ditahan jika arah ambigu, halte terlalu jauh untuk berjalan, atau usia data posisi melebihi batas. Jika jumlah halte tidak tersedia, aplikasi dapat memakai jendela ETA sebagai fallback.

## Catatan kompatibilitas

Mode lama `all_arrivals` dan `leave_now` tetap tersedia. Instalasi otomatis v0.3.0 mengaktifkan `ready_window` sebagai mode bawaan.
