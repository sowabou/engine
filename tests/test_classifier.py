"""Tests for adapters/classifier.py — flow classification logic."""
from cadorim_engine.adapters.classifier import classify_transaction, _classify_transfert

# Mock accounts lookup
ACCOUNTS = {
    16:  {"id": 16, "name": "SEDAD TRANSACTION AUTOMATIQUE", "type": "main"},
    18:  {"id": 18, "name": "Cadorim", "type": "cash"},
    19:  {"id": 19, "name": "IMARA", "type": "cash"},
    21:  {"id": 21, "name": "MASRIVI TRANSACTION AUTOMATIQUE", "type": "main"},
    33:  {"id": 33, "name": "CAISSE - 12_NKTT BMD", "type": "cash"},
    35:  {"id": 35, "name": "CAISSE - 13_Agence Seilibaby", "type": "cash"},
    159: {"id": 159, "name": "AGENT_COMPTE_49385000", "type": "cash"},
    422: {"id": 422, "name": "TERRAPAY - CASH RECU", "type": "partenaire"},
    501: {"id": 501, "name": "COMPTE CADORIM (transfert)", "type": "main"},
    778: {"id": 778, "name": "JUBA EXPRESS", "type": "partenaire"},
    782: {"id": 782, "name": "RIA CASH OUT", "type": "main"},
    808: {"id": 808, "name": "Bridge EUR", "type": "main"},
}


# ── Direct type mappings ──

class TestDirectMappings:
    def test_ria(self):
        flow, partner = classify_transaction({"type": "ria"}, ACCOUNTS)
        assert flow == "international_remittance"
        assert partner == "ria"

    def test_juba(self):
        flow, partner = classify_transaction({"type": "juba"}, ACCOUNTS)
        assert flow == "international_remittance"
        assert partner == "juba"

    def test_transfert_cadorim(self):
        flow, partner = classify_transaction({"type": "transfert_cadorim"}, ACCOUNTS)
        assert flow == "b2c_inbound"
        assert partner == "cadorim_b2c"

    def test_retrait_commande(self):
        flow, partner = classify_transaction({"type": "retrait_commande"}, ACCOUNTS)
        assert flow == "b2c_payout"
        assert partner == "cadorim_b2c"

    def test_depot(self):
        flow, partner = classify_transaction({"type": "depot"}, ACCOUNTS)
        assert flow == "wallet_deposit"
        assert partner == "cadorim_wallet"

    def test_retrait(self):
        flow, partner = classify_transaction({"type": "retrait"}, ACCOUNTS)
        assert flow == "wallet_cashout"

    def test_transfert_extra(self):
        flow, partner = classify_transaction({"type": "transfert_extra"}, ACCOUNTS)
        assert flow == "wallet_cashout"

    def test_commission(self):
        flow, partner = classify_transaction({"type": "commission"}, ACCOUNTS)
        assert flow == "agent_commission"
        assert partner == "cadorim_agent"

    def test_alimentation_compte(self):
        flow, partner = classify_transaction({"type": "alimentation_compte"}, ACCOUNTS)
        assert flow == "agent_funding"
        assert partner == "cadorim_agent"

    def test_virement_interne(self):
        flow, partner = classify_transaction({"type": "virement_interne"}, ACCOUNTS)
        assert flow == "treasury"
        assert partner == "treasury"

    def test_regularisation(self):
        flow, partner = classify_transaction({"type": "regularisation"}, ACCOUNTS)
        assert flow == "treasury"

    def test_recharge_telephonique(self):
        flow, partner = classify_transaction({"type": "recharge telephonique"}, ACCOUNTS)
        assert flow == "ancillary_telecom"

    def test_paiement(self):
        flow, partner = classify_transaction({"type": "paiement"}, ACCOUNTS)
        assert flow == "ancillary_merchant"


# ── Transfert sub-classification ──

class TestTransfertClassification:
    def test_customer_to_customer_is_wallet_p2p(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Customer",
            "creditable_type": "App\\Models\\Customer",
            "debitable_id": 100, "creditable_id": 200,
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "wallet_p2p_internal"
        assert partner == "cadorim_wallet"

    def test_terrapay_transit_to_account(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Account",
            "creditable_type": "App\\Models\\Account",
            "debitable_id": 422, "creditable_id": 18,
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "international_remittance"
        assert partner == "terrapay"

    def test_juba_account(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Account",
            "creditable_type": "App\\Models\\Account",
            "debitable_id": 778, "creditable_id": 18,
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "international_remittance"
        assert partner == "juba"

    def test_ria_cashout_account(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Account",
            "creditable_type": "App\\Models\\Customer",
            "debitable_id": 782, "creditable_id": 999,
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "international_remittance"
        assert partner == "ria"

    def test_customer_to_sedad_is_wallet_cashout(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Customer",
            "creditable_type": "App\\Models\\Account",
            "debitable_id": 100, "creditable_id": 16,  # SEDAD = main
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "wallet_cashout"
        assert partner == "cadorim_wallet"

    def test_customer_to_masrvi_is_wallet_cashout(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Customer",
            "creditable_type": "App\\Models\\Account",
            "debitable_id": 100, "creditable_id": 21,  # MASRVI = main
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "wallet_cashout"

    def test_customer_to_caisse_is_wallet_cashout(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Customer",
            "creditable_type": "App\\Models\\Account",
            "debitable_id": 100, "creditable_id": 18,  # Cadorim = cash
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "wallet_cashout"

    def test_cash_to_cash_is_agent_operations(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Account",
            "creditable_type": "App\\Models\\Account",
            "debitable_id": 159, "creditable_id": 33,  # both cash
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "agent_operations"
        assert partner == "cadorim_agent"

    def test_main_to_cash_is_treasury(self):
        tx = {
            "type": "transfert",
            "debitable_type": "App\\Models\\Account",
            "creditable_type": "App\\Models\\Account",
            "debitable_id": 501, "creditable_id": 18,  # main → cash
        }
        flow, partner = classify_transaction(tx, ACCOUNTS)
        assert flow == "treasury"
        assert partner == "treasury"

    def test_unknown_type_is_unclassified(self):
        flow, partner = classify_transaction({"type": "some_new_type"}, ACCOUNTS)
        assert flow == "unclassified"
        assert partner == "unknown"
