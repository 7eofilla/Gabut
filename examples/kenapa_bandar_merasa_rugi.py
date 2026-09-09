#!/usr/bin/env python3
"""
DEMO: kenapa bandar yang MATEMATIKANYA UNTUNG tetap MERASA selalu rugi.

Penjelasan paling sering benar untuk "kok gw rugi terus" bukan kecurangan,
melainkan bentuk distribusi keuntungan. Kalau pemain memakai strategi
martingale (gandakan taruhan setiap kalah), bandar akan:

    kalah kecil BERKALI-KALI, lalu menang besar SEKALI-SEKALI.

Rata-rata (mean) bandar tetap untung. Tapi yang DIRASAKAN manusia adalah
nilai tengah (median) - dan median bandar bisa negatif. Jadi perasaan
"gw rugi terus" 100% konsisten dengan permainan yang jujur dan menguntungkan.

Skrip ini membuktikannya dengan simulasi RNG yang DIJAMIN jujur.
"""
import numpy as np

PAYOUT = 1.95          # even-money, house edge 2.5%
BASE = 10
MAX_BET = 640          # batas meja: 10,20,40,80,160,320,640 -> 7 tingkat
ROUNDS = 200           # ronde per sesi
SESSIONS = 20_000
rng = np.random.default_rng(7)


def run(martingale: bool) -> np.ndarray:
    pnl = np.zeros(SESSIONS)
    for s in range(SESSIONS):
        bet, total = BASE, 0.0
        wins = rng.random(ROUNDS) < 0.5      # RNG JUJUR, 50/50 murni
        for r in range(ROUNDS):
            if wins[r]:                      # pemain menang
                total -= bet * (PAYOUT - 1.0)
                bet = BASE
            else:                            # bandar menang
                total += bet
                bet = min(bet * 2, MAX_BET) if martingale else BASE
        pnl[s] = total
    return pnl


print("=" * 76)
print("SIMULASI: RNG 100% JUJUR, house edge +2.5% (payout 1.95x)")
print(f"{SESSIONS:,} sesi x {ROUNDS} ronde   |   taruhan dasar {BASE}, batas meja {MAX_BET}")
print("=" * 76)
print(f"{'perilaku pemain':<22}{'MEAN':>12}{'MEDIAN':>12}{'% sesi bandar RUGI':>22}")
print("-" * 76)
for label, mart in [("taruhan datar", False), ("MARTINGALE", True)]:
    p = run(mart)
    print(f"{label:<22}{p.mean():>+12,.0f}{np.median(p):>+12,.0f}{(p < 0).mean()*100:>21.1f}%")
print("-" * 76)
print("""
CARA MEMBACA:
  Dua baris di atas memakai RNG yang persis sama jujurnya dan edge yang persis
  sama menguntungkannya. Yang berbeda cuma perilaku pemain.

  Lawan martingale, bandar RUGI di mayoritas sesi walau MEAN-nya tetap positif.
  Keuntungan bandar terkumpul di sedikit sesi besar saat pemain menabrak batas
  meja - dan sesi-sesi itu jarang terjadi.

  Artinya: "gw rugi di hampir semua sesi" BUKAN bukti kecurangan.
  Untuk membuktikan curang, kamu harus membandingkan P&L TOTAL-mu dengan
  distribusi P&L yang dihasilkan RNG jujur -> itulah bankroll_monte_carlo().
""")
