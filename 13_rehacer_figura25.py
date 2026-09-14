# ============================================================================
# 13_rehacer_figura25.py
# ----------------------------------------------------------------------------
# Rehace la Figura 25 de la memoria (comprobacion del indice frente al episodio
# de octubre de 2024) con las cifras de la variante ADOPTADA.
#
# ----------------------------------------------------------------------------
# POR QUE HABIA QUE REHACERLA
# ----------------------------------------------------------------------------
# La version anterior mostraba 73 de 1.012 activos para Quart de Poblet y 3 de
# 149 para Catadau. Esas cifras corresponden a la variante ESCALADA del campo de
# extremos, que el propio trabajo descarta en el apartado 4.7 por producir 986
# activos con racha implicada superior a la maxima jamas registrada en el
# territorio. El fichero validacion_dana.json habia quedado con los valores de
# aquella variante porque la ejecucion que debia sobreescribirlo se interrumpio
# antes de guardar.
#
# Con la variante bruta, la adoptada, los valores son:
#   Quart de Poblet   71 -> 115 de 1.012   (7,0 % -> 11,4 %)   percentil 68,1 -> 78,3
#   Catadau            0 ->   0 de 149     (0,0 % -> 0,0 %)    percentil 45,8 -> 45,2
#
# La correccion refuerza el argumento en las dos ramas: el acierto sobre Quart de
# Poblet es mayor de lo que se decia, y el fallo sobre Catadau es total y no
# parcial, lo que hace la conclusion sobre el viento convectivo mas nitida.
# ============================================================================

import json
import os

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

CARPETA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(CARPETA, "figuras")
os.makedirs(OUT, exist_ok=True)

with open(os.path.join(CARPETA, "validacion_dana.json"), encoding="utf-8") as fh:
    dana = json.load(fh)
with open(os.path.join(CARPETA, "evento_dana_observado.json"), encoding="utf-8") as fh:
    obs = json.load(fh)

# --- Paleta verificada del trabajo -----------------------------------------
SURFACE = "#ffffff"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
AZUL, NARANJA = "#2a78d6", "#eb6834"
AZUL_SUAVE, NARANJA_SUAVE = "#eaf2fd", "#fdefe9"
GRIS_CAJA = "#f2f1ed"
ANCHO_IN = 16.0 / 2.54

mpl.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300,
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


# Convencion numerica del documento desde el pase de formato del 05/09: punto
# decimal y espacio duro (U+00A0) como separador de millares.
ESPACIO_DURO = " "


def n(x, d=1):
    return f"{x:.{d}f}"


def mil(x):
    return f"{int(x):,}".replace(",", ESPACIO_DURO)


CASOS = [
    {
        "nombre": "Quart de Poblet", "rama": "Rama de inundación",
        "color": AZUL, "fondo": AZUL_SUAVE, "veredicto": "ACIERTA",
        "datos": dana["entornos"]["Quart de Poblet"],
        "relato": ("La subestación quedó anegada. Su entorno\nalcanza el percentil "
                   "{pct} y aporta {top} de sus\n{tot} activos al 5 % de mayor riesgo."),
    },
    {
        "nombre": "Catadau", "rama": "Rama eólica",
        "color": NARANJA, "fondo": NARANJA_SUAVE, "veredicto": "FALLA",
        "datos": dana["entornos"]["Catadau"],
        "relato": ("El viento derribó más de veinte apoyos.\nSu entorno no mejora al "
                   "cambiar de\nvariable: no aporta ninguno de {tot}."),
    },
]

# La figura se hace mas alta y las tarjetas se separan de la nota inferior: con el
# reparto anterior el texto de cierre de cada tarjeta se salia del recuadro y se
# solapaba con la caja gris.
# Proporcion y resolucion de la figura que el documento lleva hoy: 1390 x 928 px
# a 220 ppp, razon alto/ancho 0,668. Se reproducen para no alterar la maqueta.
# El recorte ajustado fija la razon segun el contenido, no segun el lienzo, asi
# que el alto del lienzo se corrige por el factor medido en la salida anterior
# hasta aterrizar en la razon del documento (0,668). Dos iteraciones: 0,668 daba
# 0,652 y 0,684 daba 0,655; de ahi el factor acumulado.
RAZON_OBJETIVO = 0.668
RAZON, DPI_FIG = RAZON_OBJETIVO * (0.668 / 0.652) * (0.668 / 0.655), 220
fig = plt.figure(figsize=(ANCHO_IN, ANCHO_IN * RAZON))
fig.text(0.5, 0.975, "Comprobación del índice frente al episodio de octubre de 2024",
         ha="center", va="top", fontsize=11, fontweight="bold", color="#123a6b")

for k, caso in enumerate(CASOS):
    d = caso["datos"]
    desp = d["despues"]
    x0 = 0.035 + k * 0.485
    ancho = 0.445
    ax = fig.add_axes([x0, 0.275, ancho, 0.645])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch(
        (0.01, 0.01), 0.98, 0.98, boxstyle="round,pad=0.012,rounding_size=0.045",
        facecolor=SURFACE, edgecolor=caso["color"], linewidth=1.8,
        transform=ax.transAxes, clip_on=False))

    ax.text(0.5, 0.93, caso["nombre"], ha="center", va="top",
            fontsize=13, fontweight="bold", color=caso["color"])
    ax.text(0.5, 0.83, caso["rama"], ha="center", va="top",
            fontsize=8.5, color=INK_2)
    ax.text(0.5, 0.755, "Activos en el 5 % de mayor riesgo", ha="center",
            va="top", fontsize=8, color=INK_2)

    # Barra de proporcion. Se dibuja el carril completo y, encima, la fraccion
    # alcanzada; con cero activos no se dibuja relleno, que es la lectura correcta.
    frac = desp["n_en_top5pct"] / d["n_activos"]
    ax.add_patch(FancyBboxPatch(
        (0.09, 0.575), 0.82, 0.075,
        boxstyle="round,pad=0,rounding_size=0.02",
        facecolor="#eeeeee", edgecolor="none", transform=ax.transAxes))
    if frac > 0:
        ax.add_patch(FancyBboxPatch(
            (0.09, 0.575), max(0.82 * frac, 0.012), 0.075,
            boxstyle="round,pad=0,rounding_size=0.02",
            facecolor=caso["color"], edgecolor="none", transform=ax.transAxes))

    ax.text(0.5, 0.50, f"{desp['n_en_top5pct']} de {mil(d['n_activos'])}"
                       f"   ·   {n(desp['pct_en_top5pct'])} %",
            ha="center", va="top", fontsize=12, fontweight="bold",
            color=caso["color"])

    ax.add_patch(FancyBboxPatch(
        (0.28, 0.265), 0.44, 0.115,
        boxstyle="round,pad=0.008,rounding_size=0.03",
        facecolor=caso["fondo"], edgecolor=caso["color"], linewidth=1.1,
        transform=ax.transAxes))
    ax.text(0.5, 0.322, caso["veredicto"], ha="center", va="center",
            fontsize=11.5, fontweight="bold", color=caso["color"])

    ax.text(0.5, 0.225, caso["relato"].format(
        pct=n(desp["CRS_percentil_medio"], 0),
        top=desp["n_en_top5pct"], tot=mil(d["n_activos"])),
        ha="center", va="top", fontsize=8.0, color=INK_2, linespacing=1.5)

# --- Nota inferior ---------------------------------------------------------
est = obs["estaciones"][0]
ax = fig.add_axes([0.035, 0.02, 0.93, 0.205])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.add_patch(FancyBboxPatch(
    (0.005, 0.02), 0.99, 0.96, boxstyle="round,pad=0.01,rounding_size=0.05",
    facecolor=GRIS_CAJA, edgecolor="#dddcd6", linewidth=1.0,
    transform=ax.transAxes))
ax.text(0.5, 0.80, "La asimetría no es un defecto del índice sino una propiedad "
                   "del fenómeno",
        ha="center", va="top", fontsize=9.5, fontweight="bold", color="#123a6b")
ax.text(0.5, 0.58,
        f"La racha registrada en la estación más próxima a Catadau, a "
        f"{n(est['dist_catadau_km'])} km, fue de {n(est['racha_max_episodio_ms'])} m/s: "
        f"el {est['fraccion_del_V50'] * 100:.0f} % de su propio extremo de retorno.\n"
        "El evento que causó los daños no quedó capturado ni por el reanálisis ni "
        "por la red de observación. Un índice eólico\nconstruido sobre reanálisis "
        "sirve para el viento sinóptico, no para el convectivo.",
        ha="center", va="top", fontsize=8.2, color=INK_2, linespacing=1.7)

ruta = os.path.join(OUT, "docfig25_validacion_dana.png")
fig.savefig(ruta, bbox_inches="tight", pad_inches=0.06, dpi=DPI_FIG)
plt.close(fig)
from PIL import Image
with Image.open(ruta) as im:
    print(f"generada: figuras/{os.path.basename(ruta)}  "
          f"({im.size[0]}x{im.size[1]} px, {im.info.get('dpi', ('?',))[0]:.0f} dpi)")
print(f"\n  Quart de Poblet: {dana['entornos']['Quart de Poblet']['despues']['n_en_top5pct']}"
      f" de {dana['entornos']['Quart de Poblet']['n_activos']}"
      f" ({n(dana['entornos']['Quart de Poblet']['despues']['pct_en_top5pct'])} %)")
print(f"  Catadau: {dana['entornos']['Catadau']['despues']['n_en_top5pct']}"
      f" de {dana['entornos']['Catadau']['n_activos']}"
      f" ({n(dana['entornos']['Catadau']['despues']['pct_en_top5pct'])} %)")
