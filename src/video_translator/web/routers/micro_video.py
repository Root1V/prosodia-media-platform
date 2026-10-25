"""Router de ayudas del editor de micro-video (RM-42).

Hoy solo genera el guion a partir de una idea. Va aparte de `projects` porque
no crea ni modifica un proyecto: es una ayuda que el editor pide MIENTRAS se
edita, antes de que exista nada que guardar.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from video_translator.config import load_settings
from video_translator.container import build_write_micro_video_script_use_case
from video_translator.domain.exceptions import VideoTranslatorError
from video_translator.web.db.models import User
from video_translator.web.deps import get_current_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/micro-video", tags=["micro-video"])


class ScriptRequest(BaseModel):
    idea: str = Field(min_length=1)
    # Mismo default y misma tolerancia que el resto del campo: un objetivo
    # desconocido cae a "product" dentro del prompt, no revienta aqui.
    objective: str = "product"
    # La duracion elegida en el editor, para que el guion quepa hablado. None =
    # sin tope (el video dura lo que dure la narracion).
    target_seconds: float | None = None


class ScriptResponse(BaseModel):
    script: str


@router.post("/script", response_model=ScriptResponse)
def write_script(
    payload: ScriptRequest,
    _user: User = Depends(get_current_user),
) -> ScriptResponse:
    use_case = build_write_micro_video_script_use_case(load_settings())
    try:
        script = use_case.execute(payload.idea, payload.objective, payload.target_seconds)
    except VideoTranslatorError as exc:
        # Idea vacia o demasiado larga, o respuesta vacia del modelo: son
        # mensajes pensados para leerse en la UI.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        # El LLM es un servicio externo y puede no estar: sin esto el editor
        # recibe un 500 opaco y el usuario no sabe que puede seguir escribiendo
        # el guion a mano, que es justo lo que queremos que haga.
        logger.warning("write_script.failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No se pudo generar el guion: el modelo de lenguaje no responde. "
                "Puedes escribir el texto a narrar a mano."
            ),
        )
    return ScriptResponse(script=script)
