# Layer 2 Data Inventory — 2026-04-20 (updated with parsed data)

## TerraPay — Cado02 ETH (USDC)
- **Status: INGESTED**
- Source: `data/settlements/Cado02_Transaction_Dossier_2026.xlsx` (Entrées IN sheet)
- Cado02 address: `0x983e66Ea0b6f3BDA147D523c9F70Bd24D90AdA27`
- TerraPay source addresses: `0x3c9fb156...` and `0x8195d349...`
- **35 USDC settlements ingested** (Jan 2026 → Mar 2026 window)
- **Total: 477,100 USDC** (18,606,902 MRU at FX 39.0)
- Bank: eth_cado02

## Bridge — Cado01 ETH (USDC)
- **Status: INGESTED**
- Source: `data/settlements/Cado01_Transaction_Dossier_2026.xlsx` (Entrées IN sheet)
- Cado01 address: `0x88a1d3ACf440bDa4f3a8fd72c51d4d4351E3494d`
- Bridge source: `Bridge_API` address `0x4c2c0f0bb263...`
- **568 USDC settlements ingested** (excluding 18 Cado02→Cado01 internal transfers)
- **Total: 269,400 USDC** (11,988,291 MRU at FX 44.5)
- Bank: eth_cado01
- User confirmed: "Bridge are in Cado01 if the transaction is NOT from Cado02"

## Ria — BMI + SWIFT + Wire + Excel
- **Status: AVAILABLE BUT NOT YET PARSED**
- Found: 7 BMI PDF statements (Nov 2025 → Apr 2026)
- Found: 65 SWIFT confirmation emails
- Found: 533 Wire notification receipts
- Found: 60 CorrespPayment report emails
- TODO Phase 2: Parse SWIFT emails (base64-encoded HTML) to extract settlement amounts/dates/references

## Juba — BPM
- **Status: DEFERRED**
- No BPM statement files found
- Small volume (7 transactions, 1,168 MRU). Low priority.

## Summary
- **Layer 2 settlements: 2 of 4 international partners ingested** (TerraPay + Bridge)
- **603 total settlement events** parsed from Cado01/Cado02 Excel dossiers
- Ria settlement data is available (533 Wire + 65 SWIFT) but requires email parsing — deferred to Phase 2
- Juba deferred (no source files, minimal volume)
