# Cadorim Accounting Engine — Project Memory

Consolidated context that Dr Neine built up over months of working sessions. This file replaces the per-machine auto-memory so the knowledge travels with the project.

When Claude (or anyone) starts working on this project, this is the single document that explains *why* things are the way they are. The deep technical reference lives in `../CLAUDE.md` — this file is the strategic and historical context around it.

---

## 1. The core idea (non-negotiable)

Dr Neine is a mathematician and statistician. He designed the engine as **pure algebra**, not as traditional accounting.

> One universal function covers ALL Cadorim flows — international remittance, national wallet, B2C (CadorimPay), agent operations, treasury. Some parameters go to zero in specific contexts, but the structure never changes.

Never write pipeline-specific logic. Parameterize everything. Ria is just `Par_l = "ria"`. TerraPay is just `Par_l = "terrapay"`. Adding a new partner = new registry rows + config rows. Zero logic changes.

**Notation to use** (his vocabulary):
- `transaction_a = (Client_i, Amount_j, Cur_k, Par_l, Client_m, Local_Par_n, Amount_mru_h)`
- `Par_l` — partner / source
- `Bank_t` — settlement bank
- `Local_Par_n` — payout channel
- `Cur_k` — currency

Explain in algebra and functions, never in journal-entry language.

---

## 2. Two-layer profit (the math)

**Layer 1 — Transaction level** (daily, real-time):
```
Profit_transaction_a = (commission_a − cost_payout_a) + transaction_a_fx_gain
```

**Layer 2 — Settlement level** (per `Par_l × Bank_t`):
```
gain_sett_{Par_l, Bank_t} = FX gain when settlement arrives
```
L2 belongs to the partner × bank pair, NOT individual transactions.

**Critical rule (validated 11-May-2026):** L1 and L2 are mathematically separate. Never cross-reference them — mixing inflates "gain" because unmatched transactions have unjournalized MRU outflows.

---

## 3. Five business flows, one engine

| Flow | What | Layer 1 | Layer 2 |
|---|---|---|---|
| 1. International Remittance | Ria, TerraPay, Juba — EUR/USD/USDC in, MRU out | ✓ | ✓ |
| 2A. Wallet Internal (P2P) | MauriPay wallet → wallet, MRU only | fees only | — |
| 2B. Wallet Cashout | wallet → Sedad/Click/Masrvi/Bankily/Agent | ✓ | — |
| 3. CadorimPay (B2C) | SNDP and other businesses deposit, then pay out | ✓ | EUR only |
| 4. Agent Operations | Agents do payouts for all flows, earn fees | ✓ | — |
| 5. Treasury | Bank↔Bank, caisse moves, salaries, expenses | cost only | — |

---

## 4. Production database (the source of truth)

The production system is PHP microservices on Azure MySQL (`cadorim-mysql.mysql.database.azure.com`).

**Five SQL dumps** live in `Data API transaction/` (note the trailing space in folder name):
- `wallet_db_transactions.sql` — 18,225 rows, master double-entry journal (Jan 2025 → 11-Apr-2026)
- `partner_db_orders.sql` — 4,623 cashout orders (Oct 2025 → Apr 2026)
- `wallet_db_accounts.sql` — 818 internal accounts
- `wallet_db_bank_accounts.sql` — 80 external accounts
- `wallet_db_transactions_devises.sql` — 2,222 FX journal entries (starts 20-Jan-2026)

**Loader:** `../load_production.py` parses MySQL → SQLite at `/tmp/cadorim.sqlite`. Must use `/tmp` because the mounted folder rejects SQLite creation with disk I/O error.

**Linking orders ↔ transactions** (91% coverage):
1. `orders.reference = transactions.reference` → 3,141 matches (non-TerraPay)
2. `orders.reference = transactions.external_transaction_id` → 1,060 matches (TerraPay only)

---

## 5. The classifier — 14 DB types → 5 flows

The deep mapping table lives in `../CLAUDE.md`. The CRITICAL gotcha:

The `transfert` type (6,570 rows, the largest type) is OVERLOADED — it covers 4 different flows. You MUST classify by **account pattern** (debitable_type × creditable_type × account.type), not by the type string.

| Pattern | Flow | Why |
|---|---|---|
| Customer → Customer | 2A Wallet P2P | both ends are customers |
| Account[partenaire:422] → Account[cash] | 1 TerraPay | id 422 = TERRAPAY - CASH RECU |
| Account[main:782] → Account[cash] | 1 Ria variant | id 782 = RIA CASH OUT |
| Customer → Account[main:SEDAD/MASRIVI] | 2B Wallet cashout | customer cashing out via auto-payout channel |
| Customer → Account[cash] | 2B Wallet cashout | customer cashing out at caisse |
| Account[cash] → Account[cash] | 4 Agent ops | caisse-to-caisse |

**Key account IDs to memorize:**
- `18` Cadorim main caisse (cash) — hub for Ria, agent, wallet ops
- `19` IMARA — deposit/withdrawal caisse
- `422` TERRAPAY - CASH RECU
- `782` RIA CASH OUT
- `778` JUBA EXPRESS
- `808` Bridge EUR (CadorimPay inbound)
- `501` COMPTE CADORIM transfert (CadorimPay payout)
- `440` COMPTE CHARGE AGENT
- `16` SEDAD auto-payout, `21` MASRIVI auto-payout

---

## 6. Known classifier gap — TerraPay TPFN hidden under `depot`

Status: **OPEN** (discovered 12-May-2026, not yet fixed).

- `production_data_all.json` shows 777 rows with `Par_l='terrapay'` — these are **caisse/wallet transfers, NOT customer payouts**.
- The **real** 1,029 TerraPay customer payouts have `external_transaction_id LIKE 'TPFN%'` and are classified as `db_type='depot'` (7) or `db_type='transfert'` (1,022).

The classifier in `cadorim_engine/classifier.py` keys off `type`, which maps `depot` to Flow 2 (Wallet Deposit) instead of Flow 1 (TerraPay).

**Fix path (not implemented):** classifier should check `external_transaction_id` BEFORE `type`. If it starts with:
- `TPFN` → `Par_l='terrapay'`
- `TPRA` → `Par_l='ria'` (likely)
- `TPJA` → `Par_l='juba'` (likely)

**Workaround in use:** L1 TerraPay reconciliation uses `cadorim_engine.checks.terrapay_cadorim_loader.load_cadorim_terrapay()` which queries SQL directly with the TPFN filter.

---

## 7. Open Ria reconciliation gap — 29M MRU (Q1 2026)

Status: **OPEN** (discovered 15-Apr-2026).

The Grand Livre and production DB don't reconcile for Ria:
- Grand Livre — Caisse Babe + Tidjany retraits from BMI = **51,710,768 MRU** (103 events)
- Production DB — Ria cash-outs (`type='ria'`) = **22,385,555 MRU** (2,885 txns)
- **Unexplained difference = 29,325,213 MRU**

Plus a commission booking break:
- Nov 2025 → Feb 2026: commission booked consistently (~23–36K MRU/month)
- March 2026 + April 2026: commission **dropped to zero** (1,995 cash-outs, 16.7M MRU, 0 MRU commission)
- DB commission also runs ~5.3× higher than Grand Livre over Jan–Feb

**Interpretation:** Grand Livre is a TREASURY view (wires in, BMI credits, bulk retraits). DB is the OPERATIONAL view (every beneficiary paid). Neither is "all". This is a control-environment gap — no layer stitches the two into a single source of truth.

**Note on Oct–Dec 2025:** present in the DB, absent from the Grand Livre. A separate 2025 ledger may exist — to be located.

---

## 8. Caisse naming drift (always verify)

The caisse vocabulary is **inconsistent** across three sources:

| Source | Names |
|---|---|
| CLAUDE.md instructions | Mboirick (principal), Tidjany (ops), Babe (BMI withdrawal + CadorimPay funding) |
| Grand Livre Ria 2026 | Caisse Babe (acct 10000043469), Caisse Tidjany (acct 10000042040). Mboirick not tracked. |
| Production DB | Primary Ria debit = account 40000002 "Cadorim" (used in 4,440 of 5,370 Ria rows). The Grand Livre account numbers don't exist in the DB. There's a "CAISSE - 206_baba" (account 56801861, balance 0). No "Mboirick"/"Tidjany" top-level caisses. |

**Confirmed business roles (2026-04-02):**
- Mboirick — general operations, Bankily code **11526235**
- Tidjany — general operations, linked to Bankily
- Babe — BMI withdrawals + CadorimPay funding. Typical flow: `BMI_MRU → Caisse_Babe → CadorimPay_49724069`

**Rule:** any future work mentioning Mboirick/Tidjany/Babe must verify which source the user means. Do not assume the instruction mapping is accurate until unification is decided.

---

## 9. CadorimPay (B2C platform)

Web wallet platform, mirror of real accounting (not a separate ledger).

**Key accounts:**
- `CadorimPay_49724069` — Charges account (Charge IT, phone credit, bills, salaries)
- `Hamel_Wallet_56767890` — example beneficiary wallet
- SNDP — tenant; when it deposits, creates a liability for Cadorim

**Funding:** Physical caisse (primarily Babe, which withdraws from BMI_MRU).

**4-step salary flow (e.g., 100 MRU to Hamel):**
1. DR Caisse_Babe / CR BMI_MRU — Retrait espèces
2. DR CadorimPay_49724069 / CR Caisse_Babe — Chargement compte charges
3. DR CadorimPay_49724069 / CR Hamel_Wallet_56767890 — Transfert interne
4. DR Charge_Salaire / CR Hamel_Wallet_56767890 — Paiement reconnu

**FEEDBACK RULE (don't violate):** Client/beneficiary wallets are ALWAYS CREDITED on receive, NEVER DEBITED. The debit goes to the charges account.

---

## 10. Partner reference

### Ria Money Transfer
- Nightly settlements via SWIFT (EUR) to BMI
- Banking chain: Ria (RIAIUS66) → BofA (BOFAGB22) → BNP (BREDFRPP) → BMI (BQMIMRMR)
- **Cadorim IBAN at BMI:** `MR1300024000011000003547223` (NOT Mboirick — Cadorim)
- Emails to `mel.neine@cadorim.com`, forwarded to Gmail, accessible via Gmail MCP
- Email archive: 370 SWIFT + 364 Wire + 363 CorrespPayment Excel, Sept 2024 → Apr 2026, in `mails/` and `mails (1)/` (8,150 files total)

### TerraPay
- Sends USDC from **two** ETH addresses:
  - Primary: `0x3C9fB15699BabC313DB9d5Ab96FED26c6a8a3b14`
  - Secondary: `0x8195d349c8bd1e6c68110239e2e8e5c4458e04b5` (confirmed 11-Apr-2026 — also TerraPay)
- Both send to Cado02
- TerraPay charges Cadorim 0.5% commission on USD
- Internal FX rate: USD→MRU at 39.5

### Juba Express
- EUR wire to BPM bank
- Cash agents only (Bankily integration approved Nov 2025, future)
- Commission: 1% per cash payout, USD 0.80/wallet (future)
- FX margin example (Apr 2026): Cadorim 46.20 vs Juba 45.93 = ~0.59%
- Statement contact: `bakay@cadorim.com`

### ETH addresses (mappings)
- `0x4c2c0f0b...` → **Bridge_API** — Cadorim bridge revenue, daily small amounts to Cado01
- `0xee7ae85f...` → **Binance_Exchange** — internal hot wallet, **ignore entirely**
- `0x82912b03...7E8B1` → **Binance Exchange** endpoint. Only track INCOMING. Ignore outgoing.
- `0x271e2b29...fe21705b` → **Mboirick_Euro_Account** — receives USDC from Cado01 for Charge IT
  - ⚠️ **ADDRESS POISONING detected** — scam addresses mimicking this exist. Always verify the FULL address.

---

## 11. Engine current state (12-May-2026)

The engine has **11 tabs** in `../engine.html`:
0. Setup — partners, channels, plafonds
1. CEO — clickable cards
2. Budget (legacy)
3. Treasury — bank/wallet balances
4. Operations — paginated transaction log
5. Positions — partner ledger dual-currency
6. **Check Ria L1** — daily PIN-based reconciliation
7. **Check Ria L2** — settlement-only SWIFT ↔ BMI per-credit matching
8. **Check TerraPay L2** — Cado02 USDC settlements + Binance daily FX
9. **MRU/USD Exchange** — Binance P2P daily aggregate
10. **Check TerraPay L1** — TPFN-based monthly + daily

**Q1 2026 numbers (validated 12-May-2026):**

| Check | Volume | Key finding |
|---|---|---|
| Ria L2 | 62 settlements, 1,107,735 EUR, 51,693,883 MRU received | Gain L2 = **4,615,154 MRU** (FX BMI 46.67 vs interne 42.5) |
| TerraPay L2 | 38 settlements, 552,100 USDC | Gain L2 = **682,834 MRU** (FX Binance 40.78 vs interne 39.5) |
| TerraPay L1 | 2,790 txns / 118 active days, 681,960 USD | Commission 0.5% = 3,410 USD; 26,937,426 MRU paid |
| Ria L1 | Sept 2024 → Mar 2026 | **~50% of Ria txns NOT in Cadorim DB** (MISSING_CADORIM). 28,659 unmatched PINs ≈ 1.22M EUR not journalized |

**Tunable rates** (in classifier config):
- `FX_USD_INTERNAL = 39.5`
- `FX_EUR_INTERNAL = 42.5`
- `COMMISSION_TERRAPAY = 0.005`
- `LAG_MAX_DAYS = 5` (per-credit matching)
- `FX_LOW/HIGH (Ria) = 42 / 50` (BMI rate validity band)

**Pending follow-ups:**
- No real April BMI PDF (the "Avril 26" file is mislabeled Feb data)
- No SWIFT emails archived past 31-Mar-2026
- For May 2026, need: new Cado02 xlsx, new Binance file, SWIFT/BMI for April-May
- TerraPay L1 has Dec 2025 → Apr 11 2026 data; ready to extend

---

## 12. Plafond / pending queue model

Status: **DESIGN COMPLETE, BUILD PENDING.**

Blocked transactions are **NOT canceled** — they are **QUEUED**. The beneficiary is waiting. The transaction must eventually execute.

**Three states:**
- Executed (immediate)
- Pending (waiting)
- Released (was pending, now executed)

**Key metric:** time-to-release (days in queue), NOT lost profit.

**Behavior:**
- After every liquidity event (settlement, withdrawal), re-scan the pending queue in priority order
- Auto-generate treasury movements (caisse → wallet top-up) to release pending transactions
- Wallets must NEVER go negative — if a txn would overdraw, it queues
- Priority system: P1 released before P4. CEO sees P1 clear 2-3x faster.
- Settlement goes to BANK, not wallet. Plafond usage does NOT reset on settlement. Wallet only gets money via explicit top-up.

**FEEDBACK RULE — pending separation:**
> Pending txns must NEVER appear in a partner's historical/posted ledger. They belong to a separate queue view. Once released, they move into the historical ledger with a `posted_at` date.

Every event must carry: `id`, `created_at` (entered system), `posted_at` (released/executed, null while pending), `status` (pending / released / completed / canceled / failed).

For events that never queue (settlements arriving immediately, treasury moves), `created_at == posted_at`.

---

## 13. Refresh workflow (monthly)

```bash
cd ~/cadorim-engine    # or wherever the engine repo is mounted

# Step 1: Drop new files in ../data/ or workspace root
#   - New CorrespPayment .eml → data/settlements/mails/
#   - New BMI PDFs → workspace root
#   - New Cado02_Transaction_Dossier xlsx → workspace root
#   - New Binance_P2P_USDT_MRU xlsx → workspace root
#   - New TerraPay statement xlsx → data/

# Step 2: Rebuild all indexes
python3 -m cadorim_engine.checks.build_check_index
python3 -m cadorim_engine.checks.build_exchange_account --from 2026-01-01 --to 2026-05-31
python3 -m cadorim_engine.checks.build_l2_index --from 2026-01-01 --to 2026-05-31
python3 -m cadorim_engine.checks.build_l2_terrapay_index --from 2026-01-01 --to 2026-05-31
python3 -m cadorim_engine.checks.build_terrapay_l1_index

# Step 3: Serve
python3 -m http.server 8765
# → http://localhost:8765/engine.html → Cmd+Shift+R
```

---

## 14. Feedback rules — things Dr Neine has corrected (don't repeat)

These are the working preferences. Treat them as binding.

1. **Math, not pipelines.** Use functions, parameters, tuples — never pipeline-specific code, never accounting jargon when algebra is clearer.
2. **Client wallets are CREDITED on receive.** Never debit a client wallet. The debit goes to the source/charges account.
3. **Pending ≠ historical.** Pending txns live in the queue view only. Never in posted ledgers. Every event needs `id + created_at + posted_at + status`.
4. **L1 and L2 are mathematically separate.** Never cross-reference. Mixing them inflates apparent gain.
5. **Always verify caisse naming.** Mboirick/Tidjany/Babe are ambiguous across DB, Grand Livre, and instructions. Ask before assuming.
6. **Classify `transfert` by account pattern, not type string.** It's overloaded across 4 flows.
7. **Settlement does NOT reset plafond.** Settlement goes to BANK; wallets only top up via explicit movement.

---

## 15. Tech stack & key files

- Python 3.11+, FastAPI, SQLAlchemy 2.0 async, PostgreSQL, Docker
- Project structure: see `../CLAUDE.md`
- Deep build spec: `../CLAUDE_CODE_MVP_BUILD.md`
- Active prompts (in-flight work): `../PENDING_QUEUE_PROMPT.md`, `PLAFOND_BUILD_PROMPT.md`, etc.

The eventual target stack is **PHP** (Abou + Mboirick on production). The Python engine is the working prototype that defines the math and the contracts. The PHP rewrite preserves the model.
