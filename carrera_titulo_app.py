"""Stand-alone app: «Carrera por el título» (Al Wasl · UAE Pro League).

Two modes, chosen automatically:
- Local (your computer): IMPECT credentials available and no Drive folder configured →
  «Actualizar después de la jornada» button; data are read/written in data/.
- Shared (Streamlit Cloud): Drive folder configured, no IMPECT credentials → read-only;
  data come from the Google Drive package (see README, «App independiente»).

Secrets:
    TITLE_APP_USERNAME / TITLE_APP_PASSWORD   (fallback: APP_USERNAME / APP_PASSWORD)
    TITLE_RACE_DRIVE_FOLDER_ID                 Drive folder with carrera_titulo_datos.zip
    [gcp_service_account]                      service-account JSON (read-only access to that folder)
"""
from __future__ import annotations

import base64
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))

import streamlit as st  # noqa: E402

st.set_page_config(page_title='Road to the title · Al Wasl', page_icon='🏆', layout='wide')

from postmatch_impect import i18n  # noqa: E402

i18n.install()

from postmatch_impect.title_race_data import sync_from_drive  # noqa: E402
from postmatch_impect.title_race_ui import render_title_race  # noqa: E402


def _secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:   # no secrets file locally
        return default


def _logo():
    p = ROOT/'assets'/'al_wasl_logo.png'
    return f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" style="width:64px">' if p.exists() else ''


def top_bar():
    _, right = st.columns([6, 1])
    i18n.language_selector(right)


def login() -> bool:
    if st.session_state.get('tr_auth'):
        return True
    user = _secret('TITLE_APP_USERNAME') or _secret('APP_USERNAME')
    pwd = _secret('TITLE_APP_PASSWORD') or _secret('APP_PASSWORD')
    st.markdown(f'<div style="text-align:center;margin:40px 0 10px">{_logo()}<h2 style="margin:8px 0 0">Carrera por el título</h2>'
                '<p style="color:#5B6576">Al Wasl · Football Intelligence</p></div>', unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        with st.form('tr_login', border=True):
            u = st.text_input('Usuario')
            p = st.text_input('Contraseña', type='password')
            ok = st.form_submit_button('Entrar', type='primary', width='stretch')
        if ok:
            if not user or not pwd:
                st.error('Faltan TITLE_APP_USERNAME / TITLE_APP_PASSWORD en los secretos.')
            elif u == user and p == pwd:
                st.session_state['tr_auth'] = True
                st.rerun()
            else:
                st.error('Usuario o contraseña incorrectos.')
    return False


@st.cache_resource(ttl=600, show_spinner=False)
def load_data(_stamp: int):
    """Sync data from Drive (at most every 10 minutes). Without Drive secrets, use local data/."""
    folder = _secret('TITLE_RACE_DRIVE_FOLDER_ID')
    sa = _secret('gcp_service_account')
    if not folder or not sa:
        return {'source': 'local'}
    return {'source': 'drive', **sync_from_drive(ROOT, dict(sa), folder)}


top_bar()
if login():
    try:
        with st.spinner(i18n.tr('Cargando datos…')):
            info = load_data(int(datetime.now().timestamp() // 600))
    except Exception as exc:
        st.error(f'No se pudieron descargar los datos de Google Drive: {exc}')
        info = {'source': 'error'}
    note = None
    if info.get('built_at'):
        note = f"Datos preparados el {datetime.fromisoformat(info['built_at']).strftime('%d/%m/%Y %H:%M')} (UTC)."
    client_factory = None
    if info.get('source') == 'local' and (_secret('IMPECT_USER') or os.getenv('IMPECT_USER')):
        # Local admin mode: same IMPECT client as the post-match app (credentials from secrets or .env).
        from postmatch_impect.client import ImpectClient
        from postmatch_impect.config import Settings, get_settings

        @st.cache_resource(show_spinner=False)
        def client_factory():
            if _secret('IMPECT_USER'):
                return ImpectClient(Settings(impect_user=_secret('IMPECT_USER'), impect_pass=_secret('IMPECT_PASS')))
            return ImpectClient(get_settings())
    render_title_race(ROOT, client_factory, note)
