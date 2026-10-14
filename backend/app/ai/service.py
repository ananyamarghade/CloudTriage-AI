"""Generic AI analysis service.

Dispatches a run request to the correct pipeline implementation and always
returns the standardized AIAnalysisResult structure, so the viewer and
analytics never need to know pipeline-specific result shapes.

The existing lung nodule implementation (app/lung_nodule) is reused as-is --
this module only adapts its input/output shape, it does not reimplement or
alter the model.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..lung_nodule import service as lung_nodule_service
from . import registry
from .schemas import AIAnalysisResult, Finding


class PipelineNotFoundError(Exception):
    pass


class PipelineUnavailableError(Exception):
    """Raised when a pipeline is registered but cannot run inference right
    now (e.g. no model installed). Callers should surface this as a clear,
    honest UI state rather than a generic 500 error."""

    def __init__(self, result: AIAnalysisResult):
        self.result = result
        super().__init__(result.reason or "Pipeline unavailable")


def eligibility(pipeline_id: str, dicom_paths: list[str], modality: str) -> dict:
    pipeline = registry.get_pipeline(pipeline_id)
    if pipeline is None:
        raise PipelineNotFoundError(pipeline_id)
    if pipeline_id == "lung_nodule_ct":
        return lung_nodule_service.check_eligibility(dicom_paths, modality)
    # Pipelines with no runnable model yet: eligibility is a single honest
    # check rather than fabricated pre-flight detail.
    return {
        "ready": False,
        "checks": [{
            "name": "Model available on this server",
            "passed": False,
            "detail": pipeline.status_reason,
        }],
    }


def run(pipeline_id: str, study_id: str, dicom_paths: list[str], modality: str, body_region: str) -> tuple[AIAnalysisResult, dict | None]:
    """Run a pipeline. Returns (standardized_result, raw_provenance_or_None).

    Raises PipelineNotFoundError / PipelineUnavailableError / the pipeline's
    own detection error type (LungNoduleDetectionError today) on failure --
    callers translate these into HTTP responses exactly like the existing
    dedicated lung-nodule endpoint does.
    """
    pipeline = registry.get_pipeline(pipeline_id)
    if pipeline is None:
        raise PipelineNotFoundError(pipeline_id)

    if pipeline_id == "lung_nodule_ct":
        raw = lung_nodule_service.detect_from_slice_paths(dicom_paths)
        findings = [
            Finding(
                label=n["class_name"],
                confidence=n["confidence"],
                slice_index=n["location"]["slice_index"],
                bounding_box=n["location"]["pixel_bbox"],
                point=n["location"]["pixel"],
            )
            for n in raw["nodules"]
        ]
        provenance = raw.get("provenance", {})
        result = AIAnalysisResult(
            pipeline_id=pipeline_id,
            pipeline_name=pipeline.display_name,
            model_name=provenance.get("model_name"),
            model_version=provenance.get("model_version"),
            anatomy=pipeline.anatomy,
            modality=modality or "CT",
            status="completed",
            findings=findings,
            confidence_summary=max((f.confidence for f in findings), default=None),
            processing_time_seconds=provenance.get("duration_seconds"),
            limitations=["Not clinically validated", "Human review remains required"],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return result, provenance

    # Any pipeline registered but without a runnable model (e.g. brain).
    result = AIAnalysisResult(
        pipeline_id=pipeline_id,
        pipeline_name=pipeline.display_name,
        model_name=pipeline.model_name,
        model_version=pipeline.model_version,
        anatomy=pipeline.anatomy,
        modality=modality or "Not available",
        status="inference_unavailable",
        findings=[],
        limitations=[],
        reason=pipeline.status_reason,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    raise PipelineUnavailableError(result)


def ai_readiness(modality: str, body_region: str) -> dict:
    rec = registry.recommend_pipeline(modality, body_region)
    pipelines = registry.list_pipelines()
    compatible = [p for p in pipelines if p.pipeline_id in rec["compatible_pipelines"]]
    return {
        "detected_modality": modality or "Not available",
        "detected_anatomy": body_region or "Not available",
        "compatible_pipelines": [p.model_dump() for p in compatible],
        "recommended_pipeline": rec["recommended_pipeline"],
        "reason": rec["reason"],
    }
