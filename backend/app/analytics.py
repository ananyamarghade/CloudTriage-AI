"""Analytics aggregation service.

Every function here queries the application's own SQLite tables
(studies/analyses/audit_logs/feedback) -- there is no synthetic or random
data anywhere in this module. If a table has no rows yet, callers get empty
lists/zero counts (a meaningful empty state), never fabricated numbers.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def _rows(c, sql, params=()):
    return [dict(r) for r in c.execute(sql, params).fetchall()]


def overview(c: sqlite3.Connection) -> dict:
    total_studies = c.execute("SELECT COUNT(*) n FROM studies").fetchone()["n"]
    today = datetime.now(timezone.utc).date().isoformat()
    studies_today = c.execute(
        "SELECT COUNT(*) n FROM studies WHERE substr(created_at,1,10)=?", (today,)
    ).fetchone()["n"]
    ai_completed = c.execute("SELECT COUNT(*) n FROM analyses WHERE status='COMPLETED'").fetchone()["n"]
    pending_analyses = c.execute("SELECT COUNT(*) n FROM studies WHERE ai_status='PROCESSING'").fetchone()["n"]
    avg_time_row = c.execute("SELECT AVG(duration_seconds) a FROM analyses WHERE status='COMPLETED' AND duration_seconds IS NOT NULL").fetchone()
    avg_processing_time = round(avg_time_row["a"], 2) if avg_time_row and avg_time_row["a"] is not None else None
    findings_detected = c.execute("SELECT COALESCE(SUM(nodule_count),0) n FROM analyses WHERE status='COMPLETED'").fetchone()["n"]

    by_modality = _rows(c, "SELECT COALESCE(NULLIF(modality,''),'Not available') AS label, COUNT(*) AS count FROM studies GROUP BY label ORDER BY count DESC")
    by_anatomy = _rows(c, "SELECT COALESCE(NULLIF(body_region,''),'Not available') AS label, COUNT(*) AS count FROM studies GROUP BY label ORDER BY count DESC")

    pipeline_utilization = _rows(
        c,
        "SELECT COALESCE(NULLIF(pipeline_id,''),'lung_nodule_ct') AS pipeline_id, COUNT(*) AS count "
        "FROM analyses GROUP BY pipeline_id ORDER BY count DESC",
    )

    recent_activity = _rows(c, "SELECT actor, action, detail, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 15")

    studies_over_time = _rows(
        c,
        "SELECT substr(created_at,1,10) AS date, COUNT(*) AS count FROM studies GROUP BY date ORDER BY date ASC",
    )

    return {
        "total_studies": total_studies,
        "studies_processed_today": studies_today,
        "ai_analyses_completed": ai_completed,
        "pending_analyses": pending_analyses,
        "average_processing_time_seconds": avg_processing_time,
        "findings_detected": findings_detected,
        "studies_by_modality": by_modality,
        "studies_by_anatomy": by_anatomy,
        "ai_pipeline_utilization": pipeline_utilization,
        "studies_over_time": studies_over_time,
        "recent_activity": recent_activity,
    }


def ai_analytics(c: sqlite3.Connection) -> dict:
    by_pipeline = _rows(
        c,
        "SELECT COALESCE(NULLIF(pipeline_id,''),'lung_nodule_ct') AS pipeline_id, COUNT(*) AS total, "
        "SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS succeeded, "
        "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed "
        "FROM analyses GROUP BY pipeline_id",
    )
    avg_inference = c.execute("SELECT AVG(duration_seconds) a FROM analyses WHERE duration_seconds IS NOT NULL").fetchone()
    model_usage = _rows(c, "SELECT COALESCE(NULLIF(model_name,''),'Not available') AS model_name, COUNT(*) AS count FROM analyses GROUP BY model_name ORDER BY count DESC")
    findings_by_pipeline = _rows(
        c,
        "SELECT COALESCE(NULLIF(pipeline_id,''),'lung_nodule_ct') AS pipeline_id, COALESCE(SUM(nodule_count),0) AS findings "
        "FROM analyses WHERE status='COMPLETED' GROUP BY pipeline_id",
    )
    recent_jobs = _rows(
        c,
        "SELECT id, study_id, COALESCE(NULLIF(pipeline_id,''),'lung_nodule_ct') AS pipeline_id, model_name, status, "
        "nodule_count, duration_seconds, created_at FROM analyses ORDER BY created_at DESC LIMIT 20",
    )

    confidence_rows = _rows(c, "SELECT result_json FROM analyses WHERE status='COMPLETED' AND result_json IS NOT NULL")
    buckets = {"0-25%": 0, "25-50%": 0, "50-75%": 0, "75-100%": 0}
    for row in confidence_rows:
        try:
            data = json.loads(row["result_json"])
            for n in data.get("nodules", []):
                conf = n.get("confidence")
                if conf is None:
                    continue
                pct = conf * 100
                if pct < 25:
                    buckets["0-25%"] += 1
                elif pct < 50:
                    buckets["25-50%"] += 1
                elif pct < 75:
                    buckets["50-75%"] += 1
                else:
                    buckets["75-100%"] += 1
        except Exception:
            continue

    return {
        "analyses_by_pipeline": by_pipeline,
        "average_inference_time_seconds": round(avg_inference["a"], 2) if avg_inference and avg_inference["a"] is not None else None,
        "model_usage": model_usage,
        "findings_by_pipeline": findings_by_pipeline,
        "confidence_distribution": [{"bucket": k, "count": v} for k, v in buckets.items()],
        "recent_ai_jobs": recent_jobs,
    }


def imaging_analytics(c: sqlite3.Connection) -> dict:
    by_modality = _rows(c, "SELECT COALESCE(NULLIF(modality,''),'Not available') AS label, COUNT(*) AS count FROM studies GROUP BY label ORDER BY count DESC")
    by_anatomy = _rows(c, "SELECT COALESCE(NULLIF(body_region,''),'Not available') AS label, COUNT(*) AS count FROM studies GROUP BY label ORDER BY count DESC")
    volume_over_time = _rows(c, "SELECT substr(created_at,1,10) AS date, COUNT(*) AS count FROM studies GROUP BY date ORDER BY date ASC")
    series_counts = c.execute("SELECT COUNT(DISTINCT series_uid) n FROM studies WHERE series_uid IS NOT NULL AND series_uid != ''").fetchone()["n"]
    total_slices = c.execute("SELECT COALESCE(SUM(slice_count),0) n FROM studies").fetchone()["n"]
    by_status = _rows(c, "SELECT status AS label, COUNT(*) AS count FROM studies GROUP BY status")

    return {
        "studies_by_modality": by_modality,
        "studies_by_anatomy": by_anatomy,
        "study_volume_over_time": volume_over_time,
        "distinct_series_count": series_counts,
        "total_images_slices": total_slices,
        "study_status": by_status,
    }


def findings_analytics(c: sqlite3.Connection, filters: dict) -> dict:
    where = ["a.status='COMPLETED'", "a.result_json IS NOT NULL"]
    params: list = []
    if filters.get("date_from"):
        where.append("a.created_at >= ?"); params.append(filters["date_from"])
    if filters.get("date_to"):
        where.append("a.created_at <= ?"); params.append(filters["date_to"])
    if filters.get("pipeline"):
        where.append("COALESCE(NULLIF(a.pipeline_id,''),'lung_nodule_ct') = ?"); params.append(filters["pipeline"])
    if filters.get("modality"):
        where.append("s.modality = ?"); params.append(filters["modality"])
    if filters.get("anatomy"):
        where.append("s.body_region = ?"); params.append(filters["anatomy"])

    sql = f"""SELECT a.id, a.study_id, a.result_json, a.created_at, a.pipeline_id, s.modality, s.body_region
              FROM analyses a JOIN studies s ON s.id = a.study_id
              WHERE {' AND '.join(where)} ORDER BY a.created_at DESC"""
    rows = _rows(c, sql, params)

    findings = []
    for row in rows:
        try:
            data = json.loads(row["result_json"])
        except Exception:
            continue
        for n in data.get("nodules", []):
            if filters.get("finding_type") and n.get("class_name") != filters["finding_type"]:
                continue
            findings.append({
                "study_id": row["study_id"],
                "type": n.get("class_name"),
                "anatomy": row["body_region"],
                "modality": row["modality"],
                "pipeline_id": row["pipeline_id"] or "lung_nodule_ct",
                "confidence": n.get("confidence"),
                "created_at": row["created_at"],
            })

    by_type: dict = {}
    by_anatomy: dict = {}
    by_pipeline: dict = {}
    for f in findings:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        by_anatomy[f["anatomy"] or "Not available"] = by_anatomy.get(f["anatomy"] or "Not available", 0) + 1
        by_pipeline[f["pipeline_id"]] = by_pipeline.get(f["pipeline_id"], 0) + 1

    over_time: dict = {}
    for f in findings:
        d = (f["created_at"] or "")[:10]
        over_time[d] = over_time.get(d, 0) + 1

    return {
        "total_findings": len(findings),
        "findings_by_type": [{"label": k, "count": v} for k, v in by_type.items()],
        "findings_by_anatomy": [{"label": k, "count": v} for k, v in by_anatomy.items()],
        "findings_by_pipeline": [{"label": k, "count": v} for k, v in by_pipeline.items()],
        "findings_over_time": [{"date": k, "count": v} for k, v in sorted(over_time.items())],
        "recent_findings": findings[:25],
    }


def performance_analytics(c: sqlite3.Connection) -> dict:
    succeeded = c.execute("SELECT COUNT(*) n FROM analyses WHERE status='COMPLETED'").fetchone()["n"]
    failed = c.execute("SELECT COUNT(*) n FROM analyses WHERE status='FAILED'").fetchone()["n"]
    pending = c.execute("SELECT COUNT(*) n FROM studies WHERE ai_status='PROCESSING'").fetchone()["n"]
    avg_proc = c.execute("SELECT AVG(duration_seconds) a FROM analyses WHERE duration_seconds IS NOT NULL").fetchone()
    throughput = _rows(c, "SELECT substr(created_at,1,10) AS date, COUNT(*) AS count FROM analyses GROUP BY date ORDER BY date ASC")
    recent_events = _rows(
        c,
        "SELECT id, study_id, status, duration_seconds, COALESCE(NULLIF(pipeline_id,''),'lung_nodule_ct') AS pipeline_id, created_at "
        "FROM analyses ORDER BY created_at DESC LIMIT 20",
    )
    return {
        "successful_jobs": succeeded,
        "failed_jobs": failed,
        "pending_jobs": pending,
        "average_processing_time_seconds": round(avg_proc["a"], 2) if avg_proc and avg_proc["a"] is not None else None,
        "throughput_by_day": throughput,
        "recent_processing_events": recent_events,
    }


def audit_analytics(c: sqlite3.Connection) -> dict:
    recent = _rows(c, "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 50")
    by_action = _rows(c, "SELECT action, COUNT(*) AS count FROM audit_logs GROUP BY action ORDER BY count DESC")
    ai_events = _rows(
        c,
        "SELECT * FROM audit_logs WHERE action LIKE 'AI_%' ORDER BY created_at DESC LIMIT 25",
    )
    return {
        "recent_events": recent,
        "events_by_type": by_action,
        "ai_inference_events": ai_events,
    }
