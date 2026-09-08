from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-postmatch-impect")

import matplotlib

matplotlib.use("Agg")

import numpy as np
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Rectangle
from PIL import Image as PILImage

from .assets import ensure_crest_path
from .report import (
    _al_wasl_and_rival_meta,
    _event_shot_xg_map,
    _home_away_meta,
    _player_name,
    _players_by_id,
    _squad_name,
)

PITCH_X_MIN = -52.5
PITCH_X_MAX = 52.5
PITCH_Y_MIN = -34.0
PITCH_Y_MAX = 34.0

REPORT_GOLD = "#D4A017"
REPORT_GOLD_LIGHT = "#F8E7A1"
REPORT_INK = "#111827"
REPORT_CREAM = "#FFF9EB"
AL_WASL_COLOR = "#D4A017"
RIVAL_COLOR = "#C84C09"
LINE_COLOR = "#111827"
PITCH_COLOR = "#FFFDF7"
ACCENT = "#0EA5E9"
ZONE_HIGHLIGHT = "#1D4ED8"
THREAT_CMAP = LinearSegmentedColormap.from_list("threat", ["#ECFCCB", "#65A30D", "#F59E0B", "#DC2626"])
AL_WASL_ZONE_CMAP = LinearSegmentedColormap.from_list("al_wasl_zone", ["#FFF9EB", "#F8E7A1", "#D4A017", "#7C5A0B"])
RIVAL_ZONE_CMAP = LinearSegmentedColormap.from_list("rival_zone", ["#FDEEE3", "#F3B78B", "#C84C09", "#7A2E05"])

ZONE_COLS = 6
ZONE_ROWS = 3
ZONE_14 = (4, 1)  # 5a columna (entrada al último tercio), fila central

CROSS_ACTIONS = {"HIGH_CROSS", "LOW_CROSS"}
CROSS_OUTCOME_STYLE = {
    "goal": {"color": "#16A34A", "marker": "*", "size": 340},
    "shot": {"color": "#F59E0B", "marker": "^", "size": 190},
    "completed": {"color": "#2563EB", "marker": "o", "size": 140},
    "incomplete": {"color": "#94A3B8", "marker": "x", "size": 140},
}

_CREST_CACHE: dict[Any, Any] = {}


def _t(es: str, en: str, lang: str) -> str:
    return en if lang == "en" else es


CROSS_OUTCOME_LABELS = {
    "goal": {"es": "Gol", "en": "Goal"},
    "shot": {"es": "Remate", "en": "Shot"},
    "completed": {"es": "Completado", "en": "Completed"},
    "incomplete": {"es": "Incompleto", "en": "Incomplete"},
}


def _draw_pitch(ax, pad_x: float = 2.0, pad_top: float = 2.0, pad_bottom: float = 2.0) -> None:
    ax.set_facecolor(PITCH_COLOR)
    ax.add_patch(Rectangle((PITCH_X_MIN, PITCH_Y_MIN), 105, 68, fill=False, lw=2.0, ec=LINE_COLOR, zorder=4))
    ax.plot([0, 0], [PITCH_Y_MIN, PITCH_Y_MAX], color=LINE_COLOR, lw=1.4, zorder=4)
    ax.add_patch(Circle((0, 0), 9.15, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Circle((0, 0), 0.22, color=LINE_COLOR, zorder=4))
    ax.add_patch(Rectangle((PITCH_X_MIN, -20.16), 16.5, 40.32, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Rectangle((36.0, -20.16), 16.5, 40.32, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Rectangle((PITCH_X_MIN, -9.16), 5.5, 18.32, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Rectangle((47.0, -9.16), 5.5, 18.32, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Circle((-41.5, 0), 0.22, color=LINE_COLOR, zorder=4))
    ax.add_patch(Circle((41.5, 0), 0.22, color=LINE_COLOR, zorder=4))
    ax.add_patch(Arc((-41.5, 0), 18.3, 18.3, angle=0, theta1=310, theta2=50, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Arc((41.5, 0), 18.3, 18.3, angle=0, theta1=130, theta2=230, lw=1.3, ec=ACCENT, zorder=4))
    ax.set_xlim(PITCH_X_MIN - pad_x, PITCH_X_MAX + pad_x)
    ax.set_ylim(PITCH_Y_MIN - pad_bottom, PITCH_Y_MAX + pad_top)
    ax.set_aspect("equal")
    ax.axis("off")


def _create_pitch_ax(figsize: tuple[float, float] = (12, 8), pad_x: float = 2.0, pad_top: float = 2.0, pad_bottom: float = 2.0):
    fig, ax = plt.subplots(figsize=figsize, dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    _draw_pitch(ax, pad_x=pad_x, pad_top=pad_top, pad_bottom=pad_bottom)
    return fig, ax


def _draw_pitch_vertical(ax, pad_x: float = 2.0, pad_top: float = 2.0, pad_bottom: float = 2.0) -> None:
    """Same pitch as _draw_pitch but rotated so the length (x) runs vertically.

    Data points in the normal (x=length, y=width) convention must be plotted
    here as (y, x) — use _vswap(x, y) when placing markers/lines/text.
    """
    ax.set_facecolor(PITCH_COLOR)
    ax.add_patch(Rectangle((PITCH_Y_MIN, PITCH_X_MIN), 68, 105, fill=False, lw=2.0, ec=LINE_COLOR, zorder=4))
    ax.plot([PITCH_Y_MIN, PITCH_Y_MAX], [0, 0], color=LINE_COLOR, lw=1.4, zorder=4)
    ax.add_patch(Circle((0, 0), 9.15, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Circle((0, 0), 0.22, color=LINE_COLOR, zorder=4))
    ax.add_patch(Rectangle((-20.16, PITCH_X_MIN), 40.32, 16.5, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Rectangle((-20.16, 36.0), 40.32, 16.5, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Rectangle((-9.16, PITCH_X_MIN), 18.32, 5.5, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Rectangle((-9.16, 47.0), 18.32, 5.5, fill=False, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Circle((0, -41.5), 0.22, color=LINE_COLOR, zorder=4))
    ax.add_patch(Circle((0, 41.5), 0.22, color=LINE_COLOR, zorder=4))
    ax.add_patch(Arc((0, -41.5), 18.3, 18.3, angle=0, theta1=40, theta2=140, lw=1.3, ec=ACCENT, zorder=4))
    ax.add_patch(Arc((0, 41.5), 18.3, 18.3, angle=0, theta1=220, theta2=320, lw=1.3, ec=ACCENT, zorder=4))
    ax.set_xlim(PITCH_Y_MIN - pad_x, PITCH_Y_MAX + pad_x)
    ax.set_ylim(PITCH_X_MIN - pad_bottom, PITCH_X_MAX + pad_top)
    ax.set_aspect("equal")
    ax.axis("off")


def _vswap(x: float, y: float) -> tuple[float, float]:
    # A plain transpose (y, x) would mirror left/right versus the horizontal
    # pitch (it's a reflection, not a rotation). Negate y so this is a true
    # 90-degree rotation and left/right stays consistent with render_pass_network.
    return -y, x


def _team_colors(bundle: dict[str, Any]) -> dict[int, str]:
    al_wasl_meta, rival_meta = _al_wasl_and_rival_meta(bundle)
    return {
        al_wasl_meta["id"]: AL_WASL_COLOR,
        rival_meta["id"]: RIVAL_COLOR,
    }


def _crest_array(crest_path: Path) -> Any:
    key = str(crest_path)
    if key in _CREST_CACHE:
        return _CREST_CACHE[key]
    try:
        img = PILImage.open(crest_path).convert("RGBA")
    except Exception:
        _CREST_CACHE[key] = None
        return None
    arr = np.asarray(img)
    _CREST_CACHE[key] = arr
    return arr


def _draw_crest_watermark(ax, bundle: dict[str, Any], squad_id: int | None, cx: float = 0.0, cy: float = 0.0, size: float = 58.0, alpha: float = 0.14) -> None:
    crest_path = ensure_crest_path(bundle, squad_id)
    if not crest_path:
        return
    arr = _crest_array(crest_path)
    if arr is None:
        return
    height, width = arr.shape[0], arr.shape[1]
    aspect = width / height if height else 1.0
    half_h = size / 2
    half_w = half_h * aspect
    faded = arr.astype(float).copy()
    faded[..., 3] = faded[..., 3] * alpha
    faded = faded / 255.0
    ax.imshow(
        faded,
        extent=(cx - half_w, cx + half_w, cy - half_h, cy + half_h),
        zorder=2.2,
        interpolation="bilinear",
    )


def _event_xy(event: dict[str, Any], adjusted: bool = True) -> tuple[float, float] | tuple[None, None]:
    start = event.get("start") or {}
    if adjusted:
        coords = start.get("adjCoordinates") or start.get("coordinates") or {}
    else:
        coords = start.get("coordinates") or start.get("adjCoordinates") or {}
    x, y = coords.get("x"), coords.get("y")
    if x is None or y is None:
        return None, None
    return float(x), float(y)


def _event_end_xy(event: dict[str, Any], adjusted: bool = True) -> tuple[float, float] | tuple[None, None]:
    end = event.get("end") or {}
    if adjusted:
        coords = end.get("adjCoordinates") or end.get("coordinates") or {}
    else:
        coords = end.get("coordinates") or end.get("adjCoordinates") or {}
    x, y = coords.get("x"), coords.get("y")
    if x is None or y is None:
        return None, None
    return float(x), float(y)


def _minute_label(event: dict[str, Any]) -> str:
    text = (event.get("gameTime") or {}).get("gameTime")
    if not text or ":" not in text:
        return "-"
    minute = text.split(":", 1)[0].lstrip("0") or "0"
    return f"{minute}'"


def _event_minute_int(event: dict[str, Any]) -> int | None:
    text = (event.get("gameTime") or {}).get("gameTime")
    if not text or ":" not in text:
        return None
    try:
        return int(text.split(":", 1)[0])
    except ValueError:
        return None


def _shot_outcome(event: dict[str, Any]) -> str:
    shot = event.get("shot") or {}
    if event.get("result") == "SUCCESS":
        return "Goal"
    if shot.get("woodwork"):
        return "Woodwork"
    target = shot.get("targetPoint") or {}
    y = target.get("y")
    z = target.get("z")
    in_goal_frame = y is not None and z is not None and abs(float(y)) <= 3.66 and 0.11 <= float(z) <= 2.44
    if in_goal_frame:
        return "On target"
    if event.get("distanceToOpponent") in {"LESS_THAN_ONE_METER", "ONE_METER"}:
        return "Blocked"
    return "Off target"


def _player_display_name_full(full_name: str) -> str:
    parts = full_name.split()
    if len(parts) <= 1:
        return full_name
    return f"{parts[0][0]}. {' '.join(parts[1:])}"


def _value_text(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def _safe_ratio(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _zone_bounds(cols: int = ZONE_COLS, rows: int = ZONE_ROWS):
    width = (PITCH_X_MAX - PITCH_X_MIN) / cols
    height = (PITCH_Y_MAX - PITCH_Y_MIN) / rows
    cells = []
    for col in range(cols):
        x0 = PITCH_X_MIN + col * width
        for row in range(rows):
            y0 = PITCH_Y_MIN + row * height
            cells.append({"col": col, "row": row, "x0": x0, "y0": y0})
    return cells, width, height


def _zone_index(x: float, y: float, cols: int = ZONE_COLS, rows: int = ZONE_ROWS) -> tuple[int, int]:
    width = (PITCH_X_MAX - PITCH_X_MIN) / cols
    height = (PITCH_Y_MAX - PITCH_Y_MIN) / rows
    col = min(cols - 1, max(0, int((x - PITCH_X_MIN) // width)))
    row = min(rows - 1, max(0, int((y - PITCH_Y_MIN) // height)))
    return col, row


def _zone_center(col: int, row: int, cols: int = ZONE_COLS, rows: int = ZONE_ROWS) -> tuple[float, float]:
    width = (PITCH_X_MAX - PITCH_X_MIN) / cols
    height = (PITCH_Y_MAX - PITCH_Y_MIN) / rows
    return PITCH_X_MIN + (col + 0.5) * width, PITCH_Y_MIN + (row + 0.5) * height


def _draw_zone_grid(ax, counts: dict[tuple[int, int], int], cmap, lang: str = "es") -> None:
    cells, width, height = _zone_bounds()
    max_count = max(counts.values(), default=0) or 1
    for cell in cells:
        key = (cell["col"], cell["row"])
        count = counts.get(key, 0)
        if count:
            color = cmap(count / max_count)
            ax.add_patch(Rectangle((cell["x0"], cell["y0"]), width, height, facecolor=color, alpha=0.82, lw=0, zorder=1))
            ax.text(cell["x0"] + width / 2, cell["y0"] + height / 2, str(count), ha="center", va="center", fontsize=12, fontweight="bold", color="white" if count / max_count > 0.35 else REPORT_INK, zorder=3)
        ax.add_patch(Rectangle((cell["x0"], cell["y0"]), width, height, fill=False, lw=0.7, ec="white", alpha=0.6, zorder=1.5))
    zc, zr = ZONE_14
    z_cell = next(c for c in cells if c["col"] == zc and c["row"] == zr)
    ax.add_patch(Rectangle((z_cell["x0"], z_cell["y0"]), width, height, fill=False, lw=2.6, ec=ZONE_HIGHLIGHT, zorder=5))
    ax.text(z_cell["x0"] + width / 2, z_cell["y0"] + height + 1.4, _t("ZONA 14", "ZONE 14", lang), ha="center", va="bottom", fontsize=8.5, fontweight="bold", color=ZONE_HIGHLIGHT, zorder=5)


def render_shot_map(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    home_meta, away_meta = _home_away_meta(bundle)
    colors = _team_colors(bundle)
    outcome_styles = {
        "Goal": {"marker": "*", "size": 380},
        "On target": {"marker": "o", "size": 190},
        "Woodwork": {"marker": "D", "size": 190},
        "Blocked": {"marker": "s", "size": 170},
        "Off target": {"marker": "x", "size": 210},
    }

    fig, axes = plt.subplots(2, 1, figsize=(11, 15.6), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    for ax, meta in ((axes[0], home_meta), (axes[1], away_meta)):
        _draw_pitch(ax, pad_bottom=6.5, pad_top=3.0)
        squad_id = meta["id"]
        color = colors.get(squad_id, "#475569")
        _draw_crest_watermark(ax, bundle, squad_id)
        lane_counts: Counter[str] = Counter()
        team_shots = 0
        for event in bundle.get("events", []):
            if not event.get("shot") or event.get("squadId") != squad_id:
                continue
            x, y = _event_xy(event, adjusted=False)
            if x is None:
                continue
            outcome = _shot_outcome(event)
            style = outcome_styles[outcome]
            kwargs: dict[str, Any] = {"s": style["size"], "marker": style["marker"], "linewidths": 1.6, "alpha": 0.95, "zorder": 6}
            if outcome == "Off target":
                kwargs["color"] = color
            else:
                kwargs["c"] = color
                kwargs["edgecolors"] = LINE_COLOR
            ax.scatter(x, y, **kwargs)
            ax.annotate(_minute_label(event), (x, y), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=7.5, fontweight="bold", color=REPORT_INK, zorder=7)
            lane = ((event.get("start") or {}).get("lane") or "SIN DATO").replace("_", " ").title()
            lane_counts[lane] += 1
            team_shots += 1
        ax.set_title(f"{meta['name']} — {_t(f'{team_shots} disparos', f'{team_shots} shots', lang)}", fontsize=15, fontweight="bold", color=color, pad=10)
        lane_text = "   |   ".join(f"{lane}: {count}" for lane, count in lane_counts.most_common())
        if lane_text:
            ax.text(0, PITCH_Y_MIN - 4.6, lane_text, ha="center", va="top", fontsize=9, color="#4B5563")

    legend_elements = [
        Line2D([0], [0], marker="*", color="w", label=_t("Gol", "Goal", lang), markerfacecolor="#94A3B8", markeredgecolor=LINE_COLOR, markersize=13),
        Line2D([0], [0], marker="o", color="w", label=_t("A puerta", "On target", lang), markerfacecolor="#94A3B8", markeredgecolor=LINE_COLOR, markersize=10),
        Line2D([0], [0], marker="D", color="w", label=_t("Al poste", "Woodwork", lang), markerfacecolor="#94A3B8", markeredgecolor=LINE_COLOR, markersize=9),
        Line2D([0], [0], marker="s", color="w", label=_t("Bloqueado", "Blocked", lang), markerfacecolor="#94A3B8", markeredgecolor=LINE_COLOR, markersize=9),
        Line2D([0], [0], marker="x", color=LINE_COLOR, label=_t("Fuera", "Off target", lang), markersize=10),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=5, frameon=False, fontsize=9.5, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(_t("Mapa de disparos por equipo (partido completo, ambas mitades)", "Shot map by team (full match, both halves)", lang), fontsize=17, fontweight="bold", color=LINE_COLOR)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.035, 1, 0.96])
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_pass_network(bundle: dict[str, Any], output_path: Path, squad_id: int, lang: str = "es") -> Path:
    fig, ax = _create_pitch_ax(figsize=(12, 9.2), pad_x=9.5, pad_bottom=6.5, pad_top=3.0)
    players_by_id = _players_by_id(bundle)
    squad_name = _squad_name(squad_id, bundle, f"Squad {squad_id}")
    team_color = _team_colors(bundle).get(squad_id, AL_WASL_COLOR)

    _draw_crest_watermark(ax, bundle, squad_id, size=62.0, alpha=0.13)

    all_positions: dict[int, list[tuple[float, float]]] = defaultdict(list)
    link_counter: Counter[tuple[int, int]] = Counter()
    threat_by_player: defaultdict[int, float] = defaultdict(float)
    touches: Counter[int] = Counter()
    roles: dict[int, str] = {}

    for event in bundle.get("events", []):
        if event.get("squadId") != squad_id:
            continue
        player = event.get("player") or {}
        player_id = player.get("id")
        x, y = _event_xy(event)
        if player_id and x is not None:
            touches[player_id] += 1
            all_positions[player_id].append((x, y))
            if player.get("position"):
                roles[player_id] = player["position"]
        # a receiving touch also contributes to the receiver's average position,
        # even though it isn't itself a squadId==squad_id event for the receiver
        if event.get("pass") and event.get("result") == "SUCCESS":
            receiver_meta = (event.get("pass") or {}).get("receiver") or {}
            if receiver_meta.get("type") == "TEAMMATE":
                receiver_id = receiver_meta.get("playerId")
                end_x, end_y = _event_end_xy(event)
                if receiver_id and end_x is not None:
                    all_positions[receiver_id].append((end_x, end_y))
        if not event.get("pass") or event.get("result") != "SUCCESS":
            continue
        receiver = (event.get("pass") or {}).get("receiver") or {}
        receiver_id = receiver.get("playerId")
        if not player_id or not receiver_id or receiver.get("type") != "TEAMMATE" or x is None:
            continue
        link_counter[tuple(sorted((player_id, receiver_id)))] += 1
        threat_by_player[player_id] += max(0.0, float(((event.get("pxT") or {}).get("team") or 0.0)))

    avg_pos: dict[int, tuple[float, float]] = {}
    for player_id, values in all_positions.items():
        xs = [v[0] for v in values]
        ys = [v[1] for v in values]
        avg_pos[player_id] = (median(xs), median(ys))

    visible_players = {pid for pid, count in touches.items() if count >= 8 and pid in avg_pos}
    if not visible_players:
        visible_players = set(avg_pos)

    outfield_positions = {
        pid: (median([v[0] for v in vals]), median([v[1] for v in vals]))
        for pid, vals in all_positions.items()
        if roles.get(pid) != "GOALKEEPER" and pid in visible_players
    }
    if len(outfield_positions) >= 4:
        xs_sorted = sorted(v[0] for v in outfield_positions.values())
        ys_all = [v[1] for v in outfield_positions.values()]
        back_line_x = median(xs_sorted[: max(3, len(xs_sorted) // 3)])
        front_line_x = median(xs_sorted[-max(2, len(xs_sorted) // 4):])
        width_top = max(ys_all)
        width_bottom = min(ys_all)

        arrow_y = PITCH_Y_MIN - 4.6
        ax.annotate("", xy=(front_line_x, arrow_y), xytext=(back_line_x, arrow_y), arrowprops={"arrowstyle": "<->", "color": REPORT_INK, "lw": 2.0})
        ax.text((front_line_x + back_line_x) / 2, arrow_y - 1.5, _t(f"Profundidad bloque: {front_line_x - back_line_x:.1f} m", f"Block depth: {front_line_x - back_line_x:.1f} m", lang), ha="center", va="top", fontsize=9, fontweight="bold", color=REPORT_INK)

        arrow_x = PITCH_X_MAX + 6.2
        ax.annotate("", xy=(arrow_x, width_top), xytext=(arrow_x, width_bottom), arrowprops={"arrowstyle": "<->", "color": REPORT_INK, "lw": 2.0})
        ax.text(arrow_x + 1.1, (width_top + width_bottom) / 2, _t(f"Amplitud: {width_top - width_bottom:.1f} m", f"Width: {width_top - width_bottom:.1f} m", lang), ha="left", va="center", fontsize=9, fontweight="bold", color=REPORT_INK, rotation=90)

    top_links = sorted(
        (
            (pair, count)
            for pair, count in link_counter.items()
            if count >= 5 and pair[0] in visible_players and pair[1] in visible_players
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:10]
    max_count = max((count for _, count in top_links), default=1)
    for (passer_id, receiver_id), count in top_links:
        x1, y1 = avg_pos[passer_id]
        x2, y2 = avg_pos[receiver_id]
        lw = 1.2 + (count / max_count) * 6.0
        ax.plot([x1, x2], [y1, y2], color=team_color, alpha=0.35 + 0.5 * (count / max_count), lw=lw, zorder=3, solid_capstyle="round")

    max_touches = max((touches[pid] for pid in visible_players), default=1)
    max_threat = max((threat_by_player[pid] for pid in visible_players), default=0.001)
    norm = Normalize(vmin=0, vmax=max_threat)
    for player_id in visible_players:
        if player_id not in avg_pos:
            continue
        x, y = avg_pos[player_id]
        size = 260 + 1100 * (touches[player_id] / max_touches)
        radius = (size ** 0.5) * 0.05
        color = THREAT_CMAP(norm(threat_by_player[player_id]))
        ax.scatter([x + radius * 0.14], [y - radius * 0.18], s=size * 1.05, color=REPORT_INK, alpha=0.16, zorder=4, linewidths=0)
        ax.scatter([x], [y], s=size, c=[color], edgecolors="white", linewidths=2.2, zorder=5)
        ax.scatter([x - radius * 0.22], [y + radius * 0.26], s=size * 0.22, color="white", alpha=0.45, zorder=5, linewidths=0)
        name = _player_display_name_full(_player_name(players_by_id.get(player_id), player_id))
        text = ax.text(
            x,
            y - radius - 1.3,
            name,
            ha="center",
            va="top",
            color=REPORT_INK,
            fontsize=8.5,
            fontweight="bold",
            zorder=6,
        )
        text.set_path_effects([path_effects.withStroke(linewidth=2.6, foreground="white")])

    ax.set_title(_t(f"Red de pases — {squad_name}", f"Pass network — {squad_name}", lang), fontsize=18, color=LINE_COLOR, pad=16, fontweight="bold")
    legend_handles = [
        Line2D([0], [0], color=team_color, lw=3, alpha=0.7, label=_t("Conexión de pase", "Pass connection", lang)),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#84CC16", markeredgecolor="white", markersize=10, label=_t("Tamaño = contactos", "Size = touches", lang)),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#ECFCCB", markeredgecolor="#94A3B8", markersize=10, label=_t("Amenaza baja", "Low threat", lang)),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#DC2626", markeredgecolor="#94A3B8", markersize=10, label=_t("Amenaza alta", "High threat", lang)),
    ]
    ax.legend(handles=legend_handles, loc="lower center", bbox_to_anchor=(0.5, -0.1), ncol=4, frameon=False, fontsize=8.5)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_threat_bar_chart(bundle: dict[str, Any], output_path: Path, squad_id: int, lang: str = "es") -> Path:
    players_by_id = _players_by_id(bundle)
    color = _team_colors(bundle).get(squad_id, AL_WASL_COLOR)
    squad_name = _squad_name(squad_id, bundle, f"Squad {squad_id}")
    threat_by_player: defaultdict[int, float] = defaultdict(float)
    for event in bundle.get("events", []):
        if event.get("squadId") != squad_id or not event.get("pass") or event.get("result") != "SUCCESS":
            continue
        player_id = (event.get("player") or {}).get("id")
        if not player_id:
            continue
        threat_by_player[player_id] += max(0.0, float(((event.get("pxT") or {}).get("team") or 0.0)))

    top = sorted(threat_by_player.items(), key=lambda item: item[1], reverse=True)[:8]
    labels = [_player_name(players_by_id.get(pid), pid) for pid, _ in top]
    values = [value for _, value in top]

    fig, ax = plt.subplots(figsize=(11, 4.4), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    ax.set_facecolor(REPORT_CREAM)
    ax.bar(range(len(labels)), values, color=color, width=0.6, zorder=3)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=22, ha="right", fontsize=9)
    ax.set_title(_t(f"Amenaza por jugador — {squad_name}", f"Threat by player — {squad_name}", lang), fontsize=13, fontweight="bold", color=LINE_COLOR)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.15, zorder=0)
    max_value = max(values or [1])
    for index, value in enumerate(values):
        ax.text(index, value + max_value * 0.03, f"{value:.2f}", ha="center", fontsize=8.5, fontweight="bold", color=REPORT_INK)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


PERIOD_BUCKETS = [
    ("0-10 mins", 1, 0, 10),
    ("10-20 mins", 1, 10, 20),
    ("20-30 mins", 1, 20, 30),
    ("30-40 mins", 1, 30, 40),
    ("40-End First Half", 1, 40, None),
    ("45-55 mins", 2, 0, 55),
    ("55-65 mins", 2, 55, 65),
    ("65-75 mins", 2, 65, 75),
    ("75-85 mins", 2, 75, 85),
    ("85-End Second Half", 2, 85, None),
]


def _period_bucket_label(period: int, minute: int) -> str | None:
    for label, bucket_period, lo, hi in PERIOD_BUCKETS:
        if period != bucket_period:
            continue
        if minute < lo:
            continue
        if hi is None or minute < hi:
            return label
    return None


def render_pass_distribution_by_period(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    home_meta, away_meta = _home_away_meta(bundle)
    colors = _team_colors(bundle)
    home_color = colors.get(home_meta["id"], AL_WASL_COLOR)
    away_color = colors.get(away_meta["id"], RIVAL_COLOR)

    counts: dict[str, dict[int, int]] = {home_meta["id"]: defaultdict(int), away_meta["id"]: defaultdict(int)}
    for event in bundle.get("events", []):
        if not event.get("pass") or event.get("result") != "SUCCESS":
            continue
        squad_id = event.get("squadId")
        if squad_id not in counts:
            continue
        minute = _event_minute_int(event)
        period = event.get("periodId") or 1
        if minute is None:
            continue
        label = _period_bucket_label(period, minute)
        if label is None:
            continue
        counts[squad_id][label] += 1

    labels = [label for label, *_ in PERIOD_BUCKETS]
    home_values = [counts[home_meta["id"]].get(label, 0) for label in labels]
    away_values = [counts[away_meta["id"]].get(label, 0) for label in labels]

    fig, ax = plt.subplots(figsize=(14, 6.2), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    ax.set_facecolor(REPORT_CREAM)
    x = np.arange(len(labels))
    width = 0.38
    bars_home = ax.bar(x - width / 2, home_values, width, color=home_color, label=home_meta["name"], zorder=3)
    bars_away = ax.bar(x + width / 2, away_values, width, color=away_color, label=away_meta["name"], zorder=3)
    for bars in (bars_home, bars_away):
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height + 0.6, str(int(height)), ha="center", fontsize=8, fontweight="bold", color=REPORT_INK)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=9)
    ax.set_ylabel(_t("Pases completados", "Completed passes", lang))
    ax.set_title(_t("Distribución de pases completados por períodos de 10 minutos", "Completed pass distribution by 10-minute period", lang), fontsize=16, fontweight="bold", color=LINE_COLOR)
    ax.legend(frameon=False, loc="upper center", ncol=2, fontsize=9.5, bbox_to_anchor=(0.5, 1.14))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.15, zorder=0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


POSITION_LINE = {
    "GOALKEEPER": 0,
    "CENTRAL_DEFENDER": 1,
    "LEFT_WINGBACK_DEFENDER": 1,
    "RIGHT_WINGBACK_DEFENDER": 1,
    "LEFT_BACK": 1,
    "RIGHT_BACK": 1,
    "DEFENSE_MIDFIELD": 2,
    "CENTRAL_MIDFIELD": 2,
    "LEFT_MIDFIELD": 2,
    "RIGHT_MIDFIELD": 2,
    "ATTACKING_MIDFIELD": 3,
    "LEFT_WINGER": 3,
    "RIGHT_WINGER": 3,
    "SECOND_STRIKER": 4,
    "CENTER_FORWARD": 4,
}
SIDE_ORDER = {"LEFT": 0, "CENTRE_LEFT": 1, "CENTRE": 2, "CENTRE_RIGHT": 3, "RIGHT": 4}
SIDE_Y = {"LEFT": 26.0, "CENTRE_LEFT": 9.0, "CENTRE": 0.0, "CENTRE_RIGHT": -9.0, "RIGHT": -26.0}
LINE_X = {0: -46.0, 1: -28.0, 2: -8.0, 3: 12.0, 4: 32.0}


def _lineup_positions(bundle: dict[str, Any], squad_id: int) -> tuple[list[dict[str, Any]], str]:
    match = bundle.get("match", {})
    squad_key = "squadHome" if (match.get("squadHome") or {}).get("id") == squad_id else "squadAway"
    squad_block = match.get(squad_key) or {}
    starting = squad_block.get("startingPositions", []) or []
    shirt_numbers = {p.get("id"): p.get("shirtNumber") for p in squad_block.get("players", [])}
    formation = squad_block.get("startingFormation") or "-"

    by_line: dict[int, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for entry in starting:
        line = POSITION_LINE.get(entry.get("position"), 2)
        side = SIDE_ORDER.get(entry.get("positionSide"), 2)
        by_line[line].append((side, entry))

    positions = []
    for line, entries in by_line.items():
        entries.sort(key=lambda item: item[0])
        x = LINE_X.get(line, 0.0)
        used_ys: list[float] = []
        for _side, entry in entries:
            y = SIDE_Y.get(entry.get("positionSide"), 0.0)
            while any(abs(y - other) < 4.0 for other in used_ys):
                y -= 6.0
            used_ys.append(y)
            player_id = entry.get("playerId")
            positions.append({"player_id": player_id, "x": x, "y": float(y), "shirt": shirt_numbers.get(player_id)})
    return positions, str(formation)


def render_lineup(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    home_meta, away_meta = _home_away_meta(bundle)
    colors = _team_colors(bundle)
    players_by_id = _players_by_id(bundle)
    fig, axes = plt.subplots(2, 1, figsize=(11, 14.8), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    for ax, meta in ((axes[0], home_meta), (axes[1], away_meta)):
        _draw_pitch(ax, pad_top=3.0, pad_bottom=3.0)
        color = colors.get(meta["id"], LINE_COLOR)
        _draw_crest_watermark(ax, bundle, meta["id"], alpha=0.13)
        positions, formation = _lineup_positions(bundle, meta["id"])
        for pos in positions:
            ax.scatter(pos["x"], pos["y"], s=620, color=color, edgecolors="white", linewidths=2.4, zorder=5)
            if pos["shirt"] is not None:
                ax.text(pos["x"], pos["y"], str(pos["shirt"]), ha="center", va="center", fontsize=10, fontweight="bold", color="white", zorder=6)
            name = _player_display_name_full(_player_name(players_by_id.get(pos["player_id"]), pos["player_id"]))
            text = ax.text(pos["x"], pos["y"] - 5.4, name, ha="center", va="top", fontsize=8, fontweight="bold", color=REPORT_INK, zorder=6)
            text.set_path_effects([path_effects.withStroke(linewidth=2.4, foreground="white")])
        ax.set_title(f"{meta['name']} — {formation}", fontsize=15, fontweight="bold", color=color, pad=10)
    fig.suptitle(_t("Alineaciones y sistema de juego", "Starting XI and formation", lang), fontsize=19, fontweight="bold", color=LINE_COLOR)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


PERIOD_WINDOWS_ES = [
    ("Min 0-23", 1, 0, 23),
    ("Min 23-45\n(Fin 1ª Parte)", 1, 23, None),
    ("Min 46-60\n(Inicio 2ª Parte)", 2, 0, 60),
    ("Min 60-75", 2, 60, 75),
    ("Min 75-90\n(Fin)", 2, 75, None),
]
PERIOD_WINDOWS_EN = [
    ("Min 0-23", 1, 0, 23),
    ("Min 23-45\n(End 1st Half)", 1, 23, None),
    ("Min 46-60\n(Start 2nd Half)", 2, 0, 60),
    ("Min 60-75", 2, 60, 75),
    ("Min 75-90\n(End)", 2, 75, None),
]


def _period_windows(lang: str) -> list[tuple[str, int, int, int | None]]:
    return PERIOD_WINDOWS_EN if lang == "en" else PERIOD_WINDOWS_ES


def _window_events(events: list[dict[str, Any]], period: int, lo: int, hi: int | None) -> list[dict[str, Any]]:
    result = []
    for event in events:
        if (event.get("periodId") or 1) != period:
            continue
        minute = _event_minute_int(event)
        if minute is None or minute < lo:
            continue
        if hi is not None and minute >= hi:
            continue
        result.append(event)
    return result


def _mini_network_data(
    events: list[dict[str, Any]], squad_id: int
) -> tuple[Counter[int], dict[int, tuple[float, float]], dict[int, float], Counter[tuple[int, int]]]:
    touches: Counter[int] = Counter()
    positions: dict[int, list[tuple[float, float]]] = defaultdict(list)
    threat: defaultdict[int, float] = defaultdict(float)
    links: Counter[tuple[int, int]] = Counter()
    for event in events:
        if event.get("squadId") != squad_id:
            continue
        player = event.get("player") or {}
        player_id = player.get("id")
        x, y = _event_xy(event)
        if player_id and x is not None:
            touches[player_id] += 1
            positions[player_id].append((x, y))
        if not event.get("pass") or event.get("result") != "SUCCESS":
            continue
        receiver = (event.get("pass") or {}).get("receiver") or {}
        receiver_id = receiver.get("playerId")
        if not player_id or not receiver_id or receiver.get("type") != "TEAMMATE" or x is None:
            continue
        end_x, end_y = _event_end_xy(event)
        if end_x is not None:
            positions[receiver_id].append((end_x, end_y))
        links[tuple(sorted((player_id, receiver_id)))] += 1
        threat[player_id] += max(0.0, float((event.get("pxT") or {}).get("team") or 0.0))
    avg_pos = {pid: (median([v[0] for v in vals]), median([v[1] for v in vals])) for pid, vals in positions.items()}
    return touches, avg_pos, threat, links


def _draw_crest_panel(ax, bundle: dict[str, Any], squad_id: int, squad_name: str, team_color: str) -> None:
    ax.set_xlim(-1, 1)
    ax.set_ylim(-1, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    crest_path = ensure_crest_path(bundle, squad_id)
    if crest_path:
        arr = _crest_array(crest_path)
        if arr is not None:
            height, width = arr.shape[0], arr.shape[1]
            aspect = width / height if height else 1.0
            half_h = 0.62
            half_w = half_h * aspect
            ax.imshow(arr, extent=(-half_w, half_w, -half_h + 0.12, half_h + 0.12), zorder=2)
    ax.text(0, -0.75, squad_name, ha="center", va="top", fontsize=9.5, fontweight="bold", color=team_color)


def _draw_lineup_header(ax, bundle: dict[str, Any], squad_id: int, players_by_id: dict[int, dict[str, Any]], team_color: str, lang: str = "es") -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    match = bundle.get("match", {})
    squad_key = "squadHome" if (match.get("squadHome") or {}).get("id") == squad_id else "squadAway"
    squad_block = match.get(squad_key) or {}
    starting = squad_block.get("startingPositions", []) or []
    shirt_numbers = {p.get("id"): p.get("shirtNumber") for p in squad_block.get("players", [])}
    formation = squad_block.get("startingFormation") or "-"

    ax.text(0.0, 0.92, formation, ha="left", va="top", fontsize=13, fontweight="bold", color=team_color)

    ordered = sorted(starting, key=lambda entry: (POSITION_LINE.get(entry.get("position"), 2), SIDE_ORDER.get(entry.get("positionSide"), 2)))
    columns = [ordered[:6], ordered[6:]]
    col_x = [0.0, 0.22]
    for entries, x0 in zip(columns, col_x):
        y = 0.68
        for entry in entries:
            player_id = entry.get("playerId")
            shirt = shirt_numbers.get(player_id)
            name = _player_name(players_by_id.get(player_id), player_id)
            ax.text(x0, y, f"{shirt if shirt is not None else '-'}", fontsize=8.5, fontweight="bold", color=team_color, va="top")
            ax.text(x0 + 0.045, y, name, fontsize=8.5, color=REPORT_INK, va="top")
            y -= 0.16

    subs = sorted(
        (s for s in squad_block.get("substitutions", []) or [] if s.get("substitutionType") == "SUB_ON"),
        key=lambda s: (s.get("gameTime") or {}).get("gameTimeInSec", 0),
    )
    if subs:
        sub_x = 0.46
        ax.text(sub_x, 0.92, _t("Cambios", "Substitutions", lang), fontsize=10, fontweight="bold", color=team_color, va="top")
        y = 0.68
        for sub in subs:
            in_id = sub.get("playerId")
            out_id = sub.get("exchangedPlayerId")
            minute = _minute_label({"gameTime": sub.get("gameTime")})
            in_name = _player_name(players_by_id.get(in_id), in_id)
            out_name = _player_name(players_by_id.get(out_id), out_id)
            ax.text(sub_x, y, f"{minute}  {out_name} → {in_name}", fontsize=8, color=REPORT_INK, va="top")
            y -= 0.16


def render_pass_network_period_page(bundle: dict[str, Any], output_path: Path, squad_id: int, lang: str = "es") -> Path:
    players_by_id = _players_by_id(bundle)
    squad_name = _squad_name(squad_id, bundle, f"Squad {squad_id}")
    team_color = _team_colors(bundle).get(squad_id, AL_WASL_COLOR)
    events_all = bundle.get("events", [])

    windows_data = []
    global_max_touch = 1
    global_max_threat = 0.001
    for label, period, lo, hi in _period_windows(lang):
        win_events = _window_events(events_all, period, lo, hi)
        touches, avg_pos, threat, links = _mini_network_data(win_events, squad_id)
        windows_data.append((label, touches, avg_pos, threat, links))
        if touches:
            global_max_touch = max(global_max_touch, max(touches.values()))
        if threat:
            global_max_threat = max(global_max_threat, max(threat.values()))

    fig = plt.figure(figsize=(12, 14.6), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    gs = fig.add_gridspec(3, 3, wspace=0.1, hspace=0.2, height_ratios=[0.32, 1, 1], top=0.94, bottom=0.02, left=0.02, right=0.98)

    crest_ax = fig.add_subplot(gs[0, 0])
    crest_ax.set_facecolor(REPORT_CREAM)
    _draw_crest_panel(crest_ax, bundle, squad_id, squad_name, team_color)

    info_ax = fig.add_subplot(gs[0, 1:])
    info_ax.set_facecolor(REPORT_CREAM)
    _draw_lineup_header(info_ax, bundle, squad_id, players_by_id, team_color, lang)

    grid_positions = [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1)]
    norm = Normalize(vmin=0, vmax=global_max_threat)
    for (row, col), (label, touches, avg_pos, threat, links) in zip(grid_positions, windows_data):
        ax = fig.add_subplot(gs[row, col])
        _draw_pitch_vertical(ax, pad_x=1.5, pad_top=6.5, pad_bottom=1.5)
        ax.set_title(label, fontsize=10.5, fontweight="bold", color=REPORT_INK, pad=6)

        visible = {pid for pid in touches if pid in avg_pos}
        top_links = sorted(
            ((pair, count) for pair, count in links.items() if count >= 2 and pair[0] in visible and pair[1] in visible),
            key=lambda item: item[1],
            reverse=True,
        )
        max_link = max((count for _, count in top_links), default=1)
        for (a, b), count in top_links:
            sx1, sy1 = _vswap(*avg_pos[a])
            sx2, sy2 = _vswap(*avg_pos[b])
            lw = 0.9 + (count / max_link) * 4.5
            ax.plot([sx1, sx2], [sy1, sy2], color=team_color, alpha=0.35 + 0.5 * (count / max_link), lw=lw, zorder=3)

        for player_id in visible:
            sx, sy = _vswap(*avg_pos[player_id])
            size = 70 + 360 * (touches[player_id] / global_max_touch)
            color = THREAT_CMAP(norm(threat.get(player_id, 0.0)))
            ax.scatter([sx], [sy], s=size, c=[color], edgecolors="white", linewidths=1.3, zorder=5)
            name = _player_display_name_full(_player_name(players_by_id.get(player_id), player_id))
            text = ax.text(sx, sy - (size ** 0.5) * 0.11 - 1.4, name, ha="center", va="top", fontsize=6.4, fontweight="bold", color=REPORT_INK, zorder=6)
            text.set_path_effects([path_effects.withStroke(linewidth=1.6, foreground="white")])

    legend_ax = fig.add_subplot(gs[2, 2])
    legend_ax.set_facecolor(REPORT_CREAM)
    legend_ax.axis("off")
    legend_handles = [
        Line2D([0], [0], color=team_color, lw=3, alpha=0.7, label=_t("Conexión de pase", "Pass connection", lang)),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#84CC16", markeredgecolor="white", markersize=10, label=_t("Tamaño = contactos", "Size = touches", lang)),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#DC2626", markeredgecolor="#94A3B8", markersize=10, label=_t("Color = amenaza", "Color = threat", lang)),
    ]
    legend_ax.legend(handles=legend_handles, loc="center", frameon=False, fontsize=9)

    fig.suptitle(_t(f"Red de pases por tramos — {squad_name}", f"Pass network by phase — {squad_name}", lang), fontsize=17, fontweight="bold", color=team_color, y=0.975)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _pass_zone_counts(bundle: dict[str, Any], squad_id: int) -> dict[tuple[int, int], int]:
    counts: Counter[tuple[int, int]] = Counter()
    for event in bundle.get("events", []):
        if event.get("squadId") != squad_id or not event.get("pass") or event.get("result") != "SUCCESS":
            continue
        x, y = _event_xy(event)
        if x is None:
            continue
        counts[_zone_index(x, y)] += 1
    return counts


def render_pass_zone_heatmap(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    al_wasl_meta, rival_meta = _al_wasl_and_rival_meta(bundle)
    colors = _team_colors(bundle)
    fig, axes = plt.subplots(2, 1, figsize=(11, 13.4), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    panels = ((axes[0], al_wasl_meta, AL_WASL_ZONE_CMAP), (axes[1], rival_meta, RIVAL_ZONE_CMAP))
    for ax, meta, cmap in panels:
        _draw_pitch(ax, pad_top=4.0)
        _draw_crest_watermark(ax, bundle, meta["id"], alpha=0.16)
        counts = _pass_zone_counts(bundle, meta["id"])
        _draw_zone_grid(ax, counts, cmap, lang)
        ax.set_title(meta["name"], fontsize=16, fontweight="bold", color=colors.get(meta["id"], LINE_COLOR), pad=10)
    fig.suptitle(_t("Construcción: zonas de pase completado", "Build-up: completed pass zones", lang), fontsize=19, fontweight="bold", color=LINE_COLOR)
    fig.text(
        0.5,
        0.01,
        _t(
            "Ambos equipos siempre atacan hacia la derecha del gráfico. La Zona 14 (recuadro azul) es el espacio previo al área rival.",
            "Both teams always attack towards the right of the chart. Zone 14 (blue box) is the space just outside the opponent's box.",
            lang,
        ),
        ha="center",
        fontsize=9.5,
        color="#4B5563",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.025, 1, 0.95])
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _zone14_flow_counts(bundle: dict[str, Any], squad_id: int) -> tuple[Counter[tuple[int, int]], Counter[tuple[int, int]]]:
    incoming: Counter[tuple[int, int]] = Counter()
    outgoing: Counter[tuple[int, int]] = Counter()
    for event in bundle.get("events", []):
        if event.get("squadId") != squad_id or not event.get("pass") or event.get("result") != "SUCCESS":
            continue
        sx, sy = _event_xy(event)
        ex, ey = _event_end_xy(event)
        if sx is None or ex is None:
            continue
        start_zone = _zone_index(sx, sy)
        end_zone = _zone_index(ex, ey)
        if start_zone == ZONE_14 and end_zone != ZONE_14:
            outgoing[end_zone] += 1
        elif end_zone == ZONE_14 and start_zone != ZONE_14:
            incoming[start_zone] += 1
    return incoming, outgoing


def zone14_top_players(bundle: dict[str, Any], squad_id: int) -> tuple[tuple[str, int] | None, tuple[str, int] | None]:
    players_by_id = _players_by_id(bundle)
    passers: Counter[int] = Counter()
    receivers: Counter[int] = Counter()
    for event in bundle.get("events", []):
        if event.get("squadId") != squad_id or not event.get("pass") or event.get("result") != "SUCCESS":
            continue
        sx, sy = _event_xy(event)
        ex, ey = _event_end_xy(event)
        if sx is None or ex is None:
            continue
        if _zone_index(sx, sy) == ZONE_14 or _zone_index(ex, ey) != ZONE_14:
            continue
        passer_id = (event.get("player") or {}).get("id")
        receiver_id = ((event.get("pass") or {}).get("receiver") or {}).get("playerId")
        if passer_id:
            passers[passer_id] += 1
        if receiver_id:
            receivers[receiver_id] += 1

    top_passer = max(passers.items(), key=lambda item: item[1]) if passers else None
    top_receiver = max(receivers.items(), key=lambda item: item[1]) if receivers else None
    passer_row = (_player_name(players_by_id.get(top_passer[0]), top_passer[0]), top_passer[1]) if top_passer else None
    receiver_row = (_player_name(players_by_id.get(top_receiver[0]), top_receiver[0]), top_receiver[1]) if top_receiver else None
    return passer_row, receiver_row


def render_zone14_flow(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    home_meta, away_meta = _home_away_meta(bundle)
    colors = _team_colors(bundle)
    fig, axes = plt.subplots(2, 2, figsize=(13, 13.6), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    cells, cell_w, cell_h = _zone_bounds()
    zc, zr = ZONE_14

    for row_idx, meta in enumerate((home_meta, away_meta)):
        color = colors.get(meta["id"], LINE_COLOR)
        incoming, outgoing = _zone14_flow_counts(bundle, meta["id"])
        for col_idx, (flows, direction) in enumerate(((incoming, "in"), (outgoing, "out"))):
            ax = axes[row_idx][col_idx]
            _draw_pitch(ax, pad_top=3.0, pad_bottom=3.0)
            _draw_crest_watermark(ax, bundle, meta["id"], alpha=0.13)
            for cell in cells:
                ax.add_patch(Rectangle((cell["x0"], cell["y0"]), cell_w, cell_h, fill=False, lw=0.5, ec="#CBD5E1", zorder=1.5))
            z_cell = next(c for c in cells if c["col"] == zc and c["row"] == zr)
            ax.add_patch(Rectangle((z_cell["x0"], z_cell["y0"]), cell_w, cell_h, fill=False, lw=2.4, ec=ZONE_HIGHLIGHT, zorder=5))
            zone14_center = _zone_center(zc, zr)
            max_count = max(flows.values(), default=0) or 1
            for arrow_index, (zone_key, count) in enumerate(sorted(flows.items())):
                center = _zone_center(*zone_key)
                lw = 1.6 + (count / max_count) * 8.0
                start_pt, end_pt = (center, zone14_center) if direction == "in" else (zone14_center, center)
                rad = 0.12 if arrow_index % 2 == 0 else -0.12
                arrow = FancyArrowPatch(
                    start_pt,
                    end_pt,
                    connectionstyle=f"arc3,rad={rad}",
                    arrowstyle="-|>",
                    mutation_scale=16,
                    linewidth=lw,
                    color=color,
                    alpha=0.78,
                    zorder=4,
                )
                ax.add_patch(arrow)
                ax.text(
                    center[0],
                    center[1],
                    str(count),
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color="white",
                    zorder=6,
                    bbox={"boxstyle": "circle,pad=0.3", "fc": color, "ec": "white", "lw": 1.2},
                )
            direction_label = _t("Entradas a Zona 14", "Entries into Zone 14", lang) if direction == "in" else _t("Salidas de Zona 14", "Exits from Zone 14", lang)
            ax.set_title(f"{meta['name']} — {direction_label}", fontsize=12, fontweight="bold", color=color, pad=8)

    fig.suptitle(_t("Zona 14: quién la alimenta y hacia dónde distribuye", "Zone 14: who feeds it and where it distributes to", lang), fontsize=18, fontweight="bold", color=LINE_COLOR)
    fig.text(
        0.5,
        0.008,
        _t(
            "El número junto a cada zona es la cantidad de pases entre esa zona y la Zona 14. El grosor de la flecha crece con ese mismo número (más grosor = más pases).",
            "The number next to each zone is the number of passes between that zone and Zone 14. Arrow thickness grows with that same number (thicker = more passes).",
            lang,
        ),
        ha="center",
        fontsize=9,
        color="#4B5563",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _sequence_map(events: list[dict[str, Any]]) -> dict[Any, list[dict[str, Any]]]:
    sequences: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        sequences[event.get("sequenceIndex")].append(event)
    return sequences


def _interceptions_to_shot(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    events = bundle.get("events", [])
    sequences = _sequence_map(events)
    players_by_id = _players_by_id(bundle)
    rows = []
    for seq_events in sequences.values():
        seq_sorted = sorted(seq_events, key=lambda e: e.get("index", 0))
        for interception in seq_sorted:
            if interception.get("action") != "INTERCEPTION":
                continue
            squad_id = interception.get("squadId")
            later = [
                e
                for e in seq_sorted
                if e.get("index", -1) > interception.get("index", -1) and e.get("squadId") == squad_id
            ]
            shot = next((e for e in later if e.get("shot")), None)
            if not shot:
                continue
            ix, iy = _event_xy(interception, adjusted=False)
            sx, sy = _event_xy(shot, adjusted=False)
            if ix is None or sx is None:
                continue
            player_id = (interception.get("player") or {}).get("id")
            rows.append(
                {
                    "squad_id": squad_id,
                    "period": interception.get("periodId") or 1,
                    "ix": ix,
                    "iy": iy,
                    "sx": sx,
                    "sy": sy,
                    "minute": _minute_label(interception),
                    "player": _player_name(players_by_id.get(player_id), player_id),
                    "is_goal": shot.get("result") == "SUCCESS",
                }
            )
    return rows


def render_transitions_map(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    home_meta, away_meta = _home_away_meta(bundle)
    colors = _team_colors(bundle)
    rows = _interceptions_to_shot(bundle)
    fig, axes = plt.subplots(2, 2, figsize=(16, 15.6), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    for col_idx, meta in enumerate((home_meta, away_meta)):
        color = colors.get(meta["id"], "#475569")
        for row_idx, period in enumerate((1, 2)):
            ax = axes[row_idx][col_idx]
            _draw_pitch(ax, pad_top=3.0)
            _draw_crest_watermark(ax, bundle, meta["id"])
            team_rows = [r for r in rows if r["squad_id"] == meta["id"] and r["period"] == period]
            for row in team_rows:
                marker = "*" if row["is_goal"] else "o"
                size = 380 if row["is_goal"] else 190
                ax.annotate(
                    "",
                    xy=(row["sx"], row["sy"]),
                    xytext=(row["ix"], row["iy"]),
                    arrowprops={"arrowstyle": "-|>", "color": color, "lw": 1.6, "alpha": 0.75},
                    zorder=4,
                )
                ax.scatter(row["ix"], row["iy"], s=90, marker="o", facecolor="white", edgecolors=color, linewidths=1.6, zorder=5)
                ax.scatter(row["sx"], row["sy"], s=size, marker=marker, color=color, edgecolors=LINE_COLOR, linewidths=1.3, zorder=6)
                ax.annotate(
                    f"{row['player']} ({row['minute']})",
                    (row["ix"], row["iy"]),
                    textcoords="offset points",
                    xytext=(0, 9),
                    ha="center",
                    fontsize=7.5,
                    fontweight="bold",
                    color=REPORT_INK,
                    zorder=7,
                )
            if not team_rows:
                ax.text(0, 0, _t("Sin recuperaciones\nque generen remate", "No recoveries\nleading to a shot", lang), ha="center", va="center", fontsize=12, fontweight="bold", color="#94A3B8")
            half_label = _t("1ª parte", "1st half", lang) if period == 1 else _t("2ª parte", "2nd half", lang)
            ax.set_title(f"{meta['name']} — {half_label} ({len(team_rows)})", fontsize=12.5, fontweight="bold", color=color, pad=8)

    legend = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white", markeredgecolor=LINE_COLOR, markersize=9, label=_t("Recuperación", "Recovery", lang)),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#94A3B8", markeredgecolor=LINE_COLOR, markersize=9, label=_t("Remate", "Shot", lang)),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#94A3B8", markeredgecolor=LINE_COLOR, markersize=13, label=_t("Gol", "Goal", lang)),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=3, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(_t("Transiciones: de la recuperación al remate, por parte del partido", "Transitions: from recovery to shot, by half", lang), fontsize=18, fontweight="bold", color=LINE_COLOR)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.04, 1, 0.95])
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _cross_outcome(event: dict[str, Any], sequences: dict[Any, list[dict[str, Any]]]) -> str:
    if event.get("result") != "SUCCESS":
        return "incomplete"
    seq = sequences.get(event.get("sequenceIndex"), [])
    idx = event.get("index")
    later = [e for e in seq if e.get("index", -1) > idx]
    shot = next((e for e in later if e.get("shot")), None)
    if shot and shot.get("result") == "SUCCESS":
        return "goal"
    if shot:
        return "shot"
    return "completed"


def _cross_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    events = bundle.get("events", [])
    sequences = _sequence_map(events)
    rows = []
    for event in events:
        if event.get("action") not in CROSS_ACTIONS:
            continue
        x, y = _event_xy(event, adjusted=False)
        ex, ey = _event_end_xy(event, adjusted=False)
        if x is None:
            continue
        rows.append(
            {
                "squad_id": event.get("squadId"),
                "x": x,
                "y": y,
                "ex": ex if ex is not None else x,
                "ey": ey if ey is not None else y,
                "outcome": _cross_outcome(event, sequences),
                "minute": _minute_label(event),
            }
        )
    return rows


def render_cross_map(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    home_meta, away_meta = _home_away_meta(bundle)
    colors = _team_colors(bundle)
    rows = _cross_rows(bundle)
    fig, axes = plt.subplots(2, 1, figsize=(11, 15.0), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    for ax, meta in ((axes[0], home_meta), (axes[1], away_meta)):
        _draw_pitch(ax, pad_top=3.5)
        team_color = colors.get(meta["id"], LINE_COLOR)
        _draw_crest_watermark(ax, bundle, meta["id"])
        team_rows = [row for row in rows if row["squad_id"] == meta["id"]]
        outcome_counts: Counter[str] = Counter()
        for row in team_rows:
            style = CROSS_OUTCOME_STYLE[row["outcome"]]
            ax.annotate(
                "",
                xy=(row["ex"], row["ey"]),
                xytext=(row["x"], row["y"]),
                arrowprops={"arrowstyle": "-|>", "color": style["color"], "lw": 1.3, "alpha": 0.55},
                zorder=4,
            )
            ax.scatter(row["x"], row["y"], s=55, marker="o", color=REPORT_INK, alpha=0.65, zorder=4.5, linewidths=0)
            kwargs: dict[str, Any] = {"s": style["size"], "marker": style["marker"], "linewidths": 1.4, "alpha": 0.92, "zorder": 5}
            if style["marker"] == "x":
                kwargs["color"] = style["color"]
            else:
                kwargs["c"] = style["color"]
                kwargs["edgecolors"] = LINE_COLOR
            ax.scatter(row["ex"], row["ey"], **kwargs)
            outcome_counts[row["outcome"]] += 1
        ax.set_title(f"{meta['name']} ({len(team_rows)})", fontsize=14, fontweight="bold", color=team_color, pad=10)
        summary_text = "   ".join(f"{CROSS_OUTCOME_LABELS[label][lang if lang == 'en' else 'es']}: {outcome_counts.get(label, 0)}" for label in CROSS_OUTCOME_STYLE)
        ax.text(
            0,
            2.4,
            summary_text,
            ha="center",
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color=REPORT_INK,
            zorder=7,
            bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": team_color, "lw": 1.1, "alpha": 0.92},
        )
    legend = [
        Line2D([0], [0], marker=style["marker"], color="w", markerfacecolor=style["color"], markeredgecolor=LINE_COLOR, markersize=10, label=CROSS_OUTCOME_LABELS[label][lang if lang == "en" else "es"])
        for label, style in CROSS_OUTCOME_STYLE.items()
    ]
    fig.legend(handles=legend, loc="lower center", ncol=4, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(_t("Centros laterales: origen, destino y resultado", "Crosses: origin, destination and outcome", lang), fontsize=18, fontweight="bold", color=LINE_COLOR)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.035, 1, 0.95])
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_set_piece_chart(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    from .report import _set_piece_summary

    home_meta, away_meta = _home_away_meta(bundle)
    colors = _team_colors(bundle)
    home_color = colors.get(home_meta["id"], AL_WASL_COLOR)
    away_color = colors.get(away_meta["id"], RIVAL_COLOR)
    rows = _set_piece_summary(bundle)
    grouped: defaultdict[str, dict[str, float]] = defaultdict(lambda: {"home": 0, "away": 0, "home_goals": 0.0, "away_goals": 0.0})
    for row in rows:
        if row["team"] == home_meta["name"]:
            grouped[row["category"]]["home"] += row["count"]
            grouped[row["category"]]["home_goals"] += row["goals"]
        elif row["team"] == away_meta["name"]:
            grouped[row["category"]]["away"] += row["count"]
            grouped[row["category"]]["away_goals"] += row["goals"]

    categories = sorted(grouped.keys(), key=lambda c: -(grouped[c]["home"] + grouped[c]["away"]))[:8]
    if not categories:
        categories = ["SIN DATOS"]
        grouped["SIN DATOS"] = {"home": 0, "away": 0, "home_goals": 0.0, "away_goals": 0.0}

    fig, ax = plt.subplots(figsize=(12, max(5, 0.85 * len(categories) + 2)), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    ax.set_facecolor(REPORT_CREAM)
    max_value = max((max(grouped[c]["home"], grouped[c]["away"]) for c in categories), default=1) or 1

    for index, category in enumerate(categories):
        y = len(categories) - index - 1
        home_value = grouped[category]["home"]
        away_value = grouped[category]["away"]
        ax.barh(y, -home_value, height=0.55, color=home_color, zorder=2)
        ax.barh(y, away_value, height=0.55, color=away_color, zorder=2)
        ax.text(0, y, category.replace("_", " ").title(), ha="center", va="center", fontsize=10, fontweight="bold", color=REPORT_INK, bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": "#E5E7EB"}, zorder=3)
        ax.text(-home_value - max_value * 0.05, y, f"{home_value:.0f}", ha="right", va="center", fontsize=10, fontweight="bold", color=REPORT_INK)
        ax.text(away_value + max_value * 0.05, y, f"{away_value:.0f}", ha="left", va="center", fontsize=10, fontweight="bold", color=REPORT_INK)

    ax.set_xlim(-max_value * 1.4, max_value * 1.4)
    ax.set_ylim(-0.6, len(categories) - 0.4)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(-max_value * 1.25, len(categories) - 0.1, home_meta["name"], ha="left", fontsize=12, fontweight="bold", color=home_color)
    ax.text(max_value * 1.25, len(categories) - 0.1, away_meta["name"], ha="right", fontsize=12, fontweight="bold", color=away_color)
    ax.set_title(_t("Balón parado por tipo de acción", "Set pieces by action type", lang), fontsize=18, color=LINE_COLOR, fontweight="bold", pad=24)

    home_goals = sum(grouped[c]["home_goals"] for c in grouped)
    away_goals = sum(grouped[c]["away_goals"] for c in grouped)
    fig.text(0.5, 0.015, f"{_t('Goles de ABP', 'Set-piece goals', lang)} — {home_meta['name']}: {home_goals:.0f}    |    {away_meta['name']}: {away_goals:.0f}", ha="center", fontsize=10, fontweight="bold", color=REPORT_INK)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.07, 1, 0.9])
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_match_dashboard(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    from .report import _compare_squad_kpis, _compare_squad_scores, _event_team_summary

    home_meta, away_meta = _home_away_meta(bundle)
    colors = _team_colors(bundle)
    home_color = colors.get(home_meta["id"], AL_WASL_COLOR)
    away_color = colors.get(away_meta["id"], RIVAL_COLOR)
    summary = {row["team"]: row for row in _event_team_summary(bundle)}
    score_lookup = {row["metric_name"]: row for row in _compare_squad_scores(bundle)}
    kpi_lookup = {row["metric_name"]: row for row in _compare_squad_kpis(bundle)}

    home_name = home_meta["name"]
    away_name = away_meta["name"]
    home_summary = summary.get(home_name, {})
    away_summary = summary.get(away_name, {})

    percent_metrics = {"Possession", "Pass Accuracy", "Field Tilt"}

    metrics = [
        ("Possession", score_lookup.get("RATIO_BALL_POSSESSION", {}).get("home"), score_lookup.get("RATIO_BALL_POSSESSION", {}).get("away")),
        ("Passes", home_summary.get("passes"), away_summary.get("passes")),
        ("Pass Accuracy", home_summary.get("pass_accuracy"), away_summary.get("pass_accuracy")),
        ("pxT+", score_lookup.get("PXT_POSITIVE", {}).get("home"), score_lookup.get("PXT_POSITIVE", {}).get("away")),
        ("Field Tilt", score_lookup.get("FIELD_TILT", {}).get("home"), score_lookup.get("FIELD_TILT", {}).get("away")),
        ("Shot xG", kpi_lookup.get("SHOT_XG", {}).get("home"), kpi_lookup.get("SHOT_XG", {}).get("away")),
        ("Packing xG", kpi_lookup.get("PACKING_XG", {}).get("home"), kpi_lookup.get("PACKING_XG", {}).get("away")),
        ("Goals", home_summary.get("goals"), away_summary.get("goals")),
        ("Shots", home_summary.get("shots"), away_summary.get("shots")),
    ]

    def format_value(label: str, value: Any) -> str:
        if value is None:
            return "-"
        if label in percent_metrics:
            return f"{float(value) * 100:.0f}%"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    fig, ax = plt.subplots(figsize=(12, 8.5), dpi=180)
    fig.patch.set_facecolor(REPORT_CREAM)
    ax.set_facecolor(REPORT_CREAM)

    bar_left, bar_right = -1.0, 1.0
    ax.text(bar_left - 0.05, len(metrics) + 0.5, home_name, ha="left", va="bottom", fontsize=14, fontweight="bold", color=home_color)
    ax.text(bar_right + 0.05, len(metrics) + 0.5, away_name, ha="right", va="bottom", fontsize=14, fontweight="bold", color=away_color)

    for index, (label, home_value, away_value) in enumerate(metrics):
        y = len(metrics) - index - 0.2
        home_ratio = _safe_ratio(home_value)
        away_ratio = _safe_ratio(away_value)
        total = home_ratio + away_ratio
        share = home_ratio / total if total > 0 else 0.5
        split = bar_left + (bar_right - bar_left) * share

        ax.barh(y, split - bar_left, left=bar_left, height=0.55, color=home_color, alpha=0.92, zorder=2)
        ax.barh(y, bar_right - split, left=split, height=0.55, color=away_color, alpha=0.88, zorder=2)
        ax.plot([(bar_left + bar_right) / 2] * 2, [y - 0.28, y + 0.28], color=REPORT_INK, lw=1.6, zorder=4)
        ax.text((bar_left + bar_right) / 2, y + 0.42, label.upper(), ha="center", va="bottom", fontsize=9.5, fontweight="bold", color=REPORT_INK)
        ax.text(bar_left + 0.03, y, format_value(label, home_value), ha="left", va="center", fontsize=10, fontweight="bold", color="white", zorder=5)
        ax.text(bar_right - 0.03, y, format_value(label, away_value), ha="right", va="center", fontsize=10, fontweight="bold", color="white", zorder=5)

    ax.set_xlim(bar_left - 0.15, bar_right + 0.15)
    ax.set_ylim(0.2, len(metrics) + 1.0)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("Match Dashboard", fontsize=22, color=LINE_COLOR, pad=18, fontweight="bold")
    ax.text(
        (bar_left + bar_right) / 2,
        len(metrics) + 0.85,
        _t(
            "Reparto proporcional entre ambos equipos por métrica — la marca central señala el 50%",
            "Proportional split between both teams per metric — the tick marks the 50% point",
            lang,
        ),
        ha="center",
        va="bottom",
        fontsize=10,
        color="#4B5563",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _smooth(series: list[float], window: int = 4) -> list[float]:
    result = []
    n = len(series)
    for i in range(n):
        lo = max(0, i - window)
        hi = min(n, i + window + 1)
        result.append(sum(series[lo:hi]) / (hi - lo))
    return result


def render_momentum_and_xg(bundle: dict[str, Any], output_path: Path, lang: str = "es") -> Path:
    al_wasl_meta, rival_meta = _al_wasl_and_rival_meta(bundle)
    shot_xg = _event_shot_xg_map(bundle)
    players_by_id = _players_by_id(bundle)

    events = bundle.get("events", [])
    minutes = [m for m in (_event_minute_int(e) for e in events) if m is not None]
    max_minute = max(minutes, default=90) + 1

    pxt_by_minute = {al_wasl_meta["id"]: [0.0] * (max_minute + 1), rival_meta["id"]: [0.0] * (max_minute + 1)}
    xg_by_minute = {al_wasl_meta["id"]: [0.0] * (max_minute + 1), rival_meta["id"]: [0.0] * (max_minute + 1)}
    goals = []

    for event in events:
        minute = _event_minute_int(event)
        if minute is None or minute > max_minute:
            continue
        squad_id = event.get("squadId")
        if squad_id not in pxt_by_minute:
            continue
        pxt_value = float((event.get("pxT") or {}).get("team") or 0.0)
        if pxt_value > 0:
            pxt_by_minute[squad_id][minute] += pxt_value
        if event.get("shot"):
            xg_value = shot_xg.get(event.get("id"), 0.0)
            xg_by_minute[squad_id][minute] += xg_value
            if event.get("result") == "SUCCESS":
                player_id = (event.get("player") or {}).get("id")
                goals.append(
                    {
                        "minute": minute,
                        "squad_id": squad_id,
                        "player": _player_name(players_by_id.get(player_id), player_id),
                    }
                )

    x = list(range(max_minute + 1))
    al_wasl_smooth = _smooth(_smooth(pxt_by_minute[al_wasl_meta["id"]], 4), 2)
    rival_smooth = _smooth(_smooth(pxt_by_minute[rival_meta["id"]], 4), 2)
    net = [al_wasl_smooth[i] - rival_smooth[i] for i in x]

    al_wasl_pxt_cum, rival_pxt_cum = [], []
    al_wasl_cum, rival_cum = [], []
    running_al_pxt, running_rival_pxt = 0.0, 0.0
    running_al, running_rival = 0.0, 0.0
    for i in x:
        running_al_pxt += pxt_by_minute[al_wasl_meta["id"]][i]
        running_rival_pxt += pxt_by_minute[rival_meta["id"]][i]
        al_wasl_pxt_cum.append(running_al_pxt)
        rival_pxt_cum.append(running_rival_pxt)
        running_al += xg_by_minute[al_wasl_meta["id"]][i]
        running_rival += xg_by_minute[rival_meta["id"]][i]
        al_wasl_cum.append(running_al)
        rival_cum.append(running_rival)

    fig, (ax_momentum, ax_pxt, ax_xg) = plt.subplots(
        3, 1, figsize=(12, 15.5), dpi=180, sharex=True, gridspec_kw={"height_ratios": [1.1, 0.9, 1.0]}
    )
    fig.patch.set_facecolor(REPORT_CREAM)
    for ax in (ax_momentum, ax_pxt, ax_xg):
        ax.set_facecolor(REPORT_CREAM)

    ax_momentum.axhline(0, color=REPORT_INK, lw=1.0)
    ax_momentum.fill_between(x, net, 0, where=[v >= 0 for v in net], color=AL_WASL_COLOR, alpha=0.82, interpolate=True)
    ax_momentum.fill_between(x, net, 0, where=[v < 0 for v in net], color=RIVAL_COLOR, alpha=0.82, interpolate=True)
    ax_momentum.set_title("xT Momentum", fontsize=17, fontweight="bold", color=LINE_COLOR, loc="left")
    ax_momentum.set_ylabel(_t("Amenaza neta\n(pxT suavizado)", "Net threat\n(smoothed pxT)", lang))
    ax_momentum.spines["top"].set_visible(False)
    ax_momentum.spines["right"].set_visible(False)
    ax_momentum.grid(axis="y", alpha=0.15)

    ax_pxt.plot(x, al_wasl_pxt_cum, color=AL_WASL_COLOR, lw=2.8)
    ax_pxt.plot(x, rival_pxt_cum, color=RIVAL_COLOR, lw=2.8)
    ax_pxt.set_title(_t("pxT acumulado (dominio territorial)", "Cumulative pxT (territorial dominance)", lang), fontsize=15, fontweight="bold", color=LINE_COLOR, loc="left")
    ax_pxt.set_ylabel(_t("pxT acumulado", "Cumulative pxT", lang))
    ax_pxt.spines["top"].set_visible(False)
    ax_pxt.spines["right"].set_visible(False)
    ax_pxt.grid(axis="y", alpha=0.15)

    ax_xg.plot(x, al_wasl_cum, color=AL_WASL_COLOR, lw=2.8, label=al_wasl_meta["name"])
    ax_xg.plot(x, rival_cum, color=RIVAL_COLOR, lw=2.8, label=rival_meta["name"])
    ax_xg.set_title(_t("xG acumulado", "Cumulative xG", lang), fontsize=17, fontweight="bold", color=LINE_COLOR, loc="left")
    ax_xg.set_xlabel(_t("Minuto", "Minute", lang))
    ax_xg.set_ylabel(_t("xG acumulado", "Cumulative xG", lang))
    ax_xg.legend(frameon=False, loc="upper left", fontsize=9.5)
    ax_xg.spines["top"].set_visible(False)
    ax_xg.spines["right"].set_visible(False)
    ax_xg.grid(axis="y", alpha=0.15)

    momentum_top = max([abs(v) for v in net], default=0.1) * 1.18 or 0.1
    ax_momentum.set_ylim(-momentum_top, momentum_top)

    goals_sorted = sorted(goals, key=lambda g: g["minute"])
    for goal in goals_sorted:
        color = AL_WASL_COLOR if goal["squad_id"] == al_wasl_meta["id"] else RIVAL_COLOR
        minute = min(goal["minute"], max_minute)
        for ax in (ax_momentum, ax_pxt, ax_xg):
            ax.axvline(minute, color=color, lw=1.4, ls="--", alpha=0.85, zorder=1)
        cum_value = al_wasl_cum[minute] if goal["squad_id"] == al_wasl_meta["id"] else rival_cum[minute]
        ax_xg.scatter([minute], [cum_value], marker="*", s=260, color=color, edgecolors=LINE_COLOR, zorder=5)
        ax_momentum.scatter([minute], [momentum_top * 0.92], marker="*", s=170, color=color, edgecolors=LINE_COLOR, linewidths=1.0, zorder=5, clip_on=False)

    for ax in (ax_momentum, ax_pxt, ax_xg):
        ax.set_xlim(0, max_minute)

    if goals_sorted:
        caption = _t("Goles:  ", "Goals:  ", lang) + "   ·   ".join(
            f"{goal['minute']}' {goal['player']} ({al_wasl_meta['name'] if goal['squad_id'] == al_wasl_meta['id'] else rival_meta['name']})"
            for goal in goals_sorted
        )
        fig.text(0.5, 0.008, caption, ha="center", fontsize=9, color=REPORT_INK, fontweight="bold")

    fig.suptitle(_t(f"{al_wasl_meta['name']} vs {rival_meta['name']} — evolución del partido", f"{al_wasl_meta['name']} vs {rival_meta['name']} — match evolution", lang), fontsize=14, color="#4B5563")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path
