"""Settlement ingestion — parse Cado01/Cado02 Excel + Ria SWIFT confirmations.

Returns unified list of canonical settlement events sorted by date.
"""
import email
import glob
import html
import os
import re
from datetime import datetime
from email import policy

try:
    import openpyxl
except ImportError:
    openpyxl = None

# FX rates for settlement conversion (USDC≈USD≈1:1 for USDC, EUR rate varies)
FX_USD = 39.0   # MRU per USD (TerraPay settles in USDC, treated as USD equivalent)
FX_EUR = 42.5   # MRU per EUR (Ria settles in EUR via BMI)
FX_BRIDGE_USDC = 44.5  # Bridge USDC → MRU (Bridge EUR converts through USDC)

CADO02_ADDR = '0x983e66ea0b6f3bda147d523c9f70bd24d90ada27'
SETTLEMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'settlements')
CADORIM_BMI_IBAN = 'MR1300024000011000003547223'  # Cadorim BMI EUR — Ria settlement target


def _parse_date(val):
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d')
    if isinstance(val, str):
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y'):
            try:
                return datetime.strptime(val.strip(), fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
    return None


def parse_cado02_terrapay(from_date='2025-01-01', to_date='2026-04-01'):
    """Parse Cado02 Excel → TerraPay USDC inflows."""
    path = os.path.join(SETTLEMENTS_DIR, 'Cado02_Transaction_Dossier_2026.xlsx')
    if not os.path.exists(path) or not openpyxl:
        return []
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb['Entrées (IN)']
    events = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        date_val, token, amount, source, addr, tx_hash = (list(row) + [None]*6)[:6]
        date = _parse_date(date_val)
        if not date or not amount or str(token) != 'USDC':
            continue
        if date < from_date or date >= to_date:
            continue
        amt = float(amount)
        events.append({
            "id": f"S-terrapay-{len(events)+1}",
            "partner_code": "terrapay",
            "date": date,
            "date_s": date,  # engine compat
            "Par_l": "terrapay",
            "Bank_t": "eth_cado02",
            "amount_foreign": amt,
            "Amount_s": amt,
            "currency": "USD",
            "Cur_k": "USD",
            "fx_rate_settlement": FX_USD,
            "fx_settlement_rate": FX_USD,
            "fx_reference_rate": FX_USD,
            "amount_mru": round(amt * FX_USD, 2),
            "reference": str(tx_hash or '')[:66],
            "source": "cado02_excel",
            "source_file": "Cado02_Transaction_Dossier_2026.xlsx",
        })
    wb.close()
    return events


def parse_cado01_bridge(from_date='2025-01-01', to_date='2026-04-01'):
    """Parse Cado01 Excel → Bridge settlements (exclude Cado02 transfers)."""
    path = os.path.join(SETTLEMENTS_DIR, 'Cado01_Transaction_Dossier_2026.xlsx')
    if not os.path.exists(path) or not openpyxl:
        return []
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb['Entrées (IN)']
    events = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        date_val, token, amount, source, addr, tx_hash = (list(row) + [None]*6)[:6]
        date = _parse_date(date_val)
        if not date or not amount:
            continue
        if date < from_date or date >= to_date:
            continue
        # Exclude Cado02 → Cado01 transfers (those are TerraPay internal moves)
        addr_str = (str(addr) or '').lower()
        source_str = (str(source) or '').lower()
        if CADO02_ADDR in addr_str or 'cado02' in source_str:
            continue
        amt = float(amount)
        events.append({
            "id": f"S-bridge-{len(events)+1}",
            "partner_code": "bridge",
            "date": date,
            "date_s": date,
            "Par_l": "bridge",
            "Bank_t": "eth_cado01",
            "amount_foreign": amt,
            "Amount_s": amt,
            "currency": "USD",
            "Cur_k": "USD",
            "fx_rate_settlement": FX_BRIDGE_USDC,
            "fx_settlement_rate": FX_BRIDGE_USDC,
            "fx_reference_rate": 44.0,
            "amount_mru": round(amt * FX_BRIDGE_USDC, 2),
            "reference": str(tx_hash or '')[:66],
            "source": "cado01_excel",
            "source_file": "Cado01_Transaction_Dossier_2026.xlsx",
        })
    wb.close()
    return events


def parse_ria_swift(from_date='2025-01-01', to_date='2026-04-01'):
    """Parse Ria SWIFT MX confirmation emails → EUR settlements via BMI.

    Scans all mail/ subfolders of data/settlements/, dedupes by UETR.
    """
    from .parsers.ria_swift import parse_all_mail_folders
    setts = parse_all_mail_folders(SETTLEMENTS_DIR, from_date, to_date, fx_eur=FX_EUR)
    return [s.to_dict() for s in setts]


def ingest_all(from_date='2025-01-01', to_date='2026-04-01'):
    """Ingest all available settlement data. Returns sorted list."""
    all_setts = []

    # TerraPay (Cado02)
    tp = parse_cado02_terrapay(from_date, to_date)
    all_setts.extend(tp)

    # Bridge (Cado01)
    br = parse_cado01_bridge(from_date, to_date)
    all_setts.extend(br)

    # Ria (BMI SWIFT confirmations)
    ria = parse_ria_swift(from_date, to_date)
    all_setts.extend(ria)

    # Juba (BPM) — TODO: parse BPM statements

    all_setts.sort(key=lambda s: s['date'])

    ria_eur = sum(s['amount_foreign'] for s in ria)
    print(f"  Settlements ingested: {len(all_setts)} total")
    print(f"    TerraPay (Cado02): {len(tp)}")
    print(f"    Bridge (Cado01): {len(br)}")
    print(f"    Ria (BMI SWIFT): {len(ria)} ({ria_eur:,.2f} EUR)")
    print(f"    Juba (BPM): 0 (stub)")

    return all_setts
