# ============================================================================
# 15_cifras_documento.py
# ----------------------------------------------------------------------------
# Recalcula, desde activos_con_crs_v6.csv, TODAS las cifras que la memoria cita
# en las Tablas 6 a 10 y en la prosa de los apartados 5.2 a 5.5, 5.8, 6.2 y 7.
# Existe para que ninguna cifra del documento se transcriba a mano: se ejecuta,
# se lee la salida y se corrige el .docx contra ella.
#
# Escribe cifras_documento.json, que es lo que consume el script de correccion.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd

CARPETA = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(CARPETA, "activos_con_crs_v6.csv")
SALIDA = os.path.join(CARPETA, "cifras_documento.json")

df = pd.read_csv(CSV, sep=";", encoding="utf-8-sig", low_memory=False)
with open(os.path.join(CARPETA, "crs_parametros_v6.json"), encoding="utf-8") as fh:
    par = json.load(fh)

COL = "CRS_v6"
crs = df[COL]
p50, p90, p95, p99 = (float(crs.quantile(q)) for q in (0.5, 0.90, 0.95, 0.99))
ETIQ = {"subestacion": "Subest.", "tower": "Torres", "pole": "Postes",
        "portal": "Pórticos"}


def clase(f):
    if f["tipo_activo"] == "subestacion":
        return "subestacion"
    return f["tipo_apoyo"]


df["clase"] = df.apply(clase, axis=1)
top5 = crs >= p95
top1 = crs >= p99

out = {"pesos": [par["peso_inundacion"], par["peso_viento"]]}

# --- Distribucion del indice -----------------------------------------------
print("=" * 78)
print("DISTRIBUCION DEL INDICE  (apartado 5.4, primer parrafo)")
print("=" * 78)
cuatro = crs.nlargest(4)
out["distribucion"] = {
    "mediana": round(p50, 2), "maxima": round(float(crs.max()), 2),
    "p90": round(p90, 2), "p95": round(p95, 2), "p99": round(p99, 2),
    "top4_min": round(float(cuatro.min()), 2),
    "top4_max": round(float(cuatro.max()), 2),
    "n_top5": int(top5.sum()), "n_top1": int(top1.sum()),
}
for k, v in out["distribucion"].items():
    print(f"  {k:<12} {v}")

# --- Tabla 7: bandas x clase de activo --------------------------------------
print("\n" + "=" * 78)
print("TABLA 7: bandas del indice por clase de activo")
print("=" * 78)
bandas = [("< %.2f  (mitad inferior)" % p50, crs < p50),
          ("%.2f – %.2f  (p50–p90)" % (p50, p90), (crs >= p50) & (crs < p90)),
          ("%.2f – %.2f  (p90–p95)" % (p90, p95), (crs >= p90) & (crs < p95)),
          ("%.2f – %.2f  (p95–p99)" % (p95, p99), (crs >= p95) & (crs < p99)),
          ("≥ %.2f  (1 %% superior)" % p99, crs >= p99)]
orden = ["subestacion", "tower", "pole", "portal"]
tabla7 = []
for nombre, m in bandas:
    fila = {"banda": nombre.replace(".", ","),
            **{ETIQ[c]: int((m & (df["clase"] == c)).sum()) for c in orden},
            "Total": int(m.sum())}
    tabla7.append(fila)
    print(f"  {fila['banda']:<30} " +
          " ".join(f"{fila[ETIQ[c]]:>7}" for c in orden) + f" {fila['Total']:>8}")
resumen7 = {
    "total": {ETIQ[c]: int((df["clase"] == c).sum()) for c in orden},
    "mediana": {ETIQ[c]: round(float(crs[df["clase"] == c].median()), 2)
                for c in orden},
    "maximo": {ETIQ[c]: round(float(crs[df["clase"] == c].max()), 2)
               for c in orden},
    "pct_en_top5": {ETIQ[c]: round(100 * float(top5[df["clase"] == c].mean()), 1)
                    for c in orden},
    "pct_en_top1": {ETIQ[c]: round(100 * float(top1[df["clase"] == c].mean()), 1)
                    for c in orden},
    "n_en_top1": {ETIQ[c]: int((top1 & (df["clase"] == c)).sum()) for c in orden},
}
resumen7["total"]["Total"] = len(df)
resumen7["mediana"]["Total"] = round(p50, 2)
resumen7["maximo"]["Total"] = round(float(crs.max()), 2)
resumen7["pct_en_top5"]["Total"] = round(100 * float(top5.mean()), 1)
for etiqueta, d in resumen7.items():
    print(f"  {etiqueta:<14} " + "  ".join(f"{ETIQ[c]} {d[ETIQ[c]]}" for c in orden))
out["tabla7"] = {"bandas": tabla7, "resumen": resumen7}

# --- Tabla 8: reparto provincial -------------------------------------------
print("\n" + "=" * 78)
print("TABLA 8: reparto provincial del conjunto critico")
print("=" * 78)
tabla8 = []
for prov in ("Castellón", "Valencia", "Alicante"):
    m = df["provincia"] == prov
    c = m & top5
    fila = {"provincia": prov, "activos": int(m.sum()), "criticos": int(c.sum()),
            "pct_prov": round(100 * float(top5[m].mean()), 1),
            **{ETIQ[k]: int((c & (df["clase"] == k)).sum()) for k in orden},
            "CRS_max": round(float(crs[m].max()), 2)}
    tabla8.append(fila)
    print(f"  {prov:<11} {fila['activos']:>7} {fila['criticos']:>7} "
          f"{fila['pct_prov']:>6} % " +
          " ".join(f"{fila[ETIQ[k]]:>5}" for k in orden) +
          f"  max {fila['CRS_max']}")
total8 = {"provincia": "Total", "activos": len(df), "criticos": int(top5.sum()),
          "pct_prov": round(100 * float(top5.mean()), 1),
          **{ETIQ[k]: int((top5 & (df["clase"] == k)).sum()) for k in orden},
          "CRS_max": round(float(crs.max()), 2)}
tabla8.append(total8)
print(f"  {'Total':<11} {total8['activos']:>7} {total8['criticos']:>7} "
      f"{total8['pct_prov']:>6} % " +
      " ".join(f"{total8[ETIQ[k]]:>5}" for k in orden))
out["tabla8"] = tabla8

# --- Tabla 9: las subestaciones que superan el umbral de priorizacion -------
# Antes eran "las quince de mayor indice", un corte arbitrario que coincidia con
# las 14 criticas de entonces. Con el reparto nuevo hay 19 subestaciones sobre el
# umbral, de modo que la tabla lista exactamente el conjunto critico: asi la lista
# corta y el conjunto que el apartado 5.5 declara son el mismo.
print("\n" + "=" * 78)
print("TABLA 9: las subestaciones que superan el umbral de priorizacion")
print("=" * 78)
sub = (df[(df["tipo_activo"] == "subestacion") & top5]
       .sort_values(COL, ascending=False))
tabla9 = []
for i, (_, f) in enumerate(sub.iterrows(), 1):
    nombre = f.get("nombre")
    nombre = "—" if not isinstance(nombre, str) or not nombre.strip() else nombre.strip()
    nivel = f.get("nivel_peligrosidad_patricova")
    nivel = "—" if pd.isna(nivel) else str(int(nivel))
    fila = {"n": i, "osm_id": int(f["osm_id"]), "nombre": nombre,
            "provincia": f["provincia"], "nivel": nivel,
            "lat": round(float(f["lat"]), 4), "lon": round(float(f["lon"]), 4),
            "CRS": round(float(f[COL]), 2)}
    tabla9.append(fila)
    print(f"  {i:>2} {fila['osm_id']:>11} {nombre[:26]:<26} "
          f"{fila['provincia']:<10} niv {nivel:<3} "
          f"{fila['lat']:>8} / {fila['lon']:>8}  {fila['CRS']:>6}")
out["tabla9"] = tabla9
out["tabla9_n"] = len(tabla9)
out["tabla9_sin_nombre"] = sum(1 for f in tabla9 if f["nombre"] == "—")
out["tabla9_nivel1"] = sum(1 for f in tabla9 if f["nivel"] == "1")
print(f"\n  filas: {out['tabla9_n']}")
print(f"  sin nombre declarado en OSM: {out['tabla9_sin_nombre']}")
print(f"  en el nivel 1 de PATRICOVA: {out['tabla9_nivel1']}")

# --- Subestaciones criticas por provincia ----------------------------------
print("\n" + "=" * 78)
print("SUBESTACIONES CRITICAS  (apartado 5.5 y conclusiones)")
print("=" * 78)
sc = df[(df["tipo_activo"] == "subestacion") & top5]
out["subest_criticas"] = {"total": int(len(sc)),
                          **{p: int(n) for p, n in
                             sc["provincia"].value_counts().items()}}
print(f"  total {len(sc)}   " +
      "  ".join(f"{p} {n}" for p, n in sc["provincia"].value_counts().items()))

# --- Celdas del campo de extremos ------------------------------------------
if "celda_v50" in df.columns:
    n_celdas = int(df["celda_v50"].nunique())
else:
    n_celdas = int(df.groupby(["V50_bruto_ms"]).ngroups)
out["celdas_v50_con_activos"] = n_celdas
print(f"\n  celdas del campo de extremos con al menos un activo: {n_celdas}")

# --- Perfiles 5 y 6, densidades de los perfiles 3 y 4 ----------------------
if "perfil_amenaza_subest" in df.columns:
    s = df[df["perfil_amenaza_subest"].notna()]
    dens = {int(p): {"media": round(float(g["densidad_5km"].mean()), 0),
                     "mediana": round(float(g["densidad_5km"].median()), 0),
                     "n": int(len(g)),
                     "CRS_mediano": round(float(g[COL].median()), 2),
                     "CRS_max": round(float(g[COL].max()), 2)}
            for p, g in s.groupby("perfil_amenaza_subest")}
    out["perfiles_subest"] = dens
    print("\n  perfiles de subestaciones: densidad y CRS")
    for p, v in sorted(dens.items()):
        print(f"    perfil {p}: n={v['n']:>4}  dens. media {v['media']:>7} "
              f"mediana {v['mediana']:>7}  CRS med. {v['CRS_mediano']:>6} "
              f"max {v['CRS_max']:>6}")

with open(SALIDA, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print(f"\nGuardado: {os.path.basename(SALIDA)}")
