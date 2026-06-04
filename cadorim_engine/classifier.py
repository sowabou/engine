"""Classifier: maps wallet_db_transactions rows to canonical engine events.

Phase 1b: All 14 DB types → 7 partners across 5 business flows.
"""
import re

# Fixed FX defaults. TODO Phase 2: per-transaction FX from transactions_devises
FX_EUR = 42.5
FX_USD = 39.0
FX_BRIDGE = 44.5

# Key account IDs
TERRAPAY_ACCT = 422
RIA_CASHOUT_ACCT = 782
JUBA_ACCT = 778
BRIDGE_ACCT = 808
CADORIM_TRANSFERT_ACCT = 501
SEDAD_ACCT = 16
MASRVI_ACCT = 21
CLICK_ACCT = 20
BANKILY_ACCT = 825
CHARGE_AGENT_ACCT = 440

# Credit account → Local_Par_n mapping
_CREDIT_MAP = {
    16: "sedad", 18: "caisse_cadorim", 19: "caisse_imara", 20: "click",
    21: "masrvi", 33: "caisse_mboirick", 35: "caisse_seilibaby",
    782: "ria_cash_out", 825: "bankily",
}

# Type dispatch table
_TYPE_DISPATCH = {
    'ria': '_classify_ria',
    'juba': '_classify_juba',
    'transfert_cadorim': '_classify_bridge_inbound',
    'retrait_commande': '_classify_sndp_payout',
    'depot': '_classify_wallet_deposit',
    'retrait': '_classify_wallet_cashout',
    'transfert_extra': '_classify_wallet_cashout',
    'commission': '_classify_agent_commission',
    'alimentation_compte': '_classify_agent_funding',
    'virement_interne': '_classify_treasury',
    'regularisation': '_classify_treasury',
    'recharge telephonique': '_classify_telecom',
    'paiement': '_classify_merchant',
    'transfert': '_classify_transfert',
}


def _slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def _infer_local_par(row: dict, accounts: dict) -> str:
    cid = row.get('creditable_id')
    if cid is not None:
        cid = int(cid)
        if cid in _CREDIT_MAP:
            return _CREDIT_MAP[cid]
        acct = accounts.get(cid, {})
        name = acct.get('name', f'account_{cid}')
        atype = acct.get('type', '')
        if atype == 'main' and any(w in name.lower() for w in ('bankily', 'click', 'mauripay')):
            return 'wallet_' + _slugify(name)
        return "caisse_" + _slugify(name)
    return "caisse_unknown"


def _status_map(row):
    s = (row.get('status') or '').strip().lower()
    a = (row.get('accounting_status') or '').strip().lower()
    if s in ('completed',) and a in ('posted', ''):
        return 'released', str(row['created_at'])
    if s in ('pending',) or a in ('waiting',):
        return 'pending', None
    return 'released', str(row['created_at'])


def _build_event(row, accounts, *, partner, currency, flow_type, flow_subtype,
                 flow_category, rate=0, commission=None, commission_pct=0, commission_fixed=0):
    amount_mru = float(row.get('amount') or 0)
    if commission is not None:
        comm = float(commission)
    elif commission_pct > 0 and rate > 0:
        comm = round(amount_mru / rate * commission_pct, 2)
    elif commission_fixed > 0:
        comm = commission_fixed
    else:
        comm = float(row.get('commission') or 0)
    amount_j = round(amount_mru / rate, 2) if rate > 0 else amount_mru
    status, posted_at = _status_map(row)
    local_par = _infer_local_par(row, accounts)
    return {
        "id": f"T-{partner}-{row['id']}",
        "created_at": str(row['created_at']),
        "posted_at": posted_at,
        "status": status,
        "Par_l": partner,
        "Cur_k": currency,
        "Amount_j": amount_j,
        "Client_i": None,
        "Client_m": str(row.get('description') or ''),
        "Local_Par_n": local_par,
        "Amount_mru_h": amount_mru,
        "commission_a": comm,
        "cost_payout_a": 0,
        "fx_gain_a": 0,
        "profit_transaction_a": comm,
        "reference": str(row.get('reference') or ''),
        "source_row_id": row['id'],
        "type": flow_type,
        "flow_subtype": flow_subtype,
        "flow_category": flow_category,
        "db_type": (row.get('type') or ''),
        "date": str(row['created_at']),
    }


def _classify_ria(row, accounts):
    return _build_event(row, accounts, partner='ria', currency='EUR', rate=FX_EUR,
                        flow_type='international', flow_subtype='international',
                        flow_category='revenue', commission_fixed=float(row.get('commission') or 25))


def _classify_juba(row, accounts):
    return _build_event(row, accounts, partner='juba', currency='EUR', rate=FX_EUR,
                        flow_type='international', flow_subtype='international',
                        flow_category='revenue', commission_pct=0.01)


def _classify_bridge_inbound(row, accounts):
    return _build_event(row, accounts, partner='bridge', currency='EUR', rate=FX_BRIDGE,
                        flow_type='international', flow_subtype='international',
                        flow_category='revenue')


def _classify_sndp_payout(row, accounts):
    return _build_event(row, accounts, partner='sndp', currency='MRU', rate=0,
                        flow_type='b2c_payout', flow_subtype='b2c_payout',
                        flow_category='revenue')


def _classify_wallet_deposit(row, accounts):
    return _build_event(row, accounts, partner='wallet', currency='MRU', rate=0,
                        flow_type='wallet_deposit', flow_subtype='wallet_deposit',
                        flow_category='internal')


def _classify_wallet_cashout(row, accounts):
    frais = float(row.get('frais') or 0)
    return _build_event(row, accounts, partner='wallet', currency='MRU', rate=0,
                        flow_type='wallet_cashout', flow_subtype='wallet_cashout',
                        flow_category='internal', commission=frais)


def _classify_agent_commission(row, accounts):
    return _build_event(row, accounts, partner='agent', currency='MRU', rate=0,
                        flow_type='agent_commission', flow_subtype='agent_commission',
                        flow_category='internal')


def _classify_agent_funding(row, accounts):
    return _build_event(row, accounts, partner='agent', currency='MRU', rate=0,
                        flow_type='agent_funding', flow_subtype='agent_funding',
                        flow_category='internal')


def _classify_treasury(row, accounts):
    return _build_event(row, accounts, partner='treasury', currency='MRU', rate=0,
                        flow_type='treasury', flow_subtype='treasury',
                        flow_category='internal')


def _classify_telecom(row, accounts):
    return _build_event(row, accounts, partner='ancillary', currency='MRU', rate=0,
                        flow_type='ancillary', flow_subtype='telecom',
                        flow_category='ancillary')


def _classify_merchant(row, accounts):
    return _build_event(row, accounts, partner='ancillary', currency='MRU', rate=0,
                        flow_type='ancillary', flow_subtype='merchant',
                        flow_category='ancillary')


def _classify_transfert(row, accounts):
    """Sub-dispatch the overloaded 'transfert' type by account pattern."""
    dt = row.get('debitable_type') or ''
    ct = row.get('creditable_type') or ''
    did = int(row.get('debitable_id') or 0)
    cid = int(row.get('creditable_id') or 0)
    d_acct = accounts.get(did, {}) if dt.endswith('Account') else {}
    c_acct = accounts.get(cid, {}) if ct.endswith('Account') else {}

    # TerraPay transit
    if did == TERRAPAY_ACCT:
        return _build_event(row, accounts, partner='terrapay', currency='USD', rate=FX_USD,
                            flow_type='international', flow_subtype='international',
                            flow_category='revenue', commission_pct=0.005)
    # Ria cashout via transfert
    if did == RIA_CASHOUT_ACCT:
        return _build_event(row, accounts, partner='ria', currency='EUR', rate=FX_EUR,
                            flow_type='international', flow_subtype='international',
                            flow_category='revenue', commission_fixed=float(row.get('commission') or 25))
    # Juba via transfert
    if did == JUBA_ACCT:
        return _build_event(row, accounts, partner='juba', currency='EUR', rate=FX_EUR,
                            flow_type='international', flow_subtype='international',
                            flow_category='revenue', commission_pct=0.01)
    # Wallet P2P: Customer → Customer
    if dt.endswith('Customer') and ct.endswith('Customer'):
        return _build_event(row, accounts, partner='wallet', currency='MRU', rate=0,
                            flow_type='wallet_p2p', flow_subtype='wallet_p2p',
                            flow_category='internal', commission=0)
    # Wallet cashout: Customer → Account(main: sedad/masrvi)
    if dt.endswith('Customer') and cid in (SEDAD_ACCT, MASRVI_ACCT):
        return _build_event(row, accounts, partner='wallet', currency='MRU', rate=0,
                            flow_type='wallet_cashout', flow_subtype='wallet_cashout',
                            flow_category='internal', commission=float(row.get('frais') or 0))
    # Wallet cashout: Customer → Account(cash or main)
    if dt.endswith('Customer') and not ct.endswith('Customer'):
        acct_type = c_acct.get('type', '')
        if acct_type in ('main', 'cash'):
            return _build_event(row, accounts, partner='wallet', currency='MRU', rate=0,
                                flow_type='wallet_cashout', flow_subtype='wallet_cashout',
                                flow_category='internal', commission=float(row.get('frais') or 0))
    # Agent ops: Account(cash) → Account(cash)
    if not dt.endswith('Customer') and not ct.endswith('Customer'):
        if d_acct.get('type') == 'cash' and c_acct.get('type') == 'cash':
            return _build_event(row, accounts, partner='agent', currency='MRU', rate=0,
                                flow_type='agent_operations', flow_subtype='agent_operations',
                                flow_category='internal')
        # Treasury: any other Account → Account
        return _build_event(row, accounts, partner='treasury', currency='MRU', rate=0,
                            flow_type='treasury', flow_subtype='treasury',
                            flow_category='internal')
    # Account → Customer (rare, ~2 rows)
    if not dt.endswith('Customer') and ct.endswith('Customer'):
        if d_acct.get('type') == 'partenaire':
            return _build_event(row, accounts, partner='terrapay', currency='USD', rate=FX_USD,
                                flow_type='international', flow_subtype='international',
                                flow_category='revenue', commission_pct=0.005)
    # Unclassified
    return _build_event(row, accounts, partner='unclassified', currency='MRU', rate=0,
                        flow_type='unclassified', flow_subtype='unclassified',
                        flow_category='internal')


def classify(row: dict, accounts: dict) -> dict | None:
    """Classify one wallet_db_transactions row into a canonical engine event.

    Returns engine event dict or None if the row should be filtered out.
    """
    # Basic sanity filters
    status = (row.get('status') or '').strip().lower()
    acct_status = (row.get('accounting_status') or '').strip().lower()
    if status in ('canceled', 'failed'):
        return None
    if acct_status == 'rejected':
        return None
    if not row.get('created_at'):
        return None
    amount_mru = float(row.get('amount') or 0)
    if amount_mru <= 0:
        return None

    db_type = (row.get('type') or '').strip().lower()
    handler_name = _TYPE_DISPATCH.get(db_type)
    if handler_name:
        handler = globals().get(handler_name)
        if handler:
            return handler(row, accounts)

    # Unknown type — should not happen with the 14 known types
    return _build_event(row, accounts, partner='unclassified', currency='MRU', rate=0,
                        flow_type='unclassified', flow_subtype='unclassified',
                        flow_category='internal')
