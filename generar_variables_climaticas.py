# ============================================================================
# generar_variables_climaticas.py
# ----------------------------------------------------------------------------
# Qué hace: toma los dos CSV de activos (subestaciones y apoyos, tal y como los
# genera el script de Overpass) y les añade las variables de peligrosidad por
# inundación y de viento necesarias para los capítulos 4 y 5, cruzándolos con:
#   1) La cartografía PATRICOVA de peligrosidad por inundación de la
#      Comunitat Valenciana (6 niveles, vectorial)
#   2) Un GeoTIFF de velocidad media de viento (Global Wind Atlas)
#
# ----------------------------------------------------------------------------
# NOTA SOBRE LA FUENTE DE INUNDABILIDAD
# ----------------------------------------------------------------------------
# La versión anterior de este script esperaba un único shapefile de zona
# inundable (SNCZI, T=100 años). Se ha sustituido por PATRICOVA por tres
# razones:
#
#   a) Es la cartografía oficial específica de la Comunitat Valenciana, que es
#      el área de estudio de este trabajo. SNCZI es estatal y su descarga es
#      un único fichero de 1,15 GB para toda la península.
#   b) PATRICOVA no da una máscara binaria, sino SEIS niveles de peligrosidad
#      que combinan frecuencia (periodo de retorno) y calado. Eso convierte la
#      variable de inundación en ordinal en lugar de booleana, lo que es
#      sustancialmente más informativo para el Climate Risk Score y para los
#      modelos supervisados (Random Forest / XGBoost).
#   c) Se descarga por API REST (ArcGIS) sin registro ni clave, lo que mantiene
#      la reproducibilidad completa que se reivindica en el capítulo 6.
#
# Niveles PATRICOVA (según el campo d_pelig de la propia fuente):
#   Nivel 1 -> frecuencia alta  (25 años)  y calado alto (> 0,8 m)   [peor]
#   Nivel 2 -> frecuencia media (100 años) y calado alto (> 0,8 m)
#   Nivel 3 -> frecuencia alta  (25 años)  y calado bajo (< 0,8 m)
#   Nivel 4 -> frecuencia media (100 años) y calado bajo (< 0,8 m)
#   Nivel 5 -> frecuencia baja  (500 años) y calado alto (> 0,8 m)
#   Nivel 6 -> frecuencia baja  (500 años) y calado bajo (< 0,8 m)   [mejor]
#
# Es decir: número MÁS BAJO = peligrosidad MÁS ALTA. Se conserva esta
# codificación oficial, y además se genera una variable auxiliar invertida
# (peligrosidad_ordinal, de 0 a 6, donde 6 es lo más peligroso) que es la que
# conviene usar como predictor, para que el modelo no interprete al revés la
# relación monótona.
#
# ----------------------------------------------------------------------------
# Instalación previa (una sola vez):
#   pip install pandas geopandas shapely rasterio pyproj
#
# Uso:
#   1. Los datos de entrada ya deben estar descargados en "data/":
#        data/patricova/peligrosidad_1.geojson ... peligrosidad_6.geojson
#        data/wind_speed_50m.tif
#   2. Ejecuta: python generar_variables_climaticas.py
#   3. Se generará "activos_con_variables_climaticas.csv", que es el fichero
#      de partida para el Climate Risk Score, Random Forest, XGBoost y SHAP.
# ============================================================================

import os
import glob

import pandas as pd
import geopandas as gpd
import rasterio

# ---------------------------------------------------------------------------
# 0. RUTAS Y CONSTANTES
# ---------------------------------------------------------------------------
SUBESTACIONES_CSV = "subestaciones_comunidad_valenciana.csv"
APOYOS_CSV = "apoyos_electricos_comunidad_valenciana.csv"

# Las capas geográficas de partida (raster de viento, PATRICOVA, provincias) pesan
# unos 80 MB y viven FUERA de la carpeta del proyecto, que está en OneDrive: si
# se guardan dentro, OneDrive sincroniza decenas de miles de ficheros cada vez
# que se regeneran, y consume cuota sin ninguna ventaja (son datos públicos,
# redescargables en cualquier momento). Se puede cambiar la ubicación sin tocar
# el código definiendo la variable de entorno TFM_DATA_DIR.
DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))

PATRICOVA_DIR = os.path.join(DATA_DIR, "patricova")
WIND_RASTER_PATH = os.path.join(DATA_DIR, "wind_speed_50m.tif")
PROVINCIAS_GEOJSON = os.path.join(DATA_DIR, "provincias_cv.geojson")
OUTPUT_CSV = "activos_con_variables_climaticas.csv"

# ETRS89 / UTM zona 30N: sistema proyectado válido para toda la España
# peninsular. Es imprescindible proyectar antes de medir distancias, porque en
# coordenadas geográficas (lat/lon) las distancias no se miden en metros.
UTM_EPSG = 25830


# ---------------------------------------------------------------------------
# 1. Cargar los CSV de activos
# ---------------------------------------------------------------------------
def cargar_csv_activos(path, tipo_activo):
    """
    Lee uno de los CSV generados por los scripts de Overpass.

    Los CSV se guardan "a la española": separador de columnas ';' y coma
    decimal en las coordenadas ("39,4630808"). Aquí se convierten a float con
    punto decimal para poder operar con ellas.
    """
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    df["lat"] = df["latitud"].astype(str).str.replace(",", ".").astype(float)
    df["lon"] = df["longitud"].astype(str).str.replace(",", ".").astype(float)
    df["tipo_activo"] = tipo_activo
    return df


print("Cargando subestaciones y apoyos...")
subestaciones = cargar_csv_activos(SUBESTACIONES_CSV, "subestacion")
apoyos = cargar_csv_activos(APOYOS_CSV, "apoyo")

activos = pd.concat([subestaciones, apoyos], ignore_index=True, sort=False)
print(f"Total de activos: {len(activos)} "
      f"({len(subestaciones)} subestaciones, {len(apoyos)} apoyos)")

# Comprobación de cobertura: si los dos conjuntos no cubren la misma extensión
# geográfica, cualquier estadística que los compare está sesgada. Este aviso
# existe porque una versión anterior del script de apoyos usaba un bounding box
# recortado que dejaba fuera toda la provincia de Alicante.
for nombre, sub in (("subestaciones", subestaciones), ("apoyos", apoyos)):
    print(f"  extensión {nombre}: "
          f"lat {sub['lat'].min():.4f}..{sub['lat'].max():.4f}  "
          f"lon {sub['lon'].min():.4f}..{sub['lon'].max():.4f}")

# GeoDataFrame en WGS84 (EPSG:4326, el lat/lon estándar del GPS y de OSM) y
# copia proyectada a UTM para los cálculos métricos.
gdf = gpd.GeoDataFrame(
    activos,
    geometry=gpd.points_from_xy(activos["lon"], activos["lat"]),
    crs="EPSG:4326",
)
gdf_utm = gdf.to_crs(epsg=UTM_EPSG)


# ---------------------------------------------------------------------------
# 2. Variables de inundación a partir de PATRICOVA
# ---------------------------------------------------------------------------
print("Cargando cartografía PATRICOVA de peligrosidad por inundación...")

ficheros = sorted(glob.glob(os.path.join(PATRICOVA_DIR, "peligrosidad_*.geojson")))
if not ficheros:
    raise FileNotFoundError(
        f"No se han encontrado GeoJSON de PATRICOVA en '{PATRICOVA_DIR}'."
    )

capas = []
for f in ficheros:
    capa = gpd.read_file(f)
    # n_pelig ya viene en los atributos de la fuente, pero se fuerza a entero
    # por si algún fichero lo trae como texto.
    capa["n_pelig"] = capa["n_pelig"].astype(int)
    capas.append(capa[["n_pelig", "d_pelig", "retorno", "calado", "geometry"]])
    print(f"  {os.path.basename(f)}: {len(capa)} polígonos, "
          f"nivel {capa['n_pelig'].iloc[0]}")

patricova = gpd.GeoDataFrame(
    pd.concat(capas, ignore_index=True), crs=capas[0].crs
)
patricova_utm = patricova.to_crs(epsg=UTM_EPSG)
print(f"  total: {len(patricova_utm)} polígonos de peligrosidad")

# --- 2a. Nivel de peligrosidad en el que cae cada activo -------------------
# Un activo puede caer dentro de varios polígonos solapados (por ejemplo, dentro
# de la lámina de 500 años Y de la de 25 años). En ese caso se conserva el nivel
# MÁS DESFAVORABLE, que en la codificación PATRICOVA es el número más bajo.
print("Asignando nivel de peligrosidad por inundación...")
union = gpd.sjoin(
    gdf_utm[["geometry"]],
    patricova_utm[["n_pelig", "geometry"]],
    how="left",
    predicate="within",
)
# Si un punto cayó en varios polígonos, sjoin devuelve varias filas: se agrupa
# por el índice original del activo y se toma el mínimo.
nivel = union.groupby(level=0)["n_pelig"].min()
gdf_utm["nivel_peligrosidad_patricova"] = nivel

# Variable booleana equivalente a la de la versión anterior del script, para
# mantener compatibilidad con lo ya escrito en la memoria.
gdf_utm["dentro_zona_inundable"] = gdf_utm["nivel_peligrosidad_patricova"].notna()

# Variable ordinal orientada "a más alto, más peligroso" (0 = fuera de zona
# inundable, 6 = peligrosidad máxima). Es la que conviene pasar al modelo.
gdf_utm["peligrosidad_ordinal"] = (
    7 - gdf_utm["nivel_peligrosidad_patricova"]
).fillna(0).astype(int)

# --- 2b. Distancia a la zona inundable más cercana -------------------------
# sjoin_nearest calcula, para cada activo, el polígono de peligrosidad más
# próximo y la distancia en metros (porque ambas capas están en UTM). Es mucho
# más rápido que unir todos los polígonos y medir contra la geometría fusionada,
# porque usa un índice espacial en lugar de comparar uno contra todos.
print("Calculando distancia a la zona inundable más cercana...")
cercano = gpd.sjoin_nearest(
    gdf_utm[["geometry"]],
    patricova_utm[["geometry"]],
    how="left",
    distance_col="dist_m",
)
gdf_utm["distancia_zona_inundable_m"] = (
    cercano.groupby(level=0)["dist_m"].min().round(1)
)


# --- 2c. Provincia de cada activo -----------------------------------------
# Se asigna por intersección geométrica con los polígonos provinciales del ICV,
# no por franjas de latitud. Importa porque las tres provincias no están
# igualmente cubiertas en OpenStreetMap, y ese sesgo hay que poder cuantificarlo
# y declararlo como limitación (ver la discusión sobre completitud de la
# información geográfica voluntaria en el capítulo 6).
if os.path.exists(PROVINCIAS_GEOJSON):
    print("Asignando provincia por geometría...")
    prov = gpd.read_file(PROVINCIAS_GEOJSON).to_crs(epsg=UTM_EPSG)
    # Los nombres vienen en formato bilingüe ("València/Valencia"); se queda la
    # forma en castellano, que es la usada en la redacción de la memoria.
    prov["provincia"] = prov["nombre"].str.split("/").str[-1]
    unido = gpd.sjoin(
        gdf_utm[["geometry"]],
        prov[["provincia", "geometry"]],
        how="left",
        predicate="within",
    )
    gdf_utm["provincia"] = unido.groupby(level=0)["provincia"].first()
    fuera = int(gdf_utm["provincia"].isna().sum())
    if fuera:
        # Los activos sin provincia son los que caen dentro del bounding box de
        # descarga pero fuera de la Comunitat Valenciana (por ejemplo en Teruel,
        # Cuenca, Albacete o Murcia, o mar adentro).
        print(f"  aviso: {fuera} activos caen fuera de la Comunitat Valenciana")
else:
    print(f"  (sin '{PROVINCIAS_GEOJSON}': no se asigna provincia)")


# ---------------------------------------------------------------------------
# 3. Variable de viento: velocidad media en la ubicación de cada activo
# ---------------------------------------------------------------------------
print("Muestreando velocidad de viento en cada activo...")
with rasterio.open(WIND_RASTER_PATH) as src:
    # El raster del Global Wind Atlas se sirve en WGS84, así que se muestrea
    # con las coordenadas lat/lon originales, no con las UTM. Si en el futuro se
    # usara un raster en otro CRS, habría que reproyectar los puntos antes.
    puntos = gdf.to_crs(src.crs) if src.crs and src.crs.to_epsg() != 4326 else gdf
    coords = [(geom.x, geom.y) for geom in puntos.geometry]
    nodata = src.nodata
    valores = []
    for v in src.sample(coords):
        valor = float(v[0])
        # Fuera del área cubierta por el raster, rasterio devuelve el valor
        # nodata; se convierte a NaN para que no contamine las medias.
        valores.append(float("nan") if nodata is not None and valor == nodata else valor)

gdf_utm["velocidad_viento_ms"] = [round(v, 3) if v == v else v for v in valores]


# ---------------------------------------------------------------------------
# 4. Guardar el resultado
# ---------------------------------------------------------------------------
resultado = gdf_utm.drop(columns="geometry")
resultado.to_csv(OUTPUT_CSV, index=False, sep=";", encoding="utf-8-sig")

print(f"\nListo. Fichero generado: {OUTPUT_CSV}  ({len(resultado)} filas)")
print(f"  - Activos en zona inundable: "
      f"{int(gdf_utm['dentro_zona_inundable'].sum())} de {len(gdf_utm)} "
      f"({100 * gdf_utm['dentro_zona_inundable'].mean():.1f} %)")
print("  - Reparto por nivel de peligrosidad PATRICOVA:")
reparto = (
    gdf_utm["nivel_peligrosidad_patricova"]
    .value_counts(dropna=False)
    .sort_index()
)
for nivel_val, n in reparto.items():
    etiqueta = "fuera de zona inundable" if nivel_val != nivel_val else f"nivel {int(nivel_val)}"
    print(f"      {etiqueta:<26} {n:>7}")
print(f"  - Velocidad de viento media: {gdf_utm['velocidad_viento_ms'].mean():.2f} m/s "
      f"(min {gdf_utm['velocidad_viento_ms'].min():.2f}, "
      f"max {gdf_utm['velocidad_viento_ms'].max():.2f})")

if "provincia" in gdf_utm.columns:
    print("  - Reparto por provincia y tipo de activo:")
    tabla = pd.crosstab(
        gdf_utm["provincia"].fillna("fuera de la C. Valenciana"),
        gdf_utm["tipo_activo"],
        margins=True,
        margins_name="TOTAL",
    )
    print(tabla.to_string().replace("\n", "\n      "))

    # Recuento restringido a la comunidad. Es el que debe coincidir con lo que
    # Overpass devuelve consultando por el ÁREA administrativa (relación OSM
    # 349043): 609 subestaciones y 38.332 apoyos. Si coincide, queda demostrado
    # que el rectángulo de consulta ya no recorta territorio y que el recorte
    # geométrico posterior funciona.
    dentro = gdf_utm[gdf_utm["provincia"].notna()]
    n_sub = int((dentro["tipo_activo"] == "subestacion").sum())
    n_apo = int((dentro["tipo_activo"] == "apoyo").sum())
    print("\n  - VALIDACION contra el recuento por area de Overpass:")
    print(f"      subestaciones dentro de la C.V.: {n_sub:>6}   "
          f"(Overpass por area: 609)   {'COINCIDE' if n_sub == 609 else 'DISCREPA'}")
    print(f"      apoyos dentro de la C.V.:        {n_apo:>6}   "
          f"(Overpass por area: 38332) {'COINCIDE' if n_apo == 38332 else 'DISCREPA'}")

if "tipo_apoyo" in gdf_utm.columns:
    print("\n  - Subtipo de apoyo (solo dentro de la C. Valenciana):")
    dentro = gdf_utm[(gdf_utm["provincia"].notna()) &
                     (gdf_utm["tipo_activo"] == "apoyo")]
    for subtipo, n in dentro["tipo_apoyo"].value_counts().items():
        print(f"      {subtipo:<10} {n:>7}  ({100 * n / len(dentro):.1f} %)")
