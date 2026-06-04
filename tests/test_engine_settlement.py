"""Tests for engine/settlement.py — Layer 2."""
from decimal import Decimal
from cadorim_engine.engine.settlement import compute_settlement_gain


class TestSettlementGain:
    def test_positive_gain(self):
        assert compute_settlement_gain(Decimal("1000"), Decimal("39800"), Decimal("39.5")) == Decimal("300.00")

    def test_no_gain(self):
        assert compute_settlement_gain(Decimal("1000"), Decimal("39500"), Decimal("39.5")) == Decimal("0.00")

    def test_negative_gain(self):
        assert compute_settlement_gain(Decimal("1000"), Decimal("39000"), Decimal("39.5")) == Decimal("-500.00")

    def test_no_rate(self):
        assert compute_settlement_gain(Decimal("1000"), Decimal("39800"), None) == Decimal("0")

    def test_zero_amounts(self):
        assert compute_settlement_gain(Decimal("0"), Decimal("0"), Decimal("39.5")) == Decimal("0")
