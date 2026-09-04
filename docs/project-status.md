# Estado del proyecto y próximos pasos

## Estado actual

El MVP local está terminado. El Kindle funciona como fuente de solo lectura y
la biblioteca conserva sus datos en SQLite fuera del dispositivo.

Actualmente se puede:

- inventariar y sincronizar incrementalmente un Kindle conectado por USB;
- recuperar obras, ediciones, autores, progreso, subrayados, notas y marcadores;
- reconciliar Clippings con KRDS/HAN sin perder la procedencia;
- conservar libros ausentes y su historial sin borrarlos;
- editar títulos visibles sin modificar la identidad Kindle;
- elegir portadas propias;
- crear categorías, notas propias y relaciones entre obras;
- conversar sobre una lectura usando perfiles configurables de IA;
- priorizar fichas de autores y títulos mencionados explícitamente antes de
  completar el contexto de IA con coincidencias temáticas;
- exportar paquetes remotos validados sin incluir los archivos de los libros;
- recibir paquetes de forma autenticada, transaccional e idempotente;
- reenviar paquetes pendientes mediante el comando `push`;
- crear respaldos SQLite consistentes, verificables y privados.

La suite actual contiene 80 pruebas automatizadas.

## Sincronización remota

La arquitectura local y el protocolo están implementados. La computadora donde
se conecta el Kindle ejecutará el agente Python y enviará por HTTPS los datos
derivados al servidor. La ubicación física del servidor no altera las fechas:
el agente conserva el valor original, la zona del Kindle y UTC cuando puede
determinarlo con confianza.

La implementación remota está completa hasta la preparación del despliegue:

1. Arquitectura y contrato: terminado.
2. JSON Schema y validación: terminado.
3. Exportador local: terminado.
4. Receptor autenticado y transaccional: terminado.
5. Pruebas de fallos, reenvíos y ausencias: terminado.
6. Comando manual `push`: terminado.
7. Respaldo y guía de migración: terminado.
8. Despliegue real e integración con OpenClaw: pendiente.

El paso 8 requiere dirección y acceso SSH al servidor, sistema operativo,
dominio o red privada, proxy existente y método de instalación de OpenClaw. No
se debe publicar la interfaz antes de resolver autenticación web, HTTPS y
rollback.

## Trabajo obligatorio antes de publicar

- Incorporar autenticación para toda la interfaz web. El endpoint de
  sincronización ya tiene token propio, pero la biblioteca visible todavía no.
- Ejecutar Flask detrás de un servidor WSGI de producción.
- Configurar HTTPS mediante un proxy inverso o una red privada.
- Establecer copias periódicas y probar restauraciones.
- Trasladar SQLite y las portadas locales con verificación de integridad.
- Mantener separados el usuario del servicio, OpenClaw y sus secretos.
- Conectar OpenClaw mediante una API limitada, no mediante acceso directo a SQLite.

## Mejoras posteriores no bloqueantes

- Incorporar búsqueda semántica para el acompañante de lectura. La versión
  actual ordena coincidencias textuales de forma determinista; una etapa futura
  debería generar representaciones vectoriales de títulos, subrayados, notas,
  categorías y relaciones para recuperar conexiones conceptuales aunque no
  compartan las mismas palabras. La selección recuperada debe seguir siendo
  pequeña, visible, editable y trazable mediante el tipo de fuente, la obra y
  la posición de lectura disponibles. La IA conversacional no debe acceder indiscriminadamente a toda la
  biblioteca ni reemplazar el algoritmo de recuperación. Antes de implementarlo
  habrá que decidir el modelo de embeddings, dónde se ejecuta, cómo se actualiza
  incrementalmente y qué datos privados pueden salir del servidor.
- Interfaz visual para iniciar y revisar sincronizaciones.
- Ejecución automática al conectar el Kindle.
- Transporte incremental real; el primer paquete actual contiene toda la
  información derivada.
- Administración y rotación del token de sincronización.
- Resolución manual de identidades ambiguas.
- Completar las portadas del resto de la biblioteca.
- Profundizar las relaciones y preguntas sugeridas por IA.
- Recuperar categorías Kindle si aparece una fuente USB confiable.
- Probar otros dispositivos y bibliotecas de mayor tamaño.

## Archivos de portada pendientes

Existen tres imágenes descargadas que permanecen deliberadamente fuera de Git:

```text
src/biblioteca_kindle/static/covers/8731def6-ol-12331013.jpg
src/biblioteca_kindle/static/covers/8731def6-ol-12333440.jpg
src/biblioteca_kindle/static/covers/8731def6-ol-13721029.jpg
```

Antes de versionarlas hay que confirmar si son candidatas que la aplicación
debe conservar o resultados temporales de búsqueda. No forman parte de los
commits funcionales actuales.

## Documentos relacionados

- `docs/remote-sync-contract.md`: protocolo agente-servidor.
- `docs/server-migration.md`: respaldo y traslado inicial.
- `docs/sync-contract.md`: sincronización USB local.
- `docs/mvp-scope.md`: alcance del MVP.
