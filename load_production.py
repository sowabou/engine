"""Load production data from MySQL into a local SQLite cache, classify all
transactions, compute Layer 1.

Reads directly from the MySQL container started by `docker-compose up -d mysql`
(databases `wallet_db` + `partner_db`). Falls back to environment variables:

    MYSQL_HOST   (default 127.0.0.1)
    MYSQL_PORT   (default 3306)
    MYSQL_USER   (default root)
    MYSQL_PASSWORD (default cadorim)

The MySQL rows are mirrored into the SQLite file at SQLITE_PATH so the rest of
the pipeline (classifier, opening, settlements, exports) stays unchanged.

Usage: python load_production.py
"""
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

DATA_DIR = Path(__file__).parent / "data"
SQLITE_PATH = "/tmp/cadorim_v2.sqlite"

# Maps each local SQLite table → (mysql_database, mysql_table).
MYSQL_SOURCES = {
    "accounts":             ("wallet_db",  "accounts"),
    "bank_accounts":        ("wallet_db",  "bank_accounts"),
    "transactions":         ("wallet_db",  "transactions"),
    "transactions_devises": ("wallet_db",  "transactions_devises"),
    "orders":               ("partner_db", "orders"),
    "ria_transactions":     ("partner_db", "ria_transactions"),
}


def _mysql_config():
    return {
        "host":     os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port":     int(os.environ.get("MYSQL_PORT", "3306")),
        "user":     os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", "cadorim"),
        "charset":  "utf8mb4",
        "cursorclass": DictCursor,
    }


def _sqlite_type(mysql_type: str) -> str:
    t = mysql_type.lower()
    if "int" in t:
        return "INTEGER"
    if "double" in t or "float" in t or "decimal" in t:
        return "REAL"
    return "TEXT"


def _to_sqlite_value(v):
    """Convert a MySQL row value into something sqlite3 can store directly."""
    if v is None or isinstance(v, (int, float, str)):
        return v
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return v.decode("utf-8", errors="replace")
    return str(v)


def load_mysql_to_sqlite(db_path: str, batch_size: int = 5000):
    """Mirror the MySQL tables listed in MYSQL_SOURCES into a fresh SQLite db."""
    if os.path.exists(db_path):
        os.remove(db_path)
    sqlite_conn = sqlite3.connect(db_path)
    sqlite_conn.execute("PRAGMA journal_mode=WAL")
    sqlite_conn.execute("PRAGMA synchronous=OFF")

    mysql_conn = pymysql.connect(**_mysql_config())
    try:
        for sqlite_table, (mysql_db, mysql_table) in MYSQL_SOURCES.items():
            print(f"  Pulling {mysql_db}.{mysql_table} → {sqlite_table}...")
            with mysql_conn.cursor() as cur:
                cur.execute(f"DESCRIBE `{mysql_db}`.`{mysql_table}`")
                cols = [(r["Field"], _sqlite_type(r["Type"])) for r in cur.fetchall()]
                col_names = [n for n, _ in cols]

                col_decls = ", ".join(f"`{n}` {t}" for n, t in cols)
                sqlite_conn.execute(f"DROP TABLE IF EXISTS {sqlite_table}")
                sqlite_conn.execute(f"CREATE TABLE {sqlite_table} ({col_decls})")

                placeholders = ",".join("?" * len(col_names))
                insert_sql = (
                    f"INSERT INTO {sqlite_table} "
                    f"({','.join(col_names)}) VALUES ({placeholders})"
                )
                cur.execute(f"SELECT * FROM `{mysql_db}`.`{mysql_table}`")
                total = 0
                while True:
                    rows = cur.fetchmany(batch_size)
                    if not rows:
                        break
                    sqlite_conn.executemany(
                        insert_sql,
                        [tuple(_to_sqlite_value(r[c]) for c in col_names) for r in rows],
                    )
                    total += len(rows)
                sqlite_conn.commit()
                print(f"    {total:,} rows")
    finally:
        mysql_conn.close()
    return sqlite_conn


# Backwards-compatible alias — callers that used to parse SQL dumps now hit MySQL.
def load_sql_to_sqlite(db_path, data_dir=None):
    return load_mysql_to_sqlite(db_path)


# ── Processing ──

sys.path.insert(0, str(Path(__file__).parent))
from cadorim_engine.adapters.classifier import classify_transaction
from cadorim_engine.adapters.mapper import map_wallet_transaction, safe_decimal
from cadorim_engine.engine.transaction import compute_commission, compute_payout_cost
from cadorim_engine.models.configurations import PartnerCurrency, PartnerLocalPartner

# Registries (same as seed_data.py)
PARTNERS = {
    "ria":            {"id": 1, "code": "ria",            "flow_type": "international"},
    "terrapay":       {"id": 2, "code": "terrapay",       "flow_type": "international"},
    "juba":           {"id": 3, "code": "juba",           "flow_type": "international"},
    "cadorim_wallet": {"id": 4, "code": "cadorim_wallet", "flow_type": "wallet"},
    "cadorim_b2c":    {"id": 5, "code": "cadorim_b2c",    "flow_type": "b2c"},
    "cadorim_agent":  {"id": 6, "code": "cadorim_agent",  "flow_type": "agent"},
    "treasury":       {"id": 7, "code": "treasury",       "flow_type": "treasury"},
    "unknown":        {"id": 7, "code": "treasury",       "flow_type": "treasury"},
    "unknown_partner":{"id": 2, "code": "terrapay",       "flow_type": "international"},
}
CURRENCIES = {
    "EUR": {"id": 1, "code": "EUR"}, "USD": {"id": 2, "code": "USD"},
    "USDC": {"id": 3, "code": "USDC"}, "MRU": {"id": 4, "code": "MRU"},
}
PC_CONFIGS = {
    (2, 2): Decimal("0.005"),  # terrapay+USD
    (2, 1): Decimal("0.005"),  # terrapay+EUR
    (2, 3): Decimal("0.005"),  # terrapay+USDC
    (3, 1): Decimal("0.01"),   # juba+EUR
}

FLOW_LABELS = {
    "international_remittance": "Flow 1 — International",
    "wallet_p2p_internal":      "Flow 2A — Wallet P2P",
    "wallet_cashout":           "Flow 2B — Wallet Cashout",
    "wallet_deposit":           "Flow 2 — Wallet Deposit",
    "b2c_inbound":              "Flow 3 — B2C Inbound",
    "b2c_payout":               "Flow 3 — B2C Payout",
    "agent_commission":         "Flow 4 — Agent Commission",
    "agent_funding":            "Flow 4 — Agent Funding",
    "agent_operations":         "Flow 4 — Agent Ops",
    "treasury":                 "Flow 5 — Treasury",
    "ancillary_telecom":        "Ancillary — Telecom",
    "ancillary_merchant":       "Ancillary — Merchant",
    "unclassified":             "UNCLASSIFIED",
}


def process_all(conn):
    conn.row_factory = sqlite3.Row

    # Build lookups
    accounts = {}
    for r in conn.execute("SELECT id, name, type FROM accounts"):
        accounts[int(r["id"])] = {"id": int(r["id"]), "name": r["name"], "type": r["type"]}

    orders_by_ref = {}
    orders_by_ext = {}
    for r in conn.execute("SELECT * FROM orders"):
        o = dict(r)
        if o.get("reference"):
            orders_by_ref[o["reference"]] = o
        if o.get("order_id"):
            orders_by_ext[o["order_id"]] = o

    # Classify and map all wallet_db_transactions
    engine_txs = []
    by_flow = defaultdict(lambda: {"count": 0, "completed": 0, "amount_mru": Decimal("0"),
                                     "commission": Decimal("0"), "profit": Decimal("0"),
                                     "frais": Decimal("0"), "source_comm": Decimal("0")})

    for row in conn.execute("SELECT * FROM transactions ORDER BY id"):
        tx = dict(row)
        flow_type, partner_code = classify_transaction(tx, accounts)

        mapped = map_wallet_transaction(
            tx, flow_type, partner_code,
            PARTNERS, CURRENCIES, accounts, orders_by_ref, orders_by_ext,
        )
        if not mapped:
            continue

        # Compute Layer 1
        pc_rate = PC_CONFIGS.get((mapped["partner_id"], mapped["currency_id"]))
        if pc_rate:
            pc = PartnerCurrency(commission_rate=pc_rate, commission_type="percentage")
            commission = compute_commission(pc, mapped["amount_original"])
        else:
            commission = Decimal("0")

        mapped["commission_a"] = commission
        mapped["cost_payout_a"] = Decimal("0")
        mapped["gain_transaction_a"] = commission
        mapped["fx_gain_a"] = Decimal("0")
        mapped["profit_transaction_a"] = commission

        engine_txs.append(mapped)

        # Aggregate
        f = by_flow[flow_type]
        f["count"] += 1
        if tx["status"] == "completed":
            f["completed"] += 1
        f["amount_mru"] += mapped["amount_mru"]
        f["commission"] += commission
        f["profit"] += commission
        f["frais"] += mapped["source_frais"]
        f["source_comm"] += mapped["source_commission"]

    return engine_txs, by_flow


def print_summary(engine_txs, by_flow):
    sep = "=" * 110
    thin = "-" * 110

    print(f"\n{sep}")
    print("  CADORIM ENGINE v2 — PRODUCTION DATA SUMMARY (ALL 18,225 TRANSACTIONS)")
    print(f"{sep}")

    # 1. By classified flow
    print(f"\n  1. TRANSACTIONS BY CLASSIFIED FLOW")
    print(f"  {thin}")
    print(f"  {'Flow':<35} {'Count':>7} {'OK':>7} {'Volume MRU':>16} {'Commission':>14} {'Src Frais':>12} {'Src Comm':>12}")
    print(f"  {thin}")
    grand_count = 0
    grand_mru = Decimal("0")
    grand_comm = Decimal("0")
    grand_frais = Decimal("0")
    grand_src_comm = Decimal("0")
    for flow in ["international_remittance", "wallet_p2p_internal", "wallet_cashout",
                 "wallet_deposit", "b2c_inbound", "b2c_payout",
                 "agent_commission", "agent_funding", "agent_operations",
                 "treasury", "ancillary_telecom", "ancillary_merchant", "unclassified"]:
        d = by_flow.get(flow)
        if not d:
            continue
        label = FLOW_LABELS.get(flow, flow)
        print(f"  {label:<35} {d['count']:>7,} {d['completed']:>7,} {d['amount_mru']:>16,.0f} "
              f"{d['commission']:>14,.2f} {d['frais']:>12,.2f} {d['source_comm']:>12,.2f}")
        grand_count += d["count"]
        grand_mru += d["amount_mru"]
        grand_comm += d["commission"]
        grand_frais += d["frais"]
        grand_src_comm += d["source_comm"]
    print(f"  {thin}")
    print(f"  {'TOTAL':<35} {grand_count:>7,} {'':>7} {grand_mru:>16,.0f} "
          f"{grand_comm:>14,.2f} {grand_frais:>12,.2f} {grand_src_comm:>12,.2f}")

    # 2. By partner
    by_partner = defaultdict(lambda: {"count": 0, "mru": Decimal("0"), "comm": Decimal("0")})
    for tx in engine_txs:
        p = by_partner[tx["partner_code"]]
        p["count"] += 1
        p["mru"] += tx["amount_mru"]
        p["comm"] += tx["commission_a"]
    print(f"\n  2. BY PARTNER (Par_l)")
    print(f"  {thin}")
    print(f"  {'Partner':<20} {'Count':>8} {'Volume MRU':>16} {'Commission':>14}")
    print(f"  {thin}")
    for p in sorted(by_partner, key=lambda x: -by_partner[x]["mru"]):
        d = by_partner[p]
        print(f"  {p:<20} {d['count']:>8,} {d['mru']:>16,.0f} {d['comm']:>14,.2f}")

    # 3. By local partner (credit account)
    by_local = defaultdict(lambda: {"count": 0, "mru": Decimal("0")})
    for tx in engine_txs:
        lp = tx.get("local_partner_code") or "(none)"
        by_local[lp]["count"] += 1
        by_local[lp]["mru"] += tx["amount_mru"]
    print(f"\n  3. PAYOUT CHANNELS (Local_Par_n)")
    print(f"  {thin}")
    for lp in sorted(by_local, key=lambda x: -by_local[x]["mru"]):
        d = by_local[lp]
        print(f"  {lp:<25} {d['count']:>8,} {d['mru']:>16,.0f}")

    # 4. Spec comparison
    print(f"\n  4. SPEC VOLUME COMPARISON")
    print(f"  {thin}")
    spec = {
        "Flow 1 — International": 7010,
        "Flow 2A — Wallet P2P": 673,
        "Flow 2B — Wallet Cashout": 2940,
        "Flow 2 — Wallet Deposit": 771,
        "Flow 3 (B2C)": 510,
        "Flow 4 (Agent)": 7060,
        "Flow 5 — Treasury": 159,
    }
    actual = {
        "Flow 1 — International": by_flow.get("international_remittance", {}).get("count", 0),
        "Flow 2A — Wallet P2P": by_flow.get("wallet_p2p_internal", {}).get("count", 0),
        "Flow 2B — Wallet Cashout": by_flow.get("wallet_cashout", {}).get("count", 0),
        "Flow 2 — Wallet Deposit": by_flow.get("wallet_deposit", {}).get("count", 0),
        "Flow 3 (B2C)": by_flow.get("b2c_inbound", {}).get("count", 0) + by_flow.get("b2c_payout", {}).get("count", 0),
        "Flow 4 (Agent)": by_flow.get("agent_commission", {}).get("count", 0) + by_flow.get("agent_funding", {}).get("count", 0) + by_flow.get("agent_operations", {}).get("count", 0),
        "Flow 5 — Treasury": by_flow.get("treasury", {}).get("count", 0),
    }
    print(f"  {'Flow':<30} {'Spec':>8} {'Actual':>8} {'Delta':>8} {'%':>8}")
    print(f"  {thin}")
    for flow in spec:
        s, a = spec[flow], actual.get(flow, 0)
        delta = a - s
        pct = f"{100*delta/s:+.1f}%" if s else "-"
        ok = " OK" if abs(delta/s) <= 0.05 else " !!!" if s else ""
        print(f"  {flow:<30} {s:>8,} {a:>8,} {delta:>+8,} {pct:>8}{ok}")

    print(f"\n{sep}")
    print(f"  DONE: {grand_count:,} transactions classified and computed.")
    print(f"  Layer 1 commission total: {grand_comm:,.2f}")
    print(f"  Source frais total: {grand_frais:,.2f}")
    print(f"  Source commission total: {grand_src_comm:,.2f}")
    print(f"{sep}\n")


def main():
    print("=" * 110)
    print("  CADORIM ENGINE v2 — Loading Production Data")
    print("=" * 110)

    print("\n[STEP 1] MySQL → SQLite...")
    conn = load_sql_to_sqlite(SQLITE_PATH, DATA_DIR)

    print("\n[STEP 2] Classifying + mapping + computing Layer 1...")
    engine_txs, by_flow = process_all(conn)

    print("\n[STEP 3] Summary...")
    print_summary(engine_txs, by_flow)

    conn.close()
    print(f"SQLite: {SQLITE_PATH}")


def export_ria_q1(out_path=None):
    """Export Ria Q1 2026 transactions as static JSON for engine.html."""
    import json
    from datetime import datetime
    from cadorim_engine.classifier import classify
    from cadorim_engine.opening import compute_opening

    sqlite_path = "/tmp/cadorim.sqlite"
    if not os.path.exists(sqlite_path):
        # Try cadorim_v2
        if os.path.exists("/tmp/cadorim_v2.sqlite"):
            sqlite_path = "/tmp/cadorim_v2.sqlite"
        else:
            print("SQLite not found — regenerating from dumps...")
            conn = load_sql_to_sqlite(sqlite_path, DATA_DIR)
            conn.close()

    out = out_path or str(Path(__file__).parent / "data" / "production_data_ria.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    # Load accounts lookup
    accounts = {}
    for r in conn.execute("SELECT id, name, type FROM accounts"):
        accounts[int(r['id'])] = {'id': int(r['id']), 'name': r['name'], 'type': r['type']}

    # Classify Ria Q1 2026
    cursor = conn.execute(
        "SELECT * FROM transactions WHERE type='ria' AND created_at >= '2026-01-01' AND created_at < '2026-04-01' ORDER BY created_at"
    )
    transactions = []
    skipped = 0
    total_mru = 0.0
    for row in cursor:
        evt = classify(dict(row), accounts)
        if evt:
            transactions.append(evt)
            total_mru += evt['Amount_mru_h']
        else:
            skipped += 1

    # Opening balances
    opening = compute_opening(sqlite_path, '2026-01-01')

    # Auto-discover channels from transactions
    unique_channels = sorted({t['Local_Par_n'] for t in transactions if t.get('Local_Par_n')})
    channels = [{"code": c, "cost_payout": "0", "cost_type": "fixed"} for c in unique_channels]

    # Build config block matching SIM_CONFIG shape
    # TODO Phase 2: per-txn FX from transactions_devises
    config = {
        "layer1": [{
            "code": "ria",
            "name": "Ria",
            "is_international": True,
            "currency": "EUR",
            "commission_type": "fixed",
            "commission_rate": "0",
            "commission_fixed": "25",
            "fx_partner_rate": "42.0",
            "fx_cadorim_rate": "42.5",
            "fx_market_rate": "42.3",
            "channels": channels,
        }],
        "layer2": [
            {"partner_code": "ria", "bank_code": "bmi", "currency": "EUR",
             "fx_settlement_rate": "42.5", "fx_reference_rate": "42.0"}
        ],
        "plafonds": [],
    }

    result = {
        "generated_at": datetime.now().isoformat(),
        "scope": "ria_q1_2026",
        "cutoff_date": "2026-01-01",
        "opening": opening,
        "config": config,
        "transactions": transactions,
        "settlements": [],
        "withdrawals": [],
        "stats": {
            "rows_scanned": len(transactions) + skipped,
            "rows_classified": len(transactions),
            "rows_skipped": skipped,
            "total_mru": round(total_mru, 2),
            "unique_channels": len(unique_channels),
        }
    }

    with open(out, 'w') as f:
        json.dump(result, f, indent=2, default=str)

    ria_recv = opening['opening_receivable'].get('ria', {})
    print(f"Exported {len(transactions)} Ria transactions to {out}")
    print(f"  Total MRU: {total_mru:,.0f}")
    print(f"  Channels: {len(unique_channels)}")
    print(f"  Skipped: {skipped}")
    print(f"  Opening receivable Ria: {ria_recv.get('foreign',0):,.2f} EUR / {ria_recv.get('mru',0):,.0f} MRU")
    conn.close()
    return result


def export_all(from_date='2025-01-01', to_date='2026-04-01', out_path=None):
    """Export ALL partners across full production window."""
    import json
    from datetime import datetime
    from cadorim_engine.classifier import classify
    from cadorim_engine.opening import compute_opening
    from collections import defaultdict

    sqlite_path = "/tmp/cadorim.sqlite"
    if not os.path.exists(sqlite_path):
        if os.path.exists("/tmp/cadorim_v2.sqlite"):
            sqlite_path = "/tmp/cadorim_v2.sqlite"
        else:
            conn = load_sql_to_sqlite(sqlite_path, DATA_DIR)
            conn.close()

    out = out_path or str(Path(__file__).parent / "data" / "production_data_all.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    accounts = {}
    for r in conn.execute("SELECT id, name, type FROM accounts"):
        accounts[int(r['id'])] = {'id': int(r['id']), 'name': r['name'], 'type': r['type']}

    cursor = conn.execute(
        "SELECT * FROM transactions WHERE created_at >= ? AND created_at < ? ORDER BY created_at",
        (from_date, to_date)
    )
    transactions = []
    skipped = 0
    total_mru = 0.0
    by_partner = defaultdict(lambda: {'count': 0, 'mru': 0.0})
    by_subtype = defaultdict(lambda: {'count': 0, 'mru': 0.0})
    unclassified = 0

    for row in cursor:
        evt = classify(dict(row), accounts)
        if evt:
            transactions.append(evt)
            total_mru += evt['Amount_mru_h']
            bp = by_partner[evt['Par_l']]
            bp['count'] += 1; bp['mru'] += evt['Amount_mru_h']
            bs = by_subtype[evt.get('flow_subtype', '')]
            bs['count'] += 1; bs['mru'] += evt['Amount_mru_h']
            if evt['Par_l'] == 'unclassified':
                unclassified += 1
        else:
            skipped += 1

    # Opening
    cutoff = from_date
    opening = compute_opening(sqlite_path, cutoff)

    # Layer 2: Ingest settlements
    try:
        from cadorim_engine.settlements.ingest import ingest_all as ingest_settlements
        print("  Ingesting Layer 2 settlements...")
        settlements = ingest_settlements(from_date, to_date)
    except Exception as e:
        print(f"  Layer 2 ingestion failed: {e}")
        settlements = []

    # Auto-generate plafond rules
    try:
        from cadorim_engine.plafond_generator import generate_plafonds
        plafond_rules = generate_plafonds(transactions)
        print(f"  Plafond rules generated: {len(plafond_rules)}")
    except Exception as e:
        print(f"  Plafond generation failed: {e}")
        plafond_rules = []

    # Auto-discover channels + build config
    channels_by_partner = defaultdict(set)
    for t in transactions:
        if t.get('Local_Par_n'):
            channels_by_partner[t['Par_l']].add(t['Local_Par_n'])

    PARTNER_DEFS = {
        'ria': {'name':'Ria','is_international':True,'currency':'EUR','commission_type':'fixed','commission_rate':'0','commission_fixed':'25','fx_partner_rate':'42.0','fx_cadorim_rate':'42.5','fx_market_rate':'42.3'},
        'terrapay': {'name':'TerraPay','is_international':True,'currency':'USD','commission_type':'percentage','commission_rate':'0.005','commission_fixed':'0','fx_partner_rate':'39.0','fx_cadorim_rate':'39.0','fx_market_rate':'39.0'},
        'juba': {'name':'Juba Express','is_international':True,'currency':'EUR','commission_type':'percentage','commission_rate':'0.01','commission_fixed':'0','fx_partner_rate':'42.0','fx_cadorim_rate':'42.5','fx_market_rate':'42.3'},
        'bridge': {'name':'Bridge EUR','is_international':True,'currency':'EUR','commission_type':'percentage','commission_rate':'0','commission_fixed':'0','fx_partner_rate':'44.0','fx_cadorim_rate':'44.5','fx_market_rate':'44.3'},
        'sndp': {'name':'SNDP / CadorimPay B2C','is_international':False,'currency':'MRU','commission_type':'fixed','commission_rate':'0','commission_fixed':'0','fx_partner_rate':'0','fx_cadorim_rate':'0','fx_market_rate':'0'},
        'wallet': {'name':'Cadorim Wallet','is_international':False,'currency':'MRU','commission_type':'fixed','commission_rate':'0','commission_fixed':'0','fx_partner_rate':'0','fx_cadorim_rate':'0','fx_market_rate':'0'},
        'agent': {'name':'Agent Network','is_international':False,'currency':'MRU','commission_type':'fixed','commission_rate':'0','commission_fixed':'0','fx_partner_rate':'0','fx_cadorim_rate':'0','fx_market_rate':'0'},
        'treasury': {'name':'Treasury','is_international':False,'currency':'MRU','commission_type':'fixed','commission_rate':'0','commission_fixed':'0','fx_partner_rate':'0','fx_cadorim_rate':'0','fx_market_rate':'0'},
        'ancillary': {'name':'Ancillary','is_international':False,'currency':'MRU','commission_type':'fixed','commission_rate':'0','commission_fixed':'0','fx_partner_rate':'0','fx_cadorim_rate':'0','fx_market_rate':'0'},
        'unclassified': {'name':'Unclassified','is_international':False,'currency':'MRU','commission_type':'fixed','commission_rate':'0','commission_fixed':'0','fx_partner_rate':'0','fx_cadorim_rate':'0','fx_market_rate':'0'},
    }
    layer1 = []
    for par_code in sorted(by_partner.keys()):
        pdef = PARTNER_DEFS.get(par_code, PARTNER_DEFS['unclassified']).copy()
        chans = [{"code": c, "cost_payout": "0", "cost_type": "fixed"} for c in sorted(channels_by_partner.get(par_code, []))]
        pdef['code'] = par_code
        pdef['channels'] = chans
        layer1.append(pdef)

    config = {
        "layer1": layer1,
        "layer2": [
            {"partner_code":"ria","bank_code":"bmi","currency":"EUR","fx_settlement_rate":"42.5","fx_reference_rate":"42.0"},
            {"partner_code":"terrapay","bank_code":"eth_cado02","currency":"USD","fx_settlement_rate":"39.0","fx_reference_rate":"39.0"},
            {"partner_code":"juba","bank_code":"bpm","currency":"EUR","fx_settlement_rate":"42.5","fx_reference_rate":"42.0"},
            {"partner_code":"bridge","bank_code":"bred","currency":"EUR","fx_settlement_rate":"44.5","fx_reference_rate":"44.0"},
        ],
        "plafonds": plafond_rules,
    }

    result = {
        "generated_at": datetime.now().isoformat(),
        "scope": f"all_{from_date}_to_{to_date}",
        "cutoff_date": cutoff,
        "opening": opening,
        "config": config,
        "transactions": transactions,
        "settlements": settlements,
        "withdrawals": [],
        "stats": {
            "rows_scanned": len(transactions) + skipped,
            "rows_classified": len(transactions),
            "rows_skipped": skipped,
            "unclassified": unclassified,
            "total_mru": round(total_mru, 2),
            "by_partner": {k: dict(v) for k, v in by_partner.items()},
            "by_subtype": {k: dict(v) for k, v in by_subtype.items()},
        }
    }

    with open(out, 'w') as f:
        json.dump(result, f, indent=2, default=str)

    print(f"Exported {len(transactions)} events ({len(by_partner)} partners) to {out}")
    print(f"  Total MRU: {total_mru:,.0f}")
    print(f"  Skipped: {skipped}, Unclassified: {unclassified} ({unclassified/max(1,len(transactions))*100:.1f}%)")
    for p in sorted(by_partner):
        print(f"  {p:>15}: {by_partner[p]['count']:>6,} events  {by_partner[p]['mru']:>14,.0f} MRU")
    conn.close()
    return result


def export_all_full():
    return export_all('2025-01-01', '2026-04-01', str(Path(__file__).parent / 'data' / 'production_data_all.json'))


def export_all_q1_2026():
    return export_all('2026-01-01', '2026-04-01', str(Path(__file__).parent / 'data' / 'production_data_all_q1_2026.json'))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'export_ria_q1':
        out = None
        for i, a in enumerate(sys.argv):
            if a == '--out' and i + 1 < len(sys.argv): out = sys.argv[i + 1]
        export_ria_q1(out)
    elif cmd == 'export_all_full':
        export_all_full()
    elif cmd == 'export_all_q1_2026':
        export_all_q1_2026()
    else:
        main()
