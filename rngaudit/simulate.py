"""
Simulator kasino: bikin data dengan kecurangan yang SUDAH KITA KETAHUI,
supaya kita bisa mengukur apakah detektornya benar-benar bekerja.

Ini prinsip dasar: jangan pernah percaya alat forensik yang belum pernah
diuji pada kasus yang jawabannya sudah diketahui.

Permainan contoh: dadu 6 sisi. Pemain menebak BESAR (4,5,6) atau KECIL (1,2,3).
Payout 1.95x total -> house edge 2.5%.  (outcome disimpan 0..5)
"""
from __future__ import annotations

import numpy as np

from .forensics import Round

K = 6
PAYOUT = 1.95
MODE = "total"
MULT = PAYOUT                      # mode "total"
PLAYERS = ["andi", "budi", "citra", "dewi", "eko", "fajar", "gita", "hadi"]


def simulate(n: int = 1500, rig: str = "fair", strength: float = 0.15,
             seed: int = 0, players: list[str] | None = None) -> list[Round]:
    """
    rig:
      fair            - jujur total (kelompok kontrol)
      freq_bias       - satu angka lebih sering muncul (kecurangan kasar)
      stake_targeted  - jujur, KECUALI saat taruhan besar (kecurangan cerdas)
      player_targeted - jujur, KECUALI untuk satu pemain (kolusi)
      streaky         - hasil cenderung mengulang hasil sebelumnya (RNG rusak)
      late_rig        - jujur di paruh awal, dicurangi di paruh akhir
    """
    rng = np.random.default_rng(seed)
    players = players or PLAYERS
    rounds: list[Round] = []

    # nominal taruhan: lognormal -> banyak taruhan kecil, sedikit taruhan besar
    stakes = np.round(np.exp(rng.normal(4.0, 0.9, n))).clip(5, 5000)
    big = np.quantile(stakes, 0.75)
    who = rng.choice(players, n)
    guess_big = rng.random(n) < 0.5          # pemain menebak BESAR?

    probs = np.full(K, 1.0 / K)
    if rig == "freq_bias":
        probs = probs.copy()
        probs[0] *= (1 + strength)
        probs /= probs.sum()

    prev = int(rng.integers(0, K))
    for i in range(n):
        # --- tentukan hasil dadu ---
        if rig == "streaky" and rng.random() < strength:
            out = prev
        else:
            out = int(rng.choice(K, p=probs))

        player_wins = (out >= 3) == guess_big[i]

        # --- terapkan kecurangan bersyarat: paksa pemain menang ---
        force = 0.0
        if rig == "stake_targeted" and stakes[i] >= big:
            force = strength
        elif rig == "player_targeted" and who[i] == players[0]:
            force = strength
        elif rig == "late_rig" and i > n // 2 and stakes[i] >= big:
            force = strength

        if force and not player_wins and rng.random() < force:
            # geser hasil ke sisi yang bikin pemain menang (tetap terlihat normal)
            out = int(rng.integers(3, 6)) if guess_big[i] else int(rng.integers(0, 3))
            player_wins = True

        house_won = not player_wins
        profit = float(stakes[i]) if house_won else -float(stakes[i]) * (MULT - 1.0)
        rounds.append(Round(idx=i, outcome=out, player=str(who[i]),
                            stake=float(stakes[i]), house_won=house_won,
                            profit=profit, ts=float(i)))
        prev = out
    return rounds
