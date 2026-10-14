# CloudTriage AI: Medical Imaging & Nodule Detection Platform

A Windows-first, cloud-ready prototype for AI-assisted imaging triage. This is clinical decision support only: it does not provide a medical diagnosis and does not replace professional clinical judgment.

It is a multi-organ, multi-modality imaging platform: DICOM Intelligence extracts real study/series/acquisition metadata (CT and MRI specific parameters included), a generic AI pipeline registry routes eligible studies to the right model (today: Lung Nodule Detection for Chest CT, with a registered-but-not-yet-modeled Brain Imaging pipeline for Brain CT/MRI), and an Analytics section reports real platform statistics (Overview, AI Analytics, Imaging Analytics, Findings, Performance, Audit). See `ARCHITECTURE.md` → "Platform evolution" for the full breakdown.

## Requirements

- Python 3.10+
- Node.js 18+
- npm

## Run on Windows PowerShell

From the project directory, open two PowerShell windows.

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Demo accounts are `clinician@precision.demo` and `admin@precision.demo`; no password is required.

The frontend includes a project-local `.npmrc` that uses the public npm registry at `https://registry.npmjs.org/`. No external service, registry, URL, port, or environment variable is required.

## Architecture

The backend is a small FastAPI service with SQLite and a local DemoStorage implementation. Uploaded files are validated with pydicom, metadata is persisted without exposing patient identifiers, and pixel data is rendered from the original DICOM for the study viewer. The storage boundary is intentionally isolated so an `AWSHealthImagingStorage` adapter can replace DemoStorage later.

## Features

- Empty initial database; no seeded patients or studies
- DICOM extension, structure, and pixel validation
- Multi-file study/series grouping by StudyInstanceUID and SeriesInstanceUID
- Actual slice ordering from ImagePositionPatient or InstanceNumber
- Anonymized UI study labels
- Transparent technical analysis panel based on actual DICOM pixel readability, dimensions, and intensity range
- Honest separation between prototype technical analysis and unavailable medical AI triage
- **Lung nodule CT detection** (optional): runs the real MONAI Model Zoo `lung_nodule_ct_detection` bundle (RetinaNet on a 3D ResNet-50 backbone, trained on LUNA16) against the study's actual DICOM series. Off by default until the model environment is installed (see `MODEL_INSTALL.md`). Research/demo only -- not a diagnostic tool.
- Imaging queue search, priority ordering, status persistence
- Study viewer with actual DICOM-derived slice rendering, slice navigation, zoom, fit/reset, and window/level, plus lung-nodule bounding-box overlay on the matching slice when detection has been run
- Audit events for login, upload, open, triage, review, and lung-nodule detection runs
- Light/dark theme persisted in localStorage
- Admin system status with truthful Demo/AWS/model state
- CORS and server-side validation

## Lung nodule detection

See `MODEL_INSTALL.md` to install the optional model environment (`backend/model-venv`) and download the bundle weights, and `LUNG_NODULE_INTEGRATION.md` for the full integration design, API contract, coordinate conventions, and what has/hasn't been runtime-verified.

## AWS HealthImaging

AWS is not required for the demo. When implemented, configure `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_HEALTHIMAGING_DATASTORE_ID` through `backend/.env` or Windows environment variables only. Never place credentials in the frontend. This prototype currently reports AWS HealthImaging as **Not Configured**. See `backend/.env.example`.

## Limitations

No medical *triage/priority scoring* model is loaded. The `/api/studies/{id}/analysis` endpoint runs a deterministic **prototype technical analysis** over the actual uploaded DICOM pixels: it reports decodability, dimensions, intensity range, and technical flags. It does not infer disease, lesions, cancer, or clinical priority.

An optional **lung nodule detection** model (MONAI `lung_nodule_ct_detection`) can be installed and run via `/api/studies/{id}/lung-nodule-detect` (see `MODEL_INSTALL.md`). It is an example research model trained on LUNA16, explicitly documented by its authors as **not for diagnostic purposes**. Its output is a list of candidate detection boxes with confidence scores, never a diagnosis, cancer determination, or triage priority. Real end-to-end validation with an actual patient-like DICOM CT series is still pending -- see `LUNG_NODULE_INTEGRATION.md` for exactly what has and hasn't been verified.

The viewer renders actual uploaded DICOM pixels as a browser-compatible PNG and navigates actual uploaded series slices. Do not use real patient-identifying data.
