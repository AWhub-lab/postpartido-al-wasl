"""Squad market value from Transfermarkt, joined to IMPECT minutes (experimental).

IMPECT gives, per season and squad, which players played and for how long, plus each
player's Transfermarkt id. Transfermarkt gives each player's dated market value history.
The squad value of a season is the value of its players at the season start, weighted
by the minutes each one played for the squad that season.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import numpy as np
import requests

from .title_race import _write_json, score

TM_URL = 'https://tmapi-alpha.transfermarkt.technology/player/{id}/market-value-history'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
                         'Chrome/128.0 Safari/537.36', 'Accept': 'application/json'}


def _tm_id(player):
    for m in player.get('idMappings') or []:
        ids = m.get('transfermarkt')
        if ids:
            return str(ids[0])
    return None


def season_start(data):
    dates = [m['scheduledDate'][:10] for m in data['matches'] if m.get('scheduledDate')]
    return min(dates) if dates else None


def fetch_rosters(client, folder: Path, datasets):
    """Minutes per player and squad from IMPECT, with Transfermarkt ids. Cached per season."""
    out = {}
    for d in datasets:
        it = d['iteration']['id']
        path = folder/'tm'/f'roster_{it}.json'
        if path.exists() and d['iteration']['season'] < max(x['iteration']['season'] for x in datasets):
            out[str(it)] = json.loads(path.read_text()); continue
        players = {p['id']: p for p in client._get(f'/iterations/{it}/players').get('data', [])}
        roster = {}
        for s in d['squads']:
            rows = client._get(f'/iterations/{it}/squads/{s["id"]}/player-kpis').get('data', []) or []
            minutes = {}
            for r in rows:
                minutes[r['playerId']] = minutes.get(r['playerId'], 0) + (r.get('playDuration') or 0)/60
            roster[str(s['id'])] = [{'impect': pid, 'tm': _tm_id(players.get(pid, {})), 'name': players.get(pid, {}).get('commonname'),
                                     'minutes': round(m, 1)} for pid, m in minutes.items() if m > 0]
            time.sleep(.3)
        _write_json(path, roster)
        out[str(it)] = roster
    return out


def fetch_values(folder: Path, tm_ids, progress=None, pause=(1.5, 3.0)):
    """Dated market value history per Transfermarkt player id, cached on disk (resumable)."""
    cache_dir = folder/'tm'/'players'; cache_dir.mkdir(parents=True, exist_ok=True)
    todo = [i for i in sorted({t for t in tm_ids if t}) if not (cache_dir/f'{i}.json').exists()]
    session = requests.Session()
    for n, pid in enumerate(todo, 1):
        for attempt in range(3):
            try:
                r = session.get(TM_URL.format(id=pid), headers=HEADERS, timeout=20)
                if r.status_code == 429:
                    time.sleep(30*(attempt+1)); continue
                r.raise_for_status()
                hist = [[h['marketValue']['determined'], h['marketValue']['value']]
                        for h in (r.json().get('data') or {}).get('history', []) if (h.get('marketValue') or {}).get('value') is not None]
                _write_json(cache_dir/f'{pid}.json', sorted(hist))
                break
            except (requests.RequestException, ValueError, KeyError, TypeError):
                time.sleep(5*(attempt+1))
        if progress:
            progress(n, len(todo))
        time.sleep(random.uniform(*pause))


def value_at(history, date):
    v = None
    for d, value in history:
        if d > date:
            break
        v = value
    return v


def build_squad_values(folder: Path, datasets, rosters):
    """{iteration: {squad: {...}}}: minute-weighted value of the XI at season start."""
    cache_dir = folder/'tm'/'players'
    out = {}
    for d in datasets:
        it = str(d['iteration']['id']); start = season_start(d)
        if it not in rosters or not start:
            continue
        out[it] = {'season': d['iteration']['season'], 'date': start, 'squads': {}}
        for sid, players in rosters[it].items():
            total = sum(p['minutes'] for p in players) or 1
            weighted = covered = 0.
            vals = []
            for p in players:
                path = cache_dir/f'{p["tm"]}.json' if p['tm'] else None
                hist = json.loads(path.read_text()) if path and path.exists() else []
                v = value_at(hist, start)
                if v is None:  # signed later / no valuation yet: first known value
                    v = hist[0][1] if hist else None
                if v is not None:
                    weighted += v*p['minutes']; covered += p['minutes']; vals.append(v)
            out[it]['squads'][sid] = {
                'xi_value': 11*weighted/covered if covered else None,   # value of the "average XI on the pitch"
                'coverage': round(covered/total, 3), 'players': len(players), 'valued': len(vals)}
    _write_json(folder/'market_tm.json', out)
    return out


def market_series(squad_values):
    """Market value as a dated series per squad (log euros), usable like the ISR in forecast()."""
    series = {}
    for it, season in squad_values.items():
        for sid, s in season['squads'].items():
            if s.get('xi_value'):
                series.setdefault(sid, []).append([season['date'], float(np.log(s['xi_value']))])
    return {k: sorted(v) for k, v in series.items()}


def refresh_market_tm(client, folder: Path, datasets, progress=None):
    complete = [d for d in datasets if d['matches'] and all(score(m) is not None for m in d['matches'])]
    current = max(datasets, key=lambda d: d['iteration']['season'])
    use = sorted(complete, key=lambda d: d['iteration']['season'])[-2:] + [current]
    rosters = fetch_rosters(client, folder, use)
    ids = [p['tm'] for r in rosters.values() for players in r.values() for p in players]
    fetch_values(folder, ids, progress)
    return build_squad_values(folder, use, rosters)


def squad_breakdown(folder: Path, iteration_id, squad_id, date):
    """Per player: minutes, value at `date` and weight in the XI value (weights add up to 11)."""
    roster = json.loads((folder/'tm'/f'roster_{iteration_id}.json').read_text()).get(str(squad_id), [])
    rows = []
    for p in roster:
        path = folder/'tm'/'players'/f'{p["tm"]}.json' if p['tm'] else None
        hist = json.loads(path.read_text()) if path and path.exists() else []
        v = value_at(hist, date)
        rows.append({'name': p.get('name') or str(p['impect']), 'minutes': p['minutes'],
                     'value': v if v is not None else (hist[0][1] if hist else None)})
    total = sum(r['minutes'] for r in rows if r['value'] is not None) or 1
    for r in rows:
        r['weight'] = 11*r['minutes']/total if r['value'] is not None else 0
        r['contribution'] = r['weight']*(r['value'] or 0)
    return sorted(rows, key=lambda r: -r['minutes'])
