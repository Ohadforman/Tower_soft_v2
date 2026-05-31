#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migration import normalize_dataset_csv_dir as legacy  # noqa: E402


HEADER = ["Parameter Name", "Value", "Units"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely convert legacy dataset CSV folders into reviewable new-format snapshots."
    )
    parser.add_argument("source_dir", type=Path, help="Folder containing legacy or mixed dataset CSV files.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Review output folder. Defaults to import_reviews/<source>_dataset_migration_<date>.",
    )
    parser.add_argument(
        "--live-dir",
        type=Path,
        default=ROOT / "data_set_csv",
        help="Current live dataset workspace used for collision checks.",
    )
    return parser.parse_args()


def default_output_dir(source_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return ROOT / "import_reviews" / f"{source_dir.name}_dataset_migration_{stamp}"


def list_csv_files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*.csv") if path.is_file())


def normalize_existing_rows(rows: list[tuple[str, str, str]]) -> list[list[str]]:
    out = [HEADER]
    for name, value, units in rows:
        new_name = name
        if name.startswith("Marked Zone "):
            match = legacy.re.match(r"Marked Zone (\d+) (Avg|Min|Max) - (.+)$", name)
            if match:
                new_name = f"Zone {match.group(1)} | {match.group(3)} | {match.group(2)}"
        elif legacy.re.match(r"Zone \d+ Start$", name):
            new_name = name.replace(" Start", " | Start")
        elif legacy.re.match(r"Zone \d+ End$", name):
            new_name = name.replace(" End", " | End")
        new_value = legacy.normalize_new_value(new_name, value)
        out.append([new_name, new_value, units])
    return out


def build_output_rows(source_path: Path) -> tuple[str, list[list[str]]]:
    text = source_path.read_text(encoding="utf-8", errors="ignore")
    rows = legacy.read_rows(source_path)
    if legacy.is_already_new(text):
        return "normalized_new", normalize_existing_rows(rows)
    if legacy.needs_conversion(text):
        return "converted_legacy", legacy.build_normalized_rows(rows, source_path.name)
    return "normalized_existing", normalize_existing_rows(rows)


def rows_to_param_rows(rows: list[list[str]]) -> list[tuple[str, str, str]]:
    param_rows: list[tuple[str, str, str]] = []
    for row in rows[1:]:
        name = row[0] if len(row) > 0 else ""
        value = row[1] if len(row) > 1 else ""
        units = row[2] if len(row) > 2 else ""
        param_rows.append((name, value, units))
    return param_rows


def extract_metadata(rows: list[list[str]], fallback_name: str) -> dict[str, str]:
    latest, _ordered = legacy.build_param_index(rows_to_param_rows(rows))
    draw_name = legacy.get_param(latest, "Order__Draw Name", "Draw Name") or Path(fallback_name).stem
    draw_date = legacy.get_param(latest, "Order__Draw Date", "Draw Date")
    project = legacy.normalize_project(legacy.get_param(latest, "Order__Fiber Project", "Fiber Project"))
    geometry = legacy.normalize_geometry(legacy.get_param(latest, "Order__Fiber Geometry Type", "Fiber Geometry Type"))
    preform_number = legacy.derive_preform_number(
        draw_name,
        legacy.get_param(latest, "Order__Preform Number", "Preform Number"),
    )
    good_zones = legacy.get_param(
        latest,
        "Order__Good Zones Count (required length zones)",
        "Good Zones Count (required length zones)",
        "Good Zones Count",
    )
    return {
        "draw_name": draw_name,
        "draw_date": draw_date,
        "project": project,
        "geometry": geometry,
        "preform_number": preform_number,
        "good_zones_count": good_zones,
    }


def parser_compatible(rows: list[list[str]]) -> bool:
    if not rows or rows[0] != HEADER:
        return False
    for row in rows[1:80]:
        name = (row[0] if row else "").strip()
        if name in {"=== ORDER PARAMETERS ===", "=== ZONE SNAPSHOT ==="}:
            return True
    return False


def read_live_draw_names(live_dir: Path) -> Counter[str]:
    draw_names: Counter[str] = Counter()
    if not live_dir.exists():
        return draw_names
    for path in sorted(live_dir.rglob("*.csv")):
        if not path.is_file() or path.name == "_conversion_audit.csv":
            continue
        try:
            rows = legacy.read_rows(path)
        except Exception:
            continue
        latest, _ordered = legacy.build_param_index(rows)
        draw_name = legacy.get_param(latest, "Order__Draw Name", "Draw Name") or path.stem
        if draw_name:
            draw_names[draw_name] += 1
    return draw_names


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_rows(path: Path, rows: list[list[str]]) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def write_audit(path: Path, records: list[dict[str, str]]) -> None:
    ensure_parent(path)
    fieldnames = [
        "source_relpath",
        "source_name",
        "conversion_mode",
        "bucket",
        "output_relpath",
        "draw_name",
        "draw_date",
        "project",
        "geometry",
        "preform_number",
        "good_zones_count",
        "row_count",
        "parser_compatible",
        "filename_collision_live",
        "draw_name_collision_live",
        "source_draw_name_duplicates",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def write_summary(path: Path, summary_lines: list[str]) -> None:
    ensure_parent(path)
    path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    source_dir = args.source_dir.expanduser().resolve()
    live_dir = args.live_dir.expanduser().resolve()
    output_dir = (args.output_dir.expanduser().resolve() if args.output_dir else default_output_dir(source_dir))

    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"Source directory not found: {source_dir}")

    source_files = list_csv_files(source_dir)
    if not source_files:
        raise SystemExit(f"No CSV files found under: {source_dir}")

    live_names = Counter(path.name for path in list_csv_files(live_dir)) if live_dir.exists() else Counter()
    live_draw_names = read_live_draw_names(live_dir)

    prepared: list[dict[str, object]] = []
    source_draw_names: Counter[str] = Counter()
    for source_path in source_files:
        mode, output_rows = build_output_rows(source_path)
        metadata = extract_metadata(output_rows, source_path.name)
        source_draw_names[metadata["draw_name"]] += 1
        prepared.append(
            {
                "source_path": source_path,
                "source_relpath": source_path.relative_to(source_dir),
                "mode": mode,
                "rows": output_rows,
                "metadata": metadata,
                "parser_compatible": parser_compatible(output_rows),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    audit_records: list[dict[str, str]] = []
    mode_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()
    filename_collisions = 0
    draw_name_collisions = 0

    for item in prepared:
        source_relpath = Path(str(item["source_relpath"]))
        source_name = source_relpath.name
        metadata = item["metadata"]
        draw_name = str(metadata["draw_name"])
        filename_collision = live_names[source_name] > 0
        draw_name_collision = live_draw_names[draw_name] > 0 if draw_name else False
        source_duplicate = source_draw_names[draw_name] > 1 if draw_name else False

        notes: list[str] = []
        if filename_collision:
            notes.append("filename exists in live dataset workspace")
            filename_collisions += 1
        if draw_name_collision:
            notes.append("draw name already exists in live dataset workspace")
            draw_name_collisions += 1
        if source_duplicate:
            notes.append("same draw name appears multiple times in source folder")
        if not item["parser_compatible"]:
            notes.append("output did not pass parser compatibility check")

        bucket = "ready_for_review"
        if filename_collision or draw_name_collision or source_duplicate or not item["parser_compatible"]:
            bucket = "review_conflicts"

        output_relpath = Path(bucket) / source_relpath
        write_rows(output_dir / output_relpath, item["rows"])

        mode = str(item["mode"])
        mode_counts[mode] += 1
        bucket_counts[bucket] += 1

        audit_records.append(
            {
                "source_relpath": str(source_relpath),
                "source_name": source_name,
                "conversion_mode": mode,
                "bucket": bucket,
                "output_relpath": str(output_relpath),
                "draw_name": draw_name,
                "draw_date": str(metadata["draw_date"]),
                "project": str(metadata["project"]),
                "geometry": str(metadata["geometry"]),
                "preform_number": str(metadata["preform_number"]),
                "good_zones_count": str(metadata["good_zones_count"]),
                "row_count": str(max(0, len(item["rows"]) - 1)),
                "parser_compatible": "yes" if item["parser_compatible"] else "no",
                "filename_collision_live": "yes" if filename_collision else "no",
                "draw_name_collision_live": "yes" if draw_name_collision else "no",
                "source_draw_name_duplicates": "yes" if source_duplicate else "no",
                "notes": "; ".join(notes),
            }
        )

    write_audit(output_dir / "_migration_audit.csv", audit_records)

    summary_lines = [
        f"source_dir: {source_dir}",
        f"live_dir: {live_dir}",
        f"output_dir: {output_dir}",
        f"csv_files_found: {len(source_files)}",
        f"ready_for_review: {bucket_counts['ready_for_review']}",
        f"review_conflicts: {bucket_counts['review_conflicts']}",
        f"parser_compatible: {sum(1 for item in prepared if item['parser_compatible'])}",
        f"filename_collisions_live: {filename_collisions}",
        f"draw_name_collisions_live: {draw_name_collisions}",
    ]
    for mode, count in sorted(mode_counts.items()):
        summary_lines.append(f"{mode}: {count}")
    write_summary(output_dir / "_migration_summary.txt", summary_lines)

    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
