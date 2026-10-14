# Data provenance

This document records the real source, license, and status of every dataset touched by this
project: the model's training data, and any DICOM data used to test the application during
development. No patient data, real clinical studies, or fabricated metadata are used anywhere.

## Model training data

**Dataset:** LUNA16 (LUng Nodule Analysis 2016)
**Used by:** the `lung_nodule_ct_detection` MONAI Model Zoo bundle (see `MODEL_EVALUATION.md`)
**Source:** https://luna16.grand-challenge.org/, derived from the public LIDC-IDRI collection
**License/terms:** LUNA16 data use terms as published on the challenge site; this project does not
redistribute LUNA16 data — only the resulting trained model weights, downloaded from the official
MONAI Model Zoo bundle release, are used.
**Note:** this project did not train or fine-tune the model. All claims about the model's task,
accuracy, and behavior come from the bundle's own published metadata, not from independent
validation by this project.

## Test data used during development (this repository does not ship any patient data)

No DICOM files are bundled with this repository. During development, two real DICOM test datasets
were used locally to validate the pipeline; neither is committed to this repository, and a fresh
clone/install of this project starts with zero studies (see `DASHBOARD` section of `README.md`:
an empty database reports all-zero counts).

### 1. pydicom test data (`CT_small.dcm`)

- **Source:** ships with the `pydicom` Python package (`pydicom.data.get_testdata_file`), from
  https://github.com/pydicom/pydicom
- **License:** pydicom's test data is distributed under pydicom's own license (MIT-style); see the
  pydicom repository for exact terms.
- **Content:** a single anonymized CT slice, used only to validate DICOM upload, parsing, and the
  single-slice/"3D volume required" honest-abstention path (a single slice cannot form a 3D volume).
- **Not used for:** any 3D inference, since it is a single instance.

### 2. `dcm_qa_ct` (GE HiSpeed Dual series)

- **Source:** https://github.com/neurolabusc/dcm_qa_ct, a public repository of real, anonymized
  DICOM CT series maintained for regression-testing DICOM-to-NIfTI converters (e.g. `dcm2niix`).
- **Series used:** `In/GE/` — 28 slices, GE HiSpeed Dual scanner, variable inter-slice spacing
  (documented by the repository as 1.08–6.99 mm), contributed to the repository (per its README)
  by Aliza Medical Imaging's public sample-dataset page.
- **License:** no separate license file is published in the repository at the time of writing;
  the dataset is maintained specifically for public use in testing DICOM software. This project
  does not redistribute the data — it was fetched directly from the public repository for a local,
  one-time pipeline verification and is not included in this codebase.
- **Patient data:** `PatientName`/`PatientID` fields in this dataset are already anonymized
  ("REMOVED", pseudonymous ID) by the source repository. This project's own de-identification
  posture (see `README.md` "De-identification" section) applies on top of that regardless.
- **Used for:** a genuine, documented end-to-end pipeline test (DICOM ingestion → eligibility gate
  → 3D volume construction → model loading → preprocessing). See `MODEL_EVALUATION.md`, "Update 2,"
  for exactly what was and was not verified using this series.

## What this project does NOT do

- It does not fabricate patient names, ages, MRNs, or accession numbers for demo purposes.
- It does not claim FDA clearance, CE marking, or clinical validation for any model.
- It does not present LUNA16 training performance as if it were validated on this project's own
  test data — no such validation has been performed.
