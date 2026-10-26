"""Agregados que salen de las columnas JSON de ProjectMetrics (RM-61).

Van aparte del router porque no son un GROUP BY: `stats` guarda listas (una
entrada por invocacion de la etapa, p.ej. una transcripcion por tramo), asi
que hay que sumarlas antes de promediar. Hacerlo en SQL seria ilegible; con
decenas o cientos de corridas por usuario, hacerlo en Python no cuesta nada.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, TypedDict

from video_translator.web.db.models import ProjectMetrics


class _Fase(TypedDict):
    phase: str
    avg_seconds: float


# Que clave de `stats` cuenta para cada fase. El nombre que ve el usuario sale
# de STAGE_LABELS en el frontend; aqui solo viaja el identificador.
_FASES: dict[str, tuple[str, ...]] = {
    "transcription": ("transcription.model_load_and_inference_seconds",),
    "translation": ("translation.batch_seconds",),
    "text_to_speech": ("tts.batch_wall_seconds",),
    "diarization": (
        "diarization.model_load_seconds",
        "diarization.inference_seconds",
    ),
}


def _sumar(valor: Any) -> float:
    """Un valor de `stats` puede ser un numero o una lista de numeros.

    Una etapa que corre varias veces (una transcripcion por tramo) acumula una
    entrada por invocacion, asi que lo que importa es la suma, no la primera.
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, Sequence) and not isinstance(valor, (str, bytes)):
        return sum(float(v) for v in valor if isinstance(v, (int, float)))
    return 0.0


def reparto_de_tiempo(metricas: Iterable[ProjectMetrics]) -> dict[str, Any] | None:
    """Donde se va el tiempo del servicio que mas tarda, en promedio.

    Solo corridas completadas: una que murio a mitad tiene fases a medio
    llenar y desplazaria el reparto hacia lo que alcanzo a ejecutarse.
    """
    completadas = [
        m
        for m in metricas
        if m.status == "completed" and m.total_seconds and m.stats and m.service_type == "dubbing"
    ]
    if not completadas:
        return None

    acumulado = dict.fromkeys(_FASES, 0.0)
    total = 0.0
    for m in completadas:
        total += float(m.total_seconds or 0.0)
        for fase, claves in _FASES.items():
            acumulado[fase] += sum(_sumar(m.stats.get(clave)) for clave in claves)

    n = len(completadas)
    medido = sum(acumulado.values())
    fases: list[_Fase] = [
        {"phase": fase, "avg_seconds": segundos / n}
        for fase, segundos in acumulado.items()
        if segundos > 0
    ]
    # Lo que no cae en ninguna fase medida -- extraer el audio, renderizar,
    # mover archivos -- en vez de dejar que las barras no sumen el total.
    resto = total - medido
    if resto > 0.5:
        fases.append({"phase": "other", "avg_seconds": resto / n})

    fases.sort(key=lambda f: f["avg_seconds"], reverse=True)
    return {
        "service_type": "dubbing",
        "runs": n,
        "avg_total_seconds": total / n,
        "phases": fases,
    }


def senales_de_calidad(metricas: Iterable[ProjectMetrics]) -> dict[str, int]:
    """Cosas que salieron bien a medias y no se ven en un "completado".

    Son condiciones silenciosas: la corrida termina, deja su archivo, y nadie
    se entera de que la voz se sintetizo en CPU (varias veces mas lento) o de
    que hubo que recortar frases para que el doblaje encajara en el hueco
    original -- es decir, que el resultado dice menos que el video de partida.
    """
    considerado = 0
    en_cpu = 0
    con_recortes = 0
    con_avisos = 0
    for m in metricas:
        if m.status != "completed":
            continue
        considerado += 1
        if (m.effective_config or {}).get("tts_device_forced_cpu") is True:
            en_cpu += 1
        if _sumar((m.stats or {}).get("counter.tts.overflow_trimmed_segments")) > 0:
            con_recortes += 1
        if m.warnings_count > 0:
            con_avisos += 1
    return {
        "runs_considered": considerado,
        "runs_tts_on_cpu": en_cpu,
        "runs_with_trimmed_segments": con_recortes,
        "runs_with_warnings": con_avisos,
    }
