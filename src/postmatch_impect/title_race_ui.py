from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from .title_race import (
    evidence_shares,
    backtest, complete_calendar, forecast, load_process, load_ratings, load_market, market_as_ratings, refresh, refresh_process, refresh_ratings, save_snapshot,
    score, table,
)
from .title_race_views import (
    AIN, FOCUS, JAZIRA, WASL, brand_header, compare_table, crest, esc, evolution_chart, fixture_list, focus_cards,
    form_games, funnel, glossary, goals_block, headline, inject_styles, kpi_tiles, league_table, md, method_steps, name,
    ordinal, pace_tiles, range_chart, real_position, runin_strip, section, style_chart, title_curve, xpts_chart, color,
    isr_ranking, isr_chart, isr_champion_table, isr_scatter, model_comparison, season_window, isr_jumps, isr_alert,
    scenario_cards, scenario_table, weights_chart, match_explainer, market_table, market_scatter,
    value_method, value_breakdown, value_gap_explainer, squad_evolution_table, squad_evolution_chart, squad_cross,
    SQ_FOCUS, sq_lines, pv_method, pv_table, pv_reference_table,
)
from .market import refresh_market_tm, squad_breakdown
from .squad_quality import impect_minutes, load_profiles, player_value, season_squads, winter_arrivals

METHODOLOGY = '''### Detalle técnico
**Fuente:** IMPECT Customer API: `/iterations`, `/iterations/{id}/matches`, `/iterations/{id}/squads`
y `/matches/{id}/squad-kpis` (SHOT_XG, POSTSHOT_XG, tiros…). Solo UAE Pro League.

**Calendario:** si IMPECT solo publica parte del calendario, se completan los cruces ausentes bajo
la hipótesis de liga a ida y vuelta, sin inventar fechas. El modelo mantiene las fuerzas constantes,
así que el orden de los partidos pendientes no cambia la distribución final.

**Fuerza de los equipos (modelo v4):** para cada partido jugado se toma como evidencia
`0,8 × xG + 0,2 × goles` (si no hay xG, solo goles). El PSxG no se usa: en el backtest predice peor.
Reparto, prior (12 partidos) y peso de temporadas pasadas (0,3 / 0,09) elegidos por backtest. La temporada actual pesa 1 y las anteriores
completas 0,3 / 0,09 / 0,027. Medias distintas para goles locales y visitantes.
Ataque = (evidencia ponderada a favor + prior × nivel de partida) / (goles esperados por localía + prior),
y análogo para la defensa. Prior = 12 partidos equivalentes. El nivel de partida sale del **ISR de IMPECT** en la fecha del último partido jugado:
ataque = exp(3 × (ISR − media)), defensa = exp(−3 × (ISR − media)). El factor 3 se eligió en el backtest
(2 y 4 dan casi lo mismo; 6 u 8 empeoran). Sin ISR, se usa la media de liga o el nivel histórico de los ascendidos.

**Simulación:** en cada temporada simulada, el ataque y la defensa de cada equipo se perturban con
ruido log-normal de desviación ≈ 1/√(evidencia), para reflejar que su nivel real es incierto.
Goles de cada partido pendiente ~ Poisson(media local × ataque local × defensa visitante), limitado a 0,15–5.
Semilla fija: los resultados son reproducibles.

**Título y posiciones:** el % de título reparte los empates a puntos por igual; aún no se aplica
el desempate oficial. Las posiciones finales se ordenan por puntos, diferencia y goles a favor.

**«Opciones de título si terminamos con X puntos»:** probabilidad de que ningún rival supere X
(empates repartidos), usando todas las simulaciones. Es una relación dentro del modelo, no una garantía.

**ISR y reajustes:** IMPECT recalibra a veces la escala del ISR de toda la liga a la vez
(p. ej. septiembre de 2026). Como el modelo usa la distancia de cada equipo a la media de liga en la misma
fecha, esos reajustes no le afectan; los valores absolutos de fechas distintas no son comparables.

**Validación:** el backtest repite el modelo en temporadas ya terminadas usando solo las primeras
jornadas y compara con lo que pasó. Con solo dos temporadas completas, es una comprobación orientativa.

**Limitaciones:** no contempla fichajes, lesiones, cambios de entrenador ni sanciones; no ajusta por
dificultad de los rivales ya jugados ni por forma reciente dentro de la temporada.
'''


def _read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _stamp(folder):
    return tuple(sorted((p.name, p.stat().st_mtime) for p in folder.glob('*.json')))


@st.cache_data(show_spinner=False)
def _run(folder: str, stamp, iteration_id: int, infer: bool):
    folder = Path(folder)
    datasets = [d for d in (_read_json(p) for p in folder.glob('season_*.json')) if d]
    current = next(d for d in datasets if d['iteration']['id'] == iteration_id)
    process = {d['iteration']['id']: load_process(folder, d['iteration']['id']) for d in datasets}
    ratings = load_ratings(folder)
    use = complete_calendar(current) if infer else current
    return forecast(use, datasets, process=process, ratings=ratings, isr_date=datetime.now().strftime('%Y-%m-%d')), process, ratings


def _market_values(folder: Path, source: str, iteration_id: int):
    """{squad id: euros} and metadata for one source ('besoccer' or 'tm')."""
    if source == 'tm':
        tm = _read_json(folder/'market_tm.json') or {}
        season = tm.get(str(iteration_id)) or {}
        vals = {int(k): v['xi_value'] for k, v in (season.get('squads') or {}).items() if v.get('xi_value')}
        return vals, {'source': 'Transfermarkt', 'date': season.get('date'), 'all': tm}
    market = load_market(folder)
    vals = {int(k): v['value'] for k, v in (market.get('teams') or {}).items() if v.get('value')}
    return vals, {'source': 'BeSoccer', 'date': (market.get('scraped_at') or '')[:10], 'top_n': market.get('top_n')}


@st.cache_data(show_spinner=False)
def _run_market(folder: str, stamp, iteration_id: int, infer: bool, source: str):
    """Same simulation as the main model, but the starting level comes ONLY from squad market value.

    The strength of that effect (market_k) is calibrated on past seasons with Transfermarkt
    (see market_comparison.json); the ISR is not used at all.
    """
    folder = Path(folder)
    vals, meta = _market_values(folder, source, iteration_id)
    comp = _read_json(folder/'market_comparison.json') or {}
    k = comp.get('market_k')
    datasets = [d for d in (_read_json(p) for p in folder.glob('season_*.json')) if d]
    current = next(d for d in datasets if d['iteration']['id'] == iteration_id)
    ids = [s['id'] for s in current['squads']]
    if not k or any(not vals.get(i) for i in ids):
        return None, vals, meta, comp
    today = datetime.now().strftime('%Y-%m-%d')
    series = {str(i): [[today, float(np.log(vals[i]))]] for i in ids}
    process = {d['iteration']['id']: load_process(folder, d['iteration']['id']) for d in datasets}
    use = complete_calendar(current) if infer else current
    res = forecast(use, datasets, process=process, ratings=None, isr_k=0., isr_date=today, market=series, market_k=k)
    return res, vals, meta, comp


@st.cache_data(show_spinner=False)
def _backtest(folder: str, stamp, cut: int):
    folder = Path(folder)
    datasets = [d for d in (_read_json(p) for p in folder.glob('season_*.json')) if d]
    process = {d['iteration']['id']: load_process(folder, d['iteration']['id']) for d in datasets}
    return backtest(datasets, process, cut, ratings=load_ratings(folder))


def _headline_text(row, pos, gap, ppos):
    pct = row['Título aprox. %']
    line1 = 'Líderes hoy.' if pos == 1 else f'{ordinal(pos)} hoy · a {gap} {"punto" if gap == 1 else "puntos"} del líder.'
    if pct >= 40:
        line2 = 'Favoritos al título.'
    elif pct >= 15:
        line2 = 'El título está al alcance.'
    elif pct >= 4:
        line2 = 'En la pelea: hay que acelerar.'
    else:
        line2 = 'El título exige un salto.'
    return line1, line2


def render_title_race(root: Path, client_factory=None, data_note: str | None = None):
    """client_factory=None → read-only (shared app): no IMPECT refresh, data comes with the deployment."""
    inject_styles()
    folder = root/'data/title_race'
    top = st.columns([3, 2])
    if client_factory is None:
        top[1].markdown(f'<div class="tr tr-callout" style="margin:22px 0 0;font-size:13px">🔒 <b>Modo consulta.</b> '
                        f'{esc(data_note or "Datos preparados por el departamento de análisis.")}</div>', unsafe_allow_html=True)
    elif top[1].button('↻ Actualizar después de la jornada', type='primary', width='stretch'):
        try:
            with st.status('Actualizando datos de IMPECT…', expanded=False) as status:
                client = client_factory()
                status.write('Resultados y calendarios…')
                datasets = refresh(client, folder)
                status.write('Ocasiones de cada partido (xG, PSxG)…')
                refresh_process(client, folder, datasets)
                status.write('IMPECT Squad Rating (ISR)…')
                refresh_ratings(client, folder, [d['iteration']['id'] for d in datasets])
                status.write('Minutos (IMPECT) y valores de mercado (Transfermarkt) de jugadores nuevos…')
                try:
                    refresh_market_tm(client, folder, datasets)
                except Exception:
                    status.write('Transfermarkt no respondió: se mantienen los valores guardados.')
                status.update(label='Datos actualizados', state='complete')
        except Exception:
            st.error('No se pudo completar la actualización de IMPECT. Se mantienen los datos guardados; comprueba conexión y acceso.')
    datasets = [d for d in (_read_json(p) for p in folder.glob('season_*.json')) if d]
    if not datasets:
        st.info('No hay datos cargados. ' + ('Pulsa «Actualizar después de la jornada» para cargar resultados y calendarios.' if client_factory
                                             else 'Revisa la conexión con la carpeta de datos de Google Drive.'))
        return
    datasets.sort(key=lambda d: d['iteration']['season'], reverse=True)
    selectable = [datasets[0]] + [d for d in datasets[1:] if len(d['matches']) == len(d['squads'])*(len(d['squads'])-1) and all(score(m) is not None for m in d['matches'])]
    current = top[0].selectbox('Temporada', selectable, format_func=lambda d: f"UAE Pro League {d['iteration']['season']}")
    supplied, expected = len(current['matches']), len(current['squads'])*(len(current['squads'])-1)
    infer = True
    if supplied < expected:
        with st.expander(f'Calendario: {supplied} cruces publicados por IMPECT, {expected-supplied} por confirmar'):
            st.write('Para proyectar el final de liga se completan los cruces ausentes suponiendo ida y vuelta. Sus fechas siguen sin confirmar.')
            infer = st.checkbox('Incluir los cruces pendientes inferidos', value=True)
        if not infer:
            st.dataframe(pd.DataFrame(table(current)).drop(columns='id'), hide_index=True)
            st.info('Proyección detenida hasta disponer del calendario completo o activar la hipótesis indicada.')
            return
    try:
        result, process, ratings = _run(str(folder), _stamp(folder), current['iteration']['id'], infer)
    except (ValueError, StopIteration) as exc:
        st.error(str(exc)); st.dataframe(pd.DataFrame(table(current)), hide_index=True); return
    try:
        save_snapshot(result, folder/'snapshots')
    except OSError:
        pass
    squads = {s['id']: s for s in current['squads']}
    ids = [i for i in FOCUS if i in squads]
    if WASL not in squads:
        st.warning('Al Wasl no figura en esta temporada.'); return
    rows = {r['id']: r for r in result['summary']}
    me = rows[WASL]
    pos = real_position(result)
    leader = max(r['Puntos'] for r in result['summary'])
    cur_proc = process.get(current['iteration']['id'], {})
    has_xg = bool(me.get('xG PJ'))
    updated = datetime.fromisoformat(current['fetched_at']).astimezone(ZoneInfo('Asia/Dubai')).strftime('%d/%m/%Y · %H:%M')
    st.caption(f"Datos IMPECT a {updated} (hora de Dubái) · {result['played']} partidos jugados · "
               f"xG disponible en {result['parameters']['xg_coverage'].get(str(current['iteration']['id']), 0)} de ellos")

    tabs = st.tabs(['🏆 Resumen', '🎯 ¿Qué hace falta?', '⚔️ Wasl · Jazira · Ain', '📊 Nivel ISR', '💶 Mercado · Transfermarkt', '💰 Mercado · BeSoccer', '🧬 Plantillas · ELO y valor', '📈 Evolución', '🗓️ Calendario', 'ℹ️ Cómo funciona'])
    proj_rank = sorted(result['summary'], key=lambda r: -r['Puntos previstos']).index(me) + 1

    # ------------------------------------------------------------------ 1. Summary
    with tabs[0]:
        brand_header(root, 'Carrera por el título', 'Proyección', 1)
        l1, l2 = _headline_text(me, pos[WASL], leader - me['Puntos'], proj_rank)
        favourite = result['summary'][0]
        lead = (f"Tras {me['PJ']} jornadas sumamos <b>{me['Puntos']} puntos</b>. Si jugamos la liga 20.000 veces desde hoy, "
                f"Al Wasl es campeón en <b>{me['Título aprox. %']:.0f} de cada 100</b>. "
                + (f"El favorito ahora mismo es <b>{esc(name(squads[favourite['id']]))}</b> ({favourite['Título aprox. %']:.0f}%)." if favourite['id'] != WASL else ''))
        headline(l1, l2, lead)
        kpi_tiles([
            (ordinal(pos[WASL]), 'Posición actual', f"{me['Puntos']} pts · {me['PPG']:.2f} por partido"),
            (f"{me['Puntos previstos']:.0f}", 'Puntos finales proyectados', f"rango probable {me['P10']}–{me['P90']}"),
            (f"{me['Título aprox. %']:.0f}%", 'Opciones de título', f"{proj_rank}º en la proyección"),
            (f"{me['Top 3 %']:.0f}%", 'Opciones de top 3', f"posición media {me['Posición media']:.1f}"),
        ] + ([(f"{me['xPPG']:.2f}", 'Puntos merecidos / partido', 'xPPG según ocasiones (IMPECT)')] if has_xg else []))
        section('Los tres candidatos que miramos', 'Al Wasl frente a Al Jazira y Al Ain')
        focus_cards(root, result, squads, current, ids)
        section('Tres escenarios', '¿Cómo puede acabar la temporada?',
                'Pesimista, conservador y optimista: lo que sale en 1 de cada 10 temporadas simuladas por abajo, en el medio y por arriba.')
        sc_team = st.segmented_control('Escenarios de', ids, default=WASL, format_func=lambda i: name(squads[i]), key='scen_team') or WASL
        scenario_cards(result, sc_team, squads)
        with st.expander('Ver los tres escenarios de Wasl, Jazira y Ain'):
            scenario_table(root, result, squads, ids)
        others = [r for r in result['summary'] if r['id'] not in FOCUS and r['Título aprox. %'] >= 10]
        if others:
            o = others[0]
            md(f'<div class="tr tr-callout">⚠️ Atención: el modelo ve a <b>{esc(name(squads[o["id"]]))}</b> como candidato real '
               f'({o["Título aprox. %"]:.0f}% de título), por delante de alguno de nuestros rivales de referencia.</div>')
        c1, c2 = st.columns([.8, 1.2], gap='large')
        with c1:
            section('Puntos finales vs puntos de hoy', '¿Dónde puede terminar cada equipo?',
                    'El punto es la proyección; la barra, el rango en el que terminan 8 de cada 10 simulaciones.')
            range_chart(root, result, squads)
        with c2:
            section('Clasificación proyectada', 'Orden por puntos finales esperados',
                    'xPPG: puntos que merecerían sus ocasiones. ▲ suma más de lo que merece; ▼ menos.' if has_xg else None)
            league_table(root, result, squads, has_xg)
        if ratings and any(j['hasta'] >= season_window(current)[0] for j in isr_jumps(ratings)):
            st.caption('⚠️ ISR: esta temporada IMPECT ha reajustado la escala de todos los equipos a la vez. Compara posiciones, no valores con temporadas pasadas (detalle en «Nivel ISR»).')
        with st.expander('📖 Glosario rápido: ¿qué significa cada término?'):
            glossary()

    # ------------------------------------------------------------------ 2. What does it take
    with tabs[1]:
        brand_header(root, 'Carrera por el título', '¿Qué hace falta?', 2)
        sid = st.segmented_control('Equipo', ids, default=WASL, format_func=lambda i: name(squads[i]), key='need_team') or WASL
        r = rows[sid]
        remaining = r['Pendientes']
        t50 = next((c['Puntos finales'] for c in sorted((c for c in result['curves'] if c['id'] == sid), key=lambda c: c['Puntos finales']) if c['Título aprox. %'] >= 50), None)
        t80 = next((c['Puntos finales'] for c in sorted((c for c in result['curves'] if c['id'] == sid), key=lambda c: c['Puntos finales']) if c['Título aprox. %'] >= 80), None)
        if t50 is None:
            headline('¿Qué hace falta?', 'Fuera de alcance matemático')
        else:
            headline('¿Qué hace falta?', f'{t50}–{t80} puntos' if t80 and t80 != t50 else f'{t50} puntos',
                     f'Con <b>{t50} puntos</b> {esc(name(squads[sid]))} gana la liga en la mitad de los escenarios; con <b>{t80 or t50}</b>, en 8 de cada 10. '
                     f'Hoy tiene {r["Puntos"]} y quedan <b>{remaining} partidos</b>.')
        c1, c2 = st.columns([1.1, 1], gap='large')
        with c1:
            section('Opciones de título según los puntos finales', '¿Cuántos puntos ganan la liga?',
                    'Cada barra: probabilidad de ser campeón si terminamos con esos puntos. Las líneas marcan con cuántos puntos ganaron los últimos campeones.')
            title_curve(result, sid, result['champions'])
            if t50 is not None and remaining:
                section('Un ejemplo de camino', f'Así se ven {t50} puntos en {remaining} partidos')
                runin_strip(t50 - r['Puntos'], remaining, t50)
        with c2:
            section(f'Puntos por partido · quedan {remaining}', '¿A qué ritmo tenemos que ir?')
            pace_tiles(result, sid, r['PPG'], remaining, r['Puntos'])
            goals_block(r, remaining)
            if result['champions']:
                ch = result['champions'][0]
                md(f'<div class="tr tr-callout">📚 Referencia: el último campeón ({esc(ch["season"])}, {esc(name(squads.get(ch["id"], {"id": ch["id"], "name": ch["name"]})))}) '
                   f'sumó <b>{ch["points"]} puntos</b> ({ch["points"]/ch["played"]:.2f} por partido); el segundo hizo {ch["second"]}.</div>')

    # ------------------------------------------------------------------ 3. Face to face
    with tabs[2]:
        brand_header(root, 'Carrera por el título', 'Cara a cara', 3)
        headline('Wasl · Jazira · Ain', '¿Dónde ganamos y dónde perdemos?')
        compare_table(root, result, squads, result['fixtures'], ids, has_xg)
        section('Del xG al gol', '¿Rendimiento sostenible o rachas?',
                'Ocasiones creadas (xG) → calidad de los tiros (PSxG) → goles reales. Igual en defensa.')
        fid = st.segmented_control('Equipo', ids, default=WASL, format_func=lambda i: name(squads[i]), key='funnel_team') or WASL
        funnel(rows[fid])
        direct = [f for f in result['fixtures'] if f['home_id'] in ids and f['away_id'] in ids]
        if direct:
            section('Duelos directos pendientes', 'Los partidos que deciden la carrera')
            for team in [i for i in ids if i == WASL]:
                fixture_list(root, [f for f in direct if team in (f['home_id'], f['away_id'])], squads, team)
            rest = [f for f in direct if WASL not in (f['home_id'], f['away_id'])]
            if rest:
                md('<div class="tr tr-muted" style="margin-top:8px"><b>Entre nuestros rivales</b></div>')
                for f in rest:
                    md(f'<div class="tr tr-muted">{esc(name(squads[f["home_id"]]))} – {esc(name(squads[f["away_id"]]))}: '
                       f'gana local {f["P(local) %"]:.0f}% · empate {f["P(empate) %"]:.0f}% · gana visitante {f["P(visitante) %"]:.0f}%</div>')

    # ------------------------------------------------------------------ 4. Evolution
    with tabs[3]:
        brand_header(root, 'Carrera por el título', 'Nivel IMPECT · ISR', 4)
        if not ratings:
            st.info('Sin ISR descargado. Pulsa «Actualizar después de la jornada».')
        else:
            start, _ = season_window(current)
            jumps = isr_jumps(ratings)
            past = isr_champion_table(datasets, ratings)
            mean_now = sum(r['ISR'] for r in result['summary'] if r.get('ISR') is not None)/max(1, sum(r.get('ISR') is not None for r in result['summary']))
            leader_isr = max(result['summary'], key=lambda r: r.get('ISR') or 0)
            headline('Nivel IMPECT (ISR)', f"Al Wasl {me['ISR']:.3f} · {sorted(result['summary'], key=lambda r: -(r.get('ISR') or 0)).index(me)+1}º de la liga",
                     f"El ISR es la nota global que IMPECT da a cada equipo. Hoy el mejor es <b>{esc(name(squads[leader_isr['id']]))}</b> ({leader_isr['ISR']:.3f}); "
                     f"estamos a <b>{leader_isr['ISR']-me['ISR']:.3f}</b>. En las dos últimas temporadas, el ISR medio explicó casi por completo la clasificación final.")
            isr_alert(jumps, start)
            if not past.empty:
                champs = past[past['Posición'] == 1]
                corr = past.groupby('Temporada').apply(lambda g: g['ISR vs media'].corr(g['Puntos'])).round(2)
                kpi_tiles([(f"{me['ISR']-mean_now:+.3f}", 'Al Wasl vs media hoy', 'ISR por encima de la media de la liga')]
                          + [(f"{r['ISR vs media']:+.3f}", f"Campeón {r['Temporada']}", f"{esc(r['Equipo'])} · {r['Puntos']} pts · ISR medio {r['ISR medio']:.3f}") for _, r in champs.iterrows()]
                          + [(f"{corr.mean():.2f}", 'Relación ISR – puntos', 'correlación (1 = perfecta) · ' + ' / '.join(f'{k}: {v}' for k, v in corr.items()))])
            c1, c2 = st.columns([1, 1], gap='large')
            with c1:
                section('Ranking de hoy', '¿Quién tiene más nivel ahora?', 'Variación real (sin reajustes de escala) en los últimos 30 días y desde el inicio de la temporada.')
                isr_ranking(root, ratings, squads, start)
            with c2:
                section('¿Qué ISR hace campeón?', 'Nivel IMPECT y puntos finales',
                        'Círculos: cada equipo en 24/25 y 25/26 (su ISR medio de esa temporada y los puntos que hizo). '
                        'Rombos: esta temporada (ISR de hoy y puntos proyectados). Cuanto más a la derecha, más nivel; cuanto más arriba, más puntos.')
                if not past.empty:
                    now = pd.DataFrame([{'Equipo': name(squads[i]), 'ISR vs media': rows[i]['ISR'] - mean_now, 'Puntos': rows[i]['Puntos previstos'],
                                         'c': color(i) if i != WASL else '#F2C200'} for i in ids if rows[i].get('ISR') is not None])
                    isr_scatter(past, now)
                    gap = champs['ISR vs media'].min() - (me['ISR'] - mean_now)
                    md('<div class="tr tr-callout">' + (
                        f'Los últimos campeones estuvieron al menos <b>{champs["ISR vs media"].min():+.3f}</b> por encima de la media de la liga. '
                        + (f'Al Wasl ya está en ese nivel ({me["ISR"]-mean_now:+.3f}).' if gap <= 0 else
                           f'A Al Wasl le faltan <b>{gap:.3f}</b> para llegar a ese umbral.')) + '</div>')
            section('Evolución', 'El ISR a lo largo de la temporada')
            span = st.segmented_control('Periodo', ['Esta temporada', 'Últimas 3 temporadas', 'Desde 2019'], default='Esta temporada', key='isr_span') or 'Esta temporada'
            begin = {'Esta temporada': start, 'Últimas 3 temporadas': f'{int(start[:4])-2}-07-01', 'Desde 2019': '2019-01-01'}[span]
            isr_chart(ratings, squads, ids, begin, jumps=jumps)
            st.caption(f'ISR = IMPECT Squad Rating. Lo calcula IMPECT; nosotros solo lo leemos. Líneas amarillas: reajustes generales '
                       f'({len(jumps)} detectados desde 2019). En el modelo se usa como punto de partida, siempre como distancia a la media de la liga.')

    for tab, source, number in ((tabs[4], 'tm', 5), (tabs[5], 'besoccer', 6)):
        with tab:
            _market_tab(root, folder, current, infer, result, rows, me, squads, ids, source, number)

    with tabs[6]:
        _squads_tab(root, datasets, current, squads, ids)

    with tabs[7]:
        brand_header(root, 'Carrera por el título', 'Evolución', 8)
        headline('Partido a partido', '¿Vamos a ritmo de campeón?')
        chosen = st.multiselect('Equipos', list(squads), default=ids, format_func=lambda i: name(squads[i]), key='race_evolution_teams')
        section('Puntos acumulados', 'Nuestro ritmo frente al de los últimos campeones',
                'Líneas discontinuas: los campeones de las temporadas anteriores en sus mismos partidos. Si dos equipos suman lo mismo, sus líneas se superponen.')
        if chosen:
            evolution_chart(current, squads, chosen, result['champions'])
        if has_xg:
            section('Puntos reales vs merecidos', '¿Sumamos lo que merecemos?',
                    'Línea continua: puntos por partido reales. Discontinua: los que corresponderían a las ocasiones (xPPG). '
                    'Si la continua va muy por encima, parte de los puntos vienen de acierto o fortuna.')
            xpts_chart(current, squads, chosen or ids, cur_proc)
        section('Seguimiento', 'Cómo cambian las opciones de título tras cada actualización')
        history = []
        for p in (folder/'snapshots').glob('*.json'):
            snap = _read_json(p)
            if not snap or snap['inputs']['current']['iteration']['id'] != current['iteration']['id'] or snap['version'] != result['version']:
                continue
            for r in snap['summary']:
                if r['id'] in ids:
                    history.append({'Fecha': snap['computed_at'], 'Equipo': name(squads[r['id']]), 'Opciones': r['Título aprox. %'], 'Partidos': snap['played']})
        if history:
            hist = pd.DataFrame(history).sort_values('Fecha')
            dom = [name(squads[i]) for i in ids]
            chart = alt.Chart(hist).mark_line(point=alt.OverlayMarkDef(size=90, filled=True), strokeWidth=3).encode(
                x=alt.X('Partidos:Q', title='Partidos de liga jugados al calcular', axis=alt.Axis(tickMinStep=1, format='d')),
                y=alt.Y('Opciones:Q', title='Opciones de título (%)', scale=alt.Scale(domain=[0, 100])),
                color=alt.Color('Equipo:N', scale=alt.Scale(domain=dom, range=[color(i) if i != WASL else '#E0B000' for i in ids])),
                tooltip=['Equipo', alt.Tooltip('Fecha:T', format='%d/%m/%Y %H:%M'), alt.Tooltip('Opciones:Q', format='.1f'), 'Partidos'])
            st.altair_chart(style_chart(chart, 240), width='stretch')
            if hist.Partidos.nunique() == 1:
                st.caption('Primera estimación con este modelo. Al actualizar tras cada jornada aparecerá la evolución; no se inventan porcentajes pasados.')
        if client_factory is not None:
          with st.expander('Guardar o restaurar el registro de seguimiento'):
              st.caption('En Streamlit Cloud el disco es efímero: descarga el registro para no perder la evolución.')
              archives = [a for a in (_read_json(p) for p in (folder/'snapshots').glob('*.json')) if a]
              st.download_button('Descargar registro de evolución', json.dumps(archives, ensure_ascii=False), 'title_race_history.json', 'application/json')
              uploaded = st.file_uploader('Restaurar registro de evolución', type='json')
              if uploaded is not None and st.button('Importar registro'):
                  try:
                      incoming = json.loads(uploaded.getvalue())
                      if not isinstance(incoming, list):
                          raise ValueError('Formato incorrecto')
                      for snap in incoming:
                          inputs = snap['inputs']
                          rebuilt = forecast(inputs['current'], inputs['historical'], snap['simulations'], process={
                              int(k): v for k, v in (inputs.get('process') or {}).items()})
                          if rebuilt['input_hash'] != snap['input_hash'] or rebuilt['version'] != snap['version']:
                              raise ValueError('Registro incompatible')
                          rebuilt['computed_at'] = datetime.fromisoformat(snap['computed_at']).isoformat()
                          save_snapshot(rebuilt, folder/'snapshots')
                      st.success('Registro restaurado.'); st.rerun()
                  except (ValueError, KeyError, TypeError, OSError):
                      st.error('No se pudo restaurar el registro. Comprueba su formato y versión del modelo.')

    # ------------------------------------------------------------------ 5. Calendar
    with tabs[8]:
        brand_header(root, 'Carrera por el título', 'Calendario', 9)
        sid = st.segmented_control('Equipo', list(squads), default=WASL, format_func=lambda i: name(squads[i]), key='cal_team') or WASL
        s = squads[sid]; r = rows[sid]
        fx = [f for f in result['fixtures'] if sid in (f['home_id'], f['away_id'])]
        fx.sort(key=lambda f: (f['Origen'] == 'Cruce inferido', f.get('Fecha') or '9999', f['Local']))
        exp_pts = sum(((3*(f['P(local) %'] if f['home_id'] == sid else f['P(visitante) %']) + f['P(empate) %'])/100) for f in fx)
        home_games = [g for g in form_games(current, sid, 'En casa')]; away_games = [g for g in form_games(current, sid, 'Fuera')]
        headline(f'El camino de {name(s)}', f'{len(fx)} partidos · {exp_pts:.0f} puntos esperados')
        kpi_tiles([
            (f"{sum(g['points'] for g in home_games)}", 'Puntos en casa', f'{len(home_games)} partidos'),
            (f"{sum(g['points'] for g in away_games)}", 'Puntos fuera', f'{len(away_games)} partidos'),
            (f"{exp_pts/len(fx):.2f}" if fx else '–', 'Pts esperados / partido', 'en lo que queda'),
            (f"{sum(1 for f in fx if (f['away_id'] if f['home_id'] == sid else f['home_id']) in FOCUS)}", 'Duelos directos', 'vs Wasl / Jazira / Ain'),
        ])
        if fx:
            fixture_list(root, fx, squads, sid)
            st.caption('Probabilidades del modelo para cada partido (victoria / empate / derrota del equipo elegido). '
                       'Los cruces sin fecha confirmada aparecen al final.')
            with st.expander('🧮 ¿Cómo se calculan los goles esperados y los porcentajes de un partido?'):
                match_explainer(result, fx[0], squads, sid)
        else:
            st.info('No quedan partidos pendientes.')
        played = list(reversed(form_games(current, sid)))
        if played:
            with st.expander(f'Partidos ya jugados ({len(played)})'):
                for g in played:
                    home, away = squads[g['homeSquadId']], squads[g['awaySquadId']]
                    h, a = score(g)
                    md(f'<div class="tr tr-fixture" style="--c:{"#1E8E5A" if g["outcome"] == "V" else "#8B97A8" if g["outcome"] == "E" else "#D64545"};grid-template-columns:90px 1fr 60px">'
                       f'<div class="meta">{esc((g.get("scheduledDate") or "")[:10])}</div>'
                       f'<div class="vs">{crest(root, home, 24)}<span>{esc(name(home))}</span> <b>{h} – {a}</b> <span>{esc(name(away))}</span>{crest(root, away, 24)}</div>'
                       f'<div class="xp">{g["points"]}<small>PTS</small></div></div>')

    # ------------------------------------------------------------------ 6. Method
    with tabs[9]:
        brand_header(root, 'Carrera por el título', 'Metodología', 10)
        headline('Cómo funciona', '¿De dónde salen los porcentajes?')
        method_steps(len(result['inputs']['historical']), result['simulations'], result['parameters']['xg_weight'])
        prm = result['parameters']
        section('¿Cuánto pesa cada dato?', 'ISR, temporadas pasadas y esta temporada',
                'El modelo es el mismo en todas las jornadas: no hay que rehacerlo. Lo que cambia solo es el peso de cada fuente, '
                'porque cada partido jugado añade información. La línea marca dónde estamos hoy.')
        shares = evidence_shares(prm['prior_matches'], prm['season_weights'][1], len(result['inputs']['historical']))
        weights_chart(shares, me['PJ'])
        now_sh = shares[min(me['PJ'], len(shares)-1)]
        md(f'<div class="tr tr-callout">Hoy, con {me["PJ"]} partidos jugados, el nivel de cada equipo sale aproximadamente de: '
           f'<b>ISR {100*now_sh["ISR"]:.0f}%</b> · <b>temporadas anteriores {100*now_sh["Temporadas anteriores"]:.0f}%</b> · '
           f'<b>esta temporada {100*now_sh["Esta temporada"]:.0f}%</b>. A final de liga, esta temporada pesará más de la mitad.</div>')
        section('¿Por qué estos números?', f'{100*prm["xg_weight"]:.0f}% xG + {100-100*prm["xg_weight"]:.0f}% goles, y no otro reparto')
        md(f'<div class="tr tr-callout">No los hemos elegido a ojo. Probamos repartos de 40%, 60%, 80% y 100% de xG, '
           f'combinados con distintos pesos del ISR y de las temporadas pasadas, sobre 1.610 partidos de 24/25 y 25/26. '
           f'Cuanto más peso tiene el xG, mejor predice: 80% y 100% empatan prácticamente. Nos quedamos con <b>80/20</b> y no con 100% '
           f'para no ignorar del todo los goles (penaltis, rematadores de mucho nivel). Igual se eligieron el peso del ISR '
           f'(equivale a {prm["prior_matches"]:.0f} partidos), el de la temporada anterior ({prm["season_weights"][1]:.0%} de la actual) y la fuerza del ISR (k = {prm["isr_k"]:.0f}). '
           f'<br><span class="tr-muted">Ojo: son dos temporadas de prueba. Al acabar esta, se repite la prueba con tres.</span></div>')
        section('¿Es fiable?', 'Probamos el modelo en temporadas ya terminadas',
                'Le damos solo las primeras jornadas de una temporada pasada y comparamos con lo que ocurrió de verdad.')
        cut = st.select_slider('Jornadas que conocía el modelo', [5, 10, 15, 20], value=5, key='bt_cut')
        bt = _backtest(str(folder), _stamp(folder), cut)
        if bt:
            md('<div class="tr tr-kpis">' + ''.join(
                f'<div class="tr-kpi"><b>{b["Prob. del campeón %"]:.0f}%</b><span>{esc(b["Temporada"])} · campeón {esc(b["Campeón"])}</span>'
                f'<em>{b["Favorito nº"]}º favorito del modelo · error medio {b["Error medio (pts)"]} pts · '
                f'{b["Dentro del rango 80% %"]:.0f}% de equipos dentro del rango</em></div>' for b in bt) + '</div>')
            st.caption('Lectura: % que el modelo daba al que acabó siendo campeón. Un 30-40% en jornada 5 con 14 equipos es una señal correcta '
                       '(el azar puro daría ~7%). «Dentro del rango»: de los 14 equipos, cuántos acabaron entre su escenario pesimista y optimista. '
                       'Lo correcto es ~80% (8 de cada 10). Con 14 equipos, 1–2 equipos arriba o abajo es azar normal: 71% o 93% también son resultados correctos.')
        section('¿Qué datos usamos y por qué?', 'Comparamos 6 versiones del modelo',
                'Cada versión predice las temporadas pasadas sin conocer el futuro. Nos quedamos con la que más acierta.')
        scope = st.segmented_control('Evaluar en', ['Jornada 5 (nuestra situación)', 'Todas las jornadas de corte'],
                                     default='Jornada 5 (nuestra situación)', key='comp_scope') or 'Jornada 5 (nuestra situación)'
        comp = _read_json(folder/('model_comparison_md5.json' if scope.startswith('Jornada 5') else 'model_comparison.json'))
        if comp:
            model_comparison(comp)
        else:
            st.info('Aún no se ha calculado la comparativa de modelos.')
        section('Datos utilizados', 'Cobertura')
        coverage = [{'Temporada': d['iteration']['season'], 'Partidos': len(d['matches']), 'Con resultado': sum(score(m) is not None for m in d['matches']),
                     'Con xG': result['parameters']['xg_coverage'].get(str(d['iteration']['id']), 0)} for d in [current]+result['inputs']['historical']]
        st.dataframe(pd.DataFrame(coverage), hide_index=True)
        with st.expander('Detalle técnico, fórmulas y limitaciones'):
            st.markdown(METHODOLOGY)
            strengths = [{'Equipo': name(squads[r['id']]), 'Ataque': r['Ataque'], 'Defensa (concesión)': r['Defensa']} for r in result['summary']]
            st.dataframe(pd.DataFrame(strengths), hide_index=True)
            st.caption('1 = media de liga. Ataque > 1 genera más goles; defensa > 1 concede más.')
            st.code(f"Modelo: {result['version']}\nHuella de datos: {result['input_hash']}\nSimulaciones: {result['simulations']} · Semilla: {result['seed']}")
        d1, d2 = st.columns(2)
        d1.download_button('Descargar proyección (CSV)', pd.DataFrame(result['summary']).drop(columns=['Posiciones %']).to_csv(index=False).encode('utf-8-sig'),
                           'title_race.csv', 'text/csv', width='stretch')
        d2.download_button('Descargar auditoría completa (JSON)', json.dumps(result, ensure_ascii=False), 'title_race_audit.json', 'application/json', width='stretch')


def _market_tab(root, folder, current, infer, result, rows, me, squads, ids, source, number):
    label = 'Transfermarkt' if source == 'tm' else 'BeSoccer'
    brand_header(root, 'Carrera por el título', f'Valor de mercado · {label}', number)
    mres, vals, meta, comp = _run_market(str(folder), _stamp(folder), current['iteration']['id'], infer, source)
    if mres is None:
        st.info(f'Faltan datos de {label} o la calibración del mercado (data/title_race/market_comparison.json).')
        return
    mrows = {r['id']: r for r in mres['summary']}
    fav = mres['summary'][0]
    headline('¿Y si mandara el dinero?', f"Según {label}: {name(squads[fav['id']])} {fav['Título aprox. %']:.0f}%",
             f"Misma simulación que el modelo principal, pero el punto de partida de cada equipo sale <b>solo del valor de su plantilla</b>: "
             f"aquí no se usa el ISR. Al Wasl: <b>{mrows[WASL]['Título aprox. %']:.0f}%</b> frente a <b>{me['Título aprox. %']:.0f}%</b> del modelo principal.")
    if source == 'tm':
        how = (f'Valor de cada jugador en Transfermarkt al inicio de la temporada ({esc(meta.get("date") or "")}), ponderado por los minutos que juega '
               'para su equipo según IMPECT: es el valor del «once medio» que sale al campo. El cruce jugador a jugador es exacto (IMPECT trae el id de Transfermarkt).')
    else:
        how = (f'Valores de BeSoccer del {esc(meta.get("date") or "")}: suma de los {meta.get("top_n", 18)} jugadores más valiosos de cada plantilla '
               '(sin minutos: BeSoccer no se puede cruzar jugador a jugador con IMPECT). <b>Solo hay foto de hoy</b>, así que esta vista usa la '
               'intensidad calibrada con Transfermarkt.')
    verdict = comp.get('verdict_md5', '')
    md('<div class="tr tr-callout" style="border-left-color:#D9A400;background:#FFF8E1">🧪 <b>Vista alternativa: el modelo principal no cambia.</b> '
       f'{how}<br>{verdict}</div>')
    kpi_tiles([(f"{mrows[i]['Título aprox. %']:.0f}%", f"{name(squads[i])} · {label}", f"modelo principal {rows[i]['Título aprox. %']:.0f}%") for i in ids]
              + [(f"{vals[WASL]/1e6:.0f} M€", 'Al Wasl', f"{sorted(vals.values(), reverse=True).index(vals[WASL])+1}º valor de la liga")])
    section('Cómo se calcula', '¿De dónde sale el valor de cada equipo?')
    value_method(source, meta.get('top_n') or 18)
    if source == 'tm':
        with st.expander('🔎 Ver el desglose jugador a jugador'):
            order = sorted(vals, key=lambda i: -vals[i])
            bteam = st.selectbox('Equipo', order, index=order.index(WASL), format_func=lambda i: name(squads[i]), key='tm_breakdown_team')
            value_breakdown(squad_breakdown(folder, current['iteration']['id'], bteam, meta.get('date')), name(squads[bteam]))
    c1, c2 = st.columns([1.15, 1], gap='large')
    with c1:
        section('Valor, nivel y proyección', '¿Quién rinde por encima de lo que vale?',
                '«vs su valor»: puntos proyectados por el modelo principal menos los que tendría un equipo con su valor de plantilla.')
        market_table(root, vals, result, mres, squads)
        gteam = st.segmented_control('Ver el cálculo de', ids, default=WASL, format_func=lambda i: name(squads[i]), key=f'gap_team_{source}') or WASL
        value_gap_explainer(vals, result, squads, gteam)
    with c2:
        section('Valor de plantilla y puntos', 'Dinero frente a rendimiento')
        market_scatter(root, vals, result, squads, 'Valor del once medio (M€, escala logarítmica)' if source == 'tm' else
                       'Valor de los 18 jugadores más valiosos (M€, escala logarítmica)')
    if source == 'tm' and comp.get('variants'):
        section('¿Predice el dinero?', 'Prueba en 24/25 y 25/26',
                'Mismo método que con el PSxG y el ISR: el modelo solo conoce las primeras jornadas y lo comparamos con lo que pasó.')
        view = st.segmented_control('Evaluar en', ['Jornada 5', 'Todas las jornadas'], default='Jornada 5', key='mk_scope') or 'Jornada 5'
        rows_v = comp['variants_md5'] if view == 'Jornada 5' else comp['variants']
        md('<div class="tr"><table class="tr-table"><tr><th></th><th>Punto de partida</th><th>Mejor que adivinar</th><th>Error pts finales</th><th>% al campeón real</th></tr>'
           + ''.join(f'<tr class="{"me" if v.get("main") else ""}"><td></td><td><div class="tr-team" style="font-weight:700">{esc(v["Modelo"])}</div></td>'
                     f'<td>{v["Mejor que adivinar %"]:.1f}%</td><td>{v["Error medio (pts)"]:.1f}</td><td>{v["Prob. del campeón %"]:.0f}%</td></tr>' for v in rows_v)
           + '</table></div>')
        if comp.get('verdict'):
            md(f'<div class="tr tr-callout">{comp["verdict"]}</div>')


@st.cache_data(show_spinner=False)
def _season_squads(path: str, mtime: float, only_played: bool, mode: str = 'general'):
    """Team P75 of ELO and value from the SAME point-in-time player data as the PLAYER VALUE.

    26/27: each player's BeSoccer profile today (all teams). Winter signings: their data when
    they arrived. Everyone else: the season squad listing.
    """
    import numpy as np
    pv = _player_value(path, mtime, str(_series_csv() or ''), mode)
    if only_played:
        pv = pv[pv.minutes > 0]
    out = []
    for (season, team), g in pv.groupby(['season', 'team']):
        elo, val = g.elo.dropna(), g.value.dropna()
        elo, val = elo[elo > 0], val[val > 0]
        out.append({'season': season, 'team': team, 'id': g.id.iloc[0],
                    'elo_p75': float(np.percentile(elo, 75)) if len(elo) else None, 'elo_n': len(elo),
                    'value_p75': float(np.percentile(val, 75)) if len(val) else None, 'value_n': len(val),
                    'winter': int(g.winter.sum()), 'players': len(g)})
    return out


def _squads_tab(root, datasets, current, squads, ids):
    brand_header(root, 'Carrera por el título', 'Plantillas · ELO y valor', 7)
    path = root/'data/besoccer_uae/uae_league_squads_5_seasons.csv'
    if not path.exists():
        st.info('Falta data/besoccer_uae/uae_league_squads_5_seasons.csv (plantillas por temporada de BeSoccer).')
        return
    c_mode, c_played = st.columns([1, 1])
    model = c_mode.segmented_control('Modelo', ['Modelo general', 'Modelo media'], default='Modelo general', key='sq_model',
                                     help='General: temporada pasada Y/Y+1 = valor de la gráfica del año Y. Media: media de los años Y e Y+1.') or 'Modelo general'
    mode = 'media' if model == 'Modelo media' else 'general'
    played = c_played.segmented_control('Jugadores', ['Con minutos esa temporada', 'Toda la plantilla'], default='Con minutos esa temporada',
                                        key='sq_played') or 'Con minutos esa temporada'
    md('<div class="tr tr-callout" style="font-size:13px">' + (
        '<b>Modelo general.</b> Temporadas pasadas: ELO y valor del punto de la gráfica de BeSoccer del <b>primer año</b> de la temporada '
        '(2025 para 25/26), como en el informe del club. Tendencia: % de cambio en los últimos 3 años de la gráfica (2023→2025 para 25/26).'
        if mode == 'general' else
        '<b>Modelo media.</b> Temporadas pasadas: <b>media de los dos años</b> que abarca la temporada (2025 y 2026 para 25/26), para representar '
        'la temporada completa; si falta un año, se usa el que haya. Tendencia: la temporada frente a la media de <b>dos temporadas antes</b> '
        '(25/26 frente a 23/24; 26/27 frente a 24/25).') +
        '<br><span class="tr-muted">En los dos modelos: la temporada en curso (26/27) usa el ELO y el valor de hoy de la ficha (aún no existe 2027) y los '
        'fichajes de invierno ❄️ usan los datos del año en que llegaron (Borja 25/26: 4,47 M€), no la media con su club anterior.</span></div>')
    rows = _season_squads(str(path), path.stat().st_mtime, played.startswith('Con'), mode)
    squads_all = {}
    for d in sorted(datasets, key=lambda d: d['iteration']['season']):
        squads_all.update({s['id']: s for s in d['squads']})
    rows = [r for r in rows if r['id'] in squads_all]
    seasons = sorted({r['season'] for r in rows})
    last = seasons[-1]
    by = {(r['season'], r['id']): r for r in rows}
    w_now, w_first = by.get((last, WASL)) or {}, by.get((seasons[0], WASL)) or {}
    rank = lambda m: sorted([r for r in rows if r['season'] == last and r[m]], key=lambda r: -r[m]).index(w_now) + 1 if w_now.get(m) else None
    headline('Plantillas de la liga', f"Al Wasl: {rank('elo_p75')}º en ELO · {rank('value_p75')}º en valor",
             f"Así ha cambiado el nivel de las plantillas de la UAE Pro League en las últimas {len(seasons)} temporadas, con los jugadores que "
             f"<b>de verdad</b> estuvieron en cada equipo cada temporada (BeSoccer).")
    md('<div class="tr tr-callout"><b>Cómo se calcula.</b> Para cada equipo y temporada se toman los jugadores de su plantilla de esa temporada '
       '(por defecto, los que jugaron minutos) y se calcula el <b>P75</b>: el nivel a partir del cual está el 25% mejor de la plantilla. '
       'Es más estable que la media, porque no le afectan los canteranos o suplentes con poco nivel. '
       'Se usa el <b>ELO de jugador de BeSoccer</b> (no el ELO de equipo) y el <b>valor de mercado de BeSoccer</b> de esa temporada.<br>'
       '<span class="tr-muted"><b>Dato del momento</b> (los mismos datos que el PLAYER VALUE): en 26/27, el ELO y el valor de la ficha de BeSoccer '
       'de hoy de cada jugador, para todos los equipos (p. ej. Horkaš 70, Taremi 79). Los fichajes de invierno cuentan con sus datos de cuando llegaron '
       '(p. ej. Borja 25/26: 4,5 M€ y ELO 72, no los 7,7 M€ y 75 de antes de llegar). El resto, el listado de plantilla de cada temporada. '
       'Valores vacíos en BeSoccer se dejan vacíos (no se inventan).</span></div>')
    if w_now.get('elo_p75') and w_first.get('elo_p75'):
        kpi_tiles([
            (f"{w_now['elo_p75']:.0f}", f'ELO P75 Al Wasl {last[2:]}', f"{w_now['elo_p75']-w_first['elo_p75']:+.0f} desde {seasons[0][2:]}"),
            (f"{w_now['value_p75']/1e6:.1f} M€", f'Valor P75 Al Wasl {last[2:]}', f"{w_now['value_p75']/w_first['value_p75']-1:+.0%} desde {seasons[0][2:]}"),
            (f"{rank('elo_p75')}º", 'Puesto en ELO P75', f'de {sum(1 for r in rows if r["season"] == last)} equipos'),
            (f"{rank('value_p75')}º", 'Puesto en valor P75', f'de {sum(1 for r in rows if r["season"] == last)} equipos'),
        ])
    current_ids = [i for i in squads if (last, i) in by]
    c1, c2 = st.columns(2, gap='large')
    with c1:
        section('Evolución', 'P75 del ELO de la plantilla')
        sq_lines(rows, squads_all, root, lambda r: r['elo_p75'], 'ELO P75')
        squad_evolution_table(root, rows, squads_all, 'elo_p75', seasons, current_ids)
    with c2:
        section('Evolución', 'P75 del valor de mercado (M€)')
        sq_lines(rows, squads_all, root, lambda r: r['value_p75']/1e6 if r['value_p75'] else None, 'Valor P75 (M€)', '.2f')
        squad_evolution_table(root, rows, squads_all, 'value_p75', seasons, current_ids)
    section('Cruce', 'ELO frente a valor de mercado',
            'Por encima de la tendencia: el mercado valora a la plantilla más de lo que su ELO explica; por debajo: rinde más de lo que cuesta.')
    season = st.select_slider('Temporada', seasons, value=last, key='sq_season')
    squad_cross(root, rows, squads_all, season, SQ_FOCUS)

    # ---------------------------------------------------------------- PLAYER VALUE AVG
    pv = _player_value(str(path), path.stat().st_mtime, str(_series_csv() or ''), mode)
    pv = pv[pv.id.isin(squads_all.keys())]
    section('Jugadores', 'PLAYER VALUE AVG', 'Cuánto vale cada jugador frente a sus pares de la liga y de su club, temporada a temporada.')
    pv_method(float(pv.incompleto.mean()), mode)
    played_pv = pv[pv.minutes > 0]
    team_avg = [{'season': s_, 'id': i, 'v': g.pv_league.mean()} for (s_, i), g in played_pv.groupby(['season', 'id'])]
    section('Nivel de plantilla', 'PV LEAGUE medio por equipo',
            'Nota media (0–100) de los jugadores que han jugado, comparados con los de su misma edad y posición en toda la liga.')
    sq_lines(team_avg, squads_all, root, lambda r: r['v'], 'PV LEAGUE medio', '.1f', height=280)
    with st.expander('ℹ️ Cómo se calcula el PV LEAGUE medio y cómo leerlo'):
        _pv_league_explainer(played_pv, squads_all)
    section('Ranking de jugadores', 'PLAYER VALUE AVG por equipo y temporada')
    f1, f2, f3 = st.columns([1.4, 1, 1])
    pv_season = f1.select_slider('Temporada', seasons, value=last, key='pv_season')
    teams_s = sorted(set(pv[pv.season == pv_season].id), key=lambda i: (i not in SQ_FOCUS, SQ_FOCUS.index(i) if i in SQ_FOCUS else 0, name(squads_all[i])))
    pv_team_id = f2.selectbox('Equipo', teams_s, index=teams_s.index(WASL) if WASL in teams_s else 0,
                              format_func=lambda i: name(squads_all[i]), key='pv_team')
    only = f3.toggle('Solo jugadores con minutos', value=False, key='pv_only')
    view = pv[(pv.season == pv_season) & (pv.id == pv_team_id)]
    if only:
        view = view[view.minutes > 0]
    pv_table(view.sort_values('pv_avg', ascending=False))
    ref = _read_json(path.parent/'pv_reference_colleague.json')
    if ref:
        section('Control de calidad', 'Nuestro PV frente al informe del compañero',
                f'Mismo método, calculado de forma independiente ({model.lower()}). Su informe sigue el modelo general.')
        pv_reference_table(pv, ref)


def _series_csv():
    """BeSoccer yearly series per player (current squads), used only for the trends."""
    for p in (Path.home()/'Desktop/Teams/Alwasl_ELO/squad_players_all.csv',
              Path.home()/'Desktop/Teams/Market Intelligenca_AlWasl/besoccer_full_dataset/squad_players_all.csv'):
        if p.exists():
            return p
    return None


@st.cache_data(show_spinner=False)
def _player_value(path: str, mtime: float, series: str, mode: str = 'general'):
    """PV with fresh BeSoccer profiles (data/besoccer_uae/player_charts) and IMPECT winter-arrival dates."""
    path = Path(path)
    profiles = load_profiles(path.parent/'player_charts')
    arrivals = winter_arrivals(path.parents[1]/'title_race')
    return player_value(path, None if profiles else (Path(series) if series else None), profiles=profiles, arrivals=arrivals, mode=mode,
                        minutes=impect_minutes(path.parents[1]/'title_race'))


def _pv_league_explainer(played_pv, squads_all):
    last = sorted(played_pv.season.unique())[-1]
    w = played_pv[(played_pv.season == last) & (played_pv.id == WASL)].sort_values('pv_league', ascending=False)
    league = played_pv[played_pv.season == last].groupby('id').pv_league.mean().sort_values(ascending=False)
    rank = list(league.index).index(WASL) + 1 if WASL in league.index else None
    top = ', '.join(f'{esc(r.player)} {r.pv_league:.0f}' for r in w.head(3).itertuples())
    md(f'''<div class="tr tr-callout" style="line-height:1.75">
<b>1. La nota de cada jugador (PV LEAGUE, 0–100)</b><br>
PV LEAGUE = 0,40·pct(ELO) + 0,10·pct(tendencia ELO) + 0,40·pct(valor) + 0,10·pct(tendencia valor)<br>
Cada «pct» es el percentil del jugador dentro de su grupo: <b>misma temporada, misma cohorte de edad y misma posición</b>, entre todos los
jugadores de la liga. Ejemplo: un central nacido en 1999–02 se compara solo con los centrales 1999–02 de la liga esa temporada.
Un 80 significa que está por encima del 80% de sus iguales.<br>
<b>2. La nota del equipo (PV LEAGUE medio)</b><br>
PV LEAGUE medio (equipo, temporada) = media simple del PV LEAGUE de sus jugadores <b>con minutos</b> esa temporada.<br>
<b>3. Cómo leerlo</b><br>
· <b>50</b> = plantilla de nivel medio: sus jugadores están, de media, a la altura de los de su edad y posición en la liga.<br>
· <b>70</b> = sus jugadores están, de media, por encima del 70% de sus iguales. Plantilla de las de arriba.<br>
· Al ser percentiles dentro de la liga, mide <b>el nivel relativo</b> a la liga de cada temporada, no un nivel absoluto.<br>
<b>4. Por qué el PV LEAGUE y no el PV TEAM o el PV AVG</b><br>
· El <b>PV TEAM</b> compara a cada jugador solo con sus compañeros de club: en todos los equipos hay jugadores arriba y abajo,
así que su media siempre sale alrededor de 50 y no sirve para comparar equipos.<br>
· El <b>PV AVG</b> es mitad PV LEAGUE y mitad PV TEAM: arrastra ese 50 y reduce a la mitad las diferencias entre equipos.<br>
<b>5. Ejemplo · Al Wasl {esc(last)}</b><br>
{len(w)} jugadores con minutos · mejores notas: {top}. Media: <b>{w.pv_league.mean():.1f}</b>
({rank}º de la liga esa temporada).<br>
<span class="tr-muted">Limitaciones: es una media simple (no pondera por minutos: un jugador con 20 minutos cuenta igual que uno con 450).
Con pocas jornadas, los jugadores con minutos aún pueden cambiar mucho. Las tendencias son el % de cambio en 3 años de la gráfica de BeSoccer.</span></div>''')
