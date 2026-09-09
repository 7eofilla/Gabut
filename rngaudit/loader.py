"""Pembaca data. Sengaja longgar soal nama kolom, karena catatan orang beda-beda."""
from __future__ import annotations

import csv
from pathlib import Path

from .forensics import Round

ALIASES = {
    "outcome": {"outcome", "hasil", "angka", "result", "roll", "number", "nomor"},
    "player":  {"player", "pemain", "user", "nama", "name", "penantang"},
    "stake":   {"stake", "bet", "taruhan", "nominal", "amount", "wager", "modal"},
    "house_won": {"house_won", "bandar_menang", "menang_bandar", "host_won", "win_host"},
    "player_won": {"player_won", "pemain_menang", "menang", "win", "menang_pemain"},
    "profit":  {"profit", "pnl", "untung", "laba", "net"},
    "ts":      {"ts", "time", "timestamp", "waktu", "tanggal", "date"},
}
TRUE = {"1", "true", "t", "yes", "y", "ya", "menang", "win", "w"}
FALSE = {"0", "false", "f", "no", "n", "tidak", "kalah", "lose", "l"}


def _resolve(header: list[str]) -> dict[str, str]:
    low = {h.strip().lower(): h for h in header}
    found = {}
    for canon, names in ALIASES.items():
        for n in names:
            if n in low:
                found[canon] = low[n]
                break
    return found


def _bool(v: str) -> bool | None:
    s = str(v).strip().lower()
    if s in TRUE:
        return True
    if s in FALSE:
        return False
    return None


def load_csv(path: str | Path) -> list[Round]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rdr = csv.DictReader(fh)
        if not rdr.fieldnames:
            raise ValueError("CSV kosong / tanpa header")
        col = _resolve(list(rdr.fieldnames))
        if "outcome" not in col:
            raise ValueError(
                f"kolom hasil tidak ditemukan. header terbaca: {rdr.fieldnames}\n"
                f"nama yang dikenali: {sorted(ALIASES['outcome'])}")

        rounds: list[Round] = []
        for i, row in enumerate(rdr):
            raw = str(row[col["outcome"]]).strip()
            if raw == "":
                continue
            try:
                out = int(float(raw))
            except ValueError:
                continue

            hw = None
            if "house_won" in col:
                hw = _bool(row[col["house_won"]])
            elif "player_won" in col:
                pw = _bool(row[col["player_won"]])
                hw = (not pw) if pw is not None else None

            def num(key, default=0.0):
                if key not in col:
                    return default
                try:
                    return float(str(row[col[key]]).replace(",", "").strip() or default)
                except ValueError:
                    return default

            stake = num("stake")
            profit = num("profit")
            rounds.append(Round(idx=i, outcome=out,
                                player=str(row.get(col.get("player", ""), "")).strip(),
                                stake=stake, house_won=hw, profit=profit,
                                ts=num("ts", None) if "ts" in col else None))
    return rounds


TEMPLATE = """\
# Template log ronde. Satu baris = satu ronde. Hapus baris komentar ini.
# outcome  : hasil RNG mentah. WAJIB. Pakai 0-based (dadu 1-6 -> tulis 0-5).
# player   : siapa yang bertaruh. Penting untuk mendeteksi kolusi.
# stake    : nominal taruhan. Penting untuk mendeteksi curang-saat-taruhan-besar.
# house_won: 1 kalau BANDAR menang, 0 kalau pemain menang.
# profit   : untung/rugi BANDAR ronde ini (+ untung, - rugi).
# ts       : waktu (unix / urutan). Untuk mendeteksi "mulai kapan jadi aneh".
outcome,player,stake,house_won,profit,ts
"""


def write_template(path: str | Path) -> Path:
    p = Path(path)
    p.write_text(TEMPLATE, encoding="utf-8")
    return p
