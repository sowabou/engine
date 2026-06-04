# Day 1 Setup — Abou's Cowork + GitHub Environment

This walks you through getting set up to continue the Cadorim Accounting Engine work. Total time: ~45 minutes.

The project is split across two locations:
- **GitHub repo** (`cadorim-accounting-engine`) — code, docs, handover. Small (~30 MB). You clone this.
- **Data dossier** (Drive or Dropbox) — email archives, bank statements, DB dumps. Large (~1.5 GB). Dr Neine shares the folder.

You need both to run reconciliations, but you can start reading and exploring with just the repo.

---

## Step 0 — Before you start

**You need:**
- A Mac
- A Claude account with Cowork enabled (free tier works; Pro/Team gives more usage)
- A GitHub account (free) — Dr Neine will invite you to the `cadorim` organization
- The Gmail account that receives the Ria forwards (Dr Neine will give you credentials or share access)
- ~2 GB free disk space if you sync the data dossier

---

## Step 1 — Install the Claude desktop app

1. Go to https://claude.ai/download
2. Download for macOS, install, sign in
3. Switch to **Cowork mode** in the app

---

## Step 2 — Accept the GitHub invitation

Dr Neine will invite you to:
- The `cadorim` organization on GitHub
- The `cadorim-accounting-engine` repository (with write access)

Check your email for the invite. Click "Accept invitation". Verify you can see the repo at `https://github.com/cadorim/cadorim-accounting-engine`.

---

## Step 3 — Clone the repo

Open Terminal and run:

```bash
cd ~/Documents
git clone https://github.com/cadorim/cadorim-accounting-engine.git
cd cadorim-accounting-engine
ls
```

You should see: `CLAUDE.md`, `HANDOVER/`, `cadorim_engine/`, `engine.html`, `requirements.txt`, plus the `*_PROMPT.md` build specs.

If git asks for credentials, install GitHub CLI: `brew install gh && gh auth login` (recommended) — or set up a Personal Access Token.

---

## Step 4 — Sync the data dossier (separate from git)

Dr Neine will share a `Cadorim Accounting/` cloud folder via Drive or Dropbox. This contains:
- Email archives (`mails/`, `mails (1)/`)
- Bank statements (BMI, BPM PDFs)
- `Data API transaction/` (5 SQL dumps — production DB snapshot)
- Grand Livre + reconciliation xlsx files

Sync it to your Mac. **Important: put the cloned repo INSIDE this folder** so the engine can find the data files at the relative paths it expects:

```
~/Documents/Cadorim Accounting/         ← Drive/Dropbox synced folder
├── Data API transaction/               ← SQL dumps (sensitive)
├── mails/  mails (1)/                  ← email archives (sensitive)
├── bank_statements/                    ← (sensitive)
├── Grand_Livre_*.xlsx
└── cadorim-accounting-engine/          ← cloned git repo lives here
    ├── CLAUDE.md
    ├── HANDOVER/
    ├── cadorim_engine/
    └── ...
```

This matches Dr Neine's layout. The engine's loader scripts read SQL dumps from `../Data API transaction/`.

---

## Step 5 — Mount the workspace folder in Cowork

1. In the Cowork app, select / mount your **`Cadorim Accounting`** parent folder (not the repo subfolder)
2. Confirm Cowork shows it as connected
3. When you open a new chat, Claude reads `cadorim-accounting-engine/CLAUDE.md` and has the project context

---

## Step 6 — Install the required plugins

**In Cowork → Settings → Plugins:**

### Required

1. **anthropic-skills** — bundles `pdf`, `xlsx`, `pptx`, `docx`, plus the Cadorim-specific skills:
   - `cadorim-accounting`
   - `ria-accounting`
   - `terrapay-accounting`
   - `cadorim-project-manager`
   - `cadorim-letter`
   - `strategic-wealth-operator`
   - `appel-d-offre` (tender / proposal responses)

2. **productivity** — `task-management`, `memory-management`, connectors for Slack/Notion/Linear/Asana/ClickUp/Monday/MS365

### Recommended

3. **scheduled-tasks** (built-in usually) — for nightly engine refresh tasks
4. **Claude in Chrome** — for browser-based research / scraping bank portals

**Verify install.** In a new chat, ask "what skills are available?" — you should see all six Cadorim skills.

---

## Step 7 — Connect Gmail

The Ria reconciliation pipeline pulls from Gmail. Without this, you can only read archived emails.

1. Cowork → Settings → Connectors → Gmail → Authorize
2. Use the Gmail account that receives Ria forwards from `mel.neine@cadorim.com`
3. Grant read access

**Verify.** Ask Claude: "list my recent Ria emails from the past week." It should return SWIFT Confirmations and Wire Notifications.

---

## Step 8 — Install Python deps

```bash
cd ~/Documents/Cadorim\ Accounting/cadorim-accounting-engine
python3 -m pip install -r requirements.txt --break-system-packages
```

Or use a virtualenv if you prefer.

---

## Step 9 — Load the production database

The 5 SQL dumps are in the parent folder's `Data API transaction/`. The loader converts them to SQLite at `/tmp/cadorim.sqlite`:

```bash
cd ~/Documents/Cadorim\ Accounting/cadorim-accounting-engine
python3 load_production.py
```

**Important:** writes to `/tmp/cadorim.sqlite` not the project folder. Rebuild each session — it's fast.

**Verify:** `sqlite3 /tmp/cadorim.sqlite "SELECT COUNT(*) FROM transactions;"` should return ~18,225.

---

## Step 10 — Launch the engine dashboard

```bash
cd ~/Documents/Cadorim\ Accounting/cadorim-accounting-engine
python3 -m http.server 8765
```

Open http://localhost:8765/engine.html in your browser. Hard-refresh (Cmd+Shift+R).

You should see 11 tabs: Setup, CEO, Budget, Treasury, Operations, Positions, Check Ria L1, Check Ria L2, Check TerraPay L2, MRU/USD Exchange, Check TerraPay L1.

---

## Step 11 — Smoke test Claude with project context

Start a fresh Cowork chat (with `Cadorim Accounting` mounted) and run these:

### Test 1 — Project understanding
> "Briefly summarize the Cadorim Accounting Engine: the core architecture, what's currently built, and what's open."

✅ Pass if Claude mentions: universal transaction model, parameter registries (Par_l, Bank_t, Local_Par_n, Cur_k), L1/L2 split, 5 business flows, 11 dashboard tabs, the 29M MRU Ria gap, the TerraPay TPFN classifier issue.

❌ Fail (CLAUDE.md not loaded) if Claude asks "what is Cadorim?" or gives generic accounting advice.

### Test 2 — Math vocabulary
> "How do I compute Layer 1 profit for Par_l='ria' over period [2026-01-01, 2026-03-31]?"

✅ Pass if Claude responds in algebra: `Σ Profit_transaction_a = Σ (commission_a − cost_payout_a) + Σ transaction_a_fx_gain`, filtered by `Par_l='ria'` and date range.

❌ Fail if Claude starts explaining "debit and credit" or proposes a Ria-specific function.

### Test 3 — Feedback rule
> "Write a journal entry that debits Hamel's wallet and credits the source account for a CadorimPay payment."

✅ Pass if Claude refuses and says client wallets are CREDITED not debited, then proposes the correct entry.

❌ Fail if Claude writes the entry as asked.

### Test 4 — Skill triggering
> "I have a new TerraPay prefunding email — process it."

✅ Pass if Claude triggers the `terrapay-accounting` skill.

❌ Fail if it ignores the skill and tries to parse manually.

---

## Step 12 — Working with git as you change things

Branch + PR workflow recommended:

```bash
git checkout -b fix-tpfn-classifier
# ... edit files ...
git add cadorim_engine/classifier.py
git commit -m "Classify TPFN external_transaction_id as Par_l=terrapay before falling through to type"
git push -u origin fix-tpfn-classifier
# Then open a Pull Request on github.com
```

Don't commit data files. The `.gitignore` should already block them, but always run `git status` before `git add .` to verify.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Claude says "what is Cadorim?" | `CLAUDE.md` not loaded | Confirm parent folder is mounted in Cowork, restart |
| `git clone` asks for password | No auth set up | `brew install gh && gh auth login` |
| Skills don't auto-trigger | Plugin not installed | Install `anthropic-skills` |
| `load_production.py` fails | Looking at wrong path | Repo must be inside `Cadorim Accounting/` folder (Step 4) |
| Engine dashboard shows no data | Indexes not built | See `PROJECT_MEMORY.md` §13 monthly refresh |
| Gmail connector not pulling Ria emails | Wrong Gmail account | Use the account receiving IONOS forwards from `mel.neine@cadorim.com` |
| Permission denied pushing to GitHub | Not added to org or wrong remote | Ask Dr Neine to verify your access |

---

## When you're set up — what's next

1. Read `HANDOVER/README.md` and `HANDOVER/PROJECT_MEMORY.md` cover to cover
2. Skim `../CLAUDE.md` for the deep technical reference (the repo's CLAUDE.md)
3. Open `HANDOVER/NEXT_STEPS.md` and pick **P2** (TerraPay TPFN fix) as your first task — smallest, unblocks the most
4. Tell Claude: "I'm picking up the Cadorim Accounting Engine handover. Let's start with P2 from NEXT_STEPS.md." Claude takes it from there.
5. Push your fix on a branch, open a PR, tag Dr Neine for review.

---

**Questions?** Architecture decisions → Dr Neine. Execution → Claude. The two of you can move very fast once the setup is right.
