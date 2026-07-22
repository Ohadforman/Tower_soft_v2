#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.migration.normalize_dataset_csv_dir import (
    DATASET_DIR,
    build_normalized_rows,
    build_param_index,
    get_param,
    is_already_new,
    needs_conversion,
    normalize_geometry,
    normalize_new_value,
    normalize_project,
    read_rows,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = Path("/Users/ohadformanair/Downloads/attachments")
DEFAULT_REVIEW_ROOT = ROOT / "import_reviews"


def normalize_existing_new_rows(rows: list[tuple[str, str, str]]) -> tuple[list[list[str]], bool]:
    out = [["Parameter Name", "Value", "Units"]]
    changed = False
    for name, value, units in rows:
        new_name = name
        if name.startswith("Marked Zone "):
            import re

            match = re.match(r"Marked Zone (\d+) (Avg|Min|Max) - (.+)$", name)
            if match:
                new_name = f"Zone {match.group(1)} | {match.group(3)} | {match.group(2)}"
                changed = True
        elif __import__("re").match(r"Zone \d+ Start$", name):
            new_name = name.replace(" Start", " | Start")
            changed = True
        elif __import__("re").match(r"Zone \d+ End$", name):
            new_name = name.replace(" End", " | End")
            changed = True
        new_value = normalize_new_value(new_name, value)
        if new_value != value:
            changed = True
        out.append([new_name, new_value, units])
    return out, changed


def output_rows_for_source(path: Path) -> tuple[list[list[str]] | None, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    rows = read_rows(path)
    if is_already_new(text):
        out_rows, changed = normalize_existing_new_rows(rows)
        return out_rows, "normalized_new" if changed else "copied_new"
    if needs_conversion(text):
        return build_normalized_rows(rows, path.name), "converted_legacy"
    if rows:
        out_rows = [["Parameter Name", "Value", "Units"], *[[name, value, units] for name, value, units in rows]]
        return out_rows, "copied_as_is"
    return None, "empty_or_unreadable"


def infer_dataset_meta(rows: list[list[str]], source_name: str) -> dict[str, str]:
    tuples = [(row[0], row[1], row[2]) for row in rows[1:] if len(row) >= 3]
    latest, _ = build_param_index(tuples)
    draw_name = get_param(latest, "Order__Draw Name", "Draw Name") or Path(source_name).stem
    draw_date = get_param(latest, "Order__Draw Date", "Draw Date")
    project = normalize_project(get_param(latest, "Order__Fiber Project", "Fiber Project"))
    geometry = normalize_geometry(get_param(latest, "Order__Fiber Geometry Type", "Fiber Geometry Type"))
    return {
        "draw_name": draw_name,
        "draw_date": draw_date,
        "project": project,
        "geometry": geometry,
        "row_count": str(max(0, len(rows) - 1)),
        "order_rows": str(sum(1 for row in rows if row and str(row[0]).startswith("Order__"))),
        "process_rows": str(sum(1 for row in rows if row and str(row[0]).startswith("Process__"))),
        "zone_rows": str(sum(1 for row in rows if row and "Zone " in str(row[0]))),
        "has_order_section": "yes" if any(row and row[0] == "=== ORDER PARAMETERS ===" for row in rows) else "no",
        "has_process_section": "yes" if any(row and row[0] == "=== PROCESS SETUP ===" for row in rows) else "no",
    }


def live_dataset_index() -> tuple[set[str], dict[str, list[str]]]:
    live_names: set[str] = set()
    live_draw_map: dict[str, list[str]] = {}
    for path in DATASET_DIR.rglob("*.csv"):
        if not path.is_file() or path.name == "_conversion_audit.csv":
            continue
        try:
            rows = read_rows(path)
        except Exception:
            continue
        live_names.add(path.name)
        latest, _ = build_param_index(rows)
        draw_name = get_param(latest, "Order__Draw Name", "Draw Name") or path.stem
        if draw_name:
            live_draw_map.setdefault(draw_name, []).append(path.name)
    return live_names, live_draw_map


def ensure_review_dir(source_dir: Path, output_dir: Path | None) -> Path:
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = DEFAULT_REVIEW_ROOT / f"{source_dir.name}_dataset_migration_{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def run(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    live_names, live_draw_map = live_dataset_index()
    audit_rows: list[dict[str, str]] = []
    summary = {
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "total_files": 0,
        "converted_legacy": 0,
        "normalized_new": 0,
        "copied_new": 0,
        "copied_as_is": 0,
        "empty_or_unreadable": 0,
        "live_name_collisions": 0,
        "live_draw_collisions": 0,
    }

    for source_path in sorted(source_dir.glob("*.csv")):
        summary["total_files"] += 1
        out_rows, mode = output_rows_for_source(source_path)
        summary[mode] = summary.get(mode, 0) + 1
        output_name = source_path.name
        output_path = output_dir / output_name
        draw_name = ""
        draw_date = ""
        project = ""
        geometry = ""
        row_count = "0"
        order_rows = "0"
        process_rows = "0"
        zone_rows = "0"
        has_order_section = "no"
        has_process_section = "no"
        parser_fit = "no"

        if out_rows:
            with output_path.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerows(out_rows)
            meta = infer_dataset_meta(out_rows, source_path.name)
            draw_name = meta["draw_name"]
            draw_date = meta["draw_date"]
            project = meta["project"]
            geometry = meta["geometry"]
            row_count = meta["row_count"]
            order_rows = meta["order_rows"]
            process_rows = meta["process_rows"]
            zone_rows = meta["zone_rows"]
            has_order_section = meta["has_order_section"]
            has_process_section = meta["has_process_section"]
            parser_fit = "yes" if has_order_section == "yes" and has_process_section == "yes" else "no"

        collides_name = "yes" if output_name in live_names else "no"
        collides_draw = "yes" if draw_name and draw_name in live_draw_map else "no"
        if collides_name == "yes":
            summary["live_name_collisions"] += 1
        if collides_draw == "yes":
            summary["live_draw_collisions"] += 1

        audit_rows.append(
            {
                "source_csv": source_path.name,
                "mode": mode,
                "output_csv": output_name if out_rows else "",
                "parser_fit": parser_fit,
                "draw_name": draw_name,
                "draw_date": draw_date,
                "project": project,
                "geometry": geometry,
                "row_count": row_count,
                "order_rows": order_rows,
                "process_rows": process_rows,
                "zone_rows": zone_rows,
                "has_order_section": has_order_section,
                "has_process_section": has_process_section,
                "collides_live_filename": collides_name,
                "collides_live_draw_name": collides_draw,
                "live_draw_files": "; ".join(live_draw_map.get(draw_name, [])),
            }
        )

    audit_path = output_dir / "_migration_audit.csv"
    with audit_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit_rows[0].keys()) if audit_rows else [
            "source_csv", "mode", "output_csv", "parser_fit", "draw_name", "draw_date", "project", "geometry",
            "row_count", "order_rows", "process_rows", "zone_rows", "has_order_section", "has_process_section",
            "collides_live_filename", "collides_live_draw_name", "live_draw_files",
        ])
        writer.writeheader()
        writer.writerows(audit_rows)

    summary_path = output_dir / "_migration_summary.json"
    summary["audit_csv"] = str(audit_path)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely convert a legacy dataset CSV directory into the new dataset format.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR, help="Directory containing legacy CSV dataset snapshots.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory to write converted review files into.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = args.source_dir.expanduser().resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"Source directory not found: {source_dir}")
    output_dir = ensure_review_dir(source_dir, args.output_dir.expanduser().resolve() if args.output_dir else None)
    summary = run(source_dir, output_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
