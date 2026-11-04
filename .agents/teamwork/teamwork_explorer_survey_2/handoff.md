# Handoff Report: Frontend Architecture, UI/UX & Role Views (Survey Explorer 2)

## 1. Observation

### 1.1 Architecture & Technology Stack Overview
- **Location of Frontend**: The entire frontend resides under `backend/app/web/` (`20` HTML/JS/CSS files, `28` items total).
  - Main router/mount in `backend/app/main.py:79-86`:
    ```python
    WEB_DIRECTORY = Path(__file__).resolve().parent / "web"
    app.mount("/ui", StaticFiles(directory=WEB_DIRECTORY, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def open_visual_interface() -> RedirectResponse:
        return RedirectResponse(url="/ui/")
    ```
- **Tech Stack**: Vanilla ES6 modules (`<script type="module">`), native DOM APIs, CSS3 with custom variables, and zero frontend build tools (no webpack, no vite, no react, no vue).
- **Core Shared Libraries**:
  - `backend/app/web/api.js`: API client wrapper (`request()`) with bearer token injection, auth helpers (`auth.save()`, `auth.token()`, `auth.user()`, `auth.clear()`), and group/video/material endpoints.
  - `backend/app/web/shared.js`: Route protection (`requireAuth()`), global user dropdown (`renderUserBar()`), notifications (`showNotice()`, `showToast()`), accessible modal dialogs (`confirmModal()`), button state management (`runWithButtonDisabled()`), HTML sanitizer (`escapeHtml()`), and LLM selector (`initModelSelector()`).
  - `backend/app/web/styles.css`: Complete theme system (`--ink`, `--blue`, `--violet`, `--mint`, `--red`, responsive breakpoints).
- **Routing & Views**:
  - `/ui/` (`backend/app/web/index.html`): Checks `localStorage.getItem("aulavideo_token")`; redirects to `/ui/videos/` if logged in, else `/ui/auth/`.
  - `/ui/auth/` (`backend/app/web/auth/index.html`, `page.js`): Iniciar sesión and Registrarse tabs.
  - `/ui/groups/` (`backend/app/web/groups/index.html`, `page.js`): Docente (Crear nuevo grupo) and Estudiante (Unirse con código) dashboards; lists admin vs member groups.
  - `/ui/groups/detail/?group={id}` (`backend/app/web/groups/detail/index.html`, `page.js`): Classroom detail with tabs `topics` (Temas), `members` (Miembros), `grades` (Calificaciones).
  - `/ui/videos/` (`backend/app/web/videos/index.html`, `page.js`): Catalog of processed videos, status filter, delete modal, publish-to-group modal.
  - `/ui/video/` (`backend/app/web/video/index.html`, `page.js`): Ingestion form with polling progress bar (`/videos/{id}/progress`) and cancelation.
  - `/ui/resumen/?video={id}&group={id}&topic={id}` (`backend/app/web/resumen/index.html`, `page.js`): Summary view with YouTube player, synopsis, glossary, and thematic blocks.
  - `/ui/quiz/?video={id}&material={id}&group={id}&topic={id}` (`backend/app/web/quiz/index.html`, `page.js`): Interactive evaluation quiz with YouTube player, multiple choice and open questions, timestamp buttons, and export buttons.
  - `/ui/material/?video={id}&material={id}` (`backend/app/web/material/index.html`, `page.js`): Material editor and snapshot version restore interface.

---

### 1.2 R1: Activity-Centered Grading System
- **Current Observation in `backend/app/web/groups/detail/index.html` & `page.js`**:
  - The page provides three tabs (lines 29-33 of `index.html`):
    - `data-tab="topics"`: List of topics in the group.
    - `data-tab="members"`: Member table.
    - `data-tab="grades"`: Global group gradebook matrix.
  - In `Temas` tab (`renderTopics` in `page.js:187-254`):
    - Topics are rendered as cards with links: `Resumen didáctico`, `Ver cuestionario (respuestas)` (teacher) / `Realizar evaluación` (student), and `Eliminar` (admin).
    - **No activity detail view exists**: There is no button or view to "entrar a una actividad específica" and see the students who submitted it.
  - In `Calificaciones` tab (`loadGrades` and `renderGrades` in `page.js:424-577`):
    - Renders a global cross-matrix table of all members against all topics (`data.topics` x `data.members`).
    - The teacher can only grade by clicking an individual score button in this global matrix, which opens `grade-review-modal` (`page.js:639-673`).
    - In `grade-review-modal`: Only allows editing `final_score` and `review_notes`. **It does not display the student's actual submitted answers, questions, or evidence timestamps**.
  - **Unused API Endpoints in `backend/app/web/api.js`**:
    - Line 146: `apiGetTopicSummary(groupId, topicId)` is defined (`GET /groups/{groupId}/topics/{topicId}/summary`) which returns `TopicSummaryResponse` (student list with attempts count, scores, best attempt, latest attempt), but is **never called anywhere in the frontend**.
    - Line 143: `apiGetAllTopicAttempts(groupId, topicId)` is imported in `page.js:5` but **never used**.
    - Line 140: `apiGetMyTopicAttempts(groupId, topicId)` is imported in `page.js:8` but **never used**.

---

### 1.3 R2: Separation of Individual Attempts per User
- **Current Observation in `backend/app/web/groups/detail/page.js` and `backend/app/web/quiz/page.js`**:
  - In `groups/detail/page.js`:
    - Student view of `grades` tab (`page.js:578-634`) shows only their own summary because backend `/groups/{id}/grades` returns `members: [mySummary]` when called by a student.
    - However, there is no detailed attempt breakdown (e.g. Intento 1, Intento 2...) showing timestamps and answers.
  - In `quiz/page.js`:
    - When a student completes a quiz (`page.js:594-607`), it submits answers via `apiSubmitAttempt(groupId, topicId, attemptPayload)`.
    - It displays an immediate score banner with `Intento #${attemptResult.id}` (`page.js:644`), but there is no view to inspect prior attempts or their progression.
  - Teacher view of attempts:
    - The teacher cannot view individual attempt histories per student. The backend provides `GET /groups/{groupId}/topics/{topicId}/attempts` returning `list[AdminAttemptResponse]` (which contains `answers_json` and `attempt_number`), but the frontend has no component or modal to display this data.

---

### 1.4 R3: Video Selection, Date Sorting, and Search UI
- **Current Observation in `backend/app/web/videos/index.html` & `page.js`**:
  - `videos/index.html:41-52`:
    ```html
    <div class="vid-filters" style="...">
      <label class="vid-filter-label" for="status-filter">
        Filtrar por estado
        <select id="status-filter">
          <option value="">Todos los estados</option>
          <option value="indexed">Indexado (Listo)</option>
          <option value="queued">En cola</option>
          <option value="processing">Procesando</option>
          <option value="failed">Fallido</option>
        </select>
      </label>
    </div>
    ```
    - **Missing search input**: No `<input type="search">` or text filter by video title.
    - **Missing sort order control**: No selector or toggle to alternate between "Más recientes primero" and "Más antiguos primero".
  - `videos/page.js:135-144`:
    - `loadPage(page)` calls `apiListMyVideos(page, PAGE_SIZE, currentStatus || null)`.
  - `api.js:96-99`:
    - `apiListMyVideos(page = 1, pageSize = 20, status = null)` only sends `page`, `page_size`, and `status`. It does not accept search query or sort order.
  - Video Picker in `groups/detail/index.html:171-175` & `groups/detail/page.js:105-146`:
    - In "Crear nuevo tema", `renderVideoPicker(videos)` displays cards in `#video-picker-grid`.
    - It lacks any search input field or sort order toggle.

---

### 1.5 R4: Quiz Dual View (Teacher) and Export Restrictions (Student)
- **Current Observation in `backend/app/web/quiz/index.html` & `page.js`**:
  - In `quiz/index.html:117-130`:
    ```html
    <div id="quiz-export-actions" class="export-group" style="...">
      <div style="...">
        <span>Contenido de exportación:</span>
        <select id="export-mode-select">
          <option value="false" selected>Solo preguntas (sin contestar / sin respuestas)</option>
          <option value="true">Preguntas y respuestas</option>
        </select>
      </div>
      ...
    </div>
    ```
    - The export mode dropdown `#export-mode-select` is rendered in HTML and shown whenever `updateExportVisibility(matId)` runs (`quiz/page.js:101-107`), making it accessible to students as well.
  - In `quiz/page.js:713-731`:
    - When `isAdmin = true`:
      - It hides `#quiz-mode-nav` and calls `renderQuizForAdmin(sharedQuiz.content)`.
      - **There is no selector or toggle for the teacher to switch between "Versión con respuestas" and "Versión sin respuestas"**.
    - When `isAdmin = false`:
      - It calls `renderQuizForStudent(sharedQuiz.content)`.
      - The student sees `#export-mode-select` and could change it to `"true"`.
    - Backend payload leak: `group_service.get_topic_materials` returns `shared_quiz` with `correct_option`, `explanation`, and `expected_points` directly in the payload delivered to student clients.

---

### 1.6 R5: Summary Views: Official Teacher Summary vs Student Personal Summary
- **Current Observation in `backend/app/web/resumen/index.html` & `page.js`**:
  - In `resumen/index.html`:
    - Only a single output panel `#summary-output` exists.
    - `#generate-button` ("Generar resumen") and `#model-selector-container` are always in the DOM.
  - In `resumen/page.js:322-368`:
    - Line 342: `if (topicMats?.summary)` -> **BUG**: In `contracts.py:442`, the field is named `shared_summary`, not `summary`! Therefore, line 342 is dead code (`topicMats.summary` is undefined), preventing proper detection and display of official topic summaries.
    - No tab navigation exists between official and personal summaries.
    - `#generate-button` is visible and active for students. Clicking it sends `POST /materials/summary`, generating a summary that overwrites the active view instead of preserving the teacher's official summary.
    - The teacher has no interface to view personal summaries generated by students for a topic.

---

### 1.7 R6: Timestamps and Video Player Integration
- **Current Observation in `backend/app/web/quiz/page.js` & `resumen/page.js`**:
  - In `quiz/page.js:39-56` and `resumen/page.js:32-101`:
    - `parseTimestampToSeconds(hhmmss)` parses `HH:MM:SS` or `MM:SS` into total seconds.
    - `seekToTimestamp(startHhmmss, endHhmmss)` calls `ytPlayer.seekTo(secs, true)` and `ytPlayer.playVideo()`, scrolling smoothly to `#player-panel`.
    - Every question in student and admin quiz views includes a timestamp button: `<button type="button" class="timestamp quiz-ts-btn" data-ts="...">`.
    - The player correctly navigates to the timestamp specified in `evidence_timestamp`.
    - When inspecting student attempts in the grading flow, timestamp buttons must also be present and wire into `seekToTimestamp` so teachers can verify answers against video evidence.

---

## 2. Logic Chain

1. **R1 (Activity-centered grading)**:
   - *Observation*: `groups/detail/index.html` and `page.js` currently only offer grading through the global gradebook matrix in the `Calificaciones` tab. Topics in `Temas` only link to quiz or delete.
   - *Requirement*: The teacher must enter a specific activity, see students who completed it vs pending, inspect attempts/answers, and grade directly from that activity view without depending on a general panel.
   - *Deduction*: We must introduce an **Activity Grading View / Modal** accessible directly from each topic card in the `Temas` tab. This view must call `apiGetTopicSummary(groupId, topicId)` to display students categorized by submission status ("Calificado" with score, "Pendiente de revisión", "Sin entregar"), and provide an inspection panel with student answers and inline score/notes updating via `apiUpdateAttemptGrade`.

2. **R2 (Individual attempt isolation)**:
   - *Observation*: In `quiz/page.js`, students submit attempts but cannot browse their attempt history. In `groups/detail/page.js`, teachers can only view one score in a modal without question answers or attempt lists.
   - *Requirement*: Each student sees only their own attempt count and details. The teacher consults attempts of each student individually without cross-contamination.
   - *Deduction*: In the activity view, selecting a student must call `apiGetAllTopicAttempts(groupId, topicId)` filtered by `user_id` (or a dedicated student-attempts endpoint) to list Attempt #1, #2, etc., along with `answers_json` and score history. For students, `apiGetMyTopicAttempts(groupId, topicId)` must be invoked to render their personal attempt timeline.

3. **R3 (Video sorting & search)**:
   - *Observation*: `videos/index.html` and `videos/page.js` have only `status-filter`; no title search and no sort order control. `apiListMyVideos` does not forward search or sort parameters. The topic video picker in `groups/detail` also lacks these controls.
   - *Requirement*: Videos must initially sort newest to oldest by real date, permit toggling between newest/oldest first, and provide real-time title search filtering operating jointly with the sort order without data loss.
   - *Deduction*:
     - In `videos/index.html` & `videos/page.js`: Add `<input type="search" id="video-search">` and `<select id="sort-order">` ("Más recientes primero" [default], "Más antiguos primero"). Connect them with debounced listeners and update `apiListMyVideos(page, pageSize, status, search, sort)` in `api.js`.
     - In `groups/detail/index.html` & `groups/detail/page.js` (`renderVideoPicker`): Add title search and date sort toggle above `#video-picker-grid`, filtering the videos while preserving the selected video ID.

4. **R4 (Quiz dual views & export controls)**:
   - *Observation*: `quiz/page.js` forces `renderQuizForAdmin` when `isAdmin = true` with no switch for the student preview (without answers). `#export-mode-select` is rendered in HTML and shown to students.
   - *Requirement*: Teacher has a visual control to toggle between "con respuestas" and "sin respuestas", instantly updating the view and export buttons. Students only see and export "sin respuestas", without any selector.
   - *Deduction*:
     - For teacher (`isAdmin = true`): Add a toggle switch `[ Modo con respuestas ]` / `[ Modo sin respuestas ]`. In "con respuestas", render admin view (correct options, explanations, expected points) and export with answers. In "sin respuestas", render student preview (options only, no indicators) and export without answers.
     - For student (`isAdmin = false`): Remove or hide `#export-mode-select` completely. Hardcode export calls to `include_answers=false`. Ensure UI gracefully displays question data even when backend strips `correct_option` and `explanation`.

5. **R5 (Official summary vs personal student summary)**:
   - *Observation*: `resumen/page.js:342` contains a bug checking `topicMats?.summary` instead of `shared_summary`. `#generate-button` is always accessible to students. No student personal summary tab exists.
   - *Requirement*: Official teacher summary is associated with the topic, viewable by students, but immutable and non-regenerable by them. Students have a personal space to generate and consult their own summary. Teachers can distinguish official vs personal summaries.
   - *Deduction*:
     - Fix `topicMats?.shared_summary` in `resumen/page.js`.
     - For students in a group topic: Create two tabs:
       - Tab 1: "Resumen oficial del profesor" (read-only, hide "Generar resumen" button and model selector).
       - Tab 2: "Mi resumen personal" (allows generating and consulting a personal summary via student's account without overwriting the official summary).
     - For teachers: Show the official summary with an "Oficial" badge, plus an option/selector to review personal summaries generated by students.
     - In `material/page.js`: Block students from saving edits to official materials.

6. **R6 (Timestamps & player calibration)**:
   - *Observation*: `quiz/page.js` and `resumen/page.js` correctly handle `parseTimestampToSeconds` and `ytPlayer.seekTo(secs, true)`.
   - *Requirement*: Timestamps jump 5-10 seconds before the explanation without fixed uniform offset (analyzed in RAG).
   - *Deduction*: The frontend player integration is robust and adheres to YouTube Iframe API standards. We must ensure that when the teacher reviews student attempts in the new activity grading view, the question timestamp buttons remain interactive and invoke `seekToTimestamp`.

---

## 3. Caveats

1. **Backend Dependency on Payloads**: The frontend UI for R4 (hiding answers from students) and R5 (saving personal summaries with `owner_id = user.id`) relies on the backend to enforce permission checks and scrub sensitive payload fields. Frontend masking alone is insufficient; both layers must align.
2. **SQLite Migrations**: Any database fields added for timestamps, attempts, or summaries must be backed by the existing `initialise_local_metadata()` schema patching in `backend/app/main.py`.
3. **No Webpack/Build Step**: All frontend code must remain standard ES6 modules compatible with native browser `import`/`export`. Do not introduce npm packages, JSX, or CSS preprocessors into `backend/app/web/`.

---

## 4. Conclusion

The application has a clean, well-structured frontend architecture based on native ES6 modules and a unified CSS system in `backend/app/web/`. However, there are clear architectural gaps and bugs regarding the prompt requirements:
1. **R1 & R2**: The backend already has `apiGetTopicSummary`, `apiGetAllTopicAttempts`, and `apiGetMyTopicAttempts` ready, but the frontend lacks an **Activity-Centered Grading Interface** inside `groups/detail/`. The teacher currently has no way to enter a specific activity, inspect students' attempts with actual answers, and assign grades from the activity.
2. **R3**: Neither `/ui/videos/` nor the topic video picker modal in `groups/detail/` has a title search input or a date sorting toggle (newest first / oldest first).
3. **R4**: The teacher in `/ui/quiz/` has no toggle to view the version without answers. The student has unauthorized visibility of `#export-mode-select` with the option "Preguntas y respuestas".
4. **R5**: `resumen/page.js` has a property name bug (`topicMats?.summary` vs `shared_summary`) and lacks tabbed separation between the official summary (immutable for students) and personal summaries.
5. **R6**: YouTube player integration is functional; timestamp buttons need to be included in the attempt review interface.

All files, line numbers, components, and missing pieces have been identified and mapped for the implementation phase.

---

## 5. Verification Method

To verify these observations and validate future changes:
1. **Frontend Availability Test**:
   ```bash
   cd backend
   python -m pytest tests/test_web_interface.py
   ```
2. **Visual Inspection of Pages**:
   - Start backend server:
     ```bash
     cd backend
     python -m uvicorn app.main:app --port 8000
     ```
   - Navigate to `http://localhost:8000/ui/auth/` and log in.
   - Verify `/ui/groups/detail/?group={id}`:
     - Check `Temas` tab for the presence of an Activity Grading entry point ("Ver alumnos y calificar").
     - Check that student attempt inspection renders questions and answers.
   - Verify `/ui/videos/`:
     - Check for `<input type="search" id="video-search">` and `<select id="sort-order">`.
     - Test sorting alternation (descending vs ascending) and title filtering.
   - Verify `/ui/quiz/?group={id}&topic={id}`:
     - As Teacher: Check for the dual-view toggle ("Con respuestas" vs "Sin respuestas") and confirm export reflects the active mode.
     - As Student: Confirm no version toggle exists, `#export-mode-select` is hidden, and exports only contain questions without answers.
   - Verify `/ui/resumen/?group={id}&topic={id}`:
     - As Student: Confirm official summary is loaded read-only without generate/overwrite controls; verify personal summary tab is present.
3. **Automated End-to-End & Permission Tests**:
   ```bash
   cd backend
   python -m pytest tests/test_group_permissions.py
   ```
