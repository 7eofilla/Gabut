"""
Modul forensik: menjawab pertanyaan yang TIDAK bisa dijawab tes keacakan biasa.

Pemikiran kuncinya begini. Kalau seseorang mau mencurangi bandar tanpa
ketahuan, dia TIDAK akan menggeser distribusi angka secara keseluruhan -
itu terlalu gampang ketahuan oleh chi-square. Yang dia lakukan adalah
mencurangi SECARA BERSYARAT:

  * hanya saat taruhannya besar          -> bias_vs_stake()
  * hanya untuk pemain tertentu          -> per_player_anomaly()
  * hanya mulai tanggal tertentu         -> temporal_drift()

Distribusi angka gabungannya tetap terlihat sempurna. Chi-square lewat.
Tes di modul inilah yang menangkapnya.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy import stats, optimize

from .stats_core import TestResult, apply_fdr


@dataclass
class Round:
    """Satu ronde permainan, dari sudut pandang BANDAR (host)."""
    idx: int
    outcome: int                   # hasil RNG, 0..k-1
    player: str = ""
    stake: float = 0.0             # nominal taruhan pemain
    house_won: bool | None = None  # True kalau BANDAR menang
    profit: float = 0.0            # profit BANDAR ronde ini (+ untung, - rugi)
    ts: float | None = None        # unix timestamp, opsional


# ==========================================================================
# 0. MATEMATIKA ATURAN MAIN  -- kerjakan ini SEBELUM menuduh RNG curang
# ==========================================================================
@dataclass
class BetSpec:
    """
    Satu jenis taruhan.

    payout_mode:
      "total"  -> pemain menang menerima stake * payout (SUDAH termasuk modal).
                  Contoh: taruh 100, payout 2.0, menang -> terima 200 (untung 100).
      "profit" -> pemain menang menerima modal + stake * payout.
                  Contoh: taruh 100, payout 1.0, menang -> terima 200 (untung 100).

    Salah pilih mode di sini = salah hitung house edge = rugi tanpa sadar.
    Ini penyebab bandar rugi nomor SATU, jauh di atas RNG curang.
    """
    name: str
    p_win: float                   # peluang PEMAIN menang
    payout: float
    payout_mode: str = "total"

    def house_edge(self) -> float:
        """Ekspektasi keuntungan BANDAR per 1 satuan taruhan. Positif = bandar untung."""
        mult = self.payout if self.payout_mode == "total" else 1.0 + self.payout
        return 1.0 - self.p_win * mult

    def breakeven_payout(self) -> float:
        """Payout maksimum yang masih membuat bandar impas."""
        be = 1.0 / self.p_win
        return be if self.payout_mode == "total" else be - 1.0


def analyse_rules(bets: Sequence[BetSpec]) -> str:
    """Laporan teks: apakah aturan mainmu memang menguntungkan bandar?"""
    lines = ["=" * 74, "LANGKAH 0 - AUDIT ATURAN MAIN (sebelum menyalahkan RNG)", "=" * 74]
    worst = None
    for b in bets:
        e = b.house_edge()
        status = "BANDAR UNTUNG" if e > 0 else ("IMPAS" if abs(e) < 1e-9 else "BANDAR RUGI  <-- MASALAH")
        lines.append(
            f"  {b.name:24s} p_menang={b.p_win:7.4f}  payout={b.payout:6.3f} ({b.payout_mode})\n"
            f"  {'':24s} house edge = {e*100:+7.3f}%   {status}\n"
            f"  {'':24s} payout impas = {b.breakeven_payout():.4f}"
        )
        if worst is None or e < worst:
            worst = e
    lines.append("-" * 74)
    if worst is not None and worst <= 0:
        lines.append("KESIMPULAN: ada taruhan dengan edge <= 0. Kamu rugi karena MATEMATIKA,")
        lines.append("            bukan karena dicurangi. Perbaiki payout dulu.")
    else:
        lines.append(f"KESIMPULAN: semua taruhan menguntungkan bandar (edge terkecil {worst*100:+.3f}%).")
        lines.append("            Kalau tetap rugi, lanjut ke tes berikutnya.")
    return "\n".join(lines)


# ==========================================================================
# 1. BIAS BERSYARAT TARUHAN  -- "curang cuma pas taruhan gede"
# ==========================================================================
def bias_vs_stake(rounds: Sequence[Round], n_bins: int = 4) -> list[TestResult]:
    rs = [r for r in rounds if r.house_won is not None and r.stake > 0]
    n = len(rs)
    if n < 40:
        return [TestResult("Bias vs besar taruhan", float("nan"), 1.0, n,
                           "butuh >=40 ronde ber-taruhan")]

    stakes = np.array([r.stake for r in rs], float)
    won = np.array([r.house_won for r in rs], bool)

    # bin berdasarkan kuantil supaya tiap bin isinya seimbang
    edges = np.unique(np.quantile(stakes, np.linspace(0, 1, n_bins + 1)))
    if edges.size < 3:
        return [TestResult("Bias vs besar taruhan", float("nan"), 1.0, n,
                           "variasi nominal taruhan terlalu kecil untuk diuji")]
    bin_id = np.clip(np.digitize(stakes, edges[1:-1]), 0, edges.size - 2)

    K = int(bin_id.max()) + 1
    n_i = np.array([np.count_nonzero(bin_id == i) for i in range(K)], float)
    x_i = np.array([np.count_nonzero(won & (bin_id == i)) for i in range(K)], float)
    t_i = np.array([stakes[bin_id == i].mean() for i in range(K)], float)

    rate = x_i / np.maximum(n_i, 1)
    tbl = "  ".join(f"[{t_i[i]:.0f}]{rate[i]*100:.1f}%" for i in range(K))

    out: list[TestResult] = []

    # (a) homogenitas: apakah win-rate bandar sama di semua strata taruhan?
    table = np.vstack([x_i, n_i - x_i])
    keep = table.sum(0) > 0
    if keep.sum() >= 2 and table[:, keep].sum(1).min() > 0:
        chi2, p, dof, _ = stats.chi2_contingency(table[:, keep])
        out.append(TestResult("Bias vs besar taruhan (homogenitas)", float(chi2), float(p), n,
                              f"win-rate bandar per strata: {tbl}",
                              extra={"rates": rate.tolist(), "bin_mean_stake": t_i.tolist()}))

    # (b) tren monoton (Cochran-Armitage): makin besar taruhan, makin sering bandar kalah?
    N = n_i.sum()
    p_hat = x_i.sum() / N
    z = np.log1p(t_i)                        # skor log supaya tidak didominasi outlier
    T = float((z * (x_i - n_i * p_hat)).sum())
    var = p_hat * (1 - p_hat) * float((n_i * z * z).sum() - (n_i * z).sum() ** 2 / N)
    if var > 0:
        zstat = T / np.sqrt(var)
        pt = float(2 * stats.norm.sf(abs(zstat)))
        arah = ("bandar makin SERING KALAH saat taruhan besar  <-- pola khas kecurangan"
                if zstat < 0 else "bandar makin sering menang saat taruhan besar")
        out.append(TestResult("Bias vs besar taruhan (tren Cochran-Armitage)",
                              float(zstat), pt, n,
                              arah if abs(zstat) > 1.5 else "tidak ada tren berarti"))
    return out


# ==========================================================================
# 2. ANOMALI PER PEMAIN  -- "ada satu orang yang menangnya kelewat sering"
# ==========================================================================
def per_player_anomaly(rounds: Sequence[Round], p_player_win: float | None = None,
                       min_rounds: int = 25) -> list[TestResult]:
    rs = [r for r in rounds if r.house_won is not None and r.player]
    if not rs:
        return [TestResult("Anomali per pemain", float("nan"), 1.0, 0, "tidak ada kolom pemain")]

    if p_player_win is None:                 # pakai baseline global kalau tidak diberi
        p_player_win = 1.0 - np.mean([r.house_won for r in rs])

    by: dict[str, list[Round]] = {}
    for r in rs:
        by.setdefault(r.player, []).append(r)

    out: list[TestResult] = []
    for name, lst in sorted(by.items()):
        if len(lst) < min_rounds:
            continue
        nn = len(lst)
        wins = sum(1 for r in lst if not r.house_won)      # kemenangan PEMAIN
        # uji satu sisi: apakah pemain ini menang LEBIH sering dari seharusnya?
        p = float(stats.binomtest(wins, nn, p_player_win, alternative="greater").pvalue)
        pnl = sum(r.profit for r in lst)
        out.append(TestResult(f"Pemain '{name}'", float(wins / nn), p, nn,
                              f"menang {wins}/{nn} = {wins/nn*100:.1f}% "
                              f"(ekspektasi {p_player_win*100:.1f}%), P&L bandar {pnl:+.0f}",
                              extra={"player": name, "win_rate": wins / nn, "house_pnl": pnl}))
    if not out:
        return [TestResult("Anomali per pemain", float("nan"), 1.0, len(rs),
                           f"tidak ada pemain dengan >= {min_rounds} ronde")]
    return apply_fdr(out)      # WAJIB: banyak pemain = banyak tes = banyak alarm palsu


# ==========================================================================
# 3. DRIFT WAKTU  -- "dulu normal, mulai kapan jadi aneh?"
# ==========================================================================
def temporal_drift(rounds: Sequence[Round], n_chunks: int = 6) -> list[TestResult]:
    rs = [r for r in rounds if r.house_won is not None]
    n = len(rs)
    if n < 60:
        return [TestResult("Drift waktu", float("nan"), 1.0, n, "butuh >=60 ronde")]

    won = np.array([r.house_won for r in rs], bool)
    chunks = np.array_split(np.arange(n), n_chunks)
    x = np.array([won[c].sum() for c in chunks], float)
    nn = np.array([len(c) for c in chunks], float)

    table = np.vstack([x, nn - x])
    keep = table.sum(0) > 0
    out: list[TestResult] = []
    if keep.sum() >= 2 and table[:, keep].sum(1).min() > 0:
        chi2, p, dof, _ = stats.chi2_contingency(table[:, keep])
        rates = "  ".join(f"P{i+1}:{x[i]/nn[i]*100:.1f}%" for i in range(len(x)))
        out.append(TestResult("Drift waktu (homogenitas periode)", float(chi2), float(p), n,
                              f"win-rate bandar per periode -> {rates}"))

    # CUSUM: cari titik perubahan paling tajam
    p_hat = won.mean()
    cum = np.cumsum(won - p_hat)
    cp = int(np.argmax(np.abs(cum)))
    # statistik tipe Brownian bridge -> uji Kolmogorov
    denom = np.sqrt(n * p_hat * (1 - p_hat))
    d = float(np.abs(cum).max() / denom) if denom > 0 else 0.0
    p_cp = float(stats.kstwobign.sf(d)) if d > 0 else 1.0
    out.append(TestResult("Titik perubahan (CUSUM)", d, p_cp, n,
                          f"penyimpangan terkuat di sekitar ronde ke-{cp} "
                          f"({cp/n*100:.0f}% perjalanan data)",
                          extra={"changepoint": cp, "cusum": cum.tolist()}))
    return out


# ==========================================================================
# 4. SIMULASI BANKROLL  -- "gw sial, atau gw dicurangi?"
#    Ini tes yang PALING LANGSUNG menjawab pertanyaanmu.
# ==========================================================================
def bankroll_monte_carlo(rounds: Sequence[Round], p_house_win: float,
                         payout: float, payout_mode: str = "total",
                         n_sims: int = 20000, seed: int = 0) -> TestResult:
    """
    Ambil urutan nominal taruhan yang BENAR-BENAR terjadi, lalu mainkan ulang
    ribuan kali dengan RNG yang dijamin jujur. Hasilnya: distribusi P&L yang
    "seharusnya". Kalau P&L asli kamu jatuh di ekor bawah yang ekstrem,
    kesialan murni jadi penjelasan yang sangat tidak masuk akal.
    """
    rs = [r for r in rounds if r.stake > 0]
    n = len(rs)
    if n < 30:
        return TestResult("Simulasi bankroll (Monte Carlo)", float("nan"), 1.0, n,
                          "butuh >=30 ronde")

    stakes = np.array([r.stake for r in rs], float)
    observed = float(sum(r.profit for r in rs))
    mult = payout if payout_mode == "total" else 1.0 + payout

    rng = np.random.default_rng(seed)
    # bandar menang -> +stake ; bandar kalah -> -(stake*mult - stake)
    win_mx = rng.random((n_sims, n)) < p_house_win
    pnl = np.where(win_mx, stakes, -stakes * (mult - 1.0)).sum(axis=1)

    pct = float((pnl <= observed).mean())
    p = float(max(pct, 1.0 / n_sims))           # uji satu sisi: separah apa hasilku?
    detail = (f"P&L asli {observed:+,.0f} | simulasi jujur: rata-rata {pnl.mean():+,.0f}, "
              f"sd {pnl.std():,.0f}, rentang wajar 5-95% = [{np.quantile(pnl,0.05):+,.0f}, "
              f"{np.quantile(pnl,0.95):+,.0f}] | posisi hasilmu = persentil {pct*100:.2f}")
    return TestResult("Simulasi bankroll (Monte Carlo)", float(observed), p, n, detail,
                      extra={"observed": observed, "sim_mean": float(pnl.mean()),
                             "sim_sd": float(pnl.std()), "percentile": pct,
                             "q05": float(np.quantile(pnl, 0.05)),
                             "q95": float(np.quantile(pnl, 0.95))})


# ==========================================================================
# 5. ANALISIS DAYA (POWER)  -- "berapa ronde yang harus gw kumpulin?"
# ==========================================================================
def rounds_needed(k: int, rel_bias: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """
    Berapa ronde dibutuhkan agar chi-square punya peluang `power` mendeteksi
    kecurangan sebesar `rel_bias` (mis. 0.10 = satu angka muncul 10% lebih
    sering dari seharusnya)?

    Ini fungsi terpenting untuk EKSPEKTASI. Kalau kamu cuma punya 80 ronde,
    kecurangan kecil MUSTAHIL terdeteksi - dan hasil "wajar" tidak berarti bersih.
    """
    df = k - 1
    p0 = 1.0 / k
    # geser satu kategori naik sebesar rel_bias, sisanya turun merata
    p1 = np.full(k, p0)
    p1[0] = p0 * (1 + rel_bias)
    p1[1:] -= (p1[0] - p0) / (k - 1)
    w2 = float((((p1 - p0) ** 2) / p0).sum())          # Cohen's w kuadrat
    if w2 <= 0:
        return 0
    crit = stats.chi2.isf(alpha, df)
    f = lambda lam: stats.ncx2.sf(crit, df, lam) - power
    lam = optimize.brentq(f, 1e-9, 1e7)
    return int(np.ceil(lam / w2))
