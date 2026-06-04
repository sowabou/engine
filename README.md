# Cadorim Accounting Engine

Parameter-driven accounting backbone for all Cadorim cash flows — Ria, TerraPay, Juba, CadorimPay (B2C), agent operations, and treasury. One universal function covers all five flows; everything is parameterized by partner, settlement bank, payout channel, and currency.

Python prototype today. PHP production rewrite planned (target stack: existing Cadorim platform).

## Start here

| If you are... | Read this first |
|---|---|
| **New to this project (especially Abou)** | [`HANDOVER/README.md`](HANDOVER/README.md) — orientation and onboarding |
| **Looking for design rationale + open issues** | [`HANDOVER/PROJECT_MEMORY.md`](HANDOVER/PROJECT_MEMORY.md) |
| **Picking up open work** | [`HANDOVER/NEXT_STEPS.md`](HANDOVER/NEXT_STEPS.md) — prioritized punch list |
| **Setting up your environment** | [`HANDOVER/SETUP_ABOU.md`](HANDOVER/SETUP_ABOU.md) — Day 1 walkthrough |
| **Working on the code with Claude** | [`CLAUDE.md`](CLAUDE.md) — deep technical reference and operating rules |

## What's in this repo

- **`cadorim_engine/`** — Python package: classifier, L1/L2 reconciliation checks, settlement parsers, API adapters
- **`HANDOVER/`** — onboarding kit for the team
- **`engine.html`** — 11-tab dashboard (Setup, CEO, Treasury, Operations, Positions, Ria L1/L2, TerraPay L1/L2, MRU/USD Exchange)
- **`*_PROMPT.md`** — active and completed build specs (pending queue, plafond, partner ledger, etc.)
- **`tests/`** — pytest test suite
- **`alembic/`** — database migrations

## What's NOT in this repo (and never will be)

Customer data, banking files, email archives, and production DB dumps live on a separate cloud folder (Drive / Dropbox). The repo's `.gitignore` enforces this — never commit anything matching `data/`, `*.sql`, `*.eml`, `Releve*`, `SWIFT*`, `BMI*`, etc.

If you're missing data files needed to run reconciliations, ask Dr Neine for access to the `Cadorim Accounting/` cloud folder.

## Quick start

```bash
# Clone (requires repo access)
git clone https://github.com/DrNeine/cadorim-engine.git
cd cadorim-engine

# Install Python deps
python3 -m pip install -r requirements.txt --break-system-packages

# (Optional) load production data — requires the data folder synced separately
python3 load_production.py

# Run the dashboard
python3 -m http.server 8765
# Open http://localhost:8765/engine.html
```

Full setup walkthrough: [`HANDOVER/SETUP_ABOU.md`](HANDOVER/SETUP_ABOU.md).

## Hard rules (don't violate)

These are corrections that the architect (Dr Neine) has explicitly made. They are binding:

1. **Math, not pipelines.** Use function notation. Never write partner-specific logic. Parameterize.
2. **Client wallets are CREDITED on receive, NEVER debited.** Debit the source / charges account.
3. **Pending transactions live in the queue view, NEVER in posted ledgers.** Every event needs `id + created_at + posted_at + status`.
4. **L1 and L2 are mathematically separate.** Never cross-reference.
5. **The `transfert` DB type is overloaded.** Always classify by account pattern, not by type string.
6. **Caisse naming is ambiguous.** Mboirick / Tidjany / Babe don't map cleanly across DB, Grand Livre, and instructions — ask before assuming.
7. **Settlement does NOT reset plafond.** Settlement goes to bank; wallets top up only via explicit movement.
8. **Never close a month or overwrite a ledger without explicit "yes, close."** Always preview first.

Full context for each rule: [`HANDOVER/PROJECT_MEMORY.md`](HANDOVER/PROJECT_MEMORY.md) §14.

## Team

- **Dr Mohamed Elmoctar Neine** — architect of the engine, designer of the universal transaction model
- **Abou Sow** — CTO, taking the build forward to production
- **Mboirick** — production PHP stack (alongside Abou)

## Status

- ✅ L1/L2 reconciliation live for Ria and TerraPay (Q1 2026 data)
- ✅ 11-tab dashboard operational
- ⚠️ TerraPay TPFN classifier fix pending (see `NEXT_STEPS.md` P2)
- ⚠️ 29M MRU Ria gap investigation open (see `NEXT_STEPS.md` P1)
- ⏳ Plafond / pending-queue module — design complete, build pending
- ⏳ PHP production rewrite — not yet started

---

🔒 **Private repository.** This project contains references to Cadorim's commercial operations. Do not share access, transfer ownership, or change visibility without explicit approval from Dr Neine or Abou.
