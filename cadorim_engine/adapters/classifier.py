"""Transaction classifier — maps wallet_db_transactions rows to business flows.

The 14 DB `type` values map to 5 business flows. Most map directly.
The exception is `transfert` (6,570 rows) which is OVERLOADED and must be
sub-classified by inspecting debitable_type, creditable_type, and account patterns.
"""

# Direct type → (flow_type, partner_code) for non-ambiguous types
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
TERRAPAY_ACCOUNT_ID = 422   # TERRAPAY - CASH RECU (partenaire)
RIA_CASHOUT_ACCOUNT_ID = 782  # RIA CASH OUT (main)
JUBA_ACCOUNT_ID = 778       # JUBA EXPRESS (partenaire)

CUSTOMER_TYPE = "App\\Models\\Customer"


def classify_transaction(tx_row: dict, accounts_lookup: dict) -> tuple[str, str]:
    """Classify a wallet_db_transactions row into (flow_type, partner_code).

    Args:
        tx_row: dict with keys from wallet_db_transactions
        accounts_lookup: {account_id: {"name": str, "type": str, "id": int}}

    Returns:
        (flow_type, partner_code) tuple
    """
    db_type = tx_row.get("type", "")

    if db_type in DIRECT_TYPE_MAP:
        return DIRECT_TYPE_MAP[db_type]

    if db_type == "transfert":
        return _classify_transfert(tx_row, accounts_lookup)

    return ("unclassified", "unknown")


def _classify_transfert(tx: dict, accounts_lookup: dict) -> tuple[str, str]:
    """Sub-classify the overloaded 'transfert' type by account pattern."""
    debit_is_customer = (tx.get("debitable_type") == CUSTOMER_TYPE)
    credit_is_customer = (tx.get("creditable_type") == CUSTOMER_TYPE)

    debit_id = _safe_int(tx.get("debitable_id"))
    credit_id = _safe_int(tx.get("creditable_id"))

    # Case 1: Customer → Customer = wallet P2P internal (Flow 2A)
    if debit_is_customer and credit_is_customer:
        return ("wallet_p2p_internal", "cadorim_wallet")

    # Case 2: Non-customer debit — check account identity
    if not debit_is_customer and debit_id is not None:
        debit_acct = accounts_lookup.get(debit_id, {})

        # TerraPay transit account
        if debit_id == TERRAPAY_ACCOUNT_ID:
            return ("international_remittance", "terrapay")

        # Juba account
        if debit_id == JUBA_ACCOUNT_ID:
            return ("international_remittance", "juba")

        # Ria cashout account
        if debit_id == RIA_CASHOUT_ACCOUNT_ID:
            return ("international_remittance", "ria")

        # Any other partenaire account → international
        if debit_acct.get("type") == "partenaire":
            return ("international_remittance", "unknown_partner")

    # Case 3: Customer → Account = wallet cashout (Flow 2B)
    if debit_is_customer and not credit_is_customer:
        credit_acct = accounts_lookup.get(credit_id, {})
        acct_type = credit_acct.get("type", "")
        if acct_type in ("main", "cash") or not credit_acct:
            return ("wallet_cashout", "cadorim_wallet")

    # Case 4: Account → Account (both non-customer)
    if not debit_is_customer and not credit_is_customer:
        debit_acct = accounts_lookup.get(debit_id, {})
        credit_acct = accounts_lookup.get(credit_id, {})

        # cash → cash = agent operations (Flow 4)
        if debit_acct.get("type") == "cash" and credit_acct.get("type") == "cash":
            return ("agent_operations", "cadorim_agent")

        # Any other Account → Account = treasury (Flow 5)
        return ("treasury", "treasury")

    return ("unclassified", "unknown")


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None
