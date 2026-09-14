# ============================================================================
# modelado_inundabilidad.py
# ----------------------------------------------------------------------------
# Modelado supervisado: predecir si un activo eléctrico se encuentra en zona
# inundable A PARTIR DE VARIABLES FÍSICAS DEL EMPLAZAMIENTO, sin usar la
# cartografía PATRICOVA como entrada.
#
# ----------------------------------------------------------------------------
# POR QUÉ ESTE OBJETIVO Y NO EL CLIMATE RISK SCORE
# ----------------------------------------------------------------------------
# El Climate Risk Score calculado en climate_risk_score.py es una función
# determinista y conocida de la peligrosidad, la vulnerabilidad y la densidad de
# red. Entrenar un modelo para predecirlo a partir de esas mismas variables no
# generaría conocimiento: el modelo aprendería la fórmula, y un análisis SHAP
# sobre él devolvería los pesos fijados a mano al construirla. El razonamiento
# sería circular y el resultado, vacío.
#
# El objetivo que se plantea aquí sí es un problema de aprendizaje real: dado un
# emplazamiento descrito por su altitud, su pendiente, su distancia al cauce más
# cercano y la densidad de red que lo rodea, ¿es una ubicación inundable? La
# respuesta la da PATRICOVA, que actúa como ETIQUETA pero nunca como predictor.
# El modelo resultante es transferible a territorios sin cartografía de
# inundabilidad equivalente, que es el problema práctico que abordan Wang et al.
# y Watson et al. en la literatura revisada, y el análisis SHAP informa entonces
# de qué variables físicas gobiernan la inundabilidad: un resultado propio.
#
# ----------------------------------------------------------------------------
# DOS PRECAUCIONES QUE DETERMINAN LA VALIDEZ DEL RESULTADO
# ----------------------------------------------------------------------------
# 1. FUGA DE INFORMACIÓN. Se excluyen explícitamente del conjunto de predictores
#    todas las variables derivadas de PATRICOVA. En particular
#    'distancia_zona_inundable_m', que a primera vista parece una variable
#    topográfica inocente pero se calcula CONTRA los polígonos de PATRICOVA: un
#    modelo que la reciba obtiene la respuesta casi exacta y produciría métricas
#    excelentes y completamente falsas. También se excluyen latitud, longitud y
#    provincia: con ellas el modelo memoriza dónde están las zonas inundables en
#    lugar de aprender por qué lo son, y deja de ser transferible.
#
# 2. AUTOCORRELACIÓN ESPACIAL. Los activos no son observaciones independientes:
#    hay miles de apoyos separados por decenas de metros a lo largo de una misma
#    línea, con altitud, pendiente y distancia al cauce casi idénticas. Con una
#    partición aleatoria, el conjunto de prueba contiene vecinos inmediatos de
#    los de entrenamiento y las métricas se disparan sin que el modelo haya
#    generalizado nada. Se emplea por ello validación cruzada por BLOQUES
#    ESPACIALES de 10 x 10 km: todos los activos de un bloque van juntos al mismo
#    pliegue. Se reporta además, a propósito, la métrica que daría la partición
#    aleatoria, para cuantificar el optimismo que se habría introducido.
# ============================================================================

import os
import json

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from scipy.spatial import cKDTree
from shapely.geometry import shape
from shapely.strtree import STRtree
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, KFold
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             confusion_matrix, precision_recall_curve)
from xgboost import XGBClassifier

DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))
DIR_DEM = os.path.join(DATA_DIR, "dem")
RUTA_CAUCES = os.path.join(DATA_DIR, "cauces_cv.geojson")
CSV_ACTIVOS = "activos_con_crs.csv"
SALIDA_CSV = "activos_con_topografia.csv"
SALIDA_JSON = "modelado_metricas.json"

UTM_EPSG = 25830
LADO_BLOQUE_M = 10_000      # bloques espaciales de 10 x 10 km
N_PLIEGUES = 5
SEMILLA = 42

# ---------------------------------------------------------------------------
# 1. Activos
# ---------------------------------------------------------------------------
print("Cargando activos...")
df = pd.read_csv(CSV_ACTIVOS, sep=";", encoding="utf-8-sig", low_memory=False)
df = df[df["provincia"].notna()].copy().reset_index(drop=True)
print(f"  {len(df)} activos dentro de la Comunitat Valenciana")

g = gpd.GeoDataFrame(
    df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326"
)
g_utm = g.to_crs(epsg=UTM_EPSG)
df["x_utm"] = g_utm.geometry.x.values
df["y_utm"] = g_utm.geometry.y.values

# ---------------------------------------------------------------------------
# 2. Altitud y pendiente desde el DEM
# ---------------------------------------------------------------------------
# Se procesa tesela a tesela: se carga, se calcula su pendiente completa y se
# muestrean solo los activos que caen dentro. Así nunca hay más de una tesela en
# memoria y no hacen falta miles de lecturas de ventana individuales.
#
# La pendiente se calcula sobre un DEM en coordenadas geográficas, donde el
# tamaño del píxel en metros NO es el mismo en las dos direcciones: un grado de
# longitud mide 111.320 x cos(latitud) metros y uno de latitud, 111.320. Ignorar
# esa corrección sobrestimaría la pendiente en dirección este-oeste, y a la
# latitud de la Comunitat Valenciana el error sería de un 25 % aproximadamente.
print("\nMuestreando altitud y pendiente del DEM...")

df["altitud_m"] = np.nan
df["pendiente_grados"] = np.nan

teselas = sorted(f for f in os.listdir(DIR_DEM) if f.endswith(".tif"))
if not teselas:
    raise FileNotFoundError(
        f"No hay teselas de DEM en '{DIR_DEM}'. Ejecuta descargar_topografia.py"
    )

for nombre in teselas:
    ruta = os.path.join(DIR_DEM, nombre)
    with rasterio.open(ruta) as src:
        izq, abajo, der, arriba = src.bounds
        dentro = ((df["lon"] >= izq) & (df["lon"] < der) &
                  (df["lat"] >= abajo) & (df["lat"] < arriba) &
                  df["altitud_m"].isna())
        n = int(dentro.sum())
        if n == 0:
            continue

        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan

        lat_media = (abajo + arriba) / 2.0
        paso_lon, paso_lat = abs(src.transform.a), abs(src.transform.e)
        dx = paso_lon * 111_320.0 * np.cos(np.radians(lat_media))
        dy = paso_lat * 111_320.0

        # np.gradient devuelve (d/dfila, d/dcolumna); las filas crecen hacia el
        # sur, pero para la MAGNITUD de la pendiente el signo es irrelevante.
        dz_dy, dz_dx = np.gradient(dem, dy, dx)
        pendiente = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))

        filas, cols = rasterio.transform.rowcol(
            src.transform, df.loc[dentro, "lon"].values, df.loc[dentro, "lat"].values
        )
        filas = np.clip(np.asarray(filas), 0, dem.shape[0] - 1)
        cols = np.clip(np.asarray(cols), 0, dem.shape[1] - 1)

        df.loc[dentro, "altitud_m"] = dem[filas, cols]
        df.loc[dentro, "pendiente_grados"] = pendiente[filas, cols]
        print(f"  {nombre.split('_10_')[1][:12]}: {n} activos muestreados", flush=True)

sin_dem = int(df["altitud_m"].isna().sum())
print(f"  altitud: media {df['altitud_m'].mean():.1f} m, "
      f"rango {df['altitud_m'].min():.0f}-{df['altitud_m'].max():.0f} m")
print(f"  pendiente: media {df['pendiente_grados'].mean():.2f}º, "
      f"max {df['pendiente_grados'].max():.1f}º")
if sin_dem:
    print(f"  AVISO: {sin_dem} activos sin dato de DEM")

# ---------------------------------------------------------------------------
# 3. Distancia al cauce más cercano
# ---------------------------------------------------------------------------
print("\nCalculando distancia al cauce mas cercano...")
with open(RUTA_CAUCES, encoding="utf-8-sig") as fh:
    fc = json.load(fh)
geoms = [shape(f["geometry"]) for f in fc["features"] if f.get("geometry")]
cauces = gpd.GeoSeries(geoms, crs="EPSG:4326").to_crs(epsg=UTM_EPSG)
print(f"  {len(cauces)} cauces cargados")

# Un índice espacial STRtree permite consultar el cauce más cercano a cada activo
# sin comparar contra los 83.692 uno por uno.
arbol = STRtree(list(cauces.geometry))
puntos = list(g_utm.geometry)
idx_cercano = arbol.nearest(puntos)
df["distancia_cauce_m"] = [
    p.distance(cauces.geometry.iloc[i]) for p, i in zip(puntos, idx_cercano)
]
print(f"  distancia al cauce: mediana {df['distancia_cauce_m'].median():.0f} m, "
      f"media {df['distancia_cauce_m'].mean():.0f} m, "
      f"max {df['distancia_cauce_m'].max():.0f} m")

# ---------------------------------------------------------------------------
# 4. Conjunto de predictores y variable objetivo
# ---------------------------------------------------------------------------
df["objetivo"] = (df["dentro_zona_inundable"].astype(str).str.lower() == "true").astype(int)

PREDICTORES_NUM = [
    "altitud_m",
    "pendiente_grados",
    "distancia_cauce_m",
    "densidad_5km",
    "velocidad_viento_ms",
]
# El tipo de activo entra como variables indicadoras. No es una variable física
# del emplazamiento, pero informa de la clase de infraestructura y su presencia
# permite comprobar con SHAP si el modelo se apoya indebidamente en ella.
df["clase"] = np.where(df["tipo_activo"] == "subestacion", "subestacion",
                       df["tipo_apoyo"].fillna("desconocido"))
indicadoras = pd.get_dummies(df["clase"], prefix="clase", dtype=float)
PREDICTORES = PREDICTORES_NUM + list(indicadoras.columns)

# Variables EXCLUIDAS a propósito, y el motivo. Se deja constancia en el fichero
# de métricas para que la exclusión sea auditable.
EXCLUIDAS = {
    "nivel_peligrosidad_patricova": "es la fuente de la etiqueta",
    "peligrosidad_ordinal": "derivada del nivel PATRICOVA",
    "dentro_zona_inundable": "es la etiqueta",
    "distancia_zona_inundable_m": "calculada contra los poligonos de PATRICOVA: fuga directa",
    "CRS": "contiene la peligrosidad de inundacion por construccion",
    "H_inundacion": "derivada de PATRICOVA",
    "lat": "permite memorizar la ubicacion en lugar de aprender la fisica",
    "lon": "permite memorizar la ubicacion en lugar de aprender la fisica",
    "provincia": "idem, a escala mas gruesa",
}

X = pd.concat([df[PREDICTORES_NUM], indicadoras], axis=1)
y = df["objetivo"].values
completo = X.notna().all(axis=1)
X, y = X[completo].reset_index(drop=True), y[completo.values]
df_ok = df[completo].reset_index(drop=True)
print(f"\n  {len(X)} activos con todas las variables completas")
print(f"  predictores ({len(PREDICTORES)}): {', '.join(PREDICTORES)}")
print(f"  objetivo: {y.sum()} en zona inundable ({100 * y.mean():.1f} %)")

# ---------------------------------------------------------------------------
# 5. Bloques espaciales
# ---------------------------------------------------------------------------
bx = (df_ok["x_utm"] // LADO_BLOQUE_M).astype(int)
by = (df_ok["y_utm"] // LADO_BLOQUE_M).astype(int)
bloque = (bx.astype(str) + "_" + by.astype(str))
print(f"\n  {bloque.nunique()} bloques espaciales de "
      f"{LADO_BLOQUE_M // 1000} x {LADO_BLOQUE_M // 1000} km")

def modelos():
    n_pos, n_neg = int(y.sum()), int((y == 0).sum())
    return {
        "Random Forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=5, n_jobs=-1,
            class_weight="balanced", random_state=SEMILLA),
        "XGBoost": XGBClassifier(
            n_estimators=400, max_depth=6, learning_rate=0.08,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=n_neg / n_pos,
            eval_metric="aucpr", n_jobs=-1, random_state=SEMILLA),
    }

def evaluar(particiones, etiqueta):
    """Devuelve {modelo: {roc_auc, pr_auc}} promediando los pliegues."""
    resultados = {}
    for nombre, _ in modelos().items():
        aucs, praucs = [], []
        for tr, te in particiones:
            mod = modelos()[nombre]
            mod.fit(X.iloc[tr], y[tr])
            p = mod.predict_proba(X.iloc[te])[:, 1]
            if len(np.unique(y[te])) < 2:
                continue      # pliegue sin positivos: la métrica no está definida
            aucs.append(roc_auc_score(y[te], p))
            praucs.append(average_precision_score(y[te], p))
        resultados[nombre] = {
            "roc_auc": float(np.mean(aucs)), "roc_auc_std": float(np.std(aucs)),
            "pr_auc": float(np.mean(praucs)), "pr_auc_std": float(np.std(praucs)),
            "n_pliegues": len(aucs),
        }
        print(f"  {etiqueta:<22} {nombre:<14} "
              f"ROC-AUC {np.mean(aucs):.4f} (+-{np.std(aucs):.4f})   "
              f"PR-AUC {np.mean(praucs):.4f} (+-{np.std(praucs):.4f})", flush=True)
    return resultados

print("\n=== VALIDACION CRUZADA ===")
gkf = GroupKFold(n_splits=N_PLIEGUES)
part_espacial = list(gkf.split(X, y, groups=bloque))
res_espacial = evaluar(part_espacial, "por bloques (correcta)")

kf = KFold(n_splits=N_PLIEGUES, shuffle=True, random_state=SEMILLA)
part_aleatoria = list(kf.split(X))
res_aleatoria = evaluar(part_aleatoria, "aleatoria (optimista)")

print("\n  Optimismo introducido por ignorar la autocorrelacion espacial:")
for nombre in res_espacial:
    d_roc = res_aleatoria[nombre]["roc_auc"] - res_espacial[nombre]["roc_auc"]
    d_pr = res_aleatoria[nombre]["pr_auc"] - res_espacial[nombre]["pr_auc"]
    print(f"    {nombre:<14} ROC-AUC +{d_roc:.4f}   PR-AUC +{d_pr:.4f}")

# ---------------------------------------------------------------------------
# 6. Modelo final, umbral y matriz de confusión
# ---------------------------------------------------------------------------
# Se entrena sobre el conjunto completo para el análisis SHAP, pero el umbral se
# elige con las predicciones de la validación por bloques, no con las del propio
# entrenamiento: si no, el umbral quedaría ajustado a datos ya vistos.
print("\n=== MODELO FINAL (XGBoost) ===")
pred_oof = np.zeros(len(X))
for tr, te in part_espacial:
    m = modelos()["XGBoost"]
    m.fit(X.iloc[tr], y[tr])
    pred_oof[te] = m.predict_proba(X.iloc[te])[:, 1]

prec, rec, umbrales = precision_recall_curve(y, pred_oof)
f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros_like(prec),
               where=(prec + rec) > 0)
i_mejor = int(np.argmax(f1))
umbral = float(umbrales[min(i_mejor, len(umbrales) - 1)])
print(f"  umbral que maximiza F1 (fuera de muestra): {umbral:.4f}")
print(f"    precision {prec[i_mejor]:.4f}   sensibilidad {rec[i_mejor]:.4f}   "
      f"F1 {f1[i_mejor]:.4f}")
cm = confusion_matrix(y, (pred_oof >= umbral).astype(int))
print(f"  matriz de confusion (fuera de muestra):")
print(f"    verdaderos negativos {cm[0, 0]:>6}   falsos positivos {cm[0, 1]:>6}")
print(f"    falsos negativos     {cm[1, 0]:>6}   verdaderos positivos {cm[1, 1]:>6}")

modelo_final = modelos()["XGBoost"]
modelo_final.fit(X, y)

importancias = (pd.Series(modelo_final.feature_importances_, index=X.columns)
                .sort_values(ascending=False))
print("\n  Importancia de variables (ganancia XGBoost):")
for k, v in importancias.items():
    print(f"    {k:<22} {v:.4f}")

# ---------------------------------------------------------------------------
# 7. SHAP
# ---------------------------------------------------------------------------
print("\n=== SHAP ===")
import shap
explicador = shap.TreeExplainer(modelo_final)
# Muestra aleatoria: calcular SHAP sobre 38.000 filas es innecesariamente lento y
# la distribución de contribuciones ya queda bien caracterizada con 6.000.
rng = np.random.default_rng(SEMILLA)
muestra = rng.choice(len(X), size=min(6000, len(X)), replace=False)
X_shap = X.iloc[muestra]
valores_shap = explicador.shap_values(X_shap)
np.save("shap_valores.npy", valores_shap)
X_shap.to_csv("shap_muestra.csv", index=False, sep=";", encoding="utf-8-sig")

medias_abs = (pd.Series(np.abs(valores_shap).mean(axis=0), index=X.columns)
              .sort_values(ascending=False))
print("  Contribucion media absoluta al log-odds:")
for k, v in medias_abs.items():
    print(f"    {k:<22} {v:.4f}")

# ---------------------------------------------------------------------------
# 8. Guardar
# ---------------------------------------------------------------------------
df.to_csv(SALIDA_CSV, index=False, sep=";", encoding="utf-8-sig")
with open(SALIDA_JSON, "w", encoding="utf-8") as fh:
    json.dump({
        "n_activos": int(len(X)),
        "positivos": int(y.sum()),
        "tasa_positivos": float(y.mean()),
        "predictores": list(X.columns),
        "excluidas": EXCLUIDAS,
        "lado_bloque_m": LADO_BLOQUE_M,
        "n_bloques": int(bloque.nunique()),
        "n_pliegues": N_PLIEGUES,
        "cv_espacial": res_espacial,
        "cv_aleatoria": res_aleatoria,
        "umbral_f1": umbral,
        "precision": float(prec[i_mejor]),
        "sensibilidad": float(rec[i_mejor]),
        "f1": float(f1[i_mejor]),
        "matriz_confusion": cm.tolist(),
        "importancia_xgboost": {k: float(v) for k, v in importancias.items()},
        "shap_medias_abs": {k: float(v) for k, v in medias_abs.items()},
    }, fh, ensure_ascii=False, indent=2)

print(f"\nGenerados: {SALIDA_CSV}, {SALIDA_JSON}, shap_valores.npy, shap_muestra.csv")
