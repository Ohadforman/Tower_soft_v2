from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parent
SOURCE_ROOT_DEFAULT = APP_DIR.parent
SERVER_PY = APP_DIR / "server.py"


def api(base_url: str, path: str, payload: dict | None = None, expect_json: bool = True):
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
            body = response.read()
            if not expect_json:
                return body
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{path} failed: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        handle.listen(1)
        return int(handle.getsockname()[1])


def copy_tree_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


@contextmanager
def isolated_root(source_root: Path, keep_temp: bool = False):
    temp_root = Path(tempfile.mkdtemp(prefix="tower-maint-safe-"))
    try:
        copy_tree_if_exists(source_root / "data", temp_root / "data")
        copy_tree_if_exists(source_root / "maintenance", temp_root / "maintenance")
        copy_tree_if_exists(source_root / "config", temp_root / "config")
        copy_tree_if_exists(source_root / "state", temp_root / "state")
        copy_tree_if_exists(source_root / "manuals", temp_root / "manuals")
        copy_tree_if_exists(source_root / "reports", temp_root / "reports")
        (temp_root / "hooks" / "done_csv_snapshots").mkdir(parents=True, exist_ok=True)
        (temp_root / "logs").mkdir(parents=True, exist_ok=True)
        (temp_root / "development_media").mkdir(parents=True, exist_ok=True)
        (temp_root / "backups").mkdir(parents=True, exist_ok=True)
        (temp_root / "data_set_csv").mkdir(parents=True, exist_ok=True)
        yield temp_root
    finally:
        if not keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)


@contextmanager
def isolated_server(source_root: Path, keep_temp: bool = False):
    with isolated_root(source_root, keep_temp=keep_temp) as temp_root:
        port = free_port()
        env = os.environ.copy()
        env["TOWER_REBUILD_ROOT_DIR"] = str(temp_root)
        env["TOWER_REBUILD_PORT"] = str(port)
        env["TOWER_REBUILD_HOST"] = "127.0.0.1"
        pythonpath_entries = [str(source_root)]
        existing_pythonpath = str(env.get("PYTHONPATH", "") or "").strip()
        if existing_pythonpath:
            pythonpath_entries.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
        process = subprocess.Popen(
            [sys.executable, str(SERVER_PY)],
            cwd=str(APP_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base_url = f"http://127.0.0.1:{port}"
        try:
            started = False
            for _ in range(60):
                if process.poll() is not None:
                    output = ""
                    if process.stdout is not None:
                        output = process.stdout.read() or ""
                    raise RuntimeError(f"Isolated maintenance server exited early.\n{output}")
                try:
                    api(base_url, "/api/bootstrap")
                    started = True
                    break
                except Exception:
                    time.sleep(0.5)
            require(started, "Timed out waiting for the isolated Tower rebuild server to start.")
            yield temp_root, base_url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def find_source_template(maintenance_dir: Path) -> str:
    preferred = maintenance_dir / "GenericLubrication_Maintenance_Tracker_Template.xlsx"
    if preferred.exists():
        return preferred.name
    candidates = sorted(maintenance_dir.glob("*.xlsx"))
    require(bool(candidates), f"No maintenance source workbook was found in {maintenance_dir}")
    return candidates[0].name


def task_map(payload: dict) -> dict[str, dict]:
    return {str(item.get("task_id", "")).strip(): item for item in payload.get("tasks", []) if str(item.get("task_id", "")).strip()}


def select_blocked_part_tasks(payload: dict, limit: int = 2) -> list[dict]:
    candidates = []
    for task in payload.get("tasks", []):
        unordered = task.get("missing_parts_unordered") or task.get("missing_parts") or []
        if not unordered:
            continue
        if int(task.get("linked_open_count") or 0) > 0:
            continue
        if str(task.get("status", "")).strip().upper() not in {"BLOCKED_PARTS", "PREP_READY"}:
            continue
        candidates.append(task)
        if len(candidates) >= limit:
            break
    require(len(candidates) >= limit, "Could not find enough blocked maintenance tasks with unordered missing parts for safe flow testing.")
    return candidates


def find_order_indices(part_orders_csv: Path, task_id: str) -> list[int]:
    rows = read_csv_rows(part_orders_csv)
    return [
        index
        for index, row in enumerate(rows)
        if str(row.get("Maintenance Task ID", "")).strip() == task_id
    ]


def first_manual_task(payload: dict) -> dict | None:
    for task in payload.get("tasks", []):
        if str(task.get("manual_link", "")).strip():
            return task
    return None


def first_inventory_location(data_dir: Path) -> str:
    locations_csv = data_dir / "parts_locations.csv"
    for row in read_csv_rows(locations_csv):
        location_name = str(row.get("Location Name", "")).strip()
        if location_name and location_name.lower() != "mounted":
            return location_name
    return "Safe rack"


def ensure_payload_shape(payload: dict) -> None:
    required_keys = {
        "tasks",
        "prep_queue",
        "execute_queue",
        "execute_plan_queue",
        "blocked_tracker",
        "timeline_runtime",
        "fault_open_total",
    }
    missing = sorted(required_keys.difference(payload.keys()))
    require(not missing, f"Maintenance payload is missing keys: {', '.join(missing)}")


def run_safe_flow(source_root: Path, keep_temp: bool = False) -> dict[str, object]:
    results: list[str] = []
    with isolated_server(source_root, keep_temp=keep_temp) as (temp_root, base_url):
        maintenance_dir = temp_root / "maintenance"
        data_dir = temp_root / "data"
        maintenance_payload = api(base_url, "/api/maintenance")
        ensure_payload_shape(maintenance_payload)
        results.append(f"maintenance payload OK ({len(maintenance_payload['tasks'])} tasks)")

        runtime_save = api(
            base_url,
            "/api/maintenance/runtime",
            {
                "furnaceHours": 12.5,
                "uv1Hours": 25,
                "uv2Hours": 37.5,
            },
        )
        require(runtime_save.get("ok"), f"Runtime update failed: {runtime_save}")
        runtime_payload = api(base_url, "/api/maintenance")
        runtime = runtime_payload.get("timeline_runtime") or {}
        require(float(runtime.get("furnace_hours") or 0) == 12.5, "Furnace runtime did not update in isolated maintenance payload.")
        require(float(runtime.get("uv1_hours") or 0) == 25.0, "UV1 runtime did not update in isolated maintenance payload.")
        require(float(runtime.get("uv2_hours") or 0) == 37.5, "UV2 runtime did not update in isolated maintenance payload.")
        results.append("runtime update OK")

        template_name = find_source_template(maintenance_dir)
        scratch_task_name = f"Safe scratch task {datetime.now().strftime('%Y%m%d%H%M%S')}"
        scratch_create = api(
            base_url,
            "/api/maintenance/create-task",
            {
                "sourceFile": template_name,
                "component": "Safe Test Rig",
                "task": scratch_task_name,
                "taskGroup": "Smoke",
            },
        )
        require(scratch_create.get("ok"), f"Scratch maintenance create-task failed: {scratch_create}")
        scratch_task_id = str(scratch_create.get("taskId") or "").strip()
        require(scratch_task_id, "Scratch maintenance create-task did not return a task id.")
        scratch_save = api(
            base_url,
            "/api/maintenance/work-package",
            {
                "taskId": scratch_task_id,
                "component": "Safe Test Rig",
                "task": scratch_task_name,
                "taskGroup": "Smoke",
                "sourceFile": template_name,
                "trackingMode": "calendar",
                "triggerModes": "calendar",
                "triggerCalendarValue": "1",
                "triggerCalendarUnit": "weeks",
                "calendarRule": "weekly",
                "requiredParts": "",
                "requiredTools": "multimeter",
                "preparationChecklist": '[{\"id\":\"prep-1\",\"done\":false,\"text\":\"Gather tools\"}]',
                "procedureSteps": '[{\"id\":\"step-1\",\"done\":false,\"text\":\"Check indicator lights\"}]',
                "safetyProtocol": "Lockout not required for this smoke task.",
                "drawStopPlan": "No draw stop needed.",
                "estStopMin": "20",
                "completionCriteria": "Indicator lights verified.",
                "procedureSummary": "Smoke test builder package summary.",
                "manualName": "",
                "manualLink": "",
                "manualPage": "",
            },
        )
        require(scratch_save.get("ok"), f"Scratch maintenance work-package save failed: {scratch_save}")
        scratch_delete = api(
            base_url,
            "/api/maintenance/delete-task",
            {
                "taskId": scratch_task_id,
                "component": "Safe Test Rig",
                "task": scratch_task_name,
                "sourceFile": template_name,
            },
        )
        require(scratch_delete.get("ok"), f"Scratch maintenance delete-task failed: {scratch_delete}")
        deleted_payload = api(base_url, "/api/maintenance")
        require(scratch_task_id not in task_map(deleted_payload), "Scratch maintenance task still exists after delete.")
        results.append("builder create/save/delete OK")

        flow_task_name = f"Safe flow task {datetime.now().strftime('%Y%m%d%H%M%S')}"
        flow_create = api(
            base_url,
            "/api/maintenance/create-task",
            {
                "sourceFile": template_name,
                "component": "Safe Flow Rig",
                "task": flow_task_name,
                "taskGroup": "Smoke",
            },
        )
        require(flow_create.get("ok"), f"Flow maintenance create-task failed: {flow_create}")
        flow_task_id = str(flow_create.get("taskId") or "").strip()
        require(flow_task_id, "Flow maintenance create-task did not return a task id.")
        flow_save = api(
            base_url,
            "/api/maintenance/work-package",
            {
                "taskId": flow_task_id,
                "component": "Safe Flow Rig",
                "task": flow_task_name,
                "taskGroup": "Smoke",
                "sourceFile": template_name,
                "trackingMode": "calendar",
                "triggerModes": "calendar",
                "triggerCalendarValue": "1",
                "triggerCalendarUnit": "weeks",
                "calendarRule": "weekly",
                "requiredParts": "",
                "requiredTools": "inspection torch",
                "preparationChecklist": '[{\"id\":\"prep-1\",\"done\":false,\"text\":\"Check workspace\"}]',
                "procedureSteps": '[{\"id\":\"step-1\",\"done\":false,\"text\":\"Run smoke maintenance check\"}]',
                "safetyProtocol": "Use normal PPE.",
                "drawStopPlan": "No draw stop required.",
                "estStopMin": "25",
                "completionCriteria": "Smoke maintenance task verified.",
                "procedureSummary": "Safe maintenance flow test package.",
            },
        )
        require(flow_save.get("ok"), f"Flow maintenance work-package save failed: {flow_save}")
        prep_done_result = api(
            base_url,
            "/api/maintenance/state",
            {
                "taskId": flow_task_id,
                "component": "Safe Flow Rig",
                "task": flow_task_name,
                "state": "PREP_DONE",
                "note": "Safe smoke test prep-done path.",
            },
        )
        require(prep_done_result.get("ok"), f"Prep done state update failed: {prep_done_result}")
        after_prep_payload = api(base_url, "/api/maintenance")
        flow_task = task_map(after_prep_payload).get(flow_task_id)
        require(flow_task is not None, "Flow maintenance task disappeared after PREP_DONE update.")
        require(str(flow_task.get("status", "")).strip().upper() == "PREP_DONE", "Flow maintenance task did not enter PREP_DONE state.")
        results.append("prep done override OK")

        fault_create = api(
            base_url,
            "/api/maintenance/fault",
            {
                "action": "create",
                "component": "Safe Flow Rig",
                "title": "Safe maintenance smoke fault",
                "description": "Created during isolated maintenance verification.",
                "severity": "medium",
                "actor": "safe-smoke",
            },
        )
        require(fault_create.get("ok"), f"Maintenance fault create failed: {fault_create}")
        fault_payload = api(base_url, "/api/maintenance")
        fault_row = next(
            (
                item for item in fault_payload.get("faults_open", [])
                if str(item.get("component", "")).strip() == "Safe Flow Rig"
                and str(item.get("title", "")).strip() == "Safe maintenance smoke fault"
            ),
            None,
        )
        require(fault_row is not None, "Created maintenance fault is missing from open faults.")
        fault_close = api(
            base_url,
            "/api/maintenance/fault",
            {
                "action": "close",
                "faultId": str(fault_row.get("fault_id", "")).strip(),
                "note": "Closed during isolated verification.",
                "fixSummary": "Safe smoke close path verified.",
                "actor": "safe-smoke",
            },
        )
        require(fault_close.get("ok"), f"Maintenance fault close failed: {fault_close}")
        closed_fault_payload = api(base_url, "/api/maintenance")
        require(
            any(str(item.get("fault_id", "")).strip() == str(fault_row.get("fault_id", "")).strip() for item in closed_fault_payload.get("faults_closed", [])),
            "Closed maintenance fault is missing from closed faults list.",
        )
        results.append("fault create/close OK")

        manual_task = first_manual_task(after_prep_payload)
        if manual_task and (temp_root / "manuals").exists():
            manual_path = str(manual_task.get("manual_link", "")).strip()
            if manual_path:
                manual_bytes = api(
                    base_url,
                    f"/api/maintenance/manual?path={urllib.parse.quote(manual_path)}",
                    expect_json=False,
                )
                require(len(manual_bytes) > 0, "Maintenance manual endpoint returned empty content.")
                results.append("manual fetch OK")

        blocked_candidates = select_blocked_part_tasks(after_prep_payload, limit=2)
        bulk_order_tasks = [
            {
                "taskId": str(task.get("task_id", "")).strip(),
                "component": str(task.get("component", "")).strip(),
                "task": str(task.get("task", "")).strip(),
                "parts": list(task.get("missing_parts_unordered") or task.get("missing_parts") or []),
            }
            for task in blocked_candidates
        ]
        bulk_order = api(
            base_url,
            "/api/maintenance/create-parts-orders",
            {"tasks": bulk_order_tasks},
        )
        require(bulk_order.get("ok"), f"Bulk maintenance parts order failed: {bulk_order}")
        after_order_payload = api(base_url, "/api/maintenance")
        after_order_map = task_map(after_order_payload)
        for task in blocked_candidates:
            ordered_task = after_order_map.get(str(task.get("task_id", "")).strip())
            require(ordered_task is not None, "Blocked maintenance task disappeared after ordering parts.")
            require(str(ordered_task.get("status", "")).strip().upper() == "WAIT FOR PART", f"{ordered_task.get('task_id')} did not enter WAIT FOR PART after ordering.")
            require(int(ordered_task.get("linked_open_count") or 0) >= 1, f"{ordered_task.get('task_id')} is missing linked open orders after ordering.")
        results.append("bulk order parts OK")

        part_orders_csv = data_dir / "part_orders.csv"
        sync_task = blocked_candidates[0]
        sync_task_id = str(sync_task.get("task_id", "")).strip()
        inventory_location = first_inventory_location(data_dir)
        sync_indices = find_order_indices(part_orders_csv, sync_task_id)
        require(sync_indices, f"No part orders were written for {sync_task_id}.")
        for index in sync_indices:
            update_result = api(
                base_url,
                "/api/parts/update",
                {
                    "index": index,
                    "status": "Received",
                    "orderedBy": "safe-smoke",
                    "dateOrdered": datetime.now().strftime("%Y-%m-%d"),
                    "receivedDate": datetime.now().strftime("%Y-%m-%d"),
                    "company": "Safe Smoke Supply",
                    "inventoryAction": "Locate in inventory",
                    "inventoryLocation": inventory_location,
                },
            )
            require(update_result.get("ok"), f"Part order receive/sync failed for {sync_task_id}: {update_result}")
        after_sync_payload = api(base_url, "/api/maintenance")
        synced_task = task_map(after_sync_payload).get(sync_task_id)
        require(synced_task is not None, "Synced maintenance task disappeared after inventory sync.")
        synced_status = str(synced_task.get("status", "")).strip().upper()
        require(
            synced_status == "PREP_DONE",
            (
                f"{sync_task_id} did not auto-promote to PREP_DONE after inventory sync. "
                f"status={synced_status or '<blank>'}, "
                f"flow={synced_task.get('flow_state')!r}, "
                f"missing_parts={synced_task.get('missing_parts')!r}, "
                f"missing_parts_unordered={synced_task.get('missing_parts_unordered')!r}, "
                f"linked_open_count={synced_task.get('linked_open_count')!r}, "
                f"linked_received_waiting_sync={synced_task.get('linked_received_waiting_sync')!r}, "
                f"linked_ready_count={synced_task.get('linked_ready_count')!r}"
            ),
        )
        require(int(synced_task.get("linked_ready_count") or 0) >= 1, f"{sync_task_id} did not record ready linked parts after sync.")
        results.append("receive/sync to prep-done OK")

        schedule_start_a = datetime.now() + timedelta(minutes=20)
        schedule_start_b = datetime.now() + timedelta(minutes=80)
        schedule_result = api(
            base_url,
            "/api/maintenance/schedule",
            {
                "tasks": [
                    {
                        "taskId": flow_task_id,
                        "component": "Safe Flow Rig",
                        "task": flow_task_name,
                    },
                    {
                        "taskId": sync_task_id,
                        "component": str(synced_task.get("component", "")).strip(),
                        "task": str(synced_task.get("task", "")).strip(),
                    },
                ],
                "windows": [
                    {
                        "start": schedule_start_a.strftime("%Y-%m-%d %H:%M:%S"),
                        "end": (schedule_start_a + timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S"),
                        "label": "Safe window A",
                    },
                    {
                        "start": schedule_start_b.strftime("%Y-%m-%d %H:%M:%S"),
                        "end": (schedule_start_b + timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S"),
                        "label": "Safe window B",
                    },
                ],
            },
        )
        require(schedule_result.get("ok"), f"Bulk maintenance schedule failed: {schedule_result}")
        scheduled_payload = api(base_url, "/api/maintenance")
        scheduled_map = task_map(scheduled_payload)
        require(str((scheduled_map.get(flow_task_id) or {}).get("status", "")).strip().upper() == "SCHEDULED", "Flow maintenance task did not enter SCHEDULED state.")
        require(str((scheduled_map.get(sync_task_id) or {}).get("status", "")).strip().upper() == "SCHEDULED", f"{sync_task_id} did not enter SCHEDULED state.")
        schedule_rows = read_csv_rows(data_dir / "tower_schedule.csv")
        task_schedule_rows = [row for row in schedule_rows if f"Task ID: {flow_task_id}" in str(row.get("Description", ""))]
        require(task_schedule_rows, "Scheduled maintenance row is missing from tower_schedule.csv.")
        sync_schedule_rows = [row for row in schedule_rows if f"Task ID: {sync_task_id}" in str(row.get("Description", ""))]
        require(sync_schedule_rows, f"Scheduled maintenance row is missing for {sync_task_id}.")
        require(
            str(task_schedule_rows[-1].get("Start DateTime", "")).strip() != str(sync_schedule_rows[-1].get("Start DateTime", "")).strip(),
            "Bulk schedule windows did not spread the scheduled tasks across distinct start times.",
        )
        results.append("bulk schedule spread OK")

        complete_result = api(
            base_url,
            "/api/maintenance/complete",
            {
                "taskId": flow_task_id,
                "component": "Safe Flow Rig",
                "task": flow_task_name,
                "trackingMode": "calendar",
                "note": "Safe complete flow verification.",
            },
        )
        require(complete_result.get("ok"), f"Maintenance complete failed: {complete_result}")
        completed_payload = api(base_url, "/api/maintenance")
        completed_flow_task = task_map(completed_payload).get(flow_task_id)
        require(completed_flow_task is not None, "Completed flow task disappeared from maintenance payload.")
        require(str(completed_flow_task.get("status", "")).strip().upper() == "DONE_NOW", "Completed flow task did not enter DONE_NOW state.")
        state_rows = read_csv_rows(maintenance_dir / "maintenance_task_state.csv")
        state_row = next((row for row in reversed(state_rows) if str(row.get("task_id", "")).strip() == flow_task_id), None)
        require(state_row is not None, "Completed flow task is missing from maintenance state log.")
        require(str(state_row.get("state", "")).strip().upper() == "DONE_NOW", "Maintenance state log did not capture DONE_NOW after complete.")
        action_rows = read_csv_rows(maintenance_dir / "maintenance_actions_log.csv")
        require(any(str(row.get("maintenance_task_id", "")).strip() == flow_task_id for row in action_rows), "Maintenance actions log is missing the completed flow task.")
        next_schedule_rows = [row for row in read_csv_rows(data_dir / "tower_schedule.csv") if f"Task ID: {flow_task_id}" in str(row.get("Description", ""))]
        require(next_schedule_rows, "Completed flow task did not get a next maintenance schedule row.")
        results.append("complete and reschedule OK")

        return {
            "ok": True,
            "base_url": base_url,
            "temp_root": str(temp_root),
            "results": results,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the maintenance flow safely against an isolated Tower workspace copy.")
    parser.add_argument("--source-root", default=str(SOURCE_ROOT_DEFAULT), help="Live Tower root to copy into the disposable workspace.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the disposable workspace after the run for inspection.")
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve()
    try:
        result = run_safe_flow(source_root, keep_temp=args.keep_temp)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS")
    for item in result["results"]:
        print(f"- {item}")
    if args.keep_temp:
        print(f"- temp root kept at {result['temp_root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
