#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app_io.paths import P, ensure_dir
from scripts.cli.run_maintenance_flow_playbook import load_maintenance_tasks


def build_component_pdf(component_query: str, output_pdf: str) -> tuple[int, str]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as e:
        raise RuntimeError(f"reportlab required: {e}") from e

    ensure_dir(os.path.dirname(output_pdf) or ".")
    tasks = load_maintenance_tasks().copy()
    if tasks.empty:
        raise RuntimeError("No maintenance tasks found.")

    comp_series = tasks["Component"].astype(str).fillna("")
    mask = comp_series.str.contains(component_query, case=False, na=False)
    tasks = tasks[mask].copy()
    if tasks.empty:
        raise RuntimeError(f"No maintenance tasks found for component query: {component_query}")

    component_name = tasks["Component"].astype(str).str.strip().mode().iloc[0]
    tasks["Task"] = tasks["Task"].astype(str).fillna("").str.strip()
    tasks["Procedure_Summary"] = tasks["Procedure_Summary"].astype(str).fillna("").str.strip()
    tasks["Required_Parts"] = tasks["Required_Parts"].astype(str).fillna("").str.strip()
    tasks["Manual_Name"] = tasks["Manual_Name"].astype(str).fillna("").str.strip()
    tasks["Page"] = tasks["Page"].astype(str).fillna("").str.strip()
    tasks["Timing"] = (
        tasks["Interval_Value"].astype(str).fillna("").str.strip()
        + " "
        + tasks["Interval_Unit"].astype(str).fillna("").str.strip()
    ).str.strip()
    tasks["Timing"] = tasks.apply(
        lambda r: r["Timing"] if r["Timing"] else str(r.get("Interval_Type", "")).strip(),
        axis=1,
    )
    tasks = tasks.sort_values(["Task_ID", "Task"], kind="stable").reset_index(drop=True)

    doc = SimpleDocTemplate(
        output_pdf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{component_name} Maintenance",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=18)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=12)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#4a6178"))

    story = []
    story.append(Paragraph(f"{component_name} Maintenance", h1))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", small))
    story.append(Paragraph("This PDF lists the maintenance tasks for this component and explains what to do for each one.", small))
    story.append(Spacer(1, 4 * mm))

    summary_data = [
        ["Component", component_name],
        ["Tasks", str(len(tasks))],
        ["Manual", tasks["Manual_Name"].replace("", "-").iloc[0]],
    ]
    summary_tbl = Table(summary_data, colWidths=[34 * mm, 140 * mm])
    summary_tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9eb6cf")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef4fb")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary_tbl)
    story.append(Spacer(1, 5 * mm))

    for i, (_, row) in enumerate(tasks.iterrows(), start=1):
        task_title = f"{i}. {row['Task_ID']} - {row['Task']}".strip(" -")
        timing = str(row.get("Timing", "")).strip() or str(row.get("Tracking_Mode", "")).strip()
        manual_name = str(row.get("Manual_Name", "")).strip() or str(row.get("Source_File", "")).strip()
        page = str(row.get("Page", "")).strip() or "-"
        procedure = str(row.get("Procedure_Summary", "")).strip() or str(row.get("Task", "")).strip()
        required_parts = str(row.get("Required_Parts", "")).strip() or "-"

        story.append(Paragraph(task_title, h2))
        meta_data = [
            ["Timing", timing or "-"],
            ["Manual / Page", f"{manual_name} / {page}"],
            ["Required parts", required_parts],
        ]
        meta_tbl = Table(meta_data, colWidths=[30 * mm, 145 * mm])
        meta_tbl.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c6d7ea")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f6fafe")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(meta_tbl)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>What to do:</b> {procedure}", body))
        notes = str(row.get("Notes", "")).strip()
        if notes:
            story.append(Spacer(1, 1.5 * mm))
            story.append(Paragraph(f"<b>Notes:</b> {notes}", body))
        story.append(Spacer(1, 4 * mm))

    doc.build(story)
    return len(tasks), component_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a maintenance PDF for one component.")
    parser.add_argument("--component", required=True, help="Component name or partial text, e.g. 'Clean Air'")
    parser.add_argument(
        "--output",
        default=os.path.join(
            P.reports_dir,
            "maintenance_todo",
            f"component_maintenance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        ),
        help="Output PDF path",
    )
    args = parser.parse_args()

    count, component_name = build_component_pdf(args.component, args.output)
    print("=== Component Maintenance PDF ===")
    print(f"Component: {component_name}")
    print(f"Tasks: {count}")
    print(f"PDF: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
