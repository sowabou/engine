# Claude Code Prompt — Phase 1b: ALL partners, full production window (autonomous overnight run)

## MODE: AUTONOMOUS — THE USER IS ASLEEP

You will run this task end-to-end without checkpoint-asking. When you finish, you either report **GREEN** (all acceptance criteria pass, the engine renders real production data cleanly) or **AMBER** (ran out of retries but made measurable progress — list remaining issues). Do not report RED unless an environment problem (disk, Python, SQLite) physically blocks execution.

You are authorized to:
- Write freely to `~/cadorim-engine/`, `~/Documents/Claude/Projects/Cadorim Accounting/`, and `/tmp/`
- Create intermediate debug scripts
- Drop and regenerate the SQLite cache
- Iterate on the classifier until it passes the quality bar (up to 5 iterations — see Self-Healing Loop below)

---

## Context — where we are

Phase 1 shipped: `cadorim_engine/classifier.py` handles `type='ria'` only, `export_ria_q1` produces `data/production_data_ria.json` with 2,885 Q1 2026 Ria transactions, and `engine.html` toggles between Simulation and Production cleanly.

Now we extend Phase 1 to cover **every production partner** across the **full production history (Jan 2025 → Apr 2026, 15 months, 18,225 rows)**. Same output contract, all 14 DB transaction types routed to 5 business flows, fully classified, auto-discovered channels, and three engine toggle states.

---

## SCOPE — FULL HISTORY, NOT JUST Q1 2026

The user explicitly asked to start the dataset from **January 2025**. That means:

- Primary export scope: `created_at >= '2025-01-01' AND created_at < '2026-04-01'` — all 15 months of real production.
- `cutoff_date` for opening balances: `2025-01-01` (opening receivables should be ~0 or very small, because that's when the system effectively starts in our model).
- Keep a `Q1 2026` secondary export as a sanity-check slice (same code path, narrower window), so the user can cross-check against Phase 1's Ria-only numbers.

---

## THE SEVEN PARTNERS TO REGISTER

Register these seven at Layer 1 (Par_l). **Bridge** and **SNDP are NOT the same partner**:

- **Bridge** is an **international** Par_l. It is Cadorim's own SEPA collection channel from Europe — EUR comes in, gets converted to MRU, settles to a EUR bank. Full Layer 1 + Layer 2, modeled **exactly like Ria**.
- **SNDP** is a **local B2C** Par_l. It's a Mauritanian business (tenant) that prefunds Cadorim in **MRU** (no foreign currency, no FX), then dispatches payouts through the cashout system (Sedad, Masrvi, Click, Bankily, MauriPay, caisses). No Layer 2 — the prefunding IS the settlement equivalent.

| Par_l code | Display name | Flow type | Currency | Commission model | Notes |
|---|---|---|---|---|---|
| `ria` | Ria | international | EUR | fixed 25 MRU | done — keep as-is |
| `terrapay` | TerraPay | international | USD | 0.5% of sender_amount | debitable_id=422, Layer 2 on USDC/USD banks |
| `juba` | Juba Express | international | EUR | 1% of sender_amount | debitable_id=778, Layer 2 on BPM EUR |
| `bridge` | Bridge EUR | international | EUR | 0 at Par_l (margin = FX spread) | debitable_id=808 (Bridge EUR) → Account 501. **Layer 1 + Layer 2 same as Ria.** |
| `sndp` | SNDP / CadorimPay B2C | b2c | MRU | use source `commission` or 0 | MRU prefunding → MRU payout via wallets/caisses. **NO FX, NO Layer 2.** |
| `wallet` | Cadorim Wallet / MauriPay | wallet | MRU | use source `frais` | P2P + cashout |
| `agent` | Cadorim Agent Network | agent | MRU | 0 at Par_l (commission lives at channel) | agent commission + funding + agent-to-agent |

### Bridge vs SNDP — how to tell them apart in the DB

- **Bridge inflows** = rows that bring new MRU into the system from EUR. Typically **`transfert_cadorim`** (Debit account 808 Bridge EUR → Credit account 501 COMPTE CADORIM). Classify as `bridge` / international / EUR.
- **SNDP prefunding** = MRU deposits by SNDP. Look for `depot` or `virement_interne` with SNDP references in description, or large MRU inflows to account 501 not paired with a Bridge row. If ambiguous, tag `Par_l='sndp'` + `flow_category='internal'` and surface it in the unclassified report.
- **SNDP payouts / B2C cashout** = **`retrait_commande`** (Debit 501 COMPTE CADORIM → Credit wallet/caisse). Classify as `sndp` / b2c_payout / MRU. This is where SNDP's real business activity lives.

Unmatched rows (telecom recharge, single merchant, internal treasury transfers) → Par_l = `treasury` or `ancillary`, `flow_category='internal'` or `'ancillary'`. **Never drop silently.**

---

## FIX 1 — Rewrite `cadorim_engine/classifier.py` as a true dispatcher

Replace the Ria-only classifier with a dispatcher routing each row through type-specific handlers. Keep the event shape (id / created_at / posted_at / status / Par_l / Cur_k / Amount_j / Client_i / Client_m / Local_Par_n / Amount_mru_h / commission_a / cost_payout_a / fx_gain_a / profit_transaction_a / reference / source_row_id / type / date) — plus these additions:

```python
"flow_category": "revenue" | "internal" | "ancillary",
"flow_subtype": "international" | "wallet_p2p" | "wallet_cashout" | "wallet_deposit" |
                "b2c_inbound" | "b2c_payout" | "agent_commission" | "agent_funding" |
                "agent_operations" | "treasury" | "telecom" | "merchant",
"db_type": row['type'],  # preserved for auditability
```

### Type → flow routing (authoritative)

Rows failing basic sanity (status canceled/failed, accounting_status=rejected, amount<=0, missing created_at) return None.

| DB type | Handler | Flow subtype | Notes |
|---|---|---|---|
| `ria` | `_classify_ria` | international | already works, keep |
| `juba` | `_classify_juba` | international | Par_l='juba', Cur_k='EUR', rate 42.5, commission 1% |
| `transfert_cadorim` | `_classify_bridge_inbound` | international | **Par_l='bridge'**, Cur_k='EUR'. rate ~44.5; commission_a = 0. `flow_category='revenue'` |
| `retrait_commande` | `_classify_sndp_payout` | b2c_payout | **Par_l='sndp'**, Cur_k='MRU'. commission = row['commission'] or 0. `flow_category='revenue'`. Local_Par_n from credit account. **No FX, no Layer 2.** |
| `depot` | `_classify_wallet_deposit` | wallet_deposit | Par_l='wallet'; flow_category='internal' |
| `retrait` | `_classify_wallet_cashout` | wallet_cashout | Par_l='wallet'; commission_a = source `frais` |
| `transfert_extra` | `_classify_wallet_cashout` | wallet_cashout | external-counterparty cashout |
| `commission` | `_classify_agent_commission` | agent_commission | Par_l='agent'; `flow_category='internal'` |
| `alimentation_compte` | `_classify_agent_funding` | agent_funding | Par_l='agent'; `flow_category='internal'` |
| `virement_interne` | `_classify_treasury` | treasury | Par_l='treasury'; `flow_category='internal'` |
| `regularisation` | `_classify_treasury` | treasury | corrections |
| `recharge telephonique` | `_classify_telecom` | telecom | Par_l='ancillary'; `flow_category='ancillary'` |
| `paiement` | `_classify_merchant` | merchant | Par_l='ancillary'; `flow_category='ancillary'` |
| `transfert` | `_classify_transfert` | sub-dispatcher below | the heavy lifting |

### Transfert sub-dispatcher

```python
def _classify_transfert(row, accounts):
    dt = row.get('debitable_type') or ''
    ct = row.get('creditable_type') or ''
    did = int(row.get('debitable_id') or 0)
    cid = int(row.get('creditable_id') or 0)
    d_acct = accounts.get(did, {}) if dt.endswith('Account') else {}
    c_acct = accounts.get(cid, {}) if ct.endswith('Account') else {}

    if did == 422:
        return _build_international(row, accounts, partner='terrapay', currency='USD', rate=39.0, commission_pct=0.005)
    if did == 782:
        return _build_international(row, accounts, partner='ria', currency='EUR', rate=42.5, commission_fixed=25)
    if dt.endswith('Customer') and cid in (16, 21):
        return _build_wallet_cashout(row, accounts)
    if dt.endswith('Customer') and ct.endswith('Customer'):
        return _build_wallet_p2p(row, accounts)
    if dt.endswith('Customer') and c_acct.get('type') == 'cash':
        return _build_wallet_cashout(row, accounts)
    if d_acct.get('type') == 'cash' and c_acct.get('type') == 'cash':
        return _build_agent_operations(row, accounts)
    return _build_unclassified(row, accounts)
```

### Derivations inside helpers

- `Local_Par_n`: extend `_infer_local_par`'s credit-id map with Sedad(16), Masrivi(21), and any account with `type='main'` whose name matches bankily/click/mauripay → slug to `wallet_<name>`.
- `Amount_j`: MRU → foreign via fixed FX default (`EUR=42.5, USD=39.0`). Comment `# TODO Phase 2: per-txn FX from transactions_devises`.
- `commission_a`: prefer `row['commission']` if > 0. Otherwise apply partner default.
- `client_m`: credit account name, or Customer id placeholder.
- `status`: DB `completed` → `released`; DB `pending` or `waiting` → `pending` with `posted_at=None`.

### Critical — pending versus posted

If `status='pending'` or `accounting_status='waiting'`, emit with `status='pending'`, `posted_at=None`. Never blur with historical ledger.

---

## FIX 2 — Extend `cadorim_engine/opening.py`

Compute opening at cutoff `2025-01-01`. Since the system effectively begins in 2025, most opening receivables will be ~0.

```python
opening_receivable = {}
for par, (db_pattern, currency, rate) in [
    ('ria',       ("type='ria'",                                 'EUR', 42.5)),
    ('terrapay',  ("type='transfert' AND debitable_id=422",      'USD', 39.0)),
    ('juba',      ("type='juba' OR debitable_id=778",            'EUR', 42.5)),
    ('bridge',    ("type='transfert_cadorim'",                   'EUR', 44.5)),
]:
    sql = f"SELECT COALESCE(SUM(amount),0) FROM transactions WHERE ({db_pattern}) AND status='completed' AND created_at < ?"
    mru = float(conn.execute(sql, (cutoff_date,)).fetchone()[0])
    opening_receivable[par] = {"foreign": round(mru / rate, 2), "currency": currency, "mru": mru}
```

SNDP: compute `opening_prefunding` as net MRU position at cutoff. Start at 0 if ambiguous.

---

## FIX 3 — Export entry points

In `load_production.py`:

1. Keep `export_ria_q1` for compat.
2. Add `export_all(from_date, to_date, out_path)` — generic:
   - Scan ALL `wallet_db_transactions` in the window.
   - Run each through the new classifier.
   - Build `config` block dynamically:
     - Layer 1 entry per partner that emitted ≥ 1 event.
     - `channels` auto-discovered from emitted `Local_Par_n` union.
     - Layer 2 stub: `ria→bmi/EUR`, `terrapay→eth_cado01/USD`, `juba→bpm/EUR`, `bridge→bred/EUR`. Settlements empty for Phase 2.
   - `scope`, `cutoff_date`, full `stats` block (per-partner, per-flow-subtype, unclassified, per-flow-category MRU totals).
3. Add convenience wrappers:
   - `export_all_full()` → `('2025-01-01', '2026-04-01', 'data/production_data_all.json')`
   - `export_all_q1_2026()` → `('2026-01-01', '2026-04-01', 'data/production_data_all_q1_2026.json')`
4. CLI: `python3 load_production.py export_all_full` and `export_all_q1_2026`.

Keep the Ria-only JSON.

---

## FIX 4 — Engine toggle (three states + scope label)

`engine.html` toggle offers:
1. **Simulation** (default)
2. **Production — Ria only** (Phase 1 JSON)
3. **Production — All (Jan 2025 → Mar 2026)** (new full JSON)
4. Optional: **Production — All Q1 2026** if the Q1 slice file exists

Banner shows scope + partner count + txn count + channel count + unclassified count. Fall back gracefully if a JSON is missing.

---

## FIX 5 — CEO / Treasury filter by flow_category

CEO Volume and Revenue cards: filter `SIM_TXS` to `flow_category='revenue'`. Internal/ancillary stay visible in Operations and Positions.

---

## FIX 6 — Layer 2 settlements (INGEST + MATCH + REPORT)

Layer 1 alone leaves receivables ballooning. To get clean partner balances by morning, we also ingest **settlement events** for each international partner and let the engine's `applySett` collapse receivables into bank balances + FX gain.

### Canonical settlement event shape

Every settlement event, regardless of source, must emit:

```python
{
    "id": "S-<partner>-<N>",
    "partner_code": "ria" | "terrapay" | "juba" | "bridge",
    "date": "YYYY-MM-DD",
    "amount_foreign": 12345.67,     # in partner's native currency
    "currency": "EUR" | "USD" | "USDC",
    "bank_code": "bmi" | "bpm" | "bred" | "eth_cado01" | "eth_cado02",
    "fx_rate_settlement": 42.5,      # MRU per foreign unit at settlement day
    "amount_mru": 524_823,           # derived
    "reference": "SWIFT ref or tx hash",
    "source": "bmi_statement" | "swift" | "wire" | "excel" | "etherscan" | "manual",
    "source_file": "<relative path or URL>",
}
```

### Data sources the user has confirmed

| Partner | Source | Where to find it | Parser strategy |
|---|---|---|---|
| **Ria** | BMI bank statements + Ria SWIFT + Ria Wire notifs + Ria CorrespPayment Excel | `~/Documents/Claude/Projects/Cadorim Accounting/` and subfolders (`mails/` archive has 370 SWIFT, 364 Wire, 363 Excel per memory). The `ria-accounting` skill defines the parsers. | Search for existing parsed outputs first (e.g., `Recon_*.xlsx`, ledger files). If not staged, parse the raw SWIFT/Wire/Excel files directly using the ria-accounting skill's logic. |
| **TerraPay** | Cado02 ETH wallet — USDC inflows from TerraPay ETH addresses (`0x3C9fB156...` and `0x8195d349...` per memory) | Etherscan API (token transfers endpoint, ERC-20 USDC) | Query Etherscan for USDC transfers TO Cado02 FROM each TerraPay address. Group by day. Use free-tier API key if available; else fall back to `~/Documents/Claude/Projects/Cadorim Accounting/` for any pre-exported CSV. |
| **Bridge** | Cado01 ETH wallet — settlement inflows from Bridge | Etherscan API (same pattern, Cado01 as destination) | Query USDC/EUR-stable transfers to Cado01. If the user has the Cado01 address staged in a config or memory file, use it; else look for `BRIDGE_CADO01_ADDRESS` or similar in `~/cadorim-engine/` or `~/Documents/Claude/Projects/Cadorim Accounting/`. If unfound, stub empty and log TODO. |
| **Juba** | BPM bank statements (EUR, small) | `~/Documents/Claude/Projects/Cadorim Accounting/` | Small volume per user ("Juba is small"). Best-effort parse; if not found, stub empty and log TODO — acceptable for this phase. |
| **SNDP** | N/A (MRU prefunding, no foreign settlement) | — | No Layer 2. Prefunding inflows become `flow_category='internal'` events at Layer 1 already. |

### Implementation plan

1. **Create `cadorim_engine/settlements/` module** with one file per source:
   - `bmi_parser.py` — parses BMI bank statement files (PDF/Excel/CSV — whatever the user has staged).
   - `ria_mail_parser.py` — wraps ria-accounting skill logic to parse SWIFT/Wire/Excel.
   - `etherscan_client.py` — fetches USDC transfers for a given address + counterparty filter. Use free-tier Etherscan v2 API. Cache responses in `/tmp/etherscan_cache/` to avoid rate limits across iterations.
   - `bpm_parser.py` — best-effort BPM parser (stub ok).

2. **Create `cadorim_engine/settlements/ingest.py`** with a top-level `ingest_all(from_date, to_date)` that returns a unified list of settlement events, sorted by date.

3. **Wire into `load_production.py`**:
   - `export_all(from_date, to_date, out_path)` should call `ingest_all(from_date, to_date)` and fill the `settlements: [...]` array.
   - For each settlement, derive `amount_mru` using the day's fx rate (fall back to partner default if no day rate available).
   - Default settlement banks per partner in Layer 2 config:
     - `ria → bmi (EUR)`
     - `terrapay → eth_cado02 (USDC)`
     - `bridge → eth_cado01 (USDC or EUR)`
     - `juba → bpm (EUR)`

4. **Confirm engine's `applySett`** in `engine.html` already consumes this shape — it should, because Phase 1 simulation uses the same contract. If there's a field mismatch, adapt the settlement shape, NOT the engine.

### Discovery pass (must happen before parsing)

Before writing any parser, run a **discovery pass** that inventories what's available:

```bash
# In ~/Documents/Claude/Projects/Cadorim Accounting/
find . -type f \( -name "*.pdf" -o -name "*.xlsx" -o -name "*.csv" -o -name "*.eml" -o -name "*.msg" \) -printf "%p  %s bytes  %TY-%Tm-%Td\n"
```

Log results to `~/cadorim-engine/LAYER2_DISCOVERY.md`:

```markdown
## Layer 2 data inventory — <timestamp>
### Ria — BMI + SWIFT + Wire + Excel
- Found X SWIFT files in mails/...
- Found Y Wire notifs in mails/...
- Found Z Excel CorrespPayment in mails/...
- Found N BMI statements in ...
### TerraPay — Cado02 ETH
- Cado02 address resolved: 0x... (source: memory/config)
- Etherscan query range: 2025-01-01 → 2026-04-01
- USDC transfers fetched: N
### Bridge — Cado01 ETH
- Cado01 address: <resolved or TODO>
- USDC transfers fetched: N
### Juba — BPM
- Found X statement files in ...
```

If Bridge's Cado01 address isn't resolvable from memory or config files, add a TODO to the report and ship Bridge with empty settlements — don't guess an address.

### Settlement matching + reconciliation

For each international partner, produce a **matching report** in the morning output:

- Total Layer 1 receivable (Σ Amount_j for posted txns in window)
- Total Layer 2 settlement (Σ amount_foreign from settlements in window)
- Open receivable end-of-window = L1 − L2
- FX gain at Layer 2 = Σ (amount_mru_at_settlement − amount_mru_at_transaction) per matched txn-batch
- Reconciliation percentage: `settled / total_receivable * 100`

### Q1 2026 partner balance report

In addition to the full-window report, produce a **Q1 2026 partner ledger snapshot** (`~/cadorim-engine/Q1_2026_PARTNER_BALANCES.md`):

```markdown
# Q1 2026 Partner Balances — Layer 1 + Layer 2

## Ria
- Q1 Layer 1 volume: X EUR (Y MRU)
- Q1 Layer 1 commission: Z MRU
- Q1 Layer 2 settlements: N settlements totaling X' EUR
- Q1 FX gain at settlement: Z' MRU
- Receivable at 2026-01-01: open EUR
- Receivable at 2026-03-31: open EUR  (should have compressed)
- Bank balance (BMI) delta: +X' EUR
- Reconciliation: Y% of Q1 receivable settled within Q1

## TerraPay
... same structure ...

## Juba
... same structure ...

## Bridge
... same structure ...

## SNDP
- Q1 B2C payout volume: X MRU
- Q1 commission: Y MRU
- Prefunding opening balance: Z MRU
- Prefunding closing balance: Z' MRU
- Delta: Z' − Z
```

### Audit additions (extend the self-healing loop)

Add these checks to `tools/audit_export.py`:

11. **Layer 2 presence**: for each of the 4 international partners, `settlements.filter(partner_code==X).length > 0` **unless** the partner is explicitly marked unavailable in `LAYER2_DISCOVERY.md`.
12. **Layer 2 reconciliation ratio**: `Σ amount_foreign settled / Σ Amount_j receivable` should be between 70% and 120% over the full window for Ria and TerraPay. If below 50%, anomaly — either the parser missed data or the matching is off.
13. **FX rate drift**: no settlement `fx_rate_settlement` deviates more than 5% from the partner default — flag outliers for inspection.
14. **Bank balance non-negative**: after replaying all settlements + withdrawals, every bank code balance must be ≥ 0. If negative, surface which partner/bank.

### Retry strategy for Layer 2

If Layer 2 fails (API error, missing files, parser crash), do NOT abort the entire run:
- Log the failure to `AUDIT_LOG.md` with clear cause
- Ship the export with Layer 1 complete and `settlements: []` for the affected partner
- Continue with other partners
- Report AMBER with the specific Layer 2 gap, rather than RED

---

## FIX 7 — Tests

`tests/test_classifier_all.py`:
- One test per flow subtype with fixture rows.
- Assert Par_l, Cur_k, flow_subtype, flow_category, status mapping, amount balance, `posted_at is None` when pending.

Smoke test `tests/test_export_all.py`:
- Run `export_all_full()`, assert total ≥ 15,000 emitted events, each of 7 partners has ≥ 1 event, unclassified rate < 2%, JSON structure valid.

Settlement test `tests/test_settlements.py`:
- One test per parser (bmi, ria_mail, etherscan, bpm) using small fixture data.
- Assert canonical settlement shape, date parsing, amount_mru derivation.
- Mock Etherscan HTTP calls — do not hit the network in CI.

---

## AUTONOMOUS SELF-HEALING LOOP

This is the core of the overnight task. After each export run, compute the **anomaly score** and retry up to **5 iterations**.

### Anomaly detection (run after every export)

Write `tools/audit_export.py` that loads `data/production_data_all.json` and runs checks 1-10 for Layer 1, then checks 11-14 for Layer 2:

1. **Unclassified rate**: `unclassified_count / total_rows` must be **< 2%**.
2. **Per-partner presence**: each of the 7 partners (ria, terrapay, juba, bridge, sndp, wallet, agent) must have **≥ 1 event**.
3. **Expected volume bounds** (rough spec anchors across full Jan-2025 → Apr-2026 window):
   - Ria: 5,000–6,000 events (45M–50M MRU)
   - TerraPay: 500–1,000 events
   - Juba: ≥ 10 events
   - Bridge: 200–400 events (2M–3M MRU)
   - SNDP: 200–400 events
   - Wallet: 2,500–3,500 events
   - Agent: 4,500–5,500 events
   - Any partner more than **50% off** its lower bound → anomaly.
4. **Flow-category totals**: `revenue` MRU should be the largest bucket. `internal` second. `ancillary` tiny.
5. **Duplicate detection**: no two emitted events share the same `(source_row_id)`.
6. **Negative MRU**: no event should have `Amount_mru_h <= 0`.
7. **FX sanity**: for each international partner, `Amount_j * rate ≈ Amount_mru_h` within 1% rounding.
8. **Status integrity**: any event with `status='pending'` must have `posted_at is None`; any with `status='released'` must have `posted_at` set.
9. **Channel hygiene**: no `Local_Par_n == 'caisse_unknown'` rate above 5% for any partner. If higher, the credit-id map needs extending.
10. **Opening sanity**: at cutoff `2025-01-01`, opening receivable for each international partner should be **< 5%** of that partner's total-period MRU (because the system effectively starts then).

### Self-correction rules

When audit finds an anomaly, DO NOT stop. Diagnose, patch, re-export, re-audit. Some concrete patches you are authorized to make:

- **High unclassified rate** → print top-10 unclassified patterns (grouped by `db_type + debitable_type + creditable_type + account_type`). Add a new rule to `_classify_transfert` or a new handler for an unexpected `db_type`. Re-export.
- **caisse_unknown above threshold** → list the account ids feeding it, inspect their names in `accounts` table, extend `_CREDIT_MAP` or `_infer_local_par`. Re-export.
- **Partner count off by more than 50%** → inspect samples, propose a classification tweak, re-export.
- **Duplicate events** → hunt the path in `_build_*` helpers that's double-emitting. Fix. Re-export.
- **FX sanity fail** → check the rate constants in the helpers match what's used in `opening.py`. Re-export.
- **Pending/released contract break** → fix in `_classify_*` helpers. Re-export.

### Loop bound

Up to **5 iterations** of (export → audit → patch → re-export). If after 5 iterations any critical anomaly remains (unclassified ≥ 2%, missing partner, duplicates), report AMBER with a clear remaining-issue list. Do not loop forever.

### Persistent audit log

Append every iteration to `~/cadorim-engine/AUDIT_LOG.md`:

```markdown
## Iteration N — <timestamp>
- Scope: Jan 2025 → Apr 2026
- Events emitted: X
- Unclassified: Y (Z%)
- Per-partner counts: {...}
- Anomalies detected: [...]
- Patches applied: [...]
- Status: GREEN / AMBER / re-running
```

---

## MORNING REPORT — write `~/cadorim-engine/PHASE_1B_REPORT.md`

When you're done (GREEN or AMBER), create a single markdown report Dr. Neine can read over coffee. Structure:

```markdown
# Phase 1b Morning Report — <timestamp>

## STATUS: GREEN | AMBER

## Headline numbers
- Total Layer 1 events classified: X across Y days (Jan 2025 → Mar 2026)
- Total Layer 2 settlements ingested: N across the 4 international partners
- Partners active: 7/7 (or list missing)
- Unclassified rate: Z%
- L1 profit (full window, revenue only): MRU
- L2 FX gain (full window): MRU
- L1 profit (Q1 2026 slice, revenue only): MRU
- L2 FX gain (Q1 2026 slice): MRU

## Per-partner breakdown (full window)
| Partner | Events | L1 volume (MRU) | L1 profit | L2 settlements | L2 FX gain | Reconciliation % | Open receivable end-of-window |
| ria | ... | ... | ... | ... | ... | ... | ... |
| terrapay | ... |
| juba | ... |
| bridge | ... |
| sndp | ... | n/a | n/a | n/a |
| wallet | ... |
| agent | ... |

## Q1 2026 partner balance snapshot
See `Q1_2026_PARTNER_BALANCES.md` for the full Q1 ledger snapshot per partner.

## Per-flow-subtype breakdown
...

## Layer 2 data inventory
Summary of `LAYER2_DISCOVERY.md`:
- Ria: X SWIFT + Y Wire + Z Excel + N BMI statements parsed
- TerraPay: N USDC transfers fetched from Etherscan (Cado02)
- Bridge: N transfers (or TODO if Cado01 address unresolved)
- Juba: N statements (or stub if unavailable)

## Anomalies encountered and how I handled them
- <anomaly> → <patch> → <result>

## Files changed
- cadorim_engine/classifier.py  (old → new line counts)
- cadorim_engine/opening.py
- cadorim_engine/settlements/*.py  (new module)
- load_production.py
- engine.html  (production toggle extended)
- tests/test_classifier_all.py  (new)
- tests/test_export_all.py  (new)
- tests/test_settlements.py  (new)
- tools/audit_export.py  (new)

## Outputs generated
- data/production_data_all.json  (size, event count, settlement count)
- data/production_data_all_q1_2026.json  (size, event count, settlement count)
- AUDIT_LOG.md  (iteration history)
- LAYER2_DISCOVERY.md  (Layer 2 data inventory)
- Q1_2026_PARTNER_BALANCES.md  (Q1 snapshot)

## Test results
- pytest -xvs tests/  → <pass/fail summary>

## Outstanding items for morning review
- <anything needing Dr. Neine's judgment, with a concrete proposal>
```

---

## ACCEPTANCE CRITERIA (check these at the end)

1. `data/production_data_all.json` covers Jan 2025 → Apr 2026 with all 7 partners populated at Layer 1.
2. Unclassified rate < 2% on the full window.
3. Engine toggle offers Sim + Prod Ria + Prod All (Full). Loading Prod All in the browser populates Setup with 7 partners, Operations with tens of thousands of rows, CEO with revenue-only aggregates.
4. Pending rows never appear in partner historical ledgers — only in the Operations queue view.
5. **Layer 2 settlements ingested for at least 3 of 4 international partners** (ria + terrapay + one of bridge/juba). For any partner where Layer 2 is unavailable, `LAYER2_DISCOVERY.md` documents the gap.
6. **Q1 2026 partner ledger snapshot** (`Q1_2026_PARTNER_BALANCES.md`) exists and shows per-partner L1 volume, L2 settlements, FX gain, open receivable start/end-of-quarter, and reconciliation %.
7. **Receivables compress** after Layer 2 replay — for Ria at minimum, end-of-window open receivable < Layer 1 cumulative receivable by ≥ 50%.
8. **Bank balances non-negative** after replay for all bank codes (`bmi`, `bpm`, `bred`, `eth_cado01`, `eth_cado02`).
9. All tests pass: `pytest -xvs tests/`.
10. `AUDIT_LOG.md` records the iteration history including Layer 2 audit results.
11. `PHASE_1B_REPORT.md` is the single morning deliverable and points to the other files.

---

## DO NOT

- Do not bypass the audit loop — if you only run once and stop, you miss the whole point of the overnight mode.
- Do not touch live MySQL or Grand Livre reconciliation — those are later phases.
- Do not change engine math (`computeL1/L2`, `applyTx`, `applySett`, `applyWd`).
- Do not modify the Simulation path.
- Do not drop rows silently.
- Do not mock data to pass the audit.
- Do not delete or rewrite Phase 1's Ria-only output.
- Do not invent addresses, IBANs, or partner details. If a piece of Layer 2 config is missing, log a TODO and ship with that partner's settlements empty.
- Do not skip Layer 2 entirely — at minimum Ria (BMI) and TerraPay (Cado02 via Etherscan) must be ingested. Bridge/Juba can be deferred if their source data is unreachable, but the attempt and the reason must be logged.

---

## SERVING REMINDER

The engine must be served over HTTP for the browser to fetch the JSON. If you want to visually confirm the UI render before bed, run:

```bash
cd ~/cadorim-engine && python3 -m http.server 8765
```

But this is optional — the audit script is the primary pass/fail gate.

---

## GO
