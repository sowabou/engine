# Claude Code Prompt — Pending Separation + Event Identification + Budget View

## Context

File: `~/cadorim-engine/engine.html` (~802 lines).

Two corrections to make across the whole engine:

1. **Pending transactions appear inside partner historical ledgers** (Positions tab → partner ledger). They should NOT. A pending transaction is a queued request, not a posted journal entry. It contaminates the audit trail, poisons running-receivable columns, and breaks period closing.
2. **Events (transactions, settlements, withdrawals) lack a clear identification contract.** Today `date` is overloaded — sometimes it means "when the txn was created", sometimes "when it was released". Every event needs:
   - `id` — unique identifier (T001, S001, W001) — already present
   - `created_at` — when the event entered the system
   - `posted_at` — when it was actually released/executed (null while pending)
   - `status` — `pending` / `released` / `completed` / `canceled` / `failed`

This applies EVERYWHERE — Positions tab partner ledgers, bank ledgers, CEO P&L, Treasury drill-downs, Operations transaction log, alerts.

---

## FIX 1 — Event identification contract

### 1.1 SIM_TXS, SIM_SETT, SIM_WD — add `created_at`

For every object in `SIM_TXS`, `SIM_SETT`, `SIM_WD`:
- Rename/supplement the existing `date` (transactions) / `date_s` (settlements) / `date_w` (withdrawals) field with an explicit `created_at`.
- Keep the existing field as the **default** `posted_at`. If `posted_at` isn't set at simulation-definition time, it is populated during `runEngine()` when the event is actually applied.
- Do NOT change the existing date values — use them as `created_at`.

**New canonical shape**:
```javascript
// Transaction
{id:"T001", created_at:"2026-01-05", posted_at:null, status:"pending", ...}
// Settlement
{id:"S001", created_at:"2026-01-20", posted_at:"2026-01-20", status:"released", ...}
// Withdrawal  
{id:"W001", created_at:"2026-02-15", posted_at:"2026-02-15", status:"released", ...}
```

Settlements and withdrawals in the sim are assumed released on their own date (so `posted_at == created_at`). Transactions get `posted_at` filled in when `runEngine()` actually applies them — which is either immediately (not queued) or later when the queue releases them.

### 1.2 `runEngine()` — stamp `posted_at` and `status` on every event

Inside `runEngine()`:
- When a transaction applies immediately: `tx.posted_at = tx.created_at; tx.status = 'released';`
- When a transaction is queued and later released: `tx.posted_at = <date release happened>; tx.status = 'released';`
- When a transaction stays queued at end of simulation: `tx.posted_at = null; tx.status = 'pending';`

The existing `wasQueued` and `timeInQueue` flags remain — they describe the path, not the final state.

### 1.3 `partnerLedger.entries` and `bankLedger.entries` carry both dates

Every entry pushed into `partnerLedgers[code].entries` and `bankLedgers[bank].entries` MUST include:
- `id`
- `created_at`
- `posted_at`
- `status`

This replaces the single `date` field on entries.

---

## FIX 2 — Pending stays out of historical ledgers

### 2.1 Stop pushing pending rows into partner ledger

Around line 415 currently there is:
```javascript
pl.entries.push({seq:null, date:ev.arrived, id:ev.id, ..., event:'pending', reason:...});
```

**REMOVE this push.** Pending events must NOT enter `partnerLedgers[].entries`.

Instead, create a separate structure:
```javascript
const pendingQueue = [];  // initialized outside the forEach
```

And push pending-into-queue events there:
```javascript
pendingQueue.push({
    id: ev.id,
    partner: ev.Par_l,
    created_at: ev.created_at,
    arrived_at: ev.arrived,  // the trigger moment — optional
    Amount_j: V(ev.Amount_j),
    currency: pl.config.is_international ? pl.config.currency : 'MRU',
    Amount_mru_h: V(ev.Amount_mru_h),
    reason: ev.reasonDetail || ev.reason,
    status: 'pending'
});
```

Expose `pendingQueue` to the renderers (store it on `bal.pendingQueue = pendingQueue;` so all tabs can access it).

### 2.2 Stop rendering pending rows in the partner ledger

Around line 726 there is:
```javascript
else if(e.event==='pending'){h+=`<tr style="background:var(--yellow-light)">...`}
```

**REMOVE this branch entirely.** Pending rows are no longer in `lg.entries` so the branch would never fire anyway — but delete it to be explicit.

### 2.3 Keep the existing pending queue view in the Operations tab

The Operations tab already has a pending queue UI. Update it to read from `bal.pendingQueue` (the new canonical source) and to show the new fields: `created_at`, `partner`, `Amount_j`, `currency`, `status`, reason, current queue age (in days from `created_at` to today).

### 2.4 Released-from-queue rows — keep the visual marker

When a previously queued transaction IS released (i.e., it's now in the historical ledger), keep the existing "released" visual marker (green left border, per line 724). But update the label to clarify:
```
T007 · 2026-01-12 → 2026-01-15 · RELEASED · ...
```
Where `created_at → posted_at` makes the lag visible. Use the existing `timeInQueue` to show `(queued 3d)` after it.

---

## FIX 3 — Surface `created_at` / `posted_at` everywhere

### 3.1 Partner ledger (Positions tab)

The transaction rows (around line 724) currently show `${(e.date||'').slice(5,10)}`. Change to show **both** dates when they differ:
- If `created_at === posted_at`: single date column `2026-01-12`
- If different: `created_at → posted_at` in two sub-lines or in one cell with arrow

Keep the column narrow. Use `MM-DD` for display, full ISO on hover (title attribute).

### 3.2 Bank ledger (Positions tab)

Settlement rows and withdrawal rows: show `created_at` = when the event hit the bank account (i.e., `posted_at` for settlements, which normally equals `date_s`). For bank events there is usually no queue so one date is fine, but the column MUST be labeled `Posted` and the underlying data MUST be `e.posted_at`.

### 3.3 Operations tab — transaction log

Already renders the transaction log. Update it to show two columns: `Created` and `Posted` (and highlight rows where they differ with a subtle marker). Add a sort/filter option: **All / Released only / Pending only / Queued-then-released**.

### 3.4 CEO tab — P&L date attribution

Profit numbers (L1 and L2) attribute to `posted_at`, NOT `created_at`. A transaction created 2026-01-28 but released 2026-02-03 books its profit in **February**. Verify the monthly trend chart groups by `posted_at`. If the existing code uses `ev.date`, change to `ev.posted_at`.

### 3.5 Treasury tab

Same rule: running balances advance by `posted_at`. Alerts for pending age compute from `created_at` (today − created_at = days in queue).

---

## FIX 6 — Budget View (Cadorim's Money Over Time)

This is a NEW dashboard section that answers one question: **"How much of Cadorim's own money is there today vs. the day we started?"** It shows the **equity curve** — opening capital, daily movement, current position, net change.

### 6.1 Definition — Cadorim Equity

At any point in time `t`:

```
Equity(t) = Assets(t) − Liabilities(t)

Assets(t)       = Σ cash_caisses + Σ wallet_balances + Σ bank_balances + Σ receivables_mru
Liabilities(t)  = client_float + Σ pending_payouts_mru
Equity(t)       = Assets(t) − Liabilities(t)
```

- Opening equity `Equity(0)` = 1,000,000 MRU (per current SIM_INITIAL: 450k caisses + 350k wallets + 200k bank − 0 client_float at t=0) — verify this matches once opening receivables are added (expected Equity(0) = 1,000,000 + 615,000 opening_receivable = 1,615,000 MRU).
- `Δ(t) = Equity(t) − Equity(0)` is the cumulative profit/loss since start.
- Daily delta `d(t) = Equity(t) − Equity(t−1)` is the day's movement.

### 6.2 Where it lives

Add a new top-level tab called **"Budget"** (between CEO and Treasury). It has 4 sections:

1. **Opening block** — Single panel showing starting components:
   - Caisses: 450,000 MRU
   - Wallets: 350,000 MRU
   - Bank: 200,000 MRU
   - Opening receivables: 615,000 MRU (if present)
   - Client float liability: 0 MRU
   - **Opening Equity: 1,615,000 MRU** (big number, bold)

2. **Today block** — Current-state snapshot (mirror of opening, using end-of-simulation state):
   - Caisses: X MRU
   - Wallets: X MRU
   - Bank: X MRU
   - Receivables: X MRU (split into `positive` and `overpaid` if any)
   - Client float liability: X MRU (shown as negative)
   - Pending payouts liability: X MRU (shown as negative, from `bal.pendingQueue`)
   - **Current Equity: Y MRU**
   - **Change since start: +/- Z MRU (percent)** — green if +, red if −

3. **Daily curve** — Line chart (Chart.js, reuse existing instance if convenient):
   - X-axis: date (every day from first sim date to last sim date)
   - Y-axis: Equity in MRU
   - Horizontal reference line at `Equity(0)` so deviations are visible at a glance
   - Tooltip: on hover show `Date · Equity · Δ vs start · Daily delta`

4. **Daily table** — Compact table below the chart, one row per day, columns:
   - Date
   - Caisses
   - Wallets
   - Bank
   - Receivables
   - − Client float
   - − Pending
   - **Equity**
   - Δ vs start (colored)
   - Daily Δ (colored)

### 6.3 How to compute the daily series

Add a helper in the balance-computation section:

```javascript
function computeEquitySeries(SIM_INITIAL, allEvents /* tx, sett, wd, topup, sorted by posted_at */) {
    // Gather all distinct dates that matter (from min created_at/posted_at to max)
    const dates = [...new Set(allEvents.flatMap(e => [e.posted_at, e.created_at]).filter(Boolean))].sort();
    if (dates.length === 0) return [];
    
    // Simulate state forward, snapshotting at end of each date
    const state = initBal(SIM_INITIAL);
    const snapshots = [];
    
    // Day-zero snapshot
    snapshots.push({ date: dates[0], state: snapshot(state) });
    
    for (const d of dates) {
        const todayEvents = allEvents.filter(e => e.posted_at === d);
        for (const ev of todayEvents) apply(ev, state);  // reuse applyTx/applySett/applyWd
        snapshots.push({ date: d, state: snapshot(state) });
    }
    
    return snapshots.map(s => ({
        date: s.date,
        caisses: sumObj(s.state.cash),
        wallets: sumObj(s.state.wallet),
        bank: sumObj(s.state.bank),
        receivables: sumReceivablesMRU(s.state.receivable),
        client_float: s.state.client_float,
        pending: sumPendingMRU(s.state.pendingQueue || []),
        equity: computeEquity(s.state)
    }));
}

function computeEquity(state) {
    const assets = sumObj(state.cash) + sumObj(state.wallet) + sumObj(state.bank) + sumReceivablesMRU(state.receivable);
    const liab = state.client_float + sumPendingMRU(state.pendingQueue || []);
    return assets - liab;
}
```

Don't duplicate the engine — REUSE `initBal`, `applyTx`, `applySett`, `applyWd`. Snapshot = shallow clone of the balance state after each day's events applied.

### 6.4 Interaction

- Clicking any row in the daily table opens a mini-drawer showing the events that moved equity that day (list of `id`, type, delta MRU, partner).
- Opening and Today blocks are always visible; chart and table are scrollable.
- If any day has a negative daily delta beyond 2% of opening equity, flag it with a red row in the table.

### 6.5 Alerts tied to equity

Add one alert class:
- **Equity drop alert** — if `Equity(t) < 0.9 × Equity(0)` at any point in the series, emit a red alert: `Equity fell below 90% of opening on <date> — down to <N> MRU (−<X>%)`.

### 6.6 Edge cases

- **Opening balance mismatch**: If `computeEquity(initBal(SIM_INITIAL))` ≠ the sum of opening components (caisses + wallets + bank + opening_receivable − client_float), show a red banner at the top of the Budget tab: `⚠ Opening equity integrity check failed: expected X, got Y`. This catches data-setup bugs.
- **Pending payouts liability**: a queued transaction represents an obligation to pay MRU out. It must be subtracted from equity as a liability, not counted as an asset.
- **Profit_l1 / profit_l2**: DO NOT double-count. Profit is already reflected in the state's cash/wallet/bank balances (since the applyTx/applySett functions move those balances). The equity formula captures profit as the delta; `profit_l1 + profit_l2` is a bookkeeping total but not a separate equity input.

---

## FIX 4 — Alerts

Add a new alert category for **aged pending**:

```javascript
const TODAY = new Date().toISOString().slice(0,10);
bal.pendingQueue.forEach(p => {
    const ageDays = Math.floor((new Date(TODAY) - new Date(p.created_at)) / 86400000);
    if (ageDays >= 5) {
        bal.alerts.push({
            severity: ageDays >= 10 ? 'red' : 'yellow',
            date: p.created_at,
            id: p.id,
            msg: `Pending ${ageDays}d: ${p.id} (${(p.partner||'').replace('sim_','')}) — ${p.reason}`
        });
    }
});
```

---

## FIX 5 — Partner ledger header & totals

Because pending rows are gone from the ledger, the partner ledger header summary (line ~719) should distinguish **Posted** from **Pending**:

```
terrapay (USD) — L1: 1,234 + L2: 567 = 1,801 | Recv: 4,500 USD (175,500 MRU) | Posted: 15 | Pending: 2
```

Posted count = `lg.entries.filter(e => e.event === 'transaction').length`
Pending count = `bal.pendingQueue.filter(p => p.partner === code).length`

---

## SUMMARY OF CHANGES

1. `SIM_TXS` / `SIM_SETT` / `SIM_WD` — add `created_at`, `posted_at` (null when pending), `status`
2. `runEngine()` — stamp `posted_at` and `status` as events apply
3. Remove `event:'pending'` push into `partnerLedgers[].entries`
4. Create `bal.pendingQueue` — the single source of truth for pending
5. Remove `event === 'pending'` branch from partner ledger renderer
6. Operations tab pending UI reads from `bal.pendingQueue` with `created_at` and age
7. Partner ledger entries carry `{id, created_at, posted_at, status}`
8. Partner ledger shows `created_at → posted_at` when they differ
9. CEO P&L groups by `posted_at`, NOT `created_at`
10. Treasury balances advance by `posted_at`
11. New aged-pending alerts (>=5d yellow, >=10d red)
12. Partner ledger header adds Posted/Pending counts
13. **NEW tab "Budget"** — Opening block, Today block, daily equity curve chart, daily table
14. `computeEquitySeries()` — daily snapshot helper; reuses initBal/applyTx/applySett/applyWd
15. Equity drop alert if Equity(t) < 0.9 × Equity(0)
16. Integrity banner if opening equity math doesn't reconcile

## DO NOT CHANGE

- computeL1, computeL2 formulas
- applyTx, applySett, applyWd internal math (only the metadata they attach)
- Plafond logic, double-gate, auto top-up math
- Setup tab structure
- Single-file HTML, same CDN deps
- Receivable cross-ref, opening balances, negative flagging (just landed)

## TESTING

After the fix, verify in browser:
1. Partner ledgers (Positions tab) show only `event === 'transaction'` and `event === 'settlement'` rows — NO yellow "PENDING" rows
2. Operations tab still shows a pending queue view, populated from `bal.pendingQueue`
3. A transaction that was queued and released shows `created_at → posted_at` with both dates visible
4. A still-pending transaction does NOT appear in partner ledger at all, but DOES appear in Operations pending queue with current age in days
5. CEO monthly trend groups by `posted_at` (a txn created Jan 28 released Feb 3 goes to Feb bucket)
6. Aged-pending alerts fire if today − created_at ≥ 5 days
7. Partner ledger header shows `Posted: N | Pending: M`
8. Budget tab: Opening Equity = 1,615,000 MRU (or 1,000,000 if opening receivables are zeroed out)
9. Budget tab: daily curve line starts at opening equity and moves with each day's events
10. Budget tab: Today block matches the final state of the simulation (caisse + wallet + bank + recv − float − pending = Equity)
11. Budget tab: integrity banner does NOT appear when SIM_INITIAL is consistent
12. No regression on: receivable cross-refs, opening balances, negative flag, plafond, double-gate, auto top-up, CEO drill-downs

## NUMBER ANCHOR

File before: 802 lines. Expect ~900–970 after (net +100–170, since we are removing one branch but adding: pendingQueue struct, two new date fields on every entry, dual-date rendering, aged-pending alert loop, header counts, full new Budget tab with chart + table + equity series helper).

Report: final line count, which of the 6 FIX sections you completed, anything you skipped, and any ambiguity resolved by judgment.
