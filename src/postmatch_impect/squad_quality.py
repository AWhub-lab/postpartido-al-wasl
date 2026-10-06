"""Squad quality per season from BeSoccer player ELO and market value (descriptive).

BeSoccer files list every player under his CURRENT club, so they cannot tell who played
where in past seasons. IMPECT can: we take the players who actually played for each squad
in each season (with minutes) and look up their BeSoccer ELO / market value for that year,
matching by birth date + a shared name token. Season 23/24 uses BeSoccer year 2023, etc.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

import numpy as np

from .title_race import _write_json

MIN_SHARE = .2   # players with at least 20% of the minutes of the team's most-used player


def _norm(text):
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower()
    return set(re.sub(r'[^a-z ]', ' ', text).split())


def load_besoccer_players(csv_path: Path):
    """{birth_date: [{'name', 'elo': {year: v}, 'value': {year: v}}]} from squad_players_all.csv."""
    by_birth = {}
    with open(csv_path, newline='', encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            if not r.get('birth_date'):
                continue
            try:
                elo = {int(k): float(v) for k, v in json.loads(r.get('elo_series_json') or '{}').items() if v is not None}
                val = {int(k): float(v) for k, v in json.loads(r.get('market_series_json') or '{}').items() if v is not None}
            except (ValueError, TypeError):
                continue
            by_birth.setdefault(r['birth_date'], []).append({'name': r['name'], 'tokens': _norm(r['name']), 'elo': elo, 'value': val})
    return by_birth


def match(player, by_birth):
    cands = by_birth.get(player.get('birthdate') or '', [])
    tokens = _norm(f"{player.get('commonname') or ''} {player.get('firstname') or ''} {player.get('lastname') or ''}")
    hits = [c for c in cands if tokens & c['tokens']]
    return hits[0] if len(hits) == 1 else (max(hits, key=lambda c: len(tokens & c['tokens'])) if hits else None)


def fetch_players(client, folder: Path, iteration_ids):
    """Cache IMPECT player master data (names, birth dates) per season."""
    out = {}
    for it in iteration_ids:
        path = folder/'tm'/f'players_{it}.json'
        if not path.exists():
            _write_json(path, client._get(f'/iterations/{it}/players').get('data', []))
        out[str(it)] = {p['id']: p for p in json.loads(path.read_text())}
    return out


def fetch_roster(client, folder: Path, data):
    """Minutes per player and squad for one season (same cache as market.fetch_rosters)."""
    it = data['iteration']['id']
    path = folder/'tm'/f'roster_{it}.json'
    if path.exists():
        return json.loads(path.read_text())
    roster = {}
    for s in data['squads']:
        rows = client._get(f'/iterations/{it}/squads/{s["id"]}/player-kpis').get('data', []) or []
        minutes = {}
        for r in rows:
            minutes[r['playerId']] = minutes.get(r['playerId'], 0) + (r.get('playDuration') or 0)/60
        roster[str(s['id'])] = [{'impect': pid, 'tm': None, 'name': None, 'minutes': round(m, 1)} for pid, m in minutes.items() if m > 0]
    _write_json(path, roster)
    return roster


def build(folder: Path, datasets, rosters, players, by_birth):
    """{season: {squad: {elo_p75, value_p75, coverage, ...}}} plus the matched player list."""
    out = {}
    for d in sorted(datasets, key=lambda d: d['iteration']['season']):
        it = str(d['iteration']['id']); season = d['iteration']['season']
        year = 2000 + int(season[:2])
        squads = {}
        for sid, roster in rosters.get(it, {}).items():
            top = max((p['minutes'] for p in roster), default=0)
            core = [p for p in roster if p['minutes'] >= MIN_SHARE*top]
            matched, mins_ok = [], 0.
            for p in core:
                bp = match(players.get(it, {}).get(p['impect'], {}), by_birth)
                if bp and (year in bp['elo'] or year in bp['value']):
                    matched.append({'name': bp['name'], 'minutes': p['minutes'], 'elo': bp['elo'].get(year), 'value': bp['value'].get(year)})
                    mins_ok += p['minutes']
            elos = [m['elo'] for m in matched if m['elo'] is not None]
            vals = [m['value'] for m in matched if m['value'] is not None]
            squads[sid] = {
                'elo_p75': float(np.percentile(elos, 75)) if elos else None, 'elo_p50': float(np.median(elos)) if elos else None,
                'value_p75': float(np.percentile(vals, 75)) if vals else None, 'value_p50': float(np.median(vals)) if vals else None,
                'players': len(core), 'matched': len(matched),
                'coverage': round(mins_ok/sum(p['minutes'] for p in core), 3) if core else 0,
                'detail': sorted(matched, key=lambda m: -m['minutes'])}
        out[it] = {'season': season, 'year': year, 'squads': squads}
    _write_json(folder/'squad_quality.json', out)
    return out


def refresh(client, folder: Path, datasets, csv_path: Path):
    ids = [d['iteration']['id'] for d in datasets]
    rosters = {str(d['iteration']['id']): fetch_roster(client, folder, d) for d in datasets}
    players = fetch_players(client, folder, ids)
    return build(folder, datasets, rosters, players, load_besoccer_players(csv_path))


# ---------------------------------------------------------------- BeSoccer per-season squads (real rosters)

BESOCCER_SEASON_TEAMS = {  # BeSoccer team name -> IMPECT squad id
    'Al-Wasl': 2033, 'Al-Ain': 2047, 'Al-Jazira': 2122, 'Shabab Al Ahli Dubai': 2090, 'Sharjah FC': 2093,
    'Al-Wahda': 2041, 'Baniyas': 3393, 'Ajman': 6613, 'Al Nasr Dubai': 6615, 'Al Ittihad Kalba': 6616,
    'Khorfakkan': 6618, 'Hatta Club': 6770, 'Al Dhafra': 11624, 'United FC': 17132, 'Al Bataeh': 6617,
    'Al Orooba': 6614, 'Dibba Al Hisn': 6619, 'Dibba Al Fujairah': 11607, 'Emirates Club': 6769,
}


def _num(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def season_squads(csv_path: Path, only_played=True, p=75):
    """Per season and team: P75 of BeSoccer player ELO and market value from the real season squads.

    ELO = `besoccer_elo`, the best value available: for Al Wasl 26/27 it is the one checked
    player by player on each BeSoccer profile; for everyone else, the squad listing.
    The listing-only P75 is kept as `elo_listing_p75` for reference.
    """
    rows = list(csv.DictReader(open(csv_path, newline='', encoding='utf-8')))
    groups = {}
    for r in rows:
        if only_played and not _num(r.get('minutes')):
            continue
        groups.setdefault((r['season'], r['team']), []).append(r)
    out = []
    for (season, team), players in groups.items():
        elo = [v for v in (_num(r.get('besoccer_elo')) for r in players) if v]
        listing = [v for v in (_num(r.get('besoccer_elo_squad_endpoint') or r.get('besoccer_elo')) for r in players) if v]
        checked = any(r.get('besoccer_elo_source') == 'player_profile_current' for r in players)
        val = [v for v in (_num(r.get('market_value_eur')) for r in players) if v]
        out.append({'season': season, 'team': team, 'id': BESOCCER_SEASON_TEAMS.get(team),
                    'elo_p75': float(np.percentile(elo, p)) if elo else None, 'elo_n': len(elo),
                    'value_p75': float(np.percentile(val, p)) if val else None, 'value_n': len(val),
                    'elo_listing_p75': float(np.percentile(listing, p)) if listing else None, 'profile_checked': checked,
                    'players': len(players)})
    return sorted(out, key=lambda r: (r['season'], r['team']))


# ---------------------------------------------------------------- PLAYER VALUE AVG (0-100)

PV_WEIGHTS = {'elo': .40, 'elo_trend': .10, 'value': .40, 'value_trend': .10}
COHORTS = [(0, 1991, '≤1991'), (1992, 1998, '1992–98'), (1999, 2002, '1999–02'), (2003, 2005, '2003–05'), (2006, 2010, '2006–10'), (2011, 9999, '2011+')]
POSITIONS = {'Goalkeeper': 'GK', 'Defender': 'DEF', 'Midfielder': 'MID', 'Forward': 'ATT'}


def _cohort(birth_year):
    if birth_year is None:
        return None
    return next(label for lo, hi, label in COHORTS if lo <= birth_year <= hi)


def _slope(points):
    """Change per year (least squares) over the given {year: value}; None with fewer than 2 years."""
    if len(points) < 2:
        return None
    xs = np.array(sorted(points), dtype=float); ys = np.array([points[int(x)] for x in xs], dtype=float)
    return float(np.polyfit(xs, ys, 1)[0])


def _pct_change(points, year, window):
    """% change between the first and last value of the last `window` years of BeSoccer's chart."""
    pts = {k: v for k, v in points.items() if year - window + 1 <= k <= year}
    if len(pts) < 2:
        return None
    first, last = pts[min(pts)], pts[max(pts)]
    return (last/first - 1)*100 if first else None


def _season_mean(points, y):
    """Mean of the chart points of the two calendar years of season Y/Y+1 (whichever exist)."""
    vals = [points[k] for k in (y, y + 1) if k in points]
    return float(np.mean(vals)) if vals else None


def _season_trend(points, y, now):
    """% change of this season's figure vs the season average two seasons earlier (fallback: one earlier)."""
    if now is None:
        return None
    for back in (2, 1):
        base = _season_mean(points, y - back)
        if base:
            return (now/base - 1)*100
    return None


def player_value(seasons_csv: Path, series_csv: Path | None = None, window=3, profiles: dict | None = None,
                 arrivals: dict | None = None, current_season='2026/27', mode='general', minutes: dict | None = None):
    """PLAYER VALUE AVG per player and season.

    PV = 0.40·pct(ELO) + 0.10·pct(ELO trend) + 0.40·pct(value) + 0.10·pct(value trend),
    computed twice: within season × birth cohort × position (LEAGUE) and within season × club × position (TEAM).
    AVG = (LEAGUE + TEAM) / 2. Trends: slope over the last `window` years, from the season squads plus
    BeSoccer's yearly series of each player when available. Missing parts are left out and the
    remaining weights rescaled (flagged). Trend = % change over the last 3 years of the BeSoccer
    chart of each player (same definition as the club's Player Value report).

    mode='media': a past season Y/Y+1 uses the mean of the chart points of Y and Y+1 (the whole
    season), and the trend compares that season average with the one two seasons earlier
    (25/26 vs 23/24). The current season keeps today's profile values and winter signings keep
    the data of their arrival year, as in the general model.
    """
    import pandas as pd
    rows = list(csv.DictReader(open(seasons_csv, newline='', encoding='utf-8')))
    series = {}
    if series_csv and Path(series_csv).is_file():
        for r in csv.DictReader(open(series_csv, newline='', encoding='utf-8')):
            try:
                series[r['player_id']] = ({int(k): float(v) for k, v in json.loads(r.get('elo_series_json') or '{}').items() if v},
                                          {int(k): float(v) for k, v in json.loads(r.get('market_series_json') or '{}').items() if v},
                                          r.get('birth_date') or '')
            except (ValueError, TypeError):
                continue
    # Season-file history per player (season start year -> value)
    hist_elo, hist_val = {}, {}
    for r in rows:
        y = int(r['season'][:4])
        e = _num(r.get('besoccer_elo')); v = _num(r.get('market_value_eur'))
        if e:
            hist_elo.setdefault(r['player_id'], {})[y] = e
        if v:
            hist_val.setdefault(r['player_id'], {})[y] = v
    profiles = profiles or {}
    arrivals = arrivals or {}
    now_year = int(current_season[:4])
    out = []
    for r in rows:
        y = int(r['season'][:4]); pid = r['player_id']
        s_elo, s_val, birth = series.get(pid, ({}, {}, ''))
        prof = profiles.get(pid)
        if prof:   # fresh BeSoccer profile chart wins over the older series
            s_elo, s_val = prof['elo'] or s_elo, prof['value'] or s_val
        sid = BESOCCER_SEASON_TEAMS.get(r['team'])
        winter = is_winter_arrival(arrivals, r['season'], sid, r['player']) if sid else False
        elo, value, source, ty = hist_elo.get(pid, {}).get(y), hist_val.get(pid, {}).get(y), 'temporada', y
        # "Dato del momento": what the player was worth while at the club.
        if prof and (r['season'] == current_season or (winter and y + 1 == now_year)):
            elo = prof['elo_current'] or elo; value = prof['market_current_eur'] or value
            source, ty = ('ficha actual' if r['season'] == current_season else 'llegada en invierno'), now_year
        elif winter and prof:
            elo = prof['elo'].get(y + 1, elo); value = prof['value'].get(y + 1, value)
            source, ty = 'llegada en invierno', y + 1
        elif prof and mode == 'media' and any(k in prof[f] for k in (y, y + 1) for f in ('elo', 'value')):
            elo = _season_mean(prof['elo'], y) or elo; value = _season_mean(prof['value'], y) or value
            source = f'media {y}–{y + 1}'
        elif prof and (y in prof['elo'] or y in prof['value']):
            # Past seasons: the point of the player's BeSoccer chart for that year (2025 for 25/26),
            # the same figure the BeSoccer app shows. The squad listing is only a fallback.
            elo = prof['elo'].get(y, elo); value = prof['value'].get(y, value)
            source = f'gráfica {y}'
        try:
            by = int(birth[:4]) if birth[:4].isdigit() else y - int(r['age'])
        except (TypeError, ValueError):
            by = None
        out.append({'season': r['season'], 'year': y, 'team': r['team'], 'id': sid,
                    'player_id': pid, 'player': r['player'], 'pos': POSITIONS.get(r.get('position')), 'cohort': _cohort(by),
                    'minutes': max([_num(r.get('minutes')) or 0] + [m for t, m in (minutes or {}).get((r['season'], sid), [])
                                                                     if same_player(r['player'], t)]),
                    'elo': elo, 'value': value, 'source': source, 'winter': winter,
                    'elo_trend': _season_trend(s_elo, y, elo) if mode == 'media' else _pct_change(s_elo, ty, window),
                    'value_trend': _season_trend(s_val, y, value) if mode == 'media' else _pct_change(s_val, ty, window)})
    df = pd.DataFrame(out)
    no_pos = df.pos.isna()          # BeSoccer without position: listed, but no PV (no peer group)
    df['pos'] = df.pos.fillna('?')
    parts = list(PV_WEIGHTS)
    for scope, keys in (('league', ['season', 'cohort', 'pos']), ('team', ['season', 'team', 'pos'])):
        g = df.groupby(keys, dropna=False)
        pct = {p: g[p].rank(pct=True)*100 for p in parts}
        num = sum(pct[p].fillna(0)*w for p, w in PV_WEIGHTS.items())
        den = sum(pct[p].notna()*w for p, w in PV_WEIGHTS.items())
        df[f'pv_{scope}'] = (num/den.replace(0, np.nan)).round(1)
    df.loc[no_pos, ['pv_league', 'pv_team']] = np.nan
    df['pv_avg'] = ((df.pv_league + df.pv_team)/2).round(1)
    df['incompleto'] = df[parts].isna().any(axis=1)
    return df


# ---------------------------------------------------------------- point-in-time ELO / value ("dato del momento")

def load_profiles(path: Path):
    """BeSoccer profile downloads (scripts/download_besoccer_player_charts.py): {player_id: {...}}."""
    folder = path if path.is_dir() else path.parent/'player_charts'
    out = {}
    records = []
    for f in folder.glob('*.json'):
        try:
            records.append(json.loads(f.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            continue
    combined = folder.parent/'player_charts.json'
    if not records and combined.exists():   # deployed app: one combined file instead of 1,200
        records = list(json.loads(combined.read_text(encoding='utf-8')).values())
    for d in records:
        if d.get('error'):
            continue
        out[str(d['player_id'])] = {'elo_current': d.get('elo_current'), 'market_current_eur': d.get('market_current_eur'),
                                    'elo': {int(k): float(v) for k, v in (d.get('elo_series') or {}).items()},
                                    'value': {int(k): float(v) for k, v in (d.get('market_series') or {}).items()}}
    return out


def winter_arrivals(folder: Path):
    """{(season 'YYYY/YY', impect squad id, normalised name tokens)}: first IMPECT appearance after 1 January.

    Uses IMPECT per-match player lists (data/title_race/tm/appearances_<iteration>.json) only for the
    date; names come from IMPECT player master data (players_<iteration>.json).
    """
    seasons = {'1082': '2024/25', '1499': '2025/26', '2192': '2026/27'}
    out = {}
    for it, season in seasons.items():
        app, pl = folder/'tm'/f'appearances_{it}.json', folder/'tm'/f'players_{it}.json'
        if not app.exists() or not pl.exists():
            continue
        names = {p['id']: _norm(f"{p.get('commonname') or ''} {p.get('firstname') or ''} {p.get('lastname') or ''}") for p in json.loads(pl.read_text())}
        start_year = 2000 + int(season[:2]) if len(season) == 7 and season[2] == '/' else int(season[:4])
        for key, e in json.loads(app.read_text()).items():
            if key.startswith('_'):
                continue
            sid, pid = key.split(':')
            if e['first'] >= f'{int(season[:4])+1}-01-01':
                out.setdefault((season, int(sid)), []).append(names.get(int(pid), set()))
    return out


def _ordered_tokens(name):
    text = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z ]', ' ', text).split()


def same_player(besoccer_name, impect_tokens):
    """Strict name match: the surname must appear, and the first name too (or its initial if abbreviated).

    'C. Puertas' ↔ 'Cameron Puertas' yes; 'Abdelrahman Saleh' ↔ 'Ali Saleh' no.
    """
    parts = _ordered_tokens(besoccer_name)
    if not parts or not impect_tokens:
        return False
    if len(parts) == 1:
        return parts[0] in impect_tokens
    first, last = parts[0], parts[-1]
    if last not in impect_tokens:
        return False
    if len(first) == 1:
        return any(t.startswith(first) for t in impect_tokens if t != last)
    return first in impect_tokens


def is_winter_arrival(arrivals, season, sid, name):
    return any(same_player(name, t) for t in arrivals.get((season, sid), []))


def impect_minutes(folder: Path):
    """{(season, impect squad id): [(name tokens, minutes)]} from IMPECT (more up to date than BeSoccer)."""
    seasons = {'1082': '2024/25', '1499': '2025/26', '2192': '2026/27'}
    out = {}
    for it, season in seasons.items():
        ro, pl = folder/'tm'/f'roster_{it}.json', folder/'tm'/f'players_{it}.json'
        if not ro.exists() or not pl.exists():
            continue
        names = {p['id']: _norm(f"{p.get('commonname') or ''} {p.get('firstname') or ''} {p.get('lastname') or ''}")
                 for p in json.loads(pl.read_text())}
        for sid, players in json.loads(ro.read_text()).items():
            out[(season, int(sid))] = [(names.get(p['impect'], set()), p['minutes']) for p in players]
    return out
