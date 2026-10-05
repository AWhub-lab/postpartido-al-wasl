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

## Carrera por el título

Es una app aparte del postpartido: `.venv/bin/streamlit run carrera_titulo_app.py`. En local
(con las credenciales de IMPECT y sin carpeta de Drive configurada) el botón **Actualizar después de la
jornada** consulta IMPECT (solo UAE Pro League): resultados y calendarios de hasta
cuatro temporadas y los KPIs de equipo de cada partido jugado (xG, PSxG, tiros…),
con caché incremental por partido en `data/title_race/process_<iteración>.json`.
`data/` no se distribuye con Git: en un despliegue nuevo hay que pulsar el botón.

**Modelo v4 (`xg-isr-poisson-v4`):** la fuerza ofensiva/defensiva de cada equipo se estima con
`0,8 × xG + 0,2 × goles` (solo goles si falta el xG), temporada actual peso 1 y
anteriores 0,3 / 0,09, prior de 12 partidos hacia el nivel que marca el
**ISR (IMPECT Squad Rating)** y ruido sobre el nivel de cada equipo en cada simulación.
El PSxG no entra en el modelo: en el backtest predice peor que el xG
(`compare_models`, resultados en `data/title_race/model_comparison.json` y
`model_comparison_md5.json`). Todos los parámetros se eligieron por backtest. Escenarios
pesimista / conservador / optimista = percentiles 10 / 50 / 90 de los puntos simulados. 20.000 temporadas simuladas con semilla fija. La pestaña **Cómo funciona**
incluye un backtest en temporadas terminadas y el detalle técnico.

Pestañas, siempre desde la perspectiva de Al Wasl y comparando con Al Jazira y Al Ain:

- **Resumen:** titular automático, KPIs, tarjetas de los tres candidatos, puntos
  finales por equipo con escudos y clasificación proyectada (PPG vs xPPG).
- **¿Qué hace falta?:** opciones de título según los puntos finales, ritmos actual /
  título / dominante, ejemplo de racha V-E-D y goles necesarios.
- **Wasl · Jazira · Ain:** tabla comparativa, embudo xG → PSxG → goles y duelos directos.
- **Nivel ISR:** ranking ISR actual, ISR de los campeones frente a sus puntos y evolución desde 2019.
- **Mercado · Transfermarkt / Mercado · BeSoccer (experimentales):** misma simulación con el valor de
  plantilla como único punto de partida (sin ISR). Transfermarkt: valor de cada jugador al inicio de la
  temporada ponderado por sus minutos en IMPECT (`src/postmatch_impect/market.py`, cruce por el id de
  Transfermarkt que trae IMPECT, caché en `data/title_race/tm/`). Intensidad calibrada por backtest
  (`market_comparison.json`). En jornada 5 predice algo peor que el ISR, por eso no entra en el modelo principal.
- **Evolución:** puntos acumulados frente a los últimos campeones, puntos reales vs
  merecidos y seguimiento de las estimaciones guardadas (con exportar/restaurar).
- **Calendario:** partidos pendientes con probabilidades V/E/D y puntos esperados.

Los escudos salen de `assets/crests/<squadId>.png` o de la URL de IMPECT; si no hay
imagen se muestran las siglas (Ajman, Al Nasr, Hatta y Al Dhafra no tienen escudo en IMPECT).

Limitaciones: el % de título reparte empates a puntos (sin desempate oficial), no
contempla fichajes, lesiones ni sanciones, y la validación solo cubre dos temporadas.

```bash
.venv/bin/python -m unittest discover -s tests -v
```

### App independiente «Carrera por el título» (solo consulta)

`carrera_titulo_app.py` es una app aparte, de solo lectura, para compartir. No llama a IMPECT ni a
BeSoccer: lee un paquete de datos desde una carpeta de Google Drive.

1. **Generar el paquete** (en local, tras actualizar los datos):

   ```bash
   PYTHONPATH=src .venv/bin/python -m postmatch_impect.title_race_data build
   ```

   Crea `dist/carrera_titulo_datos.zip` (~1,5 MB): resultados, xG, ISR, comparativas, Transfermarkt,
   plantillas y fichas de BeSoccer, referencia del compañero y escudos.
2. **Subirlo** a la carpeta de Drive (mismo nombre de archivo; sustituir el anterior).
3. **Cuenta de servicio** (una vez): Google Cloud → crear proyecto → activar «Google Drive API» →
   IAM → Cuentas de servicio → crear → Claves → JSON. Compartir la carpeta de Drive con el email de la
   cuenta de servicio como *Lector*.
4. **Streamlit Cloud** → New app → mismo repositorio → *Main file*: `carrera_titulo_app.py`. Secretos:

   ```toml
   TITLE_APP_USERNAME = "..."
   TITLE_APP_PASSWORD = "..."
   TITLE_RACE_DRIVE_FOLDER_ID = "id de la carpeta (lo que va tras /folders/ en la URL)"

   [gcp_service_account]
   type = "service_account"
   project_id = "..."
   private_key_id = "..."
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "...@....iam.gserviceaccount.com"
   client_id = "..."
   token_uri = "https://oauth2.googleapis.com/token"
   ```

La app comprueba Drive cada 10 minutos y descarga el paquete solo si hay una versión nueva. En
local funciona sin Drive con la carpeta `data/`:

```bash
.venv/bin/streamlit run carrera_titulo_app.py
```
