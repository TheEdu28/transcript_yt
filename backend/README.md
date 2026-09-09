# Backend: pipeline RAG local

## Ejecutar

Desde backend:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    Copy-Item .env.example ..\.env
    uvicorn app.main:app --reload

Con el servidor activo, abre `http://127.0.0.1:8000/ui/` para usar la interfaz visual. La documentación técnica sigue disponible en `http://127.0.0.1:8000/docs`.

Antes de la primera prueba, edita `../.env` y asigna una clave válida a `GEMINI_API_KEY`. También instala FFmpeg y asegúrate de que esté disponible en `PATH`. Sólo necesitas actualizar `data/cookies.txt` si la ingesta de un video nuevo falla por una restricción de YouTube.

- POST /api/v1/videos/ingest: valida URL pública de YouTube, idioma es/en y duración <=60 min; extrae audio, transcribe con faster-whisper, fragmenta, vectoriza e indexa en ../data/chroma_db.
- POST /api/v1/materials/summary: recuperación ChromaDB + Gemini con salida grounded.
- POST /api/v1/materials/quiz: cuestionario sustentado por evidencia temporal.

La primera transcripción descarga el modelo Whisper y la primera indexación descarga el modelo all-MiniLM-L6-v2. Esas descargas y el rendimiento de Whisper dependen del equipo. El límite de contexto de Gemini (MAX_GEMINI_CONTEXT_CHARS=12000) reduce el consumo de la capa gratuita.

## Probar el cuestionario (HU-04)

Primero ingesta un video y conserva su `video_id`. Con ese identificador, solicita el cuestionario:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/materials/quiz `
  -ContentType 'application/json' `
  -Body '{"video_id": 1, "multiple_choice_count": 5, "open_question_count": 3}'
```

La respuesta contiene `multiple_choice`, `open_questions`, `evidence_sufficient` e `insufficiency_note`. Cada pregunta referencia un `evidence_timestamp` que corresponde a un límite temporal recuperado desde la transcripción indexada.

## Progreso, edición y exportación (Sprint 4)

Para iniciar una ingesta no bloqueante y consultar su avance:

```powershell
$job = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/videos/ingest/async `
  -ContentType 'application/json' `
  -Body '{"url":"https://www.youtube.com/watch?v=VIDEO_ID"}'

Invoke-RestMethod "http://127.0.0.1:8000/api/v1/videos/$($job.video_id)/progress"
```

La respuesta de resumen o cuestionario ahora incluye `material_id`. Consulta su contenido, reemplázalo por una versión válida y expórtalo sin generar de nuevo:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/materials/1

$material = Invoke-RestMethod http://127.0.0.1:8000/api/v1/materials/1
# Ajusta $material.content y luego conserva sólo ese objeto en la petición PUT.
Invoke-RestMethod -Method Put -Uri http://127.0.0.1:8000/api/v1/materials/1 `
  -ContentType 'application/json' `
  -Body (@{ content = $material.content } | ConvertTo-Json -Depth 20)

Invoke-RestMethod -Method Get `
  -Uri 'http://127.0.0.1:8000/api/v1/materials/1/export?format=markdown' `
  -OutFile ..\data\exports\material_1.md
```

Los formatos disponibles son `markdown` y `json`. El servidor crea también el archivo local en `data/exports`.

## Bloom y retroalimentación (Sprint 5)

Configura los niveles cognitivos al generar un cuestionario. Si omites `bloom_levels`, se usan `remember`, `understand` y `apply`:

```powershell
$quiz = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/materials/quiz `
  -ContentType 'application/json' `
  -Body '{"video_id":1,"multiple_choice_count":3,"open_question_count":2,"bloom_levels":["remember","apply"]}'
```

Envía un intento parcial o completo al `material_id` recibido. La opción múltiple se corrige localmente; las respuestas abiertas usan Gemini con evidencia recuperada desde ChromaDB:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/materials/$($quiz.material_id)/feedback" `
  -ContentType 'application/json' `
  -Body '{"multiple_choice_answers":[{"question_index":0,"selected_option":1}],"open_answers":[{"question_index":0,"answer":"Mi explicación de la respuesta."}]}'
```

La respuesta conserva `evidence_timestamp`, indica si una opción fue correcta y, para preguntas abiertas, devuelve `achieved_points`, `missing_points` y una sugerencia breve.

## Interfaz visual

La página `/ui/` concentra las pruebas manuales del prototipo en este orden:

1. Pega una URL pública de YouTube y espera a que la barra de progreso alcance `indexed`.
2. Genera un resumen o selecciona niveles de Bloom y genera el cuestionario.
3. Responde las preguntas y presiona **Revisar respuestas**.
4. Usa el `material_id` que aparece automáticamente para cargar, editar y exportar el material en Markdown.

La interfaz no sustituye ninguna ruta de API: usa los mismos endpoints documentados, por lo que es útil tanto para la demostración de tesis como para verificar manualmente el flujo completo.
