"""Tests for opening balance computation."""
from cadorim_engine.opening import compute_opening

SQLITE = '/tmp/cadorim.sqlite'


def test_opening_returns_dict():
    result = compute_opening(SQLITE, '2026-01-01')
    assert isinstance(result, dict)
    assert 'cash' in result
    assert 'wallet' in result
    assert 'bank' in result
    assert 'opening_receivable' in result


def test_opening_cash_numeric():
    result = compute_opening(SQLITE, '2026-01-01')
    for k, v in result['cash'].items():
        assert isinstance(v, (int, float)), f"cash[{k}] is {type(v)}"


def test_opening_ria_receivable():
    result = compute_opening(SQLITE, '2026-01-01')
    ria = result['opening_receivable']['ria']
    assert ria['foreign'] >= 0
    assert ria['currency'] == 'EUR'
    assert ria['mru'] >= 0
    # Pre-2026 Ria: 1,747 txns, ~15.8M MRU → ~371K EUR
    assert ria['foreign'] > 100000  # at least 100K EUR
