"""Compute opening balances at a cutoff date from the production SQLite dump.

Phase 1c: Real wallet + caisse balances from historical replay.
"""
import re
import sqlite3

FX_EUR = 42.5
FX_USD = 39.0
FX_BRIDGE = 44.5

WALLET_ACCOUNTS = {16: 'sedad', 21: 'masrvi'}
CAISSE_KNOWN = {18: 'caisse_cadorim', 19: 'caisse_imara', 33: 'caisse_mboirick', 35: 'caisse_seilibaby', 782: 'ria_cash_out'}

PARTNER_QUERIES = [
    ('ria',      "type='ria' OR (type='transfert' AND debitable_id=782)", 'EUR', FX_EUR),
    ('terrapay', "type='transfert' AND debitable_id=422",                'USD', FX_USD),
    ('juba',     "type='juba' OR (type='transfert' AND debitable_id=778)", 'EUR', FX_EUR),
    ('bridge',   "type='transfert_cadorim'",                             'EUR', FX_BRIDGE),
]


def _slugify(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def _net_at(conn, account_id, cutoff):
    cr = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE creditable_id=? AND creditable_type LIKE '%Account%' AND status='completed' AND created_at < ?",
        (account_id, cutoff)
    ).fetchone()[0])
    dr = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE debitable_id=? AND debitable_type LIKE '%Account%' AND status='completed' AND created_at < ?",
        (account_id, cutoff)
    ).fetchone()[0])
    return float(cr - dr)


def compute_opening(sqlite_path: str, cutoff_date: str = '2025-01-01') -> dict:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    accounts = {int(r['id']): dict(r) for r in conn.execute("SELECT id, name, type FROM accounts")}

    # Wallet accounts
    wallet_map = dict(WALLET_ACCOUNTS)
    for acct in accounts.values():
        if acct['type'] == 'main':
            name_lower = (acct['name'] or '').lower()
            if 'bankily' in name_lower:
                wallet_map[acct['id']] = 'bankily'
            elif 'click' in name_lower and 'bnm' in name_lower:
                wallet_map[acct['id']] = 'click'
            elif 'mauripay' in name_lower:
                wallet_map[acct['id']] = 'mauripay'

    wallet = {}
    for aid, code in wallet_map.items():
        bal = _net_at(conn, aid, cutoff_date)
        wallet[code] = round(max(0, bal), 2)

    # Caisses — all cash-type accounts with positive balance
    cash = {}
    for acct in accounts.values():
        if acct['type'] == 'cash':
            aid = acct['id']
            if aid in CAISSE_KNOWN:
                code = CAISSE_KNOWN[aid]
            else:
                code = 'caisse_' + _slugify(acct['name'])
            bal = _net_at(conn, aid, cutoff_date)
            if bal > 0:
                cash[code] = round(bal, 2)

    # International receivables
    opening_receivable = {}
    for par, sql_cond, currency, rate in PARTNER_QUERIES:
        sql = f"SELECT COALESCE(SUM(amount),0) FROM transactions WHERE ({sql_cond}) AND status='completed' AND created_at < ?"
        mru = float(conn.execute(sql, (cutoff_date,)).fetchone()[0])
        opening_receivable[par] = {"foreign": round(mru / rate, 2), "currency": currency, "mru": mru}

    conn.close()

    print(f"  Opening balances at {cutoff_date}:")
    print(f"    Wallets: {wallet}")
    print(f"    Caisses ({len(cash)}): total {sum(cash.values()):,.0f} MRU")
    recv_str = ', '.join(f"{k}={v['foreign']:,.0f} {v['currency']}" for k,v in opening_receivable.items())
    print(f"    Receivables: {recv_str}")

    return {
        "cash": cash,
        "wallet": wallet,
        "bank": {"bmi": 0, "bpm": 0, "bred": 0, "eth_cado01": 0, "eth_cado02": 0},
        "client_float": 0,
        "working_capital": 0,
        "opening_receivable": opening_receivable,
    }
