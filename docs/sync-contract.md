# Contrato de sincronización de solo lectura

## Invariantes

1. El Kindle nunca recibe escrituras, eliminaciones ni renombres.
2. La sincronización se inicia solo si el punto de montaje existe.
3. Se registra si el montaje es `ro`; si es escribible, el proceso sigue usando
   únicamente aperturas de lectura y muestra una advertencia.
4. Los archivos fuente se leen en el dispositivo y los resultados derivados se
   guardan fuera de él.
5. Los datos privados extraídos no se incorporan a Git.
6. Una ejecución interrumpida no publica una instantánea parcial como completa.

## Flujo propuesto

1. Detectar dispositivo y montaje.
2. Crear una instantánea en estado `running`.
3. Inventariar fuentes por ruta relativa, tamaño, fecha y huella.
4. Reutilizar resultados cuando la huella y la versión del parser no cambiaron.
5. Interpretar manifiestos, metadata, KRDS, vocabulario y clippings por separado.
6. Resolver identidades mediante reglas determinísticas y generar candidatos para
   coincidencias débiles.
7. Insertar nuevas observaciones sin sobrescribir el historial.
8. Reconciliar anotaciones conservando ocurrencias por fuente.
9. Marcar como ausentes las entregas no vistas solo al completar correctamente el
   inventario total; nunca borrar sus datos históricos.
10. Cerrar la instantánea con estado, advertencias y contadores.

## Idempotencia

Repetir una sincronización sin cambios debe producir:

- cero entregas duplicadas;
- cero ocurrencias de anotación duplicadas;
- una nueva instantánea opcional, o reutilización explícita de la anterior;
- los mismos enlaces determinísticos;
- ninguna pérdida de notas, colecciones o relaciones propias.

Las claves de deduplicación no dependen únicamente de fecha de modificación. Se
basan en identificadores tipados y huellas del registro original.

## Conflictos

- Clippings presente y KRDS ausente: conservar como anotación histórica.
- KRDS presente y clippings ausente: conservar como anotación local actual.
- Texto o posición diferentes: mantener ambas ocurrencias y elegir una vista
  preferida mediante reglas explícitas.
- Dos libros candidatos para un encabezado: no fusionar; solicitar resolución.
- Libro antes presente y ahora ausente: cambiar presencia, no eliminar.
- Metadata contradictoria: conservar afirmaciones con procedencia y elegir el
  valor preferido por autoridad y confirmación manual.

## Privacidad

Los informes versionados solo incluyen estructura, contadores y conclusiones. Los
textos de libros, subrayados, notas, nombres de cuenta y volcados completos de
bases de datos permanecen en almacenamiento local excluido de Git.

