# Mapa inicial de fuentes de datos

| Dato buscado | Fuente local candidata | Estado |
| --- | --- | --- |
| Archivo y formato del libro | `documents/` | Disponible para libros descargados |
| Título y autor | rutas, metadata lateral y `vocab.db` | Disponible parcialmente; falta reconciliar |
| Identidad de entrega | `content.id` en `.mf`, nombre y `.sdr` | Determinística para 173 documentos |
| ASIN, UUID o GUID | manifiestos, miniaturas y `vocab.db` | Disponible parcialmente; requiere espacios de nombres |
| Portada | `system/thumbnails/` | Disponible, aunque la aplicación tendrá portadas propias |
| Subrayados | `My Clippings.txt` y datos laterales `.sdr` | Muy prometedor |
| Notas | `My Clippings.txt` y datos laterales `.sdr` | Muy prometedor |
| Marcadores | `My Clippings.txt` | Disponible |
| IDs alternativos de anotación | `.han` | Disponible para tres documentos; reconciliación pendiente |
| Vocabulario consultado | `vocab.db` | Disponible |
| Sesiones de lectura recientes | `fmcache.db` | Disponible, pero solo dos sesiones y un libro cubierto |
| Posición actual por libro | `lpr` en sidecars KRDS | Disponible para 185 documentos, en formato nativo |
| Máxima posición alcanzada | `fpr` en sidecars KRDS | Disponible para 84 documentos |
| Porcentaje comparable | requiere denominador específico por formato | No disponible de forma universal |
| Uso agregado del dispositivo | `isd.db` | Disponible |
| Colecciones de Kindle | ninguna fuente USB encontrada | No expuestas en esta inspección |
| Categorías y relaciones propias | base futura de la aplicación | Fuera del Kindle por diseño |

## Siguiente investigación

Los formatos laterales, la estrategia de identidad, las limitaciones del progreso,
el modelo mínimo y las fuentes auxiliares ya fueron caracterizados. La siguiente
decisión es fijar el alcance exacto de la primera versión implementable.
