"""Mapper — maps wallet_db_transactions rows to EngineTransaction dicts.

Dual-source: wallet_db_transactions is master, partner_db_orders enriches
with client names, FX rate, and foreign-currency amounts.
"""
from decimal import Decimal, InvalidOperation


def safe_decimal(val) -> Decimal:
    if val is None or val == "" or val == "NULL":
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return Decimal("0")


# Known credit_account_id → Local_Par_n code mapping
ACCOUNT_TO_LOCAL = {
    16: "sedad",      # SEDAD TRANSACTION AUTOMATIQUE
    21: "masrvi",     # MASRIVI TRANSACTION AUTOMATIQUE
    20: "click",      # BNM CLICK
    825: "bankily",   # BANKILY API TRANSACTIONS
    18: "caisse_cadorim",  # Cadorim (main caisse)
    19: "caisse_imara",
    33: "caisse_mboirick",
    35: "caisse_seilibaby",
}


def map_wallet_transaction(
    tx_row: dict,
    flow_type: str,
    partner_code: str,
    partner_lookup: dict,
    currency_lookup: dict,
    accounts_lookup: dict,
    orders_by_ref: dict,
    orders_by_ext_id: dict,
) -> dict | None:
    """Map a wallet_db_transactions row to an EngineTransaction field dict.

    Returns dict of fields ready for EngineTransaction creation, or None if unmappable.
    """
    partner = partner_lookup.get(partner_code)
    if not partner:
        return None

    # Try to find linked order (enrichment)
    ref = tx_row.get("reference") or ""
    ext_id = tx_row.get("external_transaction_id") or ""
    linked_order = orders_by_ref.get(ref) or orders_by_ref.get(ext_id) or orders_by_ext_id.get(ext_id)

    # Resolve currency
    if linked_order and linked_order.get("currency") and linked_order["currency"] != "MRU":
        currency_code = linked_order["currency"]
    else:
        currency_code = "MRU"
    currency = currency_lookup.get(currency_code)
    if not currency:
        currency = currency_lookup.get("MRU")

    # Amounts
    amount_mru = safe_decimal(tx_row.get("amount"))
    if linked_order and safe_decimal(linked_order.get("sender_amount")) > 0:
        amount_original = safe_decimal(linked_order["sender_amount"])
        fx_rate = safe_decimal(linked_order.get("rate"))
    else:
        amount_original = amount_mru
        fx_rate = Decimal("0")

    # Resolve local partner from credit account
    credit_id = tx_row.get("creditable_id")
    local_partner_code = None
    if credit_id is not None:
        try:
            local_partner_code = ACCOUNT_TO_LOCAL.get(int(credit_id))
        except (ValueError, TypeError):
            pass
    # Override from linked order channel
    if linked_order:
        ch = (linked_order.get("channel") or "").strip().lower()
        channel_map = {"sedad": "sedad", "click": "click", "masrivi": "masrvi",
                       "masrvi": "masrvi", "bankily": "bankily", "mauripay": "mauripay"}
        if ch in channel_map:
            local_partner_code = channel_map[ch]
    # P2P internal
    if flow_type == "wallet_p2p_internal":
        local_partner_code = "wallet_internal"

    # Client names from linked order
    sender_name = None
    sender_phone = None
    receiver_name = None
    receiver_phone = None
    if linked_order:
        sender_name = linked_order.get("sender_name")
        sender_phone = linked_order.get("sender_phone")
        receiver_name = linked_order.get("receiver_name")
        receiver_phone = linked_order.get("receiver_phone")

    # Debit/credit account types
    debit_id = tx_row.get("debitable_id")
    debit_acct = accounts_lookup.get(int(debit_id), {}) if debit_id is not None else {}
    credit_acct = accounts_lookup.get(int(credit_id), {}) if credit_id is not None else {}

    return {
        "source_table": "wallet_db_transactions",
        "source_id": tx_row["id"],
        "source_reference": ref or str(tx_row["id"]),
        "linked_order_id": linked_order["id"] if linked_order else None,
        "date": tx_row.get("created_at"),
        "flow_type": flow_type,
        "db_type": tx_row.get("type", ""),
        "partner_code": partner_code,
        "partner_id": partner["id"],
        "currency_code": currency_code,
        "currency_id": currency["id"],
        "local_partner_code": local_partner_code,
        "debit_account_id": debit_id,
        "debit_account_type": debit_acct.get("type"),
        "credit_account_id": credit_id,
        "credit_account_type": credit_acct.get("type"),
        "sender_name": sender_name,
        "sender_phone": sender_phone,
        "receiver_name": receiver_name,
        "receiver_phone": receiver_phone,
        "amount_original": amount_original,
        "amount_mru": amount_mru,
        "fx_rate": fx_rate,
        "source_frais": safe_decimal(tx_row.get("frais")),
        "source_commission": safe_decimal(tx_row.get("commission")),
        "status": tx_row.get("status", "completed"),
        "description": tx_row.get("description"),
    }
