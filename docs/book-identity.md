# Identidad y reconciliación de libros

## Principio

La biblioteca tendrá un identificador interno propio e inmutable. Ningún campo de
Amazon, nombre de archivo o título será por sí solo la clave primaria. Cada libro
podrá tener varios identificadores externos tipados y varias ediciones o entregas.

## Identidad de entrega Kindle

Hay 173 manifiestos `.mf`, todos JSON. Cada uno contiene un `content.id` único y
un `content.type`. En los 173 casos:

- `content.id` aparece en el nombre del libro;
- `content.id` aparece en el nombre de su directorio `.sdr`;
- existe un archivo de contenido con el mismo nombre base que el `.sdr`.

Distribución:

| Tipo | Cantidad | Forma del identificador |
| --- | ---: | --- |
| `kindle.pdoc` | 171 | token alfanumérico de 32 caracteres |
| `kindle.ebook` | 2 | ASIN de 10 caracteres |

Este identificador es excelente para unir contenido, `.sdr`, progreso y
anotaciones locales. Representa una entrega Kindle, no necesariamente una obra o
edición editorial universal.

## Manifiestos y metadata de descarga

- `.mf`: identidad de contenido, tipo y recursos de entrega.
- `.meta`: ETag y fechas de descarga bajo claves opacas.

`.meta` es útil para detectar cambios técnicos, pero no debe usarse como identidad
del libro.

## `vocab.db`

Contiene 61 libros con `id`, `asin` y `guid`. En 54 casos el campo denominado
`asin` coincide con `content.id`. Para documentos personales ese valor es el token
PDOC de 32 caracteres, no un ASIN comercial.

Por ello los identificadores deben almacenarse con espacio de nombres y tipo de
contenido, por ejemplo:

- `kindle_content_id` + `kindle.pdoc`;
- `asin` + `kindle.ebook`;
- `kindle_vocab_id`;
- `kindle_vocab_guid`.

No se debe validar todo campo `asin` como si tuviera siempre diez caracteres.

## Miniaturas

Solo los dos ASIN de ebooks coinciden directamente con miniaturas del dispositivo.
Las 15 miniaturas nombradas mediante UUID no enlazan con archivos actuales,
manifiestos ni `vocab.db`; tres aparecen en el catálogo histórico de Calibre.
Parecen caché histórica o recursos de elementos no presentes y no deben crear
automáticamente libros activos.

## `My Clippings.txt`

Sus 68 encabezados distintos se compararon mediante normalización de mayúsculas,
acentos, puntuación y el paréntesis final habitual de autor:

| Fuente candidata | Encabezados vinculados | Ambigüedad dentro de la fuente |
| --- | ---: | ---: |
| `vocab.db` | 58 | 0 |
| archivos actuales | 56 | 1 |
| caché histórica de Calibre | 12 | 1 |
| combinación de fuentes | 67 | — |

El único encabezado no resuelto debe importarse como registro provisional con su
texto original. El título normalizado es un alias útil, pero nunca una clave
estable: títulos repetidos, traducciones, ediciones y cambios de nombre pueden
producir colisiones.

## Calibre

`metadata.calibre` contiene 40 entradas y solo 11 rutas coinciden con contenido
actual. Puede aportar pistas históricas, pero tiene baja autoridad y no debe
sobrescribir metadata confirmada por manifiestos o archivos presentes.

## Estrategia propuesta

1. Crear un identificador interno de libro u obra.
2. Representar cada descarga Kindle como una edición/entrega asociada.
3. Unir determinísticamente archivo, `.sdr` y manifiesto mediante nombre base y
   `content.id`.
4. Adjuntar identificadores externos con tipo, fuente y nivel de confianza.
5. Vincular `vocab.db` por su `asin` cuando coincida con `content.id`.
6. Vincular clippings por aliases normalizados, exigiendo desambiguación cuando
   haya más de un candidato.
7. Mantener registros provisionales para clippings históricos sin archivo actual.
8. Tratar Calibre y miniaturas huérfanas como evidencia auxiliar, no autoritativa.

