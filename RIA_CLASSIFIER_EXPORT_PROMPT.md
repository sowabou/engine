# Claude Code Prompt — Production Data Bridge (Phase 1): Ria Classifier + Opening Balance + Engine Toggle

## WRITE PERMISSION (explicit user grant)

The user has **explicitly authorized you to create, edit, and delete files, run shell commands, and install Python packages** under the following locations without asking for confirmation:

- `~/cadorim-engine/` (the project root)
- `~/Documents/Claude/Projects/Cadorim Accounting/` (source data folder)
- `/tmp/` (scratch)

Do NOT write outside these locations. Do NOT commit to git or push anywhere unless the user asks. Run scripts freely to validate. You may install Python packages via `pip install` into the project's venv or globally with `--break-system-packages` if needed.

---

## Context

We are building a **static JSON bridge** between the production database (MySQL dump loaded to SQLite) and the browser engine (`engine.html`). This is Phase 1 of 7. Scope is deliberately narrow: **Ria transactions only**, **Q1 2026 only**, **static JSON output**. Once this runs end-to-end we add TerraPay, then the rest.

### Source files you will find

- `~/cadorim-engine/engine.html` — the browser engine (single file, ~800 lines — larger after pending-separation if that has landed)
- `~/cadorim-engine/cadorim_engine/` — Python package (empty-ish, you will add modules here)
- `~/cadorim-engine/load_production.py` — production loader (existing — extend it, don't duplicate)
- `~/cadorim-engine/tests/` — pytest scaffold (exists)
- `~/cadorim-engine/alembic/` — DB migrations (do NOT touch)
- `~/cadorim-engine/CLAUDE.md` — canonical project instructions (READ THIS FIRST — it contains the 14 DB types → 5 business flows mapping and the key account IDs you need)
- `/tmp/cadorim.sqlite` — the production dump loaded as SQLite
- `~/Documents/Claude/Projects/Cadorim Accounting/Data API transaction/` — original MySQL dump files

If `/tmp/cadorim.sqlite` does not exist, regenerate it. There is likely a loader script in `~/Documents/Claude/Projects/Cadorim Accounting/outputs/load_dumps.py` (per the user's memory). If not, write a new one that loads the `.sql` dumps in `Data API transaction/` into SQLite. This is a one-time prep step.

### What "Ria" means in the DB

From CLAUDE.md:

```
| ria | 5,370 rows | 45.8M MRU | Flow 1 — International
```

- `wallet_db_transactions.type = 'ria'` identifies Ria transactions.
- Debit side = Account[cash] (a caisse)
- Credit side = Account[cash] or Account[main] (payout leg)
- Commission ≈ 30 MRU
- The `description` column contains the Ria reference code

There's also a SECONDARY Ria flow in `transfert` with `debitable_id=782` (RIA CASH OUT) — but for THIS prompt, handle only `type='ria'` (5,370 rows). The `transfert` variant (~930 rows) is Phase 1b.

---

## DECISIONS ALREADY MADE

- **Delivery model**: static JSON export (not an API)
- **Scope**: Ria only, Q1 2026 only (`created_at` between 2026-01-01 and 2026-03-31 inclusive)
- **Cutoff for opening balances**: 2026-01-01 (everything before goes into `opening` state; everything from 2026-01-01 onward flows through the engine)
- **Settlements**: **deferred** to Phase 2 — for this pass, export an empty `settlements` array. Receivables will grow without being cleared — that's expected, we'll reconcile in Phase 2.

---

## DELIVERABLES

### 1. `cadorim_engine/classifier.py`

A pure Python module with one public function:

```python
def classify(row: dict, accounts: dict) -> dict | None:
    """
    Classify one wallet_db_transactions row into a canonical engine event.
    
    Args:
        row: a dict with keys matching wallet_db_transactions columns
            (id, debitable_id, debitable_type, creditable_id, creditable_type,
             amount, frais, commission, tax, type, status, accounting_status,
             description, reference, external_transaction_id, created_at, updated_at)
        accounts: dict mapping account_id -> {name, type, ...} from wallet_db_accounts
    
    Returns:
        engine event dict with canonical shape, OR None if the row
        should not produce an engine transaction (e.g., not yet supported,
        failed/canceled, test data).
    """
```

**For this prompt, the classifier handles ONLY `row['type'] == 'ria'`.**

Other types return `None` with a comment explaining they will be added in later phases.

**Canonical Ria event shape (output):**

```python
{
    "id": f"T-ria-{row['id']}",           # unique, prefixed
    "created_at": row['created_at'],      # ISO date string
    "posted_at": row['created_at'],       # Ria is immediate, no queue in DB
    "status": "released",                 # if row.status == 'completed' and accounting_status == 'posted'
    "Par_l": "ria",                       # partner code (engine uses lowercase)
    "Cur_k": "EUR",                       # Ria is always EUR
    "Amount_j": round(row['amount'] / FX_RATE, 2),  # EUR amount
                                          # See fx_rate note below
    "Client_i": None,                     # not stored in DB for Ria
    "Client_m": row.get('description', ''),  # receiver info often in description
    "Local_Par_n": _infer_local_par(row, accounts),  # see below
    "Amount_mru_h": row['amount'],        # the MRU amount paid out
    "commission_a": row.get('commission', 0),
    "cost_payout_a": 0,                   # Ria cashout has no explicit cost
    "fx_gain_a": 0,                       # L1 FX gain — compute in Phase 2
    "profit_transaction_a": row.get('commission', 0),  # = commission - cost
    "reference": row.get('reference', ''),
    "source_row_id": row['id'],           # traceability back to DB
}
```

**`Local_Par_n` inference** — Ria payouts land in different caisses depending on the creditable account:

- If `creditable_id == 18` (Cadorim caisse) → `"caisse_cadorim"`
- If `creditable_id == 19` (IMARA caisse) → `"caisse_imara"`
- If `creditable_id == 33` (NKTT BMD / Mboirick) → `"caisse_mboirick"`
- If `creditable_id == 35` (Seilibaby) → `"caisse_seilibaby"`
- If `creditable_id == 782` (RIA CASH OUT) → `"ria_cash_out"`
- Else: `"caisse_" + slugified_account_name`

**FX rate** — For this phase, use a **fixed approximation**: `FX_RATE = 42.5` MRU per EUR (the ~Q1 2026 average). Mark this with a comment: `# TODO Phase 2: per-transaction FX from wallet_db_transactions_devises`. Real FX comes in Phase 2 when we ingest settlements.

**Filter out** rows where:
- `status` ∈ {'canceled', 'failed'} → return None
- `accounting_status == 'rejected'` → return None
- `created_at` is missing → return None

---

### 2. `cadorim_engine/opening.py`

```python
def compute_opening(sqlite_path: str, cutoff_date: str = '2026-01-01') -> dict:
    """
    Compute the opening state at cutoff_date by replaying all events
    BEFORE cutoff_date from the SQLite dump.
    
    Returns a dict matching the engine's SIM_INITIAL shape:
    {
        "cash": { "sim_caisse_cadorim": X, "sim_caisse_imara": X, ... },
        "wallet": { ... },
        "bank": { ... },
        "client_float": X,
        "working_capital": X,
        "opening_receivable": {
            "sim_ria": { "foreign": X, "currency": "EUR", "mru": Y },
            ...
        }
    }
    """
```

**For this phase, compute only:**
- `cash` balances for the 5 caisses above (Cadorim, IMARA, Mboirick, Seilibaby, Ria Cash Out) — sum of debits minus credits before cutoff
- `opening_receivable['sim_ria']` — sum of Ria transactions before cutoff where settlement has NOT arrived (since we don't have settlements yet, treat ALL pre-cutoff Ria txns as unsettled — overestimate is fine for this phase, we'll correct in Phase 2)
- All other keys (`wallet`, `bank`, `client_float`, `working_capital`) default to zero or small placeholder values for now. Document this with `# TODO Phase 1b/2: ...` comments.

---

### 3. Extend `load_production.py`

Add a new CLI entry point `export_ria_q1`:

```bash
python load_production.py export_ria_q1 --out data/production_data_ria.json
```

It should:
1. Ensure `/tmp/cadorim.sqlite` exists (regenerate if missing — see note about `load_dumps.py`)
2. Load `wallet_db_accounts` into a dict
3. Iterate `wallet_db_transactions` where `type = 'ria'` and `created_at BETWEEN '2026-01-01' AND '2026-03-31 23:59:59'`
4. Classify each row via `classify()` — skip Nones
5. Compute opening state via `compute_opening(..., cutoff_date='2026-01-01')`
6. Write JSON:

```json
{
    "generated_at": "2026-04-20T...",
    "scope": "ria_q1_2026",
    "cutoff_date": "2026-01-01",
    "opening": { ... SIM_INITIAL shape ... },
    "transactions": [ ... engine events ... ],
    "settlements": [],
    "withdrawals": [],
    "stats": {
        "rows_scanned": N,
        "rows_classified": N,
        "rows_skipped": N,
        "total_mru": X
    }
}
```

Default output path: `~/cadorim-engine/data/production_data_ria.json` (create the `data/` directory if it doesn't exist).

---

### 4. Tests — `tests/test_classifier.py`, `tests/test_opening.py`, `tests/test_export.py`

Minimum:

**`test_classifier.py`** — 5 canonical Ria rows (fetch real rows from `/tmp/cadorim.sqlite` via a fixture or hardcode dicts). Assert:
- Each returns a dict with all expected keys present
- `Par_l == 'ria'` and `Cur_k == 'EUR'`
- `Amount_j > 0`, `Amount_mru_h == row['amount']`
- Canceled/failed rows return `None`
- A non-Ria row (e.g., `type='depot'`) returns `None`

**`test_opening.py`** — one test:
- `compute_opening('/tmp/cadorim.sqlite', '2026-01-01')` returns a dict with all expected keys
- All cash values are numeric (not None)
- `opening_receivable['sim_ria']['foreign']` is numeric and >= 0

**`test_export.py`** — one end-to-end test:
- Run the export to a tmp path
- Load the resulting JSON
- Assert `scope == 'ria_q1_2026'`, `len(transactions) > 0`, `opening` has expected keys
- Assert every transaction has `id`, `created_at`, `posted_at`, `status`, `Par_l`, `Cur_k`, `Amount_j`, `Amount_mru_h`

Run tests with `pytest -xvs tests/` after implementing. Report results.

---

### 5. `engine.html` — add the Simulation / Production toggle

In the existing top navigation (where tabs live), add a **data source switch** on the far right:

```
[ Simulation | Production ]
```

Default: **Simulation** (preserve all current behavior).

When **Production** is clicked:
1. Fetch `./data/production_data_ria.json` (relative path — the HTML file and the JSON sit in the same git root, JSON is in `./data/`)
2. On success: replace in-memory `SIM_TXS` / `SIM_SETT` / `SIM_WD` / `SIM_INITIAL` with the fetched `transactions` / `settlements` / `withdrawals` / `opening`
3. Re-run `runEngine()` and re-render all tabs
4. Show a small banner: `📡 Production data · N transactions · generated YYYY-MM-DD`
5. On error (fetch fails): show a yellow banner `⚠ Production data not available yet — fall back to Simulation` and stay on Simulation

**Do not rewrite the engine logic** — the point is that production data plugs into the same `runEngine()` because we enforced the canonical event shape. If anything fails because of shape mismatch, that's a classifier bug, fix the classifier not the engine.

---

## ACCEPTANCE CRITERIA

1. `python load_production.py export_ria_q1 --out data/production_data_ria.json` runs to completion with no errors.
2. The output JSON exists at `~/cadorim-engine/data/production_data_ria.json` and has >1,000 transactions.
3. `pytest -xvs tests/` passes all new tests.
4. Opening `engine.html` in a browser, clicking **Production** switches to production data and renders all 5 tabs (plus Budget if the pending-separation prompt landed) without crashing.
5. The CEO tab's monthly trend shows real 2026 Q1 data with realistic MRU magnitudes (hundreds of thousands to millions per month).
6. Receivables for Ria are large and growing (expected — no settlements yet; this is the known gap we'll address in Phase 2).
7. Simulation toggle still works and shows the original simulated data untouched.

---

## WORKING PROTOCOL

1. **Read `CLAUDE.md` first.** Then read `engine.html` (at minimum the `SIM_INITIAL`, `SIM_TXS`, `SIM_SETT`, `SIM_WD` sections and the top navigation markup). Understand the event shape before writing the classifier.
2. Before implementing: open `/tmp/cadorim.sqlite` (create it if missing), run `SELECT * FROM wallet_db_transactions WHERE type='ria' LIMIT 5;` and inspect real rows. Read the `description` and `reference` columns on a few Ria rows to understand what's there.
3. Implement classifier + tests first. Iterate until tests pass.
4. Then opening balances + test.
5. Then export script.
6. Then engine.html toggle.
7. Run the full export, open the engine, verify the CEO tab looks plausible.

---

## WHAT TO REPORT BACK

When done, report:
- Line counts for each new/modified file
- `pytest` output (copy the summary)
- Number of Ria transactions exported + total MRU volume
- Opening receivable for Ria (EUR and MRU)
- Any row that the classifier rejected with an unclear reason (include 3–5 examples)
- Any ambiguity you resolved by your own judgment
- Any assumption that could break when we extend to other flows

---

## DO NOT

- Do not modify `alembic/` or any existing migration
- Do not change the engine's math (computeL1, computeL2, applyTx, applySett, applyWd)
- Do not rewrite the engine's tab structure
- Do not add TerraPay, Wallet, or other flows — Ria only
- Do not parse settlements from PDFs — Phase 2
- Do not install unreviewed new dependencies beyond: sqlite3 (stdlib), json (stdlib), pytest (already in requirements)
