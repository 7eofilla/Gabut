#!/usr/bin/env python3
"""
VALIDASI DETEKTOR.

Dua hal yang diukur:
  1. FALSE POSITIVE - seberapa sering alat ini menuduh RNG JUJUR sebagai curang?
     (harus mendekati 5%, sesuai alpha yang kita pilih)
  2. POWER          - seberapa sering alat ini berhasil menangkap kecurangan
     yang MEMANG ADA? (makin tinggi makin bagus)

Alat forensik tanpa dua angka ini tidak layak dipercaya.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from rngaudit.simulate import simulate, K, PAYOUT, MODE
from rngaudit.stats_core import run_battery
from rngaudit.forensics import (bias_vs_stake, per_player_anomaly,
                                temporal_drift, bankroll_monte_carlo)

N_ROUNDS = 1500
N_REPS   = 120
SCENARIOS = [
    ("fair",            0.00, "KONTROL: RNG jujur"),
    ("freq_bias",       0.30, "angka '1' muncul 30% lebih sering"),
    ("streaky",         0.20, "20% hasil mengulang hasil sebelumnya"),
    ("stake_targeted",  0.30, "taruhan besar: pemain dipaksa menang 30%"),
    ("player_targeted", 0.30, "pemain 'andi' dipaksa menang 30%"),
    ("late_rig",        0.35, "curang mulai paruh kedua saja"),
]

def flags(rounds):
    """Kembalikan dict nama-kelompok-tes -> apakah menyalakan alarm."""
    o = [r.outcome for r in rounds]
    bat = run_battery(o, K)
    return {
        "chi2 frekuensi":     bat[0].suspicious,
        "runs/streak":        bat[2].suspicious,
        "autokorelasi":       bat[3].suspicious,
        "transisi":           bat[4].suspicious,
        "bias vs taruhan":    any(t.suspicious for t in bias_vs_stake(rounds)),
        "anomali pemain":     any(t.suspicious for t in per_player_anomaly(rounds)),
        "drift waktu":        any(t.suspicious for t in temporal_drift(rounds)),
    }

names = None
print(f"VALIDASI  |  {N_ROUNDS} ronde x {N_REPS} pengulangan per skenario\n")
rows = []
for rig, strength, desc in SCENARIOS:
    acc = None
    for rep in range(N_REPS):
        f = flags(simulate(N_ROUNDS, rig, strength, seed=10_000 + rep))
        if acc is None:
            acc = {k2: 0 for k2 in f}
            names = list(f)
        for k2, v in f.items():
            acc[k2] += int(v)
    rows.append((rig, desc, {k2: v / N_REPS for k2, v in acc.items()}))
    print(f"  selesai: {rig}")

w = 17
print("\n" + "=" * (w + 8 * len(names)))
print("TINGKAT DETEKSI (proporsi alarm menyala; baris 'fair' = alarm palsu)")
print("=" * (w + 8 * len(names)))
print(f"{'skenario':<{w}}" + "".join(f"{n[:7]:>8}" for n in names))
print("-" * (w + 8 * len(names)))
for rig, desc, r in rows:
    print(f"{rig:<{w}}" + "".join(f"{r[n]*100:7.1f}%" for n in names))
print("-" * (w + 8 * len(names)))
for rig, desc, _ in rows:
    print(f"  {rig:<17} = {desc}")

print("\n" + "=" * 74)
print("SIMULASI BANKROLL (1 contoh per skenario)")
print("=" * 74)
for rig, strength, desc in SCENARIOS:
    rd = simulate(N_ROUNDS, rig, strength, seed=777)
    res = bankroll_monte_carlo(rd, p_house_win=0.5, payout=PAYOUT,
                               payout_mode=MODE, n_sims=8000, seed=1)
    tag = "CURIGA" if res.p_value < 0.05 else "wajar "
    print(f"[{tag}] {rig:<16} persentil {res.extra['percentile']*100:6.2f}  "
          f"P&L {res.extra['observed']:+10,.0f}  (jujur: {res.extra['sim_mean']:+,.0f} "
          f"+- {res.extra['sim_sd']:,.0f})")
