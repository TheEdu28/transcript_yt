# Progress Heartbeat

Last visited: 2026-11-04T05:01:45Z
Status: Complete (All M1-M5 Milestones Implemented & Verified)
Current Step: Compiling comprehensive handoff report

## Milestone Tracking
- [x] Baseline verification (confirm existing 78 tests pass)
- [x] M1: Calificaciones e Intentos por Actividad (R1 & R2)
  - Backend: Added user_id query filter & dedicated endpoint `GET /{group_id}/topics/{topic_id}/members/{user_id}/attempts`, enriched `MemberTopicSummary` with `status: Literal["evaluated", "pending", "not_submitted"]` and `final_score`.
  - Frontend: Added Activity Grading view and modal in `groups/detail/` with statistics overview, student table with status badges, and inspection panel with attempt breakdown & inline grading form.
- [x] M2: Selección, Ordenamiento y Búsqueda de Videos (R3)
  - Backend: Added `search: str | None = Query(None)` and `order: str = Query("desc")` to `GET /api/v1/videos` in `routes.py`; updated `VideoRepository.list_by_owner` to filter `Video.title.ilike(...)` and order by `Video.created_at.desc()` / `asc`.
  - Frontend: Added title search input with 250ms debounce and sort order selector dropdown ("Más recientes primero" / "Más antiguos primero") in `/ui/videos/` and in Topic creation video picker in `/ui/groups/detail/`. Updated `apiListMyVideos` in `api.js`.
- [x] M3: Cuestionarios y Permisos de Respuestas (R4)
  - Backend: Added `mask_quiz_answers()` helper in `material_service.py` stripping `correct_option`, `explanation`, and `expected_points`. Masked shared quiz in `GET /{group_id}/topics/{topic_id}/materials` and `GET /materials/{id}` for students. Enforced 403 Forbidden for non-privileged users when `include_answers=True` in `GET /materials/{id}/export`.
  - Frontend: In `/ui/quiz/`, added visual toggle selector between "Versión con respuestas" and "Versión sin respuestas" for teachers, connected to preview and export. For students, hid toggle and export mode selector, locking export to questions only.
- [x] M4: Separación de Resúmenes Profesor y Alumno (R5)
  - Backend: Fixed `material_service.py:can_edit` to permit students to edit materials where `material.owner_id == user_id`, while strictly forbidding non-teachers from modifying official summaries (`shared_summary`).
  - Frontend: In `/ui/resumen/`, fixed `topicMats?.summary` -> `shared_summary` bug. Added tab navigation between "Resumen oficial del docente" (read-only for students, generate button hidden) and "Mi resumen personal" (allows generating and editing student's own summary).
- [x] M5: Calibración y Corrección de Timestamps (R6)
  - Backend: Implemented `TimestampCalibrationService` in `backend/app/services/timestamp_service.py` with 5.0s to 10.0s lead-in margin aligned to Whisper segment boundaries (`data/transcripts/raw/{id}.json`), clamping at 0.0s near start, and avoiding fixed uniform subtraction. Integrated into `PipelineService.quiz` and player timestamp seeking.
- [x] Regression testing & comprehensive test verification
  - 161 of 161 tests passing (100% pass rate, 0 failures, 0 regressions across all suites).
- [x] Final handoff report compilation
