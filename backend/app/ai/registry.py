"""AI pipeline registry.

Each pipeline declares its own metadata (anatomy, modalities, model info)
and an `available()`/`status_reason()` pair that reports the *truth* about
whether inference can actually run right now -- mirroring the fail-closed
philosophy already used by the lung nodule model's status endpoint.

Adding a new pipeline means adding one entry here (and, if it does real
inference, a small adapter module under app/ai/pipelines/). Nothing in the
frontend needs to hard-code pipeline capabilities: it discovers all of this
from GET /api/ai/pipelines.
"""

from __future__ import annotations

from ..lung_nodule import service as lung_nodule_service
from .schemas import PipelineInfo


def _lung_nodule_pipeline() -> PipelineInfo:
    status = lung_nodule_service.get_status()
    return PipelineInfo(
        pipeline_id="lung_nodule_ct",
        display_name="Lung Nodule Detection",
        anatomy="Chest / Lung",
        modalities=["CT"],
        model_name=status.get("model_name", "Lung nodule CT detection"),
        model_version=status.get("metadata_version"),
        available=status["available"],
        can_run_inference=status["available"],
        status_reason="Model available and ready for inference." if status["available"]
            else ("; ".join(status["reasons"]) or "Model is not available."),
        inference_capability="3D detection (bounding box)",
        description="MONAI Model Zoo lung_nodule_ct_detection (RetinaNet, trained on LUNA16). Research prototype, not a diagnosis.",
    )


def _brain_pipeline() -> PipelineInfo:
    # No trained brain model ships with this project. The pipeline is
    # registered so the platform's architecture and UI honestly represent it
    # as "supported" while being explicit that inference is not currently
    # available -- per the "pipeline supported" vs "model currently
    # available" distinction required for this platform.
    return PipelineInfo(
        pipeline_id="brain_imaging",
        display_name="Brain Imaging Pipeline",
        anatomy="Brain",
        modalities=["CT", "MR"],
        model_name="Not configured",
        model_version=None,
        available=False,
        can_run_inference=False,
        status_reason="No brain imaging model is currently installed on this server. The pipeline is registered and architecturally supported, but inference cannot run until a model is added.",
        inference_capability="Not available",
        description="Reserved pipeline for brain CT/MRI analysis (e.g. lesion or hemorrhage detection). Add a model under backend/app/ai/pipelines/brain.py to enable inference.",
    )


def list_pipelines() -> list[PipelineInfo]:
    return [_lung_nodule_pipeline(), _brain_pipeline()]


def get_pipeline(pipeline_id: str) -> PipelineInfo | None:
    for p in list_pipelines():
        if p.pipeline_id == pipeline_id:
            return p
    return None


# Modality/anatomy -> compatible pipeline ids. Used to recommend a pipeline
# from real DICOM metadata (see app/ai/service.py: recommend_pipeline).
COMPATIBILITY = [
    {"modality": "CT", "body_part_contains": ("CHEST", "LUNG", "THORAX"), "pipeline_id": "lung_nodule_ct"},
    {"modality": "CT", "body_part_contains": ("BRAIN", "HEAD", "SKULL"), "pipeline_id": "brain_imaging"},
    {"modality": "MR", "body_part_contains": ("BRAIN", "HEAD", "SKULL"), "pipeline_id": "brain_imaging"},
]


def recommend_pipeline(modality: str, body_part: str) -> dict:
    """Recommend a pipeline for the given real DICOM modality/body-part.

    Returns a structured, honest result rather than guessing: if nothing
    matches, or the match is uncertain, that is reported explicitly.
    """
    modality = (modality or "").upper().strip()
    body_part = (body_part or "").upper().strip()

    matches = [
        c for c in COMPATIBILITY
        if c["modality"] == modality and any(k in body_part for k in c["body_part_contains"])
    ]

    if not matches:
        return {
            "recommended_pipeline": None,
            "reason": f"No AI pipeline is registered for modality '{modality or 'Not available'}' "
                      f"and body region '{body_part or 'Not available'}'.",
            "compatible_pipelines": [],
        }

    compatible_ids = [m["pipeline_id"] for m in matches]
    pipelines = [get_pipeline(pid) for pid in compatible_ids]
    pipelines = [p for p in pipelines if p is not None]
    best = pipelines[0]
    return {
        "recommended_pipeline": best.pipeline_id,
        "reason": f"Modality '{modality}' and body region '{body_part}' match the {best.display_name} pipeline.",
        "compatible_pipelines": [p.pipeline_id for p in pipelines],
    }
