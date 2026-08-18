# Material didáctico desde videos de YouTube

Prototipo académico que transforma videos educativos de YouTube en material didáctico estructurado. Su pipeline previsto integra ingesta, Whisper local, embeddings con ChromaDB local y generación anclada al contenido mediante Gemini.

## Alcance actual

El backend funcional vive en `backend/`. El Sprint 1 implementa la ingesta de videos públicos de YouTube con idioma español o inglés y duración máxima de 60 minutos. El Sprint 2 implementa el resumen RAG en `POST /api/v1/materials/summary`.

El resumen recupera únicamente chunks indexados en ChromaDB, limita el contexto enviado a Gemini y valida que cada timestamp del glosario y de los bloques didácticos exista en la evidencia recuperada. Gemini recibe el esquema Pydantic de la salida para forzar un JSON estructurado. La salida permite hasta 4096 tokens para completar el recurso, mientras la entrada permanece limitada a 12000 caracteres. Si Gemini devuelve JSON inválido, excede 200 palabras o cita un timestamp no recuperado, la API rechaza la respuesta. Los fallos temporales de Gemini se reintentan una vez y después se devuelven como `503`.

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

La documentación queda en `http://127.0.0.1:8000/docs`; `GET /api/v1/health` comprueba que la API levantó. Consulta `docs/CHANGELOG.md` para el historial por sprint.

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

## Siguientes incrementos

1. Sprint 3: cuestionario de autoevaluación (HU-04).
2. Sprint 4: progreso, edición y exportación (HU-02, HU-06 y HU-07).
3. Sprint 5: configuración Bloom y retroalimentación interactiva (HU-08 y HU-09).
