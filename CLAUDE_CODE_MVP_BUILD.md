# Cadorim Accounting Engine v2 — Build Instructions for Claude Code

## What You Are Building

A Python microservice called **cadorim_engine** — the Cadorim Accounting Engine. It implements a universal, parameter-driven transaction model for a money transfer company in Mauritania. The engine reads from the production wallet database (TWO primary tables), classifies every transaction into the universal model, computes all Layer 1 and Layer 2 profit fields, and serves dashboards via REST API.

**Critical mindset:** The architect (Dr. Neine) is a mathematician. This system is algebra, not accounting. There are NO pipelines. Every partner is just a value of the parameter `Par_l`. The engine is ONE universal function — never write partner-specific logic.

**What changed from v1:** v1 only read from `partner_db_orders` (cashout orders). v2 reads from BOTH `wallet_db_transactions` (full journal, 18,225 rows) AND `partner_db_orders` (4,623 cashout orders). The `transfert` type in the DB is overloaded across 4 business flows — classification requires account-pattern inspection.

---

## The Mathematical Model

### The Universal Transaction

Every transaction in the system is a tuple:

```
transaction_a = (Client_i, Amount_j, Cur_k, Par_l, Client_m, Local_Par_n, Amount_mru_h)
```

**Parameters:**
- `Client_i` — sender (person or system account sending)
- `Amount_j` — amount sent (in Cur_k)
- `Cur_k` — currency (EUR, USD, USDC, MRU)
- `Par_l` — partner/source (Ria, TerraPay, Juba, cadorim_wallet, cadorim_b2c, cadorim_agent, treasury)
- `Client_m` — receiver
- `Local_Par_n` — payout channel (Sedad, Click, Masrvi, Bankily, MauriPay, wallet_internal, caisses, agents)
- `Amount_mru_h` — final amount in MRU
- `FX_Par_l` — exchange rate applied
- `Bank_t` — settlement account (BMI, BPM, BRED, ETH addresses)

### Five Business Flows, One Model

1. **International Remittance** (Ria, TerraPay, Juba): Full model — FX > 0, Layer 1 + Layer 2
2. **Cadorim Wallet** (national P2P, "MauriPay"): MRU→MRU, FX=0
   - Type A (internal): wallet→wallet, stays in system, cost_payout=0
   - Type B (cashout): wallet→Local_Par_n or Agent, cost_payout >= 0
3. **CadorimPay / B2C**: Business deposits (prefunding) + payouts (internal or external)
4. **Agent Operations**: Agent cashout for all flows, commission distribution, inter-agent movements
5. **Treasury**: Balance transfers, expense payments. Cost only, no revenue.

### Two-Layer Profit Model

**Layer 1 — per transaction_a:**
```
commission_a = commission(Par_l, Cur_k) applied to Amount_j
cost_payout_a = cost_payout(Local_Par_n)
gain_transaction_a = commission_a - cost_payout_a
fx_gain_a = FX spread (partner rate vs Cadorim rate) × Amount_j
profit_transaction_a = gain_transaction_a + fx_gain_a
```

**Layer 2 — per Par_l × Bank_t pair (international only):**
```
gain_sett_Par_l_Bank_t = FX gain at settlement (actual bank conversion vs expected)
```

**Total:** `Total_Profit = Σ profit_transaction_a + Σ gain_sett_Par_l_Bank_t`

### Derived Balances (computed, never manually set)
```
Balance_Local_Par_n = Σ inflows - Σ payouts
Balance_Bank_t = Σ settlements - Σ withdrawals
Receivable_Par_l = Σ Amount_j where settlement pending (international only)
Payable_Local_Par_n = Σ Amount_mru_h where payout pending
```

---

## Production Database — Verified Structure

Production system is PHP microservices on Azure MySQL. Five SQL dump files available in `Data API transaction /` folder.

### PRIMARY TABLE: wallet_db_transactions (18,225 rows)

The FULL double-entry journal. Every money movement. Columns:

| Column | Type | Description |
|---|---|---|
| id | INT | PK |
| debitable_id | INT | Source account ID |
| debitable_type | VARCHAR | `App\Models\Account` or `App\Models\Customer` |
| creditable_id | INT | Destination account ID |
| creditable_type | VARCHAR | `App\Models\Account`, `App\Models\Customer`, `App\Models\Merchant`, or NULL |
| amount | DECIMAL | Amount in MRU |
| frais | DECIMAL | Fees charged |
| commission | DECIMAL | Commission amount |
| tax | DECIMAL | Tax |
| type | VARCHAR | 14 distinct values (see classification below) |
| status | VARCHAR | completed/canceled/failed/pending |
| accounting_status | VARCHAR | posted/rembursed/rejected/waiting |
| description | TEXT | Contains Ria codes, Juba refs, etc. |
| reference | VARCHAR | Primary reference key |
| external_transaction_id | VARCHAR | Links to orders for TerraPay |
| created_at | DATETIME | Transaction timestamp |

### SECONDARY TABLE: partner_db_orders (4,623 rows)

Cashout orders only — payouts via wallet channels. Columns:

| Column | Type | Description |
|---|---|---|
| id | INT | PK |
| reference | VARCHAR | Links to transactions.reference (non-TerraPay) or transactions.external_transaction_id (TerraPay) |
| partner_name | VARCHAR | "terrapay", "cadorim-agent", "mauripay", or NULL |
| sender_name, sender_phone | VARCHAR | Client_i |
| receiver_name, receiver_phone | VARCHAR | Client_m |
| sender_amount | DECIMAL | Amount_j in Cur_k |
| receiver_amount | DECIMAL | Amount_mru_h |
| fee | DECIMAL | Partner-side fee |
| rate | DECIMAL | FX rate (39.0 for USD, 0 for MRU) |
| channel, provider | VARCHAR | Local_Par_n (sedad/masrivi/click/bankily/mauripay) |
| status | VARCHAR | success/failed |
| currency | VARCHAR | USD or MRU |

### SUPPORTING TABLES

**wallet_db_accounts** (818 rows): Chart of accounts with types: main, cash, commission, aggregated, charge, merchant, bank, partenaire, product.

**wallet_db_bank_accounts** (80 rows): External bank/partner accounts with types: account, product, transit, charge.

**wallet_db_transactions_devises** (2,222 rows): FX journal. Columns: transaction_type, rate, currency, debitable_amount, creditable_amount, debitable_id, creditable_id, transaction_id.

### KEY ACCOUNTS MAP

| Account ID | Name | Account Type | Engine Role |
|---|---|---|---|
| 18 | Cadorim | cash | Main caisse hub — Ria payouts, agent ops, wallet |
| 19 | IMARA | cash | Deposit/withdrawal caisse |
| 422 | TERRAPAY - CASH RECU | partenaire | TerraPay receivable/transit |
| 778 | JUBA EXPRESS | partenaire | Juba Express transit |
| 782 | RIA CASH OUT | main | Ria payout source |
| 808 | Bridge EUR | main | CadorimPay EUR inbound |
| 501 | COMPTE CADORIM (transfert) | main | CadorimPay MRU payout |
| 440 | COMPTE CHARGE AGENT | charge | Agent commission expense |
| 16 | SEDAD TRANSACTION AUTOMATIQUE | main | Sedad automated payout |
| 21 | MASRIVI TRANSACTION AUTOMATIQUE | main | Masrivi automated payout |
| 33 | CAISSE - 12_NKTT BMD | cash | Mboirick/BMD caisse |
| 35 | CAISSE - 13_Agence Seilibaby | cash | Seilibaby agent caisse |

---

## CRITICAL: Transaction Classification Logic

The 14 DB `type` values map to the 5 business flows. Most map directly. The exception is `transfert` which is OVERLOADED and must be sub-classified by account pattern.

### Direct mappings (no ambiguity)

```python
DIRECT_TYPE_MAP = {
    "ria":                   "international_remittance",  # Flow 1
    "juba":                  "international_remittance",  # Flow 1
    "transfert_cadorim":     "b2c_inbound",               # Flow 3 (EUR inbound)
    "retrait_commande":      "b2c_payout",                # Flow 3 (MRU payout)
    "depot":                 "wallet_deposit",             # Flow 2 (cash-in)
    "retrait":               "wallet_cashout",             # Flow 2B
    "transfert_extra":       "wallet_cashout",             # Flow 2B
    "commission":            "agent_commission",            # Flow 4
    "alimentation_compte":   "agent_funding",              # Flow 4
    "virement_interne":      "treasury",                   # Flow 5
    "regularisation":        "treasury",                   # Flow 5
    "recharge telephonique": "ancillary_telecom",
    "paiement":              "ancillary_merchant",
}
```

### Sub-classification of `transfert` (6,570 rows)

Classify by inspecting debitable_type, creditable_type, and the account.type of the referenced account IDs:

```python
def classify_transfert(tx, accounts_lookup):
    """
    tx has: debitable_id, debitable_type, creditable_id, creditable_type
    accounts_lookup: dict of account_id → {name, type}
    """
    debit_is_customer = (tx.debitable_type == "App\\Models\\Customer")
    credit_is_customer = (tx.creditable_type == "App\\Models\\Customer")

    # Case 1: Customer → Customer = wallet P2P internal (Flow 2A)
    if debit_is_customer and credit_is_customer:
        return "wallet_p2p_internal"

    # Case 2: TerraPay transit → cash = international (Flow 1)
    if not debit_is_customer:
        debit_acct = accounts_lookup.get(tx.debitable_id, {})
        if debit_acct.get("type") == "partenaire":
            return "international_remittance"  # TerraPay or Juba payout
        if debit_acct.get("id") == 782:  # RIA CASH OUT
            return "international_remittance"

    # Case 3: Customer → Account[main] (SEDAD/MASRIVI) = wallet cashout (Flow 2B)
    if debit_is_customer and not credit_is_customer:
        credit_acct = accounts_lookup.get(tx.creditable_id, {})
        if credit_acct.get("type") == "main":
            return "wallet_cashout"
        if credit_acct.get("type") == "cash":
            return "wallet_cashout"

    # Case 4: Account[cash] → Account[cash] = agent operations (Flow 4)
    if not debit_is_customer and not credit_is_customer:
        debit_acct = accounts_lookup.get(tx.debitable_id, {})
        credit_acct = accounts_lookup.get(tx.creditable_id, {})
        if debit_acct.get("type") == "cash" and credit_acct.get("type") == "cash":
            return "agent_operations"
        # Account[main/cash] → Account[main/cash] but not both cash = treasury
        return "treasury"

    return "unclassified"
```

### Volume by classified flow (expected totals)

| Classified Flow | Txn Count | Amount (MRU) |
|---|---|---|
| Flow 1 — International (ria + juba + transfert_terrapay) | ~7,010 | ~61M |
| Flow 2A — Wallet Internal (Customer→Customer) | ~673 | ~18M |
| Flow 2B — Wallet Cashout (retrait + transfert_extra + transfert→main/cash) | ~2,940 | ~37M |
| Flow 2 — Wallet Deposit (depot) | ~771 | ~15M |
| Flow 3 — B2C (transfert_cadorim + retrait_commande) | ~510 | ~5M |
| Flow 4 — Agent (commission + alimentation + transfert_cash→cash) | ~7,060 | ~37M |
| Flow 5 — Treasury (virement_interne + regularisation) | ~159 | ~99M |

---

## Technology Stack

- **Python 3.11+**
- **FastAPI** — web framework
- **SQLAlchemy 2.0** — ORM (async)
- **PostgreSQL 15+** — engine's own database
- **Alembic** — migrations
- **httpx** — async HTTP client (wallet API)
- **APScheduler** — periodic sync
- **Docker + docker-compose**
- **pytest**

---

## MVP Build Sequence

### Phase 1: Project Skeleton

```
cadorim_engine/
├── __init__.py
├── config.py                  # Settings via pydantic-settings
├── database.py                # PostgreSQL async engine + session
├── models/
│   ├── __init__.py
│   ├── registries.py          # Partner, Bank, LocalPartner, Currency
│   ├── configurations.py      # PartnerCurrency, PartnerBank, PartnerLocalPartner, FxRate
│   └── computed.py            # EngineTransaction, EngineSettlement
├── adapters/
│   ├── __init__.py
│   ├── wallet_api.py          # REST client for wallet microservices
│   ├── mapper.py              # Maps API response → transaction_a tuple
│   └── classifier.py          # NEW: Classifies transactions by account pattern
├── engine/
│   ├── __init__.py
│   ├── transaction.py         # Layer 1 computation
│   ├── settlement.py          # Layer 2 computation
│   ├── balances.py            # Derived balances
│   └── controls.py            # Automated validation checks
├── api/
│   ├── __init__.py
│   ├── app.py                 # FastAPI application
│   ├── routes/
│   │   ├── registries.py      # CRUD for registries
│   │   ├── configurations.py  # CRUD for config tables
│   │   ├── transactions.py    # Query engine_transactions
│   │   ├── settlements.py     # Query engine_settlements
│   │   └── dashboards.py      # CEO, Operations, Treasury endpoints
│   └── schemas/
│       ├── registries.py
│       ├── configurations.py
│       ├── transactions.py
│       └── dashboards.py
├── scheduler/
│   ├── __init__.py
│   └── sync.py                # Periodic pull from wallet API
├── alembic/
│   └── versions/
├── alembic.ini
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── seed_data.py               # Registry + config population
├── load_production.py         # NEW: Load from SQL dumps for validation
└── tests/
    ├── test_classifier.py     # NEW: Classification tests
    ├── test_engine_transaction.py
    ├── test_engine_settlement.py
    ├── test_balances.py
    ├── test_controls.py
    └── test_api.py
```

### Phase 2: Database Models (SQLAlchemy)

#### registries.py — Independent registries

```python
class Partner(Base):
    __tablename__ = "partners"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    # Values: "ria", "terrapay", "juba", "cadorim_wallet", "cadorim_b2c",
    #         "cadorim_agent", "treasury"
    name = Column(String, nullable=False)
    flow_type = Column(String, nullable=False)
    # "international", "wallet", "b2c", "agent", "treasury"
    api_partner_name = Column(String, nullable=True)
    # Maps to orders.partner_name: "terrapay", "mauripay", "cadorim-agent", NULL
    status = Column(String, default="active")
    created_at = Column(DateTime, server_default=func.now())

class Bank(Base):
    __tablename__ = "banks"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    api_bank_account_id = Column(BigInteger, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, server_default=func.now())

class LocalPartner(Base):
    __tablename__ = "local_partners"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # "wallet" / "cash" / "bank_transfer" / "internal"
    api_account_id = Column(BigInteger, nullable=True)  # wallet_db_accounts.id
    status = Column(String, default="active")
    created_at = Column(DateTime, server_default=func.now())

class Currency(Base):
    __tablename__ = "currencies"
    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String, nullable=False)
    decimals = Column(Integer, default=2)
    created_at = Column(DateTime, server_default=func.now())
```

#### configurations.py — Configurable relationships

```python
class PartnerCurrency(Base):
    __tablename__ = "partner_currencies"
    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    commission_rate = Column(Numeric(8, 4), nullable=True)
    commission_type = Column(String, default="percentage")  # "percentage" / "fixed"
    commission_fixed = Column(Numeric(15, 2), nullable=True)
    status = Column(String, default="active")
    __table_args__ = (UniqueConstraint("partner_id", "currency_id"),)

class PartnerBank(Base):
    __tablename__ = "partner_banks"
    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)
    status = Column(String, default="active")
    __table_args__ = (UniqueConstraint("partner_id", "bank_id"),)

class PartnerLocalPartner(Base):
    __tablename__ = "partner_local_partners"
    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    local_partner_id = Column(Integer, ForeignKey("local_partners.id"), nullable=False)
    payout_cost = Column(Numeric(15, 2), default=0)
    payout_cost_type = Column(String, default="fixed")
    status = Column(String, default="active")
    __table_args__ = (UniqueConstraint("partner_id", "local_partner_id"),)

class FxRate(Base):
    __tablename__ = "fx_rates"
    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    date = Column(Date, nullable=False)
    partner_rate = Column(Numeric(12, 6), nullable=False)
    market_rate = Column(Numeric(12, 6), nullable=True)
    cadorim_rate = Column(Numeric(12, 6), nullable=True)
    __table_args__ = (UniqueConstraint("partner_id", "currency_id", "date"),)
```

#### computed.py — Engine output

```python
class EngineTransaction(Base):
    __tablename__ = "engine_transactions"
    id = Column(Integer, primary_key=True)

    # Source identification — can come from EITHER table
    source_table = Column(String, nullable=False)
    # "wallet_db_transactions" or "partner_db_orders"
    source_id = Column(BigInteger, nullable=False)  # ID in source table
    source_reference = Column(String, nullable=False)
    linked_order_id = Column(BigInteger, nullable=True)  # orders.id if linked

    date = Column(DateTime, nullable=False)

    # Classified flow
    flow_type = Column(String, nullable=False)
    # "international_remittance", "wallet_p2p_internal", "wallet_cashout",
    # "wallet_deposit", "b2c_inbound", "b2c_payout", "agent_commission",
    # "agent_funding", "agent_operations", "treasury", "ancillary_telecom",
    # "ancillary_merchant"
    db_type = Column(String, nullable=False)  # Original DB type value

    # Universal parameters
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    local_partner_id = Column(Integer, ForeignKey("local_partners.id"), nullable=True)

    # Accounts (from wallet_db)
    debit_account_id = Column(BigInteger, nullable=True)
    debit_account_type = Column(String, nullable=True)  # Account type from accounts table
    credit_account_id = Column(BigInteger, nullable=True)
    credit_account_type = Column(String, nullable=True)

    # Clients
    sender_name = Column(String, nullable=True)
    sender_phone = Column(String, nullable=True)
    receiver_name = Column(String, nullable=True)
    receiver_phone = Column(String, nullable=True)

    # Amounts
    amount_original = Column(Numeric(15, 2), nullable=False)  # Amount_j in Cur_k
    amount_mru = Column(Numeric(15, 2), nullable=False)       # Amount_mru_h
    fx_rate = Column(Numeric(12, 6), default=0)               # FX_Par_l (0 for MRU flows)

    # Layer 1 — computed by engine
    commission_a = Column(Numeric(15, 2), default=0)
    cost_payout_a = Column(Numeric(15, 2), default=0)
    gain_transaction_a = Column(Numeric(15, 2), default=0)
    fx_gain_a = Column(Numeric(15, 2), default=0)
    profit_transaction_a = Column(Numeric(15, 2), default=0)

    # Fees from source (for reconciliation)
    source_frais = Column(Numeric(15, 2), default=0)
    source_commission = Column(Numeric(15, 2), default=0)

    # Status
    status = Column(String, nullable=False)
    settlement_status = Column(String, default="unsettled")

    # Description from source
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source_table", "source_id"),
    )

class EngineSettlement(Base):
    __tablename__ = "engine_settlements"
    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    date = Column(Date, nullable=False)
    amount_original = Column(Numeric(15, 2), nullable=False)
    amount_converted = Column(Numeric(15, 2), nullable=True)
    settlement_rate = Column(Numeric(12, 6), nullable=True)
    gain_sett = Column(Numeric(15, 2), nullable=True)
    external_reference = Column(String)
    api_devises_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
```

### Phase 3: Classifier (NEW — the key v2 addition)

**adapters/classifier.py** — Classifies every wallet_db_transaction into a flow:

```python
DIRECT_TYPE_MAP = {
    "ria":                   ("international_remittance", "ria"),
    "juba":                  ("international_remittance", "juba"),
    "transfert_cadorim":     ("b2c_inbound", "cadorim_b2c"),
    "retrait_commande":      ("b2c_payout", "cadorim_b2c"),
    "depot":                 ("wallet_deposit", "cadorim_wallet"),
    "retrait":               ("wallet_cashout", "cadorim_wallet"),
    "transfert_extra":       ("wallet_cashout", "cadorim_wallet"),
    "commission":            ("agent_commission", "cadorim_agent"),
    "alimentation_compte":   ("agent_funding", "cadorim_agent"),
    "virement_interne":      ("treasury", "treasury"),
    "regularisation":        ("treasury", "treasury"),
    "recharge telephonique": ("ancillary_telecom", "cadorim_wallet"),
    "paiement":              ("ancillary_merchant", "cadorim_wallet"),
}

# Key account IDs that resolve ambiguity in 'transfert'
TERRAPAY_ACCOUNT_ID = 422   # TERRAPAY - CASH RECU
RIA_CASHOUT_ACCOUNT_ID = 782  # RIA CASH OUT
JUBA_ACCOUNT_ID = 778       # JUBA EXPRESS

def classify_transaction(tx_row, accounts_lookup: dict) -> tuple[str, str]:
    """
    Returns (flow_type, partner_code).

    tx_row: row from wallet_db_transactions
    accounts_lookup: {account_id: {"name": str, "type": str}}
    """
    db_type = tx_row["type"]

    # Direct mapping for non-ambiguous types
    if db_type in DIRECT_TYPE_MAP:
        return DIRECT_TYPE_MAP[db_type]

    # 'transfert' — classify by account pattern
    if db_type == "transfert":
        return classify_transfert(tx_row, accounts_lookup)

    return ("unclassified", "unknown")


def classify_transfert(tx, accounts_lookup):
    debit_is_customer = (tx["debitable_type"] == "App\\Models\\Customer")
    credit_is_customer = (tx["creditable_type"] == "App\\Models\\Customer")

    # Customer → Customer = wallet P2P (Flow 2A)
    if debit_is_customer and credit_is_customer:
        return ("wallet_p2p_internal", "cadorim_wallet")

    # Check debit account
    if not debit_is_customer:
        debit_acct = accounts_lookup.get(int(tx["debitable_id"]), {})

        # TerraPay transit → anywhere
        if debit_acct.get("type") == "partenaire":
            if int(tx["debitable_id"]) == TERRAPAY_ACCOUNT_ID:
                return ("international_remittance", "terrapay")
            if int(tx["debitable_id"]) == JUBA_ACCOUNT_ID:
                return ("international_remittance", "juba")
            return ("international_remittance", "unknown_partner")

        # RIA CASH OUT account
        if int(tx["debitable_id"]) == RIA_CASHOUT_ACCOUNT_ID:
            return ("international_remittance", "ria")

    # Customer → Account = wallet cashout (Flow 2B)
    if debit_is_customer and not credit_is_customer:
        credit_acct = accounts_lookup.get(int(tx["creditable_id"]), {})
        acct_type = credit_acct.get("type", "")
        if acct_type in ("main", "cash"):
            return ("wallet_cashout", "cadorim_wallet")

    # Account → Account (both non-customer)
    if not debit_is_customer and not credit_is_customer:
        debit_acct = accounts_lookup.get(int(tx["debitable_id"]), {})
        credit_acct = accounts_lookup.get(int(tx["creditable_id"]), {})

        # cash → cash = agent operations
        if debit_acct.get("type") == "cash" and credit_acct.get("type") == "cash":
            return ("agent_operations", "cadorim_agent")

        # Any other Account → Account = treasury
        return ("treasury", "treasury")

    return ("unclassified", "unknown")
```

### Phase 4: Mapper (updated for dual-source)

**adapters/mapper.py:**

```python
def map_wallet_transaction(tx_row, flow_type, partner_code, config, accounts_lookup, orders_lookup):
    """
    Maps a wallet_db_transactions row to EngineTransaction.
    Uses the classified flow_type and partner_code.
    Enriches from orders_lookup if a linked order exists.
    """
    partner = config.resolve_partner(partner_code)
    currency_code = "MRU"  # Default for MRU flows

    # For international flows, get currency from linked order or FX journal
    linked_order = orders_lookup.get(tx_row["reference"]) or \
                   orders_lookup.get(tx_row["external_transaction_id"])

    if linked_order:
        currency_code = linked_order["currency"] or "MRU"

    currency = config.resolve_currency(currency_code)

    # Resolve Local_Par_n from credit account or linked order
    local_partner = resolve_local_partner(tx_row, linked_order, accounts_lookup, config)

    # Amounts
    amount_mru = Decimal(str(tx_row["amount"]))
    if linked_order and linked_order.get("sender_amount"):
        amount_original = Decimal(str(linked_order["sender_amount"]))
        fx_rate = Decimal(str(linked_order.get("rate") or 0))
    else:
        amount_original = amount_mru  # MRU flow: Amount_j = Amount_mru_h
        fx_rate = Decimal("0")

    # Compute Layer 1
    pc = config.get_partner_currency(partner.id, currency.id)
    commission_a = compute_commission(pc, amount_original) if pc else Decimal("0")
    cost_payout_a = compute_payout_cost(local_partner, config) if local_partner else Decimal("0")
    gain_a = commission_a - cost_payout_a
    fx_gain_a = compute_fx_gain(amount_original, fx_rate, config, partner.id, currency.id, tx_row["created_at"])
    profit_a = gain_a + fx_gain_a

    return EngineTransactionCreate(
        source_table="wallet_db_transactions",
        source_id=tx_row["id"],
        source_reference=tx_row["reference"],
        linked_order_id=linked_order["id"] if linked_order else None,
        date=tx_row["created_at"],
        flow_type=flow_type,
        db_type=tx_row["type"],
        partner_id=partner.id,
        currency_id=currency.id,
        local_partner_id=local_partner.id if local_partner else None,
        debit_account_id=tx_row["debitable_id"],
        debit_account_type=accounts_lookup.get(int(tx_row["debitable_id"]), {}).get("type"),
        credit_account_id=tx_row["creditable_id"],
        credit_account_type=accounts_lookup.get(int(tx_row["creditable_id"]), {}).get("type") if tx_row["creditable_id"] else None,
        amount_original=amount_original,
        amount_mru=amount_mru,
        fx_rate=fx_rate,
        commission_a=commission_a,
        cost_payout_a=cost_payout_a,
        gain_transaction_a=gain_a,
        fx_gain_a=fx_gain_a,
        profit_transaction_a=profit_a,
        source_frais=Decimal(str(tx_row["frais"] or 0)),
        source_commission=Decimal(str(tx_row["commission"] or 0)),
        status=tx_row["status"],
        description=tx_row.get("description"),
    )
```

### Phase 5: Engine Logic (unchanged from v1)

Same `compute_commission`, `compute_payout_cost`, `compute_fx_gain`, `compute_settlement_gain`, `compute_all_balances`. The algebra doesn't change — only the data source feeding it is now richer.

### Phase 6: FastAPI Routes (unchanged structure)

Same CRUD endpoints for registries, configurations, transactions, settlements, dashboards.

### Phase 7: Dashboard HTML (NEW)

Generate a single `dashboard.html` file that queries the engine API and displays:

**Section 1 — Summary by Flow Type:**
- Row per flow (International, Wallet, B2C, Agent, Treasury)
- Columns: Count, Total Amount MRU, Commission, Cost Payout, Gain, FX Gain, Profit

**Section 2 — International Remittance Detail:**
- By Par_l (Ria, TerraPay, Juba): count, amount, commission, FX gain, profit
- Receivables by partner
- Settlement status

**Section 3 — Wallet Operations:**
- Type A (internal P2P): count, amount
- Type B (cashout): count, amount, by channel (Sedad, Masrvi, Click, Bankily)
- Deposits vs withdrawals

**Section 4 — Agent Network:**
- Agent commission total (our cost)
- Agent balances
- Top agents by volume

**Section 5 — Treasury:**
- Bank balances (Balance_Bank_t)
- Local partner balances (Balance_Local_Par_n)
- Largest movements

**Section 6 — Monthly Trends:**
- Charts: volume by month, profit by month, flow mix evolution

### Phase 8: Seed Data

```python
partners = [
    {"code": "ria", "name": "Ria Money Transfer", "flow_type": "international",
     "api_partner_name": None},  # Ria has no orders, booked directly as type=ria
    {"code": "terrapay", "name": "TerraPay", "flow_type": "international",
     "api_partner_name": "terrapay"},
    {"code": "juba", "name": "Juba Express", "flow_type": "international",
     "api_partner_name": None},
    {"code": "cadorim_wallet", "name": "Cadorim Wallet (MauriPay)", "flow_type": "wallet",
     "api_partner_name": "mauripay"},
    {"code": "cadorim_b2c", "name": "CadorimPay (B2C)", "flow_type": "b2c",
     "api_partner_name": None},
    {"code": "cadorim_agent", "name": "Cadorim Agent Network", "flow_type": "agent",
     "api_partner_name": "cadorim-agent"},
    {"code": "treasury", "name": "Treasury / Internal", "flow_type": "treasury",
     "api_partner_name": None},
]

banks = [
    {"code": "bmi", "name": "BMI", "currency": "EUR"},
    {"code": "bpm", "name": "BPM", "currency": "EUR"},
    {"code": "bred", "name": "BRED", "currency": "EUR"},
    {"code": "eth_cado01", "name": "ETH Cado01", "currency": "USDC"},
    {"code": "eth_cado02", "name": "ETH Cado02", "currency": "USDC"},
]

local_partners = [
    {"code": "sedad", "name": "Sedad", "type": "wallet", "api_account_id": 16},
    {"code": "click", "name": "Click", "type": "wallet"},
    {"code": "masrvi", "name": "Masrvi", "type": "wallet", "api_account_id": 21},
    {"code": "bankily", "name": "Bankily", "type": "wallet"},
    {"code": "mauripay", "name": "MauriPay", "type": "wallet"},
    {"code": "wallet_internal", "name": "Internal Wallet Transfer", "type": "internal"},
    {"code": "caisse_cadorim", "name": "Caisse Cadorim (Main)", "type": "cash", "api_account_id": 18},
    {"code": "caisse_imara", "name": "Caisse IMARA", "type": "cash", "api_account_id": 19},
    {"code": "caisse_mboirick", "name": "Caisse Mboirick/BMD", "type": "cash", "api_account_id": 33},
    {"code": "caisse_seilibaby", "name": "Caisse Seilibaby", "type": "cash", "api_account_id": 35},
]

currencies = [
    {"code": "EUR", "name": "Euro", "decimals": 2},
    {"code": "USD", "name": "US Dollar", "decimals": 2},
    {"code": "USDC", "name": "USD Coin", "decimals": 6},
    {"code": "MRU", "name": "Mauritanian Ouguiya", "decimals": 2},
]

# Config(Par_l, Cur_k) — with commission rates
partner_currencies = [
    {"partner": "ria", "currency": "EUR", "commission_rate": 0.0, "commission_type": "percentage"},
    {"partner": "terrapay", "currency": "USD", "commission_rate": 0.005, "commission_type": "percentage"},
    {"partner": "terrapay", "currency": "USDC", "commission_rate": 0.005, "commission_type": "percentage"},
    {"partner": "terrapay", "currency": "EUR", "commission_rate": 0.005, "commission_type": "percentage"},
    {"partner": "juba", "currency": "EUR", "commission_rate": 0.01, "commission_type": "percentage"},
    {"partner": "cadorim_wallet", "currency": "MRU", "commission_rate": 0.0, "commission_type": "percentage"},
    {"partner": "cadorim_b2c", "currency": "MRU", "commission_rate": 0.0, "commission_type": "percentage"},
    {"partner": "cadorim_agent", "currency": "MRU", "commission_rate": 0.0, "commission_type": "percentage"},
    {"partner": "treasury", "currency": "MRU", "commission_rate": 0.0, "commission_type": "percentage"},
]

# Config(Par_l, Bank_t)
partner_banks = [
    {"partner": "ria", "bank": "bmi"},
    {"partner": "ria", "bank": "bred"},
    {"partner": "terrapay", "bank": "bmi"},
    {"partner": "terrapay", "bank": "eth_cado01"},
    {"partner": "terrapay", "bank": "eth_cado02"},
    {"partner": "juba", "bank": "bpm"},
]
```

### Phase 9: Production Data Loader (NEW)

**load_production.py** — Loads the 5 SQL dump files, classifies all transactions, and populates engine_transactions:

```python
def load_production_data():
    """
    1. Parse SQL dumps into SQLite (same as existing load_dumps.py)
    2. Build accounts_lookup from wallet_db_accounts
    3. Build orders_lookup (by reference AND by order fields)
    4. For each row in wallet_db_transactions:
       a. classify_transaction() → (flow_type, partner_code)
       b. map_wallet_transaction() → EngineTransaction
       c. Insert into engine_transactions
    5. For each row in transactions_devises:
       a. Map to EngineSettlement
    6. Print summary: count by flow_type, total amounts, profit breakdown
    """
```

### Phase 10: Tests

```python
# test_classifier.py
def test_ria_direct():
    """type=ria → international_remittance, ria"""
def test_transfert_customer_to_customer():
    """type=transfert, Customer→Customer → wallet_p2p_internal"""
def test_transfert_terrapay_transit():
    """type=transfert, debitable_id=422 → international_remittance, terrapay"""
def test_transfert_customer_to_sedad():
    """type=transfert, Customer→Account[main:16] → wallet_cashout"""
def test_transfert_cash_to_cash():
    """type=transfert, Account[cash]→Account[cash] → agent_operations"""
def test_virement_interne_is_treasury():
    """type=virement_interne → treasury"""
def test_commission_is_agent():
    """type=commission → agent_commission"""

# test_engine_transaction.py
def test_compute_commission_percentage()
def test_compute_commission_fixed()
def test_compute_payout_cost()
def test_compute_fx_gain_usd()
def test_compute_fx_gain_mru_is_zero()
def test_profit_formula()

# test_balances.py
def test_local_partner_balance()
def test_receivable_by_partner()

# test_controls.py
def test_duplicate_detection()
def test_fx_anomaly_detection()
def test_amount_mismatch_detection()
```

---

## ABSOLUTE RULES

1. **NEVER write partner-specific logic.** No `if partner == "ria"`. Everything is parameterized. The ONLY exception is the classifier which maps account IDs → partner codes, and even there the IDs come from configuration.
2. **Use Decimal for all money calculations.** Never float.
3. **Two layers always separate.** Transaction profit and settlement gain are never mixed.
4. **Classify by account pattern, not by type string.** The `transfert` type spans 4 flows.
5. **Configuration drives behavior.** The engine code never changes when business changes.
6. **All amounts trace back to source.** Every EngineTransaction links to source_table + source_id.
7. **Controls run before posting.** No transaction stored without validation.
8. **wallet_db_transactions is the master.** partner_db_orders enriches but never overrides.

---

## MVP Definition of Done

The MVP is complete when:
- [ ] All models created and migrated to PostgreSQL
- [ ] Classifier correctly maps all 14 DB types + transfert sub-types to flows
- [ ] Seed data loads all 7 partners, 5 banks, 10+ local partners, 4 currencies
- [ ] Production data loader processes all 18,225 transactions
- [ ] Classification summary matches expected volumes (±5%)
- [ ] Engine computes Layer 1 for every transaction
- [ ] Engine computes Layer 2 for settlement events
- [ ] Derived balances compute correctly
- [ ] Automated controls catch duplicates, FX anomalies, amount mismatches
- [ ] Dashboard HTML displays all 6 sections with real data
- [ ] Three API dashboard endpoints return correct aggregations
- [ ] Docker-compose starts the full stack
- [ ] All tests pass (especially classifier tests)
- [ ] Adding a new partner requires ZERO code changes
