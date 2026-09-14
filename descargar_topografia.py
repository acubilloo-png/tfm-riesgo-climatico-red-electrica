# ============================================================================
# descargar_topografia.py
# ----------------------------------------------------------------------------
# Descarga las dos capas que faltan para el modelado supervisado de
# inundabilidad SIN usar PATRICOVA como variable de entrada:
#
#   1. Red de cauces de la Comunitat Valenciana (Institut Cartogràfic Valencià).
#      Se usa para calcular la distancia de cada activo al cauce más cercano,
#      que es el predictor físico más directo de exposición fluvial.
#
#   2. Modelo digital de superficie Copernicus DEM GLO-30 (30 m), teselas de
#      1º x 1º que cubren la comunidad. De él se derivan la altitud y la
#      pendiente del emplazamiento de cada activo.
#
# Ambas fuentes son públicas y de acceso libre sin registro ni clave de API, lo
# que mantiene la reproducibilidad completa del trabajo.
#
# Las capas se guardan FUERA de la carpeta del proyecto (que está en OneDrive),
# porque son voluminosas y redescargables. Ver TFM_DATA_DIR.
# ============================================================================

import os
import json

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))
DIR_DEM = os.path.join(DATA_DIR, "dem")
RUTA_CAUCES = os.path.join(DATA_DIR, "cauces_cv.geojson")

# Cortesia con los servidores publicos: identificarse en cada peticion. El
# contacto es opcional y se toma de la variable de entorno TFM_CONTACTO, para
# no dejar datos personales escritos en el codigo.
_CONTACTO = os.environ.get("TFM_CONTACTO", "").strip()
CABECERAS = {"User-Agent": "TFM-DescargaTopografia/1.0"
                           + (f" ({_CONTACTO})" if _CONTACTO else "")}

os.makedirs(DIR_DEM, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Red de cauces (ArcGIS REST, paginada)
# ---------------------------------------------------------------------------
SVC_CAUCES = ("https://carto.icv.gva.es/arcgis/rest/services/"
              "tm_infraestructuras/ordenacion_territorial/MapServer/3")

def descargar_cauces():
    if os.path.exists(RUTA_CAUCES):
        mb = os.path.getsize(RUTA_CAUCES) / 1e6
        print(f"  ya existe ({mb:.1f} MB), no se vuelve a descargar")
        return

    features = []
    offset = 0
    pagina = 0
    while True:
        # maxAllowableOffset simplifica la geometría a 15 m de tolerancia y
        # geometryPrecision recorta los decimales. Para calcular la distancia de
        # un activo al cauce más cercano esa precisión sobra, y reduce el volumen
        # de descarga en un orden de magnitud.
        params = {
            "where": "1=1",
            "outFields": "objectid",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 1000,
            "maxAllowableOffset": 15,
            "geometryPrecision": 6,
        }
        r = requests.get(f"{SVC_CAUCES}/query", params=params,
                         headers=CABECERAS, timeout=300, verify=False)
        r.raise_for_status()
        lote = r.json().get("features", [])
        if not lote:
            break
        features.extend(lote)
        offset += 1000
        pagina += 1
        if pagina % 10 == 0:
            print(f"    {len(features)} cauces descargados...", flush=True)
        if len(lote) < 1000:
            break

    with open(RUTA_CAUCES, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
    mb = os.path.getsize(RUTA_CAUCES) / 1e6
    print(f"  {len(features)} cauces guardados en {RUTA_CAUCES} ({mb:.1f} MB)")


print("=== 1. Red de cauces (ICV) ===")
descargar_cauces()


# ---------------------------------------------------------------------------
# 2. Copernicus DEM GLO-30
# ---------------------------------------------------------------------------
# Las teselas se nombran por su esquina suroeste: N39_00_W001_00 cubre de 39ºN a
# 40ºN y de 1ºW a 0º. La Comunitat Valenciana se extiende de 37,84ºN a 40,79ºN y
# de 1,53ºW a 0,69ºE, así que hacen falta las latitudes 37 a 40 y las longitudes
# W002, W001 y E000.
BASE_DEM = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"

def nombre_tesela(lat, lon_txt):
    return f"Copernicus_DSM_COG_10_N{lat:02d}_00_{lon_txt}_00_DEM"


print("\n=== 2. Copernicus DEM GLO-30 ===")
descargadas, ausentes, total_mb = [], [], 0.0
for lat in (37, 38, 39, 40):
    for lon_txt in ("W002", "W001", "E000"):
        nombre = nombre_tesela(lat, lon_txt)
        destino = os.path.join(DIR_DEM, f"{nombre}.tif")
        if os.path.exists(destino):
            mb = os.path.getsize(destino) / 1e6
            total_mb += mb
            descargadas.append(nombre)
            print(f"  N{lat} {lon_txt}: ya descargada ({mb:.1f} MB)")
            continue
        url = f"{BASE_DEM}/{nombre}/{nombre}.tif"
        try:
            with requests.get(url, headers=CABECERAS, stream=True,
                              timeout=600, verify=False) as r:
                if r.status_code == 404:
                    # No es un error: las teselas íntegramente marinas no existen.
                    ausentes.append(nombre)
                    print(f"  N{lat} {lon_txt}: no existe (tesela sin tierra)")
                    continue
                r.raise_for_status()
                with open(destino, "wb") as fh:
                    for trozo in r.iter_content(chunk_size=1 << 20):
                        fh.write(trozo)
            mb = os.path.getsize(destino) / 1e6
            total_mb += mb
            descargadas.append(nombre)
            print(f"  N{lat} {lon_txt}: descargada ({mb:.1f} MB)", flush=True)
        except Exception as e:
            print(f"  N{lat} {lon_txt}: FALLO {type(e).__name__}: {e}")

print(f"\n  {len(descargadas)} teselas disponibles, {total_mb:.0f} MB en total")
print(f"  {len(ausentes)} teselas inexistentes (sin superficie terrestre)")
print(f"\nTodo en: {DATA_DIR}")
