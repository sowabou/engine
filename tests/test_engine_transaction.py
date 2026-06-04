"""Tests for engine/transaction.py — Layer 1."""
from decimal import Decimal
from datetime import date
from cadorim_engine.engine.transaction import compute_commission, compute_payout_cost, compute_transaction_fx_gain
from cadorim_engine.models.configurations import PartnerCurrency, PartnerLocalPartner


class TestComputeCommission:
    def test_percentage(self):
        pc = PartnerCurrency(commission_rate=Decimal("0.005"), commission_type="percentage")
        assert compute_commission(pc, Decimal("1000")) == Decimal("5.00")

    def test_zero_rate(self):
        pc = PartnerCurrency(commission_rate=Decimal("0"), commission_type="percentage")
        assert compute_commission(pc, Decimal("500")) == Decimal("0.00")

    def test_fixed(self):
        pc = PartnerCurrency(commission_type="fixed", commission_fixed=Decimal("0.80"))
        assert compute_commission(pc, Decimal("1000")) == Decimal("0.80")

    def test_none_config(self):
        assert compute_commission(None, Decimal("1000")) == Decimal("0")

    def test_high_percentage(self):
        pc = PartnerCurrency(commission_rate=Decimal("0.01"), commission_type="percentage")
        assert compute_commission(pc, Decimal("250")) == Decimal("2.50")


class TestComputePayoutCost:
    def test_fixed(self):
        pl = PartnerLocalPartner(payout_cost=Decimal("50"), payout_cost_type="fixed")
        assert compute_payout_cost(pl, Decimal("10000")) == Decimal("50")

    def test_percentage(self):
        pl = PartnerLocalPartner(payout_cost=Decimal("0.005"), payout_cost_type="percentage")
        assert compute_payout_cost(pl, Decimal("10000")) == Decimal("50.00")

    def test_zero(self):
        pl = PartnerLocalPartner(payout_cost=Decimal("0"), payout_cost_type="fixed")
        assert compute_payout_cost(pl, Decimal("10000")) == Decimal("0")

    def test_none(self):
        assert compute_payout_cost(None, Decimal("10000")) == Decimal("0")


class TestFxGain:
    def test_positive_spread(self):
        class MockConfig:
            def get_fx_rate(self, pid, cid, d):
                from cadorim_engine.models.configurations import FxRate
                return FxRate(partner_rate=Decimal("39.5"), cadorim_rate=Decimal("39.8"))
        # 100 × (39.8 - 39.5) = 30
        assert compute_transaction_fx_gain(Decimal("100"), 1, 1, date(2026, 4, 15), MockConfig()) == Decimal("30.00")

    def test_no_fx_record(self):
        class MockConfig:
            def get_fx_rate(self, pid, cid, d): return None
        assert compute_transaction_fx_gain(Decimal("100"), 1, 1, date(2026, 4, 15), MockConfig()) == Decimal("0")

    def test_mru_flow_no_fx(self):
        """MRU flows: no FX record → gain = 0."""
        class MockConfig:
            def get_fx_rate(self, pid, cid, d): return None
        assert compute_transaction_fx_gain(Decimal("5000"), 4, 4, date(2026, 4, 15), MockConfig()) == Decimal("0")
