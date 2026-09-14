# ============================================================================
# clustering_subestaciones.py
# ----------------------------------------------------------------------------
# Recalcula el análisis de agrupamiento no supervisado (K-Means) de las
# subestaciones de la Comunitat Valenciana, con el conjunto de datos completo.
#
# POR QUÉ SE RECALCULA
#   La versión anterior se ejecutó sobre 439 subestaciones y 25.761 apoyos, que
#   eran los que devolvía un área de consulta de Overpass que recortaba la
#   comunidad por tres lados. Con el área corregida hay 608 subestaciones y
#   38.331 apoyos, un 38 % y un 49 % más respectivamente, y además el
#   territorio incorporado (todo el interior) tiene una densidad de red muy
#   distinta de la del litoral. Los clusters anteriores no son extrapolables.
#
# VARIABLES DE ENTRADA (las mismas que en la versión anterior, para que el
# recálculo sea comparable):
#   - latitud y longitud de la subestación
#   - densidad de apoyos de línea en un radio de 5 km
#
# UNA DIFERENCIA METODOLÓGICA DELIBERADA
#   La versión anterior barría k entre 2 y 7 y encontraba el máximo del
#   coeficiente de silhouette justo en k=7, es decir, en el extremo del
#   intervalo explorado. Un máximo en la frontera del barrido no es un máximo:
#   indica que el óptimo puede estar más allá y que no se buscó lo suficiente.
#   Aquí se barre k entre 2 y 15 para que el óptimo, si existe, quede dentro.
# ============================================================================

import os
import json

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

CSV_ACTIVOS = "activos_con_variables_climaticas.csv"
SALIDA_CSV = "subestaciones_clusters.csv"
SALIDA_JSON = "clustering_metricas.json"

UTM_EPSG = 25830
RADIO_M = 5000        # radio de 5 km para la densidad de apoyos
K_MIN, K_MAX = 2, 15
SEMILLA = 42          # fija, para que el resultado sea reproducible

# ---------------------------------------------------------------------------
# 1. Cargar y restringir al área de estudio
# ---------------------------------------------------------------------------
print("Cargando activos...")
df = pd.read_csv(CSV_ACTIVOS, sep=";", encoding="utf-8-sig", low_memory=False)

# El rectángulo de descarga desborda la comunidad; el estudio es sobre la
# Comunitat Valenciana, así que se descarta lo que cae fuera.
n_bruto = len(df)
df = df[df["provincia"].notna()].copy()
print(f"  {n_bruto} descargados -> {len(df)} dentro de la Comunitat")

subes = df[df["tipo_activo"] == "subestacion"].copy().reset_index(drop=True)
apoyos = df[df["tipo_activo"] == "apoyo"].copy()
print(f"  {len(subes)} subestaciones, {len(apoyos)} apoyos")

# ---------------------------------------------------------------------------
# 2. Densidad de apoyos en 5 km alrededor de cada subestación
# ---------------------------------------------------------------------------
# Se proyecta a UTM porque el radio está en metros: en coordenadas geográficas
# un grado de longitud no mide lo mismo que uno de latitud, y el "círculo" de
# 5 km saldría deformado.
print(f"Calculando densidad de apoyos en {RADIO_M / 1000:.0f} km...")

def a_utm(sub_df):
    g = gpd.GeoDataFrame(
        sub_df,
        geometry=gpd.points_from_xy(sub_df["lon"], sub_df["lat"]),
        crs="EPSG:4326",
    ).to_crs(epsg=UTM_EPSG)
    return np.c_[g.geometry.x.values, g.geometry.y.values]

xy_subes = a_utm(subes)
xy_apoyos = a_utm(apoyos)

# Un árbol k-d permite contar vecinos dentro de un radio sin comparar cada
# subestación con los 38.331 apoyos uno a uno.
arbol = cKDTree(xy_apoyos)
subes["densidad_apoyos_5km"] = [len(v) for v in arbol.query_ball_point(xy_subes, RADIO_M)]

print(f"  densidad: media {subes['densidad_apoyos_5km'].mean():.1f}, "
      f"mediana {subes['densidad_apoyos_5km'].median():.0f}, "
      f"min {subes['densidad_apoyos_5km'].min()}, "
      f"max {subes['densidad_apoyos_5km'].max()}")

# ---------------------------------------------------------------------------
# 3. Estandarizar las variables de entrada
# ---------------------------------------------------------------------------
# K-Means minimiza distancias euclídeas, así que una variable con rango grande
# (la densidad, de 0 a varios miles) dominaría a las coordenadas si no se
# estandarizan todas a media 0 y desviación 1.
VARIABLES = ["lat", "lon", "densidad_apoyos_5km"]
X = StandardScaler().fit_transform(subes[VARIABLES].values)

# ---------------------------------------------------------------------------
# 4. Barrido de k
# ---------------------------------------------------------------------------
print(f"\nBarriendo k de {K_MIN} a {K_MAX}...")
filas = []
for k in range(K_MIN, K_MAX + 1):
    km = KMeans(n_clusters=k, random_state=SEMILLA, n_init=10)
    etiquetas = km.fit_predict(X)
    sil = silhouette_score(X, etiquetas)
    filas.append({"k": k, "inercia": km.inertia_, "silhouette": sil})
    print(f"  k={k:>2}   inercia {km.inertia_:>9.1f}   silhouette {sil:.4f}")

metricas = pd.DataFrame(filas)
k_optimo = int(metricas.loc[metricas["silhouette"].idxmax(), "k"])
sil_optimo = float(metricas["silhouette"].max())

print(f"\n  maximo del silhouette en k={k_optimo} (silhouette = {sil_optimo:.4f})")
if k_optimo in (K_MIN, K_MAX):
    print(f"  AVISO: el maximo cae en el extremo del barrido; ampliar el intervalo")
else:
    print(f"  el maximo queda dentro del intervalo explorado: es un maximo real")

# Para contexto: qué habría dado el barrido antiguo, limitado a 2-7
antiguo = metricas[metricas["k"] <= 7]
k_antiguo = int(antiguo.loc[antiguo["silhouette"].idxmax(), "k"])
print(f"  (limitando el barrido a k<=7 como en la version anterior, "
      f"saldria k={k_antiguo} con silhouette "
      f"{antiguo['silhouette'].max():.4f})")

# ---------------------------------------------------------------------------
# 5. Ajuste final y caracterización de los clusters
# ---------------------------------------------------------------------------
km = KMeans(n_clusters=k_optimo, random_state=SEMILLA, n_init=10)
subes["cluster"] = km.fit_predict(X)

# Se renumeran los clusters de norte a sur, para que la tabla de la memoria se
# lea en un orden geográfico reconocible en lugar del orden arbitrario que
# asigna K-Means según la inicialización.
orden = (subes.groupby("cluster")["lat"].mean()
         .sort_values(ascending=False).index)
remapeo = {viejo: nuevo for nuevo, viejo in enumerate(orden, start=1)}
subes["cluster"] = subes["cluster"].map(remapeo)

resumen = (subes.groupby("cluster")
           .agg(n_subestaciones=("osm_id", "size"),
                lat_media=("lat", "mean"),
                lon_media=("lon", "mean"),
                densidad_media=("densidad_apoyos_5km", "mean"),
                inundable_pct=("dentro_zona_inundable",
                               lambda s: 100 * s.astype(str).str.lower().eq("true").mean()),
                viento_medio=("velocidad_viento_ms", "mean"))
           .round(2))

# Provincia dominante de cada cluster, útil para nombrarlos en la memoria
dominante = (subes.groupby("cluster")["provincia"]
             .agg(lambda s: s.value_counts().idxmax()))
resumen["provincia_dominante"] = dominante

print(f"\n=== CARACTERIZACION DE LOS {k_optimo} CLUSTERS (numerados norte->sur) ===")
print(resumen.to_string())

# ---------------------------------------------------------------------------
# 6. Guardar
# ---------------------------------------------------------------------------
subes.to_csv(SALIDA_CSV, index=False, sep=";", encoding="utf-8-sig")
with open(SALIDA_JSON, "w", encoding="utf-8") as fh:
    json.dump({
        "k_optimo": k_optimo,
        "silhouette_optimo": sil_optimo,
        "k_si_barrido_hasta_7": k_antiguo,
        "n_subestaciones": len(subes),
        "n_apoyos": len(apoyos),
        "radio_densidad_m": RADIO_M,
        "variables": VARIABLES,
        "semilla": SEMILLA,
        "barrido": filas,
    }, fh, ensure_ascii=False, indent=2)

print(f"\nGenerados: {SALIDA_CSV} y {SALIDA_JSON}")
