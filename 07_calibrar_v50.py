# ============================================================================
# 07_calibrar_v50.py
# ----------------------------------------------------------------------------
# Decide, con datos observados, entre las dos variantes del campo de extremos:
#   V50_bruto_ms   valor de la celda de 0,25 grados, sin bajar de escala
#   V50_ms         bajado de escala por la razon de exposicion del Global Wind Atlas
#
# ----------------------------------------------------------------------------
# EL PROBLEMA A RESOLVER
# ----------------------------------------------------------------------------
# El escalado multiplicativo abre el rango de 16,9-24,6 m/s a 9,6-45,6 m/s. Un
# V50 sostenido de 45,6 m/s a 10 metros no es creible en la Comunitat Valenciana,
# pero la variante sin escalar solo tiene 56 valores distintos para 38.939
# activos, lo que la hace inutil para discriminar espacialmente. Hay que elegir, y
# la eleccion debe apoyarse en observaciones, no en criterio.
#
# ----------------------------------------------------------------------------
# LAS DOS MAGNITUDES NO SON COMPARABLES DIRECTAMENTE
# ----------------------------------------------------------------------------
# Las estaciones de AEMET miden RACHA maxima; el atlas de Pryor y Barthelmie da
# velocidad SOSTENIDA. Una racha es tipicamente entre 1,4 y 1,6 veces la
# sostenida, segun el factor de racha, que depende de la rugosidad del terreno y
# del tiempo de promediado. No cabe por tanto comparar cifras sin mas.
#
# Esa diferencia, sin embargo, habilita dos analisis que si son concluyentes:
#
#   1. FACTOR DE RACHA EMPIRICO. La razon entre el V50 de racha observado en
#      estacion y el V50 sostenido del atlas en esa misma celda estima el factor
#      de racha del territorio. Si cae en el intervalo 1,4-1,6 que da la
#      literatura, ambos conjuntos se validan mutuamente. Si cae muy fuera, uno
#      de los dos tiene un problema.
#
#   2. PRUEBA DE FALSACION. El viento sostenido NUNCA puede superar la racha del
#      mismo episodio. Si el V50 sostenido escalado de un activo, multiplicado por
#      el factor de racha, implica una racha superior a la maxima jamas registrada
#      en cuarenta anos de observacion en la comunidad, ese valor queda refutado.
#      No es una opinion sobre plausibilidad: es una imposibilidad fisica.
#
# La segunda prueba es la que decide, porque no depende de cuantas estaciones
# haya: basta una serie larga para acotar el maximo observado del territorio.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd
import rasterio

CARPETA = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))
GWA = os.path.join(DATA_DIR, "wind_speed_50m.tif")

CSV_V6 = os.path.join(CARPETA, "activos_con_crs_v6.csv")
CSV_EST_V50 = os.path.join(CARPETA, "v50_estaciones.csv")
CSV_EST = os.path.join(CARPETA, "estaciones_aemet_cv.csv")
CSV_RACHAS = os.path.join(CARPETA, "rachas_aemet_cv.csv")
NPZ = os.path.join(CARPETA, "cerra_v50.npz")
SALIDA = os.path.join(CARPETA, "calibracion_v50.json")

# Factor de racha de referencia en la literatura para terreno abierto
FACTOR_RACHA_MIN, FACTOR_RACHA_MAX = 1.4, 1.6

print("Cargando datos...")
act = pd.read_csv(CSV_V6, sep=";", encoding="utf-8-sig", low_memory=False)
est50 = pd.read_csv(CSV_EST_V50, sep=";", encoding="utf-8-sig")
est = pd.read_csv(CSV_EST, sep=";", encoding="utf-8-sig")
rachas = pd.read_csv(CSV_RACHAS, sep=";", encoding="utf-8-sig", low_memory=False)
rachas["fecha"] = pd.to_datetime(rachas["fecha"])
z = np.load(NPZ, allow_pickle=True)
print(f"  {len(act)} activos | {len(est50)} estaciones con V50 ajustado")

# ---------------------------------------------------------------------------
# 1. Muestreo del campo de Pryor y del GWA en la posicion de cada estacion
# ---------------------------------------------------------------------------
# La rejilla del atlas es la deducida y verificada en el script 02: 0,25 grados,
# latitud descendente de 85 a -85, longitud de 0 a 360.
metodo = str(z["metodo_adoptado"][0])
campo_global = None
import netCDF4
NC = os.path.join(DATA_DIR, "viento_extremo", "PryorBarthelmie_U50estimates.nc")
nc = netCDF4.Dataset(NC)
campo_global = np.asarray(nc.variables[metodo][:], dtype="float64")
nc.close()
ny, nx = campo_global.shape
lat_g = np.linspace(85, -85, ny)
lon_g = np.linspace(0, 360 - 360 / nx, nx)
paso = 360.0 / nx

est50 = est50.merge(est[["indicativo", "lat", "lon", "altitud", "provincia"]],
                    on="indicativo", how="left")

iy = np.abs(lat_g[None, :] - est50["lat"].values[:, None]).argmin(axis=1)
ix = np.abs(lon_g[None, :] - np.mod(est50["lon"].values, 360)[:, None]).argmin(axis=1)
est50["V50_pryor_sostenida"] = campo_global[iy, ix]

# GWA en la estacion y media del GWA sobre la celda del atlas, que es lo que
# define la razon de exposicion del script 04.
with rasterio.open(GWA) as src:
    est50["gwa_estacion"] = [v[0] for v in src.sample(
        list(zip(est50["lon"].values, est50["lat"].values)))]
    medias = []
    for k in range(len(est50)):
        lat_c, lon_c = lat_g[iy[k]], lon_g[ix[k]]
        lon_c = lon_c - 360 if lon_c > 180 else lon_c
        # Ventana de la celda de 0,25 grados centrada en su esquina
        ventana = rasterio.windows.from_bounds(
            lon_c - paso / 2, lat_c - paso / 2, lon_c + paso / 2, lat_c + paso / 2,
            transform=src.transform)
        try:
            bloque = src.read(1, window=ventana, boundless=True,
                              fill_value=np.nan).astype("float64")
            if src.nodata is not None:
                bloque[bloque == src.nodata] = np.nan
            medias.append(float(np.nanmean(bloque)))
        except Exception:
            medias.append(np.nan)
    est50["gwa_media_celda"] = medias

est50["razon_exposicion"] = est50["gwa_estacion"] / est50["gwa_media_celda"]
est50["V50_pryor_escalada"] = (est50["V50_pryor_sostenida"]
                               * est50["razon_exposicion"].clip(0.5, 2.0))

# ---------------------------------------------------------------------------
# 2. Factor de racha empirico
# ---------------------------------------------------------------------------
print("\n=== 1. FACTOR DE RACHA EMPIRICO ===")
print("  (V50 de racha observado / V50 sostenido del atlas, en la misma celda)")
est50["factor_racha_bruto"] = est50["V50_gumbel_ms"] / est50["V50_pryor_sostenida"]
est50["factor_racha_escalado"] = est50["V50_gumbel_ms"] / est50["V50_pryor_escalada"]

for _, f in est50.sort_values("indicativo").iterrows():
    print(f"  {f['indicativo']:<7} {str(f['nombre'])[:26]:<26} "
          f"racha V50 {f['V50_gumbel_ms']:>5.1f}  "
          f"atlas {f['V50_pryor_sostenida']:>5.1f}  "
          f"factor {f['factor_racha_bruto']:>4.2f}   "
          f"(escalado {f['V50_pryor_escalada']:>5.1f}, "
          f"factor {f['factor_racha_escalado']:>4.2f})")

fb = est50["factor_racha_bruto"].median()
fe = est50["factor_racha_escalado"].median()
print(f"\n  factor de racha mediano, variante BRUTA:    {fb:.3f}")
print(f"  factor de racha mediano, variante ESCALADA: {fe:.3f}")
print(f"  intervalo de referencia de la literatura:   "
      f"{FACTOR_RACHA_MIN}-{FACTOR_RACHA_MAX}")
en_rango_b = FACTOR_RACHA_MIN <= fb <= FACTOR_RACHA_MAX
en_rango_e = FACTOR_RACHA_MIN <= fe <= FACTOR_RACHA_MAX
print(f"    bruta dentro del rango:    {en_rango_b}")
print(f"    escalada dentro del rango: {en_rango_e}")

# Dispersion: una variante mejor calibrada deberia dar un factor mas estable
cv_b = est50["factor_racha_bruto"].std() / fb
cv_e = est50["factor_racha_escalado"].std() / fe
print(f"\n  coeficiente de variacion del factor entre estaciones:")
print(f"    bruta    {cv_b:.3f}")
print(f"    escalada {cv_e:.3f}   -> "
      f"{'la escalada es mas estable' if cv_e < cv_b else 'la bruta es mas estable'}")

# ---------------------------------------------------------------------------
# 3. Prueba de falsacion
# ---------------------------------------------------------------------------
print("\n=== 2. PRUEBA DE FALSACION ===")
racha_max_obs = float(rachas["racha"].max())
idx = rachas["racha"].idxmax()
print(f"  racha maxima registrada en la Comunitat en el periodo analizado: "
      f"{racha_max_obs:.1f} m/s ({racha_max_obs * 3.6:.0f} km/h)")
print(f"    estacion {rachas.loc[idx, 'indicativo']}, "
      f"{rachas.loc[idx, 'fecha']:%Y-%m-%d}")

# La racha implicada por cada variante, usando el factor empirico mas favorable
# (el minimo de la literatura, para no cargar el argumento)
factor = FACTOR_RACHA_MIN
resultados = {}
for etiqueta, col in (("bruta", "V50_bruto_ms"), ("escalada", "V50_ms")):
    implicada = act[col] * factor
    n_imposible = int((implicada > racha_max_obs).sum())
    resultados[etiqueta] = {
        "V50_max_ms": round(float(act[col].max()), 2),
        "racha_implicada_max_ms": round(float(implicada.max()), 2),
        "racha_implicada_max_kmh": round(float(implicada.max()) * 3.6, 1),
        "n_activos_imposibles": n_imposible,
        "pct_activos_imposibles": round(100 * n_imposible / len(act), 2),
    }
    print(f"\n  variante {etiqueta}:")
    print(f"    V50 sostenido maximo: {act[col].max():.1f} m/s")
    print(f"    racha implicada (x{factor}): {implicada.max():.1f} m/s "
          f"({implicada.max() * 3.6:.0f} km/h)")
    print(f"    activos cuya racha implicada supera la maxima jamas observada: "
          f"{n_imposible} ({100 * n_imposible / len(act):.2f} %)")
    if n_imposible:
        print(f"      -> esos valores son FISICAMENTE IMPOSIBLES")

# ---------------------------------------------------------------------------
# 4. Recomendacion
# ---------------------------------------------------------------------------
print("\n=== 3. RECOMENDACION ===")
imp_b = resultados["bruta"]["n_activos_imposibles"]
imp_e = resultados["escalada"]["n_activos_imposibles"]

if imp_e > 0 and imp_b == 0:
    decision = "bruta"
    motivo = (f"la variante escalada produce {imp_e} activos con racha implicada "
              f"superior a la maxima observada en el territorio, lo que es "
              f"fisicamente imposible; la bruta no produce ninguno")
elif imp_e == 0 and imp_b == 0:
    decision = "escalada"
    motivo = ("ninguna variante produce valores imposibles, de modo que se "
              "prefiere la escalada por su capacidad de discriminacion espacial")
else:
    decision = "bruta"
    motivo = ("ambas variantes producen valores imposibles; se adopta la bruta "
              "por ser la conservadora y se declara la limitacion")

print(f"  VARIANTE ADOPTADA: {decision}")
print(f"  motivo: {motivo}")
print(f"\n  la variante no adoptada se conserva en el CSV como analisis de "
      f"sensibilidad")

with open(SALIDA, "w", encoding="utf-8") as fh:
    json.dump({
        "n_estaciones": int(len(est50)),
        "estaciones": est50[[
            "indicativo", "nombre", "provincia", "n_anios", "lat", "lon",
            "V50_gumbel_ms", "V50_pryor_sostenida", "V50_pryor_escalada",
            "razon_exposicion", "factor_racha_bruto", "factor_racha_escalado",
        ]].round(4).to_dict("records"),
        "factor_racha": {
            "mediano_bruta": round(float(fb), 4),
            "mediano_escalada": round(float(fe), 4),
            "cv_bruta": round(float(cv_b), 4),
            "cv_escalada": round(float(cv_e), 4),
            "rango_literatura": [FACTOR_RACHA_MIN, FACTOR_RACHA_MAX],
            "bruta_en_rango": bool(en_rango_b),
            "escalada_en_rango": bool(en_rango_e),
        },
        "falsacion": {
            "racha_maxima_observada_ms": round(racha_max_obs, 2),
            "racha_maxima_observada_kmh": round(racha_max_obs * 3.6, 1),
            "estacion": str(rachas.loc[idx, "indicativo"]),
            "fecha": str(rachas.loc[idx, "fecha"].date()),
            "factor_aplicado": factor,
            "variantes": resultados,
        },
        "decision": decision,
        "motivo": motivo,
    }, fh, ensure_ascii=False, indent=2)

print(f"\nGuardado: {os.path.basename(SALIDA)}")
