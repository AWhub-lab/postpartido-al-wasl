"""Visual presentation for the title-race dashboard (Al Wasl perspective)."""
from __future__ import annotations

import base64
import html
import math
from functools import lru_cache
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from .title_race import poisson_outcomes, score

WASL, JAZIRA, AIN = 2033, 2122, 2047
FOCUS = [WASL, JAZIRA, AIN]
# id: (short name, 3-letter code, colour). Only the focus teams carry a strong colour.
TEAMS = {
    2033: ('Al Wasl', 'WSL', '#F2C200'), 2122: ('Al Jazira', 'JAZ', '#C8102E'), 2047: ('Al Ain', 'AIN', '#6C3FB5'),
    2090: ('Shabab Al Ahli', 'SAA', '#8B97A8'), 2093: ('Sharjah', 'SHJ', '#8B97A8'), 2041: ('Al Wahda', 'WAH', '#8B97A8'),
    3393: ('Baniyas', 'BAN', '#8B97A8'), 6613: ('Ajman', 'AJM', '#8B97A8'), 6615: ('Al Nasr', 'NAS', '#8B97A8'),
    6616: ('Kalba', 'ITK', '#8B97A8'), 6618: ('Khor Fakkan', 'KHF', '#8B97A8'), 6770: ('Hatta', 'HAT', '#8B97A8'),
    11624: ('Al Dhafra', 'DHA', '#8B97A8'), 17132: ('United FC', 'UTD', '#8B97A8'),
}
NAMES = {k: v[0] for k, v in TEAMS.items()}
COLORS = {k: v[2] for k, v in TEAMS.items() if k in FOCUS}
INK, YELLOW, GREY, LIGHT = '#141B2D', '#F2C200', '#8B97A8', '#F4F5F7'
WIN, DRAW, LOSS = '#1E8E5A', '#8B97A8', '#D64545'


def esc(value):
    return html.escape(str(value), quote=True)


def name(squad):
    return NAMES.get(squad['id'], squad.get('name', str(squad['id'])))


def code(sid, squad=None):
    return TEAMS.get(sid, (None, (squad or {}).get('name', '???')[:3].upper()))[1]


def color(sid):
    return COLORS.get(sid, GREY)


def ordinal(n):
    return f'{n}º'


@lru_cache(maxsize=64)
def _crest_src(root: str, sid: int, url: str) -> str:
    path = next(iter((Path(root)/'assets/crests').glob(f'{sid}.*')), None)
    if path and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
        mime = 'jpeg' if path.suffix.lower() in ('.jpg', '.jpeg') else path.suffix[1:].lower()
        return f'data:image/{mime};base64,' + base64.b64encode(path.read_bytes()).decode()
    return url if url.startswith(('https://', 'http://')) else ''


def crest_src(root, squad):
    return _crest_src(str(root), squad['id'], squad.get('imageUrl') or '')


def crest(root, squad, size=48):
    src = crest_src(root, squad)
    if src:
        return f'<img class="tr-crest" src="{esc(src)}" alt="{esc(name(squad))}" style="width:{size}px;height:{size}px">'
    return (f'<span class="tr-fallback" style="width:{size}px;height:{size}px;font-size:{max(9, size//3)}px">'
            f'{esc(code(squad["id"], squad))}</span>')


def md(body):
    """Render HTML without Markdown re-interpreting indentation."""
    st.markdown(body, unsafe_allow_html=True)


def inject_styles():
    md('''<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Inter:wght@400;500;600;700;800&display=swap');
.tr{font-family:Inter,system-ui,sans-serif;color:#141B2D}
.tr-cond{font-family:'Barlow Condensed',Inter,sans-serif;text-transform:uppercase;letter-spacing:.3px}
.tr-crest{object-fit:contain;flex-shrink:0}
.tr-fallback{display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:#E6E9EE;color:#4A5568;font-weight:800;flex-shrink:0;font-family:'Barlow Condensed',sans-serif}
.tr-brand{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:2px solid #F2C200;padding:4px 0 10px;margin:0 0 18px}
.tr-brand-left{display:flex;align-items:center;gap:10px;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:17px;letter-spacing:.6px;text-transform:uppercase;color:#141B2D}
.tr-brand-right{display:flex;align-items:center;gap:12px;text-align:right}
.tr-brand-right b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:19px;letter-spacing:.4px;text-transform:uppercase;line-height:1}
.tr-brand-right small{font-size:10px;letter-spacing:2px;color:#5B6576;text-transform:uppercase;font-weight:700}
.tr-num{background:#F2C200;color:#141B2D;font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:24px;padding:6px 13px;line-height:1}
.tr-h1{font-family:'Barlow Condensed',sans-serif;font-weight:800;text-transform:uppercase;font-size:46px;line-height:1.02;margin:0;color:#141B2D;letter-spacing:.2px}
.tr-h1 mark{background:#F2C200;color:#141B2D;padding:0 12px;display:inline-block;margin-top:6px}
.tr-lead{font-size:15px;color:#3A4558;margin:12px 0 4px;max-width:880px;line-height:1.55}
.tr-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0;border-top:2px solid #F2C200;border-bottom:1px solid #E3E6EB;margin:18px 0 22px}
.tr-kpi{padding:14px 16px;border-right:1px solid #E3E6EB}.tr-kpi:last-child{border-right:none}
.tr-kpi b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:40px;font-weight:800;line-height:1;color:#141B2D}
.tr-kpi span{font-size:10.5px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:#5B6576}
.tr-kpi em{display:block;font-style:normal;font-size:12px;color:#5B6576;margin-top:4px}
.tr-section{margin:26px 0 10px}
.tr-section small{display:block;font-size:11px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;color:#5B6576}
.tr-section h3{font-family:'Barlow Condensed',sans-serif!important;font-weight:800!important;text-transform:uppercase;font-size:26px!important;margin:2px 0 0!important;padding:0!important;color:#141B2D!important;letter-spacing:.3px}
.tr-section p{font-size:13px;color:#5B6576;margin:4px 0 0}
.tr-cards3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.tr-card{background:#fff;border:1px solid #E3E6EB;border-top:5px solid var(--c,#F2C200);padding:18px;box-shadow:0 2px 10px rgba(20,27,45,.05)}
.tr-card.me{background:linear-gradient(180deg,#FFF9DB 0,#fff 55%)}
.tr-card-head{display:flex;align-items:center;gap:12px}
.tr-card-head strong{font-family:'Barlow Condensed',sans-serif;font-size:24px;text-transform:uppercase;line-height:1}
.tr-card-head small{display:block;font-size:12px;color:#5B6576}
.tr-big{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:58px;line-height:1;margin:14px 0 0}
.tr-big span{font-size:26px}
.tr-meter{height:8px;background:#EEF0F3;margin:8px 0 2px}.tr-meter i{display:block;height:8px;background:var(--c,#F2C200)}
.tr-mini{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px;border-top:1px solid #EEF0F3;padding-top:12px}
.tr-mini b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:24px;line-height:1.05}
.tr-mini small{font-size:10px;letter-spacing:.8px;text-transform:uppercase;color:#5B6576;font-weight:700}
.tr-form{display:flex;gap:4px;margin-top:10px;flex-wrap:wrap}
.tr-chip{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:800;font-family:'Barlow Condensed',sans-serif}
.tr-muted{font-size:12px;color:#5B6576;line-height:1.5}
.tr-table{width:100%;border-collapse:separate;border-spacing:0 5px;font-size:14px}
.tr-table th{font-size:10.5px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#5B6576;text-align:right;padding:4px 8px}
.tr-table th:nth-child(2){text-align:left}
.tr-table td{white-space:nowrap;background:#fff;padding:9px 8px;text-align:right;border-top:1px solid #EEF0F3;border-bottom:1px solid #EEF0F3;font-variant-numeric:tabular-nums}
.tr-table td:first-child{border-left:4px solid var(--c,transparent);text-align:center;font-weight:700;color:#5B6576}
.tr-table td:last-child{border-right:1px solid #EEF0F3}
.tr-table tr.me td{background:#FFF6CC;font-weight:700}
.tr-table tr.rival td{background:#FAFAFC}
.tr-team{display:flex;align-items:center;gap:9px;text-align:left;font-weight:700;white-space:normal}
.tr-table .rng{font-size:11px;color:#5B6576;font-weight:500}
.tr-pill{display:inline-block;min-width:54px;padding:3px 8px;font-weight:800;text-align:center;font-family:'Barlow Condensed',sans-serif;font-size:16px}
.tr-up{color:#1E8E5A;font-weight:700}.tr-down{color:#D64545;font-weight:700}
.tr-pace{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.tr-pace div{background:#F1F2F4;padding:14px 16px}
.tr-pace div.hl{background:#F2C200}
.tr-pace span{font-size:11px;font-weight:700;letter-spacing:1.3px;text-transform:uppercase;color:#3A4558}
.tr-pace b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:50px;font-weight:800;line-height:1;margin:8px 0 6px;border-bottom:2px solid rgba(20,27,45,.15);padding-bottom:6px}
.tr-pace strong{display:block;font-family:'Barlow Condensed',sans-serif;font-size:20px;text-transform:uppercase;line-height:1.1}
.tr-strip{display:flex;gap:3px;flex-wrap:wrap;margin:8px 0 6px}
.tr-strip i{display:inline-flex;width:24px;height:26px;align-items:center;justify-content:center;font-style:normal;font-weight:800;font-size:13px;font-family:'Barlow Condensed',sans-serif}
.tr-strip .w{background:#F2C200;color:#141B2D}.tr-strip .d{background:#fff;border:1px solid #B9C0CB;color:#3A4558}.tr-strip .l{background:#fff;border:1px solid #D64545;color:#D64545}
.tr-band{background:#F2C200;font-size:11px;font-weight:800;letter-spacing:1.6px;text-transform:uppercase;padding:4px 8px;margin:16px 0 8px;color:#141B2D}
.tr-goals{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.tr-goals b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:42px;font-weight:800;line-height:1}
.tr-goals small{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#5B6576}
.tr-cmp{width:100%;border-collapse:collapse;font-size:14px}
.tr-cmp th{padding:10px 8px;text-align:center;color:#fff;font-family:'Barlow Condensed',sans-serif;font-size:20px;text-transform:uppercase;letter-spacing:.4px}
.tr-cmp th:first-child{background:#fff;color:#5B6576;text-align:left;font-family:Inter;font-size:11px;letter-spacing:1px}
.tr-cmp th div{display:flex;align-items:center;justify-content:center;gap:8px}
.tr-cmp td{padding:9px 8px;border-bottom:1px solid #EEF0F3;text-align:center;font-family:'Barlow Condensed',sans-serif;font-size:21px;font-weight:700}
.tr-cmp td:first-child{text-align:left;font-family:Inter;font-size:13px;font-weight:700}
.tr-cmp td:first-child small{display:block;font-weight:500;color:#5B6576;font-size:11px}
.tr-cmp td.best{position:relative}
.tr-cmp td.best::after{content:'▲';font-size:10px;color:#1E8E5A;margin-left:5px;vertical-align:middle}
.tr-cmp td.col-me{background:#FFF8D6}
.tr-funnel{display:grid;grid-template-columns:1fr 1fr;gap:26px}
.tr-funnel h4{font-family:'Barlow Condensed',sans-serif!important;font-size:30px!important;font-weight:800!important;margin:0!important;padding:0!important;text-transform:uppercase}
.tr-funnel h4+small{font-size:11px;letter-spacing:2px;color:#5B6576;font-weight:700;text-transform:uppercase}
.tr-bars{display:grid;grid-template-columns:1fr 70px 1fr 70px 1fr;align-items:end;gap:4px;height:210px;margin:16px 0 6px;border-bottom:2px solid #3A4558}
.tr-bars .bar{display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%}
.tr-bars .bar b{font-family:'Barlow Condensed',sans-serif;font-size:26px;font-weight:800}
.tr-bars .bar i{display:block;width:78%}
.tr-bars .arrow{align-self:center;text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;color:#3A4558;line-height:1.2}
.tr-bars .arrow b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:20px}
.tr-labels{display:grid;grid-template-columns:1fr 70px 1fr 70px 1fr;gap:4px;text-align:center}
.tr-labels b{font-family:'Barlow Condensed',sans-serif;font-size:19px;display:block}
.tr-labels small{font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase;color:#5B6576;font-weight:700}
.tr-verdict{display:flex;gap:10px;align-items:center;background:#F1F2F4;padding:10px 14px;margin-top:14px;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.tr-verdict i{font-style:normal;display:inline-flex;width:28px;height:28px;border-radius:50%;align-items:center;justify-content:center;color:#fff;flex-shrink:0}
.tr-callout{background:#F4F5F7;border-left:4px solid #F2C200;padding:12px 16px;margin:12px 0;font-size:14px;line-height:1.6;color:#2A3446}
.tr-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.tr-step{border-top:3px solid #F2C200;padding-top:10px}
.tr-step .n{font-family:'Barlow Condensed',sans-serif;font-size:40px;font-weight:800;line-height:1;float:left;margin-right:12px}
.tr-step small{font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:#5B6576;font-weight:700;display:block}
.tr-step>b{font-family:'Barlow Condensed',sans-serif;font-size:20px;text-transform:uppercase;display:block;line-height:1.1}
.tr-step ul{clear:both;margin:12px 0 0;padding:12px 14px 12px 28px;background:#F4F5F7;font-size:13px;line-height:1.55}
.tr-fixture{display:grid;grid-template-columns:72px minmax(0,1fr) 210px 70px;gap:12px;align-items:center;background:#fff;border:1px solid #E3E6EB;border-left:4px solid var(--c,#E3E6EB);padding:9px 12px;margin:6px 0}
.tr-fixture .meta{font-size:11px;color:#5B6576;font-weight:700;text-transform:uppercase;letter-spacing:.6px;line-height:1.3}
.tr-fixture .vs{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;min-width:0}
.tr-fixture .vs span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tr-stack{display:flex;height:22px;font-size:11px;font-weight:800;color:#fff}
.tr-stack span{display:flex;align-items:center;justify-content:center;overflow:hidden}
.tr-fixture .xp{text-align:right;font-family:'Barlow Condensed',sans-serif;font-size:22px;font-weight:800;line-height:1}
.tr-fixture .xp small{display:block;font-family:Inter;font-size:9px;font-weight:700;color:#5B6576;letter-spacing:.8px}
.tr-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#3A4558;margin:6px 0}
.tr-legend i{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px}
.tr-gloss{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.tr-gloss div{background:#F4F5F7;padding:10px 12px;font-size:12.5px;line-height:1.45}
.tr-gloss b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:17px;text-transform:uppercase}
@media(max-width:760px){.tr-h1{font-size:32px}.tr-cards3,.tr-pace,.tr-funnel,.tr-steps{grid-template-columns:1fr}.tr-big{font-size:46px}
.tr-fixture{grid-template-columns:1fr;gap:6px}.tr-table{font-size:12px}.tr-table .opt{display:none}.tr-brand-left span{display:none}}
</style>''')


# ---------------------------------------------------------------- building blocks

def brand_header(root, title, subtitle, number):
    logo = root/'assets/al_wasl_logo.png'
    img = (f'<img src="data:image/png;base64,{base64.b64encode(logo.read_bytes()).decode()}" style="width:34px;height:34px;object-fit:contain">'
           if logo.exists() else '')
    md(f'<div class="tr tr-brand"><div class="tr-brand-left">{img}<span>Al Wasl · Football Intelligence</span></div>'
       f'<div class="tr-brand-right"><div><b>{esc(title)}</b><small>{esc(subtitle)}</small></div><div class="tr-num">{number:02d}</div></div></div>')


def headline(line1, line2, lead=None):
    md(f'<div class="tr"><div class="tr-h1">{esc(line1)}<br><mark>{esc(line2)}</mark></div>'
       + (f'<p class="tr-lead">{lead}</p>' if lead else '') + '</div>')


def section(kicker, title, text=None):
    md(f'<div class="tr tr-section"><small>{esc(kicker)}</small><h3>{esc(title)}</h3>'
       + (f'<p>{text}</p>' if text else '') + '</div>')


def kpi_tiles(items):
    md('<div class="tr tr-kpis">' + ''.join(
        f'<div class="tr-kpi"><b>{esc(v)}</b><span>{esc(label)}</span>' + (f'<em>{note}</em>' if note else '') + '</div>'
        for v, label, note in items) + '</div>')


def chip(outcome):
    c = {'V': WIN, 'E': DRAW, 'D': LOSS}[outcome]
    return f'<span class="tr-chip" style="background:{c}">{outcome}</span>'


# ---------------------------------------------------------------- data helpers

def form_games(current, sid, venue='Todos'):
    rows = []
    for m in current['matches']:
        result = score(m)
        if result is None or sid not in (m['homeSquadId'], m['awaySquadId']):
            continue
        home = sid == m['homeSquadId']
        if venue == 'En casa' and not home or venue == 'Fuera' and home:
            continue
        gf, ga = result if home else result[::-1]
        rows.append({**m, 'gf': gf, 'ga': ga, 'outcome': 'V' if gf > ga else 'E' if gf == ga else 'D', 'points': 3 if gf > ga else int(gf == ga)})
    return sorted(rows, key=lambda m: (m.get('scheduledDate') or '', m['id']))


def form_html(games, n=5):
    if not games:
        return '<span class="tr-muted">Sin partidos disputados</span>'
    return '<div class="tr-form">' + ''.join(
        f'<span title="{g["gf"]}–{g["ga"]}">{chip(g["outcome"])}</span>' for g in games[-n:]) + '</div>'


def trajectory(current, ids, squads):
    """Cumulative known results by official matchday (IMPECT zero-based index)."""
    rows = []
    for sid in ids:
        grouped = {}
        for m in form_games(current, sid):
            idx = (m.get('matchDay') or {}).get('index')
            if idx is not None:
                grouped.setdefault(int(idx)+1, []).append(m)
        pts = played = 0
        rows.append({'Jornada': 0, 'Puntos': 0, 'PJ': 0, 'Equipo': name(squads[sid])})
        for day, ms in sorted(grouped.items()):
            pts += sum(m['points'] for m in ms); played += len(ms)
            rows.append({'Jornada': day, 'Puntos': pts, 'PJ': played, 'Equipo': name(squads[sid])})
    return rows


def fixture_perspective(fixture, team_name):
    """Preserve home/away presentation; reverse only selected team's win/loss."""
    if team_name not in (fixture['Local'], fixture['Visitante']):
        raise ValueError('El equipo no participa en este partido.')
    home = fixture['Local'] == team_name
    return {'venue': 'En casa' if home else 'Fuera', 'win': fixture['P(local) %'] if home else fixture['P(visitante) %'],
            'draw': fixture['P(empate) %'], 'loss': fixture['P(visitante) %'] if home else fixture['P(local) %']}


def real_position(result):
    rows = sorted(result['summary'], key=lambda r: (-r['Puntos'], -(r['GF']-r['GC']), -r['GF'], r['id']))
    return {r['id']: i for i, r in enumerate(rows, 1)}


def target_points(result, sid, level):
    """Smallest final total with P(title | total) >= level %."""
    for c in sorted((c for c in result['curves'] if c['id'] == sid), key=lambda c: c['Puntos finales']):
        if c['Título aprox. %'] >= level:
            return c['Puntos finales']
    return None


def title_prob_at(result, sid, pts):
    rows = [c for c in result['curves'] if c['id'] == sid]
    if not rows:
        return 0.0
    best = min(rows, key=lambda c: abs(c['Puntos finales'] - pts))
    return best['Título aprox. %']


def run_in(needed, remaining, draw_rate=.24):
    """A plausible W/D/L split that reaches `needed` points in `remaining` games."""
    if needed <= 0:
        return 0, 0, remaining
    best = None
    for d in range(remaining+1):
        w = max(0, math.ceil((needed-d)/3))
        if w + d > remaining:
            continue
        cand = (abs(d - draw_rate*remaining), w, d)
        best = min(best, cand) if best else cand
    if best is None:
        return remaining, 0, 0
    _, w, d = best
    return w, d, remaining - w - d


def expected_points(fixtures, team_name):
    ps = [fixture_perspective(f, team_name) for f in fixtures if team_name in (f['Local'], f['Visitante'])]
    return sum((3*p['win']+p['draw'])/100 for p in ps), len(ps)


def xpts_by_game(current, sid, process):
    rows = []
    for g in form_games(current, sid):
        row = (process or {}).get(str(g['id']))
        if not row:
            continue
        home = g['homeSquadId'] == sid
        xh, xa = float(row['home'].get('xg', 0)), float(row['away'].get('xg', 0))
        pw, pd_, pl = poisson_outcomes(xh, xa)
        rows.append({'xpts': 3*pw+pd_ if home else 3*pl+pd_, 'pts': g['points']})
    return rows


# ---------------------------------------------------------------- composite views

def focus_cards(root, result, squads, current, ids):
    pos = real_position(result)
    cards = []
    for sid in ids:
        r = next(x for x in result['summary'] if x['id'] == sid); s = squads[sid]
        pct = r['Título aprox. %']
        cards.append(
            f'<div class="tr-card{" me" if sid == WASL else ""}" style="--c:{color(sid)}">'
            f'<div class="tr-card-head">{crest(root, s, 52)}<div><strong>{esc(name(s))}</strong>'
            f'<small>{ordinal(pos[sid])} hoy · {r["Puntos"]} pts en {r["PJ"]} partidos</small></div></div>'
            f'<div class="tr-big">{pct:.0f}<span>%</span></div><div class="tr-muted">opciones de ser campeón</div>'
            f'<div class="tr-meter"><i style="width:{min(100, pct):.1f}%"></i></div>'
            f'<div class="tr-mini"><div><b>{r["Puntos previstos"]:.0f}</b><small>Pts finales</small></div>'
            f'<div><b>{r["P10"]}–{r["P90"]}</b><small>Rango probable</small></div>'
            f'<div><b>{r["Top 3 %"]:.0f}%</b><small>Top 3</small></div></div>'
            f'<div class="tr-muted" style="margin-top:12px">Últimos partidos</div>{form_html(form_games(current, sid))}</div>')
    md('<div class="tr tr-cards3">' + ''.join(cards) + '</div>')


def league_table(root, result, squads, has_xg):
    pos = real_position(result)
    has_isr = any(r.get('ISR') is not None for r in result['summary'])
    rows = sorted(result['summary'], key=lambda r: (-r['Puntos previstos'], pos[r['id']]))
    head = ('<tr><th>#</th><th>Equipo</th><th class="opt">Hoy</th><th>Pts</th><th class="opt">PPG</th>'
            + ('<th class="opt" title="Puntos por partido merecidos según las ocasiones (xG)">xPPG</th>'
               '<th class="opt" title="Puntos por partido merecidos según la calidad de los remates (PSxG)">PSxPPG</th>' if has_xg else '')
            + ('<th class="opt" title="IMPECT Squad Rating: nivel global del equipo según IMPECT">ISR</th>' if has_isr else '')
            + '<th title="Puntos finales esperados">Proy.</th><th>Título</th></tr>')
    body = []
    for i, r in enumerate(rows, 1):
        sid = r['id']; cls = 'me' if sid == WASL else 'rival' if sid in FOCUS else ''
        pct = r['Título aprox. %']
        pill_bg = YELLOW if sid == WASL else (color(sid) if sid in FOCUS else '#EEF0F3')
        pill_fg = INK if sid == WASL or sid not in FOCUS else '#fff'
        pct_txt = f'{pct:.0f}%' if pct >= 1 else ('<1%' if pct > 0 else '–')
        xppg = r.get('xPPG')
        trend = ''
        if has_xg and xppg is not None:
            diff = r['PPG'] - xppg
            trend = f' <small class="{"tr-down" if diff > .3 else "tr-up" if diff < -.3 else "tr-muted"}" title="Puntos reales vs merecidos">{"▲" if diff > .3 else "▼" if diff < -.3 else ""}</small>'
        body.append(
            f'<tr class="{cls}"><td style="--c:{color(sid) if sid in FOCUS else "transparent"}">{i}</td>'
            f'<td><div class="tr-team">{crest(root, squads[sid], 26)}<span>{esc(name(squads[sid]))}</span></div></td>'
            f'<td class="opt">{pos[sid]}º</td><td><b>{r["Puntos"]}</b></td><td class="opt">{r["PPG"]:.2f}</td>'
            + (f'<td class="opt">{xppg:.2f}{trend}</td><td class="opt">{r["PSxPPG"]:.2f}</td>' if has_xg and xppg is not None else ('<td class="opt">–</td><td class="opt">–</td>' if has_xg else ''))
            + (f'<td class="opt">{r["ISR"]:.3f}</td>' if has_isr and r.get('ISR') is not None else ('<td class="opt">–</td>' if has_isr else ''))
            + f'<td><b>{r["Puntos previstos"]:.0f}</b> <span class="rng">{r["P10"]}–{r["P90"]}</span></td>'
            f'<td><span class="tr-pill" style="background:{pill_bg};color:{pill_fg}">{pct_txt}</span></td></tr>')
    md('<div class="tr"><table class="tr-table">' + head + ''.join(body) + '</table></div>')


def style_chart(chart, height=300):
    return (chart.properties(height=height).configure_view(stroke=None)
            .configure_axis(labelColor='#5B6576', titleColor='#5B6576', gridColor='#EEF0F3', domain=False, labelFontSize=12, titleFontSize=11,
                            labelFont='Inter', titleFont='Inter')
            .configure_legend(title=None, labelColor='#3A4558', orient='top', symbolStrokeWidth=4, labelFontSize=12))


def range_chart(root, result, squads):
    """Projected final points: dot = expected, bar = central 80%, crest on top (slide-style)."""
    rows = []
    for r in sorted(result['summary'], key=lambda r: -r['Puntos previstos']):
        sid = r['id']
        rows.append({'Equipo': name(squads[sid]), 'code': code(sid, squads[sid]), 'Proyección': r['Puntos previstos'],
                     'P10': r['P10'], 'P90': r['P90'], 'Hoy': r['Puntos'], 'img': crest_src(root, squads[sid]),
                     'c': color(sid) if sid in FOCUS else '#B4BCC8', 'w': 12 if sid == WASL else 7,
                     'Título %': r['Título aprox. %'], 'top': r['P90'] + 4})
    df = pd.DataFrame(rows); order = list(df.code)
    x = alt.X('code:N', sort=order, title=None, axis=alt.Axis(labelAngle=0, labelFontWeight='bold'))
    tip = ['Equipo', alt.Tooltip('Proyección:Q', format='.1f', title='Puntos finales esperados'),
           alt.Tooltip('P10:Q', title='Escenario bajo (P10)'), alt.Tooltip('P90:Q', title='Escenario alto (P90)'),
           alt.Tooltip('Hoy:Q', title='Puntos hoy'), alt.Tooltip('Título %:Q', format='.1f')]
    base = alt.Chart(df).encode(x=x, tooltip=tip)
    band = base.mark_rule(opacity=.45).encode(y=alt.Y('P10:Q', title='Puntos al final de la liga', scale=alt.Scale(zero=True)),
                                              y2='P90:Q', color=alt.Color('c:N', scale=None), strokeWidth=alt.StrokeWidth('w:Q', scale=None))
    now = base.mark_tick(thickness=2, size=16, color='#3A4558', opacity=.6).encode(y='Hoy:Q')
    dot = base.mark_circle(size=150, opacity=1, stroke='#fff', strokeWidth=1.5).encode(y='Proyección:Q', color=alt.Color('c:N', scale=None))
    imgs = alt.Chart(df[df.img != '']).mark_image(width=26, height=26).encode(x=x, y='top:Q', url='img:N', tooltip=tip)
    txt = alt.Chart(df[df.img == '']).mark_text(fontWeight='bold', fontSize=10, color='#5B6576').encode(x=x, y='top:Q', text='code:N')
    st.altair_chart(style_chart(alt.layer(band, now, dot, imgs, txt), 330), width='stretch')
    md('<div class="tr tr-legend"><span><i style="background:#F2C200;border-radius:50%"></i>Puntos finales esperados</span>'
       '<span><i style="background:#B4BCC8;width:4px;height:12px"></i>Rango probable (8 de cada 10 simulaciones)</span>'
       '<span><i style="background:#3A4558;height:2px;width:14px"></i>Puntos hoy</span></div>')


def title_curve(result, sid, champions):
    r = next(x for x in result['summary'] if x['id'] == sid)
    data = pd.DataFrame([c for c in result['curves'] if c['id'] == sid])
    data = data[(data['Título aprox. %'] > .2) | (data['Puntos finales'] >= r['Puntos previstos'])]
    data = data[(data['Título aprox. %'] < 99.8) | (data['Puntos finales'] <= (data[data['Título aprox. %'] >= 99.8]['Puntos finales'].min() if (data['Título aprox. %'] >= 99.8).any() else 999))]
    if data.empty:
        st.info('No hay suficientes escenarios para dibujar la curva.'); return
    data = data.rename(columns={'Título aprox. %': 'Opciones'})
    data = data.assign(Zona=[('Más del 80%' if v >= 80 else 'Entre 50% y 80%' if v >= 50 else 'Menos del 50%') for v in data['Opciones']])
    lo, hi = int(data['Puntos finales'].min()), int(data['Puntos finales'].max())
    refs = pd.DataFrame([{'Puntos finales': c['points'], 'txt': f"Campeón {c['season']}: {c['points']} pts", 'yy': 10 + 16*i} for i, c in enumerate(champions)])
    if not refs.empty:
        lo, hi = min(lo, int(refs['Puntos finales'].min()) - 1), max(hi, int(refs['Puntos finales'].max()) + 1)
    x = alt.X('Puntos finales:Q', title='Puntos al final de la liga', scale=alt.Scale(domain=[lo - .5, hi + .5], nice=False),
              axis=alt.Axis(tickMinStep=2, format='d'))
    bars = alt.Chart(data).mark_bar(size=max(4, 520 // max(1, hi - lo + 1) - 2)).encode(
        x=x, y=alt.Y('Opciones:Q', title='Opciones de título (%)', scale=alt.Scale(domain=[0, 100])),
        color=alt.Color('Zona:N', scale=alt.Scale(domain=['Menos del 50%', 'Entre 50% y 80%', 'Más del 80%'], range=['#B4BCC8', '#F2C200', '#1E8E5A'])),
        tooltip=[alt.Tooltip('Puntos finales:Q', title='Si terminamos con'), alt.Tooltip('Opciones:Q', format='.1f', title='Opciones de título %')])
    layers = [bars]
    if not refs.empty:
        layers.append(alt.Chart(refs).mark_rule(strokeDash=[4, 4], color=INK, strokeWidth=1.5).encode(x=x))
        layers.append(alt.Chart(refs).mark_text(align='right', dx=-5, fontSize=11, color=INK, fontWeight='bold').encode(x=x, y=alt.Y('yy:Q', scale=None), text='txt:N'))
    st.altair_chart(style_chart(alt.layer(*layers), 300), width='stretch')


def pace_tiles(result, sid, current_ppg, remaining, pts_now):
    title_pts, control_pts = target_points(result, sid, 50), target_points(result, sid, 80)
    proj_now = round(pts_now + current_ppg*remaining)
    tiles = [('Ritmo actual', current_ppg, proj_now, title_prob_at(result, sid, proj_now), '')]
    if title_pts is not None and remaining:
        tiles.append(('Ritmo título', (title_pts-pts_now)/remaining, title_pts, title_prob_at(result, sid, title_pts), 'hl'))
    if control_pts is not None and remaining:
        tiles.append(('Ritmo dominante', (control_pts-pts_now)/remaining, control_pts, title_prob_at(result, sid, control_pts), ''))
    md('<div class="tr tr-pace">' + ''.join(
        f'<div class="{cls}"><span>{label}</span><b>{ppg:.2f}</b><strong>{"≈" if not cls and label == "Ritmo actual" else ""}{pts} pts</strong>'
        f'<strong style="color:{"#1E8E5A" if prob >= 80 else INK}">{prob:.0f}% título</strong></div>'
        for label, ppg, pts, prob, cls in tiles) + '</div>')
    md('<div class="tr tr-muted" style="margin-top:6px">Puntos por partido en los partidos que quedan. <b>Ritmo título</b>: el total con el que '
       'ganamos la liga en al menos la mitad de los escenarios. <b>Ritmo dominante</b>: en 8 de cada 10.</div>')
    return title_pts


def runin_strip(needed, remaining, target):
    w, d, l = run_in(needed, remaining)
    cells = ''.join(['<i class="w">V</i>']*w + ['<i class="d">E</i>']*d + ['<i class="l">D</i>']*l)
    md(f'<div class="tr"><div class="tr-strip">{cells}</div><div class="tr-muted"><b>{w} victorias · {d} empates · {l} derrotas</b> '
       f'= {needed} puntos más → <b>{target} en total</b>. Es un ejemplo de reparto, no el único camino.</div></div>')


def goals_block(row, remaining):
    gf_now = row['GF']/row['PJ'] if row['PJ'] else 0; ga_now = row['GC']/row['PJ'] if row['PJ'] else 0
    if row.get('GF título') is None:
        md('<div class="tr tr-muted">No hay suficientes escenarios de título para estimar los goles necesarios.</div>'); return
    md(f'<div class="tr"><div class="tr-band">Goles por partido en los escenarios en que somos campeones</div>'
       f'<div class="tr-goals"><div><b>{row["GF título"]:.2f}</b><small>a favor (≈{row["GF título"]*remaining:.0f} más)</small></div>'
       f'<div><b>≤{row["GC título"]:.2f}</b><small>en contra (≈{row["GC título"]*remaining:.0f} máx.)</small></div></div>'
       f'<div class="tr-band" style="background:#E9EBEF">Lo que llevamos hasta hoy</div>'
       f'<div class="tr-goals"><div><b style="color:{"#1E8E5A" if gf_now >= row["GF título"] else "#C0702A"}">{gf_now:.2f}</b><small>marcados por partido</small></div>'
       f'<div><b style="color:{"#1E8E5A" if ga_now <= row["GC título"] else "#C0702A"}">{ga_now:.2f}</b><small>encajados por partido</small></div></div></div>')


def compare_table(root, result, squads, fixtures, ids, has_xg):
    rows = {r['id']: r for r in result['summary']}

    def per(v, r):
        return v/r['PJ'] if r['PJ'] and v is not None else None

    def per_xg(v, r):
        return v/r['xG PJ'] if r.get('xG PJ') and v is not None else None
    metrics = [
        ('Puntos', 'hoy', lambda r: r['Puntos'], 'high', '{:.0f}'),
        ('Puntos por partido', 'PPG', lambda r: r['PPG'], 'high', '{:.2f}'),
    ]
    if has_xg:
        metrics.append(('Puntos merecidos', 'xPPG · según las ocasiones', lambda r: r.get('xPPG'), 'high', '{:.2f}'))
        metrics.append(('Puntos merecidos (remate)', 'PSxPPG · según la calidad de los tiros', lambda r: r.get('PSxPPG'), 'high', '{:.2f}'))
    if any(rows[i].get('ISR') is not None for i in ids):
        metrics.append(('Nivel IMPECT', 'ISR · IMPECT Squad Rating', lambda r: r.get('ISR'), 'high', '{:.3f}'))
    metrics += [('Goles a favor', 'por partido', lambda r: per(r['GF'], r), 'high', '{:.2f}')]
    if has_xg:
        metrics += [('Ocasiones creadas', 'xG por partido', lambda r: per_xg(r.get('xG'), r), 'high', '{:.2f}'),
                    ('Calidad de remate', 'PSxG por partido', lambda r: per_xg(r.get('PSxG'), r), 'high', '{:.2f}')]
    metrics += [('Goles en contra', 'por partido', lambda r: per(r['GC'], r), 'low', '{:.2f}')]
    if has_xg:
        metrics += [('Ocasiones concedidas', 'xGA por partido', lambda r: per_xg(r.get('xGA'), r), 'low', '{:.2f}'),
                    ('Acierto de cara a gol', 'goles / tiros', lambda r: 100*r['GF']/r['Tiros'] if r.get('Tiros') else None, 'high', '{:.0f}%')]
    metrics += [
        ('Calendario restante', 'puntos esperados por partido', lambda r: (lambda e: e[0]/e[1] if e[1] else None)(expected_points(fixtures, r['Equipo'])), 'high', '{:.2f}'),
        ('Puntos finales', 'proyección', lambda r: r['Puntos previstos'], 'high', '{:.0f}'),
        ('Top 3', 'probabilidad', lambda r: r['Top 3 %'], 'high', '{:.0f}%'),
        ('Campeón', 'probabilidad', lambda r: r['Título aprox. %'], 'high', '{:.0f}%'),
    ]
    head = '<tr><th>MÉTRICA</th>' + ''.join(
        f'<th style="background:{color(sid) if sid != WASL else YELLOW};color:{INK if sid == WASL else "#fff"}"><div>{crest(root, squads[sid], 28)}{esc(name(squads[sid]))}</div></th>'
        for sid in ids) + '</tr>'
    body = []
    for label, sub, fn, better, fmt in metrics:
        vals = {sid: fn(rows[sid]) for sid in ids}
        valid = [v for v in vals.values() if v is not None]
        best = (max(valid) if better == 'high' else min(valid)) if len(valid) > 1 else None
        cells = ''.join(
            f'<td class="{"col-me " if sid == WASL else ""}{"best" if best is not None and vals[sid] == best and valid.count(best) == 1 else ""}">'
            f'{fmt.format(vals[sid]) if vals[sid] is not None else "–"}</td>' for sid in ids)
        body.append(f'<tr><td>{label}<small>{sub}</small></td>{cells}</tr>')
    md('<div class="tr"><table class="tr-cmp">' + head + ''.join(body) + '</table></div>')
    md('<div class="tr tr-muted">▲ marca al mejor de los tres en cada métrica. Las métricas de ocasiones (xG, PSxG) proceden de IMPECT.</div>')


def _funnel_side(title, sub, vals, labels, notes, deltas, good_down):
    top = max(vals + [0.1])
    hcol = ['#C9CED6', '#7D8696', YELLOW]
    bars = []
    for i, v in enumerate(vals):
        bars.append(f'<div class="bar"><b>{v:.1f}</b><i style="height:{max(4, 150*v/top):.0f}px;background:{hcol[i]}"></i></div>')
        if i < 2:
            d, text = deltas[i]
            good = (d < 0) if good_down else (d > 0)
            bars.append(f'<div class="arrow"><b style="color:{"#1E8E5A" if good else "#D64545"}">{d:+.1f}</b>{text}<br>→</div>')
    lab = []
    for i, (l, n) in enumerate(zip(labels, notes)):
        lab.append(f'<div><b>{l}</b><small>{n}</small></div>')
        if i < 2:
            lab.append('<div></div>')
    return f'<div><h4>{title}</h4><small>{sub}</small><div class="tr-bars">{"".join(bars)}</div><div class="tr-labels">{"".join(lab)}</div>'


def funnel(row):
    """Attack: xG → PSxG → goals. Defence: xGA → PSxGA → goals against (slide-style)."""
    if not row.get('xG PJ'):
        md('<div class="tr tr-muted">Sin datos de xG de IMPECT para este equipo. Pulsa «Actualizar» para descargarlos.</div>'); return
    k = row['PJ']/row['xG PJ']  # scale process totals to all played matches if coverage is partial
    xg, ps, g = row['xG']*k, row['PSxG']*k, row['GF']
    xga, psa, ga = row['xGA']*k, row['PSxGA']*k, row['GC']
    shots, shots_a = (row['Tiros'] or 0)*k, (row['Tiros en contra'] or 0)*k
    att = _funnel_side('Ataque', 'Goles a favor', [xg, ps, g], ['xG', 'PSxG', 'Goles'], ['Ocasiones que creamos', 'Calidad de nuestros tiros', 'Resultado final'],
                       [(ps-xg, 'mejores remates' if ps >= xg else 'peores remates'), (g-ps, 'acierto / fortuna' if g >= ps else 'falta de acierto')], False)
    dfn = _funnel_side('Defensa', 'Goles en contra', [xga, psa, ga], ['xGA', 'PSxGA', 'Goles en contra'], ['Ocasiones que concedemos', 'Calidad de sus tiros', 'Resultado final'],
                       [(psa-xga, 'tiros rivales más flojos' if psa <= xga else 'tiros rivales mejores'), (ga-psa, 'portero / fortuna' if ga <= psa else 'encajamos de más')], True)
    conv = 100*g/shots if shots else 0; conv_a = 100*ga/shots_a if shots_a else 0

    def verdict(level, text):
        bg, icon = {'good': ('#1E8E5A', '↑'), 'warn': ('#D9A400', '!'), 'bad': ('#D64545', '↓')}[level]
        return f'<div class="tr-verdict"><i style="background:{bg}">{icon}</i>{text}</div>'
    finish = g - xg
    att_level, v_att = (('warn', 'Marcamos muy por encima de lo que generamos: ojo, difícil de sostener') if finish > 2.5 else
                        ('good', 'Aprovechamos bien lo que creamos') if finish >= -1 else ('bad', 'Creamos más de lo que marcamos: falta acierto'))
    concede = ga - xga
    def_level, v_def = (('warn', 'Encajamos menos de lo que concedemos: el portero / la fortuna nos sostiene') if concede < -2.5 else
                        ('good', 'Lo que encajamos refleja lo que concedemos') if concede <= 1 else ('bad', 'Encajamos más de lo esperado'))
    md('<div class="tr tr-funnel">'
       f'<div>{att}<div class="tr-muted" style="margin-top:10px"><b>Conversión {conv:.0f}%</b> ({g} goles / {shots:.0f} tiros) · xG por tiro {xg/shots if shots else 0:.2f}</div>'
       f'{verdict(att_level, v_att)}</div></div>'
       f'<div>{dfn}<div class="tr-muted" style="margin-top:10px"><b>Conversión rival {conv_a:.0f}%</b> ({ga} goles / {shots_a:.0f} tiros) · xGA por tiro {xga/shots_a if shots_a else 0:.2f}</div>'
       f'{verdict(def_level, v_def)}</div></div></div>')


def evolution_chart(current, squads, ids, champions):
    rows = []
    for sid in ids:
        pts = 0
        rows.append({'PJ': 0, 'Puntos': 0, 'Equipo': name(squads[sid]), 'tipo': 'Esta temporada'})
        for n, g in enumerate(form_games(current, sid), 1):
            pts += g['points']; rows.append({'PJ': n, 'Puntos': pts, 'Equipo': name(squads[sid]), 'tipo': 'Esta temporada'})
    played = max((r['PJ'] for r in rows), default=0)
    horizon = max(played + 6, 10)
    for c in champions:
        label = f"Campeón {c['season']} ({NAMES.get(c['id'], c['name'])})"
        rows.append({'PJ': 0, 'Puntos': 0, 'Equipo': label, 'tipo': 'Referencia'})
        rows += [{'PJ': p['PJ'], 'Puntos': p['Puntos'], 'Equipo': label, 'tipo': 'Referencia'} for p in c['curve'] if p['PJ'] <= horizon]
    df = pd.DataFrame(rows)
    domain = [name(squads[i]) for i in ids] + [r for r in df[df.tipo == 'Referencia'].Equipo.unique()]
    rng = [color(i) if i != WASL else '#E0B000' for i in ids] + ['#6B7280', '#A3AAB5', '#C5CAD3'][:len(domain)-len(ids)]
    chart = alt.Chart(df).mark_line(point=alt.OverlayMarkDef(size=55, filled=True), strokeWidth=3).encode(
        x=alt.X('PJ:Q', title='Partidos jugados', axis=alt.Axis(tickMinStep=1), scale=alt.Scale(domain=[0, horizon])),
        y=alt.Y('Puntos:Q', title='Puntos acumulados'),
        color=alt.Color('Equipo:N', scale=alt.Scale(domain=domain, range=rng)),
        strokeDash=alt.StrokeDash('tipo:N', scale=alt.Scale(domain=['Esta temporada', 'Referencia'], range=[[1, 0], [5, 4]]), legend=None),
        tooltip=['Equipo', 'PJ', 'Puntos'])
    st.altair_chart(style_chart(chart, 340), width='stretch')


def xpts_chart(current, squads, ids, process):
    rows = []
    for sid in ids:
        acc_p = acc_x = 0
        for n, g in enumerate(xpts_by_game(current, sid, process), 1):
            acc_p += g['pts']; acc_x += g['xpts']
            rows.append({'PJ': n, 'Equipo': name(squads[sid]), 'Real': acc_p/n, 'Merecido': acc_x/n})
    if not rows:
        st.info('Sin xG disponible para comparar puntos reales y merecidos.'); return
    df = pd.DataFrame(rows).melt(['PJ', 'Equipo'], var_name='Tipo', value_name='PPG')
    domain = [name(squads[i]) for i in ids]
    chart = alt.Chart(df).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X('PJ:Q', title='Partidos jugados', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('PPG:Q', title='Puntos por partido (acumulado)', scale=alt.Scale(domain=[0, 3])),
        color=alt.Color('Equipo:N', scale=alt.Scale(domain=domain, range=[color(i) if i != WASL else '#E0B000' for i in ids])),
        strokeDash=alt.StrokeDash('Tipo:N', scale=alt.Scale(domain=['Real', 'Merecido'], range=[[1, 0], [5, 4]])),
        tooltip=['Equipo', 'PJ', 'Tipo', alt.Tooltip('PPG:Q', format='.2f')])
    st.altair_chart(style_chart(chart, 300), width='stretch')


def fixture_list(root, fixtures, squads, sid):
    team = squads[sid]
    items = []
    for f in fixtures:
        p = fixture_perspective(f, team['name'])
        home, away = squads[f['home_id']], squads[f['away_id']]
        rival = away if home['id'] == sid else home
        xp = (3*p['win']+p['draw'])/100
        date = (f.get('Fecha') or '')[:10]
        date = f'{date[8:10]}/{date[5:7]}' if date else ''
        meta = (f'J{f["Jornada"]} · ' if f.get('Jornada') else '') + (date if date else 'Sin fecha')
        direct = rival['id'] in FOCUS
        items.append(
            f'<div class="tr-fixture" style="--c:{color(rival["id"]) if direct else "#E3E6EB"}">'
            f'<div class="meta">{esc(meta)}<br>{"🏠 Casa" if p["venue"] == "En casa" else "✈️ Fuera"}</div>'
            f'<div class="vs">{crest(root, rival, 30)}<span>{"vs " if p["venue"] == "En casa" else "en "}{esc(name(rival))}'
            f'{" · <b style=color:#C8102E>duelo directo</b>" if direct else ""}</span></div>'
            f'<div class="tr-stack"><span style="width:{p["win"]}%;background:{WIN}">{p["win"]:.0f}</span>'
            f'<span style="width:{p["draw"]}%;background:{DRAW}">{p["draw"]:.0f}</span>'
            f'<span style="width:{p["loss"]}%;background:{LOSS}">{p["loss"]:.0f}</span></div>'
            f'<div class="xp">{xp:.1f}<small>PTS ESPERADOS</small></div></div>')
    md('<div class="tr"><div class="tr-legend"><span><i style="background:#1E8E5A"></i>Victoria %</span><span><i style="background:#8B97A8"></i>Empate %</span>'
       '<span><i style="background:#D64545"></i>Derrota %</span></div>' + ''.join(items) + '</div>')


def method_steps(n_seasons, sims, xg_weight):
    md('<div class="tr tr-steps">'
       '<div class="tr-step"><span class="n">01</span><small>Datos</small><b>Lo que pasa en el campo</b>'
       '<ul><li>Resultados y calendario de la UAE Pro League (IMPECT).</li><li>Ocasiones de cada partido: xG y PSxG (IMPECT).</li>'
       f'<li>Esta temporada + {n_seasons} anteriores, con menos peso cuanto más antiguas.</li></ul></div>'
       '<div class="tr-step"><span class="n">02</span><small>Nivel de cada equipo</small><b>¿Cuánto ataca y cuánto concede?</b>'
       f'<ul><li>Mezclamos ocasiones xG ({100*xg_weight:.0f}%) y goles ({100-100*xg_weight:.0f}%): las ocasiones predicen mejor el futuro.</li>'
       '<li>Punto de partida: el <b>ISR de IMPECT</b>. Su peso baja a medida que se juegan partidos (ver gráfico más abajo).</li><li>Se tiene en cuenta jugar en casa o fuera.</li></ul></div>'
       f'<div class="tr-step"><span class="n">03</span><small>Simulación</small><b>Jugamos la liga {f"{sims:,}".replace(",", ".")} veces</b>'
       '<ul><li>Cada partido pendiente se simula con goles aleatorios según el nivel de ambos.</li>'
       '<li>Contamos en cuántas temporadas simuladas gana cada equipo: eso es el % de título.</li>'
       '<li>Incluye la incertidumbre sobre el nivel real de cada equipo.</li></ul></div></div>')


def glossary():
    md('<div class="tr tr-gloss">'
       '<div><b>xG · goles esperados</b>Probabilidad de gol de cada ocasión según dónde y cómo se tira. Suma de un partido = goles que "merecías".</div>'
       '<div><b>PSxG · calidad del remate</b>Igual que xG, pero teniendo en cuenta a dónde va el tiro (esquina, centro…). Mide la puntería.</div>'
       '<div><b>xPPG · puntos merecidos</b>Puntos por partido que corresponderían a las ocasiones creadas y concedidas.</div>'
       '<div><b>PSxPPG · puntos merecidos (remate)</b>Lo mismo, pero con la calidad real de los tiros (PSxG): premia la puntería y castiga al rival si su portero para mucho.</div>'
       '<div><b>ISR · IMPECT Squad Rating</b>Nota global del nivel del equipo que calcula IMPECT, actualizada varias veces por semana.</div>'
       '<div><b>Rango probable</b>Entre el escenario bajo y el alto: 8 de cada 10 temporadas simuladas terminan ahí.</div></div>')


# ---------------------------------------------------------------- ISR (IMPECT Squad Rating)

def isr_series(ratings, sid, start=None, end=None):
    return [(d, v) for d, v in (ratings or {}).get(str(sid), []) if (not start or d >= start) and (not end or d <= end)]


def season_window(data):
    dates = [m['scheduledDate'][:10] for m in data['matches'] if m.get('scheduledDate')]
    return (min(dates), max(dates)) if dates else (None, None)


def isr_jumps(ratings, min_shift=.02, agree=.85, extend_days=10):
    """League-wide ISR shifts: dates where (almost) every team moves the same way at once.

    These look like IMPECT recalibrations rather than changes in form, so absolute ISR
    values before and after are not comparable; distances to the league mean are.
    """
    by_date = {}
    for sid, series in (ratings or {}).items():
        for d, v in series:
            by_date.setdefault(d, {})[sid] = v
    dates = sorted(by_date)

    def shift(a, b):
        ids = set(by_date[a]) & set(by_date[b])
        if len(ids) < 8:
            return None, 0
        ch = [by_date[b][i] - by_date[a][i] for i in ids]
        m = sum(ch)/len(ch)
        return m, sum((c > 0) == (m > 0) for c in ch)/len(ch)
    out, i = [], 1
    while i < len(dates):
        m, same = shift(dates[i-1], dates[i])
        if m is None or abs(m) < min_shift or same < agree:
            i += 1; continue
        start, end = dates[i-1], dates[i]
        while i + 1 < len(dates) and (pd.Timestamp(dates[i+1]) - pd.Timestamp(start)).days <= extend_days:
            m2, same2 = shift(dates[i], dates[i+1])
            if m2 is None or (m2 > 0) != (m > 0) or abs(m2) < .004 or same2 < agree:
                break
            i += 1; end = dates[i]
        total, _ = shift(start, end)
        out.append({'desde': start, 'hasta': end, 'cambio': round(total, 3)})
        i += 1
    return out


def fmt_date(d):
    return f'{d[8:10]}/{d[5:7]}/{d[:4]}'


def isr_alert(jumps, since):
    """Amber callout for league-wide ISR shifts since `since` (ISO date)."""
    recent = [j for j in jumps if j['hasta'] >= since]
    if not recent:
        return
    items = ''.join(f'<li>{fmt_date(j["desde"])} → {fmt_date(j["hasta"])}: todos los equipos <b>{j["cambio"]:+.3f}</b></li>' for j in recent)
    md('<div class="tr tr-callout" style="border-left-color:#D9A400;background:#FFF8E1">'
       '⚠️ <b>Ojo con el ISR: reajuste general de IMPECT.</b> En estas fechas el ISR de prácticamente todos los equipos cambió a la vez, '
       f'en la misma dirección:<ul style="margin:6px 0">{items}</ul>'
       'No significa que todos hayan mejorado (o empeorado) de golpe: es un cambio de escala. Por eso <b>no compares valores absolutos antes y después</b> '
       '(p. ej. «0,718 hoy vs 0,673 la temporada pasada»). Compara posiciones o la <b>distancia a la media de la liga</b>, que es lo que usan el modelo y esta página.</div>')


def isr_ranking(root, ratings, squads, start):
    rows = []
    for sid, s in squads.items():
        series = isr_series(ratings, sid)
        if not series:
            continue
        last_d, last = series[-1]
        month = next((v for d, v in reversed(series) if d <= (pd.Timestamp(last_d) - pd.Timedelta(days=30)).strftime('%Y-%m-%d')), None)
        season0 = next((v for d, v in reversed(series) if d <= start), None)
        rows.append((sid, last, month, season0, last_d))
    rows.sort(key=lambda r: -r[1])
    mean = sum(r[1] for r in rows)/len(rows)
    # Changes are measured on the distance to the league mean, so IMPECT's
    # league-wide recalibrations (see isr_jumps) do not show up as improvement.
    m_month = [r[2] for r in rows if r[2] is not None]; m_season = [r[3] for r in rows if r[3] is not None]
    m_month = sum(m_month)/len(m_month) if m_month else 0; m_season = sum(m_season)/len(m_season) if m_season else 0
    rows = [(sid, v, None if m is None else m - m_month + mean, None if s0 is None else s0 - m_season + mean, d) for sid, v, m, s0, d in rows]

    def delta(a, b):
        if b is None:
            return '<span class="tr-muted">–</span>'
        d = a - b
        cls = 'tr-up' if d > .002 else 'tr-down' if d < -.002 else 'tr-muted'
        return f'<span class="{cls}">{"▲" if d > .002 else "▼" if d < -.002 else "="} {d:+.3f}</span>'
    head = '<tr><th>#</th><th>Equipo</th><th>ISR</th><th class="opt">vs media</th><th title="Cambio de su distancia a la media de la liga">30 días*</th><th class="opt" title="Cambio de su distancia a la media de la liga">Desde inicio*</th></tr>'
    body = ''.join(
        f'<tr class="{"me" if sid == WASL else "rival" if sid in FOCUS else ""}"><td style="--c:{color(sid) if sid in FOCUS else "transparent"}">{i}</td>'
        f'<td><div class="tr-team">{crest(root, squads[sid], 26)}<span>{esc(name(squads[sid]))}</span></div></td>'
        f'<td><b>{v:.3f}</b></td><td class="opt">{v-mean:+.3f}</td><td>{delta(v, m)}</td><td class="opt">{delta(v, s0)}</td></tr>'
        for i, (sid, v, m, s0, _) in enumerate(rows, 1))
    md('<div class="tr"><table class="tr-table">' + head + body + '</table>'
       '<div class="tr-muted">* Cambio de la distancia a la media de la liga: descuenta los reajustes generales de IMPECT.</div></div>')
    return rows[0][4] if rows else None


def isr_chart(ratings, squads, ids, start, end=None, jumps=()):
    rows = []
    for sid in squads:
        for d, v in isr_series(ratings, sid, start, end):
            rows.append({'Fecha': d, 'ISR': v, 'Equipo': name(squads[sid]), 'foco': sid in ids})
    if not rows:
        st.info('Sin ISR para este periodo.'); return
    df = pd.DataFrame(rows)
    domain = [name(squads[i]) for i in ids]
    rng = [color(i) if i != WASL else '#E0B000' for i in ids]
    others = alt.Chart(df[~df.foco]).mark_line(strokeWidth=1.2, color='#CDD2DA').encode(
        x=alt.X('Fecha:T', title=None), y=alt.Y('ISR:Q', scale=alt.Scale(zero=False), title='ISR'), detail='Equipo:N',
        tooltip=['Equipo', alt.Tooltip('Fecha:T', format='%d/%m/%Y'), alt.Tooltip('ISR:Q', format='.3f')])
    focus = alt.Chart(df[df.foco]).mark_line(strokeWidth=3.2).encode(
        x='Fecha:T', y='ISR:Q', color=alt.Color('Equipo:N', scale=alt.Scale(domain=domain, range=rng)),
        tooltip=['Equipo', alt.Tooltip('Fecha:T', format='%d/%m/%Y'), alt.Tooltip('ISR:Q', format='.3f')])
    layers = [others, focus]
    marks = pd.DataFrame([{'Fecha': j['hasta'], 'txt': f"Reajuste {j['cambio']:+.3f}"} for j in jumps if j['hasta'] >= start])
    if not marks.empty:
        layers.append(alt.Chart(marks).mark_rule(strokeDash=[4, 4], color='#D9A400', strokeWidth=1.5).encode(x='Fecha:T', tooltip=['txt:N']))
        layers.append(alt.Chart(marks).mark_text(align='left', dx=4, dy=-4, fontSize=10, color='#9A7400', fontWeight='bold').encode(x='Fecha:T', y=alt.value(10), text='txt:N'))
    st.altair_chart(style_chart(alt.layer(*layers), 320), width='stretch')


def isr_champion_table(datasets, ratings):
    """Per complete season: each team's mean ISR (absolute and vs league mean) and final points."""
    from .title_race import table as league_table_rows
    out = []
    for d in datasets:
        if not d['matches'] or not all(score(m) is not None for m in d['matches']):
            continue
        start, end = season_window(d)
        t = league_table_rows(d)
        means = {r['id']: (sum(v for _, v in isr_series(ratings, r['id'], start, end)) / max(1, len(isr_series(ratings, r['id'], start, end)))) for r in t}
        league = sum(means.values())/len(means)
        for pos, r in enumerate(t, 1):
            out.append({'Temporada': d['iteration']['season'], 'id': r['id'], 'Equipo': NAMES.get(r['id'], r['Equipo']), 'Posición': pos,
                        'Puntos': r['Puntos'], 'ISR medio': round(means[r['id']], 3), 'ISR vs media': round(means[r['id']] - league, 3)})
    return pd.DataFrame(out)


def isr_scatter(df, current_points=None):
    """ISR (relative to league mean) vs final points, past complete seasons, plus this season's projection."""
    df = df.assign(Grupo=['Campeón' if p == 1 else 'Al Wasl' if i == WASL else 'Resto' for p, i in zip(df['Posición'], df['id'])],
                   Etiqueta=[f"{e} {t}" if p == 1 or i == WASL else '' for e, t, p, i in zip(df['Equipo'], df['Temporada'], df['Posición'], df['id'])])
    x = alt.X('ISR vs media:Q', title='ISR medio respecto a la media de la liga (0 = equipo medio)')
    y = alt.Y('Puntos:Q', title='Puntos finales')
    tip = ['Temporada', 'Equipo', 'Posición', 'Puntos', alt.Tooltip('ISR medio:Q', format='.3f'), alt.Tooltip('ISR vs media:Q', format='+.3f')]
    past = alt.Chart(df).mark_circle(size=140, opacity=.85, stroke='#fff', strokeWidth=1).encode(
        x=x, y=y, color=alt.Color('Grupo:N', scale=alt.Scale(domain=['Campeón', 'Al Wasl', 'Resto'], range=['#1E8E5A', '#E0B000', '#B4BCC8']), legend=None),
        tooltip=tip)
    labels = alt.Chart(df[df.Etiqueta != '']).mark_text(align='right', dx=-9, fontSize=10, color='#3A4558').encode(x=x, y=y, text='Etiqueta:N')
    fit = alt.Chart(df).transform_regression('ISR vs media', 'Puntos').mark_line(strokeDash=[5, 4], color=INK, opacity=.45).encode(x=x, y=y)
    layers = [fit, past, labels]
    if current_points is not None and not current_points.empty:
        now = alt.Chart(current_points).encode(x=x, y=y, tooltip=['Equipo', alt.Tooltip('Puntos:Q', title='Puntos proyectados', format='.0f'),
                                                                   alt.Tooltip('ISR vs media:Q', title='ISR hoy vs media', format='+.3f')])
        layers.append(now.mark_point(shape='diamond', size=300, filled=True, stroke=INK, strokeWidth=1.2, opacity=1).encode(
            color=alt.Color('c:N', scale=None)))
        layers.append(now.mark_text(align='left', dx=12, fontSize=11, fontWeight='bold', color=INK).encode(text='Equipo:N'))
    st.altair_chart(style_chart(alt.layer(*layers), 360), width='stretch')
    md('<div class="tr tr-legend">'
       '<span><i style="background:#1E8E5A;border-radius:50%"></i>Campeón (24/25, 25/26)</span>'
       '<span><i style="background:#E0B000;border-radius:50%"></i>Al Wasl (24/25, 25/26)</span>'
       '<span><i style="background:#B4BCC8;border-radius:50%"></i>Resto de equipos</span>'
       '<span>◆ Proyección 26/27: <b style="color:#B88A00">Al Wasl</b> · <b style="color:#C8102E">Al Jazira</b> · <b style="color:#6C3FB5">Al Ain</b></span>'
       '<span>┄ Tendencia</span></div>')


def model_comparison(comp, chosen='Goles + xG + ISR'):
    """Cards: each candidate model, how well it predicted past seasons and whether we use it."""
    reasons = {
        'Solo goles': 'Es lo más simple, pero con pocos partidos el marcador engaña (rebotes, penaltis, rachas).',
        'Goles + xG': 'A lo largo de la temporada mejora a los goles; en la jornada 5, sin ISR, aún no se nota: hay muy pocos partidos.',
        'Goles + PSxG': 'Predice <b>peor</b> que el xG: el PSxG añade puntería y porteros, que cambian mucho de un mes a otro.',
        'Goles + xG + PSxG': 'Mezclar PSxG no aporta: queda entre xG y PSxG. Lo dejamos como información, no como predicción.',
        'Goles + xG + ISR': 'El mejor en todas las métricas. El ISR da un punto de partida mucho mejor que «todos iguales».',
        'Goles + PSxG + ISR': 'Con ISR también mejora, pero sigue por detrás de usar xG.',
    }
    best = min(v['Log-loss'] for v in comp['variants'])
    naive = comp['naive_log_loss']
    cards = []
    for v in comp['variants']:
        used = v['Modelo'] == chosen
        skill = 100*(naive - v['Log-loss'])/naive
        cards.append(
            f'<div class="tr-card{" me" if used else ""}" style="--c:{YELLOW if used else "#C9CED6"}">'
            f'<div class="tr-card-head"><div><strong style="font-size:21px">{esc(v["Modelo"])}</strong>'
            f'<small>{"✅ EL QUE USAMOS" if used else "No se usa"}</small></div></div>'
            f'<div class="tr-mini" style="grid-template-columns:repeat(3,1fr)">'
            f'<div><b>{skill:.1f}%</b><small>Mejor que adivinar</small></div>'
            f'<div><b>{v["Error medio (pts)"]:.1f}</b><small>Error pts finales</small></div>'
            f'<div><b>{v["Prob. del campeón %"]:.0f}%</b><small>Al campeón real</small></div></div>'
            f'<div class="tr-muted" style="margin-top:10px">{reasons.get(v["Modelo"], "")}</div></div>')
    md('<div class="tr tr-cards3">' + ''.join(cards) + '</div>')
    md(f'<div class="tr tr-muted" style="margin-top:8px">Evaluado sobre {comp["variants"][0]["Partidos evaluados"]:,} predicciones de partido '.replace(',', '.') +
       f'(temporadas 24/25 y 25/26, cortando en las jornadas {", ".join(str(c) for c in comp["cuts"])}). '
       '«Mejor que adivinar»: cuánto reduce el error de pronóstico 1X2 frente a usar solo los porcentajes medios de la liga (gana local 40%, empate 23%, gana visitante 37%). '
       'En fútbol, mejoras de 3–8% son normales: el azar pesa mucho en cada partido.</div>')


# ---------------------------------------------------------------- scenarios & explanations

def scenario_cards(result, sid, squads):
    """Pessimistic / conservative / optimistic final outcome for one team (P10 / P50 / P90 of the simulations)."""
    r = next(x for x in result['summary'] if x['id'] == sid)
    rem = r['Pendientes']
    specs = [('Pesimista', r['P10'], r['Pos pesimista'], '#D64545', 'Solo 1 de cada 10 temporadas simuladas sale peor.'),
             ('Conservador', r['P50'], r['Pos central'], YELLOW, 'Escenario central: la mitad de las simulaciones sale mejor y la mitad peor.'),
             ('Optimista', r['P90'], r['Pos optimista'], '#1E8E5A', 'Solo 1 de cada 10 temporadas simuladas sale mejor.')]
    cards = []
    for label, pts, pos, c, note in specs:
        need = pts - r['Puntos']
        w, d, l = run_in(need, rem) if rem else (0, 0, 0)
        cards.append(
            f'<div class="tr-card{" me" if label == "Conservador" else ""}" style="--c:{c}">'
            f'<div class="tr-card-head"><div><strong>{label}</strong><small>{note}</small></div></div>'
            f'<div class="tr-big">{pts}<span> pts</span></div><div class="tr-muted">al final de la liga · {ordinal(pos)} puesto</div>'
            f'<div class="tr-mini"><div><b>{(need/rem if rem else 0):.2f}</b><small>Pts/partido desde hoy</small></div>'
            f'<div><b>{w}-{d}-{l}</b><small>V-E-D aprox.</small></div>'
            f'<div><b>{title_prob_at(result, sid, pts):.0f}%</b><small>Título con esos pts</small></div></div></div>')
    md('<div class="tr tr-cards3">' + ''.join(cards) + '</div>')
    md('<div class="tr tr-muted" style="margin-top:6px">Los escenarios salen de las 20.000 temporadas simuladas: no son opiniones, son el '
       'percentil 10, 50 y 90 de los puntos finales. El puesto es el de cada escenario por separado. «Título con esos pts»: opciones de ganar la liga si terminamos con esa cifra.</div>')


def scenario_table(root, result, squads, ids):
    rows = {r['id']: r for r in result['summary']}
    body = ''.join(
        f'<tr class="{"me" if i == WASL else "rival"}"><td style="--c:{color(i)}"></td>'
        f'<td><div class="tr-team">{crest(root, squads[i], 24)}<span>{esc(name(squads[i]))}</span></div></td>'
        f'<td>{rows[i]["P10"]} <span class="rng">{ordinal(rows[i]["Pos pesimista"])}</span></td>'
        f'<td><b>{rows[i]["P50"]}</b> <span class="rng">{ordinal(rows[i]["Pos central"])}</span></td>'
        f'<td>{rows[i]["P90"]} <span class="rng">{ordinal(rows[i]["Pos optimista"])}</span></td></tr>' for i in ids)
    md('<div class="tr"><table class="tr-table"><tr><th></th><th>Equipo</th><th>Pesimista</th><th>Conservador</th><th>Optimista</th></tr>'
       + body + '</table></div>')


def weights_chart(rows, played):
    df = pd.DataFrame(rows).melt('PJ', var_name='Fuente', value_name='Peso')
    order = ['ISR', 'Temporadas anteriores', 'Esta temporada']
    area = alt.Chart(df).mark_area(opacity=.9).encode(
        x=alt.X('PJ:Q', title='Partidos jugados esta temporada', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('Peso:Q', stack='normalize', title='Peso en el nivel del equipo', axis=alt.Axis(format='%')),
        color=alt.Color('Fuente:N', sort=order, scale=alt.Scale(domain=order, range=['#6C3FB5', '#B4BCC8', YELLOW])),
        order=alt.Order('orden:Q'), tooltip=['PJ', 'Fuente', alt.Tooltip('Peso:Q', format='.0%')]
    ).transform_calculate(orden="indexof(['ISR','Temporadas anteriores','Esta temporada'], datum.Fuente)")
    rule = alt.Chart(pd.DataFrame({'PJ': [played]})).mark_rule(color=INK, strokeDash=[4, 4], strokeWidth=2).encode(x='PJ:Q')
    st.altair_chart(style_chart(area + rule, 260), width='stretch')


def match_explainer(result, fixture, squads, sid):
    """Worked example: how the expected goals and 1X2 of one fixture are obtained."""
    p = result['parameters']
    h, a = fixture['home_id'], fixture['away_id']
    att_h, att_a = p['attack'][str(h)], p['attack'][str(a)]
    def_h, def_a = p['defence'][str(h)], p['defence'][str(a)]
    lh, la = p['home_mean']*att_h*def_a, p['away_mean']*att_a*def_h
    nh, na = esc(name(squads[h])), esc(name(squads[a]))
    md(f'''<div class="tr tr-callout" style="line-height:1.75">
<b>Ejemplo: {nh} (casa) – {na} (fuera)</b><br>
<b>1. Media de la liga.</b> Un equipo local marca de media <b>{p["home_mean"]:.2f}</b> goles y uno visitante <b>{p["away_mean"]:.2f}</b>.<br>
<b>2. Nivel de cada uno</b> (1,00 = equipo medio de la liga). Ataque de {nh}: <b>{att_h:.2f}</b> · lo que concede {na}: <b>{def_a:.2f}</b>.
Ataque de {na}: <b>{att_a:.2f}</b> · lo que concede {nh}: <b>{def_h:.2f}</b>.<br>
<b>3. Goles esperados.</b> {nh}: {p["home_mean"]:.2f} × {att_h:.2f} × {def_a:.2f} = <b>{lh:.2f}</b> · {na}: {p["away_mean"]:.2f} × {att_a:.2f} × {def_h:.2f} = <b>{la:.2f}</b>.<br>
<b>4. De goles a resultado.</b> Con esos goles esperados se sortea el marcador miles de veces (distribución de Poisson, la habitual para goles en fútbol)
y se cuenta: gana {nh} <b>{fixture["P(local) %"]:.0f}%</b>, empate <b>{fixture["P(empate) %"]:.0f}%</b>, gana {na} <b>{fixture["P(visitante) %"]:.0f}%</b>.<br>
<span class="tr-muted">El «ataque» y lo que «concede» cada equipo salen del ISR, de sus partidos (80% xG + 20% goles) y de las temporadas anteriores.
Ejemplo: ataque 1,30 = genera un 30% más que un equipo medio; concede 0,75 = permite un 25% menos.</span></div>''')


# ---------------------------------------------------------------- market lens (experimental)

def market_table(root, values, result, market_result, squads):
    """Squad value vs level (ISR) vs projection; who performs above or below their budget.

    values: {squad id: euros}.
    """
    import numpy as np
    base = {r['id']: r for r in result['summary']}
    alt_r = {r['id']: r for r in market_result['summary']}
    rows = [(sid, values[sid]) for sid in squads if values.get(sid)]
    rows.sort(key=lambda r: -r[1])
    slope, icpt = value_fit(values, result)
    isr_rank = {r['id']: i for i, r in enumerate(sorted(result['summary'], key=lambda r: -(r.get('ISR') or 0)), 1)}
    proj_rank = {r['id']: i for i, r in enumerate(sorted(result['summary'], key=lambda r: -r['Puntos previstos']), 1)}
    head = ('<tr><th>#</th><th>Equipo</th><th>Valor (M€)</th><th class="opt">Puesto ISR</th><th class="opt">Puesto proyectado</th>'
            '<th title="Puntos proyectados menos los que corresponderían a su valor de plantilla">vs su valor</th>'
            '<th>Título · modelo</th><th>Título · mercado</th></tr>')
    body = []
    for i, (sid, v) in enumerate(rows, 1):
        diff = base[sid]['Puntos previstos'] - (icpt + slope*np.log(v))
        cls = 'tr-up' if diff > 2 else 'tr-down' if diff < -2 else 'tr-muted'
        word = 'por encima' if diff > 2 else 'por debajo' if diff < -2 else 'en línea'
        p1, p2 = base[sid]['Título aprox. %'], alt_r[sid]['Título aprox. %']
        body.append(
            f'<tr class="{"me" if sid == WASL else "rival" if sid in FOCUS else ""}"><td style="--c:{color(sid) if sid in FOCUS else "transparent"}">{i}</td>'
            f'<td><div class="tr-team">{crest(root, squads[sid], 26)}<span>{esc(name(squads[sid]))}</span></div></td>'
            f'<td><b>{v/1e6:.0f}</b></td><td class="opt">{isr_rank[sid]}º</td><td class="opt">{proj_rank[sid]}º</td>'
            f'<td><span class="{cls}">{diff:+.0f} pts</span> <span class="rng">{word}</span></td>'
            f'<td>{p1:.0f}%</td><td>{p2:.0f}%</td></tr>')
    md('<div class="tr"><table class="tr-table">' + head + ''.join(body) + '</table></div>')


def market_scatter(root, values, result, squads, xlabel='Valor de los 18 jugadores más valiosos (M€, escala logarítmica)'):
    df = pd.DataFrame([{'Equipo': name(squads[r['id']]), 'code': code(r['id'], squads[r['id']]), 'Valor': values[r['id']]/1e6,
                        'Puntos': r['Puntos previstos'], 'c': (color(r['id']) if r['id'] != WASL else '#E0B000') if r['id'] in FOCUS else '#B4BCC8',
                        'img': crest_src(root, squads[r['id']])}
                       for r in result['summary'] if values.get(r['id'])])
    x = alt.X('Valor:Q', scale=alt.Scale(type='log', domain=[float(df.Valor.min())*.85, float(df.Valor.max())*1.15], nice=False), title=xlabel)
    y = alt.Y('Puntos:Q', title='Puntos finales proyectados (modelo principal)', scale=alt.Scale(zero=False))
    tip = ['Equipo', alt.Tooltip('Valor:Q', format='.0f', title='Valor M€'), alt.Tooltip('Puntos:Q', format='.0f')]
    fit = alt.Chart(df).transform_regression('Valor', 'Puntos', method='log').mark_line(strokeDash=[5, 4], color=INK, opacity=.45).encode(x=x, y=y)
    dots = alt.Chart(df).mark_circle(size=520, opacity=.25).encode(x=x, y=y, color=alt.Color('c:N', scale=None), tooltip=tip)
    imgs = alt.Chart(df[df.img != '']).mark_image(width=24, height=24).encode(x=x, y=y, url='img:N', tooltip=tip)
    txt = alt.Chart(df[df.img == '']).mark_text(fontWeight='bold', fontSize=10, color='#3A4558').encode(x=x, y=y, text='code:N')
    st.altair_chart(style_chart(alt.layer(fit, dots, imgs, txt), 360), width='stretch')
    md('<div class="tr tr-legend"><span>Cada escudo es un equipo</span><span>┄ Puntos que «tocarían» según su valor</span>'
       '<span>Por encima de la línea: rinde más de lo que vale · por debajo: menos</span></div>')


def value_fit(values, result):
    """Line «points a team of this value usually gets»: projected points ~ a + b·log(value), fitted on all teams."""
    import numpy as np
    pts = {r['id']: r['Puntos previstos'] for r in result['summary']}
    ids = [i for i in values if values[i] and i in pts]
    slope, icpt = np.polyfit(np.log([values[i] for i in ids]), [pts[i] for i in ids], 1)
    return float(slope), float(icpt)


def value_method(source, top_n=18):
    """Plain explanation of how the squad value is computed for each source."""
    if source == 'tm':
        body = ('<b>1. Valor de cada jugador.</b> El que tenía en Transfermarkt el día que empezó la temporada.<br>'
                '<b>2. Peso de cada jugador según sus minutos</b> (IMPECT). Quien lo ha jugado todo cuenta como 1 puesto del once; '
                'quien ha jugado la mitad, como medio puesto. Los pesos de todo el equipo suman 11.<br>'
                '<b>3. Valor del equipo</b> = suma de (valor × peso) de todos los jugadores que han jugado. '
                'Es el valor medio del once que de verdad sale al campo, contando rotaciones y suplentes.<br>'
                '<span class="tr-muted">Por qué así y no un once tipo fijo: un jugador caro que apenas juega aporta poco, y los canteranos '
                'que no juegan no inflan el valor. Con pocas jornadas una lesión o rotación pesa mucho; cada jornada la cifra se estabiliza.</span>')
    else:
        body = (f'<b>Valor del equipo</b> = suma del valor de mercado de sus <b>{top_n} jugadores más valiosos</b> según BeSoccer (foto de hoy).<br>'
                '<span class="tr-muted">No se ponderan minutos porque los jugadores de BeSoccer no se pueden cruzar con IMPECT. Se usan los 18 más valiosos y no el total '
                'porque la fuente mezcla plantillas de 17 jugadores con otras de 57 (canteranos incluidos). Por eso las cifras no son comparables con '
                'Transfermarkt: solo el orden entre equipos.</span>')
    md(f'<div class="tr tr-callout">{body}</div>')


def value_breakdown(rows, team_name):
    """Player-by-player table behind the Transfermarkt XI value."""
    total = sum(r['contribution'] for r in rows)
    body = ''.join(
        f'<tr><td></td><td style="text-align:left">{esc(r["name"])}</td><td>{r["minutes"]:.0f}</td>'
        f'<td>{(r["value"] or 0)/1e6:.2f}</td><td>{r["weight"]:.2f}</td><td><b>{r["contribution"]/1e6:.2f}</b></td></tr>' for r in rows)
    md('<div class="tr"><table class="tr-table"><tr><th></th><th>Jugador</th><th>Minutos</th><th>Valor M€</th>'
       '<th title="Puestos del once que ocupa según sus minutos">Cuenta como…</th><th>Aporta M€</th></tr>' + body
       + f'<tr class="me"><td></td><td style="text-align:left">Total {esc(team_name)}</td><td></td><td></td>'
       f'<td>{sum(r["weight"] for r in rows):.2f}</td><td>{total/1e6:.2f}</td></tr></table>'
       '<div class="tr-muted">«Cuenta como…»: puestos del once (1,00 = lo ha jugado todo). Aporta = valor × cuenta como. '
       'Jugadores sin valoración en Transfermarkt no cuentan (normalmente canteranos con pocos minutos).</div></div>')


def value_gap_explainer(values, result, squads, sid):
    """Worked example of «above / below its value» for one team."""
    import numpy as np
    slope, icpt = value_fit(values, result)
    r = next(x for x in result['summary'] if x['id'] == sid)
    v = values[sid]
    expected = icpt + slope*np.log(v)
    diff = r['Puntos previstos'] - expected
    word = 'por encima de' if diff > 2 else 'por debajo de' if diff < -2 else 'en línea con'
    md('<div class="tr tr-callout" style="line-height:1.75">'
       '<b>¿Cómo se sabe si un equipo rinde por encima o por debajo de su valor?</b><br>'
       '<b>1. La línea de referencia.</b> Con los 14 equipos se traza la línea que mejor relaciona valor de plantilla y puntos finales '
       'proyectados (la línea discontinua del gráfico). Indica cuántos puntos «suele» hacer un equipo que vale lo que vale. Se usa escala '
       'logarítmica porque duplicar el valor no duplica los puntos: pasar de 5 a 10 M€ se nota tanto como pasar de 20 a 40 M€.<br>'
       f'<b>2. Lo que le «tocaría».</b> {esc(name(squads[sid]))} vale <b>{v/1e6:.1f} M€</b> → según la línea le corresponderían '
       f'<b>{expected:.0f} puntos</b>.<br>'
       f'<b>3. Lo que proyecta el modelo principal</b> (ISR + partidos): <b>{r["Puntos previstos"]:.0f} puntos</b>.<br>'
       f'<b>4. Diferencia:</b> {r["Puntos previstos"]:.0f} − {expected:.0f} = <b>{diff:+.0f} puntos</b> → rinde <b>{word}</b> su valor.<br>'
       '<span class="tr-muted">Entre −2 y +2 puntos se considera «en línea»: margen pequeño para no sobreinterpretar. Por encima de la línea = '
       'saca más de lo que vale su plantilla (entrenador, sistema, cohesión…); por debajo = rinde menos de lo que cuesta.</span></div>')


# ---------------------------------------------------------------- squads: ELO & market value P75 by season (BeSoccer)

def _sq_fmt(metric, v):
    if v is None:
        return '–'
    return f'{v:.0f}' if metric == 'elo_p75' else f'{v/1e6:.1f}'


def squad_evolution_table(root, rows, squads_all, metric, seasons, current_ids):
    """Card table: one row per team of the current season, one column per season, plus the change."""
    data = {(r['season'], r['id']): r for r in rows}
    last, first = seasons[-1], seasons[0]
    teams = sorted(current_ids, key=lambda i: -((data.get((last, i)) or {}).get(metric) or 0))
    head = ('<tr><th>#</th><th>Equipo</th>' + ''.join(f'<th>{esc(s[2:])}</th>' for s in seasons)
            + f'<th title="Cambio entre {first} y {last}">Δ</th></tr>')
    body = []
    for n, sid in enumerate(teams, 1):
        vals = [(data.get((s, sid)) or {}).get(metric) for s in seasons]
        known = [v for v in vals if v is not None]
        delta = ''
        if len(known) >= 2:
            d = known[-1] - known[0]
            txt = f'{d:+.0f}' if metric == 'elo_p75' else f'{d/1e6:+.1f}'
            cls = 'tr-up' if d > 0 else 'tr-down' if d < 0 else 'tr-muted'
            delta = f'<span class="{cls}">{"▲" if d > 0 else "▼" if d < 0 else "="} {txt}</span>'
        cells = ''.join(f'<td>{"<b>" if i == len(vals)-1 else ""}{_sq_fmt(metric, v)}{"</b>" if i == len(vals)-1 else ""}</td>'
                        for i, v in enumerate(vals))
        body.append(f'<tr class="{"me" if sid == WASL else "rival" if sid in SQ_FOCUS else ""}"><td style="--c:{sq_color(sid) if sid in SQ_FOCUS else "transparent"}">{n}</td>'
                    f'<td><div class="tr-team">{crest(root, squads_all[sid], 24)}<span>{esc(name(squads_all[sid]))}</span></div></td>{cells}<td>{delta}</td></tr>')
    md('<div class="tr"><table class="tr-table">' + head + ''.join(body) + '</table>'
       + ('<div class="tr-muted">«–»: el equipo no estaba en la liga esa temporada.</div>' ) + '</div>')


def squad_evolution_chart(rows, squads_all, metric, ids, ytitle):
    df = pd.DataFrame([{'Temporada': r['season'], 'Equipo': name(squads_all[r['id']]), 'foco': r['id'] in ids,
                        'Valor': (r[metric] if metric == 'elo_p75' else r[metric]/1e6) if r[metric] is not None else None,
                        'n': r['elo_n'] if metric == 'elo_p75' else r['value_n']}
                       for r in rows if r['id'] in squads_all]).dropna(subset=['Valor'])
    x = alt.X('Temporada:O', title=None, axis=alt.Axis(labelAngle=0))
    y = alt.Y('Valor:Q', title=ytitle, scale=alt.Scale(zero=False))
    tip = ['Equipo', 'Temporada', alt.Tooltip('Valor:Q', format='.1f' if metric != 'elo_p75' else '.0f', title=ytitle), alt.Tooltip('n:Q', title='Jugadores con dato')]
    others = alt.Chart(df[~df.foco]).mark_line(point=alt.OverlayMarkDef(size=25, color='#B4BCC8'), strokeWidth=1.3, color='#CDD2DA').encode(x=x, y=y, detail='Equipo:N', tooltip=tip)
    domain = [name(squads_all[i]) for i in ids]
    focus = alt.Chart(df[df.foco]).mark_line(point=alt.OverlayMarkDef(size=80, filled=True), strokeWidth=3.2).encode(
        x=x, y=y, color=alt.Color('Equipo:N', scale=alt.Scale(domain=domain, range=[color(i) if i != WASL else '#E0B000' for i in ids])), tooltip=tip)
    st.altair_chart(style_chart(others + focus, 300), width='stretch')


def squad_cross(root, rows, squads_all, season, ids):
    """ELO P75 vs market value P75 for one season, crests, plus Al Wasl's path season by season."""
    df = pd.DataFrame([{'Equipo': name(squads_all[r['id']]), 'ELO': r['elo_p75'], 'Valor': r['value_p75']/1e6,
                        'img': crest_src(root, squads_all[r['id']]), 'code': code(r['id'], squads_all[r['id']]),
                        'c': sq_color(r['id']) if r['id'] in ids else '#B4BCC8'}
                       for r in rows if r['season'] == season and r['elo_p75'] and r['value_p75']])
    trail = pd.DataFrame([{'ELO': r['elo_p75'], 'Valor': r['value_p75']/1e6, 'Temporada': r['season'][2:]}
                          for r in rows if r['id'] == WASL and r['elo_p75'] and r['value_p75']]).sort_values('Temporada')
    x = alt.X('ELO:Q', title='P75 del ELO de la plantilla', scale=alt.Scale(zero=False))
    y = alt.Y('Valor:Q', title='P75 del valor de mercado (M€)', scale=alt.Scale(domainMin=0))
    tip = ['Equipo', alt.Tooltip('ELO:Q', format='.0f'), alt.Tooltip('Valor:Q', format='.2f', title='Valor M€')]
    halo = alt.Chart(df).mark_circle(size=560, opacity=.25).encode(x=x, y=y, color=alt.Color('c:N', scale=None), tooltip=tip)
    imgs = alt.Chart(df[df.img != '']).mark_image(width=24, height=24).encode(x=x, y=y, url='img:N', tooltip=tip)
    txt = alt.Chart(df[df.img == '']).mark_text(fontWeight='bold', fontSize=10, color='#3A4558').encode(x=x, y=y, text='code:N')
    path = alt.Chart(trail).mark_line(strokeDash=[4, 3], color='#E0B000', strokeWidth=2, point=alt.OverlayMarkDef(color='#E0B000', size=40)).encode(
        x=x, y=y, order='Temporada:O', tooltip=['Temporada', alt.Tooltip('ELO:Q', format='.0f'), alt.Tooltip('Valor:Q', format='.2f')])
    lbl = alt.Chart(trail).mark_text(dx=10, dy=-8, fontSize=10, fontWeight='bold', color='#9A7400').encode(x=x, y=y, text='Temporada:N')
    fit = alt.Chart(df).transform_regression('ELO', 'Valor').mark_line(strokeDash=[5, 4], color=INK, opacity=.4, clip=True).encode(x=x, y=y)
    st.altair_chart(style_chart(alt.layer(fit, path, lbl, halo, imgs, txt), 380), width='stretch')
    md('<div class="tr tr-legend"><span>Cada escudo es un equipo en la temporada elegida</span>'
       '<span><b style="color:#B88A00">┄ Recorrido de Al Wasl</b> temporada a temporada</span>'
       '<span>┄ Tendencia de la liga esa temporada</span><span>Arriba a la derecha: plantillas fuertes y caras</span></div>')


# ---------------------------------------------------------------- squads tab: wider set of highlighted clubs + PLAYER VALUE AVG

SQ_EXTRA = {2090: '#3E8E41', 2093: '#2A9D8F', 6615: '#1E4FA0', 2041: '#8C2F39'}   # Shabab Al Ahli, Sharjah, Al Nasr, Al Wahda
SQ_FOCUS = FOCUS + list(SQ_EXTRA)


def sq_color(sid):
    if sid == WASL:
        return '#E0B000'
    return COLORS.get(sid) or SQ_EXTRA.get(sid) or GREY


def sq_lines(rows, squads_all, root, value_fn, ytitle, fmt='.0f', ids=SQ_FOCUS, height=320):
    """Season evolution: highlighted clubs in colour with their crest at the last point, rest in grey."""
    df = pd.DataFrame([{'Temporada': r['season'], 'id': r['id'], 'Equipo': name(squads_all[r['id']]), 'Valor': value_fn(r)}
                       for r in rows if r['id'] in squads_all]).dropna(subset=['Valor'])
    if df.empty:
        st.info('Sin datos.'); return
    df['foco'] = df.id.isin(ids)
    x = alt.X('Temporada:O', title=None, axis=alt.Axis(labelAngle=0))
    y = alt.Y('Valor:Q', title=ytitle, scale=alt.Scale(zero=False))
    tip = ['Equipo', 'Temporada', alt.Tooltip('Valor:Q', format=fmt, title=ytitle)]
    others = alt.Chart(df[~df.foco]).mark_line(point=alt.OverlayMarkDef(size=20, color='#C5CAD3'), strokeWidth=1.2, color='#D5D9E0').encode(
        x=x, y=y, detail='Equipo:N', tooltip=tip)
    present = [i for i in ids if i in set(df.id)]
    domain = [name(squads_all[i]) for i in present]
    focus = alt.Chart(df[df.foco]).mark_line(point=alt.OverlayMarkDef(size=60, filled=True), strokeWidth=3).encode(
        x=x, y=y, color=alt.Color('Equipo:N', scale=alt.Scale(domain=domain, range=[sq_color(i) for i in present])), tooltip=tip)
    last = df[df.foco].sort_values('Temporada').groupby('id').tail(1).copy()
    last['img'] = [crest_src(root, squads_all[i]) for i in last.id]
    ends = alt.Chart(last[last.img != '']).mark_image(width=22, height=22, xOffset=16).encode(x=x, y=y, url='img:N', tooltip=tip)
    st.altair_chart(style_chart(alt.layer(others, focus, ends), height), width='stretch')


def pv_method(share_incomplete, mode='general'):
    md('<div class="tr tr-callout" style="line-height:1.7"><b>PLAYER VALUE AVG · qué mide.</b> Cuánto vale un jugador frente a sus pares, '
       'en dos lecturas que se promedian: la liga y su propio club. Escala 0–100.<br>'
       '<b>Entradas por jugador y temporada</b> (BeSoccer): ELO y valor de mercado de esa temporada; <b>tendencia</b> de ELO y de valor '
       + ('(% de cambio entre el primer y el último año de una ventana de 3 años de la gráfica de BeSoccer: 2024→2026 para 26/27, 2023→2025 para 25/26; '
          'es la variación total en esos años, no una media anual)' if mode == 'general' else
          '(Modelo media: % de cambio de la temporada frente a la media de dos temporadas antes, p. ej. 25/26 frente a 23/24)') +
       '; <b>cohorte</b> por año de nacimiento (≤1991 · 1992–98 · 1999–02 · 2003–05 · 2006–10); '
       '<b>posición</b> amplia (GK · DEF · MID · ATT).<br>'
       '<b>PV = 0,40·pct(ELO) + 0,10·pct(tendencia ELO) + 0,40·pct(valor) + 0,10·pct(tendencia valor)</b>, calculado dos veces:<br>'
       '· <b>PV LEAGUE</b>: percentil dentro de su cohorte y posición, entre todos los jugadores de la liga esa temporada.<br>'
       '· <b>PV TEAM</b>: percentil dentro de su club y posición.<br>'
       '<b>PLAYER VALUE AVG = (PV LEAGUE + PV TEAM) / 2</b><br>'
       '<span class="tr-muted">Ojo al leerlo: los percentiles dependen del grupo (si entra o sale alguien, cambian los demás). '
       f'Si falta algún dato (sin valor publicado o sin años previos para la tendencia, {share_incomplete:.0%} de los casos) se calcula con '
       'el resto de piezas, reescalando los pesos, y se marca con ◌. Se añade la cohorte ≤1991, que el método original no tenía y agrupa al 14% de '
       'jugadores. No hay entradas manuales: todo es BeSoccer.<br>'
       '<b>Dato del momento:</b> el ELO y el valor son los del jugador mientras está en el club. En la temporada actual, los de su ficha de BeSoccer hoy '
       '(los mismos para todos los equipos). Los fichajes de invierno (❄️, primer partido después del 1 de enero según IMPECT) usan sus datos del año en que '
       'llegaron, no los de antes (p. ej. Borja 25/26: 4,5 M€ al llegar en 2026, no los 11 M€ de 2025).</span></div>')


def pv_table(df):
    """Player table for one club and season."""
    def pill(v):
        if v != v:
            return '–'
        bg = '#1E8E5A' if v >= 75 else YELLOW if v >= 50 else '#EEF0F3'
        fg = '#fff' if v >= 75 else INK
        return f'<span class="tr-pill" style="background:{bg};color:{fg}">{v:.0f}</span>'

    def trend(v, unit=''):
        if v != v or v is None:
            return '<span class="tr-muted">–</span>'
        cls = 'tr-up' if v > 0 else 'tr-down' if v < 0 else 'tr-muted'
        return f'<span class="{cls}">{v:+.0f}{unit}</span>' if unit == '%' else f'<span class="{cls}">{v:+.1f}{unit}</span>'
    body = ''.join(
        f'<tr><td></td><td style="text-align:left"><b>{esc(r.player)}</b>{" <span title=\'Fichaje de invierno: datos de su llegada\'>❄️</span>" if getattr(r, "winter", False) else ""}{" <span class=tr-muted>◌</span>" if r.incompleto else ""}</td>'
        f'<td>{r.pos}</td><td class="opt">{esc(r.cohort or "–")}</td><td class="opt">{f"{r.minutes:.0f}" if r.minutes > 0 else "<span class=tr-muted>sin minutos</span>"}</td>'
        f'<td>{"–" if r.elo != r.elo else f"{r.elo:.0f}"}</td><td class="opt">{trend(r.elo_trend, "%")}</td>'
        f'<td>{"–" if r.value != r.value else f"{r.value/1e6:.1f}"}</td><td class="opt">{trend(r.value_trend, "%")}</td>'
        f'<td>{pill(r.pv_league)}</td><td>{pill(r.pv_team)}</td><td>{pill(r.pv_avg)}</td></tr>'
        for r in df.itertuples())
    md('<div class="tr" style="overflow-x:auto"><table class="tr-table"><tr><th></th><th>Jugador</th><th>Pos.</th><th class="opt">Cohorte</th><th class="opt">Min.</th>'
       '<th>ELO</th><th class="opt" title="% de cambio en los últimos 3 años">Tend. ELO</th><th>Valor M€</th><th class="opt" title="% de cambio en los últimos 3 años">Tend. valor</th>'
       '<th title="Percentil frente a su cohorte y posición en la liga">PV LEAGUE</th><th title="Percentil frente a su club y posición">PV TEAM</th>'
       '<th>PV AVG</th></tr>' + body + '</table>'
       '<div class="tr-muted">Toda la plantilla de BeSoccer de esa temporada; minutos de IMPECT cuando están disponibles (van al día), si no de BeSoccer. Verde ≥ 75 · amarillo 50–75. Tendencias: % de cambio en los últimos 3 años (gráfica de BeSoccer). ❄️ = fichaje de invierno (datos de su llegada). ◌ = falta algún dato (pesos reescalados).</div></div>')


def pv_reference_table(pv, reference):
    """Our PLAYER VALUE AVG next to a colleague's report, player by player (Al Wasl)."""
    rows, diffs = [], []
    wasl = pv[pv.team == 'Al-Wasl']
    for ref in reference.get('players', []):
        cand = wasl[wasl.season == ref['season']]
        cand = cand[cand.player_id == ref['player_id']] if ref.get('player_id') else cand[cand.player.str.contains(ref['match'])]
        if cand.empty:
            continue
        r = cand.iloc[0]; d = r.pv_avg - ref['pv_avg']; diffs.append(abs(d))
        cls = 'tr-up' if abs(d) <= 2 else 'tr-muted' if abs(d) <= 4 else 'tr-down'
        icon = '✅' if abs(d) <= 2 else '≈' if abs(d) <= 4 else '⚠️'
        rows.append(f'<tr><td></td><td style="text-align:left"><b>{esc(r.player)}</b>{" ❄️" if r.winter else ""}</td><td>{esc(ref["season"][2:])}</td>'
                    f'<td>{r.elo:.0f}</td><td>{(r.value or 0)/1e6:.2f}</td>'
                    f'<td>{"–" if r.elo_trend != r.elo_trend else f"{r.elo_trend:+.0f}%"}</td><td>{"–" if r.value_trend != r.value_trend else f"{r.value_trend:+.0f}%"}</td>'
                    f'<td><b>{ref["pv_avg"]:.1f}</b></td><td><b>{r.pv_avg:.1f}</b></td><td><span class="{cls}">{icon} {d:+.1f}</span></td></tr>')
    if not rows:
        st.info('No se encontraron los jugadores del informe de referencia.'); return
    kpi_tiles([(f'{len(rows)}', 'Jugadores comparados', 'del informe del compañero'),
               (f'{sum(x <= 2 for x in diffs)}', 'Cuadran (±2 puntos)', ''),
               (f'{sum(2 < x <= 4 for x in diffs)}', 'Cerca (±4 puntos)', ''),
               (f'{sum(x > 4 for x in diffs)}', 'No cuadran (>4 puntos)', ''),
               (f'{sum(diffs)/len(diffs):.1f}', 'Diferencia media', 'puntos de PV AVG')])
    md('<div class="tr" style="overflow-x:auto"><table class="tr-table"><tr><th></th><th>Jugador</th><th>Temp.</th><th>ELO</th><th>Valor M€</th>'
       '<th>Tend. ELO</th><th>Tend. valor</th><th>PV AVG compañero</th><th>PV AVG nuestro</th><th>Diferencia</th></tr>'
       + ''.join(rows) + '</table>'
       f'<div class="tr-muted">Referencia: {esc(reference.get("source", ""))}. ELO, valor y tendencias son nuestros datos de entrada (BeSoccer). '
       '✅ ±2 · ≈ ±4 · ⚠️ más de 4 puntos. ❄️ fichaje de invierno.</div></div>')
