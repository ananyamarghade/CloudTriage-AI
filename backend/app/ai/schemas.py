"""Common schemas shared by every AI pipeline in the platform.

The viewer and analytics pages consume these generic shapes rather than
pipeline-specific ones, so a new pipeline (e.g. brain MRI) can be added
without teaching the frontend new terminology.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PipelineInfo(BaseModel):
    pipeline_id: str
    display_name: str
    anatomy: str
    modalities: list[str]
    model_name: str
    model_version: Optional[str] = None
    available: bool
    can_run_inference: bool
    status_reason: str
    inference_capability: str  # e.g. "detection", "segmentation", "classification"
    description: str


class Finding(BaseModel):
    label: str
    confidence: Optional[float] = None
    severity: Optional[str] = None
    slice_index: Optional[int] = None
    bounding_box: Optional[dict] = None
    mask: Optional[dict] = None
    point: Optional[dict] = None


class AIAnalysisResult(BaseModel):
    pipeline_id: str
    pipeline_name: str
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    anatomy: str
    modality: str
    status: str  # "completed" | "failed" | "unsupported_input" | "inference_unavailable"
    findings: list[Finding] = []
    confidence_summary: Optional[float] = None
    processing_time_seconds: Optional[float] = None
    limitations: list[str] = []
    reason: Optional[str] = None
    timestamp: str
