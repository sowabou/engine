# Phase 2 — Parameter Setup & Engine Validation

## Context

The Cadorim Engine v2 is already built (see cadorim_engine/ folder). It has:
- 10 DB models, classifier, mapper, FastAPI routes, dashboard HTML
- 18,225 production transactions classified into 12 flow types
- 54 tests passing

This phase adds the PARAMETER SETUP layer — the input that drives all profit computation. We validate with simulation data first, then plug in production data.

## What to Build

### 1. Partner Configuration Setup Page (HTML)

Build `setup.html` — an interactive configuration page where the user defines ALL parameters for each partner. This is the INPUT to the engine. Two fully independent sections:

#### Section A — Layer 1 Parameters (per transaction)

For each partner Par_l, the user fills:

```
Partner Definition:
  code:            string (e.g. "terrapay")
  name:            string (e.g. "TerraPay")
  is_international: bool   (true = FX applies, false = MRU only)
  currency:        Cur_k   (EUR, USD, USDC, MRU)
```
Commission function — commission(Par_l, Cur_k):
  commission_type:   "percentage" or "fixed"
  commission_rate:   Decimal (e.g. 0.005 for 0.5%)
  commission_fixed:  Decimal (e.g. 30.0 MRU)

FX function — per partner, per currency:
  fx_partner_rate:   Decimal  (rate the partner applies)
  fx_cadorim_rate:   Decimal  (rate Cadorim applies to beneficiary)
  fx_market_rate:    Decimal  (reference/market rate)
  NOTE: For local partners (MRU), all three = 0

Payout channels — Local_Par_n[] for this partner:
  Each channel has:
    local_partner_code:  string (e.g. "sedad", "click", "caisse_mboirick")
    cost_payout:         Decimal
    cost_payout_type:    "fixed" or "percentage" or "per_transaction"

#### Section B — Layer 2 Parameters (per settlement event, INDEPENDENT)

For each (Par_l, Bank_t) pair:

```
Settlement Definition:
  partner_code:     string
  bank_code:        string (e.g. "bmi", "eth_cado01")
  settlement_currency: Cur_k
  fx_settlement_rate:  Decimal (actual bank conversion rate)
  fx_reference_rate:   Decimal (expected/partner rate)
```
Layer 2 is completely independent from Layer 1. Different timeline, different data source. They share Par_l as a key but nothing else is coupled. Layer 2 can be empty while Layer 1 runs — the engine works with zero settlement data.

### 2. The Mathematical Formulas (implement exactly)

#### Layer 1 — fires for EVERY transaction_a

```python
# Input: transaction_a with (Amount_j, Cur_k, Par_l, Local_Par_n, Amount_mru_h)
# Parameters: loaded from setup config

def compute_layer1(tx, config):
    # Commission: what Cadorim earns
    pc = config.get_partner_currency(tx.Par_l, tx.Cur_k)
    if pc.commission_type == "percentage":
        commission_a = tx.Amount_j * pc.commission_rate
    else:
        commission_a = pc.commission_fixed

    # Payout cost: what Cadorim pays the channel
    pl = config.get_payout_cost(tx.Local_Par_n)
    if pl.cost_type == "percentage":
        cost_payout_a = tx.Amount_mru_h * pl.cost_payout
    elif pl.cost_type == "per_transaction":
        cost_payout_a = pl.cost_payout  # flat per txn
    else:
        cost_payout_a = pl.cost_payout  # fixed amount

    # FX gain: spread between partner rate and Cadorim rate
    # = 0 when Cur_k = MRU (local flows)
    fx_config = config.get_fx(tx.Par_l, tx.Cur_k, tx.date)
    if fx_config and fx_config.fx_cadorim_rate > 0:
        fx_gain_a = (fx_config.fx_cadorim_rate - fx_config.fx_partner_rate) * tx.Amount_j
    else:
        fx_gain_a = Decimal("0")
    # Gain and Profit
    gain_transaction_a = commission_a - cost_payout_a
    profit_transaction_a = gain_transaction_a + fx_gain_a

    return {
        "commission_a": commission_a,
        "cost_payout_a": cost_payout_a,
        "fx_gain_a": fx_gain_a,
        "gain_transaction_a": gain_transaction_a,
        "profit_transaction_a": profit_transaction_a,
    }
```

#### Layer 2 — fires for EACH settlement event (independent)

```python
# Input: settlement_s with (Par_l, Bank_t, Amount_s, Cur_k, date_s)
# Parameters: loaded from setup config (Section B)

def compute_layer2(settlement, config):
    sc = config.get_settlement(settlement.Par_l, settlement.Bank_t, settlement.date_s)
    gain_sett_s = (sc.fx_settlement_rate - sc.fx_reference_rate) * settlement.Amount_s
    return {"gain_sett_s": gain_sett_s}
```

#### Total Profit (two independent sums)

```python
total_profit = sum(tx.profit_transaction_a for tx in all_transactions) \
             + sum(s.gain_sett_s for s in all_settlements)
# The two sums are independent. You can have Layer 1 results with zero Layer 2.
```

#### Derived Balances

```python
Balance_Local_Par_n = sum(inflows to n) - sum(payouts from n)    # Layer 1 data
Receivable_Par_l    = sum(Amount_j where not yet settled)         # Layer 1 creates, Layer 2 clears
Balance_Bank_t      = sum(settlements to t) - sum(withdrawals)    # Layer 2 data
Payable_Local_Par_n = sum(Amount_mru_h where not yet paid)        # Layer 1 data
```
### 3. Simulation Data — Validate the Math First

Before touching production data, create simulation transactions with KNOWN expected results. This proves the formulas work correctly.

#### Simulation Partner Set

```python
simulation_partners = [
    {
        "code": "sim_international",
        "name": "Simulated International Partner",
        "is_international": True,
        "currency": "USD",
        "commission_type": "percentage",
        "commission_rate": 0.005,   # 0.5%
        "fx_partner_rate": 39.0,
        "fx_cadorim_rate": 39.5,    # Cadorim applies slightly higher
        "fx_market_rate": 39.2,
        "channels": [
            {"code": "sim_sedad", "cost_payout": 50, "cost_type": "fixed"},
            {"code": "sim_click", "cost_payout": 30, "cost_type": "fixed"},
        ],
        "settlement": {
            "bank": "sim_bmi",
            "currency": "USD",
            "fx_settlement_rate": 39.3,
            "fx_reference_rate": 39.0,
        }
    },
    {
        "code": "sim_wallet",
        "name": "Simulated Wallet (local P2P)",
        "is_international": False,
        "currency": "MRU",        "commission_type": "fixed",
        "commission_fixed": 0,        # No commission on P2P
        "fx_partner_rate": 0,
        "fx_cadorim_rate": 0,
        "fx_market_rate": 0,
        "channels": [
            {"code": "sim_internal", "cost_payout": 0, "cost_type": "fixed"},
        ],
        "settlement": None  # No Layer 2 for local
    },
    {
        "code": "sim_agent",
        "name": "Simulated Agent",
        "is_international": False,
        "currency": "MRU",
        "commission_type": "fixed",
        "commission_fixed": 0,
        "fx_partner_rate": 0,
        "fx_cadorim_rate": 0,
        "fx_market_rate": 0,
        "channels": [
            {"code": "sim_agent_caisse", "cost_payout": 30, "cost_type": "per_transaction"},
        ],
        "settlement": None
    }
]
```

#### Simulation Transactions (10 transactions, hand-calculable)

```python
simulation_transactions = [
    # --- International (sim_international) ---    # Tx 1: USD 1000 via sedad. Expected:
    #   commission = 1000 * 0.005 = 5.00 USD
    #   cost_payout = 50 MRU (fixed)
    #   fx_gain = (39.5 - 39.0) * 1000 = 500 MRU
    #   gain = 5.00 - 50 = -45.00 (in mixed currencies — engine must handle)
    #   profit = gain + fx_gain
    {"id": "SIM001", "Par_l": "sim_international", "Cur_k": "USD",
     "Amount_j": 1000, "Amount_mru_h": 39000, "Local_Par_n": "sim_sedad",
     "date": "2026-01-15"},

    # Tx 2: USD 500 via click
    #   commission = 500 * 0.005 = 2.50 USD
    #   cost_payout = 30 MRU (fixed)
    #   fx_gain = (39.5 - 39.0) * 500 = 250 MRU
    {"id": "SIM002", "Par_l": "sim_international", "Cur_k": "USD",
     "Amount_j": 500, "Amount_mru_h": 19500, "Local_Par_n": "sim_click",
     "date": "2026-01-15"},

    # Tx 3: USD 2000 via sedad (large transaction)
    {"id": "SIM003", "Par_l": "sim_international", "Cur_k": "USD",
     "Amount_j": 2000, "Amount_mru_h": 78000, "Local_Par_n": "sim_sedad",
     "date": "2026-02-01"},

    # --- Wallet P2P (sim_wallet) ---
    # Tx 4: internal P2P 5000 MRU. commission=0, cost=0, fx=0. Profit=0
    {"id": "SIM004", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 5000, "Amount_mru_h": 5000, "Local_Par_n": "sim_internal",
     "date": "2026-01-20"},

    # Tx 5: internal P2P 15000 MRU
    {"id": "SIM005", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 15000, "Amount_mru_h": 15000, "Local_Par_n": "sim_internal",
     "date": "2026-01-21"},
    # --- Agent (sim_agent) ---
    # Tx 6: agent cashout 8000 MRU. commission=0, cost=30 fixed. Profit=-30
    {"id": "SIM006", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 8000, "Amount_mru_h": 8000, "Local_Par_n": "sim_agent_caisse",
     "date": "2026-01-25"},

    # Tx 7: agent cashout 3000 MRU
    {"id": "SIM007", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 3000, "Amount_mru_h": 3000, "Local_Par_n": "sim_agent_caisse",
     "date": "2026-01-26"},
]

# Layer 2 simulation (independent — settlement arrives later)
simulation_settlements = [
    # Settlement for sim_international, arrived at sim_bmi
    # Amount: 3500 USD (covers Tx1+Tx2+Tx3 partially)
    # fx_settlement = 39.3, fx_reference = 39.0
    # gain_sett = (39.3 - 39.0) * 3500 = 1050 MRU
    {"id": "SETT001", "Par_l": "sim_international", "Bank_t": "sim_bmi",
     "Amount_s": 3500, "Cur_k": "USD", "date_s": "2026-02-15",
     "fx_settlement_rate": 39.3, "fx_reference_rate": 39.0},
]
```

#### Expected Simulation Results (hand-calculated)

```
LAYER 1 RESULTS:
  SIM001: commission=5.00 USD, cost=50 MRU, fx_gain=500 MRU
  SIM002: commission=2.50 USD, cost=30 MRU, fx_gain=250 MRU
  SIM003: commission=10.00 USD, cost=50 MRU, fx_gain=1000 MRU
  SIM004: commission=0, cost=0, fx_gain=0, profit=0
  SIM005: commission=0, cost=0, fx_gain=0, profit=0
  SIM006: commission=0, cost=30 MRU, fx_gain=0, profit=-30 MRU
  SIM007: commission=0, cost=30 MRU, fx_gain=0, profit=-30 MRU
LAYER 2 RESULTS (independent):
  SETT001: gain_sett = (39.3 - 39.0) * 3500 = 1050 MRU

TOTAL PROFIT = Sum(Layer1 profits) + 1050 MRU

BY PARTNER:
  sim_international: 3 txns, 3500 USD volume, Layer 1 + Layer 2
  sim_wallet: 2 txns, 20000 MRU volume, zero profit (internal)
  sim_agent: 2 txns, 11000 MRU volume, -60 MRU (pure cost)
```

### 4. Setup Page Requirements

The setup.html page must:

1. **Partner Configuration Table** — editable rows, one per partner:
   - Partner code, name, is_international flag
   - Currency
   - Commission type + rate/fixed
   - FX rates (partner, cadorim, market) — only editable if is_international=true
   - Add/remove partner rows dynamically

2. **Payout Channel Table** — per partner, editable:
   - Channel code, cost, cost type
   - Add/remove channels per partner

3. **Settlement Config Table** — independent section (Layer 2):
   - (Par_l, Bank_t) pairs with FX rates
   - Add/remove settlement configs
   - Clearly separated from Layer 1 — different section, different color

4. **Save Configuration** — exports to JSON file that the engine reads
   - `config.json` with two top-level keys: "layer1" and "layer2"
   - The engine loads this config and applies the formulas

5. **Run Engine Button** — triggers computation with current config
   - Shows results inline: per partner summary, per transaction detail
   - Highlights any mismatches vs expected values (for simulation)
6. **Drill-Down** — click any partner to see:
   - All transactions for that partner
   - Volume by channel (e.g. TerraPay: 800 via Sedad, 200 via Click, 60 via MauriPay)
   - Commission total, cost total, FX gain total, profit total
   - Each individual transaction with all computed fields

### 5. Engine Updates Needed

Update the existing engine code to:

1. **Read config from setup** — load `config.json` instead of hardcoded seed values
2. **Recompute Layer 1** for all engine_transactions using the loaded parameters
3. **Compute Layer 2** independently from settlement data + Layer 2 config
4. **Store both results** in separate tables (engine_transactions for L1, engine_settlements for L2)
5. **API endpoints** to serve both layers to the dashboard
6. **Dashboard update** — show Layer 1 results, Layer 2 results, and Total independently

### 6. Build Sequence

Step 1: Create simulation data + expected results as test fixtures
Step 2: Build the parameter config loader (reads config.json)
Step 3: Update engine formulas to use loaded config (not hardcoded)
Step 4: Run simulation — verify all 7 transactions + 1 settlement match expected
Step 5: Build setup.html with editable partner/channel/settlement tables
Step 6: Build drill-down per partner in dashboard
Step 7: Write tests for each formula with simulation data

### 7. ABSOLUTE RULES

1. Layer 1 and Layer 2 are INDEPENDENT. Never couple them.
2. All formulas use Decimal. Never float.
3. The setup page defines the parameters. The engine just applies math.
4. Every computed field traces back to: input data + config parameters.
5. The architecture is the reference — not the current DB structure.
6. Simulation validates the math BEFORE production data touches it.
7. No partner-specific logic. The formulas are universal.
