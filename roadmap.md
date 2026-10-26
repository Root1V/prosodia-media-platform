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
| RM-19 | Modo oscuro | done | Paleta oscura y botón para alternar el tema (el automático lo redefine RM-43). |
| RM-20 | Auditoría de diseño responsive | done | Revisar y corregir el diseño para tablet/celular. |
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
| RM-37 | Publicar el short video en redes sociales | todo | Publicar el video generado en TikTok, YouTube, Instagram, Facebook, LinkedIn y X, una por una o todas a la vez. |
| RM-38 | Generación: banco de imágenes/audios/videos a demanda | todo | Nueva sección para generar material con IA de antemano y reusarlo luego en Micro-Video. |
| RM-39 | Generación agéntica de short videos | todo | Un agente arma el short video de punta a punta a partir de un objetivo, usando las herramientas ya existentes. |
| RM-40 | Cortar y eliminar segmentos del video | done | Quitar varios tramos sueltos de la duración de un clip (inicio, medio, fin) y no solo un único rango, con deshacer tipo Cmd+Z. |
| RM-41 | Telemetría OpenTelemetry (integración Argus) | done | Instrumentar API y worker: la traza cruza la cola Redis→Celery y los logs del pipeline llegan correlacionados. |
| RM-42 | Perfiles de objetivo: producto vs posicionamiento profesional | todo | El objetivo del video pasa a ser una elección explícita que condiciona guion, tono, formato y redes, con las mismas herramientas. |
| RM-43 | Tema según el sistema | done | Tercera opción además de claro y oscuro: seguir al sistema operativo, en vivo. |
| RM-44 | Avisar de una ejecución interrumpida | done | Un worker que muere deja el proyecto en "corriendo" para siempre; ahora se detecta y se dice en qué etapa se cortó. |
| RM-45 | Relanzar una ejecución interrumpida | done | El botón Reintentar ya sirve para una corrida que murió, no solo para una fallida. |
| RM-46 | Reanudar el micro-video desde donde se quedó | done | Al relanzar, se reusa la voz ya sintetizada si el texto no cambió (es el 93% del tiempo). |
| RM-47 | Rediseño del login | done | Dos columnas que dicen qué hace Prosodia, contraseña visible, y errores que distinguen clave mala, cuenta desactivada y servidor caído. |
| RM-48 | Recuperar la contraseña | todo | Hoy no existe: quien la olvida depende de que alguien toque la base de datos, y el login tiene que admitirlo. |
| RM-49 | Menú lateral colapsable | done | Un botón reduce el menú a solo iconos y recuerda la elección; en móvil el cajón sigue abriéndose entero. |
| RM-50 | Rediseño de Música de fondo | done | El alta deja de ocupar la primera pantalla, se puede buscar y filtrar por categoría, y la papelera pregunta antes de borrar. |
| RM-51 | La API debe decir su zona horaria | todo | Las fechas viajan en UTC pero sin marca de zona, así que el navegador las lee como locales; hoy se compensa en el frontend. |
| RM-52 | Rediseño del listado de proyectos | done | "Nuevo proyecto" deja elegir el servicio en vez de meterte en doblaje, se busca por nombre, y la lista se refresca sola mientras algo corre. |
| RM-53 | Rediseño del detalle de un proyecto | done | Lo primero que se ve de un proyecto terminado es lo que produjo, no sus seis etapas internas; el contenido usa el ancho de la pantalla. |
| RM-54 | Soporte táctil en el editor de Micro-Video | done | Los gestos de arrastre (mover texto/emoji, paneo, recorte/unión de segmentos) funcionan también con touch, no solo mouse. |
| RM-55 | Rediseño de Voz y clonación, con ayuda de IA para el texto | done | El texto ocupa el centro, muestra cuánto audio será, y la IA lo redacta desde una idea o lo corrige — con deshacer. |
| RM-56 | Decir qué está pasando durante la síntesis de voz | todo | Sintetizar cuesta ~13× lo que durará el audio y el pipeline calla: 10 minutos indistinguibles de una ejecución muerta. |
| RM-57 | Rediseño de Nueva transcripción | done | Abre en "Subir archivo" y no en el buscador de YouTube, el nombre deja de ser obligatorio, y Transcribir se habilita solo cuando hay algo que transcribir. |
| RM-58 | Rediseño de Nuevos subtítulos, con idiomas visibles | done | La página traducía inglés→español en silencio; ahora el par se elige, y contexto/tono/glosario se pliegan. |
| RM-59 | Rediseño de Nuevo doblaje, con idiomas visibles | done | Misma omisión que RM-58 — el par de idiomas era fijo y mudo — más un rango de hablantes que nadie validaba. |
