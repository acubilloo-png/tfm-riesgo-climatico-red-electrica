# ============================================================================
# 21_autoria_del_texto.py
# ----------------------------------------------------------------------------
# Mide, parrafo a parrafo, que parte del texto del draft actual venia del
# documento anterior a mi intervencion y que parte he redactado yo. No se apoya
# en mi recuerdo ni en el registro de revisiones: compara los textos.
#
# BASE:    old/20260415_TFMAlvaroCubillo_-_revRSAR (2).docx
#          la version revisada por el director, 315 parrafos, 7 tablas, 22 refs
# ACTUAL:  20260817_TFMAlvaroCubillo_draftRicardo.docx
#          469 parrafos, 11 tablas, 36 refs
#
# Cada parrafo del documento actual se empareja con el mas parecido de la base y
# se clasifica por su semejanza:
#
#   TUYO        semejanza 1,00      el parrafo esta igual que lo escribiste
#   RETOCADO    semejanza >= 0,85   cambios menores: cifras, una frase
#   MIXTO       semejanza >= 0,55   reescrito sobre tu texto
#   MIO         semejanza <  0,55   no existia: lo he redactado yo
#
# LIMITE QUE CONVIENE TENER PRESENTE: esto mide de quien es la REDACCION, no de
# quien son las ideas ni los resultados. Los datos, los calculos, las decisiones
# metodologicas y los hallazgos son tuyos; lo que aqui se cuenta son palabras.
# ============================================================================

import difflib
import os
import re

import docx

CARPETA = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(CARPETA, "old",
                    "20260415_TFMAlvaroCubillo_-_revRSAR (2).docx")
ACTUAL = os.path.join(CARPETA, "20260817_TFMAlvaroCubillo_draftRicardo.docx")
SALIDA = os.path.join(CARPETA, "AUTORIA.md")

UMBRALES = [(1.00, "TUYO"), (0.85, "RETOCADO"), (0.55, "MIXTO"), (0.0, "MIO")]


def normalizar(t):
    return re.sub(r"\s+", " ", t).strip().lower()


def parrafos(ruta):
    d = docx.Document(ruta)
    salida = []
    for i, p in enumerate(d.paragraphs):
        t = p.text.strip()
        if not t:
            continue
        estilo = p.style.name if p.style is not None else ""
        salida.append({"i": i, "estilo": estilo, "texto": t,
                       "norm": normalizar(t),
                       "palabras": len(t.split())})
    return d, salida


d_base, base = parrafos(BASE)
d_act, actual = parrafos(ACTUAL)
print(f"base   : {len(base)} parrafos con texto")
print(f"actual : {len(actual)} parrafos con texto")

# Los indices automaticos y la plantilla de los anexos no son prosa de nadie
def es_prosa(p):
    e = p["estilo"].lower()
    if e.startswith(("toc", "referencias")):
        return False
    if e.startswith(("heading", "titulo", "tit")):
        return False
    return True


# ---------------------------------------------------------------------------
# Emparejamiento
# ---------------------------------------------------------------------------
print("\nemparejando...")
normas_base = [p["norm"] for p in base]
for p in actual:
    mejor, mejor_r = None, 0.0
    s = difflib.SequenceMatcher()
    s.set_seq2(p["norm"])
    for k, nb in enumerate(normas_base):
        s.set_seq1(nb)
        if s.real_quick_ratio() < mejor_r or s.quick_ratio() < mejor_r:
            continue
        r = s.ratio()
        if r > mejor_r:
            mejor, mejor_r = k, r
    p["r"] = mejor_r
    p["base_i"] = base[mejor]["i"] if mejor is not None else None
    for umbral, etiqueta in UMBRALES:
        if mejor_r >= umbral:
            p["clase"] = etiqueta
            break

# ---------------------------------------------------------------------------
# Estructura: a que apartado pertenece cada parrafo
# ---------------------------------------------------------------------------
d_titulos = docx.Document(ACTUAL)
titulo_de, capitulo_de = {}, {}
actual_titulo = "(portada y preliminares)"
actual_cap = "(portada y preliminares)"
for i, p in enumerate(d_titulos.paragraphs):
    e = (p.style.name if p.style is not None else "").lower()
    t = p.text.strip()
    if t and e.startswith(("heading", "titulo")) and not e.startswith("toc"):
        actual_titulo = t
        # Heading 1 marca capitulo; el resto son apartados dentro de el
        if e in ("heading 1", "titulo 1", "título 1"):
            actual_cap = t
    titulo_de[i] = actual_titulo
    capitulo_de[i] = actual_cap
for p in actual:
    p["apartado"] = titulo_de.get(p["i"], "(sin apartado)")
    p["capitulo"] = capitulo_de.get(p["i"], "(sin capitulo)")

# ---------------------------------------------------------------------------
# Recuento
# ---------------------------------------------------------------------------
prosa = [p for p in actual if es_prosa(p)]
total_pal = sum(p["palabras"] for p in prosa)
print("\n" + "=" * 78)
print("RECUENTO SOBRE LA PROSA (sin titulos, indices ni bibliografia)")
print("=" * 78)
print(f"{'clase':<10} {'parrafos':>9} {'palabras':>10} {'% palabras':>11}")
resumen = {}
for _, etiqueta in UMBRALES:
    sel = [p for p in prosa if p["clase"] == etiqueta]
    pal = sum(p["palabras"] for p in sel)
    resumen[etiqueta] = (len(sel), pal)
    print(f"{etiqueta:<10} {len(sel):>9} {pal:>10} "
          f"{100 * pal / total_pal:>10.1f} %")
print(f"{'TOTAL':<10} {len(prosa):>9} {total_pal:>10}")

# ---------------------------------------------------------------------------
# Desglose por capitulo, que es la lectura que importa
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("DESGLOSE POR CAPITULO")
print("=" * 78)
orden_cap, vistos_cap = [], set()
for p in prosa:
    if p["capitulo"] not in vistos_cap:
        vistos_cap.add(p["capitulo"])
        orden_cap.append(p["capitulo"])
caps = []
for cap in orden_cap:
    sel = [p for p in prosa if p["capitulo"] == cap]
    pal = sum(p["palabras"] for p in sel)
    d = {e: sum(p["palabras"] for p in sel if p["clase"] == e)
         for _, e in UMBRALES}
    caps.append({"cap": cap, "parrafos": len(sel), "palabras": pal, **d,
                 "pct_mio": 100 * d["MIO"] / pal if pal else 0,
                 "pct_tuyo": 100 * (d["TUYO"] + d["RETOCADO"]) / pal if pal else 0})
    print(f"  {cap[:46]:<46} {len(sel):>3} parr {pal:>6} pal  "
          f"mio {d['MIO'] / pal * 100 if pal else 0:>5.1f} %  "
          f"tuyo {(d['TUYO'] + d['RETOCADO']) / pal * 100 if pal else 0:>5.1f} %")

print("\n" + "=" * 78)
print("DESGLOSE POR APARTADO")
print("=" * 78)
orden, vistos = [], set()
for p in prosa:
    if p["apartado"] not in vistos:
        vistos.add(p["apartado"])
        orden.append(p["apartado"])

filas = []
for ap in orden:
    sel = [p for p in prosa if p["apartado"] == ap]
    pal = sum(p["palabras"] for p in sel)
    mio = sum(p["palabras"] for p in sel if p["clase"] == "MIO")
    mixto = sum(p["palabras"] for p in sel if p["clase"] == "MIXTO")
    tuyo = sum(p["palabras"] for p in sel if p["clase"] == "TUYO")
    retoc = sum(p["palabras"] for p in sel if p["clase"] == "RETOCADO")
    filas.append({"apartado": ap, "parrafos": len(sel), "palabras": pal,
                  "mio": mio, "mixto": mixto, "retocado": retoc, "tuyo": tuyo,
                  "pct_mio": 100 * mio / pal if pal else 0,
                  "indices_mios": [p["i"] for p in sel if p["clase"] == "MIO"],
                  "indices_mixtos": [p["i"] for p in sel if p["clase"] == "MIXTO"]})
    print(f"  {ap[:54]:<54} {len(sel):>3} parr  {pal:>5} pal  "
          f"mio {100 * mio / pal if pal else 0:>5.1f} %")

# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------
def tabla(cabeceras, filas_txt):
    out = ["| " + " | ".join(cabeceras) + " |",
           "|" + "|".join("---" if k == 0 else "---:"
                          for k in range(len(cabeceras))) + "|"]
    out += ["| " + " | ".join(str(c) for c in f) + " |" for f in filas_txt]
    return "\n".join(out)


n_tab_base, n_tab_act = len(d_base.tables), len(d_act.tables)
n_img_base, n_img_act = len(d_base.inline_shapes), len(d_act.inline_shapes)

lineas = [
    "# Autoría del texto de la memoria",
    "",
    "Medido, no recordado: cada párrafo del draft actual se ha emparejado con el",
    "más parecido de la versión que revisó el director "
    "(`old/20260415_TFMAlvaroCubillo_-_revRSAR (2).docx`, 315 párrafos, "
    f"{n_tab_base} tablas, 22 referencias) y se ha clasificado por su semejanza.",
    "",
    "| Clase | Criterio | Qué significa |",
    "|---|---|---|",
    "| **TUYO** | semejanza 1,00 | el párrafo sigue tal como lo escribiste |",
    "| **RETOCADO** | ≥ 0,85 | cambios menores: cifras, una frase |",
    "| **MIXTO** | ≥ 0,55 | reescrito sobre tu texto |",
    "| **MÍO** | < 0,55 | no existía: lo he redactado yo |",
    "",
    "**Lo que esto mide y lo que no.** Mide de quién es la *redacción*. No mide de",
    "quién son las ideas, los datos ni los resultados: el descarte de la variante",
    "escalada, el reparto de pesos, la validación contra la DANA, la corrección del",
    "área de consulta y todo el análisis son tuyos. Lo que se cuenta aquí son",
    "palabras.",
    "",
    "## Resumen",
    "",
    tabla(["Clase", "Párrafos", "Palabras", "% de las palabras"],
          [[e, resumen[e][0], resumen[e][1],
            f"{100 * resumen[e][1] / total_pal:.1f} %"]
           for _, e in UMBRALES]
          + [["**TOTAL**", len(prosa), total_pal, "100,0 %"]]),
    "",
    f"Además: las tablas pasaron de {n_tab_base} a {n_tab_act} y las figuras "
    f"insertadas de {n_img_base} a {n_img_act}. Las Tablas 5 a 11 y las Figuras 6",
    "a 27, con sus pies, son mías, generadas desde tus datos.",
    "",
    "## Por capítulo",
    "",
    tabla(["Capítulo", "Párr.", "Palabras", "Tuyo o retocado", "Mío"],
          [[c["cap"][:46], c["parrafos"], c["palabras"],
            f"{c['pct_tuyo']:.0f} %", f"**{c['pct_mio']:.0f} %**"]
           for c in caps]),
    "",
    "El capítulo 7 absorbe en este recuento los anexos y los restos de plantilla,",
    "porque sus encabezados no usan estilo de título; su cifra está inflada por",
    "fragmentos que no son prosa de nadie.",
    "",
    "## Por apartado",
    "",
    "Ordenado como aparece en el documento. La última columna da los índices de",
    "párrafo (contando desde 0, como los numera Word internamente) para que puedas",
    "localizarlos.",
    "",
    tabla(["Apartado", "Párr.", "Palabras", "% mío", "Míos", "Mixtos"],
          [[f["apartado"][:48], f["parrafos"], f["palabras"],
            f"{f['pct_mio']:.0f} %",
            ", ".join(str(x) for x in f["indices_mios"][:14])
            + (" …" if len(f["indices_mios"]) > 14 else ""),
            ", ".join(str(x) for x in f["indices_mixtos"][:8])
            + (" …" if len(f["indices_mixtos"]) > 8 else "")]
           for f in filas]),
    "",
    "## Los párrafos que siguen siendo enteramente tuyos",
    "",
]
tuyos = [p for p in prosa if p["clase"] == "TUYO"]
if tuyos:
    for p in tuyos:
        lineas.append(f"- **[p{p['i']}]** ({p['apartado'][:40]}) "
                      f"{p['texto'][:150]}…")
else:
    lineas.append("Ninguno conserva la redacción literal original.")

lineas += ["", "## Los párrafos más extensos que he redactado yo", ""]
mios = sorted([p for p in prosa if p["clase"] == "MIO"],
              key=lambda p: -p["palabras"])[:25]
for p in mios:
    lineas.append(f"- **[p{p['i']}]** {p['palabras']} palabras "
                  f"({p['apartado'][:40]}) — {p['texto'][:120]}…")

with open(SALIDA, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lineas) + "\n")
print(f"\nEscrito: {os.path.basename(SALIDA)}")
