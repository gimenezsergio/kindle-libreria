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

## 2026-09-03 — Mesa de trabajo del acompañante

- Problema anterior: historial, selección de material, búsqueda y compositor se
  apilaban verticalmente; para escribir había que abandonar visualmente el chat.
- Decisión: usar una mesa de trabajo con navegación de conversaciones, chat y
  panel lateral de fuentes.
- Implementación: el compositor permanece al pie del historial, las fuentes
  tienen scroll independiente y un contador muestra cuántos fragmentos están
  adjuntos. El acompañante puede usar hasta 96 rem de ancho.
- Móvil: el material pasa a una sección plegable y el chat usa todo el ancho.
- Preservado: contratos de API, identificadores del DOM y reglas que determinan
  qué contexto se envía a la IA.
- Pendiente: validar la densidad de la columna lateral con conversaciones reales.

## 2026-09-03 — Simplificación del acompañante

- Observación de uso: la lista permanente de conversaciones restaba ancho y el
  panel lateral reunía demasiados controles dentro de varios scrolls anidados.
- Navegación: la lista lateral se reemplazó por un selector compacto que informa
  el nombre de la conversación y su cantidad de mensajes.
- Proveedor: el aviso descriptivo se convirtió en una insignia desplegable; la
  explicación sobre el envío de datos sigue disponible sin ocupar una franja.
- Contexto visible: el lateral muestra solamente los fragmentos adjuntos, permite
  retirarlos y resume el estado de la búsqueda bibliotecaria.
- Selección: `Agregar material` abre un diálogo amplio —pantalla completa en
  móvil— con búsqueda textual, pestañas, referencias de posición y selección
  múltiple para todas las anotaciones y notas propias.
- Complejidad progresiva: alcance bibliotecario, resultados sugeridos y paquete
  exacto enviado a la IA permanecen plegados hasta que el lector los necesita.
- Scroll: el panel lateral dejó de desplazarse internamente; solo el historial y
  el selector temporal administran colecciones largas.
- Preservado: almacenamiento del contexto, recuperación bibliotecaria, perfiles,
  proveedor y contratos de respuesta de la API.

## 2026-09-04 — Cabecera compacta del libro

- Problema anterior: el título, los contadores y tres tarjetas de metadatos
  ocupaban gran parte de la primera pantalla antes de llegar a las pestañas.
- Decisión: tratar el libro como contexto de trabajo y no como una portada de
  presentación independiente.
- Implementación: portada pequeña, título de escala moderada, autor y una línea
  con presencia, anotaciones, idioma y actividad.
- Los datos de edición, seguimiento, organización y edición del título pasaron a
  `Detalles del documento`, disponible bajo demanda.
- Las pestañas quedaron inmediatamente después de la cabecera.
- Móvil: portada reducida, resumen abreviado y detalles apilados al desplegarse.
- Preservado: todos los datos anteriores; cambió su jerarquía, no su contenido.

## 2026-09-04 — Respuesta en curso del acompañante

- Problema anterior: al enviar una consulta, la única señal de actividad era el
  botón deshabilitado y no resultaba claro si la IA seguía trabajando.
- Implementación: el mensaje propio aparece inmediatamente y el acompañante
  agrega una burbuja temporal con su nombre, el texto `Está pensando` y tres
  puntos animados. El historial se desplaza hasta ese intercambio.
- El botón muestra `Pensando…` mientras espera y recupera su estado al terminar.
- Si el proveedor falla, la burbuja temporal se convierte en un error visible y
  el texto escrito permanece en el compositor para poder revisarlo o reenviarlo.
- Accesibilidad: el estado se anuncia mediante `role=status` y la animación se
  desactiva cuando el sistema solicita movimiento reducido.

## 2026-09-04 — Referencias bibliográficas legibles

- Problema anterior: los códigos temporales `[B1]`, `[B2]` y similares no
  explicaban por sí mismos a qué material se refería el acompañante.
- Decisión: conservar la trazabilidad interna sin trasladar sus identificadores
  técnicos al lenguaje de la conversación.
- El prompt presenta cada evidencia por tipo, obra y posición disponible, y le
  pide a la IA que la mencione naturalmente: por ejemplo, `Según un subrayado de
  La sociedad del cansancio…`.
- El detalle desplegable de cada respuesta usa el mismo formato humano y sigue
  conservando la instantánea exacta del fragmento consultado.
- Las posiciones técnicas provenientes de Kindle también se presentan como
  `Página 12` o `Ubicación 122–123`.
- Las respuestas históricas no se reescriben en SQLite: al mostrarlas, la
  interfaz traduce sus códigos antiguos usando las fuentes preservadas en cada
  mensaje. Si la fuente ya no está disponible, muestra `Fuente de la biblioteca`.

## 2026-09-04 — Canal Telegram preparado para OpenClaw

- Se separó la recuperación bibliotecaria de la capa web para reutilizar el
  mismo algoritmo desde otros canales.
- Se creó una API privada versionada con token exclusivo para catálogo,
  perfiles, conversaciones, contexto y evidencia.
- Los turnos externos se preparan y completan en dos fases. SQLite conserva la
  pregunta, las fuentes exactas y la respuesta; repetir la finalización no
  duplica mensajes.
- Se generó un tool plugin con el comando oficial de OpenClaw. Declara doce
  herramientas, compila con TypeScript y pasa la validación del manifiesto.
- Se agregó un skill que enseña a resolver ambigüedades y a completar cada turno
  antes de responder por Telegram.
- La configuración del canal para un único Telegram user ID y la lista de
  comprobaciones del servidor quedaron documentadas sin secretos reales.
- Pendiente externo: instalar en el OpenClaw del servidor, configurar BotFather
  y ejecutar la prueba con la cuenta autorizada.
