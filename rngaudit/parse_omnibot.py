"""
Parser untuk export chat WhatsApp grup kasino yang dijalankan Omni_Bot
(game "LEME"/"LEWA" alias Gemspin).

Format blok hasil yang dikenali:

    DD/MM/YY HH.MM - Omni_Bot: 📊 *Hasil*
    R1: <angka> → <keterangan>
    R2: <angka> → <keterangan>
    Hoster: <angka>
    Multiplier total: ×<m>

Parser ini juga menarik nominal bet dan payout supaya arus uang bisa direkonstruksi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

RE_HASIL = re.compile(
    r"(?P<date>\d{2}/\d{2}/\d{2}) (?P<time>\d{2}\.\d{2}) - [^:\n]+: 📊 \*Hasil\*\n"
    r"(?P<rounds>(?:R\d+: .*\n)+)"
    r"Hoster: (?P<hoster>\d+)\n"
    r"Multiplier total: ×(?P<mult>\d+)"
)
RE_ROUND = re.compile(r"R(?P<i>\d+): (?P<n>\d+) → (?P<verdict>.*)")
RE_SCORE_CMP = re.compile(r"\((?P<a>\d+)\s*[<>=]\s*(?P<b>\d+)\)")
RE_SCORE_PAREN = re.compile(r"score (?P<s>\d+)\)")
RE_NORMWIN = re.compile(r"Normal win \((?P<a>\d+) > (?P<b>\d+)\)")
RE_BET = re.compile(r"✅ Bet @⁨(?P<who>[^⁩]*)⁩ \*(?P<amt>[\d.]+)\* (?P<game>\w+) diterima!")
RE_GOALL = re.compile(r"🚀 \*GO ALL!\* @⁨(?P<who>[^⁩]*)⁩ taruhan \*(?P<amt>[\d.]+) coin\*!\n(?P<game>\w+)")
RE_PAYOUT = re.compile(
    r"🏆 \*PEMENANG: @⁨(?P<who>[^⁩]*)⁩\* 🏆\n"
    r"💰 \*PAYOUT: (?P<payout>[\d.]+) COIN\*\n"
    r"🎲 Game: (?P<game>\w+)\n"
    r"📊 Bet awal: (?P<bet>[\d.]+)"
)


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", ""))


@dataclass
class Spin:
    """Satu putaran roda, dengan peran siapa yang memutar."""
    value: int
    role: str          # "player" | "hoster"
    score: int | None
    pos: int
    date: str
    time: str


@dataclass
class GameRound:
    pos: int
    date: str
    time: str
    player_spins: list[int] = field(default_factory=list)
    player_scores: list[int | None] = field(default_factory=list)
    verdicts: list[str] = field(default_factory=list)
    hoster_spin: int = -1
    hoster_score: int | None = None
    multiplier: int = 0
    bet: float | None = None
    payout: float | None = None
    who: str = ""
    game: str = ""


def _score_from_verdict(n: int, verdict: str) -> int | None:
    """Ambil skor pemain dari teks keterangan bot (bukan dari asumsi kita)."""
    m = RE_NORMWIN.search(verdict)
    if m:
        return int(m.group("a"))
    m = RE_SCORE_PAREN.search(verdict)
    if m:
        return int(m.group("s"))
    m = RE_SCORE_CMP.search(verdict)
    if m:
        return int(m.group("a"))
    return None


def _hoster_score_from_verdicts(verdicts: list[str]) -> int | None:
    for v in verdicts:
        m = RE_NORMWIN.search(v)
        if m:
            return int(m.group("b"))
        m = RE_SCORE_CMP.search(v)
        if m:
            return int(m.group("b"))
    return None


def parse(path: str | Path) -> tuple[list[GameRound], list[Spin]]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")

    bets = [(m.start(), m) for m in RE_BET.finditer(text)]
    goalls = [(m.start(), m) for m in RE_GOALL.finditer(text)]
    stakes = sorted(bets + goalls, key=lambda t: t[0])
    payouts = sorted(((m.start(), m) for m in RE_PAYOUT.finditer(text)), key=lambda t: t[0])

    rounds: list[GameRound] = []
    spins: list[Spin] = []

    for m in RE_HASIL.finditer(text):
        gr = GameRound(pos=m.start(), date=m.group("date"), time=m.group("time"))
        for rm in RE_ROUND.finditer(m.group("rounds")):
            n = int(rm.group("n"))
            v = rm.group("verdict")
            gr.player_spins.append(n)
            gr.verdicts.append(v)
            gr.player_scores.append(_score_from_verdict(n, v))
        gr.hoster_spin = int(m.group("hoster"))
        gr.hoster_score = _hoster_score_from_verdicts(gr.verdicts)
        gr.multiplier = int(m.group("mult"))

        # taruhan = kejadian bet terakhir SEBELUM blok hasil ini
        prev = [s for s in stakes if s[0] < gr.pos]
        if prev:
            bm = prev[-1][1]
            gr.bet = _num(bm.group("amt"))
            gr.who = bm.group("who")
            gr.game = bm.group("game")
        # payout = blok PAYOUT pertama dalam 2000 karakter setelahnya
        nxt = [p for p in payouts if gr.pos < p[0] < gr.pos + 2000]
        if nxt:
            pm = nxt[0][1]
            gr.payout = _num(pm.group("payout"))
            if pm.group("bet"):
                gr.bet = _num(pm.group("bet"))
            gr.game = pm.group("game")

        for n, sc in zip(gr.player_spins, gr.player_scores):
            spins.append(Spin(n, "player", sc, gr.pos, gr.date, gr.time))
        spins.append(Spin(gr.hoster_spin, "hoster", gr.hoster_score, gr.pos, gr.date, gr.time))
        rounds.append(gr)

    return rounds, spins
