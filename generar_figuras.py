# ============================================================================
# generar_figuras.py
# ----------------------------------------------------------------------------
# Genera las figuras del TFM a partir de "activos_con_variables_climaticas.csv"
# y de la cartografía PATRICOVA descargada en "data/patricova/".
#
# Salida: carpeta "figuras/", PNG a 300 ppp y 16 cm de ancho, listos para
# insertar en Word sin reescalar.
#
# Criterios de diseño aplicados (los mismos en las cuatro figuras, para que la
# memoria se lea como un documento y no como cuatro estilos distintos):
#   - Paleta única, verificada para daltonismo (deuteranopía/protanopía/
#     tritanopía) y para contraste mínimo 3:1 sobre el fondo.
#   - Azul y naranja como los dos colores categóricos (apoyos / subestaciones).
#   - Un solo tono azul, de claro a oscuro, para todo lo que sea magnitud u
#     orden (periodo de retorno, número de activos). Nunca un arcoíris.
#   - Rejilla y ejes recesivos, marcas finas, leyenda siempre que haya dos
#     series, y etiquetas directas en lugar de un número sobre cada punto.
# ============================================================================

import os
import json
import glob

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# ---------------------------------------------------------------------------
# 0. Configuración global
# ---------------------------------------------------------------------------
CSV_ACTIVOS = "activos_con_variables_climaticas.csv"

# ---------------------------------------------------------------------------
# Version del indice de riesgo
# ---------------------------------------------------------------------------
# Si existen los ficheros de la version V6 se usan esos; si no, se cae a los de
# la V5. La V6 sustituye la peligrosidad por viento: pasa de la velocidad media
# anual del Global Wind Atlas normalizada min-max a la velocidad de retorno a 50
# anos normalizada contra la velocidad basica del CTE. Eso invalida tres figuras
# de la V5 (la de viento, la del riesgo compuesto y la de sensibilidad), que se
# regeneran; las del modelo supervisado NO cambian, porque alli la velocidad
# media sigue actuando como sustituto del relieve y el modelo no se ha tocado.
CRS_V6 = os.path.exists("activos_con_crs_v6.csv") and \
    os.path.exists("crs_parametros_v6.json")
RUTA_CRS = "activos_con_crs_v6.csv" if CRS_V6 else "activos_con_crs.csv"
RUTA_CRS_PARAMS = "crs_parametros_v6.json" if CRS_V6 else "crs_parametros.json"
COL_CRS = "CRS_v6" if CRS_V6 else "CRS"
VERSION_INDICE = "v6" if CRS_V6 else "v5"

# Variante del campo de extremos que se representa. La decide el script 07 con
# observaciones: el escalado multiplicativo quedo refutado porque implicaba rachas
# superiores a la maxima jamas registrada en el territorio. Las figuras deben
# mostrar la variante ADOPTADA, no la descartada.
COL_V50 = "V50_bruto_ms"
if CRS_V6 and os.path.exists("calibracion_v50.json"):
    with open("calibracion_v50.json", encoding="utf-8") as _fh:
        _calib = json.load(_fh)
    COL_V50 = "V50_bruto_ms" if _calib["decision"] == "bruta" else "V50_ms"
    ETIQUETA_V50 = ("V6: velocidad de retorno a 50 años"
                    if _calib["decision"] == "bruta"
                    else "V6: velocidad de retorno a 50 años (bajada de escala)")
else:
    ETIQUETA_V50 = "V6: velocidad de retorno a 50 años"

# Velocidades basicas del CTE DB-SE-AE, para marcarlas en las figuras de viento
V_BASICA_A, V_BASICA_C = 26.0, 29.0

# Ver la nota en generar_variables_climaticas.py: las capas geográficas viven
# fuera de OneDrive. Cambiable con la variable de entorno TFM_DATA_DIR.
DATA_DIR = os.environ.get(
    "TFM_DATA_DIR", os.path.join(os.path.expanduser("~"), "TFM_local", "data"))

PATRICOVA_DIR = os.path.join(DATA_DIR, "patricova")
PROVINCIAS_GEOJSON = os.path.join(DATA_DIR, "provincias_cv.geojson")
OUT_DIR = "figuras"

# --- Paleta (valores verificados; no cambiar sin volver a comprobarlos) -----
SURFACE = "#ffffff"   # fondo del gráfico: blanco puro
INK = "#0b0b0b"       # texto principal
INK_2 = "#52514e"     # texto secundario
MUTED = "#898781"     # ejes y etiquetas menores
GRID = "#e1e0d9"      # rejilla (hairline)
BASELINE = "#c3c2b7"  # línea base

# Relleno de las provincias en los mapas. NO es el fondo de la figura (ese es
# SURFACE, blanco puro): es un elemento del mapa, y su función es separar tierra
# de mar y delimitar el área de estudio, de modo que se vea qué zonas quedan sin
# activos. Ponerlo en blanco deja las provincias definidas solo por su contorno.
COLOR_TIERRA = "#f2f1ed"

SERIE_APOYO = "#2a78d6"        # categórico 1 (azul)
SERIE_SUBESTACION = "#eb6834"  # categórico 2 (naranja)

# Ordinal de 3 pasos para el periodo de retorno: más oscuro = más frecuente =
# más peligroso. Verificado: monotonía de luminosidad y separación de pasos.
COLOR_RETORNO = {25: "#0d366b", 100: "#2a78d6", 500: "#86b6ef"}

# Rampa secuencial para la matriz de peligrosidad (magnitud continua).
RAMPA_SECUENCIAL = [
    "#cde2fb", "#9ec5f4", "#86b6ef", "#5598e7",
    "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b",
]

ANCHO_CM = 16.0
ANCHO_IN = ANCHO_CM / 2.54

mpl.rcParams.update({
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 8,
    "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "text.color": INK,
    "axes.labelcolor": INK_2,
    "axes.edgecolor": BASELINE,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2,
    "axes.grid": False,
    "grid.color": GRID,
    "grid.linewidth": 0.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
    "legend.fontsize": 8,
})

# Correspondencia nivel PATRICOVA -> (periodo de retorno, calado), tal y como
# la define el campo d_pelig de la propia fuente oficial.
NIVEL_A_RETORNO = {1: 25, 2: 100, 3: 25, 4: 100, 5: 500, 6: 500}
NIVEL_A_CALADO = {1: "alto", 2: "alto", 3: "bajo", 4: "bajo", 5: "alto", 6: "bajo"}


def limpiar_eje(ax, ejes=("left", "bottom")):
    """Deja solo los ejes indicados, con la línea base recesiva."""
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_visible(lado in ejes)
    for lado in ejes:
        ax.spines[lado].set_linewidth(0.6)
        ax.spines[lado].set_color(BASELINE)


def titulo(ax, texto, subtitulo=None):
    """Título alineado a la izquierda; el subtítulo explica cómo leer el gráfico."""
    # El hueco reservado crece con el número de líneas del subtítulo; si no, un
    # subtítulo de varias líneas se solapa con el título.
    lineas = subtitulo.count("\n") + 1 if subtitulo else 0
    ax.set_title(texto, loc="left", fontsize=9.5, fontweight="bold",
                 color=INK, pad=8 + 11 * lineas)
    if subtitulo:
        ax.text(0, 1.015, subtitulo, transform=ax.transAxes, fontsize=7.8,
                color=INK_2, va="bottom", ha="left", linespacing=1.45)


def guardar(fig, nombre):
    os.makedirs(OUT_DIR, exist_ok=True)
    ruta = os.path.join(OUT_DIR, nombre)
    fig.savefig(ruta, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print(f"  generada: {ruta}")


# ---------------------------------------------------------------------------
# 1. Cargar datos
# ---------------------------------------------------------------------------
print("Cargando datos...")
df = pd.read_csv(CSV_ACTIVOS, sep=";", encoding="utf-8-sig", low_memory=False)
df["nivel"] = pd.to_numeric(df["nivel_peligrosidad_patricova"], errors="coerce")
df["retorno"] = df["nivel"].map(NIVEL_A_RETORNO)
df["calado"] = df["nivel"].map(NIVEL_A_CALADO)

# El rectángulo de consulta de Overpass desborda necesariamente los límites de
# la comunidad (Teruel, Cuenca, Albacete, Murcia, Tarragona y mar adentro). Las
# figuras representan SOLO el área de estudio, así que se descarta lo que cae
# fuera; el descarte es geométrico, contra los polígonos provinciales del ICV.
n_bruto = len(df)
df = df[df["provincia"].notna()].copy()
print(f"  {n_bruto} activos descargados, {len(df)} dentro de la Comunitat "
      f"({n_bruto - len(df)} descartados por caer fuera)")

apoyos = df[df["tipo_activo"] == "apoyo"]
subes = df[df["tipo_activo"] == "subestacion"]
print(f"  -> {len(apoyos)} apoyos, {len(subes)} subestaciones")

gdf = gpd.GeoDataFrame(
    df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326"
).to_crs(epsg=3857)

print("Cargando PATRICOVA...")
capas = []
for f in sorted(glob.glob(os.path.join(PATRICOVA_DIR, "peligrosidad_*.geojson"))):
    c = gpd.read_file(f)
    c["n_pelig"] = c["n_pelig"].astype(int)
    capas.append(c[["n_pelig", "geometry"]])
pat = gpd.GeoDataFrame(pd.concat(capas, ignore_index=True), crs=capas[0].crs)
pat["retorno"] = pat["n_pelig"].map(NIVEL_A_RETORNO)
pat = pat.to_crs(epsg=3857)
print(f"  {len(pat)} polígonos")

print("Cargando límites provinciales...")
provincias = gpd.read_file(PROVINCIAS_GEOJSON).to_crs(epsg=3857)
provincias["etiqueta"] = provincias["nombre"].str.split("/").str[-1]
print(f"  {len(provincias)} provincias: {', '.join(provincias['etiqueta'])}")


def marco_provincial(ax, etiquetar=True):
    """
    Dibuja el contorno de las tres provincias como contexto geográfico.

    Se usa esto en lugar de un mapa base de teselas por tres razones: es
    vectorial (nítido en impresión a cualquier tamaño), procede de la misma
    administración que PATRICOVA (coherencia de fuentes), y no introduce ruido
    de carreteras y topónimos que compita con los datos. El relleno es un gris
    apenas perceptible: separa tierra de mar sin llamar la atención.
    """
    provincias.plot(ax=ax, facecolor="#f2f1ed", edgecolor=BASELINE,
                    linewidth=0.6, zorder=1)
    if etiquetar:
        for _, fila in provincias.iterrows():
            # representative_point() cae siempre dentro del polígono, a
            # diferencia del centroide, que en una forma cóncava puede caer fuera.
            punto = fila.geometry.representative_point()
            texto = ax.annotate(fila["etiqueta"].upper(), xy=(punto.x, punto.y),
                                ha="center", va="center", fontsize=6.5,
                                color=MUTED, zorder=6)
            # Halo del color del fondo: en Castellón la etiqueta cae justo sobre
            # la mancha densa de apoyos y sin halo es ilegible.
            texto.set_path_effects([
                path_effects.withStroke(linewidth=2.2, foreground=SURFACE)
            ])
    # Relación de aspecto 1:1. Sin esto, scatter() estira el mapa y la geografía
    # queda deformada.
    ax.set_aspect("equal")
    minx, miny, maxx, maxy = provincias.total_bounds
    margen = 0.03 * max(maxx - minx, maxy - miny)
    ax.set_xlim(minx - margen, maxx + margen)
    ax.set_ylim(miny - margen, maxy + margen)


# ---------------------------------------------------------------------------
# FIGURA 1 — Distribución geográfica de los activos
# ---------------------------------------------------------------------------
# Forma: mapa de puntos. Trabajo del color: identidad (dos tipos de activo),
# por tanto categórico de 2 series. Los apoyos van finos y translúcidos porque
# son 25.761 y en un mapa de este tamaño se solapan; las subestaciones llevan
# un anillo blanco de separación para que no se pierdan sobre la mancha azul.
print("\nFigura 1: distribución geográfica de los activos")
fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 1.12))
g_ap = gdf[gdf["tipo_activo"] == "apoyo"]
g_su = gdf[gdf["tipo_activo"] == "subestacion"]
marco_provincial(ax)
ax.scatter(g_ap.geometry.x, g_ap.geometry.y, s=1.2, c=SERIE_APOYO,
           alpha=0.35, linewidths=0, zorder=3)
ax.scatter(g_su.geometry.x, g_su.geometry.y, s=16, c=SERIE_SUBESTACION,
           edgecolors=SURFACE, linewidths=0.5, zorder=4)
ax.set_axis_off()
titulo(ax,
       "Distribución geográfica de los activos eléctricos analizados",
       "Comunitat Valenciana · fuente: OpenStreetMap vía Overpass API")
# La leyenda va DEBAJO del mapa. Con el área de consulta corregida ya no queda
# hueco interior: la red cubre las tres provincias de extremo a extremo, y
# cualquier posición dentro del mapa taparía datos.
ax.legend(handles=[
    Line2D([], [], marker="o", linestyle="", markersize=3.5,
           markerfacecolor=SERIE_APOYO, markeredgecolor="none",
           label=f"Apoyos de línea ({len(g_ap):,})".replace(",", ".")),
    Line2D([], [], marker="o", linestyle="", markersize=5,
           markerfacecolor=SERIE_SUBESTACION, markeredgecolor=SURFACE,
           markeredgewidth=0.5,
           label=f"Subestaciones ({len(g_su):,})".replace(",", ".")),
], loc="upper left", bbox_to_anchor=(0.0, -0.005), ncol=2,
   labelcolor=INK_2, handlelength=1.6, columnspacing=2.2)
ax.text(0.0, -0.045, "Límites provinciales: Institut Cartogràfic Valencià",
        transform=ax.transAxes, fontsize=6, color=MUTED, va="top")
guardar(fig, "fig1_distribucion_activos.png")


# ---------------------------------------------------------------------------
# FIGURA 2 — Peligrosidad por inundación y activos expuestos
# ---------------------------------------------------------------------------
# Forma: mapa temático. Trabajo del color: orden (periodo de retorno), por tanto
# un solo tono azul de claro a oscuro; más oscuro = inundación más frecuente.
# Los activos expuestos se marcan en tinta neutra para no competir con la rampa.
print("Figura 2: peligrosidad por inundación y activos expuestos")
fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 1.12))
marco_provincial(ax)
for retorno in (500, 100, 25):      # de menos a más peligroso, para que el
    sub = pat[pat["retorno"] == retorno]   # oscuro quede encima
    sub.plot(ax=ax, color=COLOR_RETORNO[retorno], linewidth=0, zorder=3)
expuestos = gdf[gdf["nivel"].notna()]
# Puntos finos: donde los apoyos siguen el fondo de valle se acumulan cientos en
# muy poco espacio, y con una marca más gruesa forman manchas que tapan
# justamente el polígono de peligrosidad que da sentido a la figura.
ax.scatter(expuestos.geometry.x, expuestos.geometry.y, s=1.1,
           c=INK, alpha=0.7, linewidths=0, zorder=5)
ax.set_aspect("equal")
ax.set_axis_off()
pct = f"{100 * len(expuestos) / len(gdf):.1f}".replace(".", ",")
titulo(ax,
       "Peligrosidad por inundación PATRICOVA y activos expuestos",
       f"{len(expuestos):,}".replace(",", ".") +
       f" de {len(gdf):,}".replace(",", ".") +
       f" activos ({pct} %) caen en zona inundable")
# La leyenda va DEBAJO del mapa, no dentro: colocada en la esquina inferior
# izquierda tapaba la Vega Baja del Segura, que es una de las zonas de mayor
# peligrosidad de toda la cartografía.
ax.legend(handles=[
    Patch(facecolor=COLOR_RETORNO[25], edgecolor="none", label="Retorno 25 años (frecuencia alta)"),
    Patch(facecolor=COLOR_RETORNO[100], edgecolor="none", label="Retorno 100 años (frecuencia media)"),
    Patch(facecolor=COLOR_RETORNO[500], edgecolor="none", label="Retorno 500 años (frecuencia baja)"),
    Line2D([], [], marker="o", linestyle="", markersize=3,
           markerfacecolor=INK, markeredgecolor="none", label="Activo en zona inundable"),
], loc="upper left", bbox_to_anchor=(0.0, -0.005), ncol=2,
   labelcolor=INK_2, handlelength=1.6, columnspacing=1.6)
ax.text(0.0, -0.075,
        "Cartografía: PATRICOVA y límites provinciales, Generalitat Valenciana (Institut Cartogràfic Valencià)",
        transform=ax.transAxes, fontsize=6, color=MUTED, va="top")
guardar(fig, "fig2_peligrosidad_patricova.png")


# ---------------------------------------------------------------------------
# FIGURA 3 — Matriz de peligrosidad (frecuencia x calado)
# ---------------------------------------------------------------------------
# Los seis niveles de PATRICOVA no son una escala lineal: son el cruce de tres
# periodos de retorno por dos clases de calado. Representarlos como una rejilla
# 2x3 muestra esa estructura, que un gráfico de barras de seis niveles oculta.
# Forma: heatmap. Trabajo del color: magnitud -> secuencial de un solo tono.
print("Figura 3: matriz de peligrosidad frecuencia x calado")
retornos = [25, 100, 500]
calados = ["alto", "bajo"]
matriz = np.zeros((len(calados), len(retornos)), dtype=int)
for i, cal in enumerate(calados):
    for j, ret in enumerate(retornos):
        matriz[i, j] = int(((df["calado"] == cal) & (df["retorno"] == ret)).sum())

fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 0.42))
cmap = mpl.colors.LinearSegmentedColormap.from_list("azul", RAMPA_SECUENCIAL)
# El gap de 2 px entre celdas se consigue con un borde del color del fondo.
im = ax.imshow(matriz, cmap=cmap, aspect="auto", vmin=0, vmax=matriz.max())
for i in range(len(calados)):
    for j in range(len(retornos)):
        ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                   edgecolor=SURFACE, linewidth=2, zorder=4))
        valor = matriz[i, j]
        # Texto claro sobre celda oscura y viceversa, para no perder contraste.
        color_txt = SURFACE if valor > matriz.max() * 0.55 else INK
        ax.text(j, i - 0.10, f"{valor:,}".replace(",", "."), ha="center",
                va="center", fontsize=11, fontweight="bold", color=color_txt, zorder=5)
        ax.text(j, i + 0.22, f"nivel {int([k for k, v in NIVEL_A_RETORNO.items() if v == retornos[j] and NIVEL_A_CALADO[k] == calados[i]][0])}",
                ha="center", va="center", fontsize=6.5, color=color_txt, alpha=0.85, zorder=5)
ax.set_xticks(range(len(retornos)))
ax.set_xticklabels([f"{r} años" for r in retornos])
ax.set_yticks(range(len(calados)))
ax.set_yticklabels([f"calado {c}\n({'>' if c == 'alto' else '<'} 0,8 m)" for c in calados])
ax.set_xlabel("Periodo de retorno", color=INK_2)
ax.tick_params(length=0)
for lado in ("top", "right", "left", "bottom"):
    ax.spines[lado].set_visible(False)
titulo(ax,
       "Activos eléctricos por nivel de peligrosidad PATRICOVA",
       "La intensidad del azul codifica el NÚMERO de activos, no la gravedad: "
       "el nivel 1 es el más\npeligroso (crecida frecuente y calado alto) y es "
       "precisamente uno de los menos poblados")
guardar(fig, "fig3_matriz_peligrosidad.png")


# ---------------------------------------------------------------------------
# FIGURA 4 — Por qué la velocidad media no sirve como variable de peligrosidad
# ---------------------------------------------------------------------------
# En la version V5 esta figura comparaba la velocidad media entre apoyos y
# subestaciones. Con la V6 esa comparacion pierde interes, porque la velocidad
# media deja de ser la variable de peligrosidad. La figura se reorienta a
# sostener el argumento del cambio: las DOS variables sobre el mismo eje, con las
# velocidades basicas de diseno del CTE marcadas.
#
# El argumento se ve de un golpe: la velocidad media se concentra entre 1 y 11
# m/s, un orden de magnitud por debajo de cualquier umbral estructural, mientras
# que la velocidad de retorno a 50 anos alcanza y rebasa la franja de diseno. Una
# normalizacion min-max sobre la primera obliga a que el activo mas ventoso del
# area valga 1 aunque su viento sea inocuo, que es exactamente lo que comprimia
# la rama eolica del indice.
#
# Forma: dos histogramas de contorno, una serie por variable, normalizados cada
# uno al 100 % de su propia distribucion para que sean comparables en forma.
if CRS_V6:
    print("Figura 4: comparacion de la variable de viento, V5 frente a V6")
    crs6 = pd.read_csv(RUTA_CRS, sep=";", encoding="utf-8-sig", low_memory=False)
    fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 0.52))
    x_max = 32
    bins = np.arange(0, x_max + 1, 0.75)
    for datos, color, etiqueta in (
        (crs6["velocidad_viento_ms"].dropna(), SERIE_SUBESTACION,
         "V5: velocidad media anual (Global Wind Atlas)"),
        (crs6[COL_V50].dropna(), SERIE_APOYO, ETIQUETA_V50),
    ):
        pesos = np.ones(len(datos)) / len(datos) * 100
        ax.hist(datos, bins=bins, weights=pesos, histtype="step",
                linewidth=1.7, color=color, label=etiqueta, zorder=3)

    # La mediana se etiqueta SOBRE su propio pico, no bajo el eje: debajo choca
    # con el rotulo del eje horizontal.
    ax.set_ylim(0, ax.get_ylim()[1] * 1.18)
    tope = ax.get_ylim()[1]
    for datos, color, alineacion in (
        (crs6["velocidad_viento_ms"].dropna(), SERIE_SUBESTACION, "right"),
        (crs6[COL_V50].dropna(), SERIE_APOYO, "left"),
    ):
        mediana = float(datos.median())
        pico = float(np.histogram(datos, bins=bins,
                                  weights=np.ones(len(datos)) / len(datos) * 100)[0].max())
        ax.annotate(f"mediana {mediana:.1f}".replace(".", ",") + " m/s",
                    xy=(mediana, pico), xytext=(6 if alineacion == "left" else -6, 6),
                    textcoords="offset points", fontsize=7.2, color=color,
                    ha=alineacion, va="bottom", fontweight="bold")

    # Umbrales normativos, rotulados a media altura para no chocar con la leyenda
    for vb, zona in ((V_BASICA_A, "26 m/s · zona A"), (V_BASICA_C, "29 m/s · zona C")):
        ax.axvline(vb, color=INK, linewidth=0.9, linestyle=(0, (4, 2)), zorder=4)
        ax.annotate(zona, xy=(vb, tope * 0.52), xytext=(4, 0),
                    textcoords="offset points", fontsize=6.8, color=INK,
                    va="center", ha="left", rotation=90)

    ax.yaxis.grid(True, zorder=1)
    ax.set_axisbelow(True)
    ax.set_xlabel("Velocidad de viento a 10 m (m/s)", color=INK_2)
    ax.set_ylabel("% de activos", color=INK_2)
    ax.set_xlim(0, x_max)
    limpiar_eje(ax, ejes=("bottom",))
    # La leyenda va en el hueco central, entre las dos distribuciones
    ax.legend(loc="upper center", bbox_to_anchor=(0.42, 1.0),
              labelcolor=INK_2, fontsize=7.4)
    titulo(ax,
           "Por qué la velocidad media no mide peligrosidad estructural",
           "Ambas distribuciones normalizadas al 100 % · las líneas marcan la "
           "velocidad básica de diseño\ndel CTE DB-SE-AE, con la que se "
           "dimensionan los apoyos en España")
    guardar(fig, "fig4_viento.png")
else:
    # Version V5: comparacion entre tipos de activo sobre la velocidad media.
    print("Figura 4: distribución de velocidad de viento (V5)")
    fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 0.5))
    bins = np.arange(0, 9.5, 0.35)
    for datos, color, etiqueta in (
        (apoyos["velocidad_viento_ms"].dropna(), SERIE_APOYO, "Apoyos de línea"),
        (subes["velocidad_viento_ms"].dropna(), SERIE_SUBESTACION, "Subestaciones"),
    ):
        pesos = np.ones(len(datos)) / len(datos) * 100
        ax.hist(datos, bins=bins, weights=pesos, histtype="step",
                linewidth=1.6, color=color, label=etiqueta, zorder=3)
        mediana = datos.median()
        ax.axvline(mediana, color=color, linewidth=1, linestyle=(0, (3, 2)),
                   alpha=0.7, zorder=2)
        ax.annotate(f"mediana {mediana:.2f} m/s".replace(".", ","),
                    xy=(mediana, ax.get_ylim()[1]), xytext=(4, -2),
                    textcoords="offset points", fontsize=7, color=color,
                    va="top", ha="left")
    ax.yaxis.grid(True, zorder=1)
    ax.set_axisbelow(True)
    ax.set_xlabel("Velocidad media de viento a 50 m (m/s)", color=INK_2)
    ax.set_ylabel("% de activos del grupo", color=INK_2)
    ax.set_xlim(0, 9)
    limpiar_eje(ax, ejes=("bottom",))
    ax.legend(loc="upper right", labelcolor=INK_2)
    titulo(ax,
           "Exposición a viento de los activos eléctricos",
           "Porcentaje dentro de cada grupo · fuente: Global Wind Atlas")
    guardar(fig, "fig4_viento.png")

# ---------------------------------------------------------------------------
# FIGURA 5 — Selección del número de clusters
# ---------------------------------------------------------------------------
# Dos paneles, una serie cada uno: no hace falta leyenda, el título de cada
# panel nombra lo que se representa. Se etiqueta directamente el óptimo en lugar
# de anotar todos los puntos.
RUTA_METRICAS = "clustering_metricas.json"
RUTA_CLUSTERS = "subestaciones_clusters.csv"

if os.path.exists(RUTA_METRICAS) and os.path.exists(RUTA_CLUSTERS):
    print("Figura 5: seleccion del numero de clusters")
    with open(RUTA_METRICAS, encoding="utf-8") as fh:
        met = json.load(fh)
    barrido = pd.DataFrame(met["barrido"])
    k_opt = met["k_optimo"]

    fig, axes = plt.subplots(1, 2, figsize=(ANCHO_IN, ANCHO_IN * 0.44))

    for ax, columna, etiqueta_y, titulo_panel in (
        (axes[0], "inercia", "Inercia (suma de distancias²)", "Método del codo"),
        (axes[1], "silhouette", "Coeficiente de silhouette", "Coeficiente de silhouette"),
    ):
        ax.plot(barrido["k"], barrido[columna], color=SERIE_APOYO,
                linewidth=1.8, marker="o", markersize=3.2,
                markerfacecolor=SERIE_APOYO, markeredgecolor=SURFACE,
                markeredgewidth=0.6, zorder=3)
        # Marca del k elegido, etiquetada por debajo para no chocar con el
        # título del panel.
        valor = float(barrido.loc[barrido["k"] == k_opt, columna].iloc[0])
        ax.scatter([k_opt], [valor], s=52, facecolor="none",
                   edgecolor=INK, linewidth=1.2, zorder=4)
        ax.annotate(f"k = {k_opt}", xy=(k_opt, valor), xytext=(9, -11),
                    textcoords="offset points", fontsize=7.5,
                    fontweight="bold", color=INK)
        ax.set_xlabel("Número de clusters (k)", color=INK_2)
        ax.set_ylabel(etiqueta_y, color=INK_2, fontsize=7.5)
        ax.set_title(titulo_panel, loc="left", fontsize=8.4,
                     fontweight="bold", color=INK, pad=6)
        ax.set_xticks(barrido["k"][::2])
        ax.yaxis.grid(True, zorder=1)
        ax.set_axisbelow(True)
        limpiar_eje(ax, ejes=("bottom",))

    # Se reserva la banda superior con tight_layout(rect=...) ANTES de escribir
    # el título; si se escribe primero, tight_layout lo ignora y se solapa.
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.text(0.0, 0.985, "Selección del número de clusters de subestaciones",
             ha="left", va="top", fontsize=9.5, fontweight="bold", color=INK)
    fig.text(0.0, 0.915,
             f"Barrido de k entre {barrido['k'].min()} y {barrido['k'].max()} sobre "
             f"{met['n_subestaciones']} subestaciones · óptimo en k = {k_opt} "
             f"(silhouette {met['silhouette_optimo']:.4f}). El barrido anterior se "
             f"detenía en k = 7,\nen el propio extremo del intervalo, donde un "
             f"máximo no puede confirmarse como tal.",
             ha="left", va="top", fontsize=7.6, color=INK_2, linespacing=1.45)
    guardar(fig, "fig5_seleccion_k.png")

    # -----------------------------------------------------------------------
    # FIGURA 6 — Los clusters, en facetas
    # -----------------------------------------------------------------------
    # Con k=8 no se puede colorear un solo mapa: la paleta validada admite tres
    # series como máximo en formatos de dispersión (un mapa de puntos lo es), y
    # ocho tonos serían indistinguibles para un lector con daltonismo. La
    # solución que corresponde es facetar: un panel por cluster, cada uno con
    # una sola serie destacada y el resto de subestaciones en gris de contexto.
    print("Figura 6: clusters en facetas")
    cl = pd.read_csv(RUTA_CLUSTERS, sep=";", encoding="utf-8-sig", low_memory=False)
    g_cl = gpd.GeoDataFrame(
        cl, geometry=gpd.points_from_xy(cl["lon"], cl["lat"]), crs="EPSG:4326"
    ).to_crs(epsg=3857)

    clusters = sorted(cl["cluster"].unique())
    ncol = 4
    nrow = int(np.ceil(len(clusters) / ncol))
    fig, axes = plt.subplots(nrow, ncol,
                             figsize=(ANCHO_IN, ANCHO_IN * 0.92 * nrow / 2))
    axes = np.atleast_1d(axes).ravel()

    for ax, c in zip(axes, clusters):
        sub_c = cl[cl["cluster"] == c]
        marco_provincial(ax, etiquetar=False)
        # Contexto: todas las subestaciones, en gris recesivo
        ax.scatter(g_cl.geometry.x, g_cl.geometry.y, s=1.6, c=BASELINE,
                   linewidths=0, zorder=3)
        # La serie del panel
        g_c = g_cl[g_cl["cluster"] == c]
        ax.scatter(g_c.geometry.x, g_c.geometry.y, s=7, c=SERIE_APOYO,
                   edgecolors=SURFACE, linewidths=0.3, zorder=4)
        ax.set_axis_off()
        ax.set_title(
            f"Cluster {c} · n = {len(sub_c)}\n"
            f"{sub_c['provincia'].value_counts().idxmax()}",
            loc="center", fontsize=7, color=INK_2, pad=3, linespacing=1.4)

    for ax in axes[len(clusters):]:
        ax.set_axis_off()

    # Igual que en la figura 5: se reserva la banda superior antes de escribir
    # el título, no después.
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.text(0.0, 0.995, "Agrupamiento K-Means de las subestaciones",
             ha="left", va="top", fontsize=9.5, fontweight="bold", color=INK)
    fig.text(0.0, 0.968,
             f"k = {k_opt} · variables: latitud, longitud y densidad de apoyos en "
             "5 km · en gris, el resto de subestaciones como contexto",
             ha="left", va="top", fontsize=7.8, color=INK_2)
    guardar(fig, "fig6_clusters.png")
else:
    print(f"\n(sin '{RUTA_METRICAS}' o '{RUTA_CLUSTERS}': "
          "ejecuta antes clustering_subestaciones.py)")

# ---------------------------------------------------------------------------
# FIGURAS 7 y 8 — Climate Risk Score
# ---------------------------------------------------------------------------
# RUTA_CRS, RUTA_CRS_PARAMS y COL_CRS se fijan al principio del script segun la
# version disponible (V6 si existen sus ficheros, V5 en caso contrario). No deben
# redefinirse aqui.
if os.path.exists(RUTA_CRS) and os.path.exists(RUTA_CRS_PARAMS):
    print(f"Figura 7: activos de mayor riesgo climatico ({VERSION_INDICE})")
    crs = pd.read_csv(RUTA_CRS, sep=";", encoding="utf-8-sig", low_memory=False)
    with open(RUTA_CRS_PARAMS, encoding="utf-8") as fh:
        par = json.load(fh)

    g_crs = gpd.GeoDataFrame(
        crs, geometry=gpd.points_from_xy(crs["lon"], crs["lat"]), crs="EPSG:4326"
    ).to_crs(epsg=3857)

    # Se destaca el 5 % de mayor riesgo. Pintar los 38.939 activos coloreados por
    # CRS sería ilegible: la inmensa mayoría tiene un índice bajo y muy parecido,
    # y su mancha taparía justamente los casos que importan. El resto queda en
    # gris recesivo como contexto de red.
    umbral = crs[COL_CRS].quantile(0.95)
    altos = g_crs[g_crs[COL_CRS] >= umbral].sort_values(COL_CRS)

    fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 1.16))
    marco_provincial(ax)
    ax.scatter(g_crs.geometry.x, g_crs.geometry.y, s=0.8, c=BASELINE,
               linewidths=0, zorder=3)
    cmap = mpl.colors.LinearSegmentedColormap.from_list("azul", RAMPA_SECUENCIAL)
    disp = ax.scatter(altos.geometry.x, altos.geometry.y, s=4.5,
                      c=altos[COL_CRS], cmap=cmap,
                      vmin=umbral, vmax=crs[COL_CRS].max(),
                      linewidths=0, zorder=5)
    ax.set_aspect("equal")
    ax.set_axis_off()
    pesos_txt = (f"{par['peso_inundacion']:.2f} inundación / "
                 f"{par['peso_viento']:.2f} viento").replace(".", ",")
    # La figura debe declarar de que variable de peligrosidad eolica se trata: es
    # el cambio que separa la V5 de la V6 y sin decirlo la figura es ambigua.
    variable_txt = ("peligrosidad eólica sobre la velocidad de retorno a 50 años"
                    if CRS_V6 else
                    "peligrosidad eólica sobre la velocidad media anual")
    titulo(ax,
           "Activos eléctricos de mayor riesgo climático compuesto",
           f"El 5 % de mayor Climate Risk Score "
           f"({len(altos):,}".replace(",", ".") +
           f" de {len(crs):,}".replace(",", ".") +
           " activos) · en gris, el resto de la red\n"
           f"Índice compuesto peligrosidad × vulnerabilidad × criticidad, con "
           f"pesos {pesos_txt} · {variable_txt}")

    # La barra de color lleva su propia etiqueta; no se añade una nota aparte
    # debajo, porque en un eje sin marco ambas caen en el mismo sitio y se pisan.
    cb = fig.colorbar(disp, ax=ax, orientation="horizontal", fraction=0.030,
                      pad=0.02, aspect=42)
    cb.set_label("Climate Risk Score (0-100)", color=INK_2, fontsize=7.5,
                 labelpad=4)
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=2, colors=MUTED, labelsize=7)
    guardar(fig, "fig7_riesgo_compuesto.png")

    # -----------------------------------------------------------------------
    print("Figura 8: sensibilidad del indice al reparto de pesos")
    sens = pd.DataFrame(par["sensibilidad_pesos"])
    fig, axes = plt.subplots(1, 2, figsize=(ANCHO_IN, ANCHO_IN * 0.40))

    for ax, columna, etiqueta_y, titulo_panel, referencia in (
        (axes[0], "spearman", "Correlación de Spearman",
         "Estabilidad de la ordenación", 1.0),
        (axes[1], "solape_top5_pct", "% de coincidencia",
         "Coincidencia en el 5 % de mayor riesgo", 100.0),
    ):
        ax.plot(sens["peso_inundacion"], sens[columna], color=SERIE_APOYO,
                linewidth=1.8, marker="o", markersize=3.4,
                markerfacecolor=SERIE_APOYO, markeredgecolor=SURFACE,
                markeredgewidth=0.6, zorder=3)
        # El peso de referencia, donde por construcción la comparación vale 1
        ax.scatter([par["peso_inundacion"]], [referencia], s=52, facecolor="none",
                   edgecolor=INK, linewidth=1.2, zorder=4)
        ax.annotate("reparto\nadoptado", xy=(par["peso_inundacion"], referencia),
                    xytext=(-4, -22), textcoords="offset points", fontsize=6.4,
                    color=INK_2, ha="center", linespacing=1.3)
        ax.set_xlabel("Peso asignado a la inundación", color=INK_2)
        ax.set_ylabel(etiqueta_y, color=INK_2, fontsize=7.5)
        ax.set_title(titulo_panel, loc="left", fontsize=8.4,
                     fontweight="bold", color=INK, pad=6)
        ax.yaxis.grid(True, zorder=1)
        ax.set_axisbelow(True)
        limpiar_eje(ax, ejes=("bottom",))

    fig.tight_layout(rect=(0, 0, 1, 0.85))
    fig.text(0.0, 0.985,
             "Sensibilidad del índice al reparto de pesos entre amenazas",
             ha="left", va="top", fontsize=9.5, fontweight="bold", color=INK)
    # Ojo: la coma decimal solo se aplica al NÚMERO. Aplicar replace(".", ",")
    # sobre la frase completa convertiría también el punto final en una coma.
    spearman_min = f"{sens['spearman'].min():.2f}".replace(".", ",")
    fig.text(0.0, 0.915,
             "Comparación de cada reparto alternativo frente al adoptado. La "
             "ordenación de activos se mantiene\nestable (Spearman ≥ "
             f"{spearman_min}) en todo el rango explorado, de modo que la "
             "conclusión no depende de la elección de pesos.",
             ha="left", va="top", fontsize=7.6, color=INK_2, linespacing=1.45)
    guardar(fig, "fig8_sensibilidad_pesos.png")
else:
    print(f"\n(sin '{RUTA_CRS}': ejecuta antes climate_risk_score.py)")

# ---------------------------------------------------------------------------
# FIGURAS 9 y 10 — Modelado supervisado de inundabilidad
# ---------------------------------------------------------------------------
RUTA_MET = "modelado_metricas.json"
RUTA_SHAP = "shap_valores.npy"
RUTA_SHAP_X = "shap_muestra.csv"

ETIQUETAS_VAR = {
    "altitud_m": "Altitud (m)",
    "pendiente_grados": "Pendiente (°)",
    "distancia_cauce_m": "Distancia al cauce (m)",
    "densidad_5km": "Densidad de red (5 km)",
    "velocidad_viento_ms": "Velocidad de viento (m/s)",
    "clase_pole": "Clase: poste",
    "clase_tower": "Clase: torre",
    "clase_portal": "Clase: pórtico",
    "clase_subestacion": "Clase: subestación",
}

if os.path.exists(RUTA_MET) and os.path.exists(RUTA_SHAP):
    with open(RUTA_MET, encoding="utf-8") as fh:
        met = json.load(fh)

    # -----------------------------------------------------------------------
    # FIGURA 9 — Comparación de esquemas de validación
    # -----------------------------------------------------------------------
    # Forma: barras agrupadas. Trabajo del color: identidad (dos esquemas de
    # validación), luego categórico de 2 series. Dos paneles porque ROC-AUC y
    # PR-AUC tienen escalas distintas y no deben compartir eje: superponerlas
    # sería el error de los dos ejes verticales.
    print("Figura 9: comparacion de esquemas de validacion")
    modelos_l = list(met["cv_espacial"].keys())
    fig, axes = plt.subplots(1, 2, figsize=(ANCHO_IN, ANCHO_IN * 0.40))
    ancho = 0.36
    pos = np.arange(len(modelos_l))

    for ax, metrica, etiqueta in ((axes[0], "roc_auc", "ROC-AUC"),
                                  (axes[1], "pr_auc", "PR-AUC")):
        for desp, clave, color, nombre in (
            (-ancho / 2, "cv_espacial", SERIE_APOYO, "Bloques espaciales"),
            (+ancho / 2, "cv_aleatoria", SERIE_SUBESTACION, "Partición aleatoria"),
        ):
            vals = [met[clave][m][metrica] for m in modelos_l]
            errs = [met[clave][m][f"{metrica}_std"] for m in modelos_l]
            barras = ax.bar(pos + desp, vals, ancho * 0.92, color=color,
                            label=nombre, zorder=3)
            ax.errorbar(pos + desp, vals, yerr=errs, fmt="none",
                        ecolor=INK_2, elinewidth=0.9, capsize=2.5, zorder=4)
            # Etiqueta directa sobre cada barra: con cuatro barras por panel es
            # más legible que obligar a leer el eje.
            for b, v in zip(barras, vals):
                ax.annotate(f"{v:.3f}".replace(".", ","),
                            xy=(b.get_x() + b.get_width() / 2, v),
                            xytext=(0, 3), textcoords="offset points",
                            ha="center", fontsize=6.8, color=INK_2)
        ax.set_xticks(pos)
        ax.set_xticklabels(modelos_l)
        ax.set_ylim(0, 1.06)
        ax.set_ylabel(etiqueta, color=INK_2, fontsize=7.5)
        ax.set_title(etiqueta, loc="left", fontsize=8.4, fontweight="bold",
                     color=INK, pad=6)
        ax.yaxis.grid(True, zorder=1)
        ax.set_axisbelow(True)
        limpiar_eje(ax, ejes=("bottom",))
    axes[0].legend(loc="lower left", labelcolor=INK_2, fontsize=7)

    # Espacio reservado generoso: el subtítulo ocupa tres líneas y con menos
    # margen se solaparía con los títulos de los dos paneles.
    fig.tight_layout(rect=(0, 0, 1, 0.76))
    fig.text(0.0, 0.995,
             "El coste de ignorar la autocorrelación espacial",
             ha="left", va="top", fontsize=9.5, fontweight="bold", color=INK)
    d_pr = (met["cv_aleatoria"]["Random Forest"]["pr_auc"]
            - met["cv_espacial"]["Random Forest"]["pr_auc"])
    # La coma decimal se aplica SOLO al número. Encadenar .replace(".", ",") a un
    # literal concatenado convertiría también los puntos de la propia frase.
    d_pr_txt = f"{d_pr:.2f}".replace(".", ",")
    fig.text(0.0, 0.925,
             "Mismos modelos y mismas variables; solo cambia cómo se reparten los "
             "datos entre entrenamiento y prueba.\nCon partición aleatoria el "
             f"PR-AUC del Random Forest sube {d_pr_txt} puntos, porque el conjunto "
             "de prueba contiene\nvecinos inmediatos de los de entrenamiento. Esa "
             "mejora no existe: es fuga espacial.",
             ha="left", va="top", fontsize=7.6, color=INK_2, linespacing=1.45)
    guardar(fig, "fig9_validacion_espacial.png")

    # -----------------------------------------------------------------------
    # FIGURA 10 — SHAP
    # -----------------------------------------------------------------------
    # Diagrama de enjambre construido a mano en lugar de con shap.summary_plot,
    # para poder usar la paleta verificada del documento: el gráfico por defecto
    # de la librería emplea una rampa rojo-azul que no supera la comprobación de
    # daltonismo y no encaja con el resto de las figuras.
    #
    # Eje horizontal: contribución de la variable al log-odds de estar en zona
    # inundable. Color: valor de la propia variable, en rampa secuencial de un
    # solo tono (magnitud), normalizado por rango percentil para que unos pocos
    # valores extremos no aplasten toda la escala.
    print("Figura 10: contribuciones SHAP")
    vals_shap = np.load(RUTA_SHAP)
    X_shap = pd.read_csv(RUTA_SHAP_X, sep=";", encoding="utf-8-sig")

    orden = (pd.Series(np.abs(vals_shap).mean(axis=0), index=X_shap.columns)
             .sort_values(ascending=True))
    fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * 0.055 * len(orden) + 1.5))
    cmap = mpl.colors.LinearSegmentedColormap.from_list("azul", RAMPA_SECUENCIAL)
    rng = np.random.default_rng(42)

    for y_i, variable in enumerate(orden.index):
        col = X_shap.columns.get_loc(variable)
        s = vals_shap[:, col]
        v = X_shap[variable].values
        # Rango percentil: robusto frente a valores atípicos.
        color_norm = pd.Series(v).rank(pct=True).values
        jitter = rng.uniform(-0.17, 0.17, size=len(s))
        ax.scatter(s, np.full(len(s), y_i) + jitter, c=color_norm, cmap=cmap,
                   s=1.6, alpha=0.55, linewidths=0, zorder=3)

    ax.axvline(0, color=BASELINE, linewidth=0.8, zorder=2)
    ax.set_yticks(range(len(orden)))
    ax.set_yticklabels([ETIQUETAS_VAR.get(v, v) for v in orden.index], fontsize=7.5)
    ax.set_xlabel("Contribución al log-odds de estar en zona inundable "
                  "(valor SHAP)", color=INK_2)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.grid(True, zorder=1)
    ax.set_axisbelow(True)
    limpiar_eje(ax, ejes=("bottom",))

    barra = fig.colorbar(mpl.cm.ScalarMappable(cmap=cmap), ax=ax,
                         fraction=0.022, pad=0.015, aspect=26)
    barra.set_ticks([0, 1])
    barra.set_ticklabels(["valor bajo", "valor alto"])
    barra.ax.tick_params(length=0, colors=MUTED, labelsize=6.8)
    barra.outline.set_visible(False)

    titulo(ax,
           "Qué gobierna la exposición a inundación, según el modelo",
           f"Contribuciones SHAP del XGBoost sobre una muestra de "
           f"{len(X_shap):,}".replace(",", ".") +
           " activos · cada punto es un activo")
    guardar(fig, "fig10_shap.png")
else:
    print(f"\n(sin '{RUTA_MET}': ejecuta antes modelado_inundabilidad.py)")

print("\nListo.")
print(f"Figuras en la carpeta '{OUT_DIR}'. Insertar en Word a 16 cm de ancho, sin reescalar.")
