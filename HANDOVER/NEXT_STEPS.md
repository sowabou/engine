# Next Steps — Cadorim Accounting Engine

Prioritized open work as of 18-May-2026. Each item has: **owner suggestion**, **acceptance criteria**, **starting files**.

Work top-down. Items 1–3 are blocking; 4–6 are operational; 7+ are roadmap.

---

## 🔴 P1 — Investigate the 29M MRU Ria reconciliation gap (Q1 2026)

**The problem.** Grand Livre and production DB disagree by 29,325,213 MRU on Ria Q1 2026 cash-outs.
- Grand Livre — Caisse Babe + Tidjany BMI retraits = 51,710,768 MRU (103 events)
- Production DB — Ria cash-outs (`type='ria'`) = 22,385,555 MRU (2,885 txns)

Plus: commission booking **dropped to zero** in March + April 2026 (1,995 cash-outs, 16.7M MRU, 0 MRU commission). Nov 2025–Feb 2026 had ~23–36K MRU/month.

**Hypothesis.** The Grand Livre is a treasury view (bulk wires in / out). The DB is the operational view (every beneficiary). Both are partial. The 29M may be:
- Cash withdrawals not yet matched to individual payouts
- TerraPay TPFN payouts mis-classified into the "transfert" bucket (see P2)
- Internal caisse movements miscoded as Ria

**Acceptance criteria.**
- A reconciliation report (xlsx) that accounts for every MRU in both sources
- Either: explanation that closes the gap, OR a confirmed list of unexplained transactions with values + dates
- Decision on whether the commission stoppage in March was operational (rate changed?) or a booking bug

**Starting files.**
- `Grand_Livre_Ria_2026.xlsx`
- `../data/wallet_db_transactions.sql` (loaded via `load_production.py`)
- `../cadorim_engine/checks/check_ria_l1.py`
- `PROJECT_MEMORY.md` §7 (full context)

**Suggested owner.** Abou + Claude. Start with a SQL query to confirm the gap and split it by date / counterparty.

---

## 🔴 P2 — Fix the TerraPay TPFN classifier gap

**The problem.** 1,029 real TerraPay customer payouts are mis-classified.
- `production_data_all.json` shows 777 rows with `Par_l='terrapay'` → these are caisse/wallet **transfers**, NOT customer payouts.
- The **real** TerraPay payouts have `external_transaction_id LIKE 'TPFN%'` and are tagged as `db_type='depot'` (7) or `db_type='transfert'` (1,022).

**Root cause.** `cadorim_engine/classifier.py` keys off `type` field. `depot` maps to Flow 2 (Wallet Deposit), so TerraPay payouts get lost in the wallet bucket.

**Fix.** Classifier should check `external_transaction_id` BEFORE `type`:
```python
if ext_id.startswith('TPFN'):
    return Flow1_TerraPay
elif ext_id.startswith('TPRA'):
    return Flow1_Ria  # to verify with prod data
elif ext_id.startswith('TPJA'):
    return Flow1_Juba  # to verify
# ... then fall through to type-based classification
```

**Acceptance criteria.**
- `classifier.py` correctly tags all 1,029 TPFN rows as `Par_l='terrapay'`
- Re-run TerraPay L1 — numbers match the workaround loader `terrapay_cadorim_loader.load_cadorim_terrapay()`
- Confirm no false positives (e.g., a legit `depot` getting re-routed)
- Verify TPRA / TPJA prefixes exist in prod data; if so, extend the rule

**Starting files.**
- `../cadorim_engine/classifier.py`
- `../cadorim_engine/checks/terrapay_cadorim_loader.py` (the working SQL-direct loader — use as reference truth)
- `PROJECT_MEMORY.md` §6

**Suggested owner.** Claude implements; Abou validates against TerraPay statements.

---

## 🟡 P3 — Build the plafond / pending-queue module

**Status.** Design is complete. Implementation pending.

**The model.** Blocked transactions are **queued, not canceled**. The beneficiary is waiting. Engine must:
- Maintain 3 states: Executed, Pending, Released
- Track `created_at` (entered queue) and `posted_at` (released)
- Auto-rescan the queue after every liquidity event (settlement, withdrawal)
- Generate treasury movements (caisse → wallet) to release pending
- Honor priority (P1 clears 2-3x faster than P4)
- Never let wallets go negative
- Key metric: **time-to-release** (days in queue), NOT lost profit

**Hard rule.** Pending txns appear ONLY in the queue view. NEVER in posted ledgers (CEO, Treasury, Positions, partner ledgers).

**Acceptance criteria.**
- New `cadorim_engine/queue/` module
- Pending queue view in `engine.html` (separate tab)
- Liquidity event listener that scans and releases
- Top-up generator (caisse → wallet)
- Negative-balance guard
- Time-to-release metric surfaced in Operations

**Starting files.**
- `../PENDING_QUEUE_PROMPT.md` (full spec)
- `../PLAFOND_BUILD_PROMPT.md` (related)
- `../PLAFOND_INTELLIGENCE_PROMPT.md`
- `../PLAFOND_UX_FIX_PROMPT.md`
- `../PENDING_SEPARATION_PROMPT.md`
- `../WALLET_BALANCE_GATE_PROMPT.md`
- `PROJECT_MEMORY.md` §12

**Suggested owner.** Claude implements (working from PENDING_QUEUE_PROMPT.md). Abou reviews each phase before merge.

---

## 🟡 P4 — May 2026 data refresh

**Missing inputs:**
- Real April BMI PDF (the "Avril 26" file is mislabeled Feb data)
- SWIFT emails past 31-Mar-2026
- Cado02 transaction dossier for April/May
- Binance P2P file for April/May
- TerraPay statement xlsx for April/May

**Action.**
1. Connect Gmail (Cowork → Settings → Connectors → Gmail) using the account that receives the Ria forwards
2. Pull new SWIFT + CorrespPayment emails into `../data/settlements/mails/`
3. Download fresh Cado02 dossier from Etherscan / wallet UI
4. Pull new Binance P2P export
5. Request April/May TerraPay statement from TerraPay support
6. Rebuild all indexes (see `PROJECT_MEMORY.md` §13 monthly refresh)

**Acceptance criteria.**
- All 5 reconciliation tabs in `engine.html` show data through end of May 2026
- No "missing" warnings in the engine logs

**Suggested owner.** Operations team + Abou. Claude executes the refresh once files are dropped.

---

## 🟡 P5 — Resolve caisse naming drift

**The problem.** Mboirick / Tidjany / Babe don't map cleanly across the DB, Grand Livre, and instructions. Three sources, three vocabularies (`PROJECT_MEMORY.md` §8).

**Action.**
1. Sit with Dr Neine and confirm canonical mapping
2. Add account-number aliases in a config file
3. Update classifier and reconciliation queries to use canonical names
4. Update `PROJECT_MEMORY.md` §8 with the resolution

**Acceptance criteria.**
- A single canonical-name table that maps each caisse to: DB account ID, Grand Livre account number, instruction name
- All queries reference canonical names
- Memory updated

**Suggested owner.** Abou (with Dr Neine for the business call).

---

## 🟢 P6 — Find the 2025 Ria ledger (Oct–Dec)

DB has Oct–Dec 2025 Ria activity. Grand Livre Ria 2026 does not include it. A separate 2025 ledger may exist.

**Action.** Ask Dr Neine and Mboirick where Oct–Dec 2025 Ria entries were booked. Locate the file or confirm it doesn't exist.

**Acceptance criteria.** Either the 2025 ledger is located and added to the project folder, OR the gap is documented as "Oct–Dec 2025 not professionally journalized."

---

## 🟢 P7 — Phase 3: Connect engine to live Cadorim API

The Python engine reads from MySQL dumps today (snapshot, not live). Phase 3 connects to the production API for real-time data.

**Action.**
1. Abou designs the API endpoints needed (read-only first: transactions, orders, accounts, balances)
2. Claude updates the engine adapters to call live API instead of reading from SQL dumps
3. Add caching layer
4. Update refresh workflow

**Acceptance criteria.**
- Engine pulls transactions live (with sensible cache TTL)
- All 11 tabs work against live data
- No manual SQL dump refresh needed for daily operation

**Dependencies.** P2 done (classifier fix), P4 done (May 2026 data current).

**Suggested owner.** Abou designs API, Claude integrates.

---

## 🟢 P8 — Phase 5: PHP rewrite for production

The Python engine is the prototype. Production target is PHP (matches the existing Cadorim platform stack: Abou + Mboirick).

**Approach** (per Dr Neine's plan):
- Python prototype is throwaway; defines math and data contracts
- PHP rewrite preserves the universal model
- Use Cadorim's existing PHP framework

**Action plan.** Don't start until P3 and P7 are done. Then:
1. Define data contracts (DTOs) shared between Python and PHP
2. Build PHP version of the classifier
3. Build PHP version of the L1/L2 checks
4. Migrate the dashboard
5. Cut over

**Suggested owner.** Abou + Mboirick. Claude can help port specific modules.

---

## 🟢 P9 — Documentation & sign-off

When the engine is feature-complete:
- Publish a one-pager for the Cadorim board
- Get CEO sign-off on the universal model (lock it in writing)
- Establish the monthly close process around the engine
- Train the operations team

---

## Quick check — what's blocking what

```
P2 (TPFN fix) ──> P1 (29M gap may partially explain itself)
                  └─> P7 (live API can't be trusted until classifier is right)
                       └─> P8 (don't port a wrong classifier to PHP)

P3 (pending queue) ──> P4 (May data) ──> P7 (live API)
P5 (caisse naming) ──> P1 (gap analysis cleaner once names align)
```

**Recommendation:** start with P2 (smallest, unblocks the most). Then P1 with the fixed classifier. Then P3 in parallel with P4.
