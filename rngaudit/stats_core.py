"""
Bateri tes keacakan klasik.

Semua fungsi menerima urutan hasil (list/array integer 0..k-1) dan mengembalikan
TestResult. Tidak ada satupun tes di sini yang "membaca masa depan" - semuanya
hanya mengukur seberapa jauh data menyimpang dari model acak seragam.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy import stats


@dataclass
class TestResult:
    name: str
    statistic: float
    p_value: float
    n: int
    detail: str = ""
    # diisi belakangan oleh koreksi multiple-testing
    p_adjusted: float | None = None
    extra: dict = field(default_factory=dict)

    @property
    def suspicious(self) -> bool:
        """Pakai p yang sudah dikoreksi kalau ada; kalau belum, p mentah."""
        p = self.p_adjusted if self.p_adjusted is not None else self.p_value
        return p < 0.05

    def __str__(self) -> str:
        p = self.p_adjusted if self.p_adjusted is not None else self.p_value
        flag = "CURIGA" if self.suspicious else "wajar "
        return f"[{flag}] {self.name:38s} stat={self.statistic:10.4f}  p={p:.6f}  n={self.n}"


def _as_array(outcomes: Sequence[int]) -> np.ndarray:
    a = np.asarray(list(outcomes), dtype=np.int64)
    if a.ndim != 1:
        raise ValueError("outcomes harus urutan 1 dimensi")
    return a


# --------------------------------------------------------------------------
# 1. FREQUENCY TEST (chi-square goodness of fit)
#    Pertanyaan: apakah setiap angka muncul sesering yang seharusnya?
#    Menangkap: bandar/pemain menggeser probabilitas satu atau beberapa angka.
# --------------------------------------------------------------------------
def frequency_test(outcomes: Sequence[int], k: int) -> TestResult:
    a = _as_array(outcomes)
    n = a.size
    observed = np.bincount(a, minlength=k)[:k]
    expected = np.full(k, n / k)

    # Aturan praktis: chi-square butuh expected >= 5 per kategori.
    warn = ""
    if n / k < 5:
        warn = (f" [PERINGATAN: rata-rata expected {n/k:.2f} < 5, "
                f"chi-square tidak akurat. Butuh minimal {5*k} ronde.]")

    chi2 = float(((observed - expected) ** 2 / expected).sum())
    dof = k - 1
    p = float(stats.chi2.sf(chi2, dof))

    dev = (observed - expected) / np.sqrt(expected)  # standardized residual
    worst = int(np.argmax(np.abs(dev)))
    detail = (f"angka paling menyimpang = {worst} "
              f"(muncul {observed[worst]}x, harusnya ~{expected[worst]:.1f}, "
              f"z={dev[worst]:+.2f}){warn}")

    return TestResult("Frequency (chi-square)", chi2, p, n, detail,
                      extra={"observed": observed.tolist(),
                             "expected": expected.tolist(),
                             "residuals": dev.tolist()})


# --------------------------------------------------------------------------
# 2. ENTROPY
#    Pertanyaan: berapa bit informasi per hasil? RNG jujur = log2(k) bit.
#    Menangkap: distribusi yang timpang (versi 'ringkasan' dari frequency test).
# --------------------------------------------------------------------------
def entropy_test(outcomes: Sequence[int], k: int) -> TestResult:
    a = _as_array(outcomes)
    n = a.size
    counts = np.bincount(a, minlength=k)[:k]
    probs = counts / n
    nz = probs[probs > 0]
    h = float(-(nz * np.log2(nz)).sum())
    h_max = float(np.log2(k))

    # 2*n*ln(2)*(Hmax - H) ~ chi2(k-1) -- ini G-test / likelihood ratio.
    g = 2 * n * np.log(2) * (h_max - h)
    p = float(stats.chi2.sf(g, k - 1))
    detail = f"entropi {h:.4f} bit dari maksimum {h_max:.4f} bit ({h/h_max*100:.2f}% acak sempurna)"
    return TestResult("Entropy (G-test)", g, p, n, detail,
                      extra={"entropy": h, "entropy_max": h_max})


# --------------------------------------------------------------------------
# 3. RUNS TEST (Wald-Wolfowitz)
#    Pertanyaan: apakah panjang 'streak' masuk akal?
#    Menangkap: RNG yang terlalu 'lengket' (beruntun panjang) atau terlalu
#    'rajin gantian' (zigzag). Manusia yang memalsukan angka hampir selalu
#    bikin terlalu sedikit streak panjang - ini tes pembunuh untuk angka
#    yang diketik manusia.
# --------------------------------------------------------------------------
def runs_test(outcomes: Sequence[int], k: int) -> TestResult:
    a = _as_array(outcomes).astype(float)
    median = np.median(np.arange(k))
    mask = a != median          # buang yang persis di median (aturan baku)
    b = a[mask] > median
    n = b.size
    if n < 20:
        return TestResult("Runs test (Wald-Wolfowitz)", float("nan"), 1.0, n,
                          "data terlalu sedikit (<20) untuk runs test")

    n1 = int(b.sum())
    n2 = n - n1
    if n1 == 0 or n2 == 0:
        return TestResult("Runs test (Wald-Wolfowitz)", float("nan"), 1.0, n,
                          "semua hasil di satu sisi median")

    runs = int(1 + np.count_nonzero(b[1:] != b[:-1]))
    exp_runs = 2.0 * n1 * n2 / n + 1.0
    var_runs = (2.0 * n1 * n2 * (2.0 * n1 * n2 - n)) / (n * n * (n - 1.0))
    z = (runs - exp_runs) / np.sqrt(var_runs)
    p = float(2 * stats.norm.sf(abs(z)))

    arah = "terlalu sedikit streak (zigzag/dibuat-buat)" if z < 0 else "terlalu banyak streak (lengket)"
    detail = (f"{runs} streak, ekspektasi {exp_runs:.1f} -> "
              f"{arah if abs(z) > 1.5 else 'normal'}")
    return TestResult("Runs test (Wald-Wolfowitz)", float(z), p, n, detail,
                      extra={"runs": runs, "expected_runs": exp_runs})


# --------------------------------------------------------------------------
# 4. AUTOCORRELATION
#    Pertanyaan: apakah hasil ronde ke-i memberi petunjuk tentang ronde ke-(i+lag)?
#    Menangkap: LCG murahan, seed yang di-reuse, atau bot yang pakai
#    Math.random() dengan periode pendek.
#    INI satu-satunya tes di sini yang, kalau positif, benar-benar berarti
#    "polanya bisa diprediksi".
# --------------------------------------------------------------------------
def autocorrelation_test(outcomes: Sequence[int], max_lag: int = 10) -> TestResult:
    a = _as_array(outcomes).astype(float)
    n = a.size
    max_lag = min(max_lag, n // 4)
    if max_lag < 1:
        return TestResult("Autocorrelation (Ljung-Box)", float("nan"), 1.0, n,
                          "data terlalu sedikit")

    a = a - a.mean()
    denom = float((a * a).sum())
    if denom == 0:
        return TestResult("Autocorrelation (Ljung-Box)", float("nan"), 1.0, n,
                          "semua hasil identik")

    rhos = []
    for lag in range(1, max_lag + 1):
        rhos.append(float((a[lag:] * a[:-lag]).sum() / denom))
    rhos = np.array(rhos)

    # Ljung-Box: gabungkan semua lag jadi satu statistik.
    lags = np.arange(1, max_lag + 1)
    q = n * (n + 2) * np.sum(rhos ** 2 / (n - lags))
    p = float(stats.chi2.sf(q, max_lag))

    worst = int(np.argmax(np.abs(rhos)))
    detail = (f"korelasi terkuat di lag {worst+1}: rho={rhos[worst]:+.4f} "
              f"(batas kebisingan +-{1.96/np.sqrt(n):.4f})")
    return TestResult("Autocorrelation (Ljung-Box)", float(q), p, n, detail,
                      extra={"rhos": rhos.tolist(), "max_lag": max_lag})


# --------------------------------------------------------------------------
# 5. SERIAL / TRANSITION TEST
#    Pertanyaan: setelah muncul angka X, apakah angka berikutnya masih seragam?
#    Menangkap: aturan tersembunyi macam "tidak boleh sama dua kali berturut"
#    atau "setelah pemain menang, ronde berikut dipaksa kalah".
# --------------------------------------------------------------------------
def transition_test(outcomes: Sequence[int], k: int) -> TestResult:
    a = _as_array(outcomes)
    n = a.size
    if n < 2:
        return TestResult("Transition (Markov order-1)", float("nan"), 1.0, n, "data kurang")

    mat = np.zeros((k, k), dtype=np.int64)
    np.add.at(mat, (a[:-1], a[1:]), 1)

    # buang baris/kolom kosong supaya chi2_contingency tidak error
    rows = mat.sum(1) > 0
    cols = mat.sum(0) > 0
    sub = mat[np.ix_(rows, cols)]
    if sub.shape[0] < 2 or sub.shape[1] < 2:
        return TestResult("Transition (Markov order-1)", float("nan"), 1.0, n,
                          "variasi hasil terlalu sedikit")

    warn = ""
    if (n - 1) / (k * k) < 5:
        warn = (f" [PERINGATAN: rata-rata {(n-1)/(k*k):.2f} sampel per sel < 5. "
                f"Butuh ~{5*k*k} ronde agar tes ini bertenaga.]")

    chi2, p, dof, _ = stats.chi2_contingency(sub)
    return TestResult("Transition (Markov order-1)", float(chi2), float(p), n,
                      f"dof={dof}, menguji apakah hasil sebelumnya mempengaruhi hasil berikutnya{warn}",
                      extra={"matrix": mat.tolist()})


# --------------------------------------------------------------------------
# 6. GAP TEST
#    Pertanyaan: jarak antar kemunculan ulang sebuah angka mengikuti
#    distribusi geometrik?
#    Menangkap: RNG "tanpa pengulangan" atau yang menahan angka tertentu.
# --------------------------------------------------------------------------
def gap_test(outcomes: Sequence[int], k: int, value: int | None = None) -> TestResult:
    a = _as_array(outcomes)
    n = a.size
    if value is None:                      # pilih angka yang paling sering muncul
        value = int(np.argmax(np.bincount(a, minlength=k)[:k]))

    idx = np.flatnonzero(a == value)
    if idx.size < 12:
        return TestResult(f"Gap test (angka {value})", float("nan"), 1.0, n,
                          f"angka {value} cuma muncul {idx.size}x, butuh >=12")

    gaps = np.diff(idx) - 1                # 0 = muncul lagi persis berikutnya
    p_hit = 1.0 / k

    # bin gap jadi 0,1,2,...,m-1, >=m  dengan m dipilih agar expected >= 5
    m = 1
    while m < 30 and gaps.size * p_hit * (1 - p_hit) ** m >= 5:
        m += 1
    obs = np.array([np.count_nonzero(gaps == g) for g in range(m)] +
                   [np.count_nonzero(gaps >= m)], dtype=float)
    exp = np.array([gaps.size * p_hit * (1 - p_hit) ** g for g in range(m)] +
                   [gaps.size * (1 - p_hit) ** m], dtype=float)

    keep = exp >= 5
    if keep.sum() < 2:
        return TestResult(f"Gap test (angka {value})", float("nan"), 1.0, n,
                          "sampel kurang untuk gap test")
    obs, exp = obs[keep], exp[keep]
    exp = exp * (obs.sum() / exp.sum())    # normalisasi ulang setelah membuang bin
    chi2 = float(((obs - exp) ** 2 / exp).sum())
    p = float(stats.chi2.sf(chi2, keep.sum() - 1))
    return TestResult(f"Gap test (angka {value})", chi2, p, n,
                      f"{gaps.size} jarak dianalisis, rata-rata {gaps.mean():.2f} (harusnya ~{k-1})")


# --------------------------------------------------------------------------
# Koreksi multiple testing (Benjamini-Hochberg FDR)
#
# KENAPA INI WAJIB: kalau kita jalankan 20 tes pada RNG yang JUJUR, secara
# rata-rata 1 tes akan menunjukkan p < 0.05 murni karena kebetulan. Tanpa
# koreksi, kita akan menuduh orang curang berdasarkan kebisingan.
# --------------------------------------------------------------------------
def apply_fdr(results: list[TestResult], alpha: float = 0.05) -> list[TestResult]:
    valid = [r for r in results if np.isfinite(r.p_value)]
    if not valid:
        return results
    ps = np.array([r.p_value for r in valid])
    order = np.argsort(ps)
    m = ps.size
    adj = np.empty(m)
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        prev = min(prev, ps[i] * m / (rank + 1))
        adj[i] = min(prev, 1.0)
    for r, a in zip(valid, adj):
        r.p_adjusted = float(a)
    return results


def run_battery(outcomes: Sequence[int], k: int, max_lag: int = 10) -> list[TestResult]:
    """Jalankan semua tes keacakan dasar + koreksi FDR."""
    res = [
        frequency_test(outcomes, k),
        entropy_test(outcomes, k),
        runs_test(outcomes, k),
        autocorrelation_test(outcomes, max_lag),
        transition_test(outcomes, k),
        gap_test(outcomes, k),
    ]
    return apply_fdr(res)
