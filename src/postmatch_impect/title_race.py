"""Reproducible exploratory league forecast. No official tie-break claims."""
from __future__ import annotations
import copy
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

VERSION = 'xg-isr-poisson-v4'
SEED = 2033
SIMULATIONS = 20000


def score(row):
    goals = row.get('goals') or {}
    h = (goals.get('home') or {}).get('fullTime')
    a = (goals.get('away') or {}).get('fullTime')
    if h is None or a is None:
        return None
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0 or int(x) != x for x in (h, a)):
        raise ValueError('Marcador no válido')
    return int(h), int(a)


def validate(data):
    ids = [s['id'] for s in data['squads']]
    rows = data['matches']
    if len(ids) < 2 or len(set(ids)) != len(ids):
        raise ValueError('Listado de equipos incompleto o duplicado.')
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Hay partidos duplicados.')
    pairs = Counter((r['homeSquadId'], r['awaySquadId']) for r in rows)
    expected = {(h, a) for h in ids for a in ids if h != a}
    if set(pairs) != expected or any(v != 1 for v in pairs.values()):
        raise ValueError('El calendario no contiene exactamente una ida y una vuelta para todos los equipos. Se bloquea la proyección.')
    for row in rows:
        score(row)
        if row.get('available') and score(row) is None:
            raise ValueError('Partido disponible sin resultado final: revisar cobertura.')


def complete_calendar(data):
    """Explicit double-round-robin scenario; preserve original API rows."""
    data = copy.deepcopy(data)
    ids = [s['id'] for s in data['squads']]
    pairs = Counter((r['homeSquadId'], r['awaySquadId']) for r in data['matches'])
    expected = {(h,a) for h in ids for a in ids if h != a}
    if not set(pairs).issubset(expected) or any(v != 1 for v in pairs.values()):
        raise ValueError('El calendario contiene parejas duplicadas o equipos desconocidos.')
    missing = sorted(expected-set(pairs))
    for i, (h,a) in enumerate(missing):
        data['matches'].append({'id': -(i+1), 'homeSquadId': h, 'awaySquadId': a,
                                'scheduledDate': None, 'inferred_fixture': True})
    data['calendar_assumption'] = 'Ida y vuelta entre todos los equipos; cruces ausentes inferidos sin fecha.'
    data['inferred_fixtures'] = len(missing)
    validate(data)
    return data


def table(data):
    rows = {s['id']: {'id': s['id'], 'Equipo': s['name'], 'PJ': 0, 'Puntos': 0, 'GF': 0, 'GC': 0} for s in data['squads']}
    for m in data['matches']:
        result = score(m)
        if result is None:
            continue
        h, a = result
        for sid, gf, ga in [(m['homeSquadId'], h, a), (m['awaySquadId'], a, h)]:
            r = rows[sid]; r['PJ'] += 1; r['GF'] += gf; r['GC'] += ga
            r['Puntos'] += 3 if gf > ga else int(gf == ga)
    return sorted(rows.values(), key=lambda r: (-r['Puntos'], -(r['GF']-r['GC']), -r['GF'], r['id']))


def complete_history(datasets, season):
    """Complete seasons strictly before `season`, newest first (max three)."""
    ok = [d for d in datasets if d['iteration']['season'] < season
          and len(d['matches']) == len(d['squads'])*(len(d['squads'])-1)
          and all(score(r) is not None for r in d['matches'])]
    return sorted(ok, key=lambda d: d['iteration']['season'], reverse=True)[:3]


def match_xg(process, match_id):
    """(home xG, away xG) from the IMPECT cache, or None."""
    row = (process or {}).get(str(match_id))
    try:
        return float(row['home']['xg']), float(row['away']['xg'])
    except (TypeError, KeyError, ValueError):
        return None


def poisson_outcomes(lh, la, max_goals=10):
    """P(home win), P(draw), P(away win) for independent Poisson means."""
    k = np.arange(max_goals+1)
    fact = np.cumprod(np.r_[1, k[1:]]).astype(float)
    ph = np.exp(-lh)*lh**k/fact; pa = np.exp(-la)*la**k/fact
    grid = np.outer(ph, pa)
    return float(np.tril(grid, -1).sum()), float(np.trace(grid)), float(np.triu(grid, 1).sum())


def season_process(data, process):
    """Per-team process totals for one season: xG, xGA, PSxG, PSxGA, shots, xPts."""
    out = {}
    for m in data['matches']:
        res = score(m); row = (process or {}).get(str(m['id']))
        if res is None or not row:
            continue
        try:
            xh, xa = float(row['home']['xg']), float(row['away']['xg'])
        except (KeyError, TypeError, ValueError):
            continue
        pw, pd_, pl = poisson_outcomes(xh, xa)
        qw, qd, ql = poisson_outcomes(float(row['home'].get('psxg') or 0), float(row['away'].get('psxg') or 0))
        for side, opp, sid, xpts, psxpts in [('home', 'away', m['homeSquadId'], 3*pw+pd_, 3*qw+qd), ('away', 'home', m['awaySquadId'], 3*pl+pd_, 3*ql+qd)]:
            t = out.setdefault(sid, {'n': 0, 'xg': 0., 'xga': 0., 'psxg': 0., 'psxga': 0., 'shots': 0., 'shots_a': 0., 'xpts': 0., 'psxpts': 0., 'sp_xg': 0., 'sp_xga': 0.})
            t['n'] += 1; t['xpts'] += xpts; t['psxpts'] += psxpts
            t['xg'] += row[side].get('xg', 0) or 0; t['xga'] += row[opp].get('xg', 0) or 0
            t['psxg'] += row[side].get('psxg', 0) or 0; t['psxga'] += row[opp].get('psxg', 0) or 0
            t['shots'] += row[side].get('shots', 0) or 0; t['shots_a'] += row[opp].get('shots', 0) or 0
            t['sp_xg'] += row[side].get('sp_xg', 0) or 0; t['sp_xga'] += row[opp].get('sp_xg', 0) or 0
    return out


def champions(datasets):
    """Champion, runner-up and third per complete season, with matchday curve."""
    out = []
    for d in datasets:
        if not d['matches'] or not all(score(m) is not None for m in d['matches']):
            continue
        t = table(d)
        names = {s['id']: s['name'] for s in d['squads']}
        curve, pts = [], 0
        games = sorted([m for m in d['matches'] if t[0]['id'] in (m['homeSquadId'], m['awaySquadId'])],
                       key=lambda m: ((m.get('matchDay') or {}).get('index', 0), m.get('scheduledDate') or ''))
        for n, m in enumerate(games, 1):
            h, a = score(m); home = m['homeSquadId'] == t[0]['id']
            gf, ga = (h, a) if home else (a, h)
            pts += 3 if gf > ga else int(gf == ga)
            curve.append({'PJ': n, 'Puntos': pts})
        out.append({'season': d['iteration']['season'], 'iteration': d['iteration']['id'],
                    'id': t[0]['id'], 'name': names[t[0]['id']], 'points': t[0]['Puntos'], 'played': t[0]['PJ'],
                    'second': t[1]['Puntos'], 'third': t[2]['Puntos'], 'gf': t[0]['GF'], 'ga': t[0]['GC'], 'curve': curve})
    return sorted(out, key=lambda r: r['season'], reverse=True)


XG_WEIGHT = .8      # share of xG (vs goals) in team-strength evidence; chosen by backtest (0.4–1.0 tested)
PSXG_WEIGHT = 0.    # share of PSxG (taken from the xG share); 0 = not used, see backtest
PRIOR_MATCHES = 12  # weight of the ISR starting level, in equivalent matches; chosen by backtest (6/12)
SEASON_DECAY = .3   # weight of each previous season relative to the next one; chosen by backtest (.5/.3)
NOISE = 1.          # multiplier of the uncertainty on each team's level
ISR_K = 3.          # strength of the IMPECT Squad Rating prior (chosen by backtest, see compare_models)


def match_evidence(res, row, xg_weight, psxg_weight):
    """Blend goals, xG and PSxG for one match: (home, away) evidence."""
    try:
        xg = float(row['home']['xg']), float(row['away']['xg'])
    except (TypeError, KeyError, ValueError):
        return res, False
    try:
        ps = float(row['home']['psxg']), float(row['away']['psxg'])
    except (TypeError, KeyError, ValueError):
        ps, psxg_weight = xg, 0.
    wg = 1 - xg_weight
    return tuple(wg*g + (xg_weight-psxg_weight)*x + psxg_weight*p for g, x, p in zip(res, xg, ps)), True


def isr_at(ratings, sid, date):
    """Latest IMPECT Squad Rating of `sid` on or before `date` (ISO string), or None."""
    series = (ratings or {}).get(str(sid)) or []
    value = None
    for d, v in series:
        if date and d > date[:10]:
            break
        value = v
    return value


def last_played_date(data):
    dates = [m.get('scheduledDate') for m in data['matches'] if score(m) is not None and m.get('scheduledDate')]
    return max(dates) if dates else None


def forecast(current, historical=(), simulations=SIMULATIONS, process=None, ratings=None,
             xg_weight=XG_WEIGHT, psxg_weight=PSXG_WEIGHT, isr_k=ISR_K, isr_date=None,
             prior_matches=None, season_decay=None, noise=None, market=None, market_k=0.):
    """Monte Carlo season simulation.

    process: {iteration_id: {match_id: {'home': {...xg...}, 'away': {...}}}} from IMPECT squad KPIs.
    """
    validate(current)
    process = {str(k): v for k, v in (process or {}).items()}
    ids = [s['id'] for s in current['squads']]; index = {s: i for i, s in enumerate(ids)}
    standings = table(current); by_id = {r['id']: r for r in standings}
    season = current['iteration']['season']
    history = complete_history(historical, season)
    for d in history:
        validate(d)
    games = []
    prior_matches = PRIOR_MATCHES if prior_matches is None else prior_matches
    season_decay = SEASON_DECAY if season_decay is None else season_decay
    noise = NOISE if noise is None else noise
    for d, weight in [(current, 1.0)] + [(d, season_decay ** (i+1)) for i, d in enumerate(history)]:
        proc = process.get(str(d['iteration']['id']), {})
        for r in d['matches']:
            res = score(r)
            if res is None:
                continue
            ev, has = match_evidence(res, proc.get(str(r['id'])), xg_weight, psxg_weight)
            games.append((r, weight, ev, has))
    if not games:
        raise ValueError('No hay resultados con los que estimar la fuerza de los equipos.')
    total_w = sum(w for _, w, _, _ in games)
    home_mean = max(.2, sum(score(r)[0]*w for r, w, _, _ in games)/total_w)
    away_mean = max(.2, sum(score(r)[1]*w for r, w, _, _ in games)/total_w)
    n = len(ids)
    gf = np.zeros(n); ga = np.zeros(n); exp_f = np.zeros(n); exp_a = np.zeros(n); hist_games = np.zeros(n)
    for r, w, (eh, ea), _ in games:
        for sid, f, ag, ef, ea_ in [(r['homeSquadId'], eh, ea, home_mean, away_mean), (r['awaySquadId'], ea, eh, away_mean, home_mean)]:
            if sid in index:
                i = index[sid]; gf[i] += w*f; ga[i] += w*ag; exp_f[i] += w*ef; exp_a[i] += w*ea_
                if r.get('iterationId') != current['iteration']['id'] and w < 1:
                    hist_games[i] += 1
    # Newly promoted teams (no previous season in the window) shrink towards the
    # historical level of promoted sides, not towards the league average.
    promoted_attack, promoted_defence = promoted_level(history)
    target_a = np.where(hist_games > 0, 1.0, promoted_attack)
    target_d = np.where(hist_games > 0, 1.0, promoted_defence)
    # IMPECT Squad Rating (ISR) on the date of the last played match: replaces the
    # neutral starting level with one proportional to the rating gap to the league mean.
    # Live forecasts pass today's date; backtests use the last played match (no peeking ahead).
    cut_date = isr_date or last_played_date(current) or (current['iteration'].get('startDate') or '')
    isr_vals = [isr_at(ratings, sid, cut_date) for sid in ids] if ratings else None
    isr_now = None
    if isr_vals and all(v is not None for v in isr_vals):
        isr_now = np.array(isr_vals, dtype=float)
        if isr_k:
            dev = isr_now - isr_now.mean()
            target_a = np.exp(isr_k*dev); target_d = np.exp(-isr_k*dev)
    # Squad market value (log euros, dated series like the ISR): its own strength market_k.
    mk_vals = [isr_at(market, sid, cut_date) for sid in ids] if market and market_k else None
    if mk_vals and all(v is not None for v in mk_vals):
        mdev = np.array(mk_vals, dtype=float); mdev -= mdev.mean()
        base_a = target_a if (isr_now is not None and isr_k) else 1.0
        base_d = target_d if (isr_now is not None and isr_k) else 1.0
        target_a = base_a*np.exp(market_k*mdev); target_d = base_d*np.exp(-market_k*mdev)
    else:
        mk_vals = None
    prior = prior_matches * (home_mean+away_mean)/2
    attack = (gf + prior*target_a)/(exp_f + prior); defence = (ga + prior*target_d)/(exp_a + prior)
    # Uncertainty on each team's true level: log-normal noise ~ 1/sqrt(evidence).
    sd_a = noise/np.sqrt(gf + prior); sd_d = noise/np.sqrt(ga + prior)
    rng = np.random.default_rng(SEED)
    att_s = attack*np.exp(rng.normal(0, 1, (simulations, n))*sd_a - sd_a**2/2)
    def_s = defence*np.exp(rng.normal(0, 1, (simulations, n))*sd_d - sd_d**2/2)
    points = np.tile([by_id[s]['Puntos'] for s in ids], (simulations, 1)).astype(np.int32)
    goals_for = np.tile([by_id[s]['GF'] for s in ids], (simulations, 1)).astype(np.int32)
    goals_ag = np.tile([by_id[s]['GC'] for s in ids], (simulations, 1)).astype(np.int32)
    fixtures = []
    for r in sorted(current['matches'], key=lambda r: r['id']):
        if score(r) is not None:
            continue
        h, a = index[r['homeSquadId']], index[r['awaySquadId']]
        lh = np.clip(home_mean*att_s[:, h]*def_s[:, a], .15, 5)
        la = np.clip(away_mean*att_s[:, a]*def_s[:, h], .15, 5)
        gh = rng.poisson(lh); gaw = rng.poisson(la)
        points[:, h] += 3*(gh > gaw) + (gh == gaw); points[:, a] += 3*(gaw > gh) + (gh == gaw)
        goals_for[:, h] += gh; goals_ag[:, h] += gaw; goals_for[:, a] += gaw; goals_ag[:, a] += gh
        fixtures.append({'Origen': 'Cruce inferido' if r.get('inferred_fixture') else 'IMPECT', 'Fecha': r.get('scheduledDate'),
                         'Jornada': ((r.get('matchDay') or {}).get('index') + 1) if (r.get('matchDay') or {}).get('index') is not None else None,
                         'home_id': ids[h], 'away_id': ids[a], 'xG local': round(float(lh.mean()), 2), 'xG visitante': round(float(la.mean()), 2),
                         'Local': by_id[ids[h]]['Equipo'], 'Visitante': by_id[ids[a]]['Equipo'],
                         'P(local) %': round(100*np.mean(gh > gaw), 1), 'P(empate) %': round(100*np.mean(gh == gaw), 1), 'P(visitante) %': round(100*np.mean(gh < gaw), 1)})
    top = points.max(axis=1)
    tied = points == top[:, None]
    shares = tied / tied.sum(axis=1)[:, None]
    # Final position: points, then goal difference, then goals for (approximation of the regulations).
    key = points*1_000_000 + (goals_for-goals_ag+5000)*1000 + goals_for
    order = np.argsort(-key, axis=1, kind='stable'); position = np.empty_like(order)
    position[np.arange(simulations)[:, None], order] = np.arange(1, n+1)
    proc_now = season_process(current, process.get(str(current['iteration']['id']), {}))
    summary = []
    for i, sid in enumerate(ids):
        base = by_id[sid]; remaining = 2*(n-1)-base['PJ']
        won = shares[:, i] > 0
        pr = proc_now.get(sid)
        summary.append({**base, 'Pendientes': remaining, 'PPG': round(base['Puntos']/base['PJ'], 2) if base['PJ'] else 0,
                        'Puntos previstos': round(float(points[:, i].mean()), 1),
                        'P10': int(np.quantile(points[:, i], .1)), 'P50': int(np.quantile(points[:, i], .5)), 'P90': int(np.quantile(points[:, i], .9)),
                        'Pos optimista': int(np.quantile(position[:, i], .1)), 'Pos central': int(np.quantile(position[:, i], .5)),
                        'Pos pesimista': int(np.quantile(position[:, i], .9)),
                        'Título aprox. %': round(100*float(shares[:, i].mean()), 2),
                        'Primero en solitario %': round(100*float(np.mean(tied[:, i] & (tied.sum(axis=1) == 1))), 2),
                        'Primero o empatado %': round(100*float(tied[:, i].mean()), 2),
                        'Top 3 %': round(100*float(np.mean(position[:, i] <= 3)), 1),
                        'Posición media': round(float(position[:, i].mean()), 1),
                        'Posiciones %': [round(100*float(np.mean(position[:, i] == p)), 1) for p in range(1, n+1)],
                        'GF título': round(float(((goals_for[won, i]-base['GF'])/max(remaining, 1)).mean()), 2) if won.sum() >= 100 and remaining else None,
                        'GC título': round(float(((goals_ag[won, i]-base['GC'])/max(remaining, 1)).mean()), 2) if won.sum() >= 100 and remaining else None,
                        'Ataque': round(float(attack[i]), 3), 'Defensa': round(float(defence[i]), 3),
                        'xG PJ': pr['n'] if pr else 0,
                        'xG': round(pr['xg'], 2) if pr else None, 'xGA': round(pr['xga'], 2) if pr else None,
                        'PSxG': round(pr['psxg'], 2) if pr else None, 'PSxGA': round(pr['psxga'], 2) if pr else None,
                        'Tiros': pr['shots'] if pr else None, 'Tiros en contra': pr['shots_a'] if pr else None,
                        'xPPG': round(pr['xpts']/pr['n'], 2) if pr and pr['n'] else None,
                        'PSxPPG': round(pr['psxpts']/pr['n'], 2) if pr and pr['n'] else None,
                        'ISR': round(isr_now[i], 3) if isr_now is not None else None})
    # P(title | final points = X): probability that every rival finishes below X
    # (ties shared). Uses all simulations, so it is smooth even for unlikely totals.
    curves = []
    for i, sid in enumerate(ids):
        rivals = np.delete(points, i, axis=1); best = rivals.max(axis=1); n_best = (rivals == best[:, None]).sum(axis=1)
        lo, hi = by_id[sid]['Puntos'], by_id[sid]['Puntos'] + 3*(2*(n-1)-by_id[sid]['PJ'])
        for p in range(lo, hi+1):
            prob = np.mean(best < p) + np.mean((best == p)/(n_best+1))
            curves.append({'id': sid, 'Equipo': by_id[sid]['Equipo'], 'Puntos finales': p, 'Título aprox. %': round(100*float(prob), 1),
                           'Simulaciones': int(np.sum(points[:, i] == p))})
    winner = np.bincount(top)
    winner_points = [{'Puntos': int(p), '%': round(100*c/simulations, 2)} for p, c in enumerate(winner) if c]
    canonical = [{k: v for k, v in d.items() if k != 'fetched_at'} for d in [current]+history]
    used_proc = {k: process[k] for k in sorted(process) if k in {str(d['iteration']['id']) for d in [current]+history}}
    digest = hashlib.sha256(json.dumps([canonical, used_proc, xg_weight, psxg_weight, isr_k, isr_vals if isr_k else None, prior_matches, season_decay, noise, market_k, mk_vals], sort_keys=True).encode()).hexdigest()
    xg_coverage = {str(d['iteration']['id']): sum(match_xg(process.get(str(d['iteration']['id']), {}), m['id']) is not None for m in d['matches'] if score(m) is not None) for d in [current]+history}
    return {'version': VERSION, 'seed': SEED, 'simulations': simulations, 'input_hash': digest,
            'computed_at': datetime.now(timezone.utc).isoformat(),
            'played': sum(score(r) is not None for r in current['matches']),
            'summary': sorted(summary, key=lambda r: -r['Título aprox. %']), 'fixtures': fixtures, 'curves': curves,
            'winner_points': winner_points, 'champions': champions(history),
            'inputs': {'current': current, 'historical': history, 'process': used_proc},
            'parameters': {'season_weights': [1] + [season_decay**i for i in (1, 2, 3)], 'prior_matches': prior_matches, 'noise': noise, 'xg_weight': xg_weight, 'psxg_weight': psxg_weight, 'isr_k': isr_k, 'market_k': market_k if mk_vals else 0.,
                           'xg_coverage': xg_coverage, 'promoted_level': [promoted_attack, promoted_defence],
                           'home_mean': home_mean, 'away_mean': away_mean,
                           'attack': dict(zip(map(str, ids), attack.tolist())), 'defence': dict(zip(map(str, ids), defence.tolist()))}}


def promoted_level(history):
    """Average attack/defence ratio of teams in their first season, from history."""
    seasons = sorted(history, key=lambda d: d['iteration']['season'])
    att, dfn = [], []
    for prev, d in zip(seasons, seasons[1:]):
        before = {s['id'] for s in prev['squads']}
        t = table(d); avg = sum(r['GF'] for r in t)/max(1, sum(r['PJ'] for r in t))
        for r in t:
            if r['id'] not in before and r['PJ']:
                att.append(r['GF']/r['PJ']/avg); dfn.append(r['GC']/r['PJ']/avg)
    if not att:
        return 1.0, 1.0
    return round(float(np.mean(att)), 3), round(float(np.mean(dfn)), 3)


def truncate(data, played_per_team):
    """Copy of a season with results hidden after each team's first N games (backtesting)."""
    data = copy.deepcopy(data); count = Counter()
    for m in sorted(data['matches'], key=lambda m: ((m.get('matchDay') or {}).get('index', 0), m.get('scheduledDate') or '', m['id'])):
        day = (m.get('matchDay') or {}).get('index')
        if day is None or day >= played_per_team:
            m.pop('goals', None); m['available'] = False
    return data


def backtest(datasets, process, cut=5, simulations=4000, ratings=None, **opts):
    """Re-run the model on past complete seasons as if only `cut` matchdays were played.

    Besides the champion, scores every remaining match: log-loss and Brier of the
    1X2 probabilities (lower is better) and mean absolute error in final points.
    """
    out = []
    for d in complete_history(datasets, '99/99'):
        prior = [x for x in datasets if x['iteration']['season'] < d['iteration']['season']]
        try:
            r = forecast(truncate(d, cut), prior, simulations, process, ratings, **opts)
        except ValueError:
            continue
        final = {t['id']: t['Puntos'] for t in table(d)}
        champ = table(d)[0]['id']
        row = next(x for x in r['summary'] if x['id'] == champ)
        rank = sorted(r['summary'], key=lambda x: -x['Título aprox. %']).index(row) + 1
        actual = {(m['homeSquadId'], m['awaySquadId']): score(m) for m in d['matches']}
        ll, brier = [], []
        for f in r['fixtures']:
            h, a = actual[(f['home_id'], f['away_id'])]
            probs = np.array([f['P(local) %'], f['P(empate) %'], f['P(visitante) %']])/100
            probs = np.clip(probs, .005, 1); probs = probs/probs.sum()
            k = 0 if h > a else 1 if h == a else 2
            ll.append(-np.log(probs[k])); brier.append(float(((probs - np.eye(3)[k])**2).sum()))
        err = np.mean([abs(x['Puntos previstos'] - final[x['id']]) for x in r['summary']])
        inside = np.mean([x['P10'] <= final[x['id']] <= x['P90'] for x in r['summary']])
        out.append({'Temporada': d['iteration']['season'], 'Jornada de corte': cut, 'Campeón': row['Equipo'],
                    'Prob. del campeón %': row['Título aprox. %'], 'Favorito nº': rank,
                    'Error medio (pts)': round(float(err), 2), 'Dentro del rango 80% %': round(100*float(inside), 0),
                    'Log-loss': round(float(np.mean(ll)), 4), 'Brier': round(float(np.mean(brier)), 4), 'Partidos': len(ll)})
    return out


MODEL_VARIANTS = [
    # (name, uses xG, xG weight, PSxG weight, ISR k)
    ('Solo goles', False, 0., 0., 0.),
    ('Goles + xG', True, XG_WEIGHT, 0., 0.),
    ('Goles + PSxG', True, XG_WEIGHT, XG_WEIGHT, 0.),
    ('Goles + xG + PSxG', True, XG_WEIGHT, XG_WEIGHT/2, 0.),
    ('Goles + xG + ISR', True, XG_WEIGHT, 0., ISR_K),
    ('Goles + PSxG + ISR', True, XG_WEIGHT, XG_WEIGHT, ISR_K),
]


def compare_models(datasets, process, ratings, cuts=(0, 1, 3, 5, 10, 15, 20), simulations=3000):
    """Backtest every variant over past seasons and cut-off matchdays. Slow (minutes)."""
    rows = []
    for name, use_xg, xw, pw, k in MODEL_VARIANTS:
        res = []
        for cut in cuts:
            res += backtest(datasets, process if use_xg else None, cut, simulations, ratings if k else None,
                            xg_weight=xw if use_xg else 0., psxg_weight=pw, isr_k=k)
        n = sum(x['Partidos'] for x in res)
        rows.append({'Modelo': name, 'Log-loss': round(sum(x['Log-loss']*x['Partidos'] for x in res)/n, 4),
                     'Brier': round(sum(x['Brier']*x['Partidos'] for x in res)/n, 4),
                     'Error medio (pts)': round(float(np.mean([x['Error medio (pts)'] for x in res])), 2),
                     'Prob. del campeón %': round(float(np.mean([x['Prob. del campeón %'] for x in res])), 1),
                     'Partidos evaluados': n})
    results = [score(m) for d in complete_history(datasets, '99/99') for m in d['matches']]
    base = np.array([np.mean([h > a for h, a in results]), np.mean([h == a for h, a in results]), np.mean([h < a for h, a in results])])
    naive = float(-np.mean([np.log(base[0 if h > a else 1 if h == a else 2]) for h, a in results]))
    return {'variants': rows, 'naive_log_loss': round(naive, 4), 'cuts': list(cuts), 'version': VERSION}


def evidence_shares(prior_matches=PRIOR_MATCHES, season_decay=SEASON_DECAY, seasons=2, games=26):
    """Approximate share of ISR / previous seasons / current season in a team's level, by matches played."""
    hist = sum(games*season_decay**i for i in range(1, seasons+1))
    rows = []
    for n in range(games+1):
        total = prior_matches + hist + n
        rows.append({'PJ': n, 'ISR': prior_matches/total, 'Temporadas anteriores': hist/total, 'Esta temporada': n/total})
    return rows


def refresh_ratings(client, folder: Path, iteration_ids):
    """Download the IMPECT Squad Rating (ISR) history: {squadId: [[date, value], ...]}.

    Each iteration only lists its own squads, so relegated teams need their season.
    """
    points = {}
    for iteration_id in iteration_ids:
        data = client._get(f'/iterations/{iteration_id}/squads/ratings').get('data')
        entries = (data[0] if isinstance(data, list) else data)['squadRatingsEntries']
        for e in entries:
            for r in e['squadRatings']:
                points.setdefault(str(r['squadId']), {})[e['date'][:10]] = round(float(r['value']), 5)
    series = {sid: [[d, v] for d, v in sorted(by_date.items())] for sid, by_date in points.items()}
    _write_json(folder/'ratings.json', series)
    return series


def load_ratings(folder: Path):
    path = folder/'ratings.json'
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def save_snapshot(result, folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    sid = result['inputs']['current']['iteration']['id']
    path = folder / f"{sid}_{result['version']}_{result['input_hash'][:16]}.json"
    if not path.exists():
        temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(result, ensure_ascii=False)); temp.replace(path)
    return path


def refresh(client, folder: Path):
    iterations = [i for i in client.get_iterations() if (i.get('competition') or {}).get('name') == 'UAE Pro League']
    iterations = sorted(iterations, key=lambda i: i['season'], reverse=True)[:4]
    if not iterations:
        raise ValueError('La cuenta no devuelve temporadas de UAE Pro League.')
    datasets = []
    for i in iterations:
        datasets.append({'iteration': i, 'matches': client.get_matches(i['id']), 'squads': client.get_squads(i['id']), 'fetched_at': datetime.now(timezone.utc).isoformat()})
    folder.mkdir(parents=True, exist_ok=True)
    for data in datasets:
        path = folder / f"season_{data['iteration']['id']}.json"
        temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(data)); temp.replace(path)
    return datasets


PROCESS_KPIS = {
    'SHOT_XG': 'xg', 'POSTSHOT_XG': 'psxg', 'SHOT_AT_GOAL_NUMBER': 'shots',
    'SHOT_XG_BY_ACTION_PENALTY_KICK': 'pen_xg', 'SHOT_XG_AT_PHASE_SET_PIECE': 'sp_xg',
    'BYPASSED_OPPONENTS': 'packing', 'CRITICAL_BALL_LOSS_NUMBER': 'critical_losses',
    'BALL_WIN_NUMBER': 'ball_wins',
}


def refresh_process(client, folder: Path, datasets, max_seasons=3, progress=None):
    """Cache IMPECT squad KPIs (xG, PSxG, shots…) per played match. Incremental."""
    catalog = {r['name']: r['id'] for r in client.get_kpi_catalog()}
    wanted = {catalog[k]: v for k, v in PROCESS_KPIS.items() if k in catalog}
    for data in sorted(datasets, key=lambda d: d['iteration']['season'], reverse=True)[:max_seasons]:
        path = folder / f"process_{data['iteration']['id']}.json"
        cache = json.loads(path.read_text()) if path.exists() else {}
        todo = [m for m in data['matches'] if score(m) is not None and str(m['id']) not in cache]
        for n, m in enumerate(todo, 1):
            try:
                raw = client.get_match_squad_kpis(m['id'])
            except Exception:
                continue
            row = {}
            for side in ('squadHome', 'squadAway'):
                values = {wanted[k['kpiId']]: k['value'] for k in raw[side]['kpis'] if k['kpiId'] in wanted}
                row['home' if side == 'squadHome' else 'away'] = {'id': raw[side]['id'], **values}
            cache[str(m['id'])] = row
            if progress:
                progress(data['iteration']['season'], n, len(todo))
            if n % 20 == 0:
                _write_json(path, cache)
        _write_json(path, cache)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(payload)); temp.replace(path)


def load_process(folder: Path, iteration_id):
    path = folder / f'process_{iteration_id}.json'
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- market value (experimental)

BESOCCER_TEAMS = {  # BeSoccer team name -> IMPECT squad id (UAE Pro League 26/27)
    'Al-Jazira': 2122, 'Shabab Al Ahli Dubai': 2090, 'Al-Wasl': 2033, 'Al-Ain': 2047, 'Al-Wahda': 2041,
    'Al Nasr Dubai': 6615, 'Sharjah FC': 2093, 'Al Ittihad Kalba': 6616, 'Ajman': 6613, 'United FC': 17132,
    'Khorfakkan': 6618, 'Hatta Club': 6770, 'Baniyas': 3393, 'Al Dhafra': 11624,
}
MARKET_TOP_N = 18   # squads in the source list 17-57 players (youth included): compare the most valuable 18


def import_besoccer_values(csv_path: Path, folder: Path, top_n=MARKET_TOP_N):
    """Snapshot of BeSoccer squad market values (UAE Pro League) into data/title_race/market_besoccer.json."""
    import csv
    players = {}
    scraped = None
    with open(csv_path, newline='', encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            sid = BESOCCER_TEAMS.get(r.get('team'))
            if sid is None or 'arabian_gulf' not in (r.get('league_slug') or ''):
                continue
            try:
                value = float(r.get('market_current_eur') or 0)
            except ValueError:
                continue
            players.setdefault(sid, []).append(value)
            scraped = max(scraped or '', r.get('scraped_at') or '')
    out = {'source': 'BeSoccer', 'scraped_at': scraped, 'top_n': top_n, 'teams': {}}
    for sid, values in players.items():
        values.sort(reverse=True)
        out['teams'][str(sid)] = {'value': sum(values[:top_n]), 'top11': sum(values[:11]), 'listed': len(values)}
    _write_json(folder/'market_besoccer.json', out)
    return out


def load_market(folder: Path):
    path = folder/'market_besoccer.json'
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def market_as_ratings(market, ratings, ids, date):
    """Turn squad values into an ISR-like scale so the same model can run on them.

    log(value) is standardised and given the same mean and spread the ISR has today:
    the ranking comes from the market, the strength of the effect from the validated ISR.
    """
    teams = market.get('teams', {})
    vals = {sid: np.log(teams[str(sid)]['value']) for sid in ids if teams.get(str(sid), {}).get('value')}
    isr = [isr_at(ratings, sid, date) for sid in ids]
    isr = [v for v in isr if v is not None]
    if len(vals) != len(ids) or len(isr) != len(ids):
        return None
    lv = np.array(list(vals.values())); mu, sd = lv.mean(), lv.std() or 1
    imu, isd = float(np.mean(isr)), float(np.std(isr))
    return {str(sid): [[date[:10], round(imu + isd*(v - mu)/sd, 5)]] for sid, v in vals.items()}
