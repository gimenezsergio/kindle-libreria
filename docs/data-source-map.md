# Mapa inicial de fuentes de datos

| Dato buscado | Fuente local candidata | Estado |
| --- | --- | --- |
| Archivo y formato del libro | `documents/` | Disponible para libros descargados |
| Título y autor | rutas, metadata lateral y `vocab.db` | Disponible parcialmente; falta reconciliar |
| ASIN, UUID o GUID | nombres, `.sdr`, miniaturas y `vocab.db` | Disponible parcialmente |
| Portada | `system/thumbnails/` | Disponible, aunque la aplicación tendrá portadas propias |
| Subrayados | `My Clippings.txt` y datos laterales `.sdr` | Muy prometedor |
| Notas | `My Clippings.txt` y datos laterales `.sdr` | Muy prometedor |
| Marcadores | `My Clippings.txt` | Disponible |
| Vocabulario consultado | `vocab.db` | Disponible |
| Sesiones de lectura | `fmcache.db` | Candidata fuerte; serialización pendiente de estudiar |
| Progreso actual por libro | archivos laterales `.sdr` | Candidato; formato pendiente de estudiar |
| Uso agregado del dispositivo | `isd.db` | Disponible |
| Colecciones de Kindle | ninguna fuente USB encontrada | No expuestas en esta inspección |
| Categorías y relaciones propias | base futura de la aplicación | Fuera del Kindle por diseño |

## Siguiente investigación

La prioridad técnica siguiente es identificar de forma segura la función de los
formatos laterales `.yjf`, `.yjr`, `.azw3f`, `.azw3r`, `.pds`, `.pdt`, `.mbp1` y
`.mbs`, y determinar cuáles contienen posición, progreso o anotaciones. Después
se podrá diseñar una identidad de libro que reconcilie rutas, encabezados de
clippings, ASIN y UUID sin depender de un único campo frágil.

