# TJ Nearby v0.3.1 — Notification Policy Freeze

## Yang berubah

- Memperjelas tiga tahap kedekatan bus:
  - dua halte perantara;
  - satu halte perantara;
  - halte target menjadi pemberhentian berikutnya.
- Menambahkan preset intensitas notifikasi:
  - `minimal`;
  - `balanced` sebagai bawaan;
  - `complete`.
- Menambahkan deduplikasi per tahap agar bus yang sama dapat memberi eskalasi tanpa mengulang banner yang sama setiap polling.
- Menambahkan kebijakan `lead bus only` agar hanya bus paling depan untuk rute, arah, dan halte target yang membuat banner.
- Menambahkan jeda minimum antartahap 90 detik.
- Notifikasi final tetap dapat dikirim walaupun jeda antartahap belum selesai.
- Tahap yang terlewat tidak dikirim sekaligus ketika aplikasi baru menemukan bus di tahap yang lebih dekat.
- Semua bus relevan tetap dilacak; perubahan hanya memengaruhi kebijakan banner.
- Diagnostic sekarang mencatat preset, tahap aktif, tahap setiap arrival, dan alasan kelayakan notifikasi.

## Bawaan v0.3.1

```yaml
notification:
  mode: "ready_window"
  ready_notification_intensity: "balanced"
  ready_notify_lead_bus_only: true
  ready_min_seconds_between_stages: 90
  ready_always_send_final_stage: true
```

Preset `balanced` mengirim peringatan ketika dua halte perantara tersisa dan satu notifikasi final ketika halte target menjadi pemberhentian berikutnya.

## Catatan kompatibilitas

Konfigurasi lama tetap dapat dipakai. Kunci baru memiliki nilai bawaan dari kode, sehingga instalasi pembaruan tidak wajib menghapus `~/.tj-nearby/config.yaml`.
