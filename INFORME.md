# Informe de ejecución — sustitución del viento medio por racha extrema en el Climate Risk Score

Versión V6 del índice, con el reparto de pesos reajustado a 0,70 / 0,30 (§12).
Este informe recoge lo hecho, lo decidido, lo que no salió como se esperaba y los
supuestos introducidos. Documento vigente:
`20260415_TFMAlvaroCubillo_v14.docx`.

---

## 1. Resumen en una línea

Se sustituyó la peligrosidad eólica basada en la velocidad media anual del Global
Wind Atlas por una basada en la **velocidad de retorno a 50 años**, normalizada
contra la velocidad básica de diseño del CTE. A igualdad de pesos el cambio mejora
sustancialmente el equilibrio del índice —el peso del viento en el 5 % de mayor
riesgo pasa del 27,4 % al 48,3 %— pero **no consigue que el índice detecte
Catadau**, y la investigación de por qué no lo consigue resultó ser el hallazgo
más valioso de la tanda. El reajuste posterior de los pesos a 0,70 / 0,30 deja ese
equilibrio en el 42,0 % y la cola extrema enteramente de inundación, a cambio de
elevar de 14 a 19 las subestaciones críticas: el intercambio se declara en §12.

---

## 2. Desviaciones respecto al encargo

### 2.1 CERRA no se pudo usar. Se recurrió al plan B

**Motivo:** la API del Copernicus Climate Data Store exige una clave personal
ligada a una cuenta registrada. No estaba configurada en la máquina y no procedía
crear una cuenta en nombre del usuario. El encargo admite expresamente el
registro como motivo para el plan B.

**Estimación de volumen que se hizo antes de descartarlo,** como se pedía:

| | Celdas | Por año | 37 años |
|---|---:|---:|---:|
| Dominio completo | 1.142.761 | ~40 GB | **~1,5 TB** |
| Recortado a la caja de la Comunitat | ~2.470 | ~87 MB | **~3,2 GB** |

El volumen no era el impedimento si el recorte por área funcionaba. Lo era el
tiempo: 37 peticiones de 8.760 campos cada una sobre la cola del CDS superan con
holgura el presupuesto de dos horas fijado.

**Fuente adoptada:** atlas global de viento extremo de Pryor y Barthelmie
(Nature Energy, 2021), Zenodo `10.5281/zenodo.4306822`, CC-BY-4.0.

### 2.2 La fuente del plan B tenía dos problemas que hubo que resolver

**El fichero NetCDF no trae coordenadas utilizables.** Contiene dos variables
llamadas `Latitude` (681 valores) y `Longitude` (1440 valores), pero sus valores
no son grados: van de 9,12 a 54,74 y de 34,30 a 40,72, no son monótonos y
presentan saltos de hasta −7,5. Son, con toda probabilidad, medias por fila y por
columna de un campo de viento, escritas por error en lugar de los ejes.

La rejilla se dedujo de la forma del campo (681 × 1440 corresponde a una rejilla
ERA5 regular de 0,25°) y **el convenio se determinó empíricamente**: se muestreó
el campo en la posición de los 38.939 activos bajo los cuatro convenios posibles
y se correló con la velocidad media del Global Wind Atlas, ya validada en el
conjunto. Solo uno da correlación positiva clara —r(Uref, GWA) = +0,540 frente a
valores entre −0,02 y +0,09 en los otros tres— y es el convenio nativo de ERA5:
latitud descendente de 85 a −85, longitud de 0 a 360.

**No son rachas, son velocidades sostenidas.** El encargo pedía
`10m_wind_gust`. Este atlas da el nivel de retorno a 50 años de la velocidad
sostenida a 10 m. Una racha es típicamente 1,4–1,6 veces la sostenida. En un
aspecto resulta favorable: la velocidad básica del CTE contra la que se normaliza
es también una media de 10 minutos a 10 m con retorno de 50 años, de modo que la
comparación es homogénea, cosa que no lo sería del todo con una racha.

### 2.3 La tarea 2 no se pudo hacer con el atlas, pero sí con AEMET

El atlas distribuye el nivel de retorno ya ajustado, no las series de máximos
anuales, así que no hay nada que ajustar. Se hicieron dos cosas:

**Con el atlas:** comparar las cuatro estimaciones que él mismo publica sobre la
misma serie de ERA5. Desviación máxima entre medianas del **13,21 %**, por debajo
del criterio del 15 % fijado. Las tres variantes Gumbel concuerdan casi
perfectamente (r = 0,996); la Weibull se separa más (r = 0,797, sesgo +2,34 m/s).
Cero celdas marcadas de alta incertidumbre por los autores.

**Con las rachas observadas de AEMET,** que sí son series temporales, se hizo el
ajuste completo que pedía el encargo:

| Método | Mediana entre estaciones | Desviación |
|---|---:|---:|
| Gumbel por L-momentos | 31,39 m/s (113 km/h) | — |
| GEV por L-momentos | 31,17 m/s | −0,72 % |
| POT con Pareto generalizada | 31,80 m/s | +1,29 % |

Desviación máxima **1,29 %**. Parámetro de forma de la GEV: mediana **+0,0389**,
rango −0,153 a +0,221, con 3 de 6 estaciones bajo |ξ| < 0,1. Próximo a cero, de
modo que **el uso de la Gumbel queda justificado**.

Dos decisiones metodológicas propias, no pedidas en el encargo:

- **Desagrupamiento para POT.** Las rachas diarias no son independientes: una
  borrasca produce rachas altas varios días seguidos. Sin desagrupar, la tasa de
  excedencias se infla y el nivel de retorno sale sesgado. Se conserva solo el
  máximo de cada episodio, separando episodios por 3 días.
- **Convenio de signo declarado.** Los L-momentos de Hosking dan k = −ξ respecto
  al convenio de Coles. La conversión está explícita en el código porque es un
  error clásico en ajustes GEV.

### 2.4 La descarga de AEMET: estrategia cambiada al medirla, y alcance recortado

El endpoint diario impone dos límites: 6 meses por petición para una estación
concreta, y 15 días para `todasestaciones`.

La segunda parecía más barata por número de peticiones (974 frente a 3.520), pero
**medida resultó mucho peor**: 15 s por petición frente a 1,2 s, porque devuelve
12.485 registros de toda España para quedarse con 75 de la Comunitat. Se
descargaba y descartaba el 99,4 % de cada respuesta. Coste real ~240 min, el
doble del presupuesto.

Con peticiones por estación el ritmo inicial fue de 40 peticiones/min, pero AEMET
estrangula progresivamente y cayó a 19–21, lo que llevaba el total a ~2 h 20 min.
**Se recortó el alcance** a las cinco estaciones con serie de racha desde 1985,
conservando íntegro el caché ya descargado.

**Resultado:** 125.328 registros de 13 estaciones, 1985–2024, con 99.721 rachas.
Seis estaciones superan los 20 años completos y cuatro llegan a 40.

**Limitación que esto introduce, y hay que declararla:** la calibración espacial
del campo de extremos se apoya en 6 estaciones y no en las 44 previstas. El
ajuste de extremos no se ve afectado —necesita series largas, no muchas— pero la
comprobación de la variación espacial del campo tiene menos puntos de apoyo.

---

## 3. La decisión que cambió el resultado: escalado refutado

El encargo pedía bajar de escala el campo de 0,25° a la resolución del Global
Wind Atlas mediante la razón de exposición local, y calcular también la variante
sin escalar para comparar. Se hicieron ambas.

El escalado abre el rango de V50 de 16,9–24,6 m/s a **9,6–45,6 m/s**. Ese valor
máximo no es creíble para viento sostenido a 10 m en la Comunitat, y hubo que
decidir con datos, no con criterio.

**Prueba de falsación.** El viento sostenido nunca puede superar la racha del
mismo episodio. Con el factor de racha más favorable al escalado (1,4, el mínimo
de la literatura):

| Variante | V50 sostenido máx. | Racha implicada | Activos imposibles |
|---|---:|---:|---:|
| **Bruta** | 24,6 m/s | 34,4 m/s (124 km/h) | **0** |
| Escalada | 45,6 m/s | **63,9 m/s (230 km/h)** | **986 (2,53 %)** |

La racha máxima registrada en la Comunitat en 40 años es **39,2 m/s (141 km/h)**,
en El Pinós el 30/11/2004. El escalado implica rachas de 230 km/h en 986 activos:
físicamente imposible.

**Factor de racha empírico** (V50 de racha observado / V50 sostenido del atlas en
la misma celda): **1,603 con la variante bruta**, justo en el borde del intervalo
1,4–1,6 de la literatura, frente a **1,750 con la escalada**, claramente fuera.

**Se adopta la variante bruta.** La escalada se conserva en el CSV como análisis
de sensibilidad.

**Matiz honesto:** el escalado da un factor de racha *más estable* entre
estaciones (coeficiente de variación 0,082 frente a 0,104). Es decir, la razón de
exposición del GWA **sí captura bien la variación relativa**, pero no debe
aplicarse multiplicativamente a un extremo, porque destruye las magnitudes
absolutas. Una vía de refinamiento sería amortiguar el exponente de la razón
(por ejemplo, su raíz cuadrada), que preservaría discriminación espacial sin
inflar la cola; no se ha hecho porque introduciría un parámetro sin validar.

**Contrapartida de adoptar la bruta, declarada:** el campo de extremos queda
resuelto a 0,25°, con 56 celdas sobre los activos. Dentro de cada celda la
peligrosidad eólica es constante y las diferencias de índice provienen solo de la
vulnerabilidad y de la criticidad. Es menos resolución, pero es la que el dato
tiene.

---

## 4. Resultados

### 4.1 La peligrosidad eólica deja de estar comprimida

| | V5 | V6 |
|---|---:|---:|
| Variable | velocidad media anual | velocidad de retorno a 50 años |
| Mediana | 4,02 m/s (14,5 km/h) | **20,23 m/s (72,8 km/h)** |
| Rango | 0,74 – 11,25 | **16,87 – 24,55** |
| `H_viento` mediano | 0,1241 | **0,4865** (×3,9) |
| Activos sobre 26 m/s (CTE zona A) | 0 | **0** |
| Activos sobre 29 m/s (CTE zona C) | 0 | **0** |

Ningún activo del territorio alcanza la velocidad básica con la que se
dimensionan sus propios apoyos.

### 4.2 El índice se equilibra, pero su cola sigue siendo de inundación

Las tres columnas separan los dos cambios, que actúan en sentidos opuestos: el de
variable de peligrosidad y el de reparto de pesos (§12).

| Amenaza dominante | V5<br>media, 0,60 | solo variable<br>V50, 0,60 | **V6 vigente**<br>**V50, 0,70** |
|---|---:|---:|---:|
| Conjunto | 90,9 % viento | 97,3 % | **96,8 %** |
| 5 % superior | 27,4 % | 48,3 % | **42,0 %** |
| **1 % superior** | 0,3 % (1 de 390) | 3,1 % (12 de 391) | **0,0 % (0 de 390)** |

El cambio de variable mejora la presencia del viento en la cola; el reajuste de
pesos la devuelve en parte. Ninguna de las dos versiones invierte la composición
de la cola extrema. **La asimetría residual es física, no metodológica:** la
inundación es un fenómeno de umbral cuya peligrosidad recorre todo el intervalo
[0, 1], mientras que la velocidad de retorno eólica varía de forma moderada en
este territorio, quedando `H_viento` confinada a la banda 0,34–0,72.

Conviene señalar que la versión escalada, la refutada, daba 57,2 % de viento en
el 1 % superior. **Ese resultado espectacular era un artefacto de valores
físicamente imposibles.**

### 4.3 Distribución del índice y sensibilidad

| | V5<br>media, 0,60 | V50, 0,60 | **V6 vigente**<br>**V50, 0,70** |
|---|---:|---:|---:|
| Mediana | 4,79 | 15,47 | **11,89** |
| p95 / p99 | 10,45 / 24,04 | 24,12 / 37,61 | **18,71 / 36,48** |
| Máximo | 72,84 | 79,83 | **89,20** |
| Spearman mínimo (pesos 0,3–0,8) | 0,8953 | 0,9426 | **0,9222** |
| Coincidencia mínima en el 5 % superior | 69,7 % | 70,6 % | **65,2 %** |

Las dos últimas filas no son estrictamente comparables entre columnas, porque
cada una mide la distancia al reparto adoptado en su propia versión, y 0,70 está
más cerca del extremo del barrido que 0,60. En términos absolutos siguen
sosteniendo la conclusión: la ordenación no baja de 0,92 de correlación en todo
el rango explorado.

### 4.4 Perfiles de amenaza recalculados

El óptimo pasa de k = 4 (silhouette 0,519) a **k = 7 (silhouette 0,5127)** sobre
las 608 subestaciones. La tipología resultante es más fina:

| Perfil | n | % inundable | V50 medio | Densidad | CRS mediano | CRS máximo |
|---|---:|---:|---:|---:|---:|---:|
| 1 · Inundación crítica | 8 | 100,0 | 19,58 | 478 | **74,97** | 89,20 |
| 2 · Inundación | 20 | 100,0 | 18,82 | 215 | 19,63 | 43,48 |
| 3 · Red densa y viento | 27 | 51,9 | 22,50 | **1.364** | 9,37 | 15,63 |
| 4 · Viento, red media | 148 | 18,9 | 21,27 | 741 | 9,18 | 14,67 |
| 5 · **Viento puro** | 48 | **0,0** | **23,30** | 267 | 7,18 | 12,69 |
| 6 · Viento, red baja | 214 | 8,4 | 20,92 | 157 | 6,14 | 12,48 |
| 7 · Riesgo bajo | 143 | 2,1 | 18,75 | 120 | 5,22 | 10,54 |

La composición de los perfiles **no depende del reparto de pesos** —sus entradas
son las dos peligrosidades y la densidad, no el índice— y por eso el número de
subestaciones de cada uno es el mismo con 0,60 y con 0,70. Lo único que cambia
son las columnas de índice. Las Figuras 13 y 14 del documento resultaron
byte a byte idénticas al regenerarlas, lo que sirvió de comprobación cruzada.

La lista corta de actuación por inundación se estrecha de 14 a **8** instalaciones,
y aparece un perfil de **viento puro** de 48 subestaciones sin ninguna en zona
inundable y con el V50 más alto del conjunto.

### 4.5 Reparto provincial del conjunto crítico

| Provincia | V5<br>media, 0,60 | V50, 0,60 | **V6 vigente**<br>**V50, 0,70** |
|---|---:|---:|---:|
| Castellón | 1.095 | 1.203 | **1.135** |
| Valencia | 712 | 713 | **784** |
| Alicante | 140 | 31 | **38** |
| Subestaciones críticas | — | 14 | **19** |

Alicante casi desaparece del conjunto crítico: su viento extremo es menor y su
exposición a inundación también. El reajuste de pesos desplaza activos críticos de
Castellón a Valencia, que es donde la peligrosidad fluvial es alta, y **eleva de
14 a 19 el número de subestaciones críticas**, que es la salida más accionable del
índice.

---

## 5. Validación contra el evento real: el hallazgo principal

### 5.1 Catadau no sube. Y eso es el resultado

| Catadau (149 activos, 6 km) | Antes | Después |
|---|---:|---:|
| Variable | 4,29 m/s | 21,71 m/s |
| Percentil | 63,4 | 69,5 |
| CRS mediano | 4,48 | 11,27 |
| **En el 5 % superior** | **0 de 149** | **0 de 149** |

| Quart de Poblet (1.012 activos) | Antes | Después |
|---|---:|---:|
| Percentil medio | 68,1 | **79,3** |
| En el 5 % superior | 71 | **112** |

La rama de inundación mejora y acierta en su caso real. **La de viento sigue
fallando en el suyo**: el percentil sube seis puntos pero ningún activo cruza el
umbral.

### 5.2 Por qué no sube: comprobado con observaciones

No se argumenta, se comprueba. Rachas registradas durante el episodio
(27 oct – 4 nov 2024):

| Estación | km a Catadau | Racha del episodio | % de su propio V50 |
|---|---:|---:|---:|
| **Valencia Aeropuerto** | **30,5** | 22,2 m/s (80 km/h) | **62 %** |
| Castelló-Almassora | 93,0 | 19,2 m/s | 61 % |
| Alacant | 96,3 | 16,7 m/s | 61 % |
| Alicante-Elche | 105,8 | 18,1 m/s | 53 % |

Durante el episodio que derribó más de veinte apoyos en Catadau, la estación a
30 km registró una racha equivalente al **62 % de su propio extremo de retorno a
50 años**: un viento anodino. Y la racha máxima histórica de la Comunitat
(39,2 m/s) **no ocurrió durante esta DANA**.

**Conclusión:** el fenómeno no lo capturaron ni las observaciones directas a
decenas de kilómetros. Que el índice no señale Catadau **no es un problema de
resolución del producto empleado** —CERRA a 5,5 km tampoco lo habría resuelto—
sino de la naturaleza convectiva y local del fenómeno. Esto convierte un fallo
del método en un resultado sobre el fenómeno, y distingue el viento sinóptico,
que el reanálisis captura, del convectivo, que no y que es un problema abierto en
la normativa internacional de cargas de viento.

---

## 6. Contraste con la regla de la IEC

`Vref = 5 × Vmedia` resulta **asombrosamente exacta sobre este territorio**, y el
signo depende de cómo se mire:

- Sesgo medio: **+0,14 m/s** → la regla queda ligeramente por encima
- Razón observada mediana: **5,13** frente al 5,00 supuesto → queda por debajo
- Correlación: 0,284

**No cabe llamarla conservadora sin matizar.** Acierta casi en el centro.

---

## 7. Dos errores propios detectados y corregidos

Se dejan escritos porque afectaron a resultados intermedios.

**`pct_inundable` mal calculado.** En la tabla de perfiles se calculó como
`H_inundacion > 0,02`. El término de proximidad asigna un valor pequeño no nulo a
*todos* los activos, de modo que ese umbral contaba como inundables muchos que no
lo estaban. Producía etiquetas contradictorias —un perfil marcado como de viento
dominante con el 100 % de sus activos en zona inundable—. Corregido a la
pertenencia real (`dentro_zona_inundable`).

**Diagnóstico erróneo sobre los marcadores del documento.** Se informó de que la
V5(1) había perdido los 22 marcadores de bibliografía. No era cierto: fue un
fallo de escapado en una expresión regular. Los marcadores estaban; solo se
habían perdido los 43 campos REF. Al no detectarlo a tiempo se insertaron 22
marcadores duplicados, que Word considera inválidos; se rehízo reutilizando los
existentes y verificando que cada uno está en el asiento que le corresponde por
orden.

---

## 8. Supuestos introducidos

1. **Rejilla del atlas de Pryor y Barthelmie**: deducida de la forma del campo y
   verificada por correlación, no leída del fichero (que no la trae).
2. **Velocidad sostenida como sustituto de racha**: la fuente disponible no da
   rachas. Se declara y se mitiga porque el umbral del CTE es también una media
   de 10 minutos.
3. **Factor de racha de 1,4** en la prueba de falsación: el mínimo de la
   literatura, elegido para no cargar el argumento contra la variante escalada.
4. **Peligrosidad eólica constante dentro de cada celda de 0,25°**: consecuencia
   de descartar el escalado.
5. **Umbral de 20 años completos y 300 días por año** para admitir una estación
   en el ajuste de extremos.
6. **Desagrupamiento con hueco de 3 días** para POT.

---

## 9. Lo que NO se tocó

- **El modelo supervisado** (`modelado_inundabilidad.py`), sus métricas y sus
  valores SHAP, por indicación expresa del encargo. Allí `velocidad_viento_ms`
  opera como sustituto del relieve para predecir inundabilidad, no como amenaza.
- **La matriz de vulnerabilidad y el factor de criticidad de la rama de
  inundación**. El reparto de pesos entre amenazas sí se reajustó después (§12);
  la definición de cada rama, no.
- **Los documentos anteriores**: intactos. Cada revisión escribe un fichero nuevo
  y no sobrescribe el anterior, de modo que la V5(1), la V6, la V12 y la V13
  siguen disponibles para comparar.

**Consecuencia editorial declarada:** la memoria contiene ahora las dos variables
de viento en dos papeles distintos —velocidad media como predictor topográfico
del modelo, velocidad de retorno como peligrosidad del índice—. Es correcto pero
requiere explicación expresa, o se lee como incoherencia.

---

## 10. Ficheros entregados

| Fichero | Contenido |
|---|---|
| `baseline_v5.json` | Cifras de control de la V5, reproducidas y verificadas |
| `cerra_v50.npz` | Campo V50 sobre la Comunitat, cuatro métodos |
| `v50_metodos.json` | Comparación de los métodos del atlas |
| `rachas_aemet_cv.csv` | 125.328 registros diarios de racha, 13 estaciones |
| `estaciones_aemet_cv.csv` | Inventario de las 44 estaciones de la Comunitat |
| `extremos_observados.json` · `v50_estaciones.csv` | Ajuste Gumbel/GEV/POT con IC bootstrap |
| `calibracion_v50.json` | Factor de racha y prueba de falsación |
| `evento_dana_observado.json` | Rachas observadas durante el episodio |
| `activos_con_crs_v6.csv` | Todas las columnas, con V50, H_viento y CRS nuevos y antiguos |
| `crs_parametros_v6.json` | Pesos, normalización y sensibilidad |
| `clustering_perfiles_v6.json` · `perfiles_amenaza_v6.csv` | Perfiles en los dos subconjuntos |
| `comparativa_v5_v6.json` | Todas las cifras antes y después |
| `validacion_dana.json` · `cifras_viento.json` | Tareas 6 y 7 |
| `cifras_documento.json` | Todas las cifras de las Tablas 6 a 10, recalculadas |
| `20260415_TFMAlvaroCubillo_v15.docx` | **Memoria vigente** |

Scripts numerados y reejecutables: `00_baseline_v5` a `18_verificar_v14`.
Ninguno sobrescribe entradas previas; las descargas se cachean. Los cuatro
últimos son la cadena de esta revisión:

| Script | Cometido |
|---|---|
| `15_cifras_documento.py` | Recalcula todas las cifras que el documento cita |
| `16_figuras_conceptuales.py` | Rehace las Figuras 24 y 27, que llevan cifras |
| `17_documento_v14.py` | Aplica las 165 correcciones y sustituye 9 imágenes |
| `18_verificar_v14.py` | Comprueba que no sobrevive ninguna cifra antigua |
| `19_restaurar_campos_ref.py` | Devuelve a las citas su condición de campo (§13) |

El 17 no guarda nada si una sola sustitución no encuentra su texto, y el 18 falla
con código de salida distinto de cero si queda una cifra del reparto anterior o si
una tabla no cuadra consigo misma. La cadena completa, desde el índice hasta el
documento verificado, es:

```
04_crs_v6 → 05_validacion_y_cifras → 15_cifras_documento
         → generar_figuras + 10_figuras_v6_adicionales + 13 + 16
         → 17_documento_v14 → 18_verificar_v14
```

---

## 11. Pendiente

1. **Abrir el documento y pulsar Ctrl+A, F9** para recalcular los índices de
   figuras y de tablas y los 72 campos de cita restaurados en §13.
2. **Comprobar de un vistazo, tras ese F9, que una cita se lee `[1]` y no
   `[1.]`.** Es lo único de §13 que no se puede verificar sin abrir Word, y el
   arreglo, si hiciera falta, es de una línea: quitar el punto del formato de la
   lista de la bibliografía.
3. Los Anexos I y II siguen con la plantilla sin rellenar, marcados con
   comentarios de Word.

---

## 12. Reajuste del reparto de pesos a 0,70 / 0,30

Revisión posterior al encargo original, pedida al comprobar que la rama eólica no
producía resultados en la cola del índice.

### 12.1 Los tres candidatos, comparados con datos

No se eligió por criterio sino midiendo qué le hace cada reparto a lo que el
índice tiene que entregar:

| `w_inundación` | Viento en el 1 % sup. | Viento en el 5 % sup. | Perfil de viento puro | Subest. críticas |
|---:|---:|---:|---:|---:|
| 0,60 | 12 de 391 | 48,3 % | 48 subestaciones | 14 |
| **0,70** | **0 de 390** | **42,0 %** | **48 subestaciones** | **19** |
| 0,80 | 0 de 393 | 21,6 % | se disuelve | 30 |

La correlación de Spearman entre las ordenaciones de 0,60 y 0,70 es **0,9899**:
el cambio apenas altera el orden de los activos.

**0,80 queda descartado** porque el grupo de 48 subestaciones sin exposición
fluvial alguna deja de estar dominado por el viento en la descomposición del
índice —pasa a dominarlo el riesgo residual de proximidad— y la lectura por
mecanismo, que es lo único que la rama eólica aporta de forma operativa, se vacía
de contenido.

### 12.2 Qué se gana y qué se pierde, sin adornos

**Se gana:** las subestaciones críticas pasan de 14 a 19; el entorno de la
subestación anegada de Quart de Poblet sube del percentil 78,3 al 79,3 y de 71 a
112 activos en el 5 % superior; el reparto refleja que la inundación es la amenaza
que ha producido los daños documentados.

**Se pierde:** el 1 % superior del índice pierde los 12 activos dominados por
viento que tenía con 0,60 y se queda en cero.

Ese intercambio es deliberado y **el apartado 5.4 de la memoria lo declara**
separando el efecto de la variable del efecto del reparto, para no atribuir a uno
lo que hace el otro. Revertirlo es cambiar una constante, `PESO_INUNDACION` en
`04_crs_v6.py`, y reejecutar la cadena `04 → 05 → 15 → figuras → 17 → 18`.

### 12.3 Un error de comparación introducido y corregido en el acto

Al cambiar los pesos, la comparativa V5 → V6 empezó a calcular **la dominancia de
la V5 con los pesos de la V6**, y daba 84,2 % de viento en el conjunto donde la V5
real da 90,9 %. El reparto forma parte de la definición de cada versión y
mezclarlo producía una V5 que nunca existió. Corregido en `04_crs_v6.py`, que
ahora calcula tres variantes —V5 con sus pesos, variable nueva con los pesos de la
V5, y V6 con los suyos— precisamente para poder atribuir cada efecto a su causa.

### 12.4 Cuatro remisiones a figuras que apuntaban a la figura equivocada

Detectadas al auditar la coherencia figura–texto. Al insertar figuras nuevas en
revisiones anteriores, las posteriores se corrieron de número y cuatro remisiones
del texto conservaron el número viejo:

| Apartado | Decía | Debe decir |
|---|---|---|
| 5.3 | Figuras 10 y 11 | **13 y 14** |
| 5.4 | Figuras 13 y 14 | **16 y 17** |
| 5.5 | Figuras 15, 16 y 17 | **18, 19 y 20** |
| 5.7 | Figuras 18 y 19 | **21 y 22** |

### 12.5 Cuatro incoherencias más, ninguna derivada de los pesos

Aparecieron al revisar el documento entero y se corrigen en la misma tanda.

**La Tabla 9 no listaba el conjunto que las conclusiones prometían.** Listaba «las
quince subestaciones de mayor índice», un corte arbitrario que con el reparto
anterior coincidía con las 14 críticas. El apartado 7.1 afirma que el 5.5 «las
identifica una a una», y con 19 críticas eso dejó de ser cierto. La tabla se
amplía a **las 19 que superan el umbral**, de modo que la lista corta y el
conjunto crítico son ahora el mismo conjunto y el corte deja de ser arbitrario.

**El trabajo maneja dos densidades distintas y el texto las confundía.**

| Variable | Cuenta | Alimenta |
|---|---|---|
| `densidad_apoyos_5km` | solo apoyos | agrupamiento territorial y **Tabla 5** |
| `densidad_5km` | todos los activos, menos el propio | factor de criticidad, perfiles y **Tabla 6** |

Las cifras de la Tabla 6 y del apartado 5.3 son de la segunda, así que llamarlas
«apoyos» era incorrecto. Corregido en el texto y en la cabecera de la Tabla 6, que
ahora dice «Densidad de activos (5 km)» para que no se confunda con la Tabla 5.

**El apartado 5.3 atribuía al grupo territorial 1 «la mayor velocidad media de
viento (5,62 m/s)».** El dato es cierto, pero cita la velocidad media del Global
Wind Atlas, que este trabajo descartó como peligrosidad y que ya no figura en la
Tabla 5. Leído contra la tabla, que declara V50, parecía un error: en V50 el grupo
1 (21,02) va por detrás del grupo 2 (21,43). Reformulado sobre la variable que la
tabla sí muestra.

**Dos cifras sueltas mal.** El 5.5 decía que siete de las subestaciones de la
Tabla 9 carecen de nombre cuando son **doce** de las diecinueve, y el 6.3 daba
«unas veinticinco celdas» del campo de extremos cuando las celdas con activos son
**56**. La Figura 27 declaraba **5 fuentes públicas integradas**; son **7**,
contadas una a una en `16_figuras_conceptuales.py`.

---

## 13. Restauración de los campos de referencia cruzada

La revisión que produjo la V12 dejó el documento con los 36 marcadores de la
bibliografía intactos pero **sin un solo campo**: los números entre corchetes eran
texto plano. La consecuencia práctica es que insertar, borrar o reordenar una
entrada descuadraba todas las citas posteriores sin que Word pudiera advertirlo.

### 13.1 El mecanismo no se inventa: se reproduce el que ya funcionó

La versión `_-_refcruzadas` de este mismo documento tenía 38 campos de esta forma,
y su bibliografía usaba exactamente la misma lista numerada (`numId` 8, formato
`%1.`). Se reproduce sin cambios:

```xml
<w:fldSimple w:instr=" REF ref_biblio_05 \r \h "><w:r><w:t>5</w:t></w:r></w:fldSimple>
```

El conmutador de número de párrafo pide el número de la entrada marcada y el de
hipervínculo la convierte en enlace. Los corchetes y las comas siguen siendo
texto: el campo contiene solo el número, igual que antes. El resultado va
precalculado, de modo que las citas se leen bien incluso antes de pulsar F9.

### 13.2 Resultado

| | |
|---|---:|
| Grupos de cita convertidos | **70** |
| Campos insertados | **72** |
| Referencias distintas alcanzadas | **36 de 36** |
| Marcadores conservados | 36 |
| Caracteres de texto visible antes y después | **189.039 = 189.039** |

Esa última fila es la comprobación que importa: la conversión no cambia lo que el
documento dice, solo cómo lo dice. Si un solo carácter se hubiera movido, el
script habría fallado sin guardar nada.

### 13.3 Lo que deliberadamente no se convierte

| Caso | Dónde | Por qué |
|---|---|---|
| `[0, 1]` | 4.7 (dos veces) y 5.4 | Es el intervalo de normalización, no una cita |
| `[0, 100]` | Tabla 10 | Es el recorrido del índice |
| `[1]` | Anexos I y II | Es la instrucción de la plantilla: «Numerar las citas de forma consecutiva entre corchetes» |
| `[1]`, `[6]`, `[9]`, `[35]` | Índice de figuras | Word regenera ese índice con F9 y cualquier campo puesto a mano se perdería |

El criterio automático es que un grupo solo es cita si **todos** sus números están
entre 1 y 36, el número de entradas de la bibliografía; los intervalos se delatan
por contener un 0 o un 100.

### 13.4 Lo único que queda por confirmar a ojo

El formato de la lista de la bibliografía lleva punto tras el número. Word
devuelve para el conmutador de número de párrafo el número sin el texto literal
del formato, y así funcionó en la versión anterior de este mismo documento, pero
conviene mirar una cita después del F9: si se leyera `[1.]` en lugar de `[1]`,
basta quitar el punto del formato de esa lista.
