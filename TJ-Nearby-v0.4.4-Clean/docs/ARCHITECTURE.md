# Arsitektur Ringkas

```text
Windows Location Service
        │
        ▼
Pemilihan seluruh halte dalam radius
        │
GTFS ───┼──► stop ID, rute, trip, arah, stop sequence
        │
Realtime API ─► posisi dan identitas kendaraan
        │
        ▼
Engine pencocokan + ETA + deduplikasi
        │
        ├──► Windows GUI
        ├──► Notifikasi
        └──► Activity log / diagnostic
```

## Aturan inti

1. Halte dipilih berdasarkan radius per kelas layanan.
2. Stop ID, platform, arah, atas/bawah, dan halte bernama mirip tetap dipertahankan sebagai entitas terpisah.
3. Kendaraan hanya masuk bila perjalanan realtime masih akan mendatangi halte tersebut.
4. Satu kendaraan ditampilkan satu kali pada halte terdekat yang belum dilewati.
5. Snapshot GUI dan keputusan notifikasi menggunakan hasil siklus yang sama.
