# Changelog

Este archivo registra los incrementos funcionales del prototipo de tesis.

## Sprint 5 - HU-08 y HU-09

### Implementado

- Configuración de uno o varios niveles de Bloom en la solicitud de cuestionario: `remember`, `understand`, `apply`, `analyze`, `evaluate` y `create`.
- Etiquetado obligatorio de cada pregunta con su `bloom_level` y rechazo de niveles no solicitados.
- Nuevo endpoint `POST /api/v1/materials/{material_id}/feedback` para recibir intentos parciales o completos.
- Corrección local e inmediata de preguntas de opción múltiple, sin consumir la cuota de Gemini.
- Evaluación de preguntas abiertas con Gemini y contexto RAG recuperado de ChromaDB; se validan índices y timestamps antes de devolver la retroalimentación.
- Pruebas unitarias sin proveedores externos para Bloom, respuestas duplicadas, evidencia temporal y retroalimentación abierta.

### Pendiente

- No quedan historias de usuario planificadas en los cinco sprints iniciales.

## Sprint 4 - HU-02, HU-06 y HU-07

### Implementado

- Ingesta asíncrona en `POST /api/v1/videos/ingest/async` y sondeo de etapas/porcentaje en `GET /api/v1/videos/{video_id}/progress`.
- Persistencia SQLite de resúmenes y cuestionarios generados, con `material_id` para su consulta y trazabilidad.
- Consulta y edición validada de materiales mediante `GET` y `PUT /api/v1/materials/{material_id}`, sin volver a consumir Gemini.
- Exportación local reproducible a JSON y Markdown mediante `GET /api/v1/materials/{material_id}/export`.
- Migración compatible con SQLite existente para añadir los campos de progreso, y pruebas unitarias sin Whisper, ChromaDB ni Gemini.

### Pendiente

- Sprint 5: HU-08 y HU-09 para seleccionar niveles de Bloom y recibir retroalimentación interactiva.

## Sprint 3 - HU-04

### Implementado

- Cuestionario de autoevaluación en `POST /api/v1/materials/quiz`, con preguntas de opción múltiple y abiertas generadas por Gemini a partir de evidencia RAG local.
- Anclaje obligatorio de cada pregunta a un timestamp `HH:MM:SS` existente en los chunks recuperados de ChromaDB.
- Validación local de la respuesta: número solicitado de preguntas, cuatro opciones distintas, opción correcta válida y estructura JSON controlada.
- Respuesta segura ante evidencia insuficiente: Gemini debe devolver listas vacías y una nota, en lugar de generar contenido no fundamentado.
- Pruebas unitarias sin proveedores externos para cuestionarios válidos, timestamps ajenos, cantidades incorrectas, opciones repetidas y evidencia insuficiente.

### Pendiente

- Sprint 4: HU-02, HU-06 y HU-07 para progreso en tiempo real, edición y exportación.

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
