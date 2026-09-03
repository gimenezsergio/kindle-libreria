# Preparación de la migración al servidor

Esta guía prepara el traslado, pero no publica el servidor. Los comandos exactos
de servicio, usuario, proxy y certificados se decidirán después de inspeccionar
el sistema operativo y la instalación existente de OpenClaw.

## 1. Congelar un punto de restauración

SQLite no debe copiarse con `cp` mientras la aplicación puede escribir. El
comando `backup` utiliza la API de respaldo de SQLite, ejecuta
`PRAGMA integrity_check`, calcula SHA-256 y deja el archivo con modo `0600`:

```bash
PYTHONPATH=src python3 -m biblioteca_kindle backup \
  --database work/library.sqlite3 \
  --output work/backups/library-initial.sqlite3
```

Guardar por separado la huella mostrada. Antes del traslado conviene detener
ediciones en la interfaz o repetir el respaldo inmediatamente antes de migrar.

## 2. Datos que componen la instalación

- El respaldo SQLite: catálogo, anotaciones, organización, perfiles y conversaciones.
- Las portadas locales referenciadas desde `src/biblioteca_kindle/static/covers/`.
- El código versionado del repositorio.
- Una configuración nueva basada en `.env.server.example`.

No se traslada `work/.env`: contiene credenciales de prueba y configuraciones
propias de la computadora. Tampoco se copian archivos de libros desde el Kindle.
Las portadas deben copiarse conservando sus nombres relativos y permisos de solo
lectura para el proceso web.

## 3. Directorios y permisos previstos

```text
/opt/biblioteca-kindle/       código desplegado, no escribible por el servicio
/var/lib/biblioteca-kindle/   SQLite, portadas propias y estado persistente
/etc/biblioteca-kindle.env    secretos, modo 0600
```

El servicio debe usar un usuario sin shell, sin privilegios y distinto de
OpenClaw. Solo `/var/lib/biblioteca-kindle/` será escribible. OpenClaw accederá
más adelante mediante una API limitada, no leyendo SQLite ni los secretos.

## 4. Restauración verificable

1. Comparar SHA-256 después de copiar el respaldo.
2. Ejecutar `PRAGMA integrity_check` en el servidor.
3. Ejecutar las migraciones con `init-db` sobre una copia restaurada.
4. Comprobar los totales con `report` antes de iniciar el servicio.
5. Verificar portadas, categorías, notas, relaciones y conversaciones.
6. Conservar el respaldo inicial sin modificar para poder volver atrás.

La primera recepción remota se prueba contra otra base temporal. Solo después de
comparar los totales se habilita el agente para escribir en la base restaurada.

## 5. Red y secretos

- La aplicación escucha en `127.0.0.1`; un proxy inverso publica solo HTTPS.
- El endpoint `/api/sync/v1/packages` usa un token exclusivo de sincronización.
- La interfaz web necesita autenticación de usuario antes de exponerse.
- El firewall publica únicamente los puertos imprescindibles.
- Los logs no registran cuerpos, tokens, subrayados ni notas.
- Las copias de seguridad periódicas se almacenan cifradas y se prueba su restauración.

## 6. Comprobaciones antes del despliegue

- Sistema operativo, método actual de despliegue y proxy del servidor.
- Dominio o acceso mediante red privada.
- Política de autenticación de la interfaz.
- Ubicación persistente y estrategia de backups.
- Usuario y puertos utilizados por OpenClaw.
- Forma autorizada de acceder al servidor y de revertir cambios.

Hasta resolver estos puntos no debe improvisarse un servicio de producción.
