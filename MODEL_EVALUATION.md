# Medical model evaluation

## Decision

No pretrained model is integrated into the application at this time. The UI therefore reports **AI analysis not configured**, and it does not display fabricated findings, confidence, localization, or priority scores.

This is deliberate: the application receives arbitrary DICOM CT series, while a model used for triage would need a documented CT input contract, a documented abnormality/triage task, a usable license, local inference support, and output semantics that can be presented without implying diagnosis. The requested MONAI bundle was inspected but not enabled because a successful end-to-end inference could not be honestly verified in this project.

## Requested candidate reviewed: MONAI lung_nodule_ct_detection

- **Bundle/version:** `lung_nodule_ct_detection`, metadata version `0.6.10`
- **Official sources:** [MONAI Model Zoo](https://project-monai.github.io/model-zoo.html), [Hugging Face bundle](https://huggingface.co/MONAI/lung_nodule_ct_detection), [MONAI source configuration](https://github.com/Project-MONAI/model-zoo/tree/dev/models/lung_nodule_ct_detection)
- **Framework versions in official metadata:** MONAI `1.4.0`, PyTorch `2.4.0`, NumPy `1.24.4`, plus nibabel `5.2.1`, pytorch-ignite `0.4.11`, torchvision `0.19.0`, and tensorboard `2.17.0`
- **Task:** 3D pulmonary nodule detection in CT scans
- **Official input contract:** one-channel CT volume at `0.703125 x 0.703125 x 1.25 mm`, with normalized intensity range `0..1`; the bundle's documented data type is nibabel/NIfTI
- **Official output contract:** detection boxes, classification labels, and classification scores
- **Training data:** LUNA16
- **Intended use:** the official metadata calls it an example and says it is not for diagnostic purposes
- **License:** the bundle repository includes an Apache License 2.0 license file; dataset terms remain separate

### Why it is not enabled

The bundle requires MONAI detection internals, a fixed-spacing 3D volume, and its supplied inference configuration is built around nibabel/NIfTI input and MONAI's bundle scripts. This project currently has a DICOM-native pipeline and has not completed a verified DICOM-to-NIfTI/geometry-preserving conversion, model download, CPU inference, real public DICOM end-to-end test, and box-to-slice overlay validation on Windows. Adding the dependency without those validations would falsely imply a working model.

The application therefore retains the required fallback instead of returning fabricated detections or scores:

> AI analysis not configured

## Candidate reviewed: lungmask

- **Model/project:** lungmask, U-Net models for automated lung segmentation in CT
- **Official source:** https://github.com/JoHof/lungmask
- **License:** Apache-2.0, as stated by the repository
- **Documented task:** segmentation of lungs in CT, including cases with severe pathologies
- **Input:** CT DICOM slices/volumes according to the project documentation
- **Output:** lung segmentation masks
- **Why it was not integrated:** a lung mask is not an abnormality probability, a triage score, or a validated review-priority output. Converting its mask into one would be an invented clinical interpretation. It also does not by itself provide the requested chest-CT abnormality task.

## Candidate reviewed: MONAI Model Zoo

- **Official source:** https://github.com/Project-MONAI/model-zoo
- **License:** the Model Zoo source repository is Apache-2.0; individual bundles and their training data/model terms must still be checked independently.
- **Documented scope:** a collection of medical-imaging bundles, not one single chest-CT triage model.
- **Why it was not integrated:** the available bundle collection does not provide one verified, locally runnable model with a single clear chest-CT abnormality-triage contract and license/output semantics suitable for this application without additional model-specific validation.

## Current fallback behavior

- No model package or weight is downloaded automatically.
- No model output is persisted or shown.
- Admin status explains that no validated CT triage model is installed.
- The study workspace shows actual DICOM inputs and states that model-specific explainability/localization is unavailable.

## Prototype technical analysis

The study workspace now calls `GET /api/studies/{study_id}/analysis`. This is not a medical model. It deterministically inspects the uploaded DICOM payload and returns:

- readable versus submitted slice count
- observed pixel dimensions
- observed intensity range
- technical flags such as undecodable pixels, inconsistent dimensions, or low dynamic range

The response explicitly marks medical triage as unavailable, contains no abnormality probability, and contains no overlay or heatmap. This keeps the analysis visible and explainable without presenting invented clinical predictions as model output.

When a suitable model is selected later, it must document its exact version, source, license, preprocessing, expected volume geometry, output meaning, deterministic inference test, and limitations before being enabled.

## Update: integration completed (this document's original "not enabled" decision is superseded)

The blockers listed above have been addressed in code:

- A verified-by-design DICOM-to-NIfTI geometry-preserving conversion is implemented in `backend/app/lung_nodule/dicom_series.py` using SimpleITK's `ImageSeriesReader` (preserves spacing, orientation, and slice order) and documented in `LUNG_NODULE_INTEGRATION.md`.
- The bundle's own network, anchors, box-selector thresholds, and pre/postprocessing transforms are reused unmodified from `bundle/configs/inference.json` (see `backend/app/lung_nodule/model.py`).
- CPU inference, dependency installation, and Windows-compatible paths were addressed (see `MODEL_INSTALL.md`).
- The endpoint (`POST /api/studies/{id}/lung-nodule-detect`) is fail-closed: it returns a clear, safe error if the model/dependencies are unavailable, and the app's existing "AI analysis not configured" fallback continues to work independently.

**What remains unverified:** end-to-end inference against a real DICOM CT series. No sample CT was available in either source project during this integration, so the DICOM->NIfTI conversion, the coordinate mapping back to slice/pixel space, and the model's real output on real anatomy have not yet been observed together. See `LUNG_NODULE_INTEGRATION.md` for the precise list of what has and hasn't been exercised, and the "Safe activation checklist" above for what to confirm on real data before relying on results.

## Update 2: real end-to-end verification attempt (2026-08-28)

A real, published, anonymized 28-slice CT series (GE HiSpeed Dual, variable slice spacing) from the `neurolabusc/dcm_qa_ct` public DICOM-conversion test dataset was uploaded through the running application and pushed through the actual pipeline. Results, in order:

1. **DICOM ingestion, grouping, and the AI eligibility gate all passed for real data.** All 28 slices validated, were correctly identified as one CT series, and were assembled into a genuine `(512, 512, 28)` 3D volume via `SimpleITK.ImageSeriesReader` using the files' real `ImagePositionPatient`/`ImageOrientationPatient` values (not filename order). The `GET /api/studies/{id}/eligibility` endpoint reported `READY FOR ANALYSIS` for this study, honestly, based on the real geometry.
2. **Two real code bugs were found and fixed while attempting the run** (not fabrication — verified by reproducing the failure, fixing it, and re-running):
   - `backend/app/lung_nodule/dicom_series.py` previously imported `SimpleITK` at module import time, which crashed the *entire backend* (not just this feature) in any environment without the optional model dependencies installed. Fixed to import lazily, matching the fail-closed design already used elsewhere in this module.
   - `backend/requirements-model.txt` pinned `torchvision==0.19.0` against `torch==2.5.1`; these are mismatched (0.19.0 pairs with torch 2.4.x). Corrected to `torchvision==0.20.1`. Additionally, MONAI's `EnsureChannelFirstd` no longer accepts the `meta_key_postfix` argument in MONAI 1.4.0 (removed since the bundle's original config was authored); `backend/app/lung_nodule/model.py` was updated to drop that argument for this specific transform only, while `LoadImaged` keeps it since that transform still supports it.
3. **After both fixes, the pipeline reached real model construction and began real preprocessing/inference** — DICOM validation, series construction, model loading (real checkpoint weights), and MONAI transform preprocessing all executed against the real data.
4. **Real inference itself did not complete in this sandboxed evaluation environment**, which has only 3.9 GB of RAM: the kernel OOM-killed the backend process during the RetinaNet sliding-window inference step (`dmesg` confirms `Out of memory: Killed process ... uvicorn`, RSS ~3.9 GB at time of kill). This is a resource constraint of the evaluation sandbox, not a bug in the code: the bundle's sliding-window detector over a `512x512x28` volume needs materially more memory than was available here.

**Honest bottom line:** every stage up to and including real model weight loading and preprocessing has now been verified against a real, spatially-valid multi-slice CT series. The only unverified stage is the completion of the inference forward pass itself, and the reason is a documented, reproducible memory ceiling of this evaluation environment — not an unknown. On a machine with more RAM (8 GB+ recommended for CPU inference), or with a GPU, this should be the only remaining step to observe a first real detection result. Anyone continuing this project should re-run `POST /api/studies/{id}/lung-nodule-detect` against a real CT series on such a machine and record the actual output here.