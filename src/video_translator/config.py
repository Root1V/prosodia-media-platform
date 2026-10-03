"""Configuracion de la aplicacion, cargada desde variables de entorno / archivo .env.

Centralizar la configuracion tipada evita "magic strings" desperdigados por el
codigo y permite validar valores al arrancar (fail-fast) en vez de fallar a
mitad de un procesamiento de una hora de video.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Whisper / transcripcion
    # "faster_whisper" (CTranslate2, default multiplataforma; en Mac SOLO
    # corre en CPU, CTranslate2 no soporta Metal/MPS) | "mlx" (framework MLX
    # de Apple, usa la GPU va Metal -- solo macOS/Apple Silicon, requiere el
    # extra "transcription-mlx").
    whisper_backend: str = Field(default="faster_whisper")
    whisper_model_size: str = Field(default="large-v3")
    whisper_device: str = Field(default="cuda")
    whisper_compute_type: str = Field(default="float16")
    whisper_beam_size: int = Field(default=5)
    whisper_vad_filter: bool = Field(default=True)
    # 0 = usar todos los nucleos disponibles. Ajuste de mayor impacto para
    # transcripcion en CPU (p.ej. Mac sin CUDA): CTranslate2 no siempre
    # satura todos los nucleos por defecto.
    whisper_cpu_threads: int = Field(default=0)
    whisper_num_workers: int = Field(default=1)
    # Repo de Hugging Face con pesos ya convertidos a formato MLX. Solo se usa
    # si whisper_backend="mlx".
    mlx_whisper_model: str = Field(default="mlx-community/whisper-large-v3-mlx")

    # Ollama / traduccion
    translation_backend: str = Field(default="ollama")  # "ollama" | "llama_server"
    ollama_host: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen2.5:14b-instruct")
    ollama_temperature: float = Field(default=0.2)
    ollama_timeout_seconds: float = Field(default=120.0)
    translation_batch_max_chars: int = Field(default=1800)
    translation_context_window_segments: int = Field(default=6)

    # llama-server (llama.cpp) / cualquier backend compatible con la API de OpenAI
    llama_server_host: str = Field(default="http://localhost:8080")
    llama_server_model: str = Field(default="gpt-oss-20b-mxfp4")
    llama_server_max_tokens: int = Field(default=4096)
    llama_server_api_key: str | None = Field(default=None)

    # TTS / doblaje
    tts_backend: str = Field(default="index_tts2")  # "index_tts2" (recomendado) | "coqui_xtts"

    # IndexTTS-2.5 (recomendado): control nativo de duracion, ideal para doblaje
    index_tts2_model_dir: str = Field(default="third_party/index-tts/checkpoints")
    index_tts2_cfg_path: str = Field(default="third_party/index-tts/checkpoints/config.yaml")
    index_tts2_use_bf16: bool = Field(default=True)
    # None/vacio = autodetectar (cuda > mps > cpu). En macOS con
    # TTS_PARALLEL_WORKERS > 1 el contenedor fuerza "cpu" automaticamente
    # salvo que se fije este valor explicitamente (ver container.py): varios
    # procesos usando Metal (MPS) a la vez pueden crashear el driver de GPU y
    # reiniciar el sistema.
    index_tts2_device: str | None = Field(default=None)
    # Compila el sub-modelo s2mel (difusion, no autoregresivo) con
    # torch.compile: mismos pesos/calculo, sin perdida de calidad. Ya viene
    # soportado dentro de IndexTTS-2.5, solo apagado por defecto. Cada
    # proceso worker paga el costo de compilacion en su primera inferencia;
    # solo compensa si el worker sintetiza varios segmentos.
    index_tts2_use_torch_compile: bool = Field(default=False)
    # El GPT autoregresivo usa num_beams=3 internamente por defecto (no
    # documentado en el README). PROBADO en CPU: bajarlo a 1 NO acelero
    # gpt_gen_time (incluso salio un poco mas lento en la prueba) -- HuggingFace
    # generate() procesa los beams como dimension de batch en un solo forward
    # pass, y con margen de CPU libre el costo marginal de 3 beams es casi
    # nulo. No hay razon para bajarlo: no da velocidad y si arriesgaria calidad
    # (beam search reduce salidas degenerativas/repetitivas). Se deja
    # configurable solo por si un modelo/hardware futuro se comporta distinto.
    index_tts2_num_beams: int = Field(default=3)
    # Cuantos segmentos como maximo se batchean en una sola pasada del GPT
    # autoregresivo dentro de cada worker (ver IndexTTS2Synthesizer.
    # synthesize_batch). 1 = deshabilita el batching (cada worker procesa un
    # segmento a la vez, como antes). Experimental: combina con
    # TTS_PARALLEL_WORKERS -- mas procesos con batches mas chicos vs. menos
    # procesos con batches mas grandes es un tradeoff que conviene medir por
    # video (ver README, seccion de rendimiento de TTS).
    index_tts2_gpt_batch_size: int = Field(default=4)

    # Coqui TTS / XTTS v2 (alternativa mas liviana de instalar, requiere Python < 3.12)
    tts_model_name: str = Field(default="tts_models/multilingual/multi-dataset/xtts_v2")
    tts_device: str = Field(default="cuda")

    # Rendimiento de la sintesis de voz (doblaje), critico en videos largos:
    # 0 = auto-detectar (mitad de los nucleos disponibles, tope de 6 — cada
    # worker carga su propia copia del modelo en memoria, asi que no conviene
    # crear tantos como nucleos haya sin mas). 1 = secuencial (comportamiento
    # anterior, sin paralelismo).
    tts_parallel_workers: int = Field(default=0)

    # Agrupa segmentos consecutivos del MISMO hablante (requiere --diarize)
    # con poco silencio entre ellos en una sola llamada de sintesis, en vez
    # de una por cada segmento de Whisper (que en videos largos pueden ser
    # miles). Reduce drasticamente el numero de llamadas al motor de TTS.
    tts_group_segments: bool = Field(default=True)
    tts_group_max_gap_seconds: float = Field(default=0.5)
    tts_group_max_chars: int = Field(default=200)

    # Diarizacion de hablantes (opcional): quien habla, y clonacion de voz por hablante.
    # Corre en un venv AISLADO (ver scripts/setup_diarization_env.sh) via
    # subprocess, no como dependencia directa de este proyecto: pyannote.audio
    # y IndexTTS-2.5 tienen un conflicto real de version de protobuf que no
    # se puede resolver dentro de un unico entorno.
    diarization_python_bin: str = Field(default=".venv-diarization/bin/python")
    diarization_worker_script: str = Field(default="scripts/diarization_worker.py")
    diarization_model: str = Field(default="pyannote/speaker-diarization-community-1")
    diarization_device: str = Field(default="cpu")
    hf_token: str | None = Field(default=None)
    gender_detection_enabled: bool = Field(default=True)
    # macOS: carpeta "lib" de un entorno conda-forge con ffmpeg < 8 (ver README,
    # seccion de torchcodec/Homebrew). Se inyecta SOLO en el subprocess de
    # diarizacion, nunca en el proceso principal, para no romper el ffmpeg de
    # Homebrew que usa el resto del proyecto (DYLD_LIBRARY_PATH afecta a
    # cualquier binario que lo herede, por eso no se exporta globalmente).
    diarization_dyld_library_path: str | None = Field(default=None)

    # Medios
    ffmpeg_binary: str = Field(default="ffmpeg")
    ffprobe_binary: str = Field(default="ffprobe")
    audio_sample_rate: int = Field(default=16000)

    # General
    output_dir: Path = Field(default=Path("./output"))
    workdir: Path = Field(default=Path("./.work"))
    log_level: str = Field(default="INFO")
    log_json: bool = Field(default=False)

    # Entorno de despliegue que se reporta en la telemetria (ver RM-41). Se
    # lee aqui, y no del entorno del proceso, porque la CLI recibe TODA su
    # configuracion de .env via pydantic-settings -- que no vuelca a
    # os.environ, donde mira el SDK. Sin esto, un "video-translator translate"
    # pelado reportaba "local", que es el valor que acordamos no mandar: el
    # vocabulario es el cerrado del estandar de OpenTelemetry
    # (production/staging/test/development). El nombre del campo coincide a
    # proposito con ARGUS_ENVIRONMENT, asi que la variable de entorno tambien
    # lo pisa. La API y el worker no lo necesitan: se la pasan por proceso al
    # arrancar, como el nombre del servicio.
    argus_environment: str = Field(default="development")


def load_settings() -> Settings:
    return Settings()
