# Claude Code Prompt — Plafond Liquidity Gating System (Stage 1) — REVISED

## Context

File: `~/cadorim-engine/engine.html` — a single-file accounting engine with 4 tabs (Setup, CEO, Treasury, Operations). Runs a simulation with 5 partners, 50 transactions, 6 settlements, 3 bank withdrawals. Everything in JS memory (no localStorage, no backend).

The engine has wallet channels (Sedad, Click, Masrvi, Bankily) that are shared pools pre-funded by Cadorim. Multiple partners drain the same pool. We need a Plafond (cap) system to allocate each pool across partners, with priority-based gating.

**Scope of plafond**: ONLY wallet-type channels. Agent caisses and internal channels are exempt — agents use their own money.

## BUGS TO FIX FROM CURRENT BUILD

The current plafond implementation has these issues that MUST be fixed:

### Bug 1: Missing wallets
Historical Usage Distribution only shows sim_sedad and sim_click. It MUST show ALL 4 wallet channels from SIM_INITIAL.wallet: sedad, click, masrvi, bankily. Even if a wallet has zero historical transactions, show it with "No historical usage — set plafond manually". The wallet list must be DYNAMIC — derived from `SIM_INITIAL.wallet` keys, not hardcoded.

### Bug 2: Unlimited (-1) plafond allowed
The value -1 (unlimited) must NOT be allowed. Every wallet has a finite balance. If you set a partner to "unlimited" on a 150K wallet, you've defeated the entire purpose. REMOVE the -1 option entirely. Valid plafond values: 0 (blocked) or any positive integer ≤ channel balance. The input field must enforce: `min="0"`, and the sum of all plafonds on a channel must be ≤ channel balance.

### Bug 3: Duplicate (channel, partner) pairs possible
The UI currently allows adding two rows for the same (channel, partner) combination (e.g., two rows of sim_sedad × sim_terrapay). This MUST be prevented. Each (channel, partner) pair can appear AT MOST once. When adding a new row, if the pair already exists, show an alert and refuse. The dropdown options should ideally filter out already-used combinations.

### Bug 4: No totals / validation per channel
Below the Plafond Allocation Rules table, there must be a VALIDATION SUMMARY grouped by channel:

```
sim_sedad:  125,000 + 16,000 + 9,000 = 150,000 / 150,000 (100%) ✓
sim_click:  70,000 = 70,000 / 70,000 (100%) ✓  
sim_masrvi: (no rules) = 0 / 80,000 (0%) ⚠ Unallocated
sim_bankily: (no rules) = 0 / 50,000 (0%) ⚠ Unallocated
```

Format per channel: list each partner's plafond with `+` between them, then `= sum / balance (%)`.
- Green ✓ if sum ≤ balance
- Red ✗ if sum > balance (OVER-ALLOCATED — this is an error, block engine run)
- Yellow ⚠ if sum = 0 (no rules — warn that this wallet is unprotected)

### Bug 5: Historical usage percentages unclear
The historical bars show %, volume, and "→ suggested plafond" but it's not clear how the suggestion is computed. Make it explicit:

```
sim_sedad (150,000 MRU available):
  terrapay    ████████████████████░░░ 84%   508,950 MRU volume   → 84% × 150,000 = 126,000 suggested
  sndp        ███░░░░░░░░░░░░░░░░░░░ 11%    65,000 MRU volume   → 11% × 150,000 =  16,500 suggested
  wallet      ██░░░░░░░░░░░░░░░░░░░░  6%    35,000 MRU volume   →  6% × 150,000 =   9,000 suggested
  TOTAL                              100%   608,950 MRU          → 150,000 allocated (fits in balance)
```

Show the formula visibly: `percentage × channel_balance = suggested_plafond`. Add a TOTAL row per channel summing to 100% and showing that total suggested fits within balance.

## COMPLETE SPECIFICATION

### Section 1: Channel Liquidity Overview

Location: Setup tab, between "Payout Channels" and "Settlement Config".
Style: `border-left: 3px solid var(--accent)` (orange). Badge: "Liquidity" in orange.

#### 1A. Channel Balance Table

Read-only table. Populated DYNAMICALLY from `SIM_INITIAL.wallet` keys:

| Channel | Balance (MRU) | Status |
|---------|--------------|--------|
| sim_sedad | 150,000 | Active |
| sim_click | 70,000 | Active |
| sim_masrvi | 80,000 | Active |
| sim_bankily | 50,000 | Active |

Every key in `SIM_INITIAL.wallet` becomes a row. Map the key to channel name by prepending "sim_" (matching channel codes used elsewhere). If in the future someone adds a new wallet to SIM_INITIAL, it appears automatically.

#### 1B. Historical Usage Distribution

For EACH wallet channel (all 4), scan ALL transactions in `SIM_TXS` and compute:

```javascript
// For each wallet channel
for (const walletKey of Object.keys(SIM_INITIAL.wallet)) {
    const channelCode = "sim_" + walletKey;  // e.g., "sim_sedad"
    const txsOnChannel = SIM_TXS.filter(t => t.Local_Par_n === channelCode);
    const totalVol = sum of Amount_mru_h for txsOnChannel;
    
    // Group by partner
    for each unique Par_l in txsOnChannel:
        partnerVol = sum of Amount_mru_h where Par_l matches
        percentage = partnerVol / totalVol * 100
        suggestedPlafond = Math.round(percentage / 100 * walletBalance)
    
    // Show TOTAL row: 100%, totalVol, walletBalance
}
```

If a wallet has ZERO transactions (like masrvi and bankily in this simulation), show:
```
sim_masrvi (80,000 MRU available):
  No historical usage — set plafond manually
```

Display format per channel — show the calculation explicitly:
```
sim_sedad (150,000 MRU available):
  terrapay    [===bar===] 84%    508,950 vol    → 84% × 150,000 = 126,000
  sndp        [==bar=]    11%     65,000 vol    → 11% × 150,000 =  16,500
  wallet      [=bar]       6%     35,000 vol    →  6% × 150,000 =   9,000
  ─────────────────────────────────────────────────────────────────────────
  TOTAL                  100%    608,950 vol    → 150,000 total suggested
```

Button: **"Auto-fill from history"** — populates the plafond table with the suggested values. Only fills rules for (channel, partner) pairs that have historical usage. Does NOT add rules for wallets with zero history (user must add manually).

#### 1C. Plafond Allocation Rules (editable table)

Table columns:
| Channel | Partner | Plafond (MRU) | % of Balance | Priority | Status | ✕ |

**Channel**: dropdown. Options = ONLY wallet channel codes derived from `SIM_INITIAL.wallet` keys (sim_sedad, sim_click, sim_masrvi, sim_bankily). NO agent_caisse, NO internal.

**Partner**: dropdown. Options = all partner codes from `partners[]` array. BUT: if the selected (channel, partner) already exists in another row, disable/prevent submission. Enforce UNIQUE constraint on (channel, partner).

**Plafond (MRU)**: number input. `min="0"`. No negative values. No -1. Value of 0 means "blocked".

**% of Balance**: read-only, auto-computed. Formula: `plafond / channelBalance × 100`. Show as "83%" format. Fetch channel balance from `SIM_INITIAL.wallet[channelKey]`.

**Priority**: dropdown 1-5. Display with colored circle badge (1=green, 2=blue, 3=yellow, 4=orange, 5=red).

**Status**: read-only badge.
- Plafond > 0 → green "Active"
- Plafond = 0 → red "Blocked"

**✕ button**: removes the row.

**"+ Add plafond rule" button**: adds a new empty row. If user selects a (channel, partner) pair that already exists, show toast error "Rule already exists for this pair" and revert.

#### 1D. Validation Summary (below the table)

For EACH wallet channel (all 4, always shown), display one validation line:

```
sim_sedad: terrapay 126,000 + sndp 16,500 + wallet 9,000 = 151,500 / 150,000 (101%) ✗ OVER-ALLOCATED
sim_click: terrapay 70,000 = 70,000 / 70,000 (100%) ✓
sim_masrvi: (no rules defined) = 0 / 80,000 (0%) ⚠ UNPROTECTED  
sim_bankily: (no rules defined) = 0 / 50,000 (0%) ⚠ UNPROTECTED
```

Format: list each partner plafond joined by " + ", then " = total / balance (%)".
- ✓ green if total ≤ balance
- ✗ red bold if total > balance — and BLOCK the "Run Engine" button (show error toast "Fix over-allocation before running")
- ⚠ yellow if total = 0 (warn but allow)

This validation must UPDATE LIVE as the user edits plafond values (use oninput/onchange handlers).

### Section 2: Engine Gating Logic

#### 2A. State tracking

```javascript
let plafondUsage = {};    // "partner|channel" → cumulative MRU used
let blockedTxs = [];      // blocked transactions with reasons
```

Reset both at the start of `runEngine()`.

#### 2B. Gating function

```javascript
function checkPlafond(tx, cfg) {
    const channel = tx.Local_Par_n;
    const partner = tx.Par_l;
    const amount = V(tx.Amount_mru_h);
    const pool = getPool(channel);

    // ONLY gate wallet channels. Everything else passes freely.
    if (pool.type !== 'wallet') {
        return { allowed: true, reason: "exempt" };
    }

    const key = partner + "|" + channel;
    const rule = (cfg.plafonds || []).find(p => p.channel === channel && p.partner === partner);

    // No rule on a gated channel = not allocated = blocked
    if (!rule) {
        return { allowed: false, reason: "no_allocation" };
    }

    // Plafond = 0 = explicitly blocked
    if (V(rule.plafond) === 0) {
        return { allowed: false, reason: "blocked" };
    }

    // Check usage against cap
    const used = plafondUsage[key] || 0;
    const cap = V(rule.plafond);
    if (used + amount > cap) {
        return {
            allowed: false, reason: "exceeded",
            used, cap, requested: amount, remaining: cap - used
        };
    }

    return { allowed: true, reason: "ok", used, remaining: cap - used - amount };
}
```

#### 2C. Integration in runEngine()

In the main event loop, BEFORE processing a transaction:

```javascript
if (ev._t === 'tx') {
    const plafondCheck = checkPlafond(ev, cfg);
    if (!plafondCheck.allowed) {
        // Compute what profit WOULD have been (for "lost revenue" reporting)
        const wouldBeProfit = computeL1(ev, cfg);
        blockedTxs.push({
            ...ev,
            ...wouldBeProfit,
            blockReason: plafondCheck.reason,
            blockDetail: plafondCheck
        });
        // Add alert
        bal.alerts.push({
            severity: 'yellow',
            date: ev.date,
            id: ev.id,
            msg: `BLOCKED ${ev.id}: ${ev.Par_l}→${(ev.Local_Par_n||'').replace('sim_','')} ${fmt(ev.Amount_mru_h)} MRU (${plafondCheck.reason}${plafondCheck.remaining !== undefined ? ', remaining: '+fmt(plafondCheck.remaining) : ''})`
        });
    } else {
        // Update usage tracker
        const pool = getPool(ev.Local_Par_n);
        if (pool.type === 'wallet') {
            const key = ev.Par_l + "|" + ev.Local_Par_n;
            plafondUsage[key] = (plafondUsage[key] || 0) + V(ev.Amount_mru_h);
        }
        // Process normally
        const pr = computeL1(ev, cfg);
        applyTx(ev, pr, bal);
        txR.push({...ev, ...pr});
    }
}
```

#### 2D. Settlement resets plafond usage

When a settlement arrives for Par_l, the partner's money is coming in — this replenishes the float. In `applySett()` or right after calling it, reduce plafond usage for that partner across all channels:

```javascript
// After applying settlement
const settMru = Math.round(V(s.Amount_s) * V(s.fx_reference_rate) * 100) / 100;
// Reduce usage for this partner across all wallet channels, pro-rata
const partnerKeys = Object.keys(plafondUsage).filter(k => k.startsWith(s.Par_l + "|"));
const totalUsage = partnerKeys.reduce((a, k) => a + plafondUsage[k], 0);
if (totalUsage > 0) {
    partnerKeys.forEach(k => {
        const share = plafondUsage[k] / totalUsage;
        plafondUsage[k] = Math.max(0, plafondUsage[k] - settMru * share);
    });
}
```

#### 2E. Store results

Add to `engineResults`:
```javascript
engineResults = {
    ...existing fields,
    blockedTxs: blockedTxs,
    plafondUsage: {...plafondUsage},
    plafondRules: cfg.plafonds || []
};
```

### Section 3: Dashboard Updates

#### 3A. CEO Tab — "Blocked Volume" card

Add one new card in the existing cards grid:
```
Label: "Blocked"
Value: total blocked MRU (red color, vr class)
Sub-text: "X txns | Y MRU lost profit"
```

Where lost profit = sum of `profit_transaction_a` computed for each blocked tx.

#### 3B. Treasury Tab — Plafond partition in wallet drill-down

In the wallet drill-down table (div id="dw"), after each wallet row, add indented sub-rows showing partner allocation:

```
| sedad      | 150,000 initial | [final balance] | Status |
|  ├ terrapay |  126,000 cap    |  XX,XXX used    | [% bar] |
|  ├ sndp     |   16,500 cap    |  XX,XXX used    | [% bar] |
|  └ wallet   |    9,000 cap    |  XX,XXX used    | [% bar] |
```

Sub-rows: smaller font (11px), left-padded. % bar as inline colored span: green <70%, yellow 70-90%, red >90%.

#### 3C. Operations Tab — Plafond Status + Blocked Transactions

**At the top**, before the existing Channel Volume chart:

**"Plafond Status" section:**
Table with final usage state:
| Channel | Partner | Cap | Used | Remaining | % Used | Priority |
Color-code rows by % used (same thresholds: green/yellow/red).

**"Blocked Transactions" section** (only if blockedTxs.length > 0):
Table:
| ID | Date | Type | Partner | Channel | Amount MRU | Reason | Lost Profit |
Style: rows with light red background (var(--red-light)).
Footer row: **TOTAL: X transactions blocked | Y MRU volume | Z MRU lost profit**

### Section 4: Simulation Data

Update `SIM_CONFIG` to include plafonds. Use values derived from historical usage (84%/11%/6% split on sedad):

```javascript
"plafonds": [
    {"channel":"sim_sedad","partner":"sim_terrapay","plafond":126000,"priority":1},
    {"channel":"sim_sedad","partner":"sim_sndp","plafond":16500,"priority":3},
    {"channel":"sim_sedad","partner":"sim_wallet","plafond":9000,"priority":4},
    {"channel":"sim_click","partner":"sim_terrapay","plafond":70000,"priority":1}
]
```

Note: masrvi and bankily have no transactions in the simulation, so no plafond rules for them. The validation summary should show them as "⚠ UNPROTECTED".

Note: NO rules for sim_agent_caisse or sim_internal — exempt from plafond.

Update `loadFromDict()` to parse plafonds from config. Update `buildConfigJSON()` to include plafonds in export. Update `loadSimulation()` to load plafond rules and render them.

### Section 5: Style

- Same light cream theme (#F7F5F0), white cards
- Plafond section: `border-left: 3px solid var(--accent)` (orange #D97706)
- Badge "Liquidity": orange background/text (like b-blue but orange)
- Historical bars: inline div, height 18px, background var(--accent) for fill, var(--surface-alt) for empty
- Priority circles: 20px round, centered number. Colors: 1=#059669, 2=#2563EB, 3=#CA8A04, 4=#D97706, 5=#DC2626
- Validation: green text + ✓ for OK, red bold + ✗ for over-allocated, yellow + ⚠ for unprotected
- Blocked transaction rows: background var(--red-light), ID with text-decoration line-through
- All numbers: existing `fmt()` (French locale) and `f2()` (2 decimals)

### Section 6: Constraints (DO NOT violate)

1. Do NOT change computeL1, computeL2, applyTx, applySett, applyWd internal logic
2. Do NOT change existing Setup tables (Partners, Payout Channels, Settlements)
3. Do NOT remove any existing features, buttons, or tabs
4. Single HTML file only. Only CDN deps: Chart.js and html2pdf.js (already loaded)
5. No -1 values. No negative plafonds. Minimum is 0.
6. Each (channel, partner) pair appears at most ONCE in plafond rules
7. Sum of plafonds per channel MUST be ≤ channel balance (enforce visually + block engine if violated)
8. Plafond applies ONLY to wallet-type channels (pool.type === 'wallet'). Agent caisse, internal, cash — all exempt.
9. Historical Usage Distribution must show ALL wallets from SIM_INITIAL.wallet, not just the ones with transactions
10. Validation summary must show ALL wallets from SIM_INITIAL.wallet, not just the ones with rules
