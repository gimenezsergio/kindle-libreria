# Formato de `My Clippings.txt`

El análisis se realizó sin registrar títulos ni textos de las anotaciones.

## Estructura observada

- Tamaño: 3.011.465 bytes.
- Codificación: UTF-8 con marca inicial (`UTF-8 BOM`).
- Separador de entradas: una línea `==========`.
- Entradas: 7.251.
- Encabezados distintos de obras o documentos: 68.
- Entradas con menos de dos líneas no vacías: ninguna.

Cada entrada contiene normalmente:

1. Encabezado textual del libro o documento.
2. Línea de metadata con tipo, página o ubicación y fecha.
3. Una línea vacía.
4. Texto del subrayado o nota, si corresponde.

## Tipos

| Tipo | Cantidad |
| --- | ---: |
| Subrayado | 7.156 |
| Nota | 53 |
| Marcador | 42 |

La metadata observada está en inglés y utiliza variantes como `page`, `location`
y `Location`. Existen entradas sin contenido textual, algo esperable para los
marcadores; las excepciones deberán conservarse y clasificarse sin descartarlas.

## Duplicados

No hay bloques exactamente duplicados entre las 7.251 entradas. Esto no descarta
duplicados semánticos: el mismo pasaje podría aparecer con diferencias de fecha,
ubicación, encabezado o espacios.

## Utilidad y limitaciones

Es una fuente muy viable para subrayados, notas y marcadores. Sin embargo, el
encabezado textual no es necesariamente un identificador estable del libro. La
vinculación deberá apoyarse, cuando sea posible, en ASIN, UUID, GUID o relaciones
con archivos `.sdr`; el encabezado normalizado quedará como estrategia secundaria.

