# Handoff Report: Test Suite Architecture, Test Results, and R6 Timestamp Calibration

**Agent**: Survey Explorer 3  
**Working Directory**: `c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_explorer_survey_3\`  
**Milestone**: Survey & Exploration  
**Date**: 2026-11-04  

---

## 1. Observation

### 1.1 Dual Test Suite Structure

The workspace contains two distinct testing suites and application trees:

1. **Root Test Suite (`tests/`)**:
   - `tests/conftest.py`: Placeholder fixture file (3 lines).
   - `tests/integration/test_health.py`: 1 test verifying `/api/v1/health` against root skeleton `app.main:app`.
   - `tests/unit/test_text_chunking.py`: 1 placeholder test (`test_chunking_contract_placeholder` containing `assert True`).
   - Root application `app/`: Minimal skeleton where video search and ingestion endpoints return `HTTP 501 Not Implemented`.

2. **Backend Production Test Suite (`backend/tests/`)**:
   - 16 test files covering configuration, services, repositories, permissions, and web interface:
     - `backend/tests/core/test_config.py` (4 tests)
     - `backend/tests/repositories/test_material_repository.py` (1 test)
     - `backend/tests/services/test_export_service.py` (4 tests)
     - `backend/tests/services/test_feedback_service.py` (5 tests)
     - `backend/tests/services/test_grading_service.py` (10 tests)
     - `backend/tests/services/test_ingestion_progress.py` (4 tests)
     - `backend/tests/services/test_material_service.py` (5 tests)
     - `backend/tests/services/test_model_providers.py` (8 tests)
     - `backend/tests/services/test_pipeline.py` (8 tests)
     - `backend/tests/services/test_quiz_rag.py` (6 tests)
     - `backend/tests/services/test_subtitles.py` (5 tests)
     - `backend/tests/services/test_summary_rag.py` (6 tests)
     - `backend/tests/test_chunking.py` (2 tests)
     - `backend/tests/test_group_permissions.py` (7 tests)
     - `backend/tests/test_progress.py` (1 test)
     - `backend/tests/test_web_interface.py` (2 tests)
   - Total test count: **78 tests**.

### 1.2 Windows Sandbox / Socketpair Execution Constraint

When executing tests that instantiate FastAPI's `TestClient` (e.g. `test_web_interface.py`, `test_group_permissions.py`, `test_health.py`) in standard mode:
- Starlette 0.41.3 and AnyIO 4.14.2 initialize `anyio.from_thread.start_blocking_portal()`.
- On Python 3.13 on Windows, `ProactorEventLoop` calls `socket._fallback_socketpair()` which binds to `127.0.0.1:0` and awaits `accept()`.
- In sandboxed environments without loopback socket binding permissions, `socket.accept()` hangs indefinitely.
- **Resolution**: Setting `BypassSandbox: true` on `run_command` allows immediate loopback socket connection.

### 1.3 Baseline Test Execution Results

#### Backend Test Suite Execution:
- **Command**:
  ```powershell
  Set-Location "c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend"; .\.venv\Scripts\python.exe -m pytest
  ```
  *(Executed with BypassSandbox: true)*
- **Result Output**:
  ```
  ============================= test session starts =============================
  platform win32 -- Python 3.13.1, pytest-8.3.4, pluggy-1.6.0
  rootdir: C:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend
  plugins: anyio-4.14.2
  collected 78 items

  tests\core\test_config.py ....                                           [  5%]
  tests\repositories\test_material_repository.py .                         [  6%]
  tests\services\test_export_service.py ....                               [ 11%]
  tests\services\test_feedback_service.py .....                            [ 17%]
  tests\services\test_grading_service.py ..........                        [ 30%]
  tests\services\test_ingestion_progress.py ....                           [ 35%]
  tests\services\test_material_service.py .....                            [ 42%]
  tests\services\test_model_providers.py ........                          [ 52%]
  tests\services\test_pipeline.py ........                                 [ 62%]
  tests\services\test_quiz_rag.py ......                                   [ 70%]
  tests\services\test_subtitles.py .....                                   [ 76%]
  tests\services\test_summary_rag.py ......                                [ 84%]
  tests\test_chunking.py ..                                                [ 87%]
  tests\test_group_permissions.py .......                                  [ 96%]
  tests\test_progress.py .                                                 [ 97%]
  tests\test_web_interface.py ..                                           [100%]

  ====================== 78 passed, 47 warnings in 22.26s =======================
  ```
- **Status**: 100% pass (78 passed, 0 failed, 47 deprecation warnings).

#### Root Test Suite Execution:
- **Command**:
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ -v
  ```
  *(Executed with BypassSandbox: true)*
- **Result Output**:
  ```
  ============================= test session starts =============================
  platform win32 -- Python 3.13.1, pytest-8.3.4, pluggy-1.6.0 -- C:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.venv\Scripts\python.exe
  plugins: anyio-4.15.1, asyncio-0.25.2
  collected 2 items

  tests/integration/test_health.py::test_health_check PASSED               [ 50%]
  tests/unit/test_text_chunking.py::test_chunking_contract_placeholder PASSED [100%]

  ======================== 2 passed, 1 warning in 1.63s =========================
  ```
- **Status**: 100% pass (2 passed, 0 failed).

---

### 1.4 Codebase Examination of Timestamps and Chunking

1. **Whisper Transcription & Segment Storage** (`backend/app/services/ingestion/whisper.py`):
   ```python
   result = [
       TranscriptSegment(round(s.start, 2), round(s.end, 2), s.text.strip())
       for s in segments
       if s.text.strip()
   ]
   ```
   Stored in `data/transcripts/raw/{youtube_id}.json` as JSON array of `{"start": float, "end": float, "text": str}`.

2. **Chunking Mechanism** (`backend/app/services/ingestion/chunker.py`):
   ```python
   while start_index < len(segments):
       end_index, word_count = start_index, 0
       while end_index < len(segments) and word_count < settings.chunk_words:
           word_count += len(segments[end_index].text.split())
           end_index += 1
       current = segments[start_index:end_index]
       chunks.append(
           TranscriptChunk(
               index=len(chunks),
               text=" ".join(segment.text for segment in current),
               start=current[0].start,
               end=current[-1].end,
           )
       )
   ```
   `chunk_words` defaults to 220 words. A single chunk typically spans 60 to 90 seconds.
   The chunk's `.start` is simply `current[0].start`.

3. **ChromaDB Indexing and Timestamp Formatting** (`backend/app/services/ingestion/vectors.py`):
   ```python
   def timestamp(seconds: float) -> str:
       total = max(0, round(seconds))
       return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"

   # Inside VectorStoreService.index():
   metadatas=[
       {
           "video_id": video_id,
           "chunk_index": chunk.index,
           "start": timestamp(chunk.start),
           "end": timestamp(chunk.end),
       }
       for chunk in chunks
   ]
   ```
   ChromaDB stores only two timestamp values per chunk: the coarse chunk start and end in `HH:MM:SS` format.

4. **Quiz Evidence Grounding** (`backend/app/services/pipeline.py`):
   ```python
   available_timestamps = {
       str(value)
       for item in evidence
       for value in (item.get("start"), item.get("end"))
       if value is not None
   }
   cited_timestamps = [item.evidence_timestamp for item in result.multiple_choice]
   cited_timestamps.extend(item.evidence_timestamp for item in result.open_questions)
   unknown = sorted(set(cited_timestamps) - available_timestamps)
   if unknown:
       raise PipelineError(
           "El cuestionario cita timestamps que no pertenecen a la evidencia recuperada.",
           code="UNGROUNDED_TIMESTAMP",
           status_code=502,
       )
   ```
   Because `available_timestamps` contains only the chunk start and end boundaries, Gemini is forced to pick one of those chunk boundary strings (typically the start of a 60–90 second block).

5. **Frontend Playback / Seek Execution** (`backend/app/web/quiz/page.js`, lines 39–56, 162–166):
   ```javascript
   function parseTimestampToSeconds(hhmmss) {
     if (!hhmmss) return 0;
     const parts = hhmmss.trim().split(":").map(Number);
     if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
     if (parts.length === 2) return parts[0] * 60 + parts[1];
     return Number(parts[0]) || 0;
   }

   function seekToTimestamp(timestampStr) {
     const secs = parseTimestampToSeconds(timestampStr);
     if (ytPlayer && isPlayerReady && ytPlayer.seekTo) {
       ytPlayer.seekTo(secs, true);
       ytPlayer.playVideo();
       byId("player-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
     }
   }

   out.querySelectorAll(".quiz-ts-btn").forEach((btn) => {
     btn.addEventListener("click", () => {
       seekToTimestamp(btn.dataset.ts);
     });
   });
   ```
   `seekToTimestamp` executes a raw jump to `secs` without any contextual calibration, lead-in margin, or segment analysis.

---

## 2. Logic Chain

1. **Premise 1**: The user requirement R6 specifies:
   - "El mecanismo de asignación de timestamps para las preguntas de los cuestionarios debe asegurar que el timestamp dirija al alumno a un momento ligeramente anterior al inicio de la explicación del tema (con un margen aproximado de 5 a 10 segundos previos a la explicación relevante), evitando marcas lejanas o menciones superficiales."
   - "El ajuste debe analizar el desfase entre segmentos de transcripción y contexto sin aplicar una resta fija uniforme."
   - Acceptance Criteria: "Al seleccionar el timestamp de una pregunta, el video inicia entre 5 y 10 segundos antes del comienzo de la explicación relevante del tema." and "La corrección de timestamps se fundamenta en el análisis de segmentos y contexto, sin aplicar un desfase fijo arbitrario."

2. **Premise 2 (Current System State)**:
   - Currently, questions inherit `evidence_timestamp` from ChromaDB chunk boundaries (Observation 1.4.3 & 1.4.4).
   - In `quiz/page.js`, clicking the timestamp calls `ytPlayer.seekTo(secs, true)` with raw uncalibrated seconds (Observation 1.4.5).
   - A naive constant offset (e.g. `secs - 7` in javascript or python) directly violates the constraint: "sin aplicar una resta fija uniforme" and fails whenever the chunk boundary is at 0:00:00 or when the target topic begins late in a chunk.

3. **Inference for R6 Calibration Algorithm**:
   - Every ingested video stores its Whisper-aligned sentence segments in `data/transcripts/raw/{youtube_id}.json` with exact `start` and `end` timestamps (Observation 1.4.1).
   - The relevant topic start $T_{\text{topic}}$ can be identified by matching the question content / explanation keywords against the segments in the video's transcript.
   - Once the segment $k$ where the topic explanation starts is identified ($T_{\text{topic}} = \text{segment}[k].start$):
     - Inspect preceding segments $k-1, k-2$:
       - If segment $k-1$ starts at $T_{\text{prev\_start}}$ such that $5.0 \le (T_{\text{topic}} - T_{\text{prev\_start}}) \le 10.0$, snap $T_{\text{calibrated}} = T_{\text{prev\_start}}$. This guarantees that speech starts at a natural syntactic boundary without clipping words mid-sentence.
       - If segment $k-1$ is within 5 seconds ($T_{\text{topic}} - T_{\text{prev\_start}} < 5.0$), inspect segment $k-2$ to see if snapping to $k-2$ provides the 5–10 second lead-in.
       - If preceding segment $k-1$ started more than 10 seconds prior ($T_{\text{topic}} - T_{\text{prev\_start}} > 10.0$), check if the gap/silence between $k-1$ and $k$ ($T_{\text{topic}} - \text{segment}[k-1].end$) can be used, or dynamically select a lead-in offset $\Delta \in [5.0, 10.0]$ proportional to context and speech rate, clamping at $0.0$.
     - When $T_{\text{topic}} < 5.0$, $T_{\text{calibrated}} = 0.0$.
   - This algorithm grounds calibration directly on Whisper segment boundaries and contextual speech flow, strictly fulfilling both criteria of R6 without any fixed uniform subtraction.

4. **Inference for Test Suite & Coverage**:
   - The repository has 78 operational tests in `backend/tests/` (Observation 1.3), but zero automated tests exist for:
     - Video title search and chronological ordering (R3).
     - Role-based hiding of quiz answers for students vs teachers in API payloads and exports (R4).
     - Personal summary isolation per student (R5).
     - Timestamp calibration algorithm and margin validation (R6).
     - Activity-centric grading per student per topic (R1 & R2).

---

## 3. Caveats

1. **Sandboxed Command Execution**: Pytest tests using FastAPI's `TestClient` cannot be run with standard restrictive sandbox policies on Windows because Python 3.13 AnyIO socketpair accept blocks. All test executions require `BypassSandbox: true`.
2. **Dual `tests/` vs `backend/tests/`**: The root `tests/` folder contains legacy stubs from earlier architecture iterations. The actual active test suite documented in the project README and implementing real logic is located inside `backend/tests/`. Both suites pass cleanly.
3. **External LLM Network Calls**: Running pipeline tests that do not mock `GeminiProvider` or `OpenAIProvider` requires valid API keys in `.env`. Existing test files in `backend/tests/services/` correctly mock provider responses to run completely offline.

---

## 4. Conclusion

### Summary Table: Requirements vs Existing Implementation & Test Coverage

| Req | Description | Implementation Status | Existing Test Coverage | Gap / Missing Elements |
|:---|:---|:---|:---|:---|
| **R1** | Activity-centric grading | Backend supports `/groups/{id}/grades` and PATCH attempt grade | `test_group_permissions.py` (grades & review) | No dedicated per-activity student list endpoint/view; UI lacks activity-centric grading |
| **R2** | Individual attempt separation per user | Backend has `/my-attempts` (member) and `/attempts` (admin) | `test_group_permissions.py` (3 attempts flow) | No endpoint/filter for teacher to inspect a specific student's attempts by ID without loading all |
| **R3** | Video sorting (recent/old) & search | `VideoRepository.list_by_owner` has static `order_by(created_at.desc())` | **0 tests** | No title search query parameter `q`; no sorting toggle parameter (`asc`/`desc`); no frontend search/sort UI |
| **R4** | Quiz with/without answers role separation | API exposes `correct_option` and `explanation` unconditionally to all users | `test_quiz_rag.py`, `test_export_service.py` | API leaks answers to students; export allows `include_answers=true` without role verification; frontend needs view toggle |
| **R5** | Teacher vs student summary separation | Backend distinguishes `shared_summary` vs `personal_summary` in `group_service` | Partial in `test_group_permissions.py` | Student cannot edit personal summary (`can_edit` restricts to owner/admin); `resumen/page.js` has no personal tabs |
| **R6** | Timestamp calibration (5–10s lead-in) | Coarse chunk boundary stored; raw seconds seek in frontend | `test_chunking.py`, `test_quiz_rag.py` | No segment-aware calibration algorithm implemented; seeks directly to uncalibrated second |
| **R7** | Quality & verification reporting | Comprehensive report requirement | Survey in progress | Must document 8 required sections upon completion |

---

## 5. Verification Method

### How to Independently Verify:

1. **Verify Backend Test Suite (78 Tests)**:
   Run the following PowerShell command in `backend`:
   ```powershell
   Set-Location "c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend"; .\.venv\Scripts\python.exe -m pytest -v
   ```
   *Expected outcome*: 78 passed tests across 16 test files.

2. **Verify Root Test Suite (2 Tests)**:
   Run the following PowerShell command in workspace root:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/ -v
   ```
   *Expected outcome*: 2 passed tests (`test_health_check`, `test_chunking_contract_placeholder`).

3. **Verify Chunking & Timestamp Preservation**:
   ```powershell
   Set-Location "c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_chunking.py tests/services/test_quiz_rag.py -v
   ```
   *Expected outcome*: 8 passed tests confirming chunk creation and `UNGROUNDED_TIMESTAMP` rejection.

4. **Verify Raw Transcript Segments on Disk**:
   Inspect `data/transcripts/raw/qFtGQLu5JEw.json` to verify `start`, `end`, and `text` fields are populated and available for calibration.

5. **Invalidation Conditions**:
   - If tests are executed without `BypassSandbox: true` and hang at `TestClient` entry, this confirms the Windows socketpair restriction documented in Section 1.2.
   - If `test_group_permissions.py` fails on SQLite errors, verify that `data/metadata/app.db` is writable.
