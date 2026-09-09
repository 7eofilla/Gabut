#!/usr/bin/env python3
"""
Audit lengkap game "LEME"/Gemspin dari export chat WhatsApp Omni_Bot.

Pemakaian:
    python3 analyze_leme.py "Chat WhatsApp dengan LEME HOSTER.txt"

Skrip ini memuat seluruh rantai bukti: rekonstruksi aturan, verifikasinya
terhadap output bot, uji keacakan roda, forensik bersyarat, rekonsiliasi P&L,
dan perhitungan perbaikan aturan.
"""
import sys
from collections import Counter

import numpy as np
from scipy import stats

from rngaudit.parse_omnibot import parse
from rngaudit.stats_core import run_battery, frequency_test
from rngaudit.forensics import Round, bias_vs_stake, per_player_anomaly, temporal_drift

WHEEL = 37                                    # roulette Eropa 0..36
score = lambda n: sum(int(c) for c in str(n)) % 10


def round_multiplier(s: int, h: int) -> int:
    """Aturan LEME per ronde-pemain. Diverifikasi 100% terhadap 6.026 ronde."""
    if s == 0: return 4          # LEME jackpot
    if s == 1: return 3          # LEME jackpot
    if s == 9: return 0          # auto-lose
    return 2 if s > h else 0     # seri pun kalah


def main(path: str) -> None:
    rounds, spins = parse(path)
    pl = [s.value for s in spins if s.role == "player"]
    ho = [s.value for s in spins if s.role == "hoster"]
    B = "=" * 74

    print(B); print(f"AUDIT LEME  |  {len(rounds):,} ronde  |  {len(spins):,} spin"); print(B)

    # 1 -- verifikasi model aturan
    ok = sum(1 for r in rounds if len(r.player_spins) == 2 and
             sum(round_multiplier(score(p), score(r.hoster_spin))
                 for p in r.player_spins) == r.multiplier)
    print(f"\n[1] Model aturan cocok dengan output bot: {ok:,}/{len(rounds):,} "
          f"({ok/len(rounds)*100:.2f}%)")

    # 2 -- keacakan roda
    print(f"\n[2] Keseragaman roda")
    for nama, arr in (("spin PEMAIN", pl), ("spin HOSTER", ho)):
        t = frequency_test(arr, WHEEL)
        print(f"    {nama:<13} n={len(arr):>6,}  chi2={t.statistic:9.2f}  p={t.p_value:.3e}"
              f"  -> {'MENYIMPANG' if t.p_value < .05 else 'wajar'}")
    miss = sorted(set(range(WHEEL)) - set(ho))
    print(f"    angka absen dari spin hoster: {miss} (skor {[score(m) for m in miss]})")
    print(f"    peluang absen kebetulan     : (31/37)^{len(ho)} = 1e{len(ho)*np.log10(31/37):.0f}")

    # 3 -- house edge
    Em_uni = 2 * sum(round_multiplier(score(p), score(h))
                     for h in range(WHEEL) for p in range(WHEEL)) / WHEEL**2
    Em_obs = float(np.mean([r.multiplier for r in rounds]))
    print(f"\n[3] House edge  (payout = bet x multiplier / 2)")
    print(f"    aturan tertulis, roda seragam : pengembalian {Em_uni/2*100:7.3f}%"
          f"  -> edge bandar {(1-Em_uni/2)*100:+7.3f}%")
    print(f"    realita bot (hoster dibatasi) : pengembalian {Em_obs/2*100:7.3f}%"
          f"  -> edge bandar {(1-Em_obs/2)*100:+7.3f}%")

    # 4 -- forensik bersyarat
    R = [Round(idx=i, outcome=r.hoster_spin, player=r.who or "?", stake=r.bet,
               house_won=(r.multiplier == 0), profit=r.bet - r.bet*r.multiplier/2, ts=float(i))
         for i, r in enumerate(rounds) if r.bet]
    print(f"\n[4] Forensik bersyarat ({len(R):,} ronde ber-taruhan)")
    for t in list(bias_vs_stake(R)) + list(temporal_drift(R)):
        print(f"    {t}")
    flag = [t for t in per_player_anomaly(R, min_rounds=40) if t.suspicious]
    print(f"    pemain anomali sesudah koreksi FDR: {len(flag)}")

    # 5 -- rekonsiliasi P&L: sial, curang, atau aturan rusak?
    turnover = sum(r.stake for r in R)
    pnl = sum(r.profit for r in R)
    expected = turnover * (1 - Em_obs/2)
    sd = float(np.std([r.profit for r in R]) * np.sqrt(len(R)))
    z = (pnl - expected) / sd
    print(f"\n[5] Rekonsiliasi P&L")
    print(f"    turnover                 : {turnover:>16,.0f}")
    print(f"    P&L bandar NYATA         : {pnl:>+16,.0f}")
    print(f"    P&L yang DIPREDIKSI aturan: {expected:>+16,.0f}")
    print(f"    simpangan baku           : {sd:>16,.0f}")
    print(f"    z = {z:+.3f}  (p dua sisi = {2*stats.norm.sf(abs(z)):.3f})")
    print(f"    -> {'sesuai prediksi aturan; tidak ada sisa kerugian tak terjelaskan'if abs(z)<2 else 'ADA penyimpangan di luar aturan'}")

    # 6 -- perbaikan
    print(f"\n[6] Perbaikan: ganti pembagi payout (sekarang 2.000)")
    for edge in (0.02, 0.05, 0.10):
        print(f"    edge +{int(edge*100):2d}% -> pembagi {Em_obs/(1-edge):.3f}"
              f"   (kalau hoster tidak dibatasi: {Em_uni/(1-edge):.3f})")
    print("\n" + B)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "chat.txt")
