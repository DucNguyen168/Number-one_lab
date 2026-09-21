"""Read-only MongoDB research; export reproducible daily walk-forward results."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from app.config import settings
from app.database import MongoDatabase
from app.services.prediction import rank_numbers
from app.services.backtest import _wilson_interval


def selections(history, target, distinct=True):
    ranked = [x['number'] for x in rank_numbers(history, target, 60)['scores']]
    excluded = []
    for draw in reversed(history if distinct else history[-5:]):
        if draw['last_two'] not in excluded:
            excluded.append(draw['last_two'])
        if len(excluded) == 5:
            break
    selected = [n for n in ranked if n not in excluded][:60]
    assert len(set(selected)) == 60 and not set(selected).intersection(excluded)
    return ranked[:60], selected, excluded


def summarize(rows, key, pause=False):
    active = True
    hits = total = streak = longest = 0
    for row in rows:
        hit = row[key]
        if active or not pause:
            total += 1
            hits += hit
            streak = 0 if hit else streak + 1
            longest = max(longest, streak)
        if pause:
            active = hit
    return dict(days=total, hits=hits, misses=total-hits, skipped=len(rows)-total,
                hit_rate=hits/total if total else None,
                wilson_95=_wilson_interval(hits,total),
                longest_loss_streak_across_participating_days=longest)


def main():
    out = Path('reports/recent5_pause')
    out.mkdir(parents=True, exist_ok=True)
    mongo = MongoDatabase(settings)
    try:
        raw = list(mongo.db.draw_results.find({}, {'_id': 0, 'draw_date': 1, 'last_two': 1, 'status': 1}).sort('draw_date', 1))
    finally:
        mongo.close()
    draws = [d for d in raw if d.get('status') != 'conflict']
    assert len({d['draw_date'] for d in draws}) == len(draws)
    assert all(len(d['last_two']) == 2 and d['last_two'].isascii() and d['last_two'].isdigit() for d in draws)
    end = date.fromisoformat(draws[-1]['draw_date'])
    start = end - timedelta(days=364)
    snapshot = json.dumps(draws, ensure_ascii=False, sort_keys=True, indent=2)
    (out/'input_snapshot.json').write_text(snapshot, encoding='utf-8')
    rows = []
    active = True
    for i, actual in enumerate(draws):
        if actual['draw_date'] < start.isoformat():
            continue
        assert i >= 365
        history = draws[:i]
        target = actual['draw_date']
        base, selected, excluded = selections(history, target)
        _, selected5days, _ = selections(history, target, distinct=False)
        hit = actual['last_two'] in selected
        rows.append(dict(date=target, trained_through=history[-1]['draw_date'], actual=actual['last_two'],
                         baseline_hit=actual['last_two'] in base, hit=hit,
                         five_draws_hit=actual['last_two'] in selected5days,
                         participate=active, excluded=' '.join(excluded), selected=' '.join(selected)))
        assert history[-1]['draw_date'] < target
        active = hit
    with (out/'daily.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    observed = {r['date'] for r in rows}
    missing = [(start+timedelta(days=n)).isoformat() for n in range(365) if (start+timedelta(days=n)).isoformat() not in observed]
    result = dict(start=start.isoformat(), end=end.isoformat(), total_observed=len(rows),
                  missing_dates=missing, excluded_conflicts=len(raw)-len(draws),
                  input_sha256=hashlib.sha256(snapshot.encode()).hexdigest(),
                  baseline_top60=summarize(rows,'baseline_hit'),
                  exclude5_every_day=summarize(rows,'hit'),
                  exclude5_pause=summarize(rows,'hit',True),
                  sensitivity_last5draws_pause=summarize(rows,'five_draws_hit',True),
                  monthly={month: summarize([r for r in rows if r['date'].startswith(month)],'hit') for month in sorted({r['date'][:7] for r in rows})})
    (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
