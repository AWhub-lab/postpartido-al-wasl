# Postpartido IMPECT

Base limpia para trabajar informes postpartido desde IMPECT en esta carpeta.

## Qué hace ahora

- Autenticarse contra IMPECT con `impectPy`
- Listar partidos de una `iteration`
- Descargar un bundle partido a partido:
  - `GET /matches/{id}`
  - `GET /matches/{id}/events`
  - `GET /matches/{id}/player-kpis`
  - `GET /matches/{id}/player-scores`
  - `GET /matches/{id}/squad-kpis`
  - `GET /matches/{id}/squad-scores`
  - catálogos `GET /player-scores` y `GET /squad-scores`
- Guardar el crudo en `data/raw/match_<id>/`
- Generar un informe Markdown inicial en `reports/`
- Generar un PDF visual con portada y gráficos

## Preparación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Rellena `IMPECT_USER` y `IMPECT_PASS` en `.env`.

## Uso

Listar partidos de una competición/temporada IMPECT:

```bash
.venv/bin/python main.py list-matches --iteration-id 1499
```

Buscar primero la iteración correcta de una temporada/competición:

```bash
.venv/bin/python main.py list-iterations --season 26/27 --competition "UAE"
```

Filtrar por equipo:

```bash
.venv/bin/python main.py list-matches --iteration-id 1499 --team "Al-Wasl"
```

Ver solo los partidos ya disponibles para descargar:

```bash
.venv/bin/python main.py list-matches --iteration-id 1499 --team "Al-Wasl" --available-only
```

Generar un informe postpartido inicial:

```bash
.venv/bin/python main.py report --match-id 261945
```

Regenerar el informe desde un bundle local ya descargado:

```bash
.venv/bin/python main.py render-local --match-id 261945
```

## App web (Streamlit)

Panel con acceso por contraseña que lista todos los partidos del Al-Wasl (todas las competiciones e
iteraciones a las que tenga acceso la cuenta IMPECT), indica cuáles ya tienen datos de postpartido
disponibles y permite generar/descargar el PDF de cada uno con un clic.

Preparación local (una sola vez):

```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edita `.streamlit/secrets.toml` con tu `APP_PASSWORD` (la contraseña de acceso a la app) y tus
`IMPECT_USER`/`IMPECT_PASS`. Este archivo está en `.gitignore`, nunca se sube al repo.

Arrancar la app:

```bash
.venv/bin/streamlit run streamlit_app.py
```

El listado de partidos se cachea 10 minutos (botón "Refrescar partidos" para forzarlo antes). Los
PDF generados se guardan en `reports/`, igual que con la CLI — si ya existe el informe de un
partido, el botón pasa directamente a "Descargar".

### Desplegar en Streamlit Community Cloud

1. Sube el proyecto a un repositorio de GitHub (puede ser privado).
2. En [share.streamlit.io](https://share.streamlit.io), conecta el repo y selecciona `streamlit_app.py`
   como archivo principal.
3. En "Secrets" de la app (Settings → Secrets), pega el contenido de tu `secrets.toml` local
   (`APP_PASSWORD`, `IMPECT_USER`, `IMPECT_PASS`).
4. Ojo: el almacenamiento de Streamlit Cloud es efímero (se puede reiniciar), así que los PDF ya
   generados pueden desaparecer entre reinicios — el botón "Generar informe" siempre puede
   regenerarlos bajo demanda.

## Estructura

```text
src/postmatch_impect/
  client.py
  config.py
  report.py
  cli.py
data/raw/
reports/
PassingNetwork_Positions_NewVersion.ipynb
```

## Siguiente paso natural

La siguiente iteración sería añadir visuales:

- red de pases
- mapa de tiros
- secuencias / balón parado
- comparativa equipo vs rival

La base de autenticación y descarga ya queda separada para poder construir eso encima sin depender del notebook antiguo.
