"""Auto-generate plafond rules from historical throughput."""
from collections import defaultdict

PRIORITY = {'ria': 1, 'terrapay': 1, 'bridge': 1, 'juba': 2, 'sndp': 2, 'wallet': 3, 'agent': 4}


def generate_plafonds(events):
    """Derive plafond caps from monthly p95 throughput per (Par_l, Local_Par_n)."""
    by_pair_month = defaultdict(lambda: defaultdict(float))
    for e in events:
        par = e.get('Par_l', '')
        chan = e.get('Local_Par_n', '')
        if not par or not chan:
            continue
        month = (e.get('created_at') or '')[:7]
        if month:
            by_pair_month[(par, chan)][month] += float(e.get('Amount_mru_h') or 0)

    rules = []
    for (par, chan), monthly in by_pair_month.items():
        volumes = sorted(monthly.values())
        if not volumes:
            continue
        idx = min(int(len(volumes) * 0.95), len(volumes) - 1)
        p95 = volumes[idx]
        cap = max(100_000.0, p95 * 1.1)
        rules.append({
            "channel": chan,
            "partner": par,
            "plafond": round(cap),
            "priority": PRIORITY.get(par, 5),
        })
    return rules
