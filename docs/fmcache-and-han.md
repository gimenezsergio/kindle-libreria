# `fmcache.db` y archivos `.han`

## `fmcache.db`

La base contiene cinco sesiones de aplicación, dos sesiones de lectura y 1.301
eventos de telemetría. Todos los campos serializados son JSON válido.

### Sesiones de lectura

Las dos sesiones corresponden a KFX y contienen:

- identificadores `asin`, `asset_id`, `embedded_id` y `revision_id`;
- tipo de contenido, formato y MIME;
- inicio y fin temporal;
- posición inicial y final;
- máxima posición;
- indicador de sesión completa.

En ambos casos `asin` coincide con el `content.id` de un manifiesto local. Esto
permite asociarlas determinísticamente con una entrega Kindle.

### Eventos

Los 1.301 registros abarcan, entre otros:

- consumo de contenido y giros de página;
- selección, highlights y acciones de anotación;
- apertura, cierre y latencias del lector;
- métricas operativas, fallos, interfaz, energía y publicidad.

Hay 1.231 eventos asociados a una sesión de lectura. De los eventos con
identificador de libro, 411 enlazan con un manifiesto actual, pero corresponden a
un solo `content.id`. Esto demuestra que la base es un buffer reciente o parcial,
no un historial durable de toda la biblioteca.

### Uso propuesto

- Fuente opcional de sesiones y actividad reciente.
- No usarla para reconstruir el historial completo.
- No usar sus eventos como sustituto de `lpr`, `fpr` o anotaciones KRDS.
- Importar solo esquemas de eventos deliberadamente soportados; ignorar métricas
  operativas que no aporten valor a la biblioteca.
- Excluir datos de dispositivo, cuenta y publicidad que no sean necesarios.

## Archivos `.han`

Hay tres archivos JSON. Cada uno contiene checksum `md5` y un `payload` con
identificadores y una lista de registros. `payload.key` coincide con el
`content.id` de su manifiesto, de modo que los tres se asocian determinísticamente.

En conjunto contienen 194 registros:

| Tipo | Cantidad |
| --- | ---: |
| `kindle.highlight` | 186 |
| `kindle.note` | 1 |
| `kindle.bookmark` | 1 |
| `kindle.lpr` | 3 |
| `kindle.most_recent_read` | 3 |

Los registros personales incluyen `annotationId`, tipo, posiciones y fechas. Solo
uno contiene un campo `text`; por ello `.han` no reemplaza el texto de
`My Clippings.txt`.

### Relación con KRDS

Los mismos tres directorios contienen exactamente 188 anotaciones personales en
KRDS, la misma cantidad que highlights, nota y marcador de `.han`. Sin embargo:

- `.han` usa posiciones alfabéticas cortas;
- KRDS usa posiciones estructurales KFX con token y desplazamiento;
- las fechas tampoco coinciden directamente bajo una comparación conservadora.

La igualdad de cantidades sugiere que son representaciones paralelas del mismo
conjunto, pero no es evidencia suficiente para fusionarlas automáticamente. Hasta
validar la conversión, deben conservarse como ocurrencias de fuentes distintas y
no sumarse como anotaciones independientes.

## Conclusión

La investigación estructural necesaria para el primer modelo queda cerrada:

- manifiestos para identidad de entrega;
- KRDS para posición, temporizador y anotaciones locales;
- `My Clippings.txt` para historial textual amplio;
- `.han` como fuente paralela con IDs de anotación;
- `vocab.db` para catálogo parcial y consultas;
- `fmcache.db` para actividad reciente opcional;
- `isd.db` para uso agregado;
- colecciones Kindle no expuestas por USB.

