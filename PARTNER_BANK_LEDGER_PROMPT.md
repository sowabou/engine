# Claude Code Prompt — Partner Ledger & Bank Ledger: Full Position Drill-Down

## Context

File: `~/cadorim-engine/engine.html`. The engine runs 50 transactions across 5 partners with settlements and withdrawals. The CEO and Treasury tabs show aggregate numbers. What's missing: the ability to click on a specific partner (Ria, TerraPay, etc.) or a specific bank (BMI) and see EVERY transaction chronologically with a running balance — like a bank statement for each entity.

## THE NEED

### For Partners (National + International):

The user needs a **position table** showing each partner's bottom line, then clicks any partner to see the full ledger:

**National partners** (Wallet, SNDP, Agent): 
- All transactions in MRU
- Running MRU balance after each transaction
- Layer 1 profit per transaction (commission - cost)

**International partners** (TerraPay, Ria):
- All transactions shown in DUAL CURRENCY: the foreign amount (USD/EUR) AND the MRU amount on the same row
- Running balance in BOTH currencies: foreign running balance AND MRU running balance
- Layer 1: per-transaction profit (commission - cost + FX spread)
- Layer 2: settlement events with FX conversion detail (foreign amount × settlement rate = MRU received, gain vs reference rate)
- Receivable tracking: after each transaction the receivable grows, after each settlement it shrinks

### For Banks:

Click BMI → see every movement:
- Settlements IN: which partner, foreign amount, rate, MRU credited
- Withdrawals OUT: to which caisse, amount
- Running balance after each event

## WHAT TO BUILD

### Part 1: Partner Position Table

Add a new section in the CEO tab (after the existing cards and charts, or as a major drill-down section). This is the MASTER POSITION VIEW:

```
PARTNER POSITIONS
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Partner      │ Type    │ Txns │ Volume MRU  │ L1 Profit │ L2 Profit │ Total     │
│──────────────│─────────│──────│─────────────│───────────│───────────│───────────│
│ ▶ TerraPay   │ Intl    │  15  │   703,950   │   8,485   │   6,275   │  14,760   │
│ ▶ Ria        │ Intl    │   9  │   248,240   │   4,428   │   2,475   │   6,903   │
│ ▶ SNDP       │ B2C     │  11  │   265,000   │     190   │       0   │     190   │
│ ▶ Wallet     │ National│   8  │    54,000   │    -200   │       0   │    -200   │
│ ▶ Agent      │ Agent   │   7  │    88,000   │    -210   │       0   │    -210   │
│──────────────│─────────│──────│─────────────│───────────│───────────│───────────│
│ TOTAL        │         │  50  │ 1,359,190   │  12,693   │   8,750   │  21,443   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

For international partners, add extra columns:
- **Foreign Volume**: total in USD or EUR
- **Receivable**: current pending amount in foreign currency + MRU equivalent
- **Settled**: total settled in foreign currency

Each row has a ▶ arrow — clicking it opens the FULL LEDGER for that partner (see below).

### Part 2: International Partner Ledger (TerraPay / Ria)

When the user clicks "TerraPay" in the position table, a detailed section opens:

#### 2A: Summary Header
```
TerraPay (USD) — Position Summary
  Transactions: 15 | Volume: 18,100 USD (703,950 MRU)
  L1 Profit: 8,485 MRU (commission: 90, cost: -630, FX spread: +9,025)
  L2 Profit: 6,275 MRU (4 settlements, avg FX gain: +0.38/USD)
  Receivable: 3,650 USD (142,350 MRU) — pending settlement
  Total Settled: 14,400 USD via BMI
```

#### 2B: Layer 1 — Transaction Ledger (dual currency, running balance)

This is the key table. Each row is a transaction. TWO running balances tracked simultaneously:

```
LAYER 1 — Transaction Ledger

| #  | Date     | ID   | Beneficiary Channel | USD     | Rate  | MRU       | Comm  | Cost | FX Gain | Profit | ⟨Recv USD⟩ | ⟨Recv MRU⟩ |
|----|----------|------|---------------------|---------|-------|-----------|-------|------|---------|--------|------------|------------|
|  1 | Jan 01   | T001 | sedad               |    500  | 39.0  |   19,500  |  2.50 |  -50 |    +250 | +202.5 |       500  |    19,500  |
|  2 | Jan 01   | T002 | click               |    800  | 39.0  |   31,200  |  4.00 |  -30 |    +400 |   +374 |     1,300  |    50,700  |
|  3 | Jan 02   | T003 | sedad               |  1,200  | 39.0  |   46,800  |  6.00 |  -50 |    +600 |   +556 |     2,500  |    97,500  |
|    | Jan 20   | S001 | ← SETTLEMENT        | -4,850  | 39.3  | -190,605  |       |      |         |        |    -2,350  |   -91,650  |
|  4 | Jan 22   | T022 | click               |  1,500  | 39.0  |   58,500  |  7.50 |  -30 |    +750 | +727.5 |      -850  |   -33,150  |
| ...                                                                                                                                   |
| 15 | Mar 20   | T048 | click               |    650  | 39.0  |   25,350  |  3.25 |  -30 |    +325 | +298.25|     3,650  |   142,350  |
|────|──────────|──────|─────────────────────|─────────|───────|───────────|───────|──────|─────────|────────|────────────|────────────|
|    | TOTAL    |      |                     | 18,100  |       |  703,950  | 90.25 | -630 |  +9,025 |+8,485  |     3,650  |   142,350  |
```

Key design:
- **USD column**: the foreign amount sent by client (positive for transactions)
- **Rate**: the FX rate used (fx_cadorim_rate for L1)
- **MRU column**: the MRU amount paid out to beneficiary
- **Comm / Cost / FX Gain / Profit**: Layer 1 economics per transaction
- **⟨Recv USD⟩**: RUNNING receivable balance in foreign currency. Starts at 0, increases with each transaction (+Amount_j), decreases with each settlement (-Amount_s)
- **⟨Recv MRU⟩**: RUNNING receivable balance in MRU. Increases by Amount_mru_h per transaction, decreases by (Amount_s × fx_reference_rate) per settlement

**Settlements appear INLINE** in the ledger (interleaved chronologically). They show as rows with:
- Negative USD amount (receivable decreasing)
- The settlement FX rate (fx_settlement_rate)
- The MRU credited to bank
- No comm/cost/profit columns (those belong to Layer 2)

**Pending transactions** (from the queue) also appear inline with a yellow "PENDING" badge and no balance change (they haven't executed yet).

#### 2C: Layer 2 — Settlement Detail

Below the transaction ledger, a separate table for Layer 2:

```
LAYER 2 — Settlements (TerraPay → BMI)

| ID   | Date     | USD    | FX Sett | FX Ref | MRU Received | MRU at Ref | L2 Gain  | Bank     |
|------|----------|--------|---------|--------|--------------|------------|----------|----------|
| S001 | Jan 20   | 4,850  |  39.3   |  39.0  |    190,605   |   189,150  |  +1,455  | sim_bmi  |
| S003 | Feb 05   | 3,150  |  39.4   |  39.0  |    124,110   |   122,850  |  +1,260  | sim_bmi  |
| S004 | Feb 25   | 2,800  |  39.5   |  39.0  |    110,600   |   109,200  |  +1,400  | sim_bmi  |
| S006 | Mar 20   | 3,600  |  39.6   |  39.0  |    142,560   |   140,400  |  +2,160  | sim_bmi  |
|──────|──────────|────────|─────────|────────|──────────────|────────────|──────────|──────────|
| TOTAL|          | 14,400 |  avg 39.45|       |    567,875   |   561,600  |  +6,275  |          |
```

Columns:
- **FX Sett**: rate at which the bank converted (actual)
- **FX Ref**: reference rate (what Cadorim expected based on partner agreement)
- **MRU Received**: USD × FX Sett (actual cash to bank)
- **MRU at Ref**: USD × FX Ref (what it would have been at reference)
- **L2 Gain**: MRU Received - MRU at Ref (the settlement FX gain)

#### 2D: Combined P&L Summary
```
TerraPay — Total P&L
  Layer 1:  +8,485 MRU  (spread on 15 transactions)
  Layer 2:  +6,275 MRU  (FX gain on 4 settlements)
  TOTAL:   +14,760 MRU  on 18,100 USD volume (margin: 2.10% on foreign, 2.10% on MRU)
```

### Part 3: National Partner Ledger (Wallet / SNDP / Agent)

When clicking a national partner, show a simpler ledger (single currency, MRU only):

#### Example: SNDP (B2C)

```
SNDP (B2C) — Position Summary
  Transactions: 11 | Volume: 265,000 MRU
  L1 Profit: 190 MRU (commission: 530, cost: -340)
  Client Float Impact: +150,000 deposits, -115,000 payouts = +35,000 net

TRANSACTION LEDGER

| #  | Date     | ID   | Type        | Channel        | MRU       | Comm  | Cost | Profit | ⟨Float⟩  |
|----|----------|------|-------------|----------------|-----------|-------|------|--------|----------|
|  1 | Jan 05   | T008 | b2c_deposit | internal       |  +50,000  |  100  |    0 |   +100 |  50,000  |
|  2 | Jan 06   | T009 | b2c_payout  | sedad          |  -12,000  |   24  |  -50 |    -26 |  38,000  |
|  3 | Jan 06   | T010 | b2c_payout  | agent_caisse   |   -8,000  |   16  |  -30 |    -14 |  30,000  |
|  4 | Jan 07   | T011 | b2c_payout  | sedad          |  -15,000  |   30  |  -50 |    -20 |  15,000  |
| ...                                                                                               |
|──────────────────────────────────────────────────────────────────────────────────────────────────── |
|    | TOTAL    |      |             |                | 265,000   |  530  | -340 |   +190 |  35,000  |
```

- **MRU**: positive for deposits (money in), negative for payouts (money out)
- **⟨Float⟩**: running client float balance for this partner (starts at 0, increases on deposit, decreases on payout)
- No foreign currency columns (national = MRU only)
- No Layer 2 section (no settlements for national partners)

#### Example: Agent

```
Agent Operations — Position Summary
  Transactions: 7 | Volume: 88,000 MRU
  Agent Balance: -286,240 MRU (Cadorim owes agents)

TRANSACTION LEDGER

| #  | Date     | ID   | Type          | Caisse/Channel  | MRU       | Cost | ⟨Agent Bal⟩ |
|----|----------|------|---------------|-----------------|-----------|------|-------------|
|  1 | Jan 12   | T016 | agent_cashout | agent_caisse    |  -10,000  |  -30 |    -10,000  |
|  2 | Jan 13   | T017 | agent_cashout | agent_caisse    |  -15,000  |  -30 |    -25,000  |
|  3 | Jan 28   | T027 | agent_refund  | caisse_mboirick |  +20,000  |  -30 |     -5,000  |
| ...                                                                                      |
```

- **⟨Agent Bal⟩**: running agent balance (should always be ≤ 0, agents advance cash, we owe them)

### Part 4: Bank Ledger

Add a **Bank Position** section (in Treasury tab or as part of the CEO Net Position drill-down). Clicking a bank shows its full statement:

```
BMI Bank — Statement
  Opening: 200,000 MRU
  Settlements IN: +567,875 MRU (6 settlements from 2 partners)
  Withdrawals OUT: -240,000 MRU (3 withdrawals to caisses)
  Closing: 694,150 MRU  (should be: 200,000 + 567,875 - 240,000 = 527,875 — VERIFY)

BANK LEDGER

| #  | Date     | ID   | Type       | Partner/Caisse  | Foreign  | FX Rate | MRU In    | MRU Out   | ⟨Balance⟩  |
|----|----------|------|------------|-----------------|----------|---------|-----------|-----------|------------|
|    |          |      | OPENING    |                 |          |         |           |           |   200,000  |
|  1 | Jan 20   | S001 | Settlement | TerraPay        | 4,850 USD|  39.3   | +190,605  |           |   390,605  |
|  2 | Jan 25   | W001 | Withdrawal | → caisse_babe   |          |         |           |  -80,000  |   310,605  |
|  3 | Jan 28   | S002 | Settlement | Ria             | 2,550 EUR|  42.6   | +108,630  |           |   419,235  |
|  4 | Feb 05   | S003 | Settlement | TerraPay        | 3,150 USD|  39.4   | +124,110  |           |   543,345  |
|  5 | Feb 15   | W002 | Withdrawal | → caisse_mboirick|         |         |           | -100,000  |   443,345  |
|  6 | Feb 25   | S004 | Settlement | TerraPay        | 2,800 USD|  39.5   | +110,600  |           |   553,945  |
|  7 | Mar 01   | S005 | Settlement | Ria             | 1,350 EUR|  42.7   |  +57,645  |           |   611,590  |
|  8 | Mar 10   | W003 | Withdrawal | → caisse_tidjany |         |         |           |  -60,000  |   551,590  |
|  9 | Mar 20   | S006 | Settlement | TerraPay        | 3,600 USD|  39.6   | +142,560  |           |   694,150  |
|──────────────────────────────────────────────────────────────────────────────────────────────────────────────── |
|    | TOTAL    |      |            |                 |          |         | +734,150  | -240,000  |   694,150  |
|    | CHECK    |      |            |                 |          |         | 200,000 + 734,150 - 240,000 = 694,150 ✓ |
```

Key:
- **Foreign column**: shows the original foreign amount for settlements (blank for withdrawals)
- **FX Rate**: the settlement conversion rate
- **MRU In / MRU Out**: separate columns for clarity (like a bank statement)
- **⟨Balance⟩**: running balance after each event
- **CHECK row**: arithmetic verification: Opening + Total In - Total Out = Closing ✓

For settlements, also show a sub-detail (expandable):
```
S001: TerraPay → BMI | 4,850 USD × 39.3 = 190,605 MRU
  FX Reference: 39.0 → MRU at ref: 189,150
  L2 Gain: +1,455 MRU (spread: +0.3 per USD)
```

### Part 5: Where to Place These Drill-Downs

#### Option A (recommended): New "Positions" tab

Add a 5th tab to the tab bar: **Positions**

```
[Setup] [CEO] [Treasury] [Operations] [Positions]
```

This tab contains:
1. **Partner Position Table** (top) — all partners with click-to-expand
2. **Bank Position Table** (bottom) — all banks with click-to-expand

Each expanded partner/bank shows the full ledger as described above.

#### Also link from existing tabs:

- **CEO → Net Position drill-down → Receivables**: each partner row links to/opens the partner ledger in Positions tab
- **Treasury → Bank drill-down**: each bank row links to the bank ledger in Positions tab
- **Operations → Transaction Log**: partner names are clickable, jump to that partner's ledger

### Part 6: Data Collection During Engine Run

To build these ledgers, the engine must track more data during the run. Add:

```javascript
// Per-partner running state
const partnerLedgers = {};  // key: partner_code → array of ledger entries

// Initialize for each partner
cfg.layer1.forEach(p => {
    partnerLedgers[p.code] = {
        entries: [],
        runningRecvForeign: 0,   // for international: running receivable in foreign currency
        runningRecvMRU: 0,       // running receivable in MRU
        runningFloat: 0,         // for B2C: running client float
        runningAgentBal: 0,      // for agent: running agent balance
        totalL1Profit: 0,
        totalL2Profit: 0,
        config: p                // partner config for reference
    };
});

// Per-bank running state
const bankLedgers = {};  // key: bank_code → array of ledger entries

// Initialize for each bank
Object.keys(SIM_INITIAL.bank).forEach(bk => {
    bankLedgers[bk] = {
        entries: [],
        openingBalance: SIM_INITIAL.bank[bk],
        runningBalance: SIM_INITIAL.bank[bk],
        totalIn: 0,
        totalOut: 0
    };
});
```

When processing each event:

**Transaction executed:**
```javascript
const pLedger = partnerLedgers[tx.Par_l];
if (pLedger) {
    const entry = {
        seq: pLedger.entries.length + 1,
        date: tx.date,
        id: tx.id,
        type: tx.type,
        channel: (tx.Local_Par_n || '').replace('sim_', ''),
        foreignAmount: pCfg.is_international ? V(tx.Amount_j) : null,
        currency: pCfg.is_international ? pCfg.currency : 'MRU',
        fxRate: pCfg.is_international ? V(pCfg.fx_cadorim_rate) : null,
        mruAmount: V(tx.Amount_mru_h),
        commission: pr.commission_a,
        cost: pr.cost_payout_a,
        fxGain: pr.fx_gain_a,
        profit: pr.profit_transaction_a,
        event: 'transaction',
        status: tx.wasQueued ? 'released' : 'immediate',
        timeInQueue: tx.timeInQueue || 0
    };
    
    // Update running balances
    if (pCfg.is_international) {
        pLedger.runningRecvForeign += V(tx.Amount_j);
        pLedger.runningRecvMRU += V(tx.Amount_mru_h);
        entry.recvForeign = pLedger.runningRecvForeign;
        entry.recvMRU = pLedger.runningRecvMRU;
    }
    if (tx.type === 'b2c_deposit') {
        pLedger.runningFloat += V(tx.Amount_mru_h);
        entry.float = pLedger.runningFloat;
    } else if (tx.type === 'b2c_payout') {
        pLedger.runningFloat -= V(tx.Amount_mru_h);
        entry.float = pLedger.runningFloat;
    }
    if (tx.type === 'agent_cashout') {
        pLedger.runningAgentBal -= V(tx.Amount_mru_h);
        entry.agentBal = pLedger.runningAgentBal;
    } else if (tx.type === 'agent_refund') {
        pLedger.runningAgentBal += V(tx.Amount_mru_h);
        entry.agentBal = pLedger.runningAgentBal;
    }
    
    pLedger.totalL1Profit += pr.profit_transaction_a;
    pLedger.entries.push(entry);
}
```

**Settlement:**
```javascript
const pLedger = partnerLedgers[s.Par_l];
if (pLedger) {
    const mruReceived = Math.round(V(s.Amount_s) * V(s.fx_settlement_rate) * 100) / 100;
    const mruAtRef = Math.round(V(s.Amount_s) * V(s.fx_reference_rate) * 100) / 100;
    const l2Gain = computeL2(s).gain_sett_s;
    
    pLedger.runningRecvForeign -= V(s.Amount_s);
    pLedger.runningRecvMRU -= mruAtRef;
    pLedger.totalL2Profit += l2Gain;
    
    pLedger.entries.push({
        seq: null,  // settlements don't get a sequence number in the transaction count
        date: s.date_s,
        id: s.id,
        type: 'settlement',
        channel: '',
        foreignAmount: -V(s.Amount_s),  // negative = receivable decreasing
        currency: s.Cur_k,
        fxRate: V(s.fx_settlement_rate),
        fxRef: V(s.fx_reference_rate),
        mruAmount: mruReceived,
        mruAtRef: mruAtRef,
        l2Gain: l2Gain,
        event: 'settlement',
        bank: s.Bank_t,
        recvForeign: pLedger.runningRecvForeign,
        recvMRU: pLedger.runningRecvMRU
    });
}

// Bank ledger
const bLedger = bankLedgers[s.Bank_t];
if (bLedger) {
    const mruReceived = Math.round(V(s.Amount_s) * V(s.fx_settlement_rate) * 100) / 100;
    bLedger.runningBalance += mruReceived;
    bLedger.totalIn += mruReceived;
    bLedger.entries.push({
        date: s.date_s, id: s.id, type: 'settlement',
        partner: s.Par_l, foreignAmount: V(s.Amount_s), currency: s.Cur_k,
        fxRate: V(s.fx_settlement_rate), fxRef: V(s.fx_reference_rate),
        mruIn: mruReceived, mruOut: 0,
        l2Gain: computeL2(s).gain_sett_s,
        balance: bLedger.runningBalance
    });
}
```

**Withdrawal:**
```javascript
const bLedger = bankLedgers[w.bank];
if (bLedger) {
    bLedger.runningBalance -= V(w.amount);
    bLedger.totalOut += V(w.amount);
    bLedger.entries.push({
        date: w.date, id: w.id, type: 'withdrawal',
        destination: w.caisse,
        mruIn: 0, mruOut: V(w.amount),
        balance: bLedger.runningBalance
    });
}
```

**Pending transactions** also get logged in the partner ledger with `status: 'pending'` and no balance change.

Store in results:
```javascript
engineResults = {
    ...existingFields,
    partnerLedgers,
    bankLedgers
};
```

### Part 7: Rendering the Positions Tab

#### 7A: Partner Position Table (top section)

```javascript
function buildPositions(R) {
    let h = renderWalletBar();  // same wallet status bar as other tabs
    
    // Partner Position Summary
    h += `<div class="sec"><div class="sec-hd"><h2>Partner Positions</h2></div>`;
    h += `<table><thead><tr>
        <th></th><th>Partner</th><th>Type</th><th class="n">Txns</th>
        <th class="n">Foreign Vol</th><th class="n">MRU Vol</th>
        <th class="n">L1 Profit</th><th class="n">L2 Profit</th><th class="n">Total</th>
        <th class="n">Receivable</th><th class="n">Margin</th>
    </tr></thead><tbody>`;
    
    for (const [code, ledger] of Object.entries(R.partnerLedgers)) {
        const cfg = ledger.config;
        const isIntl = cfg.is_international;
        const txCount = ledger.entries.filter(e => e.event === 'transaction').length;
        const foreignVol = isIntl ? ledger.entries.filter(e=>e.event==='transaction').reduce((a,e)=>a+(e.foreignAmount||0),0) : null;
        const mruVol = ledger.entries.filter(e=>e.event==='transaction').reduce((a,e)=>a+Math.abs(e.mruAmount||0),0);
        const margin = mruVol > 0 ? ((ledger.totalL1Profit + ledger.totalL2Profit) / mruVol * 100) : 0;
        const recv = isIntl ? `${f2(ledger.runningRecvForeign)} ${cfg.currency}` : '-';
        
        h += `<tr style="cursor:pointer" onclick="toggle('pl_${code}')">
            <td>▶</td>
            <td><strong>${code.replace('sim_','')}</strong></td>
            <td>${isIntl ? 'International' : cfg.code.includes('sndp') ? 'B2C' : cfg.code.includes('agent') ? 'Agent' : 'National'}</td>
            <td class="n">${txCount}</td>
            <td class="n">${isIntl ? f2(foreignVol)+' '+cfg.currency : '-'}</td>
            <td class="n">${fmt(mruVol)}</td>
            <td class="n ${cls(ledger.totalL1Profit)}">${f2(ledger.totalL1Profit)}</td>
            <td class="n ${cls(ledger.totalL2Profit)}">${isIntl ? f2(ledger.totalL2Profit) : '-'}</td>
            <td class="n ${cls(ledger.totalL1Profit+ledger.totalL2Profit)}" style="font-weight:700">${f2(ledger.totalL1Profit+ledger.totalL2Profit)}</td>
            <td class="n">${recv}</td>
            <td class="n">${margin.toFixed(2)}%</td>
        </tr>`;
        
        // Drill-down: full ledger (hidden by default)
        h += `<tr><td colspan="11"><div id="pl_${code}" class="drill">`;
        h += renderPartnerLedger(code, ledger, R);
        h += `</div></td></tr>`;
    }
    h += `</tbody></table></div>`;
    
    // Bank Position Table
    h += renderBankPositions(R);
    
    document.getElementById('p4').innerHTML = h;
}
```

#### 7B: renderPartnerLedger function

This renders the full ledger (as described in Parts 2 and 3 above). For international partners: dual-currency table with settlements inline and Layer 2 section below. For national: single-currency table.

The function checks `ledger.config.is_international` and renders accordingly.

#### 7C: renderBankPositions function

```
BANK POSITIONS
┌───────────────────────────────────────────────────────────────────┐
│ Bank    │ Opening   │ Sett In    │ WD Out    │ Closing    │ Check │
│─────────│───────────│────────────│───────────│────────────│───────│
│ ▶ BMI   │  200,000  │  +734,150  │ -240,000  │  694,150   │  ✓   │
└───────────────────────────────────────────────────────────────────┘
```

Click ▶ BMI → opens full bank ledger (as described in Part 4).

### Part 8: Add the 5th Tab

In the HTML, add the Positions tab:

```html
<div class="tab-bar">
    <div class="tab active" onclick="sw(0)">Setup</div>
    <div class="tab" onclick="sw(1)">CEO</div>
    <div class="tab" onclick="sw(2)">Treasury</div>
    <div class="tab" onclick="sw(3)">Operations</div>
    <div class="tab" onclick="sw(4)">Positions</div>
</div>

<!-- Add after existing tabs: -->
<div id="p4" class="page"><div class="nodata"><b>Run Engine</b> in Setup tab first</div></div>
```

Update the `sw()` function to handle 5 tabs. Call `buildPositions(engineResults)` in `runEngine()` after the other dashboard builders.

### Part 9: Style

- Partner rows: hover highlight, cursor pointer
- International ledger: settlement rows have light purple background (var(--purple-light)) to distinguish from transaction rows
- Pending transaction rows: light yellow background
- Released transaction rows: light green left border
- Running balance columns: right-aligned, tabular-nums, bold for the current balance
- Receivable column: orange text for pending amounts
- Bank ledger: MRU In = green text, MRU Out = red text
- CHECK row at bottom of bank ledger: green ✓ if balanced, red ✗ if not
- L2 section for international: bordered with purple left border (like settlement config in Setup)
- Table font: 12px for ledger tables (lots of data), with zebra striping on alternate rows for readability

### Part 10: DO NOT CHANGE

- Profit engine, balance engine, plafond gating, pending queue — all stay as-is
- Existing 4 tabs keep their current content
- Single HTML file, same CDN dependencies
- The Positions tab READS from engineResults (partnerLedgers, bankLedgers) — it doesn't compute anything new, just displays what the engine already tracked

### Part 11: Testing

1. Load simulation → Run Engine → go to Positions tab
2. See 5 partner rows + 1 bank row
3. Click TerraPay → full dual-currency ledger with 15 transactions + 4 settlements inline + running receivable in USD and MRU + Layer 2 settlement detail
4. Click Ria → same structure but EUR, 9 transactions + 2 settlements
5. Click SNDP → single-currency MRU ledger with float tracking (deposits positive, payouts negative)
6. Click Agent → MRU ledger with agent balance tracking (always ≤ 0)
7. Click Wallet → MRU ledger with cashout tracking
8. Click BMI → full bank statement: opening 200K, 6 settlements in, 3 withdrawals out, closing 694K, arithmetic check ✓
9. Running balances are CONSISTENT — the final receivable in the TerraPay ledger matches the receivable shown in CEO Net Position
10. Total L1+L2 profit per partner sums to the total shown in CEO
