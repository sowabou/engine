# Claude Code Prompt — Pending Queue: Blocked Transactions Are Waiting, Not Dead

## Context

File: `~/cadorim-engine/engine.html`. The engine currently treats blocked transactions as permanently canceled. This is WRONG. In reality, when a transaction is blocked (plafond exceeded or insufficient wallet balance), the beneficiary is still waiting for their money. The transaction sits in a pending state until Cadorim resolves the liquidity issue.

## THE CORRECT MODEL

A transaction has THREE possible states:
1. **Executed** — passed all checks, processed immediately. Time-in-queue = 0.
2. **Pending** — failed a check, sitting in queue waiting for liquidity. Time-in-queue = counting.
3. **Released** — was pending, then liquidity arrived and it was executed. Time-in-queue = release_date - arrival_date.

There is NO "blocked forever" state. Every transaction MUST eventually execute (in a well-managed system). The measure of operational efficiency is:
- **Average time-to-release** — how long pending transactions wait
- **Max time-in-queue** — the worst case (a beneficiary waited X days)
- **Pending count at end** — how many are still unresolved (this should be ZERO in a good system)

## WHAT TO BUILD

### Part 1: Pending Queue Data Structure

Replace the current `blockedTxs` array with a proper queue:

```javascript
let pendingQueue = [];  // transactions waiting for liquidity

// Each entry:
{
    ...tx,                          // original transaction data
    arrived: tx.date,               // when the transaction came in
    queuedAt: tx.date,              // when it entered the queue (same as arrived)
    reason: 'plafond_exceeded',     // why it was queued
    reasonDetail: '...',            // human-readable detail
    priority: 1,                    // from plafond rule priority (1=highest)
    status: 'pending',              // 'pending' or 'released'
    releasedAt: null,               // date when released (null if still pending)
    releasedBy: null,               // what event released it: 'settlement', 'auto_topup', 'reallocation'
    timeInQueue: null,              // days between queuedAt and releasedAt
    wouldBeProfit: 0                // L1 profit if executed (for urgency assessment)
}
```

### Part 2: Redesigned Engine Loop

The engine loop changes fundamentally:

```javascript
function runEngine() {
    const cfg = buildConfigJSON();
    // ... validation checks ...
    
    const bal = initBal(SIM_INITIAL);
    const plafondUsage = {};
    const pendingQueue = [];
    const executedTxs = [];      // all executed (immediate + released)
    const autoActions = [];       // treasury movements auto-generated

    // Sort all events chronologically
    const all = [];
    SIM_TXS.forEach(t => all.push({...t, _t:'tx', _d:t.date}));
    SIM_SETT.forEach(s => all.push({...s, _t:'se', _d:s.date_s}));
    SIM_WD.forEach(w => all.push({...w, _t:'wd', _d:w.date}));
    all.sort((a,b) => a._d.localeCompare(b._d) || (a.id||'').localeCompare(b.id||''));

    all.forEach(ev => {
        if (ev._t === 'tx') {
            // Try to execute the transaction
            const result = tryExecute(ev, cfg, plafondUsage, bal);
            if (result.executed) {
                executedTxs.push(result.record);
            } else {
                // Add to pending queue with priority from plafond rule
                const rule = (cfg.plafonds||[]).find(p => p.channel===ev.Local_Par_n && p.partner===ev.Par_l);
                const pr = computeL1(ev, cfg);
                pendingQueue.push({
                    ...ev,
                    arrived: ev.date,
                    queuedAt: ev.date,
                    reason: result.reason,
                    reasonDetail: result.detail,
                    priority: rule ? V(rule.priority) : 5,
                    status: 'pending',
                    releasedAt: null,
                    releasedBy: null,
                    timeInQueue: null,
                    wouldBeProfit: pr.profit_transaction_a
                });
                bal.alerts.push({
                    severity: 'yellow', date: ev.date, id: ev.id,
                    msg: `QUEUED ${ev.id}: ${ev.Par_l}→${(ev.Local_Par_n||'').replace('sim_','')} ${fmt(ev.Amount_mru_h)} MRU (${result.reason})`
                });
            }
        }
        else if (ev._t === 'se') {
            applySett(ev, bal);
            // Settlement arrived → money in bank. Try auto-actions to release pending.
            autoResolve(ev.date, 'settlement', cfg, plafondUsage, bal, pendingQueue, executedTxs, autoActions);
        }
        else if (ev._t === 'wd') {
            applyWd(ev, bal);
            // Bank withdrawal → money in caisse. Check if we should top up wallets.
            autoResolve(ev.date, 'withdrawal', cfg, plafondUsage, bal, pendingQueue, executedTxs, autoActions);
        }

        // Record timeline snapshot
        timeline.push({
            date: ev._d, id: ev.id,
            ...checkEq(bal),
            profit_l1: bal.profit_l1, profit_l2: bal.profit_l2,
            client_float: bal.client_float, agent_balance: bal.agent_balance,
            pendingCount: pendingQueue.filter(p => p.status === 'pending').length,
            pendingVolume: pendingQueue.filter(p => p.status === 'pending').reduce((a,p) => a + V(p.Amount_mru_h), 0)
        });
    });

    // End-of-run: anything still pending is UNRESOLVED
    const unresolved = pendingQueue.filter(p => p.status === 'pending');
    if (unresolved.length > 0) {
        bal.alerts.push({
            severity: 'red', date: 'END', id: 'UNRESOLVED',
            msg: `${unresolved.length} transactions still pending (${fmt(unresolved.reduce((a,p) => a+V(p.Amount_mru_h), 0))} MRU). Action required.`
        });
    }

    // Store results
    engineResults = {
        balances: JSON.parse(JSON.stringify(bal)),
        equation: checkEq(bal),
        timeline, 
        txResults: executedTxs,
        pendingQueue,       // replaces blockedTxs
        autoActions,        // treasury movements auto-generated
        plafondUsage: {...plafondUsage},
        plafondRules: cfg.plafonds || [],
        settlements: SIM_SETT.map(s => ({...s, ...computeL2(s)})),
        withdrawals: SIM_WD,
        initial: SIM_INITIAL,
        config: cfg
    };
}
```

### Part 3: tryExecute Function

```javascript
function tryExecute(tx, cfg, plafondUsage, bal) {
    const ch = tx.Local_Par_n;
    const par = tx.Par_l;
    const amt = V(tx.Amount_mru_h);
    const pool = getPool(ch);

    // Non-wallet channels: always execute
    if (pool.type !== 'wallet') {
        const pr = computeL1(tx, cfg);
        applyTx(tx, pr, bal);
        if (pool.type === 'wallet') {
            plafondUsage[par+'|'+ch] = (plafondUsage[par+'|'+ch]||0) + amt;
        }
        return { executed: true, record: {...tx, ...pr, timeInQueue: 0} };
    }

    // Wallet channel: check plafond + balance
    const key = par + '|' + ch;
    const rule = (cfg.plafonds||[]).find(p => p.channel===ch && p.partner===par);

    if (!rule) return { executed: false, reason: 'no_allocation', detail: 'No plafond rule for this pair' };
    
    const cap = V(rule.plafond);
    if (cap === 0) return { executed: false, reason: 'blocked', detail: 'Plafond = 0' };

    const used = plafondUsage[key] || 0;
    if (used + amt > cap) {
        return { 
            executed: false, reason: 'plafond_exceeded',
            detail: `Used ${fmt(used)} of ${fmt(cap)}, need ${fmt(amt)}, remaining ${fmt(cap-used)}`
        };
    }

    const walletBal = bal.wallet[pool.key] || 0;
    if (walletBal < amt) {
        return { 
            executed: false, reason: 'insufficient_balance',
            detail: `Wallet ${pool.key} has ${fmt(walletBal)}, need ${fmt(amt)}, shortfall ${fmt(amt-walletBal)}`
        };
    }

    // Both checks pass → execute
    const pr = computeL1(tx, cfg);
    applyTx(tx, pr, bal);
    plafondUsage[key] = used + amt;
    return { executed: true, record: {...tx, ...pr, timeInQueue: 0} };
}
```

### Part 4: Auto-Resolve — The Intelligence

After every liquidity event (settlement, withdrawal), the engine tries to resolve pending transactions automatically:

```javascript
function autoResolve(currentDate, trigger, cfg, plafondUsage, bal, pendingQueue, executedTxs, autoActions) {
    // Sort pending by priority (1 first), then by arrival date (oldest first)
    const pending = pendingQueue
        .filter(p => p.status === 'pending')
        .sort((a, b) => a.priority - b.priority || a.arrived.localeCompare(b.arrived));

    if (pending.length === 0) return;

    // STRATEGY 1: Check if any pending transaction can now execute directly
    // (maybe another tx was blocked but now the wallet has been topped up via withdrawal)
    for (const ptx of pending) {
        const result = tryExecute(ptx, cfg, plafondUsage, bal);
        if (result.executed) {
            ptx.status = 'released';
            ptx.releasedAt = currentDate;
            ptx.releasedBy = trigger;
            ptx.timeInQueue = daysBetween(ptx.queuedAt, currentDate);
            executedTxs.push({...result.record, timeInQueue: ptx.timeInQueue, wasQueued: true});
            bal.alerts.push({
                severity: 'green', date: currentDate, id: ptx.id,
                msg: `RELEASED ${ptx.id} after ${ptx.timeInQueue}d in queue (trigger: ${trigger})`
            });
        }
    }

    // STRATEGY 2: Auto-generate wallet top-up from caisse
    // For remaining pending transactions, check if caisses have enough to fund the wallet
    const stillPending = pendingQueue.filter(p => p.status === 'pending')
        .sort((a, b) => a.priority - b.priority || a.arrived.localeCompare(b.arrived));

    for (const ptx of stillPending) {
        const pool = getPool(ptx.Local_Par_n);
        if (pool.type !== 'wallet') continue;

        const amt = V(ptx.Amount_mru_h);
        const walletBal = bal.wallet[pool.key] || 0;
        const shortfall = amt - walletBal;

        if (shortfall <= 0) continue;  // balance issue resolved by strategy 1

        // Find best caisse to fund from (highest balance, above minimum threshold)
        const caisseMinimum = 50000;  // keep at least 50K in each caisse
        const bestCaisse = Object.entries(bal.cash)
            .filter(([k, v]) => v - shortfall >= caisseMinimum)
            .sort((a, b) => b[1] - a[1])[0];

        if (bestCaisse) {
            // AUTO-ACTION: move funds from caisse to wallet
            const [caisseName, caisseBalance] = bestCaisse;
            const topUpAmount = shortfall + 10000;  // add 10K buffer
            const actualTopUp = Math.min(topUpAmount, caisseBalance - caisseMinimum);

            // Execute the treasury movement
            bal.cash[caisseName] -= actualTopUp;
            bal.wallet[pool.key] = (bal.wallet[pool.key] || 0) + actualTopUp;

            autoActions.push({
                date: currentDate,
                type: 'wallet_topup',
                from: caisseName,
                to: pool.key,
                amount: actualTopUp,
                trigger: `Release pending ${ptx.id} (priority ${ptx.priority})`,
                caisseBalanceAfter: bal.cash[caisseName],
                walletBalanceAfter: bal.wallet[pool.key]
            });

            bal.alerts.push({
                severity: 'blue', date: currentDate, id: 'AUTO',
                msg: `AUTO: Moved ${fmt(actualTopUp)} from ${caisseName} → ${pool.key} to release ${ptx.id}`
            });

            // Now try to execute the pending transaction
            const result = tryExecute(ptx, cfg, plafondUsage, bal);
            if (result.executed) {
                ptx.status = 'released';
                ptx.releasedAt = currentDate;
                ptx.releasedBy = 'auto_topup';
                ptx.timeInQueue = daysBetween(ptx.queuedAt, currentDate);
                executedTxs.push({...result.record, timeInQueue: ptx.timeInQueue, wasQueued: true});
                bal.alerts.push({
                    severity: 'green', date: currentDate, id: ptx.id,
                    msg: `RELEASED ${ptx.id} after ${ptx.timeInQueue}d (auto top-up from ${caisseName})`
                });
            }
        }
    }
}

// Helper: compute days between two date strings "YYYY-MM-DD"
function daysBetween(d1, d2) {
    const a = new Date(d1), b = new Date(d2);
    return Math.max(0, Math.round((b - a) / 86400000));
}
```

### Part 5: Dashboard Updates

#### CEO Tab — Replace "Blocked" card with "Queue" card

Remove the old "Blocked" card. Replace with:

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ QUEUE RESOLVED   │  │ STILL PENDING    │  │ AVG WAIT TIME   │
│      6           │  │      3           │  │    4.2 days      │
│ released, 0.8d avg│  │ 195,000 MRU     │  │ max: 12 days    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

Three mini-cards:
1. **Queue Resolved** (green): count of released transactions + average time-in-queue
2. **Still Pending** (red if > 0, green if 0): count + total MRU volume still waiting
3. **Avg Wait Time** (color by severity): average days across all queued transactions + max wait

#### CEO Queue Drill-Down (click any of the 3 cards)

Opens a full table:

```
PENDING QUEUE — Transaction Status

| ID   | Date     | Partner    | Channel | Amount    | Priority | Status    | Wait  | Action Taken              |
| T012 | Jan 08   | terrapay   | sedad   | 78,000    | P1       | RELEASED  | 12d   | Auto top-up from babe     |
| T019 | Jan 15   | wallet     | sedad   | 12,000    | P4       | RELEASED  | 5d    | Settlement triggered      |
| T046 | Mar 15   | terrapay   | sedad   | 117,000   | P1       | PENDING   | 15d+  | Needs 52K: babe has 80K   |
| T048 | Mar 20   | terrapay   | click   | 25,350    | P1       | PENDING   | 10d+  | Shortfall: 15K            |
```

Columns:
- **Status**: green "RELEASED" badge or red pulsing "PENDING" badge
- **Wait**: days in queue. For released: actual days. For pending: days since arrival + "+" (still counting)
- **Action Taken**: for released → what resolved it. For pending → what's needed and where funds are

Color: released rows = light green background. Pending rows = light red background.

#### CEO — "Auto Actions" section (below queue table)

Show all auto-generated treasury movements:

```
AUTO-GENERATED TREASURY MOVEMENTS

| Date     | Action                           | Amount    | Trigger                    |
| Jan 20   | caisse_babe → sedad              | 90,000    | Release T012 (P1)          |
| Feb 05   | caisse_mboirick → click           | 35,000    | Release T022 (P1)          |
| Mar 10   | caisse_tidjany → sedad            | 60,000    | Release T037 (P1)          |
```

This shows the CEO exactly what treasury movements the system recommended/executed to keep transactions flowing.

#### Treasury Tab — Add pending queue impact

In the wallet drill-down, add for each wallet:
- **Pending volume**: total MRU of pending transactions targeting this wallet
- **Pending count**: how many transactions are waiting
- **Funding needed**: total shortfall to clear all pending transactions on this wallet

```
sedad: Balance 62,000 | Pending: 3 txns (195,000 MRU) | Shortfall: 133,000 MRU
  → Recommendation: Withdraw 133,000 from BMI → babe → sedad
```

#### Operations Tab — Queue Efficiency Metrics

Add a new section: "Queue Performance"

```
┌─────────────────────────────────────────────────────┐
│ Queue Performance                                    │
│                                                     │
│ Total queued:         12 transactions                │
│ Released:              9 (75%)                       │
│ Still pending:         3 (25%)                       │
│ Avg time-to-release:  3.4 days                      │
│ Max time-in-queue:   15 days (T046, terrapay)        │
│ Auto top-ups:          5 (moved 315,000 MRU)        │
│                                                     │
│ By Priority:                                        │
│   P1 (high):    5 queued, 4 released, avg 2.1d      │
│   P3 (medium):  4 queued, 3 released, avg 4.5d      │
│   P4 (low):     3 queued, 2 released, avg 5.8d      │
│                                                     │
│ Efficiency: P1 transactions released 2.5x faster    │
│ than P4 — priority system working correctly.         │
└─────────────────────────────────────────────────────┘
```

#### Timeline Chart — Add pending queue line

In the Treasury timeline chart, add a new dataset:
- **"Pending"**: line showing pending queue volume over time (should spike when transactions are blocked, drop when released). Use dashed red line.

### Part 6: Wallet Balance Integrity

After all changes, the INVARIANT is:
- **Wallet balances ≥ 0 at ALL times.** No exceptions.
- A transaction is NEVER executed if it would make a wallet negative.
- If a transaction can't execute, it waits in the queue.
- The queue is processed in priority order after every liquidity event.

### Part 7: Auto-Action Configuration

In the Setup tab, add a checkbox or toggle:

```
☑ Enable auto top-up (move funds from caisses to wallets to release pending transactions)
  Caisse minimum reserve: [50,000] MRU (keep at least this amount in each caisse)
```

When enabled: the engine auto-generates treasury movements.
When disabled: the engine only shows recommendations (what SHOULD be done) but doesn't auto-execute. Transactions stay pending.

Default: ENABLED for simulation.

### Part 8: Style

- Released transactions: light green row background (#ECFDF5)
- Pending transactions: light red row background (#FEF2F2) with subtle pulse animation on the status badge
- Auto-action rows: light blue background (#EFF6FF)
- "RELEASED" badge: green, solid
- "PENDING" badge: red, with CSS animation `@keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:0.6 } }` — subtle pulse to draw attention
- Queue performance metrics: use the existing card grid layout
- Priority circles: same colored circles as plafond rules (P1 green, P2 blue, etc.)
- Wait time: bold red if > 7 days, orange if 3-7, green if < 3

### Part 9: DO NOT CHANGE

- computeL1, computeL2 — profit computation stays the same
- applyTx — how a transaction affects balances stays the same (only called when actually executing)
- applySett, applyWd — settlement and withdrawal logic stays the same
- Setup tab plafond configuration — stays the same
- Existing CEO drill-downs for Profit, Volume, Revenue, Net Position — stays the same (add queue drill-down alongside)
- Single HTML file, same CDN deps

### Part 10: Testing

After changes, run simulation and verify:

1. **No wallet ever goes negative** — this is the #1 requirement
2. **Some transactions enter the queue** (plafond or balance constraint)
3. **After settlements/withdrawals, queue is re-scanned** and transactions are released in priority order
4. **P1 transactions released before P4** — priority system works
5. **Auto top-ups appear** — when a caisse has enough, funds move to the wallet automatically
6. **CEO shows 3 queue cards** — Resolved, Still Pending, Avg Wait Time
7. **CEO queue drill-down** shows every queued transaction with status, wait time, and action
8. **Auto Actions table** shows all treasury movements generated by the engine
9. **Operations Queue Performance** shows efficiency metrics by priority
10. **Timeline chart** shows pending volume spike and drop over time
11. **"Still Pending" at end should be minimal** — if the system has enough total liquidity, most transactions should eventually release
