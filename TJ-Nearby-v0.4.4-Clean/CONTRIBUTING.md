# Contributing

Terima kasih sudah membantu TJ Nearby.

## Sebelum membuat issue

1. Pastikan aplikasi tidak sedang Pause atau mute.
2. Jalankan **Uji notifikasi** bila masalah terkait toast.
3. Ekspor activity diagnostic dari panel atau system tray.
4. Hapus atau samarkan koordinat, path pengguna, dan informasi pribadi yang tidak diperlukan.
5. Jelaskan versi Windows, versi TJ Nearby, langkah reproduksi, hasil yang diharapkan, dan hasil aktual.

## Pengembangan lokal

```bash
python -m venv .venv
pip install -e ".[test]"
pytest
```

Untuk GUI Windows:

```bash
pip install -e ".[windows,test]"
python -m tj_nearby.windows_gui --demo
```

## Pull request

- Buat perubahan kecil dan terfokus.
- Tambahkan atau perbarui test untuk perubahan perilaku.
- Jangan menambahkan token, cookie, device ID, config lokal, log pengguna, cache GTFS, atau koordinat pribadi.
- Jalankan seluruh test sebelum mengirim PR.
- Perbarui `CHANGELOG.md` bila perubahan berdampak pada pengguna.

## Prinsip produk

- GPS menentukan halte yang dipantau.
- Stop sequence dan arah menentukan apakah kendaraan masih akan mendatangi halte.
- Halte berbeda tidak digabung hanya karena namanya mirip.
- Semua kendaraan valid boleh masuk monitor; pembatasan UI tidak boleh membuang data yang valid.
