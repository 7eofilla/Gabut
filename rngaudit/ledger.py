"""
Rekonstruksi buku kas bandar dari export chat Omni_Bot.

Perbedaan penting dari pendekatan sebelumnya: taruhan dicocokkan dengan
hasilnya BERDASARKAN NAMA PEMAIN, bukan berdasarkan urutan kemunculan.

Alasannya empiris: 4,8% payout ternyata milik pemain yang BERBEDA dari
taruhan terakhir sebelumnya, karena beberapa pemain bertaruh berbarengan.
Pencocokan berbasis urutan diam-diam salah membebankan nominal itu.

Ditangani juga: pesan "GO ALL" diikuti baris "Bet diterima" pada bot versi
baru (tetapi tidak pada versi lama). Karena taruhan disimpan sebagai
nilai-tertunda per pemain dan bukan diakumulasi, penulisan ganda itu tidak
menyebabkan penghitungan ganda.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FEE_RATE = 0.03            # ditanggung PENGIRIM (diverifikasi pada 419 transfer)

RE_BET   = re.compile(r"✅ Bet @⁨([^⁩]*)⁩ \*([\d.,]+)\*")
RE_GOALL = re.compile(r"🚀 \*GO ALL!\* @⁨([^⁩]*)⁩ taruhan \*([\d.,]+) coin\*")
RE_HASIL = re.compile(r"📊 \*Hasil\*\n(?:R\d+: .*\n)+Hoster: (\d+)\nMultiplier total: ×(\d+)")
RE_AUTOW = re.compile(r"🚀 \*HOSTER AUTO-WIN!\*")
# penanda nama pemain yang muncul tepat setelah sebuah hasil
RE_WHO = re.compile(r"💀 @⁨([^⁩]*)⁩ kalah|🎉 @⁨([^⁩]*)⁩|🏆 \*PEMENANG: @⁨([^⁩]*)⁩|"
                    r"🎯 @⁨([^⁩]*)⁩ mau lanjut|rgo @⁨?([^⁩\n]*?)⁩?\n|┃ 👤 (?:Player: )?@⁨([^⁩]*)⁩")

_num = lambda s: float(s.replace(".", "").replace(",", ""))


@dataclass
class Settlement:
    player: str
    stake: float
    multiplier: int          # -1 = HOSTER AUTO-WIN
    payout: float
    house_pnl: float         # sudah termasuk fee transfer


def _who_after(txt: str, pos: int, window: int = 400) -> str | None:
    m = RE_WHO.search(txt, pos, pos + window)
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


def build(path: str | Path, fee: float = FEE_RATE) -> tuple[list[Settlement], dict]:
    txt = Path(path).read_text(encoding="utf-8", errors="replace")

    ev = sorted(
        [(m.start(), "bet", m.group(1), _num(m.group(2))) for m in RE_BET.finditer(txt)] +
        [(m.start(), "bet", m.group(1), _num(m.group(2))) for m in RE_GOALL.finditer(txt)] +
        [(m.end(), "hasil", None, int(m.group(2))) for m in RE_HASIL.finditer(txt)] +
        [(m.end(), "autowin", None, -1) for m in RE_AUTOW.finditer(txt)],
        key=lambda t: t[0])

    pending: dict[str, float] = {}        # nominal taruhan berjalan per pemain
    out: list[Settlement] = []
    stats = {"res": 0, "no_name": 0, "no_stake": 0}

    for pos, kind, who, val in ev:
        if kind == "bet":
            pending[who] = val            # menimpa, bukan menambah -> GO ALL aman
            continue

        if kind == "hasil" and val == 2:  # RES: taruhan tetap berjalan
            stats["res"] += 1
            continue

        name = _who_after(txt, pos)
        if name is None:
            stats["no_name"] += 1
            continue
        stake = pending.pop(name, None)
        if stake is None:
            stats["no_stake"] += 1
            continue

        if kind == "autowin" or val == 0:
            out.append(Settlement(name, stake, val, 0.0, stake))
        else:
            pay = stake * val / 2
            # bandar mengirim payout, dan PENGIRIM menanggung fee
            out.append(Settlement(name, stake, val, pay, stake - pay - pay * fee))
    return out, stats


def summarise(rows: list[Settlement]) -> dict:
    turn = sum(r.stake for r in rows)
    pnl = sum(r.house_pnl for r in rows)
    pay = sum(r.payout for r in rows)
    nH = sum(1 for r in rows if r.payout == 0)
    return {"n": len(rows), "house_wins": nH, "player_wins": len(rows) - nH,
            "turnover": turn, "payouts": pay, "fee": pay * FEE_RATE,
            "pnl": pnl, "edge": pnl / turn if turn else 0.0,
            "win_rate": nH / len(rows) if rows else 0.0}
