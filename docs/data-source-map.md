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
| Vocabulario consultado | `vocab.db` | Disponible |
| Sesiones de lectura | `fmcache.db` | Candidata fuerte; serialización pendiente de estudiar |
| Progreso actual por libro | archivos laterales `.sdr` | Candidato; formato pendiente de estudiar |
| Uso agregado del dispositivo | `isd.db` | Disponible |
| Colecciones de Kindle | ninguna fuente USB encontrada | No expuestas en esta inspección |
| Categorías y relaciones propias | base futura de la aplicación | Fuera del Kindle por diseño |

## Siguiente investigación

Los formatos laterales y la estrategia de identidad ya fueron caracterizados.
La investigación siguiente debe precisar cómo convertir posiciones KRDS a una
métrica de progreso comparable y qué campos mínimos necesita el primer modelo de
datos, sin implementar todavía la sincronización completa.
