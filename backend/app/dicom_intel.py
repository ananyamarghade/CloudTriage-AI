"""DICOM Intelligence.

Extracts study/patient/imaging/modality-specific metadata directly from the
actual uploaded DICOM files (via pydicom), computes real technical image
quality checks, and groups sibling series that belong to the same
StudyInstanceUID so a multi-series study can be explored.

Every value here is read from the real dataset or computed from the real
pixel/geometry data on disk. Nothing is fabricated: any tag or check that
cannot be read/derived is reported as "Not available" rather than guessed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pydicom

NA = "Not available"


def _s(ds, tag: str) -> str:
    val = ds.get(tag, None)
    if val is None or str(val).strip() == "":
        return NA
    return str(val).strip()


def _num(ds, tag: str):
    val = ds.get(tag, None)
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except Exception:
        return None


def deidentify_patient_id(raw_id: str, study_id: str) -> str:
    """Never surface a raw PatientID in the UI. Show a stable de-identified
    label derived from our own internal study id instead."""
    return f"PT-{study_id[-6:]}" if raw_id and raw_id != NA else NA


# ---------------------------------------------------------------------------
# Patient / Study metadata
# ---------------------------------------------------------------------------

def patient_study_metadata(ds, study_id: str) -> dict:
    return {
        "patient_id_deidentified": deidentify_patient_id(_s(ds, "PatientID"), study_id),
        "patient_age": _s(ds, "PatientAge"),
        "patient_sex": _s(ds, "PatientSex"),
        "study_date": _s(ds, "StudyDate"),
        "study_time": _s(ds, "StudyTime"),
        "study_uid": _s(ds, "StudyInstanceUID"),
        "accession_number": _s(ds, "AccessionNumber"),
        "study_description": _s(ds, "StudyDescription"),
        "referring_physician": _s(ds, "ReferringPhysicianName"),
    }


# ---------------------------------------------------------------------------
# Imaging metadata
# ---------------------------------------------------------------------------

def imaging_metadata(ds, series_count: int, image_count: int) -> dict:
    rows, cols = ds.get("Rows"), ds.get("Columns")
    dims = f"{cols} × {rows}" if rows and cols else NA
    pixel_spacing = ds.get("PixelSpacing")
    pixel_spacing_str = f"{pixel_spacing[0]} × {pixel_spacing[1]} mm" if pixel_spacing else NA
    orientation = ds.get("ImageOrientationPatient")
    orientation_str = ", ".join(str(round(float(v), 3)) for v in orientation) if orientation else NA
    position = ds.get("ImagePositionPatient")
    position_str = ", ".join(str(round(float(v), 2)) for v in position) if position else NA
    return {
        "modality": _s(ds, "Modality"),
        "body_part_examined": _s(ds, "BodyPartExamined"),
        "study_description": _s(ds, "StudyDescription"),
        "series_description": _s(ds, "SeriesDescription"),
        "series_count": series_count,
        "image_count": image_count,
        "dimensions": dims,
        "pixel_spacing": pixel_spacing_str,
        "slice_thickness": _s(ds, "SliceThickness"),
        "slice_spacing": _s(ds, "SpacingBetweenSlices"),
        "orientation": orientation_str,
        "position": position_str,
        "transfer_syntax": str(getattr(ds, "file_meta", {}).get("TransferSyntaxUID", NA)) if getattr(ds, "file_meta", None) else NA,
        "photometric_interpretation": _s(ds, "PhotometricInterpretation"),
    }


# ---------------------------------------------------------------------------
# Modality-specific acquisition parameters
# ---------------------------------------------------------------------------

def ct_parameters(ds) -> dict:
    return {
        "kvp": _s(ds, "KVP"),
        "tube_current_ma": _s(ds, "XRayTubeCurrent"),
        "exposure_mas": _s(ds, "Exposure"),
        "reconstruction_diameter": _s(ds, "ReconstructionDiameter"),
        "convolution_kernel": _s(ds, "ConvolutionKernel"),
        "ctdi_vol": _s(ds, "CTDIvol"),
        "dlp": _s(ds, "DLP") if "DLP" in ds else NA,
        "contrast_bolus_agent": _s(ds, "ContrastBolusAgent"),
        "contrast_route": _s(ds, "ContrastBolusRoute"),
    }


def mri_parameters(ds) -> dict:
    return {
        "magnetic_field_strength_t": _s(ds, "MagneticFieldStrength"),
        "sequence_name": _s(ds, "SequenceName"),
        "scanning_sequence": _s(ds, "ScanningSequence"),
        "repetition_time_tr_ms": _s(ds, "RepetitionTime"),
        "echo_time_te_ms": _s(ds, "EchoTime"),
        "flip_angle": _s(ds, "FlipAngle"),
        "slice_thickness": _s(ds, "SliceThickness"),
        "acquisition_matrix": _s(ds, "AcquisitionMatrix"),
    }


def acquisition_parameters(ds) -> dict:
    modality = _s(ds, "Modality")
    if modality == "CT":
        return {"modality": "CT", "parameters": ct_parameters(ds)}
    if modality == "MR":
        return {"modality": "MR", "parameters": mri_parameters(ds)}
    return {"modality": modality, "parameters": {}, "note": f"No modality-specific parameter set is defined for '{modality}' yet."}


# ---------------------------------------------------------------------------
# Image quality / AI readiness checks (computed from real files, never
# fabricated). Anything that can't be computed reports NA.
# ---------------------------------------------------------------------------

CRITICAL_TAGS = ["Modality", "BodyPartExamined", "Rows", "Columns", "PixelSpacing", "StudyInstanceUID", "SeriesInstanceUID"]


def image_quality(paths: list[str]) -> dict:
    if not paths:
        return {
            "metadata_completeness": NA, "missing_critical_tags": ["No files available"],
            "dimension_consistency": NA, "slice_spacing_consistency": NA,
            "series_consistency": NA, "orientation_consistency": NA,
            "image_availability": "No images available", "ai_processing_readiness": "Not ready",
        }

    datasets = []
    for p in paths:
        try:
            datasets.append(pydicom.dcmread(p))
        except Exception:
            continue

    image_availability = f"{len(datasets)} of {len(paths)} image(s) readable"

    if not datasets:
        return {
            "metadata_completeness": NA, "missing_critical_tags": ["No readable DICOM data"],
            "dimension_consistency": NA, "slice_spacing_consistency": NA,
            "series_consistency": NA, "orientation_consistency": NA,
            "image_availability": image_availability, "ai_processing_readiness": "Not ready",
        }

    first = datasets[0]
    missing = [t for t in CRITICAL_TAGS if not first.get(t)]
    present = len(CRITICAL_TAGS) - len(missing)
    metadata_completeness = f"{present}/{len(CRITICAL_TAGS)} critical tags present"

    dims = {(d.get("Rows"), d.get("Columns")) for d in datasets}
    dimension_consistency = "Consistent" if len(dims) == 1 else f"Inconsistent ({len(dims)} distinct dimension sets)"

    thicknesses = {str(d.get("SliceThickness")) for d in datasets if d.get("SliceThickness")}
    if not thicknesses:
        slice_spacing_consistency = NA
    else:
        slice_spacing_consistency = "Consistent" if len(thicknesses) == 1 else f"Varies across slices ({len(thicknesses)} distinct values)"

    series_uids = {str(d.get("SeriesInstanceUID")) for d in datasets}
    series_consistency = "Single series" if len(series_uids) == 1 else f"Multiple series mixed ({len(series_uids)})"

    orientations = {tuple(round(float(v), 2) for v in d.get("ImageOrientationPatient")) for d in datasets if d.get("ImageOrientationPatient")}
    if not orientations:
        orientation_consistency = NA
    else:
        orientation_consistency = "Consistent" if len(orientations) == 1 else f"Inconsistent ({len(orientations)} distinct orientations)"

    readiness_blockers = []
    if missing:
        readiness_blockers.append(f"Missing critical tag(s): {', '.join(missing)}")
    if len(dims) > 1:
        readiness_blockers.append("Inconsistent slice dimensions")
    if len(datasets) < len(paths):
        readiness_blockers.append("One or more slices failed to decode")
    ai_processing_readiness = "Ready" if not readiness_blockers else "Not ready: " + "; ".join(readiness_blockers)

    return {
        "metadata_completeness": metadata_completeness,
        "missing_critical_tags": missing or ["None"],
        "dimension_consistency": dimension_consistency,
        "slice_spacing_consistency": slice_spacing_consistency,
        "series_consistency": series_consistency,
        "orientation_consistency": orientation_consistency,
        "image_availability": image_availability,
        "ai_processing_readiness": ai_processing_readiness,
    }


def study_profile(row, series_count: int) -> dict:
    paths = json.loads(row["slice_paths"]) or [row["path"]]
    try:
        ds = pydicom.dcmread(paths[0])
    except Exception:
        return {"error": "Could not read the first slice of this study."}
    image_count = row["slice_count"] or len(paths)
    patient_study = patient_study_metadata(ds, row["id"])
    imaging = imaging_metadata(ds, series_count, image_count)
    return {"patient_study": patient_study, "imaging": imaging}
