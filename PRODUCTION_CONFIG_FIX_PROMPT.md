# Claude Code Prompt — Fix Production Data Contract: include partner + channel config

## WRITE PERMISSION (explicit user grant)

The user has authorized you to write to `~/cadorim-engine/`, `~/Documents/Claude/Projects/Cadorim Accounting/`, and `/tmp/`. Work freely.

## Context

The Ria classifier and export from the previous prompt landed correctly — `data/production_data_ria.json` has 2,885 real transactions. But when the user clicks **Production** in `engine.html`, the Setup tab still shows simulation partners (sim_ria, sim_terrapay, ...), and no CEO/Positions/Operations history appears for the real data.

**Root cause:** data contract mismatch on TWO dimensions:

1. Production transactions have `Par_l = 'ria'`, but engine's `SIM_CONFIG.layer1` only has a partner with `code = 'sim_ria'`. Engine looks up the partner for each production txn, finds nothing, silently drops it from profit + ledger.
2. Production transactions have ~20 distinct `Local_Par_n` values (e.g. `caisse_agent_compte_49385000`, `caisse_mboirick`). None of those channels are registered in `SIM_CONFIG`. Same silent-drop problem.

The Production toggle (lines ~894–925 in engine.html) only swaps `SIM_TXS`, `SIM_SETT`, `SIM_WD`, `SIM_INITIAL`. It does NOT swap `SIM_CONFIG` (the partner/channel registry).

## Goal

Make Production data fully wired: partner "ria" registered, every channel discovered in the data registered, Setup tab reflects production config when toggled, Positions/CEO/Operations all populate.

---

## FIX 1 — Export includes a `config` block

Update `load_production.py` `export_ria_q1` (or equivalent) so the JSON output also contains a `config` block that mirrors the shape of `SIM_CONFIG` but for production:

```json
{
  "generated_at": "...",
  "scope": "ria_q1_2026",
  "cutoff_date": "2026-01-01",
  "opening": { ... unchanged ... },
  "transactions": [ ... unchanged ... ],
  "settlements": [],
  "withdrawals": [],
  "config": {
    "layer1": [
      {
        "code": "ria",
        "name": "Ria",
        "is_international": true,
        "currency": "EUR",
        "commission_type": "fixed",
        "commission_rate": "0",
        "commission_fixed": "25",
        "fx_partner_rate": "42.0",
        "fx_cadorim_rate": "42.5",
        "fx_market_rate": "42.3",
        "channels": [
          {"code": "caisse_mboirick", "cost_payout": "0", "cost_type": "fixed"},
          {"code": "caisse_agent_compte_49385000", "cost_payout": "0", "cost_type": "fixed"},
          ... auto-generated from unique Local_Par_n values in transactions ...
        ]
      }
    ],
    "layer2": [
      {"partner_code": "ria", "bank_code": "bmi", "bank_name": "BMI"}
    ]
  },
  "stats": { ... unchanged ... }
}
```

### How to generate the channels list

In the Python export:

```python
unique_channels = sorted({t['Local_Par_n'] for t in transactions if t.get('Local_Par_n')})
channels = [
    {"code": code, "cost_payout": "0", "cost_type": "fixed"}
    for code in unique_channels
]
```

Ria has no explicit payout cost at the channel level (the commission is the full margin), so `cost_payout = "0"`. If later we learn otherwise, one line to change.

### FX rates — defensible defaults

- `fx_partner_rate = "42.0"` — Ria's internal booking rate
- `fx_cadorim_rate = "42.5"` — the rate we use when crediting MRU
- `fx_market_rate = "42.3"` — market rate reference

These are approximations. Comment with `# TODO Phase 2: per-txn FX from transactions_devises`.

### Commission

Ria charges a **fixed 25 MRU per transaction** (spot-checked from the DB: `commission ≈ 20-30 MRU`). Use `commission_type = "fixed"`, `commission_fixed = "25"`. The classifier is already capturing the actual commission per transaction in `commission_a`, so this config default only matters if the engine recomputes commission from scratch — check whether it does, and if so note any discrepancy.

---

## FIX 2 — Engine toggle swaps config too

Around line 899 in `engine.html`, inside the Production branch of `switchDataSource('prod')`:

**Current (what's there now):**
```javascript
.then(d=>{
    SIM_TXS.length=0;d.transactions.forEach(t=>SIM_TXS.push(t));
    SIM_SETT.length=0;(d.settlements||[]).forEach(s=>SIM_SETT.push(s));
    SIM_WD.length=0;(d.withdrawals||[]).forEach(w=>SIM_WD.push(w));
    Object.assign(SIM_INITIAL,d.opening);
    ...
    loadFromDict(SIM_CONFIG);  // ← this reloads the OLD sim config
    runEngine();
})
```

**Replace with:**
```javascript
.then(d=>{
    SIM_TXS.length=0;d.transactions.forEach(t=>SIM_TXS.push(t));
    SIM_SETT.length=0;(d.settlements||[]).forEach(s=>SIM_SETT.push(s));
    SIM_WD.length=0;(d.withdrawals||[]).forEach(w=>SIM_WD.push(w));
    Object.assign(SIM_INITIAL,d.opening);
    // NEW: swap the partner/channel registry too
    if(d.config){
        loadFromDict(d.config);
    } else {
        loadFromDict(SIM_CONFIG);
    }
    runEngine();
})
```

The switch back to Simulation already does `location.reload()` which resets everything cleanly — no change needed there.

---

## FIX 3 — Setup tab renders production partners/channels

This should work automatically once FIX 2 lands, because `loadFromDict()` is the same function that renders Setup from any config dict. Verify by clicking the Setup tab after toggling to Production: you should see **one partner** named "Ria" with ~20 channels listed, instead of the five sim_* partners.

If `loadFromDict()` doesn't render the channel list correctly because the production config has 20+ channels (way more than the simulation's 2), tweak the rendering to handle arbitrary channel counts — but don't refactor the function's signature.

---

## FIX 4 — Banner includes the count

Update the Production banner (line ~909) to show a fuller summary:

```javascript
banner.innerHTML = `📡 Production: ${d.transactions.length} Ria txns · ${d.config?.layer1?.[0]?.channels?.length || 0} channels · opening recv ${((d.opening?.opening_receivable?.sim_ria?.foreign || d.opening?.opening_receivable?.ria?.foreign || 0)).toLocaleString()} EUR · generated ${(d.generated_at||'').slice(0,10)}`;
```

Note: the opening receivable key is `sim_ria` in the current JSON (because `compute_opening` hardcoded that). When you fix FIX 5 below, change that key to `ria` so it matches. Support both keys in the banner during transition.

---

## FIX 5 — `opening.py` uses partner code `'ria'` not `'sim_ria'`

Check `cadorim_engine/opening.py`. If it hardcodes `'sim_ria'` in the `opening_receivable` dict, change it to `'ria'`. The engine looks up opening receivable by `Par_l` code — if we're using `'ria'` everywhere else, this must match.

Re-run the export after fixing so the JSON is consistent.

---

## FIX 6 — Regenerate the JSON

After code changes, run:
```bash
cd ~/cadorim-engine && python3 load_production.py export_ria_q1 --out data/production_data_ria.json
```

Confirm the new JSON contains a `config` block with the Ria partner and all discovered channels. Confirm `opening.opening_receivable` uses key `ria`.

---

## ACCEPTANCE CRITERIA

1. `data/production_data_ria.json` now contains a `config` block with one Ria partner and the auto-generated channel list.
2. Partner key in `opening.opening_receivable` is `ria`, not `sim_ria`.
3. Click **Production** in the browser:
   - Banner shows transaction count + channel count + opening receivable
   - Setup tab shows ONE partner named "Ria" with ~20 channels
   - Operations tab shows 2,885 transaction rows
   - CEO tab shows non-zero L1 profit (~70-90k MRU, from 2,885 × ~25 MRU commission)
   - Positions tab → "ria" partner ledger shows 2,885 entries + running receivable growing
   - Budget tab → equity curve trends down (as expected, no settlements)
4. Click **Simulation** — page reloads to original sim state.
5. No JavaScript console errors when toggling.
6. Existing tests still pass: `pytest -xvs tests/`.

---

## DO NOT

- Do not add new partners beyond Ria (that's Phase 1b, TerraPay)
- Do not touch the classifier's transaction shape — it's correct
- Do not change engine math (computeL1/L2, applyTx, applySett, applyWd)
- Do not modify the Simulation path — it must keep working exactly as today

---

## REPORT BACK

When done:
- New `engine.html` line count
- Number of unique channels auto-discovered
- L1 profit shown on CEO tab for Q1 2026 (real production number)
- Total receivable shown on Treasury at end of Q1 2026
- Confirm all 6 acceptance criteria pass
- Any ambiguity you resolved by your own judgment
