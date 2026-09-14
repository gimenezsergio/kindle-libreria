"""Recetas locales para los accesos directos del acompañante.

Las recetas describen una intención de lectura, no un proveedor ni un modelo.
La interfaz las usa para preparar un borrador editable en la conversación que
ya tiene un perfil asignado.
"""

from __future__ import annotations

from dataclasses import dataclass


ACTION_GROUPS = frozenset({"Comprender", "Interpretar", "Cuestionar", "Relacionar", "Recordar"})
SEARCH_BEHAVIORS = frozenset({"preserve", "enable"})


@dataclass(frozen=True)
class CompanionAction:
    """Una acción breve, reutilizable y neutral respecto del proveedor de IA."""

    id: str
    label: str
    description: str
    message_template: str
    requirements: dict[str, str]
    group: str
    is_primary: bool
    search_behavior: str

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "message_template": self.message_template,
            "requirements": self.requirements,
            "group": self.group,
            "is_primary": self.is_primary,
            "search_behavior": self.search_behavior,
        }


COMPANION_ACTIONS: tuple[CompanionAction, ...] = (
    CompanionAction(
        id="explain-selection",
        label="Explicar la selección",
        description="Aclará el sentido de los fragmentos que agregaste.",
        message_template=(
            "Ayudame a explicar el material seleccionado para esta conversación. "
            "Si no hay fragmentos adjuntos, indicá con honestidad qué se puede "
            "abordar solamente a partir de la ficha del libro y pedime el pasaje "
            "que haga falta. Diferenciá evidencia, conocimiento general e "
            "interpretación."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Comprender",
        is_primary=True,
        search_behavior="preserve",
    ),
    CompanionAction(
        id="detect-themes",
        label="Detectar temas",
        description="Proponé temas y tensiones para seguir leyendo.",
        message_template=(
            "Identificá temas y tensiones posibles a partir del material disponible "
            "en esta conversación. Priorizá los fragmentos adjuntos si los hay. "
            "Presentá cada tema como una hipótesis para conversar y diferenciá "
            "evidencia, conocimiento general e interpretación."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Interpretar",
        is_primary=True,
        search_behavior="preserve",
    ),
    CompanionAction(
        id="explore-symbols",
        label="Explorar símbolos",
        description="Buscá imágenes, objetos o motivos que puedan tener peso.",
        message_template=(
            "Explorá símbolos, imágenes o motivos posibles en el material disponible. "
            "No los presentes como significados cerrados: formulalos como hipótesis "
            "y explicá qué evidencia los sostiene. Diferenciá evidencia, conocimiento "
            "general e interpretación."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Interpretar",
        is_primary=True,
        search_behavior="preserve",
    ),
    CompanionAction(
        id="propose-questions",
        label="Proponer preguntas",
        description="Abrí preguntas para continuar pensando la lectura.",
        message_template=(
            "Proponé preguntas abiertas para seguir pensando esta lectura a partir "
            "del material disponible. Evitá respuestas cerradas; incluí algunas que "
            "pongan en tensión mi posible interpretación y señalá qué preguntas se "
            "apoyan en los fragmentos adjuntos."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Cuestionar",
        is_primary=True,
        search_behavior="preserve",
    ),
    CompanionAction(
        id="relate-library",
        label="Relacionar con mi biblioteca",
        description="Buscá ecos, contrastes o discusiones en otras lecturas.",
        message_template=(
            "Buscá relaciones posibles entre esta lectura y las fuentes recuperadas "
            "de mi biblioteca. Proponé ecos, contrastes o preguntas de comparación, "
            "sin afirmar una relación como hecho. Diferenciá las fuentes recuperadas "
            "de tu conocimiento general e interpretación."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar",
        is_primary=True,
        search_behavior="enable",
    ),
    CompanionAction(
        id="summarize-highlights",
        label="Resumir mis subrayados",
        description="Construí una síntesis a partir de los fragmentos que elegiste.",
        message_template=(
            "Elaborá una síntesis de los fragmentos seleccionados. Priorizá ese "
            "material y separá lo que está dicho allí de cualquier conocimiento "
            "general o hipótesis. Si no hay fragmentos, explicá el límite y pedime "
            "material para poder resumir con rigor."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="explain-passage",
        label="Explicar un pasaje",
        description="Desplegá el sentido posible de un fragmento concreto.",
        message_template=(
            "Explicá el pasaje o los fragmentos seleccionados paso a paso. Atendé "
            "a sus palabras y contexto disponible, sin fingir que tenés el texto "
            "completo. Diferenciá evidencia, conocimiento general e interpretación."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="identify-concepts",
        label="Identificar conceptos",
        description="Nombrá y aclará las ideas que organizan el material.",
        message_template=(
            "Identificá los conceptos importantes presentes en el material "
            "disponible y explicá cómo se relacionan. Priorizá los fragmentos "
            "seleccionados y distinguí evidencia, conocimiento general e hipótesis."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="create-glossary",
        label="Crear glosario",
        description="Definí términos relevantes para volver a esta lectura.",
        message_template=(
            "Creá un glosario breve de términos relevantes para esta lectura. "
            "Indicá cuáles aparecen en el material seleccionado y cuáles son "
            "aclaraciones de conocimiento general; no supongas el texto completo."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="historical-cultural-context",
        label="Contexto histórico y cultural",
        description="Ubicá el material sin confundir contexto con evidencia del libro.",
        message_template=(
            "Ofrecé contexto histórico y cultural útil para interpretar el material "
            "disponible. Separá con claridad el contexto de conocimiento general de "
            "la evidencia de mis fragmentos y de las hipótesis interpretativas."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="analyze-characters",
        label="Analizar personajes",
        description="Observá rasgos, deseos y tensiones sin completar huecos como hechos.",
        message_template=(
            "Analizá los personajes que aparecen en el material disponible: rasgos, "
            "deseos, conflictos y relaciones posibles. Marcá qué está respaldado por "
            "mis fragmentos, qué es conocimiento general y qué es una hipótesis."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Interpretar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="explore-conflicts",
        label="Explorar conflictos",
        description="Distinguí conflictos íntimos, sociales e ideológicos.",
        message_template=(
            "Explorá los conflictos posibles en el material disponible: íntimos, "
            "entre personajes, sociales o ideológicos. Proponelos como hipótesis y "
            "diferenciá evidencia, conocimiento general e interpretación."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Interpretar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="narrative-evolution",
        label="Evolución narrativa",
        description="Pensá cambios, desplazamientos y giros que sugiera el material.",
        message_template=(
            "Examiná qué evolución narrativa sugieren los fragmentos disponibles: "
            "cambios, desplazamientos o giros. No reconstruyas la obra entera; "
            "separá evidencia, conocimiento general e hipótesis."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Interpretar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="challenge-interpretation",
        label="Contradecir mi interpretación",
        description="Probá una lectura que ponga en tensión la intuición inicial.",
        message_template=(
            "Proponé una lectura alternativa que pueda contradecir o tensionar mi "
            "interpretación. No la presentes como definitiva: explicá qué evidencia "
            "la sostiene, qué es conocimiento general y qué queda como hipótesis."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Cuestionar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="alternative-reading",
        label="Lectura alternativa",
        description="Abrí otro marco posible para leer la obra o el pasaje.",
        message_template=(
            "Ofrecé una lectura alternativa del material disponible desde otro marco "
            "posible. Decí de dónde sale cada propuesta y distinguí evidencia, "
            "conocimiento general e hipótesis interpretativas."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Cuestionar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="argument-counterargument",
        label="Argumento y contraargumento",
        description="Poné una idea en diálogo con su mejor objeción.",
        message_template=(
            "Formulá un argumento que surja del material y su mejor contraargumento. "
            "No atribuyas al libro lo que no está en los fragmentos: diferenciá "
            "evidencia, conocimiento general e hipótesis."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Cuestionar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="surface-assumptions",
        label="Señalar supuestos y ambigüedades",
        description="Encontrá presupuestos, tensiones y zonas abiertas.",
        message_template=(
            "Señalá supuestos, ambigüedades o tensiones presentes en el material "
            "disponible. Plantealos como preguntas o hipótesis, indicando qué se "
            "apoya en los fragmentos y qué proviene de conocimiento general."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Cuestionar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="compare-readings",
        label="Comparar con otras lecturas",
        description="Buscá similitudes y diferencias en tu biblioteca.",
        message_template=(
            "Compará esta lectura con las fuentes recuperadas de mi biblioteca. "
            "Proponé similitudes y diferencias posibles, sin afirmarlas como hechos, "
            "y separá fuentes recuperadas, conocimiento general e interpretación."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar", is_primary=False, search_behavior="enable",
    ),
    CompanionAction(
        id="find-agreements",
        label="Buscar acuerdos",
        description="Encontrá ideas que conversen o se refuercen entre lecturas.",
        message_template=(
            "Buscá acuerdos, ecos o ideas que se refuercen entre esta lectura y las "
            "fuentes recuperadas de mi biblioteca. Presentalos como hipótesis y "
            "diferenciá evidencia, conocimiento general e interpretación."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar", is_primary=False, search_behavior="enable",
    ),
    CompanionAction(
        id="find-contradictions",
        label="Buscar contradicciones",
        description="Poné esta lectura en tensión con otras obras recuperadas.",
        message_template=(
            "Buscá contrastes o contradicciones posibles entre esta lectura y las "
            "fuentes recuperadas de mi biblioteca. No las trates como conclusiones "
            "cerradas; diferenciá evidencia, conocimiento general e hipótesis."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar", is_primary=False, search_behavior="enable",
    ),
    CompanionAction(
        id="reading-route",
        label="Proponer una ruta de lectura",
        description="Sugerí próximos cruces, preguntas y obras para continuar.",
        message_template=(
            "A partir de esta lectura y las fuentes recuperadas de mi biblioteca, "
            "proponé una ruta de lectura: próximos cruces, preguntas u obras para "
            "explorar. Explicá en qué evidencia se apoya cada sugerencia y qué es "
            "una hipótesis."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar", is_primary=False, search_behavior="enable",
    ),
    CompanionAction(
        id="reading-synthesis",
        label="Síntesis de lectura",
        description="Dejá una síntesis breve para retomar más adelante.",
        message_template=(
            "Prepará una síntesis breve para retomar esta lectura más adelante. "
            "Priorizá mi material seleccionado y marcá con honestidad qué puntos "
            "dependen de conocimiento general o quedan como hipótesis."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="ideas-to-remember",
        label="Ideas para recordar",
        description="Extraé ideas memorables sin convertirlas en verdades cerradas.",
        message_template=(
            "Extraé ideas que valga la pena recordar de esta lectura. Indicá cuáles "
            "están respaldadas por mis fragmentos y cuáles son formulaciones o "
            "hipótesis tuyas; no supongas el texto completo."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="review-questions",
        label="Preguntas de repaso",
        description="Creá preguntas para volver activamente al material.",
        message_template=(
            "Generá preguntas de repaso para volver activamente al material "
            "disponible. Señalá cuáles se apoyan directamente en mis fragmentos y "
            "evitá fingir información del texto completo."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="study-cards",
        label="Tarjetas de estudio",
        description="Convertí ideas seleccionadas en tarjetas de pregunta y respuesta.",
        message_template=(
            "Proponé tarjetas de estudio breves, con pregunta y respuesta, a partir "
            "del material seleccionado. Indicá qué respuestas están respaldadas por "
            "los fragmentos y cuáles requieren conocimiento general."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="open-questions",
        label="Preguntas pendientes",
        description="Registrá dudas fértiles para continuar leyendo.",
        message_template=(
            "Identificá preguntas pendientes o dudas fértiles para continuar esta "
            "lectura. Distinguí las que nacen de mis fragmentos de las que proponés "
            "desde conocimiento general o como hipótesis."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
)


def _validate_catalog() -> None:
    """Hace fallar temprano cambios editoriales que romperían el contrato de API."""
    ids = [action.id for action in COMPANION_ACTIONS]
    if len(ids) != len(set(ids)):
        raise ValueError("Los identificadores de acciones deben ser únicos")
    if any(action.group not in ACTION_GROUPS for action in COMPANION_ACTIONS):
        raise ValueError("El grupo de una acción no es válido")
    if any(action.search_behavior not in SEARCH_BEHAVIORS for action in COMPANION_ACTIONS):
        raise ValueError("El comportamiento de búsqueda no es válido")
    if sum(action.is_primary for action in COMPANION_ACTIONS) != 5:
        raise ValueError("El catálogo debe conservar exactamente cinco acciones principales")
    if any(
        action.group == "Relacionar" and action.search_behavior != "enable"
        for action in COMPANION_ACTIONS
    ):
        raise ValueError("Las acciones relacionales deben activar la búsqueda")


_validate_catalog()


def list_companion_actions() -> list[dict[str, object]]:
    """Devuelve las recetas en el orden editorial de la interfaz."""
    return [action.as_dict() for action in COMPANION_ACTIONS]


def get_companion_action(action_id: object) -> CompanionAction | None:
    """Busca una receta por id sin aceptar valores ambiguos del cliente.

    ``None`` representa el flujo de mensaje libre. Cualquier otro valor debe
    ser exactamente uno de los ids publicados por el catálogo; así un cliente
    no puede guardar ni declarar una acción que la aplicación no conoce.
    """
    if action_id is None:
        return None
    if not isinstance(action_id, str):
        raise ValueError("La acción del acompañante no es válida")
    for action in COMPANION_ACTIONS:
        if action.id == action_id:
            return action
    raise ValueError("La acción del acompañante no es válida")
