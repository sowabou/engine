"""Tests for the Ria classifier."""
import sqlite3
import pytest
from cadorim_engine.classifier import classify

SQLITE = '/tmp/cadorim.sqlite'


@pytest.fixture
def accounts():
    conn = sqlite3.connect(SQLITE)
    conn.row_factory = sqlite3.Row
    accts = {}
    for r in conn.execute("SELECT id, name, type FROM accounts"):
        accts[int(r['id'])] = {'id': int(r['id']), 'name': r['name'], 'type': r['type']}
    conn.close()
    return accts


@pytest.fixture
def ria_rows():
    conn = sqlite3.connect(SQLITE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM transactions WHERE type='ria' LIMIT 5")]
    conn.close()
    return rows


class TestRiaClassifier:
    def test_ria_returns_dict(self, ria_rows, accounts):
        evt = classify(ria_rows[0], accounts)
        assert evt is not None
        assert isinstance(evt, dict)

    def test_ria_has_all_keys(self, ria_rows, accounts):
        evt = classify(ria_rows[0], accounts)
        required = ['id', 'created_at', 'posted_at', 'status', 'Par_l', 'Cur_k',
                     'Amount_j', 'Amount_mru_h', 'Local_Par_n', 'commission_a',
                     'profit_transaction_a', 'reference', 'source_row_id']
        for k in required:
            assert k in evt, f"Missing key: {k}"

    def test_ria_par_l_and_cur(self, ria_rows, accounts):
        for row in ria_rows:
            evt = classify(row, accounts)
            assert evt['Par_l'] == 'ria'
            assert evt['Cur_k'] == 'EUR'

    def test_ria_amounts_positive(self, ria_rows, accounts):
        for row in ria_rows:
            evt = classify(row, accounts)
            assert evt['Amount_j'] > 0
            assert evt['Amount_mru_h'] == row['amount']

    def test_ria_id_prefixed(self, ria_rows, accounts):
        evt = classify(ria_rows[0], accounts)
        assert evt['id'].startswith('T-ria-')

    def test_non_ria_classifies_differently(self, accounts):
        row = {'id': 999, 'type': 'depot', 'status': 'completed', 'accounting_status': 'posted',
               'amount': 1000, 'created_at': '2026-01-15', 'creditable_id': 18}
        evt = classify(row, accounts)
        assert evt is not None  # Phase 1b: all types handled
        assert evt['Par_l'] != 'ria'  # depot is wallet, not ria

    def test_canceled_returns_none(self, accounts):
        row = {'id': 998, 'type': 'ria', 'status': 'canceled', 'accounting_status': 'posted',
               'amount': 1000, 'created_at': '2026-01-15', 'creditable_id': 18}
        assert classify(row, accounts) is None

    def test_five_real_rows_all_classify(self, ria_rows, accounts):
        for row in ria_rows:
            evt = classify(row, accounts)
            assert evt is not None, f"Row {row['id']} returned None"
