from __future__ import annotations

import argparse
import csv
import json
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path


ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Ww6NwAAAABJRU5ErkJggg=="
)
SYNTHETIC_RAW_LOG_NAME = "Training_full_flow_raw.csv"


def api(base_url: str, path: str, payload: dict | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{path} failed: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def diagnostics_path_payload(payload: dict) -> dict[str, str]:
    return {
        str(row.get("key", "")).strip(): str(row.get("path", "")).strip()
        for row in payload.get("path_rows", []) or []
        if str(row.get("key", "")).strip()
    }


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_synthetic_raw_log(path: Path, rows: int = 140) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Data Log",
        "[plc]BareFibreDiaDisplay,[plc]FrnTmpMv,[plc]CpLenTareVal,[plc]UVLamp1Intensity,[plc]FrnMFC1MV,[plc]GoodFibreStartState,[plc]TrendMarkerPulse",
    ]
    for index in range(rows):
        bare = 125.0 + ((index % 7) * 0.03)
        furnace = 2100.0 + (index * 0.45)
        length = round(index * 0.05, 3)
        uv = 82.0 + ((index % 5) * 0.2)
        mfc = 1.1 + ((index % 4) * 0.05)
        good_state = 1 if 10 <= index <= 120 else 0
        marker = 1 if index in {40, 80, 120} else 0
        lines.append(f"{bare:.3f},{furnace:.2f},{length:.3f},{uv:.2f},{mfc:.2f},{good_state},{marker}")
    path.write_text("\n".join(lines), encoding="utf-8")


def find_raw_log_candidate(logs_dir: Path) -> Path:
    candidates: list[tuple[int, str, Path]] = []
    for path in sorted(logs_dir.glob("*.csv")):
        name = path.name.lower()
        if name.startswith("modified_") or "fake" in name or "simulat" in name or "test" in name:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:3]
        except OSError:
            continue
        joined = "\n".join(lines).lower()
        score = 0
        if "data log" in joined:
            score += 2
        if "[plc]" in joined:
            score += 2
        if "training" in name:
            score += 1
        if score > 0:
            candidates.append((score, path.name.lower(), path))
    require(bool(candidates), f"No raw machine log candidate found in {logs_dir}")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def latest_draw_order_index(draw_orders_csv: Path, preform_number: str) -> int:
    rows = read_csv_rows(draw_orders_csv)
    for index in range(len(rows) - 1, -1, -1):
        if str(rows[index].get("Preform Number", "")).strip() == preform_number:
            return index
    raise RuntimeError(f"No draw order row found for preform {preform_number}")


def find_order_indices(part_orders_csv: Path, task_id: str) -> list[int]:
    rows = read_csv_rows(part_orders_csv)
    return [
        index
        for index, row in enumerate(rows)
        if str(row.get("Maintenance Task ID", "")).strip() == task_id
    ]


def first_inventory_location(data_dir: Path) -> str:
    locations_csv = data_dir / "parts_locations.csv"
    for row in read_csv_rows(locations_csv):
        location_name = str(row.get("Location Name", "")).strip()
        if location_name and location_name.lower() != "mounted":
            return location_name
    return "Safe rack"


def load_state(state_path: Path) -> dict:
    require(state_path.exists(), f"State file is missing: {state_path}")
    return read_json(state_path)


@contextmanager
def temporary_raw_log_override(base_url: str):
    diagnostics = api(base_url, "/api/data-diagnostics")
    original_paths = diagnostics_path_payload(diagnostics)
    require(original_paths, "Diagnostics did not expose tracked paths.")
    logs_dir = Path(original_paths.get("logs_dir", "")).expanduser()
    raw_log = None
    if str(logs_dir).strip() and logs_dir.exists():
        try:
            raw_log = find_raw_log_candidate(logs_dir)
        except RuntimeError:
            raw_log = None
    if raw_log is not None:
        yield raw_log.name
        return

    temp_root = Path(tempfile.mkdtemp(prefix="tower-full-flow-logs-"))
    logs_override = temp_root / "logs_override"
    raw_log_path = logs_override / SYNTHETIC_RAW_LOG_NAME
    try:
        write_synthetic_raw_log(raw_log_path)
        override_paths = dict(original_paths)
        override_paths["logs_dir"] = str(logs_override)
        save_result = api(base_url, "/api/data-diagnostics/paths", override_paths)
        require(save_result.get("ok"), f"Path override save failed: {save_result}")
        yield raw_log_path.name
    finally:
        try:
            api(base_url, "/api/data-diagnostics/paths", original_paths)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


def prepare_active(base_url: str, root_dir: Path, state_path: Path, raw_log_name: str) -> dict:
    data_dir = root_dir / "data"
    maintenance_dir = root_dir / "maintenance"
    reports_dir = root_dir / "reports"

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    project = f"Full Flow Smoke {stamp}"
    preform = f"FLOWP{stamp[-4:]}"
    maintenance_task = f"Weekly full flow {stamp}"
    maintenance_component = "Full Flow Rig"
    source_file = "GenericLubrication_Maintenance_Tracker_Template.xlsx"

    order_create = api(
        base_url,
        "/api/order-draw/create",
        {
            "order": {
                "preformNumber": preform,
                "project": project,
                "opener": "Codex",
                "priority": "Normal",
                "geometry": "ROUND",
                "requiredLength": "1250",
                "goodZones": "2",
                "preformDiameterMm": "16",
                "fiberDiameter": "125",
                "fiberTol": "1",
                "mainCoatingDiameter": "245",
                "mainTol": "2",
                "secondaryCoatingDiameter": "400",
                "secondaryTol": "3",
                "tension": "35",
                "drawSpeed": "5",
                "furnaceTemp": "2120",
                "mainCoating": "UV Main",
                "secondaryCoating": "UV Secondary",
                "mainCoatingTemp": "62",
                "secondaryCoatingTemp": "58",
                "notes": f"Full flow test {stamp}",
                "desiredDate": (datetime.now().date() + timedelta(days=1)).isoformat(),
                "tigerCut": "0",
                "octF2f": "0",
            },
            "scheduleNow": False,
            "saveTemplate": False,
        },
    )
    require(order_create.get("ok"), f"Order draw create failed: {order_create}")
    order_index = latest_draw_order_index(data_dir / "draw_orders.csv", preform)

    draw_start = datetime.now() + timedelta(minutes=15)
    order_schedule = api(
        base_url,
        "/api/order-draw/schedule",
        {
            "orderIndex": order_index,
            "password": "DORON",
            "date": draw_start.strftime("%Y-%m-%d"),
            "startTime": draw_start.strftime("%H:%M"),
            "durationMin": "95",
            "preformNumber": preform,
        },
    )
    require(order_schedule.get("ok"), f"Order scheduling failed: {order_schedule}")

    process_start = api(
        base_url,
        "/api/process-setup/scheduled-start",
        {
            "orderIndex": order_index,
            "preformNumber": preform,
        },
    )
    require(process_start.get("ok"), f"Scheduled process-setup start failed: {process_start}")
    dataset_name = str(process_start.get("datasetName") or process_start.get("selectedCsv") or "").strip() or f"{preform}F1.csv"

    process_save = api(
        base_url,
        "/api/process-setup/save-all",
        {
            "selectedCsv": dataset_name,
            "iris": {
                "shape": "ROUND",
                "preform_diameter_mm": "63",
                "oct_f2f_mm": "",
                "tiger_cut_pct": "",
                "pm_system": False,
                "iris_mode": "Manual",
                "selected_iris_diameter_mm": "14.2",
                "base_area_mm2": "3117.245",
                "adjusted_area_mm2": "3117.245",
                "effective_preform_diameter_mm": "63",
                "gap_area_mm2": "158.4",
            },
            "coating": {
                "entry_fiber_diameter_um": "125",
                "target_first_coating_diameter_um": "245",
                "target_second_coating_diameter_um": "400",
                "primary_coating": "UV Main",
                "secondary_coating": "UV Secondary",
                "primary_temp_c": "62",
                "secondary_temp_c": "58",
                "die_mode": "Auto",
                "primary_die": "D1",
                "secondary_die": "D2",
                "draw_speed_m_min": "5",
            },
            "pid": {
                "p_gain": "1.2",
                "i_gain": "0.4",
                "tf_mode": "Auto",
                "increment_value_mm": "0.02",
            },
            "drum": {"selected_drum": "Drum-A"},
        },
    )
    require(process_save.get("ok"), f"Process setup save failed: {process_save}")

    dashboard_log = api(base_url, f"/api/dashboard/log?name={urllib.parse.quote(raw_log_name)}")
    require(dashboard_log.get("selected_file") == raw_log_name, "Dashboard did not switch to the raw log")
    rows = dashboard_log.get("rows") or []
    require(len(rows) > 80, "Raw log did not provide enough rows for zone export")

    zone_result = api(
        base_url,
        "/api/dashboard/save-zones",
        {
            "logName": raw_log_name,
            "datasetCsv": dataset_name,
            "zones": [
                {"startIndex": 0, "endIndex": 40},
                {"startIndex": 41, "endIndex": 80},
            ],
        },
    )
    require(zone_result.get("ok"), f"Dashboard zone export failed: {zone_result}")
    require((root_dir / "data_set_csv" / preform / f"{preform}F1_Z1" / f"{preform}F1_Z1.csv").exists(), "Zone Z1 CSV is missing")
    require((root_dir / "data_set_csv" / preform / f"{preform}F1_Z2" / f"{preform}F1_Z2.csv").exists(), "Zone Z2 CSV is missing")

    sql_query = api(
        base_url,
        "/api/sql-lab/query",
        {
            "dataset": dataset_name,
            "sql": "SELECT parameter_name, value FROM dataset WHERE parameter_name LIKE 'Zone 1 | %' LIMIT 5",
        },
    )
    require(sql_query.get("ok") and (sql_query.get("rows") or []), f"SQL query failed: {sql_query}")

    sql_filter = api(
        base_url,
        "/api/sql-lab/filter",
        {
            "dataset": dataset_name,
            "conditions": [
                {
                    "params": ["Zone 1 | Bare Fibre Diameter | Avg"],
                    "op": ">",
                    "v1": "0",
                    "groupLogic": "ANY (OR)",
                    "joiner": "AND",
                }
            ],
            "includeDraws": True,
            "includeMaintenance": False,
            "includeFaults": False,
        },
    )
    require(sql_filter.get("ok"), f"SQL filter failed: {sql_filter}")

    plot_result = api(
        base_url,
        "/api/dashboard/math-plot-export",
        {
            "filename": f"{preform}_plot.png",
            "content": ONE_PIXEL_PNG_BASE64,
        },
    )
    require(plot_result.get("ok"), f"Dashboard plot export failed: {plot_result}")
    require(Path(str(plot_result.get("saved_path", "")).strip()).exists(), "Plot export did not create a file")

    create_task = api(
        base_url,
        "/api/maintenance/create-task",
        {
            "sourceFile": source_file,
            "component": maintenance_component,
            "task": maintenance_task,
            "taskGroup": "Weekly",
        },
    )
    require(create_task.get("ok"), f"Maintenance create-task failed: {create_task}")
    maintenance_task_id = str(create_task.get("taskId") or "").strip()
    require(maintenance_task_id, "Maintenance create-task did not return a task id")

    save_package = api(
        base_url,
        "/api/maintenance/work-package",
        {
            "taskId": maintenance_task_id,
            "component": maintenance_component,
            "task": maintenance_task,
            "sourceFile": source_file,
            "taskGroup": "Weekly",
            "taskGroups": "Weekly",
            "owner": "Operations",
            "triggerContext": "Full flow smoke",
            "trackingMode": "Calendar",
            "hoursSource": "Furnace",
            "intervalType": "Calendar",
            "intervalValue": "1",
            "intervalUnit": "Weeks",
            "planningWindowMonths": "1",
            "dueThresholdDays": "3",
            "requiredParts": f"{preform} Grease; {preform} Wipe",
            "requiredTools": f"{preform} Wrench",
            "conditionalParts": "",
            "preparationLeadDays": "2",
            "partsCheckLeadDays": "1",
            "autoOrderMandatoryParts": "Yes",
            "triggerModes": "Calendar",
            "triggerHoursSource": "Furnace",
            "triggerHoursInterval": "",
            "triggerDrawsInterval": "",
            "triggerCalendarValue": "1",
            "triggerCalendarUnit": "Weeks",
            "calendarRule": "weekly",
            "manualName": "General Maintenance Manual",
            "manualPage": "1",
            "manualLink": "",
            "procedureSummary": "Run the weekly smoke maintenance task.",
            "safetyNotes": "Use PPE.",
            "preparationChecklist": "Check area;Confirm tools",
            "procedureSteps": "Do task;Verify output",
            "procedurePhotos": "[]",
            "sanityChecklist": "Verify complete",
            "sanityResults": "",
            "drawStopPlan": "Stop draw if needed",
            "estStopMin": "15",
            "completionCriteria": "Task complete",
            "supplierName": "Internal",
            "supplierDetails": "N/A",
            "testPreset": "",
            "testFields": "",
            "testThresholds": "",
            "testCondition": "",
            "testAction": "",
            "safetyProtocol": "Safe",
            "safetyFallRisk": "Low",
            "safetyTnmPresence": "Allowed",
        },
    )
    require(save_package.get("ok"), f"Maintenance work package failed: {save_package}")

    parts_orders = api(
        base_url,
        "/api/maintenance/create-parts-orders",
        {
            "taskId": maintenance_task_id,
            "component": maintenance_component,
            "task": maintenance_task,
            "parts": [f"{preform} Grease", f"{preform} Wipe"],
        },
    )
    require(parts_orders.get("ok"), f"Maintenance part order creation failed: {parts_orders}")

    inventory_location = first_inventory_location(data_dir)
    part_order_indices = find_order_indices(data_dir / "part_orders.csv", maintenance_task_id)
    require(part_order_indices, f"No maintenance part orders were written for {maintenance_task_id}")
    for index in part_order_indices:
        receive_result = api(
            base_url,
            "/api/parts/update",
            {
                "index": index,
                "status": "Received",
                "orderedBy": "full-flow-smoke",
                "dateOrdered": datetime.now().strftime("%Y-%m-%d"),
                "receivedDate": datetime.now().strftime("%Y-%m-%d"),
                "company": "Full Flow Supply",
                "inventoryAction": "Locate in inventory",
                "inventoryLocation": inventory_location,
            },
        )
        require(receive_result.get("ok"), f"Maintenance part order receive/sync failed: {receive_result}")

    maintenance_after_sync = api(base_url, "/api/maintenance")
    synced_task = next(
        (
            item
            for item in maintenance_after_sync.get("tasks", [])
            if str(item.get("task_id", "")).strip() == maintenance_task_id
        ),
        None,
    )
    require(synced_task is not None, "Maintenance task disappeared after inventory sync")
    require(
        str(synced_task.get("status", "")).strip().upper() == "PREP_DONE",
        f"Maintenance task did not auto-promote to PREP_DONE after inventory sync: {synced_task}",
    )

    maintenance_start = datetime.now() + timedelta(minutes=20)
    maintenance_schedule = api(
        base_url,
        "/api/maintenance/schedule",
        {
            "taskId": maintenance_task_id,
            "component": maintenance_component,
            "task": maintenance_task,
            "eventType": "Maintenance",
            "recurrence": "weekly",
            "start": maintenance_start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": (maintenance_start + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
            "label": "Full flow maintenance window",
        },
    )
    require(maintenance_schedule.get("ok"), f"Maintenance scheduling failed: {maintenance_schedule}")

    maintenance_state = api(
        base_url,
        "/api/maintenance/state",
        {
            "taskId": maintenance_task_id,
            "component": maintenance_component,
            "task": maintenance_task,
            "state": "IN_PROGRESS",
            "note": "Started from full flow smoke test",
        },
    )
    require(maintenance_state.get("ok"), f"Maintenance state change failed: {maintenance_state}")

    project_create = api(
        base_url,
        "/api/development/project",
        {
            "projectName": project,
            "purpose": "Full flow purpose",
            "target": "Full flow target",
        },
    )
    require(project_create.get("ok"), f"Development project create failed: {project_create}")

    summary_create = api(
        base_url,
        "/api/development/summary",
        {
            "projectName": project,
            "summaryTitle": "Full flow summary",
            "summaryNotes": "Summary body",
            "summaryResearcher": "Codex",
            "summaryDate": datetime.now().strftime("%Y-%m-%d"),
        },
    )
    require(summary_create.get("ok"), f"Development summary failed: {summary_create}")

    update_create = api(
        base_url,
        "/api/development/update",
        {
            "projectName": project,
            "updateTitle": "Full flow update",
            "researcher": "Codex",
            "updateDate": datetime.now().strftime("%Y-%m-%d"),
            "updateNotes": "Update body",
        },
    )
    require(update_create.get("ok"), f"Development update failed: {update_create}")

    experiment_create = api(
        base_url,
        "/api/development/experiment",
        {
            "projectName": project,
            "experimentTitle": "Full flow experiment",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "researcher": "Codex",
            "purpose": "Purpose",
            "methods": "Methods",
            "observations": "Observations",
            "results": "Results",
            "isDrawing": True,
            "drawingDetails": "Linked to draw flow",
            "drawCsv": dataset_name,
            "markdownNotes": "Markdown notes",
        },
    )
    require(experiment_create.get("ok"), f"Development experiment failed: {experiment_create}")

    export_html = api(base_url, "/api/report-center/development-export", {"projectName": project, "format": "html"})
    export_md = api(base_url, "/api/report-center/development-export", {"projectName": project, "format": "md"})
    require(export_html.get("ok"), f"Development HTML export failed: {export_html}")
    require(export_md.get("ok"), f"Development markdown export failed: {export_md}")
    require((reports_dir / "report_center" / str(export_html.get("fileName") or "")).exists(), "Development HTML export file is missing")
    require((reports_dir / "report_center" / str(export_md.get("fileName") or "")).exists(), "Development markdown export file is missing")

    home_payload = api(base_url, "/api/home")
    require(int(home_payload["metrics"][0]["value"]) >= 1, "Home Active Draws did not rise after the draw started")
    parts_payload = api(base_url, "/api/parts")
    part_order_pool = (
        parts_payload.get("all_orders")
        or parts_payload.get("queues", {}).get("maintenance_linked")
        or parts_payload.get("open_orders")
        or []
    )
    require(
        any(preform in str(item.get("part_name") or "") for item in part_order_pool),
        "Maintenance-created part orders are missing from Parts",
    )
    maintenance_payload = api(base_url, "/api/maintenance")
    require(any(str(item.get("task_id") or "") == maintenance_task_id for item in (maintenance_payload.get("execute_queue") or [])), "Maintenance execute queue is missing the in-progress task")
    finalize_payload = api(base_url, "/api/draw-finalize")
    require(dataset_name in (finalize_payload.get("dataset_files") or []), "Draw Finalize did not list the active dataset")
    require(not any("_Z" in str(name) for name in (finalize_payload.get("dataset_files") or [])), "Zone CSV leaked into Draw Finalize")

    state = {
        "project": project,
        "preform": preform,
        "dataset_name": dataset_name,
        "raw_log": raw_log_name,
        "maintenance_task_id": maintenance_task_id,
        "maintenance_task": maintenance_task,
        "maintenance_component": maintenance_component,
        "source_file": source_file,
        "reports_dir": str(reports_dir),
        "root_dir": str(root_dir),
        "maintenance_scheduled_start": maintenance_start.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_json(state_path, state)
    return state


def finish_flow(base_url: str, root_dir: Path, state_path: Path) -> dict:
    data_dir = root_dir / "data"
    maintenance_dir = root_dir / "maintenance"
    state = load_state(state_path)
    dataset_name = state["dataset_name"]
    preform = state["preform"]
    maintenance_task_id = state["maintenance_task_id"]
    maintenance_task = state["maintenance_task"]
    maintenance_component = state["maintenance_component"]
    prior_maintenance_start = datetime.strptime(state["maintenance_scheduled_start"], "%Y-%m-%d %H:%M:%S")

    draw_done = api(
        base_url,
        "/api/draw-finalize/done",
        {
            "dataset": dataset_name,
            "doneDescription": "Full flow done description",
            "preformLengthCm": "111.1",
        },
    )
    require(draw_done.get("ok"), f"Draw finalize done failed: {draw_done}")
    done_snapshot = root_dir / "hooks" / "done_csv_snapshots" / f"{preform}F1.txt"
    require(done_snapshot.exists(), "Done snapshot TXT was not created")
    done_text = done_snapshot.read_text(encoding="utf-8", errors="ignore")
    require("Full flow done description" in done_text, "Done snapshot is missing the done description")
    require("T&M SECTION" in done_text and "ZONE DATA" in done_text, "Done snapshot is missing clean summary sections")

    draw_orders_rows = read_csv_rows(data_dir / "draw_orders.csv")
    draw_order_row = next(
        (row for row in reversed(draw_orders_rows) if str(row.get("Preform Number", "")).strip() == preform),
        None,
    )
    require(draw_order_row is not None, f"Draw order row for {preform} is missing after finalize")
    require(str(draw_order_row.get("Status", "")).strip() == "Done", f"Draw order for {preform} did not move to Done")
    require(
        "Full flow done description" in str(draw_order_row.get("Done Description", "")).strip(),
        f"Draw order for {preform} is missing the done description after finalize",
    )

    home_after_draw = api(base_url, "/api/home")
    require(
        any(
            str(item.get("preform") or "").strip() == preform
            and "Full flow done description" in str(item.get("done_description") or "")
            for item in (home_after_draw.get("draws", {}).get("recent") or [])
        ),
        "Home recent completion list is missing the draw done description",
    )
    finalize_payload = api(base_url, "/api/draw-finalize")
    require(dataset_name not in (finalize_payload.get("dataset_files") or []), "Draw Finalize still lists the completed dataset")

    maintenance_complete = api(
        base_url,
        "/api/maintenance/complete",
        {
            "taskId": maintenance_task_id,
            "component": maintenance_component,
            "task": maintenance_task,
            "trackingMode": "Calendar",
            "note": "Completed by full flow smoke test",
        },
    )
    require(maintenance_complete.get("ok"), f"Maintenance complete failed: {maintenance_complete}")

    schedule_rows = [
        row
        for row in read_csv_rows(data_dir / "tower_schedule.csv")
        if f"Task ID: {maintenance_task_id}" in str(row.get("Description", ""))
    ]
    require(schedule_rows, "Maintenance completion did not leave a next scheduled row")
    schedule_rows.sort(key=lambda row: str(row.get("Start DateTime", "")))
    next_start = datetime.strptime(str(schedule_rows[-1]["Start DateTime"]), "%Y-%m-%d %H:%M:%S")
    require((next_start - prior_maintenance_start).days >= 6, "Maintenance recurrence did not jump forward by roughly one week")

    state_rows = read_csv_rows(maintenance_dir / "maintenance_task_state.csv")
    state_row = next((row for row in reversed(state_rows) if str(row.get("task_id", "")).strip() == maintenance_task_id), None)
    require(state_row is not None, "Maintenance state row was not found after completion")
    require(str(state_row.get("state", "")).strip().upper() == "DONE_NOW", "Maintenance task state did not log DONE_NOW after completion")
    require(
        "Next scheduled for" in str(state_row.get("note", "")).strip(),
        "Maintenance completion state did not capture the next scheduled note",
    )

    maintenance_payload = api(base_url, "/api/maintenance")
    require(
        not any(str(item.get("task_id") or "") == maintenance_task_id for item in (maintenance_payload.get("execute_queue") or [])),
        "Maintenance execute queue still contains the completed task",
    )

    final_home = api(base_url, "/api/home")
    state["done_snapshot"] = str(done_snapshot)
    state["next_maintenance_start"] = str(schedule_rows[-1]["Start DateTime"])
    state["final_home_active_draws"] = int(final_home["metrics"][0]["value"])
    write_json(state_path, state)
    return state


def run_full(base_url: str, root_dir: Path, state_path: Path) -> dict:
    with temporary_raw_log_override(base_url) as raw_log_name:
        state = prepare_active(base_url, root_dir, state_path, raw_log_name)
    return finish_flow(base_url, root_dir, state_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fuller Tower rebuild workflow smoke tests.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8012", help="Base URL of the running Tower rebuild app.")
    parser.add_argument("--root-dir", required=True, help="Root directory used by the running Tower rebuild app.")
    parser.add_argument(
        "--mode",
        choices=["prepare-active", "finish", "full"],
        default="full",
        help="Prepare active draw/maintenance state, finish a prepared state, or run the full workflow end to end.",
    )
    parser.add_argument("--state-file", default="", help="Optional JSON file for passing state between prepare-active and finish.")
    args = parser.parse_args()

    root_dir = Path(args.root_dir).expanduser().resolve()
    state_file = Path(args.state_file).expanduser().resolve() if args.state_file else root_dir / "state" / "full_flow_smoke_state.json"

    if args.mode == "prepare-active":
        with temporary_raw_log_override(args.base_url) as raw_log_name:
            state = prepare_active(args.base_url, root_dir, state_file, raw_log_name)
        print("full-flow-test prepare-active: PASS")
        print(json.dumps(state, indent=2))
        return
    if args.mode == "finish":
        state = finish_flow(args.base_url, root_dir, state_file)
        print("full-flow-test finish: PASS")
        print(json.dumps(state, indent=2))
        return

    state = run_full(args.base_url, root_dir, state_file)
    print("full-flow-test full: PASS")
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
