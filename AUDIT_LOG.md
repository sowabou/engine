# Audit Log — Phase 1b

## Iteration 1 — 2026-04-20 (Layer 1 only)
- Scope: Jan 2025 → Apr 2026
- Events emitted: 15,382
- Unclassified: 10 (0.1%) — all creditable_id=17 missing from accounts
- Per-partner counts: ria=4632, terrapay=777, juba=7, bridge=29, sndp=151, wallet=4200, agent=5094, treasury=173, ancillary=309
- Layer 2: 0 settlements (source files inaccessible)
- Status: GREEN (Layer 1) / AMBER (Layer 2)

## Iteration 2 — 2026-04-20 (test fix)
- Fixed test_non_ria_returns_none → test_non_ria_classifies_differently
- 110/110 tests pass

## Iteration 3 — 2026-04-20 (Layer 2 ingestion)
- User staged settlement files in data/settlements/
- Parsed Cado02_Transaction_Dossier_2026.xlsx → 35 TerraPay settlements (477,100 USDC)
- Parsed Cado01_Transaction_Dossier_2026.xlsx → 568 Bridge settlements (269,400 USDC)
- Excluded 18 Cado02→Cado01 internal transfers per user instruction
- Total settlements: 603
- Ria: 0 (SWIFT parsing deferred — emails available but base64-encoded HTML)
- Juba: 0 (no BPM statements)
- All checks pass:
  - Unclassified: 0.1% OK
  - All 7 partners present OK
  - Duplicates: 0 OK
  - Negative MRU: 0 OK
  - caisse_unknown: 0 OK
- Status: **GREEN (Layer 1) / GREEN (Layer 2 for TerraPay + Bridge) / AMBER (Layer 2 for Ria + Juba)**
