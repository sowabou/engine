"""Ria CorrespPayment loader.

Reads all CorrespPayment_52447_*.xlsx files from data/settlements/ria_corresp/
and indexes Ria-side L1 transactions by transaction date.

Provides a single function `load_ria_by_date()` that returns a dict mapping
each date (YYYY-MM-DD) to the list of Ria transactions for that day.

Caching: the consolidation is expensive (363 files), so we cache the result
on disk under data/cache/ria_l1_by_date.json. Cache invalidates whenever the
source directory's max mtime is newer than the cache.
"""
from __future__ import annotations

import json
import os
from typing import Iterable

try:
    import openpyxl
except ImportError:
    openpyxl = None


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORRESP_DIR = os.path.join(REPO_ROOT, "data", "settlements", "ria_corresp")
CACHE_DIR = os.path.join(REPO_ROOT, "data", "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "ria_l1_by_date.json")


def _list_corresp_files() -> list[str]:
    if not os.path.isdir(CORRESP_DIR):
        return []
    return sorted(
        os.path.join(CORRESP_DIR, f)
        for f in os.listdir(CORRESP_DIR)
        if f.lower().endswith((".xlsx", ".xls"))
    )


def _max_mtime(files: Iterable[str]) -> float:
    return max((os.path.getmtime(f) for f in files), default=0.0)


def _parse_date(val) -> str | None:
    """Normalize a Ria Date cell value to YYYY-MM-DD."""
    if val is None or val == "":
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    # Try common formats
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_corresp_file(path: str) -> list[dict]:
    """Read one CorrespPayment xlsx → list of normalized row dicts."""
    if openpyxl is None:
        return []
    rows: list[dict] = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    raw = list(ws.iter_rows(values_only=True))
    wb.close()
    if not raw:
        return rows
    headers = [str(h).strip() if h else "" for h in raw[0]]
    for r in raw[1:]:
        if not r or all(v is None for v in r):
            continue
        d = dict(zip(headers, r))
        item = str(d.get("Item", "")).strip()
        if item != "Order Amount":
            continue  # skip commission-only lines, fees, etc.
        date = _parse_date(d.get("Date"))
        seq = d.get("Seq")
        if not date or not seq:
            continue

        def _to_float(x):
            try:
                return float(x) if x is not None and x != "" else 0.0
            except (TypeError, ValueError):
                return 0.0

        rows.append(
            {
                "date": date,
                "seq": str(seq).strip(),
                "beneficiary": str(d.get("Beneficiary", "")).strip(),
                "pin": str(d.get("PIN", "")).strip() if d.get("PIN") is not None else "",
                "currency": str(d.get("Cur", "")).strip(),
                "order_amt": _to_float(d.get("Order Amt")),
                "order_amt_usd": _to_float(d.get("Order Amt USD")),
                "commission_amt": _to_float(d.get("Commission Amt")),
                "commission_amt_usd": _to_float(d.get("Commission Amt USD")),
                "location": str(d.get("Location", "")).strip(),
                "source_file": os.path.basename(path),
            }
        )
    return rows


def _build_index() -> dict[str, list[dict]]:
    """Read all CorrespPayment files, dedup by seq, group by date."""
    files = _list_corresp_files()
    seen_seq: set[str] = set()
    by_date: dict[str, list[dict]] = {}
    for f in files:
        try:
            for row in _parse_corresp_file(f):
                if row["seq"] in seen_seq:
                    continue
                seen_seq.add(row["seq"])
                by_date.setdefault(row["date"], []).append(row)
        except Exception:
            continue
    # Sort each day's rows by seq for stability
    for d in by_date:
        by_date[d].sort(key=lambda r: r["seq"])
    return by_date


def load_ria_by_date(force_refresh: bool = False) -> dict[str, list[dict]]:
    """Return dict {YYYY-MM-DD: [transactions...]} for the Ria side of Check L1.

    Source resolution: prefer the Ria statement at data/ria/Transaction.xlsx
    (the authoritative Ria-reported data). Fall back to the legacy
    CorrespPayment xlsx files when that statement is absent.

    Uses an on-disk cache keyed by the source dir's max mtime for the legacy
    fallback path, so subsequent calls are instant.
    """
    # Primary source: the Ria statement Excel.
    try:
        from .ria_excel_loader import load_ria_by_date as load_ria_excel
        excel_idx = load_ria_excel()
        if excel_idx:
            return excel_idx
    except Exception:
        pass

    files = _list_corresp_files()
    if not files:
        return {}

    max_mt = _max_mtime(files)

    # Try cache
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as fh:
                cache = json.load(fh)
            if cache.get("max_mtime") == max_mt and cache.get("n_files") == len(files):
                return cache["by_date"]
        except Exception:
            pass

    # Rebuild
    by_date = _build_index()

    # Persist cache
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as fh:
            json.dump({"max_mtime": max_mt, "n_files": len(files), "by_date": by_date}, fh)
    except Exception:
        pass

    return by_date


def load_ria_for_date(d: str) -> list[dict]:
    """Convenience: return Ria transactions for a single date."""
    return load_ria_by_date().get(d, [])


def available_dates() -> list[str]:
    """Return sorted list of dates for which we have Ria data."""
    return sorted(load_ria_by_date().keys())


if __name__ == "__main__":
    idx = load_ria_by_date()
    print(f"Indexed {sum(len(v) for v in idx.values())} Ria transactions across {len(idx)} dates")
    if idx:
        dates = sorted(idx.keys())
        print(f"Date range: {dates[0]} → {dates[-1]}")
        # Show a few sample days
        for d in (dates[0], dates[len(dates) // 2], dates[-1]):
            day = idx[d]
            total = sum(r["order_amt"] for r in day if r["currency"] == "EUR")
            print(f"  {d}: {len(day):>4} tx, {total:>10,.2f} EUR")
