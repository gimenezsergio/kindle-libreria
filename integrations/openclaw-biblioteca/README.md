# Plugin OpenClaw para Biblioteca Kindle

Plugin de herramientas tipadas que conecta OpenClaw con la API privada de
Biblioteca Kindle. No abre SQLite y no contiene credenciales.

## Requisitos

- OpenClaw 2026.5.17 o posterior;
- Node compatible con la versión instalada de OpenClaw;
- Biblioteca Kindle accesible desde el mismo servidor;
- `BIBLIOTECA_OPENCLAW_TOKEN` configurado en Biblioteca Kindle;
- el mismo valor entregado al plugin mediante la configuración secreta de
  OpenClaw.

## Desarrollo y validación

```bash
npm install
npm run plugin:build
npm run plugin:validate
npm test
```

## Instalación futura en el servidor

Desde este directorio:

```bash
openclaw plugins install .
openclaw plugins inspect biblioteca-kindle --runtime
```

La configuración necesita `baseUrl` —por defecto `http://127.0.0.1:8000`— y
`token`. La opción recomendada es omitirlo de la configuración y exportar
`BIBLIOTECA_OPENCLAW_TOKEN` en el servicio de OpenClaw. Nunca debe escribirse en
este repositorio.

El flujo conversacional está descrito en `skill/SKILL.md`. En la instalación
real se instala con:

```bash
openclaw skills install ./skill --as biblioteca-kindle
```

Las herramientas permiten buscar obras, elegir perfiles, abrir conversaciones,
seleccionar contexto, recuperar evidencia y completar turnos idempotentes. Las
operaciones administrativas de la interfaz web y la sincronización del Kindle
no forman parte del plugin.
