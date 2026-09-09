"""
Parser Omni_Bot v2 - MENGGANTIKAN parse_omnibot.py.

v1 punya dua cacat fatal yang membalik kesimpulan audit:

  1. Melewatkan event "HOSTER AUTO-WIN" (format pesan berbeda, tanpa blok
     Hasil). Akibatnya 1.223 ronde yang DIMENANGKAN bandar hilang dari data,
     dan spin hoster {0,1,10,19,28,29} terlihat "tidak pernah muncul" -
     artefak parsing yang sempat disalahartikan sebagai bukti pembatasan roda.

  2. Mengabaikan RES/RGO. Kalau pemain menang 1 ronde dan kalah 1 ronde,
     percobaan DIULANG dan TIDAK dibayar. v1 membayar semuanya, sehingga
     P&L bandar terhitung jauh lebih buruk dari kenyataan.

v2 memodelkan taruhan sebagai rangkaian percobaan sampai benar-benar selesai.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

score = lambda n: sum(int(c) for c in str(n)) % 10

RE_BET     = re.compile(r"✅ Bet @⁨([^⁩]*)⁩ \*([\d.,]+)\*")
RE_GOALL   = re.compile(r"🚀 \*GO ALL!\* @⁨([^⁩]*)⁩ taruhan \*([\d.,]+) coin\*")
RE_HASIL   = re.compile(r"📊 \*Hasil\*\n((?:R\d+: .*\n)+)Hoster: (\d+)\nMultiplier total: ×(\d+)")
RE_AUTOWIN = re.compile(r"🚀 \*HOSTER AUTO-WIN!\*\nHoster spin: (\d+) \(score (\d+)\)")
RE_RES     = re.compile(r"♻️ \*RES\* — restart!")
# Format lama (grup LEME Mei-Juni)
RE_PAYOUT  = re.compile(r"💰 \*PAYOUT: ([\d.,]+) COIN\*\n🎲 Game: (\w+)\n📊 Bet awal: ([\d.,]+)")
# Format baru (kotak "PAYOUT OTOMATIS"). Tidak memuat "Bet awal",
# jadi nominal taruhan diambil dari wager yang sedang berjalan.
# Format-format baru. Bot versi baru punya TIGA gaya pengumuman menang:
#   inline  : 💰 *Payout: 40.000 COIN*
#   kotak   : ┃ 💰 Payout: *60.000 Coin*
# Keduanya memakai "Payout" (huruf kecil), berbeda dari "PAYOUT" format lama,
# sehingga tidak saling tumpang tindih.
RE_PAYOUT2 = re.compile(r"💰 \*?Payout: \*?([\d.,]+) (?:COIN|Coin)\*?")
RE_KALAH   = re.compile(r"💀 @⁨([^⁩]*)⁩ kalah")
RE_ROUND   = re.compile(r"R(\d+): (\d+) → (.*)")

WIN_MARKERS = ("jackpot", "Normal win")


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", ""))


def _is_win(verdict: str) -> bool:
    return any(w in verdict for w in WIN_MARKERS)


@dataclass
class Attempt:
    kind: str                      # "hasil" | "autowin"
    pos: int
    player_spins: list[int] = field(default_factory=list)
    wins: list[bool] = field(default_factory=list)
    hoster_spin: int = -1
    multiplier: int = 0


@dataclass
class Wager:
    """Satu taruhan, dari diterima sampai benar-benar selesai (bisa berkali RES)."""
    player: str
    stake: float
    attempts: list[Attempt] = field(default_factory=list)
    settled: str = ""              # "house" | "player" | ""
    payout: float = 0.0

    @property
    def house_pnl(self) -> float:
        if self.settled == "house":
            return self.stake
        if self.settled == "player":
            return self.stake - self.payout
        return 0.0


def parse(path: str | Path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")

    ev = []
    for m in RE_BET.finditer(text):     ev.append((m.start(), "bet", m))
    for m in RE_GOALL.finditer(text):   ev.append((m.start(), "bet", m))
    for m in RE_HASIL.finditer(text):   ev.append((m.start(), "hasil", m))
    for m in RE_AUTOWIN.finditer(text): ev.append((m.start(), "autowin", m))
    for m in RE_RES.finditer(text):     ev.append((m.start(), "res", m))
    for m in RE_PAYOUT.finditer(text):  ev.append((m.start(), "payout", m))
    for m in RE_PAYOUT2.finditer(text): ev.append((m.start(), "payout2", m))
    for m in RE_KALAH.finditer(text):   ev.append((m.start(), "kalah", m))
    ev.sort(key=lambda t: t[0])

    wagers: list[Wager] = []
    spins: list[tuple[int, str]] = []      # (nilai, peran)
    cur: Wager | None = None

    for pos, kind, m in ev:
        if kind == "bet":
            cur = Wager(player=m.group(1), stake=_num(m.group(2)))
            wagers.append(cur)
        elif kind == "hasil":
            a = Attempt("hasil", pos, hoster_spin=int(m.group(2)), multiplier=int(m.group(3)))
            for rm in RE_ROUND.finditer(m.group(1)):
                a.player_spins.append(int(rm.group(2)))
                a.wins.append(_is_win(rm.group(3)))
                spins.append((int(rm.group(2)), "player"))
            spins.append((a.hoster_spin, "hoster"))
            if cur is not None:
                cur.attempts.append(a)
        elif kind == "autowin":
            a = Attempt("autowin", pos, hoster_spin=int(m.group(1)))
            spins.append((a.hoster_spin, "hoster"))
            if cur is not None:
                cur.attempts.append(a)
        elif kind == "payout":
            if cur is not None and not cur.settled:
                cur.settled = "player"
                cur.payout = _num(m.group(1))
                cur.stake = _num(m.group(3))     # "Bet awal" lebih tepercaya
                cur = None
        elif kind == "payout2":
            if cur is not None and not cur.settled:
                cur.settled = "player"
                cur.payout = _num(m.group(1))
                cur = None
        elif kind == "kalah":
            if cur is not None and not cur.settled:
                cur.settled = "house"
                cur = None
        # "res" tidak menyelesaikan apa-apa - taruhan berlanjut

    return wagers, spins
