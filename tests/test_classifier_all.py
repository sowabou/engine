"""Tests for the full classifier — all 14 DB types → 7 partners."""
import sqlite3
import pytest
from cadorim_engine.classifier import classify

SQLITE = '/tmp/cadorim.sqlite'

@pytest.fixture
def accounts():
    conn = sqlite3.connect(SQLITE)
    conn.row_factory = sqlite3.Row
    accts = {int(r['id']): dict(r) for r in conn.execute("SELECT id, name, type FROM accounts")}
    conn.close()
    return accts

def _get_row(db_type, n=1):
    conn = sqlite3.connect(SQLITE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM transactions WHERE type=? LIMIT ?", (db_type, n))]
    conn.close()
    return rows

class TestRia:
    def test_ria(self, accounts):
        for r in _get_row('ria', 3):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'ria' and e['Cur_k'] == 'EUR'

class TestJuba:
    def test_juba(self, accounts):
        for r in _get_row('juba', 2):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'juba' and e['Cur_k'] == 'EUR'

class TestBridge:
    def test_bridge_inbound(self, accounts):
        for r in _get_row('transfert_cadorim', 3):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'bridge' and e['flow_subtype'] == 'international'

class TestSNDP:
    def test_sndp_payout(self, accounts):
        for r in _get_row('retrait_commande', 3):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'sndp' and e['flow_subtype'] == 'b2c_payout'

class TestWallet:
    def test_deposit(self, accounts):
        for r in _get_row('depot', 3):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'wallet' and e['flow_subtype'] == 'wallet_deposit'
    def test_cashout(self, accounts):
        for r in _get_row('retrait', 2):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'wallet' and e['flow_subtype'] == 'wallet_cashout'

class TestAgent:
    def test_commission(self, accounts):
        for r in _get_row('commission', 3):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'agent'
    def test_funding(self, accounts):
        for r in _get_row('alimentation_compte', 2):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'agent'

class TestTreasury:
    def test_virement(self, accounts):
        for r in _get_row('virement_interne', 2):
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'treasury'

class TestTransfert:
    def test_terrapay_transit(self, accounts):
        conn = sqlite3.connect(SQLITE)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM transactions WHERE type='transfert' AND debitable_id=422 LIMIT 3")]
        conn.close()
        for r in rows:
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'terrapay'
    def test_customer_p2p(self, accounts):
        conn = sqlite3.connect(SQLITE)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM transactions WHERE type='transfert' AND debitable_type LIKE '%Customer%' AND creditable_type LIKE '%Customer%' LIMIT 3")]
        conn.close()
        for r in rows:
            e = classify(r, accounts)
            assert e and e['Par_l'] == 'wallet' and e['flow_subtype'] == 'wallet_p2p'

class TestFilters:
    def test_canceled_returns_none(self, accounts):
        assert classify({'id':1,'type':'ria','status':'canceled','amount':100,'created_at':'2026-01-01'}, accounts) is None
    def test_zero_amount_returns_none(self, accounts):
        assert classify({'id':1,'type':'ria','status':'completed','amount':0,'created_at':'2026-01-01'}, accounts) is None
    def test_all_events_have_required_keys(self, accounts):
        for r in _get_row('ria', 1) + _get_row('depot', 1) + _get_row('commission', 1):
            e = classify(r, accounts)
            if e:
                for k in ['id','created_at','posted_at','status','Par_l','Cur_k','Amount_j','Amount_mru_h','flow_subtype','flow_category','db_type']:
                    assert k in e, f"Missing {k}"
