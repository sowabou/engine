# Claude Code Prompt — Fix: Receivable Cross-References, Opening Balances, Negative Flagging

## Context

File: `~/cadorim-engine/engine.html` (single file, ~790 lines). The Positions tab and Treasury tab show receivables, but three problems exist:

1. **No opening receivable balance** — The simulation starts receivables at zero, but settlements arrive for transactions that happened BEFORE the simulation period. This creates negative receivables (e.g., TerraPay settles 14,400 USD but only 14,750 USD of transactions occurred — if a settlement arrives before enough transactions accumulate, receivable goes negative temporarily, and the final balance can be negative).

2. **No cross-reference between partner and bank** — When a settlement appears in Ria's partner ledger, it just says "SETTLEMENT". It should say "SETTLEMENT → bmi" so you know WHERE the money went. Similarly, when that settlement appears in BMI's bank statement, it should say "from ria (3,900 EUR × 42.6)" so you know WHERE the money came from, in what currency, and at what rate.

3. **Negative receivables not flagged** — A negative receivable means Cadorim owes the partner (it's a liability, not an asset). The display doesn't distinguish this. It should be flagged visually and the total should separate assets from liabilities.

---

## FIX 1: Opening Receivable Balances

### Add to SIM_INITIAL

Add an `opening_receivable` object to `SIM_INITIAL`:

```javascript
const SIM_INITIAL = {
    cash: { ... },
    wallet: { ... },
    bank: { ... },
    client_float: 50000,
    working_capital: 950000,
    // NEW: opening receivable from prior periods
    opening_receivable: {
        "sim_terrapay": { foreign: 12000, currency: "USD", mru: 468000 },
        "sim_ria": { foreign: 3500, currency: "EUR", mru: 147000 }
    }
};
```

These represent amounts owed TO Cadorim at the start of the simulation period (carried forward from prior months).

### Update initBal()

Initialize receivables from the opening balance instead of empty:

```javascript
function initBal(ini) {
    const recv = {};
    if (ini.opening_receivable) {
        for (const [k, v] of Object.entries(ini.opening_receivable)) {
            recv[k] = { foreign: v.foreign, mru: v.mru, currency: v.currency };
        }
    }
    return {
        cash: {...ini.cash},
        wallet: {...ini.wallet},
        bank: {...ini.bank},
        receivable: recv,  // ← was {}
        client_float: ini.client_float || 0,
        agent_balance: 0,
        working_capital: ini.working_capital,
        profit_l1: 0, profit_l2: 0,
        events: [], alerts: []
    };
}
```

### Update partner ledger initialization

In `runEngine()`, when building `partnerLedgers`, initialize the running receivable from the opening balance:

```javascript
cfg.layer1.forEach(p => {
    const openR = SIM_INITIAL.opening_receivable?.[p.code];
    partnerLedgers[p.code] = {
        entries: [],
        runRecvF: openR ? openR.foreign : 0,   // ← was 0
        runRecvM: openR ? openR.mru : 0,         // ← was 0
        runFloat: 0,
        runAgent: 0,
        totalL1: 0,
        totalL2: 0,
        config: p
    };
});
```

### Add opening balance row in partner ledger display

In `buildPositions()`, for international partners, add an opening row at the top of the ledger table (before the first entry):

```javascript
// After the <thead> row, before iterating lg.entries:
const openR = SIM_INITIAL.opening_receivable?.[code];
if (openR) {
    h += `<tr style="background:var(--surface-alt);font-style:italic">
        <td></td><td></td><td></td><td>OPENING BALANCE</td>
        <td></td><td></td><td></td><td colspan="4"></td>
        <td class="n" style="font-weight:600">${f2(openR.foreign)}</td>
        <td class="n">${fmt(openR.mru)}</td></tr>`;
}
```

### Update working_capital

Since we're adding opening receivables, the `working_capital` in SIM_INITIAL should account for them. Update the value:

```javascript
working_capital: 1565000  // was 950000 — now includes opening receivables (468000 + 147000 = 615000)
```

Actually — do NOT change working_capital. The `checkEq()` function uses it differently. Leave it. The opening receivable is already part of the balance via `initBal()`.

---

## FIX 2: Cross-Reference Notes

### Settlement entries in partner ledger — add bank destination

In `buildPositions()`, when rendering settlement rows in the international partner ledger, the "Channel" column currently shows "SETTLEMENT". Change it to show the bank destination:

**Current (line ~714):**
```javascript
<td>SETTLEMENT</td>
```

**Change to:**
```javascript
<td style="color:var(--purple);font-weight:600">SETT → ${(s.bank||'').replace('sim_','')}</td>
```

So for Ria's settlement to BMI, it will show: `SETT → bmi`

### Settlement entries in bank ledger — add partner source + currency detail

In `buildPositions()`, when rendering bank ledger rows, the "Partner/Dest" column currently shows just the partner code for settlements. Change it to include the full conversion detail:

**Current (line ~747):**
```javascript
<td>${isSett ? (e.partner||'').replace('sim_','') : '→ '+(e.destination||'')}</td>
```

**Change to:**
```javascript
<td>${isSett 
    ? (e.partner||'').replace('sim_','') + ' (' + f2(e.foreignAmount) + ' ' + (e.currency||'') + ' × ' + e.fxRate + ')'
    : '→ ' + (e.destination||'')}</td>
```

So for a TerraPay settlement, it will show: `terrapay (4,850.00 USD × 39.3)`
For Ria: `ria (2,550.00 EUR × 42.6)`
For a withdrawal: `→ caisse_babe`

### Settlement entries in Treasury tab receivable section — add bank reference

In `buildCEO()` (the Net Position drill-down), the receivables table currently shows "settled" and "pending" amounts but no bank reference. Add a "Bank" column:

**Current receivable table header (inside ceo_netpos drill, around line ~533):**
```html
<tr><th>Partner</th><th class="n">Foreign</th><th class="n">MRU</th><th>Cur</th><th class="n">Settled</th><th class="n">Pending</th></tr>
```

**Change to:**
```html
<tr><th>Partner</th><th class="n">Foreign</th><th class="n">MRU</th><th>Cur</th><th class="n">Settled</th><th class="n">Pending</th><th>Bank</th></tr>
```

And in the row rendering (~line 535), add the bank(s):

```javascript
const banks = [...new Set(setts.filter(s=>s.Par_l===k).map(s=>(s.Bank_t||'').replace('sim_','')))].join(', ');
h += `<td>${banks || '-'}</td>`;
```

So Ria's row shows: `3,900.00 settled | 1,900.00 pending | bmi`

### Same fix in Treasury tab receivable drill (dr)

In `buildTreasury()`, the receivable drill section (id="dr", around line ~608) also needs the bank reference:

**Current:**
```html
<tr><th>Partner</th><th class="n">Foreign</th><th class="n">MRU</th><th>Cur</th></tr>
```

**Change to:**
```html
<tr><th>Partner</th><th class="n">Foreign</th><th class="n">MRU</th><th>Cur</th><th class="n">Settled</th><th>Bank</th><th>Status</th></tr>
```

And the row rendering:
```javascript
for (const [k, v] of Object.entries(bal.receivable)) {
    const settled = setts.filter(s => s.Par_l === k).reduce((a, s) => a + V(s.Amount_s), 0);
    const banks = [...new Set(setts.filter(s => s.Par_l === k).map(s => (s.Bank_t||'').replace('sim_','')))].join(', ');
    const isNeg = v.foreign < 0;
    h += `<tr${isNeg ? ' style="background:var(--red-light)"' : ''}>
        <td>${k.replace('sim_','')}</td>
        <td class="n ${isNeg?'neg':''}">${f2(v.foreign)}</td>
        <td class="n ${isNeg?'neg':''}">${fmt(v.mru)}</td>
        <td>${v.currency}</td>
        <td class="n">${f2(settled)} settled</td>
        <td>${banks || '-'}</td>
        <td>${isNeg ? '<span class="neg" style="font-weight:600">OVERPAID</span>' : v.foreign < 1 ? '<span class="pos">CLEAR</span>' : 'Pending'}</td>
    </tr>`;
}
```

---

## FIX 3: Flag Negative Receivables

### Visual flagging in all receivable displays

Wherever receivables are displayed, negative values should be:
- Highlighted with red background (`var(--red-light)`)
- Labeled as "OVERPAID" (partner has settled more than they owe)
- The negative amount should use the `.neg` CSS class (red text)

### Receivable header should separate positive (asset) vs negative (liability)

In the CEO Net Position drill and Treasury tab, the receivable header currently shows one total. Change to show the split:

```javascript
const recvPos = Object.values(bal.receivable).filter(r => r.mru >= 0).reduce((a, r) => a + r.mru, 0);
const recvNeg = Object.values(bal.receivable).filter(r => r.mru < 0).reduce((a, r) => a + r.mru, 0);
```

Display: `Receivables: ${fmt(recvPos)} MRU` and if recvNeg < 0: ` (${fmt(Math.abs(recvNeg))} MRU overpaid — liability)`

### Alert for negative receivable at end of engine run

After the existing sanity checks in `runEngine()` (line ~385), add:

```javascript
// Check for negative receivables (partner overpaid)
for (const [k, v] of Object.entries(bal.receivable)) {
    if (v.foreign < -0.01) {
        bal.alerts.push({
            severity: 'yellow',
            date: 'END',
            id: 'RECV',
            msg: `${k.replace('sim_','')} receivable is negative: ${f2(v.foreign)} ${v.currency} — partner has overpaid (settled more than transacted). This is a LIABILITY.`
        });
    }
}
```

### Opening receivable note in Positions tab

In the Partner Position summary table (the top table in Positions), add an "Opening" column for international partners:

```javascript
// In the header:
<th class="n">Opening</th>

// In the row:
const openR = SIM_INITIAL.opening_receivable?.[code];
<td class="n">${isI && openR ? f2(openR.foreign) + ' ' + lg.config.currency : '-'}</td>
```

This lets the CEO see at a glance what was carried forward vs. what was generated this period.

---

## FIX 4: Layer 2 settlement section in partner ledger — add bank cross-ref

In `buildPositions()`, the Layer 2 settlement detail table for international partners (line ~720) has a "Bank" column but it only shows the code. Make it more descriptive:

**Current:**
```javascript
<td>${(s.bank||'').replace('sim_','')}</td>
```

**Change to:**
```javascript
<td style="font-weight:500">${(s.bank||'').replace('sim_','').toUpperCase()}</td>
```

So it shows `BMI` instead of `bmi`.

---

## SUMMARY OF CHANGES

1. **SIM_INITIAL** — Add `opening_receivable` for sim_terrapay (12,000 USD) and sim_ria (3,500 EUR)
2. **initBal()** — Initialize receivables from opening balances, not empty
3. **Partner ledger init** — Start `runRecvF`/`runRecvM` from opening balance
4. **Partner ledger display** — Add "OPENING BALANCE" row; settlement rows show "SETT → bmi" instead of "SETTLEMENT"
5. **Bank ledger display** — Settlement rows show `ria (2,550.00 EUR × 42.6)` instead of just `ria`
6. **CEO Net Position receivable table** — Add Bank column, flag negative rows red, show "OVERPAID"
7. **Treasury receivable drill** — Add Settled, Bank, Status columns; flag negative rows
8. **Negative receivable alert** — Yellow alert at end of run if any receivable is negative
9. **Receivable header** — Split into positive (asset) vs negative (liability)
10. **Positions summary** — Add "Opening" column for international partners

## DO NOT CHANGE

- computeL1, computeL2
- applyTx, applySett, applyWd internal logic (just initBal initialization)
- Plafond system, pending queue, auto-resolve
- Setup tab structure
- Single HTML file, same CDN deps
- Any other tab layout that's not explicitly mentioned above

## TESTING

After fix, run simulation and verify:
1. **Opening receivable rows** appear at top of TerraPay and Ria ledgers
2. **Receivables are positive** (or at least make operational sense with the opening balance)
3. **Settlement in Ria ledger** shows "SETT → bmi" (not just "SETTLEMENT")
4. **Settlement in BMI bank** shows "ria (2,550.00 EUR × 42.6)" (not just "ria")
5. **Negative receivables** (if any) are flagged red with "OVERPAID" label
6. **Alert** appears if any receivable ends negative
7. **Treasury receivable drill** shows Settled amount, Bank, and Status columns
8. **No regression** on CEO drill-downs, pending queue, plafond system, Operations tab
