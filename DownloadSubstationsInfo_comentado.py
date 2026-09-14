# ============================================================================
# DownloadSubstationsInfo.py — versión COMENTADA
# ----------------------------------------------------------------------------
# Qué hace este script, en una frase:
#   Descarga de OpenStreetMap (a través de la API Overpass) todas las
#   subestaciones eléctricas (power=substation) situadas dentro de un
#   rectángulo geográfico (bounding box) que cubre la Comunidad Valenciana,
#   y las guarda en un fichero CSV listo para abrir con Excel en español.
# ============================================================================

import requests   # Librería para hacer peticiones HTTP (aquí, POST a la API Overpass)
import pandas as pd  # Librería de análisis de datos: la usamos para construir la tabla final y exportarla a CSV
import urllib3    # Librería HTTP de bajo nivel; la usamos solo para silenciar un aviso de seguridad

# Algunas redes corporativas usan proxys que rompen la verificación del
# certificado SSL. Como más abajo hacemos la petición con verify=False
# (es decir, sin verificar el certificado), Python mostraría un aviso
# (warning) por cada petición. Esta línea desactiva ese aviso concreto
# para no ensuciar la salida por consola.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _fmt_coord(v):
    """
    Formatea una coordenada (latitud o longitud) para que se pueda
    guardar en un CSV "a la española": con coma decimal en vez de punto
    (así Excel en España la reconoce automáticamente como número).

    Parámetros
    ----------
    v : el valor de la coordenada tal y como viene de Overpass (puede ser
        un float, un string con punto, o incluso None si el dato faltase).

    Devuelve
    --------
    Un string con la coordenada, p. ej. "39,4630808", o "" si v es None.
    """
    if v is None:
        # Si no hay coordenada (no debería pasar, pero por seguridad),
        # devolvemos una cadena vacía en vez de fallar.
        return ""
    try:
        # Caso normal: v ya es un número (float) o un string con punto
        # decimal ("39.4630808") que Python puede convertir directamente.
        f = float(v)
    except Exception:
        # Si la conversión directa falla (por ejemplo, porque v ya viene
        # como "39,4630808" con coma), lo intentamos de nuevo cambiando
        # la coma por un punto antes de convertir.
        try:
            f = float(str(v).replace(',', '.'))
        except Exception:
            # Si ni siquiera así se puede convertir a número, devolvemos
            # el valor tal cual (como texto) para no perder la información.
            return str(v)

    # Formateamos el número con 7 decimales (precisión de sobra para
    # coordenadas GPS), y luego quitamos los ceros sobrantes al final
    # (p. ej. "39,4630800" -> "39,46308") y un posible punto suelto.
    s = f"{f:.7f}".rstrip('0').rstrip('.')

    # Por último, sustituimos el punto decimal por una coma, que es el
    # separador decimal que usa Excel en español.
    return s.replace('.', ',')


# ----------------------------------------------------------------------------
# Consulta a Overpass (lenguaje "Overpass QL")
# ----------------------------------------------------------------------------
# Overpass es la API de consulta de OpenStreetMap. La consulta de abajo pide:
#   - todos los "node" (puntos), "way" (líneas/polígonos) y "relation"
#     (agrupaciones de elementos) etiquetados como power=substation
#     (subestación eléctrica)...
#   - ...que se encuentren dentro del rectángulo geográfico
#     (37.8, -1.6, 40.8, 0.8), es decir:
#       latitud  mínima = 37.8   (sur)
#       longitud mínima = -1.6   (oeste)
#       latitud  máxima = 40.8   (norte)
#       longitud máxima =  0.8   (este)
#
#     CORRECCIÓN: la versión anterior usaba (38.0, -0.6, 40.4, 0.8) y se daba
#     por supuesto que cubría las tres provincias. No las cubría. Los límites
#     reales de la Comunitat Valenciana, medidos sobre la cartografía del
#     Institut Cartogràfic Valencià, son longitud -1.5288..0.6903 y latitud
#     37.8438..40.7886: aquel rectángulo recortaba 0.93° por el oeste (todo el
#     interior: Requena-Utiel, Ademuz, Villena), 0.39° por el norte (Vinaròs,
#     Morella) y 0.16° por el sur (Torrevieja). El error se detectó al comparar
#     el recuento obtenido (439) con el que devuelve Overpass consultando por el
#     ÁREA administrativa real (relación OSM 349043): 609 subestaciones, un 28 %
#     más. El rectángulo actual las contiene todas, con margen; los activos que
#     caen fuera de la comunidad se descartan luego por intersección geométrica
#     con los polígonos provinciales, que es lo correcto.
# [out:json] pide que la respuesta venga en formato JSON.
# [timeout:300] da hasta 300 segundos al servidor para responder antes
# de abortar la consulta (las consultas grandes pueden tardar).
query = """
[out:json][timeout:300];

(
  node["power"="substation"](37.8,-1.6,40.8,0.8);
  way["power"="substation"](37.8,-1.6,40.8,0.8);
  relation["power"="substation"](37.8,-1.6,40.8,0.8);
);

out center tags;
"""
# "out center tags;" le dice a Overpass que, para elementos que no son un
# único punto (way o relation, que son polígonos o formas complejas),
# calcule y devuelva el punto central (center) de la figura, además de
# las etiquetas (tags) con la información de cada elemento (nombre,
# operador, voltaje...).

# ----------------------------------------------------------------------------
# Lista de servidores Overpass alternativos
# ----------------------------------------------------------------------------
# Existen varios servidores públicos que ofrecen el mismo servicio Overpass.
# Como a veces uno de ellos está caído o saturado, probamos varios en orden
# hasta que alguno responda correctamente.
api_urls = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter"
]

# Cabeceras HTTP que enviamos con la petición:
#  - "User-Agent": identifica nuestro script ante el servidor (buena
#    práctica y, en muchos servicios públicos, requisito para no ser
#    bloqueado por parecer tráfico anónimo/sospechoso).
#  - "Accept": indicamos que esperamos la respuesta en formato JSON.
headers = {
    "User-Agent": "DownloadSubstationsInfo/1.0 (+https://github.com)",
    "Accept": "application/json"
}

print("Descargando subestaciones...")

# Variables donde guardaremos la respuesta HTTP válida (si la conseguimos)
# y el último error producido (por si todos los servidores fallan y
# queremos informar de la causa).
response = None
last_error = None

# Probamos cada servidor de la lista, uno detrás de otro...
for url in api_urls:
    try:
        # Hacemos una petición POST enviando la consulta Overpass QL como
        # cuerpo (data) de la petición.
        #   - verify=False: no se valida el certificado SSL del servidor
        #     (necesario en algunas redes corporativas con proxy, aunque
        #     reduce la seguridad de la conexión).
        #   - timeout=300: si el servidor no responde en 300 segundos,
        #     Python lanza una excepción en vez de quedarse esperando
        #     indefinidamente.
        response = requests.post(
            url,
            data=query,
            headers=headers,
            verify=False,
            timeout=300
        )
        # Si el servidor responde con un código de error HTTP (4xx/5xx),
        # esta línea lanza una excepción y pasamos al except de abajo.
        response.raise_for_status()

        print(f"Conectado a: {url}")
        # Si hemos llegado hasta aquí, la petición ha funcionado:
        # salimos del bucle "for" sin seguir probando más servidores.
        break

    except requests.exceptions.RequestException as exc:
        # Si algo ha ido mal (timeout, servidor caído, error HTTP...),
        # lo mostramos por pantalla, guardamos el error, y el bucle
        # continúa probando con el siguiente servidor de la lista.
        print(f"No se pudo conectar a {url}: {exc}")
        last_error = exc

# Si tras probar TODOS los servidores seguimos sin respuesta válida,
# no tiene sentido continuar: lanzamos un error que detiene el script,
# incluyendo el último error de conexión como causa (para facilitar
# el diagnóstico del problema).
if response is None:
    raise RuntimeError("No se pudo obtener datos de Overpass API.") from last_error

# Convertimos el cuerpo de la respuesta (texto JSON) a estructuras de
# Python (diccionarios y listas) con las que ya podemos trabajar.
data = response.json()

# Lista donde iremos guardando un diccionario por cada subestación
# encontrada; al final la convertiremos en una tabla (DataFrame).
rows = []

# data["elements"] contiene la lista de todos los elementos (nodes, ways,
# relations) que ha devuelto Overpass. Recorremos uno a uno.
for e in data["elements"]:

    lat = None
    lon = None

    if e["type"] == "node":
        # Si el elemento es un "node" (un punto simple), sus coordenadas
        # vienen directamente en los campos "lat" y "lon".
        lat = e.get("lat")
        lon = e.get("lon")
    else:
        # Si es un "way" o una "relation" (una forma con varios puntos),
        # gracias a "out center" en la consulta, Overpass ya nos da un
        # diccionario "center" con la coordenada del centro de la figura.
        center = e.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")

    # "tags" es un diccionario con todos los atributos que los usuarios
    # de OpenStreetMap han rellenado para este elemento (nombre, operador,
    # voltaje, tipo de subestación, etc.). Si no existiese la clave
    # "tags" (no debería pasar), usamos un diccionario vacío por seguridad.
    tags = e.get("tags", {})

    # Añadimos una fila a nuestra lista de resultados con los campos que
    # nos interesan. tags.get("name", "") devuelve el valor de "name" si
    # existe, o una cadena vacía si esa subestación no tiene ese dato
    # (algo muy habitual en OpenStreetMap, como se comenta en la memoria).
    rows.append({
        "osm_id": e["id"],                       # Identificador único del elemento en OSM
        "nombre": tags.get("name", ""),          # Nombre de la subestación (si está informado)
        "operador": tags.get("operator", ""),    # Empresa operadora (si está informado)
        "voltaje": tags.get("voltage", ""),      # Nivel(es) de tensión, p. ej. "220000;132000;20000"
        "latitud": _fmt_coord(lat),               # Latitud formateada con coma decimal
        "longitud": _fmt_coord(lon)                # Longitud formateada con coma decimal
    })

# Convertimos la lista de diccionarios en una tabla de pandas (DataFrame),
# donde cada diccionario pasa a ser una fila y cada clave, una columna.
df = pd.DataFrame(rows)

# --------------------------------------------------------------------
# Limpieza de texto: algunas etiquetas de OSM pueden contener saltos de
# línea (\r o \n) dentro del propio texto (por ejemplo, un nombre escrito
# en varias líneas). Si los dejáramos tal cual, romperían el formato del
# CSV, porque un salto de línea dentro de una celda puede confundirse con
# el final de una fila. Por eso los sustituimos por espacios y quitamos
# espacios sobrantes al principio/final con strip().
# --------------------------------------------------------------------
for col in ["nombre", "operador", "voltaje"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str).apply(
            lambda s: s.replace('\r', ' ').replace('\n', ' ').strip()
        )

# Nos aseguramos de que las columnas de coordenadas sean texto (string) y
# no números, y sustituimos la palabra "None" (que a veces aparece al
# convertir valores vacíos a texto) por una cadena vacía. Aunque
# _fmt_coord ya debería haber devuelto strings con coma, esta es una
# comprobación de seguridad adicional antes de guardar el fichero.
for c in ["latitud", "longitud"]:
    if c in df.columns:
        df[c] = df[c].astype(str).replace('None', '')
        df[c] = df[c].apply(lambda x: '' if x in ('', 'nan') else str(x).replace('.', ','))

# Nombre del fichero de salida.
output_file = "subestaciones_comunidad_valenciana.csv"

# Guardamos la tabla como CSV:
#   - index=False: no incluir la columna de índice numérico de pandas.
#   - sep=';': usamos punto y coma como separador de columnas, porque en
#     un CSV "a la española" la coma ya se usa como separador decimal
#     (ver _fmt_coord) y no se puede usar también como separador de columnas.
#   - encoding="utf-8-sig": UTF-8 con "BOM" (marca de orden de bytes),
#     que es lo que espera Excel en Windows para mostrar correctamente
#     tildes y eñes sin que se conviertan en caracteres extraños.
df.to_csv(
    output_file,
    index=False,
    sep=';',
    encoding="utf-8-sig"
)

print(f"Subestaciones encontradas: {len(df)}")
print(f"Archivo generado: {output_file}")
