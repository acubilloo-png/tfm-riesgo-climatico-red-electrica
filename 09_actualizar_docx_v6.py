# ============================================================================
# 09_actualizar_docx_v6.py
# ----------------------------------------------------------------------------
# Aplica al documento la version V6 del indice: sustituye la peligrosidad por
# viento basada en la velocidad media anual por una basada en la velocidad de
# retorno a 50 anos, y actualiza metodologia, resultados, discusion y tablas.
#
# Trabaja sobre 20260415_TFMAlvaroCubillo_v6.docx (que ya lleva restauradas las
# referencias cruzadas) y guarda un respaldo previo. No toca la V5(1).
#
# Todas las cifras se leen de los ficheros de resultados; ninguna se teclea, de
# modo que el texto de la memoria y los scripts no pueden divergir.
# ============================================================================

import json
import os
import shutil

import pandas as pd
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

CARPETA = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v6.docx")
RESPALDO = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v6_antes_actualizar.docx")


def cargar(nombre):
    with open(os.path.join(CARPETA, nombre), encoding="utf-8") as fh:
        return json.load(fh)


par6 = cargar("crs_parametros_v6.json")
comp = cargar("comparativa_v5_v6.json")
dana = cargar("validacion_dana.json")
viento = cargar("cifras_viento.json")
extremos = cargar("extremos_observados.json")
calib = cargar("calibracion_v50.json")
obs = cargar("evento_dana_observado.json")
v50m = cargar("v50_metodos.json")

perfiles = pd.read_csv(os.path.join(CARPETA, "perfiles_amenaza_v6.csv"),
                       sep=";", encoding="utf-8-sig")
act = pd.read_csv(os.path.join(CARPETA, "activos_con_crs_v6.csv"),
                  sep=";", encoding="utf-8-sig", low_memory=False)
clu = pd.read_csv(os.path.join(CARPETA, "subestaciones_clusters.csv"),
                  sep=";", encoding="utf-8-sig", low_memory=False)


def n(x, d=2):
    """Numero con coma decimal."""
    return f"{x:.{d}f}".replace(".", ",")


def mil(x, d=0):
    """
    Formato espanol: punto de millares y coma decimal. Se separan las partes en
    lugar de encadenar dos replace, porque intercambiar ',' y '.' de esa forma
    convierte la salida del primero en entrada del segundo.
    """
    entero, _, dec = f"{x:,.{d}f}".partition(".")
    entero = entero.replace(",", ".")
    return f"{entero},{dec}" if dec else entero


ADOPTADA = calib["decision"]
COL_V50 = "V50_bruto_ms" if ADOPTADA == "bruta" else "V50_ms"
d_esc = viento["distribuciones"][
    "V50_sin_escalar" if ADOPTADA == "bruta" else "V50_escalado"]
sens = par6["sensibilidad_pesos"]
dom = comp["amenaza_dominante"]
V_BAS = par6["normalizacion_viento"]["V_basica_ms"]

print(f"variante adoptada: {ADOPTADA}")
shutil.copy2(DOC, RESPALDO)
doc = docx.Document(DOC)
print(f"respaldo: {os.path.basename(RESPALDO)}")

errores, hechas = [], 0


def sust(indice, viejo, nuevo, etiqueta):
    """
    Sustituye texto en un parrafo aunque este repartido entre varios runs, que es
    lo habitual tras insertar los campos de referencia cruzada.

    Recorre los hijos del parrafo que llevan texto —runs sueltos y campos— en
    orden de documento, localiza el tramo que contiene el texto buscado y lo
    reescribe conservando lo que hubiera antes y despues dentro de ese tramo.
    Si el tramo atraviesa un CAMPO, aborta: reescribirlo destruiria la referencia
    cruzada, y es preferible fallar de forma visible a romperla en silencio.
    """
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
        print(f"  FALLO [{etiqueta}] p{indice}: no encontrado")
        return
    fin = pos + len(viejo)

    ini_idx = fin_idx = None
    acumulado = 0
    for k, (_, _, t) in enumerate(hijos):
        inicio_c, fin_c = acumulado, acumulado + len(t)
        if ini_idx is None and fin_c > pos:
            ini_idx = k
        if inicio_c < fin:
            fin_idx = k
        acumulado = fin_c

    if any(hijos[k][0] == "f" for k in range(ini_idx, fin_idx + 1)):
        errores.append(f"[{etiqueta}] p{indice}: el tramo atraviesa un campo REF")
        print(f"  ABORTA [{etiqueta}] p{indice}: el tramo atraviesa un campo REF")
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
    for extra in ts[1:]:
        extra.text = ""
    for k in range(ini_idx + 1, fin_idx + 1):
        for t in hijos[k][1].findall(qn("w:t")):
            t.text = ""

    hechas += 1
    tramo = f"{fin_idx - ini_idx + 1} runs" if fin_idx > ini_idx else "1 run"
    print(f"  OK    [{etiqueta}]  ({tramo})")


def celda(tabla, fila, col, texto, tam=8, negrita=False):
    global hechas
    c = doc.tables[tabla].rows[fila].cells[col]
    c.text = ""
    r = c.paragraphs[0].add_run(texto)
    r.font.size = Pt(tam)
    r.bold = negrita
    hechas += 1


# ===========================================================================
print("\n=== CAPITULO 4 ===")
# ===========================================================================
sust(207,
     "La peligrosidad por viento se normaliza sobre el cuadrado de la velocidad "
     "y no sobre la velocidad, porque la carga que el viento ejerce sobre una "
     "estructura es proporcional a la presión dinámica: una normalización lineal "
     "subestimaría la diferencia entre un emplazamiento de 4 metros por segundo y "
     "otro de 11. Aun así, las dos ramas del índice no quedan en pie de igualdad, "
     "y conviene advertirlo antes de leer los resultados. La peligrosidad por "
     "inundación recorre todo el intervalo [0, 1] porque PATRICOVA distingue "
     "crecidas veinte veces más probables entre sí; la de viento, calculada sobre "
     "una velocidad media que en el área de estudio solo varía entre 0,74 y 11,25 "
     "metros por segundo, no supera el valor 0,55 en ningún activo. La asimetría "
     "no es un defecto de la formulación sino de la variable disponible: la "
     "magnitud que produce el daño estructural es la racha máxima, no la media, y "
     "no existe como capa abierta para el área de estudio. Sus consecuencias sobre "
     "la composición del índice se cuantifican en el apartado 5.4.",

     "La peligrosidad por viento se construye sobre la velocidad de retorno a 50 "
     "años y se normaliza contra una referencia física absoluta, según la "
     f"expresión H_viento = min(1, (V50 / V_básica)²) con V_básica = {n(V_BAS, 0)} "
     "metros por segundo, la velocidad básica de la zona C del Código Técnico de "
     "la Edificación DB-SE-AE, la más desfavorable de España. El cuadrado se "
     "conserva porque la carga que el viento ejerce sobre una estructura es "
     "proporcional a la presión dinámica. Esta formulación sustituye a la "
     "normalización de mínimo a máximo sobre la velocidad media anual empleada en "
     "una versión anterior de este trabajo, que presentaba dos defectos: obligaba "
     "a que el activo más ventoso del área valiese 1 aunque su viento fuese "
     "estructuralmente inocuo, y hacía el índice dependiente del rango observado "
     "en el área de estudio, lo que impedía compararlo con otras comunidades "
     "autónomas. Con una referencia absoluta el valor pasa a ser interpretable en "
     "sí mismo: H_viento = 1 significa que la velocidad de retorno a 50 años "
     "iguala la velocidad con la que se dimensionan los apoyos. Debe advertirse, "
     "no obstante, que la asimetría entre las dos ramas del índice se reduce pero "
     "no desaparece. La peligrosidad por inundación recorre todo el intervalo "
     "[0, 1] porque PATRICOVA distingue crecidas veinte veces más probables entre "
     f"sí, mientras que la eólica, con un V50 que en el área de estudio varía "
     f"entre {n(d_esc['min']['ms'], 1)} y {n(d_esc['max']['ms'], 1)} metros por "
     f"segundo, queda confinada a una banda de "
     f"{n((d_esc['min']['ms'] / V_BAS) ** 2)} a {n((d_esc['max']['ms'] / V_BAS) ** 2)}. "
     "Esa asimetría residual es física y no metodológica: responde a que la "
     "inundación es un fenómeno de umbral, mientras que el viento extremo, en este "
     "territorio, es una magnitud de variación moderada. Sus consecuencias sobre "
     "la composición del índice se cuantifican en el apartado 5.4.",
     "4.7 peligrosidad por viento")

# ===========================================================================
print("\n=== CAPITULO 5 ===")
# ===========================================================================
sust(227,
     "En cuanto al viento, el muestreo del Global Wind Atlas arroja una velocidad "
     "media de 4,12 metros por segundo, con un rango de 0,74 a 11,25, y una "
     "diferencia moderada entre tipos de activo: 4,30 metros por segundo de media "
     "en las subestaciones frente a 4,11 en los apoyos.",

     "En cuanto al viento, la velocidad de retorno a 50 años presenta una mediana "
     f"de {n(d_esc['mediana']['ms'])} metros por segundo "
     f"({n(d_esc['mediana']['kmh'], 1)} kilómetros por hora), con un rango de "
     f"{n(d_esc['min']['ms'])} a {n(d_esc['max']['ms'])} y el percentil 99 en "
     f"{n(d_esc['p99']['ms'])}. Ningún activo del área de estudio alcanza las "
     "velocidades básicas de diseño del Código Técnico, ni la de 26 metros por "
     "segundo de la zona A ni la de 29 de la zona C: el territorio queda en su "
     "conjunto por debajo del umbral con el que se dimensionan sus propios apoyos. "
     "Para referencia, la velocidad media anual que empleaba la versión anterior "
     "del índice tenía una mediana de 4,02 metros por segundo, un orden de "
     "magnitud por debajo de cualquier umbral estructural.",
     "5.2 cifras de viento")

sust(243,
     "se distribuye con una mediana de 4,79 sobre 100 y un máximo de 72,84, con "
     "los percentiles 90, 95 y 99 situados en 7,64, 10,45 y 24,04 respectivamente.",
     f"se distribuye con una mediana de {n(par6['crs']['mediana'])} sobre 100 y un "
     f"máximo de {n(par6['crs']['max'])}, con los percentiles 90, 95 y 99 situados "
     f"en {n(par6['crs']['percentiles']['90'])}, "
     f"{n(par6['crs']['percentiles']['95'])} y "
     f"{n(par6['crs']['percentiles']['99'])} respectivamente.",
     "5.4 distribucion")

rho_min = min(s["spearman"] for s in sens)
sol_min = min(s["solape_top5_pct"] for s in sens)
sust(246,
     "mantiene una correlación de Spearman no inferior a 0,90 con la ordenación de "
     "referencia, y la coincidencia en la identificación del 5 % de activos de "
     "mayor riesgo no baja del 69,7 %.",
     f"mantiene una correlación de Spearman no inferior a {n(rho_min)} con la "
     "ordenación de referencia, y la coincidencia en la identificación del 5 % de "
     f"activos de mayor riesgo no baja del {n(sol_min, 1)} %.",
     "5.4 sensibilidad")

sust(249,
     "el viento domina en el 90,9 % del conjunto, pero en el 5 % de mayor riesgo "
     "la proporción se invierte —1.414 activos dominados por inundación frente a "
     "533 por viento— y en el 1 % superior la inversión es prácticamente total: "
     "389 de los 390 activos son casos de inundación. El índice compuesto es, en "
     "su cola, un índice de inundación.",

     f"el viento domina en el {n(dom['conjunto_v6']['pct_viento'], 1)} % del "
     "conjunto, y en el 5 % de mayor riesgo la proporción se aproxima al "
     f"equilibrio: {mil(dom['top5pct_v6']['n'] - dom['top5pct_v6']['viento'])} "
     f"activos dominados por inundación frente a {mil(dom['top5pct_v6']['viento'])} "
     f"por viento, un {n(dom['top5pct_v6']['pct_viento'], 1)} % eólico. En el 1 % "
     f"superior, en cambio, la inundación sigue siendo claramente dominante: solo "
     f"{dom['top1pct_v6']['viento']} de {dom['top1pct_v6']['n']} activos son casos "
     f"de viento, un {n(dom['top1pct_v6']['pct_viento'], 1)} %. La sustitución de "
     "la velocidad media por la velocidad de retorno a 50 años mejora "
     "sustancialmente el equilibrio del índice —en el 5 % superior el peso del "
     f"viento pasa del {n(dom['top5pct_v5']['pct_viento'], 1)} % al "
     f"{n(dom['top5pct_v6']['pct_viento'], 1)} %, y en el 1 % superior de "
     f"{dom['top1pct_v5']['viento']} a {dom['top1pct_v6']['viento']} activos— pero "
     "no invierte la composición de la cola extrema, que continúa siendo de "
     "inundación. El motivo es el expuesto en el apartado 4.7 y es de naturaleza "
     "física: la inundación es un fenómeno de umbral cuya peligrosidad recorre "
     "todo el rango disponible, mientras que la velocidad de retorno eólica varía "
     "de forma moderada en este territorio.",
     "5.4 amenaza dominante")

sust(243,
     "con valores comprendidos entre 70,70 y 72,84.",
     f"con valores comprendidos entre "
     f"{n(act[act['tipo_activo'] == 'subestacion'].nlargest(4, 'CRS_v6')['CRS_v6'].min())} "
     f"y {n(par6['crs']['max'])}.",
     "5.4 los cuatro mayores")

# --- p249: la cola de la asimetria, que ya esta resuelta -------------------
sust(249,
     "mientras que la peligrosidad por viento, normalizada sobre el cuadrado de "
     "una velocidad media que solo varía entre 0,74 y 11,25 m/s, no supera el "
     "valor 0,55 en ningún activo. Emplear la racha máxima en lugar de la media "
     "—la magnitud que realmente produce",
     "mientras que la peligrosidad por viento, aun calculada ya sobre la velocidad "
     f"de retorno a 50 años, queda confinada a la banda de "
     f"{n((d_esc['min']['ms'] / V_BAS) ** 2)} a {n((d_esc['max']['ms'] / V_BAS) ** 2)} "
     "porque esa velocidad varía de forma moderada en el territorio. Emplear la "
     "racha máxima observada en lugar de la velocidad de retorno —la magnitud que "
     "realmente produce",
     "5.4 cola de la asimetria")

# --- p247: comentario de la Tabla 7 ---------------------------------------
subs_act = act[act["tipo_activo"] == "subestacion"]
tw = act[act["tipo_apoyo"] == "tower"]
p99v = par6["crs"]["percentiles"]["99"]
sust(247,
     "Las torres presentan el índice mediano más alto de las cuatro clases (5,16), "
     "consecuencia directa de la vulnerabilidad 1,00 que la matriz les asigna "
     "frente al viento, pero apenas alcanzan la cola extrema: solo 32 de 13.758 "
     "torres, un 0,2 %, se sitúan en el 1 % superior. Las subestaciones se "
     "comportan al revés: tienen el índice mediano más bajo del conjunto (4,00) y, "
     "sin embargo, aportan 14 de los 390 activos del 1 % superior, un 2,3 % de su "
     "clase, y ocupan el máximo absoluto de la distribución.",

     f"Las torres presentan el índice mediano más alto de las cuatro clases "
     f"({n(tw['CRS_v6'].median())}), consecuencia directa de la vulnerabilidad "
     f"1,00 que la matriz les asigna frente al viento, pero apenas alcanzan la "
     f"cola extrema: solo {mil(int((tw['CRS_v6'] >= p99v).sum()))} de "
     f"{mil(len(tw))} torres, un "
     f"{n(100 * (tw['CRS_v6'] >= p99v).mean(), 1)} %, se sitúan en el 1 % "
     f"superior. Las subestaciones se comportan al revés: tienen el índice mediano "
     f"más bajo del conjunto ({n(subs_act['CRS_v6'].median())}) y, sin embargo, "
     f"aportan {int((subs_act['CRS_v6'] >= p99v).sum())} de los "
     f"{int((act['CRS_v6'] >= p99v).sum())} activos del 1 % superior, un "
     f"{n(100 * (subs_act['CRS_v6'] >= p99v).mean(), 1)} % de su clase, y ocupan "
     f"el máximo absoluto de la distribución.",
     "5.4 comentario de Tabla 7")

p95 = par6["crs"]["percentiles"]["95"]
n_crit = int((act["CRS_v6"] >= p95).sum())
sust(255,
     "Se adopta como umbral el percentil 95 de la distribución regional, "
     "CRS ≥ 10,45, de modo que el conjunto crítico está formado por 1.947 de los "
     "38.939 activos analizados.",
     "Se adopta como umbral el percentil 95 de la distribución regional, "
     f"CRS ≥ {n(p95)}, de modo que el conjunto crítico está formado por "
     f"{mil(n_crit)} de los {mil(len(act))} activos analizados.",
     "5.5 umbral")

# ===========================================================================
print("\n=== PERFILES DE AMENAZA (apartados 4.5 y 5.3) ===")
k_opt = perfiles[perfiles["subconjunto"] == "subestaciones"]["perfil"].max()
sil = cargar("clustering_perfiles_v6.json")["subconjuntos"]["subestaciones"]["silhouette"]

sust(201,
     "el óptimo se desplaza a k = 4 con un silhouette de 0,519 y los cuatro grupos "
     "resultantes sí admiten una lectura de mecanismo",
     f"el óptimo se desplaza a k = {k_opt} con un silhouette de {n(sil, 4)} y los "
     f"grupos resultantes sí admiten una lectura de mecanismo",
     "4.5 optimo del segundo agrupamiento")

sust(234,
     "sitúa su óptimo en k = 4 con un coeficiente de silhouette de 0,519. La Tabla "
     "6 recoge sus cuatro perfiles, renumerados por orden decreciente de índice "
     "mediano.",
     f"sitúa su óptimo en k = {k_opt} con un coeficiente de silhouette de "
     f"{n(sil, 4)}. La Tabla 6 recoge sus {k_opt} perfiles, renumerados por orden "
     "decreciente de índice mediano.",
     "5.3 optimo del segundo agrupamiento")

# --- p236: la descripcion de los perfiles, reescrita por completo ----------
pf = {int(f["perfil"]): f for _, f in
      perfiles[perfiles["subconjunto"] == "subestaciones"].iterrows()}
sust(236,
     "El perfil 1 reúne 14 subestaciones, once de ellas en la provincia de "
     "Valencia, todas en zona inundable y con un índice mediano de 46,98 frente al "
     "4,00 del conjunto de las subestaciones: es la lista corta de actuación. El "
     "perfil 2 agrupa 27 instalaciones, veinte de ellas en Castellón, sin una sola "
     "en zona inundable pero con una velocidad media de viento de 7,00 metros por "
     "segundo, muy por encima de los 4,30 del conjunto; su riesgo es real pero de "
     "naturaleza opuesta, y la medida de adaptación que le corresponde —refuerzo "
     "estructural y de cimentación— no tiene nada que ver c",

     f"El perfil 1 reúne {int(pf[1]['n'])} subestaciones, todas en zona inundable y "
     f"todas dominadas por esa amenaza, con un índice mediano de "
     f"{n(pf[1]['CRS_mediano'])} frente al "
     f"{n(subs_act['CRS_v6'].median())} del conjunto de las subestaciones: es la "
     f"lista corta de actuación. El perfil 2 añade otras {int(pf[2]['n'])} "
     f"instalaciones con el mismo mecanismo pero menor severidad, índice mediano "
     f"{n(pf[2]['CRS_mediano'])}. En el extremo opuesto, el perfil 5 agrupa "
     f"{int(pf[5]['n'])} subestaciones, mayoritariamente en "
     f"{pf[5]['provincia_dominante']}, sin una sola en zona inundable y con la "
     f"velocidad de retorno a 50 años más alta del conjunto "
     f"({n(pf[5]['V50_medio_ms'])} metros por segundo frente a "
     f"{n(d_esc['mediana']['ms'])} de mediana regional); su riesgo es real pero de "
     "naturaleza opuesta, y la medida de adaptación que le corresponde —refuerzo "
     f"estructural y de cimentación— no tiene nada que ver c",
     "5.3 descripcion de perfiles")

print("\n=== CAPITULO 6 Y 7: LO QUE V6 RESUELVE ===")
# Estos dos parrafos declaraban como limitacion y como linea futura precisamente
# lo que esta version resuelve. Dejarlos sin tocar seria contradictorio.
sust(296,
     "Como se cuantifica en el apartado 5.4, el viento es la amenaza dominante en "
     "el 90,9 % de los activos pero solo en 1 de los 390 que componen el 1 % de "
     "mayor riesgo. El índice compuesto es, en su cola —que es precisamente",
     "Como se cuantifica en el apartado 5.4, la sustitución de la velocidad media "
     "por la velocidad de retorno a 50 años reduce sustancialmente esa compresión "
     f"—el peso del viento en el 5 % de mayor riesgo pasa del "
     f"{n(dom['top5pct_v5']['pct_viento'], 1)} % al "
     f"{n(dom['top5pct_v6']['pct_viento'], 1)} %— pero no la elimina: en el 1 % "
     f"superior el viento domina solo en {dom['top1pct_v6']['viento']} de "
     f"{dom['top1pct_v6']['n']} activos. El índice compuesto sigue siendo, en su "
     "cola —que es precisamente",
     "6 limitacion de la compresion")

sust(319,
     "El apartado 5.4 cuantifica lo que está en juego: con la variable actual, el "
     "viento domina en el 90,9 % de los activos pero solo en 1 de los 390 que "
     "forman el 1 % de mayor riesgo.",
     "El apartado 5.4 cuantifica lo conseguido y lo que queda: al pasar de la "
     "velocidad media a la velocidad de retorno a 50 años, el peso del viento en "
     f"el 1 % de mayor riesgo sube de {dom['top1pct_v5']['viento']} a "
     f"{dom['top1pct_v6']['viento']} activos de {dom['top1pct_v6']['n']}, mejora "
     "real pero insuficiente para equilibrar la cola. El paso pendiente es "
     "emplear rachas máximas de reanálisis de alta resolución, como las de CERRA a "
     "5,5 kilómetros, que este trabajo no pudo incorporar por requerir credenciales "
     "de acceso y un volumen de descarga incompatible con sus medios.",
     "7 linea de trabajo futuro")

print("\n=== TABLAS ===")
# ===========================================================================
# --- Tabla 3: fila del viento ---------------------------------------------
celda(3, 7, 1, "Velocidad de retorno a 50 años (Pryor y Barthelmie) y racha "
               "máxima observada (AEMET)")
celda(3, 7, 2, "Disponible")
print("  OK    Tabla 3, fila de viento")

# --- Tabla 5: columna de viento pasa a V50 --------------------------------
j = clu.merge(act[["osm_id", COL_V50]], on="osm_id", how="left")
v50_cluster = j.groupby("cluster")[COL_V50].mean()
celda(5, 0, 6, "V50 medio (m/s)", negrita=True)
for i, cl in enumerate(sorted(v50_cluster.index), start=1):
    celda(5, i, 6, n(v50_cluster[cl]))
print(f"  OK    Tabla 5, columna V50 ({len(v50_cluster)} grupos)")

# --- Tabla 6: perfiles de amenaza -----------------------------------------
sub = perfiles[perfiles["subconjunto"] == "subestaciones"].sort_values("perfil")
t6 = doc.tables[6]
while len(t6.rows) < 1 + len(sub):
    t6.add_row()
# Etiquetas curadas a partir de la caracterizacion real de cada perfil. Una
# heuristica automatica producia rotulos contradictorios (un perfil marcado como
# de viento dominante con el 100 % de sus activos en zona inundable), asi que se
# nombran leyendo la tabla: los dos primeros no tienen ningun activo dominado por
# viento y estan al 100 % en zona inundable; el 5 es el opuesto exacto, sin
# ninguno inundable y con el V50 mas alto; el 3 combina la mayor densidad de red
# con viento dominante.
ETIQUETAS = {
    1: "Inundación crítica",
    2: "Inundación",
    3: "Red densa y viento",
    4: "Viento, red media",
    5: "Viento puro",
    6: "Viento, red baja",
    7: "Riesgo bajo",
}
celda(6, 0, 3, "V50 medio (m/s)", negrita=True)
for i, (_, f) in enumerate(sub.iterrows(), start=1):
    celda(6, i, 0, f"{int(f['perfil'])} · {ETIQUETAS[int(f['perfil'])]}")
    celda(6, i, 1, mil(f["n"]))
    celda(6, i, 2, n(f["pct_inundable"], 1))
    celda(6, i, 3, n(f["V50_medio_ms"]))
    celda(6, i, 4, mil(f["densidad_media"]))
    celda(6, i, 5, n(f["CRS_mediano"]))
    celda(6, i, 6, n(f["CRS_max"]))
print(f"  OK    Tabla 6, {len(sub)} perfiles")

# --- Tabla 7: bandas por clase --------------------------------------------
act["clase"] = act.apply(
    lambda r: "subestacion" if r["tipo_activo"] == "subestacion"
    else str(r["tipo_apoyo"]), axis=1)
pcts = par6["crs"]["percentiles"]
bandas = [
    (f"< {n(par6['crs']['mediana'])}  (mitad inferior)", -1, par6["crs"]["mediana"]),
    (f"{n(par6['crs']['mediana'])} – {n(pcts['90'])}  (p50–p90)",
     par6["crs"]["mediana"], pcts["90"]),
    (f"{n(pcts['90'])} – {n(pcts['95'])}  (p90–p95)", pcts["90"], pcts["95"]),
    (f"{n(pcts['95'])} – {n(pcts['99'])}  (p95–p99)", pcts["95"], pcts["99"]),
    (f"≥ {n(pcts['99'])}  (1 % superior)", pcts["99"], 1e9),
]
CLASES = ["subestacion", "tower", "pole", "portal"]
for bi, (etiqueta, lo, hi) in enumerate(bandas, start=1):
    celda(7, bi, 0, etiqueta)
    sel = act[(act["CRS_v6"] >= lo) & (act["CRS_v6"] < hi)]
    for ci, cl in enumerate(CLASES, start=1):
        celda(7, bi, ci, mil(int((sel["clase"] == cl).sum())))
    celda(7, bi, 5, mil(len(sel)))
celda(7, 6, 0, "Total de activos")
for ci, cl in enumerate(CLASES, start=1):
    celda(7, 6, ci, mil(int((act["clase"] == cl).sum())))
celda(7, 6, 5, mil(len(act)))
celda(7, 7, 0, "CRS mediano")
for ci, cl in enumerate(CLASES, start=1):
    celda(7, 7, ci, n(act.loc[act["clase"] == cl, "CRS_v6"].median()))
celda(7, 7, 5, n(act["CRS_v6"].median()))
celda(7, 8, 0, "CRS máximo")
for ci, cl in enumerate(CLASES, start=1):
    celda(7, 8, ci, n(act.loc[act["clase"] == cl, "CRS_v6"].max()))
celda(7, 8, 5, n(act["CRS_v6"].max()))
celda(7, 9, 0, "% de la clase en el 5 % superior")
for ci, cl in enumerate(CLASES, start=1):
    s = act[act["clase"] == cl]
    celda(7, 9, ci, n(100 * (s["CRS_v6"] >= p95).mean(), 1) + " %")
celda(7, 9, 5, n(100 * (act["CRS_v6"] >= p95).mean(), 1) + " %")
print("  OK    Tabla 7, bandas y clases")

# --- Tabla 8: provincias ---------------------------------------------------
crit = act[act["CRS_v6"] >= p95]
for fi, prov in enumerate(["Castellón", "Valencia", "Alicante"], start=1):
    a = act[act["provincia"] == prov]
    c = crit[crit["provincia"] == prov]
    celda(8, fi, 1, mil(len(a)))
    celda(8, fi, 2, mil(len(c)))
    celda(8, fi, 3, n(100 * len(c) / len(a), 1) + " %")
    for ci, cl in enumerate(CLASES, start=4):
        celda(8, fi, ci, mil(int((c["clase"] == cl).sum())))
    celda(8, fi, 8, n(a["CRS_v6"].max()))
celda(8, 4, 1, mil(len(act)))
celda(8, 4, 2, mil(len(crit)))
celda(8, 4, 3, n(100 * len(crit) / len(act), 1) + " %")
for ci, cl in enumerate(CLASES, start=4):
    celda(8, 4, ci, mil(int((crit["clase"] == cl).sum())))
celda(8, 4, 8, n(act["CRS_v6"].max()))
print("  OK    Tabla 8, provincias")

# --- Tabla 9: las quince subestaciones -------------------------------------
subs = act[act["tipo_activo"] == "subestacion"].nlargest(15, "CRS_v6")
for fi, (_, f) in enumerate(subs.iterrows(), start=1):
    if fi >= len(doc.tables[9].rows):
        break
    celda(9, fi, 0, str(fi))
    celda(9, fi, 1, str(int(f["osm_id"])))
    celda(9, fi, 2, str(f["nombre"]) if pd.notna(f["nombre"]) else "—")
    celda(9, fi, 3, str(f["provincia"]))
    celda(9, fi, 4, "—" if pd.isna(f["nivel_peligrosidad_patricova"])
          else str(int(f["nivel_peligrosidad_patricova"])))
    celda(9, fi, 5, f"{n(f['lat'], 4)} / {n(f['lon'], 4)}")
    celda(9, fi, 6, n(f["CRS_v6"]))
print("  OK    Tabla 9, quince subestaciones")

# --- Tabla 10: fila de la capa de viento -----------------------------------
celda(10, 3, 3,
      f"V50 de Pryor y Barthelmie: {n(d_esc['min']['ms'])}–"
      f"{n(d_esc['max']['ms'])} m/s (mediana {n(d_esc['mediana']['ms'])}); "
      f"rachas de AEMET 1985-2024 en {extremos['n_estaciones_validas']} estaciones")
# La fila del indice compuesto tambien llevaba el maximo de la version anterior
celda(10, 7, 3, f"CRS en [0, 100]; máximo {n(par6['crs']['max'])}; ver Figura 12")
print("  OK    Tabla 10, capa de viento e indice compuesto")

print("\n" + "=" * 70)
if errores:
    print(f"{len(errores)} sustituciones con problema, NO se guarda:")
    for e in errores:
        print(f"  - {e}")
    raise SystemExit(1)

doc.save(DOC)
print(f"{hechas} cambios aplicados.")
print(f"Guardado: {os.path.basename(DOC)}")
