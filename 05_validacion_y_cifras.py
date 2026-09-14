# ============================================================================
# 05_validacion_y_cifras.py
# ----------------------------------------------------------------------------
# Tareas 6 y 7 del encargo:
#   - validacion del indice contra los dos entornos reales de la DANA de octubre
#     de 2024, antes y despues del cambio de variable;
#   - cifras interpretativas de viento, contraste con la velocidad basica del CTE
#     y con la regla Vref = 5 x Vmedia de la IEC;
#   - diagnostico de plausibilidad fisica del V50 bajado de escala, que no estaba
#     pedido pero hace falta (ver la nota al final).
#
# Escribe validacion_dana.json y cifras_viento.json.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd
import geopandas as gpd

CARPETA = os.path.dirname(os.path.abspath(__file__))
CSV_V6 = os.path.join(CARPETA, "activos_con_crs_v6.csv")
SAL_DANA = os.path.join(CARPETA, "validacion_dana.json")
SAL_VIENTO = os.path.join(CARPETA, "cifras_viento.json")

UTM_EPSG = 25830
RADIO_M = 6000
V_BASICA_C = 29.0
V_BASICA_A = 26.0

ENTORNOS = {
    "Catadau": {"lat": 39.2333, "lon": -0.6167,
                "evento": "mas de veinte apoyos derribados por viento"},
    "Quart de Poblet": {"lat": 39.4806, "lon": -0.4411,
                        "evento": "subestacion anegada por inundacion"},
}

print("Cargando la version V6...")
df = pd.read_csv(CSV_V6, sep=";", encoding="utf-8-sig", low_memory=False)
print(f"  {len(df)} activos")

p95_v5 = df["CRS"].quantile(0.95)
p95_v6 = df["CRS_v6"].quantile(0.95)

g = gpd.GeoDataFrame(
    df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326"
).to_crs(epsg=UTM_EPSG)


def percentil_de(serie, valor):
    return float((serie < valor).mean() * 100)


# ---------------------------------------------------------------------------
# TAREA 6
# ---------------------------------------------------------------------------
print("\n=== TAREA 6: VALIDACION CONTRA EL EVENTO REAL ===")
validacion = {}
for nombre, info in ENTORNOS.items():
    centro = (gpd.GeoSeries(
        [gpd.points_from_xy([info["lon"]], [info["lat"]])[0]], crs="EPSG:4326")
        .to_crs(epsg=UTM_EPSG).iloc[0])
    dentro = g.geometry.distance(centro) <= RADIO_M
    sub = df[dentro.values]

    v_med = float(sub["velocidad_viento_ms"].mean())
    v50 = float(sub["V50_ms"].mean())
    v50_bruto = float(sub["V50_bruto_ms"].mean())

    r = {
        "evento": info["evento"],
        "n_activos": int(len(sub)),
        "antes": {
            "variable": "velocidad media anual del Global Wind Atlas",
            "valor_ms": round(v_med, 3),
            "valor_kmh": round(v_med * 3.6, 1),
            "percentil_en_el_conjunto": round(
                percentil_de(df["velocidad_viento_ms"], v_med), 1),
            "H_viento_medio": round(float(sub["H_viento"].mean()), 4),
            "CRS_mediano": round(float(sub["CRS"].median()), 3),
            "CRS_percentil_medio": round(float(sub["CRS_percentil"].mean()), 1),
            "n_en_top5pct": int((sub["CRS"] >= p95_v5).sum()),
            "pct_en_top5pct": round(100 * (sub["CRS"] >= p95_v5).mean(), 1),
        },
        "despues": {
            "variable": "V50 sostenida de retorno a 50 anos, bajada de escala",
            "valor_ms": round(v50, 3),
            "valor_kmh": round(v50 * 3.6, 1),
            "valor_sin_escalar_ms": round(v50_bruto, 3),
            "percentil_en_el_conjunto": round(percentil_de(df["V50_ms"], v50), 1),
            "H_viento_medio": round(float(sub["H_viento_nuevo"].mean()), 4),
            "CRS_mediano": round(float(sub["CRS_v6"].median()), 3),
            "CRS_percentil_medio": round(float(sub["CRS_percentil_v6"].mean()), 1),
            "n_en_top5pct": int((sub["CRS_v6"] >= p95_v6).sum()),
            "pct_en_top5pct": round(100 * (sub["CRS_v6"] >= p95_v6).mean(), 1),
        },
    }
    validacion[nombre] = r

    print(f"\n  --- {nombre} ({info['evento']}) ---")
    print(f"      {r['n_activos']} activos en {RADIO_M / 1000:.0f} km")
    print(f"      {'':<26} {'ANTES':>12} {'DESPUES':>12}")
    print(f"      {'variable (m/s)':<26} {r['antes']['valor_ms']:>12.2f} "
          f"{r['despues']['valor_ms']:>12.2f}")
    print(f"      {'variable (km/h)':<26} {r['antes']['valor_kmh']:>12.1f} "
          f"{r['despues']['valor_kmh']:>12.1f}")
    print(f"      {'percentil':<26} {r['antes']['percentil_en_el_conjunto']:>12.1f} "
          f"{r['despues']['percentil_en_el_conjunto']:>12.1f}")
    print(f"      {'H_viento medio':<26} {r['antes']['H_viento_medio']:>12.4f} "
          f"{r['despues']['H_viento_medio']:>12.4f}")
    print(f"      {'CRS mediano':<26} {r['antes']['CRS_mediano']:>12.2f} "
          f"{r['despues']['CRS_mediano']:>12.2f}")
    print(f"      {'CRS percentil medio':<26} "
          f"{r['antes']['CRS_percentil_medio']:>12.1f} "
          f"{r['despues']['CRS_percentil_medio']:>12.1f}")
    print(f"      {'en el 5 % superior':<26} "
          f"{r['antes']['n_en_top5pct']:>12} {r['despues']['n_en_top5pct']:>12}")

cat = validacion["Catadau"]
print(f"\n  RESPUESTA A LA PREGUNTA DEL ENCARGO:")
print(f"    Catadau pasa del percentil {cat['antes']['percentil_en_el_conjunto']} "
      f"al {cat['despues']['percentil_en_el_conjunto']}")
print(f"    activos en el 5 % superior: {cat['antes']['n_en_top5pct']} -> "
      f"{cat['despues']['n_en_top5pct']} de {cat['n_activos']}")

# ---------------------------------------------------------------------------
# TAREA 7
# ---------------------------------------------------------------------------
print("\n=== TAREA 7: CIFRAS INTERPRETATIVAS ===")
cifras = {}
for etiqueta, col in (("velocidad_media_gwa", "velocidad_viento_ms"),
                      ("V50_escalado", "V50_ms"),
                      ("V50_sin_escalar", "V50_bruto_ms")):
    s = df[col].dropna()
    cifras[etiqueta] = {}
    print(f"\n  {etiqueta}:")
    for nom, val in (("min", s.min()), ("mediana", s.median()), ("media", s.mean()),
                     ("p90", s.quantile(0.90)), ("p95", s.quantile(0.95)),
                     ("p99", s.quantile(0.99)), ("max", s.max())):
        cifras[etiqueta][nom] = {"ms": round(float(val), 3),
                                 "kmh": round(float(val) * 3.6, 1)}
        print(f"    {nom:<9} {val:>7.2f} m/s = {val * 3.6:>6.1f} km/h")

print("\n  activos que superan las velocidades basicas del CTE:")
superan = {}
for col, etiqueta in (("V50_ms", "V50_escalado"), ("V50_bruto_ms", "V50_sin_escalar")):
    superan[etiqueta] = {}
    for vb, zona in ((V_BASICA_A, "26 m/s (zona A)"), (V_BASICA_C, "29 m/s (zona C)")):
        n = int((df[col] > vb).sum())
        superan[etiqueta][str(vb)] = {"n": n, "pct": round(100 * n / len(df), 2)}
        print(f"    {etiqueta:<16} > {zona:<16} {n:>6} activos "
              f"({100 * n / len(df):>5.2f} %)")

# --- Contraste con la regla de la IEC --------------------------------------
# La IEC 61400-1 define la clase de turbina con Vref = 5 x Vave. Se contrasta esa
# regla contra el V50 observado en el atlas. Cabe una advertencia: Vref de la IEC
# se refiere a la altura de buje y aqui se compara contra velocidad a 10 m, de
# modo que la comparacion es indicativa y no estricta.
print("\n  contraste con la regla IEC Vref = 5 x Vmedia:")
iec = {}
for col, etiqueta in (("V50_ms", "V50_escalado"), ("V50_bruto_ms", "V50_sin_escalar")):
    vref_iec = 5.0 * df["velocidad_viento_ms"]
    obs = df[col]
    ok = np.isfinite(vref_iec) & np.isfinite(obs)
    r = float(np.corrcoef(vref_iec[ok], obs[ok])[0, 1])
    sesgo = float((vref_iec[ok] - obs[ok]).mean())
    disp = float((vref_iec[ok] - obs[ok]).std())
    razon = float((obs[ok] / df["velocidad_viento_ms"][ok]).median())
    iec[etiqueta] = {
        "correlacion": round(r, 4),
        "sesgo_medio_ms": round(sesgo, 3),
        "dispersion_ms": round(disp, 3),
        "razon_observada_mediana": round(razon, 3),
        "regla_iec": 5.0,
        "conservadora": bool(sesgo > 0),
    }
    print(f"    {etiqueta}:")
    print(f"      correlacion r = {r:.4f}")
    print(f"      sesgo medio de la regla = {sesgo:>+7.2f} m/s "
          f"({'CONSERVADORA' if sesgo > 0 else 'NO conservadora'})")
    print(f"      dispersion = {disp:.2f} m/s")
    print(f"      razon V50/Vmedia observada, mediana = {razon:.2f} "
          f"(la regla supone 5,00)")

# --- Diagnostico de plausibilidad fisica -----------------------------------
# No lo pedia el encargo, pero el V50 bajado de escala alcanza valores que hay
# que mirar de frente antes de darlos por buenos.
print("\n  DIAGNOSTICO DE PLAUSIBILIDAD DEL V50 BAJADO DE ESCALA:")
print(f"    sin escalar, el rango es {df['V50_bruto_ms'].min():.1f}-"
      f"{df['V50_bruto_ms'].max():.1f} m/s, que es fisicamente razonable")
print(f"    escalado, el rango se abre a {df['V50_ms'].min():.1f}-"
      f"{df['V50_ms'].max():.1f} m/s")
extremos = df[df["V50_ms"] > 35]
print(f"    activos con V50 escalado > 35 m/s: {len(extremos)} "
      f"({100 * len(extremos) / len(df):.2f} %)")
if len(extremos):
    print(f"      altitud mediana {extremos['altitud_m'].median():.0f} m "
          f"(conjunto: {df['altitud_m'].median():.0f} m)"
          if "altitud_m" in df.columns else "")
    print(f"      viento medio GWA mediano {extremos['velocidad_viento_ms'].median():.2f} "
          f"m/s (conjunto: {df['velocidad_viento_ms'].median():.2f})")
    print(f"      razon de exposicion mediana "
          f"{extremos['razon_exposicion'].median():.2f}")
bajos = df[df["V50_ms"] < 12]
print(f"    activos con V50 escalado < 12 m/s: {len(bajos)} "
      f"({100 * len(bajos) / len(df):.2f} %)")

plausibilidad = {
    "rango_sin_escalar_ms": [round(float(df["V50_bruto_ms"].min()), 2),
                             round(float(df["V50_bruto_ms"].max()), 2)],
    "rango_escalado_ms": [round(float(df["V50_ms"].min()), 2),
                          round(float(df["V50_ms"].max()), 2)],
    "n_mayor_35ms": int(len(extremos)),
    "n_menor_12ms": int(len(bajos)),
    "advertencia": (
        "el escalado multiplicativo por exposicion amplia el rango muy por encima "
        "del que da el campo de origen. Un V50 sostenido de 45 m/s a 10 m no es "
        "creible en la Comunitat Valenciana: es un artefacto de multiplicar un "
        "extremo por una razon de vientos medios. La variante sin escalar acota a "
        "24,6 m/s y no produce ningun activo con H_viento saturado. Ambas se "
        "conservan en el CSV para que la decision sea explicita."),
}

with open(SAL_DANA, "w", encoding="utf-8") as fh:
    json.dump({"radio_m": RADIO_M, "entornos": validacion}, fh,
              ensure_ascii=False, indent=2)
with open(SAL_VIENTO, "w", encoding="utf-8") as fh:
    json.dump({"distribuciones": cifras,
               "superan_velocidad_basica_cte": superan,
               "contraste_iec": iec,
               "plausibilidad_fisica": plausibilidad}, fh,
              ensure_ascii=False, indent=2)

print(f"\nGuardados: {os.path.basename(SAL_DANA)} y {os.path.basename(SAL_VIENTO)}")
