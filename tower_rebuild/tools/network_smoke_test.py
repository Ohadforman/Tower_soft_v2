from __future__ import annotations

import argparse
import base64
import csv
import json
import shutil
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path


ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Ww6NwAAAABJRU5ErkJggg=="
)
SYNTHETIC_RAW_LOG_NAME = "Training_network_smoke_raw.csv"


def api(base_url: str, path: str, payload: dict | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = {"ok": False, "message": body or str(exc)}
        raise RuntimeError(f"{path} failed with HTTP {exc.code}: {detail}") from exc
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


def count_matching_rows(path: Path, predicate) -> int:
    return sum(1 for row in read_csv_rows(path) if predicate(row))


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


def concurrent_post(base_url: str, path: str, payloads: list[dict]) -> list[dict]:
    results: list[dict] = []
    errors: list[str] = []
    results_lock = threading.Lock()

    def worker(payload: dict) -> None:
        try:
            response = api(base_url, path, payload)
            with results_lock:
                results.append(response)
        except Exception as exc:  # noqa: BLE001
            with results_lock:
                errors.append(str(exc))

    with ThreadPoolExecutor(max_workers=min(8, len(payloads) or 1)) as pool:
        for payload in payloads:
            pool.submit(worker, payload)
    require(not errors, f"Concurrent {path} calls failed: {' | '.join(errors[:4])}")
    return results


def find_created_dataset_paths(dataset_root: Path, preform: str) -> list[Path]:
    draw_dir = dataset_root / preform
    if not draw_dir.exists():
        return []
    return sorted(path for path in draw_dir.glob(f"{preform}F*.csv") if path.is_file())


def latest_draw_order_index(draw_orders_csv: Path, preform_number: str) -> int:
    rows = read_csv_rows(draw_orders_csv)
    for index in range(len(rows) - 1, -1, -1):
        if str(rows[index].get("Preform Number", "")).strip() == preform_number:
            return index
    raise RuntimeError(f"No draw order row found for preform {preform_number}")


def run(base_url: str) -> None:
    diagnostics = api(base_url, "/api/data-diagnostics")
    original_paths = diagnostics_path_payload(diagnostics)
    require(original_paths, "Diagnostics did not expose tracked paths.")

    parts_orders_csv = Path(original_paths["parts_orders_csv"])
    draw_orders_csv = Path(original_paths["orders_csv"])
    schedule_csv = Path(original_paths["schedule_csv"])

    data_dir = parts_orders_csv.parent
    root_dir = data_dir.parent
    faults_log = root_dir / "maintenance" / "faults_log.csv"
    projects_csv = data_dir / "development_projects.csv"
    updates_csv = data_dir / "experiment_updates.csv"
    experiments_csv = data_dir / "development_experiments.csv"
    run_id = datetime.now().strftime("%H%M%S")
    project_name = f"Network Smoke Project {run_id}"
    manual_preform = f"NETP9{run_id[-3:]}"
    scheduled_preform = f"NETQ9{run_id[-3:]}"

    temp_root = Path(tempfile.mkdtemp(prefix="tower-smoke-network-"))
    override_paths = dict(original_paths)
    try:
        logs_override = temp_root / "logs_override"
        dataset_override = temp_root / "dataset_override"
        done_override = temp_root / "done_override"
        reports_override = temp_root / "reports_override"
        backups_override = temp_root / "backups_override"
        selected_override = temp_root / "state" / "selected_csv.json"
        sap_override = temp_root / "imports" / "sap_inventory_override.csv"
        preform_override = temp_root / "imports" / "preform_inventory_override.csv"
        for path in (logs_override, dataset_override, done_override, reports_override, backups_override, selected_override.parent, sap_override.parent):
            path.mkdir(parents=True, exist_ok=True)
        override_log_name = f"NetworkCopy_{SYNTHETIC_RAW_LOG_NAME}"
        write_synthetic_raw_log(logs_override / override_log_name)
        selected_override.write_text('{"selected_csv": ""}', encoding="utf-8")
        sap_override.write_text("Item,Count,Units,Last Updated,Notes\nSAP Rods Set,77,sets,2026-05-14,network smoke\n", encoding="utf-8")
        preform_override.write_text("Preform Number\nOVERRIDE-PREFORM-9000\n", encoding="utf-8")

        override_paths.update(
            {
                "logs_dir": str(logs_override),
                "dataset_dir": str(dataset_override),
                "done_snapshots_dir": str(done_override),
                "reports_dir": str(reports_override),
                "report_center_dir": str(reports_override / "report_center"),
                "dashboard_plots_dir": str(reports_override / "dashboard_plots"),
                "backups_dir": str(backups_override),
                "selected_csv_json": str(selected_override),
                "sap_inventory_csv": str(sap_override),
                "preform_inventory_csv": str(preform_override),
            }
        )
        save_paths = api(base_url, "/api/data-diagnostics/paths", override_paths)
        require(save_paths.get("ok"), f"Path override save failed: {save_paths}")

        dashboard = api(base_url, "/api/dashboard/log")
        require(dashboard.get("selected_file") == override_log_name, f"Dashboard did not switch to override raw log: {dashboard.get('selected_file')}")
        x_options = set(dashboard.get("x_options", []) or [])
        for label in ("Bare Fibre Diameter", "Furnace DegC Actual", "Fibre Length", "UV 1 Intensity"):
            require(label in x_options, f"Friendly mapped label missing from dashboard: {label}")

        base_schedule_rows = len(read_csv_rows(schedule_csv))
        schedule_payloads = []
        for index in range(8):
            schedule_payloads.append(
                {
                    "eventType": "Maintenance" if index % 2 == 0 else "Drawing",
                    "start": f"2026-05-2{index} 09:0{index}:00",
                    "end": f"2026-05-2{index} 10:0{index}:00",
                    "description": f"Network smoke schedule {index}",
                    "recurrence": "None",
                }
            )
        schedule_results = concurrent_post(base_url, "/api/schedule/add", schedule_payloads)
        require(all(item.get("ok") for item in schedule_results), "One or more schedule add calls returned failure.")
        require(len(read_csv_rows(schedule_csv)) >= base_schedule_rows + 8, "Concurrent schedule adds did not all persist.")

        base_parts_rows = len(read_csv_rows(parts_orders_csv))
        part_payloads = []
        for index in range(6):
            part_payloads.append(
                {
                    "partName": f"NET-SMOKE-PART-{index}",
                    "serialNumber": f"NS-{index}",
                    "project": project_name,
                    "details": f"Smoke order {index}",
                    "openedBy": "codex",
                    "approvalRequestedFrom": "lab",
                    "company": "Smoke Supplier",
                    "maintenanceComponent": "Network Component",
                    "maintenanceTask": "Smoke Task",
                }
            )
        part_results = concurrent_post(base_url, "/api/parts/create", part_payloads)
        require(all(item.get("ok") for item in part_results), "One or more part create calls returned failure.")
        require(len(read_csv_rows(parts_orders_csv)) >= base_parts_rows + 6, "Concurrent part creates did not all persist.")

        base_fault_rows = len(read_csv_rows(faults_log))
        fault_payloads = []
        for index in range(5):
            fault_payloads.append(
                {
                    "action": "create",
                    "actor": "codex",
                    "component": f"Smoke Fault Component {index}",
                    "title": f"Smoke fault {index}",
                    "description": f"Fault created during network smoke test {index}",
                    "severity": "medium" if index % 2 else "critical",
                    "relatedDraw": "",
                }
            )
        fault_results = concurrent_post(base_url, "/api/maintenance/fault", fault_payloads)
        require(all(item.get("ok") for item in fault_results), "One or more maintenance fault calls returned failure.")
        require(len(read_csv_rows(faults_log)) >= base_fault_rows + 5, "Concurrent fault creates did not all persist.")

        project_result = api(
            base_url,
            "/api/development/project",
            {"projectName": project_name, "purpose": "Network smoke purpose", "target": "Network smoke target"},
        )
        require(project_result.get("ok"), f"Development project create failed: {project_result}")
        summary_result = api(
            base_url,
            "/api/development/summary",
            {
                "projectName": project_name,
                "summaryTitle": "Smoke Summary",
                "summaryNotes": "Summary created by smoke test",
                "summaryResearcher": "Codex",
                "summaryDate": "2026-05-14",
            },
        )
        require(summary_result.get("ok"), f"Development summary save failed: {summary_result}")

        experiment_result = api(
            base_url,
            "/api/development/experiment",
            {
                "projectName": project_name,
                "experimentTitle": "Network Smoke Experiment",
                "date": "2026-05-14",
                "researcher": "Codex",
                "purpose": "Smoke-test experiment",
                "methods": "API workflow",
                "observations": "No issue",
                "results": "Pending",
                "isDrawing": False,
                "drawingDetails": "",
                "drawCsv": "",
                "markdownNotes": "Smoke markdown",
            },
        )
        require(experiment_result.get("ok"), f"Development experiment save failed: {experiment_result}")

        base_update_rows = count_matching_rows(updates_csv, lambda row: str(row.get("Project Name", "")).strip() == project_name)
        update_payloads = []
        for index in range(6):
            update_payloads.append(
                {
                    "projectName": project_name,
                    "updateTitle": f"Smoke update {index}",
                    "researcher": "Codex",
                    "updateDate": f"2026-05-1{index}",
                    "updateNotes": f"Concurrent update {index}",
                }
            )
        update_results = concurrent_post(base_url, "/api/development/update", update_payloads)
        require(all(item.get("ok") for item in update_results), "One or more development update calls returned failure.")
        require(
            count_matching_rows(updates_csv, lambda row: str(row.get("Project Name", "")).strip() == project_name) >= base_update_rows + 6,
            "Concurrent development updates did not all persist.",
        )

        manual_payloads = []
        for _ in range(4):
            manual_payloads.append(
                {
                    "project": project_name,
                    "preformNumber": manual_preform,
                    "opener": "Codex",
                    "priority": "Normal",
                    "geometry": "Round",
                    "requiredLength": "1200",
                    "goodZones": "1",
                    "notes": "Network smoke dataset",
                }
            )
        manual_results = concurrent_post(base_url, "/api/process-setup/manual-start", manual_payloads)
        require(all(item.get("ok") for item in manual_results), "One or more manual process-setup calls returned failure.")
        manual_dataset_paths = find_created_dataset_paths(dataset_override, manual_preform)
        manual_names = [path.name for path in manual_dataset_paths]
        require(
            manual_names == [f"{manual_preform}F1.csv", f"{manual_preform}F2.csv", f"{manual_preform}F3.csv", f"{manual_preform}F4.csv"],
            f"Unexpected dataset names from concurrent manual start: {manual_names}",
        )

        order_create = api(
            base_url,
            "/api/order-draw/create",
            {
                "order": {
                    "preformNumber": scheduled_preform,
                    "project": project_name,
                    "opener": "Codex",
                    "priority": "Normal",
                    "geometry": "Round",
                    "requiredLength": "1100",
                    "goodZones": "1",
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
                    "notes": "Network scheduled-start smoke",
                    "desiredDate": "2026-05-21",
                    "tigerCut": "0",
                    "octF2f": "0",
                },
                "scheduleNow": False,
                "saveTemplate": False,
            },
        )
        require(order_create.get("ok"), f"Order draw create failed: {order_create}")
        order_index = latest_draw_order_index(draw_orders_csv, scheduled_preform)
        order_schedule = api(
            base_url,
            "/api/order-draw/schedule",
            {
                "orderIndex": order_index,
                "password": "DORON",
                "date": "2026-05-22",
                "startTime": "09:30",
                "durationMin": "95",
                "preformNumber": scheduled_preform,
            },
        )
        require(order_schedule.get("ok"), f"Order scheduling failed: {order_schedule}")
        scheduled_start = api(
            base_url,
            "/api/process-setup/scheduled-start",
            {
                "orderIndex": order_index,
                "preformNumber": scheduled_preform,
            },
        )
        require(scheduled_start.get("ok"), f"Scheduled process-setup start failed: {scheduled_start}")
        require((dataset_override / scheduled_preform / f"{scheduled_preform}F1.csv").exists(), "Scheduled-start dataset was not created in the dataset workspace.")

        zone_dataset_name = f"{scheduled_preform}F1.csv"
        dashboard = api(base_url, f"/api/dashboard/log?name={urllib.parse.quote(override_log_name)}")
        zone_end = min(40, max(1, len(dashboard.get("rows", []) or []) - 1))
        zone_result = api(
            base_url,
            "/api/dashboard/save-zones",
            {
                "logName": override_log_name,
                "datasetCsv": zone_dataset_name,
                "zones": [{"startIndex": 0, "endIndex": zone_end}],
            },
        )
        require(zone_result.get("ok"), f"Dashboard zone export failed: {zone_result}")
        zone_file = dataset_override / scheduled_preform / f"{scheduled_preform}F1_Z1" / f"{scheduled_preform}F1_Z1.csv"
        require(zone_file.exists(), "Zone CSV was not created in the expected folder layout.")

        sql_query = api(
            base_url,
            "/api/sql-lab/query",
            {
                "dataset": zone_dataset_name,
                "sql": "SELECT parameter_name, value FROM dataset WHERE parameter_name LIKE 'Zone 1 | %' LIMIT 5",
            },
        )
        require(sql_query.get("ok"), f"SQL Lab query failed: {sql_query}")
        require(len(sql_query.get("rows", [])) > 0, "SQL Lab query did not return any zone rows.")

        sql_filter = api(
            base_url,
            "/api/sql-lab/filter",
            {
                "dataset": zone_dataset_name,
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
        require(sql_filter.get("ok"), f"SQL Lab filter failed: {sql_filter}")
        require(int(sql_filter.get("summary", {}).get("matched_draws", 0)) >= 1, "SQL Lab filter did not match the exported dataset.")

        plot_result = api(
            base_url,
            "/api/dashboard/math-plot-export",
            {
                "filename": "network_smoke_plot.png",
                "content": ONE_PIXEL_PNG_BASE64,
            },
        )
        require(plot_result.get("ok"), f"Dashboard plot export failed: {plot_result}")
        plot_path = Path(str(plot_result.get("saved_path", "")).strip())
        require(plot_path.exists(), "Dashboard plot export path does not exist on disk.")

        done_result = api(
            base_url,
            "/api/draw-finalize/done",
            {
                "dataset": zone_dataset_name,
                "doneDescription": "Network smoke done",
                "preformLengthCm": "123.4",
            },
        )
        require(done_result.get("ok"), f"Draw finalize done failed: {done_result}")
        done_snapshot = done_override / f"{scheduled_preform}F1.txt"
        require(done_snapshot.exists(), "Done snapshot TXT was not created in the override done workspace.")

        dev_export_html = api(
            base_url,
            "/api/report-center/development-export",
            {"projectName": project_name, "format": "html"},
        )
        require(dev_export_html.get("ok"), f"Development HTML export failed: {dev_export_html}")
        html_name = str(dev_export_html.get("fileName", "")).strip()
        require((reports_override / "report_center" / html_name).exists(), "Development HTML export file is missing.")

        dev_export_md = api(
            base_url,
            "/api/report-center/development-export",
            {"projectName": project_name, "format": "md"},
        )
        require(dev_export_md.get("ok"), f"Development Markdown export failed: {dev_export_md}")
        md_name = str(dev_export_md.get("fileName", "")).strip()
        require((reports_override / "report_center" / md_name).exists(), "Development Markdown export file is missing.")

        backup_result = api(base_url, "/api/data-diagnostics/full-backup", {})
        require(backup_result.get("ok"), f"Full backup creation failed: {backup_result}")
        snapshot_name = str((backup_result.get("snapshot") or {}).get("name", "")).strip()
        require(snapshot_name, "Full backup response did not include a snapshot name.")
        require((backups_override / snapshot_name / "manifest.json").exists(), "Full backup manifest was not created in the override backups workspace.")

        delete_project = api(base_url, "/api/development/manage", {"projectName": project_name, "action": "delete"})
        require(delete_project.get("ok"), f"Development project cleanup failed: {delete_project}")
        require(count_matching_rows(projects_csv, lambda row: str(row.get("Project Name", "")).strip() == project_name) == 0, "Development project cleanup did not remove the project row.")

        print("network-smoke-test: PASS")
        print(f"dashboard default raw log: {override_log_name}")
        print(f"manual datasets: {', '.join(manual_names)}")
        print(f"scheduled dataset: {zone_dataset_name}")
        print(f"zone csv: {zone_file}")
        print(f"done snapshot: {done_snapshot}")
        print(f"plot export: {plot_path}")
        print(f"backup snapshot: {snapshot_name}")
    finally:
        try:
            api(base_url, "/api/data-diagnostics/paths", original_paths)
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a shared-network Tower rebuild smoke test against a running app server.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="Base URL of the running Tower rebuild app.")
    args = parser.parse_args()
    run(args.base_url)


if __name__ == "__main__":
    main()
