"""CLI: python3 -m rngaudit.cli <perintah>"""
from __future__ import annotations

import argparse
import sys

from .forensics import BetSpec, analyse_rules, rounds_needed
from .loader import load_csv, write_template
from .report import audit


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rngaudit", description="Audit keadilan RNG kasino")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit file CSV")
    a.add_argument("csv")
    a.add_argument("--k", type=int, required=True, help="jumlah kemungkinan hasil (dadu=6)")
    a.add_argument("--p-house", type=float, default=None, help="peluang bandar menang menurut aturan")
    a.add_argument("--payout", type=float, default=None)
    a.add_argument("--payout-mode", choices=["total", "profit"], default="total")

    e = sub.add_parser("edge", help="hitung house edge dari aturan main")
    e.add_argument("--p-win", type=float, required=True, help="peluang PEMAIN menang")
    e.add_argument("--payout", type=float, required=True)
    e.add_argument("--payout-mode", choices=["total", "profit"], default="total")
    e.add_argument("--name", default="taruhan")

    p = sub.add_parser("power", help="berapa ronde yang perlu dikumpulkan")
    p.add_argument("--k", type=int, required=True)

    t = sub.add_parser("template", help="tulis template CSV")
    t.add_argument("path", nargs="?", default="log_ronde.csv")

    d = sub.add_parser("demo", help="jalankan pada data simulasi")
    d.add_argument("--rig", default="stake_targeted")
    d.add_argument("--n", type=int, default=1500)
    d.add_argument("--strength", type=float, default=0.30)

    ns = ap.parse_args(argv)

    if ns.cmd == "audit":
        rounds = load_csv(ns.csv)
        print(audit(rounds, ns.k, ns.p_house, ns.payout, ns.payout_mode))
    elif ns.cmd == "edge":
        print(analyse_rules([BetSpec(ns.name, ns.p_win, ns.payout, ns.payout_mode)]))
    elif ns.cmd == "power":
        print(f"Ronde dibutuhkan untuk mendeteksi bias (k={ns.k}, alpha=0.05, power=80%):")
        for b in (0.50, 0.30, 0.20, 0.10, 0.05, 0.02):
            print(f"   bias {int(b*100):3d}%  ->  {rounds_needed(ns.k, b):>10,} ronde")
    elif ns.cmd == "template":
        print(f"Template ditulis ke: {write_template(ns.path)}")
    elif ns.cmd == "demo":
        from .simulate import simulate, K, PAYOUT, MODE
        rounds = simulate(ns.n, ns.rig, ns.strength, seed=777)
        print(f"### DEMO: data simulasi dengan kecurangan '{ns.rig}' ###")
        print(audit(rounds, K, 0.5, PAYOUT, MODE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
