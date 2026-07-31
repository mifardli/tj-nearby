# Patch Notes v0.2.8

## Context-aware timing labels

Notifikasi mode `all_arrivals` tetap dikirim untuk setiap bus baru yang arah perjalanannya terkonfirmasi. Versi ini menambahkan klasifikasi urgensi berdasarkan:

```text
margin = ETA bus - perkiraan waktu berjalan
```

- margin ≤ 1 menit: `kemungkinan tidak terkejar`
- margin ≤ 5 menit: `berangkat sekarang`
- margin > 5 menit: `masih cukup jauh`

## Format banner

```text
RUTE → TUJUAN · ETA
Bus BODY-NUMBER · STATUS WAKTU
JUMLAH HALTE menuju HALTE TARGET · JARAK (WAKTU JALAN)
```

## Konfigurasi baru

```yaml
notification:
  timing_too_late_margin_minutes: 1
  timing_leave_now_margin_minutes: 5
```

## Diagnostics

Diagnostic sekarang menyertakan `timing_status`, `timing_label`, dan `margin` untuk setiap arrival.
