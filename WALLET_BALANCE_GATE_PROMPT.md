# Claude Code Prompt — Fix: Wallet Balance Must Never Go Negative

## Context

File: `~/cadorim-engine/engine.html`. The Plafond system gates transactions based on partner allocation caps. BUT there is a critical bug: the plafond check does NOT verify the actual wallet balance. A transaction can pass the plafond check (partner still has allocation) but drive the wallet balance below zero because the wallet was already drained by other partners.

Example: Sedad has 150,000 MRU. TerraPay has 126,000 plafond. SNDP has 16,500 plafond. Wallet has 9,000 plafond. Total = 151,500 (which already shouldn't be allowed but that's a separate issue). TerraPay uses 90,000. SNDP uses 16,500. Wallet uses 9,000. Total drained = 115,500. Sedad balance = 34,500. Now TerraPay sends another 78,000 transaction. Plafond check: used 90,000 + 78,000 = 168,000 > 126,000 cap → BLOCKED. Good.

But different scenario: TerraPay uses 50,000 (within plafond). SNDP uses 16,500. Wallet uses 9,000. A settlement arrives, resetting TerraPay's usage to 0. Now TerraPay sends 90,000. Plafond check: used 0 + 90,000 ≤ 126,000 → ALLOWED. But Sedad actual balance = 150,000 - 50,000 - 16,500 - 9,000 = 74,500. Transaction of 90,000 > 74,500 → **WALLET GOES TO -15,500.**

The plafond usage was reset by settlement, but the actual wallet was NOT replenished (settlement goes to bank, not wallet). This is the bug.

## THE FIX

### Rule: A transaction through a wallet channel is allowed ONLY IF BOTH conditions are true:

1. **Plafond check passes**: partner usage + amount ≤ partner's plafond cap
2. **Balance check passes**: current wallet balance ≥ transaction amount

If either fails, the transaction is BLOCKED. The block reason should clearly state which constraint was hit.

### Modified checkPlafond function

Replace the current `checkPlafond` function with this logic:

```javascript
function checkPlafond(tx, cfg, plafondUsage, walletBalances) {
    const ch = tx.Local_Par_n;
    const par = tx.Par_l;
    const amt = V(tx.Amount_mru_h);
    const pool = getPool(ch);

    // Only gate wallet channels — agent_caisse, internal, cash all exempt
    if (pool.type !== 'wallet') return { allowed: true, reason: 'exempt' };

    const key = par + '|' + ch;
    const rule = (cfg.plafonds || []).find(p => p.channel === ch && p.partner === par);

    // No rule on a wallet channel = not allocated = blocked
    if (!rule) return { allowed: false, reason: 'no_allocation' };

    const cap = V(rule.plafond);

    // Plafond = 0 = explicitly blocked
    if (cap === 0) return { allowed: false, reason: 'blocked' };

    // CHECK 1: Plafond allocation
    const used = plafondUsage[key] || 0;
    if (used + amt > cap) {
        return {
            allowed: false,
            reason: 'plafond_exceeded',
            used, cap, requested: amt,
            remaining: cap - used,
            walletBalance: walletBalances[pool.key] || 0
        };
    }

    // CHECK 2: Actual wallet balance — the wallet must have enough cash
    const currentBalance = walletBalances[pool.key] || 0;
    if (currentBalance < amt) {
        return {
            allowed: false,
            reason: 'insufficient_balance',
            walletBalance: currentBalance,
            requested: amt,
            shortfall: amt - currentBalance,
            plafondOk: true,  // plafond was fine, balance wasn't
            used, cap, remaining: cap - used
        };
    }

    return {
        allowed: true, reason: 'ok',
        used, remaining: cap - used - amt,
        walletBalance: currentBalance - amt
    };
}
```

### Updated call in runEngine()

Pass the current wallet balances to the check function:

```javascript
if (ev._t === 'tx') {
    const gate = checkPlafond(ev, cfg, plafondUsage, bal.wallet);
    // ... rest stays the same
}
```

### Block detail messages

Update the block detail string to distinguish the two reasons:

- **plafond_exceeded**: `"Plafond exceeded: used ${used} of ${cap}, need ${requested}, remaining ${remaining}. Wallet balance: ${walletBalance}."`
- **insufficient_balance**: `"Insufficient balance: wallet has ${walletBalance}, need ${requested} (shortfall: ${shortfall}). Plafond OK (${used} of ${cap} used)."`
- **blocked**: `"Blocked (plafond = 0)"`  
- **no_allocation**: `"No plafond rule — partner not allocated on this channel"`

### Updated recommendation logic

For `insufficient_balance` blocks, the recommendation should be:

- **Type: "Top up wallet"** — check if caisses have enough cash: `"Top up ${channel} from ${bestCaisse} (balance: ${caisseBalance}). Need ${shortfall} MRU."`
- **Type: "Withdraw from bank"** — if caisses are low but bank is healthy: `"Bank ${bankName} has ${bankBalance}. Withdraw ${shortfall} to caisse, then fund ${channel}."`
- **Type: "Wait settlement"** — if a settlement is pending for any partner: `"Settlement pending: ${amount} ${currency} from ${partner}. Will arrive at bank — plan top-up after."`

For `plafond_exceeded` blocks where wallet balance was sufficient, keep the existing recommendations (increase plafond, reallocate).

### Wallet bar color update

In the wallet status bar at the top of each tab, a wallet should NEVER show red/negative after this fix. If it does, that's a bug. The wallets should show:
- Green: balance > 50% of initial  
- Yellow: balance 10-50% of initial
- Orange: balance < 10% of initial but > 0
- The balance should NEVER be < 0

### Validation at end of engine run

After processing all events, add a sanity check:

```javascript
// After the event loop, verify no wallet went negative
for (const [k, v] of Object.entries(bal.wallet)) {
    if (v < -0.01) {  // small tolerance for floating point
        console.error(`BUG: wallet ${k} has negative balance: ${v}`);
        bal.alerts.push({
            severity: 'red',
            date: 'END',
            id: 'SANITY',
            msg: `ERROR: wallet ${k} ended at ${fmt(v)} MRU — should never be negative`
        });
    }
}
```

## ALSO FIX: Settlement plafond reset should consider actual state

Currently, when a settlement arrives, plafond usage is reduced. But the settlement money goes to the BANK, not to the wallet. So the plafond usage reset creates a false sense of "you can transact again" when the wallet might be nearly empty.

**Better approach**: Only reset plafond usage by the amount that the wallet was ACTUALLY replenished, not by the settlement amount. Since settlements go to bank (not wallet), the plafond usage should NOT reset on settlement. It should ONLY reset when the wallet actually receives funds (via a top-up/withdrawal event that credits the wallet).

Change the settlement handler:

```javascript
} else if (ev._t === 'se') {
    applySett(ev, bal);
    // DO NOT reset plafond usage here.
    // Settlement goes to bank, not wallet.
    // Plafond usage resets only when wallet is topped up.
    // REMOVE the existing pro-rata plafond reset code.
}
```

And add plafond reset when a withdrawal happens that funds a wallet (if such events exist), or when any event increases a wallet balance. In the current simulation, bank withdrawals go to caisses (not wallets), so there's no wallet top-up event. The plafond usage stays cumulative for the full simulation — which is correct because the wallets never get refilled.

## SUMMARY OF CHANGES

1. Add wallet balance check as SECOND gate in `checkPlafond()` — pass `bal.wallet` to the function
2. Two distinct block reasons: `plafond_exceeded` vs `insufficient_balance`
3. Block detail messages clearly state which constraint failed
4. Recommendations differ: plafond issue → increase/reallocate, balance issue → top up/withdraw
5. REMOVE settlement plafond usage reset (settlement goes to bank, not wallet)
6. Add end-of-run sanity check: all wallet balances ≥ 0
7. Wallet status bar should never show negative numbers after this fix

## DO NOT CHANGE

- computeL1, computeL2
- applyTx, applySett, applyWd internal logic  
- Setup tab structure (plafond config tables, historical usage, validation)
- CEO drill-downs, Treasury layout, Operations layout
- Single HTML file, same CDN deps

## TESTING

After fix, run simulation and verify:
1. **ALL wallet balances ≥ 0** at all times (sedad, click, masrvi, bankily)
2. **More transactions blocked** than before (because balance check is now also enforced)
3. Blocked transactions clearly show "plafond_exceeded" vs "insufficient_balance"
4. Wallet status bar shows green/yellow/orange — NEVER red/negative
5. Recommendations for insufficient_balance blocks suggest top-up, not plafond increase
6. No sanity check errors at end of run
