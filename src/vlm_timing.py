"""Persistent, per-request latency measurements for VLM calls."""

import json
import logging
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


_OUTPUT_PATH = None
_RECORDS = []
_METADATA = {}
_STARTED_AT = None


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def configure_vlm_timing(output_dir, metadata=None):
    """Start a fresh timing report for one evaluation invocation."""
    global _OUTPUT_PATH, _RECORDS, _METADATA, _STARTED_AT
    _OUTPUT_PATH = Path(output_dir) / "vlm_timing.json"
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RECORDS = []
    _METADATA = dict(metadata or {})
    _STARTED_AT = _utc_now()
    _write_report()
    logging.info("VLM request timing will be written to %s", _OUTPUT_PATH)


def _summary():
    successful = [record["response_seconds"] for record in _RECORDS if record["success"]]
    grouped = defaultdict(list)
    for record in _RECORDS:
        grouped[record["call_type"]].append(record)
    by_call_type = {}
    for call_type, records in sorted(grouped.items()):
        succeeded = [record["response_seconds"] for record in records if record["success"]]
        by_call_type[call_type] = {
            "request_attempts": len(records),
            "successful_responses": len(succeeded),
            "failed_attempts": len(records) - len(succeeded),
            "mean_success_response_seconds": (sum(succeeded) / len(succeeded)) if succeeded else None,
            "min_success_response_seconds": min(succeeded) if succeeded else None,
            "max_success_response_seconds": max(succeeded) if succeeded else None,
        }
    return {
        "request_attempts": len(_RECORDS),
        "successful_responses": len(successful),
        "failed_attempts": len(_RECORDS) - len(successful),
        "mean_success_response_seconds": (sum(successful) / len(successful)) if successful else None,
        "by_call_type": by_call_type,
    }


def _write_report():
    if _OUTPUT_PATH is None:
        return
    report = {
        "schema_version": 1,
        "measurement": "Each record is one chat.completions.create attempt; retry sleep and local processing are excluded.",
        "started_at_utc": _STARTED_AT,
        "updated_at_utc": _utc_now(),
        "metadata": _METADATA,
        "records": _RECORDS,
        "summary": _summary(),
    }
    try:
        fd, temporary_path = tempfile.mkstemp(prefix=".vlm_timing_", suffix=".json", dir=str(_OUTPUT_PATH.parent))
        with os.fdopen(fd, "w") as output_file:
            json.dump(report, output_file, indent=2)
            output_file.write("\n")
        os.replace(temporary_path, _OUTPUT_PATH)
    except Exception as exc:
        logging.warning("Unable to save VLM timing report: %s", exc)


def record_vlm_response(call_type, response_seconds, success, attempt, error_type=None):
    """Append one measured API attempt and persist an immediately usable report."""
    if _OUTPUT_PATH is None:
        return
    _RECORDS.append({
        "timestamp_utc": _utc_now(),
        "call_type": str(call_type),
        "response_seconds": round(float(response_seconds), 6),
        "success": bool(success),
        "attempt": int(attempt),
        "error_type": error_type,
    })
    _write_report()


def log_vlm_timing_summary():
    if _OUTPUT_PATH is None:
        return
    summary = _summary()
    mean = summary["mean_success_response_seconds"]
    logging.info(
        "VLM timing summary: successful=%d/%d, overall_mean=%s s (individual API requests only)",
        summary["successful_responses"], summary["request_attempts"],
        f"{mean:.3f}" if mean is not None else "n/a",
    )
    for call_type, values in summary["by_call_type"].items():
        type_mean = values["mean_success_response_seconds"]
        logging.info(
            "VLM timing [%s]: successful=%d/%d, mean=%s s",
            call_type, values["successful_responses"], values["request_attempts"],
            f"{type_mean:.3f}" if type_mean is not None else "n/a",
        )
