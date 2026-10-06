"""English / Spanish for the «Carrera por el título» app.

The pages are written in Spanish. In English mode every text Streamlit renders (markdown/HTML,
widget labels and options, tabs, captions, dataframes and Altair charts) goes through `tr()`,
which swaps Spanish phrases for their English version (dictionary in i18n_en.json; longest
phrases first, whole words only). Numbers and calculations are never touched.

    from postmatch_impect import i18n
    i18n.install()            # once, before rendering
    i18n.language_selector()  # EN / ES control (default: English)
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

import streamlit as st

DEFAULT = 'en'
KEY = 'tr_lang'
_EN = json.loads((Path(__file__).with_name('i18n_en.json')).read_text(encoding='utf-8'))
_LETTER = 'A-Za-zÀ-ÿ'


def _pattern(key):
    p = re.escape(key)
    if re.match(f'[{_LETTER}]', key):
        p = f'(?<![{_LETTER}])' + p
    if re.search(f'[{_LETTER}]$', key):
        p = p + f'(?![{_LETTER}])'
    return p


_RX = re.compile('|'.join(_pattern(k) for k in sorted(_EN, key=len, reverse=True)))
_PROTECT = re.compile(r'data:[^"\'\s)]+|<style>.*?</style>', re.S)   # images and CSS are never translated
_ORD = re.compile(r'(\d+)º')


def lang() -> str:
    return st.session_state.get(KEY, DEFAULT)


def _ordinal(m):
    n = int(m.group(1))
    suffix = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'


def tr(text):
    """Translate a rendered string to the active language (identity in Spanish)."""
    if lang() != 'en' or not isinstance(text, str) or not text:
        return text
    kept = []

    def keep(m):
        kept.append(m.group(0))
        return f'\x00{len(kept)-1}\x00'
    out = _PROTECT.sub(keep, text)
    out = _RX.sub(lambda m: _EN[m.group(0)], out)
    out = _ORD.sub(_ordinal, out)
    return re.sub(r'\x00(\d+)\x00', lambda m: kept[int(m.group(1))], out)


def t(es, en):
    """Explicit pair for the few texts that are easier to write twice."""
    return en if lang() == 'en' else es


def _deep(obj):
    """Translate every string (dict keys included) consistently: field names, data values and titles."""
    if isinstance(obj, str):
        return obj if obj.startswith(('data:', 'http')) else tr(obj)
    if isinstance(obj, list):
        return [_deep(x) for x in obj]
    if isinstance(obj, dict):
        return {_deep(k) if isinstance(k, str) else k: _deep(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------- Streamlit integration

_LABEL_FIRST = ['button', 'download_button', 'segmented_control', 'selectbox', 'select_slider', 'toggle', 'checkbox',
                'radio', 'multiselect', 'expander', 'text_input', 'file_uploader', 'form_submit_button', 'status',
                'caption', 'info', 'warning', 'error', 'success', 'markdown', 'metric', 'spinner']
_WITH_OPTIONS = {'segmented_control', 'selectbox', 'select_slider', 'radio', 'multiselect'}


def _translate_call(name, args, kwargs):
    args = list(args)
    if name == 'tabs' and args and isinstance(args[0], (list, tuple)):
        args[0] = [tr(x) for x in args[0]]
    elif name in _LABEL_FIRST and args and isinstance(args[0], str):
        args[0] = tr(args[0])
    for k in ('label', 'body', 'help', 'placeholder', 'text'):
        if isinstance(kwargs.get(k), str):
            kwargs[k] = tr(kwargs[k])
    if name in _WITH_OPTIONS:            # translate what is shown, keep the values the code compares
        fmt = kwargs.get('format_func')
        kwargs['format_func'] = (lambda x, f=fmt: tr(str(f(x)))) if fmt else (lambda x: tr(str(x)))
    if name == 'dataframe' and args and hasattr(args[0], 'rename'):
        df = args[0].copy()
        df.columns = [tr(str(c)) for c in df.columns]
        for c in df.columns:
            if df[c].dtype == object:
                df[c] = df[c].map(lambda v: tr(v) if isinstance(v, str) else v)
        args[0] = df
    return args, kwargs


def install():
    """Patch Streamlit's element methods once so their texts follow the selected language."""
    from streamlit.delta_generator import DeltaGenerator as DG
    if getattr(DG, '_tr_installed', False):
        return
    names = _LABEL_FIRST + ['tabs', 'dataframe']
    for name in names:
        orig = getattr(DG, name, None)
        if orig is None:
            continue

        @functools.wraps(orig)
        def method(self, *args, __orig=orig, __name=name, **kwargs):
            if lang() == 'en':
                args, kwargs = _translate_call(__name, args, kwargs)
            return __orig(self, *args, **kwargs)
        setattr(DG, name, method)
        module_fn = getattr(st, name, None)
        if module_fn is not None and name != 'spinner':
            @functools.wraps(module_fn)
            def fn(*args, __fn=module_fn, __name=name, **kwargs):
                if lang() == 'en':
                    args, kwargs = _translate_call(__name, args, kwargs)
                return __fn(*args, **kwargs)
            setattr(st, name, fn)

    orig_chart = DG.altair_chart

    @functools.wraps(orig_chart)
    def altair_chart(self, chart, **kwargs):
        if lang() != 'en':
            return orig_chart(self, chart, **kwargs)
        return DG.vega_lite_chart(self, spec=_deep(chart.to_dict()), **kwargs)
    DG.altair_chart = altair_chart
    st.altair_chart = lambda chart, **kw: altair_chart(st._main, chart, **kw)
    DG._tr_installed = True


def language_selector(container=None):
    """EN / ES control, English by default. Keeps the choice for the whole session."""
    if KEY not in st.session_state:
        st.session_state[KEY] = DEFAULT
    box = container or st
    choice = box.segmented_control('Language', ['EN', 'ES'], default=st.session_state[KEY].upper(),
                                   key='tr_lang_widget', label_visibility='collapsed')
    if choice and choice.lower() != st.session_state[KEY]:
        st.session_state[KEY] = choice.lower()
        st.rerun()
