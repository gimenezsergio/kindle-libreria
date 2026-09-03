# Accesibilidad y validación visual

## Criterios incorporados

- zoom móvil permitido por el `viewport` estándar;
- foco visible de alto contraste;
- controles con altura táctil aproximada de 44 px;
- navegación principal semántica y barra inferior móvil;
- pestañas con roles, `aria-selected`, `aria-controls` y flechas izquierda/derecha;
- regiones ocultas retiradas también del árbol accesible mediante `hidden`;
- etiquetas persistentes en formularios y estados con `aria-live` ya existentes;
- alternativas tipográficas locales, sin depender de una CDN;
- títulos extensos limitados visualmente sin alterar el texto accesible.

## Validación realizada

El 3 de septiembre de 2026 se comprobaron con el servidor y la base reales:

- catálogo con 24 obras por página y 186 obras totales;
- navegación y carga sin errores de consola;
- composición móvil a 390 × 844 px;
- barra inferior visible y navegación de escritorio oculta en móvil;
- ficha de `1984` con una sola región activa al cambiar pestañas;
- apertura correcta de Memoria, Cuaderno y Acompañante;
- resumen, perfiles y portadas en tamaño móvil;
- suite completa de 80 pruebas automatizadas.

La verificación no creó notas, relaciones, perfiles ni selecciones de portadas y
no envió conversaciones a ningún proveedor de IA.
