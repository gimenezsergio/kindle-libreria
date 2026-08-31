# Alcance de la primera versión

## Resultado buscado

La primera versión será una herramienta local capaz de leer el Kindle conectado,
actualizar una base SQLite fuera del dispositivo y producir un resumen verificable
del catálogo, estado de lectura y anotaciones. No necesita todavía una interfaz
gráfica completa.

El éxito del MVP consiste en demostrar que podemos sincronizar repetidamente los
datos reales de este Kindle sin escribirle, sin duplicar información y sin perder
procedencia.

## Incluido

### 1. Detección segura

- aceptar un punto de montaje indicado explícitamente;
- comprobar que existe y que parece un volumen Kindle;
- registrar si está montado en modo de solo lectura;
- abrir fuentes exclusivamente para lectura;
- rechazar rutas de salida ubicadas dentro del Kindle.

La autodetección cómoda de múltiples dispositivos puede añadirse después. Para el
MVP, una ruta explícita reduce ambigüedad y riesgo.

### 2. Inventario e instantáneas

- crear una instantánea de sincronización;
- inventariar contenido, `.sdr`, manifiestos y fuentes relevantes;
- guardar ruta relativa, tamaño, fecha y huella;
- distinguir instantánea completa de ejecución fallida;
- marcar entregas ausentes solo tras completar un inventario total.

### 3. Catálogo e identidad

- importar manifiestos `.mf`;
- crear entregas Kindle con `content.id`, tipo y formato;
- asociar determinísticamente archivo y `.sdr`;
- enriquecer con `vocab.db` cuando su `asin` coincida con `content.id`;
- crear obra y edición provisionales cuando falte metadata;
- mantener alias de título para clippings;
- conservar el encabezado no resuelto como registro provisional.

El caché de Calibre solo podrá aportar candidatos de baja confianza; no podrá
fusionar ni sobrescribir automáticamente.

### 4. Estado de lectura

- importar `lpr` para KFX, AZW3, PDF y AZW/MOBI;
- importar `fpr` cuando exista;
- guardar fechas nativas asociadas;
- conservar posición y tipo sin transformación;
- importar tiempo y palabras del temporizador como métricas separadas;
- mantener instantáneas históricas.

El campo de porcentaje quedará nulo salvo que un método específico sea validado.

### 5. Anotaciones

- importar las 7.251 entradas actuales de `My Clippings.txt`;
- clasificar highlight, note y bookmark;
- conservar encabezado, metadata, posición, fecha y texto;
- importar anotaciones KRDS cuando el sidecar exista;
- tratar cachés KRDS vacías como cero anotaciones;
- reconciliar fuentes solo cuando la regla sea determinística;
- mantener ocurrencias separadas cuando exista duda;
- registrar `.han` como fuente paralela vinculada por `content.id`, sin sumarla
  automáticamente a KRDS.

### 6. Organización mínima propia

- crear colecciones propias;
- asignar obras a colecciones;
- crear notas personales asociadas a una obra;
- crear relaciones entre dos obras con tipo y explicación.

No se intentará reflejar estos datos en el Kindle ni en Amazon.

### 7. Consulta verificable

Una interfaz de línea de comandos o reporte local deberá poder mostrar:

- resumen de la última sincronización;
- cantidad de obras, ediciones y entregas;
- libros presentes y ausentes;
- anotaciones por tipo y fuente;
- advertencias, registros provisionales y conflictos;
- ficha textual de una obra sin volcar datos privados por defecto.

## Postergado

- interfaz web o aplicación gráfica completa;
- autenticación o API de Amazon;
- escritura, transferencia o modificación del Kindle;
- conversión de libros;
- sincronización bidireccional;
- recuperación automática de colecciones Kindle;
- porcentajes universales de progreso;
- importación exhaustiva de telemetría de `fmcache.db`;
- portadas personalizadas y búsqueda de portadas externas;
- análisis semántico automático de temas o símbolos;
- sincronización entre varias computadoras;
- soporte general para modelos Kindle no observados;
- resolución automática de todas las ediciones y duplicados.

## Criterios de aceptación

### Seguridad

- ninguna prueba ni sincronización escribe dentro del punto de montaje;
- la salida siempre queda en el directorio local configurado;
- una ruta de base de datos dentro del Kindle es rechazada;
- una ejecución incompleta no marca contenido como ausente.

### Datos

- se reconocen los 173 manifiestos actuales;
- cada manifiesto enlaza un archivo y su `.sdr`;
- se importan las 7.251 entradas de clippings sin pérdidas silenciosas;
- se reconocen 185 estados con `lpr` y 84 con `fpr`;
- los 23 caches KRDS vacíos no generan errores;
- las anotaciones importadas conservan fuente y huella;
- el encabezado de clippings no resuelto permanece visible como provisional.

Estas cantidades son fixtures de aceptación para el dispositivo actual, no
constantes del producto.

### Idempotencia

Dos sincronizaciones consecutivas sin cambios deben producir:

- las mismas obras, ediciones y entregas;
- cero duplicados nuevos de clippings o KRDS;
- cero fusiones adicionales no explicadas;
- una segunda instantánea válida o reutilización explícita de la primera;
- ningún cambio en colecciones, notas o relaciones propias.

### Trazabilidad

- cada entrega importada apunta a una observación fuente;
- cada estado de lectura indica sidecar, formato y momento de observación;
- cada anotación conserva al menos una ocurrencia de fuente;
- las advertencias de parseo quedan registradas sin incluir texto privado.

## Orden de implementación

1. Esquema SQLite y migraciones.
2. Capa de instantáneas e inventario seguro.
3. Manifiestos y entregas Kindle.
4. Catálogo parcial desde `vocab.db`.
5. Parser e importación de `My Clippings.txt`.
6. Lector KRDS de progreso.
7. Lector KRDS y HAN de anotaciones.
8. Reconciliación e idempotencia.
9. Colecciones, notas y relaciones propias.
10. Reporte local y pruebas de aceptación con snapshots sanitizados.

Cada punto tendrá un commit funcional separado y pruebas proporcionales al riesgo.

