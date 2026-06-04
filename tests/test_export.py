"""End-to-end test for the Ria Q1 export."""
import json
import os
import tempfile
from load_production import export_ria_q1


def test_export_produces_valid_json():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        tmp = f.name
    try:
        export_ria_q1(tmp)
        with open(tmp) as f:
            data = json.load(f)

        assert data['scope'] == 'ria_q1_2026'
        assert len(data['transactions']) > 1000
        assert 'opening' in data
        assert 'cash' in data['opening']
        assert 'opening_receivable' in data['opening']

        # Every transaction has required keys
        for tx in data['transactions'][:10]:
            for k in ['id', 'created_at', 'posted_at', 'status', 'Par_l', 'Cur_k', 'Amount_j', 'Amount_mru_h']:
                assert k in tx, f"Missing {k} in transaction {tx.get('id')}"
    finally:
        os.unlink(tmp)
