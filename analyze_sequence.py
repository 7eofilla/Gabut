#!/usr/bin/env python3
"""
Analisis frekuensi & transisi seluruh angka roda.

    python3 analyze_sequence.py chat1.txt [chat2.txt ...] [--csv keluaran/]

Menjawab dua pertanyaan:
  1. Berapa kali tiap angka 0-36 keluar?
  2. Setelah angka X, angka apa yang cenderung keluar, dan berapa persen?

Pertanyaan kedua adalah jebakan statistik klasik, dan modul ini menanganinya
secara eksplisit. Dengan 37 angka, penerus sebuah angka tersebar ke 37 sel
yang masing-masing hanya berisi ~15 pengamatan. Pada ukuran sampel itu,
penerus terbanyak SELALU tampak menonjol walaupun datanya acak sempurna.
Karena itu setiap "pola" di sini selalu dibandingkan dengan pola yang muncul
pada data yang urutannya sudah diacak.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
from scipy import stats

from rngaudit.sequence import (frequency_table, transition_matrix, top_followers,
                               independence_test, permutation_null)

K = 37
score = lambda n: sum(int(c) for c in str(n)) % 10

RE_HASIL = re.compile(r"📊 \*Hasil\*\n((?:R\d+: .*\n)+)Hoster: (\d+)\nMultiplier total: ×(\d+)")
RE_ROUND = re.compile(r"R\d+: (\d+) → ")
RE_AUTOW = re.compile(r"🚀 \*HOSTER AUTO-WIN!\*\nHoster spin: (\d+)")


def collect(paths):
    """Kumpulkan spin dalam urutan kejadian sebenarnya, lengkap dengan perannya."""
    rows = []
    for fi, p in enumerate(paths):
        txt = Path(p).read_text(encoding="utf-8", errors="replace")
        for m in RE_HASIL.finditer(txt):
            for j, rm in enumerate(RE_ROUND.finditer(m.group(1))):
                rows.append((fi, m.start(), j, int(rm.group(1)), "player"))
            rows.append((fi, m.start(), 8, int(m.group(2)), "hoster"))
        for m in RE_AUTOW.finditer(txt):
            rows.append((fi, m.start(), 8, int(m.group(1)), "hoster"))
    rows.sort(key=lambda t: (t[0], t[1], t[2]))
    return rows


def main(paths, csv_dir=None):
    rows = collect(paths)
    vals = [r[3] for r in rows]
    B = "=" * 80

    # ---- 1. frekuensi ----
    ft = frequency_table(vals, K)
    print(B); print(f"FREKUENSI — {ft['n']:,} spin (pemain + hoster digabung)"); print(B)
    print(f"  harapan per angka: {ft['expected']:.1f}  ({100/K:.3f}%)")
    print(f"  chi-square {ft['chi2']:.2f} (dof {K-1})  p={ft['p']:.4f}  -> "
          f"{'MENYIMPANG' if ft['p'] < 0.05 else 'sesuai acak seragam'}")
    o = ft["observed"]
    hi, lo = int(np.argmax(o)), int(np.argmin(o))
    print(f"  tersering {hi} ({o[hi]}x)  |  terjarang {lo} ({o[lo]}x)  |  selisih {o[hi]-o[lo]}")

    rng = np.random.default_rng(0)
    gaps = np.array([(lambda c: c.max() - c.min())(rng.multinomial(ft["n"], [1/K]*K))
                     for _ in range(10000)])
    print(f"  KALIBRASI selisih maks-min pada roda jujur: rata-rata {gaps.mean():.0f}, "
          f"5-95% [{np.quantile(gaps,.05):.0f}, {np.quantile(gaps,.95):.0f}]"
          f"  -> data asli persentil {(gaps <= o[hi]-o[lo]).mean()*100:.0f}")

    # ---- 2. transisi ----
    mat = transition_matrix(vals, K)
    chi2, p, dof = independence_test(mat)
    print(f"\n{B}"); print("TRANSISI — 'setelah X keluar apa?'"); print(B)
    print(f"  pasangan {mat.sum():,} | 1.369 sel | rata-rata {mat.sum()/1369:.1f} per sel")
    print(f"  independensi: chi2={chi2:.1f} dof={dof} p={p:.4f}  -> "
          f"{'ADA ketergantungan' if p < 0.05 else 'TIDAK ada ketergantungan'}")

    best = []
    for v in range(K):
        tot, tops = top_followers(mat, v, 1)
        if tops:
            best.append((tops[0][2], v, tops[0][0], tops[0][1], tot))
    best.sort(reverse=True)
    print("  pola terkuat:")
    for sh, v, f, c, tot in best[:3]:
        print(f"    setelah {v:>2} -> {f:>2}: {c}/{tot} = {sh*100:.2f}%  (harapan {100/K:.2f}%)")

    bs, cs = permutation_null(vals, K, n_perm=1000, seed=1)
    print(f"  KALIBRASI pola terkuat pada data DIACAK: rata-rata {bs.mean()*100:.2f}%, "
          f"5-95% [{np.quantile(bs,.05)*100:.2f}%, {np.quantile(bs,.95)*100:.2f}%]")
    print(f"  -> data asli {best[0][0]*100:.2f}% = persentil {(bs <= best[0][0]).mean()*100:.0f}"
          f"  {'(TIDAK ADA POLA)' if (bs <= best[0][0]).mean() < 0.95 else '(DI LUAR KEBIASAAN)'}")

    # ---- 3. pengulangan langsung, dipecah per jenis pasangan ----
    print(f"\n{B}"); print("PENGULANGAN LANGSUNG (X lalu X lagi)"); print(B)
    def rep_test(label, pr):
        if len(pr) < 50:
            return
        rep = sum(1 for a, b in pr if a == b)
        e = len(pr) / K
        z = (rep - e) / np.sqrt(e * (1 - 1/K))
        print(f"  {label:<40} n={len(pr):>6,}  {rep:>4} vs {e:>6.1f}  z={z:>+6.2f}"
              f"{'  <-- MENYIMPANG' if abs(z) > 3 else ''}")

    same_round = [(rows[i][3], rows[i+1][3]) for i in range(len(rows)-1)
                  if rows[i][4] == rows[i+1][4] == "player"
                  and rows[i][2] == 0 and rows[i+1][2] == 1
                  and rows[i][0] == rows[i+1][0] and rows[i][1] == rows[i+1][1]]
    rep_test("R1 -> R2 (ronde sama, PALING BERSIH)", same_round)
    rep_test("semua pasangan berurutan", [(vals[i], vals[i+1]) for i in range(len(vals)-1)])

    if csv_dir:
        out = Path(csv_dir); out.mkdir(parents=True, exist_ok=True)
        with (out / "frekuensi.csv").open("w") as fh:
            fh.write("angka,jumlah,persen,harapan,z\n")
            for i in range(K):
                fh.write(f"{i},{o[i]},{o[i]/ft['n']*100:.4f},{ft['expected']:.2f},"
                         f"{ft['resid'][i]:.4f}\n")
        with (out / "transisi.csv").open("w") as fh:
            fh.write("dari," + ",".join(str(i) for i in range(K)) + "\n")
            for i in range(K):
                fh.write(f"{i}," + ",".join(str(int(x)) for x in mat[i]) + "\n")
        print(f"\n  CSV ditulis ke {out}/frekuensi.csv dan {out}/transisi.csv")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    csv = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--csv=")), None)
    main(args, csv)
