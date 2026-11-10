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

Para permitir que otros dispositivos o computadoras en la misma red Wi-Fi/LAN prueben el sistema:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Con el servidor activo, abre `http://127.0.0.1:8000/ui/` para usar la interfaz visual desde la máquina local, o `http://<IP-LOCAL>:8000/ui/` desde otra computadora en la misma red (por ejemplo `http://192.168.100.13:8000/ui/`). La documentación técnica sigue disponible en `/docs`.

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

## Roles, calificaciones y resúmenes (actividad por tema)

Los permisos se resuelven por grupo (administrador/docente vs. miembro/alumno):

- **Calificar por actividad:** `GET /api/v1/groups/{group_id}/topics/{topic_id}/summary` lista a los alumnos con `status` (`evaluated`, `pending`, `not_submitted`), `attempt_count`, `latest_score` y `final_score`. El docente consulta los intentos de un alumno con `GET .../topics/{topic_id}/attempts?user_id={id}` y modifica la nota con `PATCH .../topics/{topic_id}/attempts/{attempt_id}` (`final_score` 0–100 y `review_notes`). Un alumno solo obtiene sus propios intentos (el `user_id` se ignora) y recibe `403` al intentar calificar.
- **Videos:** `GET /api/v1/videos?search=texto&order=desc|asc` ordena por `created_at` (predeterminado `desc`) y filtra por título sin distinguir mayúsculas.
- **Cuestionario con/sin respuestas:** a los alumnos, `GET /materials/{id}`, `GET /groups/{id}/topics/{id}/materials` y `GET /materials/{id}/export` devuelven el cuestionario sin `correct_option`, `explanation` ni `expected_points`; `export?include_answers=true` solo se concede al docente (`403` para alumnos).
- **Resúmenes:** el resumen oficial (`shared_summary`) es de solo lectura para alumnos (`403` al editar); cada alumno tiene su `personal_summary` (`owner_id` = su usuario) que no sobrescribe el oficial ni el de otros.
- **Timestamps:** `app/services/timestamp_service.py` calibra el `evidence_timestamp` con los segmentos de Whisper para dejar 5–10 s de margen previo a la explicación, siempre en formato `HH:MM:SS`; se aplica tras generar el cuestionario.

## Interfaz visual

La interfaz se divide en vistas independientes, servidas sin framework desde `/ui/`:

1. `/ui/auth/`: inicio de sesión y registro con pestañas.
2. `/ui/videos/`: "Mis videos" con búsqueda por título y orden más recientes/antiguos primero. El orden se invierte con un botón (también en el selector de videos del formulario de nuevo tema).
3. `/ui/video/`: pega una URL pública de YouTube, observa el progreso en tiempo real y permite cancelar el trabajo (con confirmación).
4. `/ui/groups/` y `/ui/groups/detail/`: grupos, miembros, temas y calificación por actividad (alumnos calificados/pendientes, desglose de respuestas de intentos, ajuste de notas y comentarios docentes visibles para profesor y alumno).
5. `/ui/resumen/?video=42`: resumen oficial (solo lectura para alumnos) y "Mi resumen personal", con selector de proveedor/modelo.
6. `/ui/quiz/?video=42`: niveles de Bloom, cuestionario oficial o de práctica; el docente alterna con/sin respuestas, el alumno solo ve la versión sin respuestas.
7. `/ui/material/?video=42&material=17`: carga, edita, restaura versiones y exporta un material en PDF, Word, Markdown o JSON.

Las acciones destructivas usan diálogos de confirmación propios y los avisos de éxito/error usan notificaciones tipo toast (`shared.js`).

`video` y `material` se conservan en los query params; por ello los enlaces se pueden recargar o compartir sin depender de variables globales de JavaScript. La interfaz no sustituye ninguna ruta de API: usa los mismos endpoints documentados, incluyendo `POST /api/v1/videos/{video_id}/cancel` para abortar ingestas y SQLite en modo WAL para concurrencia fluida sin bloqueos.

## Pruebas automatizadas

Desde `backend`, con el entorno virtual activo:

```powershell
python -m pytest -q
```

Suites principales: regresión (`tests/services`, `tests/core`, `tests/repositories`, `tests/test_*.py`: 80 pruebas), extremo a extremo con matriz de permisos profesor/alumno (`tests/e2e/`: 100 pruebas) y adversariales (`tests/test_challenger_adversarial.py`: 13 pruebas). En Windows, las que usan `TestClient` pueden requerir ejecutarse fuera de un entorno aislado sin red, por el socket loopback de asyncio.

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
