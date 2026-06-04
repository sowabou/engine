"""Simulation tests — validate ALL formulas with hand-calculated expected values.

7 transactions + 1 settlement. Every assertion is derived by hand from the spec.
If these pass, the algebra is correct.
"""
from decimal import Decimal
from pathlib import Path
import pytest

from cadorim_engine.engine.config_loader import EngineConfig
from cadorim_engine.engine.compute import compute_layer1, compute_layer2


@pytest.fixture
def config():
    return EngineConfig.from_json(Path(__file__).parent.parent / "simulation_config.json")


# ══════════════════════════════════════════════════════════════
# SIMULATION TRANSACTIONS
# ══════════════════════════════════════════════════════════════

TRANSACTIONS = [
    # --- International (sim_international) ---
    {"id": "SIM001", "Par_l": "sim_international", "Cur_k": "USD",
     "Amount_j": 1000, "Amount_mru_h": 39000, "Local_Par_n": "sim_sedad", "date": "2026-01-15"},
    {"id": "SIM002", "Par_l": "sim_international", "Cur_k": "USD",
     "Amount_j": 500, "Amount_mru_h": 19500, "Local_Par_n": "sim_click", "date": "2026-01-15"},
    {"id": "SIM003", "Par_l": "sim_international", "Cur_k": "USD",
     "Amount_j": 2000, "Amount_mru_h": 78000, "Local_Par_n": "sim_sedad", "date": "2026-02-01"},
    # --- Wallet P2P (sim_wallet) ---
    {"id": "SIM004", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 5000, "Amount_mru_h": 5000, "Local_Par_n": "sim_internal", "date": "2026-01-20"},
    {"id": "SIM005", "Par_l": "sim_wallet", "Cur_k": "MRU",
     "Amount_j": 15000, "Amount_mru_h": 15000, "Local_Par_n": "sim_internal", "date": "2026-01-21"},
    # --- Agent (sim_agent) ---
    {"id": "SIM006", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 8000, "Amount_mru_h": 8000, "Local_Par_n": "sim_agent_caisse", "date": "2026-01-25"},
    {"id": "SIM007", "Par_l": "sim_agent", "Cur_k": "MRU",
     "Amount_j": 3000, "Amount_mru_h": 3000, "Local_Par_n": "sim_agent_caisse", "date": "2026-01-26"},
]

SETTLEMENT = {
    "id": "SETT001", "Par_l": "sim_international", "Bank_t": "sim_bmi",
    "Amount_s": 3500, "Cur_k": "USD", "date_s": "2026-02-15",
    "fx_settlement_rate": 39.3, "fx_reference_rate": 39.0,
}


# ══════════════════════════════════════════════════════════════
# LAYER 1 TESTS — per transaction
# ══════════════════════════════════════════════════════════════

class TestLayer1International:
    """sim_international: 0.5% commission, fx_spread=0.5, payout via sedad(50) or click(30)."""

    def test_sim001_commission(self, config):
        # 1000 * 0.005 = 5.00
        r = compute_layer1(TRANSACTIONS[0], config)
        assert r["commission_a"] == Decimal("5.00")

    def test_sim001_payout_cost(self, config):
        # sedad: fixed 50
        r = compute_layer1(TRANSACTIONS[0], config)
        assert r["cost_payout_a"] == Decimal("50")

    def test_sim001_fx_gain(self, config):
        # (39.5 - 39.0) * 1000 = 500.00
        r = compute_layer1(TRANSACTIONS[0], config)
        assert r["fx_gain_a"] == Decimal("500.00")

    def test_sim001_gain(self, config):
        # 5.00 - 50 = -45.00
        r = compute_layer1(TRANSACTIONS[0], config)
        assert r["gain_transaction_a"] == Decimal("-45.00")

    def test_sim001_profit(self, config):
        # -45.00 + 500.00 = 455.00
        r = compute_layer1(TRANSACTIONS[0], config)
        assert r["profit_transaction_a"] == Decimal("455.00")

    def test_sim002_commission(self, config):
        # 500 * 0.005 = 2.50
        r = compute_layer1(TRANSACTIONS[1], config)
        assert r["commission_a"] == Decimal("2.50")

    def test_sim002_payout_cost(self, config):
        # click: fixed 30
        r = compute_layer1(TRANSACTIONS[1], config)
        assert r["cost_payout_a"] == Decimal("30")

    def test_sim002_fx_gain(self, config):
        # (39.5 - 39.0) * 500 = 250.00
        r = compute_layer1(TRANSACTIONS[1], config)
        assert r["fx_gain_a"] == Decimal("250.00")

    def test_sim002_profit(self, config):
        # (2.50 - 30) + 250 = 222.50
        r = compute_layer1(TRANSACTIONS[1], config)
        assert r["profit_transaction_a"] == Decimal("222.50")

    def test_sim003_all(self, config):
        # commission = 2000 * 0.005 = 10.00
        # cost = 50 (sedad)
        # fx_gain = 0.5 * 2000 = 1000.00
        # gain = 10 - 50 = -40
        # profit = -40 + 1000 = 960.00
        r = compute_layer1(TRANSACTIONS[2], config)
        assert r["commission_a"] == Decimal("10.00")
        assert r["cost_payout_a"] == Decimal("50")
        assert r["fx_gain_a"] == Decimal("1000.00")
        assert r["gain_transaction_a"] == Decimal("-40.00")
        assert r["profit_transaction_a"] == Decimal("960.00")


class TestLayer1Wallet:
    """sim_wallet: commission=0, cost=0, fx=0. All zeros."""

    def test_sim004_all_zero(self, config):
        r = compute_layer1(TRANSACTIONS[3], config)
        assert r["commission_a"] == Decimal("0")
        assert r["cost_payout_a"] == Decimal("0")
        assert r["fx_gain_a"] == Decimal("0")
        assert r["gain_transaction_a"] == Decimal("0")
        assert r["profit_transaction_a"] == Decimal("0")

    def test_sim005_all_zero(self, config):
        r = compute_layer1(TRANSACTIONS[4], config)
        assert r["profit_transaction_a"] == Decimal("0")


class TestLayer1Agent:
    """sim_agent: commission=0, cost=30 per_transaction, fx=0. Pure cost."""

    def test_sim006_cost(self, config):
        r = compute_layer1(TRANSACTIONS[5], config)
        assert r["commission_a"] == Decimal("0")
        assert r["cost_payout_a"] == Decimal("30")
        assert r["fx_gain_a"] == Decimal("0")
        assert r["profit_transaction_a"] == Decimal("-30")

    def test_sim007_cost(self, config):
        r = compute_layer1(TRANSACTIONS[6], config)
        assert r["profit_transaction_a"] == Decimal("-30")


# ══════════════════════════════════════════════════════════════
# LAYER 2 TEST — settlement (independent)
# ══════════════════════════════════════════════════════════════

class TestLayer2:
    """Settlement gain = (fx_settlement - fx_reference) * Amount_s."""

    def test_sett001_gain(self, config):
        # (39.3 - 39.0) * 3500 = 0.3 * 3500 = 1050.00
        r = compute_layer2(SETTLEMENT, config)
        assert r["gain_sett_s"] == Decimal("1050.00")


# ══════════════════════════════════════════════════════════════
# AGGREGATE TESTS — total profit, per-partner summaries
# ══════════════════════════════════════════════════════════════

class TestAggregates:
    def test_total_layer1_profit(self, config):
        """Sum of all 7 transaction profits."""
        total = sum(compute_layer1(tx, config)["profit_transaction_a"] for tx in TRANSACTIONS)
        # 455.00 + 222.50 + 960.00 + 0 + 0 + (-30) + (-30) = 1577.50
        assert total == Decimal("1577.50")

    def test_total_layer2_gain(self, config):
        total = compute_layer2(SETTLEMENT, config)["gain_sett_s"]
        assert total == Decimal("1050.00")

    def test_grand_total_profit(self, config):
        l1 = sum(compute_layer1(tx, config)["profit_transaction_a"] for tx in TRANSACTIONS)
        l2 = compute_layer2(SETTLEMENT, config)["gain_sett_s"]
        assert l1 + l2 == Decimal("2627.50")

    def test_international_partner_volume(self, config):
        intl = [tx for tx in TRANSACTIONS if tx["Par_l"] == "sim_international"]
        assert len(intl) == 3
        assert sum(Decimal(str(tx["Amount_j"])) for tx in intl) == Decimal("3500")

    def test_wallet_zero_profit(self, config):
        wallet = [tx for tx in TRANSACTIONS if tx["Par_l"] == "sim_wallet"]
        total = sum(compute_layer1(tx, config)["profit_transaction_a"] for tx in wallet)
        assert total == Decimal("0")

    def test_agent_pure_cost(self, config):
        agent = [tx for tx in TRANSACTIONS if tx["Par_l"] == "sim_agent"]
        total = sum(compute_layer1(tx, config)["profit_transaction_a"] for tx in agent)
        assert total == Decimal("-60")

    def test_international_total_commission(self, config):
        intl = [tx for tx in TRANSACTIONS if tx["Par_l"] == "sim_international"]
        total = sum(compute_layer1(tx, config)["commission_a"] for tx in intl)
        # 5.00 + 2.50 + 10.00 = 17.50
        assert total == Decimal("17.50")

    def test_international_total_fx_gain(self, config):
        intl = [tx for tx in TRANSACTIONS if tx["Par_l"] == "sim_international"]
        total = sum(compute_layer1(tx, config)["fx_gain_a"] for tx in intl)
        # 500 + 250 + 1000 = 1750
        assert total == Decimal("1750.00")


# ══════════════════════════════════════════════════════════════
# CONFIG LOADER TESTS
# ══════════════════════════════════════════════════════════════

class TestConfigLoader:
    def test_loads_3_partners(self, config):
        assert len(config.partners) == 3

    def test_international_partner(self, config):
        p = config.get_partner("sim_international")
        assert p.is_international is True
        assert p.currency == "USD"
        assert p.commission.commission_rate == Decimal("0.005")

    def test_wallet_partner(self, config):
        p = config.get_partner("sim_wallet")
        assert p.is_international is False
        assert p.commission.commission_fixed == Decimal("0")

    def test_channel_lookup(self, config):
        ch = config.get_channel_config("sim_international", "sim_sedad")
        assert ch.cost_payout == Decimal("50")
        assert ch.cost_type == "fixed"

    def test_settlement_lookup(self, config):
        sc = config.get_settlement_config("sim_international", "sim_bmi")
        assert sc.fx_settlement_rate == Decimal("39.3")
        assert sc.fx_reference_rate == Decimal("39.0")

    def test_roundtrip(self, config):
        """Export to dict and reload — should match."""
        d = config.to_dict()
        config2 = EngineConfig.from_dict(d)
        assert len(config2.partners) == 3
        assert config2.get_partner("sim_international").commission.commission_rate == Decimal("0.005")
