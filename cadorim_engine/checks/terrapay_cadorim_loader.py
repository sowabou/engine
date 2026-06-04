"""Load Cadorim-side TerraPay transactions from wallet_db_transactions.sql.

These are the rows where `external_transaction_id LIKE 'TPFN%'` — the
genuine per-customer TerraPay payouts journalized by Cadorim (typically
classified as `db_type='depot'`).

These are NOT the same as the 777 `Par_l='terrapay'` rows in
production_data_all.json (those are caisse/wallet transfers — the
classifier separates them). For L1 reconciliation against TerraPay
statements, we MUST use the TPFN-tagged rows directly from the SQL.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class CadorimTPTx:
    """One Cadorim-side TerraPay transaction (matched by TPFN)."""

    cadorim_id: int           # transaction id in wallet_db_transactions
    tpfn: str                 # external_transaction_id
    date: str                 # YYYY-MM-DD (from created_at)
    amount_mru: float         # transaction amount (in MRU)
    frais: float              # fees charged
    type: str                 # db type (typically 'depot' for TerraPay)
    status: str               # completed/failed/canceled
    reference: str            # cadorim internal reference (e.g., c20260120125843mTjF)
    description: str          # free-text
    creditable_id: int        # the customer/account credited
    creditable_type: str
    debitable_id: int
    debitable_type: str

    def to_dict(self) -> dict:
        return asdict(self)


# Match one row from INSERT INTO `transactions` VALUES (...)
# Top-level: a tuple separated by commas, allowing nested string escapes.
def _split_sql_values(values_text: str) -> list[str]:
    """Split the VALUES (...),(...) string into individual row tuples."""
    rows: list[str] = []
    depth = 0
    in_str = False
    esc = False
    buf: list[str] = []
    for ch in values_text:
        if in_str:
            if esc:
                esc = False
                buf.append(ch)
                continue
            if ch == "\\":
                esc = True
                buf.append(ch)
                continue
            if ch == "'":
                in_str = False
            buf.append(ch)
            continue
        if ch == "'":
            in_str = True
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
            if depth == 1:
                buf = []
                continue
            buf.append(ch)
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                rows.append("".join(buf))
                buf = []
                continue
            buf.append(ch)
            continue
        if depth >= 1:
            buf.append(ch)
    return rows


def _parse_row_fields(row_text: str) -> list[str]:
    """Split a single row (already without outer parens) into fields."""
    fields: list[str] = []
    in_str = False
    esc = False
    buf: list[str] = []
    for ch in row_text:
        if in_str:
            if esc:
                esc = False
                buf.append(ch)
                continue
            if ch == "\\":
                esc = True
                buf.append(ch)
                continue
            if ch == "'":
                in_str = False
                buf.append(ch)
                continue
            buf.append(ch)
            continue
        if ch == "'":
            in_str = True
            buf.append(ch)
            continue
        if ch == ",":
            fields.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if buf:
        fields.append("".join(buf).strip())
    return fields


def _strip_sql_string(v: str) -> str:
    """Strip single quotes and unescape MySQL string."""
    if v.startswith("'") and v.endswith("'"):
        v = v[1:-1]
    return v.replace("\\'", "'").replace("\\\\", "\\")


def _to_int(v: str) -> int:
    if v == "NULL" or not v:
        return 0
    try:
        return int(v)
    except ValueError:
        return 0


def _to_float(v: str) -> float:
    if v == "NULL" or not v:
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def load_cadorim_terrapay(sql_path: str | Path) -> list[CadorimTPTx]:
    """Parse wallet_db_transactions.sql and return rows with TPFN ext_id."""
    sql_path = str(sql_path)
    if not os.path.exists(sql_path):
        return []
    with open(sql_path, "r", errors="ignore") as f:
        sql = f.read()

    # Only need rows containing 'TPFN' — much faster than full parse
    # Find INSERT INTO transactions VALUES (...), (...);
    insert_blocks = re.findall(
        r"INSERT INTO `transactions` VALUES (.*?);(?=\n|\Z)",
        sql, re.DOTALL,
    )

    out: list[CadorimTPTx] = []
    for block in insert_blocks:
        # Quick filter: only chunks containing TPFN
        if "TPFN" not in block:
            continue
        rows = _split_sql_values(block)
        for row_text in rows:
            if "TPFN" not in row_text:
                continue
            fields = _parse_row_fields(row_text)
            # Expected schema (28 columns per transactions table):
            # 0 id, 1 debitable_id, 2 debitable_type, 3 creditable_id, 4 creditable_type,
            # 5 amount, 6 debit_balance_before, 7 debit_balance_after,
            # 8 credit_balance_before, 9 credit_balance_after,
            # 10 frais, 11 commission, 12 tax, 13 type, 14 code, 15 status,
            # 16 accounting_status, 17 description, 18 reference, 19 file_path,
            # 20 details, 21 created_at, 22 updated_at, 23 created_by,
            # 24 exported, 25 external_transaction_id
            if len(fields) < 26:
                continue
            ext_id = _strip_sql_string(fields[25])
            if not ext_id.startswith("TPFN"):
                continue
            cadorim_id = _to_int(fields[0])
            debitable_id = _to_int(fields[1])
            debitable_type = _strip_sql_string(fields[2])
            creditable_id = _to_int(fields[3])
            creditable_type = _strip_sql_string(fields[4])
            amount = _to_float(fields[5])
            frais = _to_float(fields[10])
            type_ = _strip_sql_string(fields[13])
            status = _strip_sql_string(fields[15])
            description = _strip_sql_string(fields[17])
            reference = _strip_sql_string(fields[18])
            created_at_raw = _strip_sql_string(fields[21])
            date = created_at_raw[:10] if created_at_raw and created_at_raw != "NULL" else ""
            out.append(CadorimTPTx(
                cadorim_id=cadorim_id,
                tpfn=ext_id,
                date=date,
                amount_mru=amount,
                frais=frais,
                type=type_,
                status=status,
                reference=reference,
                description=description,
                creditable_id=creditable_id,
                creditable_type=creditable_type,
                debitable_id=debitable_id,
                debitable_type=debitable_type,
            ))
    out.sort(key=lambda x: x.date)
    return out


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/sessions/adoring-keen-clarke/mnt/Cadorim Accounting/cadorim-engine/data/wallet_db_transactions.sql"
    rows = load_cadorim_terrapay(path)
    print(f"Loaded {len(rows)} Cadorim TerraPay transactions (by TPFN)")
    if rows:
        from collections import Counter
        print(f"Date range : {rows[0].date} → {rows[-1].date}")
        types = Counter(r.type for r in rows)
        statuses = Counter(r.status for r in rows)
        print(f"By type    : {dict(types)}")
        print(f"By status  : {dict(statuses)}")
        # Monthly
        by_month = Counter(r.date[:7] for r in rows)
        sum_mru_m: dict[str, float] = {}
        for r in rows:
            m = r.date[:7]
            sum_mru_m[m] = sum_mru_m.get(m, 0.0) + r.amount_mru
        print(f"\nMonthly:")
        for m in sorted(by_month):
            print(f"  {m}: {by_month[m]:>4} tx, MRU {sum_mru_m[m]:>14,.2f}")
        print(f"\nTotal MRU: {sum(r.amount_mru for r in rows):,.2f}")
        print(f"\nSample 3:")
        for r in rows[:3]:
            print(f"  {r.date} {r.tpfn} type={r.type} MRU {r.amount_mru:>10,.2f} status={r.status}")
