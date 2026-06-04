# Claude Code Prompt — CEO Drill-Downs + Live Balance Across All Tabs

## Context

File: `~/cadorim-engine/engine.html`. The engine has 4 tabs: Setup, CEO, Treasury, Operations. After running the engine, dashboards populate with results.

## THE PROBLEM

1. **The Channel Liquidity Overview only shows INITIAL balances in the Setup tab.** After running the engine, the user has no way to see the POST-TRANSACTION wallet balances alongside the plafond usage EXCEPT by going to Treasury and clicking drill-downs. The live state of wallets should be visible from any tab after engine runs.

2. **The CEO tab has metric cards (Total Profit, Volume, Revenue, Net Position, Blocked) but they are FLAT.** The user sees "Net Position: 1,493,230" but cannot click on it to see WHERE the funds are — which caisses, which wallets, which bank, what receivables. The Treasury tab has this drill-down capability, but the CEO doesn't. A CEO needs to go from high-level to detail without switching tabs.

## WHAT TO BUILD

### Part 1: Make EVERY CEO card clickable with a drill-down

The CEO tab currently has these cards:
- Total Profit
- Volume (MRU)
- Revenue
- Net Position
- Blocked (if any)

Each card must become clickable (like the Treasury cards already are). Use the existing `toggle()` function and `drill` CSS class pattern that Treasury already uses.

#### Card: "Total Profit" → drill-down: P&L breakdown
```
Click → opens:
┌─────────────────────────────────────────────────────────────┐
│ P&L Breakdown                                               │
│                                                             │
│ Layer 1 (transaction level):                                │
│   Commission:        678 MRU                                │
│   Payout costs:     -1,650 MRU                              │
│   FX gain (L1):    13,665 MRU                               │
│   ─────────────────────────                                 │
│   L1 Profit:       12,483 MRU                               │
│                                                             │
│ Layer 2 (settlement level):                                 │
│   Settlement FX:    8,750 MRU                               │
│   ─────────────────────────                                 │
│   L2 Profit:        8,750 MRU                               │
│                                                             │
│ TOTAL PROFIT:      21,233 MRU                               │
│                                                             │
│ By Partner:                                                 │
│   terrapay    8,485  (1.21% margin)                         │
│   ria         4,428  (1.78% margin)                         │
│   sndp          190  (0.07% margin)                         │
│   wallet       -200  (-0.37% margin)                        │
│   agent        -210  (-0.24% margin)                        │
└─────────────────────────────────────────────────────────────┘
```

Use a table, not bullet points. Show the P&L structure clearly: L1 (comm - cost + fx) then L2 (settlement fx). Then partner breakdown with margin %.

#### Card: "Volume" → drill-down: volume by partner, by type, by month
```
Click → opens:
┌─────────────────────────────────────────────────────────────┐
│ Volume Breakdown                                            │
│                                                             │
│ By Partner:                                                 │
│   Partner     | Txns | Volume      | % of Total             │
│   terrapay    |   15 |   703,950   |   52%                  │
│   sndp        |   11 |   265,000   |   19%                  │
│   ria         |    9 |   248,240   |   18%                  │
│   agent       |    7 |    88,000   |    6%                  │
│   wallet      |    8 |    54,000   |    4%                  │
│                                                             │
│ By Flow Type:                                               │
│   international    |  24  |  952,190  |  70%                │
│   b2c              |  11  |  265,000  |  19%                │
│   agent            |   7  |   88,000  |   6%                │
│   wallet           |   8  |   54,000  |   4%                │
└─────────────────────────────────────────────────────────────┘
```

#### Card: "Revenue" → drill-down: revenue sources detail
```
Click → opens:
┌─────────────────────────────────────────────────────────────┐
│ Revenue Sources                                             │
│                                                             │
│ Source          | Amount   | % of Revenue                    │
│ FX L1 (spread) | 13,665   |   59%                           │
│ FX L2 (sett)   |  8,750   |   38%                           │
│ Commission     |    678   |    3%                            │
│ TOTAL          | 23,093   |  100%                            │
│                                                             │
│ FX Revenue by Partner:                                      │
│   terrapay  L1: 9,025  + L2: 6,275  = 15,300               │
│   ria       L1: 4,640  + L2: 2,475  =  7,115               │
│ Commission by Partner:                                      │
│   sndp        530                                           │
│   terrapay     90                                           │
│   ria          58                                           │
└─────────────────────────────────────────────────────────────┘
```

#### Card: "Net Position" → drill-down: WHERE ARE THE FUNDS

This is the most important one. The CEO clicks "Net Position: 1,493,230" and sees the full map of where every MRU sits:

```
Click → opens:
┌─────────────────────────────────────────────────────────────┐
│ Fund Distribution — Net Position: 1,493,230 MRU            │
│                                                             │
│ ASSETS (1,256,990 MRU):                                     │
│                                                             │
│  Cash (caisses): 790,000 MRU                                │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Caisse        │ Initial   │ Current   │ Change      │   │
│   │ caisse_babe   │  100,000  │  330,000  │ +230,000    │   │
│   │ caisse_mboirick│ 200,000  │  262,000  │  +62,000    │   │
│   │ caisse_tidjany│  150,000  │  198,000  │  +48,000    │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Wallet Float: -453,950 MRU                                 │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Wallet   │ Initial │ Current  │ Plafond │ Available │   │
│   │ sedad    │ 150,000 │  XX,XXX  │ 151,500 │   XX,XXX  │   │
│   │ click    │  70,000 │  XX,XXX  │  70,000 │   XX,XXX  │   │
│   │ masrvi   │  80,000 │  80,000  │  50,000 │   XX,XXX  │   │
│   │ bankily  │  50,000 │  50,000  │  30,000 │   XX,XXX  │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Bank: 694,150 MRU                                          │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Bank    │ Initial │ Sett In  │ WD Out  │ Current    │   │
│   │ sim_bmi │ 200,000 │ +734,150 │-240,000 │  694,150   │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Receivables: 226,790 MRU                                   │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Partner      │ Foreign    │ MRU     │ Currency      │   │
│   │ sim_terrapay │   3,650    │ 142,350 │ USD           │   │
│   │ sim_ria      │   1,900    │  84,440 │ EUR           │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│ LIABILITIES (-236,240 MRU):                                 │
│   Client Float:    50,000 MRU                               │
│   Agent Balance: -286,240 MRU                               │
│                                                             │
│ VISUAL: stacked horizontal bar showing proportion:          │
│ [████ Cash 63%██][░Wallet -36%░][████ Bank 55%████][██Recv 18%██]│
└─────────────────────────────────────────────────────────────┘
```

Key points for this drill-down:
- Show ALL asset categories with their sub-details (exact same data as Treasury drill-downs, but accessible from CEO tab)
- Wallet table includes a "Plafond" column showing total allocated and "Available" = min(current balance, remaining plafond allocation)
- Add a stacked bar at the top showing the proportion of each asset type visually
- Show liabilities at the bottom (client float + agent balance)
- Color code: green for healthy, yellow for low, red for negative

#### Card: "Blocked" → drill-down: blocked transaction detail with recommendations

Already specified in the previous prompt (PLAFOND_INTELLIGENCE_PROMPT.md). Make sure this drill-down also exists here. Show the full table:
| ID | Date | Partner | Channel | Amount | Actual Balance | Lost Profit | Recommendation |

### Part 2: Wallet Balance State Bar — visible across ALL dashboard tabs

After running the engine, add a PERSISTENT status bar at the top of CEO, Treasury, and Operations tabs. This bar shows the current state of all wallet channels in a compact format:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 💰 sedad: XX,XXX    click: XX,XXX    masrvi: 80,000    bankily: 50,000 │
│    [████░░]          [███░░░]          [██████]          [██████]       │
└─────────────────────────────────────────────────────────────────────────┘
```

Design:
- Horizontal strip, full width, light background (var(--surface-alt))
- Each wallet shown inline: name + current balance + mini bar showing usage vs. initial
- Bar fill: green if balance > 50% of initial, yellow if 10-50%, red if <10% or negative
- Compact: one line, small font (11px), always visible at the top of each dashboard tab
- Only appears AFTER engine has been run (hide when no results)

Implementation:
```javascript
function renderWalletBar() {
    if (!engineResults) return '';
    const bal = engineResults.balances;
    let h = '<div style="display:flex;gap:20px;align-items:center;padding:8px 16px;background:var(--surface-alt);border:1px solid var(--border);border-radius:var(--r);margin-bottom:14px;font-size:11px">';
    h += '<strong style="color:var(--muted)">Wallets:</strong>';
    for (const [k, v] of Object.entries(bal.wallet)) {
        const ini = engineResults.initial.wallet[k] || 1;
        const pct = Math.max(0, Math.min(100, v / ini * 100));
        const col = v < 0 ? 'var(--red)' : pct < 10 ? 'var(--red)' : pct < 50 ? 'var(--yellow)' : 'var(--green)';
        h += `<div style="display:flex;align-items:center;gap:6px">`;
        h += `<span>${k}</span>`;
        h += `<span style="font-weight:600;color:${col}">${fmt(v)}</span>`;
        h += `<div style="width:40px;height:6px;background:#eee;border-radius:3px;overflow:hidden"><div style="width:${Math.max(0,pct)}%;height:100%;background:${col}"></div></div>`;
        h += `</div>`;
    }
    h += '</div>';
    return h;
}
```

Insert this at the beginning of each dashboard build function:
- `buildCEO()`: insert after opening the page, before the cards
- `buildTreasury()`: insert after the equation bar, before alerts
- `buildOps()`: insert at the top, before plafond status

### Part 3: Clickable Receivables in the Net Position drill-down

When the user sees receivables in the Net Position drill-down, each partner row should be clickable to show:

```
sim_terrapay receivable: 3,650 USD (142,350 MRU)
  Settlements received:
    S001  2026-01-20  4,850 USD  → 190,605 MRU (gain: 1,455)
    S003  2026-02-05  3,150 USD  → 124,110 MRU (gain: 1,260)
    S004  2026-02-25  2,800 USD  → 110,600 MRU (gain: 1,400)
    S006  2026-03-20  3,600 USD  → 142,560 MRU (gain: 2,160)
  Total settled: 14,400 USD
  Still pending: 3,650 USD
  Average settlement time: ~15 days
```

This gives the CEO the full picture: how much was received, how much is still owed, and how fast settlements typically arrive.

### Part 4: Implementation details

#### Drill-down pattern (reuse existing)

The Treasury tab already has working drill-downs using:
```javascript
onclick="toggle('drill_id')"
// with:
<div id="drill_id" class="sec drill">...</div>
```

Use the SAME pattern for CEO drill-downs. Assign IDs:
- `ceo_profit` — Total Profit drill-down
- `ceo_volume` — Volume drill-down
- `ceo_revenue` — Revenue drill-down
- `ceo_netpos` — Net Position drill-down (the big one)
- `ceo_blocked` — Blocked transactions drill-down

Each card gets `onclick="toggle('ceo_xxx')"` and a cursor:pointer style.

#### Only one drill-down open at a time

The existing `toggle()` function already closes other drills when one opens. Make sure CEO drill-downs use the same behavior.

### Part 5: Style

- CEO cards: add `cursor:pointer` and subtle hover effect (already exists in .card:hover)
- Drill-downs: same `.sec.drill` pattern as Treasury
- Wallet status bar: subtle, compact, doesn't dominate — just an always-visible reference
- Net Position drill-down: use the same table styles as Treasury (thead, tbody, .n for numbers)
- Stacked bar for fund distribution: flex row with colored divs, height 24px, rounded corners, labels inside if wide enough
- No emojis — use text labels only
- All numbers: existing fmt() and f2()

### Part 6: DO NOT CHANGE

- Profit engine (computeL1, computeL2)
- Balance engine (applyTx, applySett, applyWd)
- Plafond gating logic (checkPlafond)
- Setup tab structure
- Existing Treasury drill-downs (they stay, CEO just gets its own set)
- Single HTML file, same CDN dependencies

### Part 7: Testing

1. Load simulation → Run Engine
2. **CEO tab**: click "Total Profit" → see L1/L2 breakdown + by partner
3. **CEO tab**: click "Net Position" → see full fund map: caisses, wallets (with plafond), bank, receivables, liabilities
4. **CEO tab**: click "Blocked" → see table with actual balance and recommendations
5. **CEO tab**: click "Revenue" → see FX vs commission split
6. **CEO tab**: click "Volume" → see by partner and by flow type
7. **Wallet bar** visible at top of CEO, Treasury, Operations — shows post-transaction balances with color-coded bars
8. **All drill-downs close when another opens** (same toggle behavior as Treasury)
9. **Receivables in Net Position** → click to see settlement history and pending amounts
