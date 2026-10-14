# Lung nodule CT detection integration

This document describes how the MONAI Model Zoo bundle `lung_nodule_ct_detection`
(RetinaNet on a 3D ResNet-50 backbone, trained on LUNA16) was integrated into the
existing Precision Imaging application, what was and wasn't changed, and exactly what
has and hasn't been verified.

## A. Final architecture

One FastAPI backend, one React frontend -- both structurally unchanged. A new,
self-contained, optional subsystem (`backend/app/lung_nodule/`) is added and wired in
through two additive endpoints. Nothing existing was removed or redesigned.

```
Browser (existing React app, unchanged shape)
  -> existing routes: /api/login, /api/studies*, /api/upload, /api/audit, /api/metrics, /api/admin/status
  -> new routes:      GET  /api/lung-nodule/status
                       POST /api/studies/{id}/lung-nodule-detect
FastAPI (backend/app/main.py, additive changes only)
  -> lung_nodule_service.detect_from_slice_paths(dicom_paths)
       -> dicom_series.convert_series_to_nifti()   (SimpleITK: DICOM series -> temp NIfTI)
       -> model.get_model()                        (lazy-loaded singleton)
            -> builds the bundle's own RetinaNet + RetinaNetDetector + anchors
            -> loads bundle/models/model.pt (real trained weights)
            -> runs the bundle's own preprocessing/postprocessing transforms
       -> dicom_series.make_index_mapper()          (world mm -> original slice/pixel)
       -> structured JSON response
```

## B. Directory structure (new/changed files only)

```
precision-imaging/
├── MODEL_INSTALL.md                     (updated: install steps for the now-wired-in model)
├── MODEL_EVALUATION.md                  (updated: records that the prior "not enabled" decision is superseded)
├── LUNG_NODULE_INTEGRATION.md           (new: this file)
├── WINDOWS_RUN.md                       (new: exact PowerShell run commands)
├── README.md                            (updated: documents the new feature)
├── backend/
│   ├── requirements.txt                 (unchanged -- base API deps)
│   ├── requirements-model.txt           (updated: + itk, SimpleITK)
│   └── app/
│       ├── main.py                      (additive: 2 new routes, updated /api/admin/status, optional startup preload)
│       └── lung_nodule/                 (new package)
│           ├── __init__.py
│           ├── config.py                (paths, env vars, bundle constants)
│           ├── dicom_series.py          (DICOM series -> NIfTI; world-mm -> slice/pixel mapping)
│           ├── model.py                 (builds/loads the real bundle network + runs inference)
│           ├── service.py               (orchestration, status, structured response, safe errors)
│           └── bundle/                  (copied verbatim from the MONAI Model Zoo bundle)
│               ├── LICENSE
│               ├── docs/README.md, docs/data_license.txt
│               ├── configs/inference.json, metadata.json, logging.conf
│               ├── scripts/__init__.py, detection_inferer.py, utils.py
│               └── models/model.pt      (real trained weights, 83.7 MB)
└── frontend/
    └── src/
        ├── main.tsx                     (additive: Lung Nodule Detection card + slice overlay in the existing Viewer; unrelated pre-existing missing `createRoot` import fixed)
        └── styles.css                   (additive: .image-frame/.nodule-box/.ln-running/.nodule-list rules)
```

## C. What was reused vs. added

- **Reused verbatim, unmodified:** `model.pt` weights, `inference.json`'s network/anchor/threshold definitions, `scripts/detection_inferer.py`, `scripts/utils.py`, the bundle's documented preprocessing and postprocessing transform chain.
- **Added:** the DICOM series -> NIfTI conversion (the bundle documents a NIfTI input contract but ships no DICOM loader), the world-mm -> original-slice/pixel coordinate mapping (needed to draw results on the existing DICOM-native viewer), and the FastAPI/React wiring.
- **Not retrained, not replaced, not approximated:** no dummy model, no placeholder detector, no different pretrained model.

## D. API

### `GET /api/lung-nodule/status`
Truthful status, independent of any study. Returns `available`, `loaded`, `reasons` (why not available, if applicable), model metadata (name, task, training data, intended use, published eval metrics from the bundle's own `metadata.json`), `device_preference`, and the standard disclaimer.

### `POST /api/studies/{study_id}/lung-nodule-detect`
Runs inference on that study's actual stored DICOM slices (the same `slice_paths` used by the existing viewer/analysis endpoints). Response shape:

```json
{
  "study_id": "IMG-XXXXXXXX",
  "status": "success",
  "nodule_count": 2,
  "nodules": [
    {
      "confidence": 0.91,
      "class_label": 0,
      "class_name": "nodule",
      "bbox_world_mm": {
        "format": "cccwhd (center_x, center_y, center_z, width, height, depth)",
        "coordinate_system": "RAS world mm",
        "values": [ ... ]
      },
      "location": {
        "slice_index": 42,
        "pixel": { "x": 213.4, "y": 301.2 },
        "pixel_bbox": { "x_min": 200.1, "y_min": 288.0, "x_max": 226.7, "y_max": 314.4 },
        "note": "..."
      }
    }
  ],
  "model": { "name": "...", "task": "...", "training_data": "LUNA16" },
  "disclaimer": "Research prototype only. ..."
}
```

Every number in `nodules` comes directly from the model's own output for that request
(`confidence`, `bbox_world_mm.values`) or is a documented geometric derivation of it
(`location.*`, described in section F). Nothing is invented, defaulted, or filled in
when inference doesn't run -- on failure the endpoint returns HTTP 422 with a safe
message instead (no stack traces).

## E. Environment variables

| Variable | Default | Effect |
|---|---|---|
| `LUNG_NODULE_MODEL_ENABLED` | `1` | Set to `0` to force the safe fallback even if the environment is otherwise ready. |
| `LUNG_NODULE_DEVICE` | `auto` | `auto` (CUDA if available else CPU), `cpu`, or `cuda`. |
| `LUNG_NODULE_MODEL_PATH` | `backend/app/lung_nodule/bundle/models/model.pt` | Override the checkpoint location. |
| `LUNG_NODULE_BUNDLE_DIR` | `backend/app/lung_nodule/bundle` | Override the whole bundle directory. |
| `LUNG_NODULE_TEMP_DIR` | `backend/app/lung_nodule/tmp` | Where per-request converted NIfTI volumes are written and deleted after use. |
| `LUNG_NODULE_PRELOAD_ON_STARTUP` | unset | Set to `1` to build/load the model once at backend startup instead of on first request. |

All paths use `pathlib.Path`, so they resolve correctly on Windows without edits.

## F. Coordinate conventions (Phase 7 requirement)

1. The bundle's postprocessing (`AffineBoxToWorldCoordinated(affine_lps_to_ras=True)` +
   `ConvertBoxModed(dst_mode="cccwhd")`) returns boxes as
   `(center_x, center_y, center_z, width, height, depth)` in **RAS world millimeters**.
   This is returned to the frontend unmodified as `bbox_world_mm`.
2. To place a box on the existing slice-based viewer, `dicom_series.make_index_mapper()`
   converts the RAS center point back to LPS (DICOM's native convention -- a sign flip
   on x and y only) and then to a continuous voxel index in the **original** DICOM
   volume's geometry (not the resampled volume used for inference), using that volume's
   own origin/spacing/direction. `slice_index` is the rounded z-index, clamped to the
   study's actual slice count.
3. `pixel_bbox` (x_min/y_min/x_max/y_max in the original image's pixel space) is derived
   by dividing the model's real mm width/height by the original volume's real in-plane
   pixel spacing. This assumes no in-plane gantry tilt relative to the image axes -- the
   same simplifying assumption the existing viewer/window-level code already makes
   elsewhere in this app. It is documented here and in the API response's
   `location.note` field rather than silently assumed.
4. None of this changes the model's own preprocessing, spatial handling, or output
   semantics -- only how a real output is mapped back onto the original series for
   display.

## G. Dependency decisions (Phase 8)

`backend/requirements-model.txt` was already deliberately isolated from
`backend/requirements.txt` in the base project. This integration only **adds** what the
code actually imports: `itk` (MONAI's `LoadImaged(reader="itkreader")`) and
`SimpleITK` (DICOM series -> NIfTI). No version already selected by the base project
(`torch==2.4.0`, `torchvision==0.19.0`, `monai==1.4.0`, `nibabel==5.2.1`,
`pytorch-ignite==0.4.11`, `tensorboard==2.17.0`) was changed, and nothing in
`backend/requirements.txt` (the core API's fastapi/pydicom/Pillow/numpy stack) was
touched or downgraded.

## H. What has actually been verified vs. what remains pending

**Verified during this integration** (see the conversation history for the exact
commands run):
- All of the above packages (torch 2.4.0, torchvision, monai 1.4.0, nibabel,
  pytorch-ignite, itk 5.4.0, SimpleITK 2.4.0) install together and import cleanly in a
  Python 3.12 virtual environment.
- `torch.cuda.is_available()` correctly returns `False` in a CPU-only environment,
  confirming the CPU-fallback code path is reachable rather than assumed.
- A real bug was caught this way: MONAI 1.4.0 does not export `RetinaNet` from
  `monai.networks.nets` as the bundle's own doc examples might suggest -- it lives in
  `monai.apps.detection.networks.retinanet_network`. This was fixed in `model.py`
  before it could reach you as a runtime `ImportError`.
- All backend Python files compile cleanly (`python -m py_compile`).

**Not verified, because no sample DICOM CT was provided in either source ZIP:**
- A full model build (`LungNoduleModel.__init__`) has not been executed end-to-end
  after the `RetinaNet` import fix -- only its imports and structure were reviewed.
- No real (or synthetic) inference has been run, so no detection box, confidence
  score, or slice mapping produced by this code has actually been observed.
- The DICOM series -> NIfTI conversion has not been exercised against real DICOM
  files, so slice ordering/orientation/spacing fidelity is verified by design and code
  review (SimpleITK's `ImageSeriesReader` is a standard, well-tested tool for this) but
  not by an observed test result.
- The frontend card and slice overlay have not been exercised against a running
  backend + browser (no `npm install`/`npm run dev` was executed for this delivery, at
  your explicit request).

**Recommended before relying on results:** follow the "Safe activation checklist" in
`MODEL_INSTALL.md` -- install the environment, then upload a real de-identified DICOM
CT series and run detection once, checking that boxes land on plausible anatomy on the
slice indicated.

## I. Medical safety (Phase 13)

The word "diagnosis" and phrases implying clinical confirmation are not used anywhere
in the new backend or frontend code. All lung-nodule output is labeled "Lung nodule
detection result" / "candidate nodule(s) detected," carries a
"Research prototype only... not a diagnosis" disclaimer in both the API response and
the UI card, and the bundle's own documented eval metrics (mAP/mAR on LUNA16) are
surfaced from `metadata.json` rather than invented or restated as clinical performance.
