"""
Analisis frekuensi dan transisi ("setelah angka X, biasanya keluar apa?").

Analisis jenis ini adalah yang PALING mudah menghasilkan pola palsu, karena
alasan yang sepenuhnya matematis:

  Roda punya 37 angka. Kalau sebuah angka muncul ~550 kali, penerusnya
  tersebar ke 37 kemungkinan, jadi rata-rata hanya ~15 pengamatan per sel.
  Dengan sampel sekecil itu, penerus terbanyak SELALU terlihat menonjol -
  sekitar 4-5% berbanding harapan 2,7% - walaupun datanya acak sempurna.

Karena itu modul ini tidak pernah melaporkan "angka X cenderung diikuti Y"
tanpa menyertakan pembandingnya: seberapa kuat pola yang muncul kalau
datanya memang acak. Kalibrasi itu dilakukan lewat uji permutasi.
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def frequency_table(spins, k: int = 37) -> dict:
    a = np.asarray(spins, dtype=np.int64)
    n = a.size
    obs = np.bincount(a, minlength=k)[:k]
    exp = n / k
    resid = (obs - exp) / np.sqrt(exp)
    chi2 = float(((obs - exp) ** 2 / exp).sum())
    return {"n": n, "observed": obs, "expected": exp, "resid": resid,
            "chi2": chi2, "p": float(stats.chi2.sf(chi2, k - 1))}


def transition_matrix(seq, k: int = 37) -> np.ndarray:
    a = np.asarray(seq, dtype=np.int64)
    m = np.zeros((k, k), dtype=np.int64)
    np.add.at(m, (a[:-1], a[1:]), 1)
    return m


def top_followers(mat: np.ndarray, value: int, top: int = 3):
    row = mat[value]
    tot = row.sum()
    if tot == 0:
        return tot, []
    idx = np.argsort(row)[::-1][:top]
    return tot, [(int(i), int(row[i]), row[i] / tot) for i in idx]


def permutation_null(seq, k: int = 37, n_perm: int = 2000, seed: int = 0):
    """
    Acak ulang urutan data (frekuensi tiap angka dipertahankan, urutannya
    dihancurkan), lalu catat sekuat apa "pola" terkuat yang muncul.

    Ini pembanding yang benar. Kalau pola pada data asli tidak melebihi
    pola pada data yang sudah diacak, maka tidak ada pola.
    """
    a = np.asarray(seq, dtype=np.int64).copy()
    rng = np.random.default_rng(seed)
    best_share = np.empty(n_perm)
    chi2s = np.empty(n_perm)
    for i in range(n_perm):
        rng.shuffle(a)
        m = transition_matrix(a, k)
        tot = m.sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.where(tot[:, None] > 0, m / np.maximum(tot, 1)[:, None], 0.0)
        best_share[i] = share.max()
        rows = tot > 0
        exp = np.outer(tot[rows], m.sum(0)) / max(m.sum(), 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            c = np.where(exp > 0, (m[rows] - exp) ** 2 / np.maximum(exp, 1e-9), 0.0)
        chi2s[i] = c.sum()
    return best_share, chi2s


def independence_test(mat: np.ndarray):
    """Chi-square: apakah angka sebelumnya mempengaruhi angka berikutnya?"""
    rows = mat.sum(1) > 0
    cols = mat.sum(0) > 0
    sub = mat[np.ix_(rows, cols)]
    if sub.shape[0] < 2 or sub.shape[1] < 2:
        return float("nan"), 1.0, 0
    chi2, p, dof, _ = stats.chi2_contingency(sub)
    return float(chi2), float(p), int(dof)
