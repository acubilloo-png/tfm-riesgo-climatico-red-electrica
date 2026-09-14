# ============================================================================
# DownloadApoyosElectricosInfo.py — versión COMENTADA y con el ÁREA CORREGIDA
# ----------------------------------------------------------------------------
# Qué hace este script, en una frase:
#   Descarga de OpenStreetMap (vía API Overpass) todos los apoyos de línea
#   eléctrica (postes, torres, pórticos y soportes) dentro de un rectángulo
#   geográfico, y los guarda en un CSV listo para abrir con Excel en español.
#
# HISTORIAL DE CORRECCIONES DEL ÁREA DE CONSULTA
#
#   1ª versión: (39.0, -0.6, 40.0, 0.2)
#      Cubría solo Castellón y parte de Valencia, dejando fuera la totalidad de
#      la provincia de Alicante. Detectado al comparar con el script de
#      subestaciones. Devolvía 12.970 apoyos.
#
#   2ª versión: (38.0, -0.6, 40.4, 0.8)
#      Se copió el rectángulo del script de subestaciones, suponiendo que aquel
#      sí cubría la comunidad completa. NO ERA CIERTO: ese rectángulo recorta la
#      Comunitat Valenciana por tres lados. Comparando el recuento obtenido con
#      el que devuelve Overpass consultando por el ÁREA administrativa real
#      (relación OSM 349043) apareció la discrepancia: 439 subestaciones frente
#      a las 609 que OSM contiene en realidad, un 28 % menos.
#
#   3ª versión (actual): (37.8, -1.6, 40.8, 0.8)
#      Límites reales de la Comunitat Valenciana, medidos sobre la cartografía
#      provincial del Institut Cartogràfic Valencià:
#         longitud  -1.5288 .. 0.6903      latitud  37.8438 .. 40.7886
#      El rectángulo anterior perdía 0.93° de longitud por el oeste (unos 80 km:
#      Requena-Utiel, Rincón de Ademuz, Villena e interior de Alicante), 0.39°
#      por el norte (Vinaròs, Morella) y 0.16° por el sur (Torrevieja, Pilar de
#      la Horadada). Se añade un margen sobre los límites exactos para no perder
#      activos justo en la frontera; los que caen fuera de la comunidad se
#      descartan después por intersección geométrica, no por rectángulo.
# ============================================================================

import requests   # Peticiones HTTP (POST a la API Overpass)
import pandas as pd  # Construcción de la tabla final y exportación a CSV
import urllib3    # Solo para silenciar el aviso de seguridad de verify=False

# Igual que en el script de subestaciones: como hacemos la petición con
# verify=False, desactivamos el aviso de "certificado no verificado" para
# no llenar la consola de warnings.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _fmt_coord(v):
    """
    Formatea una coordenada como texto con coma decimal (formato español),
    igual que en el script de subestaciones. Ver comentarios detallados
    en DownloadSubstationsInfo_comentado.py; el comportamiento es idéntico.
    """
    if v is None:
        return ""
    try:
        f = float(v)
    except Exception:
        try:
            f = float(str(v).replace(',', '.'))
        except Exception:
            return str(v)
    s = f"{f:.7f}".rstrip('0').rstrip('.')
    return s.replace('.', ',')


# ----------------------------------------------------------------------------
# Consulta Overpass QL
# ----------------------------------------------------------------------------
# power=~"^(pole|tower|portal|support)$" es una expresión regular que
# selecciona los cuatro tipos de apoyo de línea eléctrica que existen en el
# esquema de etiquetado de OpenStreetMap:
#   - pole    -> poste (normalmente de baja/media tensión, de madera u hormigón)
#   - tower   -> torre metálica de alta tensión
#   - portal  -> pórtico (estructura tipo "puerta", habitual en subestaciones
#                o en el cruce de varias líneas)
#   - support -> soporte genérico, cuando no se especifica un tipo más concreto
#
# El rectángulo geográfico (37.8, -1.6, 40.8, 0.8) contiene por completo a la
# Comunitat Valenciana, con margen. Es el mismo que usa el script de
# subestaciones, de modo que ambos conjuntos son directamente comparables.
# Ver el historial de correcciones en la cabecera: las dos versiones anteriores
# recortaban territorio, la segunda sin que se detectara en su momento.
query = """
[out:json][timeout:300];

(
  node["power"~"^(pole|tower|portal|support)$"](37.8,-1.6,40.8,0.8);
  way["power"~"^(pole|tower|portal|support)$"](37.8,-1.6,40.8,0.8);
  relation["power"~"^(pole|tower|portal|support)$"](37.8,-1.6,40.8,0.8);
);

out center tags;
"""
# "out center tags;": para elementos que no son un punto simple (way o
# relation), pide el punto central de la figura (center) y las etiquetas
# (tags) de cada elemento.

# Lista de servidores Overpass alternativos, probados en orden por si
# alguno está caído o saturado.
api_urls = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter"
]

# Cabeceras HTTP: identifican el script (User-Agent) y piden la respuesta
# en JSON (Accept).
headers = {
    "User-Agent": "DownloadApoyosElectricosInfo/1.0 (+https://github.com)",
    "Accept": "application/json"
}

print("Descargando apoyos eléctricos...")

response = None
last_error = None

# Probamos cada servidor Overpass de la lista hasta obtener una respuesta
# válida (o hasta agotar la lista).
for url in api_urls:
    try:
        response = requests.post(
            url,
            data=query,
            headers=headers,
            verify=False,   # No se valida el certificado SSL (necesario en algunas redes corporativas)
            timeout=300      # Hasta 5 minutos de espera antes de considerar que ha fallado
        )
        response.raise_for_status()  # Lanza excepción si el servidor responde con error HTTP
        print(f"Conectado a: {url}")
        break  # Conexión conseguida: no probamos más servidores
    except requests.exceptions.RequestException as exc:
        print(f"No se pudo conectar a {url}: {exc}")
        last_error = exc  # Guardamos el error para poder informarlo si todo falla

# Si ningún servidor ha respondido correctamente, detenemos el script con
# un error claro (incluyendo la causa del último fallo).
if response is None:
    raise RuntimeError("No se pudo obtener datos de Overpass API.") from last_error

# Convertimos la respuesta (texto JSON) en estructuras de datos de Python.
data = response.json()

rows = []  # Aquí guardaremos un diccionario por cada apoyo encontrado

# Recorremos todos los elementos devueltos por Overpass.
for e in data["elements"]:
    lat = None
    lon = None

    if e["type"] == "node":
        # Punto simple: coordenadas directas.
        lat = e.get("lat")
        lon = e.get("lon")
    else:
        # Way o relation: usamos el centro calculado por Overpass.
        center = e.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")

    # Diccionario de etiquetas (atributos) del elemento.
    tags = e.get("tags", {})

    rows.append({
        "osm_id": e["id"],                     # Identificador único en OSM
        # Subtipo de apoyo, tomado de la propia etiqueta power. Se guarda porque
        # es la ÚNICA característica física del apoyo que OpenStreetMap informa
        # de forma sistemática (nombre, operador y tensión están vacíos en el
        # 100 % de los casos), y porque distingue activos con vulnerabilidad al
        # viento muy distinta: una torre metálica de transmisión (tower) no se
        # comporta igual que un poste de distribución (pole).
        "tipo_apoyo": tags.get("power", ""),
        "nombre": tags.get("name", ""),        # Nombre del apoyo (casi nunca informado)
        "operador": tags.get("operator", ""),  # Operador de la línea (casi nunca informado)
        "voltaje": tags.get("voltage", ""),    # Tensión de la línea (casi nunca informado)
        "latitud": _fmt_coord(lat),             # Latitud con coma decimal
        "longitud": _fmt_coord(lon)               # Longitud con coma decimal
    })

# Aviso si la consulta no ha devuelto ningún elemento (por ejemplo, si el
# área elegida no tuviese apoyos mapeados en OpenStreetMap).
if not rows:
    print("No se encontraron apoyos eléctricos para la zona seleccionada.")

# Convertimos la lista de diccionarios en una tabla de pandas.
df = pd.DataFrame(rows)

# Nombre del fichero de salida. Se ha renombrado (respecto al original
# "apoyos_electricos_valencia.csv") para reflejar que ahora cubre toda la
# Comunidad Valenciana y no solo el área parcial anterior.
output_file = "apoyos_electricos_comunidad_valenciana.csv"

# Limpieza de texto: quitamos saltos de línea que pudieran romper el CSV,
# igual que en el script de subestaciones.
for col in ["tipo_apoyo", "nombre", "operador", "voltaje"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str).apply(
            lambda s: s.replace('\r', ' ').replace('\n', ' ').strip()
        )

# Nos aseguramos de que las coordenadas queden como texto limpio, con coma
# decimal y sin la palabra "None" en las celdas vacías.
for c in ["latitud", "longitud"]:
    if c in df.columns:
        df[c] = df[c].astype(str).replace('None', '')
        df[c] = df[c].apply(lambda x: '' if x in ('', 'nan') else str(x).replace('.', ','))

# Guardamos el CSV con punto y coma como separador de columnas (porque la
# coma ya se usa como separador decimal) y codificación UTF-8 con BOM
# (para que Excel en Windows muestre bien tildes y eñes).
df.to_csv(
    output_file,
    index=False,
    sep=';',
    encoding="utf-8-sig"
)

print(f"Apoyos eléctricos encontrados: {len(df)}")
print(f"Archivo generado: {output_file}")
