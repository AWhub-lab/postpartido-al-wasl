from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .assets import ensure_crest_path
from .config import ROOT
from .report import (
    _al_wasl_and_rival_meta,
    _compare_squad_kpis,
    _goals_summary,
    _home_away_meta,
    _match_datetime_display,
    _matchday_display,
    _player_name,
    _players_by_id,
)
from .visuals import (
    AL_WASL_COLOR,
    RIVAL_COLOR,
    _minute_label,
    _shot_outcome,
    _t,
    render_cross_map,
    render_lineup,
    render_match_dashboard,
    render_momentum_and_xg,
    render_pass_distribution_by_period,
    render_pass_network,
    render_pass_network_period_page,
    render_pass_zone_heatmap,
    render_set_piece_chart,
    render_shot_map,
    render_threat_bar_chart,
    render_transitions_map,
    render_zone14_flow,
    zone14_top_players,
)

REPORT_GOLD = colors.HexColor("#D4A017")
REPORT_GOLD_LIGHT = colors.HexColor("#F8E7A1")
REPORT_INK = colors.HexColor("#111827")
REPORT_CREAM = colors.HexColor("#FFF9EB")
REPORT_SMOKE = colors.HexColor("#F5F1E6")
REPORT_BORDER = colors.HexColor("#E5D7AE")
AL_WASL_ACCENT = colors.HexColor(AL_WASL_COLOR)
RIVAL_ACCENT = colors.HexColor(RIVAL_COLOR)

PASS_NETWORK_CAP_NOTE_ES = (
    "Esta red muestra solo las 8 conexiones más repetidas del partido completo (mínimo 5 pases entre los mismos dos "
    "jugadores). Con cientos de pases en 90 minutos, limitar a las más frecuentes ayuda a leer el patrón dominante sin "
    "saturar el gráfico. En la red de pases por tramos (5 ventanas de ~15-20 min) no se aplica este límite, porque el "
    "volumen de pases en cada tramo ya es bajo y cada conexión de 2 o más pases es relevante."
)
PASS_NETWORK_CAP_NOTE_EN = (
    "This network shows only the 8 most repeated connections of the full match (minimum 5 passes between the same two "
    "players). With hundreds of passes over 90 minutes, capping to the most frequent ones keeps the dominant pattern "
    "readable without cluttering the chart. The pass network by phase (5 windows of ~15-20 min) does not apply this "
    "cap, since the pass volume in each window is already low and every connection of 2 or more passes is relevant."
)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SectionTitle", fontName="Helvetica-Bold", fontSize=19, leading=24, textColor=REPORT_INK, spaceAfter=6))
    styles.add(ParagraphStyle(name="SectionLead", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#4B5563")))
    styles.add(ParagraphStyle(name="CardTitle", fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=REPORT_INK, alignment=1))
    styles.add(ParagraphStyle(name="CardBody", fontName="Helvetica", fontSize=10, leading=13, textColor=colors.HexColor("#334155"), alignment=1))
    styles.add(ParagraphStyle(name="Mini", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="CardCaption", fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="CardHeader", fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.white, alignment=1))
    return styles


def _fmt(value: Any, decimals: int = 3) -> str:
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    if value is None:
        return "-"
    return str(value)


def _scaled_image(path: Any, width: float, max_height: float | None = None) -> Image:
    with PILImage.open(path) as img:
        px_width, px_height = img.size
    height = width * (px_height / px_width)
    if max_height and height > max_height:
        height = max_height
        width = height * (px_width / px_height)
    return Image(str(path), width=width, height=height)


def _team_badge(name: str) -> str:
    parts = [part for part in re.split(r"[\s\-]+", name) if part]
    if not parts:
        return "TM"
    if len(parts) == 1:
        return parts[0][:3].upper()
    return "".join(part[0] for part in parts[:3]).upper()


def _draw_team_mark(canvas, bundle: dict[str, Any], squad_id: int | None, team_name: str, x: float, y: float, size: float, fill_color) -> None:
    crest = ensure_crest_path(bundle, squad_id)
    if crest:
        canvas.drawImage(str(crest), x - size / 2, y - size / 2, width=size, height=size, preserveAspectRatio=True, mask="auto")
        return
    canvas.saveState()
    canvas.setFillColor(fill_color)
    canvas.circle(x, y, size / 2, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", max(10, size * 0.22))
    canvas.drawCentredString(x, y - size * 0.09, _team_badge(team_name))
    canvas.restoreState()


def _metric_cards(bundle: dict[str, Any], styles, lang: str = "es") -> list[Any]:
    home_meta, away_meta = _home_away_meta(bundle)
    players_by_id = _players_by_id(bundle)

    def _top_threat(team_id: int) -> tuple[str, float]:
        created: dict[int, float] = {}
        for event in bundle.get("events", []):
            if event.get("squadId") != team_id or not event.get("pass") or event.get("result") != "SUCCESS":
                continue
            player_id = (event.get("player") or {}).get("id")
            if not player_id:
                continue
            created[player_id] = created.get(player_id, 0.0) + max(0.0, float(((event.get("pxT") or {}).get("team") or 0.0)))
        if not created:
            return "-", 0.0
        player_id, value = max(created.items(), key=lambda item: item[1])
        return _player_name(players_by_id.get(player_id), player_id), value

    def _top_passes(team_id: int) -> tuple[str, int]:
        counts: dict[int, int] = {}
        for event in bundle.get("events", []):
            if event.get("squadId") != team_id or not event.get("pass") or event.get("result") != "SUCCESS":
                continue
            player_id = (event.get("player") or {}).get("id")
            if player_id:
                counts[player_id] = counts.get(player_id, 0) + 1
        if not counts:
            return "-", 0
        player_id, value = max(counts.items(), key=lambda item: item[1])
        return _player_name(players_by_id.get(player_id), player_id), value

    home_threat = _top_threat(home_meta["id"])
    away_threat = _top_threat(away_meta["id"])
    home_pass = _top_passes(home_meta["id"])
    away_pass = _top_passes(away_meta["id"])

    header_row = [
        Paragraph(f"<b>{home_meta['name']}</b>", styles["CardHeader"]),
        Paragraph("&nbsp;", styles["CardHeader"]),
        Paragraph(f"<b>{away_meta['name']}</b>", styles["CardHeader"]),
    ]
    data = [
        header_row,
        [
            Paragraph(f"<b>{home_threat[0]}</b><br/><font color='#475569'>pxT created: {_fmt(home_threat[1], 2)}</font>", styles["CardBody"]),
            Paragraph("<b>Most Threat</b>", styles["CardTitle"]),
            Paragraph(f"<b>{away_threat[0]}</b><br/><font color='#475569'>pxT created: {_fmt(away_threat[1], 2)}</font>", styles["CardBody"]),
        ],
        [
            Paragraph(f"<b>{home_pass[0]}</b><br/><font color='#475569'>Completed passes: {home_pass[1]}</font>", styles["CardBody"]),
            Paragraph("<b>Completed Passes</b>", styles["CardTitle"]),
            Paragraph(f"<b>{away_pass[0]}</b><br/><font color='#475569'>Completed passes: {away_pass[1]}</font>", styles["CardBody"]),
        ],
    ]
    table = Table(data, colWidths=[6.1 * cm, 4.7 * cm, 6.1 * cm], rowHeights=[0.9 * cm, 2.25 * cm, 2.25 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), AL_WASL_ACCENT),
                ("BACKGROUND", (1, 0), (1, 0), REPORT_INK),
                ("BACKGROUND", (2, 0), (2, 0), RIVAL_ACCENT),
                ("BACKGROUND", (0, 1), (0, -1), colors.white),
                ("BACKGROUND", (2, 1), (2, -1), colors.white),
                ("BACKGROUND", (1, 1), (1, -1), REPORT_CREAM),
                ("BOX", (0, 0), (0, -1), 1.3, REPORT_BORDER),
                ("BOX", (1, 0), (1, -1), 1.3, REPORT_BORDER),
                ("BOX", (2, 0), (2, -1), 1.3, REPORT_BORDER),
                ("ROUNDEDCORNERS", [8, 8, 8, 8]),
                ("INNERGRID", (0, 1), (-1, -1), 10, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 1), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ]
        )
    )
    caption = Paragraph(
        _t(
            "<b>Most Threat</b>: jugador que más amenaza (pxT) genera con sus pases completados. "
            "<b>Completed Passes</b>: jugador con más pases completados.",
            "<b>Most Threat</b>: player generating the most threat (pxT) with completed passes. "
            "<b>Completed Passes</b>: player with the most completed passes.",
            lang,
        ),
        styles["CardCaption"],
    )
    return [table, Spacer(1, 0.2 * cm), caption]


def _styled_data_table(data: list[list[Any]], widths: list[float]) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), REPORT_INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, REPORT_CREAM]),
                ("BOX", (0, 0), (-1, -1), 0.9, REPORT_BORDER),
                ("GRID", (0, 0), (-1, -1), 0.45, REPORT_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _team_legend_row(al_wasl_meta: dict[str, Any], rival_meta: dict[str, Any], styles) -> Table:
    def swatch(color_hex: str) -> Table:
        cell = Table([[""]], colWidths=[0.45 * cm], rowHeights=[0.35 * cm])
        cell.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color_hex)), ("BOX", (0, 0), (-1, -1), 0.5, REPORT_BORDER)]))
        return cell

    row = [
        swatch(AL_WASL_COLOR),
        Paragraph(f"<b>{al_wasl_meta['name']}</b>", styles["Mini"]),
        swatch(RIVAL_COLOR),
        Paragraph(f"<b>{rival_meta['name']}</b>", styles["Mini"]),
    ]
    table = Table([row], colWidths=[0.6 * cm, 6.5 * cm, 0.6 * cm, 6.5 * cm])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return table


def _shot_timeline_sidebar(bundle: dict[str, Any], squad_id: int | None, styles, lang: str = "es") -> Table:
    al_wasl_meta, _rival_meta = _al_wasl_and_rival_meta(bundle)
    color = colors.HexColor(AL_WASL_COLOR) if squad_id == al_wasl_meta["id"] else colors.HexColor(RIVAL_COLOR)
    players_by_id = _players_by_id(bundle)

    header_style = ParagraphStyle("SidebarHeader", parent=styles["Mini"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=8.5, alignment=1)
    row_style = ParagraphStyle("SidebarRow", parent=styles["Mini"], fontSize=7.3, leading=9.5)

    rows = []
    for event in bundle.get("events", []):
        if not event.get("shot") or event.get("squadId") != squad_id:
            continue
        player_id = (event.get("player") or {}).get("id")
        minute_text = _minute_label(event)
        try:
            minute_sort = int(minute_text.rstrip("'"))
        except ValueError:
            minute_sort = 999
        rows.append((minute_sort, minute_text, _player_name(players_by_id.get(player_id), player_id), _shot_outcome(event)))
    rows.sort(key=lambda item: item[0])

    data: list[list[Any]] = [[Paragraph(_t("Disparos", "Shots", lang), header_style)]]
    for _minute_sort, minute_text, player, outcome in rows:
        data.append([Paragraph(f"<b>{minute_text}</b> {player}<br/><font size=6.5 color='#64748B'>{outcome}</font>", row_style)])
    if len(data) == 1:
        data.append([Paragraph("-", row_style)])

    table = Table(data, colWidths=[3.1 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), color),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, REPORT_CREAM]),
                ("GRID", (0, 0), (-1, -1), 0.4, REPORT_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _zone14_player_table(bundle: dict[str, Any], home_meta: dict[str, Any], away_meta: dict[str, Any], styles, lang: str = "es") -> Table:
    al_wasl_meta, _rival_meta = _al_wasl_and_rival_meta(bundle)

    def color_for(squad_id: int | None):
        return colors.HexColor(AL_WASL_COLOR) if squad_id == al_wasl_meta["id"] else colors.HexColor(RIVAL_COLOR)

    data = [[_t("Equipo", "Team", lang), _t("Más pases hacia Zona 14", "Most passes into Zone 14", lang), _t("Más recibidos en Zona 14", "Most received in Zone 14", lang)]]
    for meta in (home_meta, away_meta):
        passer_row, receiver_row = zone14_top_players(bundle, meta["id"])
        passer_text = f"{passer_row[0]} ({passer_row[1]})" if passer_row else "-"
        receiver_text = f"{receiver_row[0]} ({receiver_row[1]})" if receiver_row else "-"
        data.append([meta["name"], passer_text, receiver_text])

    table = Table(data, colWidths=[5.0 * cm, 6.2 * cm, 6.2 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), REPORT_INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, REPORT_CREAM]),
                ("GRID", (0, 0), (-1, -1), 0.45, REPORT_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TEXTCOLOR", (0, 1), (0, 1), color_for(home_meta["id"])),
                ("TEXTCOLOR", (0, 2), (0, 2), color_for(away_meta["id"])),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ]
        )
    )
    return table


def _cover_callback(meta: dict[str, Any]):
    def _draw(canvas, doc):
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(REPORT_CREAM)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        canvas.setFillColor(REPORT_GOLD)
        canvas.rect(0, height * 0.55, width, height * 0.45, fill=1, stroke=0)
        canvas.setFillColor(REPORT_INK)
        canvas.rect(0, 0, width, height * 0.16, fill=1, stroke=0)

        center_x = width / 2

        canvas.setFillColor(REPORT_INK)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawCentredString(center_x, height * 0.905, "IMPECT POST-MATCH REPORT")

        crest_y = height * 0.735
        crest_dx = 130
        home_color = AL_WASL_ACCENT if meta["home_is_al_wasl"] else RIVAL_ACCENT
        away_color = RIVAL_ACCENT if meta["home_is_al_wasl"] else AL_WASL_ACCENT
        _draw_team_mark(canvas, meta["bundle"], meta["home_id"], meta["home_name"], center_x - crest_dx, crest_y, 68, home_color)
        _draw_team_mark(canvas, meta["bundle"], meta["away_id"], meta["away_name"], center_x + crest_dx, crest_y, 68, away_color)

        canvas.setFillColor(REPORT_INK)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawCentredString(center_x, crest_y - 4, "VS")

        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawCentredString(center_x - crest_dx, crest_y - 48, meta["home_name"])
        canvas.drawCentredString(center_x + crest_dx, crest_y - 48, meta["away_name"])

        canvas.setFont("Helvetica-Bold", 48)
        canvas.drawCentredString(center_x - crest_dx, height * 0.585, meta["home_goals_text"])
        canvas.drawCentredString(center_x + crest_dx, height * 0.585, meta["away_goals_text"])
        canvas.setFont("Helvetica-Bold", 32)
        canvas.drawCentredString(center_x, height * 0.585, "-")
        if meta.get("halftime_text"):
            canvas.setFont("Helvetica", 10.5)
            canvas.drawCentredString(center_x, height * 0.545, meta["halftime_text"])

        canvas.setFont("Helvetica", 12.5)
        canvas.drawCentredString(center_x, height * 0.485, meta["date"])
        canvas.drawCentredString(center_x, height * 0.445, meta["matchday"])
        canvas.drawCentredString(center_x, height * 0.405, f"Match ID: {meta['match_id']}")

        canvas.setStrokeColor(REPORT_INK)
        canvas.setLineWidth(1.2)
        canvas.line(center_x - 115, height * 0.37, center_x + 115, height * 0.37)

        canvas.setFont("Helvetica-Bold", 16)
        canvas.setFillColor(REPORT_GOLD)
        canvas.drawCentredString(center_x, 58, "Al Wasl visual report template")
        canvas.restoreState()

    return _draw


def _inner_page_callback(meta: dict[str, Any]):
    def _draw(canvas, doc):
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(REPORT_CREAM)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        canvas.setFillColor(REPORT_INK)
        canvas.rect(0, height - 1.65 * cm, width, 1.65 * cm, fill=1, stroke=0)
        canvas.setFillColor(REPORT_GOLD)
        canvas.rect(0, height - 1.82 * cm, width, 0.16 * cm, fill=1, stroke=0)

        _draw_team_mark(canvas, meta["bundle"], meta["al_wasl_id"], meta["al_wasl_name"], 1.55 * cm, height - 0.82 * cm, 24, REPORT_GOLD)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(2.05 * cm, height - 0.98 * cm, meta["title"])
        canvas.setFont("Helvetica", 9)
        canvas.drawString(2.05 * cm, height - 1.28 * cm, f"{meta['date']}   |   {meta['score']}")

        canvas.setFillColor(REPORT_INK)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(width - 1.4 * cm, 0.75 * cm, f"{_t('Página', 'Page', meta.get('lang', 'es'))} {canvas.getPageNumber() - 1}")
        canvas.restoreState()

    return _draw


def render_pdf_report(match_id: int, bundle: dict[str, Any], lang: str = "es") -> Path:
    reports_dir = ROOT / "reports"
    assets_dir = reports_dir / f"match_{match_id}_assets_{lang}"
    reports_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    home_meta, away_meta = _home_away_meta(bundle)
    al_wasl_meta, rival_meta = _al_wasl_and_rival_meta(bundle)
    match = bundle.get("match", {})
    match_summary = bundle.get("match_summary", {})
    title = f"{home_meta['name']} vs {away_meta['name']}"
    date_text = _match_datetime_display(match, match_summary)
    matchday = _matchday_display(match_summary, lang)
    home_goals, away_goals, home_ht, away_ht = _goals_summary(match_summary)
    home_goals_text = str(home_goals) if home_goals is not None else "-"
    away_goals_text = str(away_goals) if away_goals is not None else "-"
    halftime_text = f"{_t('Descanso', 'Half-time', lang)}: {home_ht}-{away_ht}" if home_ht is not None and away_ht is not None else ""
    score_text = f"{home_goals_text}-{away_goals_text}"

    lineup = render_lineup(bundle, assets_dir / "lineup.png", lang)
    dashboard = render_match_dashboard(bundle, assets_dir / "dashboard.png", lang)
    momentum = render_momentum_and_xg(bundle, assets_dir / "momentum.png", lang)
    shot_map = render_shot_map(bundle, assets_dir / "shot_map.png", lang)
    pass_zones = render_pass_zone_heatmap(bundle, assets_dir / "pass_zones.png", lang)
    zone14_flow = render_zone14_flow(bundle, assets_dir / "zone14_flow.png", lang)
    pass_network_home = render_pass_network(bundle, assets_dir / "pass_network_home.png", home_meta["id"], lang)
    threat_home = render_threat_bar_chart(bundle, assets_dir / "threat_home.png", home_meta["id"], lang)
    pass_network_home_periods = render_pass_network_period_page(bundle, assets_dir / "pass_network_home_periods.png", home_meta["id"], lang)
    pass_network_away = render_pass_network(bundle, assets_dir / "pass_network_away.png", away_meta["id"], lang)
    threat_away = render_threat_bar_chart(bundle, assets_dir / "threat_away.png", away_meta["id"], lang)
    pass_network_away_periods = render_pass_network_period_page(bundle, assets_dir / "pass_network_away_periods.png", away_meta["id"], lang)
    pass_distribution = render_pass_distribution_by_period(bundle, assets_dir / "pass_distribution.png", lang)
    transitions_map = render_transitions_map(bundle, assets_dir / "transitions.png", lang)
    cross_map = render_cross_map(bundle, assets_dir / "crosses.png", lang)
    set_piece_chart = render_set_piece_chart(bundle, assets_dir / "set_pieces.png", lang)

    suffix = "" if lang == "es" else f"_{lang}"
    pdf_path = reports_dir / f"match_{match_id}_report{suffix}.pdf"
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=1.45 * cm,
        leftMargin=1.45 * cm,
        topMargin=2.2 * cm,
        bottomMargin=1.25 * cm,
    )
    styles = _styles()
    story = []

    meta = {
        "title": title,
        "date": date_text,
        "score": score_text,
        "home_goals_text": home_goals_text,
        "away_goals_text": away_goals_text,
        "halftime_text": halftime_text,
        "matchday": matchday,
        "match_id": match_id,
        "home_name": home_meta["name"],
        "away_name": away_meta["name"],
        "home_id": home_meta["id"],
        "away_id": away_meta["id"],
        "al_wasl_id": al_wasl_meta["id"],
        "al_wasl_name": al_wasl_meta["name"],
        "home_is_al_wasl": home_meta["id"] == al_wasl_meta["id"],
        "bundle": bundle,
        "lang": lang,
    }

    story.append(Spacer(1, 24.8 * cm))
    story.append(PageBreak())

    story.append(Paragraph(_t("Alineaciones y sistema de juego", "Starting XI and formation", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Once inicial y formación de cada equipo. Local arriba, visitante abajo.", "Starting XI and formation for each team. Home on top, away on bottom.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(lineup, 13.0 * cm))
    story.append(PageBreak())

    story.append(Paragraph("Match Dashboard", styles["SectionTitle"]))
    story.append(Paragraph(_t("Resumen central con barras enfrentadas para leer el partido de un vistazo.", "Central summary with head-to-head bars to read the match at a glance.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(Image(str(dashboard), width=18.0 * cm, height=12.0 * cm))
    story.append(Spacer(1, 0.35 * cm))
    story.extend(_metric_cards(bundle, styles, lang))
    story.append(PageBreak())

    story.append(Paragraph(_t("xT Momentum, pxT acumulado y xG acumulado", "xT Momentum, cumulative pxT and cumulative xG", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Evolución del control del partido (amenaza neta por minuto), dominio territorial acumulado (pxT) y xG acumulado por equipo, con los goles marcados en los tres ejes.", "Evolution of match control (net threat per minute), cumulative territorial dominance (pxT) and cumulative xG per team, with goals marked on all three axes.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.12 * cm))
    story.append(_team_legend_row(al_wasl_meta, rival_meta, styles))
    story.append(Spacer(1, 0.1 * cm))
    story.append(_scaled_image(momentum, 14.6 * cm))
    story.append(Spacer(1, 0.15 * cm))
    story.append(
        Paragraph(
            _t(
                "<b>xT Momentum</b>: quién genera más amenaza en cada tramo del partido (diferencia de pxT suavizada). "
                "<b>pxT acumulado</b>: suma de amenaza generada a lo largo de todo el partido, sin restar la del rival. "
                "<b>xG acumulado</b>: suma del xG real de cada disparo, minuto a minuto.",
                "<b>xT Momentum</b>: who generates more threat in each phase of the match (smoothed pxT difference). "
                "<b>Cumulative pxT</b>: sum of threat generated throughout the whole match, without subtracting the rival's. "
                "<b>Cumulative xG</b>: sum of the real xG of each shot, minute by minute.",
                lang,
            ),
            styles["CardCaption"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph(_t("Fase ofensiva: finalización", "Attacking phase: finishing", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Disparos de cada equipo en su campograma (coordenadas reales, ambas mitades del partido). Local a la izquierda, visitante a la derecha, con el detalle de cada disparo.", "Each team's shots on its own pitch map (real coordinates, both halves of the match). Home on the left, away on the right, with the detail of each shot.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    shot_map_layout = Table(
        [[_shot_timeline_sidebar(bundle, home_meta["id"], styles, lang), _scaled_image(shot_map, 12.0 * cm), _shot_timeline_sidebar(bundle, away_meta["id"], styles, lang)]],
        colWidths=[2.9 * cm, 12.0 * cm, 2.9 * cm],
    )
    shot_map_layout.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    story.append(shot_map_layout)
    story.append(PageBreak())

    story.append(Paragraph(_t("Fase de construcción", "Build-up phase", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Zonas del campo donde cada equipo completa más pases (el número es la cantidad de pases completados que empiezan en esa zona), con la Zona 14 señalada como referencia.", "Pitch zones where each team completes the most passes (the number is the count of completed passes starting in that zone), with Zone 14 marked as a reference.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(pass_zones, 13.2 * cm))
    story.append(PageBreak())

    story.append(Paragraph(_t("Zona 14: alimentación y distribución", "Zone 14: feeding and distribution", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Quién surte la Zona 14 y hacia dónde reparte desde ella cada equipo. El número y el grosor de cada flecha son la cantidad de pases entre esa zona y la Zona 14.", "Who feeds Zone 14 and where each team distributes from it. The number and thickness of each arrow are the number of passes between that zone and Zone 14.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(zone14_flow, 15.5 * cm))
    story.append(Spacer(1, 0.25 * cm))
    story.append(_zone14_player_table(bundle, home_meta, away_meta, styles, lang))
    story.append(PageBreak())

    story.append(Paragraph(_t(f"Red de pases: {home_meta['name']}", f"Pass network: {home_meta['name']}", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Tamaño del nodo por volumen de contactos, color por amenaza generada y flechas exteriores con profundidad y amplitud del bloque. Debajo, la amenaza generada por cada jugador.", "Node size by touch volume, color by threat generated, and exterior arrows showing block depth and width. Below, threat generated by each player.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(pass_network_home, 16.6 * cm, max_height=15.0 * cm))
    story.append(Spacer(1, 0.25 * cm))
    story.append(_scaled_image(threat_home, 16.6 * cm))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(_t(PASS_NETWORK_CAP_NOTE_ES, PASS_NETWORK_CAP_NOTE_EN, lang), styles["CardCaption"]))
    story.append(PageBreak())

    story.append(Paragraph(_t(f"Red de pases por tramos: {home_meta['name']}", f"Pass network by phase: {home_meta['name']}", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Alineación, cambios y evolución de la red de pases en 5 tramos del partido.", "Line-up, substitutions and pass network evolution across 5 phases of the match.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(pass_network_home_periods, 18.0 * cm, max_height=22.5 * cm))
    story.append(PageBreak())

    story.append(Paragraph(_t(f"Red de pases: {away_meta['name']}", f"Pass network: {away_meta['name']}", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Misma lectura para el rival: conexiones, amenaza generada y forma del bloque.", "Same read for the opponent: connections, threat generated and block shape.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(pass_network_away, 16.6 * cm, max_height=15.0 * cm))
    story.append(Spacer(1, 0.25 * cm))
    story.append(_scaled_image(threat_away, 16.6 * cm))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(_t(PASS_NETWORK_CAP_NOTE_ES, PASS_NETWORK_CAP_NOTE_EN, lang), styles["CardCaption"]))
    story.append(PageBreak())

    story.append(Paragraph(_t(f"Red de pases por tramos: {away_meta['name']}", f"Pass network by phase: {away_meta['name']}", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Alineación, cambios y evolución de la red de pases en 5 tramos del partido.", "Line-up, substitutions and pass network evolution across 5 phases of the match.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(pass_network_away_periods, 18.0 * cm, max_height=22.5 * cm))
    story.append(PageBreak())

    story.append(Paragraph(_t("Distribución de pases por período", "Pass distribution by period", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Volumen de pases completados de cada equipo en tramos de 10 minutos, para ver cuándo controla más el balón cada uno.", "Volume of completed passes for each team in 10-minute spans, to see when each one controls the ball the most.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(pass_distribution, 18.0 * cm))
    story.append(PageBreak())

    story.append(Paragraph(_t("Transiciones", "Transitions", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("De la recuperación (intercepción) al remate, separado por parte del partido: cada flecha conecta el punto de recuperación con el disparo que genera.", "From recovery (interception) to shot, split by half of the match: each arrow connects the recovery point with the shot it generates.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(transitions_map, 17.5 * cm))
    story.append(PageBreak())

    story.append(Paragraph(_t("Centros laterales", "Crosses", lang), styles["SectionTitle"]))
    story.append(Paragraph(_t("Punto de origen, marca de destino (según cómo terminó la jugada) y resumen por tipo cerca del centro del campo.", "Origin point, destination marker (based on how the play ended) and a by-type summary near the centre of the pitch.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_scaled_image(cross_map, 12.8 * cm, max_height=17.4 * cm))
    story.append(PageBreak())

    story.append(Paragraph("Set Pieces", styles["SectionTitle"]))
    story.append(Paragraph(_t("Bloque de ABP con gráfico principal por tipo de acción.", "Set-piece block with the main chart by action type.", lang), styles["SectionLead"]))
    story.append(Spacer(1, 0.18 * cm))
    story.append(Image(str(set_piece_chart), width=18.0 * cm, height=8.6 * cm))
    story.append(Spacer(1, 0.35 * cm))

    kpi_rows = _compare_squad_kpis(bundle)
    if kpi_rows:
        story.append(Spacer(1, 0.45 * cm))
        kpi_table = [["KPI", home_meta["name"], away_meta["name"], "Edge"]]
        for row in kpi_rows[:8]:
            kpi_table.append([row["metric"], _fmt(row["home"], 2), _fmt(row["away"], 2), row["edge"]])
        story.append(_styled_data_table(kpi_table, [7.0 * cm, 3.1 * cm, 3.1 * cm, 4.0 * cm]))

    doc.build(story, onFirstPage=_cover_callback(meta), onLaterPages=_inner_page_callback(meta))
    return pdf_path
