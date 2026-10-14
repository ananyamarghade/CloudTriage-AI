# Windows run instructions

Exact PowerShell commands to run the integrated project from a fresh extracted folder.
Two PowerShell windows: one for the backend, one for the frontend.

## 0. Prerequisites

- Python 3.10 or 3.11 on PATH (or available via `py -3.11`)
- Node.js 18+ and npm
- ~3 GB free disk space if you install the optional lung-nodule model environment (torch is the largest single package)

## 1. Backend -- base app only (lung nodule detection reports "not available")

```powershell
cd precision-imaging\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The API is now at http://localhost:8000. `GET /api/lung-nodule/status` will report
`"available": false` with a clear reason (missing dependencies), and the rest of the
app works exactly as before this integration.

## 2. Backend -- with lung nodule detection enabled (optional)

Use a separate virtual environment for the extra ML dependencies, as the project
already separates `requirements.txt` (core API) from `requirements-model.txt` (model):

```powershell
cd precision-imaging\backend
py -3.11 -m venv model-venv
.\model-venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-model.txt
python -m uvicorn app.main:app --reload
```

Optional: set environment variables before starting uvicorn to control behavior:

```powershell
$env:LUNG_NODULE_DEVICE = "cpu"                 # force CPU even if a GPU is present
$env:LUNG_NODULE_PRELOAD_ON_STARTUP = "1"        # build the model at startup instead of on first request
python -m uvicorn app.main:app --reload
```

Model weights already ship inside the app at
`backend\app\lung_nodule\bundle\models\model.pt` -- no separate download is needed.

## 3. Frontend

In a second PowerShell window:

```powershell
cd precision-imaging\frontend
npm install
npm run dev
```

Open http://localhost:5173. Sign in with `clinician@precision.demo` or
`admin@precision.demo` (no password required).

## 4. Using the app

**Upload a study:** go to "Upload Study," select one or more `.dcm` files from the same
series, and click "Validate, group, and index."

**Run lung nodule detection:** open the study from the Dashboard or Imaging Queue, and
in the "Lung Nodule Detection" card on the right, click **Run Detection**. This calls
`POST /api/studies/{study_id}/lung-nodule-detect`. If the model environment isn't
installed, the button is disabled and the card explains why. While running, the UI
shows a loading state (inference can take from seconds to several minutes on CPU,
depending on volume size). Results show nodule count, per-detection confidence, and
which slice each detection maps to; scroll to that slice to see the bounding-box
overlay drawn on the image. If no candidates clear the model's confidence threshold,
the card shows "No nodules detected" rather than an empty/broken state.

## 5. Stopping

Ctrl+C in each PowerShell window. Deactivate a virtual environment with `deactivate`.
