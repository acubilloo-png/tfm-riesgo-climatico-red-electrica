# ============================================================================
# 04_crs_v6.py
# ----------------------------------------------------------------------------
# Tareas 3, 4 y 5 del encargo: bajada de escala del campo de extremos, nueva
# definicion de la peligrosidad por viento y recalculo del indice compuesto.
#
# No sobreescribe nada: escribe activos_con_crs_v6.csv, crs_parametros_v6.json,
# clustering_perfiles_v6.json, perfiles_amenaza_v6.csv y comparativa_v5_v6.json.
#
# ----------------------------------------------------------------------------
# TAREA 3: BAJADA DE ESCALA A LA RESOLUCION DEL GLOBAL WIND ATLAS
# ----------------------------------------------------------------------------
# El campo de extremos esta a 0,25 grados (unos 21 x 28 km a esta latitud) y
# sobre la Comunitat solo hay 56 celdas con activos, de modo que asignar a cada
# activo el valor bruto de su celda dejaria a miles de activos con un valor
# identico. El Global Wind Atlas resuelve 250 m, asi que se redistribuye dentro
# de cada celda segun la exposicion local que el GWA si resuelve:
#
#     V50_activo = V50_celda x ( v_GWA_activo / v_GWA_medio_de_la_celda )
#
# SUPUESTO, y hay que decirlo: esto asume que el factor entre la velocidad media
# y el extremo de retorno a 50 anos es espacialmente uniforme dentro de la celda.
# No es una verdad fisica; es una hipotesis de trabajo razonable, porque tanto la
# media como el extremo responden a la misma exposicion orografica y de
# rugosidad. Se calcula tambien la variante SIN escalar, para poder separar su
# efecto.
#
# Una precaucion propia, no pedida en el encargo: la razon se acota al intervalo
# [0,5 , 2,0]. Sin acotarla, un activo con viento medio muy bajo dentro de una
# celda ventosa recibiria un V50 absurdamente pequeno, y al reves; con 56 celdas
# y hasta miles de activos por celda, las colas de la razon son ruido de
# interpolacion del GWA, no senal.
#
# ----------------------------------------------------------------------------
# TAREA 4: PELIGROSIDAD POR VIENTO CONTRA REFERENCIA FISICA ABSOLUTA
# ----------------------------------------------------------------------------
#     H_viento = min( 1 , ( V50_activo / V_basica )^2 )      V_basica = 29 m/s
#
# Frente a la normalizacion min-max anterior, esto cambia tres cosas:
#   1. El valor pasa a ser interpretable por si mismo: H = 1 significa que la
#      velocidad de retorno a 50 anos iguala la velocidad basica de diseno de la
#      zona C del CTE DB-SE-AE, la mas desfavorable de Espana.
#   2. El indice deja de depender del rango observado en el area de estudio, con
#      lo que se vuelve comparable entre comunidades autonomas. Eso levanta una
#      limitacion declarada del trabajo.
#   3. Deja de forzarse que el activo mas ventoso del area valga 1 aunque su
#      viento sea inocuo, que es lo que comprimia la rama eolica.
# El cuadrado se conserva porque la carga estructural va con la presion dinamica.
#
# La rama de inundacion no se toca: mismos pesos, misma matriz de vulnerabilidad
# y mismo factor de criticidad que en la version V5.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

CARPETA = os.path.dirname(os.path.abspath(__file__))
CSV_V5 = os.path.join(CARPETA, "activos_con_crs.csv")
NPZ_V50 = os.path.join(CARPETA, "cerra_v50.npz")
PARAMS_V5 = os.path.join(CARPETA, "crs_parametros.json")
BASELINE = os.path.join(CARPETA, "baseline_v5.json")

SAL_CSV = os.path.join(CARPETA, "activos_con_crs_v6.csv")
SAL_PARAMS = os.path.join(CARPETA, "crs_parametros_v6.json")
SAL_PERFILES_JSON = os.path.join(CARPETA, "clustering_perfiles_v6.json")
SAL_PERFILES_CSV = os.path.join(CARPETA, "perfiles_amenaza_v6.csv")
SAL_COMPARATIVA = os.path.join(CARPETA, "comparativa_v5_v6.json")

V_BASICA = 29.0          # m/s, zona C del CTE DB-SE-AE
RAZON_MIN, RAZON_MAX = 0.5, 2.0
SEMILLA = 42

# ---------------------------------------------------------------------------
print("Cargando la version V5...")
df = pd.read_csv(CSV_V5, sep=";", encoding="utf-8-sig", low_memory=False)
df = df[df["provincia"].notna()].copy().reset_index(drop=True)
with open(PARAMS_V5, encoding="utf-8") as fh:
    par5 = json.load(fh)
with open(BASELINE, encoding="utf-8") as fh:
    base5 = json.load(fh)
# ---------------------------------------------------------------------------
# REPARTO DE PESOS ENTRE AMENAZAS
# ---------------------------------------------------------------------------
# La version V5 empleaba 0,60 para inundacion y 0,40 para viento. Se reajusta a
# 0,70 / 0,30 por una razon de estatus probatorio, no de conveniencia: la
# peligrosidad por inundacion cuantifica una amenaza materializada en el area de
# estudio, con el 10 % de los activos en zona inundable cartografiada y danos
# reales en octubre de 2024, mientras que la eolica cuantifica propension
# relativa POR DEBAJO del umbral de dano, ya que ningun activo de la comunidad
# alcanza la velocidad basica de diseno del CTE. Asignar el 40 % del indice a
# diferencias situadas todas bajo el umbral de solicitacion sobrestimaba el peso
# de esa rama.
#
# El reajuste se decidio comparando las consecuencias de tres repartos:
#   0,60  la cola extrema conserva 12 activos de viento, que hay que explicar
#         como excepciones
#   0,70  la cola extrema pasa a ser integramente de inundacion, y el perfil de
#         48 subestaciones de viento puro SOBREVIVE
#   0,80  el perfil de viento puro DESAPARECE, con lo que la rama eolica deja de
#         aportar salida operativa alguna
# Se adopta 0,70 porque es el mayor peso de inundacion compatible con conservar
# la separacion de mecanismos, que es lo que la rama eolica aporta. La ordenacion
# de activos apenas cambia respecto a 0,60 (Spearman 0,9899).
PESO_INUNDACION = 0.70
w_i, w_v = PESO_INUNDACION, round(1.0 - PESO_INUNDACION, 2)
print(f"  {len(df)} activos | pesos {w_i} / {w_v}  "
      f"(la V5 usaba {par5['peso_inundacion']} / {par5['peso_viento']})")

z = np.load(NPZ_V50, allow_pickle=True)
df["V50_bruto_ms"] = z["activos_v50_bruto"]
celda = z["activos_celda"]
print(f"  V50 bruto: mediana {df['V50_bruto_ms'].median():.2f} m/s en "
      f"{len(np.unique(celda))} celdas")

# ---------------------------------------------------------------------------
# TAREA 3
# ---------------------------------------------------------------------------
print("\n=== TAREA 3: bajada de escala por exposicion del GWA ===")
gwa = df["velocidad_viento_ms"].values
media_celda = pd.Series(gwa).groupby(celda).transform("mean").values
razon = np.divide(gwa, media_celda, out=np.ones_like(gwa), where=media_celda > 0)
n_acotados = int(((razon < RAZON_MIN) | (razon > RAZON_MAX)).sum())
razon_acot = np.clip(razon, RAZON_MIN, RAZON_MAX)
df["razon_exposicion"] = razon_acot
df["V50_ms"] = df["V50_bruto_ms"].values * razon_acot

print(f"  razon de exposicion: mediana {np.median(razon):.3f}, "
      f"rango {razon.min():.3f}-{razon.max():.3f}")
print(f"  acotados a [{RAZON_MIN}, {RAZON_MAX}]: {n_acotados} activos "
      f"({100 * n_acotados / len(df):.2f} %)")
print(f"  V50 escalado: min {df['V50_ms'].min():.2f}  "
      f"mediana {df['V50_ms'].median():.2f}  max {df['V50_ms'].max():.2f} m/s")
print(f"  V50 bruto:    min {df['V50_bruto_ms'].min():.2f}  "
      f"mediana {df['V50_bruto_ms'].median():.2f}  "
      f"max {df['V50_bruto_ms'].max():.2f} m/s")

# ---------------------------------------------------------------------------
# TAREA 4
# ---------------------------------------------------------------------------
print("\n=== TAREA 4: nueva peligrosidad por viento ===")

# ---------------------------------------------------------------------------
# Variante adoptada: la decide el script 07 con datos observados, no el criterio
# ---------------------------------------------------------------------------
# El escalado multiplicativo por exposicion abre el V50 hasta 45,6 m/s. Contrastado
# contra las rachas observadas de AEMET (1985-2024, racha maxima registrada 39,2
# m/s), ese valor implica rachas de 63,9 m/s en 986 activos, superiores a la
# maxima jamas medida en el territorio: fisicamente imposibles, porque el viento
# sostenido nunca supera la racha del mismo episodio. La variante sin escalar no
# produce ningun valor imposible.
#
# Se adopta por tanto la BRUTA y se conserva la escalada como analisis de
# sensibilidad. La contrapartida, que hay que declarar: el campo de extremos queda
# resuelto a 0,25 grados, de modo que dentro de cada celda la peligrosidad eolica
# es constante y las diferencias de indice provienen solo de la vulnerabilidad y
# de la criticidad. Es menos resolucion, pero es la resolucion que el dato tiene.
RUTA_CALIBRACION = os.path.join(CARPETA, "calibracion_v50.json")
if os.path.exists(RUTA_CALIBRACION):
    with open(RUTA_CALIBRACION, encoding="utf-8") as fh:
        calib = json.load(fh)
    ADOPTADA = calib["decision"]
    print(f"  variante adoptada segun la calibracion (script 07): {ADOPTADA}")
    print(f"    motivo: {calib['motivo'][:120]}")
else:
    ADOPTADA = "escalada"
    calib = None
    print("  AVISO: sin calibracion disponible; se usa la escalada "
          "provisionalmente. Ejecuta 07_calibrar_v50.py")

COL_V50 = "V50_bruto_ms" if ADOPTADA == "bruta" else "V50_ms"
COL_V50_ALT = "V50_ms" if ADOPTADA == "bruta" else "V50_bruto_ms"

df["H_viento_nuevo"] = np.minimum(1.0, (df[COL_V50] / V_BASICA) ** 2)
df["H_viento_alternativa"] = np.minimum(1.0, (df[COL_V50_ALT] / V_BASICA) ** 2)
# Se conserva el nombre historico para no romper scripts que lo usaran
df["H_viento_bruto"] = np.minimum(1.0, (df["V50_bruto_ms"] / V_BASICA) ** 2)

# Variante de control: misma variable V50 adoptada pero con la normalizacion
# min-max antigua, para poder separar el efecto de cambiar de VARIABLE del efecto
# de cambiar de NORMALIZACION, que es lo que pide la tarea 4 del encargo.
v2 = df[COL_V50] ** 2
df["H_viento_minmax"] = (v2 - v2.min()) / (v2.max() - v2.min())

print(f"  H_viento V5 (min-max sobre viento medio): "
      f"mediana {df['H_viento'].median():.4f}")
print(f"  H_viento V6 (absoluta sobre V50):          "
      f"mediana {df['H_viento_nuevo'].median():.4f}  "
      f"(x{df['H_viento_nuevo'].median() / df['H_viento'].median():.1f})")
print(f"  H_viento control (min-max sobre V50):      "
      f"mediana {df['H_viento_minmax'].median():.4f}")
print(f"  activos con H_viento_nuevo = 1 (V50 >= {V_BASICA:.0f} m/s): "
      f"{int((df['H_viento_nuevo'] >= 1).sum())}")

# ---------------------------------------------------------------------------
# TAREA 5.1: CRS v6 y sensibilidad
# ---------------------------------------------------------------------------
print("\n=== TAREA 5.1: CRS v6 ===")


def calcular_crs(peso_inund, columna_viento):
    peso_v = 1.0 - peso_inund
    return 100.0 * (
        peso_inund * df["H_inundacion"] * df["V_inundacion"]
        + peso_v * df[columna_viento] * df["V_viento"]
    ) * df["factor_criticidad"]


df["CRS_v6"] = calcular_crs(w_i, "H_viento_nuevo")
df["CRS_percentil_v6"] = df["CRS_v6"].rank(pct=True) * 100
df["CRS_v6_minmax"] = calcular_crs(w_i, "H_viento_minmax")
df["CRS_v6_alternativa"] = calcular_crs(w_i, "H_viento_alternativa")
df["CRS_v6_bruto"] = calcular_crs(w_i, "H_viento_bruto")

for etiqueta, col in (("V5 (viento medio)", "CRS"),
                      (f"V6 ({ADOPTADA}, absoluta)", "CRS_v6"),
                      ("control (V50, min-max)", "CRS_v6_minmax"),
                      ("sensibilidad (otra variante)", "CRS_v6_alternativa")):
    s = df[col]
    print(f"  {etiqueta:<24} mediana {s.median():>6.2f}  media {s.mean():>6.2f}  "
          f"p95 {s.quantile(0.95):>6.2f}  p99 {s.quantile(0.99):>6.2f}  "
          f"max {s.max():>6.2f}")

print("\n  sensibilidad al reparto de pesos (V6):")
ref = df["CRS_v6"]
n_top5 = int(0.05 * len(df))
top5_ref = set(ref.nlargest(n_top5).index)
sensibilidad = []
for w in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
    crs_w = calcular_crs(w, "H_viento_nuevo")
    rho = float(ref.corr(crs_w, method="spearman"))
    solape = 100 * len(top5_ref & set(crs_w.nlargest(n_top5).index)) / n_top5
    sensibilidad.append({"peso_inundacion": w, "spearman": round(rho, 4),
                         "solape_top5_pct": round(solape, 1)})
    print(f"    w_inund {w:.2f}   Spearman {rho:.4f}   solape {solape:.1f} %")

# ---------------------------------------------------------------------------
# TAREA 5.4: amenaza dominante
# ---------------------------------------------------------------------------
print("\n=== TAREA 5.4: amenaza dominante ===")
df["term_inund"] = w_i * df["H_inundacion"] * df["V_inundacion"]
df["term_viento_v6"] = w_v * df["H_viento_nuevo"] * df["V_viento"]
df["dominante_v6"] = np.where(df["term_viento_v6"] > df["term_inund"],
                              "viento", "inundacion")

# La dominancia de la version V5 debe calcularse con LOS PESOS DE LA V5, no con
# los nuevos: el reparto forma parte de la definicion de cada version, y mezclarlo
# daria una V5 que nunca existio.
w_i5, w_v5 = par5["peso_inundacion"], par5["peso_viento"]
df["term_inund_v5"] = w_i5 * df["H_inundacion"] * df["V_inundacion"]
df["term_viento_v5"] = w_v5 * df["H_viento"] * df["V_viento"]
df["dominante_v5"] = np.where(df["term_viento_v5"] > df["term_inund_v5"],
                              "viento", "inundacion")

# Variante intermedia: LA VARIABLE NUEVA CON LOS PESOS ANTIGUOS. Sin ella, la
# comparacion V5 -> V6 mezcla dos cambios (la variable de peligrosidad y el
# reparto de pesos) y no se puede atribuir la mejora a ninguno de los dos.
df["CRS_v6_pesos_v5"] = 100.0 * (
    df["H_inundacion"] * df["V_inundacion"] * w_i5
    + df["H_viento_nuevo"] * df["V_viento"] * w_v5) * df["factor_criticidad"]
df["term_viento_v6w5"] = w_v5 * df["H_viento_nuevo"] * df["V_viento"]
df["dominante_v6w5"] = np.where(df["term_viento_v6w5"] > df["term_inund_v5"],
                                "viento", "inundacion")

dominante = {}
for etiqueta, umbral in (("conjunto", 0.0), ("top5pct", 0.95), ("top1pct", 0.99)):
    for version, col_crs, col_dom in (("v5", "CRS", "dominante_v5"),
                                      ("v6w5", "CRS_v6_pesos_v5", "dominante_v6w5"),
                                      ("v6", "CRS_v6", "dominante_v6")):
        sub = df if umbral == 0 else df[df[col_crs] >= df[col_crs].quantile(umbral)]
        nv = int((sub[col_dom] == "viento").sum())
        dominante[f"{etiqueta}_{version}"] = {
            "n": int(len(sub)), "viento": nv,
            "pct_viento": round(100 * nv / len(sub), 2)}
    a = dominante[f"{etiqueta}_v5"]
    m = dominante[f"{etiqueta}_v6w5"]
    b = dominante[f"{etiqueta}_v6"]
    print(f"  {etiqueta:<10} V5 (media, 0,60): {a['pct_viento']:>5.1f} % "
          f"({a['viento']}/{a['n']})   solo variable nueva (0,60): "
          f"{m['pct_viento']:>5.1f} % ({m['viento']}/{m['n']})   "
          f"V6 (variable nueva, 0,70): {b['pct_viento']:>5.1f} % "
          f"({b['viento']}/{b['n']})")

# ---------------------------------------------------------------------------
# TAREA 5.3: reparto provincial y subestaciones criticas
# ---------------------------------------------------------------------------
print("\n=== TAREA 5.3: reparto provincial en el 5 % superior ===")
provincial = {}
for version, col in (("v5", "CRS"), ("v6", "CRS_v6")):
    top = df[df[col] >= df[col].quantile(0.95)]
    provincial[version] = {p: {"n": int(len(g)),
                               "pct": round(100 * len(g) / len(top), 1)}
                           for p, g in top.groupby("provincia")}
    detalle = "  ".join(f"{p} {v['n']} ({v['pct']} %)"
                        for p, v in provincial[version].items())
    print(f"  {version}: {detalle}")

subs = df[df["tipo_activo"] == "subestacion"]
top20_v5 = subs.nlargest(20, "CRS")[["osm_id", "provincia", "CRS"]]
top20_v6 = subs.nlargest(20, "CRS_v6")[["osm_id", "provincia", "CRS_v6"]]
entran = set(top20_v6["osm_id"]) - set(top20_v5["osm_id"])
salen = set(top20_v5["osm_id"]) - set(top20_v6["osm_id"])
print(f"\n  top 20 de subestaciones: {len(entran)} entran, {len(salen)} salen "
      f"({20 - len(entran)} se mantienen)")

# ---------------------------------------------------------------------------
# TAREA 5.2: perfiles de amenaza, en los dos subconjuntos
# ---------------------------------------------------------------------------
print("\n=== TAREA 5.2: perfiles de amenaza ===")
VARS = ["H_inundacion", "H_viento_nuevo", "densidad_5km"]
perfiles_salida = {}
tablas = []

for etiqueta, sub in (("subestaciones", df[df["tipo_activo"] == "subestacion"]),
                      ("todos_los_activos", df)):
    print(f"\n  --- {etiqueta} (n={len(sub)}) ---")
    X = StandardScaler().fit_transform(sub[VARS].values)
    barrido = []
    for k in range(2, 16):
        km = KMeans(n_clusters=k, random_state=SEMILLA, n_init=10)
        et = km.fit_predict(X)
        if len(sub) <= 5000:
            sil = float(silhouette_score(X, et))
        else:
            sil = float(silhouette_score(X, et, sample_size=10000,
                                         random_state=SEMILLA))
        barrido.append({"k": k, "inercia": float(km.inertia_),
                        "silhouette": round(sil, 4)})
    k_opt = max(barrido, key=lambda r: r["silhouette"])["k"]
    sil_opt = max(r["silhouette"] for r in barrido)
    print(f"    optimo k={k_opt} (silhouette {sil_opt:.4f})")
    if k_opt in (2, 15):
        print(f"    AVISO: el optimo cae en el extremo del barrido")

    km = KMeans(n_clusters=k_opt, random_state=SEMILLA, n_init=10)
    s = sub.copy()
    s["perfil"] = km.fit_predict(X)
    orden = s.groupby("perfil")["CRS_v6"].median().sort_values(ascending=False).index
    s["perfil"] = s["perfil"].map({v: i for i, v in enumerate(orden, start=1)})

    # Se guarda la asignacion en el conjunto principal para que las figuras no
    # tengan que repetir el agrupamiento y arriesgarse a divergir de esta.
    columna = ("perfil_amenaza_subest" if etiqueta == "subestaciones"
               else "perfil_amenaza_todos")
    df.loc[s.index, columna] = s["perfil"].values

    for pid, g in s.groupby("perfil"):
        fila = {
            "subconjunto": etiqueta, "perfil": int(pid), "n": int(len(g)),
            "n_subestaciones": int((g["tipo_activo"] == "subestacion").sum()),
            # Se usa la pertenencia real a zona inundable, NO un umbral sobre
            # H_inundacion: el termino de proximidad asigna un valor pequeno no
            # nulo a TODOS los activos, de modo que cualquier umbral bajo cuenta
            # como inundables muchos que no lo estan.
            "pct_inundable": round(
                100 * g["dentro_zona_inundable"].astype(str).str.lower()
                .eq("true").mean(), 1),
            "V50_medio_ms": round(float(g["V50_ms"].mean()), 2),
            "H_viento_medio": round(float(g["H_viento_nuevo"].mean()), 4),
            "densidad_media": round(float(g["densidad_5km"].mean()), 1),
            "CRS_mediano": round(float(g["CRS_v6"].median()), 2),
            "CRS_max": round(float(g["CRS_v6"].max()), 2),
            "pct_dominante_viento": round(100 * g["dominante_v6"].eq("viento").mean(), 1),
            "provincia_dominante": g["provincia"].value_counts().idxmax(),
        }
        tablas.append(fila)
        print(f"    perfil {pid}: n={fila['n']:>6} ({fila['n_subestaciones']} subest.)  "
              f"V50 {fila['V50_medio_ms']:>5.2f}  viento dom. "
              f"{fila['pct_dominante_viento']:>5.1f} %  "
              f"CRS med. {fila['CRS_mediano']:>6.2f}  {fila['provincia_dominante']}")

    perfiles_salida[etiqueta] = {"n": int(len(sub)), "barrido": barrido,
                                 "k_optimo": k_opt, "silhouette": sil_opt}

pd.DataFrame(tablas).to_csv(SAL_PERFILES_CSV, index=False, sep=";",
                            encoding="utf-8-sig")

# ---------------------------------------------------------------------------
# Guardado
# ---------------------------------------------------------------------------
df.drop(columns=["term_inund", "term_inund_v5", "term_viento_v5",
                 "term_viento_v6", "term_viento_v6w5"]).to_csv(
    SAL_CSV, index=False, sep=";", encoding="utf-8-sig")

with open(SAL_PARAMS, "w", encoding="utf-8") as fh:
    json.dump({
        "version": "v6",
        "cambio": ("la peligrosidad por viento pasa de min-max sobre la velocidad "
                   "media anual del Global Wind Atlas a normalizacion absoluta "
                   "sobre la velocidad de retorno a 50 anos"),
        "fuente_v50": "Pryor y Barthelmie (2021), Zenodo 10.5281/zenodo.4306822",
        "v50_es_racha": False,
        "v50_es_sostenida": True,
        "peso_inundacion": w_i, "peso_viento": w_v,
        "vulnerabilidad": par5["vulnerabilidad"],
        "criticidad_min": par5["criticidad_min"],
        "criticidad_max": par5["criticidad_max"],
        "normalizacion_viento": {
            "formula": "H_viento = min(1, (V50/V_basica)^2)",
            "V_basica_ms": V_BASICA,
            "referencia": "zona C del CTE DB-SE-AE, la mas desfavorable de Espana",
        },
        "bajada_de_escala": {
            "formula": "V50_activo = V50_celda * (v_GWA_activo / v_GWA_medio_celda)",
            "supuesto": ("el factor entre velocidad media y extremo de retorno es "
                         "espacialmente uniforme dentro de la celda"),
            "razon_acotada_a": [RAZON_MIN, RAZON_MAX],
            "activos_acotados": n_acotados,
        },
        "crs": {
            "mediana": round(float(df["CRS_v6"].median()), 3),
            "media": round(float(df["CRS_v6"].mean()), 3),
            "max": round(float(df["CRS_v6"].max()), 3),
            "percentiles": {str(p): round(float(df["CRS_v6"].quantile(p / 100)), 3)
                            for p in (50, 75, 90, 95, 99)},
        },
        "sensibilidad_pesos": sensibilidad,
    }, fh, ensure_ascii=False, indent=2)

with open(SAL_PERFILES_JSON, "w", encoding="utf-8") as fh:
    json.dump({
        "variables": VARS,
        "semilla": SEMILLA,
        "nota": ("se calculan los dos subconjuntos porque la cifra de control de la "
                 "version V5 (k=4, silhouette 0,519, un perfil de 27 subestaciones) "
                 "solo se reproduce sobre las 608 subestaciones, no sobre los 38.939 "
                 "activos"),
        "subconjuntos": perfiles_salida,
        "tabla": tablas,
    }, fh, ensure_ascii=False, indent=2)

with open(SAL_COMPARATIVA, "w", encoding="utf-8") as fh:
    json.dump({
        "crs": {
            "v5": base5["crs"],
            "v6": {"mediana": round(float(df["CRS_v6"].median()), 3),
                   "media": round(float(df["CRS_v6"].mean()), 3),
                   "max": round(float(df["CRS_v6"].max()), 3),
                   "p95": round(float(df["CRS_v6"].quantile(0.95)), 3),
                   "p99": round(float(df["CRS_v6"].quantile(0.99)), 3)},
            "control_minmax_sobre_v50": {
                "mediana": round(float(df["CRS_v6_minmax"].median()), 3),
                "max": round(float(df["CRS_v6_minmax"].max()), 3)},
            "v6_sin_escalar": {
                "mediana": round(float(df["CRS_v6_bruto"].median()), 3),
                "max": round(float(df["CRS_v6_bruto"].max()), 3)},
        },
        "H_viento": {
            "v5_mediana": round(float(df["H_viento"].median()), 4),
            "v6_mediana": round(float(df["H_viento_nuevo"].median()), 4),
            "v6_minmax_mediana": round(float(df["H_viento_minmax"].median()), 4),
        },
        "amenaza_dominante": dominante,
        "reparto_provincial_top5": provincial,
        "top20_subestaciones": {
            "v5": top20_v5.round({"CRS": 3}).to_dict("records"),
            "v6": top20_v6.round({"CRS_v6": 3}).to_dict("records"),
            "entran_en_v6": sorted(int(x) for x in entran),
            "salen_en_v6": sorted(int(x) for x in salen),
            "se_mantienen": int(20 - len(entran)),
        },
        "perfiles": {
            "v5_subestaciones": {"k": base5["perfiles"]["k_optimo"],
                                 "silhouette": base5["perfiles"]["silhouette"]},
            "v6": {e: {"k": v["k_optimo"], "silhouette": v["silhouette"]}
                   for e, v in perfiles_salida.items()},
        },
    }, fh, ensure_ascii=False, indent=2)

print(f"\nGuardados:")
for f in (SAL_CSV, SAL_PARAMS, SAL_PERFILES_JSON, SAL_PERFILES_CSV, SAL_COMPARATIVA):
    print(f"  {os.path.basename(f)}")
