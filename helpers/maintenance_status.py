import datetime as dt
import os
import re

import numpy as np
import pandas as pd


NORMALIZE_MAP = {
    "equipment": "Component",
    "task name": "Task",
    "task id": "Task_ID",
    "group": "Task_Group",
    "maintenance group": "Task_Group",
    "todo group": "Task_Group",
    "groups": "Task_Groups",
    "task groups": "Task_Groups",
    "maintenance groups": "Task_Groups",
    "required parts": "Required_Parts",
    "parts needed": "Required_Parts",
    "needed parts": "Required_Parts",
    "mandatory parts": "Mandatory_Parts",
    "must have parts": "Mandatory_Parts",
    "conditional parts": "Conditional_Parts",
    "if needed parts": "Conditional_Parts",
    "preparation lead days": "Preparation_Lead_Days",
    "prep lead days": "Preparation_Lead_Days",
    "parts check lead days": "Parts_Check_Lead_Days",
    "part lead days": "Parts_Check_Lead_Days",
    "auto order mandatory parts": "Auto_Order_Mandatory_Parts",
    "estimated duration min": "Est_Duration_Min",
    "estimated duration (min)": "Est_Duration_Min",
    "planning months": "Planning_Window_Months",
    "window months": "Planning_Window_Months",
    "interval type": "Interval_Type",
    "interval value": "Interval_Value",
    "interval unit": "Interval_Unit",
    "tracking mode": "Tracking_Mode",
    "hours source": "Hours_Source",
    "trigger modes": "Trigger_Modes",
    "trigger hours source": "Trigger_Hours_Source",
    "trigger hours interval": "Trigger_Hours_Interval",
    "trigger draws interval": "Trigger_Draws_Interval",
    "trigger calendar value": "Trigger_Calendar_Value",
    "trigger calendar unit": "Trigger_Calendar_Unit",
    "calendar rule": "Calendar_Rule",
    "due threshold (days)": "Due_Threshold_Days",
    "document name": "Manual_Name",
    "document file/link": "Document",
    "manual page": "Page",
    "procedure summary": "Procedure_Summary",
    "safety/notes": "Notes",
    "test fields": "Test_Fields",
    "test inputs": "Test_Fields",
    "monitor fields": "Test_Fields",
    "test preset": "Test_Preset",
    "monitor preset": "Test_Preset",
    "test thresholds": "Test_Thresholds",
    "threshold rules": "Test_Thresholds",
    "condition text": "Test_Condition",
    "condition trigger": "Test_Condition",
    "if condition": "Test_Condition",
    "condition action": "Test_Action",
    "if met do": "Test_Action",
    "owner": "Owner",
    "last done date": "Last_Done_Date",
    "last done hours": "Last_Done_Hours",
    "last done draw": "Last_Done_Draw",
    "last done hours uv1": "Last_Done_Hours_UV1",
    "last done hours uv2": "Last_Done_Hours_UV2",
    "last done hours furnace": "Last_Done_Hours_Furnace",
    "last done furnace hours": "Last_Done_Hours_Furnace",
    "last done uv1 hours": "Last_Done_Hours_UV1",
    "last done uv2 hours": "Last_Done_Hours_UV2",
}

REQUIRED_COLS = ["Component", "Task", "Tracking_Mode"]
OPTIONAL_COLS = [
    "Task_ID",
    "Task_Group", "Task_Groups", "Required_Parts", "Mandatory_Parts", "Conditional_Parts",
    "Preparation_Lead_Days", "Parts_Check_Lead_Days", "Auto_Order_Mandatory_Parts",
    "Est_Duration_Min", "Planning_Window_Months",
    "Interval_Type", "Interval_Value", "Interval_Unit",
    "Due_Threshold_Days",
    "Last_Done_Date", "Last_Done_Hours", "Last_Done_Draw",
    "Manual_Name", "Page", "Document",
    "Procedure_Summary", "Notes", "Test_Preset", "Test_Fields", "Test_Thresholds", "Test_Condition", "Test_Action", "Owner",
    "Hours_Source", "Calendar_Rule",
    "Trigger_Modes", "Trigger_Hours_Source", "Trigger_Hours_Interval",
    "Trigger_Draws_Interval", "Trigger_Calendar_Value", "Trigger_Calendar_Unit",
    "Last_Done_Hours_UV1", "Last_Done_Hours_UV2", "Last_Done_Hours_Furnace",
]


def safe_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and np.isnan(v):
        return ""
    return str(v)


def parse_date(x):
    if pd.isna(x) or x == "":
        return None
    d = pd.to_datetime(x, errors="coerce")
    if pd.isna(d):
        return None
    return d.date()


def parse_float(x):
    if pd.isna(x) or x == "":
        return None
    try:
        return float(x)
    except Exception:
        return None


def parse_int(x):
    if pd.isna(x) or x == "":
        return None
    try:
        return int(float(x))
    except Exception:
        return None


def norm_source(s) -> str:
    s = "" if s is None or pd.isna(s) else str(s)
    return s.strip().lower()


def mode_norm(x: str) -> str:
    s = "" if x is None or pd.isna(x) else str(x).strip().lower()
    if s in ("draw", "draws", "draws_count", "draw_count"):
        return "draws"
    return s


def _value_or_fallback(row, primary: str, fallback: str):
    v = row.get(primary, np.nan)
    if v is None or (isinstance(v, float) and np.isnan(v)) or safe_str(v).strip() == "":
        v = row.get(fallback, np.nan)
    return v


def _legacy_either_hours_interval(row):
    txt = " ".join([
        safe_str(row.get("Interval_Unit", "")),
        safe_str(row.get("Trigger Context", "")),
        safe_str(row.get("Task", "")),
    ]).lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*operating\s*hours", txt)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)\s*hours", txt)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None


def _legacy_either_calendar(row):
    unit_txt = " ".join([
        safe_str(row.get("Interval_Unit", "")),
        safe_str(row.get("Calendar_Rule", "")),
        safe_str(row.get("Trigger Context", "")),
        safe_str(row.get("Task", "")),
    ]).lower()
    try:
        value = float(row.get("Interval_Value", np.nan))
    except Exception:
        value = np.nan
    if pd.isna(value):
        value = None
    for needle, unit in (("month", "months"), ("week", "weeks"), ("day", "days"), ("year", "years")):
        if needle in unit_txt and value is not None:
            return value, unit
    return None, None


def normalize_maintenance_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    renamed_cols = [NORMALIZE_MAP.get(str(c).strip().lower(), c) for c in df.columns]
    collapsed = pd.DataFrame(index=df.index)
    for idx, col in enumerate(renamed_cols):
        series = df.iloc[:, idx]
        if col in collapsed.columns:
            existing = collapsed[col]
            existing_text = existing.apply(safe_str).str.strip()
            collapsed[col] = existing.where(existing_text.ne(""), series)
        else:
            collapsed[col] = series
    df = collapsed
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = np.nan
    for col in OPTIONAL_COLS:
        if col not in df.columns:
            df[col] = np.nan
    return df


def read_maintenance_file(path: str) -> pd.DataFrame:
    if path.lower().endswith(".csv"):
        return pd.read_csv(path)
    return pd.read_excel(path)


def load_maintenance_folder_df(maint_folder: str) -> pd.DataFrame:
    if not os.path.isdir(maint_folder):
        return pd.DataFrame()
    ignore_files = {
        "faults_actions_log.csv",
        "faults_log.csv",
        "maintenance_actions_log.csv",
        "maintenance_task_state.csv",
        "maintenance_work_packages.csv",
        "_app_state.json",
        "maintenance_test_presets.json",
        "tm_step_checklists.json",
    }
    frames = []
    for fname in sorted(os.listdir(maint_folder)):
        if fname in ignore_files:
            continue
        if not fname.lower().endswith((".xlsx", ".xls", ".csv")):
            continue
        fpath = os.path.join(maint_folder, fname)
        try:
            raw = read_maintenance_file(fpath)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        df = normalize_maintenance_df(raw)
        df["Source_File"] = fname
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    dfm = pd.concat(frames, ignore_index=True)
    comp_s = dfm.get("Component", pd.Series([""] * len(dfm))).astype(str).str.strip()
    task_s = dfm.get("Task", pd.Series([""] * len(dfm))).astype(str).str.strip()
    mode_s = dfm.get("Tracking_Mode", pd.Series([""] * len(dfm))).astype(str).str.strip()
    tid_s = dfm.get("Task_ID", pd.Series([""] * len(dfm))).astype(str).str.strip()
    placeholder_mask = comp_s.eq("") & task_s.eq("") & mode_s.eq("") & tid_s.eq("")
    if int(placeholder_mask.sum()) > 0:
        dfm = dfm.loc[~placeholder_mask].copy()
    comp_s = dfm.get("Component", pd.Series([""] * len(dfm))).astype(str).str.strip()
    task_s = dfm.get("Task", pd.Series([""] * len(dfm))).astype(str).str.strip()
    invalid_task_mask = comp_s.eq("") | task_s.eq("")
    if int(invalid_task_mask.sum()) > 0:
        dfm = dfm.loc[~invalid_task_mask].copy()
    return dfm


def compute_maintenance_status_df(
    dfm: pd.DataFrame,
    *,
    current_draw_count: int,
    furnace_hours: float,
    uv1_hours: float,
    uv2_hours: float,
    warn_days: int,
    warn_hours: float,
    current_date=None,
) -> pd.DataFrame:
    if dfm is None or dfm.empty:
        return pd.DataFrame(columns=["Status"])

    current_date = current_date or dt.date.today()
    dfm = dfm.copy()

    def pick_current_hours(hours_source: str) -> float:
        hs = norm_source(hours_source)
        if hs in ("uv2", "uv 2", "uv_system_2", "uv system 2", "uv-system-2", "system2", "system 2"):
            return float(uv2_hours)
        if hs in ("uv1", "uv 1", "uv_system_1", "uv system 1", "uv-system-1", "system1", "system 1"):
            return float(uv1_hours)
        return float(furnace_hours)

    def split_trigger_modes(row) -> list:
        raw = safe_str(row.get("Trigger_Modes", "")).strip()
        out = []
        if raw:
            for p in raw.replace(";", ",").replace("|", ",").split(","):
                mv = mode_norm(p)
                if mv in ("hours", "draws", "calendar", "event") and mv not in out:
                    out.append(mv)
        if not out:
            tracking_mode = safe_str(row.get("Tracking_Mode", "")).strip().lower()
            if tracking_mode in ("either", "any", "both"):
                cal_value, cal_unit = _legacy_either_calendar(row)
                hours_value = _legacy_either_hours_interval(row)
                if cal_value is not None:
                    out.append("calendar")
                if hours_value is not None:
                    out.append("hours")
            else:
                mv = mode_norm(tracking_mode)
                if mv:
                    out = [mv]
        return out

    def split_hours_sources(row) -> list:
        raw = safe_str(row.get("Trigger_Hours_Source", "")).strip()
        if not raw:
            raw = safe_str(row.get("Hours_Source", "")).strip()
        if not raw:
            return ["furnace"]
        out = []
        for p in raw.replace(";", ",").replace("|", ",").split(","):
            sv = norm_source(p)
            if not sv:
                continue
            if sv in ("uv", "uv both", "uv-both", "uv1+uv2", "uv2+uv1"):
                for uv in ("uv1", "uv2"):
                    if uv not in out:
                        out.append(uv)
            elif sv in ("uv1", "uv 1", "uv_system_1", "uv system 1", "uv-system-1", "system1", "system 1"):
                if "uv1" not in out:
                    out.append("uv1")
            elif sv in ("uv2", "uv 2", "uv_system_2", "uv system 2", "uv-system-2", "system2", "system 2"):
                if "uv2" not in out:
                    out.append("uv2")
            else:
                if "furnace" not in out:
                    out.append("furnace")
        return out or ["furnace"]

    def get_hours_baseline(row, src: str):
        if src == "uv1":
            b = parse_float(row.get("Last_Done_Hours_UV1", None))
            return b if b is not None else parse_float(row.get("Last_Done_Hours", None))
        if src == "uv2":
            b = parse_float(row.get("Last_Done_Hours_UV2", None))
            return b if b is not None else parse_float(row.get("Last_Done_Hours", None))
        b = parse_float(row.get("Last_Done_Hours_Furnace", None))
        return b if b is not None else parse_float(row.get("Last_Done_Hours", None))

    dfm["Last_Done_Date_parsed"] = dfm["Last_Done_Date"].apply(parse_date)
    dfm["Last_Done_Hours_parsed"] = dfm["Last_Done_Hours"].apply(parse_float)
    dfm["Last_Done_Draw_parsed"] = dfm["Last_Done_Draw"].apply(parse_int)
    dfm["Current_Hours_For_Task"] = dfm["Hours_Source"].apply(pick_current_hours)
    dfm["Tracking_Mode_norm"] = dfm["Tracking_Mode"].apply(mode_norm)
    dfm["Trigger_Modes_norm"] = dfm.apply(split_trigger_modes, axis=1)

    def next_due_date(row):
        modes = row.get("Trigger_Modes_norm", [])
        if "calendar" not in modes:
            return None
        last = row.get("Last_Done_Date_parsed", None)
        if last is None:
            return None
        try:
            raw_v = _value_or_fallback(row, "Trigger_Calendar_Value", "Interval_Value")
            if safe_str(row.get("Tracking_Mode", "")).strip().lower() in ("either", "any", "both"):
                legacy_v, legacy_unit = _legacy_either_calendar(row)
                if legacy_v is not None:
                    raw_v = legacy_v
        except Exception:
            return None
        unit = str(_value_or_fallback(row, "Trigger_Calendar_Unit", "Interval_Unit")).strip().lower()
        if safe_str(row.get("Tracking_Mode", "")).strip().lower() in ("either", "any", "both"):
            _, legacy_unit = _legacy_either_calendar(row)
            if legacy_unit:
                unit = legacy_unit
        try:
            v = int(float(raw_v))
        except Exception:
            return None
        base = pd.Timestamp(last)
        if pd.isna(base) or base is pd.NaT:
            return None
        if "day" in unit:
            out = base + pd.DateOffset(days=v)
        elif "week" in unit:
            out = base + pd.DateOffset(weeks=v)
        elif "month" in unit:
            out = base + pd.DateOffset(months=v)
        elif "year" in unit:
            out = base + pd.DateOffset(years=v)
        else:
            out = base + pd.DateOffset(days=v)
        if pd.isna(out) or out is pd.NaT:
            return None
        return out.date()

    def next_due_hours(row):
        modes = row.get("Trigger_Modes_norm", [])
        if "hours" not in modes:
            return None
        try:
            raw_v = _value_or_fallback(row, "Trigger_Hours_Interval", "Interval_Value")
            if safe_str(row.get("Tracking_Mode", "")).strip().lower() in ("either", "any", "both"):
                legacy_hours = _legacy_either_hours_interval(row)
                if legacy_hours is not None:
                    raw_v = legacy_hours
            v = float(raw_v)
        except Exception:
            return None
        if pd.isna(v):
            return None
        due_rows = []
        for src in split_hours_sources(row):
            last_h = get_hours_baseline(row, src)
            if last_h is None:
                continue
            due_h = float(last_h) + float(v)
            cur_h = float(pick_current_hours(src))
            due_rows.append((due_h - cur_h, due_h))
        if not due_rows:
            return None
        due_rows.sort(key=lambda x: x[0])
        return float(due_rows[0][1])

    def next_due_draw(row):
        modes = row.get("Trigger_Modes_norm", [])
        if "draws" not in modes:
            return None
        last_d = row.get("Last_Done_Draw_parsed", None)
        if last_d is None:
            return None
        try:
            v = int(float(_value_or_fallback(row, "Trigger_Draws_Interval", "Interval_Value")))
        except Exception:
            return None
        return int(last_d) + int(v)

    dfm["Next_Due_Date"] = dfm.apply(next_due_date, axis=1)
    dfm["Next_Due_Hours"] = dfm.apply(next_due_hours, axis=1)
    dfm["Next_Due_Draw"] = dfm.apply(next_due_draw, axis=1)

    def status_row(row):
        modes = row.get("Trigger_Modes_norm", [])
        mode = row.get("Tracking_Mode_norm", "")
        if mode == "event":
            return "ROUTINE"
        overdue = False
        due_soon = False
        nd = row.get("Next_Due_Date", None)
        nh = row.get("Next_Due_Hours", None)
        ndr = row.get("Next_Due_Draw", None)
        missing_calendar_baseline = "calendar" in modes and row.get("Last_Done_Date_parsed", None) is None
        missing_draws_baseline = "draws" in modes and row.get("Last_Done_Draw_parsed", None) is None
        missing_hours_baseline = False
        if "hours" in modes:
            for src in split_hours_sources(row):
                if get_hours_baseline(row, src) is None:
                    missing_hours_baseline = True
                    break
        if missing_calendar_baseline or missing_draws_baseline or missing_hours_baseline:
            overdue = True
        if "calendar" in modes and nd is not None and not pd.isna(nd):
            if nd < current_date:
                overdue = True
            else:
                thresh = row.get("Due_Threshold_Days", np.nan)
                try:
                    thresh = int(float(thresh)) if not pd.isna(thresh) else int(warn_days)
                except Exception:
                    thresh = int(warn_days)
                if (nd - current_date).days <= thresh:
                    due_soon = True
        if "hours" in modes:
            try:
                raw_v = _value_or_fallback(row, "Trigger_Hours_Interval", "Interval_Value")
                if safe_str(row.get("Tracking_Mode", "")).strip().lower() in ("either", "any", "both"):
                    legacy_hours = _legacy_either_hours_interval(row)
                    if legacy_hours is not None:
                        raw_v = legacy_hours
                interval_h = float(raw_v)
            except Exception:
                interval_h = np.nan
            if not pd.isna(interval_h):
                for src in split_hours_sources(row):
                    last_h = get_hours_baseline(row, src)
                    if last_h is None:
                        continue
                    due_h = float(last_h) + float(interval_h)
                    cur_h = float(pick_current_hours(src))
                    if due_h < cur_h:
                        overdue = True
                    elif (due_h - cur_h) <= float(warn_hours):
                        due_soon = True
        if "draws" in modes and ndr is not None and not pd.isna(ndr):
            ndr = int(ndr)
            if ndr < int(current_draw_count):
                overdue = True
            elif (ndr - int(current_draw_count)) <= 5:
                due_soon = True
        if overdue:
            return "OVERDUE"
        if due_soon:
            return "DUE SOON"
        return "OK"

    dfm["Status"] = dfm.apply(status_row, axis=1)
    return dfm
