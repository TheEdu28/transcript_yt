# E2E Test Infra: transcript_yt

## Test Philosophy
- Opaque-box, requirement-driven: Derived strictly from `ORIGINAL_REQUEST.md` and user-facing specifications.
- Dual-role verification: Every feature tested from both Profesor (teacher) and Alumno (student) perspectives.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Interaction Testing + Real-World Workload Scenarios.
- Execution Environment: Python 3.13 via pytest in `backend/` (`cd backend; .\venv\Scripts\python.exe -m pytest tests/e2e/ -v`).

## Feature Inventory & Test Coverage Goals
| # | Feature | Requirement Source | Tier 1 (Min 5) | Tier 2 (Min 5) | Tier 3 (Pairwise) | Tier 4 (Real-World) |
|---|---------|-------------------|:--------------:|:--------------:|:-----------------:|:-------------------:|
| F1 | Activity-Centric Grading View | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| F2 | Individual Attempt Separation | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| F3 | Video Ordering & Text Search | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| F4 | Role-Based Quiz Answer Masking | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| F5 | Teacher vs Student Summaries | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ | ✓ |
| F6 | Timestamp Calibration (5–10s Lead-In) | ORIGINAL_REQUEST §R6 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Location**: `backend/tests/e2e/`
  - `test_e2e_tier1_features.py`: Happy path verification per feature in isolation (>= 30 tests).
  - `test_e2e_tier2_boundaries.py`: Edge cases, empty queries, invalid inputs, boundary timestamps (>= 30 tests).
  - `test_e2e_tier3_pairwise.py`: Cross-feature interactions (role + quiz + attempt + grade + export) (>= 10 tests).
  - `test_e2e_tier4_scenarios.py`: Full realistic classroom lifecycle workflows (>= 5 scenarios).
  - `test_e2e_permissions_matrix.py`: Explicit verification of all 8 role capabilities (Teacher vs Student).
- **Execution Command**:
  ```powershell
  Set-Location "c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2\backend"; .\.venv\Scripts\python.exe -m pytest tests/e2e/ -v
  ```

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Complete Course Activity Lifecycle | F1, F2, F4, F5 | High |
| 2 | Quiz Taking, Hiding Answers & Individual Review | F1, F2, F4, F6 | High |
| 3 | Large Video Catalog Management & Search | F3 | Medium |
| 4 | Collaborative Study with Personal Summaries | F5, F4 | Medium |
| 5 | Video Timestamp Navigation & Topic Study | F6, F4 | Medium |

## Role Permission Matrix Acceptance Criteria
1. Calificar alumnos: Profesor Sí, Alumno No.
2. Consultar intentos individuales: Profesor Sí (de cada alumno), Alumno solo los propios.
3. Ordenar y buscar videos: Profesor Sí, Alumno Sí.
4. Ver y exportar cuestionario con respuestas: Profesor Sí, Alumno No.
5. Ver y exportar cuestionario sin respuestas: Profesor Sí, Alumno Sí.
6. Consultar resumen del profesor: Profesor Sí, Alumno Sí.
7. Generar resumen personal: Alumno Sí.
8. Modificar resumen oficial: Alumno No.
