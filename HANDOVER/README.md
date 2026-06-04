# Handover to Abou Sow — Cadorim Accounting Engine

Abou — this is the work Dr Neine has been designing and building. He wants you to take it forward. The engine is a real, working Python prototype; the math model is locked; the path to production is PHP.

**You will work with Claude (in Cowork) to complete this.** Claude has been deeply involved in building this with Dr Neine. When you open this folder in Cowork, Claude reads the project context automatically and continues from where Dr Neine left off — but only if you set things up correctly first.

This README is your map. Read it once end-to-end, then dive in.

---

## 1. What you're inheriting

A working **Cadorim Accounting Engine** that:

- Reads from the production MySQL database (5 SQL dumps in `Data API transaction/`)
- Classifies 14 DB transaction types into 5 universal business flows (Ria, TerraPay, Juba, Wallet, B2C, Agent, Treasury)
- Runs Layer 1 (transaction-level) and Layer 2 (settlement-level) reconciliations for Ria and TerraPay
- Renders 11 dashboard tabs (CEO, Treasury, Operations, Positions, 5 reconciliation checks)
- Pulls real data: Q1 2026 Ria L2 gain = 4.6M MRU, TerraPay L2 gain = 683K MRU

**The math is locked.** Dr Neine designed the engine as pure algebra — one universal function, parameterized by partner/bank/channel/currency. Never write partner-specific logic. This is non-negotiable. The full design is in `PROJECT_MEMORY.md`.

**What's open** (priority order):
1. The 29M MRU Ria reconciliation gap (Q1 2026) — Grand Livre ≠ DB
2. TerraPay TPFN classifier fix — 1,029 real TerraPay payouts are mis-tagged as `depot`
3. Plafond / pending-queue build-out — design done, implementation pending
4. May 2026 data refresh (new BMI PDFs, SWIFT emails, Cado02 xlsx, Binance file)
5. Eventual PHP port for production

See `NEXT_STEPS.md` for the prioritized punch list with acceptance criteria.

---

## 2. How to set up (Day 1)

Do this in order. **Don't skip steps** — Claude can't help you if the context isn't loaded.

### Step 1 — Get the folder

Download / sync the shared cloud folder (Drive or Dropbox) to your Mac. Recommended path:
`/Users/<yourname>/Documents/Claude/Projects/Cadorim Accounting/`

The folder is ~1.5 GB (email archives are large). Let it fully sync before opening Cowork.

### Step 2 — Open Cowork and mount this folder

1. Open the Claude desktop app
2. Switch to **Cowork mode**
3. Select / mount the `Cadorim Accounting` folder you just synced
4. Cowork will automatically load the top-level `CLAUDE.md` — that file orients Claude to the whole project

### Step 3 — Install the same plugins Dr Neine uses

In Cowork, install these plugins from the plugin marketplace:

- **anthropic-skills** (bundles `pdf`, `xlsx`, `pptx`, `docx`, plus the project-specific skills below)
  - `ria-accounting` — Ria SWIFT/Wire/Excel parsing
  - `terrapay-accounting` — TerraPay USDC/USD/EUR + wallet payouts
  - `cadorim-accounting` — bank receipts, Binance P2P
  - `cadorim-project-manager` — project planning
  - `cadorim-letter` — official letters
  - `strategic-wealth-operator` — strategic gate-check (auto-triggers)

- **productivity** (memory + tasks + Slack/Notion/etc)

Detailed install steps are in `SETUP_ABOU.md`.

### Step 4 — Connect Gmail (for live email parsing)

Ria emails land in Dr Neine's IONOS mailbox `mel.neine@cadorim.com`, forwarded to Gmail. To access them via Claude:

1. In Cowork settings, connect **Gmail**
2. Use the account that receives the Ria forwards (Dr Neine will share access)

Without Gmail connected, you can still read the 363 CorrespPayment Excel attachments archived in `mails/` and `mails (1)/`.

### Step 5 — Verify Claude has loaded the project context

Start a new chat in Cowork (with this folder mounted) and say:

> "Briefly summarize the Cadorim Accounting Engine project and tell me what's in flight right now."

Claude should respond with the universal transaction model, the L1/L2 split, the 29M MRU Ria gap, the TerraPay TPFN issue, and the plafond queue. If it doesn't — context isn't loading. Check that `CLAUDE.md` is at the folder root.

---

## 3. How to drive Claude on this project

Dr Neine has set strong patterns. Match them and the work will be much faster.

### Speak in math, not pipelines

Wrong: *"How do I reconcile Ria payments against BMI?"*
Right: *"For Par_l='ria', Bank_t='BMI', compare ΣAmount_j at settlement vs ΣAmount_mru_h at L1 over period [t0, t1]."*

Claude will follow your style. If you speak in accounting jargon, you'll get pipeline-specific code (which Dr Neine explicitly rejects). If you speak in algebra, you'll get parameterized formulas.

### Always ask Claude to challenge first

For anything risky — modifying the classifier, closing a period, posting entries — ask Claude to propose the structure and *flag risks* before executing. The `CLAUDE.md` already tells Claude to do this, but reinforcing helps.

### Use the existing prompts

Inside `cadorim-engine/` you'll find ~15 `*_PROMPT.md` files. These are completed or in-progress design specs Dr Neine and Claude built together (CEO drilldown, partner ledger, pending queue, plafond, wallet balance gate, ...). When picking up a piece of work, read the corresponding prompt — it has the requirements, the math, and the file structure.

### Don't skip the feedback rules

Read `PROJECT_MEMORY.md` §14 (Feedback rules). These are corrections Dr Neine has made. Repeating them wastes time and frustrates him.

---

## 4. Files you absolutely must read before doing anything

In this order:

1. **`HANDOVER/README.md`** — this file (orientation)
2. **`HANDOVER/PROJECT_MEMORY.md`** — design, history, open issues, the feedback rules
3. **`../CLAUDE.md`** — deep technical reference (DB schema, classifier, accounting controls)
4. **`HANDOVER/NEXT_STEPS.md`** — what to work on first
5. **`HANDOVER/SETUP_ABOU.md`** — detailed Cowork setup steps

If you want the original design source documents:
- `Cahier_des_Charges_Cadorim_Accounting_Engine.docx` — original spec (Apr 2026)
- `Cadorim_Accounting_Engine_Architecture.docx` — architecture
- `../CLAUDE_CODE_MVP_BUILD.md` — the build spec executed to create the current engine

---

## 5. Working with Dr Neine going forward

Dr Neine has designed the architecture and built the prototype. He's stepping back to let you (and the team) operate and finish the build, with him available for design questions.

The plan from `juba_accounting_setup.md` memory:
> Claude builds Phase 1 in Python (Claude Code), team reviews, Abou rewrites in PHP for production.

Phases:
- **Phase 1** (✅ done): Local prototype — TerraPay + Ria parsers, L1/L2 reconciliation
- **Phase 2** (partial): Add Juba + CadorimPay deeper integration
- **Phase 3** (pending): Connect to live Cadorim API (you design the endpoints)
- **Phase 4** (pending): Production dashboard
- **Phase 5** (pending): Production deployment (PHP)

When you and Claude make changes — especially to the classifier, the universal model, or the data contracts — update `PROJECT_MEMORY.md` so the next person picking this up has the truth. The memory file is the long-term project brain.

---

## 6. Questions to ask Dr Neine before going too far

A few things are deliberately left open. Get his answer before deciding:

1. **Caisse naming** — Mboirick/Tidjany/Babe don't map cleanly across the DB, Grand Livre, and instructions (`PROJECT_MEMORY.md` §8). Get his preferred canonical mapping.
2. **2025 Ria ledger** — Oct–Dec 2025 are in the DB but absent from the Grand Livre. A separate 2025 ledger may exist. Ask him.
3. **Production API design** — Phase 3 needs API endpoints. He's done the data model; you'll design the API. Align with him first.
4. **PHP rewrite timeline** — Python engine works today. When do you want to fork the PHP version? After Phase 3 or earlier?

---

## 7. If something breaks

- **Claude doesn't have project context** → check `CLAUDE.md` exists at folder root, and that you opened Cowork with this folder mounted
- **Engine won't load** → `cd cadorim-engine && python3 -m http.server 8765` then open `http://localhost:8765/engine.html` and hard-refresh (Cmd+Shift+R)
- **SQLite errors when loading the DB** → the dump loader writes to `/tmp/cadorim.sqlite` (not the project folder — it rejects SQLite creation with disk I/O errors). Rebuild each session.
- **A reconciliation check returns wrong numbers** → check if classifier output is correct. TerraPay especially: don't trust `Par_l='terrapay'`, query SQL for `external_transaction_id LIKE 'TPFN%'`.
- **Skills don't trigger** → confirm the `anthropic-skills` plugin is installed in your Cowork instance.

---

**You've got this. The engine is solid, the math is locked, and Claude is fully briefed once this folder is mounted. Welcome aboard.**

— Handover prepared for Abou by Dr Neine + Claude, 18-May-2026
