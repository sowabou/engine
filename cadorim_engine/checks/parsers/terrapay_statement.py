"""TerraPay statement parser — handles 3 different file formats.

The 3 known TerraPay statements have inconsistent headers/layouts but all
contain per-transaction lines with a TPFN reference and USD amount:

  1. `Terrapay Account Statement Demcembre 2025.xlsx`
     Headers: date | Transaction label | Amount of the transfer received in USD | A 0.5% fee... | Amount of bank transfers | balance
     Each TPFN row = 1 transaction with both transfer + fee on same row.

  2. `Releve Terrapay transfert recu 01-02.2026 au 28-02-2026.xlsx`
     Headers row 3: date | Id transactio +fees 0.5% | Mouvement debit | Mouvment Credt en usd | D(usd) | C(usd)
     Each TPFN has 2 rows: transfer row + fee row (column "Mouvement debit").

  3. `releve terrapay recu du 01.03.26 au 30.04.26.xlsx`
     Headers row 2: Date | ID Transaction | Libellé | Débit (USD) | Crédit (USD) | Solde Débiteur | Solde Créditeur
     Each TPFN has 2 rows: "Virement sortant" + "Frais 0.5%".

Output: list of `TerraPaySaleTransaction` — one entry per TPFN ID with
date, TPFN, amount (gross USD transfer), fee, source_file.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable

try:
    import openpyxl
except ImportError:
    openpyxl = None


@dataclass
class TerraPayTx:
    """One TerraPay-side transaction (per TPFN reference)."""

    date: str               # YYYY-MM-DD
    tpfn: str               # TPFN000XXXXXXXXX
    transfer_usd: float     # gross transfer amount in USD
    fee_usd: float          # 0.5% fee (separate line in some files)
    source_file: str

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_date(v, period_from: str | None = None, period_to: str | None = None) -> str | None:
    """Parse a date with smart DD/MM vs MM/DD disambiguation.

    Tries DD/MM first. If the result is OUTSIDE the expected file period
    (when given), tries MM/DD as fallback. This handles inconsistent Excel
    files that mix the two formats within the same sheet.
    """
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()

    def _in_period(date_str: str) -> bool:
        if not date_str:
            return False
        if period_from and date_str < period_from:
            return False
        if period_to and date_str > period_to:
            return False
        return True

    # Try DD/MM first (French standard)
    candidates_dd_mm = []
    candidates_mm_dd = []
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            d = datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            candidates_dd_mm.append(d)
            break
        except ValueError:
            continue
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            d = datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            candidates_mm_dd.append(d)
            break
        except ValueError:
            continue

    # Prefer DD/MM in period
    for d in candidates_dd_mm:
        if _in_period(d):
            return d
    # Fallback to MM/DD in period (mixed-format files)
    for d in candidates_mm_dd:
        if _in_period(d):
            return d
    # If no period given, return DD/MM
    if candidates_dd_mm:
        return candidates_dd_mm[0]
    if candidates_mm_dd:
        return candidates_mm_dd[0]
    return None


def _is_tpfn(v) -> bool:
    return isinstance(v, str) and v.startswith("TPFN")


def _to_float(v) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_dec2025(path: str) -> list[TerraPayTx]:
    """Format 1: Terrapay Account Statement Demcembre 2025.xlsx (span: 2025)"""
    if openpyxl is None or not os.path.exists(path):
        return []
    # Period bounds for this file (year-end statement spanning 2025)
    period_from, period_to = "2025-01-01", "2025-12-31"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    out: list[TerraPayTx] = []
    for r in rows[1:]:
        if not r:
            continue
        date_v, label, transfer, fee, bank_xfer, bal = (list(r) + [None] * 6)[:6]
        if not _is_tpfn(label):
            continue
        date = _parse_date(date_v, period_from, period_to)
        if not date:
            continue
        out.append(TerraPayTx(
            date=date,
            tpfn=str(label).strip(),
            transfer_usd=_to_float(transfer),
            fee_usd=_to_float(fee),
            source_file=os.path.basename(path),
        ))
    return out


def parse_feb2026(path: str) -> list[TerraPayTx]:
    """Format 2: Releve Terrapay transfert recu 01-02.2026 au 28-02-2026.xlsx (Feb 2026)"""
    if openpyxl is None or not os.path.exists(path):
        return []
    period_from, period_to = "2026-02-01", "2026-02-28"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Feuil1"] if "Feuil1" in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    out: dict[str, TerraPayTx] = {}  # tpfn → tx
    for r in rows[4:]:  # skip header
        if not r:
            continue
        date_v = r[0]
        tpfn = r[1]
        debit = r[2]
        if not _is_tpfn(tpfn):
            continue
        date = _parse_date(date_v, period_from, period_to)
        if not date:
            continue
        tpfn = str(tpfn).strip()
        amount = _to_float(debit)
        if tpfn not in out:
            # first occurrence = transfer
            out[tpfn] = TerraPayTx(
                date=date, tpfn=tpfn, transfer_usd=amount,
                fee_usd=0.0, source_file=os.path.basename(path),
            )
        else:
            # second occurrence = fee
            out[tpfn].fee_usd = amount
    return list(out.values())


def parse_marapr2026(path: str) -> list[TerraPayTx]:
    """Format 3: releve terrapay recu du 01.03.26 au 30.04.26.xlsx (Mar-Apr 2026)"""
    if openpyxl is None or not os.path.exists(path):
        return []
    period_from, period_to = "2026-03-01", "2026-04-30"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Relevé de Compte"] if "Relevé de Compte" in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    out: dict[str, TerraPayTx] = {}
    last_date: str | None = None
    for r in rows[3:]:  # skip headers + initial balance
        if not r:
            continue
        date_v, tpfn, label, debit, credit, sd, sc = (list(r) + [None] * 7)[:7]
        if not _is_tpfn(tpfn):
            continue
        date = _parse_date(date_v, period_from, period_to) or last_date
        if date_v:
            last_date = _parse_date(date_v, period_from, period_to)
        if not date:
            continue
        tpfn = str(tpfn).strip()
        amount = _to_float(debit)
        label_str = str(label or "").lower()
        if "frais" in label_str or "fee" in label_str:
            if tpfn in out:
                out[tpfn].fee_usd = amount
            else:
                # fee row without prior transfer row — rare
                out[tpfn] = TerraPayTx(
                    date=date, tpfn=tpfn, transfer_usd=0.0,
                    fee_usd=amount, source_file=os.path.basename(path),
                )
        else:
            # transfer row
            if tpfn in out:
                out[tpfn].transfer_usd = amount
            else:
                out[tpfn] = TerraPayTx(
                    date=date, tpfn=tpfn, transfer_usd=amount,
                    fee_usd=0.0, source_file=os.path.basename(path),
                )
    return list(out.values())


def parse_all_terrapay_statements(data_dir: str) -> list[TerraPayTx]:
    """Parse all 3 TerraPay statement files in the data directory.

    Dedupes by TPFN (last write wins for the same id).
    """
    files = {
        "dec2025": "Terrapay Account Statement Demcembre 2025.xlsx",
        "feb2026": "Releve Terrapay transfert recu 01-02.2026 au 28-02-2026.xlsx",
        "marapr2026": "releve terrapay recu du 01.03.26 au 30.04.26.xlsx",
    }
    seen: dict[str, TerraPayTx] = {}
    for label, fname in files.items():
        path = os.path.join(data_dir, fname)
        if not os.path.exists(path):
            continue
        if label == "dec2025":
            rows = parse_dec2025(path)
        elif label == "feb2026":
            rows = parse_feb2026(path)
        else:
            rows = parse_marapr2026(path)
        for t in rows:
            seen[t.tpfn] = t
    return sorted(seen.values(), key=lambda x: x.date)


if __name__ == "__main__":
    import sys
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "/sessions/adoring-keen-clarke/mnt/Cadorim Accounting/cadorim-engine/data"
    txs = parse_all_terrapay_statements(data_dir)
    print(f"Parsed {len(txs)} unique TerraPay transactions")
    if txs:
        from collections import Counter
        by_month = Counter(t.date[:7] for t in txs)
        print(f"Date range: {txs[0].date} → {txs[-1].date}")
        print(f"\nBy month:")
        for m in sorted(by_month):
            month_txs = [t for t in txs if t.date.startswith(m)]
            total_usd = sum(t.transfer_usd for t in month_txs)
            total_fee = sum(t.fee_usd for t in month_txs)
            print(f"  {m}: {by_month[m]:>4} tx  transfer USD {total_usd:>12,.2f}  fee USD {total_fee:>10,.2f}")
        print(f"\nTotal transfer USD: {sum(t.transfer_usd for t in txs):,.2f}")
        print(f"Total fee USD     : {sum(t.fee_usd for t in txs):,.2f}")
        print(f"\nSample 3 transactions:")
        for t in txs[:3]:
            print(f"  {t.date} {t.tpfn} USD {t.transfer_usd:>8.2f} fee {t.fee_usd:>6.4f}")
