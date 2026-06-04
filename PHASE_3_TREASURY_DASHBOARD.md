# Phase 3 — Treasury Dashboard & Money Flow Simulation

## Context

Phase 2 validated the profit formulas (Layer 1 + Layer 2) with simulation data. The math works.

Phase 3 adds the **BALANCE layer** — tracking WHERE every MRU, USD, EUR, and USDT sits at every point in time. This is the treasury view: not just "did we make money?" but "where IS our money right now?"

The engine already computes profit. Now it must also compute **positions** — cash, receivables, bank balances, client float, agent balances — and show them evolving over time.

## The Accounting Equation

At every point in time, this MUST hold:

```
Assets = Liabilities + Equity

Where:
  Assets      = Cash_Caisses + Balance_Wallets + Balance_Banks + Receivables_Partners
  Liabilities = Client_Float + Agent_Payable
  Equity      = Working_Capital + Accumulated_Profit
```

If this equation doesn't balance, the engine has a bug. Display it on the dashboard. Always.

## What Already Exists (from Phase 2)

- `setup.html` — parameter configuration (partner, channel, settlement config)
- Engine computes: commission_a, cost_payout_a, fx_gain_a, profit_transaction_a per transaction
- Engine computes: gain_sett_s per settlement
- `dashboard.html` — currently shows profit summaries only
- Simulation data: 3 partners, 7 transactions, 1 settlement

## What to Build

### 1. Dual-Currency Balance Tracking

**Critical concept:** International partners operate in USD/EUR. Cadorim operates in MRU internally. Both views must exist in parallel.

For every international partner Par_l:

```python
# USD/EUR ledger (what the partner sees)
receivable_foreign_Par_l = sum(tx.Amount_j for tx in unsettled_txns[Par_l])
settled_foreign_Par_l    = sum(s.Amount_s for s in settlements[Par_l])

# MRU ledger (what Cadorim sees internally)
receivable_mru_Par_l     = sum(tx.Amount_mru_h for tx in unsettled_txns[Par_l])
settled_mru_Par_l        = sum(s.Amount_s * s.fx_settlement_rate for s in settlements[Par_l])
```

The dashboard shows BOTH columns side by side:
- "TerraPay owes us: **1,500 USD** (= 58,500 MRU at current rate)"
- "Ria owes us: **3,200 EUR** (= 140,800 MRU at current rate)"

### 2. Balance Positions (computed from transactions)

Every transaction moves money between positions. The engine tracks:

```python
# ASSET positions — Physical Cash (caisses)
Cash_Caisse = {
    "caisse_mboirick": Decimal,   # Physical cash held by Mboirick
    "caisse_tidjany": Decimal,    # Physical cash held by Tidjany
    "caisse_babe": Decimal,       # Physical cash held by Babe (BMI withdrawals)
}

# ASSET positions — Electronic Wallet Balances (Cadorim's own float at partners)
Balance_Wallet = {
    "sedad": Decimal,             # Cadorim's balance at Sedad
    "masrvi": Decimal,            # Cadorim's balance at Masrvi
    "bankily": Decimal,           # Cadorim's balance at Bankily
    "click": Decimal,             # Cadorim's balance at Click
}

# ASSET positions — Bank Accounts
Balance_Bank = {
    "bmi": Decimal,               # BMI bank balance (EUR/USD settlements)
}

# ASSET positions — Receivables (dual currency: foreign + MRU)
Receivable_Partner = {
    "terrapay": {"usd": Decimal, "mru": Decimal},  # Dual currency
    "ria": {"eur": Decimal, "mru": Decimal},
}

# LIABILITY positions
Client_Float = {
    "wallet_clients": Decimal,    # Total MRU held for wallet clients
    "b2c_clients": Decimal,       # Total MRU held for B2C (SNDP) clients
}

Agent_Balance = {
    "agent_x": Decimal,           # Net position per agent
}

# EQUITY
Working_Capital = Decimal("1000000")  # Initial injection: 1,000,000 MRU
Accumulated_Profit = Decimal("0")     # Sum of all Layer 1 + Layer 2 gains
```

### 3. Transaction Effects on Balances

Each transaction type affects positions differently. This is NOT special logic — it's derived from the transaction parameters:

```python
# PAYOUT CHANNEL TYPES — determines which balance pool is affected
# "caisse" channels: caisse_mboirick, caisse_tidjany, caisse_babe → Cash_Caisse
# "wallet" channels: sedad, click, masrvi, bankily → Balance_Wallet (Cadorim's float)
# "agent" channels: agent_caisse → Agent_Balance
# "internal": no cash movement

def get_payout_pool(channel_code):
    """Determine which balance pool a payout channel debits."""
    if channel_code.startswith("caisse_"):
        return "cash", channel_code
    elif channel_code in ("sedad", "click", "masrvi", "bankily",
                          "sim_sedad", "sim_click", "sim_masrvi", "sim_bankily"):
        return "wallet", channel_code.replace("sim_", "")
    elif "agent" in channel_code:
        return "agent", channel_code
    else:
        return "internal", None


def apply_transaction_to_balances(tx, balances):
    """Every transaction moves money. Track where."""
    pool_type, pool_key = get_payout_pool(tx.Local_Par_n)

    if tx.is_international:
        # INTERNATIONAL INBOUND (e.g. TerraPay sends USD, beneficiary gets MRU)
        # Step 1: Cadorim pays out MRU to beneficiary via Local_Par_n
        if pool_type == "cash":
            balances.cash[pool_key] -= tx.Amount_mru_h
        elif pool_type == "wallet":
            balances.wallet[pool_key] -= tx.Amount_mru_h
        elif pool_type == "agent":
            balances.agent_balance[pool_key] -= tx.Amount_mru_h
        # Step 2: Partner now owes us the foreign amount
        balances.receivable[tx.Par_l].foreign += tx.Amount_j
        balances.receivable[tx.Par_l].mru += tx.Amount_mru_h
        # Step 3: Profit accrues
        balances.accumulated_profit += tx.profit_transaction_a

    elif tx.is_wallet_p2p:
        # WALLET P2P: Client A → Client B. Float stays same.
        # No cash movement, no balance change. Just internal ledger.
        pass

    elif tx.is_wallet_cashout:
        # WALLET CASHOUT: Client withdraws via Local_Par_n
        if pool_type == "cash":
            balances.cash[pool_key] -= tx.Amount_mru_h
        elif pool_type == "wallet":
            balances.wallet[pool_key] -= tx.Amount_mru_h
        balances.client_float -= tx.Amount_mru_h   # Liability decreases
        balances.accumulated_profit += tx.profit_transaction_a

    elif tx.is_b2c_deposit:
        # B2C DEPOSIT (SNDP prefunds): Business sends MRU to Cadorim
        # Deposit arrives at a specific position (caisse or bank)
        if pool_type == "cash":
            balances.cash[pool_key] += tx.Amount_mru_h
        elif pool_type == "wallet":
            balances.wallet[pool_key] += tx.Amount_mru_h
        else:
            balances.cash[tx.receiving_caisse] += tx.Amount_mru_h
        balances.client_float += tx.Amount_mru_h    # Liability increases

    elif tx.is_b2c_payout:
        # B2C PAYOUT: SNDP pays salary to beneficiary via Local_Par_n
        if pool_type == "cash":
            balances.cash[pool_key] -= tx.Amount_mru_h
        elif pool_type == "wallet":
            balances.wallet[pool_key] -= tx.Amount_mru_h
        balances.client_float -= tx.Amount_mru_h
        balances.accumulated_profit += tx.profit_transaction_a

    elif tx.is_agent_cashout:
        # AGENT: Agent pays beneficiary cash, Cadorim owes agent
        balances.agent_balance[pool_key] -= tx.Amount_mru_h  # We owe agent
        balances.accumulated_profit += tx.profit_transaction_a

    elif tx.is_agent_refund:
        # AGENT REFUND: Cadorim repays agent from caisse
        balances.cash[tx.source_caisse] -= tx.Amount_mru_h
        balances.agent_balance[pool_key] += tx.Amount_mru_h  # Debt decreases


def apply_settlement_to_balances(settlement, balances):
    """Settlement: partner pays, receivable clears, bank increases."""
    par = settlement.Par_l
    bank = settlement.Bank_t

    # Foreign receivable decreases
    balances.receivable[par].foreign -= settlement.Amount_s
    # MRU equivalent cleared
    mru_received = settlement.Amount_s * settlement.fx_settlement_rate
    balances.receivable[par].mru -= settlement.Amount_s * settlement.fx_reference_rate
    # Bank balance increases
    balances.bank[bank] += mru_received
    # Layer 2 FX gain
    balances.accumulated_profit += settlement.gain_sett_s


def apply_bank_withdrawal(withdrawal, balances):
    """Withdrawal: bank → caisse. Asset rebalancing, no P&L."""
    balances.bank[withdrawal.bank] -= withdrawal.amount
    balances.cash[withdrawal.caisse] += withdrawal.amount
```

### 4. Expanded Simulation Data

Replace the simple 7-transaction simulation with a realistic 3-month scenario:

```python
# === SIMULATION CONFIGURATION ===

initial_working_capital = Decimal("1000000")  # 1,000,000 MRU

# Distribute across ALL positions (caisses + wallets + bank)
initial_cash = {
    "caisse_mboirick": Decimal("200000"),   # Physical cash
    "caisse_tidjany": Decimal("150000"),    # Physical cash
    "caisse_babe": Decimal("100000"),       # Physical cash (BMI withdrawal caisse)
}

initial_wallets = {
    "sedad": Decimal("150000"),             # Cadorim float at Sedad
    "masrvi": Decimal("80000"),             # Cadorim float at Masrvi
    "bankily": Decimal("50000"),            # Cadorim float at Bankily
    "click": Decimal("70000"),              # Cadorim float at Click
}

initial_banks = {
    "bmi": Decimal("200000"),               # BMI bank account
}

# Verify: 200k + 150k + 100k + 150k + 80k + 50k + 70k + 200k = 1,000,000 MRU

# === PARTNERS (Layer 1 config) ===

sim_partners = [
    # International
    {
        "code": "sim_terrapay",
        "name": "TerraPay (simulated)",
        "is_international": True,
        "currency": "USD",
        "commission_type": "percentage",
        "commission_rate": Decimal("0.005"),   # 0.5%
        "fx_partner_rate": Decimal("39.0"),
        "fx_cadorim_rate": Decimal("39.5"),
        "fx_market_rate": Decimal("39.2"),
        "channels": [
            {"code": "sim_sedad", "cost": Decimal("50"), "type": "fixed"},
            {"code": "sim_click", "cost": Decimal("30"), "type": "fixed"},
        ]
    },
    {
        "code": "sim_ria",
        "name": "Ria (simulated)",
        "is_international": True,
        "currency": "EUR",
        "commission_type": "percentage",
        "commission_rate": Decimal("0.01"),    # 1%
        "fx_partner_rate": Decimal("42.0"),
        "fx_cadorim_rate": Decimal("42.8"),
        "fx_market_rate": Decimal("42.5"),
        "channels": [
            {"code": "sim_agent_caisse", "cost": Decimal("30"), "type": "per_transaction"},
        ]
    },
    # Local wallet
    {
        "code": "sim_wallet",
        "name": "Cadorim Wallet (simulated)",
        "is_international": False,
        "currency": "MRU",
        "commission_type": "fixed",
        "commission_fixed": Decimal("0"),
        "channels": [
            {"code": "sim_internal", "cost": Decimal("0"), "type": "fixed"},
            {"code": "sim_sedad", "cost": Decimal("50"), "type": "fixed"},
        ]
    },
    # B2C (SNDP)
    {
        "code": "sim_sndp",
        "name": "SNDP (simulated B2C)",
        "is_international": False,
        "currency": "MRU",
        "commission_type": "percentage",
        "commission_rate": Decimal("0.002"),   # 0.2%
        "channels": [
            {"code": "sim_sedad", "cost": Decimal("50"), "type": "fixed"},
            {"code": "sim_agent_caisse", "cost": Decimal("30"), "type": "per_transaction"},
        ]
    },
    # Agent
    {
        "code": "sim_agent",
        "name": "Agent Operations (simulated)",
        "is_international": False,
        "currency": "MRU",
        "commission_type": "fixed",
        "commission_fixed": Decimal("0"),
        "channels": [
            {"code": "sim_agent_caisse", "cost": Decimal("30"), "type": "per_transaction"},
        ]
    },
]

# === SIMULATION TRANSACTIONS (50 transactions over 3 months) ===
# Designed to show realistic money flow patterns

sim_transactions = [
    # --- WEEK 1 (Jan 1-7): Initial activity ---

    # Day 1: TerraPay sends 3 transfers, paid via Sedad from Mboirick caisse
    {"id": "T001", "date": "2026-01-01", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 500, "Amount_mru_h": 19500, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T002", "date": "2026-01-01", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 800, "Amount_mru_h": 31200, "Local_Par_n": "sim_click",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T003", "date": "2026-01-02", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 1200, "Amount_mru_h": 46800, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_tidjany", "type": "international"},

    # Day 2: Ria sends 2 transfers, paid via agent from Tidjany caisse
    {"id": "T004", "date": "2026-01-02", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 300, "Amount_mru_h": 12840, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_tidjany", "type": "international"},
    {"id": "T005", "date": "2026-01-03", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 600, "Amount_mru_h": 25680, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_mboirick", "type": "international"},

    # Day 3: Wallet P2P (no cash impact) + Wallet cashout
    {"id": "T006", "date": "2026-01-03", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 5000, "Amount_mru_h": 5000, "Local_Par_n": "sim_internal",
     "caisse": "none", "type": "wallet_p2p"},
    {"id": "T007", "date": "2026-01-04", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 8000, "Amount_mru_h": 8000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_mboirick", "type": "wallet_cashout"},

    # Day 4: SNDP deposits 50,000 MRU (prefunding for salary payments)
    {"id": "T008", "date": "2026-01-05", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 50000, "Amount_mru_h": 50000, "Local_Par_n": "sim_internal",
     "caisse": "caisse_babe", "type": "b2c_deposit"},

    # Day 5: SNDP salary payouts (3 payments)
    {"id": "T009", "date": "2026-01-06", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 12000, "Amount_mru_h": 12000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_babe", "type": "b2c_payout"},
    {"id": "T010", "date": "2026-01-06", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 8000, "Amount_mru_h": 8000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_babe", "type": "b2c_payout"},
    {"id": "T011", "date": "2026-01-07", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 15000, "Amount_mru_h": 15000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_babe", "type": "b2c_payout"},

    # --- WEEK 2-3 (Jan 8-21): More volume + first settlement ---

    {"id": "T012", "date": "2026-01-08", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 2000, "Amount_mru_h": 78000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T013", "date": "2026-01-09", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 350, "Amount_mru_h": 13650, "Local_Par_n": "sim_click",
     "caisse": "caisse_tidjany", "type": "international"},
    {"id": "T014", "date": "2026-01-10", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 450, "Amount_mru_h": 19260, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_tidjany", "type": "international"},
    {"id": "T015", "date": "2026-01-11", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 700, "Amount_mru_h": 29960, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_mboirick", "type": "international"},

    # Agent cashouts (agents paying beneficiaries)
    {"id": "T016", "date": "2026-01-12", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 10000, "Amount_mru_h": 10000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "none", "type": "agent_cashout"},
    {"id": "T017", "date": "2026-01-13", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 15000, "Amount_mru_h": 15000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "none", "type": "agent_cashout"},

    # More wallet activity
    {"id": "T018", "date": "2026-01-14", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 3000, "Amount_mru_h": 3000, "Local_Par_n": "sim_internal",
     "caisse": "none", "type": "wallet_p2p"},
    {"id": "T019", "date": "2026-01-15", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 12000, "Amount_mru_h": 12000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_tidjany", "type": "wallet_cashout"},

    # More international
    {"id": "T020", "date": "2026-01-16", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 900, "Amount_mru_h": 35100, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T021", "date": "2026-01-17", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 500, "Amount_mru_h": 21400, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_tidjany", "type": "international"},

    # --- WEEK 4 (Jan 22-31): Settlements arrive, more activity ---

    {"id": "T022", "date": "2026-01-22", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 1500, "Amount_mru_h": 58500, "Local_Par_n": "sim_click",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T023", "date": "2026-01-23", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 750, "Amount_mru_h": 29250, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_tidjany", "type": "international"},

    # SNDP second batch deposit + payouts
    {"id": "T024", "date": "2026-01-25", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 40000, "Amount_mru_h": 40000, "Local_Par_n": "sim_internal",
     "caisse": "caisse_babe", "type": "b2c_deposit"},
    {"id": "T025", "date": "2026-01-26", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 10000, "Amount_mru_h": 10000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_babe", "type": "b2c_payout"},
    {"id": "T026", "date": "2026-01-27", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 20000, "Amount_mru_h": 20000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_babe", "type": "b2c_payout"},

    # Agent refund from caisse (Cadorim repays agent)
    {"id": "T027", "date": "2026-01-28", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 20000, "Amount_mru_h": 20000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_mboirick", "type": "agent_refund"},

    # --- FEBRUARY: More volume, second settlement, bank withdrawal ---

    {"id": "T028", "date": "2026-02-01", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 1800, "Amount_mru_h": 70200, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T029", "date": "2026-02-03", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 800, "Amount_mru_h": 34240, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_tidjany", "type": "international"},
    {"id": "T030", "date": "2026-02-05", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 600, "Amount_mru_h": 23400, "Local_Par_n": "sim_click",
     "caisse": "caisse_tidjany", "type": "international"},

    {"id": "T031", "date": "2026-02-07", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 7000, "Amount_mru_h": 7000, "Local_Par_n": "sim_internal",
     "caisse": "none", "type": "wallet_p2p"},
    {"id": "T032", "date": "2026-02-08", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 6000, "Amount_mru_h": 6000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_mboirick", "type": "wallet_cashout"},

    {"id": "T033", "date": "2026-02-10", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 550, "Amount_mru_h": 23540, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T034", "date": "2026-02-12", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 400, "Amount_mru_h": 15600, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_tidjany", "type": "international"},

    # More agent activity
    {"id": "T035", "date": "2026-02-14", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 8000, "Amount_mru_h": 8000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "none", "type": "agent_cashout"},
    {"id": "T036", "date": "2026-02-15", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 12000, "Amount_mru_h": 12000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_tidjany", "type": "agent_refund"},

    # --- MARCH: Third month, more settlements ---

    {"id": "T037", "date": "2026-03-01", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 2500, "Amount_mru_h": 97500, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T038", "date": "2026-03-03", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 900, "Amount_mru_h": 38520, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_tidjany", "type": "international"},
    {"id": "T039", "date": "2026-03-05", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 1100, "Amount_mru_h": 42900, "Local_Par_n": "sim_click",
     "caisse": "caisse_mboirick", "type": "international"},

    # SNDP third batch
    {"id": "T040", "date": "2026-03-06", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 60000, "Amount_mru_h": 60000, "Local_Par_n": "sim_internal",
     "caisse": "caisse_babe", "type": "b2c_deposit"},
    {"id": "T041", "date": "2026-03-07", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 18000, "Amount_mru_h": 18000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_babe", "type": "b2c_payout"},
    {"id": "T042", "date": "2026-03-08", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 22000, "Amount_mru_h": 22000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_babe", "type": "b2c_payout"},
    {"id": "T043", "date": "2026-03-09", "Par_l": "sim_sndp", "Cur_k": "MRU",
     "Amount_j": 10000, "Amount_mru_h": 10000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_babe", "type": "b2c_payout"},

    # Wallet
    {"id": "T044", "date": "2026-03-10", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 4000, "Amount_mru_h": 4000, "Local_Par_n": "sim_internal",
     "caisse": "none", "type": "wallet_p2p"},
    {"id": "T045", "date": "2026-03-12", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 9000, "Amount_mru_h": 9000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_tidjany", "type": "wallet_cashout"},

    # More international end of quarter
    {"id": "T046", "date": "2026-03-15", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 3000, "Amount_mru_h": 117000, "Local_Par_n": "sim_sedad",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T047", "date": "2026-03-18", "Par_l": "sim_ria", "Cur_k": "EUR",
     "Amount_j": 1000, "Amount_mru_h": 42800, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_mboirick", "type": "international"},
    {"id": "T048", "date": "2026-03-20", "Par_l": "sim_terrapay", "Cur_k": "USD",
     "Amount_j": 650, "Amount_mru_h": 25350, "Local_Par_n": "sim_click",
     "caisse": "caisse_tidjany", "type": "international"},

    # Final agent activity
    {"id": "T049", "date": "2026-03-22", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 5000, "Amount_mru_h": 5000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "none", "type": "agent_cashout"},
    {"id": "T050", "date": "2026-03-25", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 18000, "Amount_mru_h": 18000, "Local_Par_n": "sim_agent_caisse",
     "caisse": "caisse_mboirick", "type": "agent_refund"},
]

# === SETTLEMENTS (Layer 2 — independent timeline) ===

sim_settlements = [
    # TerraPay settles Week 1-2 batch (T001+T002+T003+T012+T013 = 4850 USD)
    {"id": "S001", "date_s": "2026-01-20", "Par_l": "sim_terrapay", "Bank_t": "sim_bmi",
     "Amount_s": 4850, "Cur_k": "USD",
     "fx_settlement_rate": Decimal("39.3"), "fx_reference_rate": Decimal("39.0")},

    # Ria settles January batch (T004+T005+T014+T015+T021 = 2550 EUR)
    {"id": "S002", "date_s": "2026-01-28", "Par_l": "sim_ria", "Bank_t": "sim_bmi",
     "Amount_s": 2550, "Cur_k": "EUR",
     "fx_settlement_rate": Decimal("42.6"), "fx_reference_rate": Decimal("42.0")},

    # TerraPay settles rest of Jan (T020+T022+T023 = 3150 USD)
    {"id": "S003", "date_s": "2026-02-05", "Par_l": "sim_terrapay", "Bank_t": "sim_bmi",
     "Amount_s": 3150, "Cur_k": "USD",
     "fx_settlement_rate": Decimal("39.4"), "fx_reference_rate": Decimal("39.0")},

    # TerraPay settles Feb batch (T028+T030+T034 = 2800 USD)
    {"id": "S004", "date_s": "2026-02-25", "Par_l": "sim_terrapay", "Bank_t": "sim_bmi",
     "Amount_s": 2800, "Cur_k": "USD",
     "fx_settlement_rate": Decimal("39.5"), "fx_reference_rate": Decimal("39.0")},

    # Ria settles Feb batch (T029+T033 = 1350 EUR)
    {"id": "S005", "date_s": "2026-03-01", "Par_l": "sim_ria", "Bank_t": "sim_bmi",
     "Amount_s": 1350, "Cur_k": "EUR",
     "fx_settlement_rate": Decimal("42.7"), "fx_reference_rate": Decimal("42.0")},

    # TerraPay settles Mar batch partial (T037+T039 = 3600 USD)
    {"id": "S006", "date_s": "2026-03-20", "Par_l": "sim_terrapay", "Bank_t": "sim_bmi",
     "Amount_s": 3600, "Cur_k": "USD",
     "fx_settlement_rate": Decimal("39.6"), "fx_reference_rate": Decimal("39.0")},
]

# === BANK WITHDRAWALS (bank → caisse, no P&L) ===

sim_withdrawals = [
    # Babe withdraws from BMI to fund caisses
    {"id": "W001", "date": "2026-01-25", "bank": "sim_bmi", "caisse": "caisse_babe",
     "amount": Decimal("80000")},
    {"id": "W002", "date": "2026-02-15", "bank": "sim_bmi", "caisse": "caisse_mboirick",
     "amount": Decimal("100000")},
    {"id": "W003", "date": "2026-03-10", "bank": "sim_bmi", "caisse": "caisse_tidjany",
     "amount": Decimal("60000")},
]
```

### 5. Dashboard Design

Update `dashboard.html` to show the treasury view. Same light theme as setup.html.

#### Top Row — Position Cards (always visible)

```
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  CASH (CAISSES) │ │  WALLET FLOAT   │ │  RECEIVABLES    │ │  BANK BALANCES  │ │  CLIENT FLOAT   │ │  AGENT BALANCE  │ │  PROFIT (P&L)   │
│   xxx,xxx MRU   │ │   xxx,xxx MRU   │ │ x,xxx USD       │ │   xxx,xxx MRU   │ │   xxx,xxx MRU   │ │   xxx,xxx MRU   │ │   xxx,xxx MRU   │
│  3 caisses      │ │  4 wallets      │ │ x,xxx EUR       │ │                 │ │                 │ │                 │ │  L1: xxx  L2: xx│
│  [ASSET]        │ │  [ASSET]        │ │ (xxx,xxx MRU)   │ │  [ASSET]        │ │  [LIABILITY]    │ │  [LIABILITY]    │ │  [EQUITY]       │
└─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘
```

#### Accounting Equation Bar (always visible, must balance)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  Assets (Cash+Wallets+Banks+Receivables): xxx,xxx  =  Liabilities (Clients+Agents): xxx,xxx  +  Equity (Capital+Profit): xxx,xxx    ✓ BALANCED  │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

If it doesn't balance, show ✗ IMBALANCED in red with the gap amount. This is the engine's self-check.

#### Section 1 — Cash Positions (drill-down)

```
CASH IN HAND — xxx,xxx MRU total
┌────────────────────┬──────────────┬──────────┬──────────┐
│ Caisse             │ Balance      │ In       │ Out      │
├────────────────────┼──────────────┼──────────┼──────────┤
│ Mboirick           │ xx,xxx MRU   │ xx,xxx   │ xx,xxx   │
│ Tidjany            │ xx,xxx MRU   │ xx,xxx   │ xx,xxx   │
│ Babe               │ xx,xxx MRU   │ xx,xxx   │ xx,xxx   │
└────────────────────┴──────────────┴──────────┴──────────┘
Click any caisse → see all transactions affecting it
```

#### Section 1b — Wallet Float (Cadorim's balance at electronic partners)

```
WALLET FLOAT — xxx,xxx MRU total (Cadorim's own balance at each partner)
┌────────────────────┬──────────────┬──────────┬──────────┐
│ Wallet Partner     │ Balance      │ In       │ Out      │
├────────────────────┼──────────────┼──────────┼──────────┤
│ Sedad              │ xxx,xxx MRU  │ xx,xxx   │ xx,xxx   │
│ Click              │ xx,xxx MRU   │ xx,xxx   │ xx,xxx   │
│ Masrvi             │ xx,xxx MRU   │ xx,xxx   │ xx,xxx   │
│ Bankily            │ xx,xxx MRU   │ xx,xxx   │ xx,xxx   │
└────────────────────┴──────────────┴──────────┴──────────┘
Click any wallet → see all transactions affecting it
Note: "Out" = payouts to beneficiaries via this channel. "In" = refunding/topping up Cadorim's float.
```

#### Section 2 — Receivables (dual-currency, drill-down)

```
RECEIVABLES BY PARTNER — DUAL CURRENCY VIEW
┌────────────────────┬──────────────┬──────────────┬──────────┬──────────┐
│ Partner            │ Foreign Owed │ MRU Equiv    │ Settled  │ Pending  │
├────────────────────┼──────────────┼──────────────┼──────────┼──────────┤
│ TerraPay           │ x,xxx USD    │ xxx,xxx MRU  │ x,xxx USD│ x,xxx USD│
│ Ria                │ x,xxx EUR    │ xxx,xxx MRU  │ x,xxx EUR│ x,xxx EUR│
│ TOTAL              │              │ xxx,xxx MRU  │          │          │
└────────────────────┴──────────────┴──────────────┴──────────┴──────────┘
Click partner → see every transaction creating receivable + every settlement clearing it
```

#### Section 3 — Bank Balances (drill-down)

```
BANK BALANCES
┌────────────────────┬──────────────┬──────────┬──────────┬──────────┐
│ Bank               │ Balance      │ In (sett)│ Out (wd) │ FX Gain  │
├────────────────────┼──────────────┼──────────┼──────────┼──────────┤
│ BMI                │ xxx,xxx MRU  │ xxx,xxx  │ xx,xxx   │ x,xxx    │
└────────────────────┴──────────────┴──────────┴──────────┴──────────┘
Click bank → see all settlements + withdrawals
```

#### Section 4 — Client Float & Agent Balances

```
CLIENT FLOAT (what we owe clients)
┌────────────────────┬──────────────┬──────────┬──────────┐
│ Type               │ Balance      │ Deposits │ Payouts  │
├────────────────────┼──────────────┼──────────┼──────────┤
│ Wallet Clients     │ xx,xxx MRU   │ xx,xxx   │ xx,xxx   │
│ SNDP (B2C)         │ xx,xxx MRU   │ xxx,xxx  │ xxx,xxx  │
└────────────────────┴──────────────┴──────────┴──────────┘

AGENT BALANCES (net position)
┌────────────────────┬──────────────┬──────────┬──────────┐
│ Agent              │ Net Balance  │ Cashouts │ Refunds  │
├────────────────────┼──────────────┼──────────┼──────────┤
│ Agent Pool         │ xx,xxx MRU   │ xx,xxx   │ xx,xxx   │
└────────────────────┴──────────────┴──────────┴──────────┘
```

#### Section 5 — P&L Summary

```
PROFIT & LOSS
┌────────────────────┬──────────────┬──────────┬──────────┬──────────┐
│ Source             │ Revenue      │ Cost     │ FX Gain  │ Net      │
├────────────────────┼──────────────┼──────────┼──────────┼──────────┤
│ Layer 1 (per txn)  │ xx,xxx MRU   │ x,xxx    │ xx,xxx   │ xx,xxx   │
│ Layer 2 (sett FX)  │              │          │ x,xxx    │ x,xxx    │
│ TOTAL              │              │          │          │ xx,xxx   │
└────────────────────┴──────────────┴──────────┴──────────┴──────────┘
```

#### Section 6 — Timeline Chart

A line chart (use Chart.js or similar) showing over the 3-month simulation:
- X-axis: dates
- Y-axis: MRU
- Lines: Cash/Caisses (green), Wallet Float (teal), Receivables MRU (orange), Bank Balance (blue), Client Float (red), Agent Balance (grey), Accumulated Profit (purple)
- Key events annotated: settlement arrivals, bank withdrawals, SNDP deposits

### 6. Build Sequence

1. Add simulation data (50 txns + 6 settlements + 3 withdrawals) to setup.html "Load Simulation" button
2. Build balance tracker engine in setup.html JavaScript (apply_transaction, apply_settlement, apply_withdrawal)
3. Verify accounting equation balances after every transaction
4. Build dashboard.html with all 6 sections + timeline chart
5. Link setup.html "Run Engine" → computes profit AND balances → dashboard.html reads results
6. Add drill-down (click any card/row to expand transactions)
7. Write self-check: if Assets ≠ Liabilities + Equity, show error with exact gap

### 7. ABSOLUTE RULES

1. Layer 1 and Layer 2 remain INDEPENDENT
2. All math uses Decimal (or integer cents). Never float.
3. Dual-currency: receivables tracked in BOTH foreign and MRU
4. Accounting equation MUST balance. Display it always. It's the engine's integrity check.
5. Every balance is DERIVED from transactions. No manual adjustments.
6. Same light theme as the redesigned setup.html (cream background, white cards, warm accents)
7. The dashboard reads data from the same engine — no separate data source
8. Drill-down available for every aggregate number
