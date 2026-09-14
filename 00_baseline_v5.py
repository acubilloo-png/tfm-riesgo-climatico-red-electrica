# ============================================================================
# 00_baseline_v5.py
# ----------------------------------------------------------------------------
# Reproduce las cifras de control de la version V5 del indice, para tener un
# "antes" verificado contra el que comparar la V6.
#
# Motivo: varias de las cifras que figuran en el encargo (90,9 % de activos
# dominados por viento, k = 4 con silhouette 0,519, Catadau en el percentil 63)
# no proceden de ningun fichero de resultados presente en el repositorio; se
# calcularon en otra sesion. Antes de sustituir la variable de viento conviene
# reproducirlas desde activos_con_crs.csv y confirmar que coinciden, porque si
# el punto de partida no es el que se supone, la comparativa V5/V6 no vale.
#
# No modifica ningun fichero existente. Escribe baseline_v5.json.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd
import geopandas as gpd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

CARPETA = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(CARPETA, "activos_con_crs.csv")
PARAMS = os.path.join(CARPETA, "crs_parametros.json")
SALIDA = os.path.join(CARPETA, "baseline_v5.json")

UTM_EPSG = 25830
SEMILLA = 42
RADIO_VALIDACION_M = 6000

ENTORNOS = {
    "Catadau": (39.2333, -0.6167),
    "Quart de Poblet": (39.4806, -0.4411),
}

print("Cargando activos_con_crs.csv...")
df = pd.read_csv(CSV, sep=";", encoding="utf-8-sig", low_memory=False)
df = df[df["provincia"].notna()].copy().reset_index(drop=True)
with open(PARAMS, encoding="utf-8") as fh:
    par = json.load(fh)
w_i, w_v = par["peso_inundacion"], par["peso_viento"]
print(f"  {len(df)} activos | pesos {w_i} inundacion / {w_v} viento")

# ---------------------------------------------------------------------------
# 1. Amenaza dominante
# ---------------------------------------------------------------------------
# El CRS suma dos terminos ya ponderados por peso y vulnerabilidad. La amenaza
# dominante de un activo es la del termino mayor.
df["term_inund"] = w_i * df["H_inundacion"] * df["V_inundacion"]
df["term_viento"] = w_v * df["H_viento"] * df["V_viento"]
df["dominante"] = np.where(df["term_viento"] > df["term_inund"], "viento", "inundacion")

p95 = df["CRS"].quantile(0.95)
p99 = df["CRS"].quantile(0.99)
top5 = df[df["CRS"] >= p95]
top1 = df[df["CRS"] >= p99]


def reparto(sub, etiqueta):
    n = len(sub)
    nv = int((sub["dominante"] == "viento").sum())
    print(f"  {etiqueta:<26} n={n:>6}   viento {nv:>5} ({100 * nv / n:>5.1f} %)   "
          f"inundacion {n - nv:>5} ({100 * (n - nv) / n:>5.1f} %)")
    return {"n": n, "viento": nv, "pct_viento": round(100 * nv / n, 2)}


print("\n=== 1. AMENAZA DOMINANTE ===")
dom_total = reparto(df, "conjunto completo")
dom_top5 = reparto(top5, "5 % de mayor CRS")
dom_top1 = reparto(top1, "1 % de mayor CRS")

print(f"\n  control del encargo: 90,9 % viento en el conjunto"
      f"  -> obtenido {dom_total['pct_viento']:.1f} %")
print(f"  control del encargo: 1 de 390 en el 1 % superior"
      f"  -> obtenido {dom_top1['viento']} de {dom_top1['n']}")

# ---------------------------------------------------------------------------
# 2. Validacion en los dos entornos de la DANA
# ---------------------------------------------------------------------------
print("\n=== 2. ENTORNOS DE LA DANA (radio 6 km) ===")
g = gpd.GeoDataFrame(
    df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326"
).to_crs(epsg=UTM_EPSG)

validacion = {}
for nombre, (lat, lon) in ENTORNOS.items():
    centro = (gpd.GeoSeries([gpd.points_from_xy([lon], [lat])[0]], crs="EPSG:4326")
              .to_crs(epsg=UTM_EPSG).iloc[0])
    dentro = g.geometry.distance(centro) <= RADIO_VALIDACION_M
    sub = df[dentro.values]
    if len(sub) == 0:
        print(f"  {nombre}: sin activos en el radio")
        continue
    v_med = float(sub["velocidad_viento_ms"].mean())
    # Percentil que ocupa ese viento medio dentro del conjunto
    pct_viento = float((df["velocidad_viento_ms"] < v_med).mean() * 100)
    n_top5 = int((sub["CRS"] >= p95).sum())
    validacion[nombre] = {
        "n_activos": int(len(sub)),
        "viento_medio_ms": round(v_med, 3),
        "viento_medio_kmh": round(v_med * 3.6, 1),
        "percentil_viento": round(pct_viento, 1),
        "H_viento_medio": round(float(sub["H_viento"].mean()), 4),
        "CRS_mediano": round(float(sub["CRS"].median()), 3),
        "CRS_percentil_medio": round(float(sub["CRS_percentil"].mean()), 1),
        "n_en_top5pct": n_top5,
    }
    print(f"  {nombre}:")
    for k, val in validacion[nombre].items():
        print(f"      {k:<22} {val}")

print(f"\n  control del encargo: Catadau percentil 63 y 0 de 149 en el 5 % superior")
if "Catadau" in validacion:
    c = validacion["Catadau"]
    print(f"  -> obtenido percentil {c['percentil_viento']} y "
          f"{c['n_en_top5pct']} de {c['n_activos']}")

# ---------------------------------------------------------------------------
# 3. Agrupamiento de perfiles de amenaza
# ---------------------------------------------------------------------------
print("\n=== 3. PERFILES DE AMENAZA (K-Means sobre H_inund, H_viento, densidad) ===")
VARS = ["H_inundacion", "H_viento", "densidad_5km"]
X = StandardScaler().fit_transform(df[VARS].values)
barrido = []
for k in range(2, 16):
    km = KMeans(n_clusters=k, random_state=SEMILLA, n_init=10)
    et = km.fit_predict(X)
    sil = float(silhouette_score(X, et, sample_size=10000, random_state=SEMILLA))
    barrido.append({"k": k, "inercia": float(km.inertia_), "silhouette": round(sil, 4)})
    print(f"  k={k:>2}   silhouette {sil:.4f}")

k_opt = max(barrido, key=lambda r: r["silhouette"])["k"]
sil_opt = max(r["silhouette"] for r in barrido)
print(f"\n  optimo en k={k_opt} (silhouette {sil_opt:.4f})")
print(f"  control del encargo: k = 4 con silhouette 0,519")

km = KMeans(n_clusters=k_opt, random_state=SEMILLA, n_init=10)
df["perfil"] = km.fit_predict(X)
# Renumerar por CRS mediano decreciente, como pide el encargo
orden = df.groupby("perfil")["CRS"].median().sort_values(ascending=False).index
df["perfil"] = df["perfil"].map({v: i for i, v in enumerate(orden, start=1)})

perfiles = []
for pid, grupo in df.groupby("perfil"):
    n_sub = int((grupo["tipo_activo"] == "subestacion").sum())
    fila = {
        "perfil": int(pid),
        "n": int(len(grupo)),
        "n_subestaciones": n_sub,
        "pct_dominante_viento": round(100 * (grupo["dominante"] == "viento").mean(), 1),
        "H_inundacion_medio": round(float(grupo["H_inundacion"].mean()), 4),
        "H_viento_medio": round(float(grupo["H_viento"].mean()), 4),
        "viento_medio_ms": round(float(grupo["velocidad_viento_ms"].mean()), 3),
        "densidad_media": round(float(grupo["densidad_5km"].mean()), 1),
        "CRS_mediano": round(float(grupo["CRS"].median()), 3),
        "CRS_max": round(float(grupo["CRS"].max()), 3),
        "provincia_dominante": grupo["provincia"].value_counts().idxmax(),
    }
    perfiles.append(fila)
    print(f"  perfil {pid}: n={fila['n']:>6} ({n_sub} subest.)  "
          f"viento dom. {fila['pct_dominante_viento']:>5.1f} %  "
          f"CRS med. {fila['CRS_mediano']:>6.2f}  {fila['provincia_dominante']}")

# ---------------------------------------------------------------------------
# 4. Reparto provincial por encima del percentil 95
# ---------------------------------------------------------------------------
print("\n=== 4. REPARTO PROVINCIAL EN EL 5 % SUPERIOR ===")
prov = {}
for p_, grupo in top5.groupby("provincia"):
    prov[p_] = {"n": int(len(grupo)),
                "pct_del_top5": round(100 * len(grupo) / len(top5), 1)}
    print(f"  {p_:<11} {prov[p_]['n']:>5} ({prov[p_]['pct_del_top5']:>5.1f} % del top 5)")

# ---------------------------------------------------------------------------
# 5. Cifras de viento medio, para contraste con V50 despues
# ---------------------------------------------------------------------------
v = df["velocidad_viento_ms"].dropna()
viento = {}
for etiqueta, valor in (("min", v.min()), ("mediana", v.median()), ("media", v.mean()),
                        ("p90", v.quantile(0.90)), ("p95", v.quantile(0.95)),
                        ("p99", v.quantile(0.99)), ("max", v.max())):
    viento[etiqueta] = {"ms": round(float(valor), 3), "kmh": round(float(valor) * 3.6, 1)}
print("\n=== 5. VELOCIDAD MEDIA ANUAL (V5) ===")
for k_, val in viento.items():
    print(f"  {k_:<9} {val['ms']:>7.3f} m/s = {val['kmh']:>5.1f} km/h")

# ---------------------------------------------------------------------------
with open(SALIDA, "w", encoding="utf-8") as fh:
    json.dump({
        "n_activos": int(len(df)),
        "pesos": {"inundacion": w_i, "viento": w_v},
        "crs": {
            "mediana": round(float(df["CRS"].median()), 3),
            "media": round(float(df["CRS"].mean()), 3),
            "max": round(float(df["CRS"].max()), 3),
            "p95": round(float(p95), 3),
            "p99": round(float(p99), 3),
        },
        "amenaza_dominante": {
            "conjunto": dom_total, "top5pct": dom_top5, "top1pct": dom_top1,
        },
        "validacion_dana": validacion,
        "perfiles": {"barrido": barrido, "k_optimo": k_opt,
                     "silhouette": sil_opt, "tabla": perfiles},
        "reparto_provincial_top5": prov,
        "viento_medio": viento,
        "top20_subestaciones": (
            df[df["tipo_activo"] == "subestacion"]
            .nlargest(20, "CRS")[["osm_id", "provincia", "CRS"]]
            .round({"CRS": 3})
            .to_dict("records")
        ),
    }, fh, ensure_ascii=False, indent=2)
print(f"\nGuardado: {os.path.basename(SALIDA)}")
