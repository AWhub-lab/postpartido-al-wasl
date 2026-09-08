from __future__ import annotations

import base64
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parent
SRC = APP_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

from postmatch_impect.client import ImpectClient
from postmatch_impect.config import ROOT, Settings
from postmatch_impect.pdf_report import render_pdf_report

AL_WASL_LOGO = APP_ROOT / "assets" / "al_wasl_logo.png"
AL_WASL_SQUAD_ID = 2033

GOLD = "#D4A017"
GOLD_LIGHT = "#F8E7A1"
INK = "#111827"
INK_SOFT = "#1F2937"
CREAM = "#FFF9EB"
BORDER = "#E5D7AE"

st.set_page_config(
    page_title="Al-Wasl Postpartido",
    page_icon=str(AL_WASL_LOGO) if AL_WASL_LOGO.exists() else "⚽",
    layout="wide",
)

# --------------------------------------------------------------------------
# i18n — platform UI only (Spanish / English / Arabic). Report PDFs keep
# their own separate Spanish/English toggle, unrelated to this one.
# --------------------------------------------------------------------------

UI_TEXT: dict[str, dict[str, str]] = {
    "app_title": {"es": "Postpartido Al-Wasl", "en": "Al-Wasl Post-Match", "ar": "ما بعد مباراة الوصل"},
    "app_subtitle": {
        "es": "Panel de informes postpartido",
        "en": "Post-match report dashboard",
        "ar": "لوحة تقارير ما بعد المباراة",
    },
    "login_username": {"es": "Usuario", "en": "Username", "ar": "اسم المستخدم"},
    "login_password": {"es": "Contraseña", "en": "Password", "ar": "كلمة المرور"},
    "login_button": {"es": "Entrar", "en": "Sign in", "ar": "دخول"},
    "login_missing_secrets": {
        "es": "Faltan APP_USERNAME / APP_PASSWORD en los secrets de la app.",
        "en": "APP_USERNAME / APP_PASSWORD are missing from the app secrets.",
        "ar": "لا يوجد APP_USERNAME / APP_PASSWORD في أسرار التطبيق.",
    },
    "login_wrong": {
        "es": "Usuario o contraseña incorrectos.",
        "en": "Incorrect username or password.",
        "ar": "اسم المستخدم أو كلمة المرور غير صحيحة.",
    },
    "report_lang_label": {"es": "Idioma del informe", "en": "Report language", "ar": "لغة التقرير"},
    "refresh_button": {"es": "Refrescar partidos", "en": "Refresh matches", "ar": "تحديث المباريات"},
    "season_label": {"es": "Temporada", "en": "Season", "ar": "الموسم"},
    "all_seasons": {"es": "Todas las temporadas", "en": "All seasons", "ar": "كل المواسم"},
    "matches_found": {
        "es": "{n} partidos encontrados. Los datos se refrescan solos cada 30 minutos, o pulsa “Refrescar”.",
        "en": "{n} matches found. Data refreshes automatically every 30 minutes, or press “Refresh”.",
        "ar": "تم العثور على {n} مباراة. يتم تحديث البيانات تلقائياً كل 30 دقيقة، أو اضغط “تحديث”.",
    },
    "no_matches": {
        "es": "No se encontraron partidos del Al-Wasl.",
        "en": "No Al-Wasl matches were found.",
        "ar": "لم يتم العثور على مباريات للوصل.",
    },
    "col_date": {"es": "Fecha", "en": "Date", "ar": "التاريخ"},
    "col_competition": {"es": "Competición", "en": "Competition", "ar": "البطولة"},
    "col_rival": {"es": "Rival", "en": "Opponent", "ar": "الخصم"},
    "col_venue": {"es": "Local/Fuera", "en": "Home/Away", "ar": "الملعب"},
    "col_result": {"es": "Resultado", "en": "Result", "ar": "النتيجة"},
    "col_wdl": {"es": "V/E/D", "en": "W/D/L", "ar": "ف/ت/خ"},
    "col_report": {"es": "Informe", "en": "Report", "ar": "التقرير"},
    "venue_home": {"es": "Casa", "en": "Home", "ar": "الديار"},
    "venue_away": {"es": "Fuera", "en": "Away", "ar": "خارج الديار"},
    "result_caption": {
        "es": "El resultado entre paréntesis corresponde al marcador al descanso.",
        "en": "The score in parentheses is the half-time score.",
        "ar": "النتيجة بين قوسين هي نتيجة الشوط الأول.",
    },
    "pending": {"es": "Pendiente", "en": "Pending", "ar": "قيد الانتظار"},
    "download_button": {"es": "Descargar", "en": "Download", "ar": "تنزيل"},
    "generate_button": {"es": "Generar informe", "en": "Generate report", "ar": "إنشاء التقرير"},
    "generating_spinner": {
        "es": "Descargando datos y generando el PDF...",
        "en": "Downloading data and generating the PDF...",
        "ar": "جارٍ تنزيل البيانات وإنشاء ملف PDF...",
    },
    "generate_error": {
        "es": "No se pudo generar el informe: {error}",
        "en": "Could not generate the report: {error}",
        "ar": "تعذر إنشاء التقرير: {error}",
    },
    "win": {"es": "Victoria", "en": "Win", "ar": "فوز"},
    "draw": {"es": "Empate", "en": "Draw", "ar": "تعادل"},
    "loss": {"es": "Derrota", "en": "Loss", "ar": "خسارة"},
}

LANG_PILL_LABELS = {"es": "ES", "en": "EN", "ar": "AR"}


def t(key: str) -> str:
    lang = st.session_state.get("ui_lang", "es")
    return UI_TEXT.get(key, {}).get(lang, UI_TEXT.get(key, {}).get("es", key))


# --------------------------------------------------------------------------
# Visual theme — brand colors, texture, card styling.
# --------------------------------------------------------------------------


def _inject_theme() -> None:
    is_rtl = st.session_state.get("ui_lang") == "ar"
    direction_css = "direction: rtl; text-align: right;" if is_rtl else ""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
                radial-gradient(circle at 1px 1px, rgba(212,160,23,0.10) 1px, transparent 0) 0 0/22px 22px,
                {CREAM};
        }}
        .block-container {{ padding-top: 3.2rem; {direction_css} }}

        /* Language switcher — slim pill row, top-right */
        .lang-switch-row div[data-testid="stSegmentedControl"] {{
            justify-content: {"flex-start" if is_rtl else "flex-end"};
        }}
        .lang-switch-row div[role="radiogroup"] {{
            gap: 0.15rem !important;
        }}
        .lang-switch-row label {{
            min-height: 1.6rem !important;
            padding: 0.15rem 0.65rem !important;
        }}
        .lang-switch-row label p {{
            font-size: 0.72rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.4px;
        }}

        /* Hero header */
        .hero {{
            position: relative;
            overflow: hidden;
            border-radius: 20px;
            padding: 2.1rem 2.2rem;
            margin-bottom: 1.3rem;
            background: linear-gradient(135deg, {INK} 0%, {INK_SOFT} 45%, {GOLD} 130%);
            box-shadow: 0 14px 34px rgba(17,24,39,0.28);
            display: flex;
            align-items: center;
            gap: 1.6rem;
        }}
        .hero::before {{
            content: "";
            position: absolute;
            inset: 0;
            background-image: repeating-linear-gradient(45deg, rgba(255,255,255,0.05) 0px, rgba(255,255,255,0.05) 2px, transparent 2px, transparent 16px);
            pointer-events: none;
        }}
        .hero::after {{
            content: "";
            position: absolute;
            right: -60px; top: -60px;
            width: 220px; height: 220px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(248,231,161,0.35), transparent 70%);
            pointer-events: none;
        }}
        .hero-logo {{
            width: 88px; height: 88px; object-fit: contain;
            filter: drop-shadow(0 6px 12px rgba(0,0,0,0.45));
            position: relative; z-index: 1; flex-shrink: 0;
        }}
        .hero-text {{ position: relative; z-index: 1; }}
        .hero-text h1 {{
            color: {CREAM}; font-size: 2.15rem; margin: 0;
            font-weight: 800; letter-spacing: 0.3px; line-height: 1.15;
        }}
        .hero-text p {{
            color: {GOLD_LIGHT}; margin: 0.35rem 0 0 0; font-size: 1.02rem; font-weight: 500;
        }}

        /* Table header bar */
        .table-header {{
            display: grid;
            gap: 0.6rem;
            background: linear-gradient(90deg, {GOLD}, #B8860B);
            color: white;
            padding: 0.7rem 1.1rem;
            border-radius: 12px;
            margin-bottom: 0.55rem;
            font-weight: 700;
            text-transform: uppercase;
            font-size: 0.76rem;
            letter-spacing: 0.5px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.14);
        }}

        /* Card rows (bordered containers) */
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 14px !important;
            border: 1px solid {BORDER} !important;
            border-{"right" if is_rtl else "left"}: 5px solid {GOLD} !important;
            box-shadow: 0 2px 8px rgba(17,24,39,0.06);
            transition: box-shadow .15s ease, transform .15s ease;
            margin-bottom: 0.55rem;
            background: #FFFFFF;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
            box-shadow: 0 8px 20px rgba(17,24,39,0.14);
            transform: translateY(-1px);
        }}

        /* Primary buttons (Entrar, Refrescar) */
        button[kind="primary"] {{
            background-color: {GOLD} !important;
            border-color: {GOLD} !important;
            color: {INK} !important;
            font-weight: 700 !important;
        }}
        button[kind="primary"]:hover {{
            background-color: #B8860B !important;
            border-color: #B8860B !important;
        }}

        /* WDL badges */
        .wdl-badge {{
            display: inline-block;
            padding: 0.22rem 0.65rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 700;
            color: white;
            letter-spacing: 0.3px;
        }}
        .wdl-win {{ background: #16A34A; }}
        .wdl-draw {{ background: #64748B; }}
        .wdl-loss {{ background: #DC2626; }}
        .wdl-none {{ color: {INK}; opacity: 0.35; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _b64_logo() -> str:
    if not AL_WASL_LOGO.exists():
        return ""
    return base64.b64encode(AL_WASL_LOGO.read_bytes()).decode("utf-8")


def _render_hero() -> None:
    logo_b64 = _b64_logo()
    logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="hero-logo" />' if logo_b64 else ""
    st.markdown(
        f"""
        <div class="hero">
            {logo_html}
            <div class="hero-text">
                <h1>{t('app_title')}</h1>
                <p>{t('app_subtitle')}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_language_switcher() -> None:
    codes = ["es", "en", "ar"]
    current = st.session_state.get("ui_lang", "es")
    st.session_state.setdefault("ui_lang_pill", LANG_PILL_LABELS[current])

    st.markdown('<div class="lang-switch-row">', unsafe_allow_html=True)
    _, right = st.columns([5, 2])
    with right:
        choice = st.segmented_control(
            "platform language",
            [LANG_PILL_LABELS[c] for c in codes],
            key="ui_lang_pill",
            label_visibility="collapsed",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    label_to_code = {v: k for k, v in LANG_PILL_LABELS.items()}
    new_code = label_to_code.get(choice, "es")
    if new_code != current:
        st.session_state["ui_lang"] = new_code
        st.rerun()


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------


def _check_login() -> bool:
    if st.session_state.get("authenticated"):
        return True

    _render_language_switcher()
    _render_hero()

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("login_form", border=True):
            username = st.text_input(t("login_username"))
            password = st.text_input(t("login_password"), type="password")
            submitted = st.form_submit_button(t("login_button"), type="primary", use_container_width=True)
        if submitted:
            expected_user = st.secrets.get("APP_USERNAME")
            expected_pass = st.secrets.get("APP_PASSWORD")
            if not expected_user or not expected_pass:
                st.error(t("login_missing_secrets"))
            elif username == expected_user and password == expected_pass:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error(t("login_wrong"))
    return False


def _settings_from_secrets() -> Settings:
    return Settings(
        impect_user=st.secrets["IMPECT_USER"],
        impect_pass=st.secrets["IMPECT_PASS"],
    )


@st.cache_resource(show_spinner=False)
def _get_client() -> ImpectClient:
    return ImpectClient(_settings_from_secrets())


def _squad_name(squads_by_id: dict[int, dict[str, Any]], squad_id: int | None, fallback: str) -> str:
    squad = squads_by_id.get(squad_id) if squad_id is not None else None
    if not squad:
        return fallback
    for key in ("name", "shortName", "commonname"):
        value = squad.get(key)
        if value:
            return str(value)
    return fallback


def _result_text(row: dict[str, Any]) -> str:
    result = row.get("result")
    if result:
        return str(result)
    goals = row.get("goals") or {}
    home_ft = (goals.get("home") or {}).get("fullTime")
    away_ft = (goals.get("away") or {}).get("fullTime")
    if home_ft is not None and away_ft is not None:
        return f"{home_ft}-{away_ft}"
    return "-"


def _wdl_outcome(row: dict[str, Any]) -> str | None:
    if not row.get("available"):
        return None
    goals = row.get("goals") or {}
    home_ft = (goals.get("home") or {}).get("fullTime")
    away_ft = (goals.get("away") or {}).get("fullTime")
    if home_ft is None or away_ft is None:
        return None
    is_home = row.get("homeSquadId") == AL_WASL_SQUAD_ID
    al_wasl_goals = home_ft if is_home else away_ft
    rival_goals = away_ft if is_home else home_ft
    if al_wasl_goals > rival_goals:
        return "win"
    if al_wasl_goals < rival_goals:
        return "loss"
    return "draw"


def _wdl_badge_html(outcome: str | None) -> str:
    if outcome is None:
        return '<span class="wdl-badge wdl-none">-</span>'
    return f'<span class="wdl-badge wdl-{outcome}">{t(outcome)}</span>'


def _fetch_iteration_matches(client: ImpectClient, iteration: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    iteration_id = iteration.get("id")
    if iteration_id is None:
        return iteration, []
    try:
        matches = client.get_matches(iteration_id)
    except Exception:
        return iteration, []
    hits = [m for m in matches if m.get("homeSquadId") == AL_WASL_SQUAD_ID or m.get("awaySquadId") == AL_WASL_SQUAD_ID]
    return iteration, hits


@st.cache_data(ttl=1800, show_spinner=False)
def _load_al_wasl_matches(_cache_key: int) -> list[dict[str, Any]]:
    client = _get_client()
    iterations = client.get_iterations()

    # The account has access to hundreds of competitions worldwide; Al-Wasl only
    # plays in a handful of them, but we don't know which ahead of time, so every
    # iteration's match list must be checked. Fetching them concurrently turns a
    # ~1-2 minute sequential scan into a few seconds. Kept modest (not higher) to
    # avoid CPU throttling on Streamlit Community Cloud's free-tier containers.
    hits_by_iteration: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_iteration_matches, client, iteration) for iteration in iterations]
        for future in as_completed(futures):
            iteration, hits = future.result()
            if hits:
                hits_by_iteration.append((iteration, hits))

    rows: list[dict[str, Any]] = []
    for iteration, hits in hits_by_iteration:
        iteration_id = iteration.get("id")
        try:
            squads = client.get_squads(iteration_id)
        except Exception:
            squads = []
        squads_by_id = {s.get("id"): s for s in squads if s.get("id") is not None}
        competition_name = ((iteration.get("competition") or {}).get("name")) or "-"
        season = iteration.get("season") or "-"
        for row in hits:
            enriched = dict(row)
            enriched["_iteration_id"] = iteration_id
            enriched["_competition"] = competition_name
            enriched["_season"] = season
            enriched["_home_name"] = _squad_name(squads_by_id, row.get("homeSquadId"), "Home")
            enriched["_away_name"] = _squad_name(squads_by_id, row.get("awaySquadId"), "Away")
            rows.append(enriched)
    rows.sort(key=lambda r: r.get("scheduledDate") or r.get("date") or "", reverse=True)
    return rows


def _season_sort_key(season: str) -> int:
    match = re.search(r"(\d{2,4})", season or "")
    if not match:
        return -1
    year = int(match.group(1))
    return year + 2000 if year < 100 else year


def _sorted_seasons(matches: list[dict[str, Any]]) -> list[str]:
    seasons = {row.get("_season") or "-" for row in matches}
    return sorted(seasons, key=_season_sort_key, reverse=True)


def _report_path(match_id: int, lang: str) -> Path:
    suffix = "" if lang == "es" else f"_{lang}"
    return ROOT / "reports" / f"match_{match_id}_report{suffix}.pdf"


def _generate_report(match_id: int, lang: str) -> Path:
    client = _get_client()
    bundle = client.get_match_bundle(match_id)
    return render_pdf_report(match_id, bundle, lang)


ROW_RATIOS = [1.1, 1.5, 1.9, 0.85, 0.85, 0.75, 1.5]


def main() -> None:
    st.session_state.setdefault("ui_lang", "es")
    _inject_theme()

    if not _check_login():
        return

    _render_language_switcher()
    _render_hero()

    matches = _load_al_wasl_matches(st.session_state.get("refresh_token", 0))

    top_left, top_right = st.columns([3, 1])
    with top_left:
        report_lang_label = st.segmented_control(
            t("report_lang_label"),
            ["Español", "English"],
            default="Español",
            key="report_lang_choice",
        )
        lang = "en" if report_lang_label == "English" else "es"
    with top_right:
        st.write("")
        if st.button(f"🔄 {t('refresh_button')}", type="primary", use_container_width=True):
            _load_al_wasl_matches.clear()
            st.session_state["refresh_token"] = st.session_state.get("refresh_token", 0) + 1
            st.rerun()

    if not matches:
        st.warning(t("no_matches"))
        return

    seasons = _sorted_seasons(matches)
    season_options = [t("all_seasons")] + seasons
    default_season = seasons[0] if seasons else t("all_seasons")
    selected_season = st.selectbox(
        t("season_label"),
        season_options,
        index=season_options.index(default_season),
    )
    if selected_season != t("all_seasons"):
        matches = [row for row in matches if (row.get("_season") or "-") == selected_season]

    st.caption(t("matches_found").format(n=len(matches)))
    st.caption(f"ℹ️ {t('result_caption')}")

    header_labels = [t("col_date"), t("col_competition"), t("col_rival"), t("col_venue"), t("col_result"), t("col_wdl"), t("col_report")]
    grid_css = " ".join(f"{r}fr" for r in ROW_RATIOS)
    header_cells = "".join(f'<div>{label}</div>' for label in header_labels)
    st.markdown(f'<div class="table-header" style="grid-template-columns:{grid_css}">{header_cells}</div>', unsafe_allow_html=True)

    for row in matches:
        match_id = row.get("id")
        is_home = row.get("homeSquadId") == AL_WASL_SQUAD_ID
        rival = row.get("_away_name") if is_home else row.get("_home_name")
        venue = t("venue_home") if is_home else t("venue_away")
        date_text = str(row.get("scheduledDate") or row.get("date") or "?")[:10]
        available = bool(row.get("available"))
        result = _result_text(row) if available else "-"
        outcome = _wdl_outcome(row)

        with st.container(border=True):
            cols = st.columns(ROW_RATIOS)
            cols[0].write(date_text)
            cols[1].write(f"{row.get('_competition')}  \n:gray[{row.get('_season')}]")
            cols[2].write(rival)
            cols[3].write(venue)
            cols[4].write(result)
            cols[5].markdown(_wdl_badge_html(outcome), unsafe_allow_html=True)

            with cols[6]:
                if not available:
                    st.caption(f"⏳ {t('pending')}")
                    continue
                report_path = _report_path(match_id, lang)
                if report_path.exists():
                    with open(report_path, "rb") as fh:
                        st.download_button(
                            f"📄 {t('download_button')}",
                            data=fh.read(),
                            file_name=report_path.name,
                            mime="application/pdf",
                            key=f"dl_{match_id}_{lang}",
                        )
                else:
                    if st.button(t("generate_button"), key=f"gen_{match_id}_{lang}"):
                        with st.spinner(t("generating_spinner")):
                            try:
                                _generate_report(match_id, lang)
                            except Exception as exc:
                                st.error(t("generate_error").format(error=exc))
                            else:
                                st.rerun()


if __name__ == "__main__":
    main()
