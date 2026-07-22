#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_CSV = ROOT / "data" / "projects_fiber_templates.csv"


TEMPLATE_FIELD_MAP = {
    "Fiber Geometry Type": "Order__Fiber Geometry Type",
    "Tiger Cut (%)": "Order__Tiger Cut (%)",
    "Octagonal F2F (mm)": "Order__Octagonal F2F (mm)",
    "Fiber Diameter (µm)": "Order__Fiber Diameter (µm)",
    "Fiber Diameter Tol (± µm)": "Order__Fiber Diameter Tol (± µm)",
    "Main Coating Diameter (µm)": "Order__Main Coating Diameter (µm)",
    "Main Coating Diameter Tol (± µm)": "Order__Main Coating Diameter Tol (± µm)",
    "Secondary Coating Diameter (µm)": "Order__Secondary Coating Diameter (µm)",
    "Secondary Coating Diameter Tol (± µm)": "Order__Secondary Coating Diameter Tol (± µm)",
    "Tension (g)": "Order__Tension (g)",
    "Draw Speed (m/min)": "Order__Draw Speed (m/min)",
    "Main Coating": "Order__Main Coating",
    "Secondary Coating": "Order__Secondary Coating",
    "Main Coating Temperature (°C)": "Order__Main Coating Temperature (°C)",
    "Secondary Coating Temperature (°C)": "Order__Secondary Coating Temperature (°C)",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply conservative filename-based project/geometry enrichment to imported dataset CSVs."
    )
    parser.add_argument("target_dir", type=Path, help="Folder containing imported dataset CSV files to enrich in place.")
    parser.add_argument(
        "--audit-dir",
        type=Path,
        required=True,
        help="Folder where enrichment audit files should be written.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[list[str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [row for row in csv.reader(handle)]


def write_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def index_by_name(rows: list[list[str]]) -> dict[str, int]:
    index: dict[str, int] = {}
    for row_number, row in enumerate(rows):
        if not row:
            continue
        name = str(row[0]).strip()
        if name:
            index[name] = row_number
    return index


def current_value(rows: list[list[str]], mapping: dict[str, int], field: str) -> str:
    row_idx = mapping.get(field)
    if row_idx is None:
        return ""
    row = rows[row_idx]
    return row[1] if len(row) > 1 else ""


def set_value(rows: list[list[str]], mapping: dict[str, int], field: str, value: str) -> None:
    row_idx = mapping.get(field)
    if row_idx is None:
        return
    row = rows[row_idx]
    while len(row) < 3:
        row.append("")
    row[1] = value


def load_templates() -> dict[str, dict[str, str]]:
    templates: dict[str, dict[str, str]] = {}
    with TEMPLATES_CSV.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            project = str(row.get("Fiber Project", "")).strip()
            if project:
                templates[project] = {str(key): str(value or "") for key, value in row.items()}
    return templates


def analyze_rules(stem_upper: str) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    is_tiger = stem_upper.startswith("T0")
    is_pm = "PM" in stem_upper
    is_1550 = "1550" in stem_upper
    is_civan = "CIVAN" in stem_upper
    is_oct = "OCT" in stem_upper

    if is_tiger:
        rules.append(
            {
                "field": "Order__Fiber Project",
                "value": "TAMAM - TIGER",
                "reason": "filename starts with T0",
            }
        )
        rules.append(
            {
                "field": "Order__Fiber Geometry Type",
                "value": "TIGER - PM",
                "reason": "filename starts with T0",
            }
        )
        return rules

    if is_1550 or is_civan:
        rules.append(
            {
                "field": "Order__Fiber Project",
                "value": "CIVAN 1550",
                "reason": "filename contains 1550/CIVAN",
            }
        )
        rules.append(
            {
                "field": "Order__Fiber Geometry Type",
                "value": "PANDA - PM",
                "reason": "filename contains 1550/CIVAN",
            }
        )
        return rules
    if is_pm:
        rules.append(
            {
                "field": "Order__Fiber Project",
                "value": "CIVAN - LARA",
                "reason": "filename contains PM",
            }
        )
        rules.append(
            {
                "field": "Order__Fiber Geometry Type",
                "value": "PANDA - PM",
                "reason": "filename contains PM",
            }
        )
        return rules
    if is_oct:
        rules.append(
            {
                "field": "Order__Fiber Project",
                "value": "LARA - ELOP",
                "reason": "filename contains OCT",
            }
        )
        rules.append(
            {
                "field": "Order__Fiber Geometry Type",
                "value": "Octagonal",
                "reason": "filename contains OCT",
            }
        )
        return rules
    return rules


def should_apply(field: str, old_value: str, new_value: str) -> bool:
    old = (old_value or "").strip()
    if not old:
        return True
    if field == "Order__Fiber Project" and old == "CIVAN - LARA" and new_value == "CIVAN 1550":
        return True
    if field == "Order__Fiber Project" and old == "CIVAN 1550" and new_value == "CIVAN - LARA":
        return True
    if field == "Order__Fiber Project" and old == "" and new_value == "LARA - ELOP":
        return True
    if field == "Order__Fiber Geometry Type" and old == "ROUND":
        return True
    return False


def main() -> None:
    args = parse_args()
    target_dir = args.target_dir.expanduser().resolve()
    audit_dir = args.audit_dir.expanduser().resolve()
    audit_dir.mkdir(parents=True, exist_ok=True)
    templates = load_templates()

    files = sorted(path for path in target_dir.glob("*.csv") if path.is_file())
    if not files:
        raise SystemExit(f"No CSV files found in {target_dir}")

    audit_rows: list[dict[str, str]] = []
    touched_files = 0
    field_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for path in files:
        rows = read_rows(path)
        mapping = index_by_name(rows)
        changes: list[dict[str, str]] = []
        for rule in analyze_rules(path.stem.upper()):
            field = rule["field"]
            old_value = current_value(rows, mapping, field)
            new_value = rule["value"]
            if not should_apply(field, old_value, new_value):
                continue
            if old_value.strip() == new_value:
                continue
            set_value(rows, mapping, field, new_value)
            changes.append(
                {
                    "file_name": path.name,
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "reason": rule["reason"],
                }
            )
        project_name = current_value(rows, mapping, "Order__Fiber Project").strip()
        template = templates.get(project_name)
        if template:
            for template_field, dataset_field in TEMPLATE_FIELD_MAP.items():
                old_value = current_value(rows, mapping, dataset_field)
                if old_value.strip():
                    continue
                new_value = str(template.get(template_field, "")).strip()
                if not new_value:
                    continue
                set_value(rows, mapping, dataset_field, new_value)
                changes.append(
                    {
                        "file_name": path.name,
                        "field": dataset_field,
                        "old_value": old_value,
                        "new_value": new_value,
                        "reason": f"template fill from {project_name}",
                    }
                )
        if changes:
            write_rows(path, rows)
            touched_files += 1
            for change in changes:
                audit_rows.append(change)
                field_counts[change["field"]] += 1
                reason_counts[change["reason"]] += 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_path = audit_dir / f"dataset_filename_enrichment_audit_{stamp}.csv"
    summary_path = audit_dir / f"dataset_filename_enrichment_summary_{stamp}.txt"

    with audit_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file_name", "field", "old_value", "new_value", "reason"])
        writer.writeheader()
        writer.writerows(audit_rows)

    summary_lines = [
        f"target_dir: {target_dir}",
        f"files_scanned: {len(files)}",
        f"files_touched: {touched_files}",
        f"field_changes: {len(audit_rows)}",
    ]
    for field, count in sorted(field_counts.items()):
        summary_lines.append(f"{field}: {count}")
    for reason, count in sorted(reason_counts.items()):
        summary_lines.append(f"rule[{reason}]: {count}")
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("\n".join(summary_lines))
    print(f"audit_path: {audit_path}")
    print(f"summary_path: {summary_path}")


if __name__ == "__main__":
    main()
