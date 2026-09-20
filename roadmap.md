# Roadmap — Prosodia

Índice. Detalle de cada item en [docs/roadmap.md](docs/roadmap.md).

| # | Feature | Status | Description |
|---|---------|--------|-------------|
| RM-01 | Transcripción standalone | done | Subir audio/video y obtener transcripción sin traducir ni doblar. |
| RM-02 | TTS standalone | done | Texto → audio, con voz pública o propia. |
| RM-03 | Analítica de negocio | done | Stats reales en el dashboard, sobreviven al borrado del proyecto. |
| RM-04 | Página de subtítulos | done | Formulario de creación real para el servicio de subtítulos. |
| RM-05 | Previsualización de media | done | Reproductor de video/audio inline antes de descargar. |
| RM-06 | Waveform reactivo en vivo | done | Animación de ondas que reacciona al audio real. |
| RM-07 | Importar proyecto desde URL | done | Subir archivo, pegar URL, o buscar en YouTube dentro de la app. |
| RM-08 | Atribución correcta de fallos de etapa | done | La UI señala la etapa real que falló, no la siguiente. |
| RM-09 | Librería de voces persistente | todo | Guardar y reusar voces clonadas entre proyectos. |
| RM-10 | Plantillas reutilizables | todo | Guardar config de un proyecto como plantilla nombrada. |
| RM-11 | Documento → audio narrado | todo | Resumir un documento y narrarlo con TTS. |
| RM-12 | API para desarrolladores | todo | Auth por API key + rate limiting para uso externo. |
| RM-13 | Workspace multi-usuario + facturación | todo | Equipos con varios usuarios y billing. |
| RM-14 | Imagen+texto → micro-video social | done | Video vertical narrado (Ken Burns + captions) desde una imagen y un texto. |
| RM-15 | Gestión de usuarios | done | Sección en el menú para administrar usuarios y su rol. |
| RM-16 | Columnas de ejecución en la tabla de proyectos | done | Agregar ID de ejecución y duración total al listado. |
| RM-17 | Selector de fuente de media: orden y validación de URL | done | YouTube primero; validar URL antes de habilitar el envío si falla el preview. |
| RM-18 | Resumen con highlights en Transcripción | done | Toggle opcional: además de la transcripción completa, un resumen de puntos clave. |
| RM-19 | Modo oscuro | done | Detecta claro/oscuro por la hora del sistema; botón para alternar a demanda. |
| RM-20 | Auditoría de diseño responsive | todo | Revisar y corregir el diseño para tablet/celular. |
| RM-21 | Mensajes de error legibles del pipeline | todo | Traducir el error técnico de una etapa fallida a una causa probable entendible. |
| RM-22 | Micro-video con video generado por IA | todo | Alternativa a RM-14 con un modelo de video generativo en vez de composición ffmpeg. |
| RM-23 | Estilo de resaltado de captions: caja o color de texto | done | Elegir entre caja de fondo (actual) o cambiar el color de la palabra. |
| RM-24 | Música de fondo en micro-video | done | Biblioteca de pistas para elegir, o sin música. |
| RM-25 | Resaltado por palabra en captions (karaoke) | done | Elegir entre pintar toda la frase o solo la palabra que se está hablando. |
| RM-26 | Categorías de música + panel de mantenimiento | done | 5 categorías de música de fondo y una pantalla admin para subir pistas nuevas (con limpieza automática de audio). |
| RM-27 | Texto editable sobre el video | done | Superado por RM-28 (texto movible incluye elegir la posición). |
| RM-28 | Editor de video completo | done | Editor con texto movible, audio de fondo recortable, subtítulos y voz en off, todo en un mismo lienzo. |
| RM-29 | Múltiples imágenes en el micro-video | done | Crear el video a partir de varias imágenes en vez de una sola. |
| RM-30 | Ajustar tamaño/posición de la imagen | done | Recortar/reposicionar cada imagen dentro del lienzo antes de generar. |
| RM-31 | Filtros de imagen (brillo, contraste, sepia, etc.) | done | Estilos preestablecidos de color sobre la(s) imagen(es). |
| RM-32 | Emoticones sobre el video | done | Agregar emojis arrastrables igual que el texto. |
| RM-33 | Estilos de texto más profesionales | done | Sombra, degradado, contorno y otras variantes visuales para el texto/captions. |
| RM-34 | Podcast de audio | todo | Nuevo servicio: guion largo → episodio de audio, con voz pública o clonada. |
| RM-35 | Logo e icono de marca definitivos | done | Reemplaza el ícono genérico (sparkle) por el logo real de Prosodia en el sidebar, login y favicon. |
| RM-36 | Videos como input para Micro-Video | done | Además de imágenes, poder usar clips de video existentes como material de entrada del short video. |
| RM-37 | Publicar el short video en redes sociales | todo | Publicar el video generado en TikTok, YouTube, Instagram y Facebook, una por una o todas a la vez. |
| RM-38 | Generación: banco de imágenes/audios/videos a demanda | todo | Nueva sección para generar material con IA de antemano y reusarlo luego en Micro-Video. |
| RM-39 | Generación agéntica de short videos | todo | Un agente arma el short video de punta a punta a partir de un objetivo, usando las herramientas ya existentes. |
| RM-40 | Cortar y eliminar segmentos del video | done | Quitar varios tramos sueltos de la duración de un clip (inicio, medio, fin) y no solo un único rango, con deshacer tipo Cmd+Z. |
| RM-41 | Soporte táctil en el editor de Micro-Video | done | Los gestos de arrastre (mover texto/emoji, paneo, recorte/unión de segmentos) funcionan también con touch, no solo mouse. |
