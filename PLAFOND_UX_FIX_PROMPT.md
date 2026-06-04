# Claude Code Prompt — Plafond UX Fixes + Reserve Balance

## Context

File: `~/cadorim-engine/engine.html`. The Plafond system is already built (Liquidity section in Setup tab with Channel Balance, Historical Usage, Plafond Allocation Rules, and Validation Summary). Three UX problems need fixing and one feature added.

## Fix 1: Number input blocks typing

**Problem**: The plafond MRU input field has real-time validation that prevents the user from typing freely. For example, trying to type "126000" gets blocked mid-keystroke because the partial value triggers validation. This is extremely frustrating.

**Solution**: 
- Remove ALL `oninput` validation that checks plafond values against balance limits while typing
- The input field should be a plain `<input type="text" inputmode="numeric">` (NOT `type="number"`) so the user can type freely without spinner arrows interfering
- Format the display with thousand separators (French locale: spaces) using an `onblur` handler — when the user leaves the field, parse the raw number, format it, and THEN validate
- Validation (sum ≤ balance check) happens ONLY:
  1. On `onblur` (when user leaves the input)
  2. On "Run Engine" click
  3. When rendering the validation summary
- While the user is typing (field has focus), do NOT interfere, do NOT reformat, do NOT validate
- Store the raw numeric value in the `plafonds[]` array, display the formatted version only after blur

Implementation pattern:
```javascript
// On the input element:
<input type="text" inputmode="numeric" 
       value="${formatNumber(rule.plafond)}"
       onfocus="this.value=this.value.replace(/\s/g,'')"
       onblur="handlePlafondBlur(this, ruleIndex)"
       style="text-align:right">

function handlePlafondBlur(el, idx) {
    const raw = parseInt(el.value.replace(/\s/g, ''), 10) || 0;
    plafonds[idx].plafond = raw;
    el.value = formatNumber(raw);  // e.g., "126 000"
    updateValidationSummary();     // recompute totals
}

function formatNumber(n) {
    return Math.round(n).toLocaleString('fr-FR');  // "126 000"
}
```

## Fix 2: Allow editing via percentage

**Problem**: It's more intuitive to say "TerraPay gets 84% of Sedad" than to calculate "84% × 150,000 = 126,000" manually. The user should be able to edit EITHER the MRU amount OR the percentage, and the other updates automatically.

**Solution**: Make the "% of Balance" column an EDITABLE input field alongside the MRU field. The two are linked:

- User types in MRU field → % auto-updates: `% = plafond / channelBalance × 100`
- User types in % field → MRU auto-updates: `plafond = Math.round(% / 100 × channelBalance)`

Both fields follow the same blur-only validation pattern (no interference while typing).

Layout for each row:
```
| Channel [dropdown] | Partner [dropdown] | [MRU input] | [% input] | Priority [dropdown] | Status | ✕ |
```

The % input:
```html
<input type="text" inputmode="numeric" 
       value="${percentValue}%"
       onfocus="this.value=this.value.replace('%','')"
       onblur="handlePercentBlur(this, ruleIndex)"
       style="text-align:right; width:70px">
```

```javascript
function handlePercentBlur(el, idx) {
    const pct = parseFloat(el.value.replace('%','')) || 0;
    const channelKey = plafonds[idx].channel.replace('sim_','');
    const balance = SIM_INITIAL.wallet[channelKey] || 0;
    plafonds[idx].plafond = Math.round(pct / 100 * balance);
    el.value = pct.toFixed(0) + '%';
    renderPlafonds();  // re-render to sync MRU field
}
```

Table header update:
```
| CHANNEL | PARTNER | PLAFOND (MRU) | % | PRIORITY | STATUS | |
```

## Fix 3: Add Reserve Balance per channel

**Problem**: The validation summary shows allocated total vs. balance, but doesn't explicitly show what's LEFT unallocated. This reserve is critical — it's the safety buffer.

**Solution**: Update the validation summary to include a **Reserve** line per channel:

Current format:
```
sim_sedad: terrapay 126,000 + sndp 16,500 + wallet 9,000 = 151,500 / 150,000 (101%) ✗ OVER-ALLOCATED
```

New format:
```
sim_sedad:
  Allocated: terrapay 126,000 + sndp 16,500 + wallet 9,000 = 151,500
  Balance:   150,000 MRU
  Reserve:   -1,500 MRU ✗ OVER-ALLOCATED (reduce allocations by 1,500)

sim_click:
  Allocated: terrapay 70,000 = 70,000
  Balance:   70,000 MRU  
  Reserve:   0 MRU ✓ Fully allocated

sim_masrvi:
  Allocated: ria 50,000 = 50,000
  Balance:   80,000 MRU
  Reserve:   30,000 MRU ✓ (37% buffer)

sim_bankily:
  Allocated: terrapay 30,000 = 30,000
  Balance:   50,000 MRU
  Reserve:   20,000 MRU ✓ (40% buffer)
```

**Reserve = Balance - Sum(plafonds for this channel)**

Color coding:
- Reserve < 0: Red, bold "OVER-ALLOCATED", show how much to reduce
- Reserve = 0: Green ✓ "Fully allocated" (fine but no buffer)
- Reserve > 0 and < 10% of balance: Yellow ✓ with "(X% buffer)" — tight but OK
- Reserve > 0 and ≥ 10% of balance: Green ✓ with "(X% buffer)"

The reserve line should be visually distinct — slightly indented, with a horizontal bar showing the allocation visually:

```
sim_sedad (150,000 MRU):
[████████ terrapay 84% ████][██ sndp 11%][█ wallet 6%][░░ reserve 0%░░]
  Reserve: -1,500 MRU ✗ OVER-ALLOCATED
```

Use inline colored divs for the stacked bar:
- Each partner's allocation = a colored segment (use the existing PC color palette)
- Reserve = light gray segment
- If over-allocated, the bar overflows (show in red)

This stacked bar should be simple CSS (flex row with proportional widths), no Chart.js needed.

## Summary of changes

1. **Input fields**: Change to `type="text" inputmode="numeric"`, validate on blur only, format with thousand separators
2. **% column**: Make editable, bidirectional sync with MRU column
3. **Validation summary**: Add Reserve = Balance - Allocated per channel, with stacked allocation bar and color-coded status
4. **No other changes** — do not touch the gating logic, the dashboard rendering, the profit engine, or any other part of the file. This is purely a Setup tab UX improvement.

## Testing

After the fix:
1. Load simulation → plafond rules populate
2. Click on a MRU field → can type freely "150000" without being blocked mid-keystroke
3. On blur → formats to "150 000" and validation updates
4. Change % field to "90%" → MRU auto-updates to "135 000" for sedad (90% × 150,000)
5. Validation shows Reserve per channel with stacked bars
6. Over-allocation shows red reserve and blocks engine
7. Run Engine → everything works as before (gating, blocked txns, dashboards)
