"""Laporan audit lengkap dalam bentuk teks."""
from __future__ import annotations

import numpy as np

from .forensics import (Round, bias_vs_stake, per_player_anomaly,
                        temporal_drift, bankroll_monte_carlo, rounds_needed)
from .stats_core import TestResult, run_battery, apply_fdr

BAR = "=" * 78
SUB = "-" * 78


def _sec(title: str) -> str:
    return f"\n{BAR}\n{title}\n{BAR}"


def audit(rounds: list[Round], k: int, p_house_win: float | None = None,
          payout: float | None = None, payout_mode: str = "total",
          alpha: float = 0.05) -> str:
    out = [r.outcome for r in rounds]
    n = len(out)
    L = [BAR, f"LAPORAN AUDIT RNG   |   {n} ronde   |   {k} kemungkinan hasil", BAR]

    if n == 0:
        return "\n".join(L + ["Tidak ada data."])

    # ---- kelayakan data -------------------------------------------------
    L.append(_sec("A. APAKAH DATAMU CUKUP? (baca ini dulu)"))
    L.append(f"  Ronde terkumpul : {n:,}")
    for b in (0.50, 0.20, 0.10, 0.05):
        need = rounds_needed(k, b)
        ok = "CUKUP" if n >= need else f"KURANG (perlu {need:,})"
        L.append(f"  Deteksi bias {int(b*100):3d}% : butuh {need:>8,} ronde  ->  {ok}")
    L.append(SUB)
    L.append("  Kalau semua baris di atas 'KURANG', hasil 'wajar' di bawah TIDAK")
    L.append("  membuktikan RNG-nya jujur. Artinya cuma: datamu belum cukup bicara.")

    # ---- tes keacakan ---------------------------------------------------
    L.append(_sec("B. TES KEACAKAN DASAR (apakah angkanya terlihat acak?)"))
    battery = run_battery(out, k)
    for t in battery:
        L.append("  " + str(t))
        if t.detail:
            L.append(f"         -> {t.detail}")

    # ---- forensik bersyarat --------------------------------------------
    L.append(_sec("C. FORENSIK BERSYARAT (menangkap kecurangan yang pintar)"))
    have_ctx = any(r.house_won is not None for r in rounds)
    if not have_ctx:
        L.append("  DILEWATI: butuh kolom house_won / player_won.")
        L.append("  Ini bagian TERPENTING untuk kasusmu - tolong catat kolom itu.")
        forensic: list[TestResult] = []
    else:
        forensic = list(bias_vs_stake(rounds)) + list(per_player_anomaly(rounds)) \
                   + list(temporal_drift(rounds))
        apply_fdr(forensic, alpha)
        for t in forensic:
            L.append("  " + str(t))
            if t.detail:
                L.append(f"         -> {t.detail}")

    # ---- bankroll -------------------------------------------------------
    L.append(_sec("D. SIAL ATAU DICURANGI? (simulasi bankroll)"))
    mc = None
    if p_house_win is None or payout is None:
        L.append("  DILEWATI: butuh --p-house dan --payout (dari aturan mainmu).")
    else:
        mc = bankroll_monte_carlo(rounds, p_house_win, payout, payout_mode)
        L.append("  " + str(mc))
        L.append(f"         -> {mc.detail}")
        if np.isfinite(mc.p_value):
            pct = mc.extra.get("percentile", 0.5) * 100
            if pct < 1:
                L.append("         -> Hasilmu di bawah persentil 1. Kesialan murni sangat")
                L.append("            tidak masuk akal sebagai penjelasan tunggal.")
            elif pct < 5:
                L.append("         -> Hasilmu buruk tapi belum ekstrem. Curigai, jangan tuduh.")
            else:
                L.append("         -> Hasilmu masih di rentang wajar. Kalau terasa rugi,")
                L.append("            periksa ulang matematika aturan main (LANGKAH 0).")

    # ---- kesimpulan -----------------------------------------------------
    L.append(_sec("E. KESIMPULAN"))
    hits = [t for t in list(battery) + list(forensic) if t.suspicious]
    if mc is not None and mc.p_value < alpha:
        hits.append(mc)
    if not hits:
        L.append("  Tidak ada bukti statistik kecurangan pada data ini.")
        L.append("  CATATAN: 'tidak ada bukti' != 'terbukti bersih'. Cek bagian A.")
    else:
        L.append(f"  {len(hits)} sinyal menyala (sesudah koreksi multiple-testing):")
        for t in hits:
            p = t.p_adjusted if t.p_adjusted is not None else t.p_value
            L.append(f"    * {t.name}  (p={p:.2e})")
        L.append(SUB)
        L.append("  Langkah lanjut yang benar: JANGAN langsung menuduh. Kumpulkan data")
        L.append("  periode berikutnya dan cek apakah sinyal yang SAMA muncul lagi.")
        L.append("  Temuan yang berulang di data baru jauh lebih kuat daripada satu")
        L.append("  temuan di data lama - karena kamu tidak bisa 'memilih' hasil dua kali.")
    L.append(BAR)
    return "\n".join(L)
