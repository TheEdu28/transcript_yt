# Dispatch: Implementation Worker (Milestones M1–M5)

**Working Directory**: c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_worker_m1_m5\
**Archetype**: teamwork_worker
**Parent ID**: 717dd07c-4cc0-4c6b-9886-3d2a500b5c6a
**Original Request File**: c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\ORIGINAL_REQUEST.md
**Project Plan**: c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\PROJECT.md

## Reference Reports from Survey Phase
- Backend Analysis: `c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_explorer_survey_1\handoff.md`
- Frontend Analysis: `c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_explorer_survey_2\handoff.md`
- Test & Timestamp Analysis: `c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_explorer_survey_3\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objective & Scope of Changes
Implement all functional improvements and corrections for requirements R1–R6:
1. **M1 (R1 & R2) - Activity-Centric Grading & Attempt Isolation**:
   - Backend: Add endpoint or query parameter to fetch attempts for a specific student (`user_id`) in a topic; enrich topic summary with student submission status ("evaluated" vs "pending"); ensure attempts are strictly bound to user, activity, and quiz.
   - Frontend: In `backend/app/web/groups/detail/`, add an activity grading view/modal accessible directly from topic cards in the `Temas` tab. Show student list with evaluated/pending badges, allow clicking a student to inspect their attempts and answers (`answers_json`), and assign/modify grades inline. Isolate student attempt views.
2. **M2 (R3) - Video Selection, Sorting & Search**:
   - Backend: Add `search: str | None = Query(None)` and `order: str = Query("desc")` to `GET /api/v1/videos` in `routes.py`; update `VideoRepository.list_by_owner` to filter `Video.title.ilike(...)` and order by `Video.created_at` (or `upload_date` if present) descending or ascending.
   - Frontend: In `/ui/videos/` and in the Topic creation video picker (`groups/detail/index.html` & `page.js`), add a search input for video title and a sort order dropdown ("Más recientes primero" / "Más antiguos primero"). Ensure search and sort operate jointly in real time without data loss. Update `apiListMyVideos` in `api.js`.
3. **M3 (R4) - Quiz Roles & Answer Masking**:
   - Backend: Create helper `mask_quiz_answers()` that strips `correct_option` and `explanation` from multiple choice and `expected_points` from open questions. Apply it in `GET /{group_id}/topics/{topic_id}/materials` for students. In `GET /materials/{id}` and `GET /materials/{id}/export`, enforce role checks: if student, mask answers or forbid `include_answers=true`.
   - Frontend: In `/ui/quiz/`, for teachers add a visual toggle selector between "Versión con respuestas" and "Versión sin respuestas" that updates view and export immediately. For students, remove the selector and export options, ensuring students only view and export the version without answers.
4. **M4 (R5) - Teacher vs Student Summary Separation**:
   - Backend: In `material_service.py:can_edit`, allow users to edit materials where `material.owner_id == user_id` (personal materials), while blocking non-teachers from modifying official summaries (`shared_summary`). Ensure official summaries cannot be overwritten by students.
   - Frontend: In `backend/app/web/resumen/`, fix the `topicMats?.summary` -> `shared_summary` bug. Implement tabs separating the official teacher summary (read-only for students, no generate/overwrite buttons) and the student's personal summary space. For teachers, allow distinguishing official vs student summaries.
5. **M5 (R6) - Timestamp Calibration (5–10s Lead-In)**:
   - Implement `timestamp_service.py` to analyze transcript segments from Whisper data (`data/transcripts/raw/{id}.json`). For quiz question timestamps, anchor to the relevant topic segment and walk backwards to preceding segment boundaries to provide a 5.0s to 10.0s lead-in margin before the explanation starts (without applying an arbitrary fixed subtraction). Connect timestamp buttons to seek cleanly in the video player.

## Verification & Completion Criteria
- Run all existing tests: `cd backend; .\venv\Scripts\python.exe -m pytest` (with `BypassSandbox: true`). All 78+ tests must pass with zero regressions.
- Write your comprehensive handoff report to `c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_worker_m1_m5\handoff.md`.
- Send completion message to parent when done.


## 2026-11-04T04:31:57Z
Sender: 717dd07c-4cc0-4c6b-9886-3d2a500b5c6a
Priority: MESSAGE_PRIORITY_HIGH
Content: You are the Implementation Worker for Milestones M1-M5. Your working directory is c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_worker_m1_m5\. Read c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\ORIGINAL_REQUEST.md, c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\PROJECT.md, the survey explorer handoff reports in c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_explorer_survey_1\handoff.md, teamwork_explorer_survey_2\handoff.md, and teamwork_explorer_survey_3\handoff.md, and your instructions in c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_worker_m1_m5\DISPATCH.md.


## 2026-11-04T04:42:23Z
Sender: 717dd07c-4cc0-4c6b-9886-3d2a500b5c6a
Priority: MESSAGE_PRIORITY_HIGH
Content: Status check. Please update your progress.md with your latest progress on M1-M5 implementation and report your current status or ETA.

## 2026-11-04T04:59:39Z
Sender: 717dd07c-4cc0-4c6b-9886-3d2a500b5c6a
Priority: MESSAGE_PRIORITY_HIGH
Content: Status check on M2-M5 Implementation. Please update your progress.md and report current status on M2 (Video Search/Sort), M3 (Quiz Masking), M4 (Summaries), and M5 (Timestamps).

