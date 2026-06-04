"""BMI bank statement parser.

Parses Cadorim's BMI MRU account statements (PDF) and extracts the daily MRU
credits labeled "Virement reçu ordre de BRED Banque Populaire" — these are
the equivalent of Ria EUR settlements after BMI's internal EUR→MRU conversion.

Source PDFs are stored as 'Relevé de compte BMI <Month> <Year>.pdf' in the
workspace root. Each PDF covers one calendar month.

Output: one record per BRED credit line, with:
  - date       : YYYY-MM-DD (transaction date)
  - amount_mru : credited amount in MRU
  - balance    : running balance after this credit (MRU)
  - source_pdf : filename
  - line_idx   : position in the statement (for debugging)

Math note:
  Cadorim has TWO BMI IBANs:
    - MR13...3547223 : EUR account (target of Ria SWIFTs)
    - MR13...3501148 : MRU account (where BMI credits the converted amount)
  This parser reads MRU account statements. The EUR→MRU FX rate is derived
  externally by dividing daily MRU credits by daily EUR SWIFTs.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from typing import Iterable

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# French month names → MM
_MONTHS = {
    "janvier": "01", "fevrier": "02", "février": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06", "juillet": "07",
    "aout": "08", "août": "08", "septembre": "09", "octobre": "10",
    "novembre": "11", "decembre": "12", "décembre": "12",
    # abbreviations
    "jan": "01", "feb": "02", "fev": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09", "oct": "10",
    "nov": "11", "dec": "12",
}


def _normalize_date(day: str, month: str, year: str) -> str | None:
    mm = _MONTHS.get(month.lower())
    if not mm:
        return None
    return f"{year}-{mm}-{int(day):02d}"


@dataclass
class BMICredit:
    """One MRU credit line on the BMI MRU account from BRED (= a Ria settlement leg)."""

    date: str          # YYYY-MM-DD
    amount_mru: float
    balance: float
    source_pdf: str
    line_idx: int

    def to_dict(self) -> dict:
        return asdict(self)


# Pattern: "02/Mars/2026 Virement reçu ordre de BRED Banque Populaire 676,383.62 -2,322,788.59"
_CREDIT_PAT = re.compile(
    r"(\d{1,2})/([A-Za-zéèùûâêîôÉÈÙÛÂÊÎÔ]+)/(\d{4})\s+"
    r"Virement reçu ordre de BRED Banque Populaire\s+"
    r"([\d,]+\.\d+)\s+"
    r"(-?[\d,]+\.\d+)"
)


def parse_pdf(pdf_path: str) -> list[BMICredit]:
    """Parse one BMI PDF statement → list of MRU BRED credits."""
    if PdfReader is None:
        return []
    reader = PdfReader(pdf_path)
    full_text = "\n".join((p.extract_text() or "") for p in reader.pages)
    credits: list[BMICredit] = []
    for i, m in enumerate(_CREDIT_PAT.finditer(full_text)):
        day, month, year, amt_str, bal_str = m.groups()
        date = _normalize_date(day, month, year)
        if not date:
            continue
        try:
            amount = float(amt_str.replace(",", ""))
            balance = float(bal_str.replace(",", ""))
        except ValueError:
            continue
        credits.append(BMICredit(
            date=date,
            amount_mru=amount,
            balance=balance,
            source_pdf=os.path.basename(pdf_path),
            line_idx=i,
        ))
    return credits


def parse_directory(workspace_root: str) -> list[BMICredit]:
    """Scan workspace root for 'Relevé de compte ... BMI ....pdf' files
    and parse all BRED credits across them. Dedups by (date, amount, balance).
    """
    pdfs: list[str] = []
    for fname in os.listdir(workspace_root):
        if "BMI" in fname and fname.lower().endswith(".pdf") and "copy" not in fname.lower():
            pdfs.append(os.path.join(workspace_root, fname))
    pdfs.sort()

    seen: set[tuple] = set()
    all_credits: list[BMICredit] = []
    for p in pdfs:
        try:
            for c in parse_pdf(p):
                key = (c.date, round(c.amount_mru, 2), round(c.balance, 2))
                if key in seen:
                    continue
                seen.add(key)
                all_credits.append(c)
        except Exception:
            continue

    all_credits.sort(key=lambda x: (x.date, x.line_idx))
    return all_credits


if __name__ == "__main__":
    import sys
    workspace = sys.argv[1] if len(sys.argv) > 1 else "/sessions/adoring-keen-clarke/mnt/Cadorim Accounting"
    creds = parse_directory(workspace)
    print(f"Parsed {len(creds)} unique BMI BRED credits")
    if creds:
        total = sum(c.amount_mru for c in creds)
        print(f"  Date range : {creds[0].date} → {creds[-1].date}")
        print(f"  Total MRU  : {total:,.2f}")
        # Monthly distribution
        from collections import Counter
        by_month = Counter()
        sums_by_month: dict[str, float] = {}
        for c in creds:
            m = c.date[:7]
            by_month[m] += 1
            sums_by_month[m] = sums_by_month.get(m, 0) + c.amount_mru
        print("\nMonthly:")
        for m in sorted(by_month):
            print(f"  {m}: {by_month[m]:>3} credits, {sums_by_month[m]:>16,.2f} MRU")
