"""Construccion de prompts y parseo de respuesta, compartido entre backends LLM.

Tanto OllamaTranslator como LlamaServerTranslator (o cualquier otro backend que
hable con un LLM instructivo) usan exactamente la misma estrategia de prompting:
solo cambia el transporte HTTP (API nativa de Ollama vs. API compatible con
OpenAI de llama.cpp/llama-server, vLLM, LM Studio, etc.).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from video_translator.domain.exceptions import TranslationError
from video_translator.domain.models import TranscriptSegment, TranslationContext

SYSTEM_PROMPT_TEMPLATE = """Eres un traductor profesional especializado en subtitulado y \
doblaje de video, traduciendo de {source_lang} a {target_lang}.

Reglas estrictas de formato:
- Recibiras lineas de texto numeradas (1, 2, 3, ...). Algunas pueden incluir una etiqueta de \
hablante entre corchetes al inicio, p.ej. "[Hablante SPEAKER_00 - voz masculina]".
- Debes devolver EXACTAMENTE el mismo numero de lineas, en el mismo orden, cada una \
precedida por su numero y un punto, en el formato "N. traduccion" — SIN repetir la \
etiqueta de hablante en tu respuesta, solo la traduccion del texto.
- Traduce el SENTIDO y el REGISTRO, no palabra por palabra; que suene natural al hablarse.
- No agregues explicaciones, notas, ni texto fuera de las lineas numeradas.
- Conserva nombres propios, siglas y numeros tal como aparecen salvo que el glosario \
indique lo contrario.
- Manten la coherencia terminologica con las traducciones previas mostradas como contexto.
- Estas lineas se usaran para generar voz sintetica que debe encajar en el mismo tiempo que \
duraba la frase original: prioriza traducciones CONCISAS, de longitud similar al original en \
numero de silabas/palabras, evitando rodeos o formulas mas largas cuando haya una opcion mas \
corta con el mismo significado. Esto es mas importante aun que sonar perfectamente idiomatico.
- Cuando una linea indique el genero del hablante, ajusta la concordancia gramatical del \
espanol en consecuencia (p.ej. adjetivos y participios: "estoy cansado" vs "estoy cansada"). \
Si no se indica genero, usa formas neutras o el masculino generico solo cuando sea inevitable.
- Si varios hablantes distintos participan, manten el registro y las muletillas de cada uno \
consistentes a lo largo de sus propias lineas (no mezcles el estilo de un hablante con el de otro).
"""

_GENDER_LABELS_ES = {"male": "voz masculina", "female": "voz femenina", "unknown": "genero no determinado"}


def build_system_prompt(context: TranslationContext) -> str:
    base = SYSTEM_PROMPT_TEMPLATE.format(
        source_lang=context.source_lang, target_lang=context.target_lang
    )
    extras = []
    if context.tone:
        extras.append(f"Tono deseado: {context.tone}.")
    if context.prompt:
        extras.append(f"Contexto del contenido (usalo para mejorar la calidad):\n{context.prompt}")
    if context.glossary:
        glossary_lines = "\n".join(f"- \"{k}\" -> \"{v}\"" for k, v in context.glossary.items())
        extras.append(
            f"Glosario obligatorio (usa siempre esta traduccion para estos terminos):\n{glossary_lines}"
        )
    if context.speaker_genders:
        speaker_lines = "\n".join(
            f"- {label}: {_GENDER_LABELS_ES.get(gender, gender)}"
            for label, gender in context.speaker_genders.items()
        )
        extras.append(
            "Genero estimado de cada hablante detectado (usalo para la concordancia "
            f"gramatical en espanol):\n{speaker_lines}"
        )
    if extras:
        base += "\n" + "\n\n".join(extras)
    return base


def build_user_prompt(
    segments: list[TranscriptSegment],
    rolling_history: list[str],
    speaker_genders: dict[str, str] | None = None,
) -> str:
    parts = []
    if rolling_history:
        history_block = "\n".join(rolling_history)
        parts.append(
            "Traducciones recientes (solo como referencia de estilo, no las repitas):\n"
            f"{history_block}"
        )
    numbered = "\n".join(
        f"{i}. {_format_line(seg, speaker_genders)}" for i, seg in enumerate(segments, start=1)
    )
    parts.append(f"Traduce estas {len(segments)} lineas:\n{numbered}")
    return "\n\n".join(parts)


def _format_line(seg: TranscriptSegment, speaker_genders: dict[str, str] | None) -> str:
    if not seg.speaker_id:
        return seg.text
    gender = (speaker_genders or {}).get(seg.speaker_id, "unknown")
    gender_label = _GENDER_LABELS_ES.get(gender, gender)
    return f"[Hablante {seg.speaker_id} - {gender_label}] {seg.text}"


def translate_batch_with_recovery(
    segments: list[TranscriptSegment],
    translate_fn: Callable[[list[TranscriptSegment]], list[str]],
    max_split_depth: int = 6,
) -> list[str]:
    """Envoltorio de resiliencia alrededor de una funcion "traducir este lote".

    Si el LLM trunca su respuesta antes de completar todas las lineas (p.ej.
    por llegar al limite de max_tokens en una respuesta larga), ``translate_fn``
    lanza ``TranslationError`` por desalineacion. En vez de abortar todo el
    pipeline — desperdiciando trabajo previo costoso como la diarizacion —
    se parte el lote a la mitad y se reintenta cada mitad por separado,
    recursivamente, hasta que cada sub-lote sea lo bastante chico para caber
    en la respuesta del modelo (o hasta llegar a un solo segmento, caso en el
    que un fallo si se propaga: ya no hay como dividir mas).
    """
    if not segments:
        return []
    try:
        return translate_fn(segments)
    except TranslationError:
        if len(segments) == 1 or max_split_depth <= 0:
            raise
        mid = len(segments) // 2
        left = translate_batch_with_recovery(segments[:mid], translate_fn, max_split_depth - 1)
        right = translate_batch_with_recovery(segments[mid:], translate_fn, max_split_depth - 1)
        return left + right


SUMMARY_SYSTEM_PROMPT = """You are an assistant that summarizes audio/video transcripts into \
their most important points.

Rules:
- Your FIRST step, before writing anything, is to detect the language the input text is \
written in. Your ENTIRE summary MUST be written in that exact same language: if the input is \
in English, respond in English; if it is in Spanish, respond in Spanish; and so on for any \
other language.
- NEVER translate the text into another language.
- Return a short list of highlights (key points), not a long paragraph or a word-for-word \
summary.
- Cover the most relevant topics from the ENTIRE text received, not just the beginning.
- Do not add a generic intro or conclusion ("this text is about..."): go straight to the \
points.
"""


def build_summary_system_prompt() -> str:
    return SUMMARY_SYSTEM_PROMPT


def build_summary_user_prompt(text: str) -> str:
    return (
        "Summarize the following text into its most important points. Remember: detect the "
        "language of the text and respond in that same language, without translating it.\n\n"
        f"Text:\n{text}"
    )


def parse_numbered_lines(raw_text: str, expected: int) -> list[str]:
    pattern = re.compile(r"^\s*(\d+)\.\s?(.*)$")
    found: dict[int, str] = {}
    for line in raw_text.splitlines():
        match = pattern.match(line)
        if match:
            idx = int(match.group(1))
            found[idx] = match.group(2).strip()

    if len(found) != expected:
        raise TranslationError(
            f"Desalineacion en la respuesta del LLM: se esperaban {expected} lineas "
            f"numeradas y se encontraron {len(found)}. Respuesta cruda: {raw_text[:300]!r}"
        )

    return [found[i] for i in range(1, expected + 1)]


# --- Guion de micro-video a partir de una idea (RM-42) -----------------------

SCRIPT_SYSTEM_PROMPT = """You are a scriptwriter for short social videos. You turn a \
one-line idea into a script that someone will read out loud over a video.

Rules:
- Your FIRST step, before writing anything, is to detect the language the idea is written \
in. Your ENTIRE script MUST be in that exact same language. NEVER translate.
- Output ONLY the words to be spoken. No titles, no headings, no scene directions, no \
camera notes, no emoji, no markdown, no quotation marks around the whole thing.
- Write for the ear, not the eye: short sentences, everyday words, no bullet lists.
- Open with the single most interesting thing. A short video loses its viewer in the first \
seconds, so nothing goes before the hook.
"""

# Un bloque por objetivo, con el MISMO patron de "extras condicionales" que
# build_system_prompt: la plantilla base de arriba es lo comun, y esto es lo
# unico que cambia entre un perfil y otro.
_SCRIPT_OBJECTIVE_BLOCKS = {
    "product": """
This script promotes a product or service.
- Lead with what the viewer gains, not with what the product is.
- Close with ONE clear call to action.
- Confident and energetic, but never invent features, numbers or claims that are not in \
the idea given to you.
""",
    "professional": """
This script builds the author's professional credibility. It does NOT sell anything.
- Make ONE point and defend it. A single idea argued well beats three mentioned.
- Speak from experience and take a position; a script that could have been written by \
anyone is worthless here.
- NO call to action, no "follow me", no "comment below", no sales pitch of any kind.
- Plain professional register: no hype, no superlatives, no buzzwords.
""",
}


def build_script_system_prompt(objective: str) -> str:
    """Prompt de sistema para generar un guion, orientado por el objetivo.

    Un objetivo desconocido cae a "product", que es el comportamiento que la
    app tenia antes de RM-42 -- mismo criterio tolerante que el resto del campo.
    """
    block = _SCRIPT_OBJECTIVE_BLOCKS.get(objective, _SCRIPT_OBJECTIVE_BLOCKS["product"])
    return SCRIPT_SYSTEM_PROMPT + block


NARRATION_DRAFT_PROMPT = """You write narration: text that someone will read out loud, \
or that a text-to-speech voice will read.

Rules:
- Output ONLY the words to be spoken. No title, no headings, no bullet lists, no stage \
directions, no markdown, no emoji, no quotation marks around the whole thing.
- Write for the ear: short sentences, everyday words, one idea per sentence.
- Neutral narrator register. Do not sell, do not add a call to action, do not address the \
listener as a marketer would.
- Never invent facts, names, numbers or claims that are not in what you were given.
"""

NARRATION_POLISH_PROMPT = """You clean up narration: text that a text-to-speech voice is \
about to read out loud.

Rules:
- Keep the SAME language as the text you are given. NEVER translate, not even partially.
- Keep the meaning and every fact. Do not add information, do not remove information, do \
not add an introduction or a closing.
- Fix spelling, accents, punctuation and agreement errors.
- Make it readable out loud: split sentences that are too long to say in one breath, and \
replace what reads badly when spoken -- abbreviations, symbols and digits -- with the \
words a person would actually say.
- Keep the author's voice and register. This is a correction, not a rewrite.
- Output ONLY the corrected text.
"""


def build_narration_draft_user_prompt(idea: str, language: str) -> str:
    # El idioma SI se impone aqui: en la pagina de voz el usuario ya eligio en
    # que idioma quiere el audio, asi que la narracion tiene que salir en ese,
    # aunque escriba la idea en otro.
    # El codigo ISO, no un nombre: es lo que ya interpola el prompt de
    # traduccion (SYSTEM_PROMPT_TEMPLATE) y evita duplicar en el backend la
    # tabla de nombres que vive en el frontend.
    return (
        f'Write the narration in the language with ISO code "{language}".\n'
        "Keep it short: under 150 words, unless the idea clearly needs more.\n\n"
        f"Idea:\n{idea}"
    )


def build_narration_polish_user_prompt(text: str) -> str:
    # Sin parametro de idioma, a proposito: corregir no es traducir, y el unico
    # idioma correcto aqui es el que el usuario ya escribio.
    return f"Clean up this narration, in its own language:\n\n{text}"


def build_script_user_prompt(idea: str, target_seconds: float | None) -> str:
    # El limite se expresa en PALABRAS y no en segundos porque un LLM no mide
    # tiempo: ~2.5 palabras por segundo es el ritmo hablado normal en es/en, y
    # se deja margen porque pasarse obliga a acelerar el audio para encajar
    # (ver target_duration_seconds en GenerateMicroVideoRequest).
    if target_seconds:
        limite = (
            f"The script must take about {int(target_seconds)} seconds to read out loud: "
            f"roughly {int(target_seconds * 2.3)} words. Going over is worse than going under."
        )
    else:
        limite = "Keep it short: under 150 words."
    return (
        f"{limite}\n\n"
        "Remember: detect the language of the idea below and write in that same language, "
        "and output only the spoken words.\n\n"
        f"Idea:\n{idea}"
    )
