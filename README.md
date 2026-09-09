# rngaudit — Forensik Statistik untuk Bandar yang Curiga

> "Gw rugi terus padahal aturannya jelas gw yang untung. Gw sial, atau gw dicurangi?"

Alat ini menjawab pertanyaan itu **dengan bukti, bukan feeling**.

Ini **bukan** alat untuk memprediksi angka atau untuk menang judi. Ini alat
**audit**: mengukur apakah sebuah urutan hasil menyimpang dari acak murni, dan
kalau iya — menyimpang ke arah mana, kapan, dan menguntungkan siapa. Ini
teknik yang sama yang dipakai regulator perjudian dan auditor RNG.

---

## Urutan yang benar (jangan dibalik)

Ini bagian terpenting. Kebanyakan orang langsung lompat ke langkah 3, lalu
menuduh orang tanpa dasar.

### Langkah 0 — Cek matematikanya dulu

**Penyebab bandar rugi nomor satu adalah house edge yang salah hitung, bukan
RNG curang.** Sering banget karena salah paham soal arti "payout".

```bash
python3 -m rngaudit.cli edge --p-win 0.5 --payout 2.0  --payout-mode total
python3 -m rngaudit.cli edge --p-win 0.5 --payout 1.95 --payout-mode total
```

Bedanya "total" vs "profit":

| Mode | Taruh 100, payout 2.0, menang | Return | Edge bandar |
|---|---|---|---|
| `total` | terima **200** total | 2.0x | **0%** (impas!) |
| `profit` | terima 100 modal + **200** untung = 300 | 3.0x | **-50%** (bandar hancur) |

Kalau langkah ini menunjukkan edge ≤ 0, **berhenti di sini**. Gak ada yang
mencurangi lo — matematikanya yang bocor.

### Langkah 1 — Cek apakah datamu cukup

```bash
python3 -m rngaudit.cli power --k 6
```

Ini menampar ekspektasi, dan memang harus:

| Besar kecurangan | Ronde yang dibutuhkan (dadu 6 sisi) |
|---|---|
| 50% | 257 |
| 20% | 1.604 |
| 10% | 6.414 |
| 5% | 25.656 |

Kecurangan kecil butuh data **puluhan ribu ronde** untuk terbukti secara
statistik. Kalau lo cuma punya 200 ronde, hasil "wajar" itu **tidak berarti
bersih** — artinya cuma datanya belum cukup bicara.

### Langkah 2 — Kumpulkan data yang benar

```bash
python3 -m rngaudit.cli template log_ronde.csv
```

| Kolom | Wajib? | Kenapa penting |
|---|---|---|
| `outcome` | **YA** | Hasil RNG mentah (0-based: dadu 1–6 → tulis 0–5) |
| `player` | sangat | Menangkap kolusi satu pemain |
| `stake` | **KRUSIAL** | Menangkap curang-hanya-saat-taruhan-besar |
| `house_won` | **KRUSIAL** | 1 = bandar menang, 0 = pemain menang |
| `profit` | sangat | Untung/rugi bandar per ronde (+/-) |
| `ts` | berguna | Menangkap "mulai kapan jadi aneh" |

> **Cuma mencatat `outcome` adalah kesalahan paling umum.** Kecurangan yang
> cerdas tidak terlihat di distribusi angka — hanya terlihat saat angka
> disilangkan dengan taruhan, pemain, dan waktu.

### Langkah 3 — Audit

```bash
python3 -m rngaudit.cli audit log_ronde.csv --k 6 --p-house 0.5 --payout 1.95
```

Coba dulu tanpa data asli:
```bash
python3 -m rngaudit.cli demo --rig stake_targeted
python3 -m rngaudit.cli demo --rig player_targeted
python3 -m rngaudit.cli demo --rig fair
```

---

## Isi bateri tesnya

**Tes keacakan dasar** — apakah angkanya *terlihat* acak?

| Tes | Menangkap |
|---|---|
| Chi-square frekuensi | Ada angka yang muncul terlalu sering |
| Entropi (G-test) | Distribusi timpang |
| Runs (Wald–Wolfowitz) | Streak terlalu panjang / terlalu zigzag — **pembunuh angka ketikan manusia** |
| Autokorelasi (Ljung–Box) | Hasil sebelumnya memprediksi berikutnya (RNG rusak) |
| Transisi (Markov) | Aturan tersembunyi antar-ronde |
| Gap test | Angka ditahan / tidak boleh berulang |

**Forensik bersyarat** — menangkap kecurangan yang *pintar*:

| Tes | Menangkap |
|---|---|
| Bias vs besar taruhan | Jujur pas receh, curang pas taruhan gede |
| Anomali per pemain | Satu orang menang jauh di atas wajar (kolusi) |
| Drift waktu (CUSUM) | Dulu jujur, mulai tanggal tertentu berubah |
| Simulasi bankroll | **Sial atau dicurangi?** — jawaban paling langsung |

---

## Bukti bahwa alat ini bekerja

Jangan percaya alat forensik yang belum diuji. `validate.py` membuat data
dengan kecurangan yang **sudah diketahui jawabannya**, lalu mengukur seberapa
sering alat ini berhasil menangkapnya.

```bash
python3 validate.py
```

Tingkat deteksi (1.500 ronde × 120 pengulangan):

| Skenario | chi² frek | runs | autokor | bias vs taruhan | anomali pemain | drift |
|---|---|---|---|---|---|---|
| **fair** (kontrol) | 0.8% | 0.0% | 0.8% | 7.5% | 2.5% | 6.7% |
| freq_bias 30% | **77.5%** | 1.7% | 2.5% | 10.0% | 3.3% | 5.0% |
| streaky 20% | 20.0% | **100%** | **100%** | 7.5% | 0.8% | 14.2% |
| stake_targeted 30% | 1.7% | 1.7% | 0.8% | **100%** | 5.0% | 7.5% |
| player_targeted 30% | 0.8% | 0.8% | 0.8% | 7.5% | **90.0%** | 7.5% |
| late_rig 35% | 2.5% | 1.7% | 0.0% | **80.0%** | 1.7% | **50.0%** |

**Baca baris `stake_targeted`.** Chi-square frekuensi — tes yang dipakai
hampir semua orang — cuma menangkapnya **1,7%**, praktis buta. Tes bias vs
taruhan menangkapnya **100%**.

Inilah alasan alat ini ada: *kecurangan yang menghabiskan uangmu adalah
kecurangan yang tak terlihat di distribusi angka.*

Baris `fair` = alarm palsu, harus rendah. Sebagian besar ≤ 5% sesuai target.
Dua kolom sedikit di atas (7,5% dan 6,7%) karena kolom itu menggabungkan
beberapa sub-tes dengan OR; itu batasan yang kami sebutkan terbuka, bukan
kami sembunyikan.

---

## Kejujuran statistik yang dipaksakan alat ini

1. **Koreksi multiple testing (Benjamini–Hochberg).** Jalankan 20 tes pada RNG
   jujur, rata-rata 1 akan lolos p<0.05 karena kebetulan murni. Tanpa koreksi,
   lo akan menuduh orang berdasarkan kebisingan.
2. **"Tidak ada bukti" ≠ "terbukti bersih."** Laporan selalu menampilkan berapa
   ronde yang lo butuhkan, supaya lo tahu kapan hasil "wajar" itu tidak berarti apa-apa.
3. **Wajib replikasi.** Kalau ada sinyal menyala, jangan langsung menuduh.
   Kumpulkan data periode **berikutnya** dan lihat apakah sinyal yang sama
   muncul lagi. Lo gak bisa "beruntung" dua kali berturut-turut.
4. **Bias seleksi.** Jangan cuma mengaudit periode saat lo rugi. Itu namanya
   memilih data yang mendukung kesimpulan yang sudah lo mau.

---

## Batasan yang jujur

- Kalau angkanya **diketik manusia**, gak perlu statistik rumit — sistem itu
  memang bisa dicurangi kapan saja. Runs test biasanya langsung menangkapnya,
  tapi masalahnya bukan statistik, melainkan desain.
- Alat ini **tidak** bisa memprediksi angka berikutnya. RNG yang terbukti bias
  pun belum tentu bisa diprediksi.
- Bukti statistik itu **bukti probabilistik**, bukan pengakuan. Gunakan untuk
  mengambil keputusan (berhenti jadi host, minta sistem provably-fair), bukan
  untuk menuduh orang di depan umum.

---

## Solusi permanen: provably fair

Semua audit di atas bersifat *reaktif*. Solusi sesungguhnya bersifat
*preventif* — skema **provably fair** yang dipakai kasino kripto:

1. Host bikin `server_seed` rahasia, umumkan **hash**-nya (`SHA256`) sebelum main.
2. Pemain menyumbang `client_seed` mereka sendiri.
3. Hasil = `HMAC_SHA256(server_seed, client_seed + nonce)` → dipetakan ke angka.
4. Setelah ronde selesai, host **buka** `server_seed`. Siapa pun bisa
   memverifikasi hash-nya cocok dan hasilnya benar.

Kuncinya: host mengunci angkanya **sebelum** tahu taruhan pemain, dan pemain
ikut menentukan input. Tidak ada satu pihak pun yang bisa mengendalikan hasil.

---

## Struktur

```
rngaudit/
  stats_core.py   bateri tes keacakan + koreksi FDR
  forensics.py    tes bersyarat, simulasi bankroll, analisis daya, house edge
  simulate.py     generator data curang untuk pengujian
  loader.py       pembaca CSV (nama kolom fleksibel, ID/EN)
  report.py       laporan audit lengkap
  cli.py          antarmuka baris perintah
validate.py       pengukur false-positive & power detektor
```

Butuh: Python 3.11+, `numpy`, `scipy`.

```bash
pip install numpy scipy
```

---

## Temuan yang paling mungkin relevan untuk kamu

Jalankan:
```bash
python3 examples/kenapa_bandar_merasa_rugi.py
```

Hasilnya, dengan **RNG 100% jujur** dan **house edge +2.5%** (jadi bandar
memang secara matematika untung):

| Perilaku pemain | Mean P&L bandar | **Median** P&L bandar | % sesi bandar RUGI |
|---|---|---|---|
| Taruhan datar | +50 | +50 | 36.3% |
| **Martingale** | **+196** | **−196** | **62.3%** |

Baca baris kedua pelan-pelan. RNG-nya jujur. Edge-nya menguntungkan bandar.
Rata-ratanya positif. **Tapi bandar rugi di 62% sesi, dan sesi tipikalnya minus.**

Penyebabnya: pemain martingale menang kecil berkali-kali lalu kalah besar
sesekali. Keuntungan bandar terkumpul di sedikit sesi besar yang jarang datang.
Yang dirasakan manusia adalah **median**, bukan mean.

**"Gw rugi di hampir semua sesi" bukan bukti kecurangan.** Untuk membuktikan
curang, P&L totalmu harus dibandingkan dengan distribusi P&L dari RNG jujur —
dan itu persis yang dilakukan `bankroll_monte_carlo()`.
