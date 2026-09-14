# ============================================================================
# 16_figuras_conceptuales.py
# ----------------------------------------------------------------------------
# Rehace las dos figuras conceptuales de la memoria que llevan cifras del indice
# y que, por tanto, caducan cada vez que el indice se recalcula:
#
#   docfig24  embudo de estrechamiento, del inventario completo a la lista corta
#   docfig27  correspondencia entre los ocho objetivos y su evidencia
#
# La Figura 26 (delimitacion del alcance) no lleva ninguna cifra dependiente del
# reparto de pesos y no se rehace aqui.
#
# Todas las cifras se leen de cifras_documento.json y de los JSON de resultados:
# ninguna esta escrita a mano en este fichero.
# ============================================================================

import json
import os
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Polygon

# Que figuras generar. Sin argumentos las hace las dos; con "embudo" solo esa.
# Existe para poder rehacer el embudo sin tocar la de objetivos, que en el
# documento va con otra numeracion y puede no necesitar cambios.
QUE = set(sys.argv[1:]) or {"embudo", "objetivos"}

CARPETA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(CARPETA, "figuras")
os.makedirs(OUT, exist_ok=True)

SURFACE = "#ffffff"
INK, INK_2 = "#0d366b", "#4a4a4a"
EMBUDO = ["#d6e5f8", "#86b6ee", "#2a78d6", "#0d366b", "#eb6834"]
BLANCO_DESDE = 2          # a partir de esta banda el texto va en blanco
FILA = "#f7fafe"
ANCHO_IN = 16.0 / 2.54

mpl.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300,
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 8,
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "text.color": INK,
})


# Convencion numerica del documento desde el pase de formato del 05/09: punto
# decimal y espacio duro (U+00A0) como separador de millares. El espacio duro
# evita que el numero se parta al final de una linea.
ESPACIO_DURO = " "


def mil(x):
    return f"{int(x):,}".replace(",", ESPACIO_DURO)


def dec(x, d=1):
    return f"{x:.{d}f}"


def guardar(fig, nombre, dpi=None):
    ruta = os.path.join(OUT, nombre)
    fig.savefig(ruta, bbox_inches="tight", pad_inches=0.10, dpi=dpi)
    plt.close(fig)
    from PIL import Image
    with Image.open(ruta) as im:
        print(f"  generada: figuras/{nombre}  ({im.size[0]}x{im.size[1]} px, "
              f"{im.info.get('dpi', ('?',))[0]:.0f} dpi)")


def cargar(nombre):
    with open(os.path.join(CARPETA, nombre), encoding="utf-8") as fh:
        return json.load(fh)


cif = cargar("cifras_documento.json")
clus = cargar("clustering_perfiles_v6.json")

n_total = cif["tabla7"]["resumen"]["total"]["Total"]
n_top5 = cif["distribucion"]["n_top5"]
n_sub_crit = cif["subest_criticas"]["total"]
n_sub_valencia = cif["subest_criticas"].get("Valencia", 0)

# Cifras de exposicion a inundacion del pie del embudo: se calculan desde el CSV
# en lugar de escribirse a mano, que es de donde vienen los desajustes.
act = pd.read_csv(os.path.join(CARPETA, "activos_con_crs_v6.csv"),
                  sep=";", encoding="utf-8-sig", low_memory=False)
_inund = act["dentro_zona_inundable"].astype(str).str.lower().eq("true")
_sub = act["tipo_activo"] == "subestacion"
N_INUND = int(_inund.sum())
PCT_INUND = 100 * float(_inund.mean())
PCT_INUND_SUB = 100 * float(_inund[_sub].mean())

# ===========================================================================
# DOCFIG 24 — el embudo
# ===========================================================================
print("docfig24: embudo de estrechamiento")
BANDAS = [
    (mil(n_total), "activos eléctricos integrados",
     "OpenStreetMap · toda la Comunitat Valenciana"),
    (mil(n_top5), "sobre el percentil 95 del índice",
     "umbral de priorización del Climate Risk Score"),
    (str(n_sub_crit), "subestaciones críticas",
     "el activo más vulnerable a la inundación"),
    (str(n_sub_valencia), "en la provincia de Valencia",
     "concentración provincial del riesgo"),
    ("4", "en el área afectada por la DANA",
     "las de mayor índice, identificadas una a una"),
]

# Proporcion y resolucion de la figura que el documento lleva hoy: 1590 x 1060 px
# a 220 ppp, es decir una razon alto/ancho de 0,667. Se reproducen para que la
# sustitucion no altere la maqueta.
# El alto del lienzo no es la razon final: bbox_inches="tight" recorta el blanco
# sobrante, de modo que la razon la fija el contenido. Con 0,667 de lienzo salia
# 0,508 de contenido, asi que se escala el lienzo por 0,667/0,508 para aterrizar
# en la proporcion del documento. Verificado en la salida que imprime guardar().
RAZON_24, DPI_24 = 0.667 * (0.667 / 0.508) * (0.667 / 0.658), 220
fig, ax = plt.subplots(figsize=(ANCHO_IN, ANCHO_IN * RAZON_24))
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")

# El estrechamiento se detiene en la ultima banda: si el trapecio se cierra mas,
# su pie de texto no cabe dentro y se desborda por los lados.
X_C, ALTO, HUECO = 38.0, 13.2, 1.3
ANCHOS = [34.0, 31.0, 28.0, 25.0, 22.5]
y = 86.0
for i, ((cifra, pie, nota), semi) in enumerate(zip(BANDAS, ANCHOS)):
    semi_inf = ANCHOS[i + 1] if i + 1 < len(ANCHOS) else 20.0
    ax.add_patch(Polygon(
        [(X_C - semi, y), (X_C + semi, y),
         (X_C + semi_inf, y - ALTO), (X_C - semi_inf, y - ALTO)],
        closed=True, facecolor=EMBUDO[i], edgecolor="none", zorder=2))
    color = "#ffffff" if i >= BLANCO_DESDE else INK
    ax.text(X_C, y - ALTO * 0.42, cifra, ha="center", va="center",
            fontsize=17, fontweight="bold", color=color, zorder=3)
    ax.text(X_C, y - ALTO * 0.78, pie, ha="center", va="center",
            fontsize=8.3, color=color, zorder=3)
    ax.text(76, y - ALTO * 0.52, nota, ha="left", va="center",
            fontsize=8.4, color=INK_2, zorder=3)
    y -= ALTO + HUECO

ax.text(0, 95.5, f"De casi {mil(39000)} activos imposibles de inspeccionar "
        "a cuatro emplazamientos concretos",
        ha="left", va="center", fontsize=10.5, fontweight="bold", color=INK)

pie_inund = (f"{mil(N_INUND)} activos ({dec(PCT_INUND)} %) se sitúan en zona "
             "inundable cartografiada; entre las subestaciones la proporción "
             f"sube al {dec(PCT_INUND_SUB)} %. La exposición\na inundación y el "
             "percentil 95 del índice no son conjuntos anidados: el índice "
             "agrega también viento, vulnerabilidad y criticidad de red.")
ax.text(0, 1.5, pie_inund, ha="left", va="bottom", fontsize=8.2,
        color=INK_2, style="italic", linespacing=1.5)
guardar(fig, "docfig24_embudo.png", dpi=DPI_24)

# ===========================================================================
# DOCFIG 27 — objetivos y evidencia
# ===========================================================================
print("docfig27: objetivos frente a evidencia")
k_terr = 8
k_perf = clus["subconjuntos"]["subestaciones"]["k_optimo"]

# Las fuentes publicas efectivamente integradas, contadas una a una para que la
# cifra de la figura no sea una afirmacion sin respaldo.
FUENTES = ["OpenStreetMap", "PATRICOVA", "Pryor y Barthelmie (ERA5)",
           "AEMET OpenData", "Copernicus DEM GLO-30",
           "Red de Cauces del ICV", "Global Wind Atlas"]

OBJETIVOS = [
    ("Analizar el estado del arte", "Cap. 2",
     "36 referencias en tres bloques temáticos"),
    ("Identificar fuentes de datos abiertas", "Ap. 4.2",
     f"{len(FUENTES)} fuentes públicas integradas"),
    ("Diseñar la integración multifuente", "Ap. 4.3",
     f"{mil(n_total)} activos en ETRS89 / UTM 30N"),
    ("Aplicar aprendizaje no supervisado", "Ap. 5.3",
     f"{k_terr} grupos territoriales · {k_perf} perfiles de riesgo"),
    ("Entrenar modelos con validación robusta", "Ap. 5.7",
     "ROC-AUC 0,841 con bloques de 10 × 10 km"),
    ("Incorporar explicabilidad mediante SHAP", "Ap. 5.7",
     "Altitud como variable dominante"),
    ("Validar mediante piloto experimental", "Ap. 5.8",
     "Contraste con la DANA de octubre de 2024"),
    ("Elaborar recomendaciones de priorización", "Ap. 5.5",
     f"{mil(n_top5)} activos · {n_sub_crit} subestaciones críticas"),
]

ALTO_F = 10.4
X_OBJ, HUECO_COL = 9.5, 3.0
ANCHO_27, DPI_27 = 24.0 / 2.54, 200


def ancho_en_datos(texto, ax, renderer):
    """Ancho real del texto ya dibujado, en unidades del eje."""
    bb = texto.get_window_extent(renderer=renderer)
    inv = ax.transData.inverted()
    (x0, _), (x1, _) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
    return x1 - x0


def dibujar_objetivos(cuerpo):
    """Compone la figura con ese tamano de letra y devuelve (fig, desbordamiento).

    Las columnas no se colocan por estimacion, que ya fallo dos veces, sino
    midiendo el texto mas ancho de cada una con el renderer.
    """
    # Lienzo ancho en pulgadas y no en pixeles: lo que decide si el texto cabe es
    # la razon entre el cuerpo de letra, en puntos, y el ancho de la figura, en
    # pulgadas. Se compensa bajando los puntos por pulgada al guardar, de modo
    # que el fichero final conserva la misma anchura en pixeles que el resto.
    fig, ax = plt.subplots(figsize=(ANCHO_27, ANCHO_27 * 0.47))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.canvas.draw()
    ren = fig.canvas.get_renderer()

    cols = [[], [], []]
    y = 92.5 - ALTO_F
    for i, (obj, ap, ev) in enumerate(OBJETIVOS, 1):
        if i % 2 == 1:
            ax.add_patch(FancyBboxPatch(
                (0, y), 100, ALTO_F, boxstyle="round,pad=0,rounding_size=1.2",
                facecolor=FILA, edgecolor="none", zorder=1))
        cy = y + ALTO_F / 2
        # Marcador y no Circle: el eje no es cuadrado y un Circle en coordenadas
        # de datos saldria eliptico.
        ax.scatter([4.0], [cy], s=520, marker="o", color="#2a78d6",
                   edgecolors="none", zorder=2)
        ax.text(4.0, cy, str(i), ha="center", va="center", fontsize=cuerpo + 0.2,
                fontweight="bold", color="#ffffff", zorder=3)
        for k, (txt, color) in enumerate(((obj, "#2a78d6"), (ap, INK_2),
                                          (ev, INK_2))):
            cols[k].append(ax.text(X_OBJ, cy, txt, ha="left", va="center",
                                   fontsize=cuerpo, color=color, zorder=3))
        y -= ALTO_F
    y_final = y + ALTO_F

    cab = [ax.text(2.5, 96.5, "OBJETIVO ESPECÍFICO", fontsize=cuerpo + 0.2,
                   fontweight="bold", color=INK, va="center"),
           ax.text(X_OBJ, 96.5, "APARTADO", fontsize=cuerpo + 0.2,
                   fontweight="bold", color=INK, va="center"),
           ax.text(X_OBJ, 96.5, "EVIDENCIA", fontsize=cuerpo + 0.2,
                   fontweight="bold", color=INK, va="center")]

    x = X_OBJ
    for k in (0, 1, 2):
        if k > 0:
            for t in cols[k]:
                t.set_x(x)
            cab[k].set_x(x)
        ancho = max(max(ancho_en_datos(t, ax, ren) for t in cols[k]),
                    ancho_en_datos(cab[k], ax, ren) if k else 0.0)
        x += ancho + HUECO_COL
    desborde = x - HUECO_COL - 100.0

    ax.plot([0, 100], [92.5, 92.5], color=INK, linewidth=1.2)
    ax.plot([0, 100], [y_final, y_final], color=INK, linewidth=1.2)
    return fig, desborde


if "objetivos" in QUE:
    for cuerpo in (9.0, 8.6, 8.2, 7.8, 7.4, 7.0, 6.6):
        fig, desborde = dibujar_objetivos(cuerpo)
        if desborde <= 0:
            print(f"  tamano de letra {cuerpo} pt: las tres columnas caben "
                  f"(margen {-desborde:.1f} unidades)")
            break
        print(f"  tamano de letra {cuerpo} pt: desborda {desborde:.1f} unidades")
        plt.close(fig)
    guardar(fig, "docfig27_objetivos.png", dpi=DPI_27)

    print("\nfuentes contadas para el objetivo 2:")
    for f in FUENTES:
        print(f"  · {f}")
else:
    print("docfig27: no se regenera (no estaba en los argumentos)")
