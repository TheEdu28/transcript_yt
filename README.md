# transcript_yt

Prototipo de tesis de Ingeniería de Software orientado a transformar videos educativos de YouTube en material didáctico estructurado.

## Objetivo
Facilitar el estudio de contenidos audiovisuales mediante la generación de recursos de repaso.

## Resultados generados
- Resúmenes.
- Glosarios.
- Cuestionarios.

### Detalle de recursos implementados
- **Resúmenes:** Sinopsis general concisa y bloques didácticos estructurados con explicaciones detalladas y marcas de tiempo (*timestamps*) verificadas que respaldan la evidencia en el video.
- **Glosarios:** Lista de términos y conceptos clave extraídos del video, acompañados de su definición contextual y el *timestamp* exacto donde se explican en el contenido audiovisual.
- **Cuestionarios:**
  - Preguntas de opción múltiple con 4 alternativas y justificación de respuesta correcta fundamentada en marcas temporales de la transcripción.
  - Preguntas abiertas orientadas a la comprensión y análisis con puntos clave esperados de evaluación.
  - Configuración pedagógica por niveles cognitivos de la Taxonomía de Bloom (*recordar, comprender, aplicar, analizar, evaluar, crear*).
  - Separación funcional entre el cuestionario oficial asignado por el docente y cuestionarios personales de práctica creados por el estudiante.
  - Retroalimentación interactiva inmediata y evaluación asistida por IA para respuestas abiertas.
- **Exportaciones portables:** Generación local de materiales descargables en formatos Markdown (`.md`), PDF (`.pdf`), Microsoft Word (`.docx`) y JSON (`.json`), con opción para exportar solo las preguntas (sin resolver) o las preguntas acompañadas de sus respuestas y pauta de corrección.

## Tecnologías
El pipeline está implementado en **Python 3.11+** e integra las bibliotecas, modelos y servicios utilizados en la solución:

- **Framework Web & API:** FastAPI y Uvicorn para servir la API RESTful asíncrona y la interfaz web integrada (HTML5, CSS3, JavaScript ES Modules nativo).
- **Ingesta y procesamiento multimedia:** `yt-dlp` para la descarga e inspección de videos públicos de YouTube y FFmpeg para la extracción y remuestreo de pistas de audio.
- **Transcripción y segmentación temporal:** `faster-whisper` (Whisper local) para transcripción automática de voz a texto con detección de segmentos e intervalos de tiempo exactos.
- **Embeddings y base de datos vectorial (RAG):** `sentence-transformers` (modelo `paraphrase-multilingual-MiniLM-L12-v2`) para la generación de representaciones vectoriales densas multilingües y `chromadb` local para almacenamiento y búsqueda semántica de fragmentos de texto (*chunks*).
- **Modelos de Lenguaje (LLM):** `google-genai` conectando con la familia de modelos Google Gemini (como `gemini-2.0-flash` y `gemini-2.0-flash-lite`) mediante Google AI Studio como proveedor predeterminado, con adaptadores desacoplados para Groq (`llama-3.1-8b-instant`) y OpenAI (`gpt-4o-mini`).
- **Persistencia relacional y metadatos:** SQLite configurado con modo WAL (`PRAGMA journal_mode=WAL`) y gestionado a través de SQLAlchemy 2.0 para el almacenamiento libre de contención de usuarios, historiales de video, versiones de materiales didácticos, grupos académicos, temas e intentos de evaluación.
- **Autenticación y seguridad:** `python-jose` para emisión y validación de tokens JWT (Bearer) y `passlib` con `bcrypt` para hashing criptográfico de contraseñas y control de acceso basado en roles (docente/administrador vs. estudiante/miembro).
- **Generación documental:** `reportlab` para la maquetación y generación programática de documentos PDF y `python-docx` para la generación estructurada de archivos Microsoft Word.
- **Validación y configuración:** Pydantic v2 y `pydantic-settings` para la estricta validación de contratos de datos JSON y control de variables de entorno mediante `python-dotenv`.
- **Pruebas de software:** Pytest y `httpx` para pruebas unitarias, de integración y verificación de permisos.

## Validación
El sistema ha sido verificado mediante un conjunto integral de pruebas automatizadas y funcionales:

- **Pruebas realizadas:**
  - Suite de pruebas automatizadas con Pytest que abarca **75 casos de prueba** distribuidos en pruebas unitarias de servicios, repositorios, configuración y pruebas de integración de API extremo a extremo.
  - Pruebas de permisos, roles y libro de calificaciones de grupos académicos.
  - Pruebas de exportación multiformato (Markdown, PDF, DOCX y JSON).
  - Pruebas funcionales de interfaz de usuario servida en `/ui/`.

- **Casos evaluados:**
  - *Ingesta, concurrencia y segmentación:* Validación de restricciones de video (máximo 60 minutos, idiomas español e inglés), control de estado de procesamiento mediante semáforo de concurrencia para evitar saturación de CPU por Whisper, cancelación oportuna de trabajos de ingesta y consistencia de marcas de tiempo.
  - *Fragmentación e indexación RAG:* División en trozos (*chunking*) con solapamiento, almacenamiento vectorial y recuperación basada en similitud semántica ordenada cronológicamente.
  - *Generación condicionada (*grounded*):* Verificación de que cada término del glosario, bloque temático y pregunta del cuestionario cite marcas de tiempo existentes en la transcripción recuperada, rechazando alucinaciones o esquemas JSON malformados.
  - *Lógica de evaluación pedagógica:* Corrección determinista de opciones múltiples, calificación cualitativa grounded de respuestas abiertas, cálculo de penalización progresiva por reintentos en exámenes y actualización de promedios en el libro de calificaciones.
  - *Permisos y roles:* Validación de que solo el administrador puede crear o eliminar temas, expulsar miembros o regenerar códigos; aislamiento de cuestionarios personales por usuario; y restricción de autoevaluación para el administrador del grupo.
  - *Exportación selectiva:* Verificación de que la exportación sin soluciones oculte las opciones correctas, explicaciones y puntos esperados, y que la exportación con soluciones los incorpore detalladamente.
  - *Persistencia y concurrencia local:* Verificación de la inicialización de SQLite en modo WAL y timeout de espera para evitar bloqueos durante accesos simultáneos.

- **Resultados obtenidos:**
  - 100% de la suite de pruebas automatizadas ejecutada con éxito (75 pruebas aprobadas).
  - Validación estructurada estable de salidas de LLM mediante esquemas Pydantic.
  - Trazabilidad y anclaje temporal funcional desde la interfaz de preguntas y glosario hacia el reproductor embebido de video.

- **Limitaciones identificadas:**
  - Duración restringida a videos de hasta 60 minutos para asegurar tiempos de transcripción razonables en hardware de consumo.
  - La velocidad de transcripción local depende de las capacidades del equipo anfitrión (CPU frente a aceleración por GPU CUDA).
  - Posible necesidad de suministrar un archivo de cookies Netscape (`cookies.txt`) si YouTube activa bloqueos temporales por peticiones automatizadas en determinados videos.
  - Dependencia de disponibilidad de cuota o conectividad a internet para consultar la API de Google AI Studio / Gemini (mitigado con conmutación visual y programática hacia Groq / Llama).
  - Base de datos local SQLite y ChromaDB optimizadas para ejecución local de prototipo o grupos reducidos, no orientadas a alta concurrencia distribuida en producción.

## Estado
Prototipo validado mediante pruebas, con desarrollo y mejoras pendientes.

- **Alcance completado:**
  - Pipeline integral de ingesta, transcripción local, indexación semántica y generación RAG de resúmenes, glosarios y cuestionarios.
  - Control de concurrencia y serialización de ingestas locales mediante semáforo para mitigar saturación de CPU por Whisper.
  - Botón de cancelación de ingesta en progreso con liberación oportuna de recursos y limpieza de audios temporales.
  - Clasificación de preguntas según niveles de la taxonomía de Bloom y retroalimentación interactiva con penalización por reintentos.
  - Gestión de grupos de estudio, administración de temas con formularios y confirmaciones emergentes (*pop-ups*), y separación entre cuestionarios del profesor y de práctica del estudiante.
  - Selector visual interactivo de modelos con distintivo del proveedor activo e indicador de cuota para conmutar sin fricción entre Google Gemini y Groq Cloud (Llama 3.1).
  - Exportación local multiformato y visor web integrado sin dependencias de frameworks externos pesados.

- **Mejoras pendientes:**
  - Soporte para videos de duración extendida mediante segmentación jerárquica de temas.
  - Incorporación de rúbricas docentes personalizables para la evaluación automática de respuestas abiertas.
  - Soporte para ingesta de material didáctico complementario en formato PDF o diapositivas.
  - Transición hacia bases de datos relacionales cliente-servidor (ej. PostgreSQL + pgvector) y colas distribuidas (Celery + Redis) para entornos multiusuario a escala.

## Ejecución
Para reproducir la ejecución del prototipo en un entorno local, siga los siguientes requisitos y pasos:

### Requisitos previos
- Sistema operativo Windows 10/11, Linux o macOS.
- **Python 3.11** o superior instalado.
- **FFmpeg** instalado y registrado en la variable de entorno `PATH` (verificable con `ffmpeg -version`).
- Clave de API de Google AI Studio ([Google Gemini](https://aistudio.google.com/)).

### Configuración del entorno
1. Clonar el repositorio y ubicarse en la raíz del proyecto.
2. Crear el archivo de variables de entorno `.env` a partir de la plantilla:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Editar el archivo `.env` y configurar las claves requeridas:
   ```ini
   ACTIVE_MODEL_PROVIDER=gemini
   GEMINI_API_KEY=tu_clave_de_google_ai_studio
   JWT_SECRET_KEY=clave_secreta_aleatoria_para_tokens
   ```

### Pasos para reproducir la ejecución
1. **Crear y activar el entorno virtual:**
   ```powershell
   python -m venv backend\.venv
   .\backend\.venv\Scripts\Activate.ps1
   ```
2. **Instalar dependencias:**
   ```powershell
   pip install -r backend\requirements.txt
   ```
3. **Iniciar el servidor de backend y la interfaz web:**
   ```powershell
   cd backend
   uvicorn app.main:app --reload
   ```
4. **Acceder al sistema:**
   - Interfaz web interactiva: `http://127.0.0.1:8000/ui/`
   - Documentación OpenAPI interactiva: `http://127.0.0.1:8000/docs`

### Ejecución de pruebas automatizadas
Con el entorno virtual activo, ejecute la suite de pruebas desde la carpeta `backend`:
```powershell
pytest
```
