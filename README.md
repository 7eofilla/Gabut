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

---

# STUDI KASUS: audit game "LEME" (Gemspin), bot WhatsApp Omni_Bot

Empat export chat, **7.648 percobaan**, **5.996 taruhan tuntas**, **20.358
putaran roda**.

```bash
python3 analyze_leme.py "Chat WhatsApp dengan LEME HOSTER.txt" [chat lain...]
```

## Aturan (setiap butir diverifikasi terhadap keluaran bot)

Roda roulette Eropa **0–36**. Skor = **jumlah digit mod 10** (`26→8`, `19→0`).
Pemain memutar 2x, hoster 1x.

1. **Hoster skor 0 atau 1 → `HOSTER AUTO-WIN`**, mengalahkan apa pun termasuk
   jackpot pemain (16,22% ronde).
2. Selain itu, tiap ronde-pemain: skor 0 → ×4 · skor 1 → ×3 · skor 2 atau 9 →
   ×0 · skor > hoster → ×2 · seri atau lebih kecil → ×0.
3. **`Multiplier total` = ×0** → bandar menang.
4. **`Multiplier total` = ×2** → `♻️ RES`, **diulang tanpa dibayar**.
5. **Sisanya** → `payout = bet × multiplier ÷ 2`.

> Butir 4 adalah kuncinya, dan halus. RES **hanya** terjadi pada ×2, yaitu satu
> *normal win* + satu kalah. Kombinasi **jackpot + kalah** menghasilkan ×3/×4
> dan **tetap dibayar**. Menebak "satu menang satu kalah selalu RES" membuat
> perkiraan house edge meleset dari +8% menjadi +27%.

Bukti: blok `×2` berjumlah 1.296 dan event `RES` berjumlah 1.297 — cocok.

## Hasil

**Model aturan terkonfirmasi** pada 7.648 percobaan, tanpa parsing pesan payout:

| Kategori | Diamati | Teori | z |
|---|---|---|---|
| Auto-win hoster | 16,91% | 16,22% | +1,64 |
| Pemain kalah | 30,01% | 30,99% | −1,85 |
| RES / restart | 17,76% | 17,47% | +0,66 |
| Pemain dibayar | 35,33% | 35,33% | **−0,00** |

**RNG jujur.** Dua belas tes, dua populasi, semuanya lolos:

| | n | chi² | Runs | Autokor. | Transisi | Gap |
|---|---|---|---|---|---|---|
| Spin pemain | 12.710 | 0,27 | 0,42 | 0,59 | 0,24 | 0,63 |
| Spin hoster | 7.648 | 0,20 | 0,69 | 0,14 | 0,29 | 0,88 |

**Bandar untung, sesuai desain:**

| | Nilai |
|---|---|
| House edge teoretis | **+8,32%** |
| Edge terealisasi | **+8,61%** |
| Bandar menang | 57,4% (teori 57,19%; z=+0,25, p=0,80) |
| Turnover | 139.740.662 coin |
| **P&L bandar** | **+12.026.882 coin** |

## Pelajaran metodologis: empat artefak, nol kecurangan

Audit ini menghasilkan **empat "temuan" palsu berturut-turut**, semuanya dari
pengumpulan data, bukan dari RNG. Didokumentasikan karena inilah isi
sesungguhnya dari pekerjaan forensik.

| # | Cacat | "Temuan" palsu yang dihasilkan |
|---|---|---|
| 1 | Event `HOSTER AUTO-WIN` tak terbaca (format pesan lain, tanpa blok `Hasil`) | Enam angka "tak pernah muncul" di 6.026 spin hoster, **peluang 1e−463** |
| 2 | `RES` diabaikan → percobaan yang diulang dihitung sebagai payout | House edge **−26%** (padahal +8%) |
| 3 | Spin pemain & hoster diuji berselang-seling (R1,R2,Hoster,…) | Uji transisi **p=0** karena pola periodik |
| 4 | Spin dikumpulkan per-regex lalu digabung tanpa diurutkan ulang | Autokorelasi **p=2e−6** karena spin auto-win menumpuk di ujung |

Artefak #1 adalah yang paling berbahaya: p-value **1e−463** terasa seperti
bukti yang tak terbantahkan. Padahal itu cuma bekas alat ukur yang rusak.

> **Sebuah p-value hanya sekuat asumsi pengumpulan datanya.** Ekstraksi yang
> bias menghasilkan bukti yang jauh lebih meyakinkan daripada kecurangan yang
> sesungguhnya. Sebelum menjalankan uji apa pun: pastikan neraca kejadian
> tertutup (jumlah taruhan = jumlah penyelesaian), dan pastikan urutan datamu
> adalah urutan kejadian yang sebenarnya.

## Kesimpulan

Aturan LEME memberi bandar keunggulan **+8,3%**, RNG-nya lolos seluruh uji
keacakan pada dua populasi dan dua periode terpisah, dan tidak ada bias
bersyarat terhadap besar taruhan, waktu, maupun pemain. Kalau seorang hoster
tetap merasa rugi, penyebabnya berada **di luar meja**.
