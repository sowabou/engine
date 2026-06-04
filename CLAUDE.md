# Cadorim Accounting — Claude Operating Instructions

> **New to this repo?** Read `HANDOVER/README.md` first — it's the project-wide orientation. Then come back here for the deep technical reference. Open issues are in `HANDOVER/NEXT_STEPS.md`. Strategic context, feedback rules and historical decisions are in `HANDOVER/PROJECT_MEMORY.md`.

## Role
Act as a mathematical systems architect. Dr. Neine is a mathematician and statistician — he sees accounting as algebra, not journal entries. Think in functions, parameters, and dimensions. If anything is unclear or risky, **challenge and propose a safer structure before executing**.

## Core Architecture: The Universal Transaction Engine

There are no pipelines. There is ONE parameter-driven engine. ALL flows use the same universal function — international remittance, national wallet (Cadorim Wallet), B2C (CadorimPay), agent operations, and treasury movements. Some parameters go to zero for specific contexts, but the structure never changes.

### Five Business Flows, One Model

1. **International Remittance**: Client_i → Amount_j in Cur_k via Par_l → Client_m via Local_Par_n. Full Layer 1 + Layer 2.
2. **Cadorim Wallet (national P2P, "MauriPay")**: MRU→MRU, FX=0. Two sub-types:
   - Type A (internal): wallet→wallet, stays in system, cost_payout=0
   - Type B (cashout): wallet→Local_Par_n or Agent, cost_payout >= 0
3. **CadorimPay (B2C)**: Business (SNDP) deposits (prefunding), then pays out internal (Type A) or external (Type B)
4. **Agent Operations**: Agents cashout for all flows, earn fees (=our cost_payout_a), move funds between themselves
5. **Treasury**: Balance transfers between Local_Par_n/Bank_t/caisses/agents + expense payments (salary, electricity). Cost only, no revenue.

### Independent Parameter Registries

Each dimension is its own registry. Add/remove without touching logic:

- `Par_l` — partner/source (Ria, TerraPay, Juba, cadorim_wallet, cadorim_b2c, cadorim_agent, treasury)
- `Bank_t` — settlement account (BMI, BPM, BRED, ETH_Cado01, ...)
- `Local_Par_n` — payout channel (Sedad, Click, Masrvi, Bankily, MauriPay, Caisse_Mboirick, Caisse_Tidjany, Caisse_Babe, wallet_internal, Agent_x, ...)
- `Cur_k` — currency (EUR, USD, USDC, MRU)
- `Client_i` — sender
- `Client_m` — receiver in Mauritania

### Configurable Relationships

Combinations are configuration rows, composed freely:

- `Config(Par_l, Cur_k)` — which currencies a partner supports
- `Config(Par_l, Bank_t)` — where a partner settles
- `Config(Par_l, Local_Par_n)` — which payout channels for a partner

New partner = new registry entries + config rows. New currency on existing partner = one config row. Zero logic changes.

### Parameterized Formulas

- `commission(Par_l, Cur_k)` — rate per partner per currency
- `cost_payout(Local_Par_n)` — cost per local channel
- `FX(Par_l, Cur_k, date)` — exchange rate per partner per currency per day

### The Universal Transaction

Every transaction_a is:

`transaction_a = (Client_i, Amount_j, Cur_k, Par_l, Client_m, Local_Par_n, Amount_mru_h)`

Flow: Client_i → Amount_j in Cur_k → Par_l → Client_m → Local_Par_n → Amount_mru_h in MRU

Settlement (separate timeline): Par_l → Amount_j in Cur_k → Bank_t

### Two-Layer Profit Model

**Layer 1 — Transaction level (daily, real-time):**
- `commission_a` — fee on transaction
- `cost_payout_transaction_a` — payout cost via Local_Par_n
- `Gain_transaction_a = commission_a - cost_payout_transaction_a`
- `transaction_a_fx_gain` — FX spread at transaction level
- `Profit_transaction_a = Gain_transaction_a + transaction_a_fx_gain`

**Layer 2 — Settlement level (per Par_l × Bank_t pair):**
- `gain_sett_Par_l_Bank_t` — FX gain at settlement
- Belongs to (Par_l, Bank_t) pair, NOT individual transactions
- Realized when settlement arrives

**Total:** `Total_Profit = Σ Profit_transaction_a + Σ gain_sett_Par_l_Bank_t`

### Derived Balances

- `Balance_Local_Par_n = Σ inflows - Σ payouts`
- `Balance_Bank_t = Σ settlements - Σ withdrawals`
- `Receivable_Par_l = Σ Amount_j where settlement pending`
- `Payable_Local_Par_n = Σ Amount_mru_h where payout pending`

### Three Dashboards (same data, different GROUP BY)

- **CEO**: Profit by period, by Par_l, receivables, growth, margin
- **Operations**: transactions, payout status, Local_Par_n balances, costs, failures
- **Treasury**: Bank_t balances, Local_Par_n balances, receivables, payables, settlement FX, liquidity

---

## Production Database — Verified Structure (as of 2026-04-17)

The production system is PHP microservices on Azure MySQL (`cadorim-mysql.mysql.database.azure.com`). Five SQL dump files, loaded into SQLite for analysis. The engine reads from TWO primary tables plus three supporting tables.

### TWO data sources — both required

**Table 1: `wallet_db_transactions`** — the FULL double-entry journal (18,225 rows, Jan 2025 → Apr 2026).
This is the master record. Every money movement in the system is here.

**Table 2: `partner_db_orders`** — CASHOUT orders only (4,623 rows, Oct 2025 → Apr 2026).
This is a subset — payout operations via Sedad/Masrivi/Click/Bankily/MauriPay. It links to transactions via reference.

**Supporting tables:** `wallet_db_accounts` (818 accounts), `wallet_db_bank_accounts` (80 external accounts), `wallet_db_transactions_devises` (2,222 FX journal entries).

### wallet_db_transactions — Column Map

| Column | Description |
|---|---|
| id | Primary key |
| debitable_id, debitable_type | Source account (Account or Customer) |
| creditable_id, creditable_type | Destination account (Account, Customer, or Merchant) |
| amount | Transaction amount in MRU |
| frais | Fees charged to customer |
| commission | Commission on transaction |
| tax | Tax amount |
| type | Transaction type (14 distinct values — see mapping below) |
| code | Transaction code (mostly NULL) |
| status | completed / canceled / failed / pending |
| accounting_status | posted / rembursed / rejected / waiting |
| description | Free text (contains Ria codes, Juba refs, partner details) |
| reference | Primary reference key |
| external_transaction_id | Links to partner_db_orders for TerraPay |
| created_at, updated_at | Timestamps |
| details | JSON metadata |

### partner_db_orders — Column Map

| Column | Description |
|---|---|
| id | Primary key |
| reference | Links to transactions.reference (non-TerraPay) or transactions.external_transaction_id (TerraPay) |
| partner_name | "terrapay", NULL (early data), "cadorim-agent", "mauripay" |
| sender_name, sender_phone | Client_i |
| receiver_name, receiver_phone | Client_m |
| sender_amount | Amount_j (in Cur_k) |
| receiver_amount | Amount_mru_h |
| fee | Commission from partner side |
| rate | FX rate (39.0 for TerraPay USD, 0 for MRU flows) |
| type_transaction | Always "wallet" |
| channel, provider | Local_Par_n (sedad/masrivi/click/bankily/mauripay) |
| status | success / failed |
| currency | Cur_k (USD for TerraPay, MRU for others) |
| order_id | External order reference |
| transaction_code | Partner API code |
| country_from, country_to | Origin/destination |

### wallet_db_accounts — Account Types

| Type | Count | Role in Model |
|---|---|---|
| main | 330 | System accounts: SEDAD, MASRIVI, RIA, BANKILY, COMPTE CADORIM, SNDP, Bridge EUR, etc. |
| cash | 235 | Caisse accounts: Cadorim (id=18), IMARA (id=19), Agent_COMPTE_x, CAISSE-n_name |
| commission | 230 | Agent commission accounts: AGENT_COMMISSION_x, COMMISSION-n_name |
| aggregated | 12 | Parent aggregation accounts (COMPTE PARTENAIRE AGRÉÉS, COMPTE CLIENTS AGRÉÉS, etc.) |
| charge | 3 | Expense accounts: COMPTE CHARGE AGENT (id=440), FRAIS_imara (id=496), Charges divers (id=425) |
| merchant | 3 | Payment merchants: Canal+, SNDE, Somelec |
| bank | 2 | Bank references: BMCI, test USD |
| partenaire | 2 | Partner transit: TERRAPAY - CASH RECU (id=422), JUBA EXPRESS (id=778) |
| product | 1 | Revenue: COMPTE PRODUIT PARTENAIRES (id=443) |

### KEY ACCOUNTS (used in flow classification)

| ID | Name | Type | Role |
|---|---|---|---|
| 18 | Cadorim | cash | Main caisse — hub for Ria, agent, wallet operations |
| 19 | IMARA | cash | Secondary caisse — deposits, withdrawals, transfers |
| 422 | TERRAPAY - CASH RECU | partenaire | TerraPay receivable/transit account |
| 778 | JUBA EXPRESS | partenaire | Juba Express transit account |
| 782 | RIA CASH OUT | main | Ria-specific account (debited on Ria payouts) |
| 808 | Bridge EUR | main | CadorimPay EUR inbound (B2C) |
| 501 | COMPTE CADORIM (transfert) | main | CadorimPay MRU transfer/payout account |
| 440 | COMPTE CHARGE AGENT | charge | Agent commission expense (debited when commissions distributed) |
| 16 | SEDAD TRANSACTION AUTOMATIQUE | main | Sedad automated payout account |
| 21 | MASRIVI TRANSACTION AUTOMATIQUE | main | Masrivi automated payout account |
| 33 | CAISSE - 12_NKTT BMD | cash | Mboirick/BMD caisse |
| 35 | CAISSE - 13_Agence Seilibaby | cash | Seilibaby agent caisse |

### 14 DB Transaction Types → 5 Business Flows

This is the CRITICAL mapping. The `type` field in `wallet_db_transactions` has 14 values. Some map 1:1 to flows, but `transfert` (the largest at 6,570 rows) is OVERLOADED — it covers 4 different flows. Classification requires inspecting the **account pattern** (debitable_type × creditable_type × account.type).

| DB Type | Count | Amount (MRU) | Business Flow | Classification Rule |
|---|---|---|---|---|
| **ria** | 5,370 | 45.8M | Flow 1 — International | Direct. Debit=Account[cash], Credit=Account[cash/main]. Commission=30 MRU. Ria code in description. |
| **juba** | 11 | 69K | Flow 1 — International | Direct. Debit=Account[partenaire:JUBA], Credit=Account[main/cash]. |
| **transfert** | 6,570 | 101.4M | **MIXED — must split** | See sub-classification below |
| **transfert_cadorim** | 273 | 2.4M | Flow 3 — B2C (inbound) | Direct. Debit=Account[main:Bridge EUR], Credit=Account[main:COMPTE CADORIM]. EUR→MRU. |
| **retrait_commande** | 237 | 3.0M | Flow 3 — B2C (payout) | Direct. Debit=Account[main:COMPTE CADORIM], Credit=Account[cash/main:Bankily/Masrvi/Cadorim]. |
| **depot** | 771 | 14.6M | Flow 2 — Wallet Deposit | Direct. Debit=Account[cash:IMARA/Cadorim], Credit=Customer. Cash-in to wallet. |
| **retrait** | 236 | 3.6M | Flow 2B — Wallet Cashout | Direct. Debit=Customer, Credit=Account[cash:IMARA]. Frais charged. |
| **transfert_extra** | 120 | 705K | Flow 2B — Wallet Cashout | Direct. Debit=Customer, Credit=Account[cash:IMARA]. Frais=40-150. External cashout. |
| **commission** | 3,082 | 492K | Flow 4 — Agent (commission) | Direct. Debit=Account[charge:CHARGE AGENT], Credit=Account[commission:AGENT_COMMISSION_x]. |
| **alimentation_compte** | 1,082 | 268K | Flow 4 — Agent (funding) | Direct. Debit=Account[commission], Credit=Account[cash:caisse]. Commission→caisse sweep. |
| **virement_interne** | 84 | 89.1M | Flow 5 — Treasury | Direct. Account→Account. Large balance movements between system accounts. |
| **regularisation** | 75 | 9.5M | Flow 5 — Treasury | Direct. Accounting adjustments and corrections. |
| **recharge telephonique** | 313 | 15K | Ancillary — Telecom | Customer→Account[main:MAURITEL]. Small airtime purchases. |
| **paiement** | 1 | 320 | Ancillary — Merchant | Customer→Merchant. Only 1 occurrence (Canal+). |

### Sub-classification of `transfert` (6,570 rows)

The `transfert` type must be split by account pattern:

| Pattern | Count | Amount | Flow | Rule |
|---|---|---|---|---|
| Account[partenaire:TERRAPAY] → Account[cash] | 639 | 5.5M | Flow 1 — International (TerraPay) | debitable_id=422 (TERRAPAY - CASH RECU) |
| Account[main:RIA] → Account[cash] | ≈930 | 9.1M | Flow 1 — International (Ria variant) | debitable_id=782 (RIA CASH OUT) — secondary Ria flow |
| Customer → Account[main:SEDAD/MASRIVI] | 1,771 | 22.2M | Flow 2B — Wallet Cashout | debitable_type=Customer, creditable account.type=main, creditable_id IN (16,21) |
| Customer → Customer | 673 | 18.3M | Flow 2A — Wallet Internal (P2P) | Both debitable_type and creditable_type = Customer |
| Customer → Account[cash] | 813 | 10.7M | Flow 2B — Wallet Cashout | debitable_type=Customer, creditable account.type=cash |
| Account[cash:caisse] → Account[cash:Cadorim] | 1,996 | 36.5M | Flow 4 — Agent Operations | Both sides are Account[cash]. Caisse-to-caisse movements. |

### Linking Orders ↔ Transactions

Two link methods, covering 91% of orders:

1. `orders.reference = transactions.reference` — matches 3,141 orders (all non-TerraPay: cadorim-agent, mauripay, NULL)
2. `orders.reference = transactions.external_transaction_id` — matches 1,060 orders (TerraPay only)

Unmatched: 416 TerraPay orders + 6 NULL/test orders. The 416 are likely TerraPay orders that failed before reaching the transaction journal, or timing gaps in the dump.

### FX Journal (transactions_devises) — 2,222 rows

| Txn Type | Currency | Count | Avg Rate | Role |
|---|---|---|---|---|
| transfert_wallet | (MRU) | 1,060 | 39.00 | TerraPay USD→MRU conversion at transaction level |
| frais | (MRU) | 1,054 | 39.00 | Fee component of TerraPay transactions |
| transfert_cadorim | (EUR) | 100 | 44.49 | CadorimPay EUR→MRU conversion (Bridge EUR) |
| depot | USD | 5 | 1.00 | USD deposit (testing/special) |
| retrait | USD | 3 | 1.00 | USD withdrawal (testing/special) |

---

## Accounting Controls

### Double-entry is non-negotiable
Every transaction balances. Debit and credit posted together, same currency. FX conversion is a separate entry. No netting.

### Separation of flows
Four buckets always distinct:
1. Client funds (liability)
2. Cadorim revenue (fees + FX margin)
3. Settlement accounts (Bank_t + Local_Par_n balances)
4. Transit / clearing accounts

### Currency integrity
Receivables stay in native Cur_k. Convert only at settlement, at documented rate. Book FX margin as revenue. Flag rate deviating >2% from market.

### Caisse mapping
- Mboirick = principal caisse (Account id=33, CAISSE - 12_NKTT BMD)
- Tidjany = secondary / operations caisse
- Babe = BMI withdrawal and CadorimPay funding caisse
- Cadorim = main hub caisse (Account id=18)
- IMARA = deposit/withdrawal caisse (Account id=19)

Every cash line names its caisse. Do not reassign without confirmation.

### Traceability
Every entry carries: `transaction_id`, `date`, `Amount_j`, `Cur_k`, `Amount_mru_h`, `FX rate`, `Par_l`, `Local_Par_n`, `Bank_t`, `external_reference`, `caisse`, `status`.

Missing any field → do not post.

### Automated controls
Before posting, detect and flag:
- Duplicates (same reference + date + amount + counterparty)
- Missing legs of a double-entry
- Amount mismatches between source and ledger
- Delayed settlements
- Abnormal FX rates (>2% deviation)
- Negative balances on any account
- Unknown counterparties

### Approval gates
Never close a month, overwrite a ledger, or execute irreversible actions without explicit "yes, close." Always preview first.

## Single source of truth
The authoritative ledger is the master workbook in this folder. Bank statements, wallet exports, partner notifications are primary evidence. No entry without an archived source document.

## File hygiene
- Ledgers: `Cadorim_Ledger_YYYY-MM.xlsx`
- Reconciliations: `Recon_YYYY-MM.xlsx` (not per pipeline — universal)
- French libellés (débit, crédit, contrepartie, libellé)
- Save to this folder only

## Existing skills
Use specialized skills for data ingestion, but remember they feed INTO the universal engine:
- `cadorim-accounting` — bank receipts, Binance P2P, caisse mapping
- `ria-accounting` — Ria SWIFT / Wire / Excel parsing
- `terrapay-accounting` — USDC / USD / EUR prefunding parsing

These skills parse source documents. The accounting logic is the universal model above.

## What to avoid
- Pipeline-specific logic (Ria-specific, TerraPay-specific — parameterize instead)
- "Black box" entries or unexplained lines
- Hardcoded relationships between parameters
- Mixing client funds with company revenue
- Approximation in FX or balances
- Posting without a source document
- Closing a period without variance sign-off
- Traditional accounting jargon when math notation is clearer
- Classifying transactions by `type` string alone — always check account pattern for `transfert`
