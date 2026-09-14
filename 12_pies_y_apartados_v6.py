# ============================================================================
# 12_pies_y_apartados_v6.py
# ----------------------------------------------------------------------------
# Cierra el documento V6 con lo que quedaba:
#
#   A. Reescribe los tres pies de figura que describian una figura distinta de la
#      que ahora hay (9, 10 y 11).
#   B. Anade el apartado de validacion contra el evento real de la DANA.
#   C. Anade el parrafo que explica los dos papeles del viento en la memoria.
#
# Las cifras se leen de los ficheros de resultados.
# ============================================================================

import json
import os
import shutil

import pandas as pd
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

CARPETA = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v6.docx")
RESPALDO = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v6_antes_pies.docx")


def cargar(nombre):
    with open(os.path.join(CARPETA, nombre), encoding="utf-8") as fh:
        return json.load(fh)


dana = cargar("validacion_dana.json")
obs = cargar("evento_dana_observado.json")
calib = cargar("calibracion_v50.json")
extremos = cargar("extremos_observados.json")
act = pd.read_csv(os.path.join(CARPETA, "activos_con_crs_v6.csv"),
                  sep=";", encoding="utf-8-sig", low_memory=False)
sub = act[act["tipo_activo"] == "subestacion"]


def n(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def mil(x, d=0):
    entero, _, dec = f"{x:,.{d}f}".partition(".")
    return (entero.replace(",", ".") + ("," + dec if dec else ""))


med3 = float(sub.loc[sub["perfil_amenaza_subest"] == 3, "densidad_5km"].median())
med4 = float(sub.loc[sub["perfil_amenaza_subest"] == 4, "densidad_5km"].median())

print(f"respaldo: {os.path.basename(RESPALDO)}")
shutil.copy2(DOC, RESPALDO)
doc = docx.Document(DOC)
errores, hechas = [], 0


def sust(indice, viejo, nuevo, etiqueta):
    """Sustituye texto aunque este repartido entre runs; aborta si hay un campo."""
    global hechas
    p = doc.paragraphs[indice]
    hijos = []
    for hijo in p._p:
        etq = hijo.tag.split("}")[-1]
        if etq == "r":
            hijos.append(("r", hijo,
                          "".join(t.text or "" for t in hijo.findall(qn("w:t")))))
        elif etq == "fldSimple":
            hijos.append(("f", hijo,
                          "".join(t.text or "" for t in hijo.iter(qn("w:t")))))
    texto = "".join(h[2] for h in hijos)
    pos = texto.find(viejo)
    if pos < 0:
        errores.append(f"[{etiqueta}] p{indice}: no encontrado")
        print(f"  FALLO [{etiqueta}]")
        return
    fin = pos + len(viejo)
    ini_idx = fin_idx = None
    acc = 0
    for k, (_, _, t) in enumerate(hijos):
        a, b = acc, acc + len(t)
        if ini_idx is None and b > pos:
            ini_idx = k
        if a < fin:
            fin_idx = k
        acc = b
    if any(hijos[k][0] == "f" for k in range(ini_idx, fin_idx + 1)):
        errores.append(f"[{etiqueta}] p{indice}: atraviesa un campo")
        print(f"  ABORTA [{etiqueta}]")
        return
    desplaz = sum(len(hijos[k][2]) for k in range(ini_idx))
    local = "".join(hijos[k][2] for k in range(ini_idx, fin_idx + 1))
    nuevo_local = local[:pos - desplaz] + nuevo + local[fin - desplaz:]
    primer = hijos[ini_idx][1]
    ts = primer.findall(qn("w:t"))
    if not ts:
        nt = OxmlElement("w:t")
        primer.append(nt)
        ts = [nt]
    ts[0].text = nuevo_local
    ts[0].set(qn("xml:space"), "preserve")
    for e in ts[1:]:
        e.text = ""
    for k in range(ini_idx + 1, fin_idx + 1):
        for t in hijos[k][1].findall(qn("w:t")):
            t.text = ""
    hechas += 1
    print(f"  OK    [{etiqueta}]")


# ===========================================================================
print("=== A. PIES DE FIGURA REESCRITOS ===")
# ===========================================================================
sust(229,
     "Figura 9. Distribución de la velocidad media de viento a 50 metros para los "
     "dos tipos de activo. Se representa el porcentaje dentro de cada grupo y no "
     "el recuento absoluto, dado que el número de apoyos supera en dos órdenes de "
     "magnitud el de subestaciones. Elaboración propia a partir del Global Wind "
     "Atlas.",
     "Figura 9. Comparación de las dos variables de viento consideradas en este "
     "trabajo, sobre un mismo eje: la velocidad media anual del Global Wind Atlas, "
     "empleada en una versión anterior del índice, y la velocidad de retorno a 50 "
     "años que la sustituye. Ambas distribuciones se normalizan al 100 % de su "
     "propio recuento para que sean comparables en forma. Las líneas verticales "
     "marcan las velocidades básicas de diseño del CTE DB-SE-AE con las que se "
     "dimensionan los apoyos en España, de 26 y 29 metros por segundo. La "
     "velocidad media se concentra un orden de magnitud por debajo de cualquiera "
     "de esos umbrales, lo que justifica el cambio de variable. Elaboración propia "
     "a partir del Global Wind Atlas y de Pryor y Barthelmie.",
     "pie Figura 9")

sust(239,
     "Figura 10. Perfiles de riesgo de las subestaciones en el plano de las dos "
     "peligrosidades. El eje de inundación es logarítmico y los valores inferiores "
     "a 10⁻⁵ se representan acumulados en el extremo izquierdo. Elaboración propia.",
     "Figura 10. Perfiles de riesgo de las subestaciones en el plano de las dos "
     "peligrosidades, representados en paneles independientes: cada uno destaca un "
     "perfil y muestra en gris las 608 subestaciones como contexto. Se recurre a "
     "paneles y no a un único diagrama con siete colores porque la paleta empleada "
     "en este trabajo admite tres series simultáneas en formatos de dispersión sin "
     "comprometer la distinguibilidad para lectores con deficiencias en la visión "
     "del color. El eje de inundación es logarítmico porque esa peligrosidad "
     "recorre tres órdenes de magnitud mientras que la eólica no llega a recorrer "
     "uno. Elaboración propia.",
     "pie Figura 10")

sust(241,
     "Figura 11. Los mismos perfiles frente a la criticidad de red. Los perfiles 3 "
     "y 4, indistinguibles en el plano de las amenazas, se separan con nitidez al "
     "introducir la densidad local de apoyos. Elaboración propia.",
     "Figura 11. Los mismos perfiles frente a la criticidad de red. Cada punto es "
     "una subestación y la línea vertical marca la mediana del perfil. Los "
     "perfiles 3 y 4, que comparten posición en el plano de las amenazas, se "
     f"separan con nitidez al introducir la densidad local de apoyos: {mil(med3)} "
     f"frente a {mil(med4)} activos en un radio de 5 kilómetros. Elaboración "
     "propia.",
     "pie Figura 11")

# ===========================================================================
print("\n=== B. APARTADO DE VALIDACION CONTRA EL EVENTO REAL ===")
# ===========================================================================
# Se inserta al final del capitulo 5, antes del encabezado del capitulo 6.
ancla = None
for p in doc.paragraphs:
    if p.style.name == "Heading 1" and p.text.strip() == "Discusión":
        ancla = p
        break
if ancla is None:
    raise SystemExit("no se localizo el encabezado del capitulo 6")

ins = 0


def meter(texto, estilo="Normal"):
    global ins
    ancla.insert_paragraph_before(texto, style=estilo)
    ins += 1


cat_a, cat_d = dana["entornos"]["Catadau"]["antes"], dana["entornos"]["Catadau"]["despues"]
qua_a = dana["entornos"]["Quart de Poblet"]["antes"]
qua_d = dana["entornos"]["Quart de Poblet"]["despues"]
n_cat = dana["entornos"]["Catadau"]["n_activos"]
n_qua = dana["entornos"]["Quart de Poblet"]["n_activos"]

meter("Validación del índice contra el episodio de octubre de 2024", "Heading 2")

meter(
    "El episodio que motiva este trabajo ofrece una prueba directa del índice, "
    "porque dañó activos por las dos amenazas en dos emplazamientos distintos: la "
    "subestación de Quart de Poblet quedó anegada por la inundación y en el "
    "entorno de Catadau el viento derribó más de veinte apoyos de la red de alta "
    "tensión. Un índice que funcione debería situar ambos entornos en su cola "
    f"superior. Se evalúan por ello los activos situados en un radio de "
    f"{dana['radio_m'] // 1000} kilómetros de cada punto, comparando el resultado "
    "que daba la versión basada en la velocidad media con el que da la versión "
    "basada en la velocidad de retorno a 50 años.")

meter(
    f"La rama de inundación acierta en su caso y mejora con el cambio. De los "
    f"{mil(n_qua)} activos del entorno de Quart de Poblet, los que se sitúan en el "
    f"5 % de mayor riesgo pasan de {qua_a['n_en_top5pct']} a "
    f"{qua_d['n_en_top5pct']}, y el percentil medio del entorno sube de "
    f"{n(qua_a['CRS_percentil_medio'], 1)} a {n(qua_d['CRS_percentil_medio'], 1)}. "
    "La rama de viento, en cambio, sigue fallando en el suyo. En el entorno de "
    f"Catadau la variable de peligrosidad eólica sube de "
    f"{n(cat_a['valor_ms'])} a {n(cat_d['valor_ms'])} metros por segundo y el "
    f"percentil que ocupa el entorno pasa del {n(cat_a['percentil_en_el_conjunto'], 1)} "
    f"al {n(cat_d['percentil_en_el_conjunto'], 1)}, pero el número de activos que "
    f"alcanzan el 5 % de mayor riesgo se mantiene en "
    f"{cat_d['n_en_top5pct']} de {n_cat}. El cambio de variable, por tanto, no "
    "consigue que el índice señale el emplazamiento donde el viento causó daños "
    "reales.")

meter(
    "Conviene detenerse en por qué no lo consigue, porque la explicación no es una "
    "insuficiencia del índice sino una propiedad del fenómeno, y puede "
    "comprobarse con observaciones. Durante los días del episodio, la estación de "
    "AEMET más próxima a Catadau, situada a "
    f"{n(obs['estaciones'][0]['dist_catadau_km'], 1)} kilómetros, registró una "
    f"racha máxima de {n(obs['estaciones'][0]['racha_max_episodio_ms'], 1)} metros "
    f"por segundo, equivalente a "
    f"{obs['estaciones'][0]['racha_max_episodio_kmh']:.0f} kilómetros por hora. "
    f"Esa racha representa el "
    f"{100 * obs['estaciones'][0]['fraccion_del_V50']:.0f} % de la velocidad de "
    "retorno a 50 años de esa misma estación, es decir, un episodio de viento sin "
    "nada de excepcional en su propio registro. Ninguna de las estaciones "
    "analizadas superó el "
    f"{100 * obs['max_fraccion_del_V50_en_cercanas']:.0f} % de su propio extremo, "
    "y la racha máxima de todo el periodo 1985-2024 en la Comunitat Valenciana, de "
    f"{n(obs['racha_maxima_del_periodo_completo_ms'], 1)} metros por segundo, no se "
    f"produjo durante esta DANA sino en {obs['racha_maxima_del_periodo_fecha'][:4]}.")

meter(
    "La conclusión que se extrae es de alcance más general que el caso concreto. "
    "El fenómeno que derribó los apoyos de Catadau fue de carácter convectivo y "
    "tornádico, con una extensión espacial muy inferior a la resolución de "
    "cualquier producto de reanálisis: no lo capturó el atlas empleado aquí, no lo "
    "habría capturado CERRA a 5,5 kilómetros, y no lo capturaron tampoco las "
    "observaciones directas a decenas de kilómetros. La no detección no es, por "
    "tanto, atribuible a la resolución del producto elegido. Lo que este resultado "
    "delimita es el alcance legítimo de un índice de riesgo eólico construido "
    "sobre reanálisis: sirve para el viento sinóptico, que es el que gobierna las "
    "cargas de diseño y el que los reanálisis representan, y no sirve para el "
    "viento convectivo, cuya caracterización estadística sigue siendo un problema "
    "abierto en la normativa internacional de cargas de viento. Distinguir ambos "
    "regímenes es una condición necesaria para interpretar correctamente cualquier "
    "evaluación de riesgo eólico sobre infraestructura lineal.")

print(f"  {ins} párrafos insertados en el capítulo 5")

# ===========================================================================
print("\n=== C. LOS DOS PAPELES DEL VIENTO ===")
# ===========================================================================
# Se inserta en el apartado del diseno del modelado supervisado, que es donde el
# lector se encuentra por primera vez la velocidad media reaparecida como
# predictor despues de haberla sustituido como amenaza.
ancla2 = None
for p in doc.paragraphs:
    if (p.style.name == "Heading 2"
            and p.text.strip().startswith("Resultados del modelado supervisado")):
        ancla2 = p
        break
if ancla2 is None:
    print("  AVISO: no se localizo el apartado de resultados del modelado")
else:
    ancla2.insert_paragraph_before(
        "Debe advertirse una circunstancia que puede inducir a confusión al leer "
        "este apartado junto con el capítulo anterior. La velocidad media anual "
        "del Global Wind Atlas fue descartada en el apartado 4.7 como variable de "
        "peligrosidad, por no medir daño estructural, y reaparece aquí como uno de "
        "los nueve predictores del modelo supervisado. No es una inconsistencia: "
        "son dos funciones distintas de la misma magnitud. Como peligrosidad "
        "pretendía cuantificar la carga que el viento ejerce sobre una estructura, "
        "cometido para el que una media anual no sirve. Como predictor de "
        "inundabilidad no se le atribuye ningún papel causal: opera como sustituto "
        "del relieve, según se detalla en el análisis de explicabilidad, porque la "
        "velocidad media a 50 metros correlaciona con la exposición topográfica y "
        "permite al modelo distinguir fondos de valle de emplazamientos elevados. "
        "El modelo supervisado y su análisis SHAP se conservan por ello sin "
        "modificación respecto a la versión anterior del trabajo, dado que el "
        "cambio de variable de peligrosidad no afecta a esa función.",
        style="Normal")
    print("  OK    párrafo de los dos papeles del viento")

print("\n" + "=" * 70)
if errores:
    print(f"{len(errores)} problemas, NO se guarda:")
    for e in errores:
        print(f"  - {e}")
    raise SystemExit(1)

doc.save(DOC)
print(f"{hechas} pies reescritos, {ins + 1} párrafos nuevos.")
print(f"Guardado: {os.path.basename(DOC)}")
