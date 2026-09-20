# Roadmap — detalle

Índice en [roadmap.md](../roadmap.md). Cada sección: **Why** (por qué existe) y **Scope** (qué incluye / qué queda fuera a propósito). No es una bitácora de cambios — eso vive en los commits.

## RM-01 — Transcripción standalone
**Why:** doblar/traducir es demasiado para alguien que solo quiere la transcripción del audio original.
**Scope:** audio o video de entrada; salida SRT + texto plano; sin traducción ni TTS.
Commit: `7064d5a`

## RM-02 — TTS standalone
**Why:** sintetizar voz a partir de texto es un caso de uso propio, no solo un paso interno del doblaje.
**Scope:** texto → audio; voz pública (masculina/femenina) o WAV propio; sin traducción.
Commits: `d047334`, `09a924d`

## RM-03 — Analítica de negocio
**Why:** el dashboard mostraba stats fijos en "—"; sin datos reales no sirve para decisiones de negocio.
**Scope:** `ProjectMetrics` persiste al borrar el proyecto; agregados (proyectos, minutos, idiomas) en `GET /dashboard/stats`.
Commit: `c13d6ea`

## RM-04 — Página de subtítulos
**Why:** `/subtitles/new` era un placeholder; el servicio ya existía en el backend.
**Scope:** formulario real con selector de modo de salida (solo SRT / incrustados / seleccionables).
Commit: `b5d4a87`

## RM-05 — Previsualización de media
**Why:** descargar un artefacto a ciegas para saber si el resultado es el esperado es mala UX.
**Scope:** reproductor de video/audio inline en cualquier vista con un artefacto descargable.
Commit: `63787a5`

## RM-06 — Waveform reactivo en vivo
**Why:** animación que reacciona al audio real durante la reproducción, no un spinner genérico.
**Scope:** barras que revelan la forma real de onda según avanza la reproducción, mezcladas con RMS en vivo cerca del cabezal.
Commits: `205cab7`, `c34df3b`, `73575e9`, `d18ec9c`

## RM-07 — Importar proyecto desde URL
**Why:** el cliente suele compartir un link (directo o de YouTube), no siempre un archivo local.
**Scope:** subir archivo / pegar URL / buscar en YouTube conviven en el mismo formulario (no se reemplazan); descarga vía yt-dlp con validación SSRF; previsualización antes de confirmar.
Commits: `f88d8ea`, `33f07ab`, `115adfc`, `396ba5e`

## RM-08 — Atribución correcta de fallos de etapa
**Why:** una etapa que crasheaba se registraba igual como "completada", así que la UI culpaba a la siguiente etapa del fallo real.
**Scope:** `PipelineTimings.stage()` ya no marca una etapa como completada si el bloque lanza una excepción; el frontend prioriza el paso "activo" sobre el primer "pendiente" al decidir cuál marcar como fallido.
Commit: `5d02d64`

## RM-09 — Librería de voces persistente
**Why:** hoy cada proyecto de doblaje/TTS sube su propia referencia de voz; no hay forma de guardar y reusar una.
**Scope:** tabla `Voice(user_id, name, wav_path, gender, language)` + selector reutilizable en doblaje/TTS. Las voces públicas actuales pueden vivir ahí como filas "del sistema".

## RM-10 — Plantillas reutilizables
**Why:** reconfigurar glosario/tono/contexto/idiomas en cada proyecto nuevo es repetitivo para un mismo tipo de contenido.
**Scope:** guardar el `config` de un proyecto como plantilla nombrada; aplicarla al crear uno nuevo.

## RM-11 — Documento → audio narrado
**Why:** nicho B2C (estudiantes/investigadores) que quiere un resumen narrado de un documento, no doblaje de video.
**Scope:** sin diseñar todavía — requiere un paso de resumen (LLM) que hoy no existe en ningún puerto; necesita su propia sesión de diseño antes de construirse.

## RM-12 — API para desarrolladores
**Why:** se retoma si el negocio gana tracción y aparecen integradores que la pidan explícitamente.
**Scope:** auth por API key + rate limiting; canal medido por uso, separado del dashboard.

## RM-13 — Workspace multi-usuario + facturación
**Why:** hoy es single-owner con roles admin/member, sin pagos; una empresa con varios usuarios necesitaría esto.
**Scope:** se revisa solo si hay tracción real con un primer cliente B2B — contradice la restricción vigente de "sin facturación".

## RM-14 — Imagen+texto → micro-video social
**Why:** idea de negocio B2C (shorts/reels desde imágenes + texto de venta); se optó por composición con ffmpeg en vez de un modelo de video generativo (ver RM-22) por velocidad de entrega y cero dependencia de GPU/costo de inferencia.
**Scope:** nuevo servicio `micro_video`: sube una imagen + escribe un texto → video vertical (9:16) con efecto Ken Burns (zoom lento) sobre la imagen, narración del texto vía TTS (reusa la voz pública o clonada de RM-02) y captions incrustados sincronizados con la narración. Sin modelo de generación de imagen/video nuevo — todo se arma con `MediaProcessor` (ffmpeg) + `SpeechSynthesizer` ya existentes. Requiere `ffmpeg-full` (libass) para incrustar captions — ver README/.env.example. Follow-up: botón de preview (play/pausa) en cada opción de voz para escucharla antes de elegir (`/api/samples/voices/{id}`).
Commit: `200594e`, `96ef4bf`

## RM-22 — Micro-video con video generado por IA
**Why:** alternativa a RM-14 que anima la imagen con un modelo de video generativo real en vez de un simple zoom, para un resultado visualmente más rico.
**Scope:** sin diseñar todavía — requiere investigación de factibilidad propia (qué modelo usar, local vs. API paga, costo de cómputo/GPU, tiempos de generación) antes de poder planearse.

## RM-23 — Estilo de resaltado de captions: caja o color de texto
**Why:** hoy el resaltado de los captions del micro-video (RM-14) es siempre una caja de fondo opaca detrás del texto blanco; algunos usuarios van a preferir un estilo sin caja, solo cambiando el color de la palabra.
**Scope:** selector en la UI ("Caja de fondo" / "Color de texto") junto al color picker ya existente. Para "color de texto", el color elegido reemplaza `PrimaryColour` (blanco) en el estilo ASS en vez de `BackColour`/`OutlineColour`; sin caja, solo contorno negro para legibilidad.
Commit: `2512508`

## RM-24 — Música de fondo en micro-video
**Why:** un micro-video sin música de fondo se siente incompleto para redes sociales; pedido explícito del usuario.
**Scope:** opción "Sin música" (default) o 4 pistas CC0 (dominio público, ver `assets/background_music/SOURCES.md`) empaquetadas con la app — no upload propio en esta primera versión. La pista se mezcla en loop debajo de la narración a volumen fijo bajo (nunca tapa la voz) y se recorta a la duración final del video. Follow-up: botón de preview (play/pausa) en cada pista para escucharla antes de elegir (`/api/samples/music/{id}`).
Commit: `358aab8`, `96ef4bf`

## RM-25 — Resaltado por palabra en captions (karaoke)
**Why:** hoy el resaltado (RM-14/RM-23) pinta el caption completo durante toda su ventana de tiempo; un estilo "karaoke" que solo resalta la palabra que se está diciendo en ese instante es más dinámico y común en redes sociales.
**Scope:** tercer estilo ("karaoke") en el mismo selector de RM-23 -- se muestra el caption completo, pero el resaltado avanza palabra por palabra. El timing de cada palabra dentro de un caption se estima igual que ya se estima el timing de cada caption dentro de un fragmento de TTS (proporcional a caracteres, `_distribute_duration` compartido por ambos niveles). Un Dialogue ASS por palabra (no uno por caption) con la palabra activa envuelta en un override inline `\c` -- se prefirió sobre los tags `\k` de karaoke nativos de ASS por reusar una tecnica ya probada en produccion (`_convert_bold_to_ass` hace lo mismo con `\b`).
Extensión (pedido explícito del usuario): cuarto estilo, "karaoke_background" -- misma mecánica de un Dialogue por palabra, pero en vez de cambiar el COLOR de la palabra activa le resalta el FONDO. Probado a mano con el ffmpeg-full real: con `BorderStyle=3` (el mismo truco de "caja" que usa el estilo "background", ver el estilo homónimo) un override inline de `OutlineColour`/alpha (`\3c`/`\3a`) prende y apaga la "caja" POR TRAMO de texto, no por todo el Dialogue -- eso es lo que permite que solo la palabra activa muestre caja mientras el resto queda en blanco plano sin ninguna. `OutlineColour` arranca totalmente transparente en la Style para que las palabras sin resaltar no muestren nada.
Segunda extensión (pedido explícito del usuario): en "background" y "karaoke_background" el texto ya no queda fijo en blanco -- nuevo campo `caption_text_color` (independiente de `caption_bg_color`, que en esos dos estilos pasa a ser pura y exclusivamente el color de la caja/resaltado). `text_color`/`karaoke` no cambian: ahí `caption_bg_color` ya era el único color elegible (el del texto/la palabra activa), no hay una caja separada que darle color. En el panel del editor esto se ve como un segundo color picker que aparece solo para esos dos estilos.
Commits: `436e54f`, `d91d47c`, `8c09e9b`

## RM-26 — Categorías de música + panel de mantenimiento
**Why:** la biblioteca de música de fondo (RM-24) hoy es un catálogo fijo de 4 pistas sin organización; a medida que se agreguen más pistas hace falta agruparlas y una forma de subir nuevas sin tocar código.
**Scope:** 5 categorías fijas (Calm & Meditation, Commercials & Professional, Energy & Pop, Happy & Romantic, Social Network); pantalla de mantenimiento (solo admin, mismo patrón de sección protegida que RM-15) para subir una pista nueva y asignarla a una categoría. Antes de agregarla al catálogo: analizar el audio, recortar silencio inicial, y convertir a WAV — pipeline de limpieza automática, no manual. Catálogo movido de un dict fijo (container.py) a una tabla `music_tracks`; las 4 pistas CC0 de RM-24 se migraron como filas.
Commit: `3bb071f`

## RM-27 — Texto editable sobre el video
**Ya cubierto por RM-28** (texto movible es un superconjunto de "elegir la posición") -- se decidió saltar la implementación fija e ir directo al editor completo.

## RM-28 — Editor de video completo
**Why:** con tantas opciones acumulándose (texto, música de fondo, subtítulos, voz en off) un formulario lineal deja de alcanzar; un editor tipo lienzo es más manejable. Subtítulos (RM-23) y voz en off (narración, RM-14) ya existían -- lo nuevo es el texto arrastrable y el recorte de música.
**Scope:** overlays de texto arrastrables (negrita, tipografía, tamaño, color, fade in/out) implementados extendiendo el mismo `.ass` de los captions vía `\pos`/`\fad` (el ffmpeg de este sistema no tiene `drawtext`, ver hallazgo en el plan) -- sin nuevo filtro de ffmpeg. Recorte [start, end] de la pista de música elegida (`MediaProcessor.extract_music_range`) antes de mezclarla. Reutiliza tal cual el resaltado de captions (RM-23) y la narración/voz (RM-14) -- no incluye el resaltado por palabra (RM-25, sigue pendiente aparte). Follow-up de UI: rediseño del layout como editor profesional (lienzo central, barra de herramientas izquierda, panel de propiedades derecho, pistas de audio abajo) -- refactor presentacional puro, sin cambios de backend/estado (ver `frontend/src/components/microVideoEditor/`). Segundo follow-up: control de volumen por pista (narración/música, `MediaProcessor.apply_volume`) y preview arrastrable del subtítulo sobre el lienzo (mismo mecanismo `\pos` que los overlays, captions pasan de posición fija a `caption_x`/`caption_y` configurables).
Tercer follow-up: el volumen ahora se escucha en el preview real (no solo al generar), slider vertical, y los dos paneles de audio (narración/música) quedan siempre visibles con la misma estructura aunque no haya pista elegida.
Commits: `4ac0f29`, `96648fe`, `caa27e3`, `f5ad31d`

## RM-29 — Múltiples imágenes en el micro-video
**Why:** hoy el servicio solo admite una imagen; el usuario final pidió poder armar el video con varias.
**Scope:** subir una lista de imágenes en vez de una sola; el video las recorre en orden (cada una con su propio efecto Ken Burns), repartiendo la duración total entre ellas. Cambia el contrato del caso de uso de `image_path: Path` a una lista -- es la base arquitectónica que también habilita RM-30/RM-31 por-imagen. Cada imagen se renderiza muda por separado y se concatenan (`MediaProcessor.concatenate_videos`), el audio se mezcla una sola vez al final sobre el video ya concatenado (`replace_audio_track`, ya existía). Overlays/captions siguen siendo globales, no por-imagen.
Commit: `68f78cf`

## RM-30 — Ajustar tamaño/posición de la imagen
**Why:** una imagen subida tal cual puede no encuadrar bien en el video vertical 9:16 (recortada mal, mal centrada).
**Scope:** en el lienzo del editor, arrastrar para reposicionar (pan) y un slider para acercar (zoom) cada imagen (RM-29) dentro del marco 9:16 antes de generar -- el encuadre elegido se aplica ANTES del Ken Burns automático existente, no lo reemplaza. `GenerateMicroVideoRequest.image_paths: list[Path]` pasa a `images: list[MicroVideoImage]` (path + offset_x/offset_y/zoom, defaults = comportamiento previo). Follow-ups tras feedback de uso: (1) la barra de Zoom/Filtro pasó de duplicarse por fila a una sola barra fija que refleja la imagen activa, y se agregó reordenar las imágenes por drag-and-drop (arrastre nativo HTML5, sin librería nueva); (2)+(3) el preview del lienzo no dejaba mover la imagen zoomeada en el eje sin sobrante de aspecto original -- primero por componer mal `object-position`+`transform:scale` (no le agrega recorrido a `object-position`), corregido reproduciendo a mano el mismo escalado que ffmpeg; ese arreglo tenía a su vez un error de álgebra (restaba `zoom` en vez de `1`) que dejaba en cero el recorrido del eje ya alineado con el aspecto del marco -- notorio sobre todo con imágenes cuyo aspecto ya es ~9:16.
Sexto follow-up: el cursor "move" no mostraba ningun glyph en Safari/macOS (cae a la flecha comun) -- macOS no tiene un glyph nativo para ese cursor. Cambiado a "grab"/"grabbing" (mano abierta/cerrada), que si tienen glyph propio en macOS, en los 4 elementos arrastrables del lienzo (imagen, overlay de texto, emoji, preview de caption).
Commits: `a6bf89a`, `d3e0a29`, `6bb3ed6`, `3f08070`, `c972364`, `86c1d48`, `6353b83`
Cuarto follow-up: en Safari, arrastrar la imagen para reposicionarla (y también arrastrar overlays de texto/emoji/subtítulo, RM-28/32, que comparten el mismo mecanismo) no hacía nada -- causa: un bug conocido de WebKit donde tras `setPointerCapture` los eventos `pointermove`/`pointerup` dejan de dispararse en cuanto el cursor sale del elemento capturado, incluso con los listeners puestos en `window` (ver https://github.com/w3c/pointerevents/issues/407). Se reemplazó Pointer Events + `setPointerCapture` por Mouse Events simples (`mousedown` + `mousemove`/`mouseup` en `window`, sin captura) en `TextOverlayCanvas.tsx` -- suficiente porque esta interacción es de escritorio, no necesita soporte multi-touch. Confirmado en Chrome (sin regresión) y explica por qué el bug no se veía al probar ahí.
Quinto follow-up: eso no alcanzó -- seguía roto en Safari real (confirmado por el usuario con una imagen de 4862x2136). Dos causas mas, ambas propias de WebKit: (1) `naturalSize` (leído en el `onLoad` del `<img>`) podía quedar en `null` para siempre si el navegador termina de decodificar el `blob:` URL antes de que React llegue a atar el listener `onLoad` -- sin esto, `backgroundImageStyle` cae a un modo que ignora el zoom directamente, y `computeExcess` devuelve cero recorrido, así que tampoco se puede mover; ahora tambien se chequea de forma sincrona via un `ref` apenas cambia la URL de la imagen, por si ya estaba `.complete`. (2) Safari igual inicia su gesto nativo de "arrastrar esta imagen como archivo" aunque el atributo HTML `draggable` este en `false` -- hace falta ademas `-webkit-user-drag: none` por CSS. No se pudo probar en Safari real de punta a punta (`do JavaScript` vía AppleScript pide habilitar una opción en el menú Desarrollo de Safari, no es algo para tocar sin permiso) -- se validó disparando la secuencia de eventos de mouse a mano y confirmando que el offset de la imagen cambia como se espera.

## RM-31 — Filtros de imagen (brillo, contraste, sepia, etc.)
**Why:** pedido explícito del usuario final; investigué estilos de filtro más usados en 2026 (VSCO/Lightroom/CapCut, ver fuentes) -- filtros como vintage/sepia, cool, warm, B&N y dramático son los presets estándar en la mayoría de editores.
**Scope:** un selector de 5 presets + "original" por imagen (RM-30), aplicados vía filtros de ffmpeg ya disponibles en este binario (confirmado con `ffmpeg -h filter=...` y probado con una imagen real): `colorchannelmixer` (sepia, matriz clásica -- `curves` no tiene preset de sepia, solo "vintage"), `hue=s=0` (B&N), `colorbalance` (frío/cálido), `eq`+`vignette` (dramático). Sin nuevo binario ni dependencia. `MicroVideoImage` gana `filter_preset: str`, mismo objeto JSON que ya viaja el encuadre de RM-30.
Commit: `df4614d`

## RM-32 — Emoticones sobre el video
**Why:** pedido explícito del usuario final, además del texto ya arrastrable (RM-28).
**Scope:** la asunción original (reusar el pipeline ASS del texto, un emoji es un carácter Unicode) resultó falsa en este sistema -- probado a mano con el `ffmpeg-full` real: ningún emoji se renderiza vía ASS, ni con la fuente por defecto ni pidiendo explícitamente "Apple Color Emoji" o "Noto Color Emoji" (instalada vía Homebrew para la prueba). En su lugar, emojis como imágenes: 20 PNG curados de Twemoji (CC-BY 4.0, atribución en `assets/emojis/SOURCES.md`) compuestos con el filtro `overlay` de ffmpeg en una etapa nueva del pipeline (`emoji_burn`, después de `caption_burn`), mismo mecanismo de posición/fade arrastrable que TextOverlay. Nuevo endpoint autenticado `GET /samples/emoji/{id}` (mismo patrón que voces/música) para que el editor pueda previsualizarlos.
Commit: `3e4945b`

## RM-33 — Estilos de texto más profesionales
**Why:** pedido explícito del usuario final; investigué tendencias de texto en video de 2026 (CapCut/tipografía cinética, ver fuentes) -- sombra dura, contorno grueso, y texto con degradado son los estilos más comunes en contenido corto viral, más allá de negrita/color plano (ya soportado desde RM-28).
**Scope:** `TextOverlay` gana `text_style` ("flat"/"hard_shadow"/"thick_outline"/"gradient"/"long_shadow"/"hollow"/"neon_glow"/"colored_outline") + `accent_color` (antes `gradient_color`, renombrado al ganar más usos que el degradado). Sombra dura y contorno grueso son directo (los campos `Shadow`/`Outline` de la línea `Style:` de ASS, ya usados, ahora configurables por preset -- valores probados a mano: (2,8) y (10,1)). Degradado: ASS no tiene relleno degradado nativo, se aproxima con un override `\1c` por CARACTER interpolando entre `color` y `accent_color` (probado a mano, se ve como un degradado suave). No incluye animación tipo "tipografía cinética" (palabra por palabra) -- eso es una iniciativa más grande, separada.
Extensión (a partir de 6 imágenes de referencia de tendencias 2026 que compartió el usuario): 4 estilos más -- `long_shadow` (Shadow=18, probado a mano), `hollow` (solo contorno, relleno transparente vía alpha `FF` en `PrimaryColour`), `neon_glow` (glow real vía `\blur6` + `OutlineColour`=`accent_color`), `colored_outline` (contorno de un color distinto al relleno) -- y 6 tipografías bundleadas en `assets/fonts/` (Bebas Neue, Montserrat, Poppins, Righteous, Pacifico, Dancing Script; licencia OFL, ver `assets/fonts/SOURCES.md`), pasadas a ffmpeg vía `fontsdir=` para no depender de que estén instaladas en la máquina (mismo patrón que los PNG de emoji de RM-32) -- verificado a mano ocultando las copias del sistema. Descartado por complejidad no justificada: degradado en el contorno, y los estilos Embossed/Inset/Letterpress (necesitan dos sombras en direcciones opuestas a la vez, ASS solo soporta una).
Fix post-extensión (reportado por el usuario con capturas del editor): (1) el editor nunca declaraba `@font-face` para las 6 tipografías bundleadas -- el navegador no tiene forma de dibujarlas sin eso, así que TODAS caían al mismo font de fallback en el preview (parecía que "todos los estilos se ven iguales"); se copian a `frontend/public/fonts/` y se declaran en `index.css`. (2) `contorno grueso`/`solo contorno`/`contorno de color` usaban un grosor de `-webkit-text-stroke` en `px` fijos (no escalaba con `font_size`) y sin `paint-order`, lo que en ciertos fonts/tamaños dejaba el contorno tapando todo el relleno; ahora escalan en la misma unidad `cqw` que el `font_size` (mismos valores de Outline que usa el backend) con `paint-order: stroke fill`. (3) `long_shadow` con el tag `Shadow` nativo de ASS es una ÚNICA copia sólida desplazada -- probado a mano con texto real, se ve como un duplicado "flotando" al lado, no como una sombra; se reemplaza por una cinta de 18 copias sólidas en negro desplazadas diagonalmente (`_LONG_SHADOW_STEPS` en el backend, mismo criterio en el preview CSS), verificado con el `ffmpeg-full` real y con el pipeline completo.
Commits: `725121b`, `05c9724`, `37c8c21`

## RM-34 — Podcast de audio
**Why:** pedido explícito del usuario -- un servicio de audio orientado a episodios largos (guion/conversación), no solo la síntesis de un texto suelto que ya cubre RM-02.
**Scope:** nuevo servicio (paralelo a `tts`/`micro_video`) que convierte un guion largo en un episodio de audio narrado, reusando la selección de voz ya existente (pública o clonación propia, ver RM-02/`SpeechSynthesizer`) -- no se reinventa la síntesis ni la clonación, solo se les da un formato de entrada/salida pensado para podcasts. Sin definir todavía: si el guion admite múltiples voces/hablantes en un mismo episodio (conversación) o es de un solo narrador -- a resolver en el plan de implementación.

## RM-35 — Logo e icono de marca definitivos
**Why:** el ícono usado hasta ahora en el sidebar, el login y el favicon era un genérico ("sparkle" de lucide-react dentro de un cuadrado violeta), no el logo real de la marca.
**Scope:** logo (PNG con transparencia, provisto por el usuario) reemplaza el ícono de `Sidebar.tsx` y `LoginPage.tsx` -- sin el cuadrado de fondo violeta que tenía el sparkle, porque el logo ya trae su propio color (degradado violeta-celeste). Dos copias del archivo original en `frontend/public/` (nunca se toca/mueve el original del usuario): `logo.png` (512px, para la UI) y `favicon.png` (128px, para la pestaña del navegador) -- se elimina el `favicon.svg` por defecto de Vite que quedó sin uso.
Commit: `9ec7b81`

## RM-36 — Videos como input para Micro-Video
**Why:** pedido explícito del usuario -- hoy Micro-Video (RM-14/RM-29) solo acepta imágenes como material de entrada (con Ken Burns); el usuario quiere poder usar también clips de video ya existentes, no solo fotos.
**Scope:** subir uno o más videos, además de o en lugar de imágenes, que se incorporan a la línea de tiempo del short video en el orden elegido (mismo criterio de orden/reordenamiento que ya existía para las imágenes). Cada clip ocupa su propia duración real (recortable con un control de inicio/fin en el editor) en vez de una tajada igual; el tiempo restante se reparte entre las imágenes, y el video se extiende (nunca recorta un clip) si los clips solos ya cubren la duración pedida. El audio original de cada clip se descarta siempre (el short video ya tiene su propia narración/música de fondo). El recorte/zoom manual de RM-30 y los filtros de RM-31 aplican igual a un clip que a una imagen. Sin límite explícito de duración por clip o del video total.
Commits: `4c34917`, `e330a56`

## RM-37 — Publicar el short video en redes sociales
**Why:** pedido explícito del usuario -- hoy el video generado se descarga a mano y el usuario lo sube por separado a cada red; publicarlo automáticamente ahorra ese paso repetitivo.
**Scope:** botón para publicar el short video ya generado en TikTok, YouTube (Shorts), Instagram (Reels) y Facebook, eligiendo una red a la vez o todas juntas. Necesita autenticación OAuth y la API de subida de video de cada plataforma por separado. A definir en el plan de implementación: si la cuenta que se conecta es del usuario final o una cuenta propia de la empresa, qué pasa si una publicación falla o es rechazada por una red y las otras no, y si hay límites de la propia API (rate limits, tamaño máximo) a respetar.

## RM-38 — Generación: banco de imágenes/audios/videos a demanda
**Why:** pedido explícito del usuario -- separar la generación de material crudo con IA de armar el short video en sí, para poder preparar contenido de antemano y reusarlo después en vez de generarlo cada vez desde cero.
**Scope:** nueva sección "Generación" donde se piden imágenes, audios o videos generados por IA a demanda; quedan guardados en una biblioteca del usuario y disponibles para elegir como material de entrada en Micro-Video (RM-14/RM-29/RM-36) sin volver a generarlos. A definir en el plan de implementación: qué modelo(s) de generación de imagen/audio/video se usan (locales, como el resto del pipeline, u otro proveedor), y si hay un límite de almacenamiento/cuota por usuario.

## RM-39 — Generación agéntica de short videos
**Why:** pedido explícito del usuario -- en vez de armar el short video paso a paso a mano, delegarle el trabajo completo a uno o más agentes que decidan y ejecuten usando las herramientas ya disponibles en la plataforma.
**Scope:** uno o más agentes a los que se les da un objetivo (y opcionalmente input: imágenes, ideas, guion) arman el short video de punta a punta, usando como "tools" lo que ya existe (doblaje, voz/clonación, la generación de RM-38, y el armado de Micro-Video en sí). A definir en el plan de implementación: qué motor de agentes se usa, cuánto control o revisión intermedia tiene el usuario antes de que el agente publique o dé por terminado el video (ver también RM-37), y el costo/límite de iteraciones por corrida.

## RM-40 — Cortar y eliminar segmentos del video
**Why:** el recorte de RM-36 solo permitía un único rango contiguo [inicio, fin]; el usuario quería poder quitar varios tramos sueltos (uno cerca del inicio, otro del medio, otro del final) y quedarse solo con las partes que le interesan.
**Scope:** reemplaza el recorte de rango único de RM-36 por `MicroVideoMediaItem.keep_ranges` (lista ordenada y sin solapes de tramos a conservar); cada tramo se renderiza como su propio sub-segmento y se concatenan entre sí. En el editor, `VideoSegmentTimeline` permite arrastrar dentro de un tramo para seleccionar y eliminar un sub-rango, con deshacer/rehacer (Cmd+Z / Cmd+Shift+Z) de historial local por item. El preview reproduce en loop solo por los tramos conservados, saltando los huecos.
Commits: `3727579`, `f8decdf`, `eb7cd57`

## RM-15 — Gestión de usuarios
**Why:** antes los usuarios solo se creaban por script (`create_admin.py`); no había forma de verlos, crearlos, cambiar su rol o desactivarlos desde la UI.
**Scope:** sección "Administración" en el menú (solo admin): listado, botón "Agregar usuario" (nombre/email/password/rol), cambio de rol y activar/desactivar inline. `GET/POST/PATCH /api/users`, todos protegidos con `require_admin`. Un admin no puede quitarse su propio rol ni desactivarse a sí mismo (bloqueado en backend y reflejado en la UI). Sigue sin auto-registro ni invitaciones por email — crear una cuenta requiere acceso admin, por diseño.
Commits: `11a3556`, `31a6b03`

## RM-16 — Columnas de ejecución en la tabla de proyectos
**Ya implementado** antes de esta sesión (dashboard M1-M6 / v1.2.0) — `ProjectsListPage` ya muestra "Duración" y "ID de ejecución" por fila.
Commit: `2d2f149`

## RM-17 — Selector de fuente de media: orden y validación de URL
**Why:** antes "Pegar URL" no bloqueaba el envío del formulario aunque la previsualización automática fallara — dejaba pasar URLs realmente rotas sin ningún aviso hasta que el pipeline fallaba recién al intentar descargar.
**Scope:** en doblaje/subtítulos/transcripción, tabs reordenados (Buscar en YouTube → Subir archivo → Pegar URL, YouTube es el tab por defecto). `MediaUrlPreview` ahora es también la validación real (reusa `GET /media/preview`, la misma extracción de yt-dlp que usaría la descarga) y reporta éxito/fallo al formulario; el botón de envío queda deshabilitado hasta validar, con un botón "Validar URL" para reintentar a mano si falla. Editar la URL resetea la validación de inmediato.
Commit: `f1b101e`

## RM-18 — Resumen con highlights en Transcripción
**Why:** pedido explícito para el servicio de transcripción; introdujo la primera capacidad de resumen vía LLM, reusable por RM-11.
**Scope:** toggle "incluir un resumen" (aditivo, no reemplaza la transcripción completa) en `NewTranscriptionProjectPage`. Nuevo puerto `Summarizer` (`application/interfaces.py`) separado de `Translator` — resumir texto libre no tiene el invariante "N líneas → N líneas" que necesita `translate_batch`. `OllamaTranslator`/`LlamaServerTranslator` ganaron `summarize()` reusando su transporte HTTP existente (`_call_llm`), sin cliente nuevo. Videos largos se resumen map-reduce (por fragmentos + resumen final) para cubrir todo el video, no solo el principio.
Commit: `e840cb4`

## RM-19 — Modo oscuro
**Why:** pedido explícito del usuario; usuarios distintos tienen preferencias distintas de tema, y el tema por defecto debe adaptarse sin acción manual.
**Scope:** paleta oscura en `index.css` (`.dark`, Tailwind ya traía `darkMode: 'class'`). Sin preferencia guardada, el tema inicial se elige por la hora del sistema (`lib/theme.ts::getSystemHourTheme` — 6:00 a 17:59 claro, resto oscuro; no es `prefers-color-scheme`, que refleja el tema del SO, no la hora). Botón toggle en `Topbar` (icono sol/luna sincronizado con el tema activo), que al usarse guarda una preferencia explícita en `localStorage` y ya no se recalcula por hora. Script inline en `index.html` aplica la clase `dark` antes de montar React para evitar flash del tema equivocado.
Commit: `7356015`

## RM-20 — Auditoría de diseño responsive
**Why:** se esperan usuarios conectándose desde iPad y celulares; el diseño no se ha validado fuera de desktop.
**Scope:** auditar dashboard, formularios de creación y detalle de proyecto en anchos de tablet/mobile; corregir donde el layout se rompa. No incluye una app nativa ni un rediseño mobile-first desde cero.

## RM-41 — Soporte táctil en el editor de Micro-Video
**Why:** la auditoría de RM-20 detectó que los gestos de arrastre de `TextOverlayCanvas` y `VideoSegmentTimeline` usaban solo eventos de mouse (decisión deliberada para evitar un bug de Safari con Pointer Events, ver comentarios en ambos archivos) y por eso no funcionaban en tablet/celular. Es un problema de INPUT, no de layout, así que quedó fuera del alcance de RM-20.
**Scope:** mouse y touch events en paralelo (sin Pointer Events, para no reintroducir el bug de Safari) vía un helper compartido (`lib/dragEvents.ts`). Cubre mover overlays de texto/emoji y el preview de captions, panear la imagen/video de fondo, y en la franja de recorte: arrastrar el cuerpo de un tramo (unir/separar), sus bordes (acortar) y la selección en modo corte. `touch-action: none` en los elementos arrastrables evita que el navegador interprete el gesto como scroll de la página. Fuera de alcance: doble clic para saltar a un punto (sigue siendo solo mouse, no es un gesto de arrastre).

## RM-21 — Mensajes de error legibles del pipeline
**Why:** hoy `project.error_message` muestra el mensaje técnico crudo de la excepción tal cual (a veces legible, a veces un stack trace de Python) — un usuario no técnico no puede entender por qué falló ni qué hacer al respecto.
**Scope:** mapear los tipos de error conocidos del pipeline (conexión al LLM, formato de descarga, disco lleno, modelo no encontrado, etc.) a un mensaje corto con causa probable + acción sugerida, mostrado en el detalle del proyecto en vez del texto crudo; conservar el mensaje técnico original visible en un detalle expandible para debugging.

---

**Descartado:** reemplazo/agregado de pista de audio en un video existente — evaluado, sin caso de uso claro con el negocio. Sin ID (nunca entró en desarrollo activo).
