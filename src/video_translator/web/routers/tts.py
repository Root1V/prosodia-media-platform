"""Router de ayudas de la pagina de voz (RM-55).

Aparte de `projects` por el mismo motivo que `micro_video`: no crea ni
modifica un proyecto. Es una ayuda que la pagina pide MIENTRAS se escribe,
antes de que exista nada que guardar.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from video_translator.config import load_settings
from video_translator.container import build_assist_narration_text_use_case
from video_translator.domain.exceptions import VideoTranslatorError
from video_translator.web.db.models import User
from video_translator.web.deps import get_current_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])


class NarrationTextRequest(BaseModel):
    text: str = Field(min_length=1)
    # "draft" redacta a partir de una idea; "polish" corrige lo que ya hay.
    # El idioma solo cuenta para "draft": corregir no traduce nunca.
    mode: str = "polish"
    language: str = "es"


class NarrationTextResponse(BaseModel):
    text: str


@router.post("/narration-text", response_model=NarrationTextResponse)
def assist_narration_text(
    payload: NarrationTextRequest,
    _user: User = Depends(get_current_user),
) -> NarrationTextResponse:
    use_case = build_assist_narration_text_use_case(load_settings())
    try:
        if payload.mode == "draft":
            resultado = use_case.draft(payload.text, payload.language)
        elif payload.mode == "polish":
            resultado = use_case.polish(payload.text)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Modo no valido: {payload.mode}",
            )
    except VideoTranslatorError as exc:
        # Texto vacio, demasiado largo, o respuesta vacia del modelo: son
        # mensajes escritos para leerse tal cual en la pagina.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # El LLM es un servicio externo y puede no estar. Sin esto llega un 500
        # opaco y el usuario no sabe que puede seguir escribiendo a mano, que es
        # justo lo que queremos que haga: la ayuda es opcional, el texto no.
        logger.warning("narration_text.failed", mode=payload.mode, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El modelo de lenguaje no responde. Puedes escribir "
                "o corregir el texto a mano."
            ),
        )
    return NarrationTextResponse(text=resultado)
