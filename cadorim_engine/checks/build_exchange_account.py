"""Build MRUUSDExchange account JSON for the engine UI.

Aggregates Binance P2P USDT→MRU sales and presents them as a single
'exchange account' with daily FX rates. Used to compute real economic gain
for TerraPay L2 (replacing the fixed FX 39.5 assumption with daily Binance
rates).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .parsers.binance_p2p import parse_p2p_file, aggregate_by_day, filter_period

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
OUT_JSON = REPO_ROOT / "data" / "mru_usd_exchange.json"
P2P_FILE = WORKSPACE_ROOT / "Binance_P2P_USDT_MRU_2026.xlsx"


def build(period_from: str | None = None, period_to: str | None = None) -> dict:
    sales = parse_p2p_file(str(P2P_FILE))
    sales = filter_period(sales, period_from, period_to)
    daily = aggregate_by_day(sales)

    # Aggregates
    total_usdt = sum(s.usdt_sold for s in sales)
    total_mru = sum(s.mru_received for s in sales)
    total_fees = sum(s.fee_taker for s in sales)
    rate_avg = (total_mru / total_usdt) if total_usdt > 0 else 0.0

    # Monthly
    by_month: dict[str, dict] = {}
    for s in sales:
        m = s.date[:7]
        d = by_month.setdefault(m, {"n_sales": 0, "usdt": 0.0, "mru": 0.0})
        d["n_sales"] += 1
        d["usdt"] += s.usdt_sold
        d["mru"] += s.mru_received
    monthly = []
    for m, d in sorted(by_month.items()):
        d["rate_avg"] = round((d["mru"] / d["usdt"]) if d["usdt"] > 0 else 0.0, 4)
        d["usdt"] = round(d["usdt"], 2)
        d["mru"] = round(d["mru"], 2)
        d["month"] = m
        monthly.append(d)

    rates = [d["rate_avg"] for d in daily if d["rate_avg"] > 0]
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "period_from": period_from or (sales[0].date if sales else ""),
        "period_to": period_to or (sales[-1].date if sales else ""),
        "n_sales": len(sales),
        "n_days": len(daily),
        "total_usdt_sold": round(total_usdt, 2),
        "total_mru_received": round(total_mru, 2),
        "total_fees_usdt": round(total_fees, 4),
        "rate_weighted_avg": round(rate_avg, 4),
        "rate_min": round(min(rates), 4) if rates else 0.0,
        "rate_max": round(max(rates), 4) if rates else 0.0,
        "by_day": daily,
        "by_month": monthly,
        "sales": [s.to_dict() for s in sales],
    }


def main() -> None:
    period_from = period_to = None
    for i, a in enumerate(sys.argv):
        if a == "--from" and i + 1 < len(sys.argv):
            period_from = sys.argv[i + 1]
        if a == "--to" and i + 1 < len(sys.argv):
            period_to = sys.argv[i + 1]
    out = build(period_from, period_to)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, separators=(",", ":"), default=str)
    size_kb = os.path.getsize(OUT_JSON) / 1024
    print(f"✓ Wrote {OUT_JSON} ({size_kb:.1f} KB)")
    print(f"  {out['n_sales']} sales on {out['n_days']} days")
    print(f"  Total USDT: {out['total_usdt_sold']:,.2f}")
    print(f"  Total MRU : {out['total_mru_received']:,.2f}")
    print(f"  Rate avg  : {out['rate_weighted_avg']}  (min {out['rate_min']}, max {out['rate_max']})")


if __name__ == "__main__":
    main()
