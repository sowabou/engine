"""Cadorim-side L1 loader backed by partner_db.ria_transactions (MySQL).

This is the CADORIM side of the Check Ria L1 reconciliation: Cadorim's own
partner-integration DB record of the Ria transactions it processed. It is
compared against Ria's official statement (data/ria/Transaction.xlsx, loaded by
ria_excel_loader).

Output: a flat list of dicts consumed by compare_day as `cadorim_transactions`:
    {
      "pin": "12397605489",
      "date": "YYYY-MM-DD",
      "amount_mru": 10139.04,          # BeneAmount
      "commission_amt": 1.92,          # PCCommissionAmount (EUR)
      "beneficiary": "Djiby Hamady Diallo",
      "id": 1234,                      # partner_db.ria_transactions.id
      "status": "success",
      "local_par_n": "",               # not tracked in partner DB
    }

Source resolution order:
  1. SQLite mirror at /tmp/cadorim_v2.sqlite (populated by load_production.py).
  2. Direct MySQL connection (same env vars as load_production.py).
"""
from __future__ import annotations

import os
import sqlite3
from typing import Iterable

SQLITE_PATH = "/tmp/cadorim_v2.sqlite"

_SELECT_COLS = (
    "PIN, OrderDate, BeneAmount, BeneCurrency, PCCommissionAmount, "
    "PCCommissionCurrency, BeneNameFirst, BeneNameMiddle, BeneNameLast1, "
    "BeneNameLast2, id, status"
)


def _parse_order_date(val) -> str | None:
    """Ria OrderDate is 'YYYYMMDD' as a string."""
    if val is None or val == "":
        return None
    s = str(val).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def _full_name(*parts) -> str:
    return " ".join(p for p in (str(x or "").strip() for x in parts) if p)


def _row_to_cadorim(row: dict) -> dict | None:
    date = _parse_order_date(row.get("OrderDate"))
    pin = str(row.get("PIN") or "").strip()
    if not date or not pin:
        return None

    commission_cur = (row.get("PCCommissionCurrency") or "").upper()
    commission = float(row.get("PCCommissionAmount") or 0)
    return {
        "pin": pin,
        "date": date,
        "amount_mru": round(float(row.get("BeneAmount") or 0), 2),
        "commission_amt": round(commission if commission_cur == "EUR" else 0.0, 2),
        "beneficiary": _full_name(
            row.get("BeneNameFirst"),
            row.get("BeneNameMiddle"),
            row.get("BeneNameLast1"),
            row.get("BeneNameLast2"),
        ),
        "id": row.get("id"),
        "status": (row.get("status") or "").strip(),
        "local_par_n": "",
    }


def _iter_rows_sqlite(db_path: str) -> Iterable[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for r in conn.execute(f"SELECT {_SELECT_COLS} FROM ria_transactions"):
            yield dict(r)
    finally:
        conn.close()


def _iter_rows_mysql() -> Iterable[dict]:
    import pymysql
    from pymysql.cursors import DictCursor

    conn = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", "cadorim"),
        database="partner_db",
        charset="utf8mb4",
        cursorclass=DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_SELECT_COLS} FROM ria_transactions")
            while True:
                rows = cur.fetchmany(5000)
                if not rows:
                    break
                yield from rows
    finally:
        conn.close()


def load_cadorim_ria() -> list[dict]:
    """Return Cadorim-side Ria rows (flat list) from partner_db.ria_transactions."""
    rows: Iterable[dict]
    if os.path.exists(SQLITE_PATH):
        try:
            rows = list(_iter_rows_sqlite(SQLITE_PATH))
        except sqlite3.OperationalError:
            rows = []
        if rows:
            return _normalize(rows)
    try:
        return _normalize(_iter_rows_mysql())
    except Exception:
        return []


def _normalize(rows: Iterable[dict]) -> list[dict]:
    out: list[dict] = []
    seen_pin: set[str] = set()
    for raw in rows:
        norm = _row_to_cadorim(raw)
        if not norm or norm["pin"] in seen_pin:
            continue
        seen_pin.add(norm["pin"])
        out.append(norm)
    out.sort(key=lambda r: (r["date"], r["pin"]))
    return out


if __name__ == "__main__":
    rows = load_cadorim_ria()
    dates = sorted({r["date"] for r in rows})
    print(f"Loaded {len(rows):,} Cadorim Ria rows across {len(dates):,} dates")
    if dates:
        print(f"Range: {dates[0]} → {dates[-1]}")
        sample = rows[:3]
        for r in sample:
            print(f"  {r['date']} pin={r['pin']} mru={r['amount_mru']:>10,.2f} comm_eur={r['commission_amt']}")
