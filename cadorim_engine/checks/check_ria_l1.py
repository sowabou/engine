"""Check Ria L1 — daily reconciliation Ria statement vs Cadorim partner DB.

Pure math: given a date d, compare two records of the SAME Ria transactions:
  Ria_d     = Ria's official statement      (data/ria/Transaction.xlsx)
  Cadorim_d = Cadorim's partner-DB record   (partner_db.ria_transactions)

Join key: PIN (Ria Personal Identification Number) — present natively on BOTH
sides, so no text extraction is needed.

Because both sources record the same payout, the comparison is a near-exact
reconciliation in MRU (amount) and EUR (commission) — there is NO FX margin
band (that only made sense when comparing Cadorim's client-facing EUR ledger
against Ria).

Read-only: no mutation of any source.

NOTE on field names: TxLine/CheckReport keep the historical `eur_*` field names
for JSON/CSV stability, but the amount fields now carry MRU values
(commission fields stay EUR). The UI labels reflect the real units.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .ria_corresp_loader import load_ria_by_date

# Tolerances. Both sides record the same payout → expect a tight match.
EPS_AMOUNT_MRU = 1.00       # absolute floor, MRU
EPS_AMOUNT_RATIO = 0.005    # 0.5% relative, whichever is larger
EPS_COMMISSION_EUR = 0.10   # EUR

# A Cadorim tx not yet on a Ria statement stays PENDING_RIA indefinitely until a
# statement confirms it. When searching for a late confirmation (MATCH_DELAYED),
# we scan the FULL history for the PIN, not a fixed window.
CONFIRMATION_WINDOW_DAYS = 7  # informational only (UI staleness flag)

# Status codes
STATUS_MATCH = "MATCH"
STATUS_MATCH_DELAYED = "MATCH_DELAYED"
STATUS_MISSING_CADORIM = "MISSING_CADORIM"
STATUS_PENDING_RIA = "PENDING_RIA"
STATUS_MISSING_RIA = "MISSING_RIA"        # reserved — manual closure only
STATUS_AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
STATUS_COMM_MISMATCH = "COMM_MISMATCH"

# Day-level verdict
VERDICT_GREEN = "GREEN"
VERDICT_AMBER = "AMBER"
VERDICT_RED = "RED"


@dataclass
class TxLine:
    """One row in the per-transaction comparison table.

    `eur_ria` / `eur_cadorim` / `diff_amount` carry MRU amounts.
    `comm_eur_ria` / `comm_eur_cadorim` / `diff_commission` carry EUR.
    """

    pin: str
    status: str
    seq: str = ""
    beneficiary: str = ""
    eur_ria: float = 0.0          # MRU (Ria order amount)
    eur_cadorim: float = 0.0      # MRU (Cadorim BeneAmount)
    comm_eur_ria: float = 0.0     # EUR
    comm_eur_cadorim: float = 0.0  # EUR
    local_par_n: str = ""
    cadorim_id: str = ""
    diff_amount: float = 0.0       # MRU
    diff_commission: float = 0.0   # EUR
    delay_days: int = 0
    age_days: int = 0
    confirmed_at: str = ""
    journal_date: str = ""


@dataclass
class CheckReport:
    """Full report for one date. Amount totals are MRU; commission totals EUR."""

    date: str
    verdict: str
    message: str
    n_ria: int
    n_cadorim: int
    n_matched: int
    n_matched_immediate: int
    n_matched_delayed: int
    n_missing_in_cadorim: int
    n_missing_in_ria: int
    n_pending_ria: int
    n_amount_mismatch: int
    n_commission_mismatch: int
    eur_total_ria: float          # MRU total (Ria side)
    eur_total_cadorim_est: float  # MRU total (Cadorim side)
    comm_eur_total_ria: float     # EUR
    comm_mru_total_cadorim: float  # EUR (Cadorim commission)
    window_days: int = CONFIRMATION_WINDOW_DAYS
    lines: list[TxLine] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lines"] = [asdict(l) for l in self.lines]
        return d


def _make_action(status: str) -> str:
    return {
        STATUS_MISSING_CADORIM: "Transaction présente sur le relevé Ria mais absente de la DB partenaire Cadorim. Vérifier l'intégration ou une référence alternative.",
        STATUS_PENDING_RIA: "Transaction enregistrée côté Cadorim mais pas encore sur le relevé Ria. Reste en attente jusqu'à confirmation Ria.",
        STATUS_AMOUNT_MISMATCH: f"Écart montant > {EPS_AMOUNT_MRU} MRU (ou {EPS_AMOUNT_RATIO:.1%}) entre Ria et Cadorim. Vérifier le montant payé.",
        STATUS_COMM_MISMATCH: f"Écart commission > {EPS_COMMISSION_EUR} EUR. Vérifier le tarif Ria appliqué.",
    }.get(status, "")


def _amount_tol(reference_mru: float) -> float:
    return max(EPS_AMOUNT_MRU, abs(reference_mru) * EPS_AMOUNT_RATIO)


def _days_between(a: str, b: str) -> int:
    fa = datetime.strptime(a, "%Y-%m-%d")
    fb = datetime.strptime(b, "%Y-%m-%d")
    return abs((fb - fa).days)


def _build_pin_index(rows: list[dict], date_key: str) -> dict[str, list[tuple[str, dict]]]:
    """PIN → sorted list of (date, row) across all dates."""
    idx: dict[str, list[tuple[str, dict]]] = {}
    for r in rows:
        pin = str(r.get("pin", "")).strip()
        d = str(r.get(date_key, ""))[:10]
        if not pin or not d:
            continue
        idx.setdefault(pin, []).append((d, r))
    for pin in idx:
        idx[pin].sort(key=lambda x: x[0])
    return idx


def _ria_all_rows(ria_by_date: dict[str, list[dict]]) -> list[dict]:
    out: list[dict] = []
    for d, rows in ria_by_date.items():
        if isinstance(rows, list):
            out.extend(rows)
    return out


def compare_day(
    date: str,
    cadorim_transactions: list[dict],
    ria_by_date: dict[str, list[dict]] | None = None,
    eps_amount_mru: float = EPS_AMOUNT_MRU,
    eps_commission: float = EPS_COMMISSION_EUR,
    window_days: int = CONFIRMATION_WINDOW_DAYS,
    today: str | None = None,
) -> CheckReport:
    """Compare Ria-statement vs Cadorim-partner-DB transactions for one date.

    Parameters
    ----------
    date : "YYYY-MM-DD"
    cadorim_transactions : Cadorim partner-DB rows (from ria_db_loader.load_cadorim_ria),
                           full set — filtered internally by date.
    ria_by_date : {date: [ria rows]} from the Excel statement (loaded on demand).
    """
    if ria_by_date is None:
        ria_by_date = load_ria_by_date()
    if today is None:
        today = datetime.utcnow().strftime("%Y-%m-%d")

    ria_all = _ria_all_rows(ria_by_date)
    ria_pin_index = _build_pin_index(ria_all, "date")
    cad_pin_index = _build_pin_index(cadorim_transactions, "date")

    ria_day = ria_by_date.get(date, [])
    cad_day = [c for c in cadorim_transactions if str(c.get("date", ""))[:10] == date]

    ria_by_pin = {str(r["pin"]).strip(): r for r in ria_day if r.get("pin")}
    cad_by_pin = {str(c["pin"]).strip(): c for c in cad_day if c.get("pin")}

    lines: list[TxLine] = []
    n_match = n_match_imm = n_match_del = 0
    n_miss_cad = n_miss_ria = n_pending = n_amt_mis = n_comm_mis = 0

    all_pins = set(ria_by_pin) | set(cad_by_pin)
    for pin in sorted(all_pins):
        r = ria_by_pin.get(pin)
        c = cad_by_pin.get(pin)

        if r and c:
            amt_r = float(r.get("order_amt_mru", 0) or 0)
            amt_c = float(c.get("amount_mru", 0) or 0)
            comm_r = float(r.get("commission_amt", 0) or 0)
            comm_c = float(c.get("commission_amt", 0) or 0)
            diff_amt = amt_c - amt_r
            diff_comm = comm_c - comm_r

            if abs(diff_amt) > _amount_tol(amt_r):
                status = STATUS_AMOUNT_MISMATCH
                n_amt_mis += 1
            elif abs(diff_comm) > eps_commission:
                status = STATUS_COMM_MISMATCH
                n_comm_mis += 1
            else:
                status = STATUS_MATCH
                n_match += 1
                n_match_imm += 1

            lines.append(TxLine(
                pin=pin, seq=r.get("seq", ""), status=status,
                beneficiary=r.get("beneficiary", "") or c.get("beneficiary", ""),
                eur_ria=round(amt_r, 2), eur_cadorim=round(amt_c, 2),
                comm_eur_ria=round(comm_r, 2), comm_eur_cadorim=round(comm_c, 2),
                local_par_n=c.get("local_par_n", "") or "",
                cadorim_id=str(c.get("id", "") or ""),
                diff_amount=round(diff_amt, 2),
                diff_commission=round(diff_comm, 2),
            ))

        elif r and not c:
            # Ria reported it; no Cadorim record same day. Scan Cadorim history.
            hist = [h for h in cad_pin_index.get(pin, []) if h[0] != date]
            if hist:
                d_cad, c_cad = min(hist, key=lambda x: _days_between(date, x[0]))
                n_match += 1
                n_match_del += 1
                lines.append(TxLine(
                    pin=pin, seq=r.get("seq", ""), status=STATUS_MATCH_DELAYED,
                    beneficiary=r.get("beneficiary", ""),
                    eur_ria=round(float(r.get("order_amt_mru", 0) or 0), 2),
                    eur_cadorim=round(float(c_cad.get("amount_mru", 0) or 0), 2),
                    comm_eur_ria=round(float(r.get("commission_amt", 0) or 0), 2),
                    comm_eur_cadorim=round(float(c_cad.get("commission_amt", 0) or 0), 2),
                    local_par_n=c_cad.get("local_par_n", "") or "",
                    cadorim_id=str(c_cad.get("id", "") or ""),
                    delay_days=_days_between(date, d_cad),
                    confirmed_at=d_cad, journal_date=date,
                ))
            else:
                n_miss_cad += 1
                lines.append(TxLine(
                    pin=pin, seq=r.get("seq", ""), status=STATUS_MISSING_CADORIM,
                    beneficiary=r.get("beneficiary", ""),
                    eur_ria=round(float(r.get("order_amt_mru", 0) or 0), 2),
                    comm_eur_ria=round(float(r.get("commission_amt", 0) or 0), 2),
                    journal_date=date,
                ))

        else:  # c and not r
            age = _days_between(date, today)
            hist = [h for h in ria_pin_index.get(pin, []) if h[0] != date]
            if hist:
                d_ria, r_ria = min(hist, key=lambda x: _days_between(date, x[0]))
                n_match += 1
                n_match_del += 1
                lines.append(TxLine(
                    pin=pin, seq=r_ria.get("seq", ""), status=STATUS_MATCH_DELAYED,
                    beneficiary=r_ria.get("beneficiary", "") or c.get("beneficiary", ""),
                    eur_ria=round(float(r_ria.get("order_amt_mru", 0) or 0), 2),
                    eur_cadorim=round(float(c.get("amount_mru", 0) or 0), 2),
                    comm_eur_ria=round(float(r_ria.get("commission_amt", 0) or 0), 2),
                    comm_eur_cadorim=round(float(c.get("commission_amt", 0) or 0), 2),
                    local_par_n=c.get("local_par_n", "") or "",
                    cadorim_id=str(c.get("id", "") or ""),
                    delay_days=_days_between(date, d_ria),
                    confirmed_at=d_ria, journal_date=date,
                ))
            else:
                n_pending += 1
                lines.append(TxLine(
                    pin=pin, status=STATUS_PENDING_RIA,
                    beneficiary=c.get("beneficiary", "") or "",
                    eur_cadorim=round(float(c.get("amount_mru", 0) or 0), 2),
                    comm_eur_cadorim=round(float(c.get("commission_amt", 0) or 0), 2),
                    local_par_n=c.get("local_par_n", "") or "",
                    cadorim_id=str(c.get("id", "") or ""),
                    age_days=age, journal_date=date,
                ))

    status_rank = {
        STATUS_MISSING_CADORIM: 0,
        STATUS_AMOUNT_MISMATCH: 1,
        STATUS_COMM_MISMATCH: 2,
        STATUS_PENDING_RIA: 3,
        STATUS_MATCH_DELAYED: 4,
        STATUS_MATCH: 5,
    }
    lines.sort(key=lambda l: (status_rank.get(l.status, 9), l.pin))

    mru_total_ria = sum(float(r.get("order_amt_mru", 0) or 0) for r in ria_day)
    mru_total_cad = sum(float(c.get("amount_mru", 0) or 0) for c in cad_day)
    comm_total_ria = sum(float(r.get("commission_amt", 0) or 0) for r in ria_day)
    comm_total_cad = sum(float(c.get("commission_amt", 0) or 0) for c in cad_day)

    n_ria = len(ria_day)
    n_cad = len(cad_day)

    verdict, message = _verdict(
        date=date, n_ria=n_ria, n_cad=n_cad,
        n_miss_cad=n_miss_cad, n_pending=n_pending,
        n_amt_mis=n_amt_mis, n_comm_mis=n_comm_mis,
        n_match=n_match, n_match_del=n_match_del,
        ria_data_available=date in ria_by_date,
    )

    status_counts = Counter(l.status for l in lines if l.status != STATUS_MATCH)
    actions = [
        {"status": s, "count": n, "message": _make_action(s)}
        for s, n in status_counts.most_common()
    ]

    return CheckReport(
        date=date, verdict=verdict, message=message,
        n_ria=n_ria, n_cadorim=n_cad,
        n_matched=n_match, n_matched_immediate=n_match_imm, n_matched_delayed=n_match_del,
        n_missing_in_cadorim=n_miss_cad, n_missing_in_ria=n_miss_ria,
        n_pending_ria=n_pending,
        n_amount_mismatch=n_amt_mis, n_commission_mismatch=n_comm_mis,
        eur_total_ria=round(mru_total_ria, 2),
        eur_total_cadorim_est=round(mru_total_cad, 2),
        comm_eur_total_ria=round(comm_total_ria, 2),
        comm_mru_total_cadorim=round(comm_total_cad, 2),
        window_days=window_days, lines=lines, actions=actions,
    )


def _verdict(
    date: str,
    n_ria: int, n_cad: int,
    n_miss_cad: int, n_pending: int,
    n_amt_mis: int, n_comm_mis: int,
    n_match: int, n_match_del: int,
    ria_data_available: bool,
) -> tuple[str, str]:
    """Day-level verdict.

      GREEN — every tx matched (immediate or delayed), no missing, no mismatch
      AMBER — only PENDING_RIA waiting on a Ria statement (open queue)
      RED   — MISSING_CADORIM > 0 OR amount/commission mismatch
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if date > today:
        return VERDICT_AMBER, f"Date {date} dans le futur — pas de vérification possible."
    if not ria_data_available and n_cad == 0:
        return VERDICT_AMBER, f"Aucune donnée Ria pour {date}."
    if n_ria == 0 and n_cad == 0:
        return VERDICT_GREEN, f"Aucune transaction Ria ni Cadorim le {date}."

    real_anomalies = n_miss_cad + n_amt_mis + n_comm_mis
    delayed_note = f", {n_match_del} confirmées en retard" if n_match_del else ""

    if real_anomalies == 0 and n_pending == 0:
        return VERDICT_GREEN, (
            f"Journée {date} : {n_match} matchées sur {n_ria} Ria / {n_cad} Cadorim{delayed_note}. "
            f"Aucune anomalie."
        )
    if real_anomalies == 0 and n_pending > 0:
        return VERDICT_AMBER, (
            f"Journée {date} : {n_match} matchées{delayed_note}, "
            f"{n_pending} en attente de relevé Ria (queue ouverte)."
        )
    return VERDICT_RED, (
        f"Journée {date} : {n_ria} Ria vs {n_cad} Cadorim — "
        f"{n_miss_cad} manquantes Cadorim, {n_pending} en attente Ria, "
        f"{n_amt_mis + n_comm_mis} écarts montant/commission."
    )


def list_available_dates(ria_by_date: dict | None = None) -> list[str]:
    if ria_by_date is None:
        ria_by_date = load_ria_by_date()
    return sorted(ria_by_date.keys())


if __name__ == "__main__":
    import sys

    from .ria_db_loader import load_cadorim_ria

    cad = load_cadorim_ria()
    ria = load_ria_by_date()
    target = sys.argv[1] if len(sys.argv) > 1 else (max(ria) if ria else max({c["date"] for c in cad}))
    print(f"Checking date: {target}")
    rep = compare_day(target, cad, ria_by_date=ria)
    print(f"  Verdict       : {rep.verdict}")
    print(f"  Message       : {rep.message}")
    print(f"  Ria tx        : {rep.n_ria}  ({rep.eur_total_ria:,.2f} MRU)")
    print(f"  Cadorim tx    : {rep.n_cadorim}  ({rep.eur_total_cadorim_est:,.2f} MRU)")
    print(f"  Matched       : {rep.n_matched} (imm {rep.n_matched_immediate} + delayed {rep.n_matched_delayed})")
    print(f"  Missing Cad   : {rep.n_missing_in_cadorim}")
    print(f"  Pending Ria   : {rep.n_pending_ria}")
    print(f"  Amt mismatch  : {rep.n_amount_mismatch}")
    print(f"  Comm mismatch : {rep.n_commission_mismatch}")
    for l in rep.lines[:5]:
        print(f"    {l.status:<16} pin={l.pin:<13} mru_ria={l.eur_ria:>10.2f} mru_cad={l.eur_cadorim:>10.2f}  {l.beneficiary[:28]}")
