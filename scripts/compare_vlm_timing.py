#!/usr/bin/env python3
"""Compare two ``vlm_timing.json`` reports produced by GOAT-Bench runs."""

import argparse
import json
from pathlib import Path


def load_report(path):
    with Path(path).open("r") as report_file:
        return json.load(report_file)


def values(report, call_type=None):
    summary = report["summary"]
    if call_type is None:
        return summary["successful_responses"], summary["mean_success_response_seconds"]
    item = summary["by_call_type"].get(call_type, {})
    return item.get("successful_responses", 0), item.get("mean_success_response_seconds")


def format_seconds(value):
    return "n/a" if value is None else f"{value:.3f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", help="First vlm_timing.json (for example HSGM-structured BEV)")
    parser.add_argument("second", help="Second vlm_timing.json (for example baseline)")
    parser.add_argument("--first-label", default="hsgm_bev")
    parser.add_argument("--second-label", default="baseline")
    args = parser.parse_args()

    first = load_report(args.first)
    second = load_report(args.second)
    call_types = sorted(
        set(first["summary"]["by_call_type"]) | set(second["summary"]["by_call_type"])
    )

    print("VLM response-time comparison (seconds; successful API responses only)")
    print(f"{'call_type':<22} {args.first_label:>18} {args.second_label:>18} {'delta(first-second)':>22}")
    for call_type in ["all"] + call_types:
        first_count, first_mean = values(first, None if call_type == "all" else call_type)
        second_count, second_mean = values(second, None if call_type == "all" else call_type)
        delta = None if first_mean is None or second_mean is None else first_mean - second_mean
        print(
            f"{call_type:<22} {format_seconds(first_mean):>10} s ({first_count:>3})"
            f" {format_seconds(second_mean):>10} s ({second_count:>3})"
            f" {format_seconds(delta):>14} s"
        )


if __name__ == "__main__":
    main()
