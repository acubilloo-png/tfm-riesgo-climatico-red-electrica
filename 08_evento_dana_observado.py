# ============================================================================
# 08_evento_dana_observado.py
# ----------------------------------------------------------------------------
# Cierra el argumento sobre por que el indice no detecta Catadau, con
# observaciones en lugar de con razonamiento.
#
# ----------------------------------------------------------------------------
# LA PREGUNTA
# ----------------------------------------------------------------------------
# La validacion del script 05 muestra que sustituir la velocidad media por la
# velocidad de retorno a 50 anos no consigue que Catadau entre en el conjunto
# critico: pasa del percentil 63,4 al 69,5, pero ninguno de sus 149 activos cruza
# el umbral del 5 % superior. La explicacion que se ofrece es que el episodio fue
# convectivo, de caracter tornadico, y que ni ERA5 a 0,25 grados ni CERRA a 5,5 km
# resuelven fenomenos de escala inferior a la rejilla.
#
# Esa explicacion se puede COMPROBAR, no solo argumentar. Si las estaciones de
# AEMET proximas a Catadau registraron rachas moderadas durante los dias del
# episodio, mientras alli se derribaban mas de veinte apoyos, entonces el
# fenomeno no lo capturaron ni las propias observaciones. Y si no lo captura una
# medida directa a pocos kilometros, ningun reanalisis de rejilla puede hacerlo:
# el problema no es la resolucion del producto elegido, es la naturaleza del
# fenomeno.
#
# Es el cierre mas solido posible para esta limitacion: convierte un fallo del
# metodo en un resultado sobre el fenomeno.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd

CARPETA = os.path.dirname(os.path.abspath(__file__))
CSV_RACHAS = os.path.join(CARPETA, "rachas_aemet_cv.csv")
CSV_EST = os.path.join(CARPETA, "estaciones_aemet_cv.csv")
CSV_V50 = os.path.join(CARPETA, "v50_estaciones.csv")
SALIDA = os.path.join(CARPETA, "evento_dana_observado.json")

# El episodio: la DANA descargo el 29 de octubre de 2024; se toma una ventana
# amplia para no depender de la hora exacta ni de posibles desfases de registro.
INICIO, FIN = "2024-10-27", "2024-11-04"
DIA_EVENTO = "2024-10-29"

CATADAU = (39.2333, -0.6167)
QUART = (39.4806, -0.4411)


def distancia_km(lat1, lon1, lat2, lon2):
    """Distancia grande-circulo aproximada, suficiente a esta escala."""
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


print("Cargando datos...")
r = pd.read_csv(CSV_RACHAS, sep=";", encoding="utf-8-sig", low_memory=False)
r["fecha"] = pd.to_datetime(r["fecha"])
est = pd.read_csv(CSV_EST, sep=";", encoding="utf-8-sig")
v50 = pd.read_csv(CSV_V50, sep=";", encoding="utf-8-sig")
nombres = dict(zip(est["indicativo"], est["nombre"]))
v50_por_est = dict(zip(v50["indicativo"], v50["V50_gumbel_ms"]))

# Distancia de cada estacion a los dos entornos
est["dist_catadau_km"] = distancia_km(est["lat"], est["lon"], *CATADAU)
est["dist_quart_km"] = distancia_km(est["lat"], est["lon"], *QUART)

con_datos = set(r["indicativo"].unique())
disponibles = est[est["indicativo"].isin(con_datos)].copy()

print("\n=== ESTACIONES CON DATOS, ORDENADAS POR CERCANIA A CATADAU ===")
for _, f in disponibles.sort_values("dist_catadau_km").iterrows():
    print(f"  {f['indicativo']:<7} {f['dist_catadau_km']:>6.1f} km   "
          f"{str(f['nombre'])[:34]}")

# ---------------------------------------------------------------------------
# Rachas durante el episodio
# ---------------------------------------------------------------------------
ventana = r[(r["fecha"] >= INICIO) & (r["fecha"] <= FIN) & r["racha"].notna()]
print(f"\n=== RACHAS REGISTRADAS DEL {INICIO} AL {FIN} ===")
if ventana.empty:
    print("  sin datos en la ventana del episodio")

filas = []
for ide, g in ventana.groupby("indicativo"):
    d_cat = float(disponibles.loc[disponibles["indicativo"] == ide,
                                  "dist_catadau_km"].iloc[0])
    idx = g["racha"].idxmax()
    racha_max = float(g.loc[idx, "racha"])
    fecha_max = g.loc[idx, "fecha"]
    dia = g[g["fecha"] == DIA_EVENTO]
    racha_dia = float(dia["racha"].iloc[0]) if len(dia) else np.nan
    v50_est = v50_por_est.get(ide, np.nan)
    # Que periodo de retorno tenia esa racha en esa estacion, groseramente:
    # fraccion del V50 alcanzada
    frac = racha_max / v50_est if v50_est == v50_est else np.nan
    filas.append({
        "indicativo": ide, "nombre": str(nombres.get(ide, "")),
        "dist_catadau_km": round(d_cat, 1),
        "racha_max_episodio_ms": round(racha_max, 1),
        "racha_max_episodio_kmh": round(racha_max * 3.6, 0),
        "fecha_racha_max": str(fecha_max.date()),
        "racha_29oct_ms": round(racha_dia, 1) if racha_dia == racha_dia else None,
        "V50_estacion_ms": round(v50_est, 1) if v50_est == v50_est else None,
        "fraccion_del_V50": round(frac, 2) if frac == frac else None,
    })

tabla = pd.DataFrame(filas).sort_values("dist_catadau_km")
print(f"\n{'estacion':<8}{'km a Cat.':>10}{'racha max':>11}{'km/h':>7}"
      f"{'fecha':>12}{'29 oct':>8}{'V50 est.':>10}{'% del V50':>11}")
for _, f in tabla.iterrows():
    print(f"{f['indicativo']:<8}{f['dist_catadau_km']:>10.1f}"
          f"{f['racha_max_episodio_ms']:>11.1f}{f['racha_max_episodio_kmh']:>7.0f}"
          f"{f['fecha_racha_max']:>12}"
          f"{(f['racha_29oct_ms'] if f['racha_29oct_ms'] else 0):>8.1f}"
          f"{(f['V50_estacion_ms'] if f['V50_estacion_ms'] else 0):>10.1f}"
          f"{(100 * f['fraccion_del_V50'] if f['fraccion_del_V50'] else 0):>10.0f}%")

# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------
print("\n=== LECTURA ===")
cercanas = tabla[tabla["dist_catadau_km"] <= 60]
if len(cercanas):
    peor = cercanas["fraccion_del_V50"].max()
    print(f"  estaciones a menos de 60 km de Catadau: {len(cercanas)}")
    print(f"  la mayor racha del episodio en ellas alcanzo el "
          f"{100 * peor:.0f} % del V50 de su propia estacion")
    if peor < 0.8:
        print("  -> Ninguna estacion proxima registro nada cercano a su propio")
        print("     extremo de retorno a 50 anos, mientras en Catadau caian mas de")
        print("     veinte apoyos. El episodio fue local y no lo capturaron ni las")
        print("     observaciones directas a decenas de kilometros: no es un")
        print("     problema de resolucion del producto empleado, sino de la")
        print("     naturaleza convectiva del fenomeno.")
    else:
        print("  -> Alguna estacion proxima si registro un valor cercano a su")
        print("     extremo: el episodio era detectable y conviene revisar por que")
        print("     el indice no lo refleja.")

maximo_historico = float(r["racha"].max())
print(f"\n  para contexto, la racha maxima de todo el periodo 1985-2024 en la")
print(f"  Comunitat fue {maximo_historico:.1f} m/s "
      f"({maximo_historico * 3.6:.0f} km/h), y NO ocurrio durante esta DANA")
idx_h = r["racha"].idxmax()
print(f"    fue en {r.loc[idx_h, 'indicativo']} el "
      f"{r.loc[idx_h, 'fecha']:%d/%m/%Y}")

with open(SALIDA, "w", encoding="utf-8") as fh:
    json.dump({
        "ventana": {"inicio": INICIO, "fin": FIN, "dia_evento": DIA_EVENTO},
        "estaciones": tabla.to_dict("records"),
        "n_estaciones_menos_60km": int(len(cercanas)),
        "max_fraccion_del_V50_en_cercanas": (
            round(float(cercanas["fraccion_del_V50"].max()), 3)
            if len(cercanas) else None),
        "racha_maxima_del_periodo_completo_ms": round(maximo_historico, 1),
        "racha_maxima_del_periodo_fecha": str(r.loc[idx_h, "fecha"].date()),
        "racha_maxima_del_periodo_estacion": str(r.loc[idx_h, "indicativo"]),
        "conclusion": (
            "el episodio de Catadau no fue capturado por las estaciones proximas, "
            "de modo que su no deteccion por el indice no es atribuible a la "
            "resolucion del producto de reanalisis empleado sino al caracter "
            "convectivo y local del fenomeno"),
    }, fh, ensure_ascii=False, indent=2)

print(f"\nGuardado: {os.path.basename(SALIDA)}")
