"""Generic AI pipeline architecture.

This package lets the platform host more than one AI pipeline (the existing
lung nodule MONAI model is one of several) behind a single, generic
interface: a registry of pipelines (metadata + availability), a router that
picks a pipeline for a given modality/anatomy, common result schemas, and an
analysis service that dispatches a run to the right pipeline implementation.

Nothing here changes how the existing lung nodule model works internally --
it is wrapped, not rewritten (see app/ai/pipelines/lung_nodule.py).
"""
