#!/usr/bin/env python3
"""
Audit lengkap game "LEME"/Gemspin dari export chat WhatsApp Omni_Bot.

    python3 analyze_leme.py chat1.txt [chat2.txt ...]

Akuntansi di sini TIDAK memakai pesan payout sama sekali. Nominal taruhan
diambil dari pesan "Bet diterima"/"GO ALL", dan hasilnya dari "Multiplier
total" yang dicetak bot. Ini penting: bot memakai empat format pengumuman
kemenangan yang berbeda antar versi, dan mengandalkannya pernah membuat
audit ini salah total. Multiplier selalu ada dan selalu sama formatnya.
"""
from __future__ import annotations

import bisect
import re
import sys
from itertools import product
from pathlib import Path

import numpy as np
from scipy import stats

from rngaudit.stats_core import run_battery, frequency_test
from rngaudit.ledger import build, summarise

WHEEL = 37
score = lambda n: sum(int(c) for c in str(n)) % 10

RE_HASIL = re.compile(r"📊 \*Hasil\*\n((?:R\d+: .*\n)+)Hoster: (\d+)\nMultiplier total: ×(\d+)")
RE_ROUND = re.compile(r"R\d+: (\d+) → (.*)")
RE_AUTOW = re.compile(r"🚀 \*HOSTER AUTO-WIN!\*\nHoster spin: (\d+)")
RE_BET   = re.compile(r"✅ Bet @⁨([^⁩]*)⁩ \*([\d.,]+)\*")
RE_GOALL = re.compile(r"🚀 \*GO ALL!\* @⁨([^⁩]*)⁩ taruhan \*([\d.,]+) coin\*")
RE_SPIN  = re.compile(r"spin the wheel and got (\d+)")

_num = lambda s: float(s.replace(".", "").replace(",", ""))


# --------------------------------------------------------------------------
# ATURAN (setiap butir diverifikasi terhadap keluaran bot)
# --------------------------------------------------------------------------
def round_multiplier(s: int, hs: int) -> int:
    if s == 0: return 4          # LEME jackpot
    if s == 1: return 3          # LEME jackpot
    if s in (2, 9): return 0     # auto-lose
    return 2 if s > hs else 0    # seri ikut kalah


def settle(total: int) -> str:
    """
    x0  -> bandar menang
    x2  -> RES: satu 'normal win' + satu kalah, diulang TANPA dibayar
    sisanya -> pemain dibayar bet x total/2

    Perhatikan: x2 adalah SATU-SATUNYA yang memicu RES. Kombinasi
    'jackpot + kalah' menghasilkan x3 atau x4 dan TETAP DIBAYAR - inilah
    yang membedakan model ini dari tebakan naif 'satu menang satu kalah = RES'.
    """
    if total == 0: return "house"
    if total == 2: return "res"
    return "player"


def theory() -> dict:
    aw = lose = res = win = 0
    pay = 0.0
    for h, s1, s2 in product(range(WHEEL), repeat=3):
        hs = score(h)
        if hs in (0, 1):                       # HOSTER AUTO-WIN
            aw += 1
            continue
        t = round_multiplier(score(s1), hs) + round_multiplier(score(s2), hs)
        r = settle(t)
        if r == "house": lose += 1
        elif r == "res": res += 1
        else: win += 1; pay += t / 2
    T = WHEEL ** 3
    house, player = (aw + lose) / T, win / T
    return {"autowin": aw/T, "lose": lose/T, "res": res/T, "win": player,
            "p_house": house/(house+player),
            "E_return": (pay/T/player) * (player/(house+player))}


def audit(paths: list[str]) -> None:
    th = theory()
    B = "=" * 84
    print(B); print("AUDIT LEME (Gemspin) — Omni_Bot"); print(B)

    print(f"\n[1] HOUSE EDGE TEORETIS (roda 0-36 seragam)")
    print(f"    auto-win hoster {th['autowin']*100:5.2f}% | kalah {th['lose']*100:5.2f}%"
          f" | RES {th['res']*100:5.2f}% | dibayar {th['win']*100:5.2f}%")
    print(f"    bandar menang (setelah RES tuntas) : {th['p_house']*100:.2f}%")
    print(f"    pengembalian ke pemain             : {th['E_return']*100:.2f}%")
    print(f"    >>> HOUSE EDGE = {(1-th['E_return'])*100:+.2f}% <<<")

    print(f"\n[2] BUKU KAS BANDAR (cocokkan per NAMA PEMAIN, fee 3% diperhitungkan)")
    hdr = (f"    {'dataset':<26}{'tuntas':>8}{'bandar':>8}{'pemain':>8}"
           f"{'turnover':>14}{'fee 3%':>11}{'P&L bersih':>14}{'edge':>8}{'win%':>7}")
    print(hdr); print("    " + "-" * (len(hdr) - 4))
    gt = gp = 0.0
    for pth in paths:
        rows, st = build(pth)
        sm = summarise(rows)
        name = Path(pth).stem[:26]
        if sm["n"] < 20:
            print(f"    {name:<26}{sm['n']:>8}   -- sampel <20, tidak disimpulkan --"); continue
        gt += sm["turnover"]; gp += sm["pnl"]
        print(f"    {name:<26}{sm['n']:>8,}{sm['house_wins']:>8,}{sm['player_wins']:>8,}"
              f"{sm['turnover']:>14,.0f}{sm['fee']:>11,.0f}{sm['pnl']:>+14,.0f}"
              f"{sm['edge']*100:>+7.2f}%{sm['win_rate']*100:>6.1f}%")
    if gt:
        print("    " + "-" * (len(hdr) - 4))
        print(f"    {'GABUNGAN':<26}{'':>8}{'':>8}{'':>8}{gt:>14,.0f}{'':>11}"
              f"{gp:>+14,.0f}{gp/gt*100:>+7.2f}%")
    E = th["E_return"]
    print(f"    teoretis: sebelum fee {(1-E)*100:+.2f}% | sesudah fee 3% atas payout"
          f" {(1-E-E*0.03)*100:+.2f}% | bandar menang {th['p_house']*100:.2f}%")

    # kumpulkan spin dan kategori percobaan
    counts = {"autowin": 0, "lose": 0, "res": 0, "win": 0}
    sp_player: list[tuple] = []
    sp_hoster: list[tuple] = []
    for fidx, pth in enumerate(paths):
        txt = Path(pth).read_text(encoding="utf-8", errors="replace")
        for m in RE_HASIL.finditer(txt):
            for k, rm in enumerate(RE_ROUND.finditer(m.group(1))):
                sp_player.append(((fidx, m.start(), k), int(rm.group(1))))
            sp_hoster.append(((fidx, m.start(), 9), int(m.group(2))))
            t = int(m.group(3))
            counts["res" if t == 2 else ("lose" if t == 0 else "win")] += 1
        for m in RE_AUTOW.finditer(txt):
            sp_hoster.append(((fidx, m.start(), 9), int(m.group(1))))
            counts["autowin"] += 1
    # urutkan menurut (file, posisi, urutan ronde) supaya spin auto-win tidak
    # menumpuk di ujung daftar dan menciptakan autokorelasi palsu
    spins_player = [v for _, v in sorted(sp_player)]
    spins_hoster = [v for _, v in sorted(sp_hoster)]

    print(f"\n[3] VALIDASI MODEL ATURAN (tingkat percobaan, tanpa parsing payout)")
    N = sum(counts.values())
    print(f"    {'kategori':<20}{'diamati':>10}{'teori':>10}{'z':>8}")
    for k, lab in [("autowin", "auto-win hoster"), ("lose", "pemain kalah"),
                   ("res", "RES / restart"), ("win", "pemain dibayar")]:
        o = counts[k] / N
        se = np.sqrt(th[k] * (1 - th[k]) / N)
        z = (o - th[k]) / se
        print(f"    {lab:<20}{o*100:>9.2f}%{th[k]*100:>9.2f}%{z:>8.2f}"
              f"{'  <-- MENYIMPANG' if abs(z) > 3 else ''}")
    print(f"    total percobaan: {N:,}")

    # Diuji TERPISAH per peran, tidak digabung. Spin hoster dan spin pemain
    # muncul berselang-seling (R1, R2, Hoster, R1, R2, Hoster, ...), dan spin
    # hoster di blok Hasil tidak pernah berskor 0/1 karena kasus itu menjadi
    # auto-win. Menggabungkannya menciptakan pola periodik buatan yang
    # langsung menyalakan uji transisi (p=0) tanpa ada yang salah pada RNG.
    print(f"\n[4] KEACAKAN RODA — diuji terpisah per peran")
    # Urutkan sesuai posisi kemunculan di chat. Blok Hasil dan blok auto-win
    # dikumpulkan oleh dua regex terpisah; kalau tidak diurutkan ulang, semua
    # spin auto-win (yang selalu berskor 0/1) menumpuk di ujung daftar dan
    # menciptakan autokorelasi palsu yang ekstrem.
    for nama, arr in (("SPIN PEMAIN", spins_player), ("SPIN HOSTER", spins_hoster)):
        print(f"\n    --- {nama} (n={len(arr):,}) ---")
        for t in run_battery(arr, WHEEL):
            print(f"    {t}")

    print("\n" + B)


if __name__ == "__main__":
    audit(sys.argv[1:] or ["chat.txt"])
