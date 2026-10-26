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
**Scope:** botón para publicar el short video ya generado en TikTok, YouTube (Shorts), Instagram (Reels), Facebook, LinkedIn y X, eligiendo una red a la vez o todas juntas. LinkedIn y X entran por RM-42 y no son equivalentes a las otras cuatro: son redes donde el texto del post pesa tanto como el video, así que publicar ahí implica también redactar ese texto, no solo subir el archivo. Necesita autenticación OAuth y la API de subida de video de cada plataforma por separado. A definir en el plan de implementación: si la cuenta que se conecta es del usuario final o una cuenta propia de la empresa, qué pasa si una publicación falla o es rechazada por una red y las otras no, y si hay límites de la propia API (rate limits, tamaño máximo) a respetar. Antes de comprometer las seis redes hay que verificar acceso y costo de cada API por separado: no todas ofrecen subida de video en un nivel gratuito, y el de X en particular cambió de condiciones -- si alguna no es viable, es mejor saberlo antes de prometerla en la UI.

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
**Scope:** paleta oscura en `index.css` (`.dark`, Tailwind ya traía `darkMode: 'class'`), botón en `Topbar` que guarda la preferencia en `localStorage`, y script inline en `index.html` que aplica la clase `dark` antes de montar React para evitar el flash del tema equivocado. El automático original (por la hora del sistema) lo reemplazó RM-43.
Commit: `7356015`

## RM-20 — Auditoría de diseño responsive
**Why:** se esperan usuarios conectándose desde iPad y celulares; el diseño no se ha validado fuera de desktop.
**Scope:** auditar dashboard, formularios de creación y detalle de proyecto en anchos de tablet/mobile; corregir donde el layout se rompa. No incluye una app nativa ni un rediseño mobile-first desde cero.
Hecho en `2034ba4`: el sidebar (256px fijos en todas las páginas) se colapsa en un drawer por debajo de 1024px, y el editor de Micro-Video — que sumaba 668px fijos antes del lienzo — pasa a barra de herramientas horizontal abajo con el panel de ajustes como hoja inferior. Más dos grillas sin versión de una columna y la barra superior del editor. Comprobado en dispositivo. **Fuera de alcance, quedó pendiente:** los gestos de arrastre del lienzo y de la línea de tiempo son solo de mouse (`onMouseDown` + listeners de `window`, decisión documentada para esquivar un bug de Safari con Pointer Events), así que en táctil no funcionan — es un problema de input, no de layout.

## RM-21 — Mensajes de error legibles del pipeline
**Why:** hoy `project.error_message` muestra el mensaje técnico crudo de la excepción tal cual (a veces legible, a veces un stack trace de Python) — un usuario no técnico no puede entender por qué falló ni qué hacer al respecto.
**Scope:** mapear los tipos de error conocidos del pipeline (conexión al LLM, formato de descarga, disco lleno, modelo no encontrado, etc.) a un mensaje corto con causa probable + acción sugerida, mostrado en el detalle del proyecto en vez del texto crudo; conservar el mensaje técnico original visible en un detalle expandible para debugging.

## RM-41 — Telemetría OpenTelemetry (integración Argus)
**Why:** el equipo Argus estandariza observabilidad para todo el portafolio; Prosodia es la única app con cola (API → Redis → worker Celery), y es la prueba que les falta poder hacer (ningún otro piloto tiene cola). Coordinación en `~/Documents/Victor/prosodia_argus/canal-prosodia-argus.md`.
**Scope:** aplicar `prosodia-instrumentar.patch` (import + `argus.init()` en `web/main.py` antes de los routers, mismo patrón en `web/tasks/celery_app.py` antes de importar Celery, y `app.add_middleware(argus.ASGIMiddleware)`); agregar `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME`/`OTEL_RESOURCE_ATTRIBUTES` a los servicios `api` y `worker` de `docker-compose.yml` (siempre `localhost`/`host.docker.internal`, nunca el plano central de Argus directo); subir `requires-python` a `>=3.11,<3.13` (acordado en el canal — sin uso real de 3.10 en CI ni Docker hoy). No incluye instrumentar a mano las etapas internas del pipeline (transcripción, clonado, mezcla) — descartado explícitamente por Argus en A-05.
**Hecho.** Verificado con un doblaje real de punta a punta (`a00d9bb`): una sola traza cubre `POST /api/projects` -> `apply_async/run_project` (API) -> `run/run_project` (worker, 463 s), con los tres spans bajo el mismo `TraceId` y los hijos con padre. El span del worker cierra ~433 s despues de la ventana de decision del muestreo y sobrevive, y ninguno lleva error — o sea que lo conserva la politica por salto a cola, no la de errores. Los logs del pipeline llegan correlacionados (35 de 39 con `TraceId`) con la etapa como atributo consultable: `audio_extraction`, `diarization`, `transcription`, `speaker_profile_building`, `translation`, `tts_synthesis`, `audio_mixing_and_muxing`, `rendering_dubbed`.
Dos problemas salieron por el camino y estan documentados en el canal: el conflicto de protobuf entre el SDK y IndexTTS (resuelto por Argus sacando el exportador OTLP del nucleo, ver S-03/A-09) y que el muestreo descartaba las trazas del trabajo asincrono largo antes de que el worker terminara (resuelto por Argus decidiendo con el span del productor, ver S-05/A-11). Del lado nuestro hubo que puentear structlog hacia stdlib con un logger dedicado (`ccbb358`), porque el puente del SDK se engancha al root y esta app nunca pasaba por ahi.

## RM-42 — Perfiles de objetivo: producto vs posicionamiento profesional
**Why:** pedido explícito del usuario -- hoy el short video (RM-14 y siguientes) y su editor (RM-28) sirven un objetivo implícito y único: promocionar un producto. Pero un profesional que quiere posicionar su perfil en LinkedIn o X persigue algo distinto: no vende, construye criterio y credibilidad. Las herramientas son las mismas o muy parecidas; lo que cambia es el objetivo, y de ahí para abajo cambia casi todo lo que decide la plataforma por el usuario.
**Scope:** el objetivo se elige al crear el proyecto y condiciona lo que el sistema propone: estructura y tono del guion (beneficio + llamada a la acción, frente a idea + punto de vista), registro visual, relación de aspecto y duración por defecto, redes destino, y el texto del post (RM-37). Dos perfiles para empezar: **producto** (promocional, el comportamiento de hoy, formalizado para que no se pierda) y **perfil profesional** (LinkedIn, X y otras redes profesionales). No incluye un pipeline nuevo ni un segundo editor: las herramientas son las que ya existen, lo que se agrega es el objetivo que las orienta. A definir en el plan de implementación: si el objetivo se elige por proyecto o se guarda en el usuario (un profesional probablemente siempre quiere el mismo); si solo cambia valores por defecto y sugerencias o además restringe herramientas que estorban a ese objetivo; qué significa "otras redes profesionales" y cuáles entran; y cómo se mide que un perfil funciona, dado que el éxito de uno es conversión y el del otro es credibilidad -- si no se puede medir, al menos no prometerlo en la UI.

## RM-43 — Tema según el sistema
**Why:** pedido explícito del usuario -- el selector ofrecía claro y oscuro, y faltaba lo que la gente espera de tercera opción: seguir al sistema operativo. Hasta ahora el automático era otro: sin preferencia guardada el tema se elegía por la HORA (RM-19), que adivina lo que el SO ya sabe y contradice a quien tiene el modo oscuro puesto todo el día.
**Scope:** tres opciones -- `claro` / `oscuro` / `sistema` -- donde `sistema` lee `prefers-color-scheme` y es además el valor por defecto sin preferencia guardada. El heurístico por hora desaparece (decisión del usuario al plantearle las alternativas). El botón del `Topbar` cicla entre las tres y su icono muestra la PREFERENCIA, no el tema pintado: con `sistema` hay que poder ver que el control lo tiene el SO. Con `sistema` activo se escucha el cambio del SO en vivo, no solo al cargar. Las preferencias `light`/`dark` guardadas antes siguen siendo válidas; lo que cambia es que no haber elegido nada ahora significa `sistema`. El script inline de `index.html` replica la misma lógica (duplicado a propósito, corre antes del bundle).

## RM-44 — Avisar de una ejecución interrumpida
**Why:** si el worker muere a mitad, la fila queda en `running` para siempre -- el proceso que debía marcarla como fallida es justo el que murió. En la UI se ve idéntica a una que avanza, así que el usuario mira una etapa "en curso" que no se va a mover nunca. Pasó de verdad con un micro-video (`run_id ee2ad68b50de`), que murió cargando el modelo de TTS.
**Scope:** `read_project_status` marca `interrupted` cuando el proyecto dice `running` y la tarea ya no está activa, y la página de detalle lo dice señalando la etapa donde se cortó. **Quién decide es Celery, no el reloj**: una etapa puede tardar minutos sin escribir nada (cargar el modelo de IndexTTS son ~10 GB), así que darla por muerta por tiempo daría falsos positivos. El tiempo solo decide *cuándo* se paga el broadcast, para no hacerlo en cada sondeo del frontend. Si nadie contesta, no se afirma nada: decir "murió" de algo vivo invita a relanzarlo por encima. No incluye relanzarlo (RM-45) ni reanudar desde donde se quedó (RM-46).

## RM-45 — Relanzar una ejecución interrumpida
**Why:** `/resume` solo aceptaba proyectos en `failed`, y una corrida interrumpida (RM-44) se queda en `running` para siempre. O sea que el único proyecto que de verdad necesitaba relanzarse era justo el que el endpoint rechazaba con un 409.
**Scope:** `/resume` acepta además un proyecto `running` **verificado como interrumpido**, y el botón Reintentar aparece en ese caso. La verificación se hace en el servidor y no se confía en el cliente: relanzar algo que sí está corriendo pondría dos workers escribiendo en el mismo directorio de salida. No incluye reanudar desde la etapa donde se cortó (RM-46): hoy la corrida empieza de cero.

## RM-46 — Reanudar el micro-video desde donde se quedó
**Why:** relanzar una corrida interrumpida (RM-45) empezaba de cero, y el micro-video no tenía checkpoints de ningún tipo. Rehacer la síntesis de voz es lo caro: medido en una corrida real, **53,8 s de 58,1 — el 93%**.
**Scope:** solo se reanuda `text_to_speech`, porque todo lo demás junto son ~4 s de ffmpeg y persistirlo costaría más de lo que ahorra. Los `.wav` ya están en disco; lo que se añade es un manifiesto con la huella de cada fragmento (texto + idioma + voz de referencia) para no reusar audio que ya no corresponde — **ese es el riesgo real, porque no falla: genera un video que suena bien y dice otra cosa**. El manifiesto se escribe después de cada fragmento, no al final, porque el caso para el que existe es justo el de una corrida que muere a mitad. Solo con `resume`: una corrida normal sintetiza todo, para que un directorio de trabajo sucio no se convierta en un resultado silenciosamente viejo.

## RM-47 — Rediseño del login
**Why:** primer paso de una revisión de UX pantalla por pantalla, pedida por el usuario. El login se veía bien pero fallaba donde importa: **todo error decía lo mismo**. Una cuenta desactivada leía "correo o contraseña incorrectos" y reintentaba para siempre, aunque el backend sí mandaba el motivo en `detail` y el frontend lo tiraba. Y con la API caída -- que pasó dos veces durante el desarrollo -- el mensaje era indistinguible de una contraseña mal escrita.
**Scope:** dos columnas. El panel de marca es oscuro con rejilla y halo -- no un degradado plano -- y **muestra el producto en vez de describirlo**: una corrida de ejemplo con sus pasos y el micro-video resultante, porque es la única pantalla que ve quien todavía no entró. En móvil se reduce a la cabecera, para no empujar el formulario fuera de la pantalla. El sello de "conexión segura" solo aparece si la página se sirve por https: un candado sobre http sería exactamente la clase de sello que no hay que creer. Contraseña con ojo, autofoco en el correo y aviso de Bloq Mayús. Cuatro mensajes de error distintos en vez de dos. **502/503/504 cuentan como "servidor caído", no como error del servidor**: con la API apagada quien responde es el proxy de delante (Vite en desarrollo, el servidor web en producción), así que decir "el servidor respondió" es falso y "reintenta" es mal consejo -- reintentar no levanta un proceso caído. El control del tema se extrajo a un componente porque ahora vive en dos sitios (topbar y login). No incluye recuperación de contraseña (RM-48): no hay endpoint, así que el login lo dice en vez de ofrecer un enlace a ningún lado.

## RM-48 — Recuperar la contraseña
**Why:** `routers/auth.py` solo tiene `login` y `me`, y `routers/users.py` solo crea usuarios con una contraseña inicial. No hay forma de cambiarla: quien la olvida necesita que alguien edite la base de datos a mano.
**Scope:** por definir. Lo mínimo honesto sería que un admin pueda restablecerla; el envío de correo es otra decisión aparte.

## RM-49 — Menú lateral colapsable
**Why:** el menú ocupa 256 px fijos en todas las pantallas, y en las más densas (el editor de micro-video, el detalle de un proyecto) ese ancho se echa de menos. Quien ya se sabe los iconos no necesita leer los nombres cada vez.
**Scope:** un botón al pie del menú lo reduce a 72 px, solo iconos, con el nombre en el tooltip y una raya fina donde iba el título de cada grupo. La elección se guarda en `localStorage` y se lee en el inicializador del estado, no en un efecto, para que no se pinte ancho y salte al estrecho en el primer frame. **Colapsar es cosa de `lg` para arriba**: por debajo el menú es un cajón (RM-20) que se abre entero o no se abre, así que las etiquetas se esconden por CSS (`lg:hidden`) y no condicionando el JSX -- hacerlo en JS filtraba el estado de escritorio al móvil y dejaba el cajón ancho y sin nombres.

## RM-50 — Rediseño de Música de fondo
**Why:** la página servía sobre todo para escuchar y ordenar lo que ya hay, pero el formulario de alta ocupaba la primera pantalla entera antes de dejar ver una sola pista. Además pintaba una tarjeta por categoría aunque estuviera vacía, y la papelera borraba el `.wav` de un clic, sin preguntar y sin vuelta atrás.
**Scope:** el alta se abre con un botón y arranca cerrada; buscador por título y filtro por categoría con su conteo; solo aparecen las categorías que tienen algo; cada pista es una tarjeta de una sola línea con el play al frente -- es lo único que distingue dos pistas de nombre parecido -- en una **rejilla de 2 o 3 columnas**: en una sola columna cada pista usaba un quinto del ancho y gastaba una segunda línea para repetir "hace 2 meses" 33 veces, así que se veían 6 pistas donde ahora se ven 19. La fecha pasa al tooltip del título. La confirmación de borrado dice de qué pista es: entre decenas de tarjetas iguales, un "¿seguro?" sin nombre es como no preguntar. El borrado se confirma en la propia fila -- no en un `window.confirm`, que es lo que todavía usa `ProjectDetailPage`. **No incluye la duración de cada pista**: el modelo solo guarda `title`, `category`, `file_path` y `created_at`, así que mostrarla exige tocar el backend. Tampoco comprueba si un micro-video está usando la pista que se borra; hoy `delete_music_track` borra el archivo sin mirar.

## RM-51 — La API debe decir su zona horaria
**Why:** las columnas de fecha son `timestamp without time zone` y el valor se guarda en UTC, así que la API devuelve `2026-10-25T23:09:38.445708`, sin marca. JavaScript lee una fecha sin zona como hora **local**, de modo que toda la app mostraba las fechas corridas el offset del usuario -- en UTC-5, cinco horas. Era invisible en proyectos de días atrás; saltó al mostrar una pista recién subida como "Agregada dentro de 5 horas".
**Scope:** por definir, en el backend. Mientras tanto `lib/format.ts` asume UTC cuando la marca no trae zona, en el único sitio por el que pasan todas las fechas del frontend.

## RM-52 — Rediseño del listado de proyectos
**Why:** el botón "Nuevo proyecto" navegaba derecho a `/dubbing/new`. Prosodia no hace "proyectos" a secas -- hace doblajes, subtítulos, transcripciones, voces y micro-videos -- así que el botón elegía por el usuario, y los otros cuatro servicios solo se alcanzaban desde el menú lateral. Además, con el listado paginado de 20 en 20 no había forma de encontrar un proyecto por nombre, y una fila "Procesando" se quedaba así para siempre porque la lista no se refrescaba sola.
**Scope:** "Nuevo proyecto" despliega los cinco servicios. Búsqueda por nombre **en el servidor** (`q` en `GET /api/projects`, con los comodines `%` y `_` escapados -- buscar "clip_2min" traía también "clipX2min"): filtrar en el cliente miraría 20 proyectos de N y diría "no hay" de los que están en la página siguiente. La lista se sondea cada 5 s **solo mientras haya algo activo**, y el estado en marcha lleva un punto latiendo. Fuera la columna "ID de ejecución" -- es dato de diagnóstico y sigue estando, copiable, en el detalle del proyecto. "Duración" pasa a "Procesado en" (junto a "Creado" se leía como la duración del video) y "Tipo" a "Resultado". Dos vacíos distintos: no tener proyectos no es lo mismo que que los filtros no encuentren nada. **Corrige de paso** que un micro-video apareciera como "Solo subtítulos": `output_mode` solo significa algo en doblaje y subtítulos, y la regla estaba escrita al revés, listando las excepciones. No incluye avisar en la lista de una ejecución interrumpida (RM-44): eso vive en `/status`, una llamada por fila.

## RM-53 — Rediseño del detalle de un proyecto
**Why:** todo caía en una columna de 768 px centrada, con media pantalla vacía a cada lado, y en ese apilado lo primero que veía alguien al abrir un proyecto **terminado** eran seis etapas con nombres de ingeniería -- "Audio mux", "Concatenación de audio" -- antes de llegar al video que había hecho. El reproductor, además, era `w-full` sin tope: un micro-video cuadrado o vertical se comía la pantalla porque el alto lo decidía el ancho del contenedor.
**Scope:** dos columnas desde `xl` (a 1024 px partir dejaría 420 px para el video, así que por debajo sigue en una): resultado y progreso a la izquierda, datos del proyecto a la derecha. En un proyecto terminado el resultado va primero, con su nombre -- "Tu video" / "Tu audio" / "Tu transcripción" -- y el progreso se pliega a una línea de resumen (`N etapas · duración`), **plegado, no escondido**. Corriendo o fallido el progreso sigue abierto, que es cuando importa. El reproductor topa por alto (`max-h-[60vh]`) y saca el ancho de la relación de aspecto. "Duración total" pasa a "Procesado en", el mismo nombre que en el listado, y el factor de tiempo real solo aparece cuando tiene valor. El borrado se confirma en línea y dice que se lleva los archivos, no solo la fila -- antes era un `window.confirm`, el último que quedaba en la app.

## RM-54 — Soporte táctil en el editor de Micro-Video
**Nota:** la rama donde se hizo era de septiembre, cuando RM-41 estaba libre; en `main` ese número es la telemetría de Argus, así que al fusionarla se renumeró a RM-54.
**Why:** la auditoría de RM-20 detectó que los gestos de arrastre de `TextOverlayCanvas` y `VideoSegmentTimeline` usaban solo eventos de mouse (decisión deliberada para evitar un bug de Safari con Pointer Events, ver comentarios en ambos archivos) y por eso no funcionaban en tablet/celular. Es un problema de INPUT, no de layout, así que quedó fuera del alcance de RM-20.
**Scope:** mouse y touch events en paralelo (sin Pointer Events, para no reintroducir el bug de Safari) vía un helper compartido (`lib/dragEvents.ts`). Cubre mover overlays de texto/emoji y el preview de captions, panear la imagen/video de fondo, y en la franja de recorte: arrastrar el cuerpo de un tramo (unir/separar), sus bordes (acortar) y la selección en modo corte. `touch-action: none` en los elementos arrastrables evita que el navegador interprete el gesto como scroll de la página. Fuera de alcance: doble clic para saltar a un punto (sigue siendo solo mouse, no es un gesto de arrastre).


## RM-55 — Rediseño de Voz y clonación, con ayuda de IA para el texto
**Why:** el primer campo de la página era "Nombre del proyecto" -- un trámite por delante de lo único que el usuario vino a hacer, que es escribir el texto. Todo caía en una columna de 768 px, y nada decía cuánto audio saldría de lo escrito, que es justo lo que determina si la síntesis tarda segundos o minutos.
**Scope:** dos columnas desde `xl`: el texto ocupa el centro y los ajustes (idioma, voz, nombre) se van al lado. El nombre pasa a ser opcional y se deriva del texto. Bajo el campo, cuántas palabras hay y cuánto audio son, a 2,3 palabras por segundo -- **la misma constante que usa el prompt del guion en el backend**, para que la estimación y el límite que se le pide al modelo no se contradigan.

La ayuda de IA son **dos acciones, no una**: *Escribir desde la idea* (`draft`) y *Mejorar* (`polish`). Con el campo lleno solo el usuario sabe si lo que hay es una idea o el texto final; adivinarlo por la longitud reescribiría un texto ya terminado. Puerto `NarrationAssistant` aparte de `ScriptWriter` (RM-42): aquel produce guion de redes -- gancho, llamada a la acción, duración que cumplir -- y eso es exactamente lo que no quiere quien solo va a narrar. **`polish` no recibe idioma, por diseño**: corregir no es traducir, y la firma lo impide. Además expande para el oído lo que una voz sintética lee mal (`3` → "tres", `4pm` → "cuatro de la tarde", `18°C` → "dieciocho grados centígrados"). Toda sustitución guarda el texto anterior y ofrece deshacer: sin eso, "mejorar" es una apuesta sobre lo que el usuario escribió. Si el modelo no responde, la página lo dice y se sigue escribiendo a mano -- la ayuda es opcional, el texto no.


---
**Descartado:** reemplazo/agregado de pista de audio en un video existente — evaluado, sin caso de uso claro con el negocio. Sin ID (nunca entró en desarrollo activo).
