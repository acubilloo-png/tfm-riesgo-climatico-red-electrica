# ============================================================================
# 10_figuras_v6_adicionales.py
# ----------------------------------------------------------------------------
# Genera las figuras del documento que la version V6 deja obsoletas y que
# generar_figuras.py no cubria, mas la division de la figura de sensibilidad en
# los dos paneles sueltos que el documento usa.
#
# Los ficheros se nombran por su numero EN EL DOCUMENTO (docfigNN_...) para que
# la correspondencia al insertarlos sea inequivoca:
#
#   docfig10  perfiles de riesgo en el plano de las dos peligrosidades
#   docfig11  los perfiles frente a la criticidad de red
#   docfig13  estabilidad de la ordenacion (panel suelto)
#   docfig14  coincidencia en el 5 % superior (panel suelto)
#   docfig15  activos criticos de Castellon
#   docfig16  activos criticos de Valencia
#   docfig17  activos criticos de Alicante
#
# ----------------------------------------------------------------------------
# UNA DECISION DE FORMA QUE CONVIENE CONOCER
# ----------------------------------------------------------------------------
# Los perfiles de amenaza pasaron de 4 a 7 con la version V6. Siete series
# categoricas en un diagrama de dispersion no son admisibles: la paleta empleada
# en este trabajo admite tres series simultaneas en formatos de dispersion sin
# comprometer la distinguibilidad para lectores con deficiencias en la vision del
# color, y siete tonos serian indiscernibles.
#
# La figura 10 se resuelve por tanto en PANELES, uno por perfil, con el resto de
# subestaciones en gris de contexto: cada panel usa una sola serie y la
# comparacion se hace entre paneles.
#
# La figura 11 cambia de forma. Su proposito es responder que separa a perfiles
# que en el plano de amenazas resultan indistinguibles, y para eso una nube de
# puntos por perfil es menos directa que una tira de puntos por perfil con la
# mediana marcada: se lee de un golpe cual tiene mas red alrededor. Requiere un
# solo tono y ninguna leyenda. Convendra ajustar ligeramente su pie en la
# memoria, porque la forma ya no es un diagrama de dispersion.
# ============================================================================

import json
import os

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

CARPETA = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))
OUT = os.path.join(CARPETA, "figuras")
os.makedirs(OUT, exist_ok=True)

# --- Paleta y estilo, identicos a generar_figuras.py -----------------------
SURFACE = "#ffffff"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
SERIE = "#2a78d6"
COLOR_TIERRA = "#f2f1ed"
RAMPA = ["#cde2fb", "#9ec5f4", "#86b6ef", "#5598e7",
         "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
ANCHO_IN = 16.0 / 2.54

mpl.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300,
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 8,
    "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "text.color": INK,
    "axes.labelcolor": INK_2, "axes.edgecolor": BASELINE,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
    "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "legend.fontsize": 8,
})


def limpiar(ax, ejes=("left", "bottom")):
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_visible(lado in ejes)
    for lado in ejes:
        ax.spines[lado].set_linewidth(0.6)
        ax.spines[lado].set_color(BASELINE)


def titulo(ax, texto, subtitulo=None):
    lineas = subtitulo.count("\n") + 1 if subtitulo else 0
    ax.set_title(texto, loc="left", fontsize=9.5, fontweight="bold",
                 color=INK, pad=8 + 11 * lineas)
    if subtitulo:
        ax.text(0, 1.015, subtitulo, transform=ax.transAxes, fontsize=7.8,
                color=INK_2, va="bottom", ha="left", linespacing=1.45)


def guardar(fig, nombre):
    ruta = os.path.join(OUT, nombre)
    fig.savefig(ruta, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print(f"  generada: figuras/{nombre}")


def n(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


# ---------------------------------------------------------------------------
print("Cargando datos...")
act = pd.read_csv(os.path.join(CARPETA, "activos_con_crs_v6.csv"),
                  sep=";", encoding="utf-8-sig", low_memory=False)
with open(os.path.join(CARPETA, "crs_parametros_v6.json"), encoding="utf-8") as fh:
    par = json.load(fh)
prov = gpd.read_file(os.path.join(DATA_DIR, "provincias_cv.geojson")).to_crs(epsg=3857)
prov["etiqueta"] = prov["nombre"].str.split("/").str[-1]

sub = act[act["tipo_activo"] == "subestacion"].copy()
sub["perfil"] = sub["perfil_amenaza_subest"].astype(int)
perfiles = sorted(sub["perfil"].unique())
p95 = par["crs"]["percentiles"]["95"]
print(f"  {len(sub)} subestaciones en {len(perfiles)} perfiles")

ETIQUETAS = {1: "Inundación crítica", 2: "Inundación", 3: "Red densa y viento",
             4: "Viento, red media", 5: "Viento puro", 6: "Viento, red baja",
             7: "Riesgo bajo"}

# ===========================================================================
# DOCFIG 10 — perfiles en el plano de las dos peligrosidades, en paneles
# ===========================================================================
print("\ndocfig10: perfiles en el plano de amenazas")
ncol = 4
nrow = int(np.ceil(len(perfiles) / ncol))
fig, axes = plt.subplots(nrow, ncol, figsize=(ANCHO_IN, ANCHO_IN * 0.30 * nrow),
                         sharex=True, sharey=True)
axes = np.atleast_1d(axes).ravel()

# El eje de inundacion es logaritmico porque la peligrosidad recorre tres ordenes
# de magnitud; se desplaza para admitir los ceros.
EPS = 1e-3
for ax, p in zip(axes, perfiles):
    ax.scatter(sub["H_inundacion"] + EPS, sub["H_viento_nuevo"], s=3.5,
               c=BASELINE, linewidths=0, zorder=2)
    s = sub[sub["perfil"] == p]
    ax.scatter(s["H_inundacion"] + EPS, s["H_viento_nuevo"], s=8,
               c=SERIE, edgecolors=SURFACE, linewidths=0.3, zorder=3)
    ax.set_xscale("log")
    ax.set_title(f"Perfil {p} · n = {len(s)}\n{ETIQUETAS.get(p, '')}",
                 loc="center", fontsize=7, color=INK_2, pad=3, linespacing=1.4)
    ax.grid(True, zorder=1, alpha=0.6)
    ax.set_axisbelow(True)
    limpiar(ax)
for ax in axes[len(perfiles):]:
    ax.set_axis_off()
# Los rotulos de eje solo en el borde: repetirlos en los siete paneles satura la
# figura sin anadir informacion, porque los ejes son compartidos.
for k, ax in enumerate(axes[:len(perfiles)]):
    ultima_fila = k >= len(perfiles) - ncol or (k + ncol) >= len(perfiles)
    if ultima_fila:
        ax.set_xlabel("Peligrosidad por inundación", fontsize=7)
    if k % ncol == 0:
        ax.set_ylabel("Peligrosidad por viento", fontsize=7)

fig.tight_layout(rect=(0, 0, 1, 0.90))
fig.text(0.0, 0.995, "Perfiles de riesgo en el plano de las dos peligrosidades",
         ha="left", va="top", fontsize=9.5, fontweight="bold", color=INK)
fig.text(0.0, 0.955,
         "Cada panel destaca un perfil; en gris, el resto de las 608 "
         "subestaciones. El eje de inundación es logarítmico porque esa "
         "peligrosidad\nrecorre tres órdenes de magnitud, mientras que la eólica "
         "no llega a recorrer uno: esa asimetría es la que explica la composición "
         "de la cola del índice.",
         ha="left", va="top", fontsize=7.6, color=INK_2, linespacing=1.45)
guardar(fig, "docfig10_perfiles_plano_amenazas.png")

# ===========================================================================
# DOCFIG 11 — los perfiles frente a la criticidad de red
# ===========================================================================
print("docfig11: perfiles frente a la criticidad de red")
fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 0.46))
rng = np.random.default_rng(42)
for i, p in enumerate(perfiles):
    s = sub[sub["perfil"] == p]
    y = np.full(len(s), i) + rng.uniform(-0.22, 0.22, len(s))
    ax.scatter(s["densidad_5km"], y, s=9, c=SERIE, alpha=0.55,
               linewidths=0, zorder=3)
    med = float(s["densidad_5km"].median())
    ax.plot([med, med], [i - 0.34, i + 0.34], color=INK, linewidth=1.6, zorder=4)
    ax.annotate(f"mediana {med:,.0f}".replace(",", "."),
                xy=(med, i + 0.36), xytext=(3, 0), textcoords="offset points",
                fontsize=6.8, color=INK, va="bottom", ha="left")

ax.set_yticks(range(len(perfiles)))
ax.set_yticklabels([f"Perfil {p} · {ETIQUETAS.get(p, '')}  (n = {int((sub['perfil'] == p).sum())})"
                    for p in perfiles], fontsize=7.4)
ax.invert_yaxis()
ax.set_xlabel("Densidad de activos en 5 km (proxy de criticidad de red)",
              color=INK_2)
ax.tick_params(axis="y", length=0)
ax.xaxis.grid(True, zorder=1)
ax.set_axisbelow(True)
limpiar(ax, ejes=("bottom",))
med3 = float(sub.loc[sub["perfil"] == 3, "densidad_5km"].median())
med4 = float(sub.loc[sub["perfil"] == 4, "densidad_5km"].median())
titulo(ax, "Qué separa a los perfiles: la criticidad de red",
       "Cada punto es una subestación; la línea vertical marca la mediana del "
       "perfil. Las medianas recorren de 113 a "
       f"{med3:,.0f}".replace(",", ".") + " activos en 5 km.\nLos perfiles 3 y 4, "
       "que comparten posición en el plano de amenazas, se separan aquí con "
       f"claridad: {med3:,.0f}".replace(",", ".") + " frente a "
       f"{med4:,.0f}".replace(",", ".") + " activos alrededor.")
guardar(fig, "docfig11_perfiles_criticidad.png")

# ===========================================================================
# DOCFIG 13 y 14 — la sensibilidad, en dos paneles sueltos
# ===========================================================================
sens = pd.DataFrame(par["sensibilidad_pesos"])
w_ref = par["peso_inundacion"]
for nombre, col, etiqueta_y, tit, sub_t, ref in (
    ("docfig13_sensibilidad_estabilidad.png", "spearman",
     "Correlación de Spearman",
     "Estabilidad de la ordenación frente al reparto de pesos",
     "Cada punto compara la ordenación completa de los {n} activos que produce un "
     "reparto alternativo con la del reparto\nadoptado. Una correlación próxima a "
     "1 significa que la conclusión del índice no depende de esa elección.", 1.0),
    ("docfig14_sensibilidad_solape.png", "solape_top5_pct",
     "% de coincidencia",
     "Coincidencia en el 5 % de mayor riesgo al variar el reparto",
     "Porcentaje de activos que siguen perteneciendo al 5 % de mayor riesgo al "
     "cambiar el reparto de pesos. Es la métrica\noperativa: mide si la lista de "
     "instalaciones a inspeccionar se mantiene.", 100.0),
):
    print(f"{nombre.split('_')[0]}: {tit[:44]}")
    fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 0.40))
    ax.plot(sens["peso_inundacion"], sens[col], color=SERIE, linewidth=1.9,
            marker="o", markersize=4, markerfacecolor=SERIE,
            markeredgecolor=SURFACE, markeredgewidth=0.7, zorder=3)
    ax.scatter([w_ref], [ref], s=64, facecolor="none", edgecolor=INK,
               linewidth=1.3, zorder=4)
    ax.annotate("reparto adoptado", xy=(w_ref, ref), xytext=(0, -24),
                textcoords="offset points", fontsize=7, color=INK_2,
                ha="center", va="top")
    for _, f in sens.iterrows():
        ax.annotate(n(f[col], 3) if col == "spearman" else n(f[col], 1),
                    xy=(f["peso_inundacion"], f[col]), xytext=(0, 7),
                    textcoords="offset points", fontsize=6.8, color=INK_2,
                    ha="center")
    ax.set_xlabel("Peso asignado a la inundación", color=INK_2)
    ax.set_ylabel(etiqueta_y, color=INK_2)
    # Separador decimal espanol en el eje, y holgura arriba para que la etiqueta
    # del punto mas alto no se solape con el subtitulo.
    ax.set_xticks(list(sens["peso_inundacion"]))
    ax.set_xticklabels([n(w, 2) for w in sens["peso_inundacion"]])
    lo, hi = float(sens[col].min()), float(sens[col].max())
    ax.set_ylim(lo - 0.10 * (hi - lo), hi + 0.22 * (hi - lo))
    ax.yaxis.grid(True, zorder=1)
    ax.set_axisbelow(True)
    limpiar(ax, ejes=("bottom",))
    titulo(ax, tit, sub_t.replace("{n}", f"{len(act):,}".replace(",", ".")))
    guardar(fig, nombre)

# ===========================================================================
# DOCFIG 15, 16 y 17 — activos criticos por provincia
# ===========================================================================
g_act = gpd.GeoDataFrame(
    act, geometry=gpd.points_from_xy(act["lon"], act["lat"]), crs="EPSG:4326"
).to_crs(epsg=3857)
cmap = mpl.colors.LinearSegmentedColormap.from_list("azul", RAMPA)
vmax = float(act["CRS_v6"].max())

for numero, nombre_prov in ((15, "Castellón"), (16, "Valencia"), (17, "Alicante")):
    print(f"docfig{numero}: activos criticos de {nombre_prov}")
    poligono = prov[prov["etiqueta"] == nombre_prov]
    g_p = g_act[g_act["provincia"] == nombre_prov]
    criticos = g_p[g_p["CRS_v6"] >= p95].sort_values("CRS_v6")

    fig, ax = plt.subplots(figsize=(ANCHO_IN * 0.72, ANCHO_IN * 0.86))
    poligono.plot(ax=ax, facecolor=COLOR_TIERRA, edgecolor=BASELINE,
                  linewidth=0.7, zorder=1)
    ax.scatter(g_p.geometry.x, g_p.geometry.y, s=0.7, c=BASELINE,
               linewidths=0, zorder=2)
    disp = ax.scatter(criticos.geometry.x, criticos.geometry.y, s=6,
                      c=criticos["CRS_v6"], cmap=cmap, vmin=p95, vmax=vmax,
                      linewidths=0, zorder=4)
    ax.set_aspect("equal")
    minx, miny, maxx, maxy = poligono.total_bounds
    m = 0.04 * max(maxx - minx, maxy - miny)
    ax.set_xlim(minx - m, maxx + m)
    ax.set_ylim(miny - m, maxy + m)
    ax.set_axis_off()

    n_sub = int((criticos["tipo_activo"] == "subestacion").sum())
    titulo(ax, f"Activos en zona crítica · {nombre_prov}",
           f"{len(criticos):,}".replace(",", ".") +
           f" de {len(g_p):,}".replace(",", ".") +
           f" activos de la provincia ({n(100 * len(criticos) / len(g_p), 1)} %), "
           f"de los que {n_sub} son subestaciones\nUmbral: percentil 95 regional, "
           f"CRS ≥ {n(p95)} · en gris, el resto de la red provincial")
    cb = fig.colorbar(disp, ax=ax, orientation="horizontal", fraction=0.032,
                      pad=0.02, aspect=34)
    cb.set_label("Climate Risk Score", color=INK_2, fontsize=7.5, labelpad=4)
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=2, colors=MUTED, labelsize=7)
    guardar(fig, f"docfig{numero}_criticos_{nombre_prov.lower().replace('ó','o')}.png")

print("\nListo. Insertar a 16 cm de ancho (las provinciales a 11,5 cm).")
