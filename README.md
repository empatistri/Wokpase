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
```

Secara default Gemini merencanakan proyek dan Groq menghasilkan kode. Profil
provider/model dapat diubah di `~/.config/wokpase/config.toml`:

```toml
[agents.planner]
provider = "gemini"
model = "gemini-2.0-flash"

[agents.executor]
provider = "groq"
model = "llama-3.3-70b-versatile"
```

## Perintah

Ketik `:help` di command bar. Perintah inti: `:open PATH`, `:save`,
`:run COMMAND`, `:ai INSTRUCTION`, dan `:create-project DESCRIPTION`.
Pintasan `Ctrl+S` menyimpan, `Ctrl+K` meminta instruksi AI, dan `Ctrl+Q`
keluar. Perubahan AI selalu ditampilkan dalam diff; tekan `Y` untuk menerima
atau `N` untuk menolak.

Perintah `:run` menjalankan shell command yang diketik pengguna di direktori
workspace. Tinjau perintah sebelum menjalankannya.
