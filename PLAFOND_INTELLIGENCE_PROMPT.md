# Claude Code Prompt — Plafond Intelligence: Balance Visibility + Decision Support

## Context

File: `~/cadorim-engine/engine.html`. The Plafond gating system is already built and working. But there are critical problems in how it presents information and makes decisions.

## THE CORE PROBLEM

A TerraPay transaction gets BLOCKED with message "exceeded (used 90,000 of 126,000, need 78,000, remaining 36,000)". Meanwhile, Sedad's ACTUAL balance might still be 85,000 MRU (because other partners haven't used their full allocation). The user sees: "Why is this blocked? There's money in Sedad!"

The disconnect: the **plafond** is an allocation cap (how much of the pool you're allowed to use), but the **actual balance** is the real money in the channel. The user needs to see BOTH to understand why a block happened and what to do about it.

Currently the engine tracks plafond usage but does NOT show the actual wallet balance at the time of each transaction/block. This must change.

## WHAT TO BUILD

### 1. Track and display ACTUAL wallet balance alongside plafond usage

#### 1A. In the engine loop, record wallet balance at each event

Currently `timeline[]` records equation-level totals. Add per-wallet balance snapshots. After each event (tx, settlement, withdrawal), record:

```javascript
// Add to timeline entry:
walletBalances: {...bal.wallet},  // snapshot of all wallet balances at this moment
plafondState: {...plafondUsage}   // snapshot of all plafond usage at this moment
```

#### 1B. For each BLOCKED transaction, record the actual wallet balance at time of block

Currently blockedTxs stores the block reason. Add:

```javascript
blockedTxs.push({
    ...ev,
    ...pr,
    blockReason: gate.reason,
    blockDetail: detail,
    // NEW: what was the actual state when this was blocked?
    walletBalanceAtBlock: bal.wallet[pool.key],  // actual MRU in the channel right now
    plafondUsed: plafondUsage[key] || 0,
    plafondCap: gate.cap,
    plafondRemaining: gate.remaining
});
```

This lets the user see: "T046 was blocked because TerraPay used 90K of its 126K cap (remaining: 36K, needed: 117K). But Sedad actual balance was 62,000 MRU at that moment."

### 2. CEO Tab — Full blocked transaction table + decision context

#### 2A. Replace the simple "Blocked" card with a clickable card that opens a drill-down

When the user clicks the Blocked card, show a detailed section:

**"Blocked Transactions — Decision Review"**

Table:
| ID | Date | Partner | Channel | Amount | Plafond Cap | Used | Remaining | Actual Balance | Lost Profit | Recommendation |

- **Plafond Cap**: the partner's allocation on this channel
- **Used**: how much the partner had used at the moment of blocking
- **Remaining**: cap - used (what was left in the allocation)
- **Actual Balance**: the REAL balance of the wallet channel at the moment of blocking
- **Lost Profit**: the profit this transaction would have generated
- **Recommendation**: auto-generated text (see section 3)

Style: light red background rows. Make the "Actual Balance" column prominent — if actual balance > transaction amount, highlight it in blue to signal "money was available, allocation was the constraint."

#### 2B. Summary cards above the table

Show 3 mini-metrics:
```
Blocked Volume: 275,000 MRU (9 txns)
Lost Profit: 2,181 MRU
Recoverable: X MRU (Y txns had actual balance available — could have gone through with higher plafond)
```

**"Recoverable"** = sum of lost profit for blocked transactions where `walletBalanceAtBlock >= Amount_mru_h`. These are transactions that COULD have executed if the plafond was higher — the money was physically there. This is the key number for the CEO: "how much money did we leave on the table because of allocation limits, not because of actual cash shortage?"

### 3. Smart Recommendations

For each blocked transaction, generate one of these recommendation types:

#### Type A: "Increase plafond" 
When: `walletBalanceAtBlock >= Amount_mru_h` (money was there, allocation was the constraint)
Text: `"Actual balance was ${walletBalance}. Increase ${partner} plafond on ${channel} from ${cap} to ${cap + amount - remaining} to allow this."`

#### Type B: "Top up channel"
When: `walletBalanceAtBlock < Amount_mru_h` AND caisse balances are healthy
Text: `"Actual balance was only ${walletBalance}. Top up ${channel} from ${bestCaisse} (balance: ${caisseBalance})."`

#### Type C: "Wait for settlement"
When: `walletBalanceAtBlock < Amount_mru_h` AND there are pending receivables for this partner
Text: `"Balance insufficient. Receivable pending: ${receivableAmount} ${currency} from ${partner}. Expected settlement will replenish."`

#### Type D: "Reallocate from underused partner"
When: Another partner on the same channel has remaining allocation > 30% unused
Text: `"${otherPartner} has ${remaining} unused on ${channel} (${pctUnused}% of allocation). Reallocate ${suggestedAmount} to ${partner}."`

The recommendation engine uses the state at the moment of blocking:
```javascript
function recommend(blockedTx, bal, plafondUsage, cfg) {
    const channel = blockedTx.Local_Par_n;
    const partner = blockedTx.Par_l;
    const amount = V(blockedTx.Amount_mru_h);
    const pool = getPool(channel);
    const actualBalance = blockedTx.walletBalanceAtBlock;
    
    // Type A: money was there
    if (actualBalance >= amount) {
        const needed = (blockedTx.plafondUsed + amount) - blockedTx.plafondCap;
        return {
            type: 'increase_plafond',
            text: `Balance was ${fmt(actualBalance)}. Increase plafond by ${fmt(needed)} to allow.`,
            actionable: true,
            priority: 'high'
        };
    }
    
    // Type D: another partner has unused allocation
    const sameChannelRules = (cfg.plafonds||[]).filter(r => r.channel === channel && r.partner !== partner);
    for (const r of sameChannelRules) {
        const key = r.partner + '|' + channel;
        const theirUsed = plafondUsage[key] || 0;
        const theirCap = V(r.plafond);
        const theirRemaining = theirCap - theirUsed;
        if (theirRemaining > theirCap * 0.3) {
            return {
                type: 'reallocate',
                text: `${r.partner.replace('sim_','')} has ${fmt(theirRemaining)} unused (${Math.round(theirRemaining/theirCap*100)}%). Reallocate to ${partner.replace('sim_','')}.`,
                actionable: true,
                priority: 'medium'
            };
        }
    }
    
    // Type C: receivable pending
    if (bal.receivable[partner] && bal.receivable[partner].mru > 0) {
        return {
            type: 'wait_settlement',
            text: `Receivable: ${f2(bal.receivable[partner].foreign)} ${bal.receivable[partner].currency}. Settlement will replenish.`,
            actionable: false,
            priority: 'low'
        };
    }
    
    // Type B: top up from caisse
    const bestCaisse = Object.entries(bal.cash).sort((a,b) => b[1] - a[1])[0];
    if (bestCaisse && bestCaisse[1] > amount) {
        return {
            type: 'top_up',
            text: `Top up ${channel.replace('sim_','')} from ${bestCaisse[0]} (balance: ${fmt(bestCaisse[1])}).`,
            actionable: true,
            priority: 'high'
        };
    }
    
    return { type: 'no_action', text: 'Insufficient liquidity across all pools.', actionable: false, priority: 'critical' };
}
```

Run this function for each blocked transaction AT THE TIME it's blocked (using the balance state at that moment, not the final state). Store the recommendation in `blockedTxs[]`.

### 4. Treasury Tab — Live wallet balance with plafond context

#### 4A. Enhanced wallet drill-down

Currently the wallet drill-down shows:
```
| Wallet | Initial | Balance | Status |
```

Change to show the FULL picture:

```
| Wallet | Initial | Final Balance | Plafond Total | Used Total | Available | Status |
```

Where:
- **Plafond Total** = sum of all plafond caps for this channel
- **Used Total** = sum of all plafond usage for this channel  
- **Available** = min(Final Balance, Plafond Total - Used Total) — the REAL amount that can still be disbursed
- **Status**: OK / LOW / EXHAUSTED based on Available

#### 4B. Per-partner rows (already exist, improve them)

The current per-partner breakdown shows usage bars. Improve to also show:
- The partner's remaining allocation: `Remaining: 36,000 of 126,000`
- Whether there were blocked transactions for this partner on this channel: `(3 txns blocked, 195K MRU)`
- The actual wallet balance when the last block happened

Format:
```
sedad: Initial 150,000 → Final 62,000 | Allocated: 151,500 | Used: 89,000 | Available: min(62,000, 62,500) = 62,000
  ├ terrapay  126,000 cap | 90,000 used | 36,000 remaining [====70%===]  2 blocked (195,000 MRU)
  ├ sndp       16,500 cap | 16,500 used |      0 remaining [===100%===]  1 blocked (10,000 MRU)
  └ wallet      9,000 cap |  9,000 used |      0 remaining [===100%===]  1 blocked (9,000 MRU)
```

### 5. Operations Tab — Enhanced plafond status

#### 5A. Plafond Status table

The existing plafond status table should add:
- **Actual Channel Balance** column (final balance of the wallet)
- **Blocked Count** column (how many transactions were blocked for this rule)
- **Blocked Volume** column

#### 5B. Blocked Transactions table improvements

Add columns:
- **Actual Balance** at time of block
- **Could Execute?** = "YES" (green) if actual balance >= amount, "NO" (red) if not
- **Recommendation** (short text from the recommend() function)

### 6. IMPORTANT: Fix plafond usage after settlement

Currently, settlement reduces plafond usage pro-rata. But this has a subtle bug: if TerraPay settles 4,850 USD at fx_ref 39.0 = 189,150 MRU, and TerraPay's total usage across channels is 170,000 MRU, the reduction caps at 170,000 (usage goes to 0). This is correct.

BUT: the settlement also brings ACTUAL money into the bank (not into the wallet). The wallet balance doesn't change on settlement — only the bank balance changes. So after settlement, the plafond usage resets but the wallet is still drained. This is the correct behavior — the plafond reset means TerraPay can use the channel again, but only if the wallet has been topped up (via bank withdrawal → caisse → wallet top-up).

Make sure the engine does NOT auto-increase wallet balances on settlement. The wallet only gets money when there's an explicit top-up event (bank withdrawal to caisse, then caisse to wallet). The plafond reset just means "this partner is allowed to transact again if there's float available."

### 7. Style

- Recommendation badges: colored pills — green "Increase plafond", blue "Reallocate", yellow "Wait settlement", orange "Top up", red "No action"
- "Could Execute?" column: green background with "YES" or red with "NO"  
- "Recoverable" metric card: blue border, blue text (this is opportunity, not loss)
- Keep all existing styles, just enhance the tables and add the recommendation column
- All numbers: existing fmt() / f2() formatting

### 8. DO NOT CHANGE

- computeL1, computeL2 functions
- applyTx, applySett, applyWd internal balance logic
- Existing Setup tab structure (Partner Config, Payout Channels, Settlement Config, Plafond sections)
- Existing chart rendering logic
- Single HTML file, same CDN dependencies

### 9. TESTING EXPECTATIONS

After changes, run simulation and verify:

1. **CEO → Click "Blocked" card** → see full table of 9 blocked transactions with actual balance at time of block, lost profit, and recommendation per transaction
2. **Recoverable number** should be > 0 — some blocked transactions had actual balance available (plafond was the constraint, not cash)
3. **Treasury → Wallet drill-down** → each wallet shows final balance, total allocated, total used, available. Per-partner rows show blocked count.
4. **Operations → Plafond Status** → shows actual balance column and "Could Execute?" for blocked transactions
5. **Recommendations** make sense — "Increase plafond" when money was there, "Reallocate" when another partner had unused allocation, "Wait settlement" when receivable exists, "Top up" when caisses have cash
