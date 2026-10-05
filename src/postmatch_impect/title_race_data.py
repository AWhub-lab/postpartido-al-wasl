"""Data package for the stand-alone «Carrera por el título» app.

The data folder is not in Git. Locally you build one zip with everything the app reads and
upload it to a Google Drive folder; the deployed app downloads it with a service account
(read-only) and unpacks it next to the code.

    .venv/bin/python -m postmatch_impect.title_race_data build      # -> dist/carrera_titulo_datos.zip
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

BUNDLE_NAME = 'carrera_titulo_datos.zip'
MARKER = Path('data')/'.carrera_titulo_bundle.json'

# Everything the title-race pages read (relative to the project root).
INCLUDE = [
    'data/title_race/season_*.json',
    'data/title_race/process_*.json',
    'data/title_race/ratings.json',
    'data/title_race/model_comparison.json',
    'data/title_race/model_comparison_md5.json',
    'data/title_race/market_comparison.json',
    'data/title_race/market_tm.json',
    'data/title_race/market_besoccer.json',
    'data/title_race/snapshots/*.json',
    'data/title_race/tm/roster_*.json',
    'data/title_race/tm/players_*.json',
    'data/title_race/tm/appearances_*.json',
    'data/title_race/tm/players/*.json',
    'data/besoccer_uae/uae_league_squads_5_seasons.csv',
    'data/besoccer_uae/player_charts.json',
    'data/besoccer_uae/pv_reference_colleague.json',
    'assets/crests/*',
]


def build_bundle(root: Path, out: Path | None = None) -> Path:
    out = out or root/'dist'/BUNDLE_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    files = sorted({p for pattern in INCLUDE for p in root.glob(pattern) if p.is_file()})
    manifest = {'built_at': datetime.now(timezone.utc).isoformat(), 'files': len(files),
                'bytes': sum(p.stat().st_size for p in files)}
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(root).as_posix())
        z.writestr('data/title_race_bundle_manifest.json', json.dumps(manifest, indent=2))
    return out


# ---------------------------------------------------------------- Google Drive (read-only)

def _token(service_account_info: dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_info(
        dict(service_account_info), scopes=['https://www.googleapis.com/auth/drive.readonly'])
    creds.refresh(Request())
    return creds.token


def drive_file(service_account_info: dict, folder_id: str, name: str = BUNDLE_NAME):
    """(file id, modifiedTime, token) of the newest file called `name` in the Drive folder."""
    token = _token(service_account_info)
    r = requests.get('https://www.googleapis.com/drive/v3/files', timeout=30,
                     headers={'Authorization': f'Bearer {token}'},
                     params={'q': f"'{folder_id}' in parents and name = '{name}' and trashed = false",
                             'fields': 'files(id,modifiedTime,size)', 'orderBy': 'modifiedTime desc',
                             'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'})
    r.raise_for_status()
    found = r.json().get('files', [])
    if not found:
        raise FileNotFoundError(f'No se encuentra {name} en la carpeta de Drive (¿está compartida con la cuenta de servicio?).')
    return found[0]['id'], found[0]['modifiedTime'], token


def sync_from_drive(root: Path, service_account_info: dict, folder_id: str) -> dict:
    """Download and unpack the bundle when Drive has a newer version. Returns the bundle info."""
    file_id, modified, token = drive_file(service_account_info, folder_id)
    marker = root/MARKER
    current = json.loads(marker.read_text()) if marker.exists() else {}
    if current.get('modifiedTime') == modified:
        return current
    r = requests.get(f'https://www.googleapis.com/drive/v3/files/{file_id}', timeout=120,
                     headers={'Authorization': f'Bearer {token}'}, params={'alt': 'media', 'supportsAllDrives': 'true'})
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for member in z.namelist():   # only paths inside data/ and assets/
            if member.startswith(('data/', 'assets/')) and '..' not in member:
                z.extract(member, root)
    manifest = root/'data'/'title_race_bundle_manifest.json'
    info = {'modifiedTime': modified, **(json.loads(manifest.read_text()) if manifest.exists() else {})}
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(info))
    return info


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    if len(sys.argv) > 1 and sys.argv[1] == 'build':
        path = build_bundle(root)
        with zipfile.ZipFile(path) as z:
            n = len(z.namelist())
        print(f'Paquete creado: {path} ({path.stat().st_size/1e6:.1f} MB, {n} archivos). Súbelo a la carpeta de Drive.')
    else:
        print(__doc__)
