# Accesos directos del acompañante de lectura

> Estado: Etapas 1 y 2 implementadas localmente. Las cinco acciones preparan
> un borrador editable; antes de enviarlo se puede revisar, sin mutaciones, el
> perfil, proveedor, alcance, material, fuentes recuperadas y paquete técnico.

## Por qué existe esta propuesta

El acompañante permite conversar mediante mensajes libres, pero no todas las
interacciones deberían exigir que el lector redacte un prompt. Algunas tareas
frecuentes —explicar una selección, detectar temas o explorar símbolos— pueden
ofrecerse como accesos directos sin crear un sistema distinto del chat.

El objetivo no es automatizar una interpretación definitiva de la obra, sino
reducir la fricción para iniciar una conversación útil y hacer visibles las
capacidades de la aplicación.

## Decisión de diseño

Cada acceso directo será una **receta de prompt** que crea un mensaje normal en
la conversación actual. La respuesta conservará el historial, el material
seleccionado, las fuentes recuperadas y la trazabilidad existentes.

La aplicación combinará estas capas:

```text
reglas comunes y salvaguardas
+ perfil de IA de la conversación
+ receta del acceso directo
+ material seleccionado y contexto recuperado
+ historial de la conversación
= solicitud al proveedor activo
```

El acceso directo define **qué tarea realizar**. El perfil define **cómo
acompañar al lector**: tono, enfoque, profundidad, tendencia a preguntar o
responder y aspectos que suele priorizar. El perfil no puede cambiar las
fuentes disponibles, inventar evidencia ni eludir las reglas de privacidad.

Cada conversación mantiene un único perfil. Los accesos directos usan el
perfil ya asociado a ella; no se vuelve a elegir en cada acción. Para abordar
la misma cuestión con otra voz, se crea otra conversación con otro perfil.

## Primer conjunto propuesto

La primera versión tendría cinco acciones:

1. **Explicar la selección**: aclarar el pasaje o la nota elegida y formular
   preguntas sobre ella.
2. **Detectar temas**: identificar asuntos recurrentes en el material
   disponible.
3. **Explorar símbolos**: proponer símbolos y motivos como hipótesis, no como
   hechos cerrados.
4. **Proponer preguntas**: generar caminos para continuar pensando la lectura.
5. **Relacionar con mi biblioteca**: buscar coincidencias y contrastes usando
   el mecanismo de recuperación de contexto de Biblioteca Kindle.

Posibles ampliaciones posteriores: personajes, conflictos, contexto histórico,
argumento y contraargumento, lectura alternativa, mapa de conceptos, síntesis
para recordar y rutas de lectura.

## Comportamiento de la interfaz

La sección se podría llamar **Explorar esta lectura**. Las cinco acciones
principales permanecerían visibles y una opción **Más formas de explorar**
agruparía acciones menos frecuentes.

La Etapa 1 muestra un bloque compacto en el chat con las cinco acciones. La
definición centralizada vive en `biblioteca_kindle.companion_actions` y se
expone a la interfaz mediante `GET /api/companion-actions`; no depende de
DeepSeek, OpenClaw ni de otro proveedor. Cada definición tiene identificador,
etiqueta, descripción, receta y requisitos de material y búsqueda.

Al pulsar una acción, se completa la caja de mensaje actual para que el lector
pueda editarla o descartarla antes de enviar. No se crea un turno ni se llama
al proveedor hasta usar **Enviar**. El perfil de la conversación vigente se
conserva sin cambios.

El alcance se muestra junto a las acciones antes de preparar el borrador:

- la ficha del libro siempre se incluye, y se informa si hay o no fragmentos
  adjuntos;
- la búsqueda de conexiones indica si está desactivada o qué alcance tiene;
- **Relacionar con mi biblioteca** activa la búsqueda solo si estaba apagada,
  pero respeta el alcance que ya hubiera elegido el lector;
- si la biblioteca no contiene el texto completo, la interfaz y la respuesta
  no deben sugerir que se analizó la obra íntegra.

No todas las acciones tienen que enviarse inmediatamente:

- las simples pueden ejecutarse con un clic;
- las interpretativas pueden completar la caja de mensaje para que el lector
  revise o precise la pregunta;
- las que necesitan una obra o alcance adicional pueden abrir una elección
  breve antes de ejecutarse.

El resultado siempre se registra como un turno normal del chat. De ese modo se
puede continuar conversando, revisar las fuentes y entender qué perfil produjo
la respuesta.

## Salvaguardas

Cada ejecución debe diferenciar:

1. evidencia recuperada de la biblioteca;
2. conocimiento general aportado por el modelo;
3. hipótesis o interpretación conversacional.

La selección exacta enviada al proveedor debe seguir siendo visible y
revisable. Ningún acceso directo debe guardar automáticamente una nota,
categoría o relación. Esas escrituras requieren confirmación humana.

## Ventajas y riesgos aceptados

Ventajas:

- reduce la necesidad de aprender a escribir prompts;
- descubre funciones que de otro modo quedarían ocultas;
- aplica contexto y salvaguardas de manera consistente;
- funciona con DeepSeek, OpenClaw u otro proveedor sin duplicar la lógica;
- puede trasladarse en el futuro a botones o comandos de Telegram.

Riesgos:

- demasiadas acciones pueden saturar el panel y quitar espacio al chat;
- una receta rígida puede producir respuestas repetitivas;
- el lector podría delegar demasiado pronto su propia interpretación;
- los nombres de las acciones pueden prometer más evidencia de la disponible;
- las consultas amplias pueden aumentar costo, latencia y volumen de contexto.

Por eso el primer alcance debe ser pequeño, editable y transparente.

## Estado de las etapas

- Etapa 1: catálogo, panel compacto, alcance visible y borradores editables:
  implementada.
- Etapa 2: perfil visible, revisión no mutante del próximo turno, fuentes y
  alcance reales, y trazabilidad opcional del atajo en el mensaje del usuario:
  implementada. El identificador y la etiqueta se guardan como snapshot
  nullable, sin acoplar la base al catálogo de recetas.
- Etapas posteriores: resultados persistentes, acciones personalizables,
  búsqueda semántica y Telegram: pendientes.

## Condiciones para considerar terminado el MVP

- Las cinco acciones aparecen sin desplazar ni reducir de forma importante el
  chat y el material para conversar.
- La acción usa el perfil de la conversación y la interfaz muestra cuál es.
- El lector conoce el alcance y puede revisar el texto que se enviará.
- La respuesta queda registrada como parte de la conversación.
- Las fuentes usadas conservan nombres y referencias legibles.
- La aplicación distingue evidencia, conocimiento general e interpretación.
- No se guarda ninguna conclusión como dato propio sin confirmación.
- El comportamiento se prueba con y sin material seleccionado, con recuperación
  de biblioteca activada y desactivada, y con al menos dos perfiles diferentes.

## Plan futuro por baby steps

1. Definir las cinco recetas y sus variables de contexto. **Hecho.**
2. Implementar el catálogo local de acciones, independiente del proveedor.
   **Hecho.**
3. Incorporar el bloque compacto **Explorar esta lectura**. **Hecho.**
4. Preparar el mensaje editable para las acciones interpretativas. **Hecho.**
5. Integrar material seleccionado y recuperación de biblioteca. **Hecho para
   el flujo existente; no hay recuperación semántica.**
6. Hacer visible el perfil que responderá y conservarlo por conversación.
   **Ya lo hacía la conversación; la etapa lo reutiliza.**
7. Mostrar alcance, procedencia y advertencias antes del envío. **Hecho:**
   `Revisar contexto` arma un turno hipotético con el borrador actual, sin
   guardar mensajes ni cambiar la selección persistida.
8. Registrar el turno y sus fuentes con el flujo normal del chat. **Hecho:**
   el mensaje de usuario puede conservar el id y la etiqueta del atajo; las
   fuentes continúan ligadas a la respuesta del asistente.
9. Probar accesibilidad, pantallas pequeñas, errores y estados de carga.
10. Documentar cómo agregar nuevas recetas sin modificar el proveedor.

Esta planificación debe revisarse contra la interfaz vigente antes de comenzar
la implementación.
