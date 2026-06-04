# Q1 2026 Partner Balances — Layer 1 + Layer 2

Generated: 2026-04-20 | Scope: 2026-01-01 → 2026-03-31

## Ria
- Q1 Layer 1 volume: 526,719 EUR (22,385,555 MRU at FX 42.5)
- Q1 Layer 1 events: 2,885 transactions
- Q1 Layer 1 commission: ~72,125 MRU (avg 25 MRU/txn)
- Q1 Layer 2 settlements: **0** (SWIFT emails available but parsing deferred)
- Open receivable (growing): ~898K EUR cumulative
- Reconciliation: 0% (Layer 2 Ria pending)

## TerraPay
- Q1 Layer 1 volume: 174,721 USD (6,814,134 MRU)
- Q1 Layer 1 events: 777 transactions
- Q1 Layer 1 commission: ~873 USD (0.5%)
- **Q1 Layer 2 settlements: 35 settlements, 477,100 USDC (18,606,902 MRU)**
- Bank: eth_cado02
- Reconciliation: 477,100 / 174,721 = **273%** (settlements exceed Q1 volume — settlements cover pre-Q1 receivable too)
- TerraPay receivable should compress significantly

## Juba Express
- Q1 Layer 1: 7 events, 1,168 MRU
- Q1 Layer 2: 0 (BPM statements unavailable)

## Bridge EUR
- Q1 Layer 1: 29 events, 80,259 MRU (1,804 EUR at FX 44.5)
- **Q1 Layer 2 settlements: 568 settlements, 269,400 USDC (11,988,291 MRU)**
- Bank: eth_cado01
- Note: Bridge settlement volume (269K USDC) far exceeds Q1 Layer 1 (1.8K EUR) — this suggests Bridge has significant pre-Q1 activity or the Layer 1 classifier captures only a subset of Bridge flows. The transfert_cadorim type (29 rows) may undercount Bridge volume. Investigation recommended.

## SNDP (B2C)
- Q1 B2C payout volume: 1,365,888 MRU
- Q1 events: 151 transactions
- No Layer 2 (MRU prefunding)

## Cadorim Wallet
- Q1 events: 928
- Q1 volume: 15,802,251 MRU

## Agent Network
- Q1 events: 4,052
- Q1 volume: 20,652,723 MRU

## Summary
- Layer 2 ingested for 2/4 international partners (TerraPay + Bridge)
- TerraPay: 35 settlements clearing 477K USDC — healthy reconciliation
- Bridge: 568 settlements clearing 269K USDC — volume mismatch with Layer 1 needs investigation
- Ria: most important revenue partner, settlement parsing is the top priority for Phase 2
