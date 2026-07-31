# TJ Nearby v0.3.2 — Turnaround & Opposite Direction Fix

Version ini memperbaiki identitas perjalanan bus secara umum untuk seluruh rute, bukan hanya 4D.

## Perubahan utama

- Menyimpan **journey epoch** untuk setiap kombinasi nomor bodi bus dan rute.
- Mendeteksi perjalanan baru ketika API menunjukkan perubahan `trip_id`, `direction_id`, atau tujuan/headsign yang benar-benar berbeda.
- Perjalanan pergi dan pulang dari nomor bodi yang sama tidak lagi berbagi identitas notifikasi.
- Deduplikasi sebelum notifikasi kini mempertahankan arah yang berbeda.
- Bus terdepan dihitung terpisah untuk setiap kombinasi rute, arah, dan halte tujuan.
- Label tujuan yang hanya diperkaya, misalnya `Pulo Gadung` menjadi `Pulo Gadung via Pramuka`, tidak dianggap sebagai putar balik palsu.
- Payload yang sementara kehilangan trip, arah, atau headsign tidak menghapus identitas perjalanan terakhir.
- Jika satu nomor bodi muncul dalam dua arah yang bertentangan pada polling yang sama, kandidat yang lebih lemah tetap terlihat di diagnostic tetapi tidak menghasilkan banner.
- Diagnostic kini menampilkan `journey_epoch`, `journey_transition`, dan arah sebelumnya.

## Logika umum

```text
nomor bodi + rute
        ↓
trip / direction / tujuan tetap
→ perjalanan yang sama

trip berubah dengan arah tetap
→ perjalanan baru

direction atau tujuan berubah
→ putar balik terdeteksi
→ journey epoch bertambah
→ notifikasi arah baru tidak diblokir perjalanan sebelumnya
```

Perbaikan berlaku untuk semua rute bolak-balik, termasuk koridor, non-BRT, dan layanan pengumpan selama data real-time dan GTFS menyediakan bukti arah yang cukup.
