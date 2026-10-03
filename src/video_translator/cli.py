"""Interfaz de linea de comandos (CLI) de Video Translator."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

try:
    # Telemetria hacia Argus (ver RM-41). Protegido porque argus-obs-sdk vive
    # en el extra "web": una instalacion solo-CLI no lo trae y aqui no debe
    # hacer falta. Sin OTEL_EXPORTER_OTLP_ENDPOINT en el entorno tampoco se
    # exporta nada, asi que el coste de tenerlo instalado es cero.
    import argus
    from argus.propagate import run as argus_run
except ImportError:  # pragma: no cover
    argus = None  # type: ignore[assignment]
    argus_run = None  # type: ignore[assignment]

from video_translator.config import load_settings
from video_translator.container import build_translate_video_use_case
from video_translator.domain.exceptions import VideoTranslatorError
from video_translator.domain.models import (
    OutputMode,
    TranslateVideoRequest,
    TranslateVideoResult,
    TranslationContext,
)
from video_translator.utils.logging_config import configure_logging, get_logger
from video_translator.utils.timing import PipelineTimings

app = typer.Typer(
    name="video-translator",
    help="Traduce videos MP4 largos de ingles a espanol usando IA open source.",
    add_completion=False,
)
console = Console()
logger = get_logger(__name__)


def _install_signal_handlers() -> None:
    """Al recibir SIGINT/SIGTERM deja constancia en el reporte de timings
    (senal y momento) ANTES de morir, para que una corrida interrumpida a
    media carrera quede documentada en pipeline_timings.json. Luego restaura
    el handler por defecto y re-envia la senal: el proceso muere con el mismo
    exit code que tendria sin nuestro handler.

    La instancia de PipelineTimings se resuelve AL LLEGAR la senal (no al
    instalar): los handlers se registran antes de execute(), que es quien
    crea la instancia.
    """
    import os
    import signal
    import types

    def _handler(signum: int, frame: types.FrameType | None) -> None:
        timings = PipelineTimings.active()
        if timings is not None:
            timings.mark_interrupted(signal.Signals(signum).name)
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):  # p.ej. signal desde un hilo no principal
            pass


@app.command()
def translate(
    input: Path = typer.Option(..., "--input", "-i", exists=True, help="Ruta al video .mp4 de entrada."),
    output_dir: Path = typer.Option(Path("./output"), "--output-dir", "-o", help="Carpeta de salida."),
    context: str | None = typer.Option(
        None,
        "--context",
        "-c",
        help=(
            "Prompt de contexto en lenguaje natural para mejorar la traduccion "
            "(dominio, tono, audiencia). Tambien puede ser la ruta a un .txt."
        ),
    ),
    glossary: Path | None = typer.Option(
        None, "--glossary", "-g", help="Ruta a un JSON {'termino_en': 'termino_es'}."
    ),
    tone: str | None = typer.Option(None, "--tone", help="Tono deseado: formal, informal, tecnico..."),
    mode: OutputMode = typer.Option(
        OutputMode.SOFT_SUBTITLES, "--mode", "-m", help="Modo de salida del video."
    ),
    keep_original_audio: bool = typer.Option(
        True, "--keep-original-audio/--no-keep-original-audio", help="Solo aplica a --mode dubbed."
    ),
    speaker_reference: Path | None = typer.Option(
        None, "--speaker-wav", help="Muestra de voz .wav para clonar el timbre en el doblaje (fallback si no hay diarizacion, o para video de un solo hablante)."
    ),
    diarize: bool = typer.Option(
        False,
        "--diarize/--no-diarize",
        help="Detecta multiples hablantes y clona la voz/estima el genero de cada uno por separado.",
    ),
    min_speakers: int | None = typer.Option(None, "--min-speakers", help="Pista opcional para la diarizacion."),
    max_speakers: int | None = typer.Option(None, "--max-speakers", help="Pista opcional para la diarizacion."),
    source_lang: str = typer.Option("en", help="Idioma de origen (codigo ISO)."),
    target_lang: str = typer.Option("es", help="Idioma de destino (codigo ISO)."),
    tts_workers: int | None = typer.Option(
        None,
        "--tts-workers",
        help="Procesos paralelos para la sintesis de voz (doblaje). Sin especificar, se "
        "auto-detecta segun los nucleos disponibles. 1 = secuencial (sin paralelismo).",
    ),
    group_segments: bool | None = typer.Option(
        None,
        "--group-segments/--no-group-segments",
        help="Fusiona segmentos consecutivos del mismo hablante (requiere --diarize) en "
        "una sola llamada de sintesis, para reducir el numero de llamadas en videos "
        "largos. Activado por defecto.",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        "-r",
        help="Reanuda el pipeline desde el ultimo checkpoint guardado en el workdir. "
        "Si se interrumpe un procesamiento largo (crash, corte de energia), "
        "usa esta opcion para saltar las etapas ya completadas.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Traduce un video completo: transcribe, traduce con contexto y genera subtitulos/doblaje."""
    settings = load_settings()

    # Antes de configure_logging, por dos motivos de orden: el puente de logs
    # busca un proveedor de OpenTelemetry YA configurado y devuelve None si no
    # lo encuentra, y argus.init() tambien toca el logging -- configurando
    # despues, gana lo que la app eligio. El nombre y el rol van aqui y no en
    # el entorno porque son fijos para este driver: la API y el worker los
    # pasan por proceso solo porque comparten codigo y se distinguen al
    # arrancar. El entorno si viene del entorno (ARGUS_ENVIRONMENT).
    if argus is not None:
        # namespace EXPLICITO: sin el, el SDK lo rellena con el nombre del
        # servicio ("prosodia-cli") y esta corrida no agrupa con la API ni el
        # worker en una consulta por namespace. Medido.
        argus.init(
            service="prosodia-cli",
            namespace="prosodia",
            role="cli",
            environment=settings.argus_environment,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "logs" / f"run_{datetime.now().astimezone():%Y%m%d_%H%M%S}.log"
    configure_logging(
        level="DEBUG" if verbose else settings.log_level,
        json_logs=settings.log_json,
        log_file=log_file,
    )
    console.print(f"[dim]Log completo de esta corrida: {log_file}[/dim]")

    if tts_workers is not None:
        settings.tts_parallel_workers = tts_workers
    if group_segments is not None:
        settings.tts_group_segments = group_segments

    context_prompt = _resolve_context_text(context)
    glossary_dict = _load_glossary(glossary)

    translation_context = TranslationContext(
        prompt=context_prompt or "",
        glossary=glossary_dict,
        source_lang=source_lang,
        target_lang=target_lang,
        tone=tone,
    )

    request = TranslateVideoRequest(
        input_video=input,
        output_dir=output_dir,
        context=translation_context,
        output_mode=mode,
        keep_original_audio_track=keep_original_audio,
        speaker_reference_wav=speaker_reference,
        source_lang_hint=source_lang,
        diarize=diarize,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )

    use_case = build_translate_video_use_case(
        settings,
        enable_dubbing=(mode == OutputMode.DUBBED),
        enable_diarization=diarize,
        resume=resume,
    )

    console.rule("[bold cyan]Video Translator")
    console.print(f"[bold]Entrada:[/bold] {input}")
    console.print(f"[bold]Modo:[/bold] {mode.value}")
    if resume:
        console.print("[bold yellow]Reanudacion:[/bold yellow] activada (saltara etapas completadas)")
    if diarize:
        console.print("[bold]Diarizacion:[/bold] activada (multi-hablante)")
    if context_prompt:
        console.print(f"[bold]Contexto:[/bold] {context_prompt[:120]}{'...' if len(context_prompt) > 120 else ''}")

    _install_signal_handlers()
    # Traza raiz de la corrida. Sin esto hay logs exportados pero sin TraceId:
    # un proceso por lotes no tiene peticion entrante que abra el span, al
    # contrario que la API. argus.init() registra el vaciado final en atexit,
    # que un proceso corto necesita o la telemetria muere con el.
    span = argus_run("cli.translate") if argus_run is not None else nullcontext()
    with span:
        try:
            with console.status("[bold green]Procesando video (esto puede tardar segun la duracion)..."):
                result = use_case.execute(request)
        except VideoTranslatorError as exc:
            logger.error("pipeline.failed", error=str(exc))
            console.print(f"[bold red]Error:[/bold red] {exc}")
            console.print(f"[dim]Detalle en el log: {log_file}[/dim]")
            raise typer.Exit(code=1) from exc
    _print_summary(result, log_file)


@app.command()
def check() -> None:
    """Verifica que las dependencias externas (ffmpeg, ollama) esten disponibles."""
    import shutil

    import httpx

    settings = load_settings()
    table = Table(title="Diagnostico de dependencias")
    table.add_column("Componente")
    table.add_column("Estado")

    ffmpeg_ok = shutil.which(settings.ffmpeg_binary) is not None
    table.add_row("ffmpeg", "[green]OK[/green]" if ffmpeg_ok else "[red]NO ENCONTRADO[/red]")

    ffprobe_ok = shutil.which(settings.ffprobe_binary) is not None
    table.add_row("ffprobe", "[green]OK[/green]" if ffprobe_ok else "[red]NO ENCONTRADO[/red]")

    backend = settings.translation_backend.lower()
    if backend == "llama_server":
        try:
            r = httpx.get(f"{settings.llama_server_host}/v1/models", timeout=5.0)
            llm_ok = r.status_code == 200
        except httpx.HTTPError:
            llm_ok = False
        table.add_row(f"llama-server ({settings.llama_server_model})", "[green]OK[/green]" if llm_ok else "[red]NO DISPONIBLE[/red]")
    else:
        try:
            r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=5.0)
            llm_ok = r.status_code == 200
        except httpx.HTTPError:
            llm_ok = False
        table.add_row("Ollama", "[green]OK[/green]" if llm_ok else "[red]NO DISPONIBLE[/red]")

    console.print(table)
    if not (ffmpeg_ok and ffprobe_ok and llm_ok):
        console.print("[yellow]Revisa el README.md para instrucciones de instalacion.[/yellow]")
        raise typer.Exit(code=1)


def _resolve_context_text(context: str | None) -> str | None:
    if context is None:
        return None
    maybe_path = Path(context)
    if maybe_path.exists() and maybe_path.is_file():
        return maybe_path.read_text(encoding="utf-8").strip()
    return context.strip()


def _load_glossary(glossary_path: Path | None) -> dict[str, str]:
    if glossary_path is None:
        return {}
    if not glossary_path.exists():
        raise typer.BadParameter(f"No existe el archivo de glosario: {glossary_path}")
    data = json.loads(glossary_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise typer.BadParameter("El glosario debe ser un objeto JSON {termino: traduccion}.")
    return {str(k): str(v) for k, v in data.items()}


def _print_summary(result: TranslateVideoResult, log_file: Path | None = None) -> None:
    console.rule("[bold green]Completado")
    table = Table(show_header=False)
    table.add_row("Duracion procesada", f"{result.duration_seconds / 60:.1f} min")
    table.add_row("Segmentos traducidos", str(len(result.segments)))
    table.add_row("Subtitulos EN", str(result.subtitles_source_path))
    table.add_row("Subtitulos ES", str(result.subtitles_target_path))
    if result.output_video:
        table.add_row("Video de salida", str(result.output_video))
    if result.timings:
        table.add_row("Tiempo total", _format_seconds(result.timings.get("total_seconds", 0)))
    if log_file is not None:
        table.add_row("Log completo", str(log_file))
    console.print(table)

    if result.speakers:
        speaker_table = Table(title="Hablantes detectados")
        speaker_table.add_column("ID")
        speaker_table.add_column("Genero estimado")
        speaker_table.add_column("Voz de referencia")
        for sp in result.speakers:
            speaker_table.add_row(
                sp.speaker_id,
                sp.gender or "desconocido",
                str(sp.reference_wav) if sp.reference_wav else "[red]sin muestra suficiente[/red]",
            )
        console.print(speaker_table)

    if result.timings and result.timings.get("stages"):
        report_path = result.subtitles_target_path.parent / "pipeline_timings.json"
        _print_timings_table(result.timings, report_path)


def _print_timings_table(timings: dict, report_path: Path) -> None:
    concurrent_groups = timings.get("concurrent_stage_groups") or []
    concurrent_names: set[str] = set()
    for group in concurrent_groups:
        concurrent_names.update(group)

    timings_table = Table(title="Tiempo por etapa del pipeline")
    timings_table.add_column("#", justify="right")
    timings_table.add_column("Etapa")
    timings_table.add_column("Duracion", justify="right")
    timings_table.add_column("% del total", justify="right")
    timings_table.add_column("Notas")

    # Llaves del esquema del reporte que no se repiten como "notas".
    standard_keys = {
        "order",
        "name",
        "seconds",
        "percent_of_total",
        "status",
        "started_at",
        "ended_at",
        "ran_concurrently",
        "resumed",
    }

    for stage in timings["stages"]:
        notes = []
        if stage.get("status") == "resumed":
            notes.append("reanudada: tiempo real de corrida anterior")
        elif stage["name"] in concurrent_names:
            notes.append("corrio en paralelo")
        extra_keys = [k for k in stage if k not in standard_keys]
        for k in extra_keys:
            notes.append(f"{k}={stage[k]}")
        timings_table.add_row(
            str(stage.get("order", "")),
            stage["name"],
            _format_seconds(stage["seconds"]),
            f"{stage['percent_of_total']:.1f}%",
            ", ".join(notes) if notes else "",
        )
    console.print(timings_table)
    console.print(f"[dim]Reporte completo: {report_path}[/dim]")

    if concurrent_groups:
        console.print(
            "[dim]Nota: las etapas marcadas 'corrio en paralelo' se solapan en el tiempo "
            "(por eso los porcentajes pueden sumar mas de 100%) — el tiempo total ya lo "
            "refleja correctamente.[/dim]"
        )
    console.print(f"[dim]Reporte completo (JSON) en: {report_path}[/dim]")


def _format_seconds(seconds: float) -> str:
    seconds = round(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


if __name__ == "__main__":
    app()
