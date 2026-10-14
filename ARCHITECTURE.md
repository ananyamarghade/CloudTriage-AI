# Architecture

This describes the application as it actually exists in this repository, not an aspirational
design. Where a section of the original spec (multi-site PACS integration, MPR, live push
notifications, production auth) is not implemented, that is stated explicitly rather than implied.

## High-level flow

```
Frontend (React/Vite, single main.tsx)
        │  fetch() with Authorization: Bearer <token> for admin/audit routes
        ▼
REST API (FastAPI, backend/app/main.py)
        │
        ├── Study ingestion & storage  ── sqlite (backend/database.db)
        │     - DICOM parsing (pydicom), study/series grouping, slice ordering by
        │       InstanceNumber/ImagePositionPatient at upload time
        │
        ├── DICOM Service  ── backend/app/lung_nodule/dicom_series.py
        │     - Real geometry-preserving series → 3D volume conversion (SimpleITK
        │       ImageSeriesReader), used by both the eligibility gate and inference
        │
        ├── AI Inference Service  ── backend/app/lung_nodule/{model.py,service.py}
        │     - Loads the real MONAI lung_nodule_ct_detection bundle (RetinaNet + LUNA16
        │       weights), runs the bundle's own documented pre/postprocessing, unmodified
        │     - Lazily imports torch/monai/itk/SimpleITK so the rest of the API keeps
        │       working when these optional, heavy dependencies are not installed
        │
        ├── Triage Policy Engine  ── backend/app/triage.py
        │     - Pure function: detection result → {HIGH, REVIEW, ROUTINE} + explanation
        │     - Explicitly documented as a prototype workflow-prioritization policy, not
        │       a clinical decision threshold; versioned (POLICY_VERSION) and stored with
        │       every analysis record so past runs remain attributable to a specific policy
        │
        └── Repository / Storage
              - Local filesystem for uploaded DICOM files (backend/uploads/)
              - SQLite for studies, analyses, feedback, and audit_logs tables
              - No AWS HealthImaging repository is implemented in this codebase; the demo
                honestly reports "Not Configured" rather than simulating a connection
                (see README.md "AWS HealthImaging" section for what a real adapter would need)
```

## Request lifecycle for a lung nodule analysis run

1. `POST /api/upload` — DICOM files are validated, grouped into a study/series, and their
   real spatial/technical metadata (rows, columns, slice thickness, UIDs) is stored. No AI
   runs at upload time; `ai_status` starts at `READY` and `priority` at `UNAVAILABLE`.
2. `GET /api/studies/{id}/eligibility` — real, inspectable checks (DICOM validity, CT modality,
   pixel data, slice count ≥2, consistent dimensions, and an actual trial volume construction)
   run against the real uploaded files. Nothing here is inferred or assumed.
3. `POST /api/studies/{id}/lung-nodule-detect`:
   - Re-runs the eligibility gate server-side (the frontend gate is a UX convenience, not the
     source of truth) and aborts with a documented reason if it fails, storing an
     `UNSUPPORTED_INPUT` analysis record.
   - On eligible input: constructs the real 3D volume, loads the real model (once, then
     cached in-process), runs the real bundle preprocessing → inference → postprocessing,
     and measures actual wall-clock duration.
   - On success: persists an `analyses` row with full model provenance (name, version, task,
     source, license, preprocessing version, runtime, device, timestamps, duration) and the
     raw result, then calls `triage.evaluate()` and stores the resulting priority + reason on
     both the `analyses` row and the `studies` row (so the queue reflects it immediately).
   - On failure at any stage (series construction, model loading, inference, output parsing):
     the real exception is caught, the stage is recorded (`error_stage`), and the study is
     marked `FAILED`/`UNAVAILABLE` — never silently retried with a fabricated result.
4. `GET /api/studies/{id}/analyses` — full history of every run (including failed/ineligible
   ones), each independently timestamped and versioned.
5. `POST /api/studies/{id}/feedback` — clinician Agree/Disagree/Unable-to-assess is stored
   against the study/analysis for later workflow evaluation. This is explicitly documented as
   not retraining or otherwise altering the model.

## RBAC

A minimal in-process session map (`SESSIONS` in `main.py`) associates a bearer token issued at
`/api/login` with a role (`clinician` or `admin`). `/api/audit`, `/api/admin/status`, and
`/api/admin/ai-diagnostics` require the `admin` role server-side (`require_role`), not just a
frontend nav-hiding convention — a clinician token receives a real `403` from these endpoints.
This is a prototype auth mechanism suitable for a local demo: sessions live only in memory and
reset on backend restart. It is not a production identity/authorization system (no password
hashing, no token expiry, no refresh flow) and should not be treated as one.

## What is intentionally NOT implemented

- **AWS HealthImaging integration.** The abstraction point exists conceptually (see README), but
  no `AWSHealthImagingRepository` class exists in this codebase. The admin status endpoint reports
  this honestly as "Not Configured" rather than simulating a connected state.
- **Multi-planar reconstruction (MPR).** The viewer shows axial slices from the original series
  only; no sagittal/coronal reformatting is implemented.
- **Real-time push notifications.** The queue is refreshed on navigation/polling by the frontend;
  there is no websocket/SSE channel pushing "new study" events to open clients.
- **Production-grade authentication.** See RBAC section above.

---

## Platform evolution: multi-organ, multi-modality AI platform

The sections below describe what was added on top of the architecture above to evolve the
product from a single lung-nodule demo into a general-purpose imaging platform. The lung nodule
implementation described above is unchanged; it is now wrapped as one pipeline among several.

### DICOM Intelligence

`backend/app/dicom_intel.py` extracts patient/study, imaging, and modality-specific (CT/MRI)
metadata directly from the real uploaded DICOM files via pydicom — nothing here is invented.
Any tag that is absent or a check that cannot be computed reports `"Not available"` rather than
a fabricated value. It also computes real, non-fabricated image-quality checks (metadata
completeness, dimension/orientation/slice-spacing consistency, pixel-decodability) by reading
the actual pixel data and geometry of every slice in the study.

This powers the new `/dicom-analysis` frontend page, backed by
`GET /api/studies/{id}/dicom-analysis`, which returns:

- **Study Profile** — patient/study fields (with a de-identified patient label; see Privacy below)
  and imaging fields (modality, dimensions, spacing, orientation, transfer syntax, etc.)
- **Acquisition Parameters** — CT (KVP, tube current, CTDIvol, contrast) or MRI (field strength,
  sequence, TR/TE, flip angle) parameters, selected based on the study's real `Modality` tag
- **Series Explorer** — sibling studies sharing the same `StudyInstanceUID` (this app creates one
  `studies` row per DICOM series, so a multi-series study is represented as multiple rows)
- **Image Quality** — the checks described above
- **AI Readiness** — see AI Pipeline Architecture below

### Multi-organ / multi-modality support

The platform no longer hard-codes "lung". Anatomy and modality are read from real DICOM tags
(`Modality`, `BodyPartExamined`) at upload time and used everywhere downstream (queue, DICOM
analysis, AI pipeline recommendation, analytics grouping). Where identification is ambiguous or
a body region has no matching pipeline, the UI/API says so explicitly (see `recommend_pipeline`
in `backend/app/ai/registry.py`) instead of guessing.

### AI Pipeline Architecture

`backend/app/ai/` is a generic abstraction so the platform can host more than one AI model:

```
backend/app/ai/
  schemas.py    — PipelineInfo, Finding, AIAnalysisResult (the standardized result shape)
  registry.py   — the list of pipelines, their real availability, and modality/anatomy
                   → pipeline compatibility/recommendation logic
  service.py    — dispatches a run/eligibility request to the right pipeline implementation
                   and always returns the standardized AIAnalysisResult
```

Each `PipelineInfo` declares: pipeline id, display name, anatomy, supported modalities, model
name/version, `available` (deps + weights actually present), `can_run_inference`, a human-
readable `status_reason`, inference capability, and description. The frontend discovers all of
this from `GET /api/ai/pipelines` — pipeline capabilities are never hard-coded in the UI.

**Lung Nodule pipeline** (`pipeline_id="lung_nodule_ct"`): a thin adapter over the existing,
unmodified `backend/app/lung_nodule` implementation. `ai/service.py` calls
`lung_nodule_service.detect_from_slice_paths()` exactly as the original dedicated endpoint does,
then reshapes its output into the standardized `AIAnalysisResult`/`Finding` schema. The original
`POST /api/studies/{id}/lung-nodule-detect` endpoint is untouched and keeps working for backward
compatibility; `POST /api/studies/{id}/ai/lung_nodule_ct/run` is the new generic equivalent and
records to the same `analyses` table (now tagged with `pipeline_id`).

**Brain Imaging pipeline** (`pipeline_id="brain_imaging"`): registered with real anatomy/modality
metadata (Brain, CT/MR) but no model ships with this project. `available`/`can_run_inference` are
`false` and `status_reason` explains why. Calling its run endpoint returns a structured
`inference_unavailable` result — it never fabricates a brain finding. This demonstrates the
required distinction between "pipeline supported" (the platform knows how to route Brain CT/MR
here) and "model currently available for inference" (no weights are installed). To make it real,
add a model wrapper analogous to `lung_nodule/service.py` and update `_brain_pipeline()` in
`registry.py` to report `available=True` once the model can actually load.

### Standardized AI results

`ai/schemas.py:AIAnalysisResult` is the common shape every pipeline returns: pipeline/model
identity, anatomy, modality, status, a list of `Finding`s (label, confidence, slice index,
bounding box / mask / point), a confidence summary, processing time, limitations, and a
timestamp. The DICOM+AI connection (`GET /api/studies/{id}/ai-readiness`,
`POST /api/studies/{id}/ai/{pipeline_id}/run`) always speaks this schema, so the viewer and
analytics pages are not coupled to "lung nodule" terminology even though only one pipeline
currently produces real findings.

### Analytics architecture

`backend/app/analytics.py` contains pure aggregation functions, one per analytics page, each
querying the existing `studies`/`analyses`/`audit_logs` tables directly — there is no synthetic
data generator anywhere in this module. `main.py` exposes them as:

```
GET /api/analytics/overview
GET /api/analytics/ai
GET /api/analytics/imaging
GET /api/analytics/findings   (supports date_from/date_to/modality/anatomy/pipeline/finding_type)
GET /api/analytics/performance
GET /api/analytics/audit      (admin-only, reuses the existing audit_logs table/RBAC)
```

Every number returned is either a real `COUNT`/`AVG`/`SUM` over real rows, or an explicit empty
list/`null` when there is no data yet — the frontend renders that as a labeled empty state rather
than a chart with invented values.

### Audit / provenance

No new audit system was created. `/api/analytics/audit` reads the same `audit_logs` table used
by the existing `/api/audit` endpoint and the `audit()` helper in `main.py`, and is protected by
the same admin-only RBAC check. New event types (`dicom_analysis_viewed`) were added using the
same `audit(actor, action, detail)` call already used throughout `main.py`.

### How to add a new AI pipeline/model

1. Implement (or adapt an existing) inference module, following the pattern in
   `backend/app/lung_nodule/service.py`: a `get_status()`-style truthful availability check and a
   `detect_...()`/`run_...()` function that raises a clear error on failure rather than returning
   a fabricated result.
2. Add a `_your_pipeline()` function to `backend/app/ai/registry.py` returning a `PipelineInfo`
   with real `available`/`can_run_inference` values, and add it to `list_pipelines()`.
3. Add its modality/body-part compatibility rule(s) to `COMPATIBILITY` in `registry.py`.
4. Wire the actual inference call into `backend/app/ai/service.py:run()` (mirroring the
   `lung_nodule_ct` branch), mapping its output into `Finding`/`AIAnalysisResult`.
5. Nothing else needs to change — `/api/ai/pipelines`, `/dicom-analysis` AI Readiness, the generic
   run endpoint, and every analytics page pick it up automatically because they all read from the
   registry/`analyses` table rather than hard-coding pipeline names.
