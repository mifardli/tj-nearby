# Security Policy

## Data yang tidak boleh dipublikasikan

Jangan mengirimkan secara publik:

- token autentikasi atau header Authorization;
- cookie atau credential;
- device ID runtime;
- `config.yaml` milik pengguna;
- activity log atau diagnostic yang masih memuat koordinat pribadi;
- path lokal yang mengandung nama akun Windows bila tidak diperlukan.

## Melaporkan kerentanan

Gunakan fitur **Private vulnerability reporting** pada tab Security repository bila tersedia. Bila fitur tersebut belum aktif, buka issue tanpa menyertakan exploit, token, atau data sensitif; minta kanal privat untuk detail lanjutan.

Proyek ini masih berstatus alpha. Jangan menggunakan TJ Nearby sebagai satu-satunya sumber untuk keputusan keselamatan, jadwal penting, atau jaminan kedatangan kendaraan.
