# ============================================================================
# 03_descargar_rachas_aemet.py
# ----------------------------------------------------------------------------
# Descarga las rachas maximas diarias observadas por las 44 estaciones de AEMET
# en la Comunitat Valenciana, 1985-2024.
#
# ----------------------------------------------------------------------------
# POR QUE OBSERVACIONES Y NO SOLO REANALISIS
# ----------------------------------------------------------------------------
# El atlas de Pryor y Barthelmie (script 02) da velocidad SOSTENIDA de retorno a
# 50 anos derivada de ERA5, a 0,25 grados. Ni ese producto ni CERRA a 5,5 km
# resuelven rachas convectivas, que son de escala inferior a la rejilla. El
# episodio de Catadau de octubre de 2024, que derribo mas de veinte apoyos, fue
# de caracter tornadico: cualquier reanalisis lo subestima por construccion. Las
# rachas de estacion si lo capturan, porque son medidas puntuales reales.
#
# Con estas series se hace ademas el ajuste de extremos que pedia la tarea 2 y
# que el atlas no permitia, al distribuir el nivel de retorno ya ajustado.
#
# ----------------------------------------------------------------------------
# ESTRATEGIA DE ACCESO: MEDIDA, NO SUPUESTA
# ----------------------------------------------------------------------------
# El endpoint diario impone dos limites distintos:
#   - todasestaciones:       15 dias por peticion, devuelve las 837 de Espana
#   - una estacion concreta:  6 meses por peticion
#
# La primera parecia mas barata por numero de peticiones (974 frente a 3.520),
# pero al medirla resulto ser mucho peor: 15 s por peticion frente a 1,2 s,
# porque devuelve 12.485 registros de los que solo 75 son de la Comunitat. Se
# descargaba y descartaba el 99,4 % de cada respuesta. El coste real era de unos
# 240 minutos, el doble del presupuesto acordado.
#
# Con peticiones por estacion: 44 estaciones x 40 anos x 2 semestres = 3.520
# peticiones a ~1,5 s = unos 90 minutos, y con el dato completo en lugar de un
# subconjunto. Las peticiones a periodos en que la estacion no existia devuelven
# 404 y son rapidas.
#
# Cada semestre se cachea por separado, de modo que relanzar no repite nada y un
# fallo a mitad se reanuda donde estaba.
#
# La clave de API se lee de fuera del repositorio; nunca aparece en el codigo.
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
SALIDA_EST = os.path.join(CARPETA, "estaciones_aemet_cv.csv")

BASE = "https://opendata.aemet.es/opendata/api"
PROVINCIAS = {"VALENCIA", "CASTELLON", "ALICANTE"}
ANIO_INI, ANIO_FIN = 1985, 2024
PAUSA = 0.3
PRESUPUESTO_MIN = 120

os.makedirs(CACHE, exist_ok=True)

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

CAMPOS = ["fecha", "indicativo", "racha", "horaracha", "velmedia", "dir"]


def pedir(ruta, intentos=5):
    """
    AEMET devuelve un sobre JSON con la URL de los datos. Ambas fases fallan de
    forma transitoria (429 por tasa, o cierre de conexion sin respuesta), asi que
    las dos se reintentan con espera creciente. Un 404 no es un fallo: significa
    que no hay datos en ese periodo, y se devuelve como tal.
    """
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


# ---------------------------------------------------------------------------
# 1. Inventario y estaciones de la Comunitat
# ---------------------------------------------------------------------------
ruta_inv = os.path.join(DATA_DIR, "cache_aemet", "inventario.json")
if os.path.exists(ruta_inv):
    with open(ruta_inv, encoding="utf-8") as fh:
        inventario = json.load(fh)
    print(f"inventario en cache: {len(inventario)} estaciones")
else:
    print("descargando inventario...")
    _, inventario = pedir("/valores/climatologicos/inventarioestaciones/todasestaciones")
    if not inventario:
        sys.exit("no se pudo obtener el inventario")
    os.makedirs(os.path.dirname(ruta_inv), exist_ok=True)
    with open(ruta_inv, "w", encoding="utf-8") as fh:
        json.dump(inventario, fh, ensure_ascii=False)


def grados(txt):
    """Convierte el sexagesimal de AEMET ('394924N') a grados decimales."""
    if not txt or len(txt) < 5:
        return None
    hemi, cifras = txt[-1].upper(), txt[:-1]
    valor = int(cifras[:-4]) + int(cifras[-4:-2]) / 60 + int(cifras[-2:]) / 3600
    return -valor if hemi in ("S", "W", "O") else valor


estaciones = [{
    "indicativo": e["indicativo"], "nombre": e["nombre"],
    "provincia": e["provincia"],
    "altitud": pd.to_numeric(e.get("altitud"), errors="coerce"),
    "lat": grados(e.get("latitud")), "lon": grados(e.get("longitud")),
} for e in inventario
    if str(e.get("provincia", "")).upper().strip() in PROVINCIAS]

est_df = pd.DataFrame(estaciones).sort_values("indicativo")
est_df.to_csv(SALIDA_EST, index=False, sep=";", encoding="utf-8-sig")
print(f"estaciones de la Comunitat Valenciana: {len(est_df)}")

# ---------------------------------------------------------------------------
# 2. Trabajos pendientes
# ---------------------------------------------------------------------------
trabajos = []
for ide in est_df["indicativo"]:
    for anio in range(ANIO_INI, ANIO_FIN + 1):
        for sem, (mi, di, mf, df_) in enumerate(
                ((1, 1, 6, 30), (7, 1, 12, 31)), start=1):
            trabajos.append((ide, anio, sem,
                             dt.date(anio, mi, di), dt.date(anio, mf, df_)))

pendientes = [t for t in trabajos
              if not os.path.exists(os.path.join(CACHE, f"{t[0]}_{t[1]}_{t[2]}.json"))]
print(f"\n{len(trabajos)} semestres-estacion en total")
print(f"  en cache: {len(trabajos) - len(pendientes)}   pendientes: {len(pendientes)}")
if pendientes:
    minutos = len(pendientes) * (1.2 + PAUSA) / 60
    print(f"  tiempo estimado: {minutos:.0f} minutos")
    if minutos > PRESUPUESTO_MIN:
        sys.exit(f"ABORTADO: supera el presupuesto de {PRESUPUESTO_MIN} min")

# ---------------------------------------------------------------------------
# 3. Descarga
# ---------------------------------------------------------------------------
t_ini = time.time()
n_404 = 0
for n, (ide, anio, sem, ini, fin) in enumerate(pendientes, start=1):
    ruta_cache = os.path.join(CACHE, f"{ide}_{anio}_{sem}.json")
    ruta = (f"/valores/climatologicos/diarios/datos/"
            f"fechaini/{ini:%Y-%m-%d}T00:00:00UTC/"
            f"fechafin/{fin:%Y-%m-%d}T23:59:59UTC/estacion/{ide}")
    estado, datos = pedir(ruta)

    if estado == 200 and isinstance(datos, list):
        registros = [{c: d.get(c) for c in CAMPOS} for d in datos]
    elif estado == 404:
        registros = []
        n_404 += 1
    else:
        # Fallo definitivo de red: NO se cachea, para que un relanzamiento lo
        # vuelva a intentar en lugar de darlo por vacio para siempre.
        print(f"    fallo de red en {ide} {anio}S{sem}, se reintentara al relanzar")
        time.sleep(PAUSA)
        continue

    with open(ruta_cache, "w", encoding="utf-8") as fh:
        json.dump(registros, fh, ensure_ascii=False)

    if n % 200 == 0 or n == len(pendientes):
        transcurrido = (time.time() - t_ini) / 60
        ritmo = n / transcurrido if transcurrido > 0 else 0
        restan = (len(pendientes) - n) / ritmo if ritmo else 0
        print(f"  [{n:>4}/{len(pendientes)}] {ide} {anio}S{sem}   "
              f"{ritmo:.1f} pet/min   quedan {restan:.0f} min", flush=True)
    time.sleep(PAUSA)

print(f"\n  peticiones sin datos (404, estacion inactiva): {n_404}")

# ---------------------------------------------------------------------------
# 4. Consolidar
# ---------------------------------------------------------------------------
print("\nconsolidando...")
filas = []
for ide, anio, sem, _, _ in trabajos:
    ruta_cache = os.path.join(CACHE, f"{ide}_{anio}_{sem}.json")
    if os.path.exists(ruta_cache):
        with open(ruta_cache, encoding="utf-8") as fh:
            filas.extend(json.load(fh))

df = pd.DataFrame(filas)
if df.empty:
    sys.exit("no se ha consolidado ningun registro")

df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
for c in ("racha", "velmedia"):
    df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ".", regex=False),
                          errors="coerce")
df = df.dropna(subset=["fecha"]).drop_duplicates(subset=["indicativo", "fecha"])
df = df.sort_values(["indicativo", "fecha"])
df.to_csv(SALIDA_CSV, index=False, sep=";", encoding="utf-8-sig")

print(f"\n{len(df)} registros de {df['indicativo'].nunique()} estaciones")
print(f"  periodo: {df['fecha'].min():%Y-%m-%d} a {df['fecha'].max():%Y-%m-%d}")
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
nombres = dict(zip(est_df["indicativo"], est_df["nombre"]))
for ide, n in buenos.items():
    print(f"  {ide:<7} {n:>3} anos   {str(nombres.get(ide, ''))[:42]}")
print(f"\n  estaciones con >=20 anos utiles: "
      f"{int((buenos >= 20).sum())}   con >=30: {int((buenos >= 30).sum())}")

print(f"\nGuardado: {os.path.basename(SALIDA_CSV)}")
