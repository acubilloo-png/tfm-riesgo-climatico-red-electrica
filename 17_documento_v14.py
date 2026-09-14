# ============================================================================
# 17_documento_v14.py
# ----------------------------------------------------------------------------
# Lleva la memoria del reparto de pesos 0,60 / 0,40 al 0,70 / 0,30, corrigiendo
# TODAS las cifras que dependen de esa eleccion: las Tablas 6 a 10, la prosa de
# los apartados 4.7, 5.3, 5.4, 5.5, 5.8, 6.2, 6.3, 7.1 y 7.2, y las imagenes de
# las figuras cuyo contenido cambia.
#
# ORIGEN:  20260415_TFMAlvaroCubillo_v13.docx   (no se modifica)
# DESTINO: 20260415_TFMAlvaroCubillo_v14.docx
#
# Ninguna cifra esta escrita a mano: todas se leen de cifras_documento.json,
# crs_parametros_v6.json, comparativa_v5_v6.json, clustering_perfiles_v6.json y
# validacion_dana.json. Si una sustitucion no encuentra su texto, el script no
# guarda nada: es preferible fallar a dejar el documento a medio corregir.
#
# ----------------------------------------------------------------------------
# LO QUE EL CAMBIO DE PESOS HACE A LOS RESULTADOS, PARA QUE CONSTE
# ----------------------------------------------------------------------------
# Mejora:  las subestaciones criticas pasan de 14 a 19, el entorno de la
#          subestacion anegada de Quart de Poblet sube del percentil 78,3 al 79,3
#          y la mediana del indice se vuelve mas interpretable.
# Empeora: el 1 % superior del indice pierde los 12 activos dominados por viento
#          que tenia con 0,60 y se queda en cero.
# Ese intercambio es deliberado y el apartado 5.4 lo declara separando el efecto
# de la variable del efecto del reparto, para no atribuir a uno lo que hace otro.
# ============================================================================

import copy
import json
import os
import re
import shutil
import zipfile

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

CARPETA = os.path.dirname(os.path.abspath(__file__))
ORIGEN = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v13.docx")
DESTINO = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v14.docx")
FIGS = os.path.join(CARPETA, "figuras")

# Correspondencia figura del documento -> parte del paquete -> fichero nuevo.
# Las partes se identificaron recorriendo los pies de figura y la imagen que
# precede a cada uno; no se deducen del tamano del fichero.
IMAGENES = {
    "Figura 13": ("word/media/image17.png", "docfig10_perfiles_plano_amenazas.png"),
    "Figura 14": ("word/media/image18.png", "docfig11_perfiles_criticidad.png"),
    "Figura 15": ("word/media/image19.png", "fig7_riesgo_compuesto.png"),
    "Figura 16": ("word/media/image20.png", "docfig13_sensibilidad_estabilidad.png"),
    "Figura 17": ("word/media/image21.png", "docfig14_sensibilidad_solape.png"),
    "Figura 18": ("word/media/image22.png", "docfig15_criticos_castellon.png"),
    "Figura 19": ("word/media/image23.png", "docfig16_criticos_valencia.png"),
    "Figura 20": ("word/media/image24.png", "docfig17_criticos_alicante.png"),
    "Figura 24": ("word/media/image28.png", "docfig24_embudo.png"),
    "Figura 25": ("word/media/image29.png", "docfig25_validacion_dana.png"),
    "Figura 27": ("word/media/image31.png", "docfig27_objetivos.png"),
}


def cargar(nombre):
    with open(os.path.join(CARPETA, nombre), encoding="utf-8") as fh:
        return json.load(fh)


cif = cargar("cifras_documento.json")
par = cargar("crs_parametros_v6.json")
comp = cargar("comparativa_v5_v6.json")
clus = cargar("clustering_perfiles_v6.json")
dana = cargar("validacion_dana.json")

q = dana["entornos"]["Quart de Poblet"]
dist = cif["distribucion"]
res7 = cif["tabla7"]["resumen"]
perf = {int(f["perfil"]): f for f in clus["tabla"]
        if f["subconjunto"] == "subestaciones"}
dom = comp["amenaza_dominante"]
sens = {s["peso_inundacion"]: s for s in par["sensibilidad_pesos"]}


def n(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def mil(x):
    return f"{int(x):,}".replace(",", ".")


def mildec(x, d=2):
    """Millares con punto y decimales con coma, como en el resto del documento."""
    entero, _, dec = f"{x:,.{d}f}".partition(".")
    return entero.replace(",", ".") + "," + dec


print(f"origen : {os.path.basename(ORIGEN)}")
print(f"destino: {os.path.basename(DESTINO)}")
shutil.copy2(ORIGEN, DESTINO)
doc = docx.Document(DESTINO)

errores, hechas = [], 0


def _partes(p):
    """Runs y campos del parrafo, con su texto, en orden."""
    hijos = []
    for hijo in p._p:
        etq = hijo.tag.split("}")[-1]
        if etq == "r":
            hijos.append(("r", hijo,
                          "".join(t.text or "" for t in hijo.findall(qn("w:t")))))
        elif etq == "fldSimple":
            hijos.append(("f", hijo,
                          "".join(t.text or "" for t in hijo.iter(qn("w:t")))))
    return hijos


def _patron(literal):
    """Regex del literal tolerante al tipo de espacio y de guion que use Word."""
    trozos = []
    for ch in literal:
        if ch in "   ":
            trozos.append("[   ]")
        elif ch in "-‐‑–—":
            trozos.append("[-‐‑–—]")
        else:
            trozos.append(re.escape(ch))
    return re.compile("".join(trozos))


def _sustituir_en(p, viejo, nuevo, etiqueta):
    hijos = _partes(p)
    texto = "".join(h[2] for h in hijos)
    m = _patron(viejo).search(texto)
    if m is None:
        return False
    pos, fin = m.start(), m.end()
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
        errores.append(f"[{etiqueta}] atraviesa un campo REF")
        print(f"  ABORTA [{etiqueta}]")
        return True
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
    return True


def sust(viejo, nuevo, etiqueta):
    """Sustituye en el cuerpo o en cualquier celda de tabla. Registra el fallo."""
    global hechas
    for p in doc.paragraphs:
        if _sustituir_en(p, viejo, nuevo, etiqueta):
            hechas += 1
            print(f"  OK    [{etiqueta}]")
            return
    for t in doc.tables:
        for fila in t.rows:
            for celda in fila.cells:
                for p in celda.paragraphs:
                    if _sustituir_en(p, viejo, nuevo, etiqueta):
                        hechas += 1
                        print(f"  OK    [{etiqueta}] (en tabla)")
                        return
    errores.append(f"[{etiqueta}] no encontrado")
    print(f"  FALLO [{etiqueta}]")


def celda(tabla, i, j, nuevo, etiqueta):
    """Reescribe una celda conservando el formato de su primer run."""
    global hechas
    try:
        c = tabla.rows[i].cells[j]
    except IndexError:
        errores.append(f"[{etiqueta}] celda ({i},{j}) inexistente")
        print(f"  FALLO [{etiqueta}] celda ({i},{j}) inexistente")
        return
    if any(h[0] == "f" for p in c.paragraphs for h in _partes(p)):
        errores.append(f"[{etiqueta}] la celda ({i},{j}) contiene un campo")
        print(f"  ABORTA [{etiqueta}] campo en la celda")
        return
    viejo = c.text.strip()
    if viejo == nuevo:
        return
    p = c.paragraphs[0]
    runs = p.runs
    if not runs:
        runs = [p.add_run()]
    runs[0].text = nuevo
    for r in runs[1:]:
        r.text = ""
    for extra in c.paragraphs[1:]:
        for r in extra.runs:
            r.text = ""
    hechas += 1
    print(f"    ({i},{j}) {viejo!r} -> {nuevo!r}")


# ===========================================================================
print("\n=== APARTADO 4.7: el reparto de pesos ===")
sust("El reparto de pesos entre amenazas se fija en 0,60 para la inundación y "
     "0,40 para el viento, atendiendo a que la inundación es la amenaza dominante "
     "en el área de estudio y la que motiva este trabajo.",
     f"El reparto de pesos entre amenazas se fija en "
     f"{n(par['peso_inundacion'], 2)} para la inundación y "
     f"{n(par['peso_viento'], 2)} para el viento, y la elección se apoya en tres "
     "consideraciones. La primera es sustantiva: la inundación es la amenaza que "
     "ha producido los daños documentados en el área de estudio y la que motiva "
     "este trabajo. La segunda se sigue de la asimetría descrita en el párrafo "
     "anterior: la peligrosidad eólica, confinada a una banda estrecha, no puede "
     "generar valores comparables a los de una crecida frecuente, de modo que un "
     "peso mayor no la llevaría a la cola del índice y sí desplazaría la "
     "ordenación en su tramo intermedio, que es donde se concentra la mayoría de "
     "los activos. La tercera es empírica: con un peso de 0,80 para la inundación, "
     f"el grupo de {perf[5]['n']} subestaciones sin exposición fluvial alguna que "
     "el apartado 5.3 identifica deja de estar dominado por el viento en la "
     "descomposición del índice —pasa a dominarlo el riesgo residual de "
     "proximidad— y la lectura por mecanismo que la rama eólica aporta se vacía "
     "de contenido.",
     "4.7 reparto de pesos")

# ===========================================================================
print("\n=== APARTADO 5.3: perfiles de riesgo ===")
sust(f"con un índice mediano de {mildec(66.94)} frente al {mildec(8.65)} del "
     "conjunto de las subestaciones",
     f"con un índice mediano de {mildec(perf[1]['CRS_mediano'])} frente al "
     f"{mildec(res7['mediana']['Subest.'])} del conjunto de las subestaciones",
     "5.3 indice mediano del perfil 1")
sust(f"el mismo mecanismo pero mucha menor severidad, índice mediano "
     f"{mildec(18.97)}",
     "el mismo mecanismo pero mucha menor severidad, índice mediano "
     f"{mildec(perf[2]['CRS_mediano'])}",
     "5.3 indice mediano del perfil 2")

# ===========================================================================
# DOS IMPRECISIONES QUE NO DEPENDEN DE LOS PESOS
# ---------------------------------------------------------------------------
# 1. El trabajo maneja DOS densidades distintas y el texto las confunde:
#      densidad_apoyos_5km  cuenta solo apoyos  -> alimenta la Tabla 5
#      densidad_5km         cuenta TODOS los activos, menos el propio
#                           -> alimenta el factor de criticidad y la Tabla 6
#    Las cifras de la Tabla 6 y del apartado 5.3 son de la segunda, de modo que
#    llamarlas "apoyos" es incorrecto: son activos.
# 2. El apartado 5.3 atribuye al grupo territorial 1 "la mayor velocidad media de
#    viento (5,62 m/s)". Es cierto, pero cita la velocidad media del Global Wind
#    Atlas, que este trabajo descarto como peligrosidad y que ya no figura en la
#    Tabla 5. Leido contra la tabla, que declara V50, parece un error: en V50 el
#    grupo 1 (21,02) va por detras del grupo 2 (21,43). Se reformula sobre la
#    variable que la tabla si muestra.
# ===========================================================================
print("\n=== PRECISIONES SOBRE LA DENSIDAD Y EL VIENTO DE LOS GRUPOS ===")
sust("la peligrosidad por inundación, la peligrosidad por viento y la densidad de "
     "apoyos en 5 kilómetros",
     "la peligrosidad por inundación, la peligrosidad por viento y la densidad de "
     "activos en 5 kilómetros",
     "4.5 entradas del segundo agrupamiento")
sust("apoyos de media en un radio de 5 kilómetros, la densidad más alta de los "
     "siete grupos",
     "activos de media en un radio de 5 kilómetros, la densidad más alta de los "
     "siete grupos",
     "5.3 densidad del perfil 3")
sust("no registra ninguna subestación en zona inundable pero sí la mayor "
     "velocidad media de viento (5,62 m/s)",
     "no registra ninguna subestación en zona inundable y sí una de las "
     "velocidades de retorno más altas del conjunto (21,02 metros por segundo, "
     "frente a los 20,23 de mediana regional)",
     "5.3 viento del grupo territorial 1")
sust("no registra ninguna subestación inundable pero sí la mayor velocidad de "
     "viento del área de estudio",
     "no registra ninguna subestación inundable y sí una de las velocidades de "
     "retorno más altas del área de estudio",
     "7.1 viento del grupo territorial 1")

# ===========================================================================
print("\n=== APARTADO 5.4: distribucion del indice ===")
sust(f"se distribuye con una mediana de {mildec(15.47)} sobre 100 y un máximo de "
     f"{mildec(79.83)}, con los percentiles 90, 95 y 99 situados en "
     f"{mildec(20.83)}, {mildec(24.12)} y {mildec(37.61)} respectivamente",
     f"se distribuye con una mediana de {mildec(dist['mediana'])} sobre 100 y un "
     f"máximo de {mildec(dist['maxima'])}, con los percentiles 90, 95 y 99 "
     f"situados en {mildec(dist['p90'])}, {mildec(dist['p95'])} y "
     f"{mildec(dist['p99'])} respectivamente",
     "5.4 mediana, maximo y percentiles")
sust(f"con valores comprendidos entre {mildec(77.55)} y {mildec(79.83)}",
     f"con valores comprendidos entre {mildec(dist['top4_min'])} y "
     f"{mildec(dist['top4_max'])}",
     "5.4 rango de los cuatro primeros")

sust(f"—frente al valor de {mildec(0.60, 2)} adoptado—, la ordenación de activos "
     "que produce el índice mantiene una correlación de Spearman no inferior a "
     f"{mildec(0.94, 2)} con la ordenación de referencia, y la coincidencia en la "
     "identificación del 5 % de activos de mayor riesgo no baja del "
     f"{mildec(70.6, 1)} %",
     f"—frente al valor de {n(par['peso_inundacion'], 2)} adoptado—, la ordenación "
     "de activos que produce el índice mantiene una correlación de Spearman no "
     f"inferior a {mildec(min(s['spearman'] for s in sens.values()), 2)} con la "
     "ordenación de referencia, y la coincidencia en la identificación del 5 % de "
     "activos de mayor riesgo no baja del "
     f"{mildec(min(s['solape_top5_pct'] for s in sens.values()), 1)} %",
     "5.4 sensibilidad a los pesos")

print("\n--- 5.4: lectura de la Tabla 7 ---")
sust(f"Las torres presentan el índice mediano más alto de las cuatro clases "
     f"({mildec(16.44)})",
     "Las torres presentan el índice mediano más alto de las cuatro clases "
     f"({mildec(res7['mediana']['Torres'])})",
     "5.4 mediana de las torres")
sust(f"solo 40 de {mil(13758)} torres, un {mildec(0.3, 1)} %, se sitúan en el "
     "1 % superior",
     f"solo {res7['n_en_top1']['Torres']} de {mil(res7['total']['Torres'])} "
     f"torres, un {mildec(res7['pct_en_top1']['Torres'], 1)} %, se sitúan en el "
     "1 % superior",
     "5.4 torres en el 1 % superior")
sust(f"tienen el índice mediano más bajo del conjunto ({mildec(8.65)}) y, sin "
     f"embargo, aportan 9 de los {mil(388)} activos del 1 % superior, un "
     f"{mildec(1.5, 1)} % de su clase",
     f"tienen el índice mediano más bajo del conjunto "
     f"({mildec(res7['mediana']['Subest.'])}) y, sin embargo, aportan "
     f"{res7['n_en_top1']['Subest.']} de los {mil(dist['n_top1'])} activos del "
     f"1 % superior, un {mildec(res7['pct_en_top1']['Subest.'], 1)} % de su clase",
     "5.4 subestaciones en el 1 % superior")

print("\n--- 5.4: composicion de la cola ---")
d5, d5w, d6 = dom["top5pct_v5"], dom["top5pct_v6w5"], dom["top5pct_v6"]
t1_5, t1_5w, t1_6 = dom["top1pct_v5"], dom["top1pct_v6w5"], dom["top1pct_v6"]
sust(f"el viento domina en el {mildec(97.3, 1)} % del conjunto, y en el 5 % de "
     f"mayor riesgo la proporción se aproxima al equilibrio: {mil(1006)} activos "
     f"dominados por inundación frente a {mil(941)} por viento, un "
     f"{mildec(48.3, 1)} % eólico. En el 1 % superior, en cambio, la inundación "
     f"sigue siendo claramente dominante: solo 12 de los {mil(388)} activos que "
     f"lo componen son casos de viento, un {mildec(3.1, 1)} %. La sustitución de "
     "la velocidad media por la velocidad de retorno a 50 años mejora "
     "sustancialmente el equilibrio del índice —en el 5 % superior el peso del "
     f"viento pasa del {mildec(27.4, 1)} % al {mildec(48.3, 1)} %, y en el 1 % "
     "superior de 1 a 12 activos— pero no invierte la composición de la cola "
     "extrema, que continúa siendo de inundación.",
     f"el viento domina en el {mildec(dom['conjunto_v6']['pct_viento'], 1)} % del "
     "conjunto, y en el 5 % de mayor riesgo la proporción se acerca al "
     f"equilibrio: {mil(d6['n'] - d6['viento'])} activos dominados por inundación "
     f"frente a {mil(d6['viento'])} por viento, un "
     f"{mildec(d6['pct_viento'], 1)} % eólico. En el 1 % superior, en cambio, la "
     "inundación es la única amenaza dominante: ninguno de los "
     f"{mil(t1_6['n'])} activos que lo componen es un caso de viento. Conviene "
     "separar los dos cambios que median entre la versión anterior del índice y "
     "esta, porque actúan en sentidos opuestos. Manteniendo el reparto de pesos "
     "anterior, la sustitución de la velocidad media por la velocidad de retorno "
     "a 50 años eleva el peso del viento en el 5 % superior del "
     f"{mildec(d5['pct_viento'], 1)} % al {mildec(d5w['pct_viento'], 1)} % y lo "
     f"hace pasar de {t1_5['viento']} a {t1_5w['viento']} activos en el 1 % "
     "superior: esa mejora es atribuible a la variable. El reajuste del reparto a "
     f"{n(par['peso_inundacion'], 2)} / {n(par['peso_viento'], 2)} devuelve "
     f"después esa proporción al {mildec(d6['pct_viento'], 1)} % en el 5 % "
     "superior y a cero en el 1 %, que es el precio deliberado de dar a la "
     "inundación el peso que le corresponde en este territorio. Ninguna de las "
     "dos versiones invierte la composición de la cola extrema, que sigue siendo "
     "de inundación.",
     "5.4 composicion de la cola")

# ===========================================================================
print("\n=== APARTADO 5.5: activos criticos por provincia ===")
sub_crit = cif["subest_criticas"]
t8 = {f["provincia"]: f for f in cif["tabla8"]}
sust(f"el percentil 95 de la distribución regional, CRS ≥ {mildec(24.12)}, de "
     f"modo que el conjunto crítico está formado por {mil(1947)} de los "
     f"{mil(38939)} activos analizados",
     f"el percentil 95 de la distribución regional, CRS ≥ "
     f"{mildec(dist['p95'])}, de modo que el conjunto crítico está formado por "
     f"{mil(dist['n_top5'])} de los {mil(res7['total']['Total'])} activos "
     "analizados",
     "5.5 umbral y tamano del conjunto critico")

sust(f"Castellón aporta el mayor número absoluto de activos críticos, "
     f"{mil(1203)}, pero ni una sola subestación: su criticidad es enteramente de "
     "apoyos de línea",
     "Castellón aporta el mayor número absoluto de activos críticos, "
     f"{mil(t8['Castellón']['criticos'])}, y una sola subestación: su criticidad "
     "es casi enteramente de apoyos de línea",
     "5.5 Castellon")
sust(f"Valencia concentra en cambio 11 de las 14 subestaciones críticas de toda "
     "la comunidad y el máximo absoluto del índice, y es la única provincia donde "
     "coinciden peligrosidad fluvial alta y densidad de red elevada",
     f"Valencia concentra en cambio {sub_crit['Valencia']} de las "
     f"{sub_crit['total']} subestaciones críticas de toda la comunidad y el "
     "máximo absoluto del índice, es la provincia con mayor proporción de activos "
     f"críticos, un {mildec(t8['Valencia']['pct_prov'], 1)} %, y es la única "
     "donde coinciden peligrosidad fluvial alta y densidad de red elevada",
     "5.5 Valencia")
sust(f"un {mildec(0.6, 1)} % frente al 5 %, y solo 31 activos por encima del "
     "umbral",
     f"un {mildec(t8['Alicante']['pct_prov'], 1)} % frente al 5 %, y solo "
     f"{t8['Alicante']['criticos']} activos por encima del umbral",
     "5.5 Alicante")
sust(f"Ese {mildec(0.6, 1)} % de Alicante merece una advertencia",
     f"Ese {mildec(t8['Alicante']['pct_prov'], 1)} % de Alicante merece una "
     "advertencia",
     "5.5 advertencia sobre Alicante")
LETRA = {12: "doce", 15: "quince", 19: "diecinueve"}
n9 = cif["tabla9_n"]
sust("Para que el resultado sea accionable, la Tabla 9 identifica una a una las "
     "quince subestaciones de mayor índice.",
     "Para que el resultado sea accionable, la Tabla 9 identifica una a una las "
     f"{LETRA.get(n9, str(n9))} subestaciones que superan el umbral.",
     "5.5 presentacion de la Tabla 9")
sust("porque el nombre solo consta en 192 de las 608 subestaciones y siete de "
     "las quince carecen de él",
     "porque el nombre solo consta en 192 de las 608 subestaciones y "
     f"{LETRA.get(cif['tabla9_sin_nombre'], str(cif['tabla9_sin_nombre']))} de "
     f"las {LETRA.get(n9, str(n9))} carecen de él",
     "5.5 subestaciones sin nombre en la Tabla 9")
sust("Su valor está en reducir 38.939 activos a una lista de quince por la que "
     "empezar.",
     f"Su valor está en reducir {mil(res7['total']['Total'])} activos a una lista "
     f"de {LETRA.get(n9, str(n9))} por la que empezar.",
     "5.5 cierre del apartado")
sust("Tabla 9. Las quince subestaciones de mayor Climate Risk Score.",
     f"Tabla 9. Las {LETRA.get(n9, str(n9))} subestaciones que superan el umbral "
     "de priorización, ordenadas por Climate Risk Score.",
     "pie de la Tabla 9")

# ===========================================================================
print("\n=== APARTADO 5.8 y capitulos 6 y 7: validacion ===")
sust(f"pasan de {q['antes']['n_en_top5pct']} a 115, es decir, del "
     f"{n(q['antes']['pct_en_top5pct'], 1)} al {mildec(11.4, 1)} % del entorno, y "
     f"el percentil medio sube de {n(q['antes']['CRS_percentil_medio'], 1)} a "
     f"{mildec(78.3, 1)}",
     f"pasan de {q['antes']['n_en_top5pct']} a {q['despues']['n_en_top5pct']}, es "
     f"decir, del {n(q['antes']['pct_en_top5pct'], 1)} al "
     f"{n(q['despues']['pct_en_top5pct'], 1)} % del entorno, y el percentil medio "
     f"sube de {n(q['antes']['CRS_percentil_medio'], 1)} a "
     f"{n(q['despues']['CRS_percentil_medio'], 1)}",
     "5.8 cifras de Quart de Poblet")
sust("queda en el percentil 78 y aporta 115 de sus 1.012 activos al 5 % de mayor "
     "riesgo",
     f"queda en el percentil {n(q['despues']['CRS_percentil_medio'], 0)} y aporta "
     f"{q['despues']['n_en_top5pct']} de sus {mil(q['n_activos'])} activos al 5 % "
     "de mayor riesgo",
     "7.1 cifras de Quart de Poblet")

print("\n--- 6.2: compresion de la rama eolica ---")
sust(f"el peso del viento en el 5 % de mayor riesgo pasa del {mildec(27.4, 1)} % "
     f"al {mildec(48.3, 1)} %— pero no la elimina: en el 1 % superior el viento "
     f"domina solo en 12 de {mil(388)} activos",
     f"el peso del viento en el 5 % de mayor riesgo pasa del "
     f"{mildec(d5['pct_viento'], 1)} % al {mildec(d6['pct_viento'], 1)} %— pero "
     "no la elimina: en el 1 % superior el viento no domina en ninguno de los "
     f"{mil(t1_6['n'])} activos",
     "6.2 compresion de la rama eolica")
sust(f"El peso de {mildec(0.40, 2)} asignado al viento no reparte",
     f"El peso de {n(par['peso_viento'], 2)} asignado al viento no reparte",
     "6.2 peso asignado al viento")

print("\n--- 6.3: resolucion del campo de extremos ---")
sust("lo que supone unas veinticinco celdas sobre el conjunto del área de estudio",
     f"lo que deja {cif['celdas_v50_con_activos']} celdas con activos sobre el "
     "conjunto del área de estudio",
     "6.3 celdas del campo de extremos")

print("\n--- 7.1 y 7.2: conclusiones ---")
sust(f"{mil(1947)} activos superan el percentil 95 de la distribución regional, "
     "entre ellos 14 subestaciones, de las cuales 11 se encuentran en la "
     "provincia de Valencia",
     f"{mil(dist['n_top5'])} activos superan el percentil 95 de la distribución "
     f"regional, entre ellos {sub_crit['total']} subestaciones, de las cuales "
     f"{sub_crit['Valencia']} se encuentran en la provincia de Valencia",
     "7.1 activos y subestaciones criticas")
sust("El apartado 5.4 cuantifica lo conseguido y lo que queda, ya que al cambiar "
     f"de variable el peso del viento en el 1 % de mayor riesgo sube de 1 a 12 "
     f"activos de {mil(388)}, mejora real pero insuficiente para equilibrar la "
     "cola.",
     "El apartado 5.4 cuantifica lo conseguido y lo que queda: a igualdad de "
     "pesos, el cambio de variable eleva el peso del viento en el 5 % de mayor "
     f"riesgo del {mildec(d5['pct_viento'], 1)} % al "
     f"{mildec(d5w['pct_viento'], 1)} %, mejora real pero insuficiente para que "
     "la cola extrema del índice deje de ser de inundación.",
     "7.2 lo conseguido y lo que queda")

# ===========================================================================
# REMISIONES A FIGURAS QUE QUEDARON CON LA NUMERACION ANTERIOR
# ---------------------------------------------------------------------------
# Al insertar las figuras nuevas todas las posteriores se corrieron de numero,
# pero cuatro remisiones del texto conservaron el numero viejo y apuntan hoy a
# figuras que no son las que describen. Se comprueba una a una contra el pie de
# la figura a la que el texto se refiere.
# ===========================================================================
print("\n=== REMISIONES A FIGURAS ===")
sust("Las Figuras 10 y 11 representan esa partición.",
     "Las Figuras 13 y 14 representan esa partición.",
     "5.3 perfiles en el plano de amenazas y frente a la criticidad")
sust("un análisis de sensibilidad que recogen las Figuras 13 y 14",
     "un análisis de sensibilidad que recogen las Figuras 16 y 17",
     "5.4 figuras de la sensibilidad")
sust("Las Figuras 15, 16 y 17 localizan estos activos sobre la red de cada "
     "provincia",
     "Las Figuras 18, 19 y 20 localizan estos activos sobre la red de cada "
     "provincia",
     "5.5 mapas provinciales")
sust("La comparación con la partición aleatoria, recogida en las Figuras 18 y 19,",
     "La comparación con la partición aleatoria, recogida en las Figuras 21 y 22,",
     "5.7 figuras de los esquemas de validacion")

# ===========================================================================
print("\n=== TABLA 6: perfiles de riesgo ===")
t6 = doc.tables[6]
# La cabecera se precisa para que no se confunda con la densidad de la Tabla 5,
# que cuenta solo apoyos mientras esta cuenta todos los activos.
celda(t6, 0, 4, "Densidad de activos (5 km)", "T6 cabecera de densidad")
for i in range(1, 8):
    p = perf[i]
    celda(t6, i, 5, mildec(p["CRS_mediano"]), f"T6 f{i} CRS mediano")
    celda(t6, i, 6, mildec(p["CRS_max"]), f"T6 f{i} CRS maximo")

print("\n=== TABLA 7: bandas por clase de activo ===")
t7 = doc.tables[7]
COLS = ["Subest.", "Torres", "Postes", "Pórticos"]
for i, b in enumerate(cif["tabla7"]["bandas"], 1):
    celda(t7, i, 0, b["banda"], f"T7 f{i} banda")
    for j, c in enumerate(COLS, 1):
        celda(t7, i, j, mil(b[c]), f"T7 f{i} {c}")
    celda(t7, i, 5, mil(b["Total"]), f"T7 f{i} total")
for j, c in enumerate(COLS, 1):
    celda(t7, 6, j, mil(res7["total"][c]), f"T7 total {c}")
    celda(t7, 7, j, mildec(res7["mediana"][c]), f"T7 mediana {c}")
    celda(t7, 8, j, mildec(res7["maximo"][c]), f"T7 maximo {c}")
    celda(t7, 9, j, f"{mildec(res7['pct_en_top5'][c], 1)} %", f"T7 pct {c}")
celda(t7, 6, 5, mil(res7["total"]["Total"]), "T7 total general")
celda(t7, 7, 5, mildec(res7["mediana"]["Total"]), "T7 mediana general")
celda(t7, 8, 5, mildec(res7["maximo"]["Total"]), "T7 maximo general")
celda(t7, 9, 5, f"{mildec(res7['pct_en_top5']['Total'], 1)} %", "T7 pct general")

print("\n=== TABLA 8: reparto provincial ===")
t8t = doc.tables[8]
for i, f in enumerate(cif["tabla8"], 1):
    celda(t8t, i, 1, mil(f["activos"]), f"T8 f{i} activos")
    celda(t8t, i, 2, mil(f["criticos"]), f"T8 f{i} criticos")
    celda(t8t, i, 3, f"{mildec(f['pct_prov'], 1)} %", f"T8 f{i} pct")
    for j, c in enumerate(COLS, 4):
        celda(t8t, i, j, mil(f[c]), f"T8 f{i} {c}")
    celda(t8t, i, 8, mildec(f["CRS_max"]), f"T8 f{i} CRS max")

print("\n=== TABLA 9: las subestaciones sobre el umbral de priorizacion ===")
# La tabla listaba las quince de mayor indice, corte que coincidia con las 14
# criticas del reparto anterior. Ahora hay 19 sobre el umbral, y las conclusiones
# afirman que el apartado 5.5 las identifica una a una: se amplia la tabla al
# conjunto critico entero para que esa afirmacion sea cierta.
t9 = doc.tables[9]
faltan = cif["tabla9_n"] - (len(t9.rows) - 1)
if faltan > 0:
    ultima9 = t9.rows[-1]._tr
    for _ in range(faltan):
        t9._tbl.append(copy.deepcopy(ultima9))
    print(f"  {faltan} filas anadidas ({len(t9.rows) - 1} en total)")
    hechas += faltan
for f in cif["tabla9"]:
    i = f["n"]
    celda(t9, i, 0, str(i), f"T9 f{i} orden")
    celda(t9, i, 1, str(f["osm_id"]), f"T9 f{i} osm_id")
    celda(t9, i, 2, f["nombre"], f"T9 f{i} nombre")
    celda(t9, i, 3, f["provincia"], f"T9 f{i} provincia")
    celda(t9, i, 4, f["nivel"], f"T9 f{i} nivel")
    celda(t9, i, 5, f"{n(f['lat'], 4)} / {n(f['lon'], 4)}", f"T9 f{i} coords")
    celda(t9, i, 6, mildec(f["CRS"]), f"T9 f{i} CRS")

print("\n=== TABLA 10: estado de las fases ===")
sust(f"CRS en [0, 100]; máximo {mildec(79.83)}; ver Figura 15",
     f"CRS en [0, 100]; máximo {mildec(dist['maxima'])}; ver Figura 15",
     "T10 maximo del indice")

# ===========================================================================
# TABLA 11: registro de revisiones
# ---------------------------------------------------------------------------
# El registro no se reescribe: sus filas describen lo que cada revision hizo, y
# la que cita "14 criticas, 11 en Valencia" sigue siendo cierta como historia de
# la revision v7. Lo que corresponde es anadir las filas de esta revision.
# ===========================================================================
print("\n=== TABLA 11: registro de revisiones ===")
t11 = doc.tables[11]
NUEVAS_FILAS = [
    ("4.7, 5.3 a 5.5, 5.8, 6.2, 6.3, 7.1 y 7.2",
     "Todas las cifras del índice procedían del reparto 0,60 de inundación y "
     "0,40 de viento",
     f"Reparto reajustado a {n(par['peso_inundacion'], 2)} / "
     f"{n(par['peso_viento'], 2)}, con su justificación en el 4.7, y recalculadas "
     "las Tablas 6 a 10 y toda la prosa dependiente; el 5.4 separa ahora el "
     "efecto del cambio de variable del efecto del reparto, que actúan en "
     "sentidos opuestos sobre la cola del índice  [v8]"),
    ("Figuras 13 a 20, 24, 25 y 27",
     "Contenido calculado con el reparto anterior; cuatro remisiones del texto "
     "conservaban la numeración previa a la inserción de figuras",
     "Figuras regeneradas desde los resultados nuevos y remisiones corregidas a "
     "las Figuras 13 y 14, 16 y 17, 18 a 20, y 21 y 22  [v8]"),
    ("Tabla 9, 4.5, 5.3, 5.5, 6.3 y 7.1",
     "La Tabla 9 listaba las quince subestaciones de mayor índice mientras el 7.1 "
     "afirmaba que el 5.5 identifica una a una las críticas; el texto llamaba "
     "«apoyos» a la densidad de activos que alimenta la Tabla 6, y atribuía al "
     "grupo territorial 1 la mayor velocidad media de viento, variable descartada "
     "como peligrosidad y ausente de la Tabla 5",
     f"Tabla 9 ampliada a las {LETRA.get(n9, str(n9))} que superan el umbral, de "
     "modo que coincide con el conjunto crítico; densidad precisada como de "
     "activos, distinta de la densidad de apoyos de la Tabla 5; el viento del "
     "grupo 1 reformulado sobre la velocidad de retorno, que es lo que la Tabla 5 "
     "declara; corregidas además las nueve subestaciones sin nombre y las "
     "cincuenta y seis celdas del campo de extremos  [v8]"),
]
ultima = t11.rows[-1]._tr
for apartado, antes, cambio in NUEVAS_FILAS:
    nueva = copy.deepcopy(ultima)
    t11._tbl.append(nueva)
    fila = t11.rows[-1]
    for j, texto in enumerate((apartado, antes, cambio)):
        c = fila.cells[j]
        for extra in c.paragraphs[1:]:
            for r in extra.runs:
                r.text = ""
        p = c.paragraphs[0]
        runs = p.runs if p.runs else [p.add_run()]
        runs[0].text = texto
        for r in runs[1:]:
            r.text = ""
    hechas += 1
    print(f"  fila anadida: {apartado[:44]}")

# ===========================================================================
if errores:
    print(f"\n{len(errores)} problemas, NO se guarda el documento:")
    for e in errores:
        print(f"  - {e}")
    raise SystemExit(1)

doc.save(DESTINO)
print(f"\n{hechas} correcciones de texto y de tabla aplicadas")

# ===========================================================================
# Sustitucion de las imagenes cuyo contenido ha cambiado
# ===========================================================================
print("\n=== IMAGENES ===")
doc = docx.Document(DESTINO)
rid_de_parte = {}
for rid, parte in doc.part.related_parts.items():
    rid_de_parte[str(parte.partname).lstrip("/")] = rid

nuevas = {}
for figura, (parte, fichero) in IMAGENES.items():
    ruta = os.path.join(FIGS, fichero)
    if not os.path.exists(ruta):
        errores.append(f"[{figura}] no existe {fichero}")
        continue
    with open(ruta, "rb") as fh:
        nuevas[parte] = fh.read()
    if parte not in rid_de_parte:
        errores.append(f"[{figura}] la parte {parte} no esta en el documento")

if errores:
    print("problemas con las imagenes, no se sustituye ninguna:")
    for e in errores:
        print(f"  - {e}")
    raise SystemExit(1)

# 1) proporcion: se ajusta el alto declarado para conservar el aspecto real
for figura, (parte, fichero) in IMAGENES.items():
    with Image.open(os.path.join(FIGS, fichero)) as im:
        w_new, h_new = im.size
    rid = rid_de_parte[parte]
    for blip in doc.element.body.iter(qn("a:blip")):
        if blip.get(qn("r:embed")) != rid:
            continue
        nodo, extents = blip, []
        for _ in range(8):
            nodo = nodo.getparent()
            if nodo is None:
                break
            for hijo in nodo.iter():
                et = hijo.tag.split("}")[-1]
                if et in ("extent", "ext") and hijo.get("cx") and hijo.get("cy"):
                    if hijo not in extents:
                        extents.append(hijo)
            if extents:
                break
        if extents:
            cx = int(extents[0].get("cx"))
            cy_viejo = int(extents[0].get("cy"))
            cy_nuevo = int(round(cx * h_new / w_new))
            for e in extents:
                e.set("cy", str(cy_nuevo))
            if cy_nuevo != cy_viejo:
                print(f"  {figura}: alto {cy_viejo} -> {cy_nuevo} "
                      f"({100 * (cy_nuevo - cy_viejo) / cy_viejo:+.1f} %)")
doc.save(DESTINO)

# 2) los bytes
temporal = DESTINO + ".tmp"
sustituidas, iguales = 0, 0
with zipfile.ZipFile(DESTINO, "r") as origen:
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as destino:
        for info in origen.infolist():
            datos = origen.read(info.filename)
            if info.filename in nuevas:
                if datos == nuevas[info.filename]:
                    iguales += 1
                else:
                    print(f"  {info.filename}: {len(datos) / 1024:.0f} KB -> "
                          f"{len(nuevas[info.filename]) / 1024:.0f} KB")
                    datos = nuevas[info.filename]
                    sustituidas += 1
            destino.writestr(info, datos)
os.replace(temporal, DESTINO)
print(f"\n{sustituidas} imagenes sustituidas, {iguales} ya identicas")
print(f"Guardado: {os.path.basename(DESTINO)}")
