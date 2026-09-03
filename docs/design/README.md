# Rediseño editorial de Biblioteca Kindle

Este directorio registra cómo se construyó la interfaz, no solo su estado final.
La referencia inicial fue el paquete `stitch_redise_o_web_editorial_biblioteca_kindle.zip`,
generado con Google Stitch el 3 de septiembre de 2026.

## Recorrido

1. [`01-stitch-evaluation.md`](01-stitch-evaluation.md): evaluación de las maquetas.
2. [`02-design-decisions.md`](02-design-decisions.md): sistema visual y decisiones de producto.
3. [`03-page-mapping.md`](03-page-mapping.md): correspondencia entre pantallas y funciones reales.
4. [`04-implementation-log.md`](04-implementation-log.md): bitácora verificable de implementación.
5. [`05-accessibility-and-validation.md`](05-accessibility-and-validation.md): criterios y comprobaciones finales.

Los HTML de Stitch no son código fuente del producto: contienen Tailwind por CDN,
imágenes remotas, datos ficticios y pantallas separadas para escritorio y móvil.
La aplicación reimplementa la dirección visual con HTML semántico, CSS propio y
JavaScript Vanilla sobre los datos y contratos reales.
