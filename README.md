# Material didáctico desde videos de YouTube

Prototipo académico que transforma videos educativos de YouTube en material didáctico estructurado. Su pipeline previsto integra ingesta, Whisper local, embeddings con ChromaDB local y generación anclada al contenido mediante Gemini.

## Alcance actual

El backend funcional vive en `backend/`. Los Sprints 1 y 2 implementan la ingesta de videos públicos de YouTube con idioma español o inglés y duración máxima de 60 minutos, además del resumen RAG en `POST /api/v1/materials/summary`. El Sprint 3 incorpora el cuestionario de autoevaluación en `POST /api/v1/materials/quiz`. El Sprint 4 añade ingesta asíncrona con progreso, edición persistida y exportación local de materiales. El Sprint 5 completa la selección de niveles de Bloom y la retroalimentación interactiva.

El resumen recupera únicamente chunks indexados en ChromaDB, limita el contexto enviado a Gemini y valida que cada timestamp del glosario y de los bloques didácticos exista en la evidencia recuperada. Gemini recibe el esquema Pydantic de la salida para forzar un JSON estructurado. La salida permite hasta 4096 tokens para completar el recurso, mientras la entrada permanece limitada a 12000 caracteres. Si Gemini devuelve JSON inválido, excede 200 palabras o cita un timestamp no recuperado, la API rechaza la respuesta. Los fallos temporales de Gemini se reintentan una vez y después se devuelven como `503`.

El cuestionario recupera evidencia distinta desde ChromaDB, solicita a Gemini preguntas de opción múltiple y abiertas, y valida localmente que el número de preguntas, las cuatro opciones distintas y cada timestamp correspondan a evidencia recuperada. Si no hay evidencia suficiente, devuelve listas vacías con una nota explicativa, sin inventar preguntas.

Los recursos generados se almacenan en SQLite con un `material_id`: pueden consultarse o reemplazarse mediante API sin volver a consumir Gemini. También se exportan localmente a JSON o Markdown dentro de `data/exports`. Para ingestas largas, `POST /api/v1/videos/ingest/async` devuelve de inmediato un `video_id`; la interfaz puede sondear `GET /api/v1/videos/{video_id}/progress` hasta obtener el estado `indexed` o `failed`.

Al solicitar un cuestionario, el cliente puede configurar uno o varios niveles de Bloom: `remember`, `understand`, `apply`, `analyze`, `evaluate` y `create`. Cada pregunta conserva su `bloom_level`. La retroalimentación de opción múltiple es inmediata y local; las respuestas abiertas se evalúan con Gemini y evidencia RAG, conservando el timestamp de respaldo del cuestionario.

La interfaz visual integrada está disponible en `http://127.0.0.1:8000/ui/`. Permite probar el flujo completo sin construir solicitudes HTTP manuales: ingesta con progreso, generación de resumen/cuestionario, selección Bloom, respuestas, retroalimentación, edición y exportación.

## Requisitos cubiertos

- RF-01: ingesta y procesamiento de video.
- RF-02: sinopsis, glosario y bloques didácticos.
- RF-03: cuestionarios por niveles de Bloom.
- RF-04: consulta y exportación.
- RF-05: búsqueda de videos por palabras clave.
- RF-06: configuración de parámetros didácticos.

## Inicio local

Requiere Python 3.11+, FFmpeg y una clave gratuita de Google AI Studio. La clave de YouTube Data API v3 es opcional para el futuro buscador.

Si YouTube rechaza un video público con mensajes como `The page needs to be reloaded`, exporta las cookies de la sesión autenticada en formato Netscape y configura su ubicación mediante `YTDLP_COOKIE_FILE`. El archivo de cookies es confidencial y no debe subirse al repositorio.

\`\`\`powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend
uvicorn app.main:app --reload
\`\`\`

Después de iniciar el servidor, abre `http://127.0.0.1:8000/ui/` y sigue el orden de los seis paneles. Antes de probar, configura `GEMINI_API_KEY` en `.env` y verifica que FFmpeg esté instalado y disponible en `PATH`. Las cookies Netscape en `data/cookies.txt` sólo deben renovarse si YouTube bloquea la ingesta de un video nuevo. La documentación queda en `http://127.0.0.1:8000/docs`; `GET /api/v1/health` comprueba que la API levantó. Consulta `docs/CHANGELOG.md` para el historial por sprint.

## Carpetas

| Ruta | Propósito |
| --- | --- |
| \`app/api\` | Endpoints HTTP versionados y dependencias FastAPI. |
| \`app/core\` | Configuración y aspectos transversales. |
| \`app/db\` y \`app/models\` | SQLite, sesión y entidades de metadatos. |
| \`app/schemas\` | Contratos Pydantic de entrada/salida. |
| \`app/services\` | Casos de uso y adaptadores de YouTube, Whisper, RAG, Gemini y exportación. |
| \`app/repositories\` | Acceso aislado a SQLite. |
| \`app/utils\` | Funciones reutilizables, por ejemplo segmentación. |
| \`tests\` | Pruebas unitarias y de integración. |
| \`notebooks\` | Prototipos aislados de Whisper, embeddings/ChromaDB y Gemini. |
| \`data\` | Datos locales: transcripciones, ChromaDB, SQLite y exportaciones. |

## Estado del alcance

Los cinco sprints previstos han sido implementados. Las ampliaciones futuras pueden incorporar interfaz web, autenticación de estudiantes o nuevos formatos de exportación, sin alterar el pipeline local actual.
