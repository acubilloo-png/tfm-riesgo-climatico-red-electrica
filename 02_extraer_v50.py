# ============================================================================
# 02_extraer_v50.py
# ----------------------------------------------------------------------------
# Extrae el campo de velocidad de retorno a 50 anos (U50) sobre la Comunitat
# Valenciana desde el atlas de Pryor y Barthelmie, y compara las estimaciones
# que el propio atlas proporciona por distintos metodos de ajuste.
#
# ----------------------------------------------------------------------------
# DOS PROBLEMAS DE LA FUENTE QUE HA HABIDO QUE RESOLVER
# ----------------------------------------------------------------------------
# 1. EL FICHERO NO TRAE COORDENADAS UTILIZABLES. Contiene dos variables llamadas
#    'Latitude' (681 valores) y 'Longitude' (1440 valores), pero sus valores no
#    son grados: van de 9,12 a 54,74 y de 34,30 a 40,72 respectivamente, no son
#    monotonas y presentan saltos de hasta -7,5. Son, con toda probabilidad, las
#    medias por fila y por columna de un campo de viento, escritas por error en
#    lugar de los ejes. La rejilla ha habido que deducirla de la forma del campo
#    (681 x 1440), que corresponde a una rejilla regular ERA5 de 0,25 grados:
#    1440 x 0,25 = 360 grados de longitud y 681 x 0,25 = 170 grados de latitud,
#    de 85 N a 85 S.
#
#    El convenio concreto se ha determinado EMPIRICAMENTE, no por suposicion:
#    se muestreo el campo en la posicion de los 38.939 activos bajo los cuatro
#    convenios posibles y se correlo con la velocidad media del Global Wind
#    Atlas, ya validada en el conjunto de datos. Solo uno da correlacion
#    positiva clara, r(Uref, GWA) = +0,540 frente a valores entre -0,02 y +0,09
#    en los otros tres: latitud descendente de 85 a -85 y longitud de 0 a 360,
#    que es justamente el convenio nativo de ERA5.
#
# 2. NO SON RACHAS, SON VELOCIDADES SOSTENIDAS. El encargo pedia rachas maximas
#    (10m_wind_gust de CERRA). Este atlas da el nivel de retorno a 50 anos de la
#    velocidad SOSTENIDA a 10 m derivada de ERA5. La diferencia importa al
#    interpretar: una racha es tipicamente 1,4-1,6 veces la sostenida. En un
#    aspecto, sin embargo, resulta favorable: la velocidad basica del CTE
#    DB-SE-AE con la que se compara en la tarea 4 es tambien una media de 10
#    minutos a 10 m con retorno de 50 anos, de modo que la comparacion es
#    homogenea, cosa que no lo seria del todo con una racha.
#
# ----------------------------------------------------------------------------
# SOBRE LA TAREA 2 DEL ENCARGO
# ----------------------------------------------------------------------------
# El encargo pedia ajustar Gumbel por L-momentos, GEV y POT sobre 37 maximos
# anuales por celda y comparar los tres. Con este atlas no es posible: distribuye
# el nivel de retorno ya ajustado, no las series anuales. No hay nada que
# ajustar.
#
# Lo que si cubre el proposito de la tarea (saber si la eleccion de metodo altera
# el resultado) es que el atlas publica cuatro estimaciones independientes de U50
# sobre la misma serie de ERA5, mas un indicador de incertidumbre por celda. Se
# comparan las cuatro y se aplica el criterio de control del 15 %.
#
# El ajuste propio de extremos sobre series temporales reales se hara con las
# rachas observadas de AEMET en el script 03.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd
import netCDF4

DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))
NC = os.path.join(DATA_DIR, "viento_extremo", "PryorBarthelmie_U50estimates.nc")
CARPETA = os.path.dirname(os.path.abspath(__file__))
CSV_ACTIVOS = os.path.join(CARPETA, "activos_con_crs.csv")
SALIDA_NPZ = os.path.join(CARPETA, "cerra_v50.npz")
SALIDA_JSON = os.path.join(CARPETA, "v50_metodos.json")

LAT_MIN, LAT_MAX = 37.7, 40.9
LON_MIN, LON_MAX = -1.7, 0.7

METODOS = ["U50_Gumbel_MoM", "U50_Gumbel_MLE", "U50_Gumbel_plot", "U50_Weibull"]
# Se adopta la maxima verosimilitud: es el estimador de referencia para Gumbel y
# el que queda en posicion central entre los cuatro sobre este territorio.
METODO_ADOPTADO = "U50_Gumbel_MLE"

# ---------------------------------------------------------------------------
# 1. Rejilla deducida y verificada (ver cabecera)
# ---------------------------------------------------------------------------
print("Abriendo el atlas...")
nc = netCDF4.Dataset(NC)
campos_globales = {m: np.asarray(nc.variables[m][:], dtype="float64")
                   for m in METODOS + ["Uref", "High_Uncertainty"]}
nc.close()

ny, nx = campos_globales[METODO_ADOPTADO].shape
lat_g = np.linspace(85, -85, ny)          # descendente, convenio ERA5
lon_g = np.linspace(0, 360 - 360 / nx, nx)  # 0..360, convenio ERA5
paso = 360.0 / nx
print(f"  campo {ny} x {nx}, rejilla regular de {paso:.2f} grados")
print(f"  convenio: latitud {lat_g[0]:.2f} -> {lat_g[-1]:.2f}, "
      f"longitud {lon_g[0]:.2f} -> {lon_g[-1]:.2f}")

# Recorte de la caja de la Comunitat. Con longitudes en 0..360, el meridiano de
# Greenwich parte la caja en dos tramos: hay que tomar los dos.
i_lat = np.where((lat_g >= LAT_MIN) & (lat_g <= LAT_MAX))[0]
lon_caja = np.mod(np.array([LON_MIN, LON_MAX]), 360)
i_lon = np.where((lon_g >= lon_caja[0]) | (lon_g <= lon_caja[1]))[0]
# Reordenar para que la caja quede contigua y en longitudes -180..180
lon_sel = lon_g[i_lon]
lon_sel_180 = np.where(lon_sel > 180, lon_sel - 360, lon_sel)
orden = np.argsort(lon_sel_180)
i_lon = i_lon[orden]
lon_sel_180 = lon_sel_180[orden]

print(f"\n  celdas en la caja: {len(i_lat)} lat x {len(i_lon)} lon "
      f"= {len(i_lat) * len(i_lon)}")
print(f"    latitudes:  {np.round(lat_g[i_lat], 2)}")
print(f"    longitudes: {np.round(lon_sel_180, 2)}")

campos = {m: campos_globales[m][np.ix_(i_lat, i_lon)]
          for m in METODOS + ["Uref", "High_Uncertainty"]}

# ---------------------------------------------------------------------------
# 2. Comparacion de los cuatro metodos
# ---------------------------------------------------------------------------
print("\n=== COMPARACION DE METODOS SOBRE LAS CELDAS DE LA COMUNITAT ===")
resumen = {}
for m in METODOS:
    f = campos[m][np.isfinite(campos[m])]
    resumen[m] = {"n_celdas": int(f.size), "min": round(float(f.min()), 3),
                  "mediana": round(float(np.median(f)), 3),
                  "media": round(float(f.mean()), 3),
                  "max": round(float(f.max()), 3)}
    print(f"  {m:<18} mediana {np.median(f):>6.2f} m/s   "
          f"rango {f.min():>5.2f}-{f.max():>5.2f}")

ref = resumen[METODO_ADOPTADO]["mediana"]
print(f"\n  desviacion de la mediana frente a {METODO_ADOPTADO} ({ref:.2f} m/s):")
max_desv = 0.0
desviaciones = {}
for m in METODOS:
    d = 100 * (resumen[m]["mediana"] - ref) / ref
    desviaciones[m] = round(d, 2)
    max_desv = max(max_desv, abs(d))
    print(f"    {m:<18} {d:>+7.2f} %")
print(f"\n  desviacion maxima {max_desv:.2f} %  "
      f"(criterio del encargo: investigar si supera el 15 %)")
print("  " + ("*** SUPERA EL 15 %, requiere investigacion ***" if max_desv > 15
              else "dentro del criterio: los metodos concuerdan"))

print("\n  concordancia espacial celda a celda:")
base = campos[METODO_ADOPTADO]
correlaciones = {}
for m in METODOS:
    if m == METODO_ADOPTADO:
        continue
    mm = np.isfinite(base) & np.isfinite(campos[m])
    r = float(np.corrcoef(base[mm], campos[m][mm])[0, 1])
    sesgo = float((campos[m][mm] - base[mm]).mean())
    correlaciones[m] = {"r": round(r, 4), "sesgo_ms": round(sesgo, 3)}
    print(f"    {m:<18} r = {r:>6.4f}   sesgo {sesgo:>+6.3f} m/s")

hu = campos["High_Uncertainty"]
hu_f = hu[np.isfinite(hu)]
n_alta = int((hu_f > 0).sum())
print(f"\n  celdas de alta incertidumbre segun los autores: {n_alta} de "
      f"{hu_f.size} ({100 * n_alta / max(hu_f.size, 1):.1f} %)")

# ---------------------------------------------------------------------------
# 3. Muestreo en la posicion de cada activo
# ---------------------------------------------------------------------------
print("\n=== MUESTREO EN LOS ACTIVOS ===")
df = pd.read_csv(CSV_ACTIVOS, sep=";", encoding="utf-8-sig", low_memory=False)
df = df[df["provincia"].notna()].copy().reset_index(drop=True)

iy = np.abs(lat_g[None, :] - df["lat"].values[:, None]).argmin(axis=1)
ix = np.abs(lon_g[None, :] - np.mod(df["lon"].values, 360)[:, None]).argmin(axis=1)
v50_activo = campos_globales[METODO_ADOPTADO][iy, ix]
uref_activo = campos_globales["Uref"][iy, ix]
celda_id = iy.astype(np.int64) * nx + ix

print(f"  {len(df)} activos en {len(np.unique(celda_id))} celdas distintas")
print(f"  V50 bruto: min {v50_activo.min():.2f}  mediana "
      f"{np.median(v50_activo):.2f}  max {v50_activo.max():.2f} m/s")
gwa = df["velocidad_viento_ms"].values
r = float(np.corrcoef(v50_activo, gwa)[0, 1])
print(f"  correlacion con el viento medio del GWA: r = {r:.4f}")

# ---------------------------------------------------------------------------
np.savez_compressed(
    SALIDA_NPZ,
    lat=lat_g[i_lat], lon=lon_sel_180,
    **{m: campos[m] for m in METODOS},
    Uref=campos["Uref"], High_Uncertainty=campos["High_Uncertainty"],
    metodo_adoptado=np.array([METODO_ADOPTADO]),
    activos_v50_bruto=v50_activo, activos_celda=celda_id,
    activos_uref=uref_activo,
)
with open(SALIDA_JSON, "w", encoding="utf-8") as fh:
    json.dump({
        "fuente": "Pryor y Barthelmie (2021), Zenodo 10.5281/zenodo.4306822, CC-BY-4.0",
        "motivo_plan_b": ("la API del CDS exige clave personal registrada, no "
                          "configurada en la maquina; el encargo admite el registro "
                          "como motivo para el plan B"),
        "variable": ("nivel de retorno a 50 anos de la velocidad SOSTENIDA a 10 m "
                     "derivada de ERA5; no es una racha"),
        "rejilla": {"forma": [int(ny), int(nx)], "paso_grados": round(paso, 4),
                    "convenio": "lat 85 a -85 descendente, lon 0 a 360 (ERA5)",
                    "determinado": "empiricamente, por correlacion con el GWA"},
        "problema_coordenadas": ("las variables Latitude y Longitude del fichero no "
                                 "contienen grados sino, aparentemente, medias por "
                                 "fila y columna de un campo de viento; la rejilla se "
                                 "dedujo de la forma del campo"),
        "celdas_comunitat": int(len(i_lat) * len(i_lon)),
        "celdas_con_activos": int(len(np.unique(celda_id))),
        "metodo_adoptado": METODO_ADOPTADO,
        "metodos": resumen,
        "desviacion_medianas_pct": desviaciones,
        "desviacion_maxima_pct": round(max_desv, 2),
        "criterio_15pct_superado": bool(max_desv > 15),
        "concordancia_espacial": correlaciones,
        "celdas_alta_incertidumbre": n_alta,
        "v50_bruto_activos": {
            "min": round(float(v50_activo.min()), 3),
            "mediana": round(float(np.median(v50_activo)), 3),
            "media": round(float(v50_activo.mean()), 3),
            "max": round(float(v50_activo.max()), 3),
            "r_con_gwa": round(r, 4),
        },
        "nota_tarea2": ("no es posible reajustar Gumbel/GEV/POT por celda: el atlas "
                        "no distribuye maximos anuales. Se comparan las cuatro "
                        "estimaciones publicadas. El ajuste propio se hara sobre "
                        "rachas observadas de AEMET en el script 03."),
    }, fh, ensure_ascii=False, indent=2)

print(f"\nGuardados: {os.path.basename(SALIDA_NPZ)} y {os.path.basename(SALIDA_JSON)}")
