"""Build terrapay_l1_checks.json for the engine UI."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .check_terrapay_l1 import load_data, compare_day

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
OUT_JSON = REPO_ROOT / "data" / "terrapay_l1_checks.json"


def main() -> None:
    period_from = period_to = None
    for i, a in enumerate(sys.argv):
        if a == "--from" and i + 1 < len(sys.argv):
            period_from = sys.argv[i + 1]
        if a == "--to" and i + 1 < len(sys.argv):
            period_to = sys.argv[i + 1]

    print(f"Workspace: {WORKSPACE_ROOT}")
    if period_from or period_to:
        print(f"Period filter: {period_from or '...'} → {period_to or '...'}")

    print("Loading data...")
    tp_by_date, cad_by_date_pin, pin_all = load_data(str(WORKSPACE_ROOT))
    print(f"  TerraPay dates : {len(tp_by_date)}")
    print(f"  Cadorim dates  : {len(cad_by_date_pin)}")

    all_dates = sorted(set(tp_by_date.keys()) | set(cad_by_date_pin.keys()))
    if period_from:
        all_dates = [d for d in all_dates if d >= period_from]
    if period_to:
        all_dates = [d for d in all_dates if d <= period_to]
    print(f"  Dates to check : {len(all_dates)}")

    by_date = {}
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for d in all_dates:
        r = compare_day(d, tp_by_date, cad_by_date_pin, pin_all)
        by_date[d] = r.to_dict()
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    # --- Monthly aggregates (TerraPay-side, per Dr Neine) ---
    # n_tx, total USD, commission 0.5%, MRU @ 39.5, daily average
    FX = 39.5
    COMM = 0.005
    by_month: dict[str, dict] = {}
    for d, rows in tp_by_date.items():
        m = d[:7]
        bm = by_month.setdefault(m, {"month": m, "n_tx": 0, "n_days": 0,
                                      "usd_total": 0.0, "fee_total": 0.0,
                                      "dates": set()})
        bm["n_tx"] += len(rows)
        bm["usd_total"] += sum(t.transfer_usd for t in rows)
        bm["fee_total"] += sum(t.fee_usd for t in rows)
        bm["dates"].add(d)

    monthly: list[dict] = []
    for m in sorted(by_month):
        bm = by_month[m]
        n_tx = bm["n_tx"]
        usd = bm["usd_total"]
        fee = bm["fee_total"]
        n_days = len(bm["dates"])
        commission_calc = usd * COMM      # 0.5% of USD = derived commission
        mru_at_internal = usd * FX        # MRU @ 39.5 = what Cadorim pays clients
        avg_per_day_tx = n_tx / n_days if n_days else 0
        avg_per_day_usd = usd / n_days if n_days else 0
        monthly.append({
            "month": m,
            "n_tx": n_tx,
            "n_days_active": n_days,
            "usd_total": round(usd, 2),
            "fee_total_reported": round(fee, 4),
            "commission_05pct": round(commission_calc, 2),
            "mru_at_internal": round(mru_at_internal, 2),
            "avg_tx_per_day": round(avg_per_day_tx, 1),
            "avg_usd_per_day": round(avg_per_day_usd, 2),
        })

    # Period totals
    total_n_tx = sum(bm["n_tx"] for bm in monthly)
    total_usd = sum(bm["usd_total"] for bm in monthly)
    total_fee = sum(bm["fee_total_reported"] for bm in monthly)
    total_commission = sum(bm["commission_05pct"] for bm in monthly)
    total_mru = sum(bm["mru_at_internal"] for bm in monthly)
    total_days = len({d for bm in by_month.values() for d in bm["dates"]})

    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema_version": 2,
        "available_dates": all_dates,
        "verdict_counts": counts,
        "by_date": by_date,
        "monthly": monthly,
        "totals": {
            "n_tx": total_n_tx,
            "n_days_active": total_days,
            "usd_total": round(total_usd, 2),
            "fee_total_reported": round(total_fee, 4),
            "commission_05pct": round(total_commission, 2),
            "mru_at_internal": round(total_mru, 2),
            "avg_tx_per_day": round(total_n_tx / total_days, 1) if total_days else 0,
            "avg_usd_per_day": round(total_usd / total_days, 2) if total_days else 0,
            "fx_internal": FX,
            "commission_rate": COMM,
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, separators=(",", ":"), default=str)
    size_kb = os.path.getsize(OUT_JSON) / 1024
    print(f"\n✓ Wrote {OUT_JSON} ({size_kb:.1f} KB)")
    print(f"  Verdicts: GREEN {counts['GREEN']}, AMBER {counts['AMBER']}, RED {counts['RED']}")


if __name__ == "__main__":
    main()
