"""Check TerraPay Layer 2 — settlement-only reconciliation.

PURE LAYER 2: this module looks ONLY at settlements (USDC received on Cado02
from TerraPay, then sold on Binance for MRU). It does NOT touch the L1
transactions table — that's Layer 1's job (Check TerraPay L1 — separate).

Math:
  For each USDC settlement S (date d_s, amount USDC) :
    FX_internal     = 39.5     (Cadorim's reference rate for booking USDC)
    FX_market(d_s)  = Binance P2P daily weighted-average rate that day
                      (fallback: nearest day, or month avg, or constant)

    mru_at_internal(S) = USDC × FX_internal              ← what Cadorim books
    mru_at_market(S)   = USDC × FX_market(d_s)           ← what Cadorim really gets
    gain_l2(S)         = USDC × (FX_market(d_s) − FX_internal)

  Total gain L2 = Σ gain_l2(S)

The Binance daily rate comes from `mru_usd_exchange.json` (built from
Binance_P2P_USDT_MRU_2026.xlsx — see `build_exchange_account.py`).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# Tunables
FX_USD_INTERNAL = 39.5            # Cadorim's reference rate
FX_USD_MARKET_FALLBACK = 40.78    # If no Binance data for a date


@dataclass
class TPSettlement:
    """One USDC settlement on Cado02 + its market conversion view."""

    date: str
    settlement_id: str
    usdc: float
    fx_internal: float                # 39.5
    fx_market: float                  # Binance daily rate
    fx_market_source: str             # "2026-01-09" if same day, "2026-01-08" if nearest, "2026-01-avg" if month avg, "fallback" if none
    mru_at_internal: float            # USDC × fx_internal
    mru_at_market: float              # USDC × fx_market
    gain_l2_mru: float                # USDC × (fx_market − fx_internal)
    reference: str                    # ETH tx hash
    source_file: str


@dataclass
class TPL2Report:
    generated_at: str
    period_from: str
    period_to: str
    fx_internal: float
    fx_market_weighted_avg: float
    fx_market_min: float
    fx_market_max: float
    n_settlements: int
    usdc_total: float
    mru_at_internal_total: float
    mru_at_market_total: float
    gain_l2_total: float
    usdc_by_month: dict[str, float] = field(default_factory=dict)
    gain_l2_by_month: dict[str, float] = field(default_factory=dict)
    mru_market_by_month: dict[str, float] = field(default_factory=dict)
    settlements: list[TPSettlement] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["settlements"] = [asdict(s) if hasattr(s, "__dataclass_fields__") else s for s in self.settlements]
        return d


def _load_settlements(production_json: Path, period_from: str | None = None, period_to: str | None = None) -> list[dict]:
    """Load TerraPay USDC settlements.

    Reads DIRECTLY from Cado02 Excel dossier (not from production_data_all.json),
    so the period can be extended freely without regenerating the production
    JSON. Falls back to production_data_all.json if Cado02 not available.
    """
    workspace = production_json.parent.parent.parent  # cadorim-engine/data → cadorim-engine → workspace root
    cado02_xlsx = workspace / "Cado02_Transaction_Dossier_2026.xlsx"
    if cado02_xlsx.exists():
        from ..settlements.ingest import parse_cado02_terrapay
        from_d = period_from or "2025-01-01"
        to_d = period_to or "2026-12-31"
        # parse_cado02_terrapay's filter is [from, to), so add 1 day to to_d
        from datetime import datetime as _dt, timedelta as _td
        to_inclusive = (_dt.strptime(to_d, "%Y-%m-%d") + _td(days=1)).strftime("%Y-%m-%d")
        return parse_cado02_terrapay(from_date=from_d, to_date=to_inclusive)
    # Fallback
    if not production_json.exists():
        return []
    with open(production_json) as f:
        prod = json.load(f)
    return [s for s in prod.get("settlements", []) if s.get("Par_l") == "terrapay"]


def _load_binance_daily_rates(workspace_root: str) -> tuple[dict[str, float], dict[str, float]]:
    """Load Binance P2P daily rates from mru_usd_exchange.json."""
    exchange_json = Path(workspace_root) / "cadorim-engine" / "data" / "mru_usd_exchange.json"
    if not exchange_json.exists():
        return {}, {}
    with open(exchange_json) as f:
        ex = json.load(f)
    by_day = {d["date"]: float(d["rate_avg"]) for d in ex.get("by_day", []) if d.get("rate_avg")}
    by_month = {d["month"]: float(d["rate_avg"]) for d in ex.get("by_month", []) if d.get("rate_avg")}
    return by_day, by_month


def _lookup_binance_rate(
    date: str, by_day: dict[str, float], by_month: dict[str, float],
    fallback: float, max_lookback: int = 7
) -> tuple[float, str]:
    """Find the closest Binance rate for a given settlement date."""
    if date in by_day:
        return by_day[date], date
    d_dt = datetime.strptime(date, "%Y-%m-%d")
    for offset in range(1, max_lookback + 1):
        prev = (d_dt - timedelta(days=offset)).strftime("%Y-%m-%d")
        if prev in by_day:
            return by_day[prev], prev
        nxt = (d_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        if nxt in by_day:
            return by_day[nxt], nxt
    month = date[:7]
    if month in by_month:
        return by_month[month], f"{month}-avg"
    return fallback, "fallback"


def reconcile(
    workspace_root: str,
    period_from: str | None = None,
    period_to: str | None = None,
    fx_internal: float = FX_USD_INTERNAL,
    fx_market_fallback: float = FX_USD_MARKET_FALLBACK,
) -> TPL2Report:
    """Pure Layer 2 reconciliation: settlements + market FX, no L1 mixing."""
    production_json = Path(workspace_root) / "cadorim-engine" / "data" / "production_data_all.json"
    raw_settlements = _load_settlements(production_json, period_from, period_to)
    binance_by_day, binance_by_month = _load_binance_daily_rates(workspace_root)

    # Apply period filter
    def in_window(d: str) -> bool:
        if period_from and d < period_from:
            return False
        if period_to and d > period_to:
            return False
        return True

    raw_settlements = [s for s in raw_settlements if in_window(s.get("date", ""))]
    raw_settlements.sort(key=lambda s: s.get("date", ""))

    settlements: list[TPSettlement] = []
    for s in raw_settlements:
        d = s.get("date", "")
        usdc = float(s.get("amount_foreign", 0) or 0)
        fx_market, fx_source = _lookup_binance_rate(d, binance_by_day, binance_by_month, fx_market_fallback)
        mru_int = usdc * fx_internal
        mru_mkt = usdc * fx_market
        gain = usdc * (fx_market - fx_internal)
        settlements.append(TPSettlement(
            date=d,
            settlement_id=s.get("id", ""),
            usdc=round(usdc, 2),
            fx_internal=fx_internal,
            fx_market=round(fx_market, 4),
            fx_market_source=fx_source,
            mru_at_internal=round(mru_int, 2),
            mru_at_market=round(mru_mkt, 2),
            gain_l2_mru=round(gain, 2),
            reference=s.get("reference", "")[:66],
            source_file=s.get("source_file", ""),
        ))

    # Aggregates
    usdc_total = sum(s.usdc for s in settlements)
    mru_int_total = sum(s.mru_at_internal for s in settlements)
    mru_mkt_total = sum(s.mru_at_market for s in settlements)
    gain_total = sum(s.gain_l2_mru for s in settlements)
    fx_avg = (mru_mkt_total / usdc_total) if usdc_total > 0 else 0.0
    fx_values = [s.fx_market for s in settlements if s.fx_market > 0]
    fx_min = min(fx_values) if fx_values else 0.0
    fx_max = max(fx_values) if fx_values else 0.0

    usdc_by_month: dict[str, float] = {}
    gain_by_month: dict[str, float] = {}
    mkt_by_month: dict[str, float] = {}
    for s in settlements:
        k = s.date[:7]
        usdc_by_month[k] = usdc_by_month.get(k, 0.0) + s.usdc
        gain_by_month[k] = gain_by_month.get(k, 0.0) + s.gain_l2_mru
        mkt_by_month[k] = mkt_by_month.get(k, 0.0) + s.mru_at_market

    return TPL2Report(
        generated_at=datetime.utcnow().isoformat() + "Z",
        period_from=settlements[0].date if settlements else "",
        period_to=settlements[-1].date if settlements else "",
        fx_internal=fx_internal,
        fx_market_weighted_avg=round(fx_avg, 4),
        fx_market_min=round(fx_min, 4),
        fx_market_max=round(fx_max, 4),
        n_settlements=len(settlements),
        usdc_total=round(usdc_total, 2),
        mru_at_internal_total=round(mru_int_total, 2),
        mru_at_market_total=round(mru_mkt_total, 2),
        gain_l2_total=round(gain_total, 2),
        usdc_by_month={k: round(v, 2) for k, v in sorted(usdc_by_month.items())},
        gain_l2_by_month={k: round(v, 2) for k, v in sorted(gain_by_month.items())},
        mru_market_by_month={k: round(v, 2) for k, v in sorted(mkt_by_month.items())},
        settlements=settlements,
    )


if __name__ == "__main__":
    import sys
    workspace = "/sessions/adoring-keen-clarke/mnt/Cadorim Accounting"
    period_from = period_to = None
    for i, a in enumerate(sys.argv):
        if a == "--from" and i + 1 < len(sys.argv):
            period_from = sys.argv[i + 1]
        if a == "--to" and i + 1 < len(sys.argv):
            period_to = sys.argv[i + 1]
    r = reconcile(workspace, period_from=period_from, period_to=period_to)
    print(f"=== TerraPay Layer 2 (settlement-only) — {r.period_from} → {r.period_to} ===")
    print(f"FX interne Cadorim   : {r.fx_internal}")
    print(f"FX Binance moyen     : {r.fx_market_weighted_avg}  (min {r.fx_market_min}, max {r.fx_market_max})")
    print(f"Spread moyen         : +{r.fx_market_weighted_avg - r.fx_internal:.4f} MRU/USDC")
    print(f"Settlements          : {r.n_settlements}")
    print(f"USDC reçu            : {r.usdc_total:>14,.2f}")
    print(f"MRU @ 39,5 interne   : {r.mru_at_internal_total:>14,.2f}")
    print(f"MRU @ Binance réel   : {r.mru_at_market_total:>14,.2f}")
    print(f"Gain L2              : {r.gain_l2_total:>14,.2f} MRU")
    print()
    print("Par mois:")
    for m in sorted(r.gain_l2_by_month, reverse=True):
        mkt = r.mru_market_by_month.get(m, 0)
        gain = r.gain_l2_by_month[m]
        print(f"  {m}: MRU reçu (Binance) {mkt:>14,.2f}  gain {gain:>14,.2f}")
