# ============================================================================
# 01_descargar_viento_extremo.py
# ----------------------------------------------------------------------------
# Descarga el atlas global de viento extremo de Pryor y Barthelmie (Nature
# Energy, 2021), alojado en Zenodo con DOI 10.5281/zenodo.4306822 y licencia
# CC-BY-4.0. Da la velocidad sostenida de retorno a 50 anos (U50) derivada de
# ERA5.
#
# POR QUE ESTA FUENTE Y NO CERRA
#   El encargo pide CERRA como fuente primaria y este atlas como plan B, con
#   "cuota, registro o formato GRIB" como motivos validos para recurrir a el. El
#   motivo aqui es el registro: la API del CDS exige una clave personal ligada a
#   una cuenta, que no esta configurada en la maquina. Queda documentado en
#   INFORME.md, como se pide.
#
# LIMITACION QUE HAY QUE DECLARAR
#   La resolucion es de ~30 km, frente a los 5,5 km de CERRA. Sobre la Comunitat
#   Valenciana eso deja del orden de 25 celdas, de modo que el campo apenas
#   resuelve variacion intracomunitaria. El escalado por exposicion local del
#   Global Wind Atlas (tarea 3) pasa a soportar todo el detalle espacial, y eso
#   debe decirse al interpretar los resultados.
#
# Cachea: no vuelve a descargar lo que ya este en disco con el tamano correcto.
# ============================================================================

import os
import sys

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))
DESTINO = os.path.join(DATA_DIR, "viento_extremo")
API_ZENODO = "https://zenodo.org/api/records/4306822"

# Cortesia con los servidores publicos: identificarse en cada peticion. El
# contacto es opcional y se toma de la variable de entorno TFM_CONTACTO, para
# no dejar datos personales escritos en el codigo.
_CONTACTO = os.environ.get("TFM_CONTACTO", "").strip()
CABECERAS = {"User-Agent": "TFM-VientoExtremo/1.0"
                           + (f" ({_CONTACTO})" if _CONTACTO else "")}

# Ficheros que interesan. Se omite el de ventanas moviles de 20 anos (157 MB):
# aporta la evolucion temporal de U50, que no se usa en este trabajo, y puede
# descargarse despues si hiciera falta analizar tendencias.
QUERIDOS = {
    "PryorBarthelmie_U50estimates.nc":
        "campo principal de U50 (velocidad sostenida de retorno a 50 anos)",
    "PryorBarthelmie_U50Uref_Weibull.nc":
        "razon U50/Uref ajustada por Weibull, util como contraste",
    "PryorBarthelmie_U50_obs.xlsx":
        "comparacion del atlas contra observaciones, para valorar su sesgo",
}

os.makedirs(DESTINO, exist_ok=True)

print("Consultando el registro de Zenodo...")
r = requests.get(API_ZENODO, headers=CABECERAS, timeout=120, verify=False)
r.raise_for_status()
registro = r.json()
print(f"  {registro['metadata']['title']}")
print(f"  licencia: {registro['metadata']['license']['id']}   "
      f"publicado: {registro['metadata']['publication_date']}")

disponibles = {f["key"]: f for f in registro["files"]}
faltan = [k for k in QUERIDOS if k not in disponibles]
if faltan:
    print(f"  AVISO: no estan en el registro: {faltan}")

total = 0
for nombre, motivo in QUERIDOS.items():
    if nombre not in disponibles:
        continue
    meta = disponibles[nombre]
    tamano = meta["size"]
    ruta = os.path.join(DESTINO, nombre)

    if os.path.exists(ruta) and os.path.getsize(ruta) == tamano:
        print(f"  {nombre}: en cache ({tamano / 1e6:.1f} MB), se omite")
        total += tamano
        continue

    url = meta["links"]["self"]
    print(f"  {nombre}: descargando {tamano / 1e6:.1f} MB")
    print(f"    ({motivo})")
    parcial = ruta + ".parcial"
    bajado = 0
    with requests.get(url, headers=CABECERAS, stream=True,
                      timeout=900, verify=False) as resp:
        resp.raise_for_status()
        with open(parcial, "wb") as fh:
            for trozo in resp.iter_content(chunk_size=1 << 20):
                fh.write(trozo)
                bajado += len(trozo)
    # Solo se renombra si el tamano cuadra: asi una descarga cortada no queda
    # en disco haciendose pasar por completa y el cache no se envenena.
    if bajado != tamano:
        os.remove(parcial)
        print(f"    ERROR: se esperaban {tamano} bytes y llegaron {bajado}")
        sys.exit(1)
    os.replace(parcial, ruta)
    total += tamano
    print(f"    listo")

print(f"\n{total / 1e6:.1f} MB en {DESTINO}")
