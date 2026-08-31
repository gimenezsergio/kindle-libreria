# Formatos laterales de lectura

## Familias observadas

### Kindle Reader Data Store (KRDS)

Los archivos `.yjf`, `.yjr`, `.azw3f`, `.azw3r`, `.pds`, `.pdt`, `.mbp1` y
`.mbs` comparten la firma binaria `00 00 00 00 00 1a b1 26`. Corresponden al
contenedor Kindle Reader Data Store, una serialización tipada de Amazon.

La asociación observada es:

| Contenido principal | Progreso y temporizador | Estado y anotaciones |
| --- | --- | --- |
| KFX | `.yjf` | `.yjr` |
| AZW3 | `.azw3f` | `.azw3r` |
| PDF | `.pdt` | `.pds` |
| AZW/MOBI anterior | `.mbs` | `.mbp1` |

Fuentes técnicas consultadas:

- [Documentación del formato KRDS](https://github.com/zevisvei/kindle-reading-dashboard/blob/main/docs/KRDS-format.md)
- [Implementación de referencia en Python](https://github.com/zevisvei/kindle-reading-dashboard/blob/main/reading-metadata/scripts/krds.py)
- [Representación KRDS en Rust](https://docs.rs/kindle_formats/latest/kindle_formats/)

## Cobertura local de progreso

Hay 185 archivos de progreso. Los 185 contienen `lpr` (última posición leída).
Además:

- 84 contienen `fpr` (máxima posición alcanzada);
- 73 contienen `timer.model` (tiempo, palabras y modelo de ritmo);
- 84 contienen `page.history.store`;
- 56 tienen un historial de páginas no vacío.

`lpr` aporta una posición interna, no un porcentaje listo para mostrar. Para
calcular un porcentaje comparable entre formatos será necesario conocer la
extensión o mapa de posiciones de cada libro. `timer.model.totalPercent` mide el
modelo de lectura por palabras y no debe asumirse automáticamente como progreso
actual.

## Cobertura local de anotaciones

Hay 84 archivos KRDS de estado/anotaciones y todos contienen
`annotation.cache.object`.

Hay 60 archivos con anotaciones y 24 cachés vacías. El analizador público
interpretó semánticamente 61 archivos —incluida una caché vacía codificada con
contador cero—, pero falló con otras 23 cachés representadas como objeto sin
valores. La implementación propia acepta ambas representaciones. No son
anotaciones inaccesibles ni evidencia de una variante nueva con datos adicionales.

Los totales presentes en los sidecars KRDS son:

- 5.216 subrayados;
- 48 notas;
- 28 marcadores.

`My Clippings.txt` contiene más anotaciones que los sidecars actualmente
disponibles: 7.156 subrayados, 53 notas y 42 marcadores. Por ello debe considerarse
un historial acumulativo más amplio, mientras que KRDS representa el estado local
de los libros presentes y aporta posiciones, fechas y asociación directa con cada
archivo. El futuro lector KRDS deberá tratar una caché vacía como cero anotaciones.

## Otros formatos

### `.asc`

JSON legible con claves `bookInfo`, `data`, `layouts`, `widgets` y
`bottomSheetEnabled`. Parece contenido auxiliar enriquecido y no una fuente
principal de progreso.

### `.han`

JSON legible con checksum `md5` y un `payload`. Su función exacta queda pendiente
de estudiar sin exponer el contenido del payload.

### `.phl`

XML comprimido con gzip. El nodo raíz es `popular` y contiene elementos
`annotation`; corresponde a subrayados populares o comunitarios y no debe
confundirse con anotaciones personales.

## Herramienta temporal

Para validar la estructura se utilizó una copia temporal del analizador KRDS
bajo `work/`. Esa carpeta está excluida de Git. La herramienta se revisó antes de
usarla y se invocó como biblioteca, evitando su modo de línea de comandos, que
intentaría escribir un JSON junto al archivo de entrada.
