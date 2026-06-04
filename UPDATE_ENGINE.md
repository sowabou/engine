## Engine Update — Handle ALL Cadorim Business Flows

The engine needs to be updated to handle ALL Cadorim business flows, not just international remittance. The universal model covers everything — some parameters go to zero but the structure never changes.

### What changed in understanding

The production data has 4 partner types: "terrapay", "cadorim (internal)", "cadorim-agent", "mauripay". They map to 5 business flows that ALL use the same universal function:

1. International Remittance (terrapay, ria, juba): Full model — FX > 0, Layer 1 + Layer 2
2. Cadorim Wallet / national P2P (mauripay): MRU to MRU, FX=0. Two sub-types:
   - Type A (internal): wallet to wallet, stays in system, cost_payout=0
   - Type B (cashout): wallet to external Local_Par_n or Agent, cost_payout >= 0
3. CadorimPay / B2C (cadorim internal): Business deposits (prefunding), then pays internal or external
4. Agent operations (cadorim-agent): Agents cashout for all flows, earn fees (=our cost). Agents can also send to any wallet client or other agent — same as Flow 2.
5. Treasury: Balance transfers + expense payments (salary, electricity). Cost only, no revenue.

KEY INSIGHT: Any sender (wallet client, B2C business, agent) can send to ANY destination (wallet client, agent, external Local_Par_n). The engine does not need to know which flow — it just reads the parameters.

### Updates needed

#### 1. Update seed data — add missing partners to Par_l registry

Add to partners seed:

- code: "cadorim_wallet", name: "Cadorim Wallet (MauriPay)"
- code: "cadorim_b2c", name: "CadorimPay (B2C)"
- code: "cadorim_agent", name: "Cadorim Agent Network"
- code: "treasury", name: "Treasury / Internal"

#### 2. Update partner_currencies config — MRU flows have no FX

- partner: "cadorim_wallet", currency: "MRU", commission_rate: 0.0, commission_type: "percentage"
- partner: "cadorim_b2c", currency: "MRU", commission_rate: 0.0, commission_type: "percentage"
- partner: "cadorim_agent", currency: "MRU", commission_rate: 0.0, commission_type: "percentage"
- partner: "treasury", currency: "MRU", commission_rate: 0.0, commission_type: "percentage"

#### 3. Update Local_Par_n registry — add internal wallet and agents

Add to local_partners seed:

- code: "wallet_internal", name: "Internal Wallet Transfer", type: "wallet"
- Discover actual agent names from production data and add them

#### 4. Update the mapper to handle all partner types from production data

The mapper needs to:
- Map "terrapay" to partner "terrapay"
- Map "mauripay" to partner "cadorim_wallet"
- Map "cadorim (internal)" to partner "cadorim_b2c" or "cadorim_wallet" (inspect the data to determine which)
- Map "cadorim-agent" to partner "cadorim_agent"
- For wallet-to-wallet (Type A): set Local_Par_n = "wallet_internal", cost_payout = 0
- For cashout (Type B): set Local_Par_n = actual channel (sedad, click, agent, etc.)

#### 5. Update the data loader script

Reload all 4,623 orders with correct partner mapping and recompute all Layer 1 fields. Then print:

- Summary by FLOW TYPE (international vs wallet vs B2C vs agent vs treasury)
- Volume and profit breakdown
- Which transactions are internal (Type A, no payout cost) vs external (Type B, with cost)
- Agent fee totals (our cost_payout for agent cashouts)

#### 6. Rebuild the HTML dashboard

Rebuild dashboard.html with the corrected data showing:
- Transactions by flow type (international / wallet / B2C / agent / treasury)
- Revenue breakdown: commission + FX gain (international) vs fees (wallet/B2C) vs cost only (treasury)
- Payout distribution: internal (wallet-to-wallet) vs external (Sedad, Click, agents, etc.)
- Local partner balances
- Receivables (international partners only)

The algebra is the same. compute_commission, compute_payout_cost, compute_fx_gain all work unchanged. The parameters just need to be set correctly for each flow.
