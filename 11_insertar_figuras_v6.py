# ============================================================================
# 11_insertar_figuras_v6.py
# ----------------------------------------------------------------------------
# Sustituye en el documento las nueve figuras que la version V6 deja obsoletas.
#
# ----------------------------------------------------------------------------
# METODO Y POR QUE ESTE
# ----------------------------------------------------------------------------
# No se borra ni se vuelve a insertar la imagen: se SUSTITUYEN LOS BYTES de la
# parte del paquete que la contiene. Asi se conservan intactos la posicion en el
# flujo del documento, el anclaje, el ajuste de texto y el pie de figura, que es
# justo lo que se rompe al reinsertar.
#
# El unico riesgo del metodo es la proporcion: Word guarda el tamano de la imagen
# en el XML (wp:extent y a:ext), de modo que si la nueva tiene otra relacion de
# aspecto se estiraria. Por eso se recalcula la altura conservando la anchura
# original, con lo que la figura mantiene su ancho de columna y no se deforma.
#
# La correspondencia figura-imagen no se supone: se recorre el cuerpo del
# documento en orden, y cada pie que empieza por "Figura N." se asocia con la
# ultima imagen encontrada antes de el.
# ============================================================================

import os
import re
import shutil
import zipfile

import docx
from docx.oxml.ns import qn
from PIL import Image

CARPETA = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v6.docx")
RESPALDO = os.path.join(CARPETA, "20260415_TFMAlvaroCubillo_v6_antes_figuras.docx")
FIGS = os.path.join(CARPETA, "figuras")

# Figura del documento -> fichero nuevo
SUSTITUCIONES = {
    9: "fig4_viento.png",
    10: "docfig10_perfiles_plano_amenazas.png",
    11: "docfig11_perfiles_criticidad.png",
    12: "fig7_riesgo_compuesto.png",
    13: "docfig13_sensibilidad_estabilidad.png",
    14: "docfig14_sensibilidad_solape.png",
    15: "docfig15_criticos_castellon.png",
    16: "docfig16_criticos_valencia.png",
    17: "docfig17_criticos_alicante.png",
}

for f in SUSTITUCIONES.values():
    if not os.path.exists(os.path.join(FIGS, f)):
        raise SystemExit(f"falta la figura {f}")

print(f"respaldo: {os.path.basename(RESPALDO)}")
shutil.copy2(DOC, RESPALDO)

# ---------------------------------------------------------------------------
# 1. Correspondencia figura -> imagen, recorriendo el cuerpo en orden
# ---------------------------------------------------------------------------
doc = docx.Document(DOC)
cuerpo = doc.element.body

PATRON = re.compile(r"^Figura\s+(\d+)\.")
ultimo_blip = None
mapa = {}          # numero de figura -> (rId, elemento a:blip, elemento pic)

for elemento in cuerpo.iter():
    etiqueta = elemento.tag.split("}")[-1]
    if etiqueta == "blip":
        rid = elemento.get(qn("r:embed"))
        if rid:
            ultimo_blip = (rid, elemento)
    elif etiqueta == "p":
        texto = "".join(t.text or "" for t in elemento.iter(qn("w:t"))).strip()
        m = PATRON.match(texto)
        if m and ultimo_blip is not None:
            numero = int(m.group(1))
            if numero not in mapa:
                mapa[numero] = ultimo_blip

print(f"\nfiguras con imagen localizada: {sorted(mapa)}")
faltan = [k for k in SUSTITUCIONES if k not in mapa]
if faltan:
    raise SystemExit(f"ABORTADO: no se localizo la imagen de las figuras {faltan}")

# ---------------------------------------------------------------------------
# 2. Ajustar la extension para conservar la proporcion nueva
# ---------------------------------------------------------------------------
print("\n=== AJUSTE DE PROPORCION ===")
partes_a_sustituir = {}       # nombre en el paquete -> bytes nuevos

for numero, fichero in sorted(SUSTITUCIONES.items()):
    rid, blip = mapa[numero]
    parte = doc.part.related_parts[rid]
    nombre_paquete = str(parte.partname).lstrip("/")

    ruta_nueva = os.path.join(FIGS, fichero)
    with Image.open(ruta_nueva) as im:
        w_new, h_new = im.size
    with Image.open(ruta_nueva) as _:
        pass
    with open(ruta_nueva, "rb") as fh:
        partes_a_sustituir[nombre_paquete] = fh.read()

    # El <a:blip> vive dentro de <pic:pic>, que a su vez esta bajo <wp:inline> o
    # <wp:anchor>. Se suben niveles hasta encontrar el contenedor con la extension.
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

    if not extents:
        print(f"  Figura {numero}: sin extension declarada, se deja como esta")
        continue

    cx = int(extents[0].get("cx"))
    cy_viejo = int(extents[0].get("cy"))
    cy_nuevo = int(round(cx * h_new / w_new))
    for e in extents:
        e.set("cx", str(cx))
        e.set("cy", str(cy_nuevo))

    cambio = 100 * (cy_nuevo - cy_viejo) / cy_viejo
    print(f"  Figura {numero:>2} <- {fichero[:42]:<42} "
          f"alto {cy_viejo} -> {cy_nuevo} ({cambio:+.1f} %)")

doc.save(DOC)
print("\nextensiones actualizadas y documento guardado")

# ---------------------------------------------------------------------------
# 3. Sustituir los bytes de las imagenes en el paquete
# ---------------------------------------------------------------------------
print("\n=== SUSTITUCION DE LAS IMAGENES EN EL PAQUETE ===")
temporal = DOC + ".tmp"
sustituidas = 0
with zipfile.ZipFile(DOC, "r") as origen:
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as destino:
        for info in origen.infolist():
            datos = origen.read(info.filename)
            if info.filename in partes_a_sustituir:
                datos = partes_a_sustituir[info.filename]
                sustituidas += 1
                print(f"  {info.filename}: "
                      f"{len(origen.read(info.filename)) / 1024:.0f} KB -> "
                      f"{len(datos) / 1024:.0f} KB")
            destino.writestr(info, datos)

os.replace(temporal, DOC)
print(f"\n{sustituidas} imagenes sustituidas de {len(partes_a_sustituir)} previstas")
if sustituidas != len(partes_a_sustituir):
    print("  AVISO: alguna parte no se encontro en el paquete")
print(f"Guardado: {os.path.basename(DOC)}")
