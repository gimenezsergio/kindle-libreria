# Mapa de páginas

| Página real | Referencia Stitch | Adaptación |
|---|---|---|
| `/` | Panorama del archivo | Solo métricas y advertencias reales; sin botón de sincronización ficticio. |
| `/library` | Catálogo de lecturas | Grilla/lista, búsqueda, presencia, anotaciones y paginación reales. |
| `/library/<id>` | Ficha y acompañante | Navegación por Memoria, Cuaderno, Acompañante y Datos; conserva todos los formularios existentes. |
| `/settings/ai-profiles` | Perfiles IA | Nombre, descripción, prompt, predeterminado y archivado; sin temperatura ni proveedor por perfil. |
| `/settings/covers` | Curaduría de portadas | Selección, descarte, nueva búsqueda y carga; sin aprobación masiva ni generación ficticia. |

Las variantes móviles de Stitch se usan como referencia de composición, no como
páginas adicionales. La aplicación mantiene cinco superficies y un único DOM
responsive para cada una.
