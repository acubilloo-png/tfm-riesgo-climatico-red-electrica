# ============================================================================
# 03b_completar_series_largas.py
# ----------------------------------------------------------------------------
# Completa la descarga de AEMET solo para las estaciones que sostienen el ajuste
# de extremos, y consolida TODO lo que haya en cache.
#
# ----------------------------------------------------------------------------
# POR QUE SE RECORTA EL ALCANCE
# ----------------------------------------------------------------------------
# La descarga completa de las 44 estaciones x 40 anos requeria 3.520 peticiones.
# Medido al arrancar, el ritmo era de 40 peticiones por minuto (unos 90 minutos),
# pero AEMET estrangula progresivamente y el ritmo cayo a 19-21, lo que llevaba el
# total a unas 2 h 20 min, por encima del presupuesto acordado.
#
# Se recorta por tanto a las CINCO estaciones con serie de racha desde 1985, que
# son las unicas capaces de sostener un ajuste de extremos con 40 maximos anuales:
#   8019   ALICANTE-ELCHE AEROPUERTO
#   8025   ALACANT/ALICANTE
#   8414A  VALENCIA AEROPUERTO
#   8416   VALENCIA
#   8500A  CASTELLO - ALMASSORA
# Cubren las tres provincias, lo que permite al menos un contraste territorial
# grueso del campo de extremos.
#
# NO SE PIERDE NADA de lo ya descargado: el cache es por estacion y semestre, y
# las 10 estaciones que quedaron completas (entre ellas 8019 y 8025) se conservan
# y entran en la consolidacion. Aportan cobertura espacial adicional aunque sus
# series sean mas cortas, lo que sirve para la calibracion del campo aunque no
# para el ajuste de extremos.
#
# LIMITACION QUE ESTO INTRODUCE, y hay que declararla en el informe: la
# calibracion espacial del campo de extremos se apoyara en las estaciones
# disponibles y no en las 44 previstas, de modo que su cobertura es menor de la
# que se habria obtenido con la descarga completa.
# ============================================================================

import datetime as dt
import json
import os
import sys
import time

import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RUTA_CLAVE = os.environ.get(
    "AEMET_API_KEY_FILE",
    os.path.join(os.path.expanduser("~"), "TFM_local", "aemet_api_key.txt"))
DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))
CACHE = os.path.join(DATA_DIR, "cache_aemet_estacion")
CARPETA = os.path.dirname(os.path.abspath(__file__))
SALIDA_CSV = os.path.join(CARPETA, "rachas_aemet_cv.csv")
CSV_EST = os.path.join(CARPETA, "estaciones_aemet_cv.csv")

BASE = "https://opendata.aemet.es/opendata/api"
ANIO_INI, ANIO_FIN = 1985, 2024
PAUSA = 0.3

# Las cinco de serie larga, mas cualquier estacion casi completa para no dejar
# huecos sueltos que luego confundan al filtrar por anos completos.
PRIORITARIAS = ["8019", "8025", "8414A", "8416", "8500A"]
UMBRAL_COMPLETAR = 0.90     # completar tambien las que esten al 90 % o mas

CAMPOS = ["fecha", "indicativo", "racha", "horaracha", "velmedia", "dir"]

with open(RUTA_CLAVE, encoding="utf-8") as fh:
    CLAVE = fh.read().strip()
S = requests.Session()
# Cortesia con los servidores publicos: identificarse en cada peticion. El
# contacto es opcional y se toma de la variable de entorno TFM_CONTACTO, para
# no dejar datos personales escritos en el codigo.
_CONTACTO = os.environ.get("TFM_CONTACTO", "").strip()
S.headers.update({"api_key": CLAVE,
                  "User-Agent": "TFM-RachasAEMET/1.0"
                                + (f" ({_CONTACTO})" if _CONTACTO else "")})


def pedir(ruta, intentos=5):
    for i in range(1, intentos + 1):
        try:
            r = S.get(f"{BASE}{ruta}", timeout=120, verify=False)
            if r.status_code == 429:
                time.sleep(10 * i)
                continue
            if r.status_code >= 500:
                time.sleep(5 * i)
                continue
            sobre = r.json()
            if sobre.get("estado") == 404:
                return 404, []
            if sobre.get("estado") != 200:
                time.sleep(5 * i)
                continue
            rd = S.get(sobre["datos"], timeout=180, verify=False)
            rd.encoding = rd.apparent_encoding or "latin-1"
            return 200, rd.json()
        except (requests.exceptions.RequestException, ValueError):
            if i == intentos:
                return None, None
            time.sleep(5 * i)
    return None, None


est_df = pd.read_csv(CSV_EST, sep=";", encoding="utf-8-sig")
nombres = dict(zip(est_df["indicativo"], est_df["nombre"]))

# ---------------------------------------------------------------------------
# 1. Inventario de lo que ya hay
# ---------------------------------------------------------------------------
todos = sorted(os.listdir(CACHE)) if os.path.isdir(CACHE) else []
por_est = {}
for f in todos:
    if not f.endswith(".json"):
        continue
    ide = f.rsplit("_", 2)[0]
    por_est[ide] = por_est.get(ide, 0) + 1

print(f"cache actual: {sum(por_est.values())} semestres de {len(por_est)} estaciones")
completar = set(PRIORITARIAS)
for ide, n in por_est.items():
    if n >= UMBRAL_COMPLETAR * 80 and n < 80:
        completar.add(ide)

trabajos = []
for ide in sorted(completar):
    for anio in range(ANIO_INI, ANIO_FIN + 1):
        for sem, (mi, di, mf, df_) in enumerate(((1, 1, 6, 30), (7, 1, 12, 31)),
                                                start=1):
            ruta_cache = os.path.join(CACHE, f"{ide}_{anio}_{sem}.json")
            if not os.path.exists(ruta_cache):
                trabajos.append((ide, anio, sem,
                                 dt.date(anio, mi, di), dt.date(anio, mf, df_)))

print(f"\nestaciones a completar: {sorted(completar)}")
print(f"semestres pendientes: {len(trabajos)}")
if trabajos:
    print(f"  tiempo estimado: {len(trabajos) * (1.5 + PAUSA) / 60:.0f} min")

# ---------------------------------------------------------------------------
# 2. Descarga de lo que falta
# ---------------------------------------------------------------------------
t0 = time.time()
for n, (ide, anio, sem, ini, fin) in enumerate(trabajos, start=1):
    ruta = (f"/valores/climatologicos/diarios/datos/"
            f"fechaini/{ini:%Y-%m-%d}T00:00:00UTC/"
            f"fechafin/{fin:%Y-%m-%d}T23:59:59UTC/estacion/{ide}")
    estado, datos = pedir(ruta)
    if estado == 200 and isinstance(datos, list):
        registros = [{c: d.get(c) for c in CAMPOS} for d in datos]
    elif estado == 404:
        registros = []
    else:
        print(f"    fallo de red en {ide} {anio}S{sem}; se reintentara al relanzar")
        time.sleep(PAUSA)
        continue
    with open(os.path.join(CACHE, f"{ide}_{anio}_{sem}.json"), "w",
              encoding="utf-8") as fh:
        json.dump(registros, fh, ensure_ascii=False)
    if n % 40 == 0 or n == len(trabajos):
        transcurrido = (time.time() - t0) / 60
        ritmo = n / transcurrido if transcurrido else 0
        print(f"  [{n:>3}/{len(trabajos)}] {ide} {anio}S{sem}   "
              f"{ritmo:.0f} pet/min   quedan "
              f"{(len(trabajos) - n) / ritmo if ritmo else 0:.0f} min", flush=True)
    time.sleep(PAUSA)

# ---------------------------------------------------------------------------
# 3. Consolidar TODO el cache, no solo las prioritarias
# ---------------------------------------------------------------------------
print("\nconsolidando todo el cache...")
filas = []
for f in sorted(os.listdir(CACHE)):
    if not f.endswith(".json"):
        continue
    with open(os.path.join(CACHE, f), encoding="utf-8") as fh:
        filas.extend(json.load(fh))

df = pd.DataFrame(filas)
if df.empty:
    sys.exit("no se ha consolidado ningun registro")
df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
for c in ("racha", "velmedia"):
    df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ".", regex=False),
                          errors="coerce")
df = (df.dropna(subset=["fecha"])
        .drop_duplicates(subset=["indicativo", "fecha"])
        .sort_values(["indicativo", "fecha"]))
df.to_csv(SALIDA_CSV, index=False, sep=";", encoding="utf-8-sig")

print(f"\n{len(df)} registros de {df['indicativo'].nunique()} estaciones")
print(f"  periodo {df['fecha'].min():%Y-%m-%d} a {df['fecha'].max():%Y-%m-%d}")
con_r = int(df["racha"].notna().sum())
print(f"  con racha: {con_r} ({100 * con_r / len(df):.1f} %)")
idx = df["racha"].idxmax()
print(f"  racha maxima: {df.loc[idx, 'racha']:.1f} m/s "
      f"({df.loc[idx, 'racha'] * 3.6:.0f} km/h) en {df.loc[idx, 'indicativo']} "
      f"el {df.loc[idx, 'fecha']:%Y-%m-%d}")

print("\nanos con al menos 300 dias de racha, por estacion:")
df["anio"] = df["fecha"].dt.year
cob = (df.dropna(subset=["racha"]).groupby(["indicativo", "anio"]).size()
       .reset_index(name="dias"))
buenos = (cob[cob["dias"] >= 300].groupby("indicativo").size()
          .sort_values(ascending=False))
for ide, n in buenos.items():
    marca = "  <== serie larga" if ide in PRIORITARIAS else ""
    print(f"  {ide:<7} {n:>3} anos   {str(nombres.get(ide, ''))[:38]}{marca}")
print(f"\n  estaciones con >=20 anos utiles: {int((buenos >= 20).sum())}"
      f"   con >=30: {int((buenos >= 30).sum())}")
print(f"\nGuardado: {os.path.basename(SALIDA_CSV)}")
