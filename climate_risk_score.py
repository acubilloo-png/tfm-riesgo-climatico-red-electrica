# ============================================================================
# climate_risk_score.py
# ----------------------------------------------------------------------------
# Construye un índice compuesto de riesgo climático (Climate Risk Score, CRS)
# para cada activo eléctrico de la Comunitat Valenciana.
#
# ESTRUCTURA DEL ÍNDICE
#   Se sigue la descomposición habitual en la literatura de riesgo climático
#   (IPCC AR6; Panteli y Mancarella; Hagenlocher et al.):
#
#       riesgo = peligrosidad x vulnerabilidad x exposición
#
#   y se aplica por separado a las dos amenazas consideradas, agregándolas
#   después con pesos explícitos:
#
#       CRS = 100 x [ w_i x (H_inund x V_inund) + w_v x (H_viento x V_viento) ]
#                 x factor_criticidad
#
#   Todos los términos están normalizados a [0, 1], de modo que el CRS resultante
#   se mueve en [0, 100] y es interpretable como un percentil de riesgo relativo
#   DENTRO del área de estudio. No es una probabilidad de fallo ni una pérdida
#   económica esperada: es un índice de priorización relativa, y como tal debe
#   presentarse.
#
# ADVERTENCIA METODOLÓGICA IMPORTANTE
#   Este índice es una construcción determinista a partir de las variables de
#   entrada. Por tanto NO debe usarse como variable objetivo de un modelo
#   supervisado alimentado con esas mismas variables: el modelo se limitaría a
#   reconstruir esta fórmula, y un análisis SHAP sobre él recuperaría los pesos
#   fijados aquí, no un conocimiento extraído de los datos. Sería un
#   razonamiento circular. Ver la nota al final del script.
# ============================================================================

import os
import json

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree

CSV_ACTIVOS = "activos_con_variables_climaticas.csv"
SALIDA_CSV = "activos_con_crs.csv"
SALIDA_JSON = "crs_parametros.json"

UTM_EPSG = 25830
RADIO_CRITICIDAD_M = 5000

# ---------------------------------------------------------------------------
# PARÁMETROS DEL ÍNDICE — explícitos y discutibles
# ---------------------------------------------------------------------------
# Pesos de las dos amenazas. Se da más peso a la inundación porque es la amenaza
# dominante en el área de estudio y la que motivó este trabajo (DANA de octubre
# de 2024). Al final del script se incluye un análisis de sensibilidad que
# muestra cuánto cambia la ordenación de activos al variar este reparto.
PESO_INUNDACION = 0.60
PESO_VIENTO = 0.40

# Matriz de vulnerabilidad por tipo de activo. Estos valores son juicio experto
# documentado, NO medidas: hay que poder defenderlos y son el primer sitio donde
# un tribunal preguntará. Justificación de cada uno:
#
#   subestación   inund. 1,00  El equipamiento crítico (transformadores,
#                              aparamenta, control) está a nivel de suelo; una
#                              entrada de agua provoca indisponibilidad total y
#                              reparación larga. Es el activo más vulnerable a
#                              inundación de todo el sistema.
#                 viento 0,40  Estructuras bajas y en parte cerradas; el viento
#                              afecta sobre todo a elementos auxiliares.
#
#   tower         inund. 0,35  Torre metálica de celosía: la estructura está
#                              elevada y solo la cimentación es sensible
#                              (socavación). Puede estar en llanura de
#                              inundación sin quedar fuera de servicio.
#                 viento 1,00  Gran altura y superficie expuesta; es el activo
#                              donde el viento extremo produce los colapsos en
#                              cascada descritos en la literatura.
#
#   pole          inund. 0,55  Menor altura pero materiales más débiles (madera,
#                              hormigón) y cimentación ligera, sensible a
#                              socavación y a arrastre de flotantes.
#                 viento 0,75  Menos superficie que una torre, pero menor
#                              resistencia estructural.
#
#   portal        inund. 0,60  Estructura intermedia, habitual en accesos a
#                 viento 0,70  subestación y cruces de línea.
VULNERABILIDAD = {
    "subestacion": {"inundacion": 1.00, "viento": 0.40},
    "tower":       {"inundacion": 0.35, "viento": 1.00},
    "pole":        {"inundacion": 0.55, "viento": 0.75},
    "portal":      {"inundacion": 0.60, "viento": 0.70},
}

# La criticidad de red modula el resultado en una banda estrecha (x0,75 a x1,25).
# Se limita a propósito: la densidad de apoyos alrededor es un proxy grosero del
# número de clientes afectados, y no debe poder invertir por sí sola la
# ordenación que producen la peligrosidad y la vulnerabilidad.
CRITICIDAD_MIN, CRITICIDAD_MAX = 0.75, 1.25

# Alcance de la proximidad a zona inundable, en metros. Un activo a 20 m de una
# lámina de inundación de 25 años no tiene riesgo nulo: la cartografía tiene una
# precisión finita. Se le asigna un riesgo residual que decae con la distancia.
ESCALA_PROXIMIDAD_M = 500.0
PESO_PROXIMIDAD = 0.10       # como máximo, un 10 % de la peligrosidad plena

NIVEL_A_RETORNO = {1: 25, 2: 100, 3: 25, 4: 100, 5: 500, 6: 500}
NIVEL_A_FACTOR_CALADO = {1: 1.0, 2: 1.0, 3: 0.5, 4: 0.5, 5: 1.0, 6: 0.5}


# ---------------------------------------------------------------------------
# 1. Cargar y restringir al área de estudio
# ---------------------------------------------------------------------------
print("Cargando activos...")
df = pd.read_csv(CSV_ACTIVOS, sep=";", encoding="utf-8-sig", low_memory=False)
n_bruto = len(df)
df = df[df["provincia"].notna()].copy().reset_index(drop=True)
print(f"  {n_bruto} descargados -> {len(df)} dentro de la Comunitat Valenciana")

df["nivel"] = pd.to_numeric(df["nivel_peligrosidad_patricova"], errors="coerce")

# Categoría de vulnerabilidad: para los apoyos, su subtipo; para las
# subestaciones, la propia clase.
df["clase_vuln"] = np.where(
    df["tipo_activo"] == "subestacion", "subestacion", df["tipo_apoyo"]
)
sin_clase = df[~df["clase_vuln"].isin(VULNERABILIDAD)]
if len(sin_clase):
    print(f"  AVISO: {len(sin_clase)} activos sin clase de vulnerabilidad "
          f"({sin_clase['clase_vuln'].unique()}); se les asigna 'pole'")
    df.loc[~df["clase_vuln"].isin(VULNERABILIDAD), "clase_vuln"] = "pole"

# ---------------------------------------------------------------------------
# 2. Peligrosidad por inundación, H_inund en [0, 1]
# ---------------------------------------------------------------------------
# Se construye a partir de la probabilidad anual de excedencia (el inverso del
# periodo de retorno) ponderada por el calado, y se normaliza dividiendo por el
# valor del nivel más desfavorable (25 años y calado alto). Esto conserva la
# proporción física entre niveles: el nivel 1 es 20 veces más probable que el 5,
# y el índice lo refleja, en lugar de tratar los seis niveles como una escala
# lineal 6-5-4-3-2-1, que sería arbitraria.
print("Calculando peligrosidad por inundacion...")

retorno = df["nivel"].map(NIVEL_A_RETORNO)
factor_calado = df["nivel"].map(NIVEL_A_FACTOR_CALADO)
peligro_bruto = (1.0 / retorno) * factor_calado
peligro_max = 1.0 / 25 * 1.0
df["H_inundacion"] = (peligro_bruto / peligro_max).fillna(0.0)

# Riesgo residual por proximidad, solo para los activos fuera de zona inundable.
dist = pd.to_numeric(df["distancia_zona_inundable_m"], errors="coerce")
fuera = df["nivel"].isna()
proximidad = PESO_PROXIMIDAD * np.exp(-dist / ESCALA_PROXIMIDAD_M)
df.loc[fuera, "H_inundacion"] = proximidad[fuera].fillna(0.0)

print(f"  H_inundacion: media {df['H_inundacion'].mean():.4f}, "
      f"max {df['H_inundacion'].max():.4f}, "
      f"activos con H>0: {int((df['H_inundacion'] > 0).sum())}")

# ---------------------------------------------------------------------------
# 3. Peligrosidad por viento, H_viento en [0, 1]
# ---------------------------------------------------------------------------
# La carga que el viento ejerce sobre una estructura es proporcional a la presión
# dinámica, que crece con el CUADRADO de la velocidad. Normalizar la velocidad
# linealmente subestimaría la diferencia entre un emplazamiento de 4 m/s y uno de
# 11 m/s, así que se normaliza sobre v².
print("Calculando peligrosidad por viento...")
v = pd.to_numeric(df["velocidad_viento_ms"], errors="coerce")
v2 = v ** 2
v2_min, v2_max = float(v2.min()), float(v2.max())
df["H_viento"] = ((v2 - v2_min) / (v2_max - v2_min)).fillna(0.0)
print(f"  velocidad {v.min():.2f}-{v.max():.2f} m/s -> "
      f"H_viento media {df['H_viento'].mean():.4f}")

# ---------------------------------------------------------------------------
# 4. Vulnerabilidad
# ---------------------------------------------------------------------------
df["V_inundacion"] = df["clase_vuln"].map(lambda c: VULNERABILIDAD[c]["inundacion"])
df["V_viento"] = df["clase_vuln"].map(lambda c: VULNERABILIDAD[c]["viento"])

# ---------------------------------------------------------------------------
# 5. Criticidad de red
# ---------------------------------------------------------------------------
print(f"Calculando criticidad (densidad de activos en "
      f"{RADIO_CRITICIDAD_M / 1000:.0f} km)...")
g = gpd.GeoDataFrame(
    df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326"
).to_crs(epsg=UTM_EPSG)
xy = np.c_[g.geometry.x.values, g.geometry.y.values]
arbol = cKDTree(xy)
# -1 para no contarse a sí mismo
df["densidad_5km"] = [len(v_) - 1 for v_ in arbol.query_ball_point(xy, RADIO_CRITICIDAD_M)]

# Se normaliza con el rango percentil 5-95 y se recorta, para que unos pocos
# activos en el centro de Valencia no compriman a todos los demás contra cero.
p5, p95 = np.percentile(df["densidad_5km"], [5, 95])
crit_norm = ((df["densidad_5km"] - p5) / (p95 - p5)).clip(0, 1)
df["factor_criticidad"] = CRITICIDAD_MIN + (CRITICIDAD_MAX - CRITICIDAD_MIN) * crit_norm
print(f"  densidad 5 km: p5={p5:.0f}, mediana={df['densidad_5km'].median():.0f}, "
      f"p95={p95:.0f}, max={df['densidad_5km'].max()}")

# ---------------------------------------------------------------------------
# 6. Índice compuesto
# ---------------------------------------------------------------------------
def calcular_crs(peso_inund):
    peso_v = 1.0 - peso_inund
    return 100.0 * (
        peso_inund * df["H_inundacion"] * df["V_inundacion"]
        + peso_v * df["H_viento"] * df["V_viento"]
    ) * df["factor_criticidad"]


df["CRS"] = calcular_crs(PESO_INUNDACION)
df["CRS_percentil"] = df["CRS"].rank(pct=True) * 100

print(f"\n=== CLIMATE RISK SCORE (w_inundacion={PESO_INUNDACION}, "
      f"w_viento={PESO_VIENTO}) ===")
print(f"  media {df['CRS'].mean():.2f}   mediana {df['CRS'].median():.2f}   "
      f"min {df['CRS'].min():.2f}   max {df['CRS'].max():.2f}")
for p in (50, 75, 90, 95, 99):
    print(f"    percentil {p}: {np.percentile(df['CRS'], p):.2f}")

print("\n  CRS medio por clase de activo:")
for clase, grupo in df.groupby("clase_vuln"):
    print(f"    {clase:<12} n={len(grupo):>6}   CRS medio {grupo['CRS'].mean():>6.2f}   "
          f"max {grupo['CRS'].max():>6.2f}")

print("\n  CRS medio por provincia:")
for p_, grupo in df.groupby("provincia"):
    print(f"    {p_:<11} n={len(grupo):>6}   CRS medio {grupo['CRS'].mean():>6.2f}")

# ---------------------------------------------------------------------------
# 7. Los activos de mayor riesgo
# ---------------------------------------------------------------------------
print("\n=== 15 ACTIVOS DE MAYOR RIESGO ===")
cols = ["osm_id", "clase_vuln", "provincia", "nivel", "velocidad_viento_ms",
        "densidad_5km", "CRS"]
top = df.nlargest(15, "CRS")[cols].copy()
top["nivel"] = top["nivel"].apply(lambda x: "-" if x != x else f"{int(x)}")
print(top.to_string(index=False))

# ---------------------------------------------------------------------------
# 8. Análisis de sensibilidad al reparto de pesos
# ---------------------------------------------------------------------------
# Un índice compuesto con pesos elegidos a mano solo es defendible si se muestra
# cuánto depende el resultado de esa elección. Se compara la ordenación de
# activos (correlación de Spearman) frente al reparto de referencia.
print("\n=== SENSIBILIDAD AL REPARTO DE PESOS ===")
print("  w_inund  corr. Spearman con w=0,60   coincidencia en el 5 % de mayor riesgo")
crs_ref = df["CRS"]
top5_ref = set(df.nlargest(int(0.05 * len(df)), "CRS").index)
sensibilidad = []
for w in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
    crs_w = calcular_crs(w)
    rho = crs_ref.corr(crs_w, method="spearman")
    top5_w = set(crs_w.nlargest(len(top5_ref)).index)
    solape = 100 * len(top5_ref & top5_w) / len(top5_ref)
    sensibilidad.append({"peso_inundacion": w, "spearman": round(float(rho), 4),
                         "solape_top5_pct": round(solape, 1)})
    print(f"     {w:.2f}            {rho:.4f}                      {solape:.1f} %")

# ---------------------------------------------------------------------------
# 9. Guardar
# ---------------------------------------------------------------------------
df.drop(columns=["clase_vuln"]).to_csv(SALIDA_CSV, index=False, sep=";",
                                       encoding="utf-8-sig")
with open(SALIDA_JSON, "w", encoding="utf-8") as fh:
    json.dump({
        "peso_inundacion": PESO_INUNDACION,
        "peso_viento": PESO_VIENTO,
        "vulnerabilidad": VULNERABILIDAD,
        "criticidad_min": CRITICIDAD_MIN,
        "criticidad_max": CRITICIDAD_MAX,
        "radio_criticidad_m": RADIO_CRITICIDAD_M,
        "escala_proximidad_m": ESCALA_PROXIMIDAD_M,
        "peso_proximidad": PESO_PROXIMIDAD,
        "n_activos": int(len(df)),
        "crs_media": float(df["CRS"].mean()),
        "crs_mediana": float(df["CRS"].median()),
        "crs_max": float(df["CRS"].max()),
        "percentiles": {str(p): float(np.percentile(df["CRS"], p))
                        for p in (50, 75, 90, 95, 99)},
        "sensibilidad_pesos": sensibilidad,
    }, fh, ensure_ascii=False, indent=2)

print(f"\nGenerados: {SALIDA_CSV} y {SALIDA_JSON}")
print("""
------------------------------------------------------------------------
NOTA SOBRE EL SIGUIENTE PASO (modelado supervisado)
------------------------------------------------------------------------
El CRS que acaba de calcularse es una funcion determinista y conocida de
H_inundacion, H_viento, la clase de activo y la densidad. Entrenar un Random
Forest o un XGBoost para predecir el CRS a partir de esas mismas variables no
produciria conocimiento: el modelo aprenderia la formula, y SHAP devolveria los
pesos fijados en la cabecera de este script. Seria circular.

Alternativa sin circularidad, y de mas valor: plantear como objetivo supervisado
la PREDICCION DE LA PELIGROSIDAD DE INUNDACION en ausencia de cartografia
PATRICOVA, a partir de variables que no la contengan (topografia, distancia a
cauce, pendiente, usos del suelo, densidad de red, viento). El modelo aprende
entonces algo real y transferible: como reconocer una zona inundable donde no
existe un PATRICOVA, que es exactamente el problema que abordan Wang et al. y
Watson et al. en la literatura citada. Y ahi SHAP si informa de que variables
gobiernan la inundabilidad, lo que constituye un resultado propio.
------------------------------------------------------------------------""")
