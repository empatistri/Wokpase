# Wokpase

Workspace coding berbasis terminal dengan editor, file tree, shell, dan bantuan
AI yang menerapkan perubahan hanya setelah ditinjau.

## Menjalankan

Gunakan Python 3.10 atau lebih baru:

```sh
python -m pip install -e .
wokpase [direktori-workspace]
```

Atau jalankan dari checkout dengan `python -m wokpase`.

## Konfigurasi AI (BYOK)

Kunci provider diberikan lewat environment variable:

```sh
export WOKPASE_GEMINI_KEY="..."
export WOKPASE_GROQ_KEY="..."
export WOKPASE_OPENROUTER_KEY="..."
```

Secara default Gemini merencanakan proyek dan Groq menghasilkan kode. Untuk
menggunakan OpenRouter Free Models Router pada kedua agen, buat API key
OpenRouter lalu pilih `openrouter/free` di `~/.config/wokpase/config.toml`:

```toml
[agents.planner]
provider = "openrouter"
model = "openrouter/free"

[agents.executor]
provider = "openrouter"
model = "openrouter/free"
```

OpenRouter juga menerima ID model gratis yang berakhiran `:free`; aplikasi
menolak model OpenRouter lain agar konfigurasi ini tidak memilih model berbayar.
Model gratis memiliki batas penggunaan dan ketersediaan yang dapat berubah.
Gemini dan Groq tetap tersedia melalui free tier masing-masing.
Lihat [OpenRouter Free Models](https://openrouter.ai/docs/cookbook/get-started/free-models-router-playground),
[model gratis](https://openrouter.ai/docs/guides/routing/model-variants/free),
[harga Gemini](https://ai.google.dev/gemini-api/docs/pricing), dan
[batas Groq](https://console.groq.com/docs/rate-limits).

## Perintah

Ketik `:help` di command bar. Perintah inti: `:open PATH`, `:file PATH`,
`:folder PATH`, `:save`, `:run COMMAND`, `:ai INSTRUCTION`, dan
`:create-project DESCRIPTION`. Membuat berkas akan langsung membukanya di
editor; folder perantara pada path berkas dibuat otomatis. `:new-file` dan
`:new-folder` tetap tersedia sebagai alias.
Typo yang jelas pada nama perintah akan dikoreksi otomatis saat Enter;
argumen seperti path tetap dibiarkan apa adanya.
Pintasan `Ctrl+S` menyimpan, `Ctrl+K` meminta instruksi AI, dan `Ctrl+Q`
keluar. Perubahan AI selalu ditampilkan dalam diff; tekan `Y` untuk menerima
atau `N` untuk menolak.

Perintah `:run` menjalankan shell command yang diketik pengguna di direktori
workspace. Tinjau perintah sebelum menjalankannya.
