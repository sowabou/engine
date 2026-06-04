"""Ria-side L1 loader backed by an Excel statement.

Reads `data/ria/Transaction.xlsx` — the official statement Ria provides — and
indexes its rows by transaction date. This is the AUTHORITATIVE Ria side of the
Check Ria L1 reconciliation (the Cadorim side comes from
`partner_db.ria_transactions` via ria_db_loader).

Expected columns (header row):
    Date              -> "DD-MM-YYYY H:MM:SS"
    PIN               -> Ria Personal Identification Number
    Beneficiary       -> beneficiary full name
    Order Amt en Mru  -> payout amount in MRU
    Commission Amt    -> Ria commission in EUR

Output shape (one list per date) matches what compare_day consumes:
    {
      "date": "YYYY-MM-DD",
      "pin": "12397605489",
      "beneficiary": "Djiby Hamady Diallo",
      "order_amt_mru": 10139.04,
      "commission_amt": 1.92,     # EUR
      "seq": "",
      "source_file": "Transaction.xlsx",
    }
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable

try:
    import openpyxl
except ImportError:
    openpyxl = None

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RIA_XLSX = os.path.join(REPO_ROOT, "data", "ria", "Transaction.xlsx")

# Header aliases → canonical field. Tolerant to minor label variations.
_COL_ALIASES = {
    "date": "date",
    "pin": "pin",
    "beneficiary": "beneficiary",
    "order amt en mru": "order_amt_mru",
    "order amt mru": "order_amt_mru",
    "commission amt": "commission_amt",
}


def _norm_header(h) -> str:
    return str(h or "").strip().lower()


def _parse_date(val) -> str | None:
    """Ria date is 'DD-MM-YYYY H:MM:SS' (or a real datetime)."""
    if val is None or val == "":
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    for fmt in (
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _to_float(x) -> float:
    try:
        return float(x) if x is not None and x != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def _parse_file(path: str) -> list[dict]:
    if openpyxl is None:
        raise RuntimeError("openpyxl is required to read the Ria Excel statement")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    raw = list(ws.iter_rows(values_only=True))
    wb.close()
    if not raw:
        return []

    headers = [_norm_header(h) for h in raw[0]]
    col_index = {}
    for i, h in enumerate(headers):
        canon = _COL_ALIASES.get(h)
        if canon:
            col_index[canon] = i

    rows: list[dict] = []
    for r in raw[1:]:
        if not r or all(v is None for v in r):
            continue

        def cell(field):
            i = col_index.get(field)
            return r[i] if i is not None and i < len(r) else None

        date = _parse_date(cell("date"))
        pin_raw = cell("pin")
        pin = str(pin_raw).strip() if pin_raw is not None else ""
        if not date or not pin:
            continue

        rows.append({
            "date": date,
            "pin": pin,
            "beneficiary": str(cell("beneficiary") or "").strip(),
            "order_amt_mru": round(_to_float(cell("order_amt_mru")), 2),
            "commission_amt": round(_to_float(cell("commission_amt")), 2),
            "seq": "",
            "source_file": os.path.basename(path),
        })
    return rows


def load_ria_by_date() -> dict[str, list[dict]]:
    """Return {YYYY-MM-DD: [rows...]} from the Ria Excel statement."""
    if not os.path.exists(RIA_XLSX):
        return {}
    by_date: dict[str, list[dict]] = {}
    seen_pin: set[str] = set()
    for row in _parse_file(RIA_XLSX):
        if row["pin"] in seen_pin:
            continue
        seen_pin.add(row["pin"])
        by_date.setdefault(row["date"], []).append(row)
    for d in by_date:
        by_date[d].sort(key=lambda x: x["pin"])
    return by_date


if __name__ == "__main__":
    idx = load_ria_by_date()
    total = sum(len(v) for v in idx.values())
    dates = sorted(idx.keys())
    print(f"Indexed {total:,} Ria rows across {len(dates):,} dates from {RIA_XLSX}")
    for d in dates:
        rows = idx[d]
        mru = sum(r["order_amt_mru"] for r in rows)
        print(f"  {d}: {len(rows):>4} rows, {mru:>14,.2f} MRU")
