#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app_io.paths import P, ensure_dir


def _to_float(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, str) and not x.strip():
            return default
        return float(x)
    except Exception:
        return default


def _parse_dt_robust(v) -> pd.Timestamp:
    if v is None:
        return pd.NaT
    s = str(v).strip()
    if not s:
        return pd.NaT
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        dt = pd.to_datetime(s, errors="coerce", dayfirst=False)
    else:
        dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.notna(dt):
        return dt
    # Support Date/Time like 19/11/2024 12:44:33772 from logs.
    try:
        parts = s.split()
        if len(parts) < 2:
            return pd.NaT
        dpart, tpart = parts[0], parts[1]
        hh, mm, secms = tpart.split(":")
        ss = int(secms[:2]) if len(secms) >= 2 else 0
        ms_str = secms[2:] if len(secms) > 2 else ""
        ms = int(ms_str[:3]) if ms_str.isdigit() and ms_str else 0
        dd, mon, yy = dpart.split("/")
        return pd.Timestamp(datetime(int(yy), int(mon), int(dd), int(hh), int(mm), int(ss), ms * 1000))
    except Exception:
        return pd.NaT


def _period_default() -> tuple[pd.Timestamp, pd.Timestamp]:
    now = pd.Timestamp.now()
    start = (now - pd.Timedelta(days=6)).normalize()
    end = now
    return start, end


def _read_csv_safe(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, keep_default_na=False)
    except Exception:
        return pd.DataFrame()


@dataclass
class DrawSummary:
    count_done: int
    unique_projects: int
    unique_preforms: int
    total_required_m: float
    avg_draw_speed: float
    done_rows: pd.DataFrame
    project_counts: pd.DataFrame


def _build_draw_summary(start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> DrawSummary:
    df = _read_csv_safe(P.orders_csv)
    if df.empty:
        return DrawSummary(0, 0, 0, 0.0, 0.0, pd.DataFrame(), pd.DataFrame())

    for col, default in {
        "Status": "",
        "Done Timestamp": "",
        "Timestamp": "",
        "Fiber Project": "",
        "Preform Number": "",
        "Fiber Type": "",
        "Draw Speed (m/min)": 0.0,
        "Required Length (m) (for T&M+costumer)": 0.0,
        "Done CSV": "",
        "Done Description": "",
    }.items():
        if col not in df.columns:
            df[col] = default

    status = df["Status"].astype(str).str.strip().str.lower()
    done_dt = df["Done Timestamp"].apply(_parse_dt_robust)
    ts_fallback = df["Timestamp"].apply(_parse_dt_robust)
    done_dt = done_dt.fillna(ts_fallback)

    mask = status.eq("done") & done_dt.notna() & (done_dt >= start_dt) & (done_dt <= end_dt)
    done = df.loc[mask].copy()
    done["_done_dt"] = done_dt.loc[mask]

    if done.empty:
        return DrawSummary(0, 0, 0, 0.0, 0.0, done, pd.DataFrame())

    done["Required Length (m) (for T&M+costumer)"] = pd.to_numeric(
        done["Required Length (m) (for T&M+costumer)"], errors="coerce"
    ).fillna(0.0)
    done["Draw Speed (m/min)"] = pd.to_numeric(done["Draw Speed (m/min)"], errors="coerce").fillna(0.0)

    project_counts = (
        done["Fiber Project"]
        .astype(str)
        .str.strip()
        .replace("", "Unknown")
        .value_counts()
        .rename_axis("project")
        .reset_index(name="done_count")
    )

    done_rows = done[
        [
            "_done_dt",
            "Fiber Project",
            "Preform Number",
            "Fiber Type",
            "Required Length (m) (for T&M+costumer)",
            "Draw Speed (m/min)",
            "Done CSV",
            "Done Description",
        ]
    ].copy()
    done_rows = done_rows.rename(
        columns={
            "_done_dt": "done_at",
            "Fiber Project": "project",
            "Preform Number": "preform",
            "Fiber Type": "fiber_type",
            "Required Length (m) (for T&M+costumer)": "required_m",
            "Draw Speed (m/min)": "draw_speed_mpm",
            "Done CSV": "dataset_csv",
            "Done Description": "notes",
        }
    ).sort_values("done_at", ascending=False)

    return DrawSummary(
        count_done=int(len(done)),
        unique_projects=int(done["Fiber Project"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()),
        unique_preforms=int(done["Preform Number"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()),
        total_required_m=float(done["Required Length (m) (for T&M+costumer)"].sum()),
        avg_draw_speed=float(done["Draw Speed (m/min)"].mean() if len(done) else 0.0),
        done_rows=done_rows,
        project_counts=project_counts,
    )


def _iter_log_csvs() -> Iterable[str]:
    for base, _, files in os.walk(P.logs_dir):
        for fn in files:
            if fn.lower().endswith(".csv"):
                yield os.path.join(base, fn)


@dataclass
class GasSummary:
    total_sl: float
    total_minutes: float
    avg_slpm_weighted: float
    logs_used: int
    avg_sl_per_log: float
    per_log: pd.DataFrame


def _build_gas_summary(start_dt: pd.Timestamp, end_dt: pd.Timestamp, dt_cap_s: float = 2.0) -> GasSummary:
    time_col = "Date/Time"
    mfc_cols = [
        "Furnace MFC1 Actual",
        "Furnace MFC2 Actual",
        "Furnace MFC3 Actual",
        "Furnace MFC4 Actual",
    ]

    per_log_rows: list[dict] = []
    total_sl = 0.0
    total_minutes = 0.0
    logs_used = 0

    for lp in _iter_log_csvs():
        try:
            df = pd.read_csv(lp)
        except Exception:
            continue
        if time_col not in df.columns:
            continue
        if not any(c in df.columns for c in mfc_cols):
            continue

        t = df[time_col].apply(_parse_dt_robust)
        flow = None
        for c in mfc_cols:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                flow = s if flow is None else (flow + s)
        if flow is None:
            continue

        work = pd.DataFrame({"t": t, "flow": flow}).dropna(subset=["t"]).sort_values("t")
        if len(work) < 3:
            continue

        # Keep rows near selected interval so diff() around boundaries remains valid.
        pad = pd.Timedelta(seconds=float(dt_cap_s))
        work = work[(work["t"] >= (start_dt - pad)) & (work["t"] <= (end_dt + pad))].copy()
        if len(work) < 3:
            continue

        dt_s = work["t"].diff().dt.total_seconds().fillna(0.0).clip(lower=0.0, upper=float(dt_cap_s))
        work["dt_min"] = dt_s / 60.0
        work = work[(work["t"] >= start_dt) & (work["t"] <= end_dt)].copy()
        if work.empty:
            continue

        sl = float((work["flow"] * work["dt_min"]).sum())
        mins = float(work["dt_min"].sum())
        if mins <= 0:
            continue

        logs_used += 1
        total_sl += sl
        total_minutes += mins
        per_log_rows.append(
            {
                "log_csv": os.path.basename(lp),
                "argon_sl": sl,
                "minutes": mins,
                "avg_slpm": float(sl / mins) if mins > 0 else 0.0,
            }
        )

    per_log_df = pd.DataFrame(per_log_rows).sort_values("argon_sl", ascending=False) if per_log_rows else pd.DataFrame()
    avg_sl_per_log = (total_sl / logs_used) if logs_used > 0 else 0.0
    avg_slpm_weighted = (total_sl / total_minutes) if total_minutes > 0 else 0.0
    return GasSummary(
        total_sl=total_sl,
        total_minutes=total_minutes,
        avg_slpm_weighted=avg_slpm_weighted,
        logs_used=logs_used,
        avg_sl_per_log=avg_sl_per_log,
        per_log=per_log_df,
    )


@dataclass
class SapSummary:
    events_count: int
    current_count: float
    events_rows: pd.DataFrame


@dataclass
class MaintenanceSummary:
    actions_count: int
    actions_rows: pd.DataFrame


@dataclass
class FaultSummary:
    faults_opened_count: int
    faults_closed_count: int
    open_faults_now_count: int
    open_critical_now_count: int
    faults_rows: pd.DataFrame
    fault_actions_rows: pd.DataFrame


@dataclass
class ScheduleSummary:
    events_count: int
    events_rows: pd.DataFrame


def _build_sap_summary(start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> SapSummary:
    sap_df = _read_csv_safe(P.sap_rods_inventory_csv)
    if sap_df.empty:
        return SapSummary(events_count=0, current_count=0.0, events_rows=pd.DataFrame())

    notes = str(sap_df.iloc[0].get("Notes", ""))
    current_count = _to_float(sap_df.iloc[0].get("Count", 0.0), 0.0)

    # Example note line:
    # [2026-02-06 10:16:10] -1 set (PM draw XXXX). New Count=8.
    patt = re.compile(r"\[(?P<ts>[\d\-:\s]+)\]\s*(?P<msg>.+)")
    rows = []
    for line in notes.splitlines():
        m = patt.search(line.strip())
        if not m:
            continue
        ts = pd.to_datetime(m.group("ts").strip(), errors="coerce")
        if pd.isna(ts):
            continue
        if ts < start_dt or ts > end_dt:
            continue
        msg = m.group("msg").strip()
        used = 1 if "-1 set" in msg.lower() else 0
        rows.append({"timestamp": ts, "event": msg, "sap_sets_used": used})

    events_df = pd.DataFrame(rows).sort_values("timestamp", ascending=False) if rows else pd.DataFrame()
    events_count = int(events_df["sap_sets_used"].sum()) if not events_df.empty else 0
    return SapSummary(events_count=events_count, current_count=current_count, events_rows=events_df)


def _build_maintenance_summary(start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> MaintenanceSummary:
    path = os.path.join(P.maintenance_dir, "maintenance_actions_log.csv")
    df = _read_csv_safe(path)
    if df.empty:
        return MaintenanceSummary(actions_count=0, actions_rows=pd.DataFrame())

    for col in ["maintenance_ts", "maintenance_component", "maintenance_task", "maintenance_actor", "maintenance_note"]:
        if col not in df.columns:
            df[col] = ""

    dt = df["maintenance_ts"].apply(_parse_dt_robust)
    mask = dt.notna() & (dt >= start_dt) & (dt <= end_dt)
    out = df.loc[mask, ["maintenance_ts", "maintenance_component", "maintenance_task", "maintenance_actor", "maintenance_note"]].copy()
    out = out.rename(
        columns={
            "maintenance_ts": "timestamp",
            "maintenance_component": "component",
            "maintenance_task": "task",
            "maintenance_actor": "actor",
            "maintenance_note": "note",
        }
    )
    if not out.empty:
        out["timestamp"] = out["timestamp"].apply(_parse_dt_robust)
        out = out.sort_values("timestamp", ascending=False)
    return MaintenanceSummary(actions_count=int(len(out)), actions_rows=out)


def _build_fault_summary(start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> FaultSummary:
    faults_path = os.path.join(P.maintenance_dir, "faults_log.csv")
    actions_path = os.path.join(P.maintenance_dir, "faults_actions_log.csv")
    faults = _read_csv_safe(faults_path)
    actions = _read_csv_safe(actions_path)

    if faults.empty:
        return FaultSummary(0, 0, 0, 0, pd.DataFrame(), pd.DataFrame())

    for col in ["fault_id", "fault_ts", "fault_component", "fault_title", "fault_description", "fault_severity"]:
        if col not in faults.columns:
            faults[col] = ""

    faults["fault_id"] = pd.to_numeric(faults["fault_id"], errors="coerce")
    faults["fault_ts"] = faults["fault_ts"].apply(_parse_dt_robust)
    faults_valid = faults.dropna(subset=["fault_id"]).copy()

    period_faults = faults_valid[(faults_valid["fault_ts"] >= start_dt) & (faults_valid["fault_ts"] <= end_dt)].copy()
    faults_rows = period_faults[
        ["fault_ts", "fault_id", "fault_component", "fault_title", "fault_severity", "fault_description"]
    ].rename(
        columns={
            "fault_ts": "timestamp",
            "fault_id": "fault_id",
            "fault_component": "component",
            "fault_title": "title",
            "fault_severity": "severity",
            "fault_description": "description",
        }
    )
    if not faults_rows.empty:
        faults_rows = faults_rows.sort_values("timestamp", ascending=False)

    if actions.empty:
        open_faults_now = faults_valid.copy()
        open_critical = int(
            open_faults_now["fault_severity"].astype(str).str.strip().str.lower().eq("critical").sum()
        )
        return FaultSummary(
            faults_opened_count=int(len(period_faults)),
            faults_closed_count=0,
            open_faults_now_count=int(len(open_faults_now)),
            open_critical_now_count=open_critical,
            faults_rows=faults_rows,
            fault_actions_rows=pd.DataFrame(),
        )

    for col in ["fault_id", "action_ts", "action_type", "actor", "note"]:
        if col not in actions.columns:
            actions[col] = ""
    actions["fault_id"] = pd.to_numeric(actions["fault_id"], errors="coerce")
    actions["action_ts"] = actions["action_ts"].apply(_parse_dt_robust)
    actions = actions.dropna(subset=["fault_id"]).copy()

    period_actions = actions[(actions["action_ts"] >= start_dt) & (actions["action_ts"] <= end_dt)].copy()
    fault_actions_rows = period_actions[["action_ts", "fault_id", "action_type", "actor", "note"]].rename(
        columns={"action_ts": "timestamp"}
    )
    if not fault_actions_rows.empty:
        fault_actions_rows = fault_actions_rows.sort_values("timestamp", ascending=False)

    closed_actions = period_actions["action_type"].astype(str).str.strip().str.lower().eq("close")
    faults_closed_count = int(closed_actions.sum())

    # Determine open faults "now" by latest action per fault id.
    latest_action = (
        actions.sort_values("action_ts")
        .groupby("fault_id", as_index=False)
        .tail(1)[["fault_id", "action_type"]]
    )
    latest_action["action_type"] = latest_action["action_type"].astype(str).str.strip().str.lower()

    merged = faults_valid[["fault_id", "fault_severity"]].drop_duplicates().merge(
        latest_action, on="fault_id", how="left"
    )
    open_now_mask = ~merged["action_type"].isin(["close", "closed", "resolved", "done", "fixed"])
    open_now = merged[open_now_mask].copy()
    open_critical_now = int(open_now["fault_severity"].astype(str).str.strip().str.lower().eq("critical").sum())

    return FaultSummary(
        faults_opened_count=int(len(period_faults)),
        faults_closed_count=faults_closed_count,
        open_faults_now_count=int(len(open_now)),
        open_critical_now_count=open_critical_now,
        faults_rows=faults_rows,
        fault_actions_rows=fault_actions_rows,
    )


def _expand_schedule_for_window(df: pd.DataFrame, start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> pd.DataFrame:
    if df.empty:
        return df
    for col in ["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]:
        if col not in df.columns:
            df[col] = ""

    df = df.copy()
    df["Start DateTime"] = pd.to_datetime(df["Start DateTime"], errors="coerce")
    df["End DateTime"] = pd.to_datetime(df["End DateTime"], errors="coerce")
    df = df.dropna(subset=["Start DateTime", "End DateTime"])
    if df.empty:
        return df

    out_rows: list[dict] = []

    def _step(ts: pd.Timestamp, rec_low: str):
        if "week" in rec_low:
            return ts + pd.DateOffset(weeks=1)
        if "month" in rec_low:
            return ts + pd.DateOffset(months=1)
        if "year" in rec_low:
            return ts + pd.DateOffset(years=1)
        return pd.NaT

    for _, r in df.iterrows():
        st0 = r["Start DateTime"]
        en0 = r["End DateTime"]
        rec = str(r.get("Recurrence", "")).strip()
        rec_low = rec.lower()
        duration = en0 - st0
        if pd.isna(duration) or duration <= pd.Timedelta(seconds=0):
            duration = pd.Timedelta(minutes=1)

        if rec_low in {"", "none", "nan"}:
            if (en0 >= start_dt) and (st0 <= end_dt):
                out_rows.append(r.to_dict())
            continue

        cur = st0
        guard = 0
        while cur + duration < start_dt and guard < 2000:
            nxt = _step(cur, rec_low)
            if pd.isna(nxt):
                break
            cur = nxt
            guard += 1

        gen = 0
        while cur <= end_dt and gen < 2000:
            ce = cur + duration
            if (ce >= start_dt) and (cur <= end_dt):
                rr = r.to_dict()
                rr["Start DateTime"] = cur
                rr["End DateTime"] = ce
                out_rows.append(rr)
            nxt = _step(cur, rec_low)
            if pd.isna(nxt):
                break
            cur = nxt
            gen += 1

    if not out_rows:
        return pd.DataFrame(columns=df.columns)
    out = pd.DataFrame(out_rows)
    out["Start DateTime"] = pd.to_datetime(out["Start DateTime"], errors="coerce")
    out["End DateTime"] = pd.to_datetime(out["End DateTime"], errors="coerce")
    return out.sort_values("Start DateTime")


def _build_next_week_schedule_summary(anchor_dt: pd.Timestamp) -> ScheduleSummary:
    sched = _read_csv_safe(P.schedule_csv)
    if sched.empty:
        return ScheduleSummary(events_count=0, events_rows=pd.DataFrame())

    start = anchor_dt.normalize()
    end = start + pd.Timedelta(days=7)
    expanded = _expand_schedule_for_window(sched, start, end)
    if expanded.empty:
        return ScheduleSummary(events_count=0, events_rows=pd.DataFrame())

    rows = expanded[["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]].copy()
    rows = rows.rename(
        columns={
            "Event Type": "event_type",
            "Start DateTime": "start",
            "End DateTime": "end",
            "Description": "description",
            "Recurrence": "recurrence",
        }
    )
    rows["recurrence"] = rows["recurrence"].astype(str).replace({"nan": "", "None": ""}).fillna("")
    rows = rows.sort_values("start")
    return ScheduleSummary(events_count=int(len(rows)), events_rows=rows)


def _latest_containers_snapshot() -> pd.DataFrame:
    df = _read_csv_safe(P.tower_containers_csv)
    if df.empty:
        return pd.DataFrame()
    last = df.tail(1).copy()
    cols = [
        c
        for c in [
            "timestamp",
            "tank1",
            "tank2",
            "tank3",
            "tank4",
            "updated_at",
            "A_level_kg",
            "B_level_kg",
            "C_level_kg",
            "D_level_kg",
            "A_type",
            "B_type",
            "C_type",
            "D_type",
        ]
        if c in last.columns
    ]
    return last[cols]


def _df_for_pdf_table(df: pd.DataFrame, limit: int = 12) -> list[list[str]]:
    if df is None or df.empty:
        return [["No data"]]
    use = df.head(limit).copy()
    rows = [list(use.columns)]
    for _, r in use.iterrows():
        out = []
        for v in r.tolist():
            if isinstance(v, pd.Timestamp):
                out.append(v.strftime("%Y-%m-%d %H:%M"))
            elif isinstance(v, float):
                out.append(f"{v:.2f}")
            else:
                out.append(str(v))
        rows.append(out)
    return rows


def _build_pdf(
    output_pdf: str,
    start_dt: pd.Timestamp,
    end_dt: pd.Timestamp,
    draws: DrawSummary,
    gas: GasSummary,
    sap: SapSummary,
    maintenance: MaintenanceSummary,
    faults: FaultSummary,
    next_week_schedule: ScheduleSummary,
    containers: pd.DataFrame,
) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except Exception as e:
        raise RuntimeError(
            "Missing reportlab package. Use your project venv to run this script, e.g. "
            "`.venv/bin/python scripts/cli/run_weekly_report.py`."
        ) from e

    doc = SimpleDocTemplate(
        output_pdf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Tower Weekly Report",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, leading=22, textColor=colors.HexColor("#0A3A66"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#114E86"))
    normal = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=13)
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=9, leading=12, textColor=colors.HexColor("#333333"))

    story = []
    story.append(Paragraph("Tower Weekly Production Report", h1))
    story.append(Paragraph(f"Period: {start_dt.strftime('%Y-%m-%d %H:%M')}  to  {end_dt.strftime('%Y-%m-%d %H:%M')}", small))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", small))
    story.append(Spacer(1, 8))

    summary_rows = [
        ["Done draws", str(draws.count_done)],
        ["Unique projects", str(draws.unique_projects)],
        ["Unique preforms", str(draws.unique_preforms)],
        ["Total required length (m)", f"{draws.total_required_m:.2f}"],
        ["Avg draw speed (m/min)", f"{draws.avg_draw_speed:.2f}"],
        ["Argon used (SL)", f"{gas.total_sl:.2f}"],
        ["Gas weighted avg flow (SLPM)", f"{gas.avg_slpm_weighted:.2f}"],
        ["SAP sets used", str(sap.events_count)],
        ["SAP sets in stock (current)", f"{sap.current_count:.0f}"],
        ["Maintenance actions (period)", str(maintenance.actions_count)],
        ["Faults opened / closed (period)", f"{faults.faults_opened_count} / {faults.faults_closed_count}"],
        ["Open critical faults (now)", str(faults.open_critical_now_count)],
        ["Next-week scheduled events", str(next_week_schedule.events_count)],
    ]
    t = Table(summary_rows, colWidths=[65 * mm, 45 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF4FF")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#A5C9E8")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F7FBFF")]),
            ]
        )
    )
    story.append(Paragraph("Executive Summary", h2))
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Draws Completed", h2))
    story.append(Paragraph("Top projects by done draws", normal))
    proj_tbl = Table(_df_for_pdf_table(draws.project_counts.rename(columns={"project": "Project", "done_count": "Done Count"}), limit=10))
    proj_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7B7B7")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0"))]))
    story.append(proj_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Latest completed draws", normal))
    done_tbl = Table(_df_for_pdf_table(draws.done_rows, limit=14), repeatRows=1)
    done_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C0C0C0")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5FF")), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(done_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Argon Gas Consumption", h2))
    gas_rows = [
        ["Logs used", str(gas.logs_used)],
        ["Total minutes", f"{gas.total_minutes:.2f}"],
        ["Total Argon (SL)", f"{gas.total_sl:.2f}"],
        ["Weighted Avg Flow (SLPM)", f"{gas.avg_slpm_weighted:.2f}"],
        ["Avg Argon per draw-log (SL)", f"{gas.avg_sl_per_log:.2f}"],
    ]
    gas_tbl = Table(gas_rows, colWidths=[70 * mm, 40 * mm])
    gas_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7B7B7")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0"))]))
    story.append(gas_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Top gas-consuming logs in period", normal))
    gas_log_tbl = Table(_df_for_pdf_table(gas.per_log, limit=12), repeatRows=1)
    gas_log_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C0C0C0")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5FF")), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(gas_log_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("SAP Rods Usage", h2))
    sap_rows = [
        ["SAP sets used in period", str(sap.events_count)],
        ["Current SAP sets in stock", f"{sap.current_count:.0f}"],
    ]
    sap_tbl = Table(sap_rows, colWidths=[70 * mm, 40 * mm])
    sap_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7B7B7")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0"))]))
    story.append(sap_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("SAP usage events (from inventory notes)", normal))
    sap_ev_tbl = Table(_df_for_pdf_table(sap.events_rows, limit=16), repeatRows=1)
    sap_ev_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C0C0C0")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5FF")), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(sap_ev_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Maintenance Report", h2))
    maint_rows = [
        ["Maintenance actions in period", str(maintenance.actions_count)],
    ]
    maint_tbl = Table(maint_rows, colWidths=[70 * mm, 40 * mm])
    maint_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7B7B7")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0"))]))
    story.append(maint_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Latest maintenance actions", normal))
    maint_actions_tbl = Table(_df_for_pdf_table(maintenance.actions_rows, limit=16), repeatRows=1)
    maint_actions_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C0C0C0")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5FF")), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(maint_actions_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Faults Report", h2))
    faults_rows = [
        ["Faults opened in period", str(faults.faults_opened_count)],
        ["Fault actions closed in period", str(faults.faults_closed_count)],
        ["Open faults now", str(faults.open_faults_now_count)],
        ["Open critical faults now", str(faults.open_critical_now_count)],
    ]
    faults_tbl = Table(faults_rows, colWidths=[70 * mm, 40 * mm])
    faults_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7B7B7")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0"))]))
    story.append(faults_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Recent faults", normal))
    faults_events_tbl = Table(_df_for_pdf_table(faults.faults_rows, limit=16), repeatRows=1)
    faults_events_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C0C0C0")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5FF")), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(faults_events_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Recent fault actions", normal))
    faults_actions_tbl = Table(_df_for_pdf_table(faults.fault_actions_rows, limit=16), repeatRows=1)
    faults_actions_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C0C0C0")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5FF")), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(faults_actions_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Next Week Schedule", h2))
    story.append(Paragraph("Planned events for the coming 7 days", normal))
    sched_tbl = Table(_df_for_pdf_table(next_week_schedule.events_rows, limit=22), repeatRows=1)
    sched_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C0C0C0")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5FF")), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(sched_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Consumables Snapshot", h2))
    cont_tbl = Table(_df_for_pdf_table(containers, limit=1))
    cont_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7B7B7")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5FF")), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(cont_tbl)
    story.append(Spacer(1, 8))
    story.append(Paragraph("Notes: Gas is calculated from Furnace MFC1-4 Actual in logs with capped dt integration.", small))

    doc.build(story)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly Tower report PDF for coworkers.")
    parser.add_argument("--start", default="", help="Start date/time (e.g. 2026-03-01 or 2026-03-01 00:00)")
    parser.add_argument("--end", default="", help="End date/time (e.g. 2026-03-07 or 2026-03-07 23:59)")
    parser.add_argument("--dt-cap", type=float, default=2.0, help="Max seconds per log sample step for gas integration.")
    args = parser.parse_args()

    start_dt, end_dt = _period_default()
    if args.start.strip():
        p = pd.to_datetime(args.start.strip(), errors="coerce")
        if pd.isna(p):
            print(f"Invalid --start value: {args.start}")
            return 2
        start_dt = p
    if args.end.strip():
        p = pd.to_datetime(args.end.strip(), errors="coerce")
        if pd.isna(p):
            print(f"Invalid --end value: {args.end}")
            return 2
        end_dt = p

    if end_dt < start_dt:
        print("Invalid period: end before start.")
        return 2

    result = generate_weekly_report(start_dt=start_dt, end_dt=end_dt, dt_cap=float(args.dt_cap))
    out_pdf = result["pdf_path"]
    draws = result["draws"]
    gas = result["gas"]
    sap = result["sap"]
    maintenance = result["maintenance"]
    faults = result["faults"]
    next_week_schedule = result["next_week_schedule"]

    print("=== Weekly Report ===")
    print(f"Period: {start_dt} -> {end_dt}")
    print(f"Done draws: {draws.count_done}")
    print(f"Gas (SL): {gas.total_sl:.2f}")
    print(f"SAP used: {sap.events_count}")
    print(f"Maintenance actions: {maintenance.actions_count}")
    print(f"Faults opened/closed: {faults.faults_opened_count}/{faults.faults_closed_count}")
    print(f"Next-week events: {next_week_schedule.events_count}")
    print(f"PDF: {out_pdf}")
    return 0


def generate_weekly_report(
    start_dt: pd.Timestamp | None = None,
    end_dt: pd.Timestamp | None = None,
    dt_cap: float = 2.0,
    output_pdf: str = "",
) -> dict:
    if start_dt is None or end_dt is None:
        start_dt, end_dt = _period_default()

    weekly_dir = ensure_dir(getattr(P, "weekly_reports_dir", os.path.join(P.reports_dir, "weekly")))
    file_tag = f"{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}"
    out_pdf = output_pdf or os.path.join(weekly_dir, f"tower_weekly_report_{file_tag}.pdf")

    draws = _build_draw_summary(start_dt, end_dt)
    gas = _build_gas_summary(start_dt, end_dt, dt_cap_s=float(dt_cap))
    sap = _build_sap_summary(start_dt, end_dt)
    maintenance = _build_maintenance_summary(start_dt, end_dt)
    faults = _build_fault_summary(start_dt, end_dt)
    next_week_schedule = _build_next_week_schedule_summary(pd.Timestamp.now())
    containers = _latest_containers_snapshot()

    _build_pdf(
        output_pdf=out_pdf,
        start_dt=start_dt,
        end_dt=end_dt,
        draws=draws,
        gas=gas,
        sap=sap,
        maintenance=maintenance,
        faults=faults,
        next_week_schedule=next_week_schedule,
        containers=containers,
    )
    return {
        "pdf_path": out_pdf,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "draws": draws,
        "gas": gas,
        "sap": sap,
        "maintenance": maintenance,
        "faults": faults,
        "next_week_schedule": next_week_schedule,
    }


if __name__ == "__main__":
    raise SystemExit(main())
