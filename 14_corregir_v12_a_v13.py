# ============================================================================
# 14_corregir_v12_a_v13.py
# ----------------------------------------------------------------------------
# Corrige en la memoria las cifras de la comprobacion frente al episodio de
# octubre de 2024, que procedian de una variante descartada del campo de
# extremos, y sustituye la Figura 25 en consecuencia.
#
# ORIGEN:  20260415_TFMAlvaroCubillo_v12_coherencia (1).docx   (no se modifica)
# DESTINO: 20260415_TFMAlvaroCubillo_v13.docx
#
# ----------------------------------------------------------------------------
# QUE ESTABA MAL Y POR QUE
# ----------------------------------------------------------------------------
# El texto de los apartados 5.8 y 6, y la Figura 25, daban 73 de 1.012 activos
# para Quart de Poblet y 3 de 149 para Catadau. Esas cifras corresponden a la
# variante ESCALADA del campo de velocidad de retorno, que el propio trabajo
# descarta en el apartado 4.7 por implicar rachas superiores a la maxima jamas
# registrada en el territorio.
#
# El origen del error fue de proceso, no de calculo: la ejecucion que debia
# regenerar validacion_dana.json con la variante adoptada se interrumpio antes de
# escribir el fichero, de modo que el JSON conservo los valores antiguos y de ahi
# pasaron al texto y a la figura. El fichero ya esta regenerado.
#
# Cifras correctas con la variante adoptada:
#   Quart de Poblet   71 -> 115 de 1.012   percentil medio 68,1 -> 78,3
#   Catadau            0 ->   0 de 149     percentil medio 45,8 -> 45,2
#
# La correccion refuerza el argumento en las dos ramas: el acierto sobre la
# inundacion es mayor del que se afirmaba, y el fallo sobre el viento es total en
# lugar de parcial, lo que hace mas nitida la conclusion sobre el caracter
# convectivo del episodio.
# ============================================================================

import json
import os
import shutil
import zipfile

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

CARPETA = os.path.dirname(os.path.abspath(__file__))
ORIGEN = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v12_coherencia (1).docx")
DESTINO = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v13.docx")
FIG_NUEVA = os.path.join(CARPETA, "figuras", "docfig25_validacion_dana.png")
PARTE_FIG25 = "word/media/image29.png"      # identificada en la auditoria

with open(os.path.join(CARPETA, "validacion_dana.json"), encoding="utf-8") as fh:
    dana = json.load(fh)
q = dana["entornos"]["Quart de Poblet"]
c = dana["entornos"]["Catadau"]


def n(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


print(f"origen : {os.path.basename(ORIGEN)}")
print(f"destino: {os.path.basename(DESTINO)}")
shutil.copy2(ORIGEN, DESTINO)
doc = docx.Document(DESTINO)

errores, hechas = [], 0


def sust(viejo, nuevo, etiqueta):
    """
    Sustituye texto en el parrafo donde aparezca, aunque este repartido entre
    varios runs. Aborta si el tramo atraviesa un campo, para no romper una
    referencia cruzada.
    """
    global hechas
    for p in doc.paragraphs:
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
            continue
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
            errores.append(f"[{etiqueta}] atraviesa un campo REF")
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
        return
    errores.append(f"[{etiqueta}] no encontrado")
    print(f"  FALLO [{etiqueta}]")


# ---------------------------------------------------------------------------
print("\n=== APARTADO 5.8 ===")
sust("los que se sitúan en el 5 % de mayor riesgo pasan de 71 a 73, y el "
     "percentil medio del entorno sube de 68,1 a 69,1",
     f"los que se sitúan en el 5 % de mayor riesgo pasan de "
     f"{q['antes']['n_en_top5pct']} a {q['despues']['n_en_top5pct']}, es decir, del "
     f"{n(q['antes']['pct_en_top5pct'])} al {n(q['despues']['pct_en_top5pct'])} % "
     f"del entorno, y el percentil medio sube de "
     f"{n(q['antes']['CRS_percentil_medio'])} a "
     f"{n(q['despues']['CRS_percentil_medio'])}",
     "5.8 cifras de Quart de Poblet")

sust("pero el número de activos que alcanzan el 5 % de mayor riesgo se mantiene "
     "en 3 de 149",
     f"pero ninguno de sus {c['n_activos']} activos alcanza el 5 % de mayor "
     "riesgo, exactamente igual que con la variable anterior",
     "5.8 cifras de Catadau")

print("\n=== CAPITULO 6 ===")
sust("el entorno de la subestación anegada de Quart de Poblet queda en el "
     "percentil 69 y aporta 73 de sus 1.012 activos al 5 % de mayor riesgo",
     f"el entorno de la subestación anegada de Quart de Poblet queda en el "
     f"percentil {n(q['despues']['CRS_percentil_medio'], 0)} y aporta "
     f"{q['despues']['n_en_top5pct']} de sus 1.012 activos al 5 % de mayor riesgo",
     "6 cifras de Quart de Poblet")

sust("el entorno de Catadau, donde el viento derribó más de veinte apoyos, apenas "
     "mejora al cambiar de variable y sigue aportando 3 activos de 149",
     "el entorno de Catadau, donde el viento derribó más de veinte apoyos, no "
     f"mejora al cambiar de variable y no aporta ninguno de sus {c['n_activos']} "
     "activos",
     "6 cifras de Catadau")

if errores:
    print(f"\n{len(errores)} problemas, NO se guarda:")
    for e in errores:
        print(f"  - {e}")
    raise SystemExit(1)

doc.save(DESTINO)
print(f"\n{hechas} sustituciones de texto aplicadas")

# ---------------------------------------------------------------------------
# Sustitucion de la imagen de la Figura 25
# ---------------------------------------------------------------------------
print("\n=== FIGURA 25 ===")
# Se ajusta la extension para conservar la proporcion de la imagen nueva
doc = docx.Document(DESTINO)
with Image.open(FIG_NUEVA) as im:
    w_new, h_new = im.size

objetivo = None
for rid, parte in doc.part.related_parts.items():
    if str(parte.partname).lstrip("/") == PARTE_FIG25:
        objetivo = rid
        break
if objetivo is None:
    raise SystemExit(f"no se localizo la parte {PARTE_FIG25}")

ajustadas = 0
for blip in doc.element.body.iter(qn("a:blip")):
    if blip.get(qn("r:embed")) != objetivo:
        continue
    nodo = blip
    extents = []
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
        ajustadas += 1
        print(f"  proporcion ajustada: alto {cy_viejo} -> {cy_nuevo} "
              f"({100 * (cy_nuevo - cy_viejo) / cy_viejo:+.1f} %)")
doc.save(DESTINO)

with open(FIG_NUEVA, "rb") as fh:
    bytes_nuevos = fh.read()
temporal = DESTINO + ".tmp"
with zipfile.ZipFile(DESTINO, "r") as origen:
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as destino:
        for info in origen.infolist():
            datos = origen.read(info.filename)
            if info.filename == PARTE_FIG25:
                print(f"  {info.filename}: {len(datos) / 1024:.0f} KB -> "
                      f"{len(bytes_nuevos) / 1024:.0f} KB")
                datos = bytes_nuevos
            destino.writestr(info, datos)
os.replace(temporal, DESTINO)

print(f"\nGuardado: {os.path.basename(DESTINO)}")
