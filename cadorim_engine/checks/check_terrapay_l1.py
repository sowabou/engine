"""Check TerraPay L1 — daily reconciliation TerraPay statement ↔ Cadorim DB.

Pure math, per-day:
  TerraPay_d = { transactions in TerraPay statement with date = d }
  Cadorim_d  = { transactions in wallet_db_transactions with TPFN ext_id and date = d }

Match key: TPFN (TerraPay reference, present on both sides).

Per-transaction status:
  MATCH              ⇔ ∃ t_t ∈ TerraPay_d, t_c ∈ Cadorim_d : TPFN(t_t) = TPFN(t_c)
  MATCH_DELAYED      ⇔ TPFN found in Cadorim on a different date (typical T+1/T+2)
  MISSING_CADORIM    ⇔ TerraPay reports it, Cadorim has NO record (real anomaly)
  PENDING_CADORIM    ⇔ TerraPay reports it, Cadorim doesn't yet (within window)
  MISSING_TERRAPAY   ⇔ Cadorim has TPFN, but no matching TerraPay record (rare —
                        means Cadorim journalized with a TPFN that TerraPay never sent)
  AMOUNT_MISMATCH    ⇔ matched but USD×FX ≠ MRU within tolerance

Day-level verdict:
  GREEN  — all matched (immediate or delayed)
  AMBER  — pending within window
  RED    — missing or material mismatch
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .parsers.terrapay_statement import parse_all_terrapay_statements, TerraPayTx
from .terrapay_cadorim_loader import load_cadorim_terrapay, CadorimTPTx

# Tunables
FX_USD_CADORIM = 39.5          # Cadorim's L1 USD→MRU rate (per Dr Neine)
COMMISSION_RATE = 0.005        # 0.5% — TerraPay's commission charged to Cadorim
EPS_USD = 1.0                  # USD diff tolerance per transaction
EPS_PCT = 0.10                 # 10% tolerance for amount comparison

# Status
STATUS_MATCH = "MATCH"
STATUS_MATCH_DELAYED = "MATCH_DELAYED"
STATUS_MISSING_CADORIM = "MISSING_CADORIM"
STATUS_PENDING_CADORIM = "PENDING_CADORIM"
STATUS_MISSING_TERRAPAY = "MISSING_TERRAPAY"
STATUS_AMOUNT_MISMATCH = "AMOUNT_MISMATCH"

VERDICT_GREEN = "GREEN"
VERDICT_AMBER = "AMBER"
VERDICT_RED = "RED"


@dataclass
class TPLine:
    """One row in the per-transaction comparison table."""

    tpfn: str
    status: str
    date: str = ""               # primary date (Cadorim if matched, else TerraPay)
    terrapay_date: str = ""
    cadorim_date: str = ""
    usd_terrapay: float = 0.0
    mru_cadorim: float = 0.0
    fee_terrapay: float = 0.0
    frais_cadorim: float = 0.0
    fx_implicit: float = 0.0     # mru_cadorim / usd_terrapay
    diff_amount_usd: float = 0.0
    delay_days: int = 0
    cadorim_type: str = ""
    cadorim_ref: str = ""


@dataclass
class TPCheckReport:
    date: str
    verdict: str
    message: str
    n_terrapay: int
    n_cadorim: int
    n_matched: int
    n_matched_immediate: int
    n_matched_delayed: int
    n_missing_in_cadorim: int
    n_missing_in_terrapay: int
    n_pending_cadorim: int
    n_amount_mismatch: int
    usd_total_terrapay: float
    mru_total_cadorim: float
    fee_total_terrapay: float
    frais_total_cadorim: float
    lines: list[TPLine] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lines"] = [asdict(l) for l in self.lines]
        return d


def _days_between(a: str, b: str) -> int:
    fa = datetime.strptime(a, "%Y-%m-%d")
    fb = datetime.strptime(b, "%Y-%m-%d")
    return abs((fb - fa).days)


def _build_pin_index(
    terrapay_by_date: dict[str, list[TerraPayTx]]
) -> dict[str, list[tuple[str, TerraPayTx]]]:
    """TPFN → list of (date, terrapay_tx) across all dates."""
    idx: dict[str, list[tuple[str, TerraPayTx]]] = {}
    for d, rows in terrapay_by_date.items():
        for t in rows:
            idx.setdefault(t.tpfn, []).append((d, t))
    return idx


def compare_day(
    date: str,
    terrapay_by_date: dict[str, list[TerraPayTx]],
    cadorim_by_date_pin: dict[str, dict[str, CadorimTPTx]],
    pin_to_all_cadorim_dates: dict[str, list[tuple[str, CadorimTPTx]]],
    fx_usd: float = FX_USD_CADORIM,
    eps_pct: float = EPS_PCT,
) -> TPCheckReport:
    """Compare TerraPay vs Cadorim for one date by TPFN."""
    tp_day = terrapay_by_date.get(date, [])
    cad_day = cadorim_by_date_pin.get(date, {})  # tpfn → CadorimTPTx

    tp_by_pin = {t.tpfn: t for t in tp_day}

    lines: list[TPLine] = []
    n_match = n_imm = n_del = n_miss_cad = n_miss_tp = n_pending = n_amt_mis = 0

    today = datetime.utcnow().strftime("%Y-%m-%d")

    all_pins = set(tp_by_pin.keys()) | set(cad_day.keys())
    for pin in sorted(all_pins):
        tp = tp_by_pin.get(pin)
        cd = cad_day.get(pin)
        if tp and cd:
            # Same day match
            fx = cd.amount_mru / tp.transfer_usd if tp.transfer_usd > 0 else 0.0
            expected_mru = tp.transfer_usd * fx_usd
            diff_usd = (cd.amount_mru - expected_mru) / fx_usd  # express diff in USD
            n_match += 1
            n_imm += 1
            status = STATUS_MATCH
            if expected_mru > 0 and abs(cd.amount_mru - expected_mru) / expected_mru > eps_pct:
                status = STATUS_AMOUNT_MISMATCH
                n_amt_mis += 1
                n_imm -= 1
                n_match -= 1
            lines.append(TPLine(
                tpfn=pin, status=status, date=date,
                terrapay_date=date, cadorim_date=date,
                usd_terrapay=tp.transfer_usd, mru_cadorim=cd.amount_mru,
                fee_terrapay=tp.fee_usd, frais_cadorim=cd.frais,
                fx_implicit=round(fx, 4), diff_amount_usd=round(diff_usd, 2),
                delay_days=0, cadorim_type=cd.type, cadorim_ref=cd.reference,
            ))
        elif tp and not cd:
            # TerraPay has it but Cadorim doesn't on this date
            # Scan full Cadorim history for TPFN
            found = pin_to_all_cadorim_dates.get(pin, [])
            if found:
                # MATCH_DELAYED — Cadorim journalized on a different date
                d_cad, c_cad = min(found, key=lambda x: _days_between(date, x[0]))
                delay = _days_between(date, d_cad)
                fx = c_cad.amount_mru / tp.transfer_usd if tp.transfer_usd > 0 else 0.0
                n_match += 1
                n_del += 1
                lines.append(TPLine(
                    tpfn=pin, status=STATUS_MATCH_DELAYED, date=date,
                    terrapay_date=date, cadorim_date=d_cad,
                    usd_terrapay=tp.transfer_usd, mru_cadorim=c_cad.amount_mru,
                    fee_terrapay=tp.fee_usd, frais_cadorim=c_cad.frais,
                    fx_implicit=round(fx, 4),
                    delay_days=delay, cadorim_type=c_cad.type, cadorim_ref=c_cad.reference,
                ))
            else:
                # Real MISSING_CADORIM
                n_miss_cad += 1
                lines.append(TPLine(
                    tpfn=pin, status=STATUS_MISSING_CADORIM, date=date,
                    terrapay_date=date,
                    usd_terrapay=tp.transfer_usd, fee_terrapay=tp.fee_usd,
                ))
        elif cd and not tp:
            # Cadorim has it but TerraPay doesn't on this date
            n_miss_tp += 1
            lines.append(TPLine(
                tpfn=pin, status=STATUS_MISSING_TERRAPAY, date=date,
                cadorim_date=date, mru_cadorim=cd.amount_mru,
                frais_cadorim=cd.frais, cadorim_type=cd.type, cadorim_ref=cd.reference,
            ))

    # Sort: anomalies first
    rank = {
        STATUS_MISSING_CADORIM: 0,
        STATUS_AMOUNT_MISMATCH: 1,
        STATUS_MISSING_TERRAPAY: 2,
        STATUS_MATCH_DELAYED: 3,
        STATUS_MATCH: 4,
    }
    lines.sort(key=lambda l: (rank.get(l.status, 9), l.tpfn))

    usd_total = sum(t.transfer_usd for t in tp_day)
    mru_total = sum(c.amount_mru for c in cad_day.values())
    fee_total = sum(t.fee_usd for t in tp_day)
    frais_total = sum(c.frais for c in cad_day.values())

    # Verdict
    n_t = len(tp_day)
    n_c = len(cad_day)
    if n_t == 0 and n_c == 0:
        verdict, msg = VERDICT_GREEN, f"Aucune transaction TerraPay ni Cadorim le {date}."
    else:
        real = n_miss_cad + n_miss_tp + n_amt_mis
        delayed_note = f", {n_del} confirmées en retard" if n_del else ""
        if real == 0 and n_pending == 0:
            verdict = VERDICT_GREEN
            msg = f"Journée {date} : {n_match} matchées{delayed_note}. Aucune anomalie."
        elif real == 0:
            verdict = VERDICT_AMBER
            msg = f"Journée {date} : {n_match} matchées{delayed_note}, {n_pending} en attente."
        else:
            verdict = VERDICT_RED
            msg = (f"Journée {date} : {n_t} TerraPay vs {n_c} Cadorim — "
                   f"{n_miss_cad} manquantes Cadorim, {n_miss_tp} manquantes TerraPay, "
                   f"{n_amt_mis} écarts.")

    return TPCheckReport(
        date=date, verdict=verdict, message=msg,
        n_terrapay=n_t, n_cadorim=n_c,
        n_matched=n_match, n_matched_immediate=n_imm, n_matched_delayed=n_del,
        n_missing_in_cadorim=n_miss_cad, n_missing_in_terrapay=n_miss_tp,
        n_pending_cadorim=n_pending, n_amount_mismatch=n_amt_mis,
        usd_total_terrapay=round(usd_total, 2),
        mru_total_cadorim=round(mru_total, 2),
        fee_total_terrapay=round(fee_total, 4),
        frais_total_cadorim=round(frais_total, 2),
        lines=lines,
    )


def load_data(workspace_root: str) -> tuple[
    dict[str, list[TerraPayTx]],
    dict[str, dict[str, CadorimTPTx]],
    dict[str, list[tuple[str, CadorimTPTx]]],
]:
    """Load both sides and build indexed structures."""
    data_dir = os.path.join(workspace_root, "cadorim-engine", "data")
    terrapay_txs = parse_all_terrapay_statements(data_dir)
    cadorim_txs = load_cadorim_terrapay(os.path.join(data_dir, "wallet_db_transactions.sql"))

    # Index TerraPay by date
    terrapay_by_date: dict[str, list[TerraPayTx]] = {}
    for t in terrapay_txs:
        terrapay_by_date.setdefault(t.date, []).append(t)

    # Index Cadorim by date + tpfn
    cadorim_by_date_pin: dict[str, dict[str, CadorimTPTx]] = {}
    pin_to_all_dates: dict[str, list[tuple[str, CadorimTPTx]]] = {}
    for c in cadorim_txs:
        cadorim_by_date_pin.setdefault(c.date, {})[c.tpfn] = c
        pin_to_all_dates.setdefault(c.tpfn, []).append((c.date, c))

    return terrapay_by_date, cadorim_by_date_pin, pin_to_all_dates


if __name__ == "__main__":
    import sys
    workspace = "/sessions/adoring-keen-clarke/mnt/Cadorim Accounting"
    tp_by_date, cad_by_date_pin, pin_all = load_data(workspace)
    print(f"TerraPay dates with data : {len(tp_by_date)}")
    print(f"Cadorim dates with data  : {len(cad_by_date_pin)}")
    target = sys.argv[1] if len(sys.argv) > 1 else sorted(tp_by_date.keys() & cad_by_date_pin.keys())[-1]
    print(f"\nChecking date: {target}")
    r = compare_day(target, tp_by_date, cad_by_date_pin, pin_all)
    print(f"  Verdict       : {r.verdict}")
    print(f"  Message       : {r.message}")
    print(f"  TerraPay tx   : {r.n_terrapay}  USD {r.usd_total_terrapay:,.2f}")
    print(f"  Cadorim tx    : {r.n_cadorim}  MRU {r.mru_total_cadorim:,.2f}")
    print(f"  Matched (imm/del): {r.n_matched_immediate}/{r.n_matched_delayed}")
    print(f"  Missing Cad   : {r.n_missing_in_cadorim}")
    print(f"  Missing TP    : {r.n_missing_in_terrapay}")
    print(f"  Amt mismatch  : {r.n_amount_mismatch}")
    if r.lines[:5]:
        print(f"\n  First 5 lines:")
        for l in r.lines[:5]:
            print(f"    {l.status:<22} {l.tpfn} usd_tp={l.usd_terrapay:>7.2f} mru_cad={l.mru_cadorim:>10.2f} fx={l.fx_implicit}")
