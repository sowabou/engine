"""Build the Check Ria L1 index — one report per date, written to disk.

Sources:
  - Cadorim side : partner_db.ria_transactions (via ria_db_loader)
  - Ria side     : data/ria/Transaction.xlsx   (via ria_excel_loader)

Runs `check_ria_l1.compare_day` for every date that has Ria OR Cadorim data,
and writes the result to `data/ria_l1_checks.json`.

Output schema:
    {
        "generated_at": ISO timestamp,
        "available_dates": [list of YYYY-MM-DD with at least one side data],
        "by_date": { "YYYY-MM-DD": CheckReport.to_dict() }
    }

The engine UI consumes this file directly via fetch — no backend needed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .check_ria_l1 import compare_day
from .ria_corresp_loader import load_ria_by_date
from .ria_db_loader import load_cadorim_ria

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = REPO_ROOT / "data" / "ria_l1_checks.json"


def build_index(out_path: Path = OUT_JSON) -> dict:
    print(f"Loading Cadorim partner DB (partner_db.ria_transactions)...")
    cad_ria_tx = load_cadorim_ria()
    print(f"  Cadorim Ria transactions: {len(cad_ria_tx):,}")

    print(f"Loading Ria statement (data/ria/Transaction.xlsx)...")
    ria_by_date = load_ria_by_date()
    print(f"  Ria transactions        : {sum(len(v) for v in ria_by_date.values()):,}")
    print(f"  Ria dates with data     : {len(ria_by_date):,}")

    # All dates we have any data for
    cad_dates = {str(t.get("date", ""))[:10] for t in cad_ria_tx if t.get("date")}
    ria_dates = set(ria_by_date.keys())
    all_dates = sorted(d for d in (cad_dates | ria_dates) if d)
    print(f"  Combined dates to check : {len(all_dates):,}")

    print(f"\nRunning checks...")
    by_date: dict[str, dict] = {}
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for d in all_dates:
        r = compare_day(d, cad_ria_tx, ria_by_date=ria_by_date)
        by_date[d] = r.to_dict()
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    print(f"\nVerdict distribution:")
    for v, n in counts.items():
        print(f"  {v:<8}: {n:>4}")

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema_version": 1,
        "available_dates": all_dates,
        "verdict_counts": counts,
        "by_date": by_date,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"), default=str)

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"\n✓ Index written: {out_path} ({size_mb:.2f} MB)")
    return output


if __name__ == "__main__":
    build_index()
