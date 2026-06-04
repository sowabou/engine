"""Smoke test for the full export."""
import json, os, tempfile
from load_production import export_all

def test_export_all_full():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        tmp = f.name
    try:
        export_all('2025-01-01', '2026-04-01', tmp)
        with open(tmp) as f:
            d = json.load(f)
        assert len(d['transactions']) >= 15000
        partners = set(t['Par_l'] for t in d['transactions'])
        for p in ['ria','terrapay','juba','bridge','sndp','wallet','agent']:
            assert p in partners, f"Missing partner: {p}"
        unc = sum(1 for t in d['transactions'] if t['Par_l'] == 'unclassified')
        assert unc / len(d['transactions']) < 0.02
        assert 'config' in d
        assert len(d['config']['layer1']) >= 7
    finally:
        os.unlink(tmp)
