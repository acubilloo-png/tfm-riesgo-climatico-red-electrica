# ============================================================================
# 19_restaurar_campos_ref.py
# ----------------------------------------------------------------------------
# Devuelve a las citas del texto su condicion de referencia cruzada. Desde la V12
# el documento conserva los 36 marcadores de la bibliografia pero ha perdido los
# campos, de modo que los numeros entre corchetes son texto plano: si se inserta,
# elimina o reordena una entrada, las citas dejan de corresponder y no hay forma
# de que Word lo advierta.
#
# ORIGEN:  20260415_TFMAlvaroCubillo_v14.docx   (no se modifica)
# DESTINO: 20260415_TFMAlvaroCubillo_v15.docx
#
# ----------------------------------------------------------------------------
# EL MECANISMO, QUE NO SE INVENTA AQUI
# ----------------------------------------------------------------------------
# Se reproduce exactamente el que ya tuvo este documento en la version
# "_-_refcruzadas", verificado en ella: la bibliografia es una lista numerada
# (numId 8) y cada entrada lleva un marcador ref_biblio_NN, de modo que
#
#     <w:fldSimple w:instr=" REF ref_biblio_05 \r \h "><w:r><w:t>5</w:t></w:r></w:fldSimple>
#
# muestra el numero de la entrada marcada y lo recalcula con F9. El conmutador \r
# pide el numero de parrafo y \h lo convierte en hipervinculo. Los corchetes y las
# comas siguen siendo texto: el campo contiene solo el numero, igual que antes.
#
# ----------------------------------------------------------------------------
# QUE NO SE CONVIERTE, Y POR QUE
# ----------------------------------------------------------------------------
#   · Los intervalos matematicos [0, 1] y [0, 100] del 4.7 y de la Tabla 10. No
#     son citas; se distinguen porque contienen numeros fuera de 1..36.
#   · Las dos frases de plantilla de los anexos ("Numerar las citas de forma
#     consecutiva entre corchetes [1]"), que son instrucciones, no citas.
#   · Los indices automaticos de figuras y tablas, que Word regenera con F9 y
#     donde cualquier campo insertado a mano se perderia.
#   · La propia bibliografia.
# ============================================================================

import copy
import os
import re
import shutil
import zipfile

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

CARPETA = os.path.dirname(os.path.abspath(__file__))
ORIGEN = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v14.docx")
DESTINO = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v15.docx")

PATRON = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
FRASE_PLANTILLA = "Numerar las citas de forma consecutiva"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def texto_visible(ruta):
    """Todo el texto del cuerpo, incluido el que va dentro de un campo."""
    with zipfile.ZipFile(ruta) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    raiz = etree.fromstring(xml.encode("utf-8"))
    return "".join(t.text or "" for t in raiz.iter(f"{W}t"))


print(f"origen : {os.path.basename(ORIGEN)}")
print(f"destino: {os.path.basename(DESTINO)}")
antes = texto_visible(ORIGEN)
shutil.copy2(ORIGEN, DESTINO)
doc = docx.Document(DESTINO)

# ---------------------------------------------------------------------------
# 1. Inventario de marcadores: sin ellos no hay nada que referenciar
# ---------------------------------------------------------------------------
marcadores = {}
for i, p in enumerate(doc.paragraphs):
    for b in p._p.iter(qn("w:bookmarkStart")):
        nombre = b.get(qn("w:name")) or ""
        if not nombre.startswith("ref_biblio_"):
            continue
        numero = int(re.search(r"\d+", nombre).group())
        if numero in marcadores:
            raise SystemExit(f"marcador duplicado para la referencia {numero}")
        ppr = p._p.find(qn("w:pPr"))
        numerado = ppr is not None and ppr.find(qn("w:numPr")) is not None
        if not numerado:
            raise SystemExit(
                f"{nombre} esta en un parrafo sin numeracion automatica: el "
                "conmutador \\r no devolveria ningun numero")
        marcadores[numero] = nombre

N_REFS = len(marcadores)
faltan = [k for k in range(1, N_REFS + 1) if k not in marcadores]
if faltan:
    raise SystemExit(f"faltan marcadores para las referencias {faltan}")
print(f"  {N_REFS} marcadores, de ref_biblio_01 a {marcadores[N_REFS]}, "
      "todos en parrafos numerados")


# ---------------------------------------------------------------------------
# 2. Construccion de un campo
# ---------------------------------------------------------------------------
def campo(numero, rpr):
    """<w:fldSimple> con el numero ya calculado, para que se vea sin pulsar F9."""
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), f" REF {marcadores[numero]} \\r \\h ")
    r = OxmlElement("w:r")
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = OxmlElement("w:t")
    t.text = str(numero)
    r.append(t)
    fld.append(r)
    return fld


def run_texto(texto, rpr):
    r = OxmlElement("w:r")
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = OxmlElement("w:t")
    t.text = texto
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    return r


def texto_de(run_el):
    return "".join(t.text or "" for t in run_el.findall(qn("w:t")))


def poner_texto(run_el, texto):
    ts = run_el.findall(qn("w:t"))
    if not ts:
        nt = OxmlElement("w:t")
        run_el.append(nt)
        ts = [nt]
    ts[0].text = texto
    ts[0].set(qn("xml:space"), "preserve")
    for e in ts[1:]:
        e.text = ""


def es_cita(grupo):
    """Un grupo es cita si todos sus numeros son entradas de la bibliografia."""
    return all(1 <= int(x) <= N_REFS for x in re.findall(r"\d+", grupo))


def juntar_runs_partidos(p):
    """
    Si un grupo de cita queda repartido entre varios runs, se pasa su texto al
    primero y se vacian los demas. Sin esto, el grupo no se podria sustituir de
    una pieza. Se conserva el formato del primer run del tramo, que es lo unico
    que se puede conservar al fusionar.
    """
    cambios = 0
    while True:
        runs = [h for h in p if h.tag == qn("w:r")]
        if not runs:
            return cambios
        textos = [texto_de(r) for r in runs]
        completo = "".join(textos)
        objetivo = None
        for m in PATRON.finditer(completo):
            if not es_cita(m.group(1)):
                continue
            acc, ini_idx, fin_idx = 0, None, None
            for k, t in enumerate(textos):
                a, b = acc, acc + len(t)
                if ini_idx is None and b > m.start():
                    ini_idx = k
                if a < m.end():
                    fin_idx = k
                acc = b
            if ini_idx != fin_idx:
                objetivo = (ini_idx, fin_idx)
                break
        if objetivo is None:
            return cambios
        i0, i1 = objetivo
        poner_texto(runs[i0], "".join(textos[i0:i1 + 1]))
        for r in runs[i0 + 1:i1 + 1]:
            poner_texto(r, "")
        cambios += 1


def convertir(p, etiqueta):
    """Sustituye en el parrafo cada grupo de cita por corchetes mas campos."""
    global n_campos, n_grupos
    texto_p = p_text(p)
    if FRASE_PLANTILLA in texto_p:
        return 0
    if not any(es_cita(m.group(1)) for m in PATRON.finditer(texto_p)):
        return 0
    juntar_runs_partidos(p)

    hechos = 0
    for run_el in [h for h in p if h.tag == qn("w:r")]:
        t = texto_de(run_el)
        if not t or not any(es_cita(m.group(1)) for m in PATRON.finditer(t)):
            continue
        rpr = run_el.find(qn("w:rPr"))
        nodos, cursor = [], 0
        for m in PATRON.finditer(t):
            if not es_cita(m.group(1)):
                continue
            if m.start() > cursor:
                nodos.append(run_texto(t[cursor:m.start()], rpr))
            partes = re.split(r"(\s*,\s*)", m.group(1))
            nodos.append(run_texto("[", rpr))
            for parte in partes:
                if parte.strip().isdigit():
                    nodos.append(campo(int(parte.strip()), rpr))
                    n_campos += 1
                else:
                    nodos.append(run_texto(parte, rpr))
            nodos.append(run_texto("]", rpr))
            n_grupos += 1
            hechos += 1
            cursor = m.end()
        if cursor < len(t):
            nodos.append(run_texto(t[cursor:], rpr))
        idx = list(p).index(run_el)
        for k, nodo in enumerate(nodos):
            p.insert(idx + k, nodo)
        p.remove(run_el)
    if hechos:
        print(f"  {etiqueta}: {hechos} grupo(s)")
    return hechos


def p_text(p):
    return "".join(texto_de(h) for h in p if h.tag == qn("w:r"))


# ---------------------------------------------------------------------------
# 3. Recorrido del documento
# ---------------------------------------------------------------------------
print("\nconvirtiendo las citas del cuerpo...")
n_campos = n_grupos = 0
omitidos = {"indice automatico": 0, "bibliografia": 0, "plantilla": 0}

for i, par in enumerate(doc.paragraphs):
    estilo = par.style.name if par.style is not None else ""
    texto = par.text
    if not PATRON.search(texto):
        continue
    if estilo.lower().startswith("toc"):
        omitidos["indice automatico"] += 1
        continue
    if estilo.startswith("Referencias"):
        omitidos["bibliografia"] += 1
        continue
    if FRASE_PLANTILLA in texto:
        omitidos["plantilla"] += 1
        continue
    convertir(par._p, f"p{i:03d}")

print("\nconvirtiendo las citas de las tablas...")
for k, t in enumerate(doc.tables):
    for fi, fila in enumerate(t.rows):
        for ci, celda in enumerate(fila.cells):
            for par in celda.paragraphs:
                if PATRON.search(par.text):
                    convertir(par._p, f"T{k} f{fi} c{ci}")

print(f"\n{n_grupos} grupos convertidos, {n_campos} campos REF insertados")
print("omitidos deliberadamente: " +
      ", ".join(f"{v} en {k}" for k, v in omitidos.items() if v))

doc.save(DESTINO)

# ---------------------------------------------------------------------------
# 4. Comprobacion: el texto visible no puede haber cambiado ni un caracter
# ---------------------------------------------------------------------------
print("\n=== COMPROBACION ===")
despues = texto_visible(DESTINO)
if antes == despues:
    print(f"  el texto visible es identico ({len(antes)} caracteres)")
else:
    print(f"  CAMBIO EL TEXTO: {len(antes)} -> {len(despues)} caracteres")
    for k in range(min(len(antes), len(despues))):
        if antes[k] != despues[k]:
            print(f"    primera diferencia en el caracter {k}:")
            print(f"      antes  : ...{antes[max(0, k - 70):k + 70]}...")
            print(f"      despues: ...{despues[max(0, k - 70):k + 70]}...")
            break
    raise SystemExit(1)

with zipfile.ZipFile(DESTINO) as z:
    if z.testzip() is not None:
        raise SystemExit("el paquete quedo corrupto")
    xml = z.read("word/document.xml").decode("utf-8")
etree.fromstring(xml.encode("utf-8"))
campos = re.findall(r'w:instr=" REF (ref_biblio_\d+) \\r \\h "', xml)
print(f"  campos REF en el paquete: {len(campos)}")
print(f"  referencias distintas referenciadas: {len(set(campos))} de {N_REFS}")
sin_usar = sorted(set(marcadores.values()) - set(campos))
if sin_usar:
    print(f"  marcadores sin ninguna cita que los use: {len(sin_usar)} "
          f"{sin_usar}")
huerfanos = sorted(set(campos) - set(marcadores.values()))
if huerfanos:
    print(f"  CAMPOS QUE APUNTAN A UN MARCADOR INEXISTENTE: {huerfanos}")
    raise SystemExit(1)
print(f"  marcadores conservados: "
      f"{len(set(re.findall(r'w:name=.(ref_biblio_\d+)', xml)))}")

d2 = docx.Document(DESTINO)
print(f"  parrafos {len(d2.paragraphs)}   tablas {len(d2.tables)}   "
      f"formas {len(d2.inline_shapes)}")

# ---------------------------------------------------------------------------
# 5. El registro de revisiones, en un paso aparte
# ---------------------------------------------------------------------------
# Va despues de la comprobacion a proposito: anadir la fila cambia el texto
# visible del documento, y si se hiciera antes invalidaria la unica prueba que
# garantiza que la conversion de las citas no ha tocado ni un caracter.
print("\n=== REGISTRO DE REVISIONES ===")
t_reg = d2.tables[11]
t_reg._tbl.append(copy.deepcopy(t_reg.rows[-1]._tr))
fila = t_reg.rows[-1]
FILA = (
    "Citas bibliográficas de todo el documento",
    "Los números entre corchetes eran texto plano: la revisión que produjo la V12 "
    "perdió los campos de referencia cruzada y conservó solo los 36 marcadores, de "
    "modo que insertar o reordenar una entrada descuadraba las citas sin que Word "
    "pudiera advertirlo",
    f"Restaurados {n_campos} campos REF sobre los marcadores existentes, uno por "
    f"número citado en los {n_grupos} grupos de cita, con los conmutadores de "
    "número de párrafo e hipervínculo; quedan fuera los intervalos matemáticos "
    "[0, 1] y [0, 100], las dos frases de plantilla de los anexos y los índices "
    "automáticos  [v9]")
for j, texto in enumerate(FILA):
    c = fila.cells[j]
    for extra in c.paragraphs[1:]:
        for r in extra.runs:
            r.text = ""
    par = c.paragraphs[0]
    runs = par.runs if par.runs else [par.add_run()]
    runs[0].text = texto
    for r in runs[1:]:
        r.text = ""
d2.save(DESTINO)
print(f"  fila anadida: el registro tiene ahora {len(t_reg.rows)} filas")

# Ultima comprobacion tras el anadido
with zipfile.ZipFile(DESTINO) as z:
    if z.testzip() is not None:
        raise SystemExit("el paquete quedo corrupto al anadir la fila")
    xml = z.read("word/document.xml").decode("utf-8")
etree.fromstring(xml.encode("utf-8"))
n_final = len(re.findall(r'w:instr=" REF ref_biblio_\d+ \\r \\h "', xml))
print(f"  campos REF tras guardar: {n_final}  "
      f"{'OK' if n_final == n_campos else 'MAL'}")
if n_final != n_campos:
    raise SystemExit("se han perdido campos al anadir la fila")

print(f"\nGuardado: {os.path.basename(DESTINO)}")
print("Abre el documento y pulsa Ctrl+A y F9 para que Word recalcule los campos.")
