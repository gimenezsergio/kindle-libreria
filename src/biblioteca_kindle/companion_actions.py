"""Recetas locales para los accesos directos del acompañante.

Las recetas describen una intención de lectura, no un proveedor ni un modelo.
La interfaz las usa para preparar un borrador editable en la conversación que
ya tiene un perfil asignado.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanionAction:
    """Una acción breve, reutilizable y neutral respecto del proveedor de IA."""

    id: str
    label: str
    description: str
    message_template: str
    requirements: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "message_template": self.message_template,
            "requirements": self.requirements,
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
    ),
)


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
