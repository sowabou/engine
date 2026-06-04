# Claude Code Prompt — Phase 1c: Make the production engine usable + resume Layer 2

## 1. MODE — AUTONOMOUS, NEVER STOP, NEVER ASK

Run this task end-to-end without interactive confirmation. Strict rules:

- **Never ask the user for permission.** Do not pause on "Do you want to proceed?" or "Contains brace with quote character" prompts. If a CLI offers a choice, pick the safe default and continue. If a shell command is rejected by a safety warning, rewrite it without braces/quotes and re-run.
- **Never halt on a single failure.** Catch, log, patch, retry up to 5 times per sub-task, then tag AMBER on that sub-task only and move on.
- **Full write permission** is granted for `~/cadorim-engine/`, `~/Documents/Claude/Projects/Cadorim Accounting/`, and `/tmp/`. Write freely.
- **No interactive Python.** Every script runs unattended. No `input()` calls.
- **macOS sandbox errors** when reading `~/Documents/Claude/Projects/Cadorim Accounting/`: try `cat`/`find`/`ls` first; if denied, log the path to `~/cadorim-engine/SANDBOX_GAPS.md` and continue.
- **Final report only.** One `PHASE_1C_REPORT.md` at the end — no mid-flight status updates.

---

## 2. CONTEXT — where we are after the overnight Phase 1b run

- **Layer 1 GREEN**: `data/production_data_all.json` has 15,382 transactions, Jan 2025 → Apr 2026, across 7 partners + ancillary + treasury. 110/110 tests pass. 0.1% unclassified. Engine toggle works (Sim / Ria / All Partners).
- **Layer 2 AMBER**: all 4 international partners have empty settlements (sandbox blocked source files).

**Problems surfaced this morning when loading All Partners in the browser:**

1. **Chrome freezes** ("Page Unresponsive") on the Operations tab — 15,382 `<tr>` rows rendered synchronously.
2. **PENDING = 1,971 transactions (24M MRU)**, **Released = 0** — the engine's double-gate (plafond + wallet) blocks nearly everything because wallet opening balances are all 0 and no plafond config exists for real partners.
3. **Only Ria shows profit** on the CEO dashboard; bridge/terrapay/wallet/agent bars are flat.

Phase 1c fixes these, then resumes Layer 2.

---

## 3. FIX ORDER — start with browser freeze so user has a usable UI within minutes

### FIX 1 — Operations tab virtualization (FIRST — kills the freeze)

In `engine.html`, find `renderOperations()` (or wherever the Operations `<tbody>` is populated from `SIM_TXS.forEach`). Replace with paginated render:

```javascript
const OPS_PAGE_SIZE = 200;
let opsOffset = 0;
let opsFilters = { partner: 'all', category: 'all', from: null, to: null };

function filteredOps() {
    return SIM_TXS.filter(tx => {
        if (opsFilters.partner !== 'all' && tx.Par_l !== opsFilters.partner) return false;
        if (opsFilters.category !== 'all' && tx.flow_category !== opsFilters.category) return false;
        if (opsFilters.from && tx.created_at < opsFilters.from) return false;
        if (opsFilters.to && tx.created_at > opsFilters.to) return false;
        return true;
    });
}

function renderOperations() {
    const all = filteredOps();
    const page = all.slice(opsOffset, opsOffset + OPS_PAGE_SIZE);
    const frag = document.createDocumentFragment();
    page.forEach(tx => frag.appendChild(buildOpsRow(tx)));
    const body = document.querySelector('#ops-tbody');
    body.replaceChildren(frag);
    document.querySelector('#ops-footer').textContent =
        `Showing ${opsOffset+1}–${opsOffset+page.length} of ${all.length}`;
}
```

Add above the table:

```html
<div class="ops-filter-bar">
    <select id="ops-partner"><option value="all">All partners</option>...</select>
    <select id="ops-category">
        <option value="all">All</option>
        <option value="revenue">Revenue only</option>
        <option value="internal">Internal</option>
        <option value="ancillary">Ancillary</option>
    </select>
    <input type="date" id="ops-from"> <input type="date" id="ops-to">
    <button id="ops-prev">◀ Prev</button>
    <button id="ops-next">Next ▶</button>
</div>
```

Apply the same pattern to the **Positions** tab's per-partner ledger (paginate per partner, not global).

**Acceptance:** Loading All Partners no longer triggers Page Unresponsive. Operations first render < 1s.

### FIX 2 — Real opening balances for wallets and caisses at 2025-01-01

Currently `cadorim_engine/opening.py` returns zeros, which is why every transaction gets gate-blocked. Replace with real replay:

```python
def compute_opening(sqlite_path, cutoff_date='2025-01-01'):
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    # Load accounts to classify
    accounts = {int(r['id']): dict(r) for r in conn.execute(
        "SELECT id, name, type FROM accounts"
    )}

    def net_at(account_id):
        """Net balance at cutoff = sum(credits) - sum(debits) for completed txns."""
        credits = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions "
            "WHERE creditable_id=? AND creditable_type LIKE '%Account%' "
            "AND status='completed' AND created_at < ?",
            (account_id, cutoff_date)
        ).fetchone()[0]
        debits = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions "
            "WHERE debitable_id=? AND debitable_type LIKE '%Account%' "
            "AND status='completed' AND created_at < ?",
            (account_id, cutoff_date)
        ).fetchone()[0]
        return max(0.0, float(credits) - float(debits))

    cash, wallet = {}, {}

    # Wallet accounts — Sedad(16), Masrivi(21), and any main with matching name
    WALLET_MAP = {16: 'sedad', 21: 'masrvi'}
    for acct in accounts.values():
        if acct['type'] == 'main':
            name_lower = (acct['name'] or '').lower()
            if 'bankily' in name_lower:
                WALLET_MAP[acct['id']] = 'bankily'
            elif 'click' in name_lower:
                WALLET_MAP[acct['id']] = 'click'
            elif 'mauripay' in name_lower:
                WALLET_MAP[acct['id']] = 'mauripay'
    for aid, code in WALLET_MAP.items():
        wallet[code] = round(net_at(aid), 2)

    # Caisses
    for acct in accounts.values():
        if acct['type'] == 'cash':
            slug = 'caisse_' + re.sub(r'[^a-z0-9]+', '_', acct['name'].lower()).strip('_')
            bal = net_at(acct['id'])
            if bal > 0:
                cash[slug] = round(bal, 2)

    # Existing international partner receivables (keep as-is)
    opening_receivable = compute_international_receivables(conn, cutoff_date)

    # SNDP prefunding
    sndp_in = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions "
        "WHERE type='virement_interne' AND creditable_id=501 "
        "AND status='completed' AND created_at < ?", (cutoff_date,)
    ).fetchone()[0]
    sndp_out = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions "
        "WHERE type='retrait_commande' AND status='completed' AND created_at < ?",
        (cutoff_date,)
    ).fetchone()[0]

    conn.close()

    return {
        "cash": cash,
        "wallet": wallet,
        "bank": {"bmi": 0, "bpm": 0, "bred": 0, "eth_cado01": 0, "eth_cado02": 0},
        "client_float": 0,  # TODO Phase 2
        "opening_receivable": opening_receivable,
        "opening_prefunding": {"sndp": max(0, float(sndp_in) - float(sndp_out))},
    }
```

Print all computed balances during export so the log shows what was set.

### FIX 3 — Auto-generate plafond rules from historical throughput

Add `cadorim_engine/plafond_generator.py`:

```python
from collections import defaultdict
import statistics

PRIORITY = {'ria': 1, 'terrapay': 1, 'bridge': 1, 'juba': 2, 'sndp': 2, 'wallet': 3, 'agent': 4}

def generate_plafonds(events):
    """Derive Plafond(Par_l, Local_Par_n) caps from monthly p95 throughput."""
    by_pair_month = defaultdict(lambda: defaultdict(float))
    for e in events:
        if e.get('flow_category') != 'revenue':
            continue
        par, chan = e.get('Par_l'), e.get('Local_Par_n')
        if not par or not chan:
            continue
        month = (e.get('created_at') or '')[:7]  # YYYY-MM
        by_pair_month[(par, chan)][month] += float(e.get('Amount_mru_h') or 0)

    rules = []
    for (par, chan), monthly in by_pair_month.items():
        volumes = sorted(monthly.values())
        if not volumes:
            continue
        # p95 with 10% headroom, minimum cap 100k MRU for safety
        idx = int(len(volumes) * 0.95)
        p95 = volumes[min(idx, len(volumes)-1)]
        cap = max(100_000.0, p95 * 1.1)
        rules.append({
            "partner_code": par,
            "channel_code": chan,
            "cap_mru": round(cap, 2),
            "priority": PRIORITY.get(par, 5),
        })
    return rules
```

Call this from `load_production.py` after events are classified; inject into `config.plafonds`.

Unit-test in `tests/test_plafond_generator.py` (3 cases: normal partner, empty partner, multi-month).

**Acceptance:** PENDING drops below **5% of total** after regenerating the JSON and reloading. Every partner has at least one plafond rule.

### FIX 4 — Resume Layer 2 (settlements)

Try the source folder first; fall back to the staging folder user may have created.

```python
SETTLEMENT_ROOTS = [
    Path.home() / "Documents" / "Claude" / "Projects" / "Cadorim Accounting",
    Path.home() / "cadorim-engine" / "data" / "settlements",
]

def find_settlement_files(partner):
    """Return list of candidate source files for a partner, from any accessible root."""
    patterns = {
        'ria':     ['*SWIFT*', '*Wire*', '*CorrespPayment*', '*BMI*'],
        'terrapay':['*terrapay*', '*TerraPay*'],
        'bridge':  ['*Bridge*', '*BRED*'],
        'juba':    ['*Juba*', '*BPM*'],
    }
    hits = []
    for root in SETTLEMENT_ROOTS:
        if not root.exists():
            continue
        try:
            for pat in patterns.get(partner, []):
                hits.extend(root.rglob(pat))
        except PermissionError as e:
            log_sandbox_gap(root, str(e))
    return hits
```

Build parsers in `cadorim_engine/settlements/`:

- `bmi_parser.py` — reads BMI bank statement files (PDF/Excel/CSV). Use `pdfplumber` for PDFs, `openpyxl` for xlsx, `csv` for csv. Extract (date, amount_eur, reference, counterparty="Ria") for each credit line.
- `ria_mail_parser.py` — parses SWIFT (MT103), Wire notif, CorrespPayment Excel. Reuse patterns from the ria-accounting skill if staged.
- `bpm_parser.py` — best-effort for Juba (user said it's small, stub OK).

### FIX 5 — ETH settlements WITHOUT Etherscan API key

User does not have an Etherscan API key yet, but has the addresses. Use **public Ethereum JSON-RPC** (no key needed) to query USDC Transfer events directly.

Create `cadorim_engine/settlements/eth_rpc_client.py`:

```python
"""Query USDC/USDT Transfer events via public Ethereum RPC — no API key needed."""
import json, requests
from datetime import datetime

USDC_CONTRACT = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
USDT_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
EURC_CONTRACT = "0x1abaea1f7c830bd89acc67ec4af516284b1bc33c"

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

PUBLIC_RPCS = [
    "https://ethereum.publicnode.com",
    "https://cloudflare-eth.com",
    "https://rpc.ankr.com/eth",
    "https://eth.llamarpc.com",
]

def _pad_address(addr):
    return "0x" + addr.lower().replace("0x", "").rjust(64, "0")

def _rpc_call(method, params):
    """Try public RPCs in order until one responds."""
    for url in PUBLIC_RPCS:
        try:
            r = requests.post(url, json={
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params
            }, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if "result" in data:
                    return data["result"]
        except Exception:
            continue
    raise RuntimeError(f"All public RPCs failed for {method}")

def block_for_date(ts_iso):
    """Approximate block number for a UTC date using binary search on timestamps."""
    # ~12s avg block time; rough estimate suffices, refine at extremes
    target_ts = int(datetime.fromisoformat(ts_iso).timestamp())
    latest = int(_rpc_call("eth_blockNumber", []), 16)
    latest_ts = int(_rpc_call("eth_getBlockByNumber",
        [hex(latest), False])["timestamp"], 16)
    # Linear estimate
    seconds_per_block = 12.05
    blocks_ago = (latest_ts - target_ts) / seconds_per_block
    return max(0, int(latest - blocks_ago))

def fetch_transfers(token_contract, to_address, from_block, to_block, from_filter=None):
    """
    Fetch ERC-20 Transfer events for the token where 'to' matches the address.
    Optionally filter by 'from' address (list).
    Uses eth_getLogs in chunks of 10k blocks to stay under RPC limits.
    """
    results = []
    chunk = 10_000
    b = from_block
    while b <= to_block:
        end = min(b + chunk - 1, to_block)
        topics = [TRANSFER_TOPIC, None, _pad_address(to_address)]
        if from_filter:
            topics[1] = [_pad_address(a) for a in from_filter] if len(from_filter) > 1 else _pad_address(from_filter[0])
        logs = _rpc_call("eth_getLogs", [{
            "address": token_contract,
            "fromBlock": hex(b), "toBlock": hex(end),
            "topics": topics,
        }])
        for log in logs or []:
            # Transfer: data = amount (uint256, USDC=6 decimals, USDT=6, EURC=6)
            amount_raw = int(log["data"], 16)
            amount = amount_raw / 1_000_000
            tx_hash = log["transactionHash"]
            block_num = int(log["blockNumber"], 16)
            # Fetch block for timestamp (cache this if many logs share blocks)
            blk = _rpc_call("eth_getBlockByNumber", [hex(block_num), False])
            ts = datetime.utcfromtimestamp(int(blk["timestamp"], 16)).isoformat()
            from_addr = "0x" + log["topics"][1][-40:]
            results.append({
                "tx_hash": tx_hash, "block": block_num, "timestamp": ts,
                "from": from_addr, "amount": amount,
            })
        b = end + 1
    return results
```

**Getting the addresses:** Read from `~/cadorim-engine/.env` first (format `CADO01_ADDRESS=0x...`, `CADO02_ADDRESS=0x...`). If missing, search for them in:

1. Memory files: `~/Library/Application Support/Claude/local-agent-mode-sessions/*/spaces/*/memory/*.md` — grep for `Cado01`, `Cado02`, TerraPay addresses (`0x3C9fB156`, `0x8195d349`), Mboirick (`0x271e`).
2. Project folder: `~/Documents/Claude/Projects/Cadorim Accounting/` — grep for `0x` addresses.
3. Existing CLAUDE.md and memory content mentioned in the prompt's context.

If the Cado01 or Cado02 addresses cannot be resolved, log to `LAYER2_DISCOVERY.md` with a TODO for the user and proceed with empty ETH settlements for that partner — do not fail the run.

**Wrapping eth_rpc_client into settlement events:**

```python
def fetch_terrapay_settlements(cutoff_start, cutoff_end):
    cado02 = resolve_address('CADO02')
    if not cado02:
        log_discovery('terrapay', 'Cado02 address not resolved')
        return []
    terrapay_sources = [
        '0x3C9fB156...', '0x8195d349...',  # fill from memory lookup
    ]
    from_block = block_for_date(cutoff_start)
    to_block = block_for_date(cutoff_end)
    transfers = fetch_transfers(USDC_CONTRACT, cado02, from_block, to_block,
                                from_filter=terrapay_sources)
    events = []
    for i, t in enumerate(transfers, 1):
        events.append({
            "id": f"S-terrapay-{i}",
            "partner_code": "terrapay",
            "date": t["timestamp"][:10],
            "amount_foreign": round(t["amount"], 2),
            "currency": "USDC",
            "bank_code": "eth_cado02",
            "fx_rate_settlement": 39.0,
            "amount_mru": round(t["amount"] * 39.0, 2),
            "reference": t["tx_hash"],
            "source": "eth_rpc",
            "source_file": f"public-rpc:{t['block']}",
        })
    return events
```

Do the same for **Bridge → Cado01** (USDC/USDT/EURC inbound to Cado01 address). Accept whichever token shows volume.

### Canonical settlement shape (fed into `data/production_data_all.json`'s `settlements: []`)

```python
{
    "id": "S-<partner>-<N>",
    "partner_code": "ria" | "terrapay" | "juba" | "bridge",
    "date": "YYYY-MM-DD",
    "amount_foreign": 12345.67,
    "currency": "EUR" | "USD" | "USDC",
    "bank_code": "bmi" | "bpm" | "bred" | "eth_cado01" | "eth_cado02",
    "fx_rate_settlement": 42.5,
    "amount_mru": 524_823,
    "reference": "<SWIFT ref or tx_hash>",
    "source": "bmi_statement" | "swift" | "wire" | "excel" | "eth_rpc",
    "source_file": "<path or rpc:block>",
}
```

---

## 4. SELF-HEALING AUDIT LOOP

Extend `tools/audit_export.py` with these checks (added to the Phase 1b checks):

11. **Pending ratio**: `pending_count / total_revenue_txns < 5%` after plafond fix.
12. **Wallet opening non-zero**: at least Sedad and Masrivi have `opening.wallet[...] > 0` (else document reason).
13. **Plafond coverage**: every `(Par_l, Local_Par_n)` pair with revenue volume has a plafond rule.
14. **Layer 2 presence**: ≥ 2 of 4 international partners have non-empty settlements.
15. **Receivable compression**: for Ria, end-of-window open receivable < 50% of cumulative Layer 1 receivable.
16. **ETH RPC sanity**: if Cado02 transfers fetched, at least one matches a known TerraPay source address.

After each export, run audit → diagnose → patch → re-export. Max **5 iterations**. Log to `AUDIT_LOG.md` (append).

---

## 5. FINAL REPORT — `~/cadorim-engine/PHASE_1C_REPORT.md`

One file, read-once over coffee. Structure:

```markdown
# Phase 1c Report — <timestamp>
## STATUS: GREEN | AMBER

## Headline
- Browser freeze on All Partners: FIXED / NOT FIXED
- PENDING ratio: 14.7% → X%
- Released transactions: 0 → N
- Layer 2 settlements: M across K partners
- Total profit (L1 + L2) full window: MRU
- Total profit Q1 2026: MRU
- Open receivable end-of-window: before Y → after Z (compression: W%)

## Per-partner Q1 2026 snapshot
| Partner | Events | L1 profit | L2 settlements | L2 FX gain | Open receivable EoQ |
(7 partners populated)

## Fixes applied
1. Operations virtualization — PAGE_SIZE=200, filter bar, pagination
2. Opening balances — Sedad: X, Masrvi: Y, Bankily: Z, caisses: {...}
3. Plafond auto-discovery — N rules across M partners
4. Layer 2 — Ria: <count via BMI/SWIFT>, TerraPay: <count via ETH RPC>, Bridge: <count or TODO>, Juba: <count or stub>

## Acceptance
- [x/ ] No browser freeze
- [x/ ] PENDING < 5%
- [x/ ] Released > 0
- [x/ ] 5+ partners show profit on CEO
- [x/ ] Layer 2 ≥ 2 partners
- [x/ ] All tests pass

## Files changed
(list with line counts)

## Outstanding for Dr. Neine
- ETH addresses unresolved: <list or none>
- Layer 2 parsers that AMBER'd: <list with reason>
- Any other manual action needed
```

---

## 6. HARD ACCEPTANCE CRITERIA

1. Loading "All Partners" does NOT trigger Page Unresponsive.
2. CEO tab shows non-zero profit for **at least 5 of 7 partners**.
3. PENDING < 5% of total transactions.
4. Released > 0.
5. Wallet opening balances non-zero where historical data exists before 2025-01-01 (else documented).
6. Layer 2 settlements present for **at least 2 of 4 international partners** (Ria from BMI/mails + TerraPay from ETH RPC is the minimum target).
7. All existing tests pass; new tests (plafond_generator, opening_balances, eth_rpc_client mock) pass.
8. `PHASE_1C_REPORT.md` delivered.

---

## 7. DO NOT

- Do not stop for user confirmation.
- Do not use Etherscan API (user has no key) — use public Ethereum RPC only.
- Do not invent ETH addresses or IBANs. Log unresolved to `LAYER2_DISCOVERY.md`.
- Do not modify engine math (`computeL1/L2`, `applyTx`, `applySett`, `applyWd`).
- Do not touch the Simulation path.
- Do not mock data to pass the audit.
- Do not break Phase 1b's all-partners JSON shape — only extend.

---

## GO

Start with **FIX 1** (virtualization) so the user has a usable browser within 5 minutes. Then FIX 2, FIX 3, FIX 4, FIX 5 in order. Run the full audit loop. Write the final report. End.
