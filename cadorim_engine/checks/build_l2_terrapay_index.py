"""Build ria_l2_checks.json's TerraPay equivalent for the engine UI."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .check_terrapay_l2 import reconcile

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
OUT_JSON = REPO_ROOT / "data" / "terrapay_l2_checks.json"


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
    r = reconcile(str(WORKSPACE_ROOT), period_from=period_from, period_to=period_to)
    out = r.to_dict()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, separators=(",", ":"), default=str)
    size_kb = os.path.getsize(OUT_JSON) / 1024
    print(f"✓ Wrote {OUT_JSON} ({size_kb:.1f} KB)")
    print(f"  {r.n_settlements} settlements (settlement-only L2, no L1 mixing)")
    print(f"  USDC reçu: {r.usdc_total:,.2f} | MRU @ interne: {r.mru_at_internal_total:,.2f} | MRU @ Binance: {r.mru_at_market_total:,.2f}")
    print(f"  Gain L2: {r.gain_l2_total:,.2f} MRU (spread {r.fx_market_weighted_avg - r.fx_internal:.4f} MRU/USDC)")


if __name__ == "__main__":
    main()
