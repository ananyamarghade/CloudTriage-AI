# Installing the MONAI lung nodule model locally

The lung nodule detection subsystem (`backend/app/lung_nodule/`) is now wired into the
application (endpoints, DICOM->NIfTI conversion, coordinate mapping, frontend card).
It is **fail-closed**: with no extra dependencies installed, `GET /api/lung-nodule/status`
reports `available: false` and the app behaves exactly as before. Installing the
environment below and restarting the backend is what turns it on -- nothing in the base
app (`backend/requirements.txt`) changes.

This installs the real, reviewed MONAI Model Zoo bundle `lung_nodule_ct_detection`
(RetinaNet on a 3D ResNet-50 backbone, trained on LUNA16). It is an example pulmonary
nodule detector, **not a diagnostic device**.

## Windows PowerShell

Run these commands from `precision-imaging`:

```powershell
py -3.11 -m venv backend\model-venv
backend\model-venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
python -m pip install -r backend\requirements-model.txt
```

`requirements-model.txt` now pins everything the integration actually imports:
`torch==2.4.0`, `torchvision==0.19.0`, `monai==1.4.0`, `nibabel==5.2.1`,
`pytorch-ignite==0.4.11`, `tensorboard==2.17.0`, plus `itk==5.4.0` (MONAI's
`LoadImaged(reader="itkreader")`) and `SimpleITK==2.4.0` (DICOM series -> NIfTI
conversion). These were confirmed installable and importable together during this
integration (see `LUNG_NODULE_INTEGRATION.md`).

The model weights already ship with the app at
`backend\app\lung_nodule\bundle\models\model.pt` (copied from the reviewed bundle) --
there is no separate download step.

Verify the environment (no CT data needed for this check):

```powershell
python -c "import torch, monai, itk, SimpleITK; print('torch', torch.__version__); print('monai', monai.__version__); print('cuda available:', torch.cuda.is_available())"
```

## Linux / macOS

```bash
cd precision-imaging
python3.11 -m venv backend/model-venv
source backend/model-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python -m pip install -r backend/requirements-model.txt
```

## Turning it on

1. Start the backend using the `model-venv` interpreter (see the root `README.md` /
   `WINDOWS_RUN.md` for exact commands).
2. Open the Admin console, or call `GET /api/lung-nodule/status` -- it should report
   `"available": true` once torch/monai/itk/SimpleITK import successfully and
   `backend/app/lung_nodule/bundle/models/model.pt` is present.
3. Open any uploaded study and use the **Lung Nodule Detection** card's "Run Detection"
   button.

Set `LUNG_NODULE_MODEL_ENABLED=0` as an environment variable to force the safe
fallback off even if the environment is otherwise ready (kept for the same reasons the
original fail-closed design in `MODEL_EVALUATION.md` was chosen). Set
`LUNG_NODULE_DEVICE=cpu` to force CPU even if a CUDA GPU is present, or `=cuda` to
require GPU.

## Model contract (unchanged from the bundle's own documentation)

The bundle expects a one-channel CT volume resampled to
`0.703125 x 0.703125 x 1.25 mm`, intensity-normalized to `0..1`, NIfTI-shaped input.
`backend/app/lung_nodule/dicom_series.py` performs the DICOM -> NIfTI conversion
(via SimpleITK's `ImageSeriesReader`, preserving spacing/orientation/slice order), and
`backend/app/lung_nodule/model.py` runs the bundle's own preprocessing
(`Orientationd` -> RAS, `Spacingd` -> the bundle's target spacing, `ScaleIntensityRanged`
-1024..300 -> 0..1) exactly as specified in `bundle/configs/inference.json`.

The bundle's output (detection boxes, labels, scores) is returned as-is. It is not
converted into a "triage score" and is never labeled "cancer detected" or "diagnosis"
anywhere in the backend or frontend -- see `LUNG_NODULE_INTEGRATION.md`.

## What is verified vs. still pending

Installing the packages above and confirming the imports succeed is **not** the same as
a validated end-to-end run. This integration has **not yet been tested against a real
DICOM CT series**, because none was available in either source project. Before trusting
results in your environment:

1. Run the environment check above.
2. Upload a real (de-identified) DICOM CT series through the existing Upload page.
3. Run detection from the study viewer and confirm inference completes without error.
4. Visually confirm any returned boxes land on plausible anatomy on the indicated
   slice.
5. Only then treat the "Available" status as meaning "verified," not just "installed."

The existing technical analysis endpoint (`/api/studies/{id}/analysis`) remains the
safe fallback that is always available regardless of whether this model environment is
installed.
