# Investigation Report: Pipeline Integration & Error Handling Safeguards (Iteration 2)

**Agent**: Explorer 2 (`teamwork_explorer_it2_2`)  
**Archetype**: teamwork_explorer (read-only investigation & analysis)  
**Parent Conversation ID**: `717dd07c-4cc0-4c6b-9886-3d2a500b5c6a`  
**Working Directory**: `c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\.agents\teamwork\teamwork_explorer_it2_2\`  
**Date**: 2026-11-04  
**Target File**: `backend/app/services/pipeline.py` (lines 436–452)  
**Related Files**: `backend/app/services/timestamp_service.py`, `backend/app/schemas/contracts.py`, `backend/app/services/material_service.py`

---

## 1. Observation

### 1.1 Current Pipeline Integration in `backend/app/services/pipeline.py`
In `backend/app/services/pipeline.py`, the `quiz` method (lines 407–453) executes the following sequence for generating, calibrating, and saving quizzes:

```python
433:         video = self.repository.get(session, video_id)
434:         effective_owner = owner_id if owner_id is not None else (video.owner_id if video else None)
435:         parsed_quiz = parse_grounded_quiz(raw_response, evidence, multiple_choice_count, open_question_count, bloom_levels)
436:         if video and video.youtube_id:
437:             try:
438:                 from app.services.timestamp_service import TimestampCalibrationService
439:                 segments = TimestampCalibrationService.load_raw_segments(video.youtube_id)
440:                 if segments:
441:                     calibrator = TimestampCalibrationService()
442:                     calibrated_dict = calibrator.calibrate_quiz(parsed_quiz.model_dump(), segments)
443:                     parsed_quiz = QuizResponse.model_validate(calibrated_dict)
444:             except Exception:
445:                 pass
446:         return MaterialService().save_generated(
447:             session,
448:             video_id,
449:             "quiz",
450:             parsed_quiz,
451:             owner_id=effective_owner,
452:         )
```

### 1.2 Unused Module Logger in `pipeline.py`
In `backend/app/services/pipeline.py` (line 43), the module logger is already initialized:
```python
43: logger = logging.getLogger(__name__)
```
However, a codebase-wide grep confirms that `logger` is **never referenced or called anywhere** in `pipeline.py`. When errors happen inside `try ... except Exception: pass` (lines 437–445), zero log records are emitted.

### 1.3 Empirical Reproduction of the Validation Failure Swallowed by `pass`
Executing the exact interaction between `calibrator.calibrate_quiz()` and `QuizResponse.model_validate()` on Python 3.13:

```powershell
Set-Location "c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend"
.\venv\Scripts\python.exe -c "from app.services.timestamp_service import TimestampCalibrationService; from app.schemas.contracts import QuizResponse; s = TimestampCalibrationService(); quiz = {'multiple_choice': [{'question': '¿Qué es x?', 'options': ['a', 'b', 'c', 'd'], 'correct_option': 0, 'explanation': 'exp', 'evidence_timestamp': '00:00:20', 'bloom_level': 'understand'}], 'open_questions': [{'question': 'Explica y', 'expected_points': ['pt1'], 'evidence_timestamp': '00:00:40', 'bloom_level': 'understand'}], 'evidence_sufficient': True, 'insufficiency_note': None}; segments = [{'start': 0.0, 'end': 10.0, 'text': 'intro'}, {'start': 10.0, 'end': 20.0, 'text': 'x'}, {'start': 20.0, 'end': 40.0, 'text': 'y'}]; res = s.calibrate_quiz(quiz, segments); print('Calibrated dict:', res); QuizResponse.model_validate(res)"
```

**Verbatim Output**:
```
Calibrated dict: {'multiple_choice': [{'question': '¿Qué es x?', 'options': ['a', 'b', 'c', 'd'], 'correct_option': 0, 'explanation': 'exp', 'evidence_timestamp': '00:10', 'bloom_level': 'understand', 'raw_timestamp': '00:00:20'}], 'open_questions': [{'question': 'Explica y', 'expected_points': ['pt1'], 'evidence_timestamp': '00:32', 'bloom_level': 'understand', 'raw_timestamp': '00:00:40'}], 'evidence_sufficient': True, 'insufficiency_note': None}
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 2 validation errors for QuizResponse
multiple_choice.0.evidence_timestamp
  String should match pattern '^\d{2}:\d{2}:\d{2}$' [type=string_pattern_mismatch, input_value='00:10', input_type=str]
open_questions.0.evidence_timestamp
  String should match pattern '^\d{2}:\d{2}:\d{2}$' [type=string_pattern_mismatch, input_value='00:32', input_type=str]
```

**Consequence in Live Pipeline**:
Because lines 444–445 execute `except Exception: pass`, this `ValidationError` was silently caught and swallowed without logging. As a direct result, `parsed_quiz` remained the uncalibrated instance. The uncalibrated quiz was passed to `MaterialService().save_generated()`, persisted in the SQLite database, and returned to the client as HTTP 200, giving the illusion of normal operation while silently violating R6 for all videos under 1 hour.

### 1.4 Stripping of `raw_timestamp` During Pydantic Re-Validation
In `timestamp_service.py` (lines 174 and 182), `calibrate_quiz` sets:
```python
q["evidence_timestamp"] = self.to_timestamp_string(calibrated_secs)
q["raw_timestamp"] = raw_ts
```
However, in `backend/app/schemas/contracts.py` (lines 154–172):
- `MultipleChoiceQuestion` defines only: `['question', 'options', 'correct_option', 'explanation', 'evidence_timestamp', 'bloom_level']`.
- `OpenQuestion` defines only: `['question', 'expected_points', 'evidence_timestamp', 'bloom_level']`.

When `QuizResponse.model_validate(calibrated_dict)` is executed, Pydantic v2's default `extra='ignore'` setting silently drops `raw_timestamp`. When `MaterialService().save_generated()` executes `content.model_dump(mode="json", exclude={"material_id"})`, the resulting JSON stored in `didactic_materials.content_json` loses the `raw_timestamp` field completely.

### 1.5 Transcript Segment Resolution Vulnerability
In `pipeline.py` line 439:
```python
segments = TimestampCalibrationService.load_raw_segments(video.youtube_id)
```
In `timestamp_service.py` (lines 187–210), `load_raw_segments(youtube_id, base_dir=None)` checks only three relative paths:
1. `Path("data/transcripts/raw") / f"{youtube_id}.json"`
2. `Path("../data/transcripts/raw") / f"{youtube_id}.json"`
3. `Path(__file__).resolve().parent.parent.parent / "data" / "transcripts" / "raw" / f"{youtube_id}.json"`

However:
- The database record `video` already holds the authoritative absolute transcript path in `video.transcript_path` (set at line 266: `self.settings.raw_transcripts_directory / f"{video_info.youtube_id}.json"`).
- Neither `base_dir=self.settings.raw_transcripts_directory` nor `video.transcript_path` is passed into `load_raw_segments`.
- If the working directory differs or tests use custom temporary storage directories, `load_raw_segments` returns `[]`, causing `if segments:` to be `False` and silently bypassing calibration without logging any message.

---

## 2. Logic Chain

1. **Observation 1.1** establishes that `pipeline.py` relies on `QuizResponse.model_validate(calibrated_dict)` to re-parse the calibrated dictionary into a typed Pydantic instance required by `MaterialService().save_generated`.
2. **Observation 1.3** proves that whenever `calibrator.calibrate_quiz()` emits a dictionary violating the strict `^\d{2}:\d{2}:\d{2}$` pattern mandated by `contracts.py:Timestamp`, Pydantic raises a `ValidationError`.
3. **Observation 1.3** demonstrates that `except Exception: pass` in lines 444–445 intercepts and completely suppresses this `ValidationError`, silently abandoning calibration and falling back to uncalibrated timestamps.
4. **Observation 1.2** shows that `pipeline.py` already defines `logger = logging.getLogger(__name__)` on line 43, yet suppressed errors leave no trace in logs or monitoring.
5. **Observation 1.4** demonstrates that `raw_timestamp` injected by `calibrate_quiz` is stripped during `QuizResponse.model_validate()` because the Pydantic schemas do not declare the field.
6. **Observation 1.5** demonstrates that `load_raw_segments` relies on hardcoded paths instead of the configured `self.settings.raw_transcripts_directory` or the database-persisted `video.transcript_path`.
7. Therefore, fixing requirement R6 in the pipeline requires:
   - Differentiated exception handling that explicitly logs `ValidationError` and other exceptions with full context and traceback.
   - Robust transcript segment discovery utilizing `self.settings.raw_transcripts_directory` and `video.transcript_path`.
   - Clear contract alignment so that `model_validate()` preserves data integrity and schema validity.

---

## 3. Caveats

- **LLM Call Costs**: In production, `pipeline.quiz` invokes external or local LLMs (`GeminiService`), which consumes API quota and takes 5–15 seconds. If `ValidationError` occurs during post-processing calibration, completely crashing the user request (HTTP 500) discards an otherwise valid pedagogical quiz. Logging the error loudly while falling back to the uncalibrated quiz protects user experience while alerting engineering teams. In testing/CI environments, dedicated tests must assert that calibration does NOT fail or fall back.
- **Read-Only Scope**: In compliance with the Teamwork Explorer archetype, no source files were modified during this investigation.

---

## 4. Conclusion & Actionable Fix Recommendations

### 4.1 Recommendation 1: Replace Silent `pass` with Explicit Structured Logging in `pipeline.py`
In `backend/app/services/pipeline.py` (lines 436–452), replace lines 436–445 with structured exception handling that differentiates between schema validation failures (`ValidationError`), missing segments, and unexpected runtime errors:

```python
        if video and video.youtube_id:
            try:
                from app.services.timestamp_service import TimestampCalibrationService
                segments = TimestampCalibrationService.load_raw_segments(
                    video.youtube_id,
                    base_dir=getattr(self.settings, "raw_transcripts_directory", None),
                )
                if not segments and getattr(video, "transcript_path", None):
                    tp = Path(video.transcript_path)
                    if tp.exists():
                        try:
                            raw_data = json.loads(tp.read_text(encoding="utf-8"))
                            segments = raw_data if isinstance(raw_data, list) else raw_data.get("segments", [])
                        except Exception as read_err:
                            logger.warning(
                                "Failed to read transcript from video.transcript_path %s: %s",
                                tp, read_err,
                            )

                if segments:
                    calibrator = TimestampCalibrationService()
                    calibrated_dict = calibrator.calibrate_quiz(parsed_quiz.model_dump(), segments)
                    parsed_quiz = QuizResponse.model_validate(calibrated_dict)
                    logger.info(
                        "Successfully calibrated quiz timestamps for video %s (%s).",
                        video_id, video.youtube_id,
                    )
                else:
                    logger.warning(
                        "No transcript segments found for video %s (%s); quiz generated with uncalibrated timestamps.",
                        video_id, video.youtube_id,
                    )
            except ValidationError as val_err:
                logger.error(
                    "Pydantic validation failed during quiz timestamp calibration for video %s (%s): %s. Falling back to uncalibrated quiz.",
                    video_id, video.youtube_id, val_err, exc_info=True,
                )
            except Exception as exc:
                logger.error(
                    "Unexpected error during quiz timestamp calibration for video %s (%s): %s. Falling back to uncalibrated quiz.",
                    video_id, video.youtube_id, exc, exc_info=True,
                )
```

### 4.2 Recommendation 2: Optional Schema Enhancement for `raw_timestamp`
To prevent `raw_timestamp` from being stripped when `QuizResponse.model_validate(calibrated_dict)` executes, update `backend/app/schemas/contracts.py`:

```python
class MultipleChoiceQuestion(BaseModel):
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option: int = Field(ge=0, le=3)
    explanation: str
    evidence_timestamp: Timestamp
    bloom_level: BloomLevel
    raw_timestamp: Timestamp | None = None


class OpenQuestion(BaseModel):
    question: str
    expected_points: list[str] = Field(min_length=1)
    evidence_timestamp: Timestamp
    bloom_level: BloomLevel
    raw_timestamp: Timestamp | None = None
```
This preserves the pre-calibration timestamp in SQLite JSON storage and ensures that tests asserting `assert mc["raw_timestamp"] == "00:00:15"` pass on model instances as well as dictionaries.

### 4.3 Recommendation 3: Add Pipeline-Level Integration Test for Quiz Calibration
Currently, no test in `backend/tests/services/test_quiz_rag.py` or `backend/tests/e2e/` tests the full flow:
`parsed_quiz` (valid `QuizResponse`) -> `calibrate_quiz` -> `QuizResponse.model_validate(calibrated_dict)`.

Add a test in `backend/tests/services/test_quiz_rag.py`:
```python
def test_calibrate_quiz_produces_schema_valid_quiz_response() -> None:
    """Ensure calibrated quiz dictionary satisfies QuizResponse schema without ValidationError."""
    from app.services.timestamp_service import TimestampCalibrationService
    from app.schemas.contracts import QuizResponse
    
    quiz_dict = {
        "multiple_choice": [{
            "question": "¿Qué es la fotosíntesis?",
            "options": ["A", "B", "C", "D"],
            "correct_option": 0,
            "explanation": "Exp",
            "evidence_timestamp": "00:00:20",
            "bloom_level": "understand",
        }],
        "open_questions": [{
            "question": "Explica la clorofila.",
            "expected_points": ["Punto 1"],
            "evidence_timestamp": "00:00:45",
            "bloom_level": "understand",
        }],
        "evidence_sufficient": True,
        "insufficiency_note": None,
    }
    segments = [
        {"start": 0.0, "end": 12.0, "text": "Introducción"},
        {"start": 12.0, "end": 25.0, "text": "Fotosíntesis"},
        {"start": 25.0, "end": 50.0, "text": "Clorofila"},
    ]
    service = TimestampCalibrationService()
    calibrated_dict = service.calibrate_quiz(quiz_dict, segments)
    
    # Must validate cleanly without raising ValidationError:
    validated = QuizResponse.model_validate(calibrated_dict)
    assert validated.multiple_choice[0].evidence_timestamp == "00:00:12"
    assert validated.open_questions[0].evidence_timestamp == "00:00:37"
```

---

## 5. Verification Method

### 5.1 Verification Commands
1. **Verify that `QuizResponse.model_validate` fails when timestamps are formatted as `MM:SS` (Before Fix)**:
   ```powershell
   Set-Location "c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend"
   .\venv\Scripts\python.exe -c "from app.services.timestamp_service import TimestampCalibrationService; from app.schemas.contracts import QuizResponse; s = TimestampCalibrationService(); quiz = {'multiple_choice': [{'question': 'q?', 'options': ['a','b','c','d'], 'correct_option': 0, 'explanation': 'e', 'evidence_timestamp': '00:00:20', 'bloom_level': 'understand'}], 'open_questions': [], 'evidence_sufficient': True}; segments = [{'start': 0.0, 'end': 10.0, 'text': 'intro'}, {'start': 10.0, 'end': 20.0, 'text': 't'}]; res = s.calibrate_quiz(quiz, segments); QuizResponse.model_validate(res)"
   ```
   *Expected Outcome*: Raises `pydantic_core._pydantic_core.ValidationError` (`String should match pattern '^\d{2}:\d{2}:\d{2}$'`).

2. **Verify that `QuizResponse.model_validate` succeeds when timestamps are formatted as `HH:MM:SS` (Target State)**:
   ```powershell
   Set-Location "c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend"
   .\venv\Scripts\python.exe -c "from app.schemas.contracts import QuizResponse; res = {'multiple_choice': [{'question': 'q?', 'options': ['a','b','c','d'], 'correct_option': 0, 'explanation': 'e', 'evidence_timestamp': '00:00:10', 'bloom_level': 'understand'}], 'open_questions': [], 'evidence_sufficient': True}; validated = QuizResponse.model_validate(res); print('SUCCESS:', validated.multiple_choice[0].evidence_timestamp)"
   ```
   *Expected Outcome*: Prints `SUCCESS: 00:00:10`.

3. **Verify Existing E2E Test Suite**:
   ```powershell
   Set-Location "c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend"
   .\venv\Scripts\python.exe -m pytest tests/e2e/ -v
   ```
   *Expected Outcome*: 100 passed.

### 5.2 Files to Inspect
- `backend/app/services/pipeline.py` (lines 436–452)
- `backend/app/services/timestamp_service.py` (lines 124–145, 187–210)
- `backend/app/schemas/contracts.py` (lines 9, 154–172)
- `backend/tests/services/test_quiz_rag.py`

### 5.3 Invalidation Conditions
- Any occurrence of unlogged `except Exception: pass` in `pipeline.py`.
- Any failure in `QuizResponse.model_validate(calibrated_dict)` causing silent fallback to uncalibrated timestamps.
- Any regression in the 100 passing E2E tests.
