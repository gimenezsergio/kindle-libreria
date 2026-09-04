# Despliegue de OpenClaw y Telegram

Esta guía se ejecutará cuando Biblioteca Kindle y OpenClaw estén en el servidor.
No contiene tokens ni identificadores reales.

## Datos necesarios

Antes de comenzar hay que disponer de:

- acceso al servidor y usuario que ejecuta cada servicio;
- versión de OpenClaw (`2026.5.17` o posterior para el tool plugin);
- token largo y aleatorio para `BIBLIOTECA_OPENCLAW_TOKEN`;
- token del bot creado con `@BotFather`;
- Telegram user ID numérico del dueño;
- método existente de secretos y reinicio de servicios.

## 1. Biblioteca Kindle

Configurar `BIBLIOTECA_OPENCLAW_TOKEN` en el entorno del servicio y mantener la
aplicación escuchando en loopback, por ejemplo `127.0.0.1:8000`. Comprobar la API
con una solicitud autenticada a `/api/openclaw/v1/status`.

El token de OpenClaw debe ser distinto de `BIBLIOTECA_SYNC_TOKEN` y de cualquier
clave de proveedor de IA.

## 2. Plugin y skill

Copiar o clonar el repositorio en el servidor y, desde
`integrations/openclaw-biblioteca`, ejecutar:

```bash
npm install
npm run plugin:build
npm run plugin:validate
npm test
openclaw plugins install .
openclaw plugins enable biblioteca-kindle
openclaw plugins inspect biblioteca-kindle --runtime
openclaw skills install ./skill --as biblioteca-kindle
```

Entregar `BIBLIOTECA_OPENCLAW_TOKEN` al proceso de OpenClaw mediante el sistema
de secretos del servidor. Si la API no usa la dirección predeterminada, definir
`plugins.entries.biblioteca-kindle.config.baseUrl`. No escribir el token en Git.

Si existe una lista global `plugins.allow`, incluir `biblioteca-kindle`. La
política de herramientas del agente también debe permitir las herramientas
`biblioteca_*`; no es necesario habilitar herramientas de archivos ni ejecución
de comandos para esta conversación.

## 3. Telegram para un único dueño

OpenClaw incorpora el canal Telegram. La configuración inicial recomendada es:

```json5
{
  channels: {
    telegram: {
      enabled: true,
      dmPolicy: "allowlist",
      allowFrom: ["tg:TELEGRAM_USER_ID"],
      streaming: { mode: "partial" }
    }
  },
  commands: {
    ownerAllowFrom: ["telegram:TELEGRAM_USER_ID"]
  }
}
```

El token del bot se entrega como `TELEGRAM_BOT_TOKEN` al proceso de OpenClaw o
mediante el mecanismo de secretos admitido por el canal. `TELEGRAM_USER_ID` se
reemplaza por el número real, no por el nombre `@usuario`.

Para una primera prueba también puede usarse el emparejamiento de DMs y aprobar
el código con los comandos que muestre la versión instalada. Para el uso estable
de un solo dueño se prefiere la allowlist numérica explícita.

No se habilitan grupos en la primera versión. Si más adelante se usan, deben
configurarse por chat ID y conservar `requireMention: true`.

## 4. Verificación completa

Después de reiniciar o recargar el Gateway:

1. Verificar el estado del Gateway y el plugin.
2. Escribir al bot desde la única cuenta autorizada.
3. Pedir «Quiero hablar sobre 1984».
4. Confirmar que busca la obra y pregunta ante resultados ambiguos.
5. Crear o continuar una conversación.
6. Hacer una pregunta que requiera un subrayado y otra que busque relaciones en
   toda la biblioteca.
7. Confirmar desde la web que ambos mensajes, la respuesta y sus fuentes fueron
   guardados en la misma conversación.
8. Reintentar una finalización y confirmar que no duplica la respuesta.
9. Probar una cuenta de Telegram no autorizada y confirmar que no obtiene acceso.
10. Revisar registros para asegurar que los tokens y fragmentos privados no se
    imprimen completos.

## 5. Recuperación ante fallos

- Si Telegram funciona pero la biblioteca no responde, revisar
  `biblioteca_status`, el proceso Flask/WSGI y el token del servicio.
- Si las herramientas no aparecen, inspeccionar el plugin en runtime, su
  allowlist y la política de herramientas del agente.
- Si una respuesta fue generada pero no guardada, reintentar
  `biblioteca_completar_turno` con el mismo `turn_id`.
- Si se desconoce si la preparación terminó, consultar la conversación antes de
  crear otro turno para evitar repetir la pregunta.
- Antes de actualizar plugin o aplicación, realizar el respaldo consistente de
  SQLite indicado en `server-migration.md`.

## Trabajo que exige acceso externo

Este repositorio deja preparada y validada la API y el plugin. La instalación
del plugin en el OpenClaw del servidor, la creación/configuración del bot y la
prueba con el Telegram user ID real no pueden realizarse sin acceso al servidor,
el token de BotFather y ese identificador.
