# Validación integral con el Kindle real

Fecha: 2026-08-31.

## Protección aplicada

El montaje automático del sistema exponía el dispositivo como `rw`. Para no
depender de esa configuración, cada sincronización se ejecutó dentro de un
espacio de montaje aislado con una vista *bind* remontada `ro`. El kernel confirmó
la opción `ro` antes de abrir las fuentes. La base SQLite se guardó fuera del
dispositivo, en `work/library.sqlite3`, y está excluida de Git.

## Primera sincronización

- fuentes inventariadas: 811;
- manifiestos: 173;
- entradas de `My Clippings.txt`: 7.251;
- estados de lectura vinculados: 170;
- anotaciones locales nuevas desde KRDS/HAN: 5.308;
- entregas marcadas ausentes: 0.

## Segunda sincronización

La misma operación se repitió sobre el dispositivo sin cambios:

- fuentes inventariadas: 811;
- manifiestos: 173;
- entradas de `My Clippings.txt`: 7.251;
- estados de lectura vinculados: 170;
- anotaciones locales nuevas: 0;
- entregas marcadas ausentes: 0.

Esto confirma la idempotencia con los datos reales observados: la segunda
ejecución no creó anotaciones duplicadas.

## Estado resultante del catálogo

- obras: 186;
- ediciones: 186;
- entregas presentes: 173;
- anotaciones: 12.559 (12.388 subrayados, 101 notas y 70 marcadores);
- ocurrencias por fuente: 7.251 clippings, 5.120 KRDS y 188 HAN;
- registros de historial de lectura: 250;
- observaciones con advertencias o fallos: 0;
- entregas huérfanas: 0;
- comprobación de integridad SQLite: `ok`.

Las 185 obras provisionales y la obra marcada para revisión son deuda explícita
de reconciliación de identidad, no errores de integridad. No se intentó resolver
automáticamente casos ambiguos.
