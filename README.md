# Biblioteca Kindle

Proyecto para construir una biblioteca personal independiente usando un Kindle
como fuente de datos de solo lectura.

## Principios

- Amazon y Send to Kindle siguen siendo el mecanismo de entrega y sincronización.
- Nunca se modifican, eliminan ni escriben archivos en el Kindle.
- Los datos derivados y las portadas propias viven fuera del dispositivo.
- Primero se documentan los datos realmente disponibles; el extractor se diseña después.

## Directorios

- `docs/`: hallazgos y decisiones del proyecto.
- `work/`: resultados locales temporales, excluidos de Git.

## Desarrollo local

El proyecto usa Python 3.11 o posterior y SQLite, sin dependencias de ejecución.

Para crear una base local durante el desarrollo:

```bash
PYTHONPATH=src python -m biblioteca_kindle init-db work/library.sqlite3
```

La base debe permanecer fuera del Kindle. `work/` está excluido de Git porque
puede contener datos privados derivados del dispositivo.

Para crear una instantánea de inventario de solo lectura:

```bash
PYTHONPATH=src python -m biblioteca_kindle inventory /media/usuario/Kindle \
  --database work/library.sqlite3
```

El comando rechaza una base ubicada dentro del Kindle y solo inventaría fuentes
relevantes; no interpreta todavía libros ni anotaciones.
