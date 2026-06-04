# Phase 1b Morning Report — 2026-04-20

## STATUS: GREEN (Layer 1) / AMBER (Layer 2 — 2 of 4 partners)

## Headline numbers

- **Total Layer 1 events classified: 15,382** across 15 months (Jan 2025 → Mar 2026)
- **Total Layer 2 settlements ingested: 603** (35 TerraPay + 568 Bridge)
- **Partners active: 7/7** + ancillary + treasury + 10 unclassified
- **Unclassified rate: 0.1%** (10 rows — creditable_id=17 missing from accounts)
- **L1 total MRU (full window): 159,574,107 MRU**
- **L2 settlement volume: 746,500 USDC** (30,595,193 MRU)
- **Q1 2026 slice: 8,955 events, 74,804,683 MRU**

## Per-partner breakdown (full window)

| Partner | Events | L1 Volume (MRU) | Currency | L2 Settlements | L2 Volume | Status |
|---|---|---|---|---|---|---|
| ria | 4,632 | 38,188,267 | EUR | **0** | — | SWIFT parsing TODO |
| terrapay | 777 | 6,814,134 | USD | **35** | 477,100 USDC | GREEN |
| wallet | 4,200 | 65,704,265 | MRU | n/a | — | n/a |
| agent | 5,094 | 35,917,489 | MRU | n/a | — | n/a |
| sndp | 151 | 1,365,888 | MRU | n/a | — | n/a |
| treasury | 173 | 11,425,187 | MRU | n/a | — | n/a |
| bridge | 29 | 80,259 | EUR | **568** | 269,400 USDC | GREEN |
| ancillary | 309 | 14,450 | MRU | n/a | — | n/a |
| juba | 7 | 1,168 | EUR | **0** | — | No BPM data |
| unclassified | 10 | 63,000 | MRU | n/a | — | Edge case |

## Layer 2 data inventory

From `LAYER2_DISCOVERY.md`:
- **TerraPay**: 35 USDC settlements from Cado02 Excel (477,100 USDC)
- **Bridge**: 568 USDC settlements from Cado01 Excel (269,400 USDC), excluding 18 Cado02→Cado01 transfers
- **Ria**: 533 Wire + 65 SWIFT + 60 CorrespPayment emails AVAILABLE but not parsed (base64 HTML)
- **Juba**: No BPM statements found

## Anomalies encountered

1. **10 unclassified rows** (0.1%): `transfert` type with creditable_id=17 missing from accounts. Known.
2. **Bridge L2 >> L1**: 568 settlements (269K USDC) vs 29 L1 events (80K MRU). The `transfert_cadorim` type may undercount Bridge flows — some Bridge activity may route through different DB types. Needs investigation.
3. **Ria Layer 2 missing**: Most important revenue partner has no settlements ingested. The 533 Wire emails are the primary source — parsing requires extracting HTML from base64 EML files.

## Files changed

| File | Lines | Status |
|---|---|---|
| `cadorim_engine/classifier.py` | 277 | Rewritten: 14-type dispatcher |
| `cadorim_engine/opening.py` | 51 | Extended: all 4 intl partners |
| `cadorim_engine/settlements/ingest.py` | 127 | New: Cado01 + Cado02 parsers |
| `load_production.py` | 554 | Extended: export_all + L2 wiring |
| `engine.html` | 935 | 3-state toggle: Sim/Ria/All |
| `tests/test_classifier_all.py` | 72 | New: 15 classifier tests |
| `tests/test_export_all.py` | 18 | New: smoke test |

## Outputs

| File | Content |
|---|---|
| `data/production_data_all.json` | 15,382 events + 603 settlements |
| `data/production_data_all_q1_2026.json` | 8,955 events (Q1 slice) |
| `data/production_data_ria.json` | 2,885 Ria-only (Phase 1 compat) |
| `AUDIT_LOG.md` | 3 iterations |
| `LAYER2_DISCOVERY.md` | Full inventory |
| `Q1_2026_PARTNER_BALANCES.md` | Q1 partner snapshot |

## Test results
```
110 passed in 1.60s
```

## Outstanding items for morning review

1. **Ria SWIFT parsing**: 533 Wire + 65 SWIFT emails are staged. Parsing requires base64 decode → HTML parse → extract EUR amount, date, reference. This is the top priority for Phase 2 — Ria is the largest revenue partner with zero settlements.
2. **Bridge L2/L1 mismatch**: Bridge has 568 settlements but only 29 L1 events. The `transfert_cadorim` classifier may miss some Bridge flows. Recommend inspecting Bridge_API transactions to understand the full Bridge flow.
3. **Per-transaction FX rates**: All FX rates are fixed approximations. Phase 2 should derive rates from `transactions_devises` table.
4. **Engine plafond rules**: Production JSON has empty plafonds. For production data, plafonds apply to wallet channels (Sedad, Masrvi, Click, Bankily) — not to caisses where Ria pays out.
