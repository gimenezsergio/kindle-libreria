# Inventario inicial del dispositivo

Fecha de observación: 2026-08-31.

## Montaje

- Dispositivo: `/dev/sdb`.
- Punto de montaje: `/media/sergio/Kindle`.
- Sistema de archivos: FAT (`vfat`).
- Modo observado antes de inspeccionar datos: `ro` (solo lectura).
- Capacidad aproximada: 6,3 GB; 674 MB usados.

## Estructura principal

Las áreas potencialmente relevantes son:

- `documents/`: libros, documentos, `My Clippings.txt` y datos laterales `.sdr`.
- `system/`: bases de datos, índices y miniaturas administrados por Kindle.
- `system/thumbnails/`: portadas identificadas mediante ASIN o UUID.

También existen archivos dejados por un uso anterior de Calibre. No se los
considerará una fuente autoritativa del catálogo.

## Biblioteca visible

Se encontraron 201 directorios `.sdr`. Entre los archivos de contenido visibles
hay 159 KFX, 10 PDF, 6 AZW3 y 5 AZW. `My Clippings.txt` es el único archivo TXT.

Familias de datos laterales observadas:

| Formato del documento | Archivos laterales característicos |
| --- | --- |
| KFX | `.mf`, `.meta`, `.yjf`, `.yjr` |
| PDF | `.mf`, `.meta`, `.pds`, `.pdt` |
| AZW3 | `.mf`, `.meta`, `.azw3f`, `.azw3r` |

La presencia y el tamaño de esos archivos varían por documento. Algunos tienen
copias con sufijo `.bad_file`; no deben tomarse como fuente válida sin comprobar
su función.

## Bases de datos candidatas

- `system/readingstreams/readingstreams.db`
- `system/fmcache/fmcache.db`
- `system/vocabulary/vocab.db`
- `system/isd.db`
- `system/Search Indexes/Index.db`

La siguiente etapa inspeccionará solamente sus esquemas antes de consultar filas.

