# Prosodia — AI Video Dubbing Pipeline (EN → ES, 100% Open Source)

[![CI](https://github.com/Root1V/ai-video-dubbing-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Root1V/ai-video-dubbing-pipeline/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Release](https://img.shields.io/github/v/release/Root1V/ai-video-dubbing-pipeline)](https://github.com/Root1V/ai-video-dubbing-pipeline/releases)

*The CLI and Python package keep the technical name `video-translator`; **Prosodia** is the project's name.*

A production-grade pipeline that turns an **hour-plus** English video with
**multiple speakers** into a dubbed Spanish video — with each person's voice
cloned individually, respecting their gender and timbre, and with
context-aware translation (domain, tone, glossary). Runs 100% locally on
open source models: no paid APIs, no data leaving your machine.

**End-to-end pipeline:**
1. **Transcribes** the original audio (Whisper via `faster-whisper`, streaming/VAD for long audio).
2. **Detects who's speaking and when** (diarization with `pyannote.audio`) and estimates each speaker's gender.
3. **Translates with context** using a local LLM (Ollama or `llama.cpp`), not a generic NMT translator: you can specify domain, tone, a glossary of mandatory terms, and it respects per-speaker gender agreement.
4. **Clones each speaker's voice individually** (IndexTTS-2.5, zero-shot voice cloning with native duration control) and syncs every line to its real time slot, adaptively compressing audio per-segment instead of cutting content off.
5. **Renders the final video** with dubbed audio (or subtitles, if preferred), via `ffmpeg`.

Built with **hexagonal architecture** (domain/application/infrastructure
decoupled via `Protocol` + dependency injection), unit tests with test
doubles, CI on GitHub Actions, and Python environment isolation for the case
where two AI stacks have unresolvable dependency conflicts (diarization vs.
dubbing) — a real-world AI systems engineering problem, not just a
single-file script.

> **New here? Before you clone:** this repo automates the *hard* parts
> (isolated environments, checkpoint downloads, GPU tuning) but three things
> stay manual regardless of your OS — see [Installation](#installation) for
> the full checklist:
> 1. A Hugging Face token with the diarization model's terms accepted (free, 2 minutes).
> 2. A local LLM server already running (Ollama or `llama-server`) — this project doesn't install or manage one for you.
> 3. `ffmpeg` on your `PATH`.

## Table of Contents

- [Key Features](#key-features)
- [AI Stack](#ai-stack)
- [Installation](#installation)
  - [Requirements](#requirements)
  - [Optional extras](#optional-extras-dubbing-engines-apple-gpu-transcription)
  - [Steps with `uv` (recommended)](#steps-with-uv-recommended)
  - [Steps with `pip` / classic venv](#steps-with-pip--classic-venv)
  - [Installing IndexTTS-2.5](#installing-indextts-25)
  - [Alternative dubbing engine: XTTS v2](#alternative-dubbing-engine-xtts-v2-coqui-tts)
  - [Installing diarization (isolated venv)](#installing-diarization-isolated-venv)
  - [macOS (Apple Silicon)](#macos-apple-silicon-m1m2m3m4)
  - [macOS: `libtorchcodec` error](#macos-if-you-see-a-libtorchcodec--libavutilnndylib-not-loaded-error)
  - [Docker (Linux / Windows with NVIDIA GPU)](#docker-linux--windows-with-nvidia-gpu)
- [Usage](#usage)
  - [Subtitles only](#subtitles-only-fastest-no-powerful-gpu-required)
  - [Subtitles burned into the video](#subtitles-burned-into-the-video)
  - [Subtitles as a selectable track](#subtitles-as-a-selectable-track-default)
  - [Full dubbing with voice cloning](#full-dubbing-with-voice-cloning-single-speaker)
  - [How overlapping voices are avoided](#how-overlapping-voices-are-avoided)
  - [Multiple speakers (`--diarize`)](#multiple-speakers-per-person-voice-and-gender---diarize)
  - [Context-driven translation](#context-driven-translation-applies-to-both-subtitles-and-dubbing)
  - [Using `llama-server` instead of Ollama](#using-llama-server-llamacpp-instead-of-ollama)
  - [Resuming an interrupted run](#resuming-an-interrupted-run---resume)
- [Architecture](#architecture)
- [Performance & Benchmarks](#performance--benchmarks)
  - [Handling long videos (>1h)](#handling-long-videos-1h)
  - [Keeping a 1h video under ~1h of processing](#keeping-a-1-hour-video-under-1-hour-of-processing)
  - [GPT-level batching](#gpt-level-batching-new-on-by-default)
  - [macOS: parallel TTS and GPU safety](#macos-parallel-tts-and-gpu-metal-safety)
  - [macOS: transcription and diarization on the GPU](#macos-transcription-and-diarization-on-the-gpu)
  - [Validated at scale](#validated-at-scale-3-minutes-to-a-full-72-minute-lecture)
- [Observability](#observability-where-did-the-time-go)
- [Web Dashboard (Prosodia Web)](#web-dashboard-prosodia-web--optional-admin-ui)
- [Testing](#testing)
- [Extensibility](#extensibility)
- [Author](#author)
- [License](#license)

## Key Features

- **Per-speaker zero-shot voice cloning** with native duration control (IndexTTS-2.5) — not generic post-hoc audio stretching.
- **Context-aware LLM translation**: domain prompt, tone, mandatory glossary, and per-speaker grammatical gender agreement — not a generic NMT model.
- **Automatic multi-speaker diarization**: one cloned voice per detected speaker, not a single flattened voice for the whole video.
- **Resumable pipeline** (`--resume`): safe to interrupt a multi-hour run and pick up exactly where it left off.
- **GPU-accelerated** on Apple Silicon (MLX + Metal) and NVIDIA (CUDA) — tuned per stage, not a single blanket "use GPU" switch.
- **Full observability**: a per-stage timing JSON plus structured logs for every run, so performance claims are independently verifiable.
- **Validated at scale**: dubs a 72-minute lecture end to end in ~117 minutes on a single Apple Silicon machine.
- **100% local and open source**: no paid APIs, no data leaving your machine.

## AI Stack

| Stage | Technology | Why |
|---|---|---|
| Transcription (STT) | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper large-v3 on CTranslate2) | Fast, accurate, built-in VAD for long audio without manual chunking |
| Diarization (optional) | [pyannote.audio](https://github.com/pyannote/pyannote-audio) (`speaker-diarization-community-1`) | Open source standard for detecting who's speaking and when, the basis for per-speaker voice cloning |
| Translation | Open source LLM via [Ollama](https://ollama.com) or [`llama-server`](https://github.com/ggerganov/llama.cpp) (Qwen2.5, Llama 3.1, gpt-oss, Mistral...) | Unlike a classic NMT model (NLLB/M2M100), an instruction-tuned LLM lets you **guide the translation with a natural-language context prompt**, and respect speaker/gender agreement |
| Dubbing (Spanish audio) | [IndexTTS-2.5](https://github.com/index-tts/index-tts) (recommended) or XTTS v2 (Coqui) | Zero-shot per-speaker voice cloning + **native duration control**, purpose-built for audiovisual sync in dubbing |
| Media | ffmpeg | Audio extraction, subtitles, remuxing, track mixing |

Everything runs locally; no paid external API is ever called.

## Installation

### Requirements
- Python 3.10, 3.11, or 3.12 (**not 3.13**: `TTS`/Coqui, used for dubbing, doesn't support 3.13 yet; the rest of the project would work fine on 3.13, but `pyproject.toml` pins it to `<3.13` to avoid the build failure). The repo includes `.python-version` set to `3.11`.
- [ffmpeg](https://ffmpeg.org/download.html) installed and on `PATH`.
- A local LLM backend already running: [Ollama](https://ollama.com/download) **or** [`llama-server`](https://github.com/ggerganov/llama.cpp) (see [Using `llama-server`](#using-llama-server-llamacpp-instead-of-ollama)). The pipeline is a *client* of this — it doesn't install, download, or start an LLM server for you.
- A [Hugging Face](https://huggingface.co) account + token, **only if you plan to use `--diarize`** (multi-speaker detection/voice cloning): create one at [hf.co/settings/tokens](https://hf.co/settings/tokens) and accept the terms on [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1). Not needed for single-speaker dubbing or subtitles-only modes.
- GPU recommended for long videos: NVIDIA (CUDA) on Linux/Windows, or Apple Silicon (Metal/MPS) on macOS — see [macOS (Apple Silicon)](#macos-apple-silicon-m1m2m3m4). CPU-only works but is much slower.

### Optional extras (dubbing engines, Apple GPU transcription)

The base install (`uv sync` / `pip install -e .`) only covers subtitles —
transcription, translation, and subtitle generation. Dubbing (`--mode
dubbed`) needs one more extra, and each does something genuinely different
(they're not interchangeable flags for the same feature):

| Extra | Adds | When to use it |
|---|---|---|
| `dubbing-indextts` | [IndexTTS-2.5](#installing-indextts-25) — recommended | Best sync/quality, but requires cloning a repo and downloading checkpoints (see below) |
| `dubbing-coqui` | XTTS v2 via Coqui TTS | Installs directly with `pip`/`uv`, no extra setup script — trade-off is less precise timing sync (post-hoc `ffmpeg` stretch instead of native duration control) |
| `transcription-mlx` | [`mlx-whisper`](#macos-transcription-and-diarization-on-the-gpu) | macOS + Apple Silicon only: GPU-accelerated transcription, ~16x faster than the CPU default in our testing |

`dubbing-indextts` and `dubbing-coqui` are **mutually exclusive** (`uv` will
refuse to install both — see the [alternative dubbing engine](#alternative-dubbing-engine-xtts-v2-coqui-tts)
section for why). `transcription-mlx` can be combined with either.

### Steps with `uv` (recommended)

```bash
git clone https://github.com/Root1V/ai-video-dubbing-pipeline.git
cd ai-video-dubbing-pipeline

uv python install 3.11     # if you don't already have it (uv downloads it for you)
uv sync                    # uses .python-version -> installs with Python 3.11, subtitles only

cp .env.example .env       # macOS: use `cp .env.macos.example .env` instead (pre-tuned for Apple Silicon)

# --- Pick ONE dubbing engine if you want --mode dubbed (skip both for subtitles-only) ---
./scripts/setup_index_tts2.sh          # recommended: clones third_party/index-tts, downloads checkpoints, runs `uv sync --extra dubbing-indextts`
# uv sync --extra dubbing-coqui        # ...or the simpler alternative, no script needed

# --- macOS + Apple Silicon only, optional but recommended ---
uv sync --extra transcription-mlx      # GPU-accelerated transcription

video-translator check      # verify ffmpeg + your LLM backend are reachable
```

### Steps with `pip` / classic venv

```bash
python3.11 -m venv .venv    # explicitly use 3.11 or 3.12, not 3.13
source .venv/bin/activate

pip install -e ".[dev]"                     # base install + dev tools (subtitles only)
pip install -e ".[dubbing-coqui]"           # optional dubbing (simpler alt.; for IndexTTS-2.5 use setup_index_tts2.sh instead, uv-only)
pip install -e ".[transcription-mlx]"       # optional, macOS + Apple Silicon only

cp .env.example .env             # macOS: cp .env.macos.example .env instead

./scripts/setup_models.sh qwen2.5:14b-instruct   # pulls this model into a local Ollama install

video-translator check           # verify ffmpeg / ollama (or llama-server)
```

> `IndexTTS-2.5` (the `dubbing-indextts` extra) resolves to a local path
> dependency (`third_party/index-tts/`, cloned by `setup_index_tts2.sh`) that
> `uv sync` needs to already exist on disk — this is why it's not a plain
> `pip install`-able extra and needs the setup script specifically. The
> `pip`/classic-venv path above only covers the simpler Coqui alternative for
> this reason; see [Installing IndexTTS-2.5](#installing-indextts-25) if you
> want the recommended engine without `uv`.

### Installing IndexTTS-2.5

Not on PyPI; it's resolved as a local path dependency pointing at the cloned
repo (`[tool.uv.sources]` in `pyproject.toml`). The script automates everything:

```bash
./scripts/setup_index_tts2.sh
```

This clones the repo into `third_party/index-tts`, runs `uv sync --extra dubbing-indextts`
(which installs it AND registers it in the `uv` lockfile), and downloads the checkpoints.

> **Important:** from now on always use `uv sync --extra <whatever>` to
> install or update dependencies, never a bare `pip install` / `uv pip install`.
> `uv sync` makes the environment match *exactly* what its lockfile knows —
> any package installed outside that mechanism (including `indextts`, if you
> installed it with a plain `pip install -e` instead of this script)
> **disappears the next time you run `uv sync`** for any other reason,
> because `uv` treats it as "foreign" to the project.

### Alternative dubbing engine: XTTS v2 (Coqui TTS)

If you'd rather avoid cloning repos and manually downloading checkpoints,
XTTS v2 installs directly with `pip`/`uv` (though without native duration
control, only post-hoc ffmpeg adjustment, so sync is somewhat less precise):

```bash
uv sync --extra dubbing-coqui        # requires Python < 3.12
```
```dotenv
TTS_BACKEND=coqui_xtts
```

> **Incompatible with `--extra dubbing-indextts`:** `TTS==0.22.0` (Coqui)
> requires `pandas<2.0`/`numpy<2.0`, and IndexTTS-2.5's transitive
> dependencies require newer versions — they're mutually exclusive extras
> (`uv` will explicitly block installing both). Use one or the other, not
> both in the same environment.

### Installing diarization (isolated venv)

`pyannote.audio` **is not a dependency of the main project**. It runs in a
**completely separate venv** invoked via subprocess, for a concrete reason:
`pyannote.audio` requires `protobuf>=5.0` (via its telemetry client
`pyannoteai-sdk`), and **IndexTTS-2.5 requires `protobuf<3.20`** (via
`descript-audiotools`) — this is a real version conflict with no possible
combination that satisfies both at once. If you ever see a `uv` "no solution
found" error mentioning `protobuf` when mixing diarization with dubbing,
that's this conflict: the fix isn't to look for another version, it's to
keep them in separate processes, which is exactly what this project does.

```bash
./scripts/setup_diarization_env.sh    # creates .venv-diarization/ with pyannote.audio + librosa
```

This script **does not touch your main venv** (`.venv/`); it creates a new
one (`.venv-diarization/`) just for this. The project invokes it via
subprocess when you use `--diarize` (see
`infrastructure/diarization/subprocess_diarizer.py` and
`scripts/diarization_worker.py`), so your main environment never imports
`pyannote.audio` directly and never clashes with `indextts`.

`pyannote.audio` also requires a Hugging Face token with terms accepted:
1. Create a token at [hf.co/settings/tokens](https://hf.co/settings/tokens).
2. Accept the model's terms on its page: [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1).
3. Set `HF_TOKEN` in your main project's `.env` (the subprocess receives it automatically).

### macOS (Apple Silicon: M1/M2/M3/M4)

There's no NVIDIA/CUDA GPU on Mac, so **don't use the `Dockerfile`/
`docker-compose.yml`** (see [Docker](#docker-linux--windows-with-nvidia-gpu) —
they're built for CUDA, and Docker Desktop on Mac can't pass Metal through to
the container anyway). On Mac everything runs natively, with `uv`
(recommended, since the IndexTTS-2.5 extra needs it — see
[Optional extras](#optional-extras-dubbing-engines-apple-gpu-transcription)):

```bash
brew install ffmpeg ollama
# The standard ffmpeg formula has no libass, so it can't burn subtitles/captions
# into a video (dubbing/subtitles "burn" mode, the micro-video service). If you
# need that, install `ffmpeg-full` (keg-only) instead and point FFMPEG_BINARY/
# FFPROBE_BINARY at its path -- see .env.example.

git clone https://github.com/Root1V/ai-video-dubbing-pipeline.git
cd ai-video-dubbing-pipeline

uv sync
uv sync --extra transcription-mlx      # GPU-accelerated transcription (see below) -- recommended

./scripts/setup_index_tts2.sh          # recommended dubbing engine, or:
# uv sync --extra dubbing-coqui        # simpler alternative

cp .env.macos.example .env             # already pre-tuned with everything validated below

ollama serve &                          # if it's not already running as a service
./scripts/setup_models.sh qwen2.5:32b-instruct

video-translator check
video-translator translate -i video.mp4 --mode soft_subtitles
```

**Settings `.env.macos.example` already applies, all validated end-to-end**
(see [Performance & Benchmarks](#performance--benchmarks)
for the numbers behind each one):

| Component | Setting | Why |
|---|---|---|
| Transcription | `WHISPER_BACKEND=mlx` (needs `transcription-mlx` extra) | Runs on the GPU via Apple's MLX framework — ~16x faster than the CPU-only default (`faster-whisper`/CTranslate2 has no Metal backend at all) |
| Diarization | `DIARIZATION_DEVICE=mps` | Not officially certified by `pyannote.audio`, but ~17x faster in testing, with no crashes across dozens of real runs |
| TTS (dubbing) | `TTS_PARALLEL_WORKERS=0` (auto → 8 on a 16-core Mac), CPU | Counter-intuitively, GPU (MPS) TTS was **3.2x slower** than parallel CPU workers here — IndexTTS-2.5's autoregressive step doesn't reliably speed up on MPS. Stays on CPU on purpose |
| Ollama (LLM) | No changes needed | Automatically Metal-accelerated |
| LLM model | Scale with your RAM: `qwen2.5:14b-instruct` (16-32GB) up to `qwen2.5:72b-instruct`/`llama3.1:70b-instruct` (128GB) | More unified memory → bigger model → better translation quality, no other trade-off |
| Coqui TTS (if used instead of IndexTTS-2.5) | `TTS_DEVICE=cpu` | XTTS v2 on MPS is unstable (unimplemented operators) |
| Docker | Don't use the included Dockerfile/compose | Built on `nvidia/cuda`; irrelevant on Mac, everything here runs natively |

If you're on the same class of hardware we validated this on (Apple Silicon
Max/Ultra, 64GB+ unified memory), you shouldn't need to tune anything beyond
copying `.env.macos.example` — see
[Validated at scale](#validated-at-scale-3-minutes-to-a-full-72-minute-lecture)
for the exact numbers (a 1-hour lecture dubs in ~1.5 hours end to end) and
what to check first if your results differ meaningfully.

### macOS: if you see a `libtorchcodec` / `libavutil.NN.dylib not loaded` error

`pyannote.audio >= 4.0` uses [`torchcodec`](https://github.com/pytorch/torchcodec)
to read audio, which on macOS has a **known, unresolved incompatibility with
Homebrew's FFmpeg** ([torchcodec#570](https://github.com/meta-pytorch/torchcodec/issues/570)) —
it's not fixed by installing a different Homebrew version. The fix that
actually works (recommended by the torchcodec team itself) is to use
**conda-forge** to get the FFmpeg libraries, **without exporting
`DYLD_LIBRARY_PATH` in your shell** (that would break the Homebrew
`ffmpeg`/`ffprobe` the rest of the project uses — it affects any binary that
inherits it, not just torchcodec). Instead, the project injects that
variable **only inside the isolated diarization subprocess**, via
`DIARIZATION_DYLD_LIBRARY_PATH` in your `.env`:

```bash
brew install miniforge
conda init zsh                       # restart your terminal after this

conda create -n ffmpeg-libs -c conda-forge "ffmpeg<8" -y   # <8: what torchcodec 0.7.0 supports

conda env list   # copy the path shown next to "ffmpeg-libs"
```

Set that path (+ `/lib`) in your `.env`:
```dotenv
DIARIZATION_DYLD_LIBRARY_PATH=/opt/homebrew/Caskroom/miniforge/base/envs/ffmpeg-libs/lib
```

Verify the library actually exists there before retrying:
```bash
ls "/opt/homebrew/Caskroom/miniforge/base/envs/ffmpeg-libs/lib" | grep libavutil
```
With that configured, `video-translator` works from any terminal — no need
to manually export anything each session.

### Docker (Linux / Windows with NVIDIA GPU)

No LLM server is bundled in `docker-compose.yml` — translation only needs
*any* OpenAI-compatible chat-completions endpoint reachable from the
container (`llama-server`, vLLM, Ollama, or your own inference platform),
configured via `TRANSLATION_BACKEND=llama_server` + `LLAMA_SERVER_HOST` (see
[Using `llama-server`](#using-llama-server-llamacpp-instead-of-ollama) — the
same generic OpenAI-compatible client works regardless of what's actually
serving the model). If that server runs on the host machine itself, point it
at `http://host.docker.internal:<port>` (already wired up via `extra_hosts`
in the compose file, including on Linux); use a real hostname/IP for a
remote one.

```bash
LLAMA_SERVER_HOST=http://host.docker.internal:8080 docker compose up --build
```

> **Heads up:** Docker Compose auto-loads a `.env` file in the project root
> for variable substitution — if you also use a plain `.env` for the CLI
> with `LLAMA_SERVER_HOST=http://localhost:...` in it, that value leaks into
> the container as-is (where `localhost` means the *container*, not your
> host) unless you override it on the command line as shown above.

Put your video at `./data/video.mp4` and your context at
`./data/context.txt`; output appears in `./output`. Requires Docker with
NVIDIA support (nvidia-container-toolkit); **doesn't apply to macOS**.

## Usage

### Subtitles only (fastest, no powerful GPU required)
```bash
video-translator translate -i video.mp4 -o ./output \
  --context "Nature documentary, slow narrative tone." \
  --mode subtitles_only
```

### Subtitles burned into the video
```bash
video-translator translate -i video.mp4 --mode burn_subtitles
```

### Subtitles as a selectable track (default)
```bash
video-translator translate -i video.mp4 --mode soft_subtitles
```

### Full dubbing with voice cloning (single speaker)

**Recommended engine: IndexTTS-2.5** ([index-tts/index-tts](https://github.com/index-tts/index-tts),
Bilibili/IndexTeam, open code and weights). It's the current state of the art
in open source TTS for this exact use case because:
- **Zero-shot** voice cloning: clones a speaker's timbre from just 6-15s of reference audio.
- Native Spanish support (plus English, Chinese, Japanese, Arabic).
- **Explicit duration control** (`duration_factor`): unlike XTTS v2, which generates at a free
  pace and depends on stretching/compressing the audio afterward with ffmpeg, IndexTTS-2.5 can
  generate voice aiming directly at the original segment's target duration — better
  lip/timing sync and less prosody distortion.
- Emotion control, useful so the dub doesn't sound flat in narrative content.

> Needs a dubbing engine installed first — see
> [Installing IndexTTS-2.5](#installing-indextts-25) (recommended) or the
> [XTTS v2 alternative](#alternative-dubbing-engine-xtts-v2-coqui-tts).

```bash
# extract a 6-15s clean audio sample of the original speaker
ffmpeg -i original_video.mp4 -ss 00:00:10 -t 12 -vn -ar 24000 -ac 1 voice_sample.wav

video-translator translate \
  -i original_video.mp4 \
  -o ./output \
  --mode dubbed \
  --speaker-wav voice_sample.wav \
  --context "This is a programming tutorial video, warm but professional tone." \
  -v
```

Result in `./output/lecture.dubbed.mp4` (the output name derives from the
input file name plus a mode suffix, so two different videos translated into
the same folder never overwrite each other): the original video with a second
Spanish audio track (the original is kept as a secondary track by default,
`--no-keep-original-audio` to replace it entirely) generated by IndexTTS-2.5,
with the original speaker's timbre, synced segment by segment with the
original transcription timing.

### How overlapping voices are avoided

Each line is synthesized aiming at the real gap available until the next one
starts (not the original transcription duration), in three layers that kick
in in order:
1. The TTS engine itself tries to generate the voice directly at that duration
   (IndexTTS-2.5's native duration control).
2. If it still runs long, speed is adjusted with `ffmpeg` within a range that
   doesn't distort the voice too much.
3. If it *still* doesn't fit, it's trimmed to the exact limit with a short
   fade-out (~80ms) — but **only when it's actually needed**, never
   unconditionally, so a clip that already fit well is left untouched.

The translation LLM is also asked to favor concise phrasing (similar length
to the source), specifically so layer 3 rarely has to kick in. If you notice
frequent voice cutoffs, check the `-v` logs
(`audio_mixing.segment_truncated`) — it tells you exactly how much each
segment overran its available slot, useful for deciding whether to ask for
even shorter translations via `--context`.

### Multiple speakers: per-person voice and gender (`--diarize`)

If the video has several people speaking, `--diarize` enables an extra
**diarization** step (detecting who speaks and when) with
[pyannote.audio](https://github.com/pyannote/pyannote-audio), the open
source standard for this. From there, the pipeline:

1. Assigns each transcript line to the corresponding speaker (by maximum temporal overlap).
2. Automatically extracts, for each detected speaker, their longest speaking turn (6-15s) as a voice reference sample.
3. Estimates each speaker's gender by voice pitch (F0), and passes it to the LLM as context so it adjusts Spanish grammatical gender agreement (e.g. "listo" vs "lista").
4. In `--mode dubbed`, **each speaker is cloned with their own voice** (not one generic voice for the whole video): person A's lines are synthesized with A's timbre, B's with B's.

> Requires the isolated diarization environment — see
> [Installing diarization](#installing-diarization-isolated-venv) if you
> haven't set it up yet.

```bash
video-translator translate \
  -i interview.mp4 \
  --mode dubbed \
  --diarize \
  --context "This is an interview between two people about artificial intelligence." \
  -v
```

No need to pass `--speaker-wav`: the system automatically extracts a voice
sample for each detected speaker. `--speaker-wav` is still available as a
*fallback* if a speaker doesn't have enough clean audio to generate their own
sample, or to force a single voice if you'd rather disable per-speaker
cloning.

If you know upfront how many people are speaking, narrow the search:
```bash
video-translator translate -i video.mp4 --mode dubbed --diarize --min-speakers 2 --max-speakers 2
```

When done, the CLI prints a table with the detected speakers, their
estimated gender, and whether a usable voice sample was successfully
extracted for each.

**Note on gender estimation:** it's a heuristic based on voice pitch
(fundamental frequency), not a precise demographic identification — it's
used solely as an auxiliary signal for Spanish grammatical agreement, not to
label people. `--diarize` is also useful without dubbing (e.g. with `--mode
soft_subtitles`) so the translation reflects each speaker's register in the
subtitles.

### Context-driven translation (applies to both subtitles and dubbing)

The `--context` parameter (or `TranslationContext.prompt`) is injected into
the LLM's *system prompt* along with:
- Desired **tone** (`--tone formal|informal|technical`).
- Mandatory **glossary** term→translation (`--glossary glossary.json`), to force consistency in product names, technical jargon, etc.

Example:

```bash
video-translator translate \
  --input pycon_talk.mp4 \
  --context "This is a technical PyCon talk about async Python. \
Use a warm but professional tone, aimed at developers. \
Keep terms like 'async', 'coroutine', 'event loop' in English." \
  --glossary glossary.json \
  --mode soft_subtitles
```

`glossary.json`:
```json
{
  "event loop": "event loop",
  "coroutine": "corrutina",
  "pull request": "pull request"
}
```

### Using `llama-server` (llama.cpp) instead of Ollama

If you already have a model running with `llama-server` (e.g.
`gpt-oss-20b-mxfp4`), you don't need Ollama. The project ships a second
adapter (`LlamaServerTranslator`) that talks to the OpenAI-compatible API
`llama-server` exposes (`POST /v1/chat/completions`), instead of Ollama's
native API (`/api/chat`).

```dotenv
TRANSLATION_BACKEND=llama_server
LLAMA_SERVER_HOST=http://localhost:8080
LLAMA_SERVER_MODEL=gpt-oss-20b-mxfp4
LLAMA_SERVER_MAX_TOKENS=4096
```

With your server already running (`llama-server -m gpt-oss-20b-mxfp4.gguf --port 8080 -c 8192`):

```bash
video-translator check          # now validates llama-server instead of Ollama
video-translator translate -i video.mp4 --mode soft_subtitles
```

Nothing else in the pipeline needs to change: `TranslateVideoUseCase` only
knows the `Translator` `Protocol`, so it doesn't matter whether Ollama,
llama-server, vLLM, or any other OpenAI-compatible backend sits underneath.
`container.py` decides which adapter to build based on
`TRANSLATION_BACKEND`.

A couple of things to watch with `llama-server`:
- Tune `-c` (context size) when starting the server based on your
  translation batch size (`TRANSLATION_BATCH_MAX_CHARS`); if a batch +
  history + system prompt exceeds the context, the server will truncate or
  fail.
- If you see `Error: LLM response misalignment: expected N lines...` with
  the raw response cut off mid-sentence, generation hit the
  `LLAMA_SERVER_MAX_TOKENS` limit (default 4096) before finishing the batch
  — raise that value in your `.env`, and make sure the server's `-c` is
  larger than `LLAMA_SERVER_MAX_TOKENS` + the input prompt size. The
  translator also automatically retries by splitting the batch in half when
  this happens (see `translate_batch_with_recovery` in `prompting.py`), so
  one unusually long batch shouldn't bring down the whole pipeline — but it's
  still worth raising the limit if you see it often, for efficiency.
- `gpt-oss-20b-mxfp4` is a model quantized in MXFP4 format: on an M4 Max
  with 128GB you have plenty of memory headroom; the bottleneck is usually
  generation speed, not memory.

### Resuming an interrupted run (`--resume`)

Even at the validated ~1.5x realtime factor, a multi-hour video is still a
multi-hour job — if the pipeline gets interrupted (power loss, Ctrl-C, crash,
reboot), you can resume it from the last completed stage with `--resume`/`-r`:

```bash
video-translator translate -i video.mp4 --mode dubbed --diarize --resume -v
```

The pipeline automatically saves a checkpoint (`_work/checkpoint.json`)
inside the output directory after each key stage:

| Stage | What's saved |
|---|---|
| Audio extraction | The extracted WAV file (verified by existence) |
| Transcription | Transcript segments + diarization segments (serialized as JSON) |
| Speaker profiles | Profiles with gender and reference clips (only with `--diarize`) |
| Translation | Translated segments (serialized as JSON) |
| Subtitles | The SRT files (verified by existence) |
| TTS synthesis | Each `tts_segments/group_NNNNNN.wav` file, verified individually |
| Final video | The output MP4 (verified by existence) |

On resume:
- Already-completed stages are skipped automatically (`pipeline.resume_skipping` shows up in the logs).
- For TTS, each already-generated WAV is checked individually — only the missing ones get synthesized.
- The checkpoint is validated against the input video, the output mode, and the `--diarize` flag: if any of those changed, it's ignored and the run restarts from scratch.
- Once the pipeline completes successfully, the checkpoint is deleted automatically.

**Tip**: use `--resume` by default; it costs nothing when there's no prior checkpoint, and saves hours if a long run ever gets interrupted.

## Architecture

Hexagonal architecture (Clean Architecture) with dependency inversion:

```
src/video_translator/
├── domain/            # Pure entities and exceptions (no external dependencies)
│   ├── models.py
│   └── exceptions.py
├── application/        # Use cases + ports (interfaces/Protocols)
│   ├── interfaces.py
│   ├── synthesis_job.py                  <- TTS job DTO, dispatched sequentially or in parallel
│   └── use_cases/translate_video.py     <- pipeline orchestrator (timing-instrumented)
├── infrastructure/     # Concrete adapters (implement the ports)
│   ├── media/ffmpeg_processor.py
│   ├── transcription/faster_whisper_transcriber.py
│   ├── translation/ollama_translator.py  <- context prompt applied here
│   ├── synthesis/
│   │   ├── index_tts2_synthesizer.py     <- single-pass inference
│   │   ├── parallel_tts_pool.py          <- multi-process TTS dispatch
│   │   └── coqui_tts_synthesizer.py
│   ├── diarization/subprocess_diarizer.py  <- isolated venv, subprocess-based
│   └── subtitles/srt_writer.py
├── utils/
│   ├── timing.py                          <- per-stage timing / observability
│   ├── synthesis_grouping.py              <- merges same-speaker segments before TTS
│   └── text_batching.py
├── config.py           # Typed configuration (pydantic-settings)
├── container.py        # Composition root (dependency injection)
└── cli.py               # Command-line interface (Typer)
```

**Why this structure:** the business logic (`application/`) never imports
anything from `infrastructure/`, only interfaces (`Protocol`). This allows:
- Swapping the LLM, STT engine, or TTS engine without touching the pipeline.
- Testing `TranslateVideoUseCase` with in-memory test doubles (see `tests/unit`), no ffmpeg/GPU required.
- Scaling the team: each adapter is developed and tested in isolation.

## Performance & Benchmarks

### Handling long videos (>1h)

- `faster-whisper` uses VAD (voice activity detection) internally, streaming the audio without manually chunking it or loading it fully into memory.
- Translation happens in **batches** (`utils/text_batching.py`), bounded by character count, to stay within the LLM's context window. A **rolling history** of recent translations is kept across batches to preserve terminology and style consistency throughout the whole video.
- Every batch is validated 1:1 (same number of input/output lines) and automatically retried (exponential backoff) on network errors or LLM misalignment.

### Keeping a 1-hour video under ~1 hour of processing

A 1-hour video can produce **1000+ transcript segments**. Naively processing
each one sequentially — especially through an autoregressive TTS model for
dubbing — is what turns a video into a 10-hour job. Four independent
optimizations attack this:

1. **Transcription and diarization run concurrently.** They're independent
   (both only need the extracted audio), and each can take tens of minutes
   on its own — running them sequentially just adds their times together for
   no reason. They now run in two threads (`_transcribe_and_diarize` in
   `translate_video.py`); the pipeline report shows both as
   `concurrent_stage_groups` so it's clear they overlapped.
2. **One TTS inference pass per segment, not two.** An earlier version
   generated speech once "at natural pace," measured the result, and — if it
   missed the target duration by more than 15% — generated it a *second*
   time with a corrected `duration_factor`. That's up to 2x the most
   expensive step in the whole pipeline, for every segment. Now a
   `duration_factor` is estimated upfront from a cheap chars-per-second
   heuristic (no generation needed to compute it), one inference pass runs,
   and the final precision fit is handled by `ffmpeg` (`fit_to_duration`,
   uncapped chained `atempo`, see the dubbing section above) — far cheaper
   than a second model call.
3. **Segments get grouped before synthesis** (`utils/synthesis_grouping.py`,
   `TTS_GROUP_SEGMENTS=true` by default). Consecutive lines from the *same
   confirmed speaker* (requires `--diarize`; segments without a resolved
   speaker are never merged, to avoid guessing) with little silence between
   them are merged into a single, longer TTS call instead of one call per
   short Whisper segment. Every TTS call has a fixed startup cost on top of
   the per-character cost; with 1000+ short segments that fixed cost
   dominates, so cutting the call count directly cuts wall time.
4. **TTS synthesis runs in a parallel process pool**
   (`infrastructure/synthesis/parallel_tts_pool.py`, `TTS_PARALLEL_WORKERS`,
   default `0` = auto-detect: half the available cores, capped at 6). Each
   worker process loads its own persistent copy of the model once and then
   processes jobs from a shared queue — on a multi-core machine with enough
   RAM (each worker needs its own model in memory, roughly 4-6GB for
   IndexTTS-2.5) this scales close to linearly with worker count. The use
   case builds every `SynthesisJob` upfront and dispatches them all via
   `synthesize_batch` when the configured synthesizer supports it (duck-typed
   via `hasattr`), falling back to the original one-at-a-time loop otherwise
   — so a plain, non-pooled synthesizer keeps working exactly as before.
5. **Each TTS worker process is capped to its fair share of CPU threads**
   (`parallel_tts_pool._init_worker`, via `OMP_NUM_THREADS`/`MKL_NUM_THREADS`/
   `torch.set_num_threads`). Without this, every worker process defaults to
   using *all* CPU cores for its own PyTorch/BLAS calls, so N workers end up
   oversubscribing the machine and competing with each other — measured on a
   real run, 3 CPU workers took exactly as long as running the same jobs
   sequentially. Splitting the core budget evenly across workers is what lets
   the parallelism in point 4 actually pay off.

None of this changes the anti-overlap/no-content-loss guarantees described
above — grouping and parallelism only change *how many* TTS calls happen and
*in what order*, never the final per-segment timing math.

### GPT-level batching (new, on by default)

IndexTTS-2.5's autoregressive GPT step is the single most expensive part of
synthesis. The underlying network is architecturally built to generate
several texts in one forward pass (same speaker, padded/masked per item) —
but the official `infer()`/`infer_generator()` API (in the vendored
[`third_party/index-tts`](https://github.com/index-tts/index-tts) repo,
**never modified by this project**) never uses that capability, because it
was designed for one-request-at-a-time use (a Gradio demo, a single API
call), not for batch-dubbing a video with hundreds of short segments.

**Where this lives:** entirely in *our* adapter,
[`IndexTTS2Synthesizer`](src/video_translator/infrastructure/synthesis/index_tts2_synthesizer.py)
— the class implementing the `SpeechSynthesizer` port for this engine. Two
methods matter:
- `synthesize_segment()`: the original, one-text-at-a-time path (unchanged) — estimates a `duration_factor`, calls `infer()` once, and lets `ffmpeg` do the final precision fit.
- `synthesize_batch()` (new): groups queued segments by speaker and, for each
  group of up to `INDEX_TTS2_GPT_BATCH_SIZE` (default 4), calls a private
  helper (`_synthesize_batch_same_speaker`) that reimplements the *setup*
  portion of `infer_generator()` (loading/caching the speaker's voice
  embedding) and then calls the model's internal GPT method
  (`tts.gpt.inference_speech(...)`) directly with a padded batch of texts,
  instead of one `infer()` call per text. Everything downstream of that —
  semantic codec decoding, the s2mel diffusion step, the bigvgan vocoder —
  still runs **per item, unbatched, on the exact same code path as
  `synthesize_segment`**; only the GPT call itself is batched, to keep the
  higher-risk part of the change as small as possible.
- `ParallelTTSPool` was updated to hand each worker a *chunk* of jobs instead
  of one job per future, so this batching actually gets exercised across
  processes, not just within a single sequential call.

**The trade-off — coupling to `third_party/index-tts`'s internals:** because
`infer()` never exposes batching, `synthesize_batch()` has to reach into
attributes that are *not* part of IndexTTS-2.5's public/documented API
(`tts.gpt`, `tts.cache_spk_cond`, `tts.semantic_codec`, `tts.s2mel`,
`tts.bigvgan`, ...). Those are implementation details of the version cloned
by `./scripts/setup_index_tts2.sh` today, not a versioned contract — if a
future IndexTTS-2.5 release restructures its internals, this specific method
could break silently even though `synthesize_segment()` (which only calls
the public `infer()`) keeps working. The code comments in
`index_tts2_synthesizer.py` cite the exact upstream file/lines this mirrors,
specifically so that risk is easy to re-check after an upstream update.

Caught (and fixed, with regression tests) two real correctness bugs while
building this: one had every batch item silently decoding the *first* item's
audio content instead of its own (found via an ASR round-trip check — each
generated clip was transcribed back and compared against its intended text),
and one crashed on a degenerate "stops immediately" generation. Both are
now covered by unit tests against a pure `_split_batched_codes` helper.

We also tried enabling `torch.compile` on the model's non-autoregressive
s2mel sub-module (`INDEX_TTS2_USE_TORCH_COMPILE=true` — wired through but
off by default): it's a genuinely free, same-weights optimization already
built into IndexTTS-2.5, but each short-lived worker process only handles a
couple of segments before exiting, so the one-time compilation cost per
process never gets amortized — net effect on a real run was a wash (within
run-to-run noise). It only makes sense with a very different architecture
(long-lived worker processes handling many segments each), which is a
bigger change than flipping this flag. Separately, we found (and rejected)
that lowering IndexTTS-2.5's internal `num_beams` from 3 to 1 does **not**
speed anything up on CPU — HuggingFace's `generate()` runs beams as a batch
dimension in one forward pass, and with CPU headroom to spare the marginal
cost of 3 beams over 1 is close to free — so there's no reason to risk the
quality trade-off of fewer beams for zero speed gain.

### macOS: parallel TTS and GPU (Metal) safety

**Do not force `INDEX_TTS2_DEVICE=mps` together with `TTS_PARALLEL_WORKERS > 1`.**
IndexTTS-2.5 auto-selects Metal (MPS) on Apple Silicon when no device is
specified, and several *separate processes* each grabbing their own Metal
context at the same time is a known-unstable combination on macOS — it can
crash the GPU driver and **force a full system reboot** (not a normal Python
exception you can catch or recover from). The project handles this
automatically: whenever `TTS_PARALLEL_WORKERS`/`--tts-workers` is above 1 on
macOS and you haven't explicitly set `INDEX_TTS2_DEVICE`, it forces `cpu` for
every worker process, logging a warning so it's clear why. Parallelism still
helps — you get real speedup from multiple CPU processes on a multi-core
Mac — it just doesn't also try to share the GPU across them. A single worker
(`--tts-workers 1`) is unaffected and keeps using MPS normally, since that's
the officially supported single-process use case.

**Quick tuning knobs**, no `.env` editing required:
```bash
video-translator translate -i video.mp4 --mode dubbed --diarize \
  --tts-workers 8 --group-segments -v
```
The auto-detected worker count (`TTS_PARALLEL_WORKERS=0`) now goes up to one
worker per core, capped at 8 (not "half the cores capped at 6" like before).
That cap was tuned on realistic-length videos, not just short clips: on a
14-job 3-minute clip more workers kept helping all the way up to one worker
per job, but on 10/30/60-minute videos (44-269 jobs) **8 was the actual
sweet spot** — 4 workers measured ~17.7s/job, 8 measured 14.3-17.3s/job (the
best of the three), and 12 measured ~18.3s/job, worse than 8. Past a certain
point, each worker getting fewer CPU threads costs more than the extra
process-level parallelism buys back. If you process very short clips
routinely, `--tts-workers` above the cap can still help there specifically.

### macOS: transcription and diarization on the GPU

`faster-whisper` (the default transcription engine) runs on CTranslate2,
which has **no Metal/MPS backend** — on a Mac it is always CPU-bound,
regardless of configuration. If you install the `transcription-mlx` extra
(`pip install "video-translator[transcription-mlx]"`, Apple Silicon only) you
can switch to [`mlx-whisper`](https://github.com/ml-explore/mlx-examples)
instead, which runs on the GPU via Apple's MLX framework:

```bash
# .env
WHISPER_BACKEND=mlx
MLX_WHISPER_MODEL=mlx-community/whisper-large-v3-mlx
```

The rest of the `WHISPER_*` settings (`compute_type`, `cpu_threads`, ...) are
specific to the `faster_whisper` backend and don't apply when using `mlx`.
pyannote.audio's diarization also isn't officially certified for MPS, but
running it there works in practice — just set `DIARIZATION_DEVICE=mps`, no
code changes needed.

Measured on an M4 Max with a real 3-minute, single-speaker clip (warm model
cache; the very first `mlx` run also pays a one-time ~3GB Hugging Face
download):

| Stage | CPU (default) | GPU (Metal/MPS) | Result |
|---|---|---|---|
| Transcription (`WHISPER_BACKEND=mlx`) | 136s (faster-whisper) | **8.6s** (mlx-whisper) | ~16x faster |
| Diarization (`DIARIZATION_DEVICE=mps`) | 166s | **10s** | ~17x faster |
| TTS (`TTS_PARALLEL_WORKERS=1`, `INDEX_TTS2_DEVICE=mps`) | 328s (6 CPU workers) | 1059s (1 GPU worker) | **3.2x *slower* — don't use** |

Transcription and diarization run concurrently (point 1 above), so together
they went from a ~166s critical-path block down to ~10-14s. TTS is the
exception: IndexTTS-2.5's autoregressive generation step didn't reliably
speed up on MPS (sometimes matching CPU speed), and losing the 6-way process
parallelism outweighed whatever the GPU saved on the non-autoregressive
parts of the model (`s2mel`/`bigvgan`, which *did* speed up substantially).
Keep TTS on CPU with multiple workers; only try MPS there if you have a
different TTS backend/model where this trade-off might not hold.

End to end, on the same 3-minute clip, this took the total pipeline time from
~530s down to ~416s (`realtime_factor` 2.31) — with TTS now representing
~88% of the remaining time, by far the biggest lever left if you want to go
faster still.

### Validated at scale: 3 minutes to a full 72-minute lecture

All of the above was re-verified end to end (not just unit-tested) on real
Stanford lecture recordings at 3, 10, 30, 60, and 72.5 minutes (the full
source video, unclipped) — M4 Max, GPT batching on, `WHISPER_BACKEND=mlx`,
`DIARIZATION_DEVICE=mps`:

| Video length | TTS workers | Synthesis jobs | `s/job` (TTS) | Total processing time | `realtime_factor` |
|---|---|---|---|---|---|
| 3 min | 4 | 14 | — | ~5-7 min | ~2.3x |
| 10 min | 4 | 44 | 17.7s | ~15 min | 1.52x |
| 10 min | **8** | 75 | **14.3s** | ~14 min | — |
| 10 min | 12 | 55 | 18.3s | ~20 min | 1.96x |
| 30 min | 8 | 125 | 17.3s | ~45 min | 1.51x |
| 60 min | 8 | 269 | 15.6s | ~89 min | 1.48x |
| 72.5 min (full video) | 8 | 328 | — | — | (this config) |
| 72.5 min (full video) | 10 | 328 | 17.1s | ~117 min | 1.61x |

Two things stand out. First, `realtime_factor` holds steady around 1.5x from
10 minutes onward — fixed per-run overhead (model loading, etc.) is a
shrinking fraction of the total as the video gets longer, so the pipeline
scales predictably rather than degrading on long inputs; a 1-hour lecture
finishes in under 1.5 hours end to end, dubbed audio included. Second, more
TTS workers is **not** always faster: at every video length we tested with
more than one worker count, 8 workers beat both fewer (4) and more (10, 12)
— going past 8 means each worker gets less than 2 CPU threads (16 cores ÷
worker count) and ends up fighting the others for memory bandwidth (each
worker holds its own ~4-6GB model copy) for no net gain. `TTS_PARALLEL_WORKERS`
auto-detects to this validated value; only override it if you've profiled
your own hardware and confirmed a different number wins.

TTS remains ~43-45% of total time at every length past the first few
minutes — it's still the biggest lever if you want to go faster still. This
testing also exercised real multi-speaker content (two speakers in the
30- and 60-minute clips, three in the full 72.5-minute lecture, several of
them too brief to get a clean voice reference of their own): a segment with
no matching diarization turn, or belonging to a speaker with no usable
reference clip, now falls back to the one speaker that *does* have a
reference instead of aborting the whole dubbed render.

## Observability: where did the time go?

Every stage is timed (`utils/timing.py`) and reported two ways:
- **A summary table** printed at the end of the run (order, durations, % of total,
  and a note on which stages ran concurrently or were resumed from a previous run).
- **A JSON report** written to `<output_dir>/pipeline_timings.json` and
  **updated incrementally after every stage** (and even when a stage starts, via
  `current_stage`), so a crashed run still leaves an accurate partial snapshot
  (`"completed": false`). You can diff timings between runs (e.g. after tuning
  `--tts-workers`) instead of guessing from scrollback logs.

```json
{
  "run_id": "a1b2c3d4e5f6",
  "run_ids": ["9f8e7d6c5b4a", "a1b2c3d4e5f6"],
  "started_at": "2026-08-21T10:00:00+00:00",
  "generated_at": "2026-08-21T10:35:40+00:00",
  "completed": true,
  "resumed_run": false,
  "total_seconds": 2140.3,
  "num_stages": 9,
  "sum_of_stage_seconds": 5411.7,
  "overhead_seconds": 3.2,
  "parallel_time_saved_seconds": 1802.5,
  "concurrent_stage_groups": [["transcription", "diarization"]],
  "input": {"video": "video/lecture.mp4", "duration_seconds": 3615.2},
  "realtime_factor": 0.59,
  "effective_config": {
    "whisper_model": "large-v3", "whisper_device": "cpu", "whisper_compute_type": "int8",
    "translation_backend": "llama_server", "llm_model": "gpt-oss-20b-mxfp4",
    "diarize_enabled": true, "tts_backend": "index_tts2", "tts_workers": 3,
    "tts_device_forced_cpu": true
  },
  "warnings": [
    {"source": "audio_mixing.overflow_after_compression", "segment_index": 2, "overflow_seconds": 0.27}
  ],
  "stages": [
    {"order": 1, "name": "audio_extraction", "status": "completed", "seconds": 4.1, "percent_of_total": 0.2, "started_at": "...", "ended_at": "..."},
    {"order": 2, "name": "transcription", "status": "completed", "seconds": 1802.5, "percent_of_total": 84.2, "ran_concurrently": true, "num_segments": 1284},
    {"order": 3, "name": "diarization", "status": "completed", "seconds": 1950.7, "percent_of_total": 91.1, "ran_concurrently": true, "num_speakers": 2, "num_turns": 340},
    {"order": 4, "name": "speaker_profile_building", "status": "completed", "seconds": 8.3, "percent_of_total": 0.4, "num_speakers": 2},
    {"order": 5, "name": "translation", "status": "completed", "seconds": 95.2, "percent_of_total": 4.4, "num_segments": 1284, "num_batches": 42},
    {"order": 6, "name": "subtitles_writing", "status": "completed", "seconds": 0.1, "percent_of_total": 0.0},
    {"order": 7, "name": "rendering_dubbed", "status": "completed", "seconds": 1620.4, "percent_of_total": 75.7},
    {"order": 8, "name": "tts_synthesis", "status": "completed", "seconds": 1540.8, "percent_of_total": 72.0, "num_jobs": 412, "num_segments_input": 1284, "num_groups": 412, "grouping_reduction_pct": 67.9},
    {"order": 9, "name": "audio_mixing_and_muxing", "status": "completed", "seconds": 79.6, "percent_of_total": 3.7}
  ]
}
```
Each stage carries an `order` (execution sequence), a `status`
(`"completed"` or `"resumed"`), and `started_at`/`ended_at` UTC timestamps.
When you relaunch with `--resume`, skipped stages keep the **real duration they
had in the previous run** (`"status": "resumed"`) — the report is adopted from
the existing file instead of resetting them to 0.0s — so the final report is
still a faithful profile of the total work.
(`percent_of_total` is computed against `sum_of_stage_seconds` — the total
recorded work, including durations inherited from a previous run on resume —
so stage percentages always add up to ~100%; note that `rendering_dubbed`
nests `tts_synthesis`/`audio_mixing_and_muxing` inside it, so those overlap.
The top-level `total_seconds` remains the real wall-clock number.) Every
stage's start/end is also logged with `-v`, tagged
with a `run_id` shared across the whole run, so log lines from concurrent
stages (or, eventually, multiple runs interleaved in a shared log stream)
can be told apart. The report also carries `run_ids`: the full chain of runs
that produced the result (one per `--resume` relaunch), current run last.

**Every log line is also persisted to a file**, not just printed to the
terminal: `<output_dir>/logs/run_<timestamp>.log` (plain text, no ANSI color
codes, so it's readable in any editor or `grep`-able). The CLI prints its
path both at the start and end of the run. This means you don't need `-v`
open in a terminal you can't lose — a long run's full log (including any
error, if the pipeline fails partway through) survives in the output
directory alongside the subtitles and the timings report. Set
`LOG_JSON=true` in your `.env` if you'd rather have the file (and console) in
structured JSON-lines instead of the human-readable format.

## Web Dashboard (Prosodia Web) — optional admin UI

**Status: work in progress (Milestones 1-2 of 6 done).** A web dashboard
(React + FastAPI + Celery/Redis + Postgres) is being built as a second
"driver" alongside the CLI — same `application`/`domain` layers, same
`container.build_translate_video_use_case`, nothing in the core pipeline is
modified for it.

**What actually works today:** login, creating a project by uploading a
video via drag-and-drop, and **real** dubbing/subtitles/transcription
processing — the background job calls the same pipeline the CLI does, and
the project detail page polls live progress (stage by stage) straight from
`pipeline_timings.json`, exactly like the CLI's own summary table. You can
also download the finished video/subtitles and retry a failed project.

**What's still missing** (tracked as later milestones, not bugs):

| Milestone | What it adds | Status |
|---|---|---|
| M1 — Foundation | Auth, project CRUD, drag-and-drop upload | ✅ Done |
| M2 — Real pipeline integration | Real dubbing/subtitles/transcription runs, live progress, downloads, retry | ✅ Done |
| M3 — YouTube import | The "Buscar en YouTube" tab (currently disabled/"Próximamente") | Pending |
| M4 — Subtitles/transcription pages | Dedicated forms for those two services (currently placeholder pages) | Pending |
| M5 — Voices & templates libraries | Reusable saved voice clips / context presets | Pending |
| M6 — Admin pages | User management UI, editable settings, dashboard stats (currently always "—") | Pending |

Code lives in `src/video_translator/web/` (backend) and `frontend/`
(React SPA) — neither is required to use the CLI; this is purely additive.

### Prerequisites

- [Docker](https://www.docker.com/) (for Postgres + Redis — or point at
  your own instances if you already run them).
- [Node.js](https://nodejs.org/) 18+ (for the frontend).
- The `web` extra installed: `uv sync --extra web`.

  > **If you already use this project for dubbing/transcription, don't run
  > that command alone.** `uv sync` makes the environment match *exactly*
  > the extras listed in that one invocation — it's not additive across
  > separate calls. Running just `uv sync --extra web` on a venv that
  > already had, say, `dubbing-indextts`/`transcription-mlx` installed
  > **uninstalls them** (you'll see a long list of `- package` removals).
  > Always list every extra you want installed *at once*:
  > ```bash
  > uv sync --extra web --extra dev --extra dubbing-indextts --extra transcription-mlx
  > ```
  > (swap in whichever dubbing/transcription extras you actually use). If
  > this already happened to you, that same command restores everything.

- To actually process videos (not just click around the UI), the Celery
  worker needs the **same dependencies you'd use to run the CLI** — a
  dubbing engine extra if you want `--mode dubbed` (see
  [Optional extras](#optional-extras-dubbing-engines-apple-gpu-transcription)),
  your LLM backend running, etc. The worker reads the same `.env` the CLI
  does.

### Running it: two ways

**Option A — one command (Linux/Windows with an NVIDIA GPU, same
requirement as the CLI's [Docker](#docker-linux--windows-with-nvidia-gpu)
path — doesn't apply to macOS):** `docker-compose.yml` now has every piece
(`postgres`, `redis`, `api`, `worker`, `frontend`), reusing the same image as
the `video-translator` CLI service for `worker` (it needs the same
faster-whisper/TTS dependencies to actually process videos).

```bash
LLAMA_SERVER_HOST=http://host.docker.internal:8080 docker compose up --build postgres redis api worker frontend

# once it's up, in another terminal:
docker compose exec api python3.11 scripts/create_admin.py --email admin@example.com --password "change-me" --name "Admin"
```

Open `http://localhost:3000` (the dashboard is served by `frontend`'s nginx,
which proxies `/api` to the `api` service — not `http://localhost:8000`
directly, that's the raw API). Migrations don't run automatically either;
apply them once against the `api` container the same way as the admin
script above: `docker compose exec api alembic upgrade head`.

**Option B — local processes with hot reload (recommended while actively
developing the dashboard itself):**

```bash
# 1. Postgres + Redis only
docker compose up -d postgres redis

# 2. Apply the database schema
uv run alembic upgrade head

# 3. Create the first admin user (no self-registration by design)
uv run python scripts/create_admin.py --email admin@example.com --password "change-me" --name "Admin"

# 4. API (in one terminal)
uv run uvicorn video_translator.web.main:app --reload --port 8000

# To also emit telemetry to Argus (RM-41), prefix with --env-file and set the
# OTEL_* vars in .env (see .env.example). pydantic-settings reads .env for its
# own settings but does NOT export it to os.environ, which is where the
# OpenTelemetry SDK looks -- so --env-file is what actually makes them arrive:
#   uv run --env-file .env uvicorn video_translator.web.main:app --port 8000
# Natively the endpoint is http://localhost:4318; the host.docker.internal in
# docker-compose.yml only resolves inside a container.

# 5. Celery worker (in another terminal — required, or projects stay "queued" forever)
# --pool=solo: Celery's default "prefork" pool forks a child process, and
# GPU-backed libraries (MLX/Metal on macOS, CUDA has the same documented
# issue) don't reliably survive that -- you'd otherwise hit errors like
# "Unable to reach MTLCompilerService" the moment a real job tries to use
# the GPU, even though the exact same .env works fine through the CLI
# (which never forks). "solo" runs everything in the one process, no fork.
uv run celery -A video_translator.web.tasks.celery_app worker --loglevel=info --pool=solo

# 6. Frontend (in another terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api to localhost:8000, hot-reloads on save
```

Either way, log in with the admin you just created and upload a video from
**Doblaje de Video** to watch it move through `queued` → `running` →
`completed` against the real pipeline, with the stage timeline updating
live.

> **macOS + `transcription-mlx`, known `uv` resolution quirk:** installing
> `transcription-mlx` **by itself** (`uv sync --extra web --extra
> transcription-mlx`) makes `uv` resolve `mlx-whisper`'s `torch` dependency
> to the Linux/CUDA wheel, which fails to install on macOS. This is a
> pre-existing lockfile edge case, not specific to the web module. Workaround:
> install `dubbing-indextts` alongside it (it happens to pull in a
> macOS-compatible `torch` too, since IndexTTS-2.5 needs one):
> ```bash
> uv sync --extra web --extra dev --extra transcription-mlx --extra dubbing-indextts
> ```
> If you'd rather not deal with this, leave `WHISPER_BACKEND=faster_whisper`
> (the default) in your `.env` — slower on Mac, but unaffected by this.

### Configuration

Settings live in a separate `.env.web` file (not the pipeline's `.env` —
this is a distinct concern), read by `WebSettings`
(`src/video_translator/web/config.py`). Sane defaults matching the
`docker compose up -d postgres redis` setup above are built in, so local
development works with no `.env.web` at all:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://prosodia:prosodia@localhost:5432/prosodia` | Matches `docker-compose.yml`'s `postgres` service |
| `REDIS_URL` | `redis://localhost:6379/0` | Matches the `redis` service |
| `JWT_SECRET_KEY` | an insecure, clearly-marked dev value | **Set a real secret before exposing this beyond localhost** |
| `JWT_EXPIRE_MINUTES` | `720` (12h) | |
| `STORAGE_ROOT` | `./data/prosodia_web` | Uploaded videos and per-project output directories |
| `CORS_ORIGINS` | `["http://localhost:5173", "http://localhost:3000"]` | Add your deployed frontend origin here |

### Testing the web module

```bash
uv run pytest tests/unit/web -v      # backend: in-memory SQLite, no Postgres/Redis needed
cd frontend && npm run build          # frontend: TypeScript + Vite production build
```

## Testing

```bash
pytest --cov=video_translator --cov-report=term-missing
ruff check src tests
mypy src
```

Unit tests use test doubles (fakes) for the four core interfaces
(`MediaProcessor`, `Transcriber`, `Translator`, `SubtitleWriter`), so they
run in seconds without needing ffmpeg, a GPU, or a real LLM.

## Extensibility

- **Another translation LLM**: create a new class implementing `Translator`
  (e.g. using local `transformers` instead of Ollama) and register it in `container.py`.
- **Another STT engine**: implement `Transcriber` (e.g. `whisper.cpp` via bindings).
- **Other languages**: the pipeline is agnostic to the language pair; change
  `source_lang`/`target_lang` in `TranslationContext`.

## Author

**Victor Espiritu** ([@Root1V](https://github.com/Root1V))

## License

MIT — see [LICENSE](LICENSE).
