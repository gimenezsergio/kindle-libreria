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
        description="Aclará el sentido de la obra y los fragmentos que agregaste.",
        message_template=(
            "Ayudame a explorar las ideas centrales de esta obra. Si hay fragmentos "
            "o subrayados adjuntos, usalos como punto de partida prioritario para la "
            "explicación; si no los hay, analizá la obra a partir de tu conocimiento "
            "general sobre el libro."
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
            "Identificá los temas y tensiones principales de esta obra. Si hay "
            "fragmentos o subrayados adjuntos, priorizá esos pasajes como mi foco de "
            "atención. Presentá cada tema como una hipótesis para conversar."
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
            "Explorá los símbolos, imágenes o motivos principales de esta obra. "
            "Formulalos como hipótesis interpretativas y vinculalos con tu análisis "
            "de la lectura."
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
            "Proponé preguntas abiertas y estimulantes para profundizar en esta obra. "
            "Evitá respuestas cerradas e incluí algunas que pongan en tensión "
            "posibles interpretaciones."
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
            "Buscá relaciones posibles entre esta obra y las fuentes recuperadas "
            "de mi biblioteca. Proponé ecos, contrastes o preguntas de comparación "
            "para enriquecer el diálogo."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar",
        is_primary=True,
        search_behavior="enable",
    ),
    CompanionAction(
        id="summarize-highlights",
        label="Resumir mis subrayados",
        description="Construí una síntesis a partir de la obra y tus fragmentos.",
        message_template=(
            "Elaborá una síntesis de las ideas y pasajes fundamentales de esta lectura, "
            "destacando los subrayados o fragmentos seleccionados si los hay."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="explain-passage",
        label="Explicar un pasaje",
        description="Desplegá el sentido posible de un fragmento concreto.",
        message_template=(
            "Explicá el pasaje o momento seleccionado paso a paso. Atendé a sus "
            "palabras e ideas en relación con el desarrollo general de la obra."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="identify-concepts",
        label="Identificar conceptos",
        description="Nombrá y aclará las ideas que organizan el material.",
        message_template=(
            "Identificá los conceptos clave que organizan esta obra y explicá cómo "
            "se relacionan entre sí."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="create-glossary",
        label="Crear glosario",
        description="Definí términos relevantes para volver a esta lectura.",
        message_template=(
            "Creá un glosario breve de los términos, metáforas o conceptos más "
            "relevantes para comprender esta obra."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="historical-cultural-context",
        label="Contexto histórico y cultural",
        description="Ubicá la obra en su época y su marco intelectual.",
        message_template=(
            "Ofrecé el contexto histórico, político y cultural en el que fue creada "
            "o ambientada esta obra, explicando su impacto en las ideas del libro."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Comprender", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="analyze-characters",
        label="Analizar personajes",
        description="Observá rasgos, deseos, evoluciones y tensiones entre personajes.",
        message_template=(
            "Analizá los personajes principales de esta obra: sus rasgos, deseos, "
            "conflictos internos, evoluciones y relaciones. Si hay subrayados o "
            "notas adjuntas, vinculalos con tu análisis de los personajes."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Interpretar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="explore-conflicts",
        label="Explorar conflictos",
        description="Distinguí conflictos íntimos, sociales e ideológicos.",
        message_template=(
            "Explorá los conflictos estructurantes de esta obra: dilemas personales, "
            "tensiones sociales o enfrentamientos ideológicos."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Interpretar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="narrative-evolution",
        label="Evolución narrativa",
        description="Pensá cambios, desplazamientos y giros clave de la obra.",
        message_template=(
            "Examiná la evolución narrativa y temática de esta obra: cambios, "
            "desplazamientos de poder o giros argumentales."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Interpretar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="challenge-interpretation",
        label="Contradecir mi interpretación",
        description="Probá una lectura que ponga en tensión la intuición inicial.",
        message_template=(
            "Proponé una lectura alternativa que ponga en tensión o contradiga una "
            "interpretación habitual de la obra. Explicá qué argumentos la sostienen."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Cuestionar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="alternative-reading",
        label="Lectura alternativa",
        description="Abrí otro marco posible para leer la obra.",
        message_template=(
            "Ofrecé una lectura de esta obra desde un marco teórico o filosófico "
            "diferente al convencional."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Cuestionar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="argument-counterargument",
        label="Argumento y contraargumento",
        description="Poné una idea en diálogo con su mejor objeción.",
        message_template=(
            "Formulá la tesis principal o un argumento central de esta obra y "
            "desarrollá su mejor contraargumento u objeción crítica."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Cuestionar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="surface-assumptions",
        label="Señalar supuestos y ambigüedades",
        description="Encontrá presupuestos, tensiones y zonas abiertas.",
        message_template=(
            "Señalá los supuestos no dichos, las ambigüedades o las tensiones "
            "internas que atraviesan esta obra."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Cuestionar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="compare-readings",
        label="Comparar con otras lecturas",
        description="Buscá similitudes y diferencias en tu biblioteca.",
        message_template=(
            "Compará esta obra con las fuentes recuperadas de mi biblioteca, "
            "destacando similitudes, divergencias o influencias cruzadas."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar", is_primary=False, search_behavior="enable",
    ),
    CompanionAction(
        id="find-agreements",
        label="Buscar acuerdos",
        description="Encontrá ideas que conversen o se refuercen entre lecturas.",
        message_template=(
            "Buscá puntos de encuentro o coincidencias filosóficas entre esta obra "
            "y las fuentes recuperadas de mi biblioteca."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar", is_primary=False, search_behavior="enable",
    ),
    CompanionAction(
        id="find-contradictions",
        label="Buscar contradicciones",
        description="Poné esta lectura en tensión con otras obras recuperadas.",
        message_template=(
            "Buscá desacuerdos o tensiones conceptuales entre esta obra y las "
            "fuentes recuperadas de mi biblioteca."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar", is_primary=False, search_behavior="enable",
    ),
    CompanionAction(
        id="reading-route",
        label="Proponer una ruta de lectura",
        description="Sugerí próximos cruces, preguntas y obras para continuar.",
        message_template=(
            "A partir de esta obra y las fuentes de mi biblioteca, proponé una "
            "ruta de lectura con próximas obras, autores o temas para explorar."
        ),
        requirements={"material": "opcional", "library_search": "activar si estaba desactivada; respetar el alcance elegido"},
        group="Relacionar", is_primary=False, search_behavior="enable",
    ),
    CompanionAction(
        id="reading-synthesis",
        label="Síntesis de lectura",
        description="Dejá una síntesis breve para retomar más adelante.",
        message_template=(
            "Prepará una síntesis de los aspectos fundamentales de esta obra para "
            "retomar la lectura más adelante."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="ideas-to-remember",
        label="Ideas para recordar",
        description="Extraé ideas memorables para conservar.",
        message_template=(
            "Extraé las ideas más memorables y valiosas de esta obra que valga la "
            "pena conservar en el tiempo."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="review-questions",
        label="Preguntas de repaso",
        description="Creá preguntas para volver activamente al material.",
        message_template=(
            "Generá preguntas de repaso estimulantes para volver activamente sobre "
            "los temas clave de esta obra."
        ),
        requirements={"material": "opcional", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="study-cards",
        label="Tarjetas de estudio",
        description="Convertí ideas seleccionadas en tarjetas de pregunta y respuesta.",
        message_template=(
            "Proponé tarjetas de estudio breves (pregunta y respuesta) sobre los "
            "conceptos centrales de esta obra."
        ),
        requirements={"material": "recomendado", "library_search": "respetar la configuración actual"},
        group="Recordar", is_primary=False, search_behavior="preserve",
    ),
    CompanionAction(
        id="open-questions",
        label="Preguntas pendientes",
        description="Registrá dudas fértiles para continuar leyendo.",
        message_template=(
            "Identificá preguntas o dilemas abiertos que deja esta obra para seguir "
            "reflexionando."
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
