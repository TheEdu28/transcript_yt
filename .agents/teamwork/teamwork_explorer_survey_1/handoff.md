# Handoff Report: Survey Explorer 1 (Backend Architecture, Data Models & APIs)

## 1. Observation

Direct observations from examining the codebase at `c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend`:

### A. Codebase Root and Active Backend
- The actual running backend application and test suite reside inside `backend/` (`backend/app/` and `backend/tests/`).
- The root `app/` and root `tests/` are a minimal skeleton from an earlier revision; running pytest from root without specifying `backend/` causes `ModuleNotFoundError: No module named 'app'`.
- Running tests requires executing inside `backend` with the active virtual environment (`backend\.venv\Scripts\python.exe -m pytest`). When running from `backend`, 70+ unit and service tests pass cleanly (`test_config.py`, `test_material_repository.py`, `test_export_service.py`, `test_feedback_service.py`, `test_grading_service.py`, `test_ingestion_progress.py`, `test_material_service.py`, `test_model_providers.py`, `test_pipeline.py`, `test_quiz_rag.py`, `test_subtitles.py`, `test_summary_rag.py`, `test_chunking.py`).

### B. Database Models and Schema (`backend/app/models/` and `backend/app/main.py`)
1. **User Identity** (`backend/app/models/user.py`, lines 11-21):
   - Table `users`: `id`, `nombre`, `email`, `password_hash`, `created_at`.
   - Users do not possess a global role column; permissions are strictly contextual per group (`admin_id` vs `group_memberships`).
2. **Groups & Memberships** (`backend/app/models/group.py`, lines 11-42):
   - Table `groups`: `id`, `name`, `admin_id` (FK `users.id`), `code` (6-char alphanumeric), `created_at`.
   - Table `group_memberships`: `id`, `group_id`, `user_id`, `joined_at`, with `UniqueConstraint("group_id", "user_id")`.
   - Creator is `admin_id` (Teacher/Docente). Members in `group_memberships` are Students/Alumnos.
3. **Activities / Topics** (`backend/app/models/group.py`, lines 48-68):
   - Table `topics`: `id`, `group_id`, `video_id`, `material_id` (FK to quiz), `title`, `description`, `is_published`, `created_by`, `created_at`, `is_active`.
   - `Topic` stores a direct reference to a quiz (`material_id`), but contains NO column for `summary_id`.
4. **Attempts & Grades** (`backend/app/models/group.py`, lines 70-85):
   - Table `attempts`: `id`, `topic_id`, `user_id`, `attempt_number`, `raw_score`, `final_score`, `answers_json`, `submitted_at`.
   - No explicit column for `review_notes` or `status` (`evaluated` vs `pending`).
5. **Materials & Versions** (`backend/app/models/material.py`, lines 11-39):
   - Table `didactic_materials`: `id`, `video_id`, `material_type` ("summary" | "quiz"), `content_json`, `owner_id` (FK `users.id`).
   - Table `material_versions`: `id`, `material_id`, `content_json`, `edited_by`, `edited_at`.
   - Note: `DidacticMaterial` has NO `topic_id` column.
6. **Videos** (`backend/app/models/video.py`, lines 11-28):
   - Table `videos`: `id`, `youtube_id`, `source_url`, `title`, `language`, `duration_seconds`, `transcript_path`, `status`, `progress_stage`, `progress_percent`, `processing_seconds`, `owner_id`, `created_at`.
   - Stores `created_at` (registration timestamp). Does NOT persist YouTube publication date (`upload_date`).
7. **Schema Migrations** (`backend/app/main.py`, lines 24-67):
   - `initialise_local_metadata()` inspects SQLite `PRAGMA table_info` and applies dynamic `ALTER TABLE` statements at application startup.

### C. Authentication & Authorization (`backend/app/api/dependencies_auth.py` and `routes_auth.py`)
- `require_group_admin` (`dependencies_auth.py:12`): verifies `group.admin_id == current_user.id`; raises HTTP 403 `FORBIDDEN_NOT_GROUP_ADMIN` otherwise.
- `require_group_member` (`dependencies_auth.py:42`): allows if `group.admin_id == current_user.id` or user has a record in `group_memberships`; raises HTTP 403 `FORBIDDEN_NOT_GROUP_MEMBER` otherwise.
- Auth tokens are JWT Bearer tokens signed with `jwt_secret_key` and algorithm `HS256` (`auth_service.py:67-72`).

### D. R1 Findings: Activity-Centric Grading (`backend/app/api/routes_groups.py`, `group_service.py`, `group_repository.py`)
- Endpoint `GET /api/v1/groups/{group_id}/topics/{topic_id}/summary` (`routes_groups.py:304`):
  - Accessible only to group admin (`require_group_admin`).
  - Returns `TopicSummaryResponse` with `members_summary: list[MemberTopicSummary]`.
  - In `group_service.py:508-537`, it computes `best_attempt` and `latest_attempt`, but omits `answers_json` and intermediate attempts.
  - Does NOT provide a status badge ("evaluated" vs "pending") directly in `MemberTopicSummary` (that status only exists in `GroupGradesResponse` in `get_group_grades`, lines 435, 460).
- Endpoint `GET /api/v1/groups/{group_id}/topics/{topic_id}/attempts` (`routes_groups.py:288`):
  - Returns ALL attempts of ALL users for `topic_id` in a single flat list (`list[AdminAttemptResponse]`).
  - Does NOT accept a `user_id` query filter, forcing any caller to download all students' attempts.
- Endpoint `PATCH /api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}` (`routes_groups.py:330`):
  - Allows admin to update `final_score` and `review_notes`.
  - In `group_repository.py:223-237`, `review_notes` is serialized inside `answers_json` (`data["review_notes"] = review_notes`).

### E. R2 Findings: Attempt Tracking per User (`backend/app/api/routes_groups.py`, `group_repository.py`)
- In `group_repository.py`:
  - `count_user_attempts(session, topic_id, user_id)` (lines 169-177): strictly queries `Attempt.topic_id == topic_id, Attempt.user_id == user_id`.
  - `list_user_attempts(session, topic_id, user_id)` (lines 202-209): strictly queries `Attempt.topic_id == topic_id, Attempt.user_id == user_id`.
  - `save_attempt(...)` (lines 179-200): associates `attempt_number = previous_attempts_count + 1`, `topic_id`, and `user_id`.
- In `routes_groups.py`:
  - `GET /{group_id}/topics/{topic_id}/my-attempts` (line 271): Member sees only their own attempts.
  - However, there is NO endpoint for a teacher to request only the attempts of student X (`user_id`). The teacher must either call `GET /{group_id}/topics/{topic_id}/attempts` (which dumps all students' attempts together) or `GET /{group_id}/grades`.

### F. R3 Findings: Video Listing, Sorting, and Search (`backend/app/api/routes.py`, `video_repository.py`)
- In `backend/app/api/routes.py`:
  ```python
  @router.get("/videos", response_model=VideoHistoryResponse)
  def list_my_videos(
      page: int = Query(default=1, ge=1),
      page_size: int = Query(default=20, ge=1, le=100),
      status: str | None = Query(default=None),
      current_user: User = Depends(get_current_user),
      session: Session = Depends(get_session),
  ) -> VideoHistoryResponse:
  ```
- In `backend/app/repositories/video_repository.py` lines 58-59:
  ```python
  base_q = select(Video).where(*where).order_by(Video.created_at.desc())
  ```
- Observation:
  - `routes.py` has NO `query` / `search` parameter.
  - `routes.py` has NO `sort` / `order` parameter.
  - `video_repository.py` hardcodes descending order by `Video.created_at`.
  - No text filter on `Video.title` is supported by the backend query.

### G. R4 Findings: Quiz Endpoints and Answer Leakage (`backend/app/api/routes.py`, `routes_groups.py`, `export_service.py`)
1. **Unprotected Material Retrieval** (`backend/app/api/routes.py:260-266`):
   ```python
   @router.get("/materials/{material_id}", response_model=MaterialResponse)
   def get_material(material_id: int, session: Session = Depends(get_session)) -> MaterialResponse:
       ...
   ```
   - Requires NO authentication and performs NO role check.
   - Serializes `content_json` directly through `_as_response()`, which includes `correct_option`, `explanation`, and `expected_points`.
2. **Topic Materials Endpoint** (`backend/app/api/routes_groups.py:236-247` and `group_service.py:205-312`):
   - When a student calls `GET /{group_id}/topics/{topic_id}/materials`, `TopicMaterialsResponse.shared_quiz` contains the full `MaterialResponse` including `correct_option` and `explanation`.
3. **Export Endpoint** (`backend/app/api/routes.py:346-353`):
   ```python
   @router.get("/materials/{material_id}/export")
   def export_material(
       material_id: int,
       format: ExportFormat = "markdown",
       include_answers: bool = Query(default=False),
       session: Session = Depends(get_session),
   ) -> FileResponse:
   ```
   - Requires NO authentication and performs NO role check.
   - Any student or anonymous caller can pass `?include_answers=true` and download questions with solutions in JSON, PDF, DOCX, or Markdown.
4. `ExportService` (`backend/app/services/export_service.py:23-29`) does support answer stripping (`q.pop("correct_option", None)`, `q.pop("explanation", None)`, `q.pop("expected_points", None)`), but this is ONLY invoked if `include_answers=False`.

### H. R5 Findings: Teacher vs Student Summaries (`backend/app/models/material.py`, `group_service.py`, `material_service.py`)
- `DidacticMaterial` possesses an `owner_id` column (`users.id`), but NO `topic_id` column.
- In `group_service.py:243-300`:
  - `shared_summary` is identified as a summary belonging to `group.admin_id`, `topic.created_by`, or `owner_id IS NULL`.
  - `personal_summary` is identified as a summary belonging to `current_user.id` and `id != shared_summary_id`.
- Bug in `material_service.py:89-93` (`can_edit`):
  ```python
  def can_edit(self, session: Session, material_id: int, user_id: int) -> bool:
      material = self.repository.get(session, material_id)
      return material is not None and self.repository.is_video_owner_or_published_group_admin(session, material, user_id)
  ```
  - `is_video_owner_or_published_group_admin` does NOT check `material.owner_id == user_id`.
  - As a result, when a student creates a personal summary, the student CANNOT edit their own personal material (`can_edit` returns `False` because the student is neither video owner nor group admin).
- Students cannot modify the teacher's official summary (protected by `can_edit`), but students have no mechanism to associate a summary to a specific `topic_id`.
- Teachers cannot query a list of personal summaries generated by students for a given activity.

### I. R6 Findings: Timestamp Extraction and Calibration (`backend/app/services/pipeline.py`, `ingestion/chunker.py`)
- Whisper produces segment-level timestamps (`TranscriptSegment(start, end, text)`).
- Subtitle parser (`youtube.py:236-281`) parses `json3` / `vtt` into `TranscriptSegment(start, end, text)`.
- `ChunkingService.build` (`chunker.py:24-44`) merges multiple segments into ~220-word chunks.
- `VectorStoreService` (`vectors.py:59-67`) indexes chunk boundaries:
  - `"start": timestamp(chunk.start)`
  - `"end": timestamp(chunk.end)`
- `parse_grounded_quiz` (`pipeline.py:151-165`):
  - Strictly validates that all `cited_timestamps` in the quiz must match an entry in `available_timestamps` (which are strictly chunk start or end timestamps).
  - If a timestamp does not match a chunk boundary, `PipelineError("El cuestionario cita timestamps que no pertenecen a la evidencia recuperada.", code="UNGROUNDED_TIMESTAMP")` is raised.
- Currently, NO calibration algorithm exists in the backend:
  - No contextual lead-in calculation (e.g. 5-10s before the explanation starts).
  - No segment-level boundary alignment.

### J. Environment & Test Runner Issue (Python 3.13 / Windows)
- The test suite in `backend/tests/` uses Starlette's `TestClient` in `test_group_permissions.py` and `test_web_interface.py`.
- On Windows with Python 3.13, Starlette's `TestClient.__enter__()` calls `anyio.from_thread.start_blocking_portal()`, which hangs due to an event loop deadlock in `anyio` 4.14 / Python 3.13 on Windows.
- Service and unit tests that do not invoke `TestClient` (e.g. `test_grading_service.py`, `test_chunking.py`, `test_material_repository.py`, etc.) run in under 6 seconds.

---

## 2. Logic Chain

1. **R1 / R2 (Activity-Centric Grading & User Attempt Isolation)**:
   - *From Observation D & E*: In `TopicSummaryResponse`, `members_summary` contains aggregated metrics (`total_attempts`, `best_attempt`, `latest_attempt`), but does not contain intermediate attempts, student answers (`answers_json`), or an explicit `status` field ("evaluated" vs "pending").
   - *From Observation D & E*: In `routes_groups.py`, the only attempt list endpoint for admin is `GET /{group_id}/topics/{topic_id}/attempts`, which dumps all attempts for all members without filtering.
   - *Reasoning*: A teacher entering a specific activity cannot inspect a specific student's attempts without either downloading all students' attempts or relying on client-side filtering. Furthermore, distinguishing between "evaluated" and "pending" is only computed in `get_group_grades` (the general group gradebook), not in `get_topic_summary`.
   - *Remediation*:
     a) Add an optional `user_id: int | None = Query(None)` parameter to `GET /api/v1/groups/{group_id}/topics/{topic_id}/attempts` (or add a dedicated endpoint `GET /api/v1/groups/{group_id}/topics/{topic_id}/members/{user_id}/attempts`).
     b) Enrich `MemberTopicSummary` (in `schemas/contracts.py` and `grading_service.py:compute_member_topic_summary`) to include `status: Literal["evaluated", "pending"]` and a list of attempts or link.

2. **R3 (Video Selection, Ordering, and Search)**:
   - *From Observation F*: `routes.py:list_my_videos` and `video_repository.py:list_by_owner` only accept `page`, `page_size`, and `status`. The query hardcodes `order_by(Video.created_at.desc())`.
   - *Reasoning*: The requirement calls for sorting newest-to-oldest by default with the ability to toggle to oldest-to-newest, combined with a text search on `Video.title`. Currently, any attempt to search or invert sort order cannot be handled by the backend.
   - *Remediation*:
     a) Update `list_my_videos` in `routes.py` to accept `search: str | None = Query(None)` and `order: Literal["desc", "asc"] = Query("desc")`.
     b) Update `VideoRepository.list_by_owner` to apply `Video.title.ilike(f"%{search}%")` when `search` is provided, and order by `Video.created_at.asc()` or `Video.created_at.desc()`.

3. **R4 (Role Separation and Answer Masking)**:
   - *From Observation G*: `GET /materials/{material_id}` has no auth and returns all correct answers. `GET /groups/{group_id}/topics/{topic_id}/materials` returns `shared_quiz` with answers to students. `GET /materials/{material_id}/export` does not check role and allows `include_answers=true`.
   - *Reasoning*: This allows any student to inspect network responses or call the export endpoint to obtain the quiz answers before taking the quiz.
   - *Remediation*:
     a) Create a reusable masking utility `mask_quiz_answers(quiz_content: dict) -> dict` that deletes `correct_option` and `explanation` from each multiple choice question and `expected_points` from each open question.
     b) In `get_topic_materials` (`group_service.py`), if `current_user.id != group.admin_id`, pass `shared_quiz.content` through `mask_quiz_answers`.
     c) In `get_material` (`routes.py`), require authentication or determine caller role; if caller is a student in a topic utilizing this material, mask answers unless the caller is group admin or material owner.
     d) In `export_material` (`routes.py`), verify that if `include_answers=True`, caller must be authenticated and must be the material owner or group admin. If caller is a student, either return HTTP 403 Forbidden or force `include_answers=False`.

4. **R5 (Teacher vs Student Summary Separation)**:
   - *From Observation H*: `can_edit` in `material_service.py` blocks students from editing materials where `owner_id == student.id` because it only checks `is_video_owner_or_published_group_admin`.
   - *Reasoning*: When a student creates a personal summary, they cannot save edits to it. Moreover, `Topic` lacks a `summary_id` column, relying on loose `video_id` matching.
   - *Remediation*:
     a) In `material_service.py:can_edit`, allow edit if `material.owner_id == user_id` (for personal materials) while continuing to prohibit students from editing materials owned by admin or video owner.
     b) In `TopicMaterialsResponse`, clearly distinguish `shared_summary` (official) and `personal_summary`.
     c) Provide an endpoint for teachers to view student personal summaries for a topic (e.g. `GET /groups/{group_id}/topics/{topic_id}/summaries`).

5. **R6 (Timestamp Calibration)**:
   - *From Observation I*: Quiz evidence timestamps are currently constrained to chunk start/end boundaries, which represent ~220-word blocks.
   - *Reasoning*: A chunk boundary does not represent the precise sentence where a topic is explained, nor does it provide a calibrated 5-10 second context lead-in.
   - *Remediation*:
     a) Implement `TimestampCalibrationService`: Reads the transcript segments (`data/transcripts/processed/<youtube_id>.json`).
     b) For each question, locates the segment containing the explanation or key terms.
     c) Identifies the explanation start second $T_{\text{expl}}$.
     d) Walks backwards to the previous segment boundary such that the lead-in is between 5 and 10 seconds before $T_{\text{expl}}$.
     e) Updates `evidence_timestamp` to the calibrated time.
     f) Ensure `parse_grounded_quiz` accepts segment timestamps within the retrieved chunks or applies the calibration after validation.

---

## 3. Caveats

1. **Python 3.13 / AnyIO on Windows**:
   - `fastapi.testclient.TestClient` deadlocks during startup on Windows Python 3.13 due to `anyio.from_thread.start_blocking_portal()`.
   - All unit and domain service tests (grading, chunking, providers, materials, exports) run fast and pass without issue.
   - For integration tests, using `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` with `pytest-asyncio` avoids the blocking portal deadlock.
2. **Video Publication Date**:
   - YouTube's `upload_date` is extracted by `yt-dlp` during `inspect()` but is not currently persisted into the `videos` table. The existing system uses `Video.created_at` (registration timestamp) as the date. R3 asks for "fechas reales de publicación o registro disponibles". Adding an optional `upload_date` column to `Video` is beneficial, but sorting by `created_at` satisfies "fecha de registro".
3. **Database Engine**:
   - SQLite is configured with WAL mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`). While adequate for single-node prototypes, multiple concurrent write transactions during test execution must be handled cleanly.

---

## 4. Conclusion

The backend architecture is clean and modular, structured around SQLAlchemy 2.0 ORM, FastAPI routers, Pydantic contracts, and isolated domain services. However, critical gaps exist for requirements R1-R6:

| Req | Core Gap | Backend Files to Modify |
|---|---|---|
| **R1** | No per-student attempt query for teachers in a specific activity; missing "evaluated" vs "pending" status in `MemberTopicSummary`. | `backend/app/api/routes_groups.py`, `group_service.py`, `group_repository.py`, `schemas/contracts.py` |
| **R2** | `GET /{group_id}/topics/{topic_id}/attempts` dumps all students' attempts without filtering by user. | `backend/app/api/routes_groups.py`, `group_service.py`, `group_repository.py` |
| **R3** | `GET /api/v1/videos` lacks `search` and `sort` parameters; `VideoRepository.list_by_owner` hardcodes descending order. | `backend/app/api/routes.py`, `video_repository.py` |
| **R4** | Correct answers and explanations are exposed in `GET /materials/{id}`, `GET /{group_id}/topics/{topic_id}/materials`, and `GET /materials/{id}/export` without role filtering. | `backend/app/api/routes.py`, `group_service.py`, `material_service.py`, `export_service.py` |
| **R5** | Student personal summaries cannot be edited by students due to `can_edit` checking video ownership instead of material ownership; summaries lack activity linkage. | `backend/app/services/material_service.py`, `group_service.py`, `routes_groups.py` |
| **R6** | No timestamp calibration exists; timestamps are coarse chunk boundaries without context-aware 5-10s lead-in. | `backend/app/services/` (new `timestamp_service.py`), `pipeline.py` |

---

## 5. Verification Method

To independently verify all findings and test suite behavior:

1. **Verify Unit & Service Tests**:
   ```powershell
   Set-Location backend
   .\.venv\Scripts\python.exe -m pytest tests/services/test_grading_service.py -v
   .\.venv\Scripts\python.exe -m pytest tests/services/test_export_service.py -v
   .\.venv\Scripts\python.exe -m pytest tests/repositories/test_material_repository.py -v
   ```
2. **Verify Answer Leakage (R4)**:
   - Inspect `backend/app/api/routes.py` lines 260-266 and lines 346-353. Note lack of `current_user` dependency or role-based answer masking.
   - Inspect `backend/app/services/group_service.py` line 224: `shared_quiz` is returned with raw `content_json` to students.
3. **Verify Video Search & Sorting (R3)**:
   - Inspect `backend/app/api/routes.py` line 61 (`list_my_videos`). Note absence of search or order query parameters.
   - Inspect `backend/app/repositories/video_repository.py` line 58. Note hardcoded `order_by(Video.created_at.desc())`.
4. **Verify Student Edit Permission Bug (R5)**:
   - Inspect `backend/app/services/material_service.py` line 89 (`can_edit`) and `material_repository.py` line 69 (`is_video_owner_or_published_group_admin`). Note that `material.owner_id == user_id` is never checked.
5. **Verify Timestamp Chunk Boundaries (R6)**:
   - Inspect `backend/app/services/pipeline.py` lines 151-165. Note that `available_timestamps` is composed solely of chunk `start` and `end` times.
