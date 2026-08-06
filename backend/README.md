# Backend: pipeline RAG local

## Ejecutar

Desde backend:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    Copy-Item .env.example ..\.env
    uvicorn app.main:app --reload

- POST /api/v1/videos/ingest: valida URL pública de YouTube, idioma es/en y duración <=60 min; extrae audio, transcribe con faster-whisper, fragmenta, vectoriza e indexa en ../data/chroma_db.
- POST /api/v1/materials/summary: recuperación ChromaDB + Gemini con salida grounded.
- POST /api/v1/materials/quiz: cuestionario sustentado por evidencia temporal.

La primera transcripción descarga el modelo Whisper y la primera indexación descarga el modelo all-MiniLM-L6-v2. Esas descargas y el rendimiento de Whisper dependen del equipo. El límite de contexto de Gemini (MAX_GEMINI_CONTEXT_CHARS=12000) reduce el consumo de la capa gratuita.

