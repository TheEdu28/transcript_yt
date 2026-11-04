# Project: transcript_yt

## Architecture
- **Backend**: FastAPI with SQLAlchemy 2.0 ORM, SQLite database (with WAL mode), Pydantic schemas, and JWT bearer authentication (`HS256`).
- **Frontend**: Vanilla ES6 modules mounted at `/ui/` using native browser DOM APIs and CSS3 variables (no external bundler).
- **Domain Services**:
  - `group_service.py`: Group membership, topics, attempts, grades, and topic material resolution.
  - `material_service.py`: Didactic materials (quizzes, summaries), version history, and permission checks.
  - `video_repository.py` & `routes.py`: Video ingestion, status tracking, search, and sorting.
  - `export_service.py`: Exporting materials to Markdown, JSON, PDF, and DOCX.
  - `pipeline.py`: RAG question generation and evidence grounding.
  - `timestamp_service.py` (new): Segment-aware timestamp calibration with 5-10s context lead-in.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Activity-Centric Grading View | Teacher accesses an activity directly to see submitted vs pending students, inspect individual attempts and answers, and grade inline without depending on the global gradebook. | M1 | Survey (R1) |
| 2 | Individual Attempt Separation & Querying | Each student views only their own attempts; teacher queries attempts per individual student without cross-student data leakage; strict user-activity-quiz relational constraints. | M1 | Survey (R2) |
| 3 | Video Selection, Sorting & Text Search | Videos listed newest to oldest by real date by default; toggle newest/oldest first; real-time title search operating jointly without data loss; applied in `/ui/videos/` and Topic Video Picker. | M2 | Survey (R3) |
| 4 | Role-Based Quiz Views & Answer Masking | Teacher has visual toggle for quiz with/without answers; student restricted strictly to without-answers view and export; backend endpoints (`/materials/{id}`, `/{group_id}/topics/{id}/materials`, `/materials/{id}/export`) strip correct answers and explanations for students. | M3 | Survey (R4) |
| 5 | Teacher vs Student Summary Isolation | Official teacher summary is immutable and non-overwritable by students; student has an independent personal summary space per topic; teachers can distinguish official vs personal summaries; fixes `shared_summary` and `can_edit` permissions. | M4 | Survey (R5) |
| 6 | Timestamp Calibration (5–10s Lead-In) | Calibrates question evidence timestamps to start 5–10 seconds before topic explanation begins, grounded in Whisper transcript segment boundaries and context rather than arbitrary uniform subtractions. | M5 | Survey (R6) |
| 7 | Opaque-Box E2E Test Suite | Automated test suite in `backend/tests/` covering Tiers 1-4 (features, boundaries, combinations, real-world) and role permission matrix (Profesor vs Alumno), publishing `TEST_READY.md`. | E2E Track | Survey (R7) |
| 8 | Final Verification, E2E Pass & Technical Report | 100% E2E test pass, adversarial test hardening (Tier 5), and comprehensive technical report covering the 8 required points. | M6 | Survey (R7) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Suite Track | Comprehensive opaque-box test suite for R1–R6, permission matrix, and publish `TEST_READY.md` | none | PLANNED |
| M1 | Calificaciones e Intentos por Actividad | Backend per-student attempt query, evaluation status, and frontend activity grading view in `groups/detail/` (R1 & R2) | none | PLANNED |
| M2 | Selección, Ordenamiento y Búsqueda de Videos | Video query search and sort parameters in backend & frontend `/ui/videos/` and topic video picker (R3) | none | PLANNED |
| M3 | Cuestionarios y Permisos de Respuestas | Mask quiz answers in API & export for students; teacher con/sin respuestas toggle in `/ui/quiz/` (R4) | none | PLANNED |
| M4 | Separación de Resúmenes Profesor y Alumno | Fix `shared_summary`, student personal summary space, fix `can_edit` permission check (R5) | none | PLANNED |
| M5 | Calibración y Corrección de Timestamps | Segment-aware timestamp calibration algorithm with 5–10s lead-in, transcript alignment, and seek integration (R6) | none | PLANNED |
| M6 | Final Milestone: E2E Pass & Technical Report | Verify 100% E2E test pass, adversarial coverage hardening, and compile complete technical report (R7) | M1, M2, M3, M4, M5, E2E | PLANNED |

## Interface Contracts
### M1: Activity Grading & Attempts
- `GET /api/v1/groups/{group_id}/topics/{topic_id}/summary`:
  - Returns `TopicSummaryResponse` with `members_summary`: includes `status: "evaluated" | "pending" | "not_submitted"`, `student_name`, `email`, `attempt_count`, `latest_score`, `final_score`.
- `GET /api/v1/groups/{group_id}/topics/{topic_id}/members/{user_id}/attempts` (or `?user_id={id}` on `/attempts`):
  - Accessible to teacher (group admin). Returns list of attempts for that specific student with `attempt_number`, `answers_json`, `raw_score`, `final_score`, `submitted_at`.
- `PATCH /api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}`:
  - Teacher modifies `final_score` and `review_notes`. Updates status to "evaluated".

### M2: Video Search & Ordering
- `GET /api/v1/videos?search={text}&order={desc|asc}&page={page}&page_size={size}`:
  - Filters by `title.ilike(f"%{search}%")`. Orders by `Video.created_at.desc()` (default) or `asc`.
  - Frontend forwards debounced search input and order select box.

### M3: Quiz Roles & Answer Masking
- `mask_quiz_answers(content: dict) -> dict`:
  - Strips `correct_option` and `explanation` from `multiple_choice`, and `expected_points` from `open_questions`.
- `GET /api/v1/groups/{group_id}/topics/{topic_id}/materials`:
  - For students (`current_user.id != group.admin_id`): `shared_quiz.content` has masked answers.
- `GET /api/v1/materials/{material_id}/export?include_answers={bool}`:
  - If `include_answers=True`, caller MUST be group admin or video owner. If student, returns HTTP 403 or forces `include_answers=False`.
- Frontend `/ui/quiz/`:
  - Teacher: visual toggle between "Con respuestas" and "Sin respuestas" controlling view and export.
  - Student: only "Sin respuestas", export dropdown hidden or restricted.

### M4: Teacher vs Student Summaries
- `GET /api/v1/groups/{group_id}/topics/{topic_id}/materials`:
  - Returns `shared_summary` (official teacher summary) and `personal_summary` (student's own summary for this topic/video).
- `can_edit`:
  - Allows editing if `material.owner_id == user_id` (personal materials).
  - Blocks students from editing teacher's official summary (`shared_summary`).
- Frontend `/ui/resumen/`:
  - Tab 1: "Resumen oficial" (read-only for students; generate/overwrite buttons hidden).
  - Tab 2: "Mi resumen personal" (student can generate and edit personal summary).

### M5: Timestamp Calibration
- `TimestampCalibrationService.calibrate(transcript_segments, topic_start_time, topic_text) -> float`:
  - Finds relevant topic segment $k$.
  - Walks back to preceding segment boundary $k-1$ or $k-2$ to provide a 5.0s to 10.0s lead-in margin without mid-sentence clipping.
  - If preceding boundary is not within range, dynamically selects lead-in based on segment boundaries and pauses.
  - Clamps at 0.0s.

## Code Layout
- Backend Source: `backend/app/`
  - Routes: `backend/app/api/` (`routes.py`, `routes_groups.py`, `dependencies_auth.py`)
  - Services: `backend/app/services/` (`group_service.py`, `material_service.py`, `export_service.py`, `timestamp_service.py`)
  - Repositories: `backend/app/repositories/` (`group_repository.py`, `video_repository.py`, `material_repository.py`)
  - Models: `backend/app/models/` (`group.py`, `video.py`, `material.py`, `user.py`)
  - Schemas: `backend/app/schemas/` (`contracts.py`)
- Frontend Source: `backend/app/web/`
  - Group Detail: `backend/app/web/groups/detail/` (`index.html`, `page.js`)
  - Videos: `backend/app/web/videos/` (`index.html`, `page.js`)
  - Quiz: `backend/app/web/quiz/` (`index.html`, `page.js`)
  - Resumen: `backend/app/web/resumen/` (`index.html`, `page.js`)
  - Shared: `backend/app/web/api.js`, `backend/app/web/shared.js`, `backend/app/web/styles.css`
- Tests: `backend/tests/`
  - Unit/Service tests: `backend/tests/services/`, `backend/tests/repositories/`
  - Permission/E2E tests: `backend/tests/test_group_permissions.py`, `backend/tests/test_web_interface.py`, new `backend/tests/e2e/`
