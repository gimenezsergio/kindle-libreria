# Disponibilidad de colecciones

## Resultado local

No se encontró una fuente visible de colecciones en el almacenamiento USB
exportado por este Kindle.

Comprobaciones realizadas:

- búsqueda de rutas y archivos con nombres relacionados con colecciones;
- búsqueda de los archivos históricos `collections.json` y variantes en SQLite
  o JSON;
- inspección por tipo de `system/cmm` y `system/kindleCurator`;
- búsqueda textual de términos relacionados, excluyendo los índices de búsqueda
  y `My Clippings.txt` para evitar falsos positivos y datos privados.

`system/cmm/home` contiene únicamente 243 imágenes JPEG y 2 PNG. El único archivo
no gráfico relevante es `system/kindleCurator/data/config`, una serialización
Java pequeña; no hay una base de catálogo o colecciones acompañante visible.

## Conclusión provisional

Las colecciones de este modelo parecen residir fuera del almacenamiento USB
exportado, posiblemente en almacenamiento interno no publicado o en datos
sincronizados por Amazon. Esto no demuestra que sean irrecuperables por cualquier
método, pero sí que no hay una fuente local evidente compatible con nuestra
restricción actual de lectura por USB.

El catálogo independiente deberá poder mantener categorías propias. Si en el
futuro se encuentra una fuente autorizada y estable de colecciones de Amazon,
podrá incorporarse como una capa adicional sin convertirla en la identidad
principal del catálogo.

