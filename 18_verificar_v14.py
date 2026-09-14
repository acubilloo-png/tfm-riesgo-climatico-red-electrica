# ============================================================================
# 18_verificar_v14.py
# ----------------------------------------------------------------------------
# Comprueba que la V14 esta bien formada, que no conserva ninguna cifra del
# reparto anterior y que las cifras que ahora declara coinciden con los ficheros
# de resultados. Es la red de seguridad del script 17: si algo se corrigio a
# medias, aparece aqui.
# ============================================================================

import json
import os
import re
import zipfile

import docx
from lxml import etree

CARPETA = os.path.dirname(os.path.abspath(__file__))
V14 = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v14.docx")
V13 = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v13.docx")
FIGS = os.path.join(CARPETA, "figuras")


def cargar(nombre):
    with open(os.path.join(CARPETA, nombre), encoding="utf-8") as fh:
        return json.load(fh)


cif = cargar("cifras_documento.json")
par = cargar("crs_parametros_v6.json")

fallos = []

# --- 1. Integridad del paquete ---------------------------------------------
print("=" * 74)
print("INTEGRIDAD")
print("=" * 74)
with zipfile.ZipFile(V14) as z:
    roto = z.testzip()
    xml = z.read("word/document.xml").decode("utf-8")
    partes = z.namelist()
    medios = {k: z.read(k) for k in partes if k.startswith("word/media/")}
etree.fromstring(xml.encode("utf-8"))
print(f"  zip: {'OK' if roto is None else 'CORRUPTO ' + str(roto)}")
print(f"  XML del cuerpo: bien formado")
if roto is not None:
    fallos.append("el paquete esta corrupto")

d = docx.Document(V14)
d13 = docx.Document(V13)
print(f"  parrafos {len(d.paragraphs)} (V13: {len(d13.paragraphs)})   "
      f"tablas {len(d.tables)} (V13: {len(d13.tables)})   "
      f"imagenes {len(medios)}")
if len(d.paragraphs) != len(d13.paragraphs) or len(d.tables) != len(d13.tables):
    fallos.append("ha cambiado el numero de parrafos o de tablas")
# El registro de revisiones debe haber crecido en las dos filas de esta revision
f11, f11_13 = len(d.tables[11].rows), len(d13.tables[11].rows)
print(f"  registro de revisiones: {f11} filas (V13: {f11_13})  "
      f"{'OK' if f11 == f11_13 + 3 else 'MAL'}")
if f11 != f11_13 + 3:
    fallos.append("el registro de revisiones no recoge las tres filas nuevas")

marcadores = len(set(re.findall(r'w:name="(ref_biblio_\d+)"', xml)))
campos = len(re.findall(r'w:instr="[^"]*\bREF\b', xml))
with zipfile.ZipFile(V13) as z:
    xml13 = z.read("word/document.xml").decode("utf-8")
m13 = len(set(re.findall(r'w:name="(ref_biblio_\d+)"', xml13)))
print(f"  marcadores de bibliografia {marcadores} (V13: {m13})   campos REF {campos}")
if marcadores != m13:
    fallos.append("se han perdido marcadores de bibliografia")

# --- 2. Imagenes ------------------------------------------------------------
print("\n" + "=" * 74)
print("IMAGENES")
print("=" * 74)
ESPERADAS = {
    "word/media/image17.png": "docfig10_perfiles_plano_amenazas.png",
    "word/media/image18.png": "docfig11_perfiles_criticidad.png",
    "word/media/image19.png": "fig7_riesgo_compuesto.png",
    "word/media/image20.png": "docfig13_sensibilidad_estabilidad.png",
    "word/media/image21.png": "docfig14_sensibilidad_solape.png",
    "word/media/image22.png": "docfig15_criticos_castellon.png",
    "word/media/image23.png": "docfig16_criticos_valencia.png",
    "word/media/image24.png": "docfig17_criticos_alicante.png",
    "word/media/image28.png": "docfig24_embudo.png",
    "word/media/image29.png": "docfig25_validacion_dana.png",
    "word/media/image31.png": "docfig27_objetivos.png",
}
for parte, fichero in ESPERADAS.items():
    with open(os.path.join(FIGS, fichero), "rb") as fh:
        esperado = fh.read()
    ok = medios.get(parte) == esperado
    print(f"  {'OK  ' if ok else 'MAL '} {parte:<26} = {fichero}")
    if not ok:
        fallos.append(f"{parte} no coincide con {fichero}")

with zipfile.ZipFile(V13) as z:
    previas = {k: z.read(k) for k in z.namelist() if k.startswith("word/media/")}
tocadas_de_mas = [k for k in previas
                  if k not in ESPERADAS and previas[k] != medios.get(k)]
print(f"  imagenes alteradas sin motivo: {len(tocadas_de_mas)} "
      f"{tocadas_de_mas if tocadas_de_mas else ''}")
if tocadas_de_mas:
    fallos.append("se han alterado imagenes que no debian cambiar")

# --- 3. Cifras del reparto anterior que no deben sobrevivir ----------------
print("\n" + "=" * 74)
print("CIFRAS DEL REPARTO ANTERIOR")
print("=" * 74)
todo = " ".join(p.text for p in d.paragraphs)
# El registro de revisiones (Tabla 11) queda fuera del rastreo: su columna "estado
# anterior" cita por definicion las cifras y las frases que se acaban de corregir,
# y contarlas como supervivientes seria un falso positivo.
todo += " " + " ".join(c.text for k, t in enumerate(d.tables) if k != 11
                       for f in t.rows for c in f.cells)
registro = " ".join(c.text for f in d.tables[11].rows for c in f.cells)
for hito in ("0,70", "diecinueve", "densidad de activos"):
    if hito not in registro:
        fallos.append(f"el registro de revisiones no menciona {hito!r}")
print("  (la Tabla 11, registro de revisiones, se excluye del rastreo porque "
      "cita el estado anterior; documenta los cambios: "
      f"{'OK' if all(h in registro for h in ('0,70', 'diecinueve')) else 'MAL'})")
todo = todo.replace(" ", " ")

# Cada patron va anclado para que no cace un numero mayor que lo contenga: sin el
# anclaje, "14 subestaciones" cazaba el "214 subestaciones" del perfil 6.
VIEJAS = ["79,83", "15,47", "24,12", "37,61", "20,83", "1.947",
          "66,94", " 8,65", "16,44", "18,97", "11,45", " 9,05", " 7,69", " 6,34",
          "0,60 para la inundación", "0,40 para el viento",
          "ellos 14 subestaciones", "11 de las 14", "de 388",
          "no baja del 70,6", "no inferior a 0,94", "70,6 %", "97,3 %",
          "veinticinco celdas", "siete de las quince", "nueve de las quince",
          "críticos, 1.203", "solo 31 activos por encima",
          "las quince subestaciones de mayor índice", "lista de quince",
          "apoyos de media en un radio de 5 kilómetros",
          "la mayor velocidad media de viento",
          "la mayor velocidad de viento del área de estudio"]
for v in VIEJAS:
    k = todo.count(v)
    print(f"  {v!r:<30} {k}  " + ("<-- SIGUE AHI" if k else "limpio"))
    if k:
        fallos.append(f"sobrevive la cifra antigua {v!r}")

# Estas dos cifras del reparto anterior SI deben sobrevivir, y un numero exacto de
# veces: son el efecto del cambio de variable a igualdad de pesos, que los
# apartados 5.4 y 7.2 citan para separarlo del efecto del reparto.
print()
for v, esperadas in (("48,3", 2), ("de 1 a 12", 1), ("27,4", 3)):
    k = todo.count(v)
    ok = k == esperadas
    print(f"  {v!r:<30} {k}  "
          + ("OK, es el efecto de la variable" if ok
             else f"<-- REVISAR, se esperaban {esperadas}"))
    if not ok:
        fallos.append(f"{v!r} aparece {k} veces y se esperaban {esperadas}")

# --- 4. Cifras nuevas que deben estar ---------------------------------------
print("\n" + "=" * 74)
print("CIFRAS NUEVAS")
print("=" * 74)
dist, res7 = cif["distribucion"], cif["tabla7"]["resumen"]
sc = cif["subest_criticas"]


def mildec(x, dd=2):
    e, _, dec = f"{x:,.{dd}f}".partition(".")
    return e.replace(",", ".") + "," + dec


def mil(x):
    return f"{int(x):,}".replace(",", ".")


NUEVAS = {
    "mediana del indice": mildec(dist["mediana"]),
    "maximo del indice": mildec(dist["maxima"]),
    "percentil 95": mildec(dist["p95"]),
    "percentil 99": mildec(dist["p99"]),
    "conjunto critico": mil(dist["n_top5"]),
    "activos del 1 % superior": mil(dist["n_top1"]),
    "subestaciones criticas": f"{sc['total']} subestaciones",
    "subestaciones en Valencia": f"{sc['Valencia']} de las {sc['total']}",
    "peso de la inundacion": "0,70 para la inundación",
    "peso del viento": "0,30 para el viento",
    "dominancia en el conjunto": "96,8 %",
    "dominancia en el 5 % superior": "42,0 %",
    "criticos de Castellon": mil(1135),
    "criticos de Valencia": mil(784),
    "criticos de Alicante": "38 activos por encima del umbral",
    "celdas del campo de extremos": f"{cif['celdas_v50_con_activos']} celdas",
    "Spearman minimo": "no inferior a 0,92",
    "solape minimo": "no baja del 65,2",
}
for etiqueta, v in NUEVAS.items():
    k = todo.count(v)
    print(f"  {'OK  ' if k else 'MAL '} {etiqueta:<32} {v!r} x{k}")
    if not k:
        fallos.append(f"falta la cifra nueva {etiqueta} ({v!r})")

# --- 5. Coherencia interna de las tablas -----------------------------------
print("\n" + "=" * 74)
print("COHERENCIA INTERNA DE LAS TABLAS")
print("=" * 74)


def num(s):
    s = s.strip().replace(" %", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


t7 = d.tables[7]
suma_bandas = sum(num(t7.rows[i].cells[5].text) for i in range(1, 6))
total7 = num(t7.rows[6].cells[5].text)
print(f"  Tabla 7: las cinco bandas suman {suma_bandas:.0f}, el total declara "
      f"{total7:.0f}  {'OK' if suma_bandas == total7 else 'MAL'}")
if suma_bandas != total7:
    fallos.append("las bandas de la Tabla 7 no suman el total")

for j, clase in enumerate(("Subest.", "Torres", "Postes", "Pórticos"), 1):
    s = sum(num(t7.rows[i].cells[j].text) for i in range(1, 6))
    t = num(t7.rows[6].cells[j].text)
    ok = s == t
    print(f"           {clase:<9} bandas {s:>7.0f}  total {t:>7.0f}  "
          f"{'OK' if ok else 'MAL'}")
    if not ok:
        fallos.append(f"la columna {clase} de la Tabla 7 no cuadra")

t8 = d.tables[8]
suma_prov = sum(num(t8.rows[i].cells[2].text) for i in range(1, 4))
total8 = num(t8.rows[4].cells[2].text)
print(f"  Tabla 8: las tres provincias suman {suma_prov:.0f} criticos, el total "
      f"declara {total8:.0f}  {'OK' if suma_prov == total8 else 'MAL'}")
if suma_prov != total8:
    fallos.append("los criticos de la Tabla 8 no suman el total")
sub8 = sum(num(t8.rows[i].cells[4].text) for i in range(1, 4))
print(f"           subestaciones criticas por provincia: {sub8:.0f}, "
      f"el conjunto de resultados dice {sc['total']}  "
      f"{'OK' if sub8 == sc['total'] else 'MAL'}")
if sub8 != sc["total"]:
    fallos.append("las subestaciones criticas de la Tabla 8 no cuadran")

# El 5 % superior de la Tabla 7 (p95-p99 mas el 1 % superior) y el conjunto
# critico de la Tabla 8 deben ser el mismo conjunto.
top5_t7 = num(t7.rows[4].cells[5].text) + num(t7.rows[5].cells[5].text)
print(f"  Tablas 7 y 8: 5 % superior segun la 7 = {top5_t7:.0f}, segun la 8 = "
      f"{total8:.0f}  {'OK' if top5_t7 == total8 else 'MAL'}")
if top5_t7 != total8:
    fallos.append("el 5 % superior no coincide entre las Tablas 7 y 8")

t9 = d.tables[9]
n9 = cif["tabla9_n"]
print(f"  Tabla 9: {len(t9.rows) - 1} filas, el conjunto critico de subestaciones "
      f"tiene {n9}  {'OK' if len(t9.rows) - 1 == n9 else 'MAL'}")
if len(t9.rows) - 1 != n9:
    fallos.append("la Tabla 9 no lista todas las subestaciones criticas")
crs9 = [num(t9.rows[i].cells[6].text) for i in range(1, n9 + 1)]
umbral9 = min(crs9)
print(f"  Tabla 9: el ultimo declara {umbral9:.2f} y el umbral es "
      f"{cif['distribucion']['p95']}  "
      f"{'OK' if umbral9 >= cif['distribucion']['p95'] else 'MAL'}")
if umbral9 < cif["distribucion"]["p95"]:
    fallos.append("la Tabla 9 incluye una subestacion por debajo del umbral")
ordenada = all(crs9[i] >= crs9[i + 1] for i in range(len(crs9) - 1))
print(f"  Tabla 9: las {n9} filas en orden decreciente de indice  "
      f"{'OK' if ordenada else 'MAL'}")
if not ordenada:
    fallos.append("la Tabla 9 no esta ordenada")
print(f"           el primero declara {crs9[0]:.2f} y el maximo del indice es "
      f"{dist['maxima']}  {'OK' if crs9[0] == dist['maxima'] else 'MAL'}")
if crs9[0] != dist["maxima"]:
    fallos.append("el primero de la Tabla 9 no es el maximo del indice")

t6 = d.tables[6]
med6 = [num(t6.rows[i].cells[5].text) for i in range(1, 8)]
ok6 = all(med6[i] >= med6[i + 1] for i in range(len(med6) - 1))
print(f"  Tabla 6: los siete perfiles en orden decreciente de indice mediano  "
      f"{'OK' if ok6 else 'MAL'}")
if not ok6:
    fallos.append("los perfiles de la Tabla 6 no estan ordenados")

# --- 6. Remisiones a figuras -----------------------------------------------
print("\n" + "=" * 74)
print("REMISIONES A FIGURAS")
print("=" * 74)
REMISIONES = ["Las Figuras 13 y 14 representan esa partición",
              "recogen las Figuras 16 y 17",
              "Las Figuras 18, 19 y 20 localizan",
              "recogida en las Figuras 21 y 22"]
for r in REMISIONES:
    k = todo.count(r)
    print(f"  {'OK  ' if k else 'MAL '} {r!r}")
    if not k:
        fallos.append(f"falta la remision corregida {r!r}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
if fallos:
    print(f"{len(fallos)} PROBLEMAS")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("SIN PROBLEMAS: la V14 es coherente con los ficheros de resultados")
