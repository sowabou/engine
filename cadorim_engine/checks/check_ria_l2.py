"""Check Ria Layer 2 — settlement-only reconciliation SWIFT ↔ BMI.

PURE LAYER 2: this module looks ONLY at settlements (Ria SWIFTs sending EUR
to Cadorim's BMI account, BMI converting EUR to MRU). It does NOT touch the
L1 transactions table — that's Layer 1's job (Check Ria L1 — separate tab).

Math:
  For each BMI credit b (date d_b, MRU amount):
    Find best SWIFT match within lag window [d_b − N, d_b]
      score = (|lag|, |fx − FX_target|), filter fx ∈ [42, 50]
    For the matched pair :
      fx_implicit = MRU_BMI / EUR_SWIFT      ← BMI's real conversion rate
      mru_at_internal = EUR_SWIFT × FX_internal  ← what Cadorim books
      gain_l2 = MRU_BMI − mru_at_internal
              = EUR_SWIFT × (fx_implicit − FX_internal)

  Three settlement statuses:
    MATCHED       — SWIFT confirmed by BMI within lag window
    SWIFT_NO_BMI  — Ria sent, BMI hasn't credited yet (in transit)
    BMI_NO_SWIFT  — BMI credit with no SWIFT counterpart (pre-archive)

The matching is PER-CREDIT (not daily aggregate), so 2 BMI credits same day
correctly link to 2 SWIFTs from different dates.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from .parsers.bmi_statement import parse_directory as parse_bmi_directory, BMICredit
from cadorim_engine.settlements.parsers.ria_swift import (
    parse_all_mail_folders as parse_ria_swifts,
    RiaSwiftSettlement,
)

# Tunables
LAG_MAX_DAYS = 5
FX_LOW = 42.0
FX_HIGH = 50.0
FX_TARGET = 46.0          # observed median BMI FX
FX_CADORIM_INTERNAL = 42.5

# Status
STATUS_MATCHED = "MATCHED"
STATUS_SWIFT_NO_BMI = "SWIFT_NO_BMI"
STATUS_BMI_NO_SWIFT = "BMI_NO_SWIFT"


def _days(a: str, b: str) -> int:
    fa = datetime.strptime(a, "%Y-%m-%d")
    fb = datetime.strptime(b, "%Y-%m-%d")
    return (fb - fa).days


@dataclass
class Match:
    """One BMI credit matched to one SWIFT — pure settlement view."""

    swift_date: str
    bmi_date: str
    lag_days: int
    eur: float                  # SWIFT amount (Ria wholesale)
    mru: float                  # BMI credit amount (real)
    fx_implicit: float          # MRU / EUR for THIS settlement (= BMI's real rate)
    fx_internal: float          # Cadorim's reference rate (42.5)
    mru_at_internal: float      # EUR × FX_internal — what Cadorim would book
    gain_l2_mru: float          # MRU − mru_at_internal = EUR × (fx_implicit − FX_internal)
    swift_ref: str
    swift_uetr: str
    bmi_source_pdf: str
    bmi_balance: float
    status: str = STATUS_MATCHED


@dataclass
class Unmatched:
    side: str               # 'swift' or 'bmi'
    date: str
    amount: float           # EUR for SWIFT, MRU for BMI
    currency: str
    reference: str = ""
    source: str = ""
    status: str = ""


@dataclass
class L2Report:
    generated_at: str
    period_from: str
    period_to: str
    lag_max_days: int
    fx_internal: float
    fx_avg_matched: float
    fx_min: float
    fx_max: float
    n_matched: int
    n_swift_in_transit: int
    n_bmi_orphan: int
    eur_total_matched: float
    mru_total_matched: float
    mru_at_internal_total: float
    gain_l2_total: float
    eur_by_month: dict[str, float] = field(default_factory=dict)
    mru_bmi_by_month: dict[str, float] = field(default_factory=dict)
    gain_l2_by_month: dict[str, float] = field(default_factory=dict)
    matches: list[Match] = field(default_factory=list)
    unmatched_swifts: list[Unmatched] = field(default_factory=list)
    unmatched_bmis: list[Unmatched] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items()
               if k not in ("matches", "unmatched_swifts", "unmatched_bmis")},
            "matches": [asdict(m) for m in self.matches],
            "unmatched_swifts": [asdict(u) for u in self.unmatched_swifts],
            "unmatched_bmis": [asdict(u) for u in self.unmatched_bmis],
        }


def reconcile(
    workspace_root: str,
    lag_max: int = LAG_MAX_DAYS,
    fx_low: float = FX_LOW,
    fx_high: float = FX_HIGH,
    fx_internal: float = FX_CADORIM_INTERNAL,
    period_from: str | None = None,
    period_to: str | None = None,
) -> L2Report:
    """Pure Layer 2: SWIFT ↔ BMI, no L1 references."""
    swifts = parse_ria_swifts(os.path.join(workspace_root, "cadorim-engine", "data", "settlements"))
    bmi_credits = parse_bmi_directory(workspace_root)

    # Period filter
    if period_from:
        swifts = [s for s in swifts if s.date >= period_from]
    if period_to:
        swifts = [s for s in swifts if s.date <= period_to]
        bmi_cutoff = (datetime.strptime(period_to, "%Y-%m-%d") + timedelta(days=lag_max)).strftime("%Y-%m-%d")
        bmi_credits = [c for c in bmi_credits if c.date <= bmi_cutoff]
    if period_from:
        bmi_credits = [c for c in bmi_credits if c.date >= period_from]

    swifts_sorted = sorted(swifts, key=lambda s: s.date)
    bmi_sorted = sorted(bmi_credits, key=lambda c: (c.date, c.line_idx))

    swift_used: set[str] = set()
    matched_bmi_set: set[tuple] = set()
    matches: list[Match] = []

    for b in bmi_sorted:
        best = None
        best_score = (float("inf"), float("inf"))
        for s in swifts_sorted:
            if s.uetr in swift_used or s.amount_foreign <= 0:
                continue
            lag = _days(s.date, b.date)
            if lag < 0 or lag > lag_max:
                continue
            fx = b.amount_mru / s.amount_foreign
            if not (fx_low <= fx <= fx_high):
                continue
            score = (abs(lag), abs(fx - FX_TARGET))
            if score < best_score:
                best_score = score
                best = (s, lag, fx)
        if best is None:
            continue
        s, lag, fx = best
        swift_used.add(s.uetr)
        matched_bmi_set.add((b.source_pdf, b.line_idx, b.date))

        mru_internal = s.amount_foreign * fx_internal
        gain = b.amount_mru - mru_internal

        matches.append(Match(
            swift_date=s.date,
            bmi_date=b.date,
            lag_days=lag,
            eur=round(s.amount_foreign, 2),
            mru=round(b.amount_mru, 2),
            fx_implicit=round(fx, 4),
            fx_internal=fx_internal,
            mru_at_internal=round(mru_internal, 2),
            gain_l2_mru=round(gain, 2),
            swift_ref=s.reference,
            swift_uetr=s.uetr,
            bmi_source_pdf=b.source_pdf,
            bmi_balance=round(b.balance, 2),
        ))

    # Unmatched
    unmatched_swifts = [
        Unmatched(side="swift", date=s.date, amount=round(s.amount_foreign, 2),
                  currency=s.currency, reference=s.reference, source=s.source_file,
                  status=STATUS_SWIFT_NO_BMI)
        for s in swifts_sorted if s.uetr not in swift_used
    ]
    unmatched_bmis = [
        Unmatched(side="bmi", date=b.date, amount=round(b.amount_mru, 2),
                  currency="MRU", source=b.source_pdf, status=STATUS_BMI_NO_SWIFT)
        for b in bmi_sorted if (b.source_pdf, b.line_idx, b.date) not in matched_bmi_set
    ]

    # Aggregates
    eur_total = sum(m.eur for m in matches)
    mru_total = sum(m.mru for m in matches)
    mru_int_total = sum(m.mru_at_internal for m in matches)
    gain_total = sum(m.gain_l2_mru for m in matches)
    fx_avg = (mru_total / eur_total) if eur_total > 0 else 0.0
    fx_values = [m.fx_implicit for m in matches if m.fx_implicit > 0]
    fx_min = min(fx_values) if fx_values else 0.0
    fx_max = max(fx_values) if fx_values else 0.0

    gain_by_month: dict[str, float] = {}
    eur_by_month: dict[str, float] = {}
    mru_bmi_by_month: dict[str, float] = {}
    for m in matches:
        key = m.bmi_date[:7]
        gain_by_month[key] = gain_by_month.get(key, 0.0) + m.gain_l2_mru
        eur_by_month[key] = eur_by_month.get(key, 0.0) + m.eur
        mru_bmi_by_month[key] = mru_bmi_by_month.get(key, 0.0) + m.mru

    all_dates = [m.swift_date for m in matches] + [m.bmi_date for m in matches] + \
                [u.date for u in unmatched_swifts] + [u.date for u in unmatched_bmis]
    period_from_out = min(all_dates) if all_dates else ""
    period_to_out = max(all_dates) if all_dates else ""

    return L2Report(
        generated_at=datetime.utcnow().isoformat() + "Z",
        period_from=period_from_out,
        period_to=period_to_out,
        lag_max_days=lag_max,
        fx_internal=fx_internal,
        fx_avg_matched=round(fx_avg, 4),
        fx_min=round(fx_min, 4),
        fx_max=round(fx_max, 4),
        n_matched=len(matches),
        n_swift_in_transit=len(unmatched_swifts),
        n_bmi_orphan=len(unmatched_bmis),
        eur_total_matched=round(eur_total, 2),
        mru_total_matched=round(mru_total, 2),
        mru_at_internal_total=round(mru_int_total, 2),
        gain_l2_total=round(gain_total, 2),
        eur_by_month={k: round(v, 2) for k, v in sorted(eur_by_month.items())},
        mru_bmi_by_month={k: round(v, 2) for k, v in sorted(mru_bmi_by_month.items())},
        gain_l2_by_month={k: round(v, 2) for k, v in sorted(gain_by_month.items())},
        matches=matches,
        unmatched_swifts=unmatched_swifts,
        unmatched_bmis=unmatched_bmis,
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
    print(f"=== Ria Layer 2 (settlement-only) — {r.period_from} → {r.period_to} ===")
    print(f"FX interne Cadorim   : {r.fx_internal}")
    print(f"FX BMI moyen pondéré : {r.fx_avg_matched}  (min {r.fx_min}, max {r.fx_max})")
    print(f"Spread moyen         : +{r.fx_avg_matched - r.fx_internal:.4f} MRU/EUR")
    print(f"Matches              : {r.n_matched}")
    print(f"SWIFT en transit     : {r.n_swift_in_transit}")
    print(f"BMI orphelins        : {r.n_bmi_orphan}")
    print(f"EUR SWIFT matched    : {r.eur_total_matched:>14,.2f}")
    print(f"MRU BMI matched      : {r.mru_total_matched:>14,.2f}")
    print(f"MRU @ interne 42,5   : {r.mru_at_internal_total:>14,.2f}")
    print(f"Gain L2              : {r.gain_l2_total:>14,.2f} MRU")
    print()
    print("Par mois:")
    for m in sorted(r.gain_l2_by_month, reverse=True):
        print(f"  {m}: gain {r.gain_l2_by_month[m]:>14,.2f}")
