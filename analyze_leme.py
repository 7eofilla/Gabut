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

    print(f"\n[2] REKONSTRUKSI TARUHAN")
    hdr = f"    {'dataset':<26}{'tuntas':>8}{'bandar':>8}{'pemain':>8}{'RES':>7}{'turnover':>14}{'P&L':>14}{'edge':>9}{'win%':>7}"
    print(hdr); print("    " + "-" * (len(hdr) - 4))
    gt = gp = 0.0
    spins_player: list[int] = []
    spins_hoster: list[int] = []
    counts = {"autowin": 0, "lose": 0, "res": 0, "win": 0}

    for fidx, p in enumerate(paths):
        txt = Path(p).read_text(encoding="utf-8", errors="replace")
        ev = sorted(
            [(m.start(), "bet", _num(m.group(2))) for m in RE_BET.finditer(txt)] +
            [(m.start(), "bet", _num(m.group(2))) for m in RE_GOALL.finditer(txt)] +
            [(m.start(), "hasil", int(m.group(3))) for m in RE_HASIL.finditer(txt)] +
            [(m.start(), "autowin", -1) for m in RE_AUTOW.finditer(txt)])

        for m in RE_HASIL.finditer(txt):
            for k, rm in enumerate(RE_ROUND.finditer(m.group(1))):
                # kunci urut: (file, posisi blok, urutan ronde dalam blok)
                spins_player.append(((fidx, m.start(), k), int(rm.group(1))))
            spins_hoster.append(((fidx, m.start(), 9), int(m.group(2))))
            counts["res" if int(m.group(3)) == 2 else
                   ("lose" if int(m.group(3)) == 0 else "win")] += 1
        for m in RE_AUTOW.finditer(txt):
            spins_hoster.append(((fidx, m.start(), 9), int(m.group(1)))); counts["autowin"] += 1
        # CATATAN: baris "spin the wheel and got N" dari bot roulette adalah
        # GEMA dari spin yang sama, bukan putaran tambahan. Memasukkannya akan
        # menggandakan setiap spin dan menciptakan korelasi berurutan palsu
        # (uji transisi langsung menyala p=0). Jadi hanya blok Hasil dan
        # auto-win yang dipakai - itu catatan permainan yang otoritatif.

        stake = None; pnl = turn = 0.0; nH = nP = nR = 0
        for _, kind, val in ev:
            if kind == "bet":
                stake = val
            elif stake is None:
                continue
            elif kind == "autowin":
                pnl += stake; turn += stake; nH += 1; stake = None
            else:
                r = settle(val)
                if r == "res": nR += 1; continue
                if r == "house": pnl += stake; nH += 1
                else: pnl += stake - stake * val / 2; nP += 1
                turn += stake; stake = None

        n = nH + nP
        name = Path(p).stem[:26]
        if n < 20:
            print(f"    {name:<26}{n:>8}   -- sampel <20, tidak disimpulkan --"); continue
        gt += turn; gp += pnl
        print(f"    {name:<26}{n:>8,}{nH:>8,}{nP:>8,}{nR:>7,}{turn:>14,.0f}"
              f"{pnl:>+14,.0f}{pnl/turn*100:>+8.2f}%{nH/n*100:>6.1f}%")

    if gt:
        print("    " + "-" * (len(hdr) - 4))
        print(f"    {'GABUNGAN':<26}{'':>8}{'':>8}{'':>8}{'':>7}{gt:>14,.0f}"
              f"{gp:>+14,.0f}{gp/gt*100:>+8.2f}%")

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
    spins_player = [v for _, v in sorted(spins_player)]
    spins_hoster = [v for _, v in sorted(spins_hoster)]
    for nama, arr in (("SPIN PEMAIN", spins_player), ("SPIN HOSTER", spins_hoster)):
        print(f"\n    --- {nama} (n={len(arr):,}) ---")
        for t in run_battery(arr, WHEEL):
            print(f"    {t}")

    print("\n" + B)


if __name__ == "__main__":
    audit(sys.argv[1:] or ["chat.txt"])
