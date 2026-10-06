# Backend: pipeline RAG local

## Requisitos

- Windows 10/11 (los comandos de esta guía usan PowerShell).
- Python 3.11 o superior.
- FFmpeg instalado y disponible en `PATH`.
- Una clave de Google AI Studio para `GEMINI_API_KEY`.
- Conexión a internet durante la primera ingesta y para descargar los modelos
  de Whisper y embeddings.

Comprueba las herramientas antes de instalar:

```powershell
python --version
ffmpeg -version
```

## Instalación limpia

Desde la raíz del repositorio:

```powershell
Set-Location .\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example ..\.env
```

Si PowerShell bloquea la activación del entorno, ejecútalo una vez con una
terminal abierta como usuario:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

No es obligatorio activar el entorno: también puedes sustituir `python` por
`.\.venv\Scripts\python.exe` y `uvicorn` por
`.\.venv\Scripts\uvicorn.exe`.

## Ejecutar

Desde `backend`, con el entorno virtual activo:

```powershell
uvicorn app.main:app --reload
```

Con el servidor activo, abre `http://127.0.0.1:8000/ui/` para usar la interfaz visual. La documentación técnica sigue disponible en `http://127.0.0.1:8000/docs`.

Antes de la primera prueba, edita `../.env` y asigna una clave válida a
`GEMINI_API_KEY` y un secreto aleatorio a `JWT_SECRET_KEY`. Sólo necesitas
actualizar `data/cookies.txt` si la ingesta de un video nuevo falla por una
restricción de YouTube.

Para generar un secreto local:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Para autenticación, configura también `JWT_SECRET_KEY` con una cadena larga y aleatoria. El registro y el inicio de sesión usan JSON y devuelven un token Bearer:

```powershell
$user = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/register `
  -ContentType 'application/json' `
  -Body '{"nombre":"Ada Lovelace","email":"ada@example.com","password":"clave-segura-123"}'

$token = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType 'application/json' `
  -Body '{"email":"ada@example.com","password":"clave-segura-123"}'

$authorization = @{ Authorization = "Bearer $($token.access_token)" }
```

El token identifica al usuario, pero no concede un rol global. Los permisos
se resuelven por grupo: el creador de un grupo es su administrador; una misma
persona puede ser administrador de un grupo y miembro normal de otro.

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

La respuesta de resumen o cuestionario incluye `material_id`. Consulta su
contenido, reemplázalo por una versión válida y expórtalo sin generar de nuevo:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/materials/1

$material = Invoke-RestMethod http://127.0.0.1:8000/api/v1/materials/1
# Ajusta $material.content y luego conserva sólo ese objeto en la petición PUT.
Invoke-RestMethod -Method Put -Uri http://127.0.0.1:8000/api/v1/materials/1 `
  -Headers $authorization `
  -ContentType 'application/json' `
  -Body (@{ content = $material.content } | ConvertTo-Json -Depth 20)
```

La edición requiere autenticación y sólo se permite al dueño del video o al
administrador de un grupo donde ese video esté publicado como tema. `content`
se valida contra `SummaryResponse` o `QuizResponse`; una edición inválida
responde `422` con el código `INVALID_MATERIAL_CONTENT`. Antes de reemplazar
el contenido actual se guarda una instantánea en `MaterialVersion`, consultable
con:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/materials/1/versions `
  -Headers @{ Authorization = "Bearer $token" }

# $versionId es el id de una entrada de /versions.
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/materials/1/versions/$versionId/restore" `
  -Headers @{ Authorization = "Bearer $token" }

```

Para exportar, utiliza uno de estos valores: `markdown`, `json`, `pdf` o
`docx`. PDF se genera con ReportLab y DOCX con python-docx, directamente desde
el JSON validado y sin usar un navegador:

```powershell
Invoke-RestMethod -Method Get `
  -Uri 'http://127.0.0.1:8000/api/v1/materials/1/export?format=pdf' `
  -OutFile ..\data\exports\material_1.pdf

Invoke-RestMethod -Method Get `
  -Uri 'http://127.0.0.1:8000/api/v1/materials/1/export?format=docx' `
  -OutFile ..\data\exports\material_1.docx
```

El servidor también conserva los archivos en `data/exports`. La edición y la
restauración requieren el encabezado `Authorization`; la consulta y
exportación no lo requieren actualmente.

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

La interfaz se divide en vistas independientes, servidas sin framework desde `/ui/`:

1. `/ui/video/`: pega una URL pública de YouTube y espera a que la ingesta alcance `indexed`.
2. `/ui/resumen/?video=42`: genera el resumen grounded de un video indexado.
3. `/ui/quiz/?video=42`: configura niveles de Bloom, genera y responde un cuestionario.
4. `/ui/material/?video=42&material=17`: carga, edita, restaura versiones y
   exporta un material existente.

`video` y `material` se conservan en los query params; por ello los enlaces se pueden recargar o compartir sin depender de variables globales de JavaScript. La interfaz no sustituye ninguna ruta de API: usa los mismos endpoints documentados, por lo que es útil tanto para la demostración de tesis como para verificar manualmente el flujo completo.

## Pruebas automatizadas

Desde `backend`, con el entorno virtual activo:

```powershell
python -m pytest -q
```

Para validar específicamente la exportación:

```powershell
python -m pytest tests\services\test_export_service.py -q
```

Las pruebas unitarias no requieren una clave de Gemini ni procesar un video.
Las pruebas manuales de ingesta sí descargan modelos y pueden tardar varios
minutos la primera vez.

## Solución de problemas

- **`ffmpeg` no se reconoce**: instala FFmpeg y agrega su carpeta `bin` al
  `PATH`; abre una nueva terminal y repite `ffmpeg -version`.
- **Falla la activación de `.venv`**: usa la política
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` o ejecuta directamente
  `.\.venv\Scripts\python.exe`.
- **`GEMINI_API_KEY` ausente**: verifica que la variable esté en
  `C:\...\transcript_yt 2\.env`, no en `backend\.env`.
- **YouTube rechaza la descarga**: configura un archivo Netscape de cookies en
  `data\cookies.txt` y confirma que `YTDLP_COOKIE_FILE=../data/cookies.txt`
  apunte a ese archivo. Nunca subas las cookies al repositorio.
- **Primera ejecución lenta**: Whisper, Sentence Transformers y ChromaDB pueden
  descargar modelos o crear índices locales en `data`.
- **Error al exportar PDF/DOCX**: reinstala las dependencias del backend con
  `python -m pip install -r requirements.txt`.
