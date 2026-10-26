"""El avance dentro de una etapa larga llega a disco MIENTRAS corre (RM-56).

Es la diferencia entre una corrida viva y una muerta: la sintesis de voz
puede tardar diez minutos sin escribir nada, y eso se ve exactamente igual
que un worker que murio a mitad (ver RM-44).
"""

from __future__ import annotations

import json
from pathlib import Path

from video_translator.utils.timing import PipelineTimings


def _leer(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_el_progreso_se_ve_en_disco_antes_de_terminar_la_etapa(tmp_path: Path) -> None:
    reporte = tmp_path / "pipeline_timings.json"
    timings = PipelineTimings(report_path=reporte)

    with timings.stage("text_to_speech", num_chunks=3):
        timings.report_progress(0, 3)
        assert _leer(reporte)["current_stage"]["progress"] == {"done": 0, "total": 3}

        timings.report_progress(1, 3)
        # Lo importante: el archivo ya lo refleja, sin esperar al final.
        actual = _leer(reporte)["current_stage"]
        assert actual["name"] == "text_to_speech"
        assert actual["progress"] == {"done": 1, "total": 3}

        timings.report_progress(3, 3)
        assert _leer(reporte)["current_stage"]["progress"] == {"done": 3, "total": 3}


def test_al_terminar_la_etapa_el_progreso_desaparece(tmp_path: Path) -> None:
    """Un progreso que sobrevive a su etapa diria que algo sigue corriendo."""
    reporte = tmp_path / "pipeline_timings.json"
    timings = PipelineTimings(report_path=reporte)

    with timings.stage("text_to_speech", num_chunks=2):
        timings.report_progress(1, 2)

    # La clave se omite cuando no hay etapa en curso (ver as_dict), que es lo
    # que el lector de estado interpreta como "no hay nada corriendo".
    assert "current_stage" not in _leer(reporte)


def test_sin_etapa_en_curso_no_hace_nada(tmp_path: Path) -> None:
    """Fuera de una etapa el progreso no significa nada, y no debe reventar."""
    reporte = tmp_path / "pipeline_timings.json"
    timings = PipelineTimings(report_path=reporte)

    timings.report_progress(1, 2)  # no lanza

    timings.write_report(reporte)
    assert "current_stage" not in _leer(reporte)


def test_una_etapa_que_falla_conserva_donde_se_quedo(tmp_path: Path) -> None:
    """Es el caso que mas importa: saber en que fragmento murio."""
    reporte = tmp_path / "pipeline_timings.json"
    timings = PipelineTimings(report_path=reporte)

    try:
        with timings.stage("text_to_speech", num_chunks=5):
            timings.report_progress(2, 5)
            raise RuntimeError("el worker se cayo")
    except RuntimeError:
        pass

    actual = _leer(reporte)["current_stage"]
    assert actual["name"] == "text_to_speech"
    assert actual["progress"] == {"done": 2, "total": 5}
