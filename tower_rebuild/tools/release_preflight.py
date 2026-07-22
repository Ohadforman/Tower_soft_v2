from __future__ import annotations

import base64
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import server  # noqa: E402


APP_JS = ROOT_DIR / "static" / "app" / "app.js"
SERVER_PY = ROOT_DIR / "server.py"
RUNTIME_FILES = [
    SERVER_PY,
    ROOT_DIR / "static" / "app" / "router.js",
    ROOT_DIR / "static" / "app" / "main.js",
    APP_JS,
    ROOT_DIR / "static" / "index.html",
]
PATH_LEAK_PATTERN = re.compile(r"/Users/ohadformanair|PycharmProjects/Tower_work")
API_LITERAL_PATTERN = re.compile(r'["\'`](/api/[A-Za-z0-9._/?=&%+-]+)')
SYNTHETIC_RAW_LOG_NAME = "Training_preflight_raw.csv"
SYNTHETIC_RAW_LOG_TEXT = "\n".join(
    [
        "Data Log",
        "[plc]BareFibreDiaDisplay,[plc]FrnTmpMv,[plc]CpLenTareVal,[plc]UVLamp1Intensity,[plc]FrnMFC1MV,[plc]GoodFibreStartState,[plc]TrendMarkerPulse",
        "125.10,2105.0,0.00,82.0,1.2,0,0",
        "125.22,2107.5,0.45,82.5,1.3,1,1",
        "125.31,2110.0,0.95,83.0,1.4,1,0",
        "125.28,2108.2,1.40,82.8,1.2,1,0",
        "125.18,2106.4,1.90,82.2,1.1,0,0",
    ]
)


def check(name: str, ok: bool, detail: str) -> dict[str, object]:
    return {"name": name, "ok": ok, "detail": detail}


def runtime_path_leak_check() -> dict[str, object]:
    hits: list[str] = []
    for file_path in RUNTIME_FILES:
        text = file_path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if PATH_LEAK_PATTERN.search(line):
                hits.append(f"{file_path.name}:{line_number}")
    if hits:
        return check("runtime-paths", False, f"Absolute workstation paths found in runtime files: {', '.join(hits[:8])}")
    return check("runtime-paths", True, "Runtime files do not contain workstation-specific absolute paths.")


def helper_python_check() -> dict[str, object]:
    helper = server.resolve_helper_python(("pypdf",))
    if helper is None:
        return check("helper-python", False, "No helper Python runtime with pypdf was found for manual indexing.")
    return check("helper-python", True, f"Resolved helper runtime: {helper}")


def manual_renderer_check() -> dict[str, object]:
    mode = server.manual_page_render_mode()
    if mode == "image":
        return check("manual-renderer", True, "Manual page viewer can render page images on this platform.")
    if mode == "pdf-inline":
        return check("manual-renderer", True, "Manual page viewer will use inline PDF fallback instead of image rendering.")
    return check("manual-renderer", False, f"Unexpected manual render mode: {mode}")


def bootstrap_check() -> dict[str, object]:
    payload = server.build_bootstrap_payload().body
    required = {
        "home",
        "schedule",
        "parts",
        "maintenance",
        "consumables",
        "processSetup",
        "orderDraw",
        "dashboard",
        "drawFinalize",
        "diagnostics",
        "reportCenter",
        "sqlLab",
        "development",
    }
    missing = sorted(required.difference(payload.keys()))
    if missing:
        return check("bootstrap", False, f"Bootstrap payload is missing keys: {', '.join(missing)}")
    return check("bootstrap", True, f"Bootstrap payload exposes all {len(required)} required sections.")


def diagnostics_check() -> dict[str, object]:
    payload = server.build_diagnostics_payload().body
    expected_keys = {
        "ready_count",
        "tracked_count",
        "health_checks",
        "overall_ok",
        "global_mirror_count",
        "global_mirror_pending_count",
        "global_mirror_issue_count",
    }
    missing = sorted(expected_keys.difference(payload.keys()))
    if missing:
        return check("diagnostics", False, f"Diagnostics payload is missing keys: {', '.join(missing)}")
    path_rows = payload.get("path_rows") or []
    if path_rows:
        sample = path_rows[0]
        required_row_keys = {"global_enabled", "global_path", "global_status", "global_detail"}
        row_missing = sorted(required_row_keys.difference(sample.keys()))
        if row_missing:
            return check("diagnostics", False, f"Diagnostics path rows are missing mirror fields: {', '.join(row_missing)}")
    return check(
        "diagnostics",
        True,
        f"Diagnostics payload built successfully with {payload.get('passed_checks', 0)}/{payload.get('total_checks', 0)} checks passing.",
    )


def tracked_path_coverage_check() -> dict[str, object]:
    payload = server.build_diagnostics_payload().body
    path_keys = {
        str(row.get("key") or "")
        for row in payload.get("path_rows", []) or []
    }
    required = {
        "development_projects_csv",
        "development_experiments_csv",
        "experiment_updates_csv",
        "maintenance_work_packages_csv",
        "argon_monthly_report_csv",
        "report_center_dir",
        "dashboard_plots_dir",
        "maintenance_manual_pages_dir",
        "dashboard_exports_dir",
        "manual_page_cache_dir",
        "external_manuals_dir",
    }
    missing = sorted(required.difference(path_keys))
    if missing:
        return check("tracked-path-coverage", False, f"Diagnostics path manager is missing: {', '.join(missing)}")
    return check("tracked-path-coverage", True, f"Diagnostics path manager exposes all {len(required)} extended live data paths.")


def dataset_workspace_repair_check() -> dict[str, object]:
    temp_root = Path(tempfile.mkdtemp(prefix="tower-rebuild-dataset-repair-"))
    try:
        primary = temp_root / "data_set_csv" / "P7777"
        zone_dir = primary / "P7777F1_Z1"
        legacy = temp_root / "legacy_converted_out_v2"
        primary.mkdir(parents=True, exist_ok=True)
        zone_dir.mkdir(parents=True, exist_ok=True)
        legacy.mkdir(parents=True, exist_ok=True)
        (primary / "P7777F1.csv").write_text(
            "\n".join(
                [
                    "Parameter Name,Value,Units",
                    "Dashboard Log File,override_Training_preflight_raw.csv,",
                    "Good Zones Count,1,count",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (zone_dir / "P7777F1_Z1.csv").write_text(
            "\n".join(
                [
                    "Parameter Name,Value,Units",
                    "=== ZONE SNAPSHOT ===,,",
                    "Zone Number,1,",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_file = legacy / "P0475F_1.csv"
        legacy_file.write_text(
            "\n".join(
                [
                    "Parameter Name,Value,Units",
                    "=== ORDER PARAMETERS ===,,",
                    "Order__Draw Name,P0475F_1,",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        resolved = server.resolve_default_dataset_dir(temp_root)
        copied_file = temp_root / "data_set_csv" / legacy_file.name
        if resolved != temp_root / "data_set_csv":
            return check("dataset-workspace-repair", False, f"Dataset resolver unexpectedly switched to {resolved}.")
        if not copied_file.exists():
            return check("dataset-workspace-repair", False, "Legacy draw datasets were not copied into data_set_csv when only zone snapshots were present.")
        return check("dataset-workspace-repair", True, f"Zone-only dataset folders are repaired by backfilling draw snapshots into {resolved}.")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def find_raw_log_candidate() -> Path | None:
    for path in server.list_dashboard_log_files():
        if server.inspect_log_header_shape(path).get("is_raw"):
            return path
    return None


@contextmanager
def temporary_raw_log_fixture():
    raw_candidate = find_raw_log_candidate()
    if raw_candidate is not None:
        yield raw_candidate
        return
    temp_root = Path(tempfile.mkdtemp(prefix="tower-rebuild-raw-log-fixture-"))
    try:
        fixture_path = temp_root / SYNTHETIC_RAW_LOG_NAME
        fixture_path.write_text(SYNTHETIC_RAW_LOG_TEXT, encoding="utf-8")
        yield fixture_path
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@contextmanager
def temporary_logs_workspace():
    with temporary_raw_log_fixture() as raw_candidate:
        temp_root = Path(tempfile.mkdtemp(prefix="tower-rebuild-preflight-logs-"))
        original_logs_dir = server.LOGS_DIR
        try:
            temp_root.mkdir(parents=True, exist_ok=True)
            workspace_log = temp_root / raw_candidate.name
            shutil.copy2(raw_candidate, workspace_log)
            server.LOGS_DIR = temp_root
            yield workspace_log
        finally:
            server.LOGS_DIR = original_logs_dir
            shutil.rmtree(temp_root, ignore_errors=True)


def dashboard_log_default_check() -> dict[str, object]:
    with temporary_logs_workspace() as raw_candidate:
        payload = server.build_dashboard_log_payload().body
        selected = str(payload.get("selected_file") or "").strip()
        available = [str(item or "").strip() for item in payload.get("available_logs", [])]
        x_options = set(payload.get("x_options", []) or [])
        bad_hints = tuple(str(item).lower() for item in getattr(server, "LOG_DEPRIORITIZED_NAME_HINTS", ()))
        if not selected:
            return check("dashboard-log-default", False, "Dashboard log payload did not resolve any default log file.")
        if any(hint in selected.lower() for hint in bad_hints):
            return check("dashboard-log-default", False, f"Dashboard defaulted to a deprioritized log file: {selected}")
        if selected != raw_candidate.name:
            return check("dashboard-log-default", False, f"Dashboard did not prefer the raw machine log. Expected {raw_candidate.name}, got {selected}.")
        required_labels = {"Bare Fibre Diameter", "Furnace DegC Actual", "Fibre Length"}
        missing_labels = sorted(required_labels.difference(x_options))
        if missing_labels:
            return check("dashboard-log-default", False, f"Mapped dashboard labels are missing from the default log: {', '.join(missing_labels)}")
        return check("dashboard-log-default", True, f"Dashboard defaults to {selected} with mapped machine labels available across {len(available)} log choices.")


def raw_log_mapping_check() -> dict[str, object]:
    with temporary_logs_workspace() as raw_candidate:
        payload = server.build_dashboard_log_payload(raw_candidate.name).body
        headers = set(payload.get("x_options", []) or [])
        bad_headers = [header for header in headers if "[plc]" in str(header).lower()]
        if bad_headers:
            return check("raw-log-mapping", False, f"Mapped payload still exposes raw PLC headers: {', '.join(sorted(bad_headers)[:8])}")
        required_labels = {"Bare Fibre Diameter", "Furnace DegC Actual", "Fibre Length"}
        missing = sorted(required_labels.difference(headers))
        if missing:
            return check("raw-log-mapping", False, f"Raw machine log did not map into friendly labels: {', '.join(missing)}")
        return check("raw-log-mapping", True, f"Raw machine log {raw_candidate.name} is read from logs/ and exposed with friendly labels.")


def dataset_scope_separation_check() -> dict[str, object]:
    sql_payload = server.build_sql_lab_payload().body
    finalize_payload = server.build_draw_finalize_payload().body
    sql_names = [str(item or "") for item in sql_payload.get("dataset_files", [])]
    finalize_names = [str(item or "") for item in finalize_payload.get("dataset_files", [])]
    leaked = [name for name in [*sql_names, *finalize_names] if "_Z" in name]
    if leaked:
        return check("dataset-scope-separation", False, f"Zone CSVs leaked into full-dataset selectors: {', '.join(sorted(set(leaked))[:8])}")
    selected = str(finalize_payload.get("selected_csv") or "")
    if "_Z" in selected:
        return check("dataset-scope-separation", False, f"Draw Finalize selected a zone CSV instead of a full dataset: {selected}")
    return check("dataset-scope-separation", True, f"SQL Lab and Draw Finalize stay on full draw datasets only; Draw Finalize selected {selected or 'none'}.")


def done_snapshot_path_check() -> dict[str, object]:
    diagnostics = server.build_diagnostics_payload().body
    path_rows = diagnostics.get("path_rows", []) or []
    matched = next((row for row in path_rows if str(row.get("key") or "") == "done_snapshots_dir"), None)
    if not matched:
        return check("done-snapshot-path", False, "Diagnostics tracked paths do not expose Done Snapshots Workspace.")
    if str(matched.get("status") or "") != "READY":
        return check("done-snapshot-path", False, f"Done Snapshots Workspace is not ready: {matched.get('status')}")
    return check("done-snapshot-path", True, f"Done Snapshots Workspace is tracked and ready at {matched.get('path')}.")


def current_tracked_path_payload() -> dict[str, str]:
    return {
        str(spec["key"]): str(path)
        for spec, path in server.current_tracked_paths()
    }


@contextmanager
def temporary_tracked_path_override_file():
    temp_root = Path(tempfile.mkdtemp(prefix="tower-rebuild-tracked-paths-"))
    original_override_file = server.TRACKED_PATH_OVERRIDES_FILE
    original_overrides = server.load_tracked_path_overrides()
    try:
        server.TRACKED_PATH_OVERRIDES_FILE = temp_root / "state" / "tracked_path_overrides.json"
        yield temp_root
    finally:
        server.TRACKED_PATH_OVERRIDES_FILE = original_override_file
        server.save_tracked_path_overrides(original_overrides)
        server.apply_tracked_path_overrides(original_overrides)
        server.ensure_runtime_directories()
        shutil.rmtree(temp_root, ignore_errors=True)


def tracked_path_override_flow_check() -> dict[str, object]:
    with temporary_raw_log_fixture() as raw_candidate:
        with temporary_tracked_path_override_file() as temp_root:
            temp_logs = temp_root / "logs_override"
            temp_dataset = temp_root / "dataset_override"
            temp_done = temp_root / "done_override"
            temp_selected = temp_root / "state" / "selected_csv.json"
            temp_sap = temp_root / "imports" / "sap_inventory_override.csv"
            temp_preform = temp_root / "imports" / "preform_inventory_override.csv"
            temp_logs.mkdir(parents=True, exist_ok=True)
            temp_dataset.mkdir(parents=True, exist_ok=True)
            temp_done.mkdir(parents=True, exist_ok=True)
            raw_override_name = f"override_{raw_candidate.name}"
            shutil.copy2(raw_candidate, temp_logs / raw_override_name)
            server.write_json_value(temp_selected, {"selected_csv": ""})
            server.write_csv_rows(
                temp_sap,
                [
                    {
                        "Item": "SAP Rods Set",
                        "Count": "77",
                        "Units": "sets",
                        "Last Updated": "2026-05-13",
                        "Notes": "Tracked path preflight",
                    }
                ],
                ["Item", "Count", "Units", "Last Updated", "Notes"],
            )
            server.write_csv_rows(
                temp_preform,
                [{"Preform Number": "OVERRIDE-PREFORM-9000"}],
                ["Preform Number"],
            )

            payload = current_tracked_path_payload()
            payload.update(
                {
                    "logs_dir": str(temp_logs),
                    "dataset_dir": str(temp_dataset),
                    "done_snapshots_dir": str(temp_done),
                    "selected_csv_json": str(temp_selected),
                    "sap_inventory_csv": str(temp_sap),
                    "preform_inventory_csv": str(temp_preform),
                }
            )
            save_result = server.save_diagnostics_paths_action(payload).body
            if not save_result.get("ok"):
                return check("tracked-path-overrides", False, f"Tracked path save action failed: {save_result.get('message')}")

            diagnostics = server.build_diagnostics_payload().body
            rows_by_key = {
                str(row.get("key") or ""): row
                for row in diagnostics.get("path_rows", []) or []
            }
            expected_override_paths = {
                "logs_dir": temp_logs.resolve(),
                "dataset_dir": temp_dataset.resolve(),
                "done_snapshots_dir": temp_done.resolve(),
                "selected_csv_json": temp_selected.resolve(),
                "sap_inventory_csv": temp_sap.resolve(),
                "preform_inventory_csv": temp_preform.resolve(),
            }
            for key, expected_path in expected_override_paths.items():
                row = rows_by_key.get(key)
                if not row:
                    return check("tracked-path-overrides", False, f"Diagnostics path rows are missing {key}.")
                if Path(str(row.get("path") or "")).resolve() != expected_path:
                    return check("tracked-path-overrides", False, f"Diagnostics did not apply the override path for {key}.")
                if not bool(row.get("is_override")):
                    return check("tracked-path-overrides", False, f"Diagnostics did not mark {key} as an override.")
                if str(row.get("status") or "") != "READY":
                    return check("tracked-path-overrides", False, f"Diagnostics reported {key} as {row.get('status')} after saving the override.")

            log_paths = server.list_dashboard_log_files()
            if raw_override_name not in [path.name for path in log_paths]:
                return check("tracked-path-overrides", False, "Dashboard log listing did not switch to the overridden logs workspace.")
            dashboard_payload = server.build_dashboard_log_payload().body
            if raw_override_name not in [str(name) for name in dashboard_payload.get("available_logs", []) or []]:
                return check("tracked-path-overrides", False, "Dashboard payload did not expose the raw log inside the overridden logs workspace.")
            raw_dashboard_payload = server.build_dashboard_log_payload(raw_override_name).body
            if str(raw_dashboard_payload.get("selected_file") or "") != raw_override_name:
                return check("tracked-path-overrides", False, "Dashboard could not open the raw log inside the overridden logs workspace when requested.")
            friendly_headers = set(raw_dashboard_payload.get("x_options", []) or [])
            required_headers = {"Bare Fibre Diameter", "Furnace DegC Actual", "Fibre Length"}
            missing_headers = sorted(required_headers.difference(friendly_headers))
            if missing_headers:
                return check("tracked-path-overrides", False, f"Dashboard lost friendly mapped labels after logs path override: {', '.join(missing_headers)}")

            sap_summary = server.build_order_draw_payload().body.get("sap_summary", {})
            if int(round(float(sap_summary.get("count") or 0))) != 77:
                return check("tracked-path-overrides", False, "Dashboard SAP summary did not read from the overridden SAP inventory file.")
            preform_options = (
                server.build_process_setup_payload()
                .body.get("manual_options", {})
                .get("preform_options", [])
            )
            if "OVERRIDE-PREFORM-9000" not in preform_options:
                return check("tracked-path-overrides", False, "Process Setup did not read preform options from the overridden preform inventory file.")

            save_zone_result = server.save_dashboard_zones_action(
                {
                    "logName": raw_override_name,
                    "datasetCsv": "P7777F1.csv",
                    "zones": [{"startIndex": 0, "endIndex": 4}],
                }
            ).body
            if not save_zone_result.get("ok"):
                return check("tracked-path-overrides", False, f"Zone export failed after path override: {save_zone_result.get('message')}")
            dataset_path = server.resolve_dataset_csv_path("P7777F1.csv")
            if dataset_path is None or not dataset_path.exists():
                return check("tracked-path-overrides", False, "Zone export did not create a dataset inside the overridden dataset workspace.")
            if not server.path_is_within(dataset_path, temp_dataset):
                return check("tracked-path-overrides", False, "Full dataset CSV was written outside the overridden dataset workspace.")
            zone_files = [Path(path) for path in save_zone_result.get("zone_files", [])]
            if not zone_files or not zone_files[0].exists() or not server.path_is_within(zone_files[0], temp_dataset):
                return check("tracked-path-overrides", False, "Zone CSV was written outside the overridden dataset workspace.")
            snapshot_ok, snapshot_path = server.create_done_snapshot("P7777F1.csv", 12.3, "Tracked path preflight")
            snapshot_output = Path(snapshot_path) if snapshot_ok else Path()
            if not snapshot_ok or not snapshot_output.exists():
                return check("tracked-path-overrides", False, f"Done snapshot failed after path override: {snapshot_path}")
            if not server.path_is_within(snapshot_output, temp_done):
                return check("tracked-path-overrides", False, "Done snapshot was written outside the overridden done snapshots workspace.")

            backup_sources = server.build_full_backup_sources()
            backup_targets = {
                str(item.get("target") or ""): Path(item["path"]).resolve()
                for item in backup_sources
            }
            if backup_targets.get("data_set_csv") != temp_dataset.resolve():
                return check("tracked-path-overrides", False, "Full backup sources did not switch to the overridden dataset workspace.")
            if backup_targets.get("logs") != temp_logs.resolve():
                return check("tracked-path-overrides", False, "Full backup sources did not switch to the overridden logs workspace.")
            if backup_targets.get("external_paths/done_snapshots_dir") != temp_done.resolve():
                return check("tracked-path-overrides", False, "Full backup sources did not capture the overridden done snapshots workspace.")
            if backup_targets.get("external_paths/sap_inventory_csv.csv") != temp_sap.resolve():
                return check("tracked-path-overrides", False, "Full backup sources did not capture the overridden SAP inventory file.")
            if backup_targets.get("external_paths/preform_inventory_csv.csv") != temp_preform.resolve():
                return check("tracked-path-overrides", False, "Full backup sources did not capture the overridden preform inventory file.")

            reset_result = server.save_diagnostics_paths_action({"resetDefaults": "true"}).body
            if not reset_result.get("ok"):
                return check("tracked-path-overrides", False, f"Tracked path reset action failed: {reset_result.get('message')}")
            reset_rows = {
                str(row.get("key") or ""): row
                for row in (server.build_diagnostics_payload().body.get("path_rows", []) or [])
            }
            logs_row = reset_rows.get("logs_dir")
            if not logs_row:
                return check("tracked-path-overrides", False, "Diagnostics path rows disappeared after resetting tracked paths.")
            if bool(logs_row.get("is_override")):
                return check("tracked-path-overrides", False, "Tracked path reset left logs_dir marked as an override.")
            if Path(str(logs_row.get("path") or "")).resolve() != server.tracked_path_defaults()["logs_dir"].resolve():
                return check("tracked-path-overrides", False, "Tracked path reset did not restore the default logs workspace.")
            return check(
                "tracked-path-overrides",
                True,
                "App path save/reset flow redirects logs, datasets, done prints, SAP inventory, preform inventory, and backup sources without hidden hardcoded fallbacks.",
            )


@contextmanager
def temporary_pipeline_output_roots():
    temp_root = Path(tempfile.mkdtemp(prefix="tower-rebuild-log-pipeline-"))
    original_dataset = server.DATASET_DIR
    original_done = server.DONE_SNAPSHOTS_DIR
    original_reports = server.REPORTS_DIR
    try:
        server.DATASET_DIR = temp_root / "dataset"
        server.DONE_SNAPSHOTS_DIR = temp_root / "done"
        server.REPORTS_DIR = temp_root / "reports"
        server.DATASET_DIR.mkdir(parents=True, exist_ok=True)
        server.DONE_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        server.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        yield temp_root
    finally:
        server.DATASET_DIR = original_dataset
        server.DONE_SNAPSHOTS_DIR = original_done
        server.REPORTS_DIR = original_reports
        shutil.rmtree(temp_root, ignore_errors=True)


def log_output_pipeline_check() -> dict[str, object]:
    tiny_png = base64.b64encode(
        bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D49444154789C6360F8CFC0000003010100C9FE92EF0000000049454E44AE426082"
        )
    ).decode("ascii")
    with temporary_logs_workspace() as raw_candidate:
        with temporary_pipeline_output_roots():
            save_result = server.save_dashboard_zones_action(
                {
                    "logName": raw_candidate.name,
                    "datasetCsv": "P0888F1.csv",
                    "zones": [{"startIndex": 0, "endIndex": 4}],
                }
            ).body
            if not save_result.get("ok"):
                return check("log-output-pipeline", False, f"Zone export from raw log failed: {save_result.get('message')}")
            dataset_path = server.resolve_dataset_csv_path("P0888F1.csv")
            if dataset_path is None or not dataset_path.exists():
                return check("log-output-pipeline", False, "Full dataset CSV was not created during zone export.")
            if dataset_path.name != "P0888F1.csv":
                return check("log-output-pipeline", False, f"Full dataset CSV was created with legacy naming: {dataset_path.name}")
            dataset_text = dataset_path.read_text(encoding="utf-8-sig", errors="ignore")
            if "[plc]" in dataset_text:
                return check("log-output-pipeline", False, "Full dataset CSV still contains raw PLC column names.")
            if "Bare Fibre Diameter" not in dataset_text:
                return check("log-output-pipeline", False, "Full dataset CSV did not include mapped friendly labels.")
            zone_files = [Path(path) for path in save_result.get("zone_files", [])]
            if not zone_files or not zone_files[0].exists():
                return check("log-output-pipeline", False, "Zone CSV export did not produce a zone file.")
            if zone_files[0].name != "P0888F1_Z1.csv":
                return check("log-output-pipeline", False, f"Zone CSV export used legacy naming: {zone_files[0].name}")
            zone_text = zone_files[0].read_text(encoding="utf-8-sig", errors="ignore")
            if "[plc]" in zone_text or "Bare Fibre Diameter" not in zone_text:
                return check("log-output-pipeline", False, "Zone CSV export did not preserve friendly mapped labels.")
            snapshot_ok, snapshot_path = server.create_done_snapshot("P0888F1.csv", 123.4, "Preflight snapshot")
            if not snapshot_ok:
                return check("log-output-pipeline", False, f"Done snapshot export failed: {snapshot_path}")
            snapshot_text = Path(snapshot_path).read_text(encoding="utf-8", errors="ignore")
            if "[plc]" in snapshot_text or "Bare Fibre Diameter" not in snapshot_text:
                return check("log-output-pipeline", False, "Done snapshot text leaked raw PLC names instead of mapped labels.")
            if "DRAW REPORT - CLEAN SUMMARY" not in snapshot_text or "CSV CONTENT (raw):" in snapshot_text:
                return check("log-output-pipeline", False, "Done snapshot text did not use the clean summary print layout.")
            plot_result = server.export_dashboard_math_plot_action(
                {
                    "filename": "preflight_plot.png",
                    "content": f"data:image/png;base64,{tiny_png}",
                }
            ).body
            plot_path = Path(str(plot_result.get("saved_path") or ""))
            if not plot_result.get("ok") or not plot_path.exists():
                return check("log-output-pipeline", False, "Dashboard plot export did not create a PNG output file.")
            return check(
                "log-output-pipeline",
                True,
                f"Raw log {raw_candidate.name} flows cleanly into dataset CSV, zone CSV, done snapshot, and plot export outputs.",
            )


def development_payload_check() -> dict[str, object]:
    payload = server.build_development_payload().body
    if "project_names" not in payload or "metrics" not in payload:
        return check("development-payload", False, "Development payload is missing project_names or metrics.")
    return check(
        "development-payload",
        True,
        f"Development payload built successfully with {len(payload.get('project_names', []))} project choices.",
    )


def maintenance_execute_contract_check() -> dict[str, object]:
    payload = server.build_maintenance_payload().body
    if "execute_plan_queue" not in payload:
        return check("maintenance-execute-contract", False, "Maintenance payload is missing execute_plan_queue for execute handoff filtering.")
    invalid_statuses = sorted(
        {
            str(item.get("status", "")).strip().upper()
            for item in payload.get("execute_plan_queue", []) or []
            if str(item.get("status", "")).strip().upper() not in {"SCHEDULED", "IN_PROGRESS"}
        }
    )
    if invalid_statuses:
        return check(
            "maintenance-execute-contract",
            False,
            f"Execute plan queue leaked non-execute states: {', '.join(invalid_statuses)}",
        )
    return check(
        "maintenance-execute-contract",
        True,
        f"Maintenance payload exposes execute_plan_queue with {len(payload.get('execute_plan_queue', []) or [])} explicit plan handoff rows.",
    )


def route_wiring_check() -> dict[str, object]:
    app_text = APP_JS.read_text(encoding="utf-8")
    app_routes = sorted({match.split("?", 1)[0] for match in API_LITERAL_PATTERN.findall(app_text)})
    server_routes = set(server.API_ROUTES.keys()) | set(server.POST_API_ROUTES.keys()) | {
        "/api/maintenance/manual",
        "/api/maintenance/manual-page",
        "/api/maintenance/manual-page-pdf",
        "/api/maintenance/manual-prefetch",
        "/api/development/media",
        "/api/dashboard/log",
        "/api/dashboard/math-plot-export",
        "/api/report-center/project",
        "/api/report-center/file",
        "/api/sql-lab/dataset",
        "/api/draw-finalize",
        "/api/development/project",
    }
    missing = [route for route in app_routes if route not in server_routes]
    if missing:
        return check("route-wiring", False, f"App references routes with no backend handler: {', '.join(missing[:10])}")
    return check("route-wiring", True, f"Verified {len(app_routes)} app API references against backend route handlers.")


def folder_structure_check() -> dict[str, object]:
    required_dirs = [
        ROOT_DIR / "static" / "app",
        ROOT_DIR / "static" / "styles",
        ROOT_DIR / "tools",
        server.STATE_DIR,
        server.REPORT_CENTER_DIR,
        server.BACKUPS_DIR,
    ]
    missing = [str(path.relative_to(ROOT_DIR)) if path.is_relative_to(ROOT_DIR) else str(path) for path in required_dirs if not path.exists()]
    if missing:
        return check("folder-structure", False, f"Missing runtime or source folders: {', '.join(missing)}")
    return check("folder-structure", True, "Core source and runtime folders are present.")


@contextmanager
def temporary_report_output():
    temp_root = Path(tempfile.mkdtemp(prefix="tower-rebuild-preflight-"))
    original_reports = server.REPORTS_DIR
    original_center = server.REPORT_CENTER_DIR
    try:
        server.REPORTS_DIR = temp_root / "reports"
        server.REPORT_CENTER_DIR = server.REPORTS_DIR / "report_center"
        server.ensure_runtime_directories()
        yield temp_root
    finally:
        server.REPORTS_DIR = original_reports
        server.REPORT_CENTER_DIR = original_center
        shutil.rmtree(temp_root, ignore_errors=True)


def report_export_check() -> dict[str, object]:
    development = server.build_development_payload().body
    project_name = str(development.get("default_project") or (development.get("project_names") or [""])[0]).strip()
    if not project_name:
        return check("report-export", True, "Skipped project export exercise because no development projects were found.")
    with temporary_report_output():
        html_result = server.create_development_report_action({"projectName": project_name, "format": "html"}).body
        markdown_result = server.create_development_report_action({"projectName": project_name, "format": "md"}).body
        html_name = str(html_result.get("fileName") or "")
        markdown_name = str(markdown_result.get("fileName") or "")
        html_path = server.REPORT_CENTER_DIR / html_name
        markdown_path = server.REPORT_CENTER_DIR / markdown_name
        if not html_name or not markdown_name or not html_path.exists() or not markdown_path.exists():
            return check("report-export", False, "Project export did not create both HTML and markdown files in the report center.")
    return check("report-export", True, f"Project export succeeds for {project_name} in both HTML paper and markdown modes.")


def backup_sources_check() -> dict[str, object]:
    server.ensure_runtime_directories()
    sources = server.build_full_backup_sources()
    missing_labels = [str(item["label"]) for item in sources if not Path(item["path"]).exists()]
    if missing_labels:
        return check("backup-sources", False, f"Backup source paths are missing: {', '.join(missing_labels[:8])}")
    return check("backup-sources", True, f"Backup manifest resolves {len(sources)} source locations for full backups.")


def run_preflight() -> int:
    checks = [
        runtime_path_leak_check(),
        helper_python_check(),
        manual_renderer_check(),
        folder_structure_check(),
        bootstrap_check(),
        diagnostics_check(),
        tracked_path_coverage_check(),
        dataset_workspace_repair_check(),
        dashboard_log_default_check(),
        raw_log_mapping_check(),
        dataset_scope_separation_check(),
        done_snapshot_path_check(),
        tracked_path_override_flow_check(),
        log_output_pipeline_check(),
        development_payload_check(),
        maintenance_execute_contract_check(),
        route_wiring_check(),
        report_export_check(),
        backup_sources_check(),
    ]
    failures = [item for item in checks if not item["ok"]]
    for item in checks:
        status = "PASS" if item["ok"] else "FAIL"
        print(f"[{status}] {item['name']}: {item['detail']}")
    print()
    print(f"Checks passed: {len(checks) - len(failures)}/{len(checks)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_preflight())
