# Evaluación del diseño de Stitch

## Lo adoptado

- estética editorial cálida inspirada en papel, tinta y marginalia;
- combinación de serif para lectura y sans serif para interfaz;
- paleta marfil, terracota, verde profundo y bordó;
- catálogo centrado en portadas y títulos;
- ficha de libro organizada por áreas en vez de una única columna extensa;
- fuentes del acompañante visibles mediante referencias `[B1]`, `[B2]`;
- navegación móvil persistente y controles táctiles amplios;
- bordes finos y jerarquía tipográfica en lugar de sombras excesivas.

## Lo descartado

- Tailwind, dependencias CDN y HTML diferente para cada tamaño de pantalla;
- métricas o funciones no implementadas: cifrado, precisión hermenéutica,
  temperatura por perfil, tokens, exportaciones y generación de portadas;
- porcentajes de progreso cuando el Kindle no los expone con confianza;
- lenguaje excesivamente académico que dificulta tareas habituales;
- `maximum-scale=1`, porque impide el zoom accesible.

## Criterio

Se adopta el lenguaje visual, no la maqueta literalmente. Toda afirmación visible
debe provenir de SQLite o expresar con honestidad que el dato no está disponible.
