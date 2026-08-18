# Changelog

Este archivo registra los incrementos funcionales del prototipo de tesis.

## Corrección de integración YouTube

- Se agregó `YTDLP_COOKIE_FILE` para configurar explícitamente el archivo local de cookies usado por yt-dlp.
- Se actualizó yt-dlp a `2026.7.4` para incorporar correcciones recientes del extractor de YouTube.
- Las cookies permanecen fuera de control de versiones y no se copian ni se exponen desde la aplicación.

## Corrección de salida Gemini

- El resumen envía el esquema Pydantic `SummaryResponse` a Gemini para recibir JSON estructurado.
- Se normalizan bloques Markdown accidentales antes de validar la respuesta.
- Se actualizó el SDK `google-genai` a `2.18.1` y se agregó un reintento para fallos transitorios `429`, `500` y `503`.

## Sprint 2 - HU-03 y HU-05

### Implementado

- Recuperación de chunks relevantes indexados en ChromaDB para construir el contexto RAG del resumen.
- Presupuesto estricto de caracteres de contexto antes de llamar a Gemini, para proteger la capa gratuita.
- Contrato estructurado de sinopsis, glosario y bloques didácticos con timestamps `HH:MM:SS`.
- Verificación posterior: cada timestamp generado debe coincidir con un límite temporal de la evidencia recuperada.
- Rechazo controlado de JSON inválido, sinopsis de más de 200 palabras y respuestas inconsistentes por evidencia insuficiente.
- Pruebas unitarias sin proveedores externos para contexto limitado, timestamps fundamentados y errores de salida.

### Pendiente

- Sprint 3: HU-04, cuestionario de autoevaluación con evidencia temporal.

## Sprint 1 - HU-01 y HU-10

### Implementado

- Validación previa a la descarga de URLs de videos YouTube, excluyendo listas de reproducción y dominios ajenos.
- Verificación de acceso público, rechazo de transmisiones en vivo y error específico para videos privados/no disponibles.
- Restricción configurable de duración máxima de 60 minutos.
- Aceptación exclusiva de contenido declarado en español o inglés, incluyendo metadatos de subtítulos.
- Pruebas unitarias sin dependencias de red para URL, visibilidad, idioma y duración.

### Pendiente

- Sprint 2: HU-03 y HU-05, resumen estructurado y anclaje temporal mediante RAG.
