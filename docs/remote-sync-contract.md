# Sincronización remota: agente local y servidor

## Decisión de arquitectura

Cuando Biblioteca Kindle se aloje junto a OpenClaw en un servidor remoto, el
navegador y el servidor no tendrán acceso directo al Kindle conectado por USB en
Argentina. La lectura del dispositivo debe ocurrir en la computadora donde está
conectado.

La solución se divide en dos procesos:

```text
Kindle USB (solo lectura)
        |
        v
Agente Python local
        |
        | HTTPS autenticado
        v
API de Biblioteca Kindle en el servidor
        |
        +-- SQLite y copias de seguridad
        +-- interfaz web
        +-- OpenClaw
```

La primera versión será manual. El usuario conectará el Kindle y ejecutará un
comando como:

```bash
biblioteca-kindle push
```

La detección automática al conectar el dispositivo queda fuera de esta primera
versión. El agente y el servidor se desarrollarán primero contra `localhost`.

## Responsabilidades

### Agente local

- Detectar el punto de montaje del Kindle.
- Confirmar la identidad del dispositivo y registrar si el montaje es `ro`.
- Abrir las fuentes del Kindle exclusivamente para lectura.
- Ejecutar los parsers actuales de manifiestos, Clippings, KRDS, HAN y progreso.
- Normalizar los datos y construir un paquete versionado.
- No incluir los archivos completos de los libros.
- Enviar el paquete por HTTPS y mostrar la respuesta del servidor.
- Conservar localmente el identificador y la huella del último paquete confirmado.
- Reintentar exactamente el mismo paquete cuando la respuesta sea incierta.

### Servidor

- Autenticar al agente antes de aceptar contenido.
- Validar esquema, versión, tamaños y tipos antes de abrir una transacción.
- Reconocer paquetes ya procesados sin volver a aplicar sus efectos.
- Aplicar el paquete completo dentro de una transacción SQLite.
- Reconciliar identificadores y procedencias con las reglas existentes.
- Aplicar ausencias únicamente después de aceptar una instantánea completa.
- Responder con los cambios producidos y los totales resultantes.
- Mantener categorías, portadas, notas propias, relaciones y conversaciones.

El servidor será la fuente principal de la biblioteca. La base auxiliar del
agente no reemplaza al servidor ni se copia sobre su SQLite.

## Unidad de transporte

Cada intento envía un paquete lógico completo, aunque el contenido pueda
comprimirse durante el transporte. La envoltura mínima será:

```json
{
  "schema_version": 1,
  "package_id": "uuid",
  "created_at_utc": "2026-09-03T13:30:00Z",
  "agent_id": "uuid-generado-en-la-PC",
  "device_key": "identificador-opaco",
  "snapshot": {
    "kind": "full",
    "started_at_utc": "2026-09-03T13:29:00Z",
    "completed_at_utc": "2026-09-03T13:29:40Z",
    "mount_read_only": true,
    "source_timezone": "America/Argentina/Buenos_Aires"
  },
  "entities": {
    "works": [],
    "editions": [],
    "contributors": [],
    "edition_contributors": [],
    "deliveries": [],
    "external_identifiers": [],
    "title_aliases": [],
    "device_snapshots": [],
    "source_observations": [],
    "annotations": [],
    "annotation_occurrences": [],
    "reading_states": [],
    "reading_history_records": []
  },
  "present_delivery_ids": [],
  "warnings": []
}
```

La versión inicial del contrato está expresada como JSON Schema en
`src/biblioteca_kindle/schemas/`. El validador local agrega comprobaciones
semánticas de identificadores, presencias y contenido prohibido. Los
identificadores de entidades serán las claves estables que ya usa la aplicación;
nunca números consecutivos dependientes de una base local.

## Sincronización inicial e incremental

La primera sincronización remota enviará el catálogo derivado necesario para
reconstruir el estado del servidor. No enviará EPUB, KFX, AZW, PDF ni otros libros.

En sincronizaciones posteriores el agente podrá omitir entidades cuya huella no
cambió, pero siempre enviará:

- una identificación inequívoca del paquete;
- la versión del contrato y de los parsers;
- los registros nuevos o modificados;
- todas las procedencias necesarias para verificarlos;
- el conjunto completo de entregas presentes en esa instantánea.

El conjunto completo de presencias permite detectar libros ausentes sin confundir
“no cambió y no fue enviado” con “ya no está en el Kindle”. Una ausencia cambia el
estado de la entrega; nunca elimina la obra ni su información histórica.

Si la captura local, la validación o la carga no finalizan, el servidor no aplica
ausencias. Una instantánea parcial jamás se presenta como completa.

## Idempotencia, reintentos y confirmación

`package_id` identifica un contenido inmutable. El agente calcula además una
huella del cuerpo canónico. El servidor guarda ambos valores junto al resultado.

- Mismo `package_id` y misma huella: devolver la confirmación original.
- Mismo `package_id` y otra huella: rechazar como conflicto.
- Entidades con identificadores ya conocidos: actualizar o reconocer, no duplicar.
- Corte antes de recibir confirmación: el agente reenvía el mismo paquete.
- Error de validación: no se abre la transacción.
- Error durante la aplicación: se revierte toda la transacción.

Una respuesta satisfactoria incluirá al menos:

```json
{
  "package_id": "uuid",
  "status": "applied",
  "changes": {
    "books_created": 0,
    "books_marked_absent": 0,
    "annotations_created": 12,
    "annotations_reconciled": 10
  },
  "totals": {
    "works": 186,
    "books_present": 173,
    "highlights": 8121,
    "notes": 59,
    "bookmarks": 50
  },
  "warnings": []
}
```

El agente solo registra el paquete como confirmado después de validar esta
respuesta.

## Tiempo y zonas horarias

El país del servidor no define la hora de una anotación. El agente conserva:

- el valor original extraído;
- la fuente que lo produjo;
- la zona IANA configurada para el Kindle, por ejemplo
  `America/Argentina/Buenos_Aires`;
- el instante normalizado en UTC cuando pueda determinarse con confianza.

El servidor almacena instantes normalizados en UTC. El navegador decide cómo
mostrarlos según la zona del usuario. Si una fuente no contiene información
suficiente para normalizarla, el valor queda explícitamente como hora local en
vez de inventar un UTC.

## Seguridad y privacidad

- Solo HTTPS; nunca aceptar tokens ni anotaciones por HTTP fuera de `localhost`.
- Token distinto de las claves de proveedores de IA y con permiso exclusivo de
  sincronización.
- Token guardado en variables de entorno o almacén de secretos, nunca en Git,
  SQLite exportada, URL ni registros.
- Límite de tamaño de solicitud y cantidad de registros.
- Comparación segura del token y rotación sin perder el catálogo.
- Registro de metadatos operativos sin guardar textos privados en logs.
- La API de sincronización no queda accesible a OpenClaw por defecto.
- Copia de seguridad consistente de SQLite antes de la primera importación real.

Un paquete contiene textos privados de subrayados y notas. HTTPS protege el
tránsito, no sustituye el control de acceso ni la protección del servidor.

## Configuración prevista del agente

```env
BIBLIOTECA_SERVER_URL=https://biblioteca.example.com
BIBLIOTECA_SYNC_TOKEN=secreto-independiente
KINDLE_TIMEZONE=America/Argentina/Buenos_Aires
```

El token nunca se acepta como argumento de línea de comandos porque podría
quedar visible en el historial o en la lista de procesos.

## Fuera de alcance del primer corte

- Escritura de cualquier clase sobre el Kindle.
- Transferencia de los archivos de los libros.
- Sincronización automática al conectar USB.
- Edición simultánea bidireccional de los datos propios.
- Exposición directa de SQLite por red.
- Acceso del navegador al dispositivo mediante APIs experimentales.

## Orden de implementación

1. Definir y probar el JSON Schema del paquete y la respuesta.
2. Crear el exportador local sin red y verificar que no incluya libros.
3. Crear el receptor local autenticado y transaccional. **Implementado.**
4. Probar reenvíos, cortes, paquetes corruptos y ausencias con `localhost`.
   **Implementado.**
5. Incorporar el comando `push` y su resumen legible. **Implementado.**
6. Preparar migración y copia de seguridad de la base actual.
7. Configurar HTTPS, secretos y despliegue en el servidor.
8. Conectar OpenClaw mediante una interfaz separada y de permisos limitados.

Los pasos 1 y 2 ya están implementados. El exportador se ejecuta sin red con:

```bash
PYTHONPATH=src python3 -m biblioteca_kindle export-sync \
  --database work/library.sqlite3 \
  --output work/sync-package.json \
  --agent-id UUID-ESTABLE-DE-ESTA-PC
```

El archivo contiene datos privados y debe permanecer dentro de `work/` o de otro
directorio protegido y excluido de Git. La huella e ID que muestra el comando
identifican exactamente el paquete que más adelante se reenviará por HTTPS.
La escritura es atómica y el archivo nuevo queda limitado al usuario local.

El receptor está disponible mediante `POST /api/sync/v1/packages`. Requiere
`Authorization: Bearer <token>`, valida el paquete antes de escribir y aplica
todos sus registros dentro de una única transacción. Un primer envío responde
`201 applied`; la repetición exacta responde `200 already_applied`. Reutilizar
el mismo ID con otro contenido se rechaza.

Para las pruebas locales se configura `BIBLIOTECA_SYNC_TOKEN` en `work/.env`.
El límite predeterminado es 32 MiB y puede reducirse con
`BIBLIOTECA_SYNC_MAX_BYTES`. En producción este endpoint solo se expondrá detrás
de HTTPS.

Las pruebas automatizadas verifican tokens ausentes, JSON truncado, cargas que
superan el límite, reenvíos exactos, reutilización conflictiva de IDs, rollback
por referencias inválidas y ausencias. Una ausencia conserva las anotaciones y
los datos propios; un paquete inválido no cambia presencias ni publica una
recepción parcial.

El comando manual completo es:

```bash
PYTHONPATH=src python3 -m biblioteca_kindle push /media/usuario/Kindle \
  --database work/library.sqlite3
```

Lee la configuración privada desde `work/.env`, ejecuta primero la sincronización
USB de solo lectura y luego realiza hasta tres intentos de entrega. Una falla de
red conserva `work/sync-agent/pending-sync-package.json`; una ejecución posterior
prioriza ese mismo paquete. Solo una confirmación válida y correspondiente a su
ID permite eliminarlo. HTTP se admite únicamente contra `localhost`; cualquier
servidor remoto requiere HTTPS.
