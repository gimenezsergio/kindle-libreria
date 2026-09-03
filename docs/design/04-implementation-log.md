# Bitácora del rediseño editorial

## 2026-09-03 — Referencias y decisiones

- Problema: la interfaz funcional había crecido sin una jerarquía consistente.
- Referencia: diez maquetas de Stitch (cinco superficies, escritorio y móvil).
- Decisión: conservar lenguaje editorial y reimplementar sin Tailwind ni datos ficticios.
- Resultado: evaluación, sistema visual y mapa de páginas versionados.

## Plantilla para continuaciones

```text
Fecha:
Objetivo:
Problema anterior:
Referencia utilizada:
Decisiones tomadas:
Funciones reales preservadas:
Elementos descartados:
Archivos modificados:
Pruebas ejecutadas:
Resultado visual:
Commit:
Pendientes:
```

Cada cambio visual posterior debe agregar aquí su resultado y el commit que lo
introdujo. Las decisiones abandonadas también se registran para evitar repetir
experimentos sin contexto.

## 2026-09-03 — Sistema visual y cinco superficies

- Objetivo: aplicar la dirección Stitch sin incorporar su código demostrativo.
- Decisiones: CSS propio, tipografías locales, un DOM responsive y datos reales.
- Implementación: encabezado editorial, navegación móvil, grilla del catálogo,
  paneles y métricas, ficha con pestañas, acompañante, perfiles y portadas.
- Preservado: todos los identificadores y contratos usados por JavaScript y API.
- Descartado: Tailwind, CDN, pantallas duplicadas, métricas y acciones ficticias.
- Pruebas: 80 automatizadas y navegación visual en escritorio y 390 × 844 px.
- Commit de interfaz: `8477b3e`.
- Pendiente: observación de uso real y ajustes de densidad según contenido propio.
