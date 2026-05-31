from __future__ import annotations

import atexit
import csv
import json
import mimetypes
import calendar
import os
import math
import re
import sys
import sqlite3
import base64
import subprocess
import hashlib
import threading
import shutil
import tempfile
import time
from contextlib import ExitStack, contextmanager
from html import escape as escape_html
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import pandas as pd
try:
    import duckdb  # type: ignore
except ImportError:
    duckdb = None

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR_ENV = str(os.environ.get("TOWER_REBUILD_ROOT_DIR", "") or "").strip()
DATA_DIR_ENV = str(os.environ.get("TOWER_REBUILD_DATA_DIR", "") or "").strip()
ROOT_DIR = Path(ROOT_DIR_ENV).expanduser().resolve() if ROOT_DIR_ENV else BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
VENDOR_DIR = BASE_DIR / ".vendor"
DATA_DIR = Path(DATA_DIR_ENV).expanduser().resolve() if DATA_DIR_ENV else ROOT_DIR / "data"

DRAW_ORDERS = DATA_DIR / "draw_orders.csv"
TOWER_SCHEDULE = DATA_DIR / "tower_schedule.csv"
PART_ORDERS = DATA_DIR / "part_orders.csv"
PARTS_INVENTORY = DATA_DIR / "parts_inventory.csv"
PARTS_LOCATIONS = DATA_DIR / "parts_locations.csv"
PARTS_COMPANIES = DATA_DIR / "parts_companies.csv"
PROJECTS_FIBER = DATA_DIR / "projects_fiber.csv"
PROJECTS_TEMPLATES = DATA_DIR / "projects_fiber_templates.csv"
SAP_RODS_INVENTORY = DATA_DIR / "sap_rods_inventory.csv"
SELECTED_CSV_JSON = DATA_DIR / "selected_csv.json"
DEVELOPMENT_PROJECTS = DATA_DIR / "development_projects.csv"
DEVELOPMENT_EXPERIMENTS = DATA_DIR / "development_experiments.csv"
EXPERIMENT_UPDATES = DATA_DIR / "experiment_updates.csv"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from helpers.maintenance_status import compute_maintenance_status_df, load_maintenance_folder_df


_INVISIBLE_PATH_MARKS = str.maketrans("", "", "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _strip_invisible_path_marks(value: str) -> str:
    return str(value or "").translate(_INVISIBLE_PATH_MARKS)


def _dataset_snapshot_signature_present(path: Path, include_zone_snapshots: bool = True, row_limit: int = 40) -> bool:
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".csv":
        return False
    accepted_markers = {"=== ORDER PARAMETERS ==="}
    if include_zone_snapshots:
        accepted_markers.add("=== ZONE SNAPSHOT ===")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = [str(item or "").strip() for item in (reader.fieldnames or [])]
            if header != ["Parameter Name", "Value", "Units"]:
                return False
            for index, row in enumerate(reader):
                parameter_name = str((row or {}).get("Parameter Name", "")).strip()
                if parameter_name in accepted_markers:
                    return True
                if index >= row_limit:
                    break
    except Exception:
        return False
    return False


def _directory_has_dataset_snapshots(directory: Path, include_zone_snapshots: bool = True) -> bool:
    if not directory.exists():
        return False
    try:
        for path in directory.rglob("*.csv"):
            if path.name == "_conversion_audit.csv":
                continue
            if _dataset_snapshot_signature_present(path, include_zone_snapshots=include_zone_snapshots):
                return True
    except OSError:
        return False
    return False


def _copy_missing_children(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir(), key=lambda item: item.name.lower()):
        target = destination / child.name
        if target.exists():
            continue
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def resolve_default_dataset_dir(root_dir: Path) -> Path:
    primary = root_dir / "data_set_csv"
    legacy = root_dir / "legacy_converted_out_v2"
    if primary.exists():
        if _directory_has_dataset_snapshots(legacy, include_zone_snapshots=False) and not _directory_has_dataset_snapshots(primary, include_zone_snapshots=False):
            try:
                _copy_missing_children(legacy, primary)
            except OSError:
                return legacy
        return primary
    if legacy.exists():
        try:
            _copy_missing_children(legacy, primary)
            return primary
        except OSError:
            return legacy
    return primary

MAINTENANCE_DIR = ROOT_DIR / "maintenance"
COATING_CONFIG = ROOT_DIR / "config" / "config_coating.json"
PID_CONFIG = ROOT_DIR / "config" / "pid_config.json"
CONTAINER_CONFIG = ROOT_DIR / "config" / "container_config.json"
DIES_CONFIG = ROOT_DIR / "config" / "dies_6station.json"
HEATER_CONFIG = ROOT_DIR / "config" / "heater_config.json"
DATASET_DIR = resolve_default_dataset_dir(ROOT_DIR)
LOGS_DIR = ROOT_DIR / "logs"
REPORTS_DIR = ROOT_DIR / "reports"
REPORT_CENTER_DIR = REPORTS_DIR / "report_center"
DASHBOARD_PLOTS_DIR = REPORTS_DIR / "dashboard_plots"
MAINTENANCE_MANUAL_PAGES_DIR = REPORTS_DIR / "maintenance_manual_pages"
DEVELOPMENT_MEDIA_DIR = ROOT_DIR / "development_media"
BACKUPS_DIR = ROOT_DIR / "backups"
DONE_SNAPSHOTS_DIR = ROOT_DIR / "hooks" / "done_csv_snapshots"
DUCKDB_PATH = DATA_DIR / "tower.duckdb"
STATE_DIR = ROOT_DIR / "state"
DASHBOARD_EXPORTS_DIR = STATE_DIR / "dashboard_exports"
COATING_STOCK = STATE_DIR / "coating_type_stock.json"
COATING_INVENTORY_META = STATE_DIR / "coating_inventory_meta.json"
CONTAINER_SNAPSHOT = STATE_DIR / "container_levels_prev.json"
MAINTENANCE_STATE = MAINTENANCE_DIR / "maintenance_task_state.csv"
MAINTENANCE_ACTIONS = MAINTENANCE_DIR / "maintenance_actions_log.csv"
MAINTENANCE_WAITS = MAINTENANCE_DIR / "maintenance_wait_parts_log.csv"
MAINTENANCE_RUNTIME = MAINTENANCE_DIR / "_app_state.json"
MAINTENANCE_WORK_PACKAGES = MAINTENANCE_DIR / "maintenance_work_packages.csv"
MAINTENANCE_PACKAGE_PHOTOS_DIR = STATIC_DIR / "uploads" / "maintenance_packages"
MAINTENANCE_TEST_PRESETS = MAINTENANCE_DIR / "maintenance_test_presets.json"
TOWER_TEMPS = DATA_DIR / "tower_temps.csv"
TOWER_CONTAINERS = DATA_DIR / "tower_containers.csv"
CONTAINER_LOGGER_SCRIPT = BASE_DIR / "tools" / "tower_containers_logger.py"
PREFORM_INVENTORY = DATA_DIR / "preforms_inventory.csv"
FAULTS_LOG = MAINTENANCE_DIR / "faults_log.csv"
FAULTS_ACTIONS_LOG = MAINTENANCE_DIR / "faults_actions_log.csv"
ARGON_MONTHLY_REPORT = REPORTS_DIR / "gas" / "argon_monthly_report.csv"
MANUALS_DIR = ROOT_DIR / "manuals"
EXTERNAL_MANUALS_DIR = ROOT_DIR.parent / "manuals"
MANUAL_INDEX_SCRIPT = BASE_DIR / "tools" / "extract_manual_index.py"
MANUAL_PAGE_RENDER_SCRIPT = BASE_DIR / "tools" / "render_manual_page.swift"
MANUAL_PAGE_CACHE_DIR = STATE_DIR / "manual_page_cache"
DEFAULT_COATING_MIN_STOCK_KG = 1.0
DEFAULT_CONTAINER_DIAMETER_MM = 280.0
DEFAULT_CONTAINER_FILL_HEIGHT_MM = 300.0
DEFAULT_CONTAINER_DENSITY_KG_PER_L = 1.0
DEFAULT_CONTAINER_LOW_PERCENT = 15.0
CONTAINER_FEED_STALE_SECONDS = 60.0
CONTAINER_FEED_SMOOTHING_SAMPLES = 4
CONTAINER_LOGGER_SCAN_INTERVAL_SECONDS = 2.0
CONTAINER_LOGGER_LOG_INTERVAL_SECONDS = 5.0
CONTAINER_LOGGER_STALE_THRESHOLD_SECONDS = 60.0
AUTO_CONTAINER_REFILL_MIN_KG = 0.0
AUTO_CONTAINER_REFILL_MIN_PERCENT = 30.0
CONTAINER_SENSOR_OPTIONS = ("tank1", "tank2", "tank3", "tank4")
CONTAINER_SENSOR_DEFAULTS = {
    "A": "tank1",
    "B": "tank2",
    "C": "tank3",
    "D": "tank4",
}
BUNDLED_RUNTIME_PYTHON = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "bin" / "python3"
HELPER_PYTHON_ENV = str(os.environ.get("TOWER_REBUILD_HELPER_PYTHON", "") or "").strip()
MANUAL_PAGE_MODE_ENV = str(os.environ.get("TOWER_REBUILD_MANUAL_PAGE_MODE", "") or "").strip().lower()
DEFAULT_BIND_HOST = str(os.environ.get("TOWER_REBUILD_HOST", "") or "").strip() or "127.0.0.1"
try:
    DEFAULT_BIND_PORT = int(str(os.environ.get("TOWER_REBUILD_PORT", "") or "").strip() or "8010")
except ValueError:
    DEFAULT_BIND_PORT = 8010

PROJECTS_COL = "Fiber Project"
GEOMETRY_COL = "Fiber Geometry Type"
GOOD_ZONES_COL = "Good Zones Count (required length zones)"
LENGTH_COL = "Required Length (m) (for T&M+costumer)"
MAIN_TEMP_COL = "Main Coating Temperature (°C)"
SECONDARY_TEMP_COL = "Secondary Coating Temperature (°C)"
FURNACE_TEMP_COL = "Furnace Temperature (°C)"
FIBER_TOL_COL = "Fiber Diameter Tol (± µm)"
MAIN_TOL_COL = "Main Coating Diameter Tol (± µm)"
SECONDARY_TOL_COL = "Secondary Coating Diameter Tol (± µm)"
TIGER_CUT_COL = "Tiger Cut (%)"
OCT_F2F_COL = "Octagonal F2F (mm)"
PREFORM_DIAMETER_COL = "Preform Diameter (mm)"
SCHEDULE_PASSWORD = "DORON"
SCHEDULE_REQUIRED_COLS = ["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]
ORDER_DRAW_GEOMETRY_OPTIONS = [
    "",
    "PANDA - PM",
    "TIGER - PM",
    "Octagonal",
    "ROUND",
    "STEP INDEX",
    "Ring Core",
    "Hollow Core",
    "Photonic Crystal",
    "Custom (write in Notes)",
]
TEMPLATE_FIELDS = [
    PROJECTS_COL,
    GEOMETRY_COL,
    PREFORM_DIAMETER_COL,
    TIGER_CUT_COL,
    OCT_F2F_COL,
    "Fiber Diameter (µm)",
    FIBER_TOL_COL,
    "Main Coating Diameter (µm)",
    MAIN_TOL_COL,
    "Secondary Coating Diameter (µm)",
    SECONDARY_TOL_COL,
    "Tension (g)",
    "Draw Speed (m/min)",
    FURNACE_TEMP_COL,
    "Main Coating",
    "Secondary Coating",
    MAIN_TEMP_COL,
    SECONDARY_TEMP_COL,
    "Notes Default",
]
PART_STATUS_ORDER = [
    "Opened",
    "Wait for Approval",
    "Approved",
    "Ordered",
    "Received",
    "Archived",
]
REPORT_CENTER_SECTIONS = [
    "Executive Summary",
    "Resources: Gas + SAP + Preforms",
    "Draw Outcomes (Done/Failed + Notes)",
    "Parts Orders Status",
    "Schedule: Past Week + Next Week",
    "Maintenance + Faults",
    "Maintenance Tests + Measurements",
    "Consumables Snapshot",
]
AUTO_MOVE_DONE_TO_TM_DAYS = 5

CONSUMABLE_TEMP_FIELDS = [
    "die_holder_primary_c",
    "die_holder_secondary_c",
    "A_container_c",
    "A_pipe_c",
    "B_container_c",
    "B_pipe_c",
    "C_container_c",
    "C_pipe_c",
    "D_container_c",
    "D_pipe_c",
]
CONSUMABLE_TEMP_SETPOINT_KEYS = {
    "die_holder_primary_c": "die_holder_primary_temp_c",
    "die_holder_secondary_c": "die_holder_secondary_temp_c",
    "A_container_c": "A_container_c",
    "A_pipe_c": "A_pipe_c",
    "B_container_c": "B_container_c",
    "B_pipe_c": "B_pipe_c",
    "C_container_c": "C_container_c",
    "C_pipe_c": "C_pipe_c",
    "D_container_c": "D_container_c",
    "D_pipe_c": "D_pipe_c",
}


def consumable_temp_setpoint_csv_field(field: str) -> str:
    return f"{field[:-2]}_sp_c" if field.endswith("_c") else f"{field}_sp"


@dataclass
class JsonResponse:
    body: dict
    status: int = 200


_PARTS_MANUAL_INDEX_CACHE: dict[str, object] = {"signature": None, "payload": None}
_MANUAL_PAGE_RENDER_LOCK = threading.Lock()
_MANUAL_PAGE_RENDER_EVENTS: dict[str, threading.Event] = {}
_MANUAL_PAGE_PREFETCH_LOCK = threading.Lock()
_MANUAL_PAGE_PREFETCH_QUEUED: set[str] = set()
_MANUAL_PAGE_PRIORITY_PREFETCH_QUEUED: set[str] = set()
_MANUAL_PAGE_PREFETCH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="manual-page-prefetch")
_MANUAL_PAGE_PRIORITY_PREFETCH_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="manual-page-prefetch-priority")
_HELPER_PYTHON_CACHE: dict[tuple[str, ...], Path | None] = {}
_REQUEST_LOCKS_DIR = STATE_DIR / "request_locks"
_REQUEST_LOCK_TIMEOUT_SECONDS = 30.0
_REQUEST_LOCK_STALE_SECONDS = 900.0
_REQUEST_LOCK_GUARDS: dict[str, threading.RLock] = {}
_REQUEST_LOCK_GUARDS_LOCK = threading.Lock()
_TRACKED_PATH_OVERRIDES_MTIME_NS: int | None = None


def _request_lock_guard(lock_path: Path) -> threading.RLock:
    key = str(lock_path)
    with _REQUEST_LOCK_GUARDS_LOCK:
        lock = _REQUEST_LOCK_GUARDS.get(key)
        if lock is None:
            lock = threading.RLock()
            _REQUEST_LOCK_GUARDS[key] = lock
        return lock


def _normalized_lock_target(path: Path | str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    try:
        return candidate.resolve()
    except FileNotFoundError:
        return Path(os.path.abspath(str(candidate)))


def _request_lock_file_path(path: Path | str) -> Path:
    target = _normalized_lock_target(path)
    key = hashlib.sha1(str(target).encode("utf-8")).hexdigest()
    return _REQUEST_LOCKS_DIR / f"{key}.lock"


@contextmanager
def hold_request_lock(path: Path | str, timeout: float = _REQUEST_LOCK_TIMEOUT_SECONDS):
    lock_target = _normalized_lock_target(path)
    lock_path = _request_lock_file_path(lock_target)
    _REQUEST_LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    guard = _request_lock_guard(lock_path)
    with guard:
        started = time.monotonic()
        while True:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "path": str(lock_target),
                                "pid": os.getpid(),
                                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            }
                        )
                    )
                break
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > _REQUEST_LOCK_STALE_SECONDS:
                    try:
                        lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"Timed out waiting for shared app lock: {lock_target}")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


@contextmanager
def hold_request_locks(paths: list[Path | str] | tuple[Path | str, ...]):
    normalized: list[Path] = []
    seen: set[str] = set()
    for item in paths:
        candidate = _normalized_lock_target(item)
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(candidate)
    with ExitStack() as stack:
        for item in sorted(normalized, key=lambda candidate: str(candidate)):
            stack.enter_context(hold_request_lock(item))
        yield


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except FileNotFoundError:
            pass


def write_dataframe_atomic(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=path.suffix or ".tmp", dir=str(path.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            df.to_excel(temp_path, index=False)
        else:
            df.to_csv(temp_path, index=False)
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except FileNotFoundError:
            pass


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_csv_fieldnames(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


LEGACY_LOG_COLUMN_MAP = {
    "[plc]BareFibreDiaDisplay": "Bare Fibre Diameter",
    "[plc]diadevbaremv": "Diameter Error",
    "[plc]PfProcessPsn": "Pf Process Position",
    "[plc]cpspdactval": "Capstan Speed",
    "[plc]CpLenTareVal": "Fibre Length",
    "[plc]GoodFibreStartState": "Good Fibre State",
    "[plc]FrnTmpMv": "Furnace DegC Actual",
    "[plc]FrnPwrMv": "Furnace Power",
    "[plc]pfspdactval": "Preform Speed Actual",
    "[plc]FrnMFC1MV": "Furnace MFC1 Actual",
    "[plc]FrnMFC2MV": "Furnace MFC2 Actual",
    "[plc]FrnMFC3MV": "Furnace MFC3 Actual",
    "[plc]FrnMFC4MV": "Furnace MFC4 Actual",
    "[plc]CaneSpdActVal": "Cane Speed Actual",
    "[plc]TenTareVal": "Tension N",
    "[plc]TrendMarkerPulse": "Trend Marker",
    "[plc]CoatedOuterFibreDiaDisplay": "Coated Outer Diameter",
    "[plc]FrnMFC1SP": "Furnace MFC1 Set",
    "[plc]FrnMFC3SP": "Furnace MFC3 Set",
    "[plc]FrnMFC4SP": "Furnace MFC4 Set",
    "[plc]FrnMFC2SP": "Furnace MFC2 Set",
    "[plc]FrnTmpSP": "Furnace DegC Set",
    "[plc]UVHiLo[0].status": "UV1 Status",
    "[plc]UVHiLO[1].Status": "UV2 Status",
    "plc]PolyXDia": "Poly X Diameter",
    "plc]PolyYDia": "Poly Y Diameter",
    "[plc]PloyMajorAxis": "Poly Major Value",
    "[plc]PolyMinorAxis": "Poly Minor Value",
    "[plc]DiaDevXYBareMV": "Diameter Deviation Gauge 2",
    "[plc]CoatedInnerFibreDiaDisplay": "Coated Inner Diameter",
    "[plc]UVLamp1Intensity": "UV 1 Intensity",
    "[plc]UVLamp2Intensity": "UV 2 Intensity",
}
LEGACY_LOG_COLUMN_MAP_NORMALIZED = {
    str(key).strip().lower(): value for key, value in LEGACY_LOG_COLUMN_MAP.items()
}
LEGACY_LOG_MAPPED_VALUES_NORMALIZED = {
    str(value).strip().lower() for value in LEGACY_LOG_COLUMN_MAP.values()
}


def normalize_log_column_name(name: object) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    return LEGACY_LOG_COLUMN_MAP.get(raw) or LEGACY_LOG_COLUMN_MAP_NORMALIZED.get(raw.lower(), raw)


def normalize_dataset_parameter_name(name: object) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    # Older dataset exports mixed "Fiber Length" and the mapped PLC label "Fibre Length".
    # Normalize them at read time so SQL Lab, zone views, and reports stay consistent.
    return raw.replace("Fiber Length", "Fibre Length")


def normalize_dataset_parameter_value(parameter_name: str, value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if parameter_name in {"Good Zones X Column", "Zone Length Column (log)"}:
        return raw.replace("Fiber Length", "Fibre Length")
    return raw


def load_log_csv_rows(path: Path) -> tuple[list[dict[str, object]], dict[str, str]]:
    if not path.exists():
        return [], {}
    skiprows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        first_row = next(reader, [])
    if len(first_row) == 1 and str(first_row[0] or "").strip().lower() == "data log":
        skiprows = 1
    try:
        df = pd.read_csv(path, skiprows=skiprows)
    except Exception:
        return [], {}
    if df is None or df.empty:
        return [], {}
    df.columns = [str(column).strip() for column in df.columns]
    original_headers = list(df.columns)
    rename_map = {column: normalize_log_column_name(column) for column in original_headers}
    df.rename(columns=rename_map, inplace=True)
    df.dropna(axis=1, how="all", inplace=True)
    if df.columns.duplicated().any():
        merged = pd.DataFrame(index=df.index)
        ordered_cols = list(dict.fromkeys(df.columns.tolist()))
        for column in ordered_cols:
            same_name = df.loc[:, df.columns == column]
            if isinstance(same_name, pd.Series):
                merged[column] = same_name
            else:
                merged[column] = same_name.bfill(axis=1).iloc[:, 0]
        df = merged
    display_labels = {}
    for original, mapped in rename_map.items():
        if mapped and original and mapped != original:
            display_labels[mapped] = mapped
    return df.to_dict(orient="records"), display_labels


def write_csv_rows(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved_fieldnames = list(fieldnames or [])
    for row in rows:
        for key in row.keys():
            if key not in resolved_fieldnames:
                resolved_fieldnames.append(key)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=resolved_fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except FileNotFoundError:
            pass


def read_json_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def read_json_value(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json_value(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(value, indent=2), encoding="utf-8")


def _python_candidate_paths() -> list[Path]:
    root_venv_bin = ROOT_DIR / ".venv" / "bin" / "python"
    root_venv_win = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    base_venv_bin = BASE_DIR / ".venv" / "bin" / "python"
    base_venv_win = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    raw_candidates = [
        HELPER_PYTHON_ENV,
        sys.executable,
        root_venv_bin,
        root_venv_win,
        base_venv_bin,
        base_venv_win,
        BUNDLED_RUNTIME_PYTHON,
        shutil.which("python3") or "",
        shutil.which("python") or "",
    ]
    candidates: list[Path] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        candidate = Path(text).expanduser()
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def _python_supports_modules(candidate: Path, required_modules: tuple[str, ...]) -> bool:
    if not required_modules:
        return True
    try:
        env = dict(os.environ)
        vendor_python_path = str(VENDOR_DIR)
        current_python_path = str(env.get("PYTHONPATH", "") or "").strip()
        env["PYTHONPATH"] = vendor_python_path if not current_python_path else f"{vendor_python_path}{os.pathsep}{current_python_path}"
        result = subprocess.run(
            [
                str(candidate),
                "-c",
                "import importlib.util, sys; modules = tuple(sys.argv[1:]); missing = [name for name in modules if importlib.util.find_spec(name) is None]; raise SystemExit(0 if not missing else 1)",
                *required_modules,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def resolve_helper_python(required_modules: tuple[str, ...] = ("pypdf",)) -> Path | None:
    cache_key = tuple(required_modules)
    if cache_key in _HELPER_PYTHON_CACHE:
        return _HELPER_PYTHON_CACHE[cache_key]
    for candidate in _python_candidate_paths():
        if not candidate.exists() or not candidate.is_file():
            continue
        if _python_supports_modules(candidate, cache_key):
            resolved = candidate.resolve()
            _HELPER_PYTHON_CACHE[cache_key] = resolved
            return resolved
    _HELPER_PYTHON_CACHE[cache_key] = None
    return None


def manual_page_render_mode() -> str:
    if MANUAL_PAGE_MODE_ENV in {"image", "page-image", "png"}:
        return "image"
    if MANUAL_PAGE_MODE_ENV in {"pdf", "pdf-inline", "inline"}:
        return "pdf-inline"
    renderer_binary = MANUAL_PAGE_CACHE_DIR / "render_manual_page"
    if sys.platform == "darwin" and MANUAL_PAGE_RENDER_SCRIPT.exists() and (shutil.which("xcrun") or renderer_binary.exists()):
        return "image"
    return "pdf-inline"


def ensure_runtime_directories() -> None:
    for path in (
        DATA_DIR,
        MAINTENANCE_DIR,
        STATE_DIR,
        DASHBOARD_EXPORTS_DIR,
        LOGS_DIR,
        REPORTS_DIR,
        REPORT_CENTER_DIR,
        DASHBOARD_PLOTS_DIR,
        MAINTENANCE_MANUAL_PAGES_DIR,
        BACKUPS_DIR,
        DONE_SNAPSHOTS_DIR,
        DEVELOPMENT_MEDIA_DIR,
        DATASET_DIR,
        MANUALS_DIR,
        MANUAL_PAGE_CACHE_DIR,
        STATIC_DIR / "uploads",
        MAINTENANCE_PACKAGE_PHOTOS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
    ensure_runtime_seed_files()


def ensure_runtime_seed_files() -> None:
    if not PARTS_INVENTORY.exists():
        write_csv_rows(
            PARTS_INVENTORY,
            [],
            ["Part Name", "Item Type", "Component", "Supplier", "Serial Number", "Location", "Location Serial", "Quantity", "Min Level", "Notes", "Last Updated"],
        )
    if not PARTS_LOCATIONS.exists():
        write_csv_rows(
            PARTS_LOCATIONS,
            [{"Location Name": "Mounted", "Location Serial": "MOUNTED", "Notes": "Default machine-mounted location"}],
            ["Location Name", "Location Serial", "Notes"],
        )
    if not PARTS_COMPANIES.exists():
        write_csv_rows(PARTS_COMPANIES, [], ["Company", "Last Updated"])
    if not PROJECTS_TEMPLATES.exists():
        write_csv_rows(PROJECTS_TEMPLATES, [], TEMPLATE_FIELDS[:])
    if not TOWER_TEMPS.exists():
        temp_fields = CONSUMABLE_TEMP_FIELDS + [consumable_temp_setpoint_csv_field(field) for field in CONSUMABLE_TEMP_FIELDS] + ["updated_at"]
        temp_row = {field: "0" for field in temp_fields if field != "updated_at"}
        temp_row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        write_csv_rows(TOWER_TEMPS, [temp_row], temp_fields)
    if not TOWER_CONTAINERS.exists():
        container_fields = ["timestamp", "tank1", "tank2", "tank3", "tank4"]
        container_rows = [
            {"timestamp": "18/05/2026 17:33", "tank1": "88.39", "tank2": "90.62", "tank3": "90.99", "tank4": "90.99"},
            {"timestamp": "18/05/2026 17:34", "tank1": "88.55", "tank2": "90.62", "tank3": "89.68", "tank4": "90.91"},
            {"timestamp": "18/05/2026 17:35", "tank1": "88.34", "tank2": "90.63", "tank3": "89.64", "tank4": "91.01"},
            {"timestamp": "18/05/2026 17:36", "tank1": "88.42", "tank2": "90.62", "tank3": "89.78", "tank4": "90.94"},
            {"timestamp": "18/05/2026 17:37", "tank1": "88.39", "tank2": "90.62", "tank3": "89.70", "tank4": "91.00"},
            {"timestamp": "18/05/2026 17:38", "tank1": "88.47", "tank2": "90.62", "tank3": "89.64", "tank4": "92.47"},
            {"timestamp": "18/05/2026 17:39", "tank1": "88.48", "tank2": "90.65", "tank3": "89.83", "tank4": "92.38"},
            {"timestamp": "18/05/2026 17:40", "tank1": "88.37", "tank2": "90.67", "tank3": "89.70", "tank4": "91.93"},
            {"timestamp": "18/05/2026 17:41", "tank1": "88.50", "tank2": "90.80", "tank3": "89.69", "tank4": "91.90"},
            {"timestamp": "18/05/2026 17:42", "tank1": "88.52", "tank2": "90.65", "tank3": "89.64", "tank4": "91.89"},
        ]
        write_csv_rows(TOWER_CONTAINERS, container_rows, container_fields)
    if not MAINTENANCE_WAITS.exists():
        write_csv_rows(
            MAINTENANCE_WAITS,
            [],
            ["wait_id", "maintenance_task_id", "maintenance_component", "maintenance_task", "part_name", "quantity", "opened_ts", "resolved_ts", "notes"],
        )
    if not MAINTENANCE_RUNTIME.exists():
        write_json_value(
            MAINTENANCE_RUNTIME,
            {
                "furnace_hours": 0.0,
                "uv1_hours": 0.0,
                "uv2_hours": 0.0,
                "last_draw_count": 0,
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "warn_days": 14,
                "warn_hours": 50.0,
            },
        )
    if not FAULTS_ACTIONS_LOG.exists():
        write_csv_rows(
            FAULTS_ACTIONS_LOG,
            [],
            ["fault_action_id", "fault_id", "action_ts", "action_type", "actor", "note", "fix_summary"],
        )
    if not ARGON_MONTHLY_REPORT.exists():
        write_csv_rows(ARGON_MONTHLY_REPORT, [], ["month", "total_standard_liters"])
    if not DUCKDB_PATH.exists():
        if duckdb is not None:
            conn = duckdb.connect(str(DUCKDB_PATH))
            conn.close()
        else:
            atomic_write_bytes(DUCKDB_PATH, b"")


TRACKED_PATH_OVERRIDES_FILE = STATE_DIR / "tracked_path_overrides.json"
TRACKED_PATH_SPECS = (
    {"key": "orders_csv", "label": "Orders CSV", "global_name": "DRAW_ORDERS", "kind": "file", "default": DRAW_ORDERS},
    {"key": "parts_orders_csv", "label": "Parts Orders CSV", "global_name": "PART_ORDERS", "kind": "file", "default": PART_ORDERS},
    {"key": "parts_inventory_csv", "label": "Parts Inventory CSV", "global_name": "PARTS_INVENTORY", "kind": "file", "default": PARTS_INVENTORY},
    {"key": "parts_locations_csv", "label": "Parts Locations CSV", "global_name": "PARTS_LOCATIONS", "kind": "file", "default": PARTS_LOCATIONS},
    {"key": "parts_companies_csv", "label": "Parts Companies CSV", "global_name": "PARTS_COMPANIES", "kind": "file", "default": PARTS_COMPANIES},
    {"key": "schedule_csv", "label": "Schedule CSV", "global_name": "TOWER_SCHEDULE", "kind": "file", "default": TOWER_SCHEDULE},
    {"key": "sap_inventory_csv", "label": "SAP Inventory CSV", "global_name": "SAP_RODS_INVENTORY", "kind": "file", "default": SAP_RODS_INVENTORY},
    {"key": "preform_inventory_csv", "label": "Preform Inventory CSV", "global_name": "PREFORM_INVENTORY", "kind": "file", "default": PREFORM_INVENTORY},
    {"key": "selected_csv_json", "label": "Selected CSV JSON", "global_name": "SELECTED_CSV_JSON", "kind": "file", "default": SELECTED_CSV_JSON},
    {"key": "development_projects_csv", "label": "Development Projects CSV", "global_name": "DEVELOPMENT_PROJECTS", "kind": "file", "default": DEVELOPMENT_PROJECTS},
    {"key": "development_experiments_csv", "label": "Development Experiments CSV", "global_name": "DEVELOPMENT_EXPERIMENTS", "kind": "file", "default": DEVELOPMENT_EXPERIMENTS},
    {"key": "experiment_updates_csv", "label": "Experiment Updates CSV", "global_name": "EXPERIMENT_UPDATES", "kind": "file", "default": EXPERIMENT_UPDATES},
    {"key": "projects_fiber_csv", "label": "Projects Fiber CSV", "global_name": "PROJECTS_FIBER", "kind": "file", "default": PROJECTS_FIBER},
    {"key": "projects_templates_csv", "label": "Projects Templates CSV", "global_name": "PROJECTS_TEMPLATES", "kind": "file", "default": PROJECTS_TEMPLATES},
    {"key": "tower_temps_csv", "label": "Tower Temps CSV", "global_name": "TOWER_TEMPS", "kind": "file", "default": TOWER_TEMPS},
    {"key": "tower_containers_csv", "label": "Tower Containers CSV", "global_name": "TOWER_CONTAINERS", "kind": "file", "default": TOWER_CONTAINERS},
    {
        "key": "tower_containers_logger_py",
        "label": "Tower Containers Logger Script",
        "global_name": "CONTAINER_LOGGER_SCRIPT",
        "kind": "file",
        "default": CONTAINER_LOGGER_SCRIPT,
    },
    {"key": "maintenance_state_csv", "label": "Maintenance State CSV", "global_name": "MAINTENANCE_STATE", "kind": "file", "default": MAINTENANCE_STATE},
    {"key": "maintenance_actions_csv", "label": "Maintenance Actions CSV", "global_name": "MAINTENANCE_ACTIONS", "kind": "file", "default": MAINTENANCE_ACTIONS},
    {"key": "maintenance_waits_csv", "label": "Maintenance Waits CSV", "global_name": "MAINTENANCE_WAITS", "kind": "file", "default": MAINTENANCE_WAITS},
    {"key": "maintenance_runtime_json", "label": "Maintenance Runtime JSON", "global_name": "MAINTENANCE_RUNTIME", "kind": "file", "default": MAINTENANCE_RUNTIME},
    {"key": "maintenance_work_packages_csv", "label": "Maintenance Work Packages CSV", "global_name": "MAINTENANCE_WORK_PACKAGES", "kind": "file", "default": MAINTENANCE_WORK_PACKAGES},
    {"key": "maintenance_test_presets_json", "label": "Maintenance Test Presets JSON", "global_name": "MAINTENANCE_TEST_PRESETS", "kind": "file", "default": MAINTENANCE_TEST_PRESETS},
    {"key": "faults_log_csv", "label": "Faults Log CSV", "global_name": "FAULTS_LOG", "kind": "file", "default": FAULTS_LOG},
    {"key": "faults_actions_csv", "label": "Faults Actions CSV", "global_name": "FAULTS_ACTIONS_LOG", "kind": "file", "default": FAULTS_ACTIONS_LOG},
    {"key": "coating_config_json", "label": "Coating Config JSON", "global_name": "COATING_CONFIG", "kind": "file", "default": COATING_CONFIG},
    {"key": "pid_config_json", "label": "PID Config JSON", "global_name": "PID_CONFIG", "kind": "file", "default": PID_CONFIG},
    {"key": "container_config_json", "label": "Container Config JSON", "global_name": "CONTAINER_CONFIG", "kind": "file", "default": CONTAINER_CONFIG},
    {"key": "dies_config_json", "label": "Dies Config JSON", "global_name": "DIES_CONFIG", "kind": "file", "default": DIES_CONFIG},
    {"key": "heater_config_json", "label": "Heater Config JSON", "global_name": "HEATER_CONFIG", "kind": "file", "default": HEATER_CONFIG},
    {"key": "coating_stock_json", "label": "Coating Stock JSON", "global_name": "COATING_STOCK", "kind": "file", "default": COATING_STOCK},
    {"key": "container_snapshot_json", "label": "Container Snapshot JSON", "global_name": "CONTAINER_SNAPSHOT", "kind": "file", "default": CONTAINER_SNAPSHOT},
    {"key": "argon_monthly_report_csv", "label": "Argon Monthly Report CSV", "global_name": "ARGON_MONTHLY_REPORT", "kind": "file", "default": ARGON_MONTHLY_REPORT},
    {"key": "dataset_dir", "label": "Dataset Workspace", "global_name": "DATASET_DIR", "kind": "dir", "default": DATASET_DIR},
    {"key": "logs_dir", "label": "Logs Workspace", "global_name": "LOGS_DIR", "kind": "dir", "default": LOGS_DIR},
    {"key": "reports_dir", "label": "Reports Workspace", "global_name": "REPORTS_DIR", "kind": "dir", "default": REPORTS_DIR},
    {"key": "report_center_dir", "label": "Report Center Workspace", "global_name": "REPORT_CENTER_DIR", "kind": "dir", "default": REPORT_CENTER_DIR},
    {"key": "dashboard_plots_dir", "label": "Dashboard Plots Workspace", "global_name": "DASHBOARD_PLOTS_DIR", "kind": "dir", "default": DASHBOARD_PLOTS_DIR},
    {"key": "maintenance_manual_pages_dir", "label": "Maintenance Manual Pages Workspace", "global_name": "MAINTENANCE_MANUAL_PAGES_DIR", "kind": "dir", "default": MAINTENANCE_MANUAL_PAGES_DIR},
    {"key": "development_media_dir", "label": "Development Media Workspace", "global_name": "DEVELOPMENT_MEDIA_DIR", "kind": "dir", "default": DEVELOPMENT_MEDIA_DIR},
    {"key": "manuals_dir", "label": "Manuals Workspace", "global_name": "MANUALS_DIR", "kind": "dir", "default": MANUALS_DIR},
    {"key": "external_manuals_dir", "label": "External Manuals Workspace", "global_name": "EXTERNAL_MANUALS_DIR", "kind": "dir", "default": EXTERNAL_MANUALS_DIR},
    {"key": "dashboard_exports_dir", "label": "Dashboard Exports Workspace", "global_name": "DASHBOARD_EXPORTS_DIR", "kind": "dir", "default": DASHBOARD_EXPORTS_DIR},
    {"key": "manual_page_cache_dir", "label": "Manual Page Cache Workspace", "global_name": "MANUAL_PAGE_CACHE_DIR", "kind": "dir", "default": MANUAL_PAGE_CACHE_DIR},
    {"key": "maintenance_package_photos_dir", "label": "Maintenance Package Photos", "global_name": "MAINTENANCE_PACKAGE_PHOTOS_DIR", "kind": "dir", "default": MAINTENANCE_PACKAGE_PHOTOS_DIR},
    {"key": "done_snapshots_dir", "label": "Done Snapshots Workspace", "global_name": "DONE_SNAPSHOTS_DIR", "kind": "dir", "default": DONE_SNAPSHOTS_DIR},
    {"key": "backups_dir", "label": "Backups Workspace", "global_name": "BACKUPS_DIR", "kind": "dir", "default": BACKUPS_DIR},
    {"key": "duckdb_path", "label": "DuckDB File", "global_name": "DUCKDB_PATH", "kind": "file", "default": DUCKDB_PATH},
)
TRACKED_PATH_SPEC_MAP = {str(item["key"]): item for item in TRACKED_PATH_SPECS}


def normalize_tracked_path_value(value: str | Path) -> Path:
    text = str(value or "").strip()
    candidate = Path(text).expanduser() if text else ROOT_DIR
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return candidate.resolve()


def tracked_path_defaults() -> dict[str, Path]:
    return {str(item["key"]): Path(item["default"]) for item in TRACKED_PATH_SPECS}


def load_tracked_path_overrides() -> dict[str, Path]:
    raw = read_json_dict(TRACKED_PATH_OVERRIDES_FILE)
    overrides: dict[str, Path] = {}
    for item in TRACKED_PATH_SPECS:
        key = str(item["key"])
        value = raw.get(key)
        if not value:
            continue
        overrides[key] = normalize_tracked_path_value(value)
    return overrides


def apply_tracked_path_overrides(overrides: dict[str, Path] | None = None) -> None:
    values = tracked_path_defaults()
    for key, path in (overrides or {}).items():
        if key in values:
            values[key] = normalize_tracked_path_value(path)
    module_globals = globals()
    for item in TRACKED_PATH_SPECS:
        module_globals[str(item["global_name"])] = values[str(item["key"])]
    _PARTS_MANUAL_INDEX_CACHE.clear()


def save_tracked_path_overrides(overrides: dict[str, Path]) -> None:
    defaults = tracked_path_defaults()
    payload = {
        key: str(normalize_tracked_path_value(path))
        for key, path in overrides.items()
        if key in defaults and normalize_tracked_path_value(path) != defaults[key]
    }
    if payload:
        write_json_value(TRACKED_PATH_OVERRIDES_FILE, payload)
        return
    try:
        TRACKED_PATH_OVERRIDES_FILE.unlink()
    except FileNotFoundError:
        pass


def current_tracked_paths() -> list[tuple[dict[str, object], Path]]:
    module_globals = globals()
    return [
        (item, Path(module_globals[str(item["global_name"])]))
        for item in TRACKED_PATH_SPECS
    ]


def current_tracked_path_overrides_mtime_ns() -> int | None:
    try:
        return TRACKED_PATH_OVERRIDES_FILE.stat().st_mtime_ns
    except FileNotFoundError:
        return None


_CONTAINER_LOGGER_LOCK = threading.Lock()
_CONTAINER_LOGGER_PROCESS: subprocess.Popen[str] | None = None
_CONTAINER_LOGGER_SIGNATURE: tuple[str, ...] | None = None
_CONTAINER_LOGGER_STATUS: dict[str, object] = {
    "state": "idle",
    "message": "Container logger has not started yet.",
    "pid": None,
    "python": "",
    "script": "",
    "output": "",
}


def _set_container_logger_status(
    state: str,
    message: str,
    *,
    pid: int | None = None,
    python_path: Path | None = None,
    script_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    global _CONTAINER_LOGGER_STATUS
    _CONTAINER_LOGGER_STATUS = {
        "state": str(state or "").strip() or "idle",
        "message": str(message or "").strip(),
        "pid": pid,
        "python": str(python_path or "").strip(),
        "script": str(script_path or "").strip(),
        "output": str(output_path or "").strip(),
    }


def current_container_logger_status() -> dict[str, object]:
    with _CONTAINER_LOGGER_LOCK:
        process = _CONTAINER_LOGGER_PROCESS
        signature = _CONTAINER_LOGGER_SIGNATURE
        status = dict(_CONTAINER_LOGGER_STATUS)
        if process is not None and process.poll() is not None:
            signature_parts = tuple(signature or ())
            python_text = signature_parts[0] if len(signature_parts) > 0 else ""
            script_text = signature_parts[1] if len(signature_parts) > 1 else ""
            output_text = signature_parts[2] if len(signature_parts) > 2 else ""
            status = {
                "state": "stopped",
                "message": f"Container logger exited with code {process.returncode}.",
                "pid": None,
                "python": python_text,
                "script": script_text,
                "output": output_text,
            }
        return status


def stop_container_logger_process() -> None:
    global _CONTAINER_LOGGER_PROCESS, _CONTAINER_LOGGER_SIGNATURE
    with _CONTAINER_LOGGER_LOCK:
        process = _CONTAINER_LOGGER_PROCESS
        signature = _CONTAINER_LOGGER_SIGNATURE or ("", "", "")
        _CONTAINER_LOGGER_PROCESS = None
        _CONTAINER_LOGGER_SIGNATURE = None
        if process is None:
            return
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.SubprocessError):
                    pass
        _set_container_logger_status(
            "stopped",
            "Container logger stopped.",
            python_path=Path(signature[0]) if signature[0] else None,
            script_path=Path(signature[1]) if signature[1] else None,
            output_path=Path(signature[2]) if signature[2] else None,
        )


def cleanup_stray_container_logger_processes(script_path: Path, output_path: Path, keep_pid: int | None = None) -> None:
    script_text = str(script_path.resolve())
    output_text = str(output_path.resolve())
    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    if result.returncode != 0:
        return
    for raw_line in result.stdout.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        try:
            pid_text, command_text = line.split(None, 1)
            pid = int(pid_text)
        except (ValueError, TypeError):
            continue
        if keep_pid is not None and pid == keep_pid:
            continue
        if "tower_containers_logger.py" not in command_text:
            continue
        if script_text not in command_text:
            continue
        if output_text not in command_text:
            continue
        try:
            os.kill(pid, 15)
        except OSError:
            continue


def ensure_container_logger_process(force_restart: bool = False) -> None:
    global _CONTAINER_LOGGER_PROCESS, _CONTAINER_LOGGER_SIGNATURE
    script_path = Path(CONTAINER_LOGGER_SCRIPT)
    output_path = Path(TOWER_CONTAINERS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not script_path.exists():
        stop_container_logger_process()
        _set_container_logger_status(
            "blocked",
            "Container logger script is missing.",
            script_path=script_path,
            output_path=output_path,
        )
        return
    helper_python = resolve_helper_python(required_modules=("serial",))
    if helper_python is None:
        stop_container_logger_process()
        _set_container_logger_status(
            "blocked",
            "pyserial is not installed for the app Python, so the container logger cannot start yet.",
            script_path=script_path,
            output_path=output_path,
        )
        return
    desired_signature = (
        str(helper_python.resolve()),
        str(script_path.resolve()),
        str(output_path.resolve()),
        str(CONTAINER_LOGGER_SCAN_INTERVAL_SECONDS),
        str(CONTAINER_LOGGER_LOG_INTERVAL_SECONDS),
        str(CONTAINER_LOGGER_STALE_THRESHOLD_SECONDS),
    )
    with _CONTAINER_LOGGER_LOCK:
        process = _CONTAINER_LOGGER_PROCESS
        if process is not None and process.poll() is not None:
            _CONTAINER_LOGGER_PROCESS = None
            _CONTAINER_LOGGER_SIGNATURE = None
            process = None
        if not force_restart and process is not None and _CONTAINER_LOGGER_SIGNATURE == desired_signature:
            cleanup_stray_container_logger_processes(script_path, output_path, keep_pid=process.pid)
            _set_container_logger_status(
                "running",
                "Container logger is sampling Arduino tank fill data in the background.",
                pid=process.pid,
                python_path=helper_python,
                script_path=script_path,
                output_path=output_path,
            )
            return
    stop_container_logger_process()
    cleanup_stray_container_logger_processes(script_path, output_path)
    command = [
        str(helper_python),
        str(script_path),
        "--output",
        str(output_path),
        "--scan-interval",
        str(CONTAINER_LOGGER_SCAN_INTERVAL_SECONDS),
        "--log-interval",
        str(CONTAINER_LOGGER_LOG_INTERVAL_SECONDS),
        "--stale-threshold",
        str(CONTAINER_LOGGER_STALE_THRESHOLD_SECONDS),
    ]
    env = dict(os.environ)
    vendor_python_path = str(VENDOR_DIR)
    current_python_path = str(env.get("PYTHONPATH", "") or "").strip()
    env["PYTHONPATH"] = vendor_python_path if not current_python_path else f"{vendor_python_path}{os.pathsep}{current_python_path}"
    try:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
        )
    except OSError as exc:
        _set_container_logger_status(
            "blocked",
            f"Container logger failed to start: {exc}",
            python_path=helper_python,
            script_path=script_path,
            output_path=output_path,
        )
        return
    with _CONTAINER_LOGGER_LOCK:
        _CONTAINER_LOGGER_PROCESS = process
        _CONTAINER_LOGGER_SIGNATURE = desired_signature
    _set_container_logger_status(
        "running",
        "Container logger is sampling Arduino tank fill data in the background.",
        pid=process.pid,
        python_path=helper_python,
        script_path=script_path,
        output_path=output_path,
    )


def sync_tracked_path_overrides_if_needed(force: bool = False) -> None:
    global _TRACKED_PATH_OVERRIDES_MTIME_NS
    current_mtime = current_tracked_path_overrides_mtime_ns()
    if not force and current_mtime == _TRACKED_PATH_OVERRIDES_MTIME_NS:
        return
    apply_tracked_path_overrides(load_tracked_path_overrides() if current_mtime is not None else {})
    _TRACKED_PATH_OVERRIDES_MTIME_NS = current_mtime
    ensure_runtime_directories()


sync_tracked_path_overrides_if_needed(force=True)

FULL_BACKUP_INTERVAL = timedelta(days=7)
FULL_BACKUP_POLICY_LABEL = "Runs inside the app once every 7 days while the app is active"
FULL_BACKUP_LOCK = threading.Lock()

FULL_BACKUP_SOURCE_SPECS = (
    {"label": "Core data", "path_key": "DATA_DIR", "target": "data"},
    {"label": "Dataset CSVs", "path_key": "DATASET_DIR", "target": "data_set_csv"},
    {"label": "Logs", "path_key": "LOGS_DIR", "target": "logs"},
    {"label": "Manuals", "path_key": "MANUALS_DIR", "target": "manuals"},
    {"label": "Reports", "path_key": "REPORTS_DIR", "target": "reports"},
    {"label": "Maintenance", "path_key": "MAINTENANCE_DIR", "target": "maintenance"},
    {"label": "State", "path_key": "STATE_DIR", "target": "state"},
    {"label": "Config", "path": ROOT_DIR / "config", "target": "config"},
    {"label": "Development media", "path_key": "DEVELOPMENT_MEDIA_DIR", "target": "development_media"},
    {"label": "App uploads", "path": STATIC_DIR / "uploads", "target": "tower_rebuild/static/uploads"},
)


def path_is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def path_has_entries(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return True
    try:
        next(path.iterdir())
    except (StopIteration, OSError):
        return False
    return True


def cleanup_empty_parent_chain(path: Path, stop_at: Path) -> None:
    current = path
    stop_resolved = stop_at.resolve()
    while current.exists():
        try:
            if current.resolve() == stop_resolved:
                break
        except FileNotFoundError:
            break
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def relocate_file_path(label: str, source: Path, destination: Path) -> list[str]:
    notes: list[str] = []
    if not source.exists() or source.resolve() == destination.resolve():
        return notes
    if source.is_dir():
        raise ValueError(f"{label} currently points to a folder, not a file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.resolve() != source.resolve():
        notes.append(f"{label}: target already exists, so the current file stayed in place.")
        return notes
    shutil.move(str(source), str(destination))
    cleanup_empty_parent_chain(source.parent, ROOT_DIR)
    notes.append(f"{label}: moved file into {destination}.")
    return notes


def merge_directory_contents(label: str, source: Path, destination: Path) -> list[str]:
    notes: list[str] = []
    destination.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir(), key=lambda item: item.name.lower()):
        target_child = destination / child.name
        if child.is_dir():
            if target_child.exists() and target_child.is_file():
                notes.append(f"{label}: kept existing file {target_child.name} and left source folder {child.name} untouched.")
                continue
            notes.extend(merge_directory_contents(label, child, target_child))
            cleanup_empty_parent_chain(child, source)
            continue
        if target_child.exists():
            notes.append(f"{label}: kept existing file {target_child.name} and left the old copy untouched.")
            continue
        shutil.move(str(child), str(target_child))
    cleanup_empty_parent_chain(source, ROOT_DIR)
    return notes


def relocate_directory_path(label: str, source: Path, destination: Path) -> list[str]:
    notes: list[str] = []
    if not source.exists() or source.resolve() == destination.resolve():
        destination.mkdir(parents=True, exist_ok=True)
        return notes
    if source.is_file():
        raise ValueError(f"{label} currently points to a file, not a folder.")
    source_resolved = source.resolve()
    destination_resolved = destination.resolve()
    if path_is_within(destination_resolved, source_resolved) or path_is_within(source_resolved, destination_resolved):
        raise ValueError(f"{label} cannot move into a nested folder of itself.")
    notes.extend(merge_directory_contents(label, source, destination))
    notes.append(f"{label}: moved folder contents into {destination}.")
    return notes


def relocate_tracked_path(spec: dict[str, object], source: Path, destination: Path) -> list[str]:
    label = str(spec["label"])
    kind = str(spec["kind"])
    if kind == "dir":
        return relocate_directory_path(label, source, destination)
    return relocate_file_path(label, source, destination)


def build_full_backup_sources() -> list[dict[str, object]]:
    module_globals = globals()
    sources = [
        {
            "label": str(item["label"]),
            "path": Path(module_globals[str(item["path_key"])]) if item.get("path_key") else Path(item["path"]),
            "target": str(item["target"]),
        }
        for item in FULL_BACKUP_SOURCE_SPECS
    ]
    covered_dirs = [Path(item["path"]).resolve() for item in sources if Path(item["path"]).exists() and Path(item["path"]).is_dir()]
    covered_files = {Path(item["path"]).resolve() for item in sources if Path(item["path"]).exists() and Path(item["path"]).is_file()}
    for spec, current_path in current_tracked_paths():
        key = str(spec["key"])
        resolved_path = Path(current_path).resolve()
        if key == "backups_dir" or resolved_path == BACKUPS_DIR.resolve():
            continue
        if resolved_path in covered_files or any(path_is_within(resolved_path, directory) for directory in covered_dirs):
            continue
        target_name = key if str(spec["kind"]) == "dir" else f"{key}{resolved_path.suffix}"
        sources.append({
            "label": f"{spec['label']} override",
            "path": resolved_path,
            "target": f"external_paths/{target_name}",
        })
        if resolved_path.is_dir():
            covered_dirs.append(resolved_path)
        else:
            covered_files.add(resolved_path)
    return sources


def list_backup_directories(prefix: str | None = None) -> list[Path]:
    if not BACKUPS_DIR.exists():
        return []
    folders = [path for path in BACKUPS_DIR.iterdir() if path.is_dir()]
    if prefix:
        folders = [path for path in folders if path.name.startswith(prefix)]
    return sorted(folders, key=lambda path: path.stat().st_mtime, reverse=True)


def latest_backup_directory(prefix: str | None = None) -> Path | None:
    folders = list_backup_directories(prefix)
    return folders[0] if folders else None


def latest_backup_snapshot(prefix: str | None = None) -> dict[str, str] | None:
    latest = latest_backup_directory(prefix)
    if not latest:
        return None
    return {
        "name": latest.name,
        "path": str(latest),
        "modified": datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
    }


def next_backup_snapshot_dir(prefix: str = "full_backup") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = BACKUPS_DIR / f"{prefix}_{stamp}"
    version = 2
    while candidate.exists():
        candidate = BACKUPS_DIR / f"{prefix}_{stamp}__{version}"
        version += 1
    return candidate


def create_full_backup_snapshot(trigger: str = "manual") -> dict[str, object]:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_dir = next_backup_snapshot_dir("full_backup")
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    copied: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for item in build_full_backup_sources():
        source = Path(item["path"])
        target = snapshot_dir / str(item["target"])
        if not source.exists():
            missing.append({"label": str(item["label"]), "path": str(source)})
            continue
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        copied.append({"label": str(item["label"]), "path": str(source), "target": str(target.relative_to(snapshot_dir))})
    manifest = {
        "kind": "full_backup",
        "trigger": trigger,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "root_dir": str(ROOT_DIR),
        "policy_label": FULL_BACKUP_POLICY_LABEL,
        "copied": copied,
        "missing": missing,
    }
    write_json_value(snapshot_dir / "manifest.json", manifest)
    return {
        "name": snapshot_dir.name,
        "path": str(snapshot_dir),
        "copied_count": len(copied),
        "missing_count": len(missing),
        "modified": datetime.fromtimestamp(snapshot_dir.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "trigger": trigger,
    }


def ensure_app_weekly_full_backup() -> dict[str, object] | None:
    with FULL_BACKUP_LOCK:
        latest = latest_backup_directory("full_backup_")
        if latest:
            latest_modified = datetime.fromtimestamp(latest.stat().st_mtime)
            if datetime.now() - latest_modified < FULL_BACKUP_INTERVAL:
                return None
        try:
            return create_full_backup_snapshot(trigger="app-weekly")
        except Exception:
            return None


def slugify(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "export"


def dedupe_clean_strings(values) -> list[str]:
    seen: set[str] = set()
    clean: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        clean.append(text)
    return clean


def parseBuilderMediaPaths(value) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return dedupe_clean_strings(part.strip() for part in text.split(";"))


def parseBuilderPhotoEntries(value) -> list[dict[str, str]]:
    text = str(value or "").strip()
    if not text:
        return []
    raw_items = []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                raw_items = parsed
        except Exception:
            raw_items = []
    if not raw_items:
        raw_items = [{"path": path} for path in parseBuilderMediaPaths(text)]
    seen: set[str] = set()
    clean: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        temp_id = str(item.get("temp_id", "") or item.get("tempId", "")).strip()
        name = str(item.get("name", "")).strip()
        step_key = str(item.get("step_key", "") or item.get("stepKey", "")).strip()
        step_label = str(item.get("step_label", "") or item.get("stepLabel", "")).strip()
        if not path and not temp_id:
            continue
        dedupe_key = f"path:{path}" if path else f"temp:{temp_id}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        clean.append(
            {
                "path": path,
                "temp_id": temp_id,
                "name": name or (os.path.basename(path) if path else ""),
                "step_key": step_key,
                "step_label": step_label,
            }
        )
    return clean


def get_maintenance_runtime() -> dict[str, float]:
    stored = read_json_dict(MAINTENANCE_RUNTIME)
    defaults = {
        "furnace_hours": 0.0,
        "uv1_hours": 0.0,
        "uv2_hours": 0.0,
        "draw_count": 0.0,
    }
    runtime: dict[str, float] = {}
    source_map = {
        "furnace_hours": "furnace_hours",
        "uv1_hours": "uv1_hours",
        "uv2_hours": "uv2_hours",
        "draw_count": "last_draw_count",
    }
    for key, default in defaults.items():
        try:
            runtime[key] = float(stored.get(source_map[key], default))
        except (TypeError, ValueError):
            runtime[key] = float(default)
    try:
        runtime["draw_count"] = float(len(list_dataset_csv_files()))
    except Exception:
        runtime["draw_count"] = float(runtime.get("draw_count", 0.0) or 0.0)
    return runtime


def get_maintenance_runtime_context() -> dict:
    stored = read_json_dict(MAINTENANCE_RUNTIME)
    runtime = get_maintenance_runtime()
    current_date_raw = str(stored.get("current_date", "")).strip()
    try:
        current_date = datetime.strptime(current_date_raw, "%Y-%m-%d").date() if current_date_raw else datetime.now().date()
    except ValueError:
        current_date = datetime.now().date()
    try:
        warn_days = int(float(stored.get("warn_days", 14)))
    except (TypeError, ValueError):
        warn_days = 14
    try:
        warn_hours = float(stored.get("warn_hours", 50.0))
    except (TypeError, ValueError):
        warn_hours = 50.0
    return {
        **runtime,
        "current_date": current_date,
        "warn_days": warn_days,
        "warn_hours": warn_hours,
    }


def read_maintenance_tracker_rows() -> list[dict[str, str]]:
    if not MAINTENANCE_DIR.exists():
        return []
    rows: list[dict[str, str]] = []
    for path in sorted(MAINTENANCE_DIR.glob("*.xlsx")):
        try:
            df = pd.read_excel(path)
        except Exception:
            continue
        rename_map = {
            "Equipment": "Component",
            "Task ID": "Task_ID",
            "Task Name": "Task",
            "Tracking Mode": "Tracking_Mode",
            "Required Parts": "Required_Parts",
            "Group": "Task_Group",
            "Planning months": "Planning_Window_Months",
            "Estimated duration min": "Est_Duration_Min",
            "Manual Page": "Page",
            "Document Name": "Manual_Name",
            "Document File/Link": "Document",
            "Last Done Date": "Last_Done_Date",
            "Last Done Hours": "Last_Done_Hours",
            "Last_Done_Draw": "Last_Done_Draw",
        }
        df = df.rename(columns=rename_map)
        for column in ["Component", "Task_ID", "Task", "Task_Group", "Tracking_Mode", "Required_Parts"]:
            if column not in df.columns:
                df[column] = ""
        df["Source_File"] = path.name
        for row in df.to_dict(orient="records"):
            component = str(row.get("Component", "")).strip()
            task = str(row.get("Task", "")).strip()
            if not component or not task:
                continue
            rows.append({key: "" if (value is None or (isinstance(value, float) and math.isnan(value))) else str(value) for key, value in row.items()})
    return rows


MAINTENANCE_SOURCE_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "Task_ID": ("Task_ID", "Task ID"),
    "Component": ("Component", "Equipment"),
    "Task": ("Task", "Task Name"),
    "Task_Group": ("Task_Group", "Group"),
    "Task_Groups": ("Task_Groups", "Task_Group", "Group"),
    "Required_Parts": ("Required_Parts", "Required Parts"),
    "Required_Tools": ("Required_Tools", "Required Tools"),
    "Mandatory_Parts": ("Mandatory_Parts", "Mandatory Parts"),
    "Conditional_Parts": ("Conditional_Parts", "Conditional Parts"),
    "Preparation_Lead_Days": ("Preparation_Lead_Days", "Preparation Lead Days"),
    "Parts_Check_Lead_Days": ("Parts_Check_Lead_Days", "Parts Check Lead Days"),
    "Auto_Order_Mandatory_Parts": ("Auto_Order_Mandatory_Parts", "Auto Order Mandatory Parts"),
    "Tracking_Mode": ("Tracking_Mode", "Tracking Mode"),
    "Hours Source": ("Hours Source", "Hours_Source"),
    "Interval Type": ("Interval Type",),
    "Interval Value": ("Interval Value",),
    "Interval Unit": ("Interval Unit",),
    "Planning_Window_Months": ("Planning_Window_Months", "Planning months"),
    "Due Threshold (days)": ("Due Threshold (days)",),
    "Trigger Context": ("Trigger Context",),
    "Trigger_Modes": ("Trigger_Modes", "Trigger Modes"),
    "Trigger_Hours_Source": ("Trigger_Hours_Source", "Trigger Hours Source"),
    "Trigger_Hours_Interval": ("Trigger_Hours_Interval", "Trigger Hours Interval"),
    "Trigger_Draws_Interval": ("Trigger_Draws_Interval", "Trigger Draws Interval"),
    "Trigger_Calendar_Value": ("Trigger_Calendar_Value", "Trigger Calendar Value"),
    "Trigger_Calendar_Unit": ("Trigger_Calendar_Unit", "Trigger Calendar Unit"),
    "Calendar Rule": ("Calendar Rule",),
    "Owner": ("Owner",),
    "Manual_Name": ("Manual_Name", "Document Name"),
    "Page": ("Page", "Manual Page"),
    "Document": ("Document", "Document File/Link"),
    "Last_Done_Date": ("Last_Done_Date", "Last Done Date"),
    "Last_Done_Hours": ("Last_Done_Hours", "Last Done Hours"),
    "Last_Done_Draw": ("Last_Done_Draw", "Last Done Draw"),
    "Last_Done_Hours_UV1": ("Last_Done_Hours_UV1", "Last Done Hours UV1", "Last Done UV1 Hours"),
    "Last_Done_Hours_UV2": ("Last_Done_Hours_UV2", "Last Done Hours UV2", "Last Done UV2 Hours"),
    "Last_Done_Hours_Furnace": ("Last_Done_Hours_Furnace", "Last Done Hours Furnace", "Last Done Furnace Hours"),
    "Procedure Summary": ("Procedure Summary",),
    "Safety/Notes": ("Safety/Notes",),
    "Test_Preset": ("Test_Preset", "Test Preset"),
    "Test_Fields": ("Test_Fields", "Test Fields"),
    "Test_Thresholds": ("Test_Thresholds", "Test Thresholds"),
    "Test_Condition": ("Test_Condition", "Test Condition"),
    "Test_Action": ("Test_Action", "Test Action"),
}


def maintenance_field_aliases(name: str) -> tuple[str, ...]:
    return MAINTENANCE_SOURCE_FIELD_ALIASES.get(name, (name,))


def first_task_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = str(row.get(name, "") or "").strip()
        if value:
            return value
    return ""


def load_maintenance_test_preset_library() -> dict[str, dict]:
    data = read_json_value(MAINTENANCE_TEST_PRESETS, {})
    return data if isinstance(data, dict) else {}


def resolve_maintenance_source_column(columns, logical_name: str) -> str:
    available = {str(column): column for column in columns}
    for alias in maintenance_field_aliases(logical_name):
        if alias in available:
            return alias
    return maintenance_field_aliases(logical_name)[0]


def find_maintenance_source_row_mask(df: pd.DataFrame, task_id: str, component: str, task: str) -> pd.Series:
    mask = pd.Series([False] * len(df), index=df.index)
    safe_task_id = str(task_id or "").strip()
    safe_component = str(component or "").strip().lower()
    safe_task = str(task or "").strip().lower()
    if safe_task_id:
        for column_name in maintenance_field_aliases("Task_ID"):
            if column_name in df.columns:
                mask = df[column_name].astype(str).str.strip().eq(safe_task_id)
                if mask.any():
                    return mask
    component_columns = [name for name in maintenance_field_aliases("Component") if name in df.columns]
    task_columns = [name for name in maintenance_field_aliases("Task") if name in df.columns]
    for component_column in component_columns:
        for task_column in task_columns:
            mask = (
                df[component_column].astype(str).str.strip().str.lower().eq(safe_component)
                & df[task_column].astype(str).str.strip().str.lower().eq(safe_task)
            )
            if mask.any():
                return mask
    return mask


def update_maintenance_source_task(source_file: str, task_id: str, component: str, task: str, updates: dict[str, object]) -> None:
    source_name = str(source_file or "").strip()
    if not source_name:
        raise ValueError("Task source file is missing.")
    path = MAINTENANCE_DIR / source_name
    if not path.exists():
        raise FileNotFoundError(f"Maintenance source file not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    elif suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported maintenance source type: {path.suffix}")
    mask = find_maintenance_source_row_mask(df, task_id, component, task)
    if not mask.any():
        raise ValueError("Task row was not found in the maintenance source file.")
    for logical_name, raw_value in updates.items():
        column_name = resolve_maintenance_source_column(df.columns, logical_name)
        if column_name not in df.columns:
            df[column_name] = ""
        df.loc[mask, column_name] = raw_value
    if suffix in {".xlsx", ".xls"}:
        write_dataframe_atomic(path, df)
    else:
        write_dataframe_atomic(path, df)


def delete_maintenance_source_task(source_file: str, task_id: str, component: str, task: str) -> None:
    source_name = str(source_file or "").strip()
    if not source_name:
        raise ValueError("Task source file is missing.")
    path = MAINTENANCE_DIR / source_name
    if not path.exists():
        raise FileNotFoundError(f"Maintenance source file not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    elif suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported maintenance source type: {path.suffix}")
    mask = find_maintenance_source_row_mask(df, task_id, component, task)
    if not mask.any():
        raise ValueError("Task row was not found in the maintenance source file.")
    df = df.loc[~mask].copy()
    if suffix in {".xlsx", ".xls"}:
        write_dataframe_atomic(path, df)
    else:
        write_dataframe_atomic(path, df)


def maintenance_task_id_prefix_for_component(df: pd.DataFrame, component: str) -> str:
    task_id_columns = [name for name in maintenance_field_aliases("Task_ID") if name in df.columns]
    component_columns = [name for name in maintenance_field_aliases("Component") if name in df.columns]
    safe_component = str(component or "").strip().lower()

    def extract_prefix(raw_task_id: object) -> str:
        safe_value = str(raw_task_id or "").strip()
        match = re.match(r"^(.*?)[-_]?(\d+)$", safe_value)
        return match.group(1).rstrip("-_") if match else ""

    component_prefixes: dict[str, int] = {}
    if safe_component and task_id_columns and component_columns:
        for component_column in component_columns:
            for task_id_column in task_id_columns:
                for _, row in df.iterrows():
                    row_component = str(row.get(component_column, "")).strip().lower()
                    if row_component != safe_component:
                        continue
                    prefix = extract_prefix(row.get(task_id_column, ""))
                    if prefix:
                        component_prefixes[prefix] = component_prefixes.get(prefix, 0) + 1
    if component_prefixes:
        return sorted(component_prefixes.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))[0][0]

    all_prefixes: dict[str, int] = {}
    for task_id_column in task_id_columns:
        for raw_value in df.get(task_id_column, []):
            prefix = extract_prefix(raw_value)
            if prefix:
                all_prefixes[prefix] = all_prefixes.get(prefix, 0) + 1
    if len(all_prefixes) == 1:
        return next(iter(all_prefixes))

    words = [token for token in re.findall(r"[A-Za-z0-9]+", str(component or "")) if token]
    if not words:
        return "GEN-MNT"
    initials = "".join(token[0].upper() for token in words[:3])
    return f"{initials or 'GEN'}-MNT"


def generate_next_maintenance_task_id(df: pd.DataFrame, component: str) -> str:
    prefix = maintenance_task_id_prefix_for_component(df, component)
    task_id_columns = [name for name in maintenance_field_aliases("Task_ID") if name in df.columns]
    max_value = 0
    for task_id_column in task_id_columns:
        for raw_value in df.get(task_id_column, []):
            safe_value = str(raw_value or "").strip()
            match = re.match(rf"^{re.escape(prefix)}[-_]?(\d+)$", safe_value, re.IGNORECASE)
            if not match:
                continue
            try:
                max_value = max(max_value, int(match.group(1)))
            except ValueError:
                continue
    return f"{prefix}-{max_value + 1:03d}"


def create_maintenance_source_task(
    source_file: str,
    component: str,
    task: str,
    task_group: str,
) -> dict[str, str]:
    source_name = str(source_file or "").strip()
    if not source_name:
        raise ValueError("Task source file is required.")
    path = MAINTENANCE_DIR / source_name
    if not path.exists():
        raise FileNotFoundError(f"Maintenance source file not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    elif suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported maintenance source type: {path.suffix}")

    safe_component = str(component or "").strip() or "General"
    safe_task = str(task or "").strip()
    safe_group = str(task_group or "").strip() or "General"
    if not safe_task:
        raise ValueError("Task name is required.")

    existing_mask = find_maintenance_source_row_mask(df, "", safe_component, safe_task)
    if existing_mask.any():
        raise ValueError("A task with the same component and task name already exists in that source file.")

    required_logical_fields = [
        "Task_ID",
        "Component",
        "Task",
        "Task_Group",
        "Task_Groups",
        "Tracking_Mode",
        "Required_Parts",
        "Required_Tools",
        "Mandatory_Parts",
        "Conditional_Parts",
        "Preparation_Lead_Days",
        "Parts_Check_Lead_Days",
        "Auto_Order_Mandatory_Parts",
        "Owner",
        "Manual_Name",
        "Page",
        "Document",
        "Procedure Summary",
        "Safety/Notes",
    ]
    for logical_name in required_logical_fields:
        column_name = resolve_maintenance_source_column(df.columns, logical_name)
        if column_name not in df.columns:
            df[column_name] = ""

    task_id = generate_next_maintenance_task_id(df, safe_component)
    new_row = {str(column): "" for column in df.columns}
    new_row[resolve_maintenance_source_column(df.columns, "Task_ID")] = task_id
    new_row[resolve_maintenance_source_column(df.columns, "Component")] = safe_component
    new_row[resolve_maintenance_source_column(df.columns, "Task")] = safe_task
    new_row[resolve_maintenance_source_column(df.columns, "Task_Group")] = safe_group
    task_groups_column = resolve_maintenance_source_column(df.columns, "Task_Groups")
    if task_groups_column in new_row:
        new_row[task_groups_column] = safe_group

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    write_dataframe_atomic(path, df)
    return {
        "task_id": task_id,
        "component": safe_component,
        "task": safe_task,
        "task_group": safe_group,
        "source_file": source_name,
    }


def split_required_parts(value: str | None) -> list[str]:
    text = str(value or "").replace("\n", ";").replace("/", ";")
    output = []
    for item in text.split(";"):
        part = item.strip()
        if part and part.lower() != "nan":
            output.append(part)
    return dedupe_strings(output)


def dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def is_tool_like_part_name(part_name: str) -> bool:
    lowered = str(part_name or "").strip().lower()
    if not lowered:
        return False
    tool_tokens = [
        "cleaning kit",
        "cleaning cloth",
        "tool",
        "wrench",
        "screwdriver",
        "hex key",
        "allen key",
        "spanner",
    ]
    return any(token in lowered for token in tool_tokens)


def ensure_parts_company(company_name: str) -> None:
    company = str(company_name or "").strip()
    if not company:
        return
    rows = read_csv_rows(PARTS_COMPANIES)
    fieldnames = read_csv_fieldnames(PARTS_COMPANIES) or ["Company", "Last Updated"]
    if any(str(row.get("Company", "")).strip().lower() == company.lower() for row in rows):
        return
    rows.append(
        {
            "Company": company,
            "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    write_csv_rows(PARTS_COMPANIES, rows, fieldnames)


def to_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def to_int(value: str | None, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _process_setup_match_key(name: str, keys: list[str]) -> str | None:
    raw = str(name or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    for key in keys:
        if str(key).strip().lower() == lowered:
            return key
    for key in keys:
        option = str(key).strip().lower()
        if lowered in option or option in lowered:
            return key
    return None


def _process_setup_interpolate_linear(x: float, points: list[tuple[float, float]]) -> float:
    if not points:
        return 1.0
    pts = sorted(points, key=lambda item: item[0])
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for left, right in zip(pts, pts[1:]):
        x0, y0 = left
        x1, y1 = right
        if x0 <= x <= x1:
            span = x1 - x0
            if span <= 0:
                return y0
            ratio = (x - x0) / span
            return y0 + ((y1 - y0) * ratio)
    return pts[-1][1]


def _process_setup_coating_viscosity_kg_m_s(coating_name: str, temp_c: float, coating_cfg: dict) -> float:
    coatings = (coating_cfg or {}).get("coatings", {}) or {}
    match = _process_setup_match_key(coating_name, list(coatings.keys()))
    coating_entry = coatings.get(match, {}) if match else {}
    configured = to_float((coating_entry or {}).get("Viscosity"))
    if configured > 0:
        return configured
    normalized = str(match or coating_name or "").strip().upper().replace("_", "").replace("-", "")
    if "DP1032" in normalized:
        return max(0.01, (34.884 * math.exp(-0.0806 * float(temp_c))) - 0.162)
    ds_points = [
        (25.0, 5.9),
        (30.0, 3.5),
        (35.0, 2.04),
        (40.0, 1.2),
        (45.0, 0.7),
        (50.0, 0.4),
        (55.0, 0.25),
    ]
    return max(0.01, _process_setup_interpolate_linear(float(temp_c), ds_points))


def _process_setup_calculate_coated_diameter_um(
    entry_fiber_diameter_um: float,
    die_diameter_um: float,
    mu_kg_m_s: float,
    rho_kg_m3: float,
    neck_length_m: float,
    pulling_speed_m_s: float,
    g_m_s2: float = 9.80665,
) -> float:
    entry_um = to_float(entry_fiber_diameter_um)
    die_um = to_float(die_diameter_um)
    mu = to_float(mu_kg_m_s)
    rho = to_float(rho_kg_m3)
    neck_length = to_float(neck_length_m)
    speed = to_float(pulling_speed_m_s)
    gravity = to_float(g_m_s2) or 9.80665
    if entry_um <= 0 or die_um <= 0 or mu <= 0 or rho <= 0 or neck_length <= 0 or speed <= 0:
        return entry_um

    die_radius_m = (die_um / 2.0) * 1e-6
    fiber_radius_m = (entry_um / 2.0) * 1e-6
    if fiber_radius_m <= 0 or die_radius_m <= 0 or fiber_radius_m >= die_radius_m:
        return entry_um

    ratio = fiber_radius_m / die_radius_m
    try:
        ratio_log = math.log(ratio)
    except ValueError:
        return entry_um
    if ratio_log == 0:
        return entry_um

    delta_p = neck_length * rho * gravity
    phi = (delta_p * (die_radius_m**2)) / (8.0 * mu * neck_length * speed)
    term1 = phi * (
        1.0 - ratio**4 + (((1.0 - ratio**2) ** 2) / ratio_log)
    )
    term2 = -(ratio**2 + ((1.0 - ratio**2) / (2.0 * ratio_log)))
    inside = term1 + term2 + ratio**2
    if inside <= 0:
        return entry_um

    thickness_m = die_radius_m * (math.sqrt(inside) - ratio)
    return entry_um + (thickness_m * 2.0 * 1e6)


def _process_setup_stocked_die_names(coating_cfg: dict, dies_map: dict) -> list[str]:
    config_dies = (coating_cfg or {}).get("dies", {}) or {}
    if not isinstance(dies_map, dict) or not config_dies:
        return []
    sizes: list[float] = []
    for row in dies_map.values():
        if not isinstance(row, dict):
            continue
        for key in ("entry_die_um", "primary_die_um"):
            size = to_float(row.get(key))
            if size > 0:
                sizes.append(size)
    stocked: list[str] = []
    for size in sizes:
        best_name = ""
        best_gap = float("inf")
        for die_name, die_cfg in config_dies.items():
            die_diameter = to_float((die_cfg or {}).get("Die_Diameter"))
            if die_diameter <= 0:
                continue
            gap = abs(die_diameter - size)
            if gap < best_gap:
                best_gap = gap
                best_name = str(die_name)
        if best_name and best_gap <= 15:
            stocked.append(best_name)
    return dedupe_strings(stocked)


def auto_select_process_setup_dies_action(payload: dict) -> JsonResponse:
    coating_payload = payload.get("coating") or {}
    if not isinstance(coating_payload, dict):
        coating_payload = {}

    entry_um = to_float(coating_payload.get("entry_fiber_diameter_um"))
    target_first_um = to_float(coating_payload.get("target_first_coating_diameter_um"))
    target_second_um = to_float(coating_payload.get("target_second_coating_diameter_um"))
    primary_temp_c = to_float(coating_payload.get("primary_temp_c"))
    secondary_temp_c = to_float(coating_payload.get("secondary_temp_c"))
    draw_speed_m_min = to_float(coating_payload.get("draw_speed_m_min"))
    primary_coating = str(coating_payload.get("primary_coating", "")).strip()
    secondary_coating = str(coating_payload.get("secondary_coating", "")).strip()

    missing: list[str] = []
    if entry_um <= 0:
        missing.append("Entry fiber diameter")
    if target_first_um <= 0:
        missing.append("Target first coating diameter")
    if target_second_um <= 0:
        missing.append("Target second coating diameter")
    if not primary_coating:
        missing.append("Primary coating")
    if not secondary_coating:
        missing.append("Secondary coating")
    if primary_temp_c <= 0:
        missing.append("Primary temperature")
    if secondary_temp_c <= 0:
        missing.append("Secondary temperature")
    if draw_speed_m_min <= 0:
        missing.append("Draw speed")
    if missing:
        return JsonResponse(
            {
                "ok": True,
                "ready": False,
                "message": f"Fill {', '.join(missing)} to auto-pick dies.",
                "missing": missing,
            },
            200,
        )

    coating_cfg = read_json_dict(COATING_CONFIG)
    dies_cfg = read_json_dict(DIES_CONFIG)
    config_dies = (coating_cfg or {}).get("dies", {}) or {}
    coatings = (coating_cfg or {}).get("coatings", {}) or {}
    primary_key = _process_setup_match_key(primary_coating, list(coatings.keys()))
    secondary_key = _process_setup_match_key(secondary_coating, list(coatings.keys()))
    if not primary_key or not secondary_key:
        return JsonResponse(
            {
                "ok": False,
                "message": "Could not match the selected coating names to the coating guide config.",
            },
            400,
        )
    if not config_dies:
        return JsonResponse({"ok": False, "message": "No dies are configured in config_coating.json."}, 400)

    stocked_die_names = _process_setup_stocked_die_names(coating_cfg, dies_cfg)
    die_catalog_names = stocked_die_names if len(stocked_die_names) >= 2 else dedupe_strings(list(config_dies.keys()))
    using_stock_only = len(stocked_die_names) >= 2

    mu1 = _process_setup_coating_viscosity_kg_m_s(primary_key, primary_temp_c, coating_cfg)
    mu2 = _process_setup_coating_viscosity_kg_m_s(secondary_key, secondary_temp_c, coating_cfg)
    rho1 = to_float((coatings.get(primary_key) or {}).get("Density")) or 1000.0
    rho2 = to_float((coatings.get(secondary_key) or {}).get("Density")) or 1000.0
    speed_m_s = draw_speed_m_min / 60.0 if draw_speed_m_min > 0 else 0.917

    best_primary = ""
    best_secondary = ""
    best_fc = 0.0
    best_sc = 0.0
    best_score = float("inf")
    best_primary_die_um = 0.0
    best_secondary_die_um = 0.0

    for primary_name in die_catalog_names:
        primary_cfg = config_dies.get(primary_name, {}) or {}
        primary_die_um = to_float(primary_cfg.get("Die_Diameter"))
        primary_neck_length = to_float(primary_cfg.get("Neck_Length")) or 0.002
        if primary_die_um <= 0:
            continue
        predicted_fc = _process_setup_calculate_coated_diameter_um(
            entry_fiber_diameter_um=entry_um,
            die_diameter_um=primary_die_um,
            mu_kg_m_s=mu1,
            rho_kg_m3=rho1,
            neck_length_m=primary_neck_length,
            pulling_speed_m_s=speed_m_s,
        )
        for secondary_name in die_catalog_names:
            secondary_cfg = config_dies.get(secondary_name, {}) or {}
            secondary_die_um = to_float(secondary_cfg.get("Die_Diameter"))
            secondary_neck_length = to_float(secondary_cfg.get("Neck_Length")) or 0.002
            if secondary_die_um <= 0:
                continue
            predicted_sc = _process_setup_calculate_coated_diameter_um(
                entry_fiber_diameter_um=predicted_fc,
                die_diameter_um=secondary_die_um,
                mu_kg_m_s=mu2,
                rho_kg_m3=rho2,
                neck_length_m=secondary_neck_length,
                pulling_speed_m_s=speed_m_s,
            )
            score = ((predicted_fc - target_first_um) ** 2) + ((predicted_sc - target_second_um) ** 2)
            if score < best_score:
                best_score = score
                best_primary = str(primary_name)
                best_secondary = str(secondary_name)
                best_fc = float(predicted_fc)
                best_sc = float(predicted_sc)
                best_primary_die_um = primary_die_um
                best_secondary_die_um = secondary_die_um

    if not best_primary or not best_secondary:
        return JsonResponse({"ok": False, "message": "Could not evaluate a valid die pair."}, 400)

    stock_note = using_stock_only
    source_note = (
        f"Auto picked from {len(die_catalog_names)} stocked dies."
        if stock_note
        else f"Auto picked from full die catalog ({len(die_catalog_names)} dies) because stocked die setup is incomplete."
    )
    details = {
        "primary_die": best_primary,
        "secondary_die": best_secondary,
        "predicted_first_um": round(best_fc, 2),
        "predicted_second_um": round(best_sc, 2),
        "ideal_primary_die_um": round(best_primary_die_um, 1),
        "ideal_secondary_die_um": round(best_secondary_die_um, 1),
        "source_note": source_note,
        "using_stock_only": using_stock_only,
        "catalog_count": len(die_catalog_names),
        "stocked_die_names": stocked_die_names,
        "error_first_um": round(best_fc - target_first_um, 2),
        "error_second_um": round(best_sc - target_second_um, 2),
        "primary_coating": primary_key,
        "secondary_coating": secondary_key,
    }
    return JsonResponse(
        {
            "ok": True,
            "ready": True,
            "message": source_note,
            "auto_dies": details,
        },
        200,
    )


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def normalize_recurrence(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"none", "nan"}:
        return "none"
    if text == "weekly":
        return "weekly"
    if text == "monthly":
        return "monthly"
    if text in {"every 3 months", "3 months", "quarterly"}:
        return "quarterly"
    if text in {"every 6 months", "6 months", "semiannual", "semi-annually"}:
        return "semiannual"
    if text == "yearly":
        return "yearly"
    return "none"


def next_recurrence_dt(dt: datetime, recurrence: str) -> datetime:
    if recurrence == "weekly":
        return dt + timedelta(weeks=1)
    if recurrence == "monthly":
        month = dt.month + 1
        year = dt.year
        if month > 12:
            month = 1
            year += 1
        return dt.replace(year=year, month=month)
    if recurrence == "quarterly":
        month = dt.month + 3
        year = dt.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        return dt.replace(year=year, month=month)
    if recurrence == "semiannual":
        month = dt.month + 6
        year = dt.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        return dt.replace(year=year, month=month)
    if recurrence == "yearly":
        return dt.replace(year=dt.year + 1)
    return dt


def normalize_maintenance_hours_source(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if text in {"uv1", "uv 1", "uv_system_1", "uv system 1", "system1", "system 1"}:
        return "uv1"
    if text in {"uv2", "uv 2", "uv_system_2", "uv system 2", "system2", "system 2"}:
        return "uv2"
    return "furnace"


def maintenance_runtime_hours_for_source(source: str, runtime_context: dict) -> float:
    key = normalize_maintenance_hours_source(source)
    if key == "uv1":
        return float(runtime_context.get("uv1_hours", 0.0) or 0.0)
    if key == "uv2":
        return float(runtime_context.get("uv2_hours", 0.0) or 0.0)
    return float(runtime_context.get("furnace_hours", 0.0) or 0.0)


def maintenance_last_done_updates(source: str, runtime_context: dict) -> dict[str, object]:
    hours_value = round(maintenance_runtime_hours_for_source(source, runtime_context), 3)
    draw_value = int(round(float(runtime_context.get("draw_count", 0.0) or 0.0)))
    date_label = datetime.now().strftime("%Y-%m-%d")
    updates: dict[str, object] = {
        "Last_Done_Date": date_label,
        "Last_Done_Hours": hours_value,
        "Last_Done_Draw": draw_value,
    }
    source_key = normalize_maintenance_hours_source(source)
    if source_key == "uv1":
        updates["Last_Done_Hours_UV1"] = hours_value
    elif source_key == "uv2":
        updates["Last_Done_Hours_UV2"] = hours_value
    else:
        updates["Last_Done_Hours_Furnace"] = hours_value
    return updates


def infer_maintenance_recurrence_from_task(task_row: dict[str, str]) -> str:
    direct = normalize_recurrence(first_task_value(task_row, "Calendar Rule"))
    if direct != "none":
        return direct
    try:
        interval_value = float(first_task_value(task_row, "Trigger_Calendar_Value", "Interval Value", "Interval_Value") or 0)
    except (TypeError, ValueError):
        interval_value = 0.0
    unit = first_task_value(task_row, "Trigger_Calendar_Unit", "Interval Unit", "Interval_Unit").strip().lower()
    if "week" in unit and interval_value >= 1:
        return "weekly"
    if "month" in unit:
        if abs(interval_value - 1.0) < 0.01:
            return "monthly"
        if abs(interval_value - 3.0) < 0.01:
            return "quarterly"
        if abs(interval_value - 6.0) < 0.01:
            return "semiannual"
        if abs(interval_value - 12.0) < 0.01:
            return "yearly"
    if "year" in unit and interval_value >= 1:
        return "yearly"
    return "none"


def find_maintenance_task_record(task_id: str, component: str, task: str) -> dict[str, str] | None:
    safe_task_id = str(task_id or "").strip()
    safe_component = str(component or "").strip().lower()
    safe_task = str(task or "").strip().lower()
    for row in read_maintenance_tracker_rows():
        row_task_id = str(row.get("Task_ID", "") or row.get("Task ID", "")).strip()
        row_component = str(row.get("Component", "") or row.get("Equipment", "")).strip().lower()
        row_task = str(row.get("Task", "") or row.get("Task Name", "")).strip().lower()
        if safe_task_id and row_task_id == safe_task_id:
            return row
        if row_component == safe_component and row_task == safe_task:
            return row
    return None


def build_maintenance_due_lookup(runtime_context: dict) -> dict[str, dict[str, object]]:
    due_lookup: dict[str, dict[str, object]] = {}
    def due_meta_score(entry: dict[str, object]) -> int:
        score = 0
        next_due_date = str(entry.get("next_due_date", "") or "").strip()
        next_due_hours = entry.get("next_due_hours")
        next_due_draw = entry.get("next_due_draw")
        timing_status = str(entry.get("timing_status", "") or "").strip().upper()
        hours_source = str(entry.get("hours_source", "") or "").strip()
        if next_due_date:
            score += 4
        if next_due_hours is not None and not pd.isna(next_due_hours):
            score += 4
        if next_due_draw is not None and not pd.isna(next_due_draw):
            score += 4
        if timing_status and timing_status != "ROUTINE":
            score += 1
        if hours_source:
            score += 1
        return score
    try:
        helper_df = load_maintenance_folder_df(str(MAINTENANCE_DIR))
        helper_status_df = compute_maintenance_status_df(
            helper_df,
            current_draw_count=int(runtime_context["draw_count"]),
            furnace_hours=float(runtime_context["furnace_hours"]),
            uv1_hours=float(runtime_context["uv1_hours"]),
            uv2_hours=float(runtime_context["uv2_hours"]),
            warn_days=int(runtime_context["warn_days"]),
            warn_hours=float(runtime_context["warn_hours"]),
            current_date=runtime_context["current_date"],
        )
        for _, helper_row in helper_status_df.iterrows():
            task_id = str(helper_row.get("Task_ID", "")).strip()
            component = str(helper_row.get("Component", "")).strip().lower()
            task = str(helper_row.get("Task", "")).strip().lower()
            helper_key = task_id or f"{component}::{task}"
            if not helper_key:
                continue
            next_due_date = helper_row.get("Next_Due_Date")
            if hasattr(next_due_date, "isoformat"):
                next_due_date = next_due_date.isoformat()
            candidate = {
                "next_due_date": str(next_due_date or "").strip(),
                "next_due_hours": helper_row.get("Next_Due_Hours"),
                "next_due_draw": helper_row.get("Next_Due_Draw"),
                "timing_status": str(helper_row.get("Status", "")).strip(),
                "hours_source": str(helper_row.get("Hours_Source", "")).strip(),
            }
            existing = due_lookup.get(helper_key)
            if existing is None or due_meta_score(candidate) >= due_meta_score(existing):
                due_lookup[helper_key] = candidate
    except Exception:
        return {}
    return due_lookup


def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def add_months(dt: datetime, months: int) -> datetime:
    month = dt.month + months
    year = dt.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def build_demo_schedule_events(anchor: datetime) -> list[dict]:
    demo_day = anchor + timedelta(days=2)
    week_span_start = (anchor + timedelta(days=1)).replace(hour=18, minute=30)
    week_span_end = (anchor + timedelta(days=4)).replace(hour=9, minute=30)
    month_span_start = (anchor + timedelta(days=9)).replace(hour=8, minute=0)
    month_span_end = (anchor + timedelta(days=18)).replace(hour=17, minute=30)
    slots = [
        ("Maintenance", demo_day.replace(hour=7, minute=30), demo_day.replace(hour=9, minute=0), "DEMO | Morning maintenance window"),
        ("Drawing", demo_day.replace(hour=9, minute=15), demo_day.replace(hour=11, minute=45), "DEMO | Draw order cluster A"),
        ("Management Event", demo_day.replace(hour=10, minute=0), demo_day.replace(hour=10, minute=40), "DEMO | Shift coordination review"),
        ("Drawing", demo_day.replace(hour=12, minute=15), demo_day.replace(hour=16, minute=0), "DEMO | Draw order cluster B"),
        ("Stop", demo_day.replace(hour=16, minute=15), demo_day.replace(hour=18, minute=0), "DEMO | Cooling / stop block"),
        ("Maintenance", demo_day.replace(hour=18, minute=15), demo_day.replace(hour=19, minute=45), "DEMO | End-of-day coating check"),
        ("Management Event", week_span_start, week_span_end, "DEMO | Multi-day planning window"),
        ("Maintenance", month_span_start, month_span_end, "DEMO | Extended maintenance hold"),
    ]
    demo_events = []
    for event_type, start, end, description in slots:
        demo_events.append(
            {
                "event_type": event_type,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "start_label": start.strftime("%Y-%m-%d %H:%M"),
                "end_label": end.strftime("%Y-%m-%d %H:%M"),
                "date_label": start.strftime("%b %d"),
                "day_key": start.strftime("%Y-%m-%d"),
                "weekday_label": start.strftime("%a"),
                "description": description,
                "recurrence": "demo",
                "duration_hours": round((end - start).total_seconds() / 3600.0, 2),
                "is_demo": True,
            }
        )
    return demo_events


def summarize_draw_orders() -> dict:
    rows = read_csv_rows(DRAW_ORDERS)
    fieldnames = read_csv_fieldnames(DRAW_ORDERS)
    status_counts: dict[str, int] = {}
    raw_status_counts: dict[str, int] = {}
    recent = []
    monthly_counts: dict[str, int] = {}
    changed = False
    now = datetime.now()

    def tm_moved(value: object) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "y"}

    def dataset_snapshot_kv(csv_name: str | None) -> dict[str, str]:
        path = resolve_dataset_csv_path(str(csv_name or "").strip())
        if not path or not path.exists():
            return {}
        kv: dict[str, str] = {}
        for snapshot_row in read_csv_rows(path):
            key = str(snapshot_row.get("Parameter Name") or "").strip()
            if not key or key in kv:
                continue
            kv[key] = str(snapshot_row.get("Value") or "").strip()
        return kv

    def infer_done_dt(row: dict[str, str]) -> datetime | None:
        direct_done = parse_dt(row.get("Done Timestamp"))
        if direct_done:
            return direct_done
        csv_name = row.get("Assigned Dataset CSV", "") or row.get("Done CSV", "") or row.get("Active CSV", "")
        kv = dataset_snapshot_kv(csv_name)
        for key in (
            "Order__Draw Date",
            "Draw Date",
            "Process__Process Setup Timestamp",
            "Process Setup Timestamp",
        ):
            inferred = parse_dt(kv.get(key))
            if inferred:
                return inferred
        return None

    for row in rows:
        status = (row.get("Status") or "Unknown").strip() or "Unknown"
        raw_status_counts[status] = raw_status_counts.get(status, 0) + 1
        normalized_status = status.lower()
        moved_to_tm = tm_moved(row.get("T&M Moved"))
        if normalized_status == "done" and not moved_to_tm:
            done_dt = infer_done_dt(row)
            if done_dt and not str(row.get("Done Timestamp") or "").strip():
                row["Done Timestamp"] = done_dt.strftime("%Y-%m-%d %H:%M:%S")
                changed = True
            if done_dt and ((now - done_dt).total_seconds() / 86400.0) >= AUTO_MOVE_DONE_TO_TM_DAYS:
                row["T&M Moved"] = True
                if not str(row.get("T&M Moved Timestamp") or "").strip():
                    row["T&M Moved Timestamp"] = now.strftime("%Y-%m-%d %H:%M:%S")
                changed = True
                moved_to_tm = True
        if normalized_status == "done" and moved_to_tm:
            continue

        status_counts[status] = status_counts.get(status, 0) + 1
        updated_at = row.get("Status Updated At") or row.get("Timestamp") or ""
        dt = parse_dt(updated_at)
        if dt:
            month_key = dt.strftime("%m/%d")
            monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
        recent.append(
            {
                "preform": row.get("Preform Number", ""),
                "project": row.get("Fiber Project", ""),
                "geometry": row.get("Fiber Geometry Type", "") or row.get("Geometry", ""),
                "status": status,
                "priority": row.get("Priority", "Normal"),
                "length": row.get("Length (m)") or row.get("Required Length (m) (for T&M+costumer)") or "0",
                "good_zones": row.get("Good Zones Count", "") or row.get("Good Zones Count (required length zones)", "") or "0",
                "notes": row.get("Notes", ""),
                "done_description": row.get("Done Description", ""),
                "failed_description": row.get("Failed Description", ""),
                "dataset": row.get("Assigned Dataset CSV", "") or row.get("Done CSV", "") or row.get("Failed CSV", ""),
                "updated_at": updated_at,
            }
        )

    if changed and rows:
        write_csv_rows(DRAW_ORDERS, rows, fieldnames or list(rows[0].keys()))

    def sort_key(item: dict) -> datetime:
        return parse_dt(item.get("updated_at")) or datetime.min

    recent.sort(key=sort_key, reverse=True)
    total = len(rows)
    done = status_counts.get("Done", 0)
    failed = status_counts.get("Failed", 0)
    active = sum(
        count
        for label, count in raw_status_counts.items()
        if str(label or "").strip().lower() not in {"done", "failed"}
    )
    in_progress = status_counts.get("In Progress", 0)
    scheduled = status_counts.get("Scheduled", 0)
    pending = status_counts.get("Pending", 0)
    return {
        "total": total,
        "active": active,
        "in_progress": in_progress,
        "scheduled": scheduled,
        "pending": pending,
        "done": done,
        "failed": failed,
        "status_counts": status_counts,
        "recent": recent[:6],
        "activity_series": [{"label": key, "value": value} for key, value in list(monthly_counts.items())[-8:]],
    }


def summarize_schedule() -> dict:
    rows = read_csv_rows(TOWER_SCHEDULE)
    events = []
    master_rows = []
    daily_load: dict[str, dict[str, float]] = {}
    now = datetime.now()
    anchor = now.replace(hour=0, minute=0, second=0, microsecond=0)
    range_start = anchor - timedelta(days=7)
    range_end = add_months(anchor, 3)

    for row in rows:
        start = parse_dt(row.get("Start DateTime"))
        end = parse_dt(row.get("End DateTime"))
        master_rows.append(
            {
                "index": len(master_rows),
                "event_type": row.get("Event Type", "Unknown"),
                "start": row.get("Start DateTime", ""),
                "end": row.get("End DateTime", ""),
                "description": (row.get("Description") or "").strip(),
                "recurrence": normalize_recurrence(row.get("Recurrence", "")) or "none",
            }
        )
        duration_hours = round(((end - start).total_seconds() / 3600.0), 2) if start and end else 0
        events.append(
            {
                "event_type": row.get("Event Type", "Unknown"),
                "start": row.get("Start DateTime", ""),
                "end": row.get("End DateTime", ""),
                "description": (row.get("Description") or "").strip(),
                "recurrence": normalize_recurrence(row.get("Recurrence", "")),
                "sort": start or datetime.max,
                "duration_hours": duration_hours,
            }
        )

    expanded_events = []
    for item in events:
        start = item["sort"]
        end = parse_dt(item["end"])
        if not start or start == datetime.max or not end:
            continue

        recurrence = item["recurrence"]
        duration = end - start

        if recurrence == "none":
            occurrences = [(start, end)]
        else:
            occurrences = []
            occ_start = start
            occ_end = end
            safety = 0
            while occ_end < range_start and safety < 5000:
                occ_start = next_recurrence_dt(occ_start, recurrence)
                occ_end = occ_start + duration
                safety += 1
            safety = 0
            while occ_start <= range_end and safety < 5000:
                occurrences.append((occ_start, occ_end))
                occ_start = next_recurrence_dt(occ_start, recurrence)
                occ_end = occ_start + duration
                safety += 1

        for occ_start, occ_end in occurrences:
            if occ_end < range_start or occ_start > range_end:
                continue
            hours = round((occ_end - occ_start).total_seconds() / 3600.0, 2)
            day_key = occ_start.strftime("%m/%d")
            bucket = daily_load.setdefault(day_key, {"events": 0, "hours": 0.0})
            bucket["events"] += 1
            bucket["hours"] += hours
            expanded_events.append(
                {
                    "event_type": item["event_type"],
                    "start": occ_start.isoformat(),
                    "end": occ_end.isoformat(),
                    "start_label": occ_start.strftime("%Y-%m-%d %H:%M"),
                    "end_label": occ_end.strftime("%Y-%m-%d %H:%M"),
                    "date_label": occ_start.strftime("%b %d"),
                    "day_key": occ_start.strftime("%Y-%m-%d"),
                    "weekday_label": occ_start.strftime("%a"),
                    "description": item["description"],
                    "recurrence": recurrence,
                    "duration_hours": hours,
                    "is_demo": False,
                }
            )

    for demo_event in build_demo_schedule_events(anchor):
        demo_start = parse_dt(demo_event["start"])
        if demo_start:
            day_key = demo_start.strftime("%m/%d")
            bucket = daily_load.setdefault(day_key, {"events": 0, "hours": 0.0})
            bucket["events"] += 1
            bucket["hours"] += demo_event["duration_hours"]
        expanded_events.append(demo_event)

    expanded_events.sort(key=lambda item: item["start"])
    upcoming = expanded_events[:12]
    type_counts: dict[str, int] = {}
    for item in expanded_events:
        key = item["event_type"]
        type_counts[key] = type_counts.get(key, 0) + 1
    daily_series = [
        {"label": key, "events": value["events"], "hours": round(value["hours"], 2)}
        for key, value in list(daily_load.items())[-10:]
    ]

    month_buckets: dict[str, dict] = {}
    for item in expanded_events:
        dt = parse_dt(item["start"])
        if not dt:
            continue
        bucket_key = dt.strftime("%Y-%m")
        bucket = month_buckets.setdefault(
            bucket_key,
            {"label": dt.strftime("%b %Y"), "events": 0, "hours": 0.0},
        )
        bucket["events"] += 1
        bucket["hours"] += item["duration_hours"]

    return {
        "upcoming": upcoming,
        "type_counts": type_counts,
        "total": len(expanded_events),
        "daily_series": daily_series,
        "expanded_events": expanded_events,
        "master_rows": master_rows,
        "month_series": [
            {"key": key, "label": value["label"], "events": value["events"], "hours": round(value["hours"], 2)}
            for key, value in sorted(month_buckets.items())
        ],
        "timeline_anchor": anchor.strftime("%Y-%m-%d"),
    }


def save_schedule_master_action(payload: dict) -> JsonResponse:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return JsonResponse({"ok": False, "message": "Rows payload is required."}, 400)
    fieldnames = ["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]
    cleaned_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cleaned_rows.append(
            {
                "Event Type": str(row.get("event_type", "")).strip(),
                "Start DateTime": str(row.get("start", "")).strip(),
                "End DateTime": str(row.get("end", "")).strip(),
                "Description": str(row.get("description", "")).strip(),
                "Recurrence": normalize_recurrence(row.get("recurrence", "")) or "none",
            }
        )
    write_csv_rows(TOWER_SCHEDULE, cleaned_rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Schedule master saved.", "bootstrap": build_bootstrap_payload().body})


def add_schedule_event_action(payload: dict) -> JsonResponse:
    event_type = str(payload.get("eventType", "")).strip()
    start = str(payload.get("start", "")).strip()
    end = str(payload.get("end", "")).strip()
    description = str(payload.get("description", "")).strip()
    recurrence = normalize_recurrence(payload.get("recurrence", "")) or "none"
    if not event_type or not start or not end:
        return JsonResponse({"ok": False, "message": "Event type, start, and end are required."}, 400)
    fieldnames = ["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]
    rows = read_csv_rows(TOWER_SCHEDULE)
    rows.append(
        {
            "Event Type": event_type,
            "Start DateTime": start,
            "End DateTime": end,
            "Description": description,
            "Recurrence": recurrence,
        }
    )
    write_csv_rows(TOWER_SCHEDULE, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Event added to schedule.", "bootstrap": build_bootstrap_payload().body})


def delete_schedule_event_action(payload: dict) -> JsonResponse:
    try:
        index = int(payload.get("index"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "Valid event index is required."}, 400)
    rows = read_csv_rows(TOWER_SCHEDULE)
    fieldnames = read_csv_fieldnames(TOWER_SCHEDULE) or ["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]
    if index < 0 or index >= len(rows):
        return JsonResponse({"ok": False, "message": "Event not found."}, 404)
    del rows[index]
    write_csv_rows(TOWER_SCHEDULE, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Event deleted.", "bootstrap": build_bootstrap_payload().body})


def summarize_part_orders() -> dict:
    rows = read_csv_rows(PART_ORDERS)
    status_counts: dict[str, int] = {}
    open_orders = []
    all_orders = []
    maintenance_open = 0
    approval_queue = []
    ready_to_order = []
    ordered_open = []
    received_pending_inventory = []
    maintenance_linked = []
    project_names = dedupe_strings([item.get(PROJECTS_COL, "") for item in read_csv_rows(PROJECTS_FIBER)])
    company_names = [row.get("Company", "") for row in read_csv_rows(PARTS_COMPANIES)]
    for index, row in enumerate(rows):
        status = (row.get("Status") or "Unknown").strip() or "Unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        project_name = row.get("Project Name", "")
        company = row.get("Company", "")
        maintenance_component = row.get("Maintenance Component", "")
        maintenance_task = row.get("Maintenance Task", "")
        details = (row.get("Details") or "").strip()
        inventory_synced = (row.get("Inventory Synced") or "").strip()
        received_state = (row.get("Received State") or "").strip()
        item = {
            "index": index,
            "status": status,
            "part_name": row.get("Part Name", ""),
            "serial_number": row.get("Serial Number", ""),
            "project": project_name,
            "details": details,
            "opened_by": row.get("Opened By", ""),
            "approval_requested_from": row.get("Approval Requested From", ""),
            "approved": row.get("Approved", ""),
            "approved_by": row.get("Approved By", ""),
            "approval_date": row.get("Approval Date", ""),
            "received_date": row.get("Received Date", ""),
            "received_state": received_state,
            "ordered_by": row.get("Ordered By", ""),
            "date_ordered": row.get("Date Ordered", ""),
            "company": company,
            "inventory_synced": inventory_synced,
            "maintenance_component": maintenance_component,
            "maintenance_task": maintenance_task,
            "maintenance_task_id": row.get("Maintenance Task ID", ""),
            "wait_id": row.get("Wait ID", ""),
            "origin": "Maintenance" if maintenance_component or maintenance_task or str(project_name).strip().lower() == "maintenance" else "General",
        }
        all_orders.append(item)
        if status not in {"Received", "Closed"}:
            open_orders.append(item)
        if str(project_name).strip().lower() == "maintenance" and status not in {"Received", "Closed"}:
            maintenance_open += 1
        if company:
            company_names.append(company)
        if status == "Wait for Approval":
            approval_queue.append(item)
        if status == "Approved":
            ready_to_order.append(item)
        if status == "Ordered":
            ordered_open.append(item)
        if status == "Received" and (inventory_synced != "Yes" or not received_state):
            received_pending_inventory.append(item)
        if maintenance_component or maintenance_task or str(project_name).strip().lower() == "maintenance":
            maintenance_linked.append(item)
    sorted_status_counts = {key: status_counts.get(key, 0) for key in PART_STATUS_ORDER if key in status_counts}
    for key, value in status_counts.items():
        if key not in sorted_status_counts:
            sorted_status_counts[key] = value
    return {
        "status_counts": sorted_status_counts,
        "all_orders": all_orders,
        "open_orders": open_orders[:8],
        "maintenance_open": maintenance_open,
        "total": len(rows),
        "status_series": [{"label": key, "value": value} for key, value in sorted_status_counts.items()],
        "queues": {
            "approval": approval_queue[:8],
            "approved": ready_to_order[:8],
            "ordered": ordered_open[:8],
            "received_pending": received_pending_inventory[:8],
            "maintenance_linked": maintenance_linked[:8],
        },
        "queue_counts": {
            "approval": len(approval_queue),
            "approved": len(ready_to_order),
            "ordered": len(ordered_open),
            "received_pending": len(received_pending_inventory),
            "maintenance_linked": len(maintenance_linked),
        },
        "project_names": dedupe_strings(project_names + [item["project"] for item in all_orders]),
        "company_names": dedupe_strings(company_names),
        "status_order": PART_STATUS_ORDER,
    }


def summarize_inventory() -> dict:
    rows = read_csv_rows(PARTS_INVENTORY)
    low_stock = []
    component_pressure: dict[str, int] = {}
    mounted_rows = []
    for row in rows:
        quantity = to_float(row.get("Quantity"))
        min_level = to_float(row.get("Min Level"))
        location = row.get("Location", "")
        if str(location).strip().lower() == "mounted":
            mounted_rows.append(
                {
                    "part_name": row.get("Part Name", ""),
                    "serial_number": row.get("Serial Number", ""),
                    "quantity": quantity,
                    "component": row.get("Component", ""),
                    "location": location,
                }
            )
        if quantity <= min_level:
            component = row.get("Component", "") or "Unknown"
            component_pressure[component] = component_pressure.get(component, 0) + 1
            low_stock.append(
                {
                    "part_name": row.get("Part Name", ""),
                    "component": row.get("Component", ""),
                    "quantity": quantity,
                    "min_level": min_level,
                    "location": row.get("Location", ""),
                }
            )
    low_stock.sort(key=lambda item: (item["quantity"], item["part_name"]))
    pressure_series = [
        {"label": key, "value": value}
        for key, value in sorted(component_pressure.items(), key=lambda item: item[1], reverse=True)[:6]
    ]
    return {
        "low_stock": low_stock[:8],
        "low_stock_total": len(low_stock),
        "tracked_parts": len(rows),
        "pressure_series": pressure_series,
        "mounted_rows": mounted_rows[:12],
        "inventory_rows": [
            {
                "part_name": row.get("Part Name", ""),
                "item_type": row.get("Item Type", ""),
                "component": row.get("Component", ""),
                "supplier": row.get("Supplier", ""),
                "serial_number": row.get("Serial Number", ""),
                "location": row.get("Location", ""),
                "location_serial": row.get("Location Serial", ""),
                "quantity": to_float(row.get("Quantity")),
                "min_level": to_float(row.get("Min Level")),
                "notes": row.get("Notes", ""),
            }
            for row in rows
        ],
        "location_names": dedupe_strings([row.get("Location Name", "") for row in read_csv_rows(PARTS_LOCATIONS)]),
    }


def get_parts_manual_roots() -> list[Path]:
    return [root for root in [MANUALS_DIR, EXTERNAL_MANUALS_DIR] if root.exists() and root.is_dir()]


def pick_parts_manuals_dir() -> Path | None:
    roots = get_parts_manual_roots()
    if not roots:
        return None
    ranked = sorted(
        roots,
        key=lambda root: (len(list(root.glob("*.pdf"))), int(root.stat().st_mtime)),
        reverse=True,
    )
    return ranked[0]


def empty_parts_manual_index(message: str = "") -> dict[str, object]:
    return {
        "ok": True,
        "manuals": [],
        "rows": [],
        "totals": {"manual_count": 0, "row_count": 0},
        "message": message,
    }


def build_parts_manual_signature(root: Path | None) -> tuple[object, ...]:
    if root is None:
        return ("missing",)
    entries: list[tuple[str, int, int]] = []
    for pdf_path in sorted(root.glob("*.pdf")):
        try:
            stats = pdf_path.stat()
        except OSError:
            continue
        entries.append((pdf_path.name, int(stats.st_mtime), int(stats.st_size)))
    return (str(root), *entries)


def get_parts_manual_index() -> dict[str, object]:
    manuals_root = pick_parts_manuals_dir()
    signature = build_parts_manual_signature(manuals_root)
    cached_signature = _PARTS_MANUAL_INDEX_CACHE.get("signature")
    cached_payload = _PARTS_MANUAL_INDEX_CACHE.get("payload")
    if cached_signature == signature and isinstance(cached_payload, dict):
        return cached_payload
    if manuals_root is None:
        payload = empty_parts_manual_index("No manuals directory found.")
    elif not MANUAL_INDEX_SCRIPT.exists():
        payload = empty_parts_manual_index("Manual index script is missing.")
    else:
        helper_python = resolve_helper_python(("pypdf",))
        if helper_python is None:
            payload = empty_parts_manual_index("No compatible PDF helper runtime with pypdf was found.")
        else:
            try:
                result = subprocess.run(
                    [str(helper_python), str(MANUAL_INDEX_SCRIPT), str(manuals_root)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                payload = json.loads(result.stdout or "{}")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
                payload = empty_parts_manual_index("Manual index build failed.")
            else:
                payload["message"] = payload.get("message", "")
                payload["source_dir"] = str(manuals_root)
                payload["runtime_python"] = str(helper_python)
    if isinstance(payload, dict):
        payload["render_mode"] = manual_page_render_mode()
    _PARTS_MANUAL_INDEX_CACHE["signature"] = signature
    _PARTS_MANUAL_INDEX_CACHE["payload"] = payload
    return payload


def build_parts_manual_index_payload() -> JsonResponse:
    return JsonResponse(get_parts_manual_index())


def summarize_parts_manual_lookup() -> dict[str, object]:
    manuals_root = pick_parts_manuals_dir()
    cached_payload = _PARTS_MANUAL_INDEX_CACHE.get("payload")
    totals = cached_payload.get("totals") if isinstance(cached_payload, dict) else {}
    helper_python = resolve_helper_python(("pypdf",))
    manual_count = len(list(manuals_root.glob("*.pdf"))) if manuals_root else 0
    return {
        "manual_count": manual_count,
        "row_count": int((totals or {}).get("row_count", 0)),
        "message": str((cached_payload or {}).get("message", "")) if isinstance(cached_payload, dict) else "",
        "render_mode": manual_page_render_mode(),
        "helper_python": str(helper_python) if helper_python else "",
    }


def _manual_page_render_artifacts(pdf_path: Path, page_number: int) -> tuple[int, str, Path]:
    safe_page = max(1, int(page_number or 1))
    MANUAL_PAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    render_signature = hashlib.sha1(
        "::".join(
            [
                str(pdf_path.resolve()),
                str(pdf_path.stat().st_mtime_ns),
                str(safe_page),
                str(MANUAL_PAGE_RENDER_SCRIPT.stat().st_mtime_ns if MANUAL_PAGE_RENDER_SCRIPT.exists() else 0),
            ]
        ).encode("utf-8")
    ).hexdigest()
    output_path = MANUAL_PAGE_CACHE_DIR / f"{render_signature}.png"
    return safe_page, render_signature, output_path


def _manual_page_renderer_env() -> dict[str, str]:
    MANUAL_PAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    clang_cache = MANUAL_PAGE_CACHE_DIR / "clang_module_cache"
    swift_cache = MANUAL_PAGE_CACHE_DIR / "swift_module_cache"
    clang_cache.mkdir(parents=True, exist_ok=True)
    swift_cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CLANG_MODULE_CACHE_PATH"] = str(clang_cache)
    env["SWIFT_MODULE_CACHE_PATH"] = str(swift_cache)
    xcode_developer_dir = Path("/Applications/Xcode.app/Contents/Developer")
    if xcode_developer_dir.exists():
        env["DEVELOPER_DIR"] = str(xcode_developer_dir)
    return env


def _ensure_manual_page_renderer_binary(env: dict[str, str]) -> Path:
    if not MANUAL_PAGE_RENDER_SCRIPT.exists():
        raise FileNotFoundError("Manual page render script is missing.")
    renderer_binary = MANUAL_PAGE_CACHE_DIR / "render_manual_page"
    renderer_source_mtime = MANUAL_PAGE_RENDER_SCRIPT.stat().st_mtime_ns
    binary_needs_rebuild = (
        not renderer_binary.exists()
        or renderer_binary.stat().st_mtime_ns < renderer_source_mtime
    )
    if binary_needs_rebuild:
        subprocess.run(
            ["xcrun", "swiftc", "-O", str(MANUAL_PAGE_RENDER_SCRIPT), "-o", str(renderer_binary)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
    return renderer_binary


def _render_manual_page_image_once(pdf_path: Path, safe_page: int, output_path: Path) -> Path:
    env = _manual_page_renderer_env()
    renderer_binary = _ensure_manual_page_renderer_binary(env)

    result = subprocess.run(
        [str(renderer_binary), str(pdf_path), str(safe_page), str(output_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    rendered_path = Path((result.stdout or "").strip() or output_path)
    if rendered_path.exists() and rendered_path.is_file():
        return rendered_path
    raise FileNotFoundError("Manual page image render failed.")


def render_manual_page_image(pdf_path: Path, page_number: int) -> Path:
    if manual_page_render_mode() != "image":
        raise RuntimeError("Manual page image rendering is not enabled on this platform.")
    safe_page, render_signature, output_path = _manual_page_render_artifacts(pdf_path, page_number)
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    owns_render = False
    with _MANUAL_PAGE_RENDER_LOCK:
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path
        render_event = _MANUAL_PAGE_RENDER_EVENTS.get(render_signature)
        if render_event is None:
            render_event = threading.Event()
            _MANUAL_PAGE_RENDER_EVENTS[render_signature] = render_event
            owns_render = True
    if owns_render:
        try:
            return _render_manual_page_image_once(pdf_path, safe_page, output_path)
        finally:
            with _MANUAL_PAGE_RENDER_LOCK:
                _MANUAL_PAGE_RENDER_EVENTS.pop(render_signature, None)
                render_event.set()
    render_event.wait(timeout=125)
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    return _render_manual_page_image_once(pdf_path, safe_page, output_path)


def export_manual_page_pdf(pdf_path: Path, page_number: int) -> Path:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Manual PDF not found: {pdf_path.name}")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Manual PDF path is not a file: {pdf_path.name}")
    helper_python = resolve_helper_python(("pypdf",))
    if helper_python is None:
        raise RuntimeError("No compatible PDF helper runtime with pypdf was found.")
    safe_page = max(1, int(page_number or 1))
    output_dir = MAINTENANCE_MANUAL_PAGES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slugify(pdf_path.stem) or 'manual'}_page_{safe_page}.pdf"
    export_script = (
        "from pathlib import Path\n"
        "from pypdf import PdfReader, PdfWriter\n"
        "import sys\n"
        "src = Path(sys.argv[1])\n"
        "page_number = max(1, int(sys.argv[2]))\n"
        "dest = Path(sys.argv[3])\n"
        "reader = PdfReader(str(src))\n"
        "if page_number > len(reader.pages):\n"
        "    raise SystemExit('Page out of range')\n"
        "writer = PdfWriter()\n"
        "writer.add_page(reader.pages[page_number - 1])\n"
        "dest.parent.mkdir(parents=True, exist_ok=True)\n"
        "with dest.open('wb') as handle:\n"
        "    writer.write(handle)\n"
    )
    try:
        subprocess.run(
            [str(helper_python), "-c", export_script, str(pdf_path), str(safe_page), str(output_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or "Unknown PDF export error"
        raise RuntimeError(f"Manual page PDF export failed: {detail}") from exc
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise FileNotFoundError("Manual page PDF export failed.")
    return output_path


def development_media_placeholder_svg(title: str, detail: str = "") -> bytes:
    safe_title = escape_html(str(title or "").strip() or "Preview unavailable")
    safe_detail = escape_html(str(detail or "").strip())
    body = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760">
  <defs>
    <linearGradient id="bg" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stop-color="#0d1b28"/>
      <stop offset="100%" stop-color="#08131d"/>
    </linearGradient>
    <radialGradient id="glow" cx="78%" cy="20%" r="48%">
      <stop offset="0%" stop-color="#72ffe8" stop-opacity="0.14"/>
      <stop offset="100%" stop-color="#72ffe8" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1200" height="760" fill="url(#bg)"/>
  <rect width="1200" height="760" fill="url(#glow)"/>
  <rect x="48" y="48" width="1104" height="664" rx="24" fill="none" stroke="#1f4f5a" stroke-width="2"/>
  <rect x="88" y="96" width="180" height="56" rx="28" fill="#163645" stroke="#2a6c76" stroke-width="1.5"/>
  <text x="178" y="131" text-anchor="middle" font-family="Orbitron, Arial, sans-serif" font-size="24" fill="#dff9fb" letter-spacing="3">PREVIEW</text>
  <text x="88" y="252" font-family="Orbitron, Arial, sans-serif" font-size="54" fill="#ecf8fa" letter-spacing="2">{safe_title}</text>
  <text x="88" y="320" font-family="Arial, sans-serif" font-size="28" fill="#9bc8cf">{safe_detail}</text>
</svg>"""
    return body.encode("utf-8")


def _prefetch_manual_page_image_task(pdf_path: Path, page_number: int, render_signature: str, priority: bool = False) -> None:
    try:
        render_manual_page_image(pdf_path, page_number)
    except Exception:
        return
    finally:
        with _MANUAL_PAGE_PREFETCH_LOCK:
            if priority:
                _MANUAL_PAGE_PRIORITY_PREFETCH_QUEUED.discard(render_signature)
            else:
                _MANUAL_PAGE_PREFETCH_QUEUED.discard(render_signature)


def schedule_manual_page_prefetch(pdf_path: Path, page_numbers: list[int], priority: bool = False) -> int:
    if manual_page_render_mode() != "image":
        return 0
    scheduled = 0
    seen_pages: set[int] = set()
    for page_number in page_numbers:
        safe_page, render_signature, output_path = _manual_page_render_artifacts(pdf_path, page_number)
        if safe_page in seen_pages:
            continue
        seen_pages.add(safe_page)
        if output_path.exists() and output_path.stat().st_size > 0:
            continue
        with _MANUAL_PAGE_PREFETCH_LOCK:
            queued_signatures = _MANUAL_PAGE_PRIORITY_PREFETCH_QUEUED if priority else _MANUAL_PAGE_PREFETCH_QUEUED
            if render_signature in queued_signatures:
                continue
            queued_signatures.add(render_signature)
        executor = _MANUAL_PAGE_PRIORITY_PREFETCH_EXECUTOR if priority else _MANUAL_PAGE_PREFETCH_EXECUTOR
        executor.submit(_prefetch_manual_page_image_task, pdf_path, safe_page, render_signature, priority)
        scheduled += 1
    return scheduled


FAULT_LOG_FIELDS = [
    "fault_id",
    "fault_ts",
    "fault_component",
    "fault_title",
    "fault_description",
    "fault_severity",
    "fault_actor",
    "fault_source_file",
    "fault_related_draw",
]

FAULT_ACTION_FIELDS = [
    "fault_action_id",
    "fault_id",
    "action_ts",
    "action_type",
    "actor",
    "note",
    "fix_summary",
]


def parse_fault_timestamp(value: object) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.min
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def maintenance_fault_latest_state_map(fault_action_rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    sorted_rows = sorted(
        fault_action_rows or [],
        key=lambda row: (
            str(row.get("fault_id", "")).strip(),
            parse_fault_timestamp(row.get("action_ts", "")),
            str(row.get("fault_action_id", "")).strip(),
        ),
    )
    for row in sorted_rows:
        fault_id = str(row.get("fault_id", "")).strip()
        if not fault_id:
            continue
        action_type = str(row.get("action_type", "")).strip().lower()
        latest[fault_id] = {
            "is_closed": action_type == "close",
            "last_ts": str(row.get("action_ts", "")).strip(),
            "last_note": str(row.get("note", "")).strip(),
            "last_fix": str(row.get("fix_summary", "")).strip(),
            "last_type": action_type,
            "last_actor": str(row.get("actor", "")).strip(),
        }
    return latest


def build_maintenance_fault_entry(row: dict[str, str], state_map: dict[str, dict[str, object]]) -> dict[str, object] | None:
    fault_id = str(row.get("fault_id", "")).strip()
    if not fault_id:
        return None
    state = state_map.get(fault_id, {})
    return {
        "fault_id": fault_id,
        "ts": str(row.get("fault_ts", "")).strip(),
        "component": str(row.get("fault_component", "")).strip() or "Unknown component",
        "title": str(row.get("fault_title", "")).strip() or "Fault",
        "description": str(row.get("fault_description", "")).strip(),
        "severity": str(row.get("fault_severity", "")).strip() or "medium",
        "actor": str(row.get("fault_actor", "")).strip(),
        "source_file": str(row.get("fault_source_file", "")).strip(),
        "related_draw": str(row.get("fault_related_draw", "")).strip(),
        "is_closed": bool(state.get("is_closed", False)),
        "last_action_type": str(state.get("last_type", "")).strip(),
        "last_action_ts": str(state.get("last_ts", "")).strip(),
        "last_action_actor": str(state.get("last_actor", "")).strip(),
        "last_note": str(state.get("last_note", "")).strip(),
        "last_fix": str(state.get("last_fix", "")).strip(),
    }


def summarize_maintenance_rebuild() -> dict:
    runtime_context = get_maintenance_runtime_context()
    tasks = read_maintenance_tracker_rows()
    test_preset_library = load_maintenance_test_preset_library()
    state_rows = read_csv_rows(MAINTENANCE_STATE)
    action_rows = read_csv_rows(MAINTENANCE_ACTIONS)
    wait_rows = [row for row in read_csv_rows(MAINTENANCE_WAITS) if not str(row.get("resolved_ts", "")).strip()]
    part_orders = read_csv_rows(PART_ORDERS)
    inventory_rows = read_csv_rows(PARTS_INVENTORY)
    schedule = summarize_schedule()
    work_package_rows = read_csv_rows(MAINTENANCE_WORK_PACKAGES)
    fault_rows = read_csv_rows(FAULTS_LOG)
    fault_action_rows = read_csv_rows(FAULTS_ACTIONS_LOG)
    execute_status_rank = {
        "SCHEDULED": 0,
        "IN_PROGRESS": 1,
        "PREP_DONE": 2,
        "PREP_READY": 3,
        "WAIT FOR PART": 4,
        "BLOCKED_PARTS": 5,
    }
    due_lookup = build_maintenance_due_lookup(runtime_context)

    def maintenance_signature(task_id: str, component: str, task: str) -> str:
        raw_task_id = str(task_id or "").strip()
        normalized_task_id = raw_task_id
        if raw_task_id:
            embedded_task_id = re.search(r"([A-Za-z0-9]+-MNT-\d+)", raw_task_id, re.IGNORECASE)
            if embedded_task_id:
                normalized_task_id = embedded_task_id.group(1)
            elif raw_task_id.lower().startswith("demo-"):
                normalized_task_id = re.sub(r"^demo-[^-]+-", "", raw_task_id, flags=re.IGNORECASE)
                normalized_task_id = re.sub(r"-\d+$", "", normalized_task_id)
        base = str(normalized_task_id or "").strip().lower() or f"{str(component or '').strip().lower()}::{str(task or '').strip().lower()}"
        return base

    state_by_task = {str(row.get("task_id", "")).strip(): row for row in state_rows if str(row.get("task_id", "")).strip()}
    state_by_signature = {
        maintenance_signature(row.get("task_id", ""), row.get("component", ""), row.get("task", "")): row
        for row in state_rows
    }
    wait_by_task = {str(row.get("maintenance_task_id", "")).strip(): row for row in wait_rows if str(row.get("maintenance_task_id", "")).strip()}
    wait_by_signature = {
        maintenance_signature(row.get("maintenance_task_id", ""), row.get("maintenance_component", ""), row.get("maintenance_task", "")): row
        for row in wait_rows
    }
    work_package_by_task = {str(row.get("Task_ID", "")).strip(): row for row in work_package_rows if str(row.get("Task_ID", "")).strip()}
    work_package_by_signature = {
        maintenance_signature(row.get("Task_ID", ""), row.get("Component", ""), row.get("Task", "")): row
        for row in work_package_rows
    }
    linked_orders_by_task: dict[str, list[dict[str, str]]] = {}
    for row in part_orders:
        task_id = str(row.get("Maintenance Task ID", "")).strip()
        if not task_id:
            continue
        linked_orders_by_task.setdefault(task_id, []).append(row)

    stock_names = {str(row.get("Part Name", "")).strip().lower() for row in inventory_rows if to_float(row.get("Quantity")) > 0 and str(row.get("Location", "")).strip().lower() != "mounted"}
    completed_ids = [str(row.get("maintenance_task_id", "")).strip() for row in action_rows if str(row.get("maintenance_task_id", "")).strip()]
    recent_actions = [
        {
            "task_id": str(row.get("maintenance_task_id", "")).strip(),
            "component": row.get("maintenance_component", ""),
            "task": row.get("maintenance_task", ""),
            "done_date": row.get("maintenance_done_date", ""),
            "note": row.get("maintenance_note", ""),
        }
        for row in action_rows[-10:]
    ][::-1]
    scheduled_windows_by_task: dict[str, list[dict[str, str]]] = {}
    task_id_pattern = re.compile(r"Task ID:\s*([A-Za-z0-9-]+)", re.IGNORECASE)
    for schedule_row in schedule.get("master_rows", []):
        if "maintenance" not in str(schedule_row.get("event_type", "")).strip().lower():
            continue
        description = str(schedule_row.get("description", "")).strip()
        task_id_match = task_id_pattern.search(description)
        if not task_id_match:
            continue
        scheduled_task_id = task_id_match.group(1).strip()
        if not scheduled_task_id:
            continue
        scheduled_windows_by_task.setdefault(scheduled_task_id, []).append(
            {
                "start": str(schedule_row.get("start", "")).strip(),
                "end": str(schedule_row.get("end", "")).strip(),
                "label": str(schedule_row.get("start", "")).strip()[:16].replace("T", " "),
                "recurrence": normalize_recurrence(schedule_row.get("recurrence", "")) or "none",
            }
        )
    for windows in scheduled_windows_by_task.values():
        windows.sort(key=lambda item: (item.get("start", ""), item.get("end", ""), item.get("label", "")))

    task_rows = []
    prep_queue = []
    execute_queue = []
    execute_plan_queue = []
    blocked_tracker = []
    seen_task_signatures: set[str] = set()
    for row in tasks:
        task_id = str(row.get("Task_ID", "")).strip()
        task_signature = maintenance_signature(task_id, row.get("Component", ""), row.get("Task", ""))
        if task_signature in seen_task_signatures:
            continue
        seen_task_signatures.add(task_signature)
        helper_key = task_id or f"{str(row.get('Component', '')).strip().lower()}::{str(row.get('Task', '')).strip().lower()}"
        due_meta = due_lookup.get(helper_key, {})
        required_parts_text = first_task_value(row, "Mandatory_Parts", "Required_Parts")
        required_tools_text = first_task_value(row, "Required_Tools")
        conditional_parts_text = first_task_value(row, "Conditional_Parts")
        required_parts = split_required_parts(required_parts_text)
        required_tools = split_required_parts(required_tools_text)
        mandatory_parts = split_required_parts(first_task_value(row, "Mandatory_Parts"))
        conditional_parts = split_required_parts(conditional_parts_text)
        missing_parts = [part for part in required_parts if part.lower() not in stock_names]
        work_package_row = work_package_by_task.get(task_id) or work_package_by_signature.get(task_signature) or {}
        linked_orders = linked_orders_by_task.get(task_id, [])
        open_linked = [
            item for item in linked_orders
            if str(item.get("Status", "")).strip() in {"Opened", "Wait for Approval", "Approved", "Ordered"}
        ]
        received_waiting_sync = [
            item for item in linked_orders
            if str(item.get("Status", "")).strip() == "Received"
            and str(item.get("Inventory Synced", "")).strip().lower() != "yes"
        ]
        linked_ready = [
            item for item in linked_orders
            if str(item.get("Status", "")).strip() in {"Received", "Archived"}
            and str(item.get("Inventory Synced", "")).strip().lower() == "yes"
        ]
        ordered_part_names = {
            str(item.get("Part Name", "")).strip().lower()
            for item in linked_orders
            if str(item.get("Status", "")).strip() in {"Opened", "Wait for Approval", "Approved", "Ordered", "Received"}
        }
        missing_parts_unordered = [part for part in missing_parts if part.lower() not in ordered_part_names]
        missing_parts_ordered = [part for part in missing_parts if part.lower() in ordered_part_names]
        parts_blocker_cleared = not missing_parts and not open_linked and not received_waiting_sync
        current_state = str((state_by_task.get(task_id) or state_by_signature.get(task_signature) or {}).get("state", "")).strip() or ""
        if current_state == "BLOCKED_PARTS":
            current_state = "PREP_READY"
        flow_state = "Ready for preparation"
        if received_waiting_sync:
            flow_state = "Received, sync into inventory"
        elif open_linked:
            flow_state = "Parts ordered, waiting for arrival"
        elif missing_parts:
            flow_state = "Missing parts, no linked order yet"
        if current_state not in {"PREP_DONE", "SCHEDULED", "IN_PROGRESS", "DONE_NOW"}:
            if (
                task_id in wait_by_task
                or task_signature in wait_by_signature
                or received_waiting_sync
                or open_linked
            ):
                current_state = "WAIT FOR PART"
        if current_state not in {"SCHEDULED", "IN_PROGRESS", "DONE_NOW"} and parts_blocker_cleared:
            if linked_ready:
                current_state = "PREP_DONE"
                flow_state = "Ready to execute after inventory sync"
            elif current_state == "WAIT FOR PART":
                current_state = "PREP_READY"
                flow_state = "Parts ready, finish prep"
            elif current_state in {"PREP_READY", ""}:
                current_state = "PREP_DONE"
                flow_state = "Ready to execute"
        if not current_state:
            current_state = "PREP_READY"
        if current_state == "PREP_DONE" and flow_state != "Ready to execute after inventory sync":
            flow_state = "Ready to execute by prep override"
        scheduled_windows = scheduled_windows_by_task.get(task_id, [])
        plan_forwarded = bool(scheduled_windows) or current_state in {"SCHEDULED", "PREP_DONE"}
        item = {
            "task_id": task_id,
            "component": row.get("Component", ""),
            "task": row.get("Task", ""),
            "task_group": row.get("Task_Group", ""),
            "task_groups": first_task_value(row, "Task_Groups", "Task_Group"),
            "owner": first_task_value(row, "Owner"),
            "tracking_mode": row.get("Tracking_Mode", ""),
            "hours_source": row.get("Hours_Source", "") or due_meta.get("hours_source", ""),
            "interval_type": first_task_value(row, "Interval Type"),
            "interval_value": first_task_value(row, "Interval Value"),
            "interval_unit": first_task_value(row, "Interval Unit"),
            "planning_window_months": first_task_value(row, "Planning_Window_Months"),
            "due_threshold_days": first_task_value(row, "Due Threshold (days)"),
            "trigger_context": first_task_value(row, "Trigger Context"),
            "trigger_modes": first_task_value(row, "Trigger_Modes"),
            "trigger_hours_source": first_task_value(row, "Trigger_Hours_Source"),
            "trigger_hours_interval": first_task_value(row, "Trigger_Hours_Interval"),
            "trigger_draws_interval": first_task_value(row, "Trigger_Draws_Interval"),
            "trigger_calendar_value": first_task_value(row, "Trigger_Calendar_Value"),
            "trigger_calendar_unit": first_task_value(row, "Trigger_Calendar_Unit"),
            "calendar_rule": first_task_value(row, "Calendar Rule"),
            "required_parts": required_parts,
            "required_parts_text": required_parts_text,
            "required_tools": required_tools,
            "required_tools_text": required_tools_text,
            "mandatory_parts": mandatory_parts,
            "mandatory_parts_text": first_task_value(row, "Mandatory_Parts", "Required_Parts"),
            "conditional_parts": conditional_parts,
            "conditional_parts_text": conditional_parts_text,
            "preparation_lead_days": first_task_value(row, "Preparation_Lead_Days"),
            "parts_check_lead_days": first_task_value(row, "Parts_Check_Lead_Days"),
            "auto_order_mandatory_parts": first_task_value(row, "Auto_Order_Mandatory_Parts"),
            "missing_parts": missing_parts,
            "missing_parts_unordered": missing_parts_unordered,
            "missing_parts_ordered": missing_parts_ordered,
            "status": current_state,
            "timing_status": str(due_meta.get("timing_status", "")),
            "flow_state": flow_state,
            "source_file": row.get("Source_File", ""),
            "last_done_date": row.get("Last_Done_Date", ""),
            "last_done_hours": row.get("Last_Done_Hours", ""),
            "last_done_draw": row.get("Last_Done_Draw", ""),
            "next_due_date": str(due_meta.get("next_due_date", "")),
            "next_due_hours": due_meta.get("next_due_hours", ""),
            "next_due_draw": due_meta.get("next_due_draw", ""),
            "est_duration_min": row.get("Est_Duration_Min", ""),
            "procedure_summary": row.get("Procedure Summary", ""),
            "safety_notes": row.get("Safety/Notes", ""),
            "manual_name": row.get("Manual_Name", ""),
            "manual_link": row.get("Document", ""),
            "manual_page": row.get("Page", ""),
            "procedure_summary_text": first_task_value(row, "Procedure Summary"),
            "safety_notes_text": first_task_value(row, "Safety/Notes"),
            "test_preset": first_task_value(row, "Test_Preset"),
            "test_fields": first_task_value(row, "Test_Fields"),
            "test_thresholds": first_task_value(row, "Test_Thresholds"),
            "test_condition": first_task_value(row, "Test_Condition"),
            "test_action": first_task_value(row, "Test_Action"),
            "wait_note": str(
                (
                    wait_by_task.get(task_id)
                    or wait_by_signature.get(task_signature)
                    or {}
                ).get("reason", "")
                or (
                    wait_by_task.get(task_id)
                    or wait_by_signature.get(task_signature)
                    or {}
                ).get("note", "")
            ).strip(),
            "linked_open_count": len(open_linked),
            "linked_received_waiting_sync": len(received_waiting_sync),
            "linked_ready_count": len(linked_ready),
            "work_package": {
                "preparation_checklist": str(work_package_row.get("Preparation_Checklist", "")).strip(),
                "safety_protocol": str(work_package_row.get("Safety_Protocol", "")).strip(),
                "safety_fall_risk": str(work_package_row.get("Safety_Fall_Risk", "")).strip(),
                "safety_tnm_presence": str(work_package_row.get("Safety_TnM_Presence", "")).strip(),
                "procedure_steps": str(work_package_row.get("Procedure_Steps", "")).strip(),
                "procedure_photos": str(work_package_row.get("Procedure_Photos", "")).strip(),
                "sanity_checklist": str(work_package_row.get("Sanity_Checklist", "")).strip(),
                "sanity_results": str(work_package_row.get("Sanity_Results", "")).strip(),
                "supplier_name": str(work_package_row.get("Supplier_Name", "")).strip(),
                "supplier_details": str(work_package_row.get("Supplier_Details", "")).strip(),
                "draw_stop_plan": str(work_package_row.get("Draw_Stop_Plan", "")).strip(),
                "est_stop_min": str(work_package_row.get("Est_Stop_Min", "")).strip(),
                "completion_criteria": str(work_package_row.get("Completion_Criteria", "")).strip(),
                "last_updated": str(work_package_row.get("Last_Updated", "")).strip(),
                "updated_by": str(work_package_row.get("Updated_By", "")).strip(),
            },
            "linked_orders": [
                {
                    "part_name": order.get("Part Name", ""),
                    "status": order.get("Status", ""),
                    "details": order.get("Details", ""),
                }
                for order in linked_orders[:6]
            ],
            "scheduled_windows": scheduled_windows[:3],
            "scheduled_window_labels": [window.get("label", "") for window in scheduled_windows[:3] if window.get("label")],
            "scheduled_window_count": len(scheduled_windows),
            "plan_forwarded": plan_forwarded,
            "prep_done_override": current_state == "PREP_DONE",
        }
        task_rows.append(item)
        if current_state in {"PREP_READY", "PREP_DONE", "WAIT FOR PART"}:
            prep_queue.append(item)
        # Execute should show only tasks that were actually handed forward
        # from plan, are live now, or are blocked after being handed off.
        if current_state in {"SCHEDULED", "IN_PROGRESS"}:
            execute_queue.append(item)
        elif current_state == "WAIT FOR PART" and plan_forwarded:
            execute_queue.append(item)
        if current_state in {"SCHEDULED", "IN_PROGRESS"} and (plan_forwarded or current_state == "SCHEDULED"):
            execute_plan_queue.append(item)
        if current_state != "PREP_DONE" and (flow_state != "Ready for preparation" or current_state == "WAIT FOR PART"):
            blocked_tracker.append(item)

    task_rows.sort(key=lambda item: (item["status"], item["component"], item["task"]))
    prep_queue.sort(key=lambda item: (item["status"], item["component"], item["task"]))
    execute_queue.sort(key=lambda item: (execute_status_rank.get(str(item["status"]).upper(), 99), item["component"], item["task"]))
    execute_plan_queue.sort(key=lambda item: (execute_status_rank.get(str(item["status"]).upper(), 99), item["component"], item["task"]))
    blocked_tracker.sort(key=lambda item: (item["status"], item["component"], item["task"]))
    maintenance_events = [
        item for item in schedule.get("upcoming", [])
        if "maintenance" in str(item.get("event_type", "")).lower()
    ]
    prep_events = [
        item for item in schedule.get("upcoming", [])
        if any(token in str(item.get("event_type", "")).lower() for token in ["maintenance preparation", "maintenance parts check"])
    ]
    smart_todo = (blocked_tracker[:4] + [item for item in prep_queue if item["task_id"] not in {row["task_id"] for row in blocked_tracker[:4]}][:4])[:8]
    fault_state_map = maintenance_fault_latest_state_map(fault_action_rows)
    fault_entries = [
        item
        for item in (build_maintenance_fault_entry(row, fault_state_map) for row in fault_rows)
        if item
    ]
    fault_entries.sort(
        key=lambda item: (
            parse_fault_timestamp(item.get("ts", "")),
            str(item.get("fault_id", "")).strip(),
        ),
        reverse=True,
    )
    faults_open = [item for item in fault_entries if not item["is_closed"]]
    faults_closed = [item for item in fault_entries if item["is_closed"]]
    faults_recent = fault_entries[:16]
    component_fault_counts: dict[str, int] = {}
    for row in faults_open:
        component = str(row.get("component", "")).strip() or "Unknown"
        component_fault_counts[component] = component_fault_counts.get(component, 0) + 1
    runtime = get_maintenance_runtime()

    return {
        "metrics": [
            {"label": "Tasks", "value": len(task_rows)},
            {"label": "Prep Queue", "value": len(prep_queue)},
            {"label": "Wait For Part", "value": len([item for item in task_rows if item["status"] == "WAIT FOR PART"])},
            {"label": "Recent Actions", "value": len(action_rows)},
        ],
        "tasks": task_rows,
        "prep_queue": prep_queue,
        "execute_queue": execute_queue,
        "execute_plan_queue": execute_plan_queue,
        "blocked_tracker": blocked_tracker,
        "recent_actions": recent_actions,
        "completed_ids": completed_ids[-12:],
        "maintenance_events": maintenance_events[:8],
        "prep_events": prep_events[:8],
        "smart_todo": smart_todo,
        "faults_open": faults_open[:24],
        "faults_closed": faults_closed[:24],
        "fault_open_total": len(faults_open),
        "fault_open_critical_total": len(
            [item for item in faults_open if str(item.get("severity", "")).strip().lower() == "critical"]
        ),
        "faults_recent": faults_recent,
        "fault_actions_total": len(fault_action_rows),
        "timeline_runtime": runtime,
        "test_preset_options": sorted(test_preset_library.keys()),
        "tool_options": dedupe_strings(
            [
                str(row.get("Part Name", "")).strip()
                for row in inventory_rows
                if str(row.get("Part Name", "")).strip()
                and (
                    str(row.get("Item Type", "")).strip().lower() == "tool"
                    or is_tool_like_part_name(str(row.get("Part Name", "")).strip())
                )
            ]
            + [tool for item in task_rows for tool in item.get("required_tools", [])]
        ),
    }


def save_maintenance_fault_action(payload: dict) -> JsonResponse:
    action = str(payload.get("action", "")).strip().lower()
    actor = str(payload.get("actor", "")).strip() or "rebuild"
    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fault_rows = read_csv_rows(FAULTS_LOG)
    fault_fieldnames = read_csv_fieldnames(FAULTS_LOG) or list(FAULT_LOG_FIELDS)
    fault_action_rows = read_csv_rows(FAULTS_ACTIONS_LOG)
    fault_action_fieldnames = read_csv_fieldnames(FAULTS_ACTIONS_LOG) or list(FAULT_ACTION_FIELDS)
    fault_id = str(payload.get("faultId", "")).strip()

    if action == "create":
        component = str(payload.get("component", "")).strip()
        title = str(payload.get("title", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not component:
            return JsonResponse({"ok": False, "message": "Fault component is required."}, 400)
        if not title and not description:
            return JsonResponse({"ok": False, "message": "Add at least a fault title or description."}, 400)
        fault_rows.append(
            {
                "fault_id": str(int(datetime.now().timestamp() * 1000)),
                "fault_ts": now_label,
                "fault_component": component,
                "fault_title": title or "Fault",
                "fault_description": description,
                "fault_severity": str(payload.get("severity", "")).strip() or "medium",
                "fault_actor": actor,
                "fault_source_file": str(payload.get("sourceFile", "")).strip(),
                "fault_related_draw": str(payload.get("relatedDraw", "")).strip(),
            }
        )
        write_csv_rows(FAULTS_LOG, fault_rows, fault_fieldnames)
        return JsonResponse({"ok": True, "message": "Fault logged.", "bootstrap": build_bootstrap_payload().body})

    match_index = next((index for index, row in enumerate(fault_rows) if str(row.get("fault_id", "")).strip() == fault_id), None)
    if match_index is None:
        return JsonResponse({"ok": False, "message": "Fault not found."}, 404)

    if action == "edit":
        component = str(payload.get("component", "")).strip()
        title = str(payload.get("title", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not component:
            return JsonResponse({"ok": False, "message": "Fault component is required."}, 400)
        if not title and not description:
            return JsonResponse({"ok": False, "message": "Add at least a fault title or description."}, 400)
        row = dict(fault_rows[match_index])
        row["fault_component"] = component
        row["fault_title"] = title or "Fault"
        row["fault_description"] = description
        row["fault_severity"] = str(payload.get("severity", "")).strip() or row.get("fault_severity", "") or "medium"
        row["fault_source_file"] = str(payload.get("sourceFile", "")).strip()
        row["fault_related_draw"] = str(payload.get("relatedDraw", "")).strip()
        fault_rows[match_index] = row
        write_csv_rows(FAULTS_LOG, fault_rows, fault_fieldnames)
        return JsonResponse({"ok": True, "message": "Fault updated.", "bootstrap": build_bootstrap_payload().body})

    if action in {"close", "note", "reopen"}:
        note = str(payload.get("note", "")).strip()
        fix_summary = str(payload.get("fixSummary", "")).strip()
        if action == "close" and not note and not fix_summary:
            return JsonResponse({"ok": False, "message": "Add a close note or fix summary."}, 400)
        if action in {"note", "reopen"} and not note:
            return JsonResponse({"ok": False, "message": "Add a note first."}, 400)
        fault_action_rows.append(
            {
                "fault_action_id": str(int(datetime.now().timestamp() * 1000)),
                "fault_id": fault_id,
                "action_ts": now_label,
                "action_type": action,
                "actor": actor,
                "note": note,
                "fix_summary": fix_summary,
            }
        )
        write_csv_rows(FAULTS_ACTIONS_LOG, fault_action_rows, fault_action_fieldnames)
        message = {
            "close": "Fault closed.",
            "note": "Fault note saved.",
            "reopen": "Fault reopened.",
        }[action]
        return JsonResponse({"ok": True, "message": message, "bootstrap": build_bootstrap_payload().body})

    return JsonResponse({"ok": False, "message": "Unknown fault action."}, 400)


def save_maintenance_runtime_action(payload: dict) -> JsonResponse:
    current = get_maintenance_runtime()
    stored = read_json_dict(MAINTENANCE_RUNTIME)
    updated = dict(stored)
    field_map = {
        "furnaceHours": "furnace_hours",
        "uv1Hours": "uv1_hours",
        "uv2Hours": "uv2_hours",
    }
    runtime_key_map = {
        "furnaceHours": "furnace_hours",
        "uv1Hours": "uv1_hours",
        "uv2Hours": "uv2_hours",
    }
    for payload_key, state_key in field_map.items():
        raw = payload.get(payload_key, current[runtime_key_map[payload_key]])
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "message": f"Invalid value for {payload_key}."}, 400)
        updated[state_key] = int(round(value)) if state_key == "last_draw_count" else value
    updated["last_draw_count"] = int(round(float(len(list_dataset_csv_files()))))
    updated["current_date"] = datetime.now().strftime("%Y-%m-%d")
    write_json_value(MAINTENANCE_RUNTIME, updated)
    return JsonResponse({"ok": True, "message": "Maintenance runtime updated.", "bootstrap": build_bootstrap_payload().body})


def save_maintenance_work_package_action(payload: dict) -> JsonResponse:
    task_id = str(payload.get("taskId", "")).strip()
    component = str(payload.get("component", "")).strip()
    task = str(payload.get("task", "")).strip()
    source_file = str(payload.get("sourceFile", "")).strip()
    if not task_id or not component or not task:
        return JsonResponse({"ok": False, "message": "Task id, component, and task are required."}, 400)
    path = MAINTENANCE_WORK_PACKAGES
    rows = read_csv_rows(path)
    fieldnames = read_csv_fieldnames(path) or [
        "Task_ID", "Component", "Task", "Task_Group", "Required_Parts", "Required_Tools", "Preparation_Checklist", "Safety_Protocol",
        "Safety_Fall_Risk", "Safety_TnM_Presence", "Procedure_Steps", "Procedure_Photos", "Sanity_Checklist", "Draw_Stop_Plan",
        "Est_Stop_Min", "Completion_Criteria", "Supplier_Name", "Supplier_Details", "Sanity_Results", "Last_Updated", "Updated_By",
    ]
    for extra_field in ["Required_Tools", "Supplier_Name", "Supplier_Details", "Sanity_Checklist", "Sanity_Results"]:
        if extra_field not in fieldnames:
            fieldnames.append(extra_field)
    index = next((i for i, row in enumerate(rows) if str(row.get("Task_ID", "")).strip() == task_id), None)
    base_row = rows[index] if index is not None else {key: "" for key in fieldnames}
    photo_entries = parseBuilderPhotoEntries(payload.get("procedurePhotos", ""))
    upload_items = payload.get("photoUploads", []) or []
    if upload_items:
        photo_dir = MAINTENANCE_PACKAGE_PHOTOS_DIR / slugify(component) / slugify(task_id)
        photo_dir.mkdir(parents=True, exist_ok=True)
        uploaded_paths: dict[str, str] = {}
        for item in upload_items:
            temp_id = str(item.get("temp_id", "")).strip()
            filename = os.path.basename(str(item.get("name", "")).strip())
            content = str(item.get("content", "")).strip()
            if not filename or not content:
                continue
            try:
                raw = base64.b64decode(content)
            except Exception:
                continue
            candidate = photo_dir / filename
            stem = candidate.stem
            suffix = candidate.suffix
            version = 2
            while candidate.exists():
                candidate = photo_dir / f"{stem}__{version}{suffix}"
                version += 1
            atomic_write_bytes(candidate, raw)
            saved_path = "/" + str(candidate.relative_to(STATIC_DIR)).replace(os.sep, "/")
            if temp_id:
                uploaded_paths[temp_id] = saved_path
            else:
                photo_entries.append({"path": saved_path, "name": filename, "step_key": "", "step_label": ""})
        resolved_entries: list[dict[str, str]] = []
        for entry in photo_entries:
            path = str(entry.get("path", "")).strip()
            temp_id = str(entry.get("temp_id", "")).strip()
            if not path and temp_id:
                path = uploaded_paths.get(temp_id, "")
            if not path:
                continue
            resolved_entries.append(
                {
                    "path": path,
                    "name": str(entry.get("name", "")).strip() or os.path.basename(path),
                    "step_key": str(entry.get("step_key", "")).strip(),
                    "step_label": str(entry.get("step_label", "")).strip(),
                }
            )
        photo_entries = resolved_entries
    photo_entries = [
        entry
        for entry in parseBuilderPhotoEntries(json.dumps(photo_entries, ensure_ascii=False))
        if str(entry.get("path", "")).strip()
    ]
    base_row["Task_ID"] = task_id
    base_row["Component"] = component
    base_row["Task"] = task
    base_row["Task_Group"] = str(payload.get("taskGroup", base_row.get("Task_Group", ""))).strip()
    base_row["Required_Parts"] = str(payload.get("requiredParts", base_row.get("Required_Parts", ""))).strip()
    base_row["Required_Tools"] = str(payload.get("requiredTools", base_row.get("Required_Tools", ""))).strip()
    base_row["Preparation_Checklist"] = str(payload.get("preparationChecklist", "")).strip()
    base_row["Safety_Protocol"] = str(payload.get("safetyProtocol", "")).strip()
    base_row["Safety_Fall_Risk"] = str(payload.get("safetyFallRisk", "")).strip()
    base_row["Safety_TnM_Presence"] = str(payload.get("safetyTnmPresence", "")).strip()
    base_row["Procedure_Steps"] = str(payload.get("procedureSteps", "")).strip()
    base_row["Procedure_Photos"] = json.dumps(photo_entries, ensure_ascii=False)
    base_row["Sanity_Checklist"] = str(payload.get("sanityChecklist", "")).strip()
    base_row["Sanity_Results"] = str(payload.get("sanityResults", "")).strip()
    base_row["Draw_Stop_Plan"] = str(payload.get("drawStopPlan", "")).strip()
    base_row["Est_Stop_Min"] = str(payload.get("estStopMin", "")).strip()
    base_row["Completion_Criteria"] = str(payload.get("completionCriteria", "")).strip()
    base_row["Supplier_Name"] = str(payload.get("supplierName", "")).strip()
    base_row["Supplier_Details"] = str(payload.get("supplierDetails", "")).strip()
    base_row["Last_Updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base_row["Updated_By"] = "rebuild"
    source_updates = {
        "Task": task,
        "Task_Group": str(payload.get("taskGroup", "")).strip(),
        "Task_Groups": str(payload.get("taskGroups", "")).strip() or str(payload.get("taskGroup", "")).strip(),
        "Owner": str(payload.get("owner", "")).strip(),
        "Trigger Context": str(payload.get("triggerContext", "")).strip(),
        "Tracking_Mode": str(payload.get("trackingMode", "")).strip(),
        "Hours Source": str(payload.get("hoursSource", "")).strip(),
        "Interval Type": str(payload.get("intervalType", "")).strip(),
        "Interval Value": str(payload.get("intervalValue", "")).strip(),
        "Interval Unit": str(payload.get("intervalUnit", "")).strip(),
        "Planning_Window_Months": str(payload.get("planningWindowMonths", "")).strip(),
        "Due Threshold (days)": str(payload.get("dueThresholdDays", "")).strip(),
        "Required_Parts": str(payload.get("requiredParts", "")).strip(),
        "Required_Tools": str(payload.get("requiredTools", "")).strip(),
        "Mandatory_Parts": str(payload.get("requiredParts", "")).strip(),
        "Conditional_Parts": str(payload.get("conditionalParts", "")).strip(),
        "Preparation_Lead_Days": str(payload.get("preparationLeadDays", "")).strip(),
        "Parts_Check_Lead_Days": str(payload.get("partsCheckLeadDays", "")).strip(),
        "Auto_Order_Mandatory_Parts": str(payload.get("autoOrderMandatoryParts", "")).strip(),
        "Trigger_Modes": str(payload.get("triggerModes", "")).strip(),
        "Trigger_Hours_Source": str(payload.get("triggerHoursSource", "")).strip(),
        "Trigger_Hours_Interval": str(payload.get("triggerHoursInterval", "")).strip(),
        "Trigger_Draws_Interval": str(payload.get("triggerDrawsInterval", "")).strip(),
        "Trigger_Calendar_Value": str(payload.get("triggerCalendarValue", "")).strip(),
        "Trigger_Calendar_Unit": str(payload.get("triggerCalendarUnit", "")).strip(),
        "Calendar Rule": str(payload.get("calendarRule", "")).strip(),
        "Manual_Name": str(payload.get("manualName", "")).strip(),
        "Page": str(payload.get("manualPage", "")).strip(),
        "Document": str(payload.get("manualLink", "")).strip(),
        "Procedure Summary": str(payload.get("procedureSummary", "")).strip(),
        "Safety/Notes": str(payload.get("safetyNotes", "")).strip(),
        "Test_Preset": str(payload.get("testPreset", "")).strip(),
        "Test_Fields": str(payload.get("testFields", "")).strip(),
        "Test_Thresholds": str(payload.get("testThresholds", "")).strip(),
        "Test_Condition": str(payload.get("testCondition", "")).strip(),
        "Test_Action": str(payload.get("testAction", "")).strip(),
    }
    if source_file:
        try:
            update_maintenance_source_task(source_file, task_id, component, task, source_updates)
        except Exception as exc:
            return JsonResponse({"ok": False, "message": f"Failed to update maintenance source row: {exc}"}, 400)
    if index is None:
        rows.append(base_row)
    else:
        rows[index] = base_row
    write_csv_rows(path, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Maintenance work package saved.", "bootstrap": build_bootstrap_payload().body})


def create_maintenance_task_action(payload: dict) -> JsonResponse:
    source_file = str(payload.get("sourceFile", "")).strip()
    component = str(payload.get("component", "")).strip() or "General"
    task = str(payload.get("task", "")).strip()
    task_group = str(payload.get("taskGroup", "")).strip() or "General"
    try:
        created = create_maintenance_source_task(source_file, component, task, task_group)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": f"Failed to create maintenance task: {exc}"}, 400)
    return JsonResponse(
        {
            "ok": True,
            "message": "Maintenance task created.",
            "taskId": created["task_id"],
            "component": created["component"],
            "task": created["task"],
            "bootstrap": build_bootstrap_payload().body,
        }
    )


def maintenance_row_matches_identity(
    row: dict[str, object],
    task_id: str,
    component: str,
    task: str,
    task_id_keys: tuple[str, ...],
    component_keys: tuple[str, ...],
    task_keys: tuple[str, ...],
) -> bool:
    safe_task_id = str(task_id or "").strip()
    if safe_task_id and any(str(row.get(key, "")).strip() == safe_task_id for key in task_id_keys):
        return True
    safe_component = str(component or "").strip().lower()
    safe_task = str(task or "").strip().lower()
    if not safe_component or not safe_task:
        return False
    row_component = next((str(row.get(key, "")).strip().lower() for key in component_keys if str(row.get(key, "")).strip()), "")
    row_task = next((str(row.get(key, "")).strip().lower() for key in task_keys if str(row.get(key, "")).strip()), "")
    return bool(row_component and row_task and row_component == safe_component and row_task == safe_task)


def delete_csv_rows_for_maintenance_task(
    path: Path,
    task_id: str,
    component: str,
    task: str,
    task_id_keys: tuple[str, ...],
    component_keys: tuple[str, ...],
    task_keys: tuple[str, ...],
) -> int:
    if not path.exists():
        return 0
    rows = read_csv_rows(path)
    fieldnames = read_csv_fieldnames(path)
    kept_rows = [
        row
        for row in rows
        if not maintenance_row_matches_identity(row, task_id, component, task, task_id_keys, component_keys, task_keys)
    ]
    removed = len(rows) - len(kept_rows)
    if removed:
        write_csv_rows(path, kept_rows, fieldnames or list((rows[0] if rows else {}).keys()))
    return removed


def delete_maintenance_task_action(payload: dict) -> JsonResponse:
    task_id = str(payload.get("taskId", "")).strip()
    component = str(payload.get("component", "")).strip()
    task = str(payload.get("task", "")).strip()
    source_file = str(payload.get("sourceFile", "")).strip()
    if not component or not task:
        return JsonResponse({"ok": False, "message": "Component and task are required."}, 400)
    if not source_file:
        return JsonResponse({"ok": False, "message": "Task source file is required for delete."}, 400)
    try:
        delete_maintenance_source_task(source_file, task_id, component, task)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": f"Failed to delete maintenance task: {exc}"}, 400)
    delete_csv_rows_for_maintenance_task(
        MAINTENANCE_WORK_PACKAGES,
        task_id,
        component,
        task,
        ("Task_ID",),
        ("Component",),
        ("Task",),
    )
    delete_csv_rows_for_maintenance_task(
        MAINTENANCE_STATE,
        task_id,
        component,
        task,
        ("task_id",),
        ("component",),
        ("task",),
    )
    delete_csv_rows_for_maintenance_task(
        MAINTENANCE_WAITS,
        task_id,
        component,
        task,
        ("maintenance_task_id",),
        ("maintenance_component",),
        ("maintenance_task",),
    )
    return JsonResponse({"ok": True, "message": "Maintenance task deleted.", "bootstrap": build_bootstrap_payload().body})


def update_inventory_stock_action(payload: dict) -> JsonResponse:
    rows = read_csv_rows(PARTS_INVENTORY)
    fieldnames = read_csv_fieldnames(PARTS_INVENTORY)
    if not fieldnames:
        fieldnames = ["Part Name", "Item Type", "Component", "Supplier", "Serial Number", "Location", "Location Serial", "Quantity", "Min Level", "Notes", "Last Updated"]
    elif "Supplier" not in fieldnames:
        insert_at = fieldnames.index("Component") + 1 if "Component" in fieldnames else len(fieldnames)
        fieldnames = fieldnames[:insert_at] + ["Supplier"] + fieldnames[insert_at:]
    part_name = str(payload.get("partName", "")).strip()
    if not part_name:
        return JsonResponse({"ok": False, "message": "Part name is required."}, 400)
    serial = str(payload.get("serialNumber", "")).strip()
    mode = str(payload.get("mode", "add")).strip()
    qty = max(0.0 if mode == "edit" else 0.01, to_float(str(payload.get("quantity", "1"))))
    location = str(payload.get("location", "")).strip()
    item_type = str(payload.get("itemType", "Part")).strip() or "Part"
    component = str(payload.get("component", "Tower Parts")).strip() or "Tower Parts"
    supplier = str(payload.get("supplier", "")).strip()
    min_level = str(payload.get("minLevel", "")).strip()
    notes = str(payload.get("notes", "")).strip()
    location_serial_map = {
        str(row.get("Location Name", "")).strip(): str(row.get("Location Serial", "")).strip()
        for row in read_csv_rows(PARTS_LOCATIONS)
        if str(row.get("Location Name", "")).strip()
    }
    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    match_index = None
    for index, row in enumerate(rows):
        if str(row.get("Part Name", "")).strip().lower() != part_name.lower():
            continue
        if str(row.get("Serial Number", "")).strip().lower() != serial.lower():
            continue
        if mode == "use":
            match_index = index
            break
        existing_location = str(row.get("Location", "")).strip().lower()
        desired_location = location.lower()
        if existing_location == desired_location:
            match_index = index
            break
    if mode == "add":
        if match_index is None:
            rows.append(
                {
                    "Part Name": part_name,
                    "Item Type": item_type,
                    "Component": component,
                    "Supplier": supplier,
                    "Serial Number": serial,
                    "Location": location,
                    "Location Serial": location_serial_map.get(location, "MOUNTED" if location.lower() == "mounted" else ""),
                    "Quantity": f"{qty:g}",
                    "Min Level": min_level or "0",
                    "Notes": notes or "Quick inventory add",
                    "Last Updated": now_label,
                }
            )
        else:
            current_qty = to_float(rows[match_index].get("Quantity"))
            rows[match_index]["Quantity"] = f"{current_qty + qty:g}"
            rows[match_index]["Item Type"] = item_type
            rows[match_index]["Component"] = component
            rows[match_index]["Supplier"] = supplier if supplier else str(rows[match_index].get("Supplier", "")).strip()
            rows[match_index]["Location"] = location
            rows[match_index]["Location Serial"] = location_serial_map.get(location, "MOUNTED" if location.lower() == "mounted" else rows[match_index].get("Location Serial", ""))
            if min_level:
                rows[match_index]["Min Level"] = min_level
            if notes:
                rows[match_index]["Notes"] = notes
            rows[match_index]["Last Updated"] = now_label
        write_csv_rows(PARTS_INVENTORY, rows, fieldnames)
        return JsonResponse({"ok": True, "message": "Inventory stock increased.", "bootstrap": build_bootstrap_payload().body})
    if mode == "new":
        for row in rows:
            if str(row.get("Part Name", "")).strip().lower() != part_name.lower():
                continue
            if str(row.get("Serial Number", "")).strip().lower() != serial.lower():
                continue
            if str(row.get("Location", "")).strip().lower() != location.lower():
                continue
            return JsonResponse({"ok": False, "message": "Inventory row already exists. Use edit or add stock instead."}, 400)
        rows.append(
            {
                "Part Name": part_name,
                "Item Type": item_type,
                "Component": component,
                "Supplier": supplier,
                "Serial Number": serial,
                "Location": location,
                "Location Serial": location_serial_map.get(location, "MOUNTED" if location.lower() == "mounted" else ""),
                "Quantity": f"{qty:g}",
                "Min Level": min_level or "0",
                "Notes": notes or "New inventory row",
                "Last Updated": now_label,
            }
        )
        write_csv_rows(PARTS_INVENTORY, rows, fieldnames)
        return JsonResponse({"ok": True, "message": "Inventory row created.", "bootstrap": build_bootstrap_payload().body})
    if mode == "edit":
        try:
            edit_index = int(payload.get("inventoryEditIndex", ""))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "message": "Choose which inventory row to edit."}, 400)
        if edit_index < 0 or edit_index >= len(rows):
            return JsonResponse({"ok": False, "message": "Inventory row was not found."}, 400)
        current_row = rows[edit_index]
        rows[edit_index]["Part Name"] = part_name or str(current_row.get("Part Name", "")).strip()
        rows[edit_index]["Item Type"] = item_type or str(current_row.get("Item Type", "")).strip() or "Part"
        rows[edit_index]["Component"] = component or str(current_row.get("Component", "")).strip() or "Tower Parts"
        rows[edit_index]["Supplier"] = supplier if supplier else str(current_row.get("Supplier", "")).strip()
        rows[edit_index]["Serial Number"] = serial
        rows[edit_index]["Location"] = location
        rows[edit_index]["Location Serial"] = location_serial_map.get(location, "MOUNTED" if location.lower() == "mounted" else str(current_row.get("Location Serial", "")).strip())
        rows[edit_index]["Quantity"] = f"{qty:g}"
        rows[edit_index]["Min Level"] = min_level if min_level != "" else str(current_row.get("Min Level", "")).strip() or "0"
        rows[edit_index]["Notes"] = notes if notes else str(current_row.get("Notes", "")).strip()
        rows[edit_index]["Last Updated"] = now_label
        write_csv_rows(PARTS_INVENTORY, rows, fieldnames)
        return JsonResponse({"ok": True, "message": "Inventory row updated.", "bootstrap": build_bootstrap_payload().body})
    if match_index is None:
        return JsonResponse({"ok": False, "message": "Part was not found in inventory."}, 400)
    current_qty = to_float(rows[match_index].get("Quantity"))
    remaining = max(0.0, current_qty - qty)
    rows[match_index]["Quantity"] = f"{remaining:g}"
    rows[match_index]["Last Updated"] = now_label
    rows[match_index]["Notes"] = notes or "Quick inventory use"
    write_csv_rows(PARTS_INVENTORY, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Inventory stock decreased.", "bootstrap": build_bootstrap_payload().body})


def sync_part_order_into_inventory(row: dict[str, str], payload: dict) -> bool:
    rows = read_csv_rows(PARTS_INVENTORY)
    fieldnames = read_csv_fieldnames(PARTS_INVENTORY)
    if not fieldnames:
        fieldnames = ["Part Name", "Item Type", "Component", "Supplier", "Serial Number", "Location", "Location Serial", "Quantity", "Min Level", "Notes", "Last Updated"]
    elif "Supplier" not in fieldnames:
        insert_at = fieldnames.index("Component") + 1 if "Component" in fieldnames else len(fieldnames)
        fieldnames = fieldnames[:insert_at] + ["Supplier"] + fieldnames[insert_at:]
    location_serial_map = {
        str(item.get("Location Name", "")).strip(): str(item.get("Location Serial", "")).strip()
        for item in read_csv_rows(PARTS_LOCATIONS)
        if str(item.get("Location Name", "")).strip()
    }
    inventory_action = str(payload.get("inventoryAction", "")).strip()
    if inventory_action == "Locate in inventory":
        location = str(payload.get("inventoryLocation", "")).strip()
    elif inventory_action == "Mount on machine":
        location = str(payload.get("inventoryLocation", "")).strip() or "Mounted"
    else:
        location = ""
    part_name = str(payload.get("partName", row.get("Part Name", ""))).strip()
    serial = str(payload.get("serialNumber", row.get("Serial Number", ""))).strip()
    quantity = max(0.01, to_float(str(payload.get("inventoryQuantity", "1"))))
    item_type = str(payload.get("inventoryItemType", "")).strip() or "Part"
    component = str(
        payload.get("inventoryComponent", "")
        or payload.get("maintenanceComponent", row.get("Maintenance Component", ""))
    ).strip() or "Tower Parts"
    supplier = str(payload.get("inventorySupplier", row.get("Company", ""))).strip()
    min_level = str(payload.get("inventoryMinLevel", "")).strip() or "0"
    notes = str(payload.get("inventoryNotes", "")).strip() or f"Auto from received order ({inventory_action})"
    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    match_index = None
    preferred_index = to_int(payload.get("inventoryMatchIndex"), -1)
    if 0 <= preferred_index < len(rows):
        preferred_row = rows[preferred_index]
        preferred_part = str(preferred_row.get("Part Name", "")).strip().lower()
        preferred_serial = str(preferred_row.get("Serial Number", "")).strip().lower()
        preferred_component = str(preferred_row.get("Component", "")).strip().lower()
        if (
            (part_name and preferred_part == part_name.lower())
            or (serial and preferred_serial == serial.lower())
            or (component and preferred_component == component.lower())
        ):
            match_index = preferred_index
            if not location:
                location = str(preferred_row.get("Location", "")).strip()
            if not supplier:
                supplier = str(preferred_row.get("Supplier", "")).strip()
            if not min_level:
                min_level = str(preferred_row.get("Min Level", "")).strip() or "0"
            if not item_type:
                item_type = str(preferred_row.get("Item Type", "")).strip() or "Part"
    for index, inv_row in enumerate(rows):
        if match_index is not None:
            break
        if str(inv_row.get("Part Name", "")).strip().lower() != part_name.lower():
            continue
        if str(inv_row.get("Serial Number", "")).strip().lower() != serial.lower():
            continue
        if str(inv_row.get("Location", "")).strip().lower() != location.lower():
            continue
        match_index = index
        break
    if match_index is not None and not location:
        location = str(rows[match_index].get("Location", "")).strip()
    if not location:
        return False
    if match_index is None:
        rows.append(
            {
                "Part Name": part_name,
                "Item Type": item_type,
                "Component": component,
                "Supplier": supplier,
                "Serial Number": serial,
                "Location": location,
                "Location Serial": location_serial_map.get(location, "MOUNTED" if location.lower() == "mounted" else ""),
                "Quantity": f"{quantity:g}",
                "Min Level": min_level,
                "Notes": notes,
                "Last Updated": now_label,
            }
        )
    else:
        current_qty = to_float(rows[match_index].get("Quantity"))
        rows[match_index]["Quantity"] = f"{current_qty + quantity:g}"
        rows[match_index]["Item Type"] = item_type
        rows[match_index]["Component"] = component
        rows[match_index]["Supplier"] = supplier if supplier else str(rows[match_index].get("Supplier", "")).strip()
        rows[match_index]["Location"] = location
        rows[match_index]["Location Serial"] = location_serial_map.get(location, "MOUNTED" if location.lower() == "mounted" else rows[match_index].get("Location Serial", ""))
        rows[match_index]["Notes"] = notes
        rows[match_index]["Last Updated"] = now_label
        if min_level:
            rows[match_index]["Min Level"] = min_level
    write_csv_rows(PARTS_INVENTORY, rows, fieldnames)
    return True


def delete_part_order_action(payload: dict) -> JsonResponse:
    rows = read_csv_rows(PART_ORDERS)
    fieldnames = read_csv_fieldnames(PART_ORDERS)
    try:
        index = int(payload.get("index"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "Order selection is invalid."}, 400)
    if index < 0 or index >= len(rows):
        return JsonResponse({"ok": False, "message": "Order not found."}, 400)
    del rows[index]
    write_csv_rows(PART_ORDERS, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Part order deleted.", "bootstrap": build_bootstrap_payload().body})


def set_maintenance_state_action(payload: dict) -> JsonResponse:
    task_id = str(payload.get("taskId", "")).strip()
    component = str(payload.get("component", "")).strip()
    task = str(payload.get("task", "")).strip()
    state = str(payload.get("state", "")).strip()
    note = str(payload.get("note", "")).strip()
    if not task_id or not state:
      return JsonResponse({"ok": False, "message": "Task and state are required."}, 400)
    rows = read_csv_rows(MAINTENANCE_STATE)
    fieldnames = read_csv_fieldnames(MAINTENANCE_STATE) or ["task_key", "task_id", "component", "task", "state", "updated_ts", "updated_by", "note"]
    task_key = f"{task_id.lower()}::{component.lower()}::{task.lower()}"
    updated = False
    for row in rows:
        if str(row.get("task_id", "")).strip() == task_id:
            row["task_key"] = task_key
            row["component"] = component
            row["task"] = task
            row["state"] = state
            row["updated_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row["updated_by"] = "rebuild"
            row["note"] = note
            updated = True
            break
    if not updated:
        rows.append(
            {
                "task_key": task_key,
                "task_id": task_id,
                "component": component,
                "task": task,
                "state": state,
                "updated_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updated_by": "rebuild",
                "note": note,
            }
        )
    write_csv_rows(MAINTENANCE_STATE, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Maintenance state updated.", "bootstrap": build_bootstrap_payload().body})


def complete_maintenance_task_action(payload: dict) -> JsonResponse:
    task_id = str(payload.get("taskId", "")).strip()
    component = str(payload.get("component", "")).strip()
    task = str(payload.get("task", "")).strip()
    mode = str(payload.get("trackingMode", "")).strip()
    note = str(payload.get("note", "")).strip()
    if not task_id:
        return JsonResponse({"ok": False, "message": "Task is required."}, 400)
    runtime_context = get_maintenance_runtime_context()
    task_row = find_maintenance_task_record(task_id, component, task)
    if task_row is None:
        return JsonResponse({"ok": False, "message": "Maintenance task source row was not found."}, 404)
    source_file = str(task_row.get("Source_File", "")).strip()
    hours_source = first_task_value(task_row, "Hours Source", "Hours_Source")
    last_done_updates = maintenance_last_done_updates(hours_source, runtime_context)
    try:
        update_maintenance_source_task(source_file, task_id, component, task, last_done_updates)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": f"Failed to update maintenance source row: {exc}"}, 400)

    rows = read_csv_rows(MAINTENANCE_ACTIONS)
    fieldnames = read_csv_fieldnames(MAINTENANCE_ACTIONS) or [
        "maintenance_id", "maintenance_ts", "maintenance_component", "maintenance_task", "maintenance_task_id",
        "maintenance_mode", "maintenance_hours_source", "maintenance_done_date", "maintenance_done_hours",
        "maintenance_done_draw", "maintenance_source_file", "maintenance_actor", "maintenance_note",
    ]
    rows.append(
        {
            "maintenance_id": str(int(datetime.now().timestamp() * 1000)),
            "maintenance_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "maintenance_component": component,
            "maintenance_task": task,
            "maintenance_task_id": task_id,
            "maintenance_mode": mode,
            "maintenance_hours_source": normalize_maintenance_hours_source(hours_source),
            "maintenance_done_date": str(last_done_updates.get("Last_Done_Date", "")),
            "maintenance_done_hours": str(last_done_updates.get("Last_Done_Hours", "")),
            "maintenance_done_draw": str(last_done_updates.get("Last_Done_Draw", "")),
            "maintenance_source_file": source_file,
            "maintenance_actor": "rebuild",
            "maintenance_note": note,
        }
    )
    write_csv_rows(MAINTENANCE_ACTIONS, rows, fieldnames)

    refreshed_runtime_context = get_maintenance_runtime_context()
    updated_task_row = find_maintenance_task_record(task_id, component, task) or task_row
    due_lookup = build_maintenance_due_lookup(refreshed_runtime_context)
    due_key = task_id or f"{component.strip().lower()}::{task.strip().lower()}"
    due_meta = due_lookup.get(due_key, {})
    next_due_date = parse_dt(str(due_meta.get("next_due_date", "")).strip())
    schedule_rows = read_csv_rows(TOWER_SCHEDULE)
    schedule_fieldnames = read_csv_fieldnames(TOWER_SCHEDULE) or SCHEDULE_REQUIRED_COLS[:]
    schedule_fieldnames = schedule_fieldnames + [field for field in SCHEDULE_REQUIRED_COLS if field not in schedule_fieldnames]
    task_schedule_rows = [
        row for row in schedule_rows
        if f"Task ID: {task_id}" in str(row.get("Description", ""))
        and "maintenance" in str(row.get("Event Type", "")).strip().lower()
    ]
    latest_schedule_row = None
    latest_schedule_start = None
    for row in task_schedule_rows:
        row_start = parse_dt(str(row.get("Start DateTime", "")).strip())
        if row_start and (latest_schedule_start is None or row_start > latest_schedule_start):
            latest_schedule_start = row_start
            latest_schedule_row = row

    duration_minutes = int(
        round(
            to_float(
                first_task_value(updated_task_row, "Est_Duration_Min", "Estimated duration min")
                or "60"
            )
        )
    ) or 60
    if latest_schedule_row:
        prior_start = parse_dt(str(latest_schedule_row.get("Start DateTime", "")).strip())
        prior_end = parse_dt(str(latest_schedule_row.get("End DateTime", "")).strip())
        if prior_start and prior_end and prior_end > prior_start:
            duration_minutes = max(1, int(round((prior_end - prior_start).total_seconds() / 60)))

    next_start = None
    recurrence = "none"
    if next_due_date:
        template_time = latest_schedule_start.time() if latest_schedule_start else datetime.strptime("08:00", "%H:%M").time()
        next_start = datetime.combine(next_due_date.date(), template_time)
        recurrence = infer_maintenance_recurrence_from_task(updated_task_row)
    elif latest_schedule_start:
        inferred = infer_maintenance_recurrence_from_task(updated_task_row)
        if inferred != "none":
            next_start = next_recurrence_dt(latest_schedule_start, inferred)
            recurrence = inferred

    if next_start:
        next_end = next_start + timedelta(minutes=max(1, duration_minutes))
        description = f"Maintenance scheduled: {component} — {task} (Task ID: {task_id})."
        schedule_rows = [
            row
            for row in schedule_rows
            if not (
                f"Task ID: {task_id}" in str(row.get("Description", ""))
                and "maintenance" in str(row.get("Event Type", "")).strip().lower()
            )
        ]
        schedule_rows.append(
            {
                "Event Type": "Maintenance",
                "Start DateTime": next_start.strftime("%Y-%m-%d %H:%M:%S"),
                "End DateTime": next_end.strftime("%Y-%m-%d %H:%M:%S"),
                "Description": description,
                "Recurrence": recurrence,
            }
        )
        write_csv_rows(TOWER_SCHEDULE, schedule_rows, schedule_fieldnames)
        set_maintenance_state_action(
            {
                "taskId": task_id,
                "component": component,
                "task": task,
                "state": "DONE_NOW",
                "note": f"Completed. Next scheduled for {next_start.strftime('%Y-%m-%d %H:%M')}.",
            }
        )
        return JsonResponse(
            {
                "ok": True,
                "message": f"Maintenance action logged. Next occurrence scheduled for {next_start.strftime('%Y-%m-%d %H:%M')}.",
                "bootstrap": build_bootstrap_payload().body,
            }
        )

    set_maintenance_state_action({"taskId": task_id, "component": component, "task": task, "state": "DONE_NOW", "note": note or "Completed."})
    return JsonResponse({"ok": True, "message": "Maintenance action logged.", "bootstrap": build_bootstrap_payload().body})


def create_maintenance_part_orders_action(payload: dict) -> JsonResponse:
    task_entries = payload.get("tasks")
    if isinstance(task_entries, list) and task_entries:
        normalized_tasks = [
            {
                "task_id": str(item.get("taskId", "")).strip(),
                "component": str(item.get("component", "")).strip(),
                "task": str(item.get("task", "")).strip(),
                "parts": item.get("parts", []) or [],
            }
            for item in task_entries
            if str(item.get("taskId", "")).strip()
        ]
    else:
        task_id = str(payload.get("taskId", "")).strip()
        component = str(payload.get("component", "")).strip()
        task = str(payload.get("task", "")).strip()
        parts = payload.get("parts", []) or []
        normalized_tasks = [{
            "task_id": task_id,
            "component": component,
            "task": task,
            "parts": parts,
        }] if task_id else []

    if not normalized_tasks:
        return JsonResponse({"ok": False, "message": "Task and parts are required."}, 400)
    rows = read_csv_rows(PART_ORDERS)
    fieldnames = read_csv_fieldnames(PART_ORDERS)
    active_status = {"Opened", "Wait for Approval", "Approved", "Ordered", "Received"}
    created = 0
    touched_tasks: list[tuple[str, str, str]] = []
    for task_entry in normalized_tasks:
        task_id = task_entry["task_id"]
        component = task_entry["component"]
        task = task_entry["task"]
        parts = task_entry["parts"]
        if not task_id or not parts:
            continue
        for part_name in parts:
            part = str(part_name or "").strip()
            if not part:
                continue
            exists = any(
                str(row.get("Part Name", "")).strip().lower() == part.lower()
                and str(row.get("Maintenance Task ID", "")).strip() == task_id
                and str(row.get("Status", "")).strip() in active_status
                for row in rows
            )
            if exists:
                continue
            rows.append(
                {
                    "Status": "Opened",
                    "Part Name": part,
                    "Serial Number": "",
                    "Project Name": "Maintenance",
                    "Details": f"Maintenance hold: {component} — {task} (Task ID: {task_id}).",
                    "Opened By": "rebuild",
                    "Approval Requested From": "",
                    "Approved": "No",
                    "Approved By": "",
                    "Approval Date": "",
                    "Received Date": "",
                    "Received State": "",
                    "Ordered By": "",
                    "Date Ordered": "",
                    "Company": "",
                    "Inventory Synced": "",
                    "Maintenance Component": component,
                    "Maintenance Task": task,
                    "Maintenance Task ID": task_id,
                    "Wait ID": "",
                }
            )
            created += 1
        touched_tasks.append((task_id, component, task))
    write_csv_rows(PART_ORDERS, rows, fieldnames)
    for task_id, component, task in touched_tasks:
        set_maintenance_state_action({
            "taskId": task_id,
            "component": component,
            "task": task,
            "state": "WAIT FOR PART",
            "note": "Parts ordered from prep horizon.",
        })
    return JsonResponse({"ok": True, "message": f"Created {created} maintenance part order(s).", "bootstrap": build_bootstrap_payload().body})


def schedule_maintenance_tasks_action(payload: dict) -> JsonResponse:
    event_type = str(payload.get("eventType", "")).strip() or "Maintenance"
    recurrence = normalize_recurrence(payload.get("recurrence", "")) or "none"
    task_entries = payload.get("tasks")
    window_entries = payload.get("windows")
    normalized_windows = []
    if isinstance(window_entries, list) and window_entries:
        normalized_windows = [
            {
                "start": str(item.get("start", "")).strip(),
                "end": str(item.get("end", "")).strip(),
                "label": str(item.get("label", "")).strip(),
            }
            for item in window_entries
            if str(item.get("start", "")).strip() and str(item.get("end", "")).strip()
        ]
    else:
        start = str(payload.get("start", "")).strip()
        end = str(payload.get("end", "")).strip()
        if start and end:
            normalized_windows = [{
                "start": start,
                "end": end,
                "label": str(payload.get("label", "")).strip(),
            }]
    if not normalized_windows:
        return JsonResponse({"ok": False, "message": "Schedule window is required."}, 400)
    if isinstance(task_entries, list) and task_entries:
        normalized_tasks = [
            {
                "task_id": str(item.get("taskId", "")).strip(),
                "component": str(item.get("component", "")).strip(),
                "task": str(item.get("task", "")).strip(),
            }
            for item in task_entries
            if str(item.get("taskId", "")).strip()
        ]
    else:
        task_id = str(payload.get("taskId", "")).strip()
        normalized_tasks = [{
            "task_id": task_id,
            "component": str(payload.get("component", "")).strip(),
            "task": str(payload.get("task", "")).strip(),
        }] if task_id else []
    if not normalized_tasks:
        return JsonResponse({"ok": False, "message": "Task is required."}, 400)

    maintenance_summary = summarize_maintenance_rebuild()
    task_rows = maintenance_summary.get("tasks", [])

    def resolve_schedule_task(task_id: str, component: str, task: str) -> dict[str, object] | None:
        normalized_task_id = str(task_id or "").strip().lower()
        normalized_component = str(component or "").strip().lower()
        normalized_task = str(task or "").strip().lower()
        for row in task_rows:
            row_task_id = str(row.get("task_id", "")).strip().lower()
            if normalized_task_id and row_task_id == normalized_task_id:
                return row
        for row in task_rows:
            row_component = str(row.get("component", "")).strip().lower()
            row_task = str(row.get("task", "")).strip().lower()
            if normalized_component and normalized_task and row_component == normalized_component and row_task == normalized_task:
                return row
        return None

    for task_entry in normalized_tasks:
        task_row = resolve_schedule_task(task_entry["task_id"], task_entry["component"], task_entry["task"])
        if task_row is None:
            return JsonResponse({"ok": False, "message": f"Maintenance task {task_entry['task_id'] or task_entry['task'] or 'row'} was not found."}, 404)
        current_state = str(task_row.get("status", "")).strip().upper()
        if current_state != "PREP_DONE":
            component_label = str(task_row.get("component", "")).strip() or str(task_entry["component"]).strip() or "Task"
            return JsonResponse({"ok": False, "message": f"{component_label} must be marked ready before it can be scheduled."}, 400)

    rows = read_csv_rows(TOWER_SCHEDULE)
    fieldnames = read_csv_fieldnames(TOWER_SCHEDULE) or SCHEDULE_REQUIRED_COLS[:]
    created = 0
    for index, task_entry in enumerate(normalized_tasks):
        task_id = task_entry["task_id"]
        component = task_entry["component"]
        task = task_entry["task"]
        selected_window = normalized_windows[index % len(normalized_windows)]
        start = selected_window["start"]
        end = selected_window["end"]
        scheduled_for_label = selected_window["label"] or (parse_dt(start).strftime("%b %d %H:%M") if parse_dt(start) else start)
        description = f"Maintenance scheduled: {component} — {task} (Task ID: {task_id})."
        exists = any(
            str(row.get("Start DateTime", "")).strip() == start
            and f"Task ID: {task_id}" in str(row.get("Description", ""))
            for row in rows
        )
        if not exists:
            rows.append(
                {
                    "Event Type": event_type,
                    "Start DateTime": start,
                    "End DateTime": end,
                    "Description": description,
                    "Recurrence": recurrence,
                }
            )
            created += 1
        set_maintenance_state_action({
            "taskId": task_id,
            "component": component,
            "task": task,
            "state": "SCHEDULED",
            "note": f"Scheduled from prep horizon for {scheduled_for_label}.",
        })
    write_csv_rows(TOWER_SCHEDULE, rows, fieldnames)
    return JsonResponse({"ok": True, "message": f"Scheduled {len(normalized_tasks)} maintenance task(s).", "bootstrap": build_bootstrap_payload().body})


def unmount_inventory_item_action(payload: dict) -> JsonResponse:
    rows = read_csv_rows(PARTS_INVENTORY)
    fieldnames = read_csv_fieldnames(PARTS_INVENTORY)
    part_name = str(payload.get("partName", "")).strip()
    serial = str(payload.get("serialNumber", "")).strip()
    qty = max(0.01, to_float(str(payload.get("quantity", "1"))))
    if not part_name:
        return JsonResponse({"ok": False, "message": "Mounted part is required."}, 400)
    match_index = None
    for index, row in enumerate(rows):
        if str(row.get("Part Name", "")).strip().lower() != part_name.lower():
            continue
        if str(row.get("Location", "")).strip().lower() != "mounted":
            continue
        if serial and str(row.get("Serial Number", "")).strip().lower() != serial.lower():
            continue
        match_index = index
        break
    if match_index is None:
        return JsonResponse({"ok": False, "message": "Mounted row was not found."}, 400)
    current_qty = to_float(rows[match_index].get("Quantity"))
    remaining = max(0.0, current_qty - qty)
    rows[match_index]["Quantity"] = f"{remaining:g}"
    rows[match_index]["Last Updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows[match_index]["Notes"] = "Unmounted from machine"
    if remaining == 0:
        rows[match_index]["Location"] = ""
        rows[match_index]["Location Serial"] = ""
        if not str(rows[match_index].get("Component", "")).strip():
            rows[match_index]["Component"] = "Tower Parts"
    write_csv_rows(PARTS_INVENTORY, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Mounted inventory updated.", "bootstrap": build_bootstrap_payload().body})


def list_recent_files(directory: Path, suffixes: tuple[str, ...] = (".csv",), limit: int = 6) -> list[dict]:
    if not directory.exists() or not directory.is_dir():
        return []
    files = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in suffixes]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    output = []
    for path in files[:limit]:
        stat = path.stat()
        output.append(
            {
                "name": path.name,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "size_kb": round(stat.st_size / 1024, 1),
            }
        )
    return output


def list_csv_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted([path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".csv"], key=lambda p: p.stat().st_mtime, reverse=True)


LOG_DEPRIORITIZED_NAME_HINTS = ("fake", "simulated", "test", "newst", "demo", "sample", "log1")
LOG_FALLBACK_NAME_HINTS = ("modified_", "adjusted")
LOG_PRODUCTION_NAME_HINTS = ("training", "fiber_drawing", "tower", "draw")


def inspect_log_header_shape(path: Path) -> dict[str, bool]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            reader = csv.reader(handle)
            first_row = next(reader, [])
            second_row = next(reader, [])
    except Exception:
        return {"is_raw": False, "is_friendly": False}
    first_text = str(first_row[0] or "").strip().lower() if first_row else ""
    header_row = second_row if first_text == "data log" else first_row
    lowered = [str(item or "").strip().lower() for item in header_row]
    is_raw = first_text == "data log" or any(item.startswith("[plc]") or item.startswith("plc]") for item in lowered)
    is_friendly = any(item in LEGACY_LOG_MAPPED_VALUES_NORMALIZED for item in lowered)
    return {"is_raw": is_raw, "is_friendly": is_friendly}


def dashboard_log_sort_tuple(path: Path) -> tuple[int, int, int, int, float]:
    name = path.name.lower()
    stat = path.stat()
    shape = inspect_log_header_shape(path)
    is_raw = shape["is_raw"]
    is_friendly = shape["is_friendly"]
    is_production_named = any(hint in name for hint in LOG_PRODUCTION_NAME_HINTS)
    is_fallback_named = any(hint in name for hint in LOG_FALLBACK_NAME_HINTS)
    is_deprioritized = any(hint in name for hint in LOG_DEPRIORITIZED_NAME_HINTS)
    return (
        0 if is_deprioritized else 1,
        1 if is_raw else 0,
        1 if is_production_named else 0,
        1 if is_friendly and not is_fallback_named else 0,
        stat.st_size,
        stat.st_mtime,
    )


def list_dashboard_log_files() -> list[Path]:
    files = list_csv_files(LOGS_DIR)
    return sorted(files, key=dashboard_log_sort_tuple, reverse=True)


DRAW_DATASET_CANONICAL_RE = re.compile(r"^(?P<preform>.+?)F(?P<index>\d+)$", re.IGNORECASE)
DRAW_DATASET_UNDERSCORE_RE = re.compile(r"^(?P<preform>.+?)_F(?P<index>\d+)$", re.IGNORECASE)
DRAW_DATASET_LEGACY_RE = re.compile(r"^(?P<preform>.+?)F_(?P<index>\d+)$", re.IGNORECASE)
ZONE_DATASET_RE = re.compile(r"^(?P<draw>.+)_Z(?P<zone>\d+)$", re.IGNORECASE)


def normalize_preform_token(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def canonical_draw_dataset_stem(preform: object, index: object) -> str:
    return f"{normalize_preform_token(preform)}F{int(str(index or '0') or '0')}"


def canonical_draw_dataset_filename(csv_name: str) -> str:
    dataset_file = os.path.basename(str(csv_name or "").strip())
    if not dataset_file:
        return ""
    path = Path(dataset_file)
    zone_match = ZONE_DATASET_RE.match(path.stem)
    zone_suffix = f"_Z{zone_match.group('zone')}" if zone_match else ""
    identity = parse_draw_dataset_identity(path.stem)
    if not identity:
        return dataset_file
    ext = path.suffix or ".csv"
    return f"{identity['draw_stem']}{zone_suffix}{ext}"


def draw_dataset_filename_variants(csv_name: str) -> list[str]:
    dataset_file = os.path.basename(str(csv_name or "").strip())
    if not dataset_file:
        return []
    path = Path(dataset_file)
    zone_match = ZONE_DATASET_RE.match(path.stem)
    zone_suffix = f"_Z{zone_match.group('zone')}" if zone_match else ""
    identity = parse_draw_dataset_identity(path.stem)
    if not identity:
        return [dataset_file]
    ext = path.suffix or ".csv"
    preform = str(identity["preform"])
    index = int(identity["index"])
    variants = [
        f"{preform}F{index}{zone_suffix}{ext}",
        f"{preform}_F{index}{zone_suffix}{ext}",
        f"{preform}F_{index}{zone_suffix}{ext}",
    ]
    return list(dict.fromkeys(variants))


def parse_draw_dataset_identity(stem: str) -> dict[str, object] | None:
    text = normalize_preform_token(stem)
    if not text:
        return None
    zone_match = ZONE_DATASET_RE.match(text)
    if zone_match:
        text = str(zone_match.group("draw") or "").strip()
    for pattern in (DRAW_DATASET_UNDERSCORE_RE, DRAW_DATASET_LEGACY_RE, DRAW_DATASET_CANONICAL_RE):
        match = pattern.match(text)
        if not match:
            continue
        preform = normalize_preform_token(match.group("preform"))
        index = int(str(match.group("index") or "0") or "0")
        if not preform or index <= 0:
            continue
        return {
            "preform": preform,
            "index": index,
            "draw_stem": canonical_draw_dataset_stem(preform, index),
        }
    return None


def is_zone_dataset_path(path: Path) -> bool:
    return bool(ZONE_DATASET_RE.match(path.stem))


def looks_like_dataset_snapshot_path(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".csv":
        return False
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            normalized_header = [str(item or "").strip() for item in header]
            if normalized_header != ["Parameter Name", "Value", "Units"]:
                return False
            for index, row in enumerate(reader):
                parameter_name = str((row or {}).get("Parameter Name", "")).strip()
                if parameter_name in {"=== ORDER PARAMETERS ===", "=== ZONE SNAPSHOT ==="}:
                    return True
                if index >= 40:
                    break
    except Exception:
        return False
    return False


def dataset_directory_for_draw_name(csv_name: str) -> Path:
    stem = Path(str(csv_name or "").strip()).stem
    identity = parse_draw_dataset_identity(stem)
    if identity:
        return DATASET_DIR / str(identity["preform"])
    return DATASET_DIR


def full_dataset_target_path(csv_name: str) -> Path:
    dataset_file = canonical_draw_dataset_filename(csv_name)
    return dataset_directory_for_draw_name(dataset_file) / dataset_file


def zone_dataset_target_path(csv_name: str, zone_number: int) -> Path:
    dataset_file = canonical_draw_dataset_filename(csv_name)
    identity = parse_draw_dataset_identity(Path(dataset_file).stem)
    draw_stem = str(identity["draw_stem"]) if identity else Path(dataset_file).stem
    zone_folder_name = f"{draw_stem}_Z{zone_number}"
    existing_dataset_path = resolve_dataset_csv_path(dataset_file)
    parent_dir = existing_dataset_path.parent if existing_dataset_path else dataset_directory_for_draw_name(dataset_file)
    return parent_dir / zone_folder_name / f"{zone_folder_name}.csv"


def list_dataset_csv_files(include_zone_files: bool = False) -> list[Path]:
    if not DATASET_DIR.exists():
        return []
    files = [
        path
        for path in DATASET_DIR.rglob("*.csv")
        if path.is_file()
        and path.name != "_conversion_audit.csv"
        and looks_like_dataset_snapshot_path(path)
    ]
    if not include_zone_files:
        files = [path for path in files if not is_zone_dataset_path(path)]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def list_recent_dataset_files(limit: int = 6) -> list[dict]:
    output = []
    for path in list_dataset_csv_files()[:limit]:
        stat = path.stat()
        output.append(
            {
                "name": path.name,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "size_kb": round(stat.st_size / 1024, 1),
            }
        )
    return output


def resolve_dataset_csv_path(csv_name: str, include_zone_files: bool = False) -> Path | None:
    dataset_file = os.path.basename(str(csv_name or "").strip())
    if not dataset_file:
        return None
    variants = draw_dataset_filename_variants(dataset_file)
    for candidate in variants:
        direct = DATASET_DIR / candidate
        if direct.exists() and direct.is_file() and (include_zone_files or not is_zone_dataset_path(direct)):
            return direct
        target = full_dataset_target_path(candidate)
        if target.exists() and target.is_file() and (include_zone_files or not is_zone_dataset_path(target)):
            return target
    matches = [
        path
        for path in list_dataset_csv_files(include_zone_files=include_zone_files)
        if path.name in variants
    ]
    if not matches:
        return None
    rank = {name: index for index, name in enumerate(variants)}
    matches.sort(key=lambda path: rank.get(path.name, len(rank)))
    return matches[0]


def analyze_log_file(log_name: str | None = None, sample_limit: int = 1600) -> dict:
    files = list_dashboard_log_files()
    if not files:
        return {
            "selected_file": "",
            "available_logs": [],
            "x_options": [],
            "numeric_columns": [],
            "rows": [],
            "display_labels": {},
            "sample_count": 0,
            "total_rows": 0,
        }
    by_name = {path.name: path for path in files}
    selected_path = by_name.get(str(log_name or "").strip(), files[0])
    rows, display_labels = load_log_csv_rows(selected_path)
    if not rows:
        return {
            "selected_file": selected_path.name,
            "available_logs": [path.name for path in files],
            "x_options": [],
            "numeric_columns": [],
            "rows": [],
            "display_labels": {},
            "sample_count": 0,
            "total_rows": 0,
        }

    def normalize_x_value(raw_value: object, fallback_index: int) -> tuple[float, str]:
        text_value = str(raw_value or "").strip()
        if not text_value:
            return float(fallback_index), "index"
        parsed_dt = parse_dt(text_value)
        if parsed_dt:
            return parsed_dt.timestamp(), "datetime"
        for pattern in ("%d/%m/%Y %H:%M:%S%f", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text_value, pattern).timestamp(), "datetime"
            except ValueError:
                continue
        numeric_value = to_float(text_value)
        if numeric_value is not None:
            return float(numeric_value), "numeric"
        return float(fallback_index), "index"

    headers = list(rows[0].keys())
    numeric_columns = []
    for column in headers:
        non_empty = [row.get(column, "") for row in rows[:400] if str(row.get(column, "")).strip()]
        if not non_empty:
            continue
        numeric_count = sum(1 for value in non_empty if str(value).replace(".", "", 1).replace("-", "", 1).isdigit())
        if numeric_count / max(1, len(non_empty)) >= 0.75:
            numeric_columns.append(column)

    sampled_rows = rows[:sample_limit]
    suggested_x = "Date/Time" if "Date/Time" in headers else ("Timestamp" if "Timestamp" in headers else headers[0])
    compact_rows = []
    x_series: dict[str, list[float]] = {column: [] for column in headers}
    x_display: dict[str, list[str]] = {column: [] for column in headers}
    x_kinds: dict[str, str] = {}
    for index, row in enumerate(sampled_rows):
        item = {"__index": index, "__x": str(row.get(suggested_x, "") or index)}
        for column in numeric_columns:
            item[column] = to_float(row.get(column))
        for column in headers:
            normalized_value, detected_kind = normalize_x_value(row.get(column, ""), index)
            x_series[column].append(normalized_value)
            x_display[column].append(str(row.get(column, "") or ""))
            x_kinds[column] = detected_kind if x_kinds.get(column) in (None, "index") else x_kinds[column]
            if x_kinds.get(column) is None:
                x_kinds[column] = detected_kind
            elif x_kinds[column] == "index" and detected_kind != "index":
                x_kinds[column] = detected_kind
        compact_rows.append(item)

    suggested_y = [column for column in numeric_columns if column != suggested_x][:4]
    length_candidates = [column for column in headers if "length" in str(column).lower()]
    return {
        "selected_file": selected_path.name,
        "available_logs": [path.name for path in files],
        "x_options": headers,
        "numeric_columns": numeric_columns,
        "rows": compact_rows,
        "display_labels": display_labels,
        "x_series": x_series,
        "x_display": x_display,
        "x_kinds": x_kinds,
        "sample_count": len(compact_rows),
        "total_rows": len(rows),
        "suggested_x": suggested_x,
        "suggested_y": suggested_y,
        "latest_modified": datetime.fromtimestamp(selected_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "length_column": length_candidates[0] if length_candidates else "",
    }


def load_coating_options() -> list[str]:
    config = read_json_dict(COATING_CONFIG)
    coatings = config.get("coatings", {})
    if not isinstance(coatings, dict):
        return []
    return dedupe_strings(list(coatings.keys()))


def sort_order_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    def sort_key(row: dict[str, str]) -> datetime:
        return parse_dt(row.get("Timestamp")) or datetime.min

    return sorted(rows, key=sort_key, reverse=True)


def fmt_pm(value: str | None, tol: str | None, unit: str = "µm") -> str:
    num = to_float(value)
    tol_num = to_float(tol)
    if num <= 0:
        return ""
    if tol_num > 0:
        return f"{num:g} ± {tol_num:g} {unit}"
    return f"{num:g} {unit}"


def format_order_for_ui(row: dict[str, str], index: int) -> dict:
    geometry = (row.get(GEOMETRY_COL) or "Unspecified").strip() or "Unspecified"
    status = (row.get("Status") or "Unknown").strip() or "Unknown"
    return {
        "index": index,
        "preform": row.get("Preform Number", ""),
        "project": row.get(PROJECTS_COL, ""),
        "opener": row.get("Order Opener", ""),
        "status": status,
        "priority": row.get("Priority", "Normal"),
        "timestamp": row.get("Timestamp", ""),
        "next_draw": row.get("Next Planned Draw Date", "") or row.get("Desired Date", ""),
        "desired_date": row.get("Desired Date", ""),
        "geometry": geometry,
        "length": row.get(LENGTH_COL, "") or "0",
        "good_zones": row.get(GOOD_ZONES_COL, "") or "0",
        "notes": row.get("Notes", ""),
        "main_coating": row.get("Main Coating", ""),
        "secondary_coating": row.get("Secondary Coating", ""),
        "main_temp": row.get(MAIN_TEMP_COL, ""),
        "secondary_temp": row.get(SECONDARY_TEMP_COL, ""),
        "fiber_spec": fmt_pm(row.get("Fiber Diameter (µm)"), row.get(FIBER_TOL_COL)),
        "main_spec": fmt_pm(row.get("Main Coating Diameter (µm)"), row.get(MAIN_TOL_COL)),
        "secondary_spec": fmt_pm(row.get("Secondary Coating Diameter (µm)"), row.get(SECONDARY_TOL_COL)),
        "tiger_cut": row.get(TIGER_CUT_COL, ""),
        "oct_f2f": row.get(OCT_F2F_COL, ""),
    }


def build_schedule_description(order: dict[str, str], order_index: int, preform_number: str) -> str:
    geometry = str(order.get(GEOMETRY_COL, "")).strip()
    priority = str(order.get("Priority", "Normal")).strip()
    selected_project = str(order.get(PROJECTS_COL, "")).strip()
    length_required = str(order.get(LENGTH_COL, "")).strip()
    good_zones = str(order.get(GOOD_ZONES_COL, "")).strip()
    desc_lines = [
        f"ORDER #{order_index} | Priority: {priority}",
        f"Fiber: {selected_project} | Geometry: {geometry} | Preform: {preform_number}",
        f"Required Length: {length_required} m | Good Zones Count: {good_zones}",
    ]
    diameter_bits = []
    fiber_spec = fmt_pm(order.get("Fiber Diameter (µm)"), order.get(FIBER_TOL_COL))
    main_spec = fmt_pm(order.get("Main Coating Diameter (µm)"), order.get(MAIN_TOL_COL))
    secondary_spec = fmt_pm(order.get("Secondary Coating Diameter (µm)"), order.get(SECONDARY_TOL_COL))
    if fiber_spec:
        diameter_bits.append(f"Fiber {fiber_spec}")
    if main_spec:
        diameter_bits.append(f"Coat1 {main_spec}")
    if secondary_spec:
        diameter_bits.append(f"Coat2 {secondary_spec}")
    if diameter_bits:
        desc_lines.append("Diameters: " + " | ".join(diameter_bits))
    if geometry == "TIGER - PM" and to_float(order.get(TIGER_CUT_COL)) > 0:
        desc_lines.append(f"Tiger Cut: {to_float(order.get(TIGER_CUT_COL)):.1f}%")
    if geometry == "Octagonal" and to_float(order.get(OCT_F2F_COL)) > 0:
        desc_lines.append(f"Oct F2F: {to_float(order.get(OCT_F2F_COL)):.2f} mm")
    if to_float(order.get(MAIN_TEMP_COL)) > 0:
        desc_lines.append(f"Main Coat Temp: {to_float(order.get(MAIN_TEMP_COL)):.0f}°C")
    if to_float(order.get(SECONDARY_TEMP_COL)) > 0:
        desc_lines.append(f"Sec Coat Temp: {to_float(order.get(SECONDARY_TEMP_COL)):.0f}°C")
    notes = str(order.get("Notes", "")).strip()
    if notes:
        desc_lines.append(f"Notes: {notes}")
    return " | ".join([line for line in desc_lines if line.strip()])


def summarize_order_draw() -> dict:
    raw_orders = sort_order_rows(read_csv_rows(DRAW_ORDERS))
    orders = [format_order_for_ui(row, index) for index, row in enumerate(raw_orders)]
    projects = dedupe_strings([row.get(PROJECTS_COL, "") for row in read_csv_rows(PROJECTS_FIBER)])
    templates = read_csv_rows(PROJECTS_TEMPLATES)
    templates_by_project = {}
    for row in templates:
        project = str(row.get(PROJECTS_COL, "")).strip()
        if project:
            templates_by_project[project] = {field: row.get(field, "") for field in TEMPLATE_FIELDS}
    sap_items = read_csv_rows(SAP_RODS_INVENTORY)
    status_counts: dict[str, int] = {}
    geometry_counts: dict[str, int] = {}
    pending_orders = []
    scheduled_orders = []
    completed_orders = []
    for row in orders:
        status = row["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        geometry = row["geometry"]
        geometry_counts[geometry] = geometry_counts.get(geometry, 0) + 1
        if status == "Pending":
            pending_orders.append(row)
        elif status in {"Scheduled", "In Progress"}:
            scheduled_orders.append(row)
        else:
            completed_orders.append(row)
    sap_sets = next(
        (
            row
            for row in sap_items
            if str(row.get("Item") or row.get("Item Name") or "").strip().lower() == "sap rods set"
        ),
        sap_items[0] if sap_items else {},
    )
    sap_count = to_float(sap_sets.get("Count"))
    return {
        "status_counts": status_counts,
        "geometry_series": [{"label": key, "value": value} for key, value in sorted(geometry_counts.items(), key=lambda item: item[1], reverse=True)[:6]],
        "all_orders": orders[:18],
        "pending_orders": pending_orders,
        "scheduled_orders": scheduled_orders,
        "completed_orders": completed_orders[:18],
        "queue_counts": {
            "pending": len(pending_orders),
            "scheduled": len(scheduled_orders),
            "history": len(completed_orders),
        },
        "active_count": len(pending_orders) + len(scheduled_orders),
        "project_count": len(projects),
        "template_count": len(templates),
        "sap_item_count": len(sap_items),
        "project_names": projects,
        "template_project_names": sorted(templates_by_project.keys()),
        "templates_by_project": templates_by_project,
        "coating_options": load_coating_options(),
        "form_config": {
            "geometry_options": ORDER_DRAW_GEOMETRY_OPTIONS,
        },
        "sap_summary": {
            "item": sap_sets.get("Item") or sap_sets.get("Item Name") or "SAP Rods Set",
            "count": sap_count,
            "units": sap_sets.get("Units", "sets"),
            "last_updated": sap_sets.get("Last Updated", ""),
            "notes": sap_sets.get("Notes", ""),
            "low": sap_count < 1,
        },
    }


def decrement_sap_rods_set_for_panda_draw(source_draw: str) -> tuple[bool, str]:
    when_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_label = str(source_draw or "").strip() or "Unnamed draw"
    default_fieldnames = ["Item", "Count", "Units", "Last Updated", "Notes"]
    with hold_request_lock(SAP_RODS_INVENTORY):
        rows = read_csv_rows(SAP_RODS_INVENTORY)
        fieldnames = read_csv_fieldnames(SAP_RODS_INVENTORY) or default_fieldnames
        fieldnames = fieldnames + [field for field in default_fieldnames if field not in fieldnames]
        target_row = None
        for row in rows:
            item_name = str(row.get("Item") or row.get("Item Name") or "").strip().lower()
            if item_name == "sap rods set":
                target_row = row
                break
        if target_row is None:
            target_row = {
                "Item": "SAP Rods Set",
                "Count": 0,
                "Units": "sets",
                "Last Updated": when_str,
                "Notes": "Auto-added row",
            }
            rows.append(target_row)
        current_count = max(0, int(round(to_float(target_row.get("Count")))))
        note_prefix = str(target_row.get("Notes", "")).strip()
        if current_count < 1:
            warning_note = f"[{when_str}] Attempted decrement for PANDA - PM draw {source_label} but Count was 0."
            target_row["Item"] = str(target_row.get("Item") or target_row.get("Item Name") or "SAP Rods Set").strip() or "SAP Rods Set"
            target_row["Count"] = current_count
            target_row["Units"] = str(target_row.get("Units", "")).strip() or "sets"
            target_row["Last Updated"] = when_str
            target_row["Notes"] = f"{note_prefix}\n{warning_note}".strip() if note_prefix else warning_note
            if "Item Name" in fieldnames and "Item Name" in target_row:
                target_row["Item Name"] = target_row["Item"]
            write_csv_rows(SAP_RODS_INVENTORY, rows, fieldnames)
            return False, "SAP rods inventory is empty, so no set was deducted."
        target_row["Item"] = str(target_row.get("Item") or target_row.get("Item Name") or "SAP Rods Set").strip() or "SAP Rods Set"
        target_row["Count"] = current_count - 1
        target_row["Units"] = str(target_row.get("Units", "")).strip() or "sets"
        target_row["Last Updated"] = when_str
        success_note = f"[{when_str}] -1 set reserved for PANDA - PM draw {source_label}. New Count={current_count - 1}."
        target_row["Notes"] = f"{note_prefix}\n{success_note}".strip() if note_prefix else success_note
        if "Item Name" in fieldnames and "Item Name" in target_row:
            target_row["Item Name"] = target_row["Item"]
        write_csv_rows(SAP_RODS_INVENTORY, rows, fieldnames)
    return True, "SAP rods auto-reserved for this PANDA - PM draw."


def summarize_dashboard() -> dict:
    draws = summarize_draw_orders()
    schedule = summarize_schedule()
    parts = summarize_part_orders()
    inventory = summarize_inventory()
    log_csvs = list_dashboard_log_files()
    dataset_csvs = list_dataset_csv_files()
    dataset_files = list_recent_dataset_files()
    log_files = [
        {
            "name": path.name,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "size_kb": round(path.stat().st_size / 1024, 1),
        }
        for path in log_csvs[:6]
    ]
    report_files = list_recent_files(REPORTS_DIR, suffixes=(".csv", ".json", ".pdf", ".log"))
    return {
        "metrics": [
            {"label": "Dataset CSVs", "value": len(dataset_csvs)},
            {"label": "Log CSVs", "value": len(list(LOGS_DIR.glob("*.csv"))) if LOGS_DIR.exists() else 0},
            {"label": "Active Draws", "value": draws["in_progress"]},
            {"label": "Open Part Orders", "value": len(parts["open_orders"])},
        ],
        "draw_status_series": [{"label": key, "value": value} for key, value in draws["status_counts"].items()],
        "schedule_series": schedule["daily_series"],
        "inventory_series": inventory["pressure_series"],
        "dataset_files": dataset_files,
        "log_files": log_files,
        "report_files": report_files,
        "available_logs": [path.name for path in log_csvs],
        "latest_log": log_csvs[0].name if log_csvs else "",
        "dataset_csvs": [path.name for path in dataset_csvs[:18]],
        "latest_dataset": dataset_csvs[0].name if dataset_csvs else "",
    }


def summarize_diagnostics() -> dict:
    ensure_app_weekly_full_backup()
    tracked_paths = current_tracked_paths()
    defaults = tracked_path_defaults()
    container_logger_status = current_container_logger_status()
    path_rows = []
    ready_count = 0
    for item, path in tracked_paths:
        key = str(item["key"])
        label = str(item["label"])
        exists = path.exists()
        readable = exists and os.access(path, os.R_OK)
        writable_target = path if exists else path.parent
        writable = writable_target.exists() and os.access(writable_target, os.W_OK)
        healthy = exists and readable and writable
        ready_count += int(healthy)
        path_rows.append(
            {
                "key": key,
                "label": label,
                "kind": item["kind"],
                "status": "READY" if healthy else "BLOCKED",
                "exists": exists,
                "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if exists else "missing",
                "path": str(path),
                "default_path": str(defaults[key]),
                "is_override": path != defaults[key],
            }
        )
    schema_checks = [
        {"csv": "orders", "path": DRAW_ORDERS, "required": ("Status", "Priority", "Preform Number", "Fiber Project")},
        {"csv": "parts_orders", "path": PART_ORDERS, "required": ("Status", "Part Name", "Project Name")},
        {"csv": "schedule", "path": TOWER_SCHEDULE, "required": ("Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence")},
    ]
    schema_rows = []
    for check in schema_checks:
        rows = read_csv_rows(check["path"])
        header = rows[0].keys() if rows else []
        missing = [column for column in check["required"] if column not in header]
        schema_rows.append(
            {
                "csv": check["csv"],
                "ok": not missing,
                "rows": len(rows),
                "missing_columns": ", ".join(missing),
            }
        )
    dataset_files = list_dataset_csv_files()
    log_files = list_csv_files(LOGS_DIR)
    path_ok = ready_count == len(tracked_paths)
    schema_ok = all(item["ok"] for item in schema_rows)
    backup_snapshots = len(list_backup_directories())
    full_backup_snapshots = len(list_backup_directories("full_backup_"))
    latest_full_backup = latest_backup_snapshot("full_backup_")
    report_file_count = len(list(REPORTS_DIR.rglob("*"))) if REPORTS_DIR.exists() else 0
    logs_path = next((item for item in path_rows if item["key"] == "logs_dir"), None)
    reports_path = next((item for item in path_rows if item["key"] == "reports_dir"), None)
    health_checks = [
        {
            "key": "paths",
            "label": "Required paths",
            "ok": path_ok,
            "detail": f"{ready_count}/{len(tracked_paths)} tracked paths are ready for read/write work.",
        },
        {
            "key": "schema",
            "label": "CSV schema",
            "ok": schema_ok,
            "detail": f"{sum(1 for item in schema_rows if item['ok'])}/{len(schema_rows)} required CSV structures are complete.",
        },
        {
            "key": "datasets",
            "label": "Dataset workspace",
            "ok": bool(dataset_files),
            "detail": f"{len(dataset_files)} dataset CSVs are available in the draw workspace.",
        },
        {
            "key": "logs",
            "label": "Logs workspace",
            "ok": bool(logs_path and logs_path["status"] == "READY") and bool(log_files),
            "detail": f"{len(log_files)} log CSVs are available in the logs workspace.",
        },
        {
            "key": "backups",
            "label": "Backup coverage",
            "ok": backup_snapshots > 0,
            "detail": f"{backup_snapshots} backup snapshots are available for recovery.",
        },
        {
            "key": "reports",
            "label": "Report output lane",
            "ok": bool(reports_path and reports_path["status"] == "READY"),
            "detail": f"{report_file_count} report files are reachable in the report center.",
        },
        {
            "key": "container_logger",
            "label": "Container logger",
            "ok": str(container_logger_status.get("state", "")).strip() == "running",
            "detail": str(container_logger_status.get("message", "")).strip() or "Container logger status unavailable.",
        },
    ]
    passed_checks = sum(1 for item in health_checks if item["ok"])
    overall_ok = passed_checks == len(health_checks)
    return {
        "ready_count": ready_count,
        "tracked_count": len(tracked_paths),
        "path_rows": path_rows,
        "schema_rows": schema_rows,
        "backup_snapshots": backup_snapshots,
        "report_file_count": report_file_count,
        "dataset_count": len(dataset_files),
        "log_count": len(log_files),
        "override_count": sum(1 for item in path_rows if item["is_override"]),
        "full_backup_count": full_backup_snapshots,
        "latest_full_backup": latest_full_backup,
        "full_backup_policy_label": FULL_BACKUP_POLICY_LABEL,
        "container_logger": container_logger_status,
        "health_checks": health_checks,
        "passed_checks": passed_checks,
        "total_checks": len(health_checks),
        "overall_ok": overall_ok,
        "overall_label": "All core diagnostics are green." if overall_ok else "Diagnostics need attention.",
        "overall_detail": (
            "Paths, schemas, datasets, logs, backups, and report output are all ready."
            if overall_ok
            else "At least one required diagnostics lane is blocked, missing, or incomplete."
        ),
    }


def latest_csv_row(path: Path) -> dict[str, str]:
    rows = read_csv_rows(path)
    return rows[-1] if rows else {}


def load_consumables_temp_setpoints(latest_temps: dict[str, str] | None = None) -> dict[str, float]:
    latest_temps = latest_temps or {}
    heater_map = read_json_dict(HEATER_CONFIG)
    setpoints: dict[str, float] = {}
    for field in CONSUMABLE_TEMP_FIELDS:
        default_value = round(to_float(latest_temps.get(field)), 2)
        config_key = CONSUMABLE_TEMP_SETPOINT_KEYS[field]
        csv_key = consumable_temp_setpoint_csv_field(field)
        raw_value = heater_map.get(
            config_key,
            latest_temps.get(csv_key, heater_map.get(field, default_value)),
        )
        setpoints[field] = round(to_float(raw_value), 2)
    return setpoints


def normalize_container_sensor_column(value: object, label: str) -> str:
    text = str(value or "").strip().lower()
    if text in CONTAINER_SENSOR_OPTIONS:
        return text
    return CONTAINER_SENSOR_DEFAULTS.get(label, "tank1")


def normalize_container_config(raw: dict | None) -> dict[str, dict[str, object]]:
    source = raw if isinstance(raw, dict) else {}
    cleaned: dict[str, dict[str, object]] = {}
    for label in ["A", "B", "C", "D"]:
        current = source.get(label, {})
        current = current if isinstance(current, dict) else {}
        diameter_mm = round(to_float(current.get("diameter_mm", current.get("diameter", DEFAULT_CONTAINER_DIAMETER_MM))), 2)
        fill_height_mm = round(
            to_float(
                current.get(
                    "fill_height_mm",
                    current.get("height_mm", current.get("working_height_mm", DEFAULT_CONTAINER_FILL_HEIGHT_MM)),
                )
            ),
            2,
        )
        cleaned[label] = {
            "type": str(current.get("type", "")).strip(),
            "sensor_column": normalize_container_sensor_column(current.get("sensor_column", current.get("sensor")), label),
            "diameter_mm": diameter_mm if diameter_mm > 0 else DEFAULT_CONTAINER_DIAMETER_MM,
            "fill_height_mm": fill_height_mm if fill_height_mm > 0 else DEFAULT_CONTAINER_FILL_HEIGHT_MM,
        }
    return cleaned


def coating_density_to_kg_per_l(raw_density: object) -> float:
    density = to_float(raw_density)
    if density <= 0:
        return DEFAULT_CONTAINER_DENSITY_KG_PER_L
    if density > 10000:
        return round(density / 1_000_000.0, 4)
    if density > 10:
        return round(density / 1000.0, 4)
    return round(density, 4)


def cylinder_volume_liters(diameter_mm: object, fill_height_mm: object) -> float:
    diameter = to_float(diameter_mm)
    height = to_float(fill_height_mm)
    if diameter <= 0 or height <= 0:
        return 0.0
    radius_mm = diameter / 2.0
    volume_mm3 = math.pi * (radius_mm ** 2) * height
    return round(volume_mm3 / 1_000_000.0, 2)


def read_container_live_feed(path: Path) -> dict[str, object]:
    rows = read_csv_rows(path)
    latest: dict[str, str] = {}
    normalized: dict[str, object] = {}
    for candidate in reversed(rows):
        current = {str(key or "").strip().lower(): value for key, value in candidate.items()}
        timestamp_value = str(current.get("timestamp") or current.get("updated_at") or "").strip()
        has_percent_fields = any(sensor in current for sensor in CONTAINER_SENSOR_OPTIONS)
        has_percent_sample = any(str(current.get(sensor, "")).strip() for sensor in CONTAINER_SENSOR_OPTIONS)
        has_legacy_fields = any(f"{label}_level_kg" in candidate or f"{label}_type" in candidate for label in ["A", "B", "C", "D"])
        has_legacy_sample = any(
            str(candidate.get(f"{label}_level_kg", "")).strip() or str(candidate.get(f"{label}_type", "")).strip()
            for label in ["A", "B", "C", "D"]
        )
        if timestamp_value or has_percent_fields or has_percent_sample or has_legacy_fields or has_legacy_sample:
            latest = candidate
            normalized = current
            break
    if not latest:
        return {"mode": "empty", "timestamp": "", "percents": {}, "levels": {}, "types": {}, "raw": {}, "age_seconds": None, "sensor_states": {}}
    timestamp_text = str(normalized.get("timestamp") or normalized.get("updated_at") or "").strip()
    parsed_timestamp = parse_dt(timestamp_text)
    age_seconds: float | None = None
    if parsed_timestamp is not None:
        age_seconds = round(max(0.0, (datetime.now() - parsed_timestamp).total_seconds()), 2)
    is_stale = age_seconds is not None and age_seconds > CONTAINER_FEED_STALE_SECONDS
    if any(sensor in normalized for sensor in CONTAINER_SENSOR_OPTIONS):
        sensor_states: dict[str, str] = {}
        sensor_timestamps: dict[str, str] = {}
        percents: dict[str, float] = {}
        display_percents: dict[str, float] = {}
        for sensor in CONTAINER_SENSOR_OPTIONS:
            sensor_value: float | None = None
            sensor_age: float | None = None
            sensor_timestamp_text = ""
            recent_values: list[float] = []
            for candidate in reversed(rows):
                current = {str(key or "").strip().lower(): value for key, value in candidate.items()}
                if sensor not in current:
                    continue
                raw_value = str(current.get(sensor, "")).strip()
                if not raw_value:
                    continue
                parsed_value = to_float(raw_value)
                if parsed_value is None:
                    continue
                sensor_timestamp_text = str(current.get("timestamp") or current.get("updated_at") or "").strip()
                parsed_sensor_ts = parse_dt(sensor_timestamp_text)
                if parsed_sensor_ts is not None:
                    sensor_age = round(max(0.0, (datetime.now() - parsed_sensor_ts).total_seconds()), 2)
                bounded_value = round(max(0.0, min(100.0, parsed_value)), 2)
                if sensor_value is None:
                    sensor_value = bounded_value
                if sensor_age is None or sensor_age <= CONTAINER_FEED_STALE_SECONDS:
                    recent_values.append(bounded_value)
                    if len(recent_values) >= CONTAINER_FEED_SMOOTHING_SAMPLES:
                        break
            if sensor_value is None:
                sensor_states[sensor] = "disconnected"
                continue
            if sensor_age is not None and sensor_age > CONTAINER_FEED_STALE_SECONDS:
                sensor_states[sensor] = "stale"
                continue
            percents[sensor] = sensor_value
            display_percents[sensor] = round(sum(recent_values) / len(recent_values), 2) if recent_values else sensor_value
            sensor_states[sensor] = "live"
            if sensor_timestamp_text:
                sensor_timestamps[sensor] = sensor_timestamp_text
        if not percents:
            return {
                "mode": "stale" if is_stale else "disconnected",
                "timestamp": timestamp_text,
                "percents": {},
                "levels": {},
                "types": {},
                "raw": latest,
                "age_seconds": age_seconds,
                "sensor_states": sensor_states,
            }
        return {
            "mode": "percent",
            "timestamp": timestamp_text,
            "percents": percents,
            "display_percents": display_percents,
            "levels": {},
            "types": {},
            "raw": latest,
            "age_seconds": age_seconds,
            "sensor_states": sensor_states,
            "sensor_timestamps": sensor_timestamps,
        }
    has_live_legacy_sample = any(
        str(latest.get(f"{label}_level_kg", "")).strip() or str(latest.get(f"{label}_type", "")).strip()
        for label in ["A", "B", "C", "D"]
    )
    if not has_live_legacy_sample:
        return {
            "mode": "disconnected",
            "timestamp": timestamp_text,
            "percents": {},
            "levels": {},
            "types": {},
            "raw": latest,
            "age_seconds": age_seconds,
            "sensor_states": {},
        }
    if is_stale:
        return {
            "mode": "stale",
            "timestamp": timestamp_text,
            "percents": {},
            "levels": {},
            "types": {},
            "raw": latest,
            "age_seconds": age_seconds,
            "sensor_states": {},
        }
    levels = {label: round(to_float(latest.get(f"{label}_level_kg")), 2) for label in ["A", "B", "C", "D"]}
    types = {label: str(latest.get(f"{label}_type", "")).strip() for label in ["A", "B", "C", "D"]}
    return {
        "mode": "legacy",
        "timestamp": timestamp_text,
        "percents": {},
        "levels": levels,
        "types": types,
        "raw": latest,
        "age_seconds": age_seconds,
        "sensor_states": {},
    }


def container_feed_signature(feed: dict[str, object] | None) -> str:
    current = feed if isinstance(feed, dict) else {}
    mode = str(current.get("mode", "")).strip()
    payload: dict[str, object] = {
        "mode": mode,
        "timestamp": str(current.get("timestamp", "")).strip(),
    }
    if mode == "percent":
        payload.update(
            {
                sensor: round(to_float((current.get("percents", {}) or {}).get(sensor)), 2)
                for sensor in CONTAINER_SENSOR_OPTIONS
            }
        )
        payload["sensor_states"] = {
            sensor: str((current.get("sensor_states", {}) or {}).get(sensor, "")).strip()
            for sensor in CONTAINER_SENSOR_OPTIONS
        }
    else:
        for label in ["A", "B", "C", "D"]:
            payload[f"{label}_level"] = round(to_float((current.get("levels", {}) or {}).get(label)), 2)
            payload[f"{label}_type"] = str((current.get("types", {}) or {}).get(label, "")).strip()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def normalize_container_snapshot(raw: dict | None) -> dict[str, object]:
    source = raw if isinstance(raw, dict) else {}
    raw_containers = source.get("containers")
    if not isinstance(raw_containers, dict):
        raw_containers = {
            label: source.get(label, {})
            for label in ["A", "B", "C", "D"]
            if isinstance(source.get(label, {}), dict)
        }
    containers: dict[str, dict[str, object]] = {}
    for label in ["A", "B", "C", "D"]:
        current = raw_containers.get(label, {})
        current = current if isinstance(current, dict) else {}
        containers[label] = {
            "level": round(to_float(current.get("level", current.get("level_kg", 0.0))), 2),
            "fill_percent": round(to_float(current.get("fill_percent", 0.0)), 2),
            "raw_level": round(to_float(current.get("raw_level", current.get("raw_level_kg", current.get("level", current.get("level_kg", 0.0))))), 2),
            "raw_fill_percent": round(to_float(current.get("raw_fill_percent", current.get("fill_percent", 0.0))), 2),
            "type": str(current.get("type", "")).strip(),
            "updated_at": str(current.get("updated_at", "")).strip(),
        }
    return {
        "feed_signature": str(source.get("_feed_signature") or source.get("feed_signature") or "").strip(),
        "updated_at": str(source.get("_updated_at") or source.get("updated_at") or "").strip(),
        "containers": containers,
    }


def build_container_snapshot_payload(container_cards: list[dict], feed_signature: str, updated_at: str) -> dict[str, object]:
    return {
        "_feed_signature": str(feed_signature or "").strip(),
        "_updated_at": str(updated_at or "").strip(),
        "containers": {
            str(item.get("label", "")).strip(): {
                "level": round(to_float(item.get("level")), 2),
                "fill_percent": round(to_float(item.get("fill_percent")), 2),
                "raw_level": round(to_float(item.get("raw_level", item.get("level"))), 2),
                "raw_fill_percent": round(to_float(item.get("raw_fill_percent", item.get("fill_percent"))), 2),
                "type": str(item.get("type", "")).strip(),
                "updated_at": str(item.get("updated_at", "")).strip(),
            }
            for item in container_cards
            if str(item.get("label", "")).strip()
        },
    }


def auto_adjust_warehouse_from_container_refill(
    feed: dict[str, object],
    container_cards: list[dict],
    stock_map: dict | None,
) -> tuple[dict[str, float], list[dict[str, object]]]:
    next_stock_map = {str(key): round(to_float(value), 2) for key, value in (stock_map or {}).items()}
    snapshot = normalize_container_snapshot(read_json_value(CONTAINER_SNAPSHOT, {}))
    signature = container_feed_signature(feed)
    updated_at = str(feed.get("timestamp", "")).strip() if isinstance(feed, dict) else ""
    current_snapshot = build_container_snapshot_payload(container_cards, signature, updated_at)
    if not signature:
        write_json_value(CONTAINER_SNAPSHOT, current_snapshot)
        return next_stock_map, []
    if not snapshot.get("feed_signature"):
        write_json_value(CONTAINER_SNAPSHOT, current_snapshot)
        return next_stock_map, []
    if snapshot.get("feed_signature") == signature:
        return next_stock_map, []

    events: list[dict[str, object]] = []
    previous_containers = snapshot.get("containers", {})
    previous_containers = previous_containers if isinstance(previous_containers, dict) else {}
    for item in container_cards:
        label = str(item.get("label", "")).strip()
        kind = str(item.get("type", "")).strip()
        previous = previous_containers.get(label, {})
        previous = previous if isinstance(previous, dict) else {}
        previous_type = str(previous.get("type", "")).strip()
        if not label or not kind or not previous_type or previous_type != kind:
            continue
        current_level = round(to_float(item.get("raw_level", item.get("level"))), 2)
        previous_level = round(to_float(previous.get("raw_level", previous.get("level"))), 2)
        current_fill = round(to_float(item.get("raw_fill_percent", item.get("fill_percent"))), 2)
        previous_fill = round(to_float(previous.get("raw_fill_percent", previous.get("fill_percent"))), 2)
        delta_kg = round(current_level - previous_level, 2)
        delta_fill_percent = round(current_fill - previous_fill, 2)
        if delta_kg <= AUTO_CONTAINER_REFILL_MIN_KG or delta_fill_percent < AUTO_CONTAINER_REFILL_MIN_PERCENT:
            continue
        full_capacity_kg = 0.0
        if current_fill > 0:
            full_capacity_kg = round((current_level / current_fill) * 100.0, 2)
        if full_capacity_kg > 0 and delta_kg > full_capacity_kg * 1.05:
            continue
        previous_warehouse = round(to_float(next_stock_map.get(kind)), 2)
        next_warehouse = round(max(0.0, previous_warehouse - delta_kg), 2)
        if abs(next_warehouse - previous_warehouse) < 0.01:
            continue
        next_stock_map[kind] = next_warehouse
        events.append(
            {
                "label": label,
                "type": kind,
                "delta_kg": delta_kg,
                "previous_warehouse_kg": previous_warehouse,
                "next_warehouse_kg": next_warehouse,
            }
        )

    if events:
        write_json_value(COATING_STOCK, next_stock_map)
    write_json_value(CONTAINER_SNAPSHOT, current_snapshot)
    return next_stock_map, events


def known_consumables_coating_types(
    stock_map: dict | None = None,
    coating_config: dict | None = None,
    latest_containers: dict[str, str] | None = None,
) -> list[str]:
    known: set[str] = set()

    def add_type(value: object) -> None:
        text = str(value or "").strip()
        if text:
            known.add(text)

    for key in (stock_map or {}).keys():
        add_type(key)
    for key in ((coating_config or {}).get("coatings", {}) or {}).keys():
        add_type(key)
    container_defaults = read_json_dict(CONTAINER_CONFIG)
    latest_containers = latest_containers or {}
    for label in ["A", "B", "C", "D"]:
        add_type(latest_containers.get(f"{label}_type"))
        add_type((container_defaults.get(label) or {}).get("type"))
    for row in read_csv_rows(DRAW_ORDERS):
        add_type(row.get("Main Coating"))
        add_type(row.get("Secondary Coating"))
    for row in read_csv_rows(PROJECTS_TEMPLATES):
        add_type(row.get("Main Coating"))
        add_type(row.get("Secondary Coating"))
    for path in list_dataset_csv_files():
        for row in read_csv_rows(path):
            param = str(row.get("Parameter Name", "")).strip()
            if param not in {
                "Order__Main Coating",
                "Order__Secondary Coating",
                "Process__Primary Coating",
                "Process__Secondary Coating",
            }:
                continue
            add_type(row.get("Value"))
    return sorted(known, key=str.lower)


def read_consumables_inventory_meta() -> dict[str, dict[str, float]]:
    raw = read_json_value(COATING_INVENTORY_META, {})
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict[str, float]] = {}
    for label, value in raw.items():
        key = str(label or "").strip()
        if not key:
            continue
        if isinstance(value, dict):
            cleaned[key] = {
                "min_stock_kg": round(to_float(value.get("min_stock_kg", DEFAULT_COATING_MIN_STOCK_KG)), 2),
            }
        else:
            cleaned[key] = {
                "min_stock_kg": round(to_float(value), 2),
            }
    return cleaned


def summarize_consumables() -> dict:
    latest_containers = read_container_live_feed(TOWER_CONTAINERS)
    latest_temps = latest_csv_row(TOWER_TEMPS)
    stock_map = read_json_value(COATING_STOCK, {})
    inventory_meta = read_consumables_inventory_meta()
    dies_map = read_json_value(DIES_CONFIG, {})
    temp_setpoints = load_consumables_temp_setpoints(latest_temps)
    coating_config = read_json_value(COATING_CONFIG, {})
    coating_definitions = coating_config.get("coatings", {}) if isinstance(coating_config, dict) else {}
    container_defaults = normalize_container_config(read_json_dict(CONTAINER_CONFIG))
    container_logger_status = current_container_logger_status()
    container_feed_mode = str(latest_containers.get("mode", "")).strip() or "empty"
    container_feed_is_live = container_feed_mode in {"percent", "legacy"}
    argon_rows = read_csv_rows(ARGON_MONTHLY_REPORT)
    container_cards = []
    low_count = 0
    type_counts: dict[str, float] = {}
    latest_container_type_fields: dict[str, str] = {}
    for label in ["A", "B", "C", "D"]:
        defaults = container_defaults.get(label, {})
        kind = str((latest_containers.get("types", {}) or {}).get(label, "")).strip() or str(defaults.get("type", "")).strip()
        sensor_column = str(defaults.get("sensor_column", CONTAINER_SENSOR_DEFAULTS.get(label, "tank1"))).strip() or CONTAINER_SENSOR_DEFAULTS.get(label, "tank1")
        diameter_mm = round(to_float(defaults.get("diameter_mm", DEFAULT_CONTAINER_DIAMETER_MM)), 2)
        fill_height_mm = round(to_float(defaults.get("fill_height_mm", DEFAULT_CONTAINER_FILL_HEIGHT_MM)), 2)
        density_kg_per_l = coating_density_to_kg_per_l((coating_definitions.get(kind, {}) or {}).get("Density", ""))
        full_volume_l = cylinder_volume_liters(diameter_mm, fill_height_mm)
        sensor_state = str((latest_containers.get("sensor_states", {}) or {}).get(sensor_column, "")).strip()
        if latest_containers.get("mode") == "percent":
            raw_fill_percent = round(to_float((latest_containers.get("percents", {}) or {}).get(sensor_column)), 2)
            fill_percent = round(
                to_float((latest_containers.get("display_percents", {}) or {}).get(sensor_column, raw_fill_percent)),
                2,
            )
            volume_l = round(full_volume_l * (fill_percent / 100.0), 2)
            level = round(volume_l * density_kg_per_l, 2)
            raw_volume_l = round(full_volume_l * (raw_fill_percent / 100.0), 2)
            raw_level = round(raw_volume_l * density_kg_per_l, 2)
            current_live_state = sensor_state or "live"
        elif latest_containers.get("mode") == "legacy":
            level = round(to_float((latest_containers.get("levels", {}) or {}).get(label)), 2)
            volume_l = round(level / density_kg_per_l, 2) if density_kg_per_l > 0 else 0.0
            fill_percent = round((volume_l / full_volume_l) * 100.0, 2) if full_volume_l > 0 else 0.0
            raw_level = level
            raw_fill_percent = fill_percent
            current_live_state = "live"
        else:
            fill_percent = 0.0
            volume_l = 0.0
            level = 0.0
            raw_level = 0.0
            raw_fill_percent = 0.0
            current_live_state = container_feed_mode
        is_low = container_feed_is_live and (fill_percent <= DEFAULT_CONTAINER_LOW_PERCENT or level < 1.0)
        if is_low:
            low_count += 1
        if container_feed_is_live and level > 0:
            type_counts[kind or f"Container {label}"] = type_counts.get(kind or f"Container {label}", 0.0) + level
        latest_container_type_fields[f"{label}_type"] = kind
        container_cards.append(
            {
                "label": label,
                "level": round(level, 2),
                "type": kind or "Unassigned",
                "low": is_low,
                "updated_at": str(latest_containers.get("timestamp", "")).strip(),
                "fill_percent": round(fill_percent, 2),
                "raw_fill_percent": round(raw_fill_percent, 2),
                "volume_l": round(volume_l, 2),
                "raw_level": round(raw_level, 2),
                "sensor_column": sensor_column,
                "diameter_mm": diameter_mm,
                "fill_height_mm": fill_height_mm,
                "density_kg_per_l": density_kg_per_l,
                "live_state": current_live_state,
            }
        )
    stock_map, container_refill_events = auto_adjust_warehouse_from_container_refill(latest_containers, container_cards, stock_map)
    known_coatings = known_consumables_coating_types(stock_map, coating_config, latest_container_type_fields)
    temp_holders = []
    for key, label in [
        ("die_holder_primary_c", "Primary holder"),
        ("die_holder_secondary_c", "Secondary holder"),
    ]:
        value = to_float(latest_temps.get(key))
        set_value = temp_setpoints.get(key, round(value, 2))
        if value or value == 0:
            tone = "bad" if value >= 40 else "warn" if value >= 32 else "info"
            temp_holders.append(
                {
                    "label": label,
                    "field": key,
                    "measured_value": round(value, 2),
                    "set_value": round(set_value, 2),
                    "offset": round(value - set_value, 2),
                    "tone": tone,
                }
            )
    temp_stations = []
    for label in ["A", "B", "C", "D"]:
        container_value = to_float(latest_temps.get(f"{label}_container_c"))
        pipe_value = to_float(latest_temps.get(f"{label}_pipe_c"))
        container_field = f"{label}_container_c"
        pipe_field = f"{label}_pipe_c"
        container_set_value = temp_setpoints.get(container_field, round(container_value, 2))
        pipe_set_value = temp_setpoints.get(pipe_field, round(pipe_value, 2))
        values = [value for value in [container_value, pipe_value] if value or value == 0]
        hottest = max(values) if values else 0.0
        tone = "bad" if hottest >= 40 else "warn" if hottest >= 32 else "info"
        temp_stations.append(
            {
                "label": label,
                "container_field": container_field,
                "pipe_field": pipe_field,
                "container_measured_value": round(container_value, 2),
                "container_set_value": round(container_set_value, 2),
                "container_offset": round(container_value - container_set_value, 2),
                "pipe_measured_value": round(pipe_value, 2),
                "pipe_set_value": round(pipe_set_value, 2),
                "pipe_offset": round(pipe_value - pipe_set_value, 2),
                "delta": round(abs(container_value - pipe_value), 2),
                "tone": tone,
            }
        )
    stock_rows = []
    for key in sorted(
        known_coatings,
        key=lambda item: (
            -round(to_float((stock_map or {}).get(item)) + type_counts.get(item, 0.0), 2),
            item.lower(),
        ),
    ):
        warehouse_kg = round(to_float((stock_map or {}).get(key)), 2)
        loaded_kg = round(type_counts.get(key, 0.0), 2)
        total_kg = round(warehouse_kg + loaded_kg, 2)
        min_stock_kg = round(
            to_float((inventory_meta.get(key) or {}).get("min_stock_kg", DEFAULT_COATING_MIN_STOCK_KG)),
            2,
        )
        tone = "bad" if total_kg <= 0 or total_kg < min_stock_kg else "good"
        stock_rows.append(
            {
                "label": key,
                "value": total_kg,
                "unit": "kg",
                "tone": tone,
                "warehouse_kg": warehouse_kg,
                "loaded_kg": loaded_kg,
                "min_stock_kg": min_stock_kg,
            }
        )
    dies_rows = []
    for station, values in (dies_map or {}).items():
        values = values if isinstance(values, dict) else {}
        dies_rows.append(
            {
                "station": station,
                "station_key": station,
                "entry_die_um": to_float(values.get("entry_die_um")),
                "primary_die_um": to_float(values.get("primary_die_um")),
                "primary_on_tower": bool(values.get("primary_on_tower")),
                "secondary_on_tower": bool(values.get("secondary_on_tower")),
            }
        )
    coating_rows = []
    for label in known_coatings:
        config = (coating_definitions or {}).get(label, {})
        config = config if isinstance(config, dict) else {}
        warehouse_kg = round(to_float((stock_map or {}).get(label)), 2)
        loaded_kg = round(type_counts.get(label, 0.0), 2)
        total_kg = round(warehouse_kg + loaded_kg, 2)
        min_stock_kg = round(
            to_float((inventory_meta.get(label) or {}).get("min_stock_kg", DEFAULT_COATING_MIN_STOCK_KG)),
            2,
        )
        coating_rows.append(
            {
                "label": label,
                "description": str(config.get("Description", "")).strip() or "No operator note yet.",
                "density": config.get("Density", ""),
                "viscosity": config.get("Viscosity", ""),
                "refractive_index": config.get("Refractive Index", ""),
                "stock_kg": total_kg,
                "warehouse_kg": warehouse_kg,
                "loaded_kg": loaded_kg,
                "min_stock_kg": min_stock_kg,
                "in_config": label in coating_definitions,
                "tone": "bad" if total_kg <= 0 or total_kg < min_stock_kg else "good",
            }
        )
    argon_series = [{"label": row.get("month", ""), "value": round(to_float(row.get("total_standard_liters")), 2)} for row in argon_rows[-8:]]
    low_stock_lines = sum(1 for row in stock_rows if row["value"] < row["min_stock_kg"])
    return {
        "metrics": [
            {"label": "Low containers", "value": low_count, "tone": "warn" if low_count else "good"},
            {"label": "Low inventory lines", "value": low_stock_lines, "tone": "bad" if low_stock_lines else "good"},
            {"label": "Loaded coatings", "value": len([key for key in type_counts if key]), "tone": "info"},
            {"label": "Die stations", "value": len(dies_rows), "tone": "neutral"},
        ],
        "containers": container_cards,
        "container_editor_rows": [
            {
                "label": row["label"],
                "type": row["type"],
                "sensor_column": row["sensor_column"],
                "diameter_mm": row["diameter_mm"],
                "fill_height_mm": row["fill_height_mm"],
                "fill_percent": row["fill_percent"],
                "volume_l": row["volume_l"],
                "level_kg": row["level"],
                "updated_at": row["updated_at"],
            }
            for row in container_cards
        ],
        "container_shared_diameter_mm": round(
            to_float(container_cards[0]["diameter_mm"]) if container_cards else DEFAULT_CONTAINER_DIAMETER_MM,
            2,
        ),
        "container_sensor_options": list(CONTAINER_SENSOR_OPTIONS),
        "coating_type_options": known_coatings,
        "stock_rows": stock_rows,
        "stock_editor_rows": [
            {
                "label": row["label"],
                "value": row["warehouse_kg"],
                "unit": row["unit"],
                "tone": row["tone"],
                "loaded_kg": row["loaded_kg"],
                "total_kg": row["value"],
                "min_stock_kg": row["min_stock_kg"],
                "in_config": row["label"] in coating_definitions,
            }
            for row in stock_rows
        ],
        "stock_by_type": [{"label": key, "value": round(value, 2)} for key, value in type_counts.items()],
        "container_logger": container_logger_status,
        "temp_rows": temp_holders,
        "temp_holders": temp_holders,
        "temp_stations": temp_stations,
        "temps_updated_at": latest_temps.get("updated_at", ""),
        "dies_rows": dies_rows,
        "coating_rows": coating_rows,
        "argon_rows": argon_rows[-12:],
        "argon_series": argon_series,
        "container_refill_events": container_refill_events,
    }


def save_consumables_containers_action(payload: dict) -> JsonResponse:
    rows = payload.get("rows") or []
    if not isinstance(rows, list) or not rows:
        return JsonResponse({"ok": False, "message": "No container rows were supplied."}, 400)

    next_config = normalize_container_config(read_json_dict(CONTAINER_CONFIG))
    shared_diameter_mm = round(to_float(payload.get("shared_diameter_mm", DEFAULT_CONTAINER_DIAMETER_MM)), 2)
    if shared_diameter_mm <= 0:
        shared_diameter_mm = DEFAULT_CONTAINER_DIAMETER_MM
    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip().upper()
        if label not in {"A", "B", "C", "D"}:
            continue
        current = dict(next_config.get(label, {}))
        fill_height_mm = round(
            to_float(item.get("fill_height_mm", current.get("fill_height_mm", DEFAULT_CONTAINER_FILL_HEIGHT_MM))),
            2,
        )
        current["type"] = str(item.get("type", current.get("type", ""))).strip()
        current["sensor_column"] = normalize_container_sensor_column(item.get("sensor_column", current.get("sensor_column")), label)
        current["diameter_mm"] = shared_diameter_mm
        current["fill_height_mm"] = fill_height_mm if fill_height_mm > 0 else DEFAULT_CONTAINER_FILL_HEIGHT_MM
        next_config[label] = current

    write_json_value(CONTAINER_CONFIG, next_config)
    return JsonResponse({"ok": True, "message": "Container live-fill setup saved.", "bootstrap": build_bootstrap_payload().body})


def save_consumables_stock_action(payload: dict) -> JsonResponse:
    stock_map = read_json_value(COATING_STOCK, {})
    inventory_meta = read_consumables_inventory_meta()
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        return JsonResponse({"ok": False, "message": "No stock rows were supplied."}, 400)
    next_map: dict[str, float] = {}
    next_meta: dict[str, dict[str, float]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        remove = str(item.get("remove", "")).strip().lower() in {"1", "true", "yes", "on"}
        min_stock_kg = round(to_float(item.get("min_stock_kg", DEFAULT_COATING_MIN_STOCK_KG)), 2)
        if not remove:
            next_map[label] = round(to_float(item.get("value")), 2)
            next_meta[label] = {"min_stock_kg": min_stock_kg}
    custom = payload.get("custom") or {}
    if isinstance(custom, dict):
        label = str(custom.get("label", "")).strip()
        if label:
            next_map[label] = round(to_float(custom.get("value")), 2)
            next_meta[label] = {
                "min_stock_kg": round(to_float(custom.get("min_stock_kg", DEFAULT_COATING_MIN_STOCK_KG)), 2),
            }
    write_json_value(COATING_STOCK, next_map)
    write_json_value(COATING_INVENTORY_META, next_meta)
    return JsonResponse({"ok": True, "message": "Coating stock saved.", "bootstrap": build_bootstrap_payload().body})


def save_consumables_coatings_action(payload: dict) -> JsonResponse:
    rows = payload.get("rows") or []
    if not isinstance(rows, list) or not rows:
        return JsonResponse({"ok": False, "message": "No coating rows were supplied."}, 400)

    config_root = read_json_value(COATING_CONFIG, {})
    if not isinstance(config_root, dict):
        config_root = {}

    existing_coatings = config_root.get("coatings", {})
    coatings = dict(existing_coatings) if isinstance(existing_coatings, dict) else {}

    def normalize_optional_number(value):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except (TypeError, ValueError):
            return text

    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        current_entry = coatings.get(label, {})
        next_entry = dict(current_entry) if isinstance(current_entry, dict) else {}

        description = str(item.get("description", "")).strip()
        if description:
            next_entry["Description"] = description
        else:
            next_entry.pop("Description", None)

        density = normalize_optional_number(item.get("density", ""))
        if density is None:
            next_entry.pop("Density", None)
        else:
            next_entry["Density"] = density

        viscosity = normalize_optional_number(item.get("viscosity", ""))
        if viscosity is None:
            next_entry.pop("Viscosity", None)
        else:
            next_entry["Viscosity"] = viscosity

        refractive_index = normalize_optional_number(item.get("refractive_index", ""))
        if refractive_index is None:
            next_entry.pop("Refractive Index", None)
        else:
            next_entry["Refractive Index"] = refractive_index

        coatings[label] = next_entry

    config_root["coatings"] = coatings
    write_json_value(COATING_CONFIG, config_root)
    return JsonResponse({"ok": True, "message": "Coating guide saved.", "bootstrap": build_bootstrap_payload().body})


def save_consumables_dies_action(payload: dict) -> JsonResponse:
    dies_map = read_json_value(DIES_CONFIG, {})
    stations = payload.get("stations") or []
    if not isinstance(stations, list) or not stations:
        return JsonResponse({"ok": False, "message": "No die station values were supplied."}, 400)
    if not isinstance(dies_map, dict):
        dies_map = {}
    next_dies_map: dict[str, dict] = {}
    for item in stations:
        if not isinstance(item, dict):
            continue
        station = str(item.get("station", "")).strip()
        original_station = str(item.get("original_station", "")).strip()
        if not station:
            return JsonResponse({"ok": False, "message": "Every die row needs a station name."}, 400)
        if station in next_dies_map:
            return JsonResponse({"ok": False, "message": f"Duplicate die station name: {station}."}, 400)
        current = dies_map.get(original_station or station, {})
        if not isinstance(current, dict):
            current = {}
        current["entry_die_um"] = to_float(item.get("entry_die_um"))
        current["primary_die_um"] = to_float(item.get("primary_die_um"))
        next_dies_map[station] = current
    write_json_value(DIES_CONFIG, next_dies_map)
    return JsonResponse({"ok": True, "message": "Die setup saved.", "bootstrap": build_bootstrap_payload().body})


def save_consumables_temps_action(payload: dict) -> JsonResponse:
    raw_setpoints = payload.get("setpoints") or {}
    if not isinstance(raw_setpoints, dict) or not raw_setpoints:
        return JsonResponse({"ok": False, "message": "No temperature set values were supplied."}, 400)
    latest_temps = latest_csv_row(TOWER_TEMPS)
    merged = load_consumables_temp_setpoints(latest_temps)
    for field in CONSUMABLE_TEMP_FIELDS:
        if field in raw_setpoints:
            merged[field] = round(to_float(raw_setpoints.get(field)), 2)
    heater_map = read_json_value(HEATER_CONFIG, {})
    if not isinstance(heater_map, dict):
        heater_map = {}
    for field, config_key in CONSUMABLE_TEMP_SETPOINT_KEYS.items():
        heater_map[config_key] = merged[field]
    heater_map["die_holder_heater_temp_c"] = merged["die_holder_primary_c"]
    write_json_value(HEATER_CONFIG, heater_map)
    temp_rows = read_csv_rows(TOWER_TEMPS)
    temp_fieldnames = read_csv_fieldnames(TOWER_TEMPS)
    if temp_rows and temp_fieldnames:
        for field in CONSUMABLE_TEMP_FIELDS:
            csv_key = consumable_temp_setpoint_csv_field(field)
            if csv_key not in temp_fieldnames:
                temp_fieldnames.append(csv_key)
            temp_rows[-1][csv_key] = merged[field]
        write_csv_rows(TOWER_TEMPS, temp_rows, temp_fieldnames)
    return JsonResponse({"ok": True, "message": "Temperature set values saved.", "bootstrap": build_bootstrap_payload().body})


def summarize_process_setup() -> dict:
    order_draw = summarize_order_draw()
    selected_csv = read_json_dict(SELECTED_CSV_JSON).get("selected_csv", "")
    raw_rows = read_csv_rows(DRAW_ORDERS)
    latest_temps = latest_csv_row(TOWER_TEMPS)
    indexed_rows = [{"source_index": index, **row} for index, row in enumerate(raw_rows)]
    sorted_indexed_rows = sorted(indexed_rows, key=lambda item: parse_dt(item.get("Timestamp")) or datetime.min, reverse=True)

    def process_setup_schedule_key(item: dict[str, str]) -> tuple[int, datetime, datetime]:
        scheduled_dt = (
            parse_dt(item.get("Next Planned Draw Date"))
            or parse_dt(item.get("Desired Date"))
            or parse_dt(item.get("Timestamp"))
        )
        has_date = 0 if scheduled_dt else 1
        return (
            has_date,
            scheduled_dt or datetime.max,
            parse_dt(item.get("Timestamp")) or datetime.min,
        )

    scheduled_order_rows = sorted(
        [
            item for item in indexed_rows
            if str(item.get("Status", "")).strip() == "Scheduled"
        ],
        key=process_setup_schedule_key,
    )
    scheduled_orders = [
        format_order_for_ui(item, int(item.get("source_index", 0)))
        for item in scheduled_order_rows
    ][:12]
    in_progress_orders = [
        format_order_for_ui(item, int(item.get("source_index", 0)))
        for item in sorted_indexed_rows
        if str(item.get("Status", "")).strip() == "In Progress"
    ][:8]
    template_cards = []
    for project_name, template in list(order_draw["templates_by_project"].items())[:8]:
        template_cards.append(
            {
                "project": project_name,
                "geometry": template.get(GEOMETRY_COL, ""),
                "main_coating": template.get("Main Coating", ""),
                "secondary_coating": template.get("Secondary Coating", ""),
                "speed": template.get("Draw Speed (m/min)", ""),
                "tension": template.get("Tension (g)", ""),
            }
        )
    dataset_files = list_dataset_csv_files()
    if selected_csv and not any(path.name == selected_csv for path in dataset_files):
        selected_csv = ""
    selected_csv = selected_csv or (dataset_files[0].name if dataset_files else "")
    latest_dataset_name = dataset_files[0].name if dataset_files else ""
    dataset_info = analyze_dataset_file(selected_csv) if selected_csv else {
        "selected_file": "",
        "preview_rows": [],
        "parameter_names": [],
        "groups": [],
        "sections": [],
        "family_counts": [],
        "row_count": 0,
        "numeric_count": 0,
        "latest_modified": "",
    }
    dataset_linked_order_index = find_order_index_by_dataset(selected_csv) if selected_csv else None
    process_rows = [
        row for row in dataset_info.get("preview_rows", [])
        if str(row.get("parameter_name", "")).startswith("Process__")
    ][:24]
    order_rows = [
        row for row in dataset_info.get("preview_rows", [])
        if str(row.get("parameter_name", "")).startswith("Order__")
    ][:16]
    process_map = {
        str(row.get("parameter_name", "")).replace("Process__", "", 1): row.get("value", "")
        for row in dataset_info.get("preview_rows", [])
        if str(row.get("parameter_name", "")).startswith("Process__")
    }
    order_map = {
        str(row.get("parameter_name", "")).replace("Order__", "", 1): row.get("value", "")
        for row in dataset_info.get("preview_rows", [])
        if str(row.get("parameter_name", "")).startswith("Order__")
    }
    preform_options = dedupe_strings(
        [row.get("Preform Number", "") for row in raw_rows]
        + [row.get("Preform Number", "") for row in read_csv_rows(PREFORM_INVENTORY)]
    )
    coating_cfg = read_json_dict(COATING_CONFIG)
    pid_defaults = read_json_dict(PID_CONFIG)
    coating_options = dedupe_strings(list((coating_cfg.get("coatings", {}) or {}).keys()))
    die_options = dedupe_strings(list((coating_cfg.get("dies", {}) or {}).keys()))
    holder_setpoints = load_consumables_temp_setpoints(latest_temps)
    temp_context = {
        "sampled_at": latest_temps.get("updated_at", ""),
        "primary_holder_mv_c": round(to_float(latest_temps.get("die_holder_primary_c")), 2),
        "secondary_holder_mv_c": round(to_float(latest_temps.get("die_holder_secondary_c")), 2),
        "primary_holder_sp_c": round(holder_setpoints.get("die_holder_primary_c", 0.0), 2),
        "secondary_holder_sp_c": round(holder_setpoints.get("die_holder_secondary_c", 0.0), 2),
    }
    return {
        "metrics": [
            {"label": "Scheduled orders", "value": len(scheduled_order_rows)},
        ],
        "scheduled_orders": scheduled_orders,
        "in_progress_orders": in_progress_orders,
        "template_cards": template_cards,
        "selected_csv": selected_csv,
        "dataset_files": [path.name for path in dataset_files],
        "dataset_info": {
            "selected_file": dataset_info.get("selected_file", ""),
            "row_count": dataset_info.get("row_count", 0),
            "numeric_count": dataset_info.get("numeric_count", 0),
            "latest_modified": dataset_info.get("latest_modified", ""),
            "group_count": len(dataset_info.get("groups", [])),
            "section_count": len(dataset_info.get("sections", [])),
            "process_rows": process_rows,
            "order_rows": order_rows,
            "process_map": process_map,
            "order_map": order_map,
        },
        "dataset_context": {
            "selected_file": selected_csv,
            "latest_file": latest_dataset_name,
            "row_count": dataset_info.get("row_count", 0),
            "latest_modified": dataset_info.get("latest_modified", ""),
            "linked_order_index": dataset_linked_order_index,
        },
        "manual_options": {
            "project_names": order_draw["project_names"],
            "preform_options": preform_options,
            "geometry_options": ORDER_DRAW_GEOMETRY_OPTIONS,
            "priorities": ["Low", "Normal", "High"],
        },
        "setup_options": {
            "coatings": coating_options,
            "dies": die_options,
            "pid_defaults": {
                "p_gain": pid_defaults.get("p_gain", 1.0),
                "i_gain": pid_defaults.get("i_gain", 1.0),
                "winder_mode": pid_defaults.get("winder_mode", "Winder"),
                "increment_value": pid_defaults.get("increment_value", 0.5),
            },
            "drums": [f"BN{i}" for i in range(1, 7)],
        },
        "temp_context": temp_context,
        "sap_summary": order_draw["sap_summary"],
    }


def next_process_setup_index(preform_number: str) -> int:
    raw_value = normalize_preform_token(preform_number)
    if not raw_value:
        return 1
    identity = parse_draw_dataset_identity(Path(raw_value).stem)
    preform_key = str(identity["preform"]) if identity else raw_value
    max_index = 0
    for path in list_dataset_csv_files():
        identity = parse_draw_dataset_identity(path.stem)
        if identity and str(identity["preform"]) == preform_key:
            max_index = max(max_index, int(identity["index"]))
    return max_index + 1


def process_setup_dataset_name(preform_number: str) -> str:
    preform = normalize_preform_token(Path(str(preform_number or "").strip()).stem)
    if preform:
        identity = parse_draw_dataset_identity(preform)
        if identity:
            return f"{identity['draw_stem']}.csv"
        return f"{preform}F{next_process_setup_index(preform)}.csv"
    return f"draw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


def process_setup_order_rows(row: dict[str, object], order_index: int | None, csv_name: str) -> list[dict[str, object]]:
    draw_name = Path(csv_name).stem
    rows = [
        {"Parameter Name": "=== ORDER PARAMETERS ===", "Value": "", "Units": ""},
        {"Parameter Name": "Order__Draw Name", "Value": draw_name, "Units": ""},
        {"Parameter Name": "Order__Draw Date", "Value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Units": ""},
    ]
    if order_index is not None:
        rows.append({"Parameter Name": "Order__Order Index", "Value": order_index, "Units": ""})

    def add_row(name: str, value, units: str = "") -> None:
        rows.append({"Parameter Name": f"Order__{name}", "Value": value, "Units": units})

    add_row("Preform Number", row.get("Preform Number", ""))
    add_row("Fiber Project", row.get(PROJECTS_COL, ""))
    add_row("Priority", row.get("Priority", "Normal"))
    add_row("Order Opener", row.get("Order Opener", ""))
    add_row("Fiber Geometry Type", row.get(GEOMETRY_COL, ""))
    add_row("Preform Diameter (mm)", row.get(PREFORM_DIAMETER_COL, ""), "mm")
    add_row("Tiger Cut (%)", row.get(TIGER_CUT_COL, ""), "%")
    add_row("Octagonal F2F (mm)", row.get(OCT_F2F_COL, ""), "mm")
    add_row("Required Length (m) (for T&M+costumer)", row.get(LENGTH_COL, ""), "m")
    add_row("Good Zones Count (required length zones)", row.get(GOOD_ZONES_COL, ""), "count")
    add_row("Fiber Diameter (µm)", row.get("Fiber Diameter (µm)", ""), "µm")
    add_row("Fiber Diameter Tol (± µm)", row.get(FIBER_TOL_COL, ""), "µm")
    add_row("Main Coating Diameter (µm)", row.get("Main Coating Diameter (µm)", ""), "µm")
    add_row("Main Coating Diameter Tol (± µm)", row.get(MAIN_TOL_COL, ""), "µm")
    add_row("Secondary Coating Diameter (µm)", row.get("Secondary Coating Diameter (µm)", ""), "µm")
    add_row("Secondary Coating Diameter Tol (± µm)", row.get(SECONDARY_TOL_COL, ""), "µm")
    add_row("Tension (g)", row.get("Tension (g)", ""), "g")
    add_row("Draw Speed (m/min)", row.get("Draw Speed (m/min)", ""), "m/min")
    add_row("Furnace Temperature (°C)", row.get(FURNACE_TEMP_COL, ""), "°C")
    add_row("Main Coating", row.get("Main Coating", ""))
    add_row("Secondary Coating", row.get("Secondary Coating", ""))
    add_row("Main Coating Temperature (°C)", row.get(MAIN_TEMP_COL, ""), "°C")
    add_row("Secondary Coating Temperature (°C)", row.get(SECONDARY_TEMP_COL, ""), "°C")
    add_row("Order Notes", row.get("Notes", ""))
    rows.append({"Parameter Name": "", "Value": "", "Units": ""})
    return rows


def write_selected_dataset_csv(csv_name: str) -> None:
    write_json_value(SELECTED_CSV_JSON, {"selected_csv": os.path.basename(str(csv_name or "").strip())})


def create_process_setup_manual_action(payload: dict) -> JsonResponse:
    preform_number = str(payload.get("preformNumber", "")).strip()
    csv_name = os.path.basename(str(payload.get("csvName", "")).strip() or process_setup_dataset_name(preform_number))
    if not csv_name.lower().endswith(".csv"):
        csv_name = f"{csv_name}.csv"
    csv_path = full_dataset_target_path(csv_name)
    if csv_path.exists():
        return JsonResponse({"ok": False, "message": f"Dataset CSV already exists: {csv_name}"}, 400)

    row = {
        PROJECTS_COL: str(payload.get("project", "")).strip(),
        "Preform Number": preform_number,
        "Order Opener": str(payload.get("opener", "")).strip(),
        "Priority": str(payload.get("priority", "Normal")).strip() or "Normal",
        GEOMETRY_COL: str(payload.get("geometry", "")).strip(),
        LENGTH_COL: str(payload.get("requiredLength", "")).strip(),
        GOOD_ZONES_COL: str(payload.get("goodZones", "")).strip(),
        "Notes": str(payload.get("notes", "")).strip(),
    }
    write_csv_rows(csv_path, process_setup_order_rows(row, None, csv_name), ["Parameter Name", "Value", "Units"])
    write_selected_dataset_csv(csv_name)
    return JsonResponse({"ok": True, "message": f"Created {csv_name} and set it as the active setup dataset.", "bootstrap": build_bootstrap_payload().body})


def create_process_setup_scheduled_action(payload: dict) -> JsonResponse:
    order_index = to_int(payload.get("orderIndex"), -1)
    rows = read_csv_rows(DRAW_ORDERS)
    if order_index < 0 or order_index >= len(rows):
        return JsonResponse({"ok": False, "message": "Scheduled order was not found."}, 404)
    row = rows[order_index]
    status = str(row.get("Status", "")).strip()
    if status != "Scheduled":
        return JsonResponse({"ok": False, "message": "Only scheduled orders can start Process Setup here."}, 400)

    preform_number = str(payload.get("preformNumber", "")).strip() or str(row.get("Preform Number", "")).strip()
    if not preform_number or preform_number == "0":
        return JsonResponse({"ok": False, "message": "A valid preform number is required first."}, 400)

    csv_name = os.path.basename(str(payload.get("csvName", "")).strip() or process_setup_dataset_name(preform_number))
    if not csv_name.lower().endswith(".csv"):
        csv_name = f"{csv_name}.csv"
    csv_path = full_dataset_target_path(csv_name)
    if csv_path.exists():
        return JsonResponse({"ok": False, "message": f"Dataset CSV already exists: {csv_name}"}, 400)

    row["Preform Number"] = preform_number
    write_csv_rows(csv_path, process_setup_order_rows(row, order_index, csv_name), ["Parameter Name", "Value", "Units"])
    row["Active CSV"] = csv_name
    row["Status"] = "In Progress"
    row["Status Updated At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fieldnames = read_csv_fieldnames(DRAW_ORDERS) or list(row.keys())
    write_csv_rows(DRAW_ORDERS, rows, fieldnames)
    write_selected_dataset_csv(csv_name)
    return JsonResponse({"ok": True, "message": f"Started Process Setup from order #{order_index} and created {csv_name}.", "bootstrap": build_bootstrap_payload().body})


def select_process_setup_dataset_action(payload: dict) -> JsonResponse:
    selected_csv = os.path.basename(str(payload.get("selectedCsv", "")).strip())
    if selected_csv and not resolve_dataset_csv_path(selected_csv):
        return JsonResponse({"ok": False, "message": "Selected dataset CSV was not found."}, 404)
    write_selected_dataset_csv(selected_csv)
    return JsonResponse({"ok": True, "message": "Process Setup dataset changed.", "bootstrap": build_bootstrap_payload().body})


def build_process_setup_save_rows(payload: dict) -> list[dict[str, object]]:
    rows = [
        {"Parameter Name": "=== PROCESS SETUP ===", "Value": "", "Units": ""},
        {"Parameter Name": "Process__Process Setup Timestamp", "Value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Units": ""},
    ]

    def add(name: str, value, units: str = "") -> None:
        if value is None:
            return
        value_text = str(value).strip()
        if value_text == "":
            return
        rows.append({"Parameter Name": f"Process__{name}", "Value": value, "Units": units})

    iris = payload.get("iris") or {}
    coating = payload.get("coating") or {}
    pid = payload.get("pid") or {}
    drum = payload.get("drum") or {}

    add("Preform Shape", iris.get("shape"))
    add("Preform Diameter", iris.get("preform_diameter_mm"), "mm")
    add("Octagonal Preform", 1 if str(iris.get("shape", "")).strip() == "Octagonal" else 0, "bool")
    add("Octagonal F2F", iris.get("oct_f2f_mm"), "mm")
    add("Tiger Preform", 1 if str(iris.get("shape", "")).strip() == "Tiger Cut" else 0, "bool")
    add("Tiger Cut", iris.get("tiger_cut_pct"), "%")
    add("PM Iris System", 1 if iris.get("pm_system") else 0, "bool")
    add("Iris Mode", iris.get("iris_mode"))
    add("Base Area", iris.get("base_area_mm2"), "mm^2")
    add("Adjusted Area", iris.get("adjusted_area_mm2"), "mm^2")
    add("Effective Preform Diameter", iris.get("effective_preform_diameter_mm"), "mm")
    add("Selected Iris Diameter", iris.get("selected_iris_diameter_mm"), "mm")
    add("Iris Gap Area", iris.get("gap_area_mm2"), "mm^2")

    add("Entry Fiber Diameter", coating.get("entry_fiber_diameter_um"), "µm")
    add("Furnace Temperature", coating.get("furnace_temp_c"), "°C")
    add("Target First Coating Diameter", coating.get("target_first_coating_diameter_um"), "µm")
    add("Target Second Coating Diameter", coating.get("target_second_coating_diameter_um"), "µm")
    add("Primary Coating", coating.get("primary_coating"))
    add("Secondary Coating", coating.get("secondary_coating"))
    add("Primary Coating Temperature", coating.get("primary_temp_c"), "°C")
    add("Secondary Coating Temperature", coating.get("secondary_temp_c"), "°C")
    add("Primary Die Name", coating.get("primary_die"))
    add("Secondary Die Name", coating.get("secondary_die"))
    add("Coating Die Selection Mode", coating.get("die_mode"))
    add("First Coating Diameter (Theoretical)", coating.get("predicted_first_coating_diameter_um"), "µm")
    add("Second Coating Diameter (Theoretical)", coating.get("predicted_second_coating_diameter_um"), "µm")
    add("Ideal Primary Die (µm)", coating.get("ideal_primary_die_um"), "µm")
    add("Ideal Secondary Die (µm)", coating.get("ideal_secondary_die_um"), "µm")
    add("Draw Speed", coating.get("draw_speed_m_min"), "m/min")

    add("P Gain (Diameter Control)", pid.get("p_gain"))
    add("I Gain (Diameter Control)", pid.get("i_gain"))
    add("TF Mode", pid.get("tf_mode"))
    add("Increment TF Value", pid.get("increment_value_mm"), "mm")

    add("Selected Drum", drum.get("selected_drum"))
    rows.append({"Parameter Name": "", "Value": "", "Units": ""})
    return rows


def save_process_setup_action(payload: dict) -> JsonResponse:
    selected_csv = os.path.basename(str(payload.get("selectedCsv", "")).strip())
    if not selected_csv:
        return JsonResponse({"ok": False, "message": "Choose an active dataset CSV first."}, 400)
    rows = build_process_setup_save_rows(payload)
    ok, message = append_dataset_rows(selected_csv, rows)
    status = 200 if ok else 400
    if not ok:
        return JsonResponse({"ok": False, "message": message}, status)
    write_selected_dataset_csv(selected_csv)
    return JsonResponse({"ok": True, "message": message, "bootstrap": build_bootstrap_payload().body}, status)


def find_order_index_by_dataset(dataset_name: str) -> int | None:
    rows = read_csv_rows(DRAW_ORDERS)
    dataset_name = os.path.basename(str(dataset_name or "").strip())
    for index, row in enumerate(rows):
        for key in ("Assigned Dataset CSV", "Active CSV", "Done CSV", "Failed CSV", "Fail Try Dataset CSV"):
            if os.path.basename(str(row.get(key, "")).strip()) == dataset_name and dataset_name:
                return index
    for index, row in enumerate(rows):
        active_csv = os.path.basename(str(row.get("Active CSV", "")).strip())
        if active_csv == dataset_name and dataset_name:
            return index
    return None


def list_in_progress_draw_finalize_datasets() -> list[Path]:
    dataset_files = list_dataset_csv_files()
    if not dataset_files:
        return []
    active_names: set[str] = set()
    for row in read_csv_rows(DRAW_ORDERS):
        if str(row.get("Status", "")).strip() != "In Progress":
            continue
        for key in ("Active CSV", "Assigned Dataset CSV"):
            dataset_name = os.path.basename(str(row.get(key, "")).strip())
            if dataset_name:
                active_names.add(dataset_name)
    return [path for path in dataset_files if path.name in active_names]


def summarize_draw_finalize(selected_csv_override: str | None = None) -> dict:
    dataset_files = list_in_progress_draw_finalize_datasets()
    latest_dataset = dataset_files[0].name if dataset_files else ""
    selected_csv = latest_dataset
    if selected_csv_override:
        requested_csv = os.path.basename(str(selected_csv_override).strip())
        if any(path.name == requested_csv for path in dataset_files):
            selected_csv = requested_csv
    orders = read_csv_rows(DRAW_ORDERS)
    fault_rows = read_csv_rows(FAULTS_LOG)
    fault_action_rows = read_csv_rows(FAULTS_ACTIONS_LOG)
    matched_index = find_order_index_by_dataset(selected_csv) if selected_csv else None
    matched_order = format_order_for_ui(orders[matched_index], matched_index) if matched_index is not None and matched_index < len(orders) else {}
    components = dedupe_strings([row.get("fault_component", "") for row in fault_rows] + [row.get("component", "") for row in summarize_maintenance_rebuild()["tasks"]])
    return {
        "dataset_files": [path.name for path in dataset_files],
        "latest_dataset": latest_dataset,
        "selected_csv": selected_csv,
        "matched_order": matched_order,
        "components": components,
        "recent_faults": fault_rows[-8:],
        "active_only": True,
    }


def read_development_tables() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    projects = read_csv_rows(DEVELOPMENT_PROJECTS)
    experiments = read_csv_rows(DEVELOPMENT_EXPERIMENTS)
    updates = read_csv_rows(EXPERIMENT_UPDATES)
    return projects, experiments, updates


DEVELOPMENT_PROJECT_FIELDS = [
    "Project Name",
    "Project Purpose",
    "Target",
    "Created At",
    "Archived",
    "Summary Title",
    "Summary Notes",
    "Summary Date",
    "Summary Researcher",
]


def development_project_fieldnames() -> list[str]:
    fieldnames = read_csv_fieldnames(DEVELOPMENT_PROJECTS) or []
    if not fieldnames:
        fieldnames = DEVELOPMENT_PROJECT_FIELDS[:]
    else:
        fieldnames = fieldnames[:]
        for field in DEVELOPMENT_PROJECT_FIELDS:
            if field not in fieldnames:
                fieldnames.append(field)
    return fieldnames


def ensure_report_center_dir() -> None:
    REPORT_CENTER_DIR.mkdir(parents=True, exist_ok=True)


def build_operations_report_markdown(title: str, start_date: str, end_date: str, sections: list[str]) -> str:
    draws = summarize_draw_orders()
    schedule = summarize_schedule()
    parts = summarize_part_orders()
    maintenance = summarize_maintenance_rebuild()
    included = sections or REPORT_CENTER_SECTIONS
    lines = [
        f"# {title or 'Tower Operations Report'}",
        "",
        f"- Window: `{start_date}` to `{end_date}`",
        f"- Generated: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## Snapshot",
        "",
        f"- Active draws: **{draws['active']}**",
        f"- Upcoming events: **{len(schedule['upcoming'])}**",
        f"- Open part orders: **{len(parts['open_orders'])}**",
        f"- Maintenance prep queue: **{len(maintenance['prep_queue'])}**",
        "",
    ]
    for section in included:
        lines.extend(["", f"## {section}", ""])
        if section == "Executive Summary":
            lines.extend(
                [
                    f"- Draw outcomes: Done **{draws['done']}**, Failed **{draws['failed']}**",
                    f"- Schedule event types tracked: **{len(schedule['type_counts'])}**",
                    f"- Part order statuses tracked: **{len(parts['status_counts'])}**",
                    f"- Maintenance tasks tracked: **{len(maintenance['tasks'])}**",
                ]
            )
        elif section == "Resources: Gas + SAP + Preforms":
            sap = summarize_order_draw()["sap_summary"]
            lines.extend(
                [
                    f"- {sap['item']}: **{sap['count']} {sap['units']}**",
                    f"- Last updated: `{sap['last_updated'] or 'Unknown'}`",
                    f"- Notes: {sap['notes'] or 'No notes'}",
                ]
            )
        elif section == "Draw Outcomes (Done/Failed + Notes)":
            recent = draws["recent"][:8]
            if recent:
                for item in recent:
                    lines.append(f"- {item['preform'] or 'Unknown'} | {item['project'] or 'No project'} | {item['status']}")
            else:
                lines.append("- No recent draw rows found.")
        elif section == "Parts Orders Status":
            for item in parts["all_orders"][:10]:
                lines.append(f"- {item['part_name']} | {item['status']} | {item['project'] or item['company'] or 'General'}")
        elif section == "Schedule: Past Week + Next Week":
            for item in schedule["upcoming"][:10]:
                lines.append(f"- {item['start_label']} | {item['event_type']} | {item['description'] or 'No description'}")
        elif section == "Maintenance + Faults":
            for item in maintenance["prep_queue"][:10]:
                lines.append(f"- {item['component']} | {item['task']} | {item['flow_state']}")
        elif section == "Maintenance Tests + Measurements":
            for item in maintenance["recent_actions"][:10]:
                lines.append(f"- {item['done_date']} | {item['component']} | {item['task']}")
        elif section == "Consumables Snapshot":
            inventory = summarize_inventory()
            for item in inventory["low_stock"][:10]:
                lines.append(f"- {item['part_name']} | Qty {item['quantity']} | {item['location'] or 'No location'}")
    return "\n".join(lines).strip() + "\n"


def summarize_development_project(project_name: str) -> dict:
    projects, experiments, updates = read_development_tables()
    project = next((row for row in projects if str(row.get("Project Name", "")).strip() == project_name.strip()), {})
    project_experiments = [row for row in experiments if str(row.get("Project Name", "")).strip() == project_name.strip()]
    project_updates = [row for row in updates if str(row.get("Project Name", "")).strip() == project_name.strip()]
    media_count = 0
    researchers = dedupe_strings([row.get("Researcher", "") for row in project_experiments + project_updates])
    latest_update = ""
    dated_updates = sorted(
        project_updates,
        key=lambda row: str(row.get("Update Date", "")),
        reverse=True,
    )
    if dated_updates:
        latest_update = dated_updates[0].get("Update Date", "")
    project_experiments = sorted(project_experiments, key=lambda row: str(row.get("Date", "")), reverse=True)
    drawing_experiments = [row for row in project_experiments if str(row.get("Is Drawing", "")).strip().lower() in {"true", "1", "yes"}]
    for row in project_experiments:
        for field in ("Result Images", "Result Docs", "Attachments"):
            media_count += len([item for item in str(row.get(field, "")).split(";") if item.strip()])
    return {
        "project": project,
        "experiment_count": len(project_experiments),
        "update_count": len(project_updates),
        "media_count": media_count,
        "latest_update": latest_update,
        "latest_experiment": project_experiments[0] if project_experiments else {},
        "drawing_experiment_count": len(drawing_experiments),
        "archived": str(project.get("Archived", "")).strip().lower() in {"true", "1", "yes"},
        "researchers": researchers,
        "experiments": project_experiments[:18],
        "updates": project_updates[:18],
        "dataset_files": [path.name for path in list_dataset_csv_files()[:40]],
    }


def development_project_timeline_entries(details: dict) -> list[dict]:
    dated_items: list[dict] = []
    order = 0
    for item in reversed(details.get("experiments", []) or []):
        dated_items.append(
            {
                "kind": "experiment",
                "order": order,
                "date": str(item.get("Date", "")).strip(),
                "item": item,
            }
        )
        order += 1
    for item in details.get("updates", []) or []:
        dated_items.append(
            {
                "kind": "update",
                "order": order,
                "date": str(item.get("Update Date", "")).strip(),
                "item": item,
            }
        )
        order += 1
    project = details.get("project", {}) or {}
    summary_notes = str(project.get("Summary Notes", "")).strip()
    summary_date = str(project.get("Summary Date", "")).strip()
    summary_title = str(project.get("Summary Title", "")).strip()
    summary_researcher = str(project.get("Summary Researcher", "")).strip()
    if project.get("Project Name") and (summary_notes or summary_title or summary_date or summary_researcher):
        dated_items.append(
            {
                "kind": "summary",
                "order": order,
                "date": summary_date or str(details.get("latest_update", "")).strip(),
                "item": {
                    "title": summary_title or "Project summary",
                    "status": "Archived" if details.get("archived") else "Active",
                    "drawings": details.get("drawing_experiment_count") or 0,
                    "researchers": ", ".join(details.get("researchers") or []) or "Not listed",
                    "target": project.get("Target") or "Not set",
                    "notes": summary_notes,
                    "researcher": summary_researcher,
                    "latestActivity": summary_date or str(details.get("latest_update", "")).strip() or "No activity yet",
                },
            }
        )
    return sorted(
        dated_items,
        key=lambda entry: ((entry.get("date") or "9999-99-99"), entry.get("order", 0)),
    )


def development_project_latest_activity(details: dict) -> str:
    timeline = development_project_timeline_entries(details)
    if timeline:
        return str(timeline[-1].get("date", "")).strip() or "No activity yet"
    return str(details.get("latest_update", "")).strip() or "No activity yet"


def markdown_paragraph(value: str, fallback: str = "Not set.") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def html_multiline(value: str, fallback: str = "Not set.") -> str:
    text = str(value or "").strip()
    safe = escape_html(text or fallback)
    return safe.replace("\n", "<br/>")


def build_development_report_markdown(project_name: str) -> str:
    details = summarize_development_project(project_name)
    project = details["project"]
    if not project:
        return f"# Project Paper: {project_name}\n\nProject was not found.\n"
    timeline = development_project_timeline_entries(details)
    latest_activity = development_project_latest_activity(details)
    lines = [
        f"# Project Paper: {project_name}",
        "",
        "> Structured export from the Tower development workspace.",
        "",
        "## Project Identity",
        "",
        f"- Description: {project.get('Project Purpose', 'Not set')}",
        f"- Target: {project.get('Target', 'Not set')}",
        f"- Created: {project.get('Created At', 'Unknown')}",
        f"- Researchers: {', '.join(details['researchers']) or 'None listed'}",
        f"- Latest activity: {latest_activity}",
        f"- Status: {'Archived' if details.get('archived') else 'Active'}",
        "",
        "## Workspace Metrics",
        "",
        f"- Experiments: **{details['experiment_count']}**",
        f"- Updates: **{details['update_count']}**",
        f"- Drawing runs: **{details['drawing_experiment_count'] or 0}**",
        f"- Media attachments: **{details['media_count']}**",
        "",
        "## Project Summary",
        "",
        f"- Title: {project.get('Summary Title', '') or 'Project summary'}",
        f"- Date: {project.get('Summary Date', '') or 'Not set'}",
        f"- Researcher: {project.get('Summary Researcher', '') or 'Not set'}",
        "",
        markdown_paragraph(project.get("Summary Notes", ""), "No project summary saved yet."),
        "",
        "## Timeline",
        "",
    ]
    if timeline:
        for entry in timeline:
            item = entry.get("item", {}) or {}
            if entry.get("kind") == "summary":
                lines.extend(
                    [
                        f"### {entry.get('date') or 'No date'} · Summary",
                        f"- Title: {item.get('title', 'Project summary')}",
                        f"- Researcher: {item.get('researcher', '') or 'Not set'}",
                        f"- Status: {item.get('status', 'Active')}",
                        f"- Draws: {item.get('drawings', 0)}",
                        "",
                        markdown_paragraph(item.get("notes", ""), "No project summary was written yet."),
                        "",
                    ]
                )
                continue
            if entry.get("kind") == "update":
                lines.extend(
                    [
                        f"### {entry.get('date') or 'No date'} · Update",
                        f"- Title: {item.get('Experiment Title', '') or 'Project update'}",
                        f"- Researcher: {item.get('Researcher', '') or 'Not set'}",
                        "",
                        markdown_paragraph(item.get("Update Notes", ""), "No update notes saved."),
                        "",
                    ]
                )
                continue
            lines.extend(
                [
                    f"### {entry.get('date') or 'No date'} · Experiment",
                    f"- Title: {item.get('Experiment Title', 'Untitled Experiment')}",
                    f"- Researcher: {item.get('Researcher', '') or 'Not set'}",
                    f"- Purpose: {item.get('Purpose', '') or '-'}",
                    f"- Methods: {item.get('Methods', '') or '-'}",
                    f"- Observations: {item.get('Observations', '') or '-'}",
                    f"- Results: {item.get('Results', '') or '-'}",
                    f"- Draw CSV: {item.get('Draw CSV', '') or 'Not linked'}",
                    f"- Drawing details: {item.get('Drawing Details', '') or '-'}",
                    "",
                    markdown_paragraph(item.get("Markdown Notes", ""), "No experiment notes saved."),
                    "",
                ]
            )
    else:
        lines.append("- No project history found.")
    return "\n".join(lines).strip() + "\n"


def build_development_report_html(project_name: str) -> str:
    details = summarize_development_project(project_name)
    project = details["project"]
    if not project:
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Project Paper</title></head>
<body><main><h1>Project Paper</h1><p>Project was not found.</p></main></body></html>"""
    timeline = development_project_timeline_entries(details)
    latest_activity = development_project_latest_activity(details)
    archived_label = "Archived" if details.get("archived") else "Active"
    metrics = [
        ("Experiments", str(details.get("experiment_count", 0))),
        ("Updates", str(details.get("update_count", 0))),
        ("Drawing runs", str(details.get("drawing_experiment_count", 0))),
        ("Status", archived_label),
    ]
    facts = [
        ("Latest activity", latest_activity),
        ("Researchers", ", ".join(details.get("researchers") or []) or "Not listed"),
        ("Created", str(project.get("Created At", "")).strip() or "Unknown"),
    ]
    timeline_markup = []
    for entry in timeline:
        item = entry.get("item", {}) or {}
        kind = str(entry.get("kind", "")).strip()
        date_text = escape_html(str(entry.get("date", "")).strip() or "No date")
        if kind == "summary":
            body = f"""
              <div class="paper-card-body">
                <div class="paper-facet-grid">
                  <div class="paper-facet"><span>Status</span><strong>{escape_html(str(item.get('status', 'Active')))}</strong></div>
                  <div class="paper-facet"><span>Draws</span><strong>{escape_html(str(item.get('drawings', 0)))}</strong></div>
                  <div class="paper-facet"><span>Researchers</span><strong>{escape_html(str(item.get('researchers', 'Not listed')))}</strong></div>
                </div>
                <div class="paper-rich-note">{html_multiline(item.get('notes', ''), 'No project summary was written yet.')}</div>
              </div>
            """
            title = escape_html(str(item.get("title", "Project summary")))
            label = "Summary"
            meta = escape_html(str(item.get("researcher", "")).strip() or "Project note")
            node = "SM"
        elif kind == "update":
            body = f"""
              <div class="paper-card-body">
                <div class="paper-rich-note">{html_multiline(item.get('Update Notes', ''), 'No update notes saved.')}</div>
              </div>
            """
            title = escape_html(str(item.get("Experiment Title", "")).strip() or "Project update")
            label = "Update"
            meta = escape_html(str(item.get("Researcher", "")).strip() or "Not set")
            node = "UP"
        else:
            is_drawing = str(item.get("Is Drawing", "")).strip().lower() in {"true", "1", "yes"}
            body = f"""
              <div class="paper-card-body">
                <div class="paper-facet-grid">
                  <div class="paper-facet"><span>Purpose</span><strong>{escape_html(str(item.get('Purpose', '')).strip() or '-')}</strong></div>
                  <div class="paper-facet"><span>Methods</span><strong>{escape_html(str(item.get('Methods', '')).strip() or '-')}</strong></div>
                  <div class="paper-facet"><span>Observations</span><strong>{escape_html(str(item.get('Observations', '')).strip() or '-')}</strong></div>
                  <div class="paper-facet"><span>Results</span><strong>{escape_html(str(item.get('Results', '')).strip() or '-')}</strong></div>
                </div>
                <div class="paper-rich-note">{html_multiline(item.get('Markdown Notes', ''), 'No experiment notes saved.')}</div>
                <div class="paper-footnote">Draw CSV: {escape_html(str(item.get('Draw CSV', '')).strip() or 'Not linked')} · Drawing details: {escape_html(str(item.get('Drawing Details', '')).strip() or '-')}</div>
              </div>
            """
            title = escape_html(str(item.get("Experiment Title", "")).strip() or "Untitled experiment")
            label = "Draw experiment" if is_drawing else "Experiment"
            meta = escape_html(str(item.get("Researcher", "")).strip() or "Not set")
            node = "DR" if is_drawing else "EX"
        timeline_markup.append(
            f"""
            <article class="paper-timeline-item paper-kind-{kind or 'experiment'}">
              <div class="paper-rail">
                <span class="paper-node">{node}</span>
              </div>
              <div class="paper-card">
                <div class="paper-card-head">
                  <div>
                    <span>{escape_html(label)}</span>
                    <strong>{title}</strong>
                  </div>
                  <div class="paper-card-meta">{date_text} · {meta}</div>
                </div>
                {body}
              </div>
            </article>
            """
        )
    metric_markup = "".join(
        f'<div class="paper-metric"><span>{escape_html(label)}</span><strong>{escape_html(value)}</strong></div>'
        for label, value in metrics
    )
    fact_markup = "".join(
        f'<div class="paper-fact"><span>{escape_html(label)}</span><strong>{escape_html(value)}</strong></div>'
        for label, value in facts
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Project Paper - {escape_html(project_name)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #061018;
      --panel: rgba(10, 18, 29, 0.92);
      --panel-soft: rgba(12, 24, 36, 0.82);
      --line: rgba(159, 223, 227, 0.14);
      --muted: rgba(183, 214, 220, 0.74);
      --text: rgba(244, 250, 251, 0.96);
      --accent: #72ffe8;
      --accent-soft: rgba(114, 255, 232, 0.18);
      --good: #82ffcf;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top right, rgba(114,255,232,0.08), transparent 28%),
        linear-gradient(180deg, #07121d 0%, #050c14 100%);
      color: var(--text);
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}
    .paper-toolbar {{
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 22px;
      border-bottom: 1px solid var(--line);
      background: rgba(6, 16, 24, 0.94);
      backdrop-filter: blur(18px);
    }}
    .paper-toolbar-copy {{
      display: grid;
      gap: 4px;
    }}
    .paper-toolbar-copy span,
    .paper-hero-kicker,
    .paper-section-kicker,
    .paper-card-head span,
    .paper-metric span,
    .paper-fact span,
    .paper-facet span {{
      font-size: 0.72rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .paper-toolbar button {{
      border: 1px solid rgba(114,255,232,0.24);
      background: linear-gradient(180deg, rgba(114,255,232,0.16), rgba(114,255,232,0.04));
      color: var(--text);
      padding: 10px 14px;
      cursor: pointer;
    }}
    .paper-shell {{
      width: min(1160px, calc(100% - 40px));
      margin: 0 auto;
      padding: 28px 0 40px;
      display: grid;
      gap: 18px;
    }}
    .paper-hero,
    .paper-panel,
    .paper-progress {{
      border: 1px solid var(--line);
      background: linear-gradient(180deg, var(--panel-soft), rgba(7, 14, 22, 0.84));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }}
    .paper-hero {{
      padding: 24px;
      display: grid;
      gap: 12px;
    }}
    .paper-hero h1 {{
      margin: 0;
      font-size: clamp(2.2rem, 5vw, 4rem);
      line-height: 0.95;
      text-transform: uppercase;
      letter-spacing: -0.04em;
    }}
    .paper-description {{
      max-width: 78ch;
      color: rgba(224,238,240,0.9);
      line-height: 1.6;
    }}
    .paper-target {{
      display: grid;
      gap: 4px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      max-width: 48ch;
    }}
    .paper-target strong,
    .paper-fact strong,
    .paper-facet strong,
    .paper-metric strong {{
      font-size: 1.02rem;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    .paper-metrics,
    .paper-facts,
    .paper-facet-grid {{
      display: grid;
      gap: 10px;
    }}
    .paper-metrics {{
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }}
    .paper-facts {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    .paper-facet-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .paper-metric,
    .paper-fact,
    .paper-facet {{
      display: grid;
      gap: 6px;
      padding: 14px 16px;
      border: 1px solid rgba(159,223,227,0.08);
      background: linear-gradient(180deg, rgba(8,16,24,0.54), rgba(8,16,24,0.18));
    }}
    .paper-panel {{
      padding: 20px;
      display: grid;
      gap: 14px;
    }}
    .paper-rich-note {{
      color: rgba(224,238,240,0.92);
      line-height: 1.7;
      white-space: normal;
    }}
    .paper-progress {{
      padding: 20px;
      display: grid;
      gap: 18px;
    }}
    .paper-timeline {{
      display: grid;
      gap: 16px;
    }}
    .paper-timeline-item {{
      display: grid;
      grid-template-columns: 52px minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }}
    .paper-rail {{
      position: relative;
      display: flex;
      justify-content: center;
    }}
    .paper-rail::after {{
      content: "";
      position: absolute;
      top: 44px;
      bottom: -16px;
      width: 1px;
      background: linear-gradient(180deg, rgba(114,255,232,0.28), rgba(114,255,232,0));
    }}
    .paper-timeline-item:last-child .paper-rail::after {{ display: none; }}
    .paper-node {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border-radius: 12px;
      border: 1px solid rgba(114,255,232,0.18);
      background: rgba(13, 28, 40, 0.88);
      color: rgba(233,247,249,0.96);
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.08em;
    }}
    .paper-kind-update .paper-node {{
      border-color: rgba(198, 126, 255, 0.22);
      background: rgba(31, 18, 46, 0.92);
    }}
    .paper-card {{
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(10,18,29,0.82), rgba(8,14,22,0.92));
    }}
    .paper-card-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 18px 14px;
      border-bottom: 1px solid rgba(159,223,227,0.08);
    }}
    .paper-card-head strong {{
      display: block;
      margin-top: 4px;
      font-size: 1.02rem;
      line-height: 1.4;
    }}
    .paper-card-meta {{
      align-self: end;
      color: rgba(214, 233, 236, 0.84);
      white-space: nowrap;
    }}
    .paper-card-body {{
      display: grid;
      gap: 14px;
      padding: 16px 18px 18px;
    }}
    .paper-footnote {{
      color: rgba(183,214,220,0.78);
      line-height: 1.5;
    }}
    @media (max-width: 900px) {{
      .paper-shell {{ width: min(100%, calc(100% - 24px)); }}
      .paper-metrics,
      .paper-facts,
      .paper-facet-grid {{ grid-template-columns: 1fr 1fr; }}
      .paper-card-head {{ flex-direction: column; }}
      .paper-card-meta {{ white-space: normal; }}
    }}
    @media (max-width: 640px) {{
      .paper-metrics,
      .paper-facts,
      .paper-facet-grid {{ grid-template-columns: 1fr; }}
      .paper-timeline-item {{ grid-template-columns: 1fr; }}
      .paper-rail {{ justify-content: flex-start; }}
      .paper-rail::after {{ display: none; }}
    }}
    @media print {{
      @page {{
        size: A4;
        margin: 12mm;
      }}
      .paper-toolbar {{ display: none; }}
      body {{ background: #061018; }}
      .paper-shell {{
        width: 100%;
        padding: 0;
      }}
      .paper-hero,
      .paper-panel,
      .paper-progress,
      .paper-card,
      .paper-timeline-item,
      .paper-metric,
      .paper-fact,
      .paper-facet {{
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .paper-timeline {{
        gap: 12px;
      }}
      .paper-card-body,
      .paper-rich-note,
      .paper-footnote {{
        orphans: 3;
        widows: 3;
      }}
    }}
  </style>
</head>
<body>
  <div class="paper-toolbar">
    <div class="paper-toolbar-copy">
      <span>Project paper export</span>
      <strong>{escape_html(project_name)}</strong>
    </div>
    <button type="button" onclick="window.print()">Print / Save PDF</button>
  </div>
  <main class="paper-shell">
    <section class="paper-hero">
      <span class="paper-hero-kicker">Development</span>
      <h1>{escape_html(project_name)}</h1>
      <div class="paper-description">{html_multiline(project.get("Project Purpose", ""), "No project description saved yet.")}</div>
      <div class="paper-target">
        <span>Target</span>
        <strong>{escape_html(str(project.get("Target", "")).strip() or "Not set")}</strong>
      </div>
    </section>
    <section class="paper-metrics">{metric_markup}</section>
    <section class="paper-panel">
      <span class="paper-section-kicker">Project facts</span>
      <div class="paper-facts">{fact_markup}</div>
    </section>
    <section class="paper-panel">
      <span class="paper-section-kicker">Project summary</span>
      <strong>{escape_html(str(project.get("Summary Title", "")).strip() or "Project summary")}</strong>
      <div class="paper-footnote">Date: {escape_html(str(project.get("Summary Date", "")).strip() or "Not set")} · Researcher: {escape_html(str(project.get("Summary Researcher", "")).strip() or "Not set")}</div>
      <div class="paper-rich-note">{html_multiline(project.get("Summary Notes", ""), "No project summary saved yet.")}</div>
    </section>
    <section class="paper-progress">
      <div>
        <span class="paper-section-kicker">Project progress</span>
        <h2>Append lab work in one timeline</h2>
      </div>
      <div class="paper-timeline">
        {''.join(timeline_markup) if timeline_markup else '<div class="paper-panel"><div class="paper-rich-note">No project history found yet.</div></div>'}
      </div>
    </section>
  </main>
</body>
</html>"""


def summarize_report_center() -> dict:
    ensure_report_center_dir()
    projects, experiments, updates = read_development_tables()
    md_exports = list_recent_files(REPORT_CENTER_DIR, suffixes=(".md",), limit=20)
    project_names = dedupe_strings([row.get("Project Name", "") for row in projects if row.get("Project Name", "")])
    return {
        "metrics": [
            {"label": "Report exports", "value": len(md_exports)},
            {"label": "Dev projects", "value": len(project_names)},
            {"label": "Experiments", "value": len(experiments)},
            {"label": "Updates", "value": len(updates)},
        ],
        "modes": ["Operations Report", "Development Process", "Recent Exports"],
        "sections": REPORT_CENTER_SECTIONS,
        "project_names": project_names,
        "projects_count": len(project_names),
        "experiments_count": len(experiments),
        "updates_count": len(updates),
        "recent_md_exports": md_exports,
        "latest_export": md_exports[0] if md_exports else {},
        "default_project": project_names[0] if project_names else "",
    }


def normalize_dataset_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    current_section = "General"
    normalized = []
    for index, row in enumerate(rows):
        parameter_name = normalize_dataset_parameter_name(row.get("Parameter Name", ""))
        value = normalize_dataset_parameter_value(parameter_name, row.get("Value", ""))
        units = str(row.get("Units", "")).strip()
        if parameter_name.startswith("===") and parameter_name.endswith("==="):
            current_section = parameter_name.strip("= ").title()
            continue
        group_name = ""
        key_name = parameter_name
        if "__" in parameter_name:
            group_name, key_name = parameter_name.split("__", 1)
        value_num = None
        try:
            value_num = float(value)
        except ValueError:
            value_num = None
        normalized.append(
            {
                "row_index": index,
                "section": current_section,
                "parameter_name": parameter_name,
                "group_name": group_name or current_section,
                "key_name": key_name,
                "value": value,
                "units": units,
                "value_num": value_num,
            }
        )
    return normalized


def dataset_param_family(name: str) -> str:
    s = str(name or "").lower()
    if s.startswith("order__"):
        return "Order"
    if s.startswith("process__"):
        return "Process"
    if "zone " in s or s.startswith("zone ") or s.startswith("marked zone"):
        return "Zones"
    if "t&m" in s or "good zone" in s or "cut/save" in s or "fiber length" in s or "drum |" in s:
        return "Winder + T&M"
    return "General"


def infer_dataset_event_ts(normalized_rows: list[dict[str, object]], path: Path) -> str:
    candidates = []
    for row in normalized_rows:
        param = str(row.get("parameter_name", "")).strip().lower()
        value = str(row.get("value", "")).strip()
        if not value:
            continue
        if param in {"draw date", "draw datetime"} or "draw date" in param or "draw time" in param or "datetime" in param:
            candidates.append(value)
    for value in candidates:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def load_dataset_scope_records(dataset_name: str | None = None) -> tuple[list[Path], list[dict[str, object]]]:
    files = list_dataset_csv_files()
    selected_name = str(dataset_name or "").strip()
    if selected_name and selected_name != "__ALL__":
        files = [path for path in files if path.name == selected_name]
    records: list[dict[str, object]] = []
    for path in files:
        normalized = normalize_dataset_rows(read_csv_rows(path))
        draw_id = path.stem
        event_ts = infer_dataset_event_ts(normalized, path)
        for row in normalized:
            records.append(
                {
                    **row,
                    "_draw": draw_id,
                    "filename": path.name,
                    "event_ts": event_ts,
                }
            )
    return files, records


def load_dataset_records_for_filenames(file_names: list[str] | None = None) -> tuple[list[Path], list[dict[str, object]]]:
    requested = {str(name or "").strip() for name in (file_names or []) if str(name or "").strip()}
    files = list_dataset_csv_files()
    if requested:
        files = [path for path in files if path.name in requested]
    records: list[dict[str, object]] = []
    for path in files:
        normalized = normalize_dataset_rows(read_csv_rows(path))
        draw_id = path.stem
        event_ts = infer_dataset_event_ts(normalized, path)
        for row in normalized:
            records.append(
                {
                    **row,
                    "_draw": draw_id,
                    "filename": path.name,
                    "event_ts": event_ts,
                }
            )
    return files, records


def collect_sql_lab_components() -> dict[str, list[str]]:
    maintenance_components = dedupe_strings(
        [row.get("component", "") for row in read_csv_rows(MAINTENANCE_ACTIONS)]
        + [row.get("Component", "") for row in read_maintenance_tracker_rows()]
    )
    fault_components = dedupe_strings([row.get("fault_component", "") for row in read_csv_rows(FAULTS_LOG)] + maintenance_components)
    return {
        "maintenance": maintenance_components,
        "faults": fault_components,
    }


def analyze_dataset_file(dataset_name: str | None = None) -> dict:
    files, normalized = load_dataset_scope_records(dataset_name)
    selected_name = str(dataset_name or "").strip()
    selected_label = selected_name if selected_name and selected_name != "__ALL__" else "__ALL__"
    if not files:
        return {
            "selected_file": "",
            "available_files": [],
            "groups": [],
            "sections": [],
            "parameter_names": [],
            "family_counts": [],
            "preview_rows": [],
            "row_count": 0,
            "numeric_count": 0,
        }
    group_counts: dict[str, int] = {}
    section_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    value_map: dict[str, list[str]] = {}
    for row in normalized:
        group = str(row["group_name"] or "General")
        section = str(row["section"] or "General")
        family = dataset_param_family(str(row["parameter_name"] or ""))
        group_counts[group] = group_counts.get(group, 0) + 1
        section_counts[section] = section_counts.get(section, 0) + 1
        family_counts[family] = family_counts.get(family, 0) + 1
        param = str(row["parameter_name"] or "")
        value = str(row["value"] or "")
        if param and value and len(value_map.get(param, [])) < 20 and value not in value_map.setdefault(param, []):
            value_map[param].append(value)
    return {
        "selected_file": selected_label,
        "available_files": ["__ALL__", *[path.name for path in files]],
        "groups": [{"label": key, "value": value} for key, value in sorted(group_counts.items(), key=lambda item: item[0].lower())],
        "sections": [{"label": key, "value": value} for key, value in sorted(section_counts.items(), key=lambda item: item[0].lower())],
        "family_counts": [{"label": key, "value": value} for key, value in sorted(family_counts.items(), key=lambda item: item[0].lower())],
        "parameter_names": sorted({str(row["parameter_name"]) for row in normalized if str(row.get("parameter_name", "")).strip()}, key=str.lower),
        "parameter_values": value_map,
        "preview_rows": normalized[:160],
        "row_count": len(normalized),
        "numeric_count": len([row for row in normalized if row["value_num"] is not None]),
        "latest_modified": max(datetime.fromtimestamp(path.stat().st_mtime) for path in files).strftime("%Y-%m-%d %H:%M"),
    }


def summarize_sql_lab() -> dict:
    dataset_files = list_dataset_csv_files()
    latest_payload = analyze_dataset_file("__ALL__") if dataset_files else {}
    components = collect_sql_lab_components()
    return {
        "metrics": [
            {"label": "Dataset CSVs", "value": len(dataset_files)},
            {"label": "Rows in focus", "value": latest_payload.get("row_count", 0)},
            {"label": "Numeric values", "value": latest_payload.get("numeric_count", 0)},
            {"label": "Groups", "value": len(latest_payload.get("groups", []))},
        ],
        "dataset_files": ["__ALL__", *[path.name for path in dataset_files]],
        "latest_dataset": "__ALL__",
        "operators": ["any", "=", "!=", ">", ">=", "<", "<=", "between", "contains"],
        "include_modes": ["Draws", "Maintenance", "Faults"],
        "event_scope_modes": [
            "All events",
            "Only within time filter window",
            "Only within matched draws window",
        ],
        "maintenance_components": components["maintenance"],
        "fault_components": components["faults"],
        "query_templates": [
            {"key": "overview", "label": "Overview", "sql": "SELECT section, COUNT(*) AS rows FROM dataset GROUP BY section ORDER BY rows DESC;"},
            {"key": "order", "label": "Order Params", "sql": "SELECT parameter_name, value, units FROM dataset WHERE group_name = 'Order' ORDER BY parameter_name;"},
            {"key": "numeric", "label": "Numeric", "sql": "SELECT parameter_name, value_num, units FROM dataset WHERE value_num IS NOT NULL ORDER BY ABS(value_num) DESC LIMIT 25;"},
        ],
    }


def sql_value_matches(row: dict[str, object], operator: str, value1: str, value2: str) -> bool:
    operator = str(operator or "any").strip().lower()
    raw_value = str(row.get("value", "")).strip()
    numeric_value = row.get("value_num")
    value1 = str(value1 or "").strip()
    value2 = str(value2 or "").strip()
    if operator == "any":
        return True
    if operator == "contains":
        return bool(value1) and value1.lower() in raw_value.lower()
    if operator == "between":
        if not value1 or not value2:
            return False
        if numeric_value is not None and value1.replace(".", "", 1).replace("-", "", 1).isdigit() and value2.replace(".", "", 1).replace("-", "", 1).isdigit():
            low, high = sorted([float(value1), float(value2)])
            return low <= float(numeric_value) <= high
        return value1 <= raw_value <= value2
    if not value1:
        return False
    if numeric_value is not None and value1.replace(".", "", 1).replace("-", "", 1).isdigit():
        left = float(numeric_value)
        right = float(value1)
    else:
        left = raw_value
        right = value1
    if operator == "=":
        return left == right
    if operator == "!=":
        return left != right
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    return False


def sql_eval_group_condition(draw_rows: list[dict[str, object]], condition: dict[str, object]) -> bool:
    params = dedupe_strings(condition.get("params", []) or [])
    if not params:
        return False
    param_results = []
    for param in params:
        matching_rows = [row for row in draw_rows if str(row.get("parameter_name", "")).strip() == param]
        result = any(sql_value_matches(row, str(condition.get("op", "any")), str(condition.get("v1", "")), str(condition.get("v2", ""))) for row in matching_rows)
        param_results.append(result)
    group_logic = str(condition.get("groupLogic", "ANY (OR)"))
    outcome = all(param_results) if group_logic.startswith("ALL") else any(param_results)
    if condition.get("negate"):
        return not outcome
    return outcome


def sql_filter_dataset_records(
    payload: dict,
    *,
    draw_limit: int | None = 200,
    value_limit: int | None = 400,
    event_limit: int | None = 120,
) -> dict:
    dataset_name = str(payload.get("dataset", "__ALL__")).strip() or "__ALL__"
    _, records = load_dataset_scope_records(dataset_name)
    by_draw: dict[str, list[dict[str, object]]] = {}
    for row in records:
        by_draw.setdefault(str(row.get("_draw", "")), []).append(row)

    conditions = payload.get("conditions", []) or []
    time_enabled = bool(payload.get("timeEnabled"))
    time_from = str(payload.get("timeFrom", "")).strip()
    time_to = str(payload.get("timeTo", "")).strip()
    include_draws = bool(payload.get("includeDraws", True))
    include_maintenance = bool(payload.get("includeMaintenance"))
    include_faults = bool(payload.get("includeFaults"))
    event_scope = str(payload.get("eventScope", "Only within matched draws window")).strip()

    matched_draws = []
    matched_values = []
    for draw_id, draw_rows in by_draw.items():
        draw_ts = parse_dt(str(draw_rows[0].get("event_ts", "")))
        if time_enabled and time_from and time_to and draw_ts:
            start_dt = datetime.fromisoformat(time_from)
            end_dt = datetime.fromisoformat(time_to) + timedelta(days=1) - timedelta(seconds=1)
            if not (start_dt <= draw_ts <= end_dt):
                continue
        if conditions:
            overall = None
            for index, condition in enumerate(conditions):
                result = sql_eval_group_condition(draw_rows, condition)
                joiner = str(condition.get("joiner", "AND")).upper()
                if index == 0 or overall is None:
                    overall = result
                elif joiner == "OR":
                    overall = overall or result
                else:
                    overall = overall and result
            if not overall:
                continue
        event_ts = str(draw_rows[0].get("event_ts", ""))
        matched_draws.append(
            {
                "_draw": draw_id,
                "event_ts": event_ts,
                "filename": str(draw_rows[0].get("filename", "")),
            }
        )
        if conditions:
            for condition in conditions:
                params = dedupe_strings(condition.get("params", []) or [])
                for row in draw_rows:
                    if params and str(row.get("parameter_name", "")) not in params:
                        continue
                    if sql_value_matches(row, str(condition.get("op", "any")), str(condition.get("v1", "")), str(condition.get("v2", ""))):
                        matched_values.append(
                            {
                                "_draw": draw_id,
                                "parameter_name": str(row.get("parameter_name", "")),
                                "value": str(row.get("value", "")),
                                "units": str(row.get("units", "")),
                                "event_ts": event_ts,
                            }
                        )

    matched_draws.sort(key=lambda item: (item["event_ts"], item["_draw"]))
    matched_draw_ids = {item["_draw"] for item in matched_draws}
    if value_limit is not None:
        matched_values = matched_values[:value_limit]

    scope_start = None
    scope_end = None
    if matched_draws and event_scope == "Only within matched draws window":
        scope_times = [parse_dt(item["event_ts"]) for item in matched_draws if parse_dt(item["event_ts"])]
        if scope_times:
            scope_start, scope_end = min(scope_times), max(scope_times)
    elif time_enabled and time_from and time_to and event_scope == "Only within time filter window":
        scope_start = datetime.fromisoformat(time_from)
        scope_end = datetime.fromisoformat(time_to) + timedelta(days=1) - timedelta(seconds=1)

    maintenance_rows = []
    if include_maintenance:
        maint_text = str(payload.get("maintenanceText", "")).strip().lower()
        maint_component = str(payload.get("maintenanceComponent", "")).strip().lower()
        for row in read_csv_rows(MAINTENANCE_ACTIONS):
            ts = parse_dt(str(row.get("action_ts", "")))
            if scope_start and scope_end and ts and not (scope_start <= ts <= scope_end):
                continue
            haystack = " ".join(
                [
                    str(row.get("component", "")),
                    str(row.get("task", "")),
                    str(row.get("note", "")),
                    str(row.get("source_file", "")),
                ]
            ).lower()
            if maint_text and maint_text not in haystack:
                continue
            if maint_component and maint_component not in str(row.get("component", "")).lower():
                continue
            maintenance_rows.append(
                {
                    "event_id": str(row.get("action_id", "")),
                    "event_ts": str(row.get("action_ts", "")),
                    "component": str(row.get("component", "")),
                    "title": str(row.get("task", "")),
                    "note": str(row.get("note", "")),
                    "source_file": str(row.get("source_file", "")),
                }
            )

    fault_rows = []
    if include_faults:
        fault_text = str(payload.get("faultText", "")).strip().lower()
        fault_component = str(payload.get("faultComponent", "")).strip().lower()
        fault_severity = str(payload.get("faultSeverity", "")).strip().lower()
        for row in read_csv_rows(FAULTS_LOG):
            ts = parse_dt(str(row.get("fault_ts", "")))
            if scope_start and scope_end and ts and not (scope_start <= ts <= scope_end):
                continue
            haystack = " ".join(
                [
                    str(row.get("fault_component", "")),
                    str(row.get("fault_title", "")),
                    str(row.get("fault_description", "")),
                    str(row.get("fault_source_file", "")),
                ]
            ).lower()
            if fault_text and fault_text not in haystack:
                continue
            if fault_component and fault_component not in str(row.get("fault_component", "")).lower():
                continue
            if fault_severity and fault_severity != str(row.get("fault_severity", "")).strip().lower():
                continue
            fault_rows.append(
                {
                    "event_id": str(row.get("fault_id", "")),
                    "event_ts": str(row.get("fault_ts", "")),
                    "component": str(row.get("fault_component", "")),
                    "title": str(row.get("fault_title", "")),
                    "severity": str(row.get("fault_severity", "")),
                    "description": str(row.get("fault_description", "")),
                    "source_file": str(row.get("fault_source_file", "")),
                }
            )

    return {
        "ok": True,
        "summary": {
            "matched_draws": len(matched_draws),
            "matched_values": len(matched_values),
            "maintenance_events": len(maintenance_rows),
            "fault_events": len(fault_rows),
            "draw_scope": len(matched_draw_ids),
        },
        "matched_draws": matched_draws[:draw_limit] if include_draws and draw_limit is not None else (matched_draws if include_draws else []),
        "matched_values": matched_values,
        "maintenance_events": maintenance_rows[:event_limit] if event_limit is not None else maintenance_rows,
        "fault_events": fault_rows[:event_limit] if event_limit is not None else fault_rows,
    }


def run_sql_lab_filter_action(payload: dict) -> JsonResponse:
    try:
        return JsonResponse(sql_filter_dataset_records(payload))
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, 400)


def sql_collect_condition_parameter_names(payload: dict) -> list[str]:
    names: list[str] = []
    for condition in (payload.get("conditions") or []):
        for raw_name in (condition.get("params") or []):
            name = str(raw_name or "").strip()
            if name:
                names.append(name)
    return dedupe_strings(names)


def sql_condition_operator_label_server(operator: str) -> str:
    op = str(operator or "any").strip().lower()
    mapping = {
        "any": "Any value",
        "=": "=",
        "!=": "!=",
        ">": ">",
        ">=": ">=",
        "<": "<",
        "<=": "<=",
        "between": "between",
        "contains": "contains",
    }
    return mapping.get(op, op or "any")


def sql_describe_filter_conditions(payload: dict) -> list[str]:
    lines: list[str] = []
    for index, condition in enumerate(payload.get("conditions") or []):
        params = dedupe_strings(condition.get("params") or [])
        params_label = ", ".join(params[:4]) if params else "No parameters"
        if len(params) > 4:
            params_label = f"{params_label} +{len(params) - 4} more"
        op = sql_condition_operator_label_server(str(condition.get("op", "any")))
        v1 = str(condition.get("v1", "")).strip()
        v2 = str(condition.get("v2", "")).strip()
        value_label = ""
        if op == "between":
            value_label = f" {v1 or '?'} .. {v2 or '?'}"
        elif op not in {"Any value"} and v1:
            value_label = f" {v1}"
        negate_label = " · NOT" if condition.get("negate") else ""
        group_logic = str(condition.get("groupLogic", "ANY (OR)")).strip() or "ANY (OR)"
        joiner = "BASE" if index == 0 else str(condition.get("joiner", "AND")).strip().upper()
        lines.append(f"{joiner} · {group_logic} · {params_label} · {op}{value_label}{negate_label}")
    return lines


def build_sql_lab_export_context(payload: dict) -> dict:
    filter_result = sql_filter_dataset_records(payload, draw_limit=None, value_limit=None, event_limit=None)
    matched_draws = list(filter_result.get("matched_draws") or [])
    filenames = dedupe_strings([str(item.get("filename", "")).strip() for item in matched_draws if str(item.get("filename", "")).strip()])
    _, scope_records = load_dataset_records_for_filenames(filenames)
    rows_by_draw: dict[str, list[dict[str, object]]] = {}
    for row in scope_records:
        draw_id = str(row.get("_draw", "")).strip()
        if not draw_id:
            continue
        rows_by_draw.setdefault(draw_id, []).append(row)

    parameter_names = sql_collect_condition_parameter_names(payload)
    if not parameter_names:
        parameter_names = dedupe_strings(
            [
                str(item.get("parameter_name", "")).strip()
                for item in (filter_result.get("matched_values") or [])
                if str(item.get("parameter_name", "")).strip()
            ]
        )[:24]

    draw_details: list[dict[str, object]] = []
    for draw_meta in matched_draws:
        draw_id = str(draw_meta.get("_draw", "")).strip()
        draw_rows = rows_by_draw.get(draw_id, [])
        parameter_rows: list[dict[str, str]] = []
        if parameter_names:
            for parameter_name in parameter_names:
                matching_rows = [row for row in draw_rows if str(row.get("parameter_name", "")).strip() == parameter_name]
                if not matching_rows:
                    parameter_rows.append(
                        {
                            "parameter_name": parameter_name,
                            "value": "—",
                            "units": "",
                            "section": "",
                            "group_name": "",
                        }
                    )
                    continue
                for row in matching_rows[:3]:
                    parameter_rows.append(
                        {
                            "parameter_name": parameter_name,
                            "value": str(row.get("value", "")).strip() or "—",
                            "units": str(row.get("units", "")).strip(),
                            "section": str(row.get("section", "")).strip(),
                            "group_name": str(row.get("group_name", "")).strip(),
                        }
                    )
        draw_details.append(
            {
                "draw": draw_id,
                "event_ts": str(draw_meta.get("event_ts", "")).strip(),
                "filename": str(draw_meta.get("filename", "")).strip(),
                "parameter_rows": parameter_rows,
            }
        )

    active_lanes = []
    if payload.get("includeDraws", True):
        active_lanes.append("Draws")
    if payload.get("includeMaintenance"):
        active_lanes.append("Maintenance")
    if payload.get("includeFaults"):
        active_lanes.append("Faults")

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": str(payload.get("dataset", "__ALL__")).strip() or "__ALL__",
        "summary": filter_result.get("summary") or {},
        "conditions": sql_describe_filter_conditions(payload),
        "parameter_names": parameter_names,
        "time_enabled": bool(payload.get("timeEnabled")),
        "time_from": str(payload.get("timeFrom", "")).strip(),
        "time_to": str(payload.get("timeTo", "")).strip(),
        "event_scope": str(payload.get("eventScope", "Only within matched draws window")).strip(),
        "active_lanes": active_lanes,
        "draw_details": draw_details,
        "maintenance_events": filter_result.get("maintenance_events") or [],
        "fault_events": filter_result.get("fault_events") or [],
    }


def create_sql_lab_results_export_action(payload: dict) -> JsonResponse:
    ensure_report_center_dir()
    export_context = build_sql_lab_export_context(payload)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_label = str(export_context.get("dataset", "__ALL__")).strip() or "__ALL__"
    safe_dataset = re.sub(r"[^A-Za-z0-9._-]+", "_", dataset_label).strip("._") or "all"
    output_name = f"sql_lab_matched_results_{safe_dataset}_{timestamp}.csv"
    output_path = REPORT_CENTER_DIR / output_name
    parameter_names = list(export_context.get("parameter_names") or [])
    draw_details = list(export_context.get("draw_details") or [])
    parameter_unit_map: dict[str, str] = {}
    for item in draw_details:
        for row in (item.get("parameter_rows") or []):
            parameter_name = str(row.get("parameter_name", "")).strip()
            units = str(row.get("units", "")).strip()
            if parameter_name and units and parameter_name not in parameter_unit_map:
                parameter_unit_map[parameter_name] = units
    headers = ["draw", "event_ts", "filename"]
    for parameter_name in parameter_names:
        units = parameter_unit_map.get(parameter_name, "")
        headers.append(f"{parameter_name} ({units})" if units else parameter_name)
    try:
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for item in draw_details:
                parameter_value_map: dict[str, list[str]] = {}
                for row in (item.get("parameter_rows") or []):
                    parameter_name = str(row.get("parameter_name", "")).strip()
                    if not parameter_name:
                        continue
                    value = str(row.get("value", "")).strip() or "—"
                    parameter_value_map.setdefault(parameter_name, []).append(value)
                writer.writerow(
                    [
                        str(item.get("draw", "")).strip(),
                        str(item.get("event_ts", "")).strip(),
                        str(item.get("filename", "")).strip(),
                        *[" | ".join(parameter_value_map.get(name, ["—"])) for name in parameter_names],
                    ]
                )
    except OSError as exc:
        return JsonResponse({"ok": False, "message": f"Could not write matched results CSV: {exc}"}, 500)
    encoded_name = quote(output_path.name)
    return JsonResponse(
        {
            "ok": True,
            "message": f"Matched results CSV saved as {output_path.name}.",
            "fileName": output_path.name,
            "fileUrl": f"/api/report-center/file?name={encoded_name}&download=1",
            "viewUrl": f"/api/report-center/file?name={encoded_name}&mode=inline",
            "downloadUrl": f"/api/report-center/file?name={encoded_name}&download=1",
            "format": "csv",
            "matchedDraws": int((export_context.get("summary") or {}).get("matched_draws", 0)),
            "conditionParams": len(parameter_names),
        }
    )


def run_sql_lab_analysis_scope_action(payload: dict) -> JsonResponse:
    filenames = dedupe_strings([str(item).strip() for item in (payload.get("filenames") or []) if str(item).strip()])
    if not filenames:
        return JsonResponse(
            {
                "ok": True,
                "records": [],
                "draw_count": 0,
                "row_count": 0,
                "grouped_labels": [],
            }
        )
    files, records = load_dataset_records_for_filenames(filenames[:120])
    return JsonResponse(
        {
            "ok": True,
            "records": records[:30000],
            "draw_count": len(files),
            "row_count": len(records),
            "grouped_labels": sorted(
                {
                    str(row.get("parameter_name", "")).strip()
                    for row in records
                    if str(row.get("parameter_name", "")).strip()
                },
                key=str.lower,
            )[:2000],
        }
    )


def summarize_development() -> dict:
    projects, experiments, updates = read_development_tables()
    active_projects = [row for row in projects if str(row.get("Archived", "")).strip().lower() not in {"true", "1", "yes"}]
    archived_projects = [row for row in projects if str(row.get("Archived", "")).strip().lower() in {"true", "1", "yes"}]
    project_names = [row.get("Project Name", "") for row in active_projects if row.get("Project Name", "")]
    latest_updates = sorted(updates, key=lambda row: str(row.get("Update Date", "")), reverse=True)[:12]
    return {
        "metrics": [
            {"label": "Projects", "value": len(project_names)},
            {"label": "Active", "value": len(active_projects)},
        ],
        "project_names": project_names,
        "archived_project_names": [row.get("Project Name", "") for row in archived_projects if row.get("Project Name", "")],
        "default_project": project_names[0] if project_names else "",
        "latest_updates": latest_updates,
        "dataset_files": [path.name for path in list_dataset_csv_files()[:60]],
    }


def run_sql_lab_query_action(payload: dict) -> JsonResponse:
    dataset_name = str(payload.get("dataset", "")).strip()
    sql = str(payload.get("sql", "")).strip()
    if not dataset_name:
        return JsonResponse({"ok": False, "message": "Choose a dataset first."}, 400)
    if not sql:
        return JsonResponse({"ok": False, "message": "SQL is empty."}, 400)
    normalized_sql = sql.lstrip().lower()
    if not (normalized_sql.startswith("select") or normalized_sql.startswith("with")):
        return JsonResponse({"ok": False, "message": "Only SELECT queries are allowed in the rebuild SQL Lab."}, 400)
    _, normalized_rows = load_dataset_scope_records(dataset_name)
    if not normalized_rows:
        return JsonResponse({"ok": False, "message": "Selected dataset scope was not found."}, 404)
    conn = duckdb.connect(":memory:") if duckdb else sqlite3.connect(":memory:")
    try:
        df = pd.DataFrame(normalized_rows)
        if duckdb:
            conn.register("dataset_df", df)
            conn.execute("CREATE TABLE dataset AS SELECT * FROM dataset_df")
        else:
            conn.execute(
                """
                CREATE TABLE dataset (
                    row_index INTEGER,
                    section TEXT,
                    parameter_name TEXT,
                    group_name TEXT,
                    key_name TEXT,
                    value TEXT,
                    units TEXT,
                    value_num REAL,
                    _draw TEXT,
                    filename TEXT,
                    event_ts TEXT
                )
                """
            )
            conn.executemany(
                "INSERT INTO dataset VALUES (:row_index, :section, :parameter_name, :group_name, :key_name, :value, :units, :value_num, :_draw, :filename, :event_ts)",
                normalized_rows,
            )
        limited_sql = sql.rstrip().rstrip(";")
        if " limit " not in normalized_sql:
            limited_sql = f"{limited_sql} LIMIT 200"
        cursor = conn.execute(limited_sql)
        columns = [item[0] for item in cursor.description] if cursor.description else []
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return JsonResponse({"ok": True, "columns": columns, "rows": rows, "row_count": len(rows)})
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, 400)
    finally:
        conn.close()


def append_project_if_missing(project_name: str) -> None:
    project_name = str(project_name or "").strip()
    if not project_name:
        return
    rows = read_csv_rows(PROJECTS_FIBER)
    existing = dedupe_strings([row.get(PROJECTS_COL, "") for row in rows])
    if project_name in existing:
        return
    fieldnames = read_csv_fieldnames(PROJECTS_FIBER) or [PROJECTS_COL]
    rows.append({PROJECTS_COL: project_name})
    write_csv_rows(PROJECTS_FIBER, rows, fieldnames)


def save_project_template(payload: dict) -> None:
    project_name = str(payload.get(PROJECTS_COL, "")).strip()
    if not project_name:
        return
    rows = read_csv_rows(PROJECTS_TEMPLATES)
    fieldnames = read_csv_fieldnames(PROJECTS_TEMPLATES) or TEMPLATE_FIELDS[:]
    fieldnames = fieldnames + [field for field in TEMPLATE_FIELDS if field not in fieldnames]
    template_row = {field: payload.get(field, "") for field in fieldnames}
    replaced = False
    for index, row in enumerate(rows):
        if str(row.get(PROJECTS_COL, "")).strip() == project_name:
            rows[index] = {field: template_row.get(field, row.get(field, "")) for field in fieldnames}
            replaced = True
            break
    if not replaced:
        rows.append(template_row)
    write_csv_rows(PROJECTS_TEMPLATES, rows, fieldnames)


def validate_order_payload(order: dict) -> list[str]:
    errors = []
    if not str(order.get("preformNumber", "")).strip():
        errors.append("Preform Number")
    if not str(order.get("project", "")).strip():
        errors.append("Fiber Project")
    if not str(order.get("opener", "")).strip():
        errors.append("Order Opened By")
    if to_float(order.get("requiredLength")) <= 0:
        errors.append("Required Length (m)")
    if int(to_float(order.get("goodZones") or 0)) <= 0:
        errors.append("Good Zones Count")
    geometry = str(order.get("geometry", "")).strip()
    if not geometry:
        errors.append(GEOMETRY_COL)
    if geometry == "TIGER - PM" and to_float(order.get("tigerCut")) <= 0:
        errors.append("Tiger Cut (%)")
    if geometry == "Octagonal" and to_float(order.get("octF2f")) <= 0:
        errors.append("Octagonal F2F (mm)")
    if to_float(order.get("preformDiameterMm")) <= 0:
        errors.append("Preform Diameter (mm)")
    if to_float(order.get("furnaceTemp")) <= 0:
        errors.append("Furnace Temperature (°C)")
    return errors


def write_schedule_entry(order_row: dict[str, str], order_index: int, schedule_payload: dict, preform_number: str) -> None:
    date_value = str(schedule_payload.get("date", "")).strip()
    time_value = str(schedule_payload.get("startTime", "")).strip()
    duration_minutes = int(to_float(schedule_payload.get("durationMin") or 0))
    start = datetime.fromisoformat(f"{date_value}T{time_value}")
    end = start + timedelta(minutes=duration_minutes)
    existing = read_csv_rows(TOWER_SCHEDULE)
    fieldnames = read_csv_fieldnames(TOWER_SCHEDULE) or SCHEDULE_REQUIRED_COLS[:]
    fieldnames = fieldnames + [field for field in SCHEDULE_REQUIRED_COLS if field not in fieldnames]
    existing.append(
        {
            "Event Type": "Drawing",
            "Start DateTime": start.strftime("%Y-%m-%d %H:%M:%S"),
            "End DateTime": end.strftime("%Y-%m-%d %H:%M:%S"),
            "Description": build_schedule_description(order_row, order_index, preform_number),
            "Recurrence": "None",
        }
    )
    write_csv_rows(TOWER_SCHEDULE, existing, fieldnames)


def create_order_draw_action(payload: dict) -> JsonResponse:
    order = payload.get("order", {})
    schedule_now = bool(payload.get("scheduleNow"))
    schedule_payload = payload.get("schedule", {}) or {}
    save_template = bool(payload.get("saveTemplate"))
    errors = validate_order_payload(order)
    if errors:
        return JsonResponse({"ok": False, "message": "Missing required fields: " + ", ".join(errors)}, 400)
    project_name = str(order.get("project", "")).strip()
    append_project_if_missing(project_name)
    existing = read_csv_rows(DRAW_ORDERS)
    fieldnames = read_csv_fieldnames(DRAW_ORDERS) or []
    new_row = {
        "Status": "Pending",
        "Priority": str(order.get("priority", "Normal")).strip() or "Normal",
        "Order Opener": str(order.get("opener", "")).strip(),
        "Preform Number": str(order.get("preformNumber", "")).strip(),
        PROJECTS_COL: project_name,
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "Fiber Diameter (µm)": to_float(order.get("fiberDiameter")),
        "Main Coating Diameter (µm)": to_float(order.get("mainCoatingDiameter")),
        "Secondary Coating Diameter (µm)": to_float(order.get("secondaryCoatingDiameter")),
        "Tension (g)": to_float(order.get("tension")),
        "Draw Speed (m/min)": to_float(order.get("drawSpeed")),
        FURNACE_TEMP_COL: to_float(order.get("furnaceTemp")),
        LENGTH_COL: to_float(order.get("requiredLength")),
        GOOD_ZONES_COL: int(to_float(order.get("goodZones") or 0)),
        "Main Coating": str(order.get("mainCoating", "")).strip(),
        "Secondary Coating": str(order.get("secondaryCoating", "")).strip(),
        "Notes": str(order.get("notes", "")).strip(),
        "Desired Date": "",
        "Next Planned Draw Date": "",
        GEOMETRY_COL: str(order.get("geometry", "")).strip(),
        PREFORM_DIAMETER_COL: to_float(order.get("preformDiameterMm")),
        TIGER_CUT_COL: to_float(order.get("tigerCut")),
        OCT_F2F_COL: to_float(order.get("octF2f")),
        MAIN_TEMP_COL: to_float(order.get("mainCoatingTemp")),
        SECONDARY_TEMP_COL: to_float(order.get("secondaryCoatingTemp")),
        FIBER_TOL_COL: to_float(order.get("fiberTol")),
        MAIN_TOL_COL: to_float(order.get("mainTol")),
        SECONDARY_TOL_COL: to_float(order.get("secondaryTol")),
        "Active CSV": "",
        "Done CSV": "",
        "Done Description": "",
        "T&M Moved": False,
        "T&M Moved Timestamp": "",
    }
    fieldnames = fieldnames or list(new_row.keys())
    fieldnames = fieldnames + [field for field in new_row.keys() if field not in fieldnames]
    existing.append({field: new_row.get(field, "") for field in fieldnames})
    order_index = len(existing) - 1
    message = "Draw order saved."
    sap_message = ""
    if schedule_now:
        schedule_ready = (
            str(schedule_payload.get("password", "")).strip() == SCHEDULE_PASSWORD
            and str(schedule_payload.get("date", "")).strip()
            and str(schedule_payload.get("startTime", "")).strip()
            and int(to_float(schedule_payload.get("durationMin") or 0)) > 0
        )
        if schedule_ready:
            write_schedule_entry(new_row, order_index, schedule_payload, new_row["Preform Number"])
            existing[order_index]["Status"] = "Scheduled"
            message = "Draw order saved and scheduled."
        else:
            message = "Draw order saved, but not scheduled because the schedule details or password were invalid."
    write_csv_rows(DRAW_ORDERS, existing, fieldnames)
    if new_row[GEOMETRY_COL] == "PANDA - PM":
        sap_source_draw = new_row["Preform Number"] or f"{project_name} {new_row['Timestamp']}"
        _, sap_message = decrement_sap_rods_set_for_panda_draw(sap_source_draw)
    if save_template:
        save_project_template(
            {
                PROJECTS_COL: project_name,
                GEOMETRY_COL: new_row[GEOMETRY_COL],
                PREFORM_DIAMETER_COL: new_row[PREFORM_DIAMETER_COL],
                TIGER_CUT_COL: new_row[TIGER_CUT_COL],
                OCT_F2F_COL: new_row[OCT_F2F_COL],
                "Fiber Diameter (µm)": new_row["Fiber Diameter (µm)"],
                FIBER_TOL_COL: new_row[FIBER_TOL_COL],
                "Main Coating Diameter (µm)": new_row["Main Coating Diameter (µm)"],
                MAIN_TOL_COL: new_row[MAIN_TOL_COL],
                "Secondary Coating Diameter (µm)": new_row["Secondary Coating Diameter (µm)"],
                SECONDARY_TOL_COL: new_row[SECONDARY_TOL_COL],
                "Tension (g)": new_row["Tension (g)"],
                "Draw Speed (m/min)": new_row["Draw Speed (m/min)"],
                FURNACE_TEMP_COL: new_row[FURNACE_TEMP_COL],
                "Main Coating": new_row["Main Coating"],
                "Secondary Coating": new_row["Secondary Coating"],
                MAIN_TEMP_COL: new_row[MAIN_TEMP_COL],
                SECONDARY_TEMP_COL: new_row[SECONDARY_TEMP_COL],
                "Notes Default": new_row["Notes"],
            }
        )
    if sap_message:
        message = f"{message} {sap_message}".strip()
    return JsonResponse({"ok": True, "message": message, "bootstrap": build_bootstrap_payload().body})


def save_order_draw_template_action(payload: dict) -> JsonResponse:
    project_name = str(payload.get("project", "")).strip()
    if not project_name:
        return JsonResponse({"ok": False, "message": "Choose a project before saving a template."}, 400)
    append_project_if_missing(project_name)
    save_project_template(
        {
            PROJECTS_COL: project_name,
            GEOMETRY_COL: str(payload.get("geometry", "")).strip(),
            PREFORM_DIAMETER_COL: to_float(payload.get("preformDiameterMm")),
            TIGER_CUT_COL: to_float(payload.get("tigerCut")),
            OCT_F2F_COL: to_float(payload.get("octF2f")),
            "Fiber Diameter (µm)": to_float(payload.get("fiberDiameter")),
            FIBER_TOL_COL: to_float(payload.get("fiberTol")),
            "Main Coating Diameter (µm)": to_float(payload.get("mainCoatingDiameter")),
            MAIN_TOL_COL: to_float(payload.get("mainTol")),
            "Secondary Coating Diameter (µm)": to_float(payload.get("secondaryCoatingDiameter")),
            SECONDARY_TOL_COL: to_float(payload.get("secondaryTol")),
            "Tension (g)": to_float(payload.get("tension")),
            "Draw Speed (m/min)": to_float(payload.get("drawSpeed")),
            FURNACE_TEMP_COL: to_float(payload.get("furnaceTemp")),
            "Main Coating": str(payload.get("mainCoating", "")).strip(),
            "Secondary Coating": str(payload.get("secondaryCoating", "")).strip(),
            MAIN_TEMP_COL: to_float(payload.get("mainCoatingTemp")),
            SECONDARY_TEMP_COL: to_float(payload.get("secondaryCoatingTemp")),
            "Notes Default": str(payload.get("notes", "")).strip(),
        }
    )
    return JsonResponse({"ok": True, "message": "Template saved.", "bootstrap": build_bootstrap_payload().body})


def schedule_pending_order_action(payload: dict) -> JsonResponse:
    password = str(payload.get("password", "")).strip()
    if password != SCHEDULE_PASSWORD:
        return JsonResponse({"ok": False, "message": "Scheduling password is missing or wrong."}, 400)
    order_index = to_int(payload.get("orderIndex"), -1)
    orders = read_csv_rows(DRAW_ORDERS)
    if order_index < 0 or order_index >= len(orders):
        return JsonResponse({"ok": False, "message": "Selected order was not found."}, 404)
    row = orders[order_index]
    if str(row.get("Status", "")).strip() != "Pending":
        return JsonResponse({"ok": False, "message": "Only pending orders can be scheduled here."}, 400)
    preform_number = str(payload.get("preformNumber", "")).strip() or str(row.get("Preform Number", "")).strip()
    if not preform_number or preform_number == "0":
        return JsonResponse({"ok": False, "message": "A real preform number is required before scheduling."}, 400)
    write_schedule_entry(row, order_index, payload, preform_number)
    row["Preform Number"] = preform_number
    row["Status"] = "Scheduled"
    fieldnames = read_csv_fieldnames(DRAW_ORDERS) or list(row.keys())
    write_csv_rows(DRAW_ORDERS, orders, fieldnames)
    return JsonResponse({"ok": True, "message": "Pending order scheduled.", "bootstrap": build_bootstrap_payload().body})


def append_dataset_rows(selected_csv: str, rows: list[dict]) -> tuple[bool, str]:
    if not selected_csv:
        return False, "No dataset CSV selected."
    csv_path = resolve_dataset_csv_path(selected_csv) or full_dataset_target_path(selected_csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_csv_rows(csv_path)
    fieldnames = ["Parameter Name", "Value", "Units"]
    normalized_existing = []
    for row in existing:
        normalized_existing.append({field: row.get(field, "") for field in fieldnames})
    normalized_new = [{field: row.get(field, "") for field in fieldnames} for row in rows]
    write_csv_rows(csv_path, normalized_existing + normalized_new, fieldnames)
    return True, f"Saved {len(normalized_new)} rows into {csv_path.name}"


def format_done_snapshot_value(value: object, units: object = "") -> str:
    text = str(value or "").strip()
    unit_text = str(units or "").strip()
    if not text:
        return ""
    try:
        number = float(text)
        if not math.isfinite(number):
            return f"{text} {unit_text}".strip()
        if number.is_integer():
            return f"{int(number)} {unit_text}".strip()
        return f"{round(number, 3)} {unit_text}".strip()
    except (TypeError, ValueError):
        return f"{text} {unit_text}".strip()


def latest_dataset_parameter_value(rows: list[dict[str, str]], name: str) -> str:
    for row in reversed(rows):
        if str(row.get("Parameter Name", "")).strip() != name:
            continue
        return format_done_snapshot_value(row.get("Value", ""), row.get("Units", ""))
    return ""


def first_dataset_parameter_value(rows: list[dict[str, str]], *names: str) -> str:
    for name in names:
        value = latest_dataset_parameter_value(rows, name)
        if value:
            return value
    return ""


def build_done_snapshot_text(csv_path: Path, dataset_name: str, preform_len_cm: float, done_description: str) -> str:
    rows = read_csv_rows(csv_path)
    done_desc = re.sub(r"\s+", " ", str(done_description or "").strip())
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    identity_section = [
        ("Project", latest_dataset_parameter_value(rows, "Order__Fiber Project")),
        ("Draw Name", latest_dataset_parameter_value(rows, "Order__Draw Name")),
        ("Preform", latest_dataset_parameter_value(rows, "Order__Preform Number")),
        ("Geometry", latest_dataset_parameter_value(rows, "Order__Fiber Geometry Type")),
        ("Fiber Diameter", latest_dataset_parameter_value(rows, "Order__Fiber Diameter (µm)")),
        ("Main Coating", latest_dataset_parameter_value(rows, "Order__Main Coating")),
        ("Main Coat Dia", latest_dataset_parameter_value(rows, "Order__Main Coating Diameter (µm)")),
        ("Secondary Coating", latest_dataset_parameter_value(rows, "Order__Secondary Coating")),
        ("Secondary Coat Dia", latest_dataset_parameter_value(rows, "Order__Secondary Coating Diameter (µm)")),
    ]

    tm_section = [
        ("Drum", first_dataset_parameter_value(rows, "Drum | Selected", "Process__Selected Drum")),
        ("Total Saved", latest_dataset_parameter_value(rows, "Total Saved Length")),
        ("Total Cut", latest_dataset_parameter_value(rows, "Total Cut Length")),
        ("Good Zones", latest_dataset_parameter_value(rows, "Good Zones Count")),
        ("Fiber Length End (log end)", first_dataset_parameter_value(rows, "Fiber Length End (log end)", "Fibre Length End (log end)")),
    ]

    for row in rows:
        name = str(row.get("Parameter Name", "")).strip()
        if re.match(r"^Good Zone \d+ Length$", name):
            tm_section.append((name, format_done_snapshot_value(row.get("Value", ""), row.get("Units", ""))))
    for row in rows:
        name = str(row.get("Parameter Name", "")).strip()
        if re.search(r"Good Zone .*Fib(?:re|er) Length (Min|Max)", name):
            tm_section.append((name, format_done_snapshot_value(row.get("Value", ""), row.get("Units", ""))))

    step_dict: dict[int, dict[str, str]] = {}
    for row in rows:
        name = str(row.get("Parameter Name", "")).strip()
        if not name.startswith("T&M Step"):
            continue
        match = re.match(r"T&M Step (\d+) (.*)", name)
        if not match:
            continue
        step_num = int(match.group(1))
        label = str(match.group(2) or "").strip()
        step_dict.setdefault(step_num, {})[label] = format_done_snapshot_value(row.get("Value", ""), row.get("Units", ""))

    instruction_lines: list[str] = []
    for step_num in sorted(step_dict):
        data = step_dict[step_num]
        line = f"Step {step_num}: {data.get('Action', '')}".rstrip()
        if data.get("Length"):
            line += f"  ->  {data['Length']}"
        if data.get("Zone"):
            line += f"  ({data['Zone']})"
        instruction_lines.append(line.rstrip())
        for key, value in data.items():
            if "Fibre Length Min" in key or "Fibre Length Max" in key or "Fiber Length Min" in key or "Fiber Length Max" in key:
                instruction_lines.append(f"    {key}: {value}")

    remove_tokens = [
        "Good Fibre State",
        "Diameter Error",
        "Furnace Power",
        "Furnace MFC",
        "Preform Speed Actual",
        "Trend Marker",
        "Furnace DegC Set",
        "Intensity",
        "Poly",
        "Diameter Deviation",
    ]

    zone_lines: list[tuple[str, str]] = []
    seen_zone_keys: set[tuple[str, str]] = set()
    for row in rows:
        name = str(row.get("Parameter Name", "")).strip()
        if not name.startswith("Zone "):
            continue
        display_name = normalize_dataset_parameter_name(name)
        if any(token in name for token in remove_tokens):
            continue
        formatted_value = format_done_snapshot_value(row.get("Value", ""), row.get("Units", ""))
        if not formatted_value:
            continue
        if "Pf Process Position" in name:
            if "| Min" in name or "| Max" in name:
                dedupe_key = (display_name, formatted_value)
                if dedupe_key not in seen_zone_keys:
                    seen_zone_keys.add(dedupe_key)
                    zone_lines.append((display_name, formatted_value))
            continue
        if "Fibre Length" in name or "Fiber Length" in name:
            if "| Min" in name or "| Max" in name:
                dedupe_key = (display_name, formatted_value)
                if dedupe_key not in seen_zone_keys:
                    seen_zone_keys.add(dedupe_key)
                    zone_lines.append((display_name, formatted_value))
            continue
        if "| Avg" in name:
            dedupe_key = (display_name, formatted_value)
            if dedupe_key not in seen_zone_keys:
                seen_zone_keys.add(dedupe_key)
                zone_lines.append((display_name, formatted_value))

    output_lines = [
        "============================================================",
        "DRAW REPORT - CLEAN SUMMARY",
        "============================================================",
        f"Time: {now_str}",
        f"CSV: {dataset_name}",
        f"Preform Length After Draw: {format_done_snapshot_value(preform_len_cm, 'cm')}",
    ]
    if done_desc:
        output_lines.append(f"Done Description: {done_desc}")
    output_lines.extend(["", "******************* T&M SECTION ***************************"])
    for key, value in tm_section:
        if value:
            output_lines.append(f"{key}: {value}")
    if instruction_lines:
        output_lines.extend(["", "T&M INSTRUCTIONS:"])
        output_lines.extend(instruction_lines)
    output_lines.extend(["", "******************* IDENTITY *******************************"])
    for key, value in identity_section:
        if value:
            output_lines.append(f"{key}: {value}")
    output_lines.extend(["", "******************* ZONE DATA ******************************"])
    for key, value in zone_lines:
        output_lines.append(f"{key}: {value}")
    output_lines.extend(["", "============================================================", ""])
    return "\n".join(output_lines)


def create_done_snapshot(dataset_name: str, preform_len_cm: float, done_description: str) -> tuple[bool, str]:
    dataset_file = os.path.basename(str(dataset_name or "").strip())
    if not dataset_file:
        return False, "No dataset selected for done snapshot."
    csv_path = resolve_dataset_csv_path(dataset_file)
    if not csv_path or not csv_path.exists() or not csv_path.is_file():
        return False, f"Dataset file was not found for snapshot: {dataset_file}"
    DONE_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    identity = parse_draw_dataset_identity(Path(dataset_file).stem)
    snapshot_stem = str(identity["draw_stem"]) if identity else Path(dataset_file).stem
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", snapshot_stem).strip("._") or "done_snapshot"
    snapshot_path = DONE_SNAPSHOTS_DIR / f"{safe_name}.txt"
    atomic_write_text(snapshot_path, build_done_snapshot_text(csv_path, dataset_file, preform_len_cm, done_description), encoding="utf-8")
    return True, str(snapshot_path)


def current_default_printer() -> str:
    try:
        result = subprocess.run(
            ["lpstat", "-d"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (result.stdout or "").strip()
        if result.returncode == 0 and ":" in output:
            return output.split(":", 1)[1].strip()
    except Exception:
        pass
    try:
        lpoptions_path = Path.home() / ".cups" / "lpoptions"
        if lpoptions_path.exists():
            for line in lpoptions_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("Default "):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1].strip()
    except Exception:
        pass
    return ""


def try_print_snapshot(snapshot_path: str) -> tuple[bool, str, str]:
    if not snapshot_path:
        return False, "", "No snapshot path was provided for printing."
    if sys.platform != "darwin":
        return False, "", "System print handoff is supported only on macOS in this build."
    default_printer = current_default_printer()
    command = ["lp"]
    if default_printer:
        command.extend(["-d", default_printer])
    command.append(snapshot_path)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        return False, default_printer, f"Printer handoff failed: {exc}"
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode == 0:
        return True, default_printer, stdout or "Print job sent successfully."
    detail = stderr or stdout or "Unknown CUPS print error."
    if not default_printer:
        return False, "", f"No default printer is configured. {detail}"
    return False, default_printer, detail


def build_zone_dataset_rows(log_data: dict, zone: dict, zone_number: int) -> list[dict[str, object]]:
    rows = [
        {"Parameter Name": "=== ZONE SNAPSHOT ===", "Value": "", "Units": ""},
        {"Parameter Name": "Zone Number", "Value": zone_number, "Units": ""},
        {"Parameter Name": "Dashboard Log File", "Value": log_data.get("selected_file", ""), "Units": ""},
        {"Parameter Name": "Good Zones X Column", "Value": log_data.get("suggested_x", ""), "Units": ""},
    ]
    length_col = str(log_data.get("length_column", "")).strip()
    if length_col:
        rows.append({"Parameter Name": "Zone Length Column (log)", "Value": length_col, "Units": ""})
    all_rows = log_data.get("rows", [])
    numeric_columns = log_data.get("numeric_columns", [])
    start_index = int(zone.get("startIndex", 0))
    end_index = int(zone.get("endIndex", 0))
    if end_index < start_index:
        start_index, end_index = end_index, start_index
    segment = all_rows[start_index:end_index + 1]
    if not segment:
        return rows
    rows.append({"Parameter Name": f"Zone {zone_number} | Start", "Value": segment[0].get("__x", ""), "Units": log_data.get("suggested_x", "")})
    rows.append({"Parameter Name": f"Zone {zone_number} | End", "Value": segment[-1].get("__x", ""), "Units": log_data.get("suggested_x", "")})
    if length_col:
        start_len = to_float(segment[0].get(length_col))
        end_len = to_float(segment[-1].get(length_col))
        rows.append({"Parameter Name": f"Zone {zone_number} | Length span", "Value": abs(end_len - start_len), "Units": "km"})
        rows.append({"Parameter Name": f"Zone {zone_number} | {length_col} | Min", "Value": min(to_float(item.get(length_col)) for item in segment), "Units": "km"})
        rows.append({"Parameter Name": f"Zone {zone_number} | {length_col} | Max", "Value": max(to_float(item.get(length_col)) for item in segment), "Units": "km"})
    for column in numeric_columns[:10]:
        values = [to_float(item.get(column)) for item in segment]
        rows.append({"Parameter Name": f"Zone {zone_number} | {column} | Avg", "Value": sum(values) / max(1, len(values)), "Units": ""})
        rows.append({"Parameter Name": f"Zone {zone_number} | {column} | Min", "Value": min(values), "Units": ""})
        rows.append({"Parameter Name": f"Zone {zone_number} | {column} | Max", "Value": max(values), "Units": ""})
    return rows


def save_zone_dataset_exports(selected_csv: str, log_data: dict, zones: list[dict]) -> list[str]:
    dataset_file = os.path.basename(str(selected_csv or "").strip())
    if not dataset_file:
        return []
    existing_dataset_path = resolve_dataset_csv_path(dataset_file)
    parent_dir = existing_dataset_path.parent if existing_dataset_path else dataset_directory_for_draw_name(dataset_file)
    identity = parse_draw_dataset_identity(Path(dataset_file).stem)
    canonical_stem = str(identity["draw_stem"]) if identity else Path(dataset_file).stem
    zone_prefixes = {Path(dataset_file).stem, canonical_stem}
    for zone_prefix in zone_prefixes:
        for existing in parent_dir.glob(f"{zone_prefix}_Z*"):
            if existing.is_dir():
                shutil.rmtree(existing, ignore_errors=True)
    created: list[str] = []
    for zone_number, zone in enumerate(zones, start=1):
        zone_path = zone_dataset_target_path(dataset_file, zone_number)
        zone_path.parent.mkdir(parents=True, exist_ok=True)
        zone_rows = build_zone_dataset_rows(log_data, zone, zone_number)
        write_csv_rows(zone_path, zone_rows, ["Parameter Name", "Value", "Units"])
        created.append(str(zone_path))
    return created


def build_dashboard_zone_rows(log_data: dict, zones: list[dict]) -> list[dict]:
    rows = []
    rows.append({"Parameter Name": "—", "Value": "—", "Units": ""})
    rows.append({"Parameter Name": "Dashboard Log File", "Value": log_data.get("selected_file", ""), "Units": ""})
    rows.append({"Parameter Name": "Good Zones Count", "Value": len(zones), "Units": "count"})
    rows.append({"Parameter Name": "Good Zones X Column", "Value": log_data.get("suggested_x", ""), "Units": ""})
    length_col = log_data.get("length_column", "")
    all_rows = log_data.get("rows", [])
    numeric_columns = log_data.get("numeric_columns", [])
    for zone_number, zone in enumerate(zones, start=1):
        start_index = int(zone.get("startIndex", 0))
        end_index = int(zone.get("endIndex", 0))
        if end_index < start_index:
            start_index, end_index = end_index, start_index
        segment = all_rows[start_index:end_index + 1]
        if not segment:
            continue
        rows.append({"Parameter Name": f"Zone {zone_number} | Start", "Value": segment[0].get("__x", ""), "Units": log_data.get("suggested_x", "")})
        rows.append({"Parameter Name": f"Zone {zone_number} | End", "Value": segment[-1].get("__x", ""), "Units": log_data.get("suggested_x", "")})
        if length_col:
            start_len = to_float(segment[0].get(length_col))
            end_len = to_float(segment[-1].get(length_col))
            rows.append({"Parameter Name": f"Zone {zone_number} | Length span", "Value": abs(end_len - start_len), "Units": "km"})
        for column in numeric_columns[:10]:
            values = [to_float(item.get(column)) for item in segment]
            rows.append({"Parameter Name": f"Zone {zone_number} | {column} | Avg", "Value": sum(values) / max(1, len(values)), "Units": ""})
            rows.append({"Parameter Name": f"Zone {zone_number} | {column} | Min", "Value": min(values), "Units": ""})
            rows.append({"Parameter Name": f"Zone {zone_number} | {column} | Max", "Value": max(values), "Units": ""})
        rows.append({"Parameter Name": "", "Value": "", "Units": ""})
    return rows


def save_dashboard_zones_action(payload: dict) -> JsonResponse:
    log_name = str(payload.get("logName", "")).strip()
    selected_csv = str(payload.get("datasetCsv", "")).strip()
    zones = payload.get("zones", []) or []
    if not zones:
        return JsonResponse({"ok": False, "message": "No saved zones to export."}, 400)
    log_data = analyze_log_file(log_name, sample_limit=1600)
    rows = build_dashboard_zone_rows(log_data, zones)
    ok, message = append_dataset_rows(selected_csv, rows)
    status = 200 if ok else 400
    if not ok:
        return JsonResponse({"ok": False, "message": message}, status)
    created_zone_files = save_zone_dataset_exports(selected_csv, log_data, zones)
    return JsonResponse(
        {
            "ok": True,
            "message": f"{message} Created {len(created_zone_files)} zone CSV file(s).",
            "zone_files": created_zone_files,
        },
        status,
    )


def export_dashboard_math_plot_action(payload: dict) -> JsonResponse:
    filename = os.path.basename(str(payload.get("filename", "")).strip()) or "tower_math_plot.png"
    content = str(payload.get("content", "")).strip()
    if not content:
        return JsonResponse({"ok": False, "message": "Missing image content."}, 400)
    if content.startswith("data:"):
        _, _, content = content.partition(",")
    try:
        raw = base64.b64decode(content)
    except Exception:
        return JsonResponse({"ok": False, "message": "Invalid image content."}, 400)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename).strip("._") or "tower_math_plot.png"
    if not safe_name.lower().endswith(".png"):
        safe_name = f"{safe_name}.png"
    plot_exports_dir = DASHBOARD_PLOTS_DIR
    plot_exports_dir.mkdir(parents=True, exist_ok=True)
    target = plot_exports_dir / safe_name
    stem = target.stem
    suffix = target.suffix
    version = 2
    while target.exists():
        target = plot_exports_dir / f"{stem}_{version}{suffix}"
        version += 1
    atomic_write_bytes(target, raw)
    return JsonResponse({
        "ok": True,
        "saved_path": str(target),
        "filename": target.name,
        "message": f"Saved plot to {target}",
    })


def build_home_payload() -> JsonResponse:
    draws = summarize_draw_orders()
    schedule = summarize_schedule()
    parts = summarize_part_orders()
    inventory = summarize_inventory()
    maintenance = summarize_maintenance_rebuild()
    payload = {
        "hero": {
            "title": "Tower command deck",
            "subtitle": "Non-Streamlit rebuild foundation",
            "summary": "A real page system with shared shell, page routing, and live Tower data summaries delivered through lightweight Python APIs.",
        },
        "metrics": [
            {"label": "Active Draws", "value": draws["in_progress"]},
            {"label": "Completed", "value": draws["done"]},
            {"label": "Upcoming Events", "value": len(schedule["upcoming"])},
            {"label": "Open Part Orders", "value": len(parts["open_orders"])},
        ],
        "draws": draws,
        "schedule": schedule,
        "parts": parts,
        "inventory": inventory,
        "maintenance": maintenance,
    }
    return JsonResponse(payload)


def build_schedule_payload() -> JsonResponse:
    return JsonResponse(summarize_schedule())


def build_parts_payload() -> JsonResponse:
    payload = summarize_part_orders()
    payload["inventory"] = summarize_inventory()
    payload["manual_lookup"] = summarize_parts_manual_lookup()
    payload["manual_index_rows"] = get_parts_manual_index().get("rows", [])
    return JsonResponse(payload)


def create_part_order_action(payload: dict) -> JsonResponse:
    rows = read_csv_rows(PART_ORDERS)
    fieldnames = read_csv_fieldnames(PART_ORDERS)
    if not fieldnames:
        fieldnames = [
            "Status", "Part Name", "Serial Number", "Project Name", "Details", "Opened By",
            "Approval Requested From", "Approved", "Approved By", "Approval Date", "Received Date",
            "Received State", "Ordered By", "Date Ordered", "Company", "Inventory Synced",
            "Maintenance Component", "Maintenance Task", "Maintenance Task ID", "Wait ID",
        ]
    part_name = str(payload.get("partName", "")).strip()
    if not part_name:
        return JsonResponse({"ok": False, "message": "Part name is required."}, 400)
    status = str(payload.get("status", "Opened")).strip() or "Opened"
    if status not in PART_STATUS_ORDER or status == "Archived":
        status = "Opened"
    is_approved_step = status in {"Approved", "Ordered", "Received", "Archived"}
    is_ordered_step = status in {"Ordered", "Received", "Archived"}
    is_received_step = status in {"Received", "Archived"}
    new_row = {
        "Status": status,
        "Part Name": part_name,
        "Serial Number": str(payload.get("serialNumber", "")).strip(),
        "Project Name": str(payload.get("project", "")).strip(),
        "Details": str(payload.get("details", "")).strip(),
        "Opened By": str(payload.get("openedBy", "")).strip(),
        "Approval Requested From": str(payload.get("approvalRequestedFrom", "")).strip() if status in {"Wait for Approval", "Approved", "Ordered", "Received"} else "",
        "Approved": "Yes" if is_approved_step else "No",
        "Approved By": str(payload.get("approvedBy", "")).strip() if is_approved_step else "",
        "Approval Date": str(payload.get("approvalDate", "")).strip() if is_approved_step else "",
        "Received Date": str(payload.get("receivedDate", "")).strip() if is_received_step else "",
        "Received State": "Waiting for inventory action" if is_received_step else "",
        "Ordered By": str(payload.get("orderedBy", "")).strip() if is_ordered_step else "",
        "Date Ordered": str(payload.get("dateOrdered", "")).strip() if is_ordered_step else "",
        "Company": str(payload.get("company", "")).strip() if is_ordered_step else "",
        "Inventory Synced": "Pending" if is_received_step else "",
        "Maintenance Component": str(payload.get("maintenanceComponent", "")).strip(),
        "Maintenance Task": str(payload.get("maintenanceTask", "")).strip(),
        "Maintenance Task ID": str(payload.get("maintenanceTaskId", "")).strip(),
        "Wait ID": str(payload.get("waitId", "")).strip(),
    }
    rows.append(new_row)
    write_csv_rows(PART_ORDERS, rows, fieldnames)
    ensure_parts_company(new_row["Company"])
    return JsonResponse({"ok": True, "message": "Part order saved.", "bootstrap": build_bootstrap_payload().body})


def update_part_order_action(payload: dict) -> JsonResponse:
    rows = read_csv_rows(PART_ORDERS)
    fieldnames = read_csv_fieldnames(PART_ORDERS)
    try:
        index = int(payload.get("index"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "Order selection is invalid."}, 400)
    if index < 0 or index >= len(rows):
        return JsonResponse({"ok": False, "message": "Order not found."}, 400)
    row = rows[index]
    was_inventory_synced = str(row.get("Inventory Synced", "")).strip().lower() == "yes"
    current_status = str(row.get("Status", "Opened")).strip() or "Opened"
    status = str(payload.get("status", current_status)).strip() or current_status
    if status not in PART_STATUS_ORDER:
        status = current_status
    if current_status in PART_STATUS_ORDER and status in PART_STATUS_ORDER:
        cur_idx = PART_STATUS_ORDER.index(current_status)
        allowed = PART_STATUS_ORDER[cur_idx + 1:] or [current_status]
        if status not in allowed:
            status = allowed[0]
    row["Status"] = status
    for source_key, field_name in [
        ("partName", "Part Name"),
        ("serialNumber", "Serial Number"),
        ("project", "Project Name"),
        ("details", "Details"),
        ("openedBy", "Opened By"),
        ("approvalRequestedFrom", "Approval Requested From"),
        ("approvedBy", "Approved By"),
        ("approvalDate", "Approval Date"),
        ("receivedDate", "Received Date"),
        ("receivedState", "Received State"),
        ("orderedBy", "Ordered By"),
        ("dateOrdered", "Date Ordered"),
        ("company", "Company"),
        ("inventorySynced", "Inventory Synced"),
        ("maintenanceComponent", "Maintenance Component"),
        ("maintenanceTask", "Maintenance Task"),
        ("maintenanceTaskId", "Maintenance Task ID"),
        ("waitId", "Wait ID"),
    ]:
        if source_key in payload:
            row[field_name] = str(payload.get(source_key, "")).strip()
    if status in {"Approved", "Ordered", "Received", "Archived"}:
        row["Approved"] = "Yes"
    elif status in {"Opened", "Wait for Approval"}:
        row["Approved"] = "No"
    if status == "Wait for Approval" and not str(row.get("Approval Requested From", "")).strip():
        row["Approval Requested From"] = str(payload.get("approvalRequestedFrom", "")).strip()
    is_approved_step = status in {"Approved", "Ordered", "Received", "Archived"}
    is_ordered_step = status in {"Ordered", "Received", "Archived"}
    is_received_step = status in {"Received", "Archived"}
    if not is_approved_step:
        row["Approved By"] = ""
        row["Approval Date"] = ""
    if not is_ordered_step:
        row["Ordered By"] = ""
        row["Date Ordered"] = ""
        row["Company"] = str(payload.get("company", row.get("Company", ""))).strip() if status == "Wait for Approval" else ""
    if not is_received_step:
        row["Received Date"] = ""
        row["Received State"] = ""
        row["Inventory Synced"] = ""
    inventory_action = str(payload.get("inventoryAction", "")).strip()
    inventory_sync_completed = False
    if (
        is_received_step
        and inventory_action in {"Locate in inventory", "Mount on machine"}
        and not was_inventory_synced
    ):
        inventory_sync_completed = sync_part_order_into_inventory(row, payload)
    if is_received_step:
        if inventory_action == "Locate in inventory":
            if inventory_sync_completed or was_inventory_synced:
                row["Received State"] = "Located in inventory"
                row["Inventory Synced"] = "Yes"
            else:
                row["Received State"] = "Waiting for inventory action"
                row["Inventory Synced"] = "Pending"
        elif inventory_action == "Mount on machine":
            if inventory_sync_completed or was_inventory_synced:
                row["Received State"] = "Mounted on machine"
                row["Inventory Synced"] = "Yes"
            else:
                row["Received State"] = "Waiting for inventory action"
                row["Inventory Synced"] = "Pending"
        elif not str(row.get("Received State", "")).strip():
            row["Received State"] = "Waiting for inventory action"
            row["Inventory Synced"] = "Pending"
        elif str(row.get("Received State", "")).strip() == "Waiting for inventory action":
            row["Inventory Synced"] = "Pending"
    ensure_parts_company(row.get("Company", ""))
    rows[index] = row
    write_csv_rows(PART_ORDERS, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Part order updated.", "bootstrap": build_bootstrap_payload().body})


def build_maintenance_payload() -> JsonResponse:
    return JsonResponse(summarize_maintenance_rebuild())


def build_order_draw_payload() -> JsonResponse:
    return JsonResponse(summarize_order_draw())


def build_dashboard_payload() -> JsonResponse:
    return JsonResponse(summarize_dashboard())


def build_dashboard_log_payload(log_name: str | None = None) -> JsonResponse:
    return JsonResponse(analyze_log_file(log_name))


def build_report_center_payload() -> JsonResponse:
    return JsonResponse(summarize_report_center())


def build_report_center_file_payload(file_name: str | None = None) -> Path | None:
    ensure_report_center_dir()
    requested = os.path.basename(str(file_name or "").strip())
    if not requested:
        return None
    candidate = (REPORT_CENTER_DIR / requested).resolve()
    if REPORT_CENTER_DIR.resolve() not in candidate.parents or not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def build_report_center_project_payload(project_name: str | None = None) -> JsonResponse:
    project_name = str(project_name or "").strip()
    return JsonResponse(summarize_development_project(project_name) if project_name else {})


def build_sql_lab_payload() -> JsonResponse:
    return JsonResponse(summarize_sql_lab())


def build_sql_lab_dataset_payload(dataset_name: str | None = None) -> JsonResponse:
    return JsonResponse(analyze_dataset_file(dataset_name))


def build_consumables_payload() -> JsonResponse:
    return JsonResponse(summarize_consumables())


def build_process_setup_payload() -> JsonResponse:
    return JsonResponse(summarize_process_setup())


def build_draw_finalize_payload(selected_csv_override: str | None = None) -> JsonResponse:
    return JsonResponse(summarize_draw_finalize(selected_csv_override))


def build_development_payload() -> JsonResponse:
    return JsonResponse(summarize_development())


def build_development_project_payload(project_name: str | None = None) -> JsonResponse:
    project_name = str(project_name or "").strip()
    return JsonResponse(summarize_development_project(project_name) if project_name else {})


def build_diagnostics_payload() -> JsonResponse:
    return JsonResponse(summarize_diagnostics())


def save_diagnostics_paths_action(payload: dict) -> JsonResponse:
    reset_defaults = str(payload.get("resetDefaults", "")).strip().lower() in {"1", "true", "yes"}
    current_paths = {str(item["key"]): Path(current_path) for item, current_path in current_tracked_paths()}
    defaults = tracked_path_defaults()
    overrides: dict[str, Path] = {}
    desired_paths: dict[str, Path] = {}
    for item in TRACKED_PATH_SPECS:
        key = str(item["key"])
        label = str(item["label"])
        kind = str(item["kind"])
        raw_value = "" if reset_defaults else str(payload.get(key, "")).strip()
        if not reset_defaults and not raw_value:
            return JsonResponse({"ok": False, "message": f"{label} is required."}, 400)
        if reset_defaults:
            normalized = defaults[key]
        else:
            normalized = normalize_tracked_path_value(raw_value)
        if normalized.exists():
            if kind == "dir" and not normalized.is_dir():
                return JsonResponse({"ok": False, "message": f"{label} must point to a folder."}, 400)
            if kind == "file" and not normalized.is_file():
                return JsonResponse({"ok": False, "message": f"{label} must point to a file path, not a folder."}, 400)
        if kind == "dir":
            normalized.mkdir(parents=True, exist_ok=True)
        else:
            normalized.parent.mkdir(parents=True, exist_ok=True)
        desired_paths[key] = normalized
        if not reset_defaults:
            overrides[key] = normalized
    move_notes: list[str] = []
    try:
        for item in TRACKED_PATH_SPECS:
            key = str(item["key"])
            current_path = current_paths[key]
            next_path = desired_paths[key]
            if current_path.resolve() == next_path.resolve():
                continue
            move_notes.extend(relocate_tracked_path(item, current_path, next_path))
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, 400)
    save_tracked_path_overrides({} if reset_defaults else overrides)
    sync_tracked_path_overrides_if_needed(force=True)
    ensure_container_logger_process(force_restart=True)
    message = "Tracked paths reset to Tower defaults." if reset_defaults else "Tracked paths saved and applied to the Python app."
    if move_notes:
        message = f"{message} {move_notes[-1]}"
    return JsonResponse(
        {
            "ok": True,
            "message": message,
            "moveNotes": move_notes,
            "bootstrap": build_bootstrap_payload().body,
        }
    )


def create_full_backup_action(payload: dict | None = None) -> JsonResponse:
    snapshot = create_full_backup_snapshot(trigger="manual")
    return JsonResponse(
        {
            "ok": True,
            "message": f"Full backup created: {snapshot['name']}.",
            "snapshot": snapshot,
            "bootstrap": build_bootstrap_payload().body,
        }
    )


def create_operations_report_action(payload: dict) -> JsonResponse:
    ensure_report_center_dir()
    title = str(payload.get("title", "")).strip() or "Tower Operations Report"
    start_date = str(payload.get("startDate", "")).strip()
    end_date = str(payload.get("endDate", "")).strip()
    sections = [str(item).strip() for item in (payload.get("sections") or []) if str(item).strip()]
    filename = str(payload.get("filename", "")).strip() or f"operations_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    if not filename.lower().endswith(".md"):
        filename = f"{filename}.md"
    output_path = REPORT_CENTER_DIR / Path(filename).name
    atomic_write_text(output_path, build_operations_report_markdown(title, start_date, end_date, sections), encoding="utf-8")
    return JsonResponse(
        {
            "ok": True,
            "message": f"Operations export saved as {output_path.name}.",
            "bootstrap": build_bootstrap_payload().body,
        }
    )


def create_development_report_action(payload: dict) -> JsonResponse:
    ensure_report_center_dir()
    project_name = str(payload.get("projectName", "")).strip()
    if not project_name:
        return JsonResponse({"ok": False, "message": "Choose a development project first."}, 400)
    details = summarize_development_project(project_name)
    if not details.get("project"):
        return JsonResponse({"ok": False, "message": "Selected project was not found."}, 404)
    export_format = str(payload.get("format", "md")).strip().lower() or "md"
    if export_format not in {"md", "html"}:
        return JsonResponse({"ok": False, "message": "Export format is not supported."}, 400)
    default_suffix = "html" if export_format == "html" else "md"
    default_stem = "project_paper" if export_format == "html" else "project_markdown"
    filename = str(payload.get("filename", "")).strip() or f"{default_stem}_{slugify(project_name)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{default_suffix}"
    if not filename.lower().endswith(f".{default_suffix}"):
        filename = f"{filename}.{default_suffix}"
    output_path = REPORT_CENTER_DIR / Path(filename).name
    content = build_development_report_html(project_name) if export_format == "html" else build_development_report_markdown(project_name)
    atomic_write_text(output_path, content, encoding="utf-8")
    encoded_name = quote(output_path.name)
    return JsonResponse(
        {
            "ok": True,
            "message": f"Project export saved as {output_path.name}.",
            "fileName": output_path.name,
            "fileUrl": f"/api/report-center/file?name={encoded_name}&download=1",
            "viewUrl": f"/api/report-center/file?name={encoded_name}&mode=inline",
            "downloadUrl": f"/api/report-center/file?name={encoded_name}&download=1",
            "format": export_format,
            "bootstrap": build_bootstrap_payload().body,
        }
    )


def create_development_project_action(payload: dict) -> JsonResponse:
    project_name = str(payload.get("projectName", "")).strip()
    if not project_name:
        return JsonResponse({"ok": False, "message": "Project name is required."}, 400)
    rows = read_csv_rows(DEVELOPMENT_PROJECTS)
    fieldnames = development_project_fieldnames()
    if any(str(row.get("Project Name", "")).strip() == project_name for row in rows):
        return JsonResponse({"ok": False, "message": "Project already exists."}, 400)
    rows.append(
        {
            "Project Name": project_name,
            "Project Purpose": str(payload.get("purpose", "")).strip(),
            "Target": str(payload.get("target", "")).strip(),
            "Created At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Archived": "False",
            "Summary Title": "",
            "Summary Notes": "",
            "Summary Date": "",
            "Summary Researcher": "",
        }
    )
    write_csv_rows(DEVELOPMENT_PROJECTS, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Development project created.", "bootstrap": build_bootstrap_payload().body})


def save_development_summary_action(payload: dict) -> JsonResponse:
    project_name = str(payload.get("projectName", "")).strip()
    summary_notes = str(payload.get("summaryNotes", "")).strip()
    if not project_name or not summary_notes:
        return JsonResponse({"ok": False, "message": "Project and summary notes are required."}, 400)
    rows = read_csv_rows(DEVELOPMENT_PROJECTS)
    fieldnames = development_project_fieldnames()
    index = next((i for i, row in enumerate(rows) if str(row.get("Project Name", "")).strip() == project_name), None)
    if index is None:
        return JsonResponse({"ok": False, "message": "Project not found."}, 404)
    row = rows[index]
    row["Summary Title"] = str(payload.get("summaryTitle", "")).strip()
    row["Summary Notes"] = summary_notes
    row["Summary Date"] = str(payload.get("summaryDate", "")).strip() or datetime.now().strftime("%Y-%m-%d")
    row["Summary Researcher"] = str(payload.get("summaryResearcher", "")).strip()
    rows[index] = row
    write_csv_rows(DEVELOPMENT_PROJECTS, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Project summary saved.", "bootstrap": build_bootstrap_payload().body})


def create_development_update_action(payload: dict) -> JsonResponse:
    project_name = str(payload.get("projectName", "")).strip()
    notes = str(payload.get("updateNotes", "")).strip()
    if not project_name or not notes:
        return JsonResponse({"ok": False, "message": "Project and update notes are required."}, 400)
    rows = read_csv_rows(EXPERIMENT_UPDATES)
    fieldnames = read_csv_fieldnames(EXPERIMENT_UPDATES) or ["Experiment Title", "Update Date", "Researcher", "Update Notes", "Project Name"]
    rows.append(
        {
            "Experiment Title": str(payload.get("updateTitle", "")).strip() or str(payload.get("experimentTitle", "")).strip(),
            "Update Date": str(payload.get("updateDate", "")).strip() or datetime.now().strftime("%Y-%m-%d"),
            "Researcher": str(payload.get("researcher", "")).strip(),
            "Update Notes": notes,
            "Project Name": project_name,
        }
    )
    write_csv_rows(EXPERIMENT_UPDATES, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Development update saved."})


def create_development_experiment_action(payload: dict) -> JsonResponse:
    project_name = str(payload.get("projectName", "")).strip()
    experiment_title = str(payload.get("experimentTitle", "")).strip()
    if not project_name or not experiment_title:
        return JsonResponse({"ok": False, "message": "Project and experiment title are required."}, 400)
    rows = read_csv_rows(DEVELOPMENT_EXPERIMENTS)
    fieldnames = read_csv_fieldnames(DEVELOPMENT_EXPERIMENTS) or [
        "Project Name",
        "Experiment Title",
        "Date",
        "Researcher",
        "Methods",
        "Purpose",
        "Observations",
        "Results",
        "Is Drawing",
        "Drawing Details",
        "Draw CSV",
        "Attachments",
        "Attachment Captions",
        "Markdown Notes",
    ]
    if any(
        str(row.get("Project Name", "")).strip() == project_name
        and str(row.get("Experiment Title", "")).strip() == experiment_title
        for row in rows
    ):
        return JsonResponse({"ok": False, "message": "That experiment title already exists in this project."}, 400)
    exp_date = str(payload.get("date", "")).strip() or datetime.now().strftime("%Y-%m-%d")
    attachment_paths: list[str] = [item.strip() for item in str(payload.get("attachments", "")).split(";") if item.strip()]
    upload_items = payload.get("attachmentUploads", []) or []
    if upload_items:
        exp_dir = DEVELOPMENT_MEDIA_DIR / slugify(project_name) / f"{slugify(experiment_title)}__{slugify(exp_date)}"
        exp_dir.mkdir(parents=True, exist_ok=True)
        for item in upload_items:
            filename = os.path.basename(str(item.get("name", "")).strip())
            content = str(item.get("content", "")).strip()
            if not filename or not content:
                continue
            try:
                raw = base64.b64decode(content)
            except Exception:
                continue
            candidate = exp_dir / filename
            stem = candidate.stem
            suffix = candidate.suffix
            version = 2
            while candidate.exists():
                candidate = exp_dir / f"{stem}__{version}{suffix}"
                version += 1
            atomic_write_bytes(candidate, raw)
            attachment_paths.append(str(candidate))
    rows.append(
        {
            "Project Name": project_name,
            "Experiment Title": experiment_title,
            "Date": exp_date,
            "Researcher": str(payload.get("researcher", "")).strip(),
            "Methods": str(payload.get("methods", "")).strip(),
            "Purpose": str(payload.get("purpose", "")).strip(),
            "Observations": str(payload.get("observations", "")).strip(),
            "Results": str(payload.get("results", "")).strip(),
            "Is Drawing": "True" if payload.get("isDrawing") else "False",
            "Drawing Details": str(payload.get("drawingDetails", "")).strip(),
            "Draw CSV": str(payload.get("drawCsv", "")).strip(),
            "Attachments": ";".join(attachment_paths),
            "Attachment Captions": "",
            "Markdown Notes": str(payload.get("markdownNotes", "")).strip(),
        }
    )
    write_csv_rows(DEVELOPMENT_EXPERIMENTS, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Experiment saved.", "bootstrap": build_bootstrap_payload().body})


def update_development_experiment_action(payload: dict) -> JsonResponse:
    project_name = str(payload.get("projectName", "")).strip()
    original_title = str(payload.get("originalTitle", "")).strip()
    original_date = str(payload.get("originalDate", "")).strip()
    if not project_name or not original_title or not original_date:
        return JsonResponse({"ok": False, "message": "Choose an existing experiment first."}, 400)
    rows = read_csv_rows(DEVELOPMENT_EXPERIMENTS)
    fieldnames = read_csv_fieldnames(DEVELOPMENT_EXPERIMENTS) or [
        "Project Name",
        "Experiment Title",
        "Date",
        "Researcher",
        "Methods",
        "Purpose",
        "Observations",
        "Results",
        "Is Drawing",
        "Drawing Details",
        "Draw CSV",
        "Attachments",
        "Attachment Captions",
        "Markdown Notes",
    ]
    index = next(
        (
            i for i, row in enumerate(rows)
            if str(row.get("Project Name", "")).strip() == project_name
            and str(row.get("Experiment Title", "")).strip() == original_title
            and str(row.get("Date", "")).strip() == original_date
        ),
        None,
    )
    if index is None:
        return JsonResponse({"ok": False, "message": "Experiment not found."}, 404)
    row = rows[index]
    for source_key, field_name in [
        ("researcher", "Researcher"),
        ("methods", "Methods"),
        ("purpose", "Purpose"),
        ("observations", "Observations"),
        ("results", "Results"),
        ("drawingDetails", "Drawing Details"),
        ("drawCsv", "Draw CSV"),
        ("markdownNotes", "Markdown Notes"),
        ("attachments", "Attachments"),
    ]:
        if source_key in payload:
            row[field_name] = str(payload.get(source_key, "")).strip()
    row["Is Drawing"] = "True" if payload.get("isDrawing") else "False"
    rows[index] = row
    write_csv_rows(DEVELOPMENT_EXPERIMENTS, rows, fieldnames)
    return JsonResponse({"ok": True, "message": "Experiment updated.", "bootstrap": build_bootstrap_payload().body})


def manage_development_project_action(payload: dict) -> JsonResponse:
    project_name = str(payload.get("projectName", "")).strip()
    action = str(payload.get("action", "")).strip().lower()
    if not project_name:
        return JsonResponse({"ok": False, "message": "Choose a project first."}, 400)
    rows = read_csv_rows(DEVELOPMENT_PROJECTS)
    fieldnames = development_project_fieldnames()
    index = next((i for i, row in enumerate(rows) if str(row.get("Project Name", "")).strip() == project_name), None)
    if index is None:
        return JsonResponse({"ok": False, "message": "Project not found."}, 404)
    if action == "archive":
        rows[index]["Archived"] = "True"
        write_csv_rows(DEVELOPMENT_PROJECTS, rows, fieldnames)
        return JsonResponse({"ok": True, "message": "Project archived.", "bootstrap": build_bootstrap_payload().body})
    if action == "restore":
        rows[index]["Archived"] = "False"
        write_csv_rows(DEVELOPMENT_PROJECTS, rows, fieldnames)
        return JsonResponse({"ok": True, "message": "Project restored.", "bootstrap": build_bootstrap_payload().body})
    if action == "delete":
        del rows[index]
        write_csv_rows(DEVELOPMENT_PROJECTS, rows, fieldnames)
        exp_rows = [row for row in read_csv_rows(DEVELOPMENT_EXPERIMENTS) if str(row.get("Project Name", "")).strip() != project_name]
        exp_fields = read_csv_fieldnames(DEVELOPMENT_EXPERIMENTS)
        write_csv_rows(DEVELOPMENT_EXPERIMENTS, exp_rows, exp_fields)
        upd_rows = [row for row in read_csv_rows(EXPERIMENT_UPDATES) if str(row.get("Project Name", "")).strip() != project_name]
        upd_fields = read_csv_fieldnames(EXPERIMENT_UPDATES)
        write_csv_rows(EXPERIMENT_UPDATES, upd_rows, upd_fields)
        return JsonResponse({"ok": True, "message": "Project deleted.", "bootstrap": build_bootstrap_payload().body})
    return JsonResponse({"ok": False, "message": "Unknown project action."}, 400)


def finalize_done_action(payload: dict) -> JsonResponse:
    dataset_name = os.path.basename(str(payload.get("dataset", "")).strip())
    done_description = str(payload.get("doneDescription", "")).strip()
    preform_len_cm = to_float(payload.get("preformLengthCm"))
    if not dataset_name:
        return JsonResponse({"ok": False, "message": "Choose a dataset first."}, 400)
    rows = read_csv_rows(DRAW_ORDERS)
    fieldnames = read_csv_fieldnames(DRAW_ORDERS)
    index = find_order_index_by_dataset(dataset_name)
    if index is None or index >= len(rows):
        return JsonResponse({"ok": False, "message": "No draw order matched the selected dataset."}, 404)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = rows[index]
    row["Status"] = "Done"
    row["Done CSV"] = dataset_name
    row["Assigned Dataset CSV"] = dataset_name
    row["Done Description"] = done_description
    row["Done Timestamp"] = now_str
    row["Status Updated At"] = now_str
    row["Failed CSV"] = ""
    row["Failed Description"] = ""
    row["Failed Timestamp"] = ""
    if preform_len_cm > 0:
        row["Preform Length After Draw (cm)"] = str(preform_len_cm)
    rows[index] = row
    write_csv_rows(DRAW_ORDERS, rows, fieldnames)
    append_dataset_rows(dataset_name, [
        {"Parameter Name": "Done Description", "Value": done_description, "Units": ""},
        {"Parameter Name": "Done Timestamp", "Value": now_str, "Units": ""},
        {"Parameter Name": "Preform Length After Draw", "Value": preform_len_cm, "Units": "cm"},
    ])
    snapshot_ok, snapshot_detail = create_done_snapshot(dataset_name, preform_len_cm, done_description)
    message = "Draw marked as done."
    print_ok = False
    print_detail = ""
    printer_name = ""
    if snapshot_ok:
        message = f"{message} Snapshot saved in done snapshots."
        print_ok, printer_name, print_detail = try_print_snapshot(snapshot_detail)
        if print_ok:
            message = f"{message} Print job sent."
        else:
            printer_label = printer_name or "default printer"
            detail = print_detail or "Printer handoff failed."
            message = f"{message} Print warning: {printer_label} not available. {detail}"
    else:
        message = f"{message} Snapshot warning: {snapshot_detail}"
    return JsonResponse(
        {
            "ok": True,
            "message": message,
            "done_snapshot_path": snapshot_detail if snapshot_ok else "",
            "print_ok": print_ok,
            "print_detail": print_detail,
            "printer_name": printer_name,
            "bootstrap": build_bootstrap_payload().body,
        }
    )


def finalize_failed_action(payload: dict) -> JsonResponse:
    dataset_name = os.path.basename(str(payload.get("dataset", "")).strip())
    failed_description = str(payload.get("failedDescription", "")).strip()
    failed_reason = str(payload.get("failedReason", "")).strip()
    preform_left_cm = to_float(payload.get("preformLeftCm"))
    log_fault = bool(payload.get("logFault"))
    if not dataset_name:
        return JsonResponse({"ok": False, "message": "Choose a dataset first."}, 400)
    rows = read_csv_rows(DRAW_ORDERS)
    fieldnames = read_csv_fieldnames(DRAW_ORDERS)
    index = find_order_index_by_dataset(dataset_name)
    if index is None or index >= len(rows):
        return JsonResponse({"ok": False, "message": "No draw order matched the selected dataset."}, 404)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = rows[index]
    row["Status"] = "Failed"
    row["Failed CSV"] = dataset_name
    row["Assigned Dataset CSV"] = dataset_name
    row["Failed Description"] = failed_description
    row["Failed Reason"] = failed_reason
    row["Failed Timestamp"] = now_str
    row["Status Updated At"] = now_str
    row["Fail Try Count"] = str(int(to_float(row.get("Fail Try Count")) + 1))
    row["Fail Try Last Time"] = now_str
    row["Fail Try Dataset CSV"] = dataset_name
    rows[index] = row
    write_csv_rows(DRAW_ORDERS, rows, fieldnames)
    append_dataset_rows(dataset_name, [
        {"Parameter Name": "Failed Description", "Value": failed_description, "Units": ""},
        {"Parameter Name": "Failed Reason", "Value": failed_reason, "Units": ""},
        {"Parameter Name": "Failed Timestamp", "Value": now_str, "Units": ""},
        {"Parameter Name": "Preform Length After Failed Draw", "Value": preform_left_cm, "Units": "cm"},
    ])
    if log_fault:
        fault_rows = read_csv_rows(FAULTS_LOG)
        fault_fieldnames = read_csv_fieldnames(FAULTS_LOG) or ["fault_id", "fault_ts", "fault_component", "fault_title", "fault_description", "fault_severity", "fault_actor", "fault_source_file", "fault_related_draw"]
        fault_id = str(int(datetime.now().timestamp() * 1000))
        fault_rows.append(
            {
                "fault_id": fault_id,
                "fault_ts": now_str,
                "fault_component": str(payload.get("faultComponent", "")).strip(),
                "fault_title": str(payload.get("faultTitle", "")).strip() or "Draw failure",
                "fault_description": str(payload.get("faultDescription", "")).strip() or failed_description,
                "fault_severity": str(payload.get("faultSeverity", "")).strip() or "medium",
                "fault_actor": str(payload.get("actor", "")).strip() or "rebuild",
                "fault_source_file": dataset_name,
                "fault_related_draw": os.path.splitext(dataset_name)[0],
            }
        )
        write_csv_rows(FAULTS_LOG, fault_rows, fault_fieldnames)
    return JsonResponse({"ok": True, "message": "Draw marked as failed.", "bootstrap": build_bootstrap_payload().body})


def compute_next_planned_draw_date(now_dt: datetime | None = None) -> str:
    now_dt = now_dt or datetime.now()
    weekday = now_dt.weekday()
    next_dt = now_dt + timedelta(days=3 if weekday == 3 else 1)
    return next_dt.strftime("%Y-%m-%d")


def reset_failed_draw_action(payload: dict) -> JsonResponse:
    dataset_name = os.path.basename(str(payload.get("dataset", "")).strip())
    mode = str(payload.get("mode", "")).strip().lower()
    if not dataset_name:
        return JsonResponse({"ok": False, "message": "Choose a dataset first."}, 400)
    if mode not in {"next-day", "pending"}:
        return JsonResponse({"ok": False, "message": "Reset mode is invalid."}, 400)
    rows = read_csv_rows(DRAW_ORDERS)
    fieldnames = read_csv_fieldnames(DRAW_ORDERS)
    index = find_order_index_by_dataset(dataset_name)
    if index is None or index >= len(rows):
        return JsonResponse({"ok": False, "message": "No draw order matched the selected dataset."}, 404)
    row = rows[index]
    schedule_date = compute_next_planned_draw_date(datetime.now()) if mode == "next-day" else ""
    row["Status"] = "Scheduled" if schedule_date else "Pending"
    row["Next Planned Draw Date"] = schedule_date
    row["Active CSV"] = ""
    row["Assigned Dataset CSV"] = ""
    row["Done CSV"] = ""
    row["Done Description"] = ""
    row["Done Timestamp"] = ""
    row["Failed CSV"] = ""
    row["Failed Description"] = ""
    row["Failed Reason"] = ""
    row["Failed Timestamp"] = ""
    row["T&M Moved"] = False
    row["T&M Moved Timestamp"] = ""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row["Status Updated At"] = now_str
    row["Last Reset Timestamp"] = now_str
    rows[index] = row
    write_csv_rows(DRAW_ORDERS, rows, fieldnames)
    if schedule_date:
        message = f"Reset to Scheduled. Next Planned Draw Date = {schedule_date}."
    else:
        message = "Reset to Pending (no schedule)."
    return JsonResponse({"ok": True, "message": message, "bootstrap": build_bootstrap_payload().body})


def build_bootstrap_payload() -> JsonResponse:
    home = build_home_payload().body
    schedule = summarize_schedule()
    parts = build_parts_payload().body
    maintenance = build_maintenance_payload().body
    consumables = summarize_consumables()
    process_setup = summarize_process_setup()
    order_draw = summarize_order_draw()
    dashboard = summarize_dashboard()
    draw_finalize = summarize_draw_finalize()
    diagnostics = summarize_diagnostics()
    report_center = summarize_report_center()
    sql_lab = summarize_sql_lab()
    development = summarize_development()
    return JsonResponse(
        {
            "home": home,
            "schedule": schedule,
            "parts": parts,
            "maintenance": maintenance,
            "consumables": consumables,
            "processSetup": process_setup,
            "orderDraw": order_draw,
            "dashboard": dashboard,
            "drawFinalize": draw_finalize,
            "diagnostics": diagnostics,
            "reportCenter": report_center,
            "sqlLab": sql_lab,
            "development": development,
        }
    )


def development_media_preview_route_action() -> JsonResponse:
    return JsonResponse({"ok": False, "message": "Preview path is required."}, 400)


API_ROUTES = {
    "/api/bootstrap": build_bootstrap_payload,
    "/api/home": build_home_payload,
    "/api/schedule": build_schedule_payload,
    "/api/parts": build_parts_payload,
    "/api/parts/manual-index": build_parts_manual_index_payload,
    "/api/maintenance": build_maintenance_payload,
    "/api/consumables": build_consumables_payload,
    "/api/process-setup": build_process_setup_payload,
    "/api/order-draw": build_order_draw_payload,
    "/api/dashboard": build_dashboard_payload,
    "/api/draw-finalize": build_draw_finalize_payload,
    "/api/report-center": build_report_center_payload,
    "/api/sql-lab": build_sql_lab_payload,
    "/api/development": build_development_payload,
    "/api/development/media-preview": development_media_preview_route_action,
    "/api/data-diagnostics": build_diagnostics_payload,
}

POST_API_ROUTES = {
    "/api/development/project": create_development_project_action,
    "/api/development/summary": save_development_summary_action,
    "/api/development/update": create_development_update_action,
    "/api/development/experiment": create_development_experiment_action,
    "/api/development/experiment-update": update_development_experiment_action,
    "/api/development/manage": manage_development_project_action,
    "/api/draw-finalize/done": finalize_done_action,
    "/api/draw-finalize/failed": finalize_failed_action,
    "/api/draw-finalize/reset": reset_failed_draw_action,
    "/api/report-center/development-export": create_development_report_action,
    "/api/report-center/operations-export": create_operations_report_action,
    "/api/maintenance/complete": complete_maintenance_task_action,
    "/api/maintenance/create-task": create_maintenance_task_action,
    "/api/maintenance/create-parts-orders": create_maintenance_part_orders_action,
    "/api/maintenance/fault": save_maintenance_fault_action,
    "/api/maintenance/delete-task": delete_maintenance_task_action,
    "/api/maintenance/schedule": schedule_maintenance_tasks_action,
    "/api/maintenance/runtime": save_maintenance_runtime_action,
    "/api/maintenance/state": set_maintenance_state_action,
    "/api/maintenance/work-package": save_maintenance_work_package_action,
    "/api/schedule/add": add_schedule_event_action,
    "/api/schedule/delete": delete_schedule_event_action,
    "/api/schedule/save-master": save_schedule_master_action,
    "/api/parts/delete": delete_part_order_action,
    "/api/parts/create": create_part_order_action,
    "/api/parts/inventory-stock": update_inventory_stock_action,
    "/api/parts/unmount": unmount_inventory_item_action,
    "/api/parts/update": update_part_order_action,
    "/api/consumables/containers-save": save_consumables_containers_action,
    "/api/consumables/stock-save": save_consumables_stock_action,
    "/api/consumables/coatings-save": save_consumables_coatings_action,
    "/api/consumables/dies-save": save_consumables_dies_action,
    "/api/consumables/temps-save": save_consumables_temps_action,
    "/api/process-setup/auto-dies": auto_select_process_setup_dies_action,
    "/api/process-setup/manual-start": create_process_setup_manual_action,
    "/api/process-setup/scheduled-start": create_process_setup_scheduled_action,
    "/api/process-setup/select-dataset": select_process_setup_dataset_action,
    "/api/process-setup/save-all": save_process_setup_action,
    "/api/order-draw/create": create_order_draw_action,
    "/api/order-draw/template": save_order_draw_template_action,
    "/api/order-draw/schedule": schedule_pending_order_action,
    "/api/dashboard/save-zones": save_dashboard_zones_action,
    "/api/dashboard/math-plot-export": export_dashboard_math_plot_action,
    "/api/sql-lab/filter": run_sql_lab_filter_action,
    "/api/sql-lab/export-results": create_sql_lab_results_export_action,
    "/api/sql-lab/analysis-scope": run_sql_lab_analysis_scope_action,
    "/api/sql-lab/query": run_sql_lab_query_action,
    "/api/data-diagnostics/paths": save_diagnostics_paths_action,
    "/api/data-diagnostics/full-backup": create_full_backup_action,
}

POST_ROUTE_LOCKS: dict[str, tuple[Path | str, ...]] = {
    "/api/development/project": (DEVELOPMENT_PROJECTS,),
    "/api/development/summary": (DEVELOPMENT_PROJECTS,),
    "/api/development/update": (EXPERIMENT_UPDATES,),
    "/api/development/experiment": (DEVELOPMENT_EXPERIMENTS, DEVELOPMENT_MEDIA_DIR),
    "/api/development/experiment-update": (DEVELOPMENT_EXPERIMENTS,),
    "/api/development/manage": (
        DEVELOPMENT_PROJECTS,
        DEVELOPMENT_EXPERIMENTS,
        EXPERIMENT_UPDATES,
    ),
    "/api/draw-finalize/done": (DRAW_ORDERS, DATASET_DIR, DONE_SNAPSHOTS_DIR),
    "/api/draw-finalize/failed": (DRAW_ORDERS, DATASET_DIR, FAULTS_LOG),
    "/api/draw-finalize/reset": (DRAW_ORDERS,),
    "/api/report-center/development-export": (
        REPORT_CENTER_DIR,
        DEVELOPMENT_PROJECTS,
        DEVELOPMENT_EXPERIMENTS,
        EXPERIMENT_UPDATES,
    ),
    "/api/report-center/operations-export": (REPORT_CENTER_DIR,),
    "/api/sql-lab/export-results": (
        REPORT_CENTER_DIR,
        DATASET_DIR,
        MAINTENANCE_ACTIONS,
        FAULTS_LOG,
    ),
    "/api/maintenance/complete": (MAINTENANCE_DIR, PARTS_INVENTORY),
    "/api/maintenance/create-parts-orders": (MAINTENANCE_DIR, PART_ORDERS),
    "/api/maintenance/fault": (FAULTS_LOG, FAULTS_ACTIONS_LOG),
    "/api/maintenance/delete-task": (MAINTENANCE_DIR, PART_ORDERS, PARTS_INVENTORY),
    "/api/maintenance/schedule": (MAINTENANCE_DIR, TOWER_SCHEDULE),
    "/api/maintenance/runtime": (MAINTENANCE_RUNTIME,),
    "/api/maintenance/state": (MAINTENANCE_STATE,),
    "/api/maintenance/work-package": (MAINTENANCE_DIR,),
    "/api/schedule/add": (TOWER_SCHEDULE,),
    "/api/schedule/delete": (TOWER_SCHEDULE,),
    "/api/schedule/save-master": (TOWER_SCHEDULE,),
    "/api/parts/delete": (PART_ORDERS,),
    "/api/parts/create": (PART_ORDERS, PARTS_COMPANIES),
    "/api/parts/inventory-stock": (PARTS_INVENTORY, PARTS_COMPANIES),
    "/api/parts/unmount": (PARTS_INVENTORY,),
    "/api/parts/update": (PART_ORDERS, PARTS_INVENTORY, PARTS_COMPANIES),
    "/api/consumables/containers-save": (CONTAINER_CONFIG,),
    "/api/consumables/stock-save": (COATING_STOCK, COATING_INVENTORY_META),
    "/api/consumables/coatings-save": (COATING_CONFIG,),
    "/api/consumables/dies-save": (DIES_CONFIG,),
    "/api/consumables/temps-save": (HEATER_CONFIG, TOWER_TEMPS),
    "/api/process-setup/manual-start": (DRAW_ORDERS, DATASET_DIR, SELECTED_CSV_JSON),
    "/api/process-setup/scheduled-start": (DRAW_ORDERS, DATASET_DIR, SELECTED_CSV_JSON),
    "/api/process-setup/select-dataset": (SELECTED_CSV_JSON,),
    "/api/process-setup/save-all": (DATASET_DIR, SELECTED_CSV_JSON),
    "/api/order-draw/create": (DRAW_ORDERS, PROJECTS_TEMPLATES),
    "/api/order-draw/template": (PROJECTS_TEMPLATES,),
    "/api/order-draw/schedule": (DRAW_ORDERS,),
    "/api/dashboard/save-zones": (DATASET_DIR,),
    "/api/dashboard/math-plot-export": (REPORTS_DIR,),
    "/api/data-diagnostics/paths": (TRACKED_PATH_OVERRIDES_FILE,),
    "/api/data-diagnostics/full-backup": (BACKUPS_DIR, TRACKED_PATH_OVERRIDES_FILE),
}


def resolve_post_route_lock_paths(route: str) -> list[Path | str]:
    return list(POST_ROUTE_LOCKS.get(route, ()))


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, Path):
        return str(value)
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except Exception:
            return str(value)
    return value


class TowerRebuildHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(_json_safe(payload), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _send_file(self, path: Path, download_name: str | None = None, inline: bool = False) -> None:
        content_type, _ = mimetypes.guess_type(path.name)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        elif inline:
            self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _resolve_allowed_file(self, requested: str, roots: list[Path], fallback_names: list[Path] | None = None) -> Path | None:
        text = str(requested or "").strip()
        if not text:
            return None
        raw = Path(text).expanduser()
        candidates: list[Path] = []
        normalized_variants = [text]
        stripped_text = _strip_invisible_path_marks(text)
        if stripped_text and stripped_text not in normalized_variants:
            normalized_variants.append(stripped_text)
        for prefix in ("development_media/", "data/development_media/", "manuals/", "maintenance/"):
            for variant in tuple(normalized_variants):
                if variant.startswith(prefix):
                    trimmed = variant[len(prefix):]
                    if trimmed and trimmed not in normalized_variants:
                        normalized_variants.append(trimmed)
        if raw.is_absolute():
            candidates.append(raw.resolve())
            if stripped_text and stripped_text != text:
                candidates.append(Path(stripped_text).expanduser().resolve())
        else:
            for variant in normalized_variants:
                for root in roots:
                    candidates.append((root / variant).resolve())
                file_name = Path(variant).name
                stripped_name = _strip_invisible_path_marks(file_name)
                for root in (fallback_names or []):
                    candidates.append((root / file_name).resolve())
                    if stripped_name and stripped_name != file_name:
                        candidates.append((root / stripped_name).resolve())
        allowed_roots = [root.resolve() for root in roots + (fallback_names or [])]
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if not any(str(candidate).startswith(str(root)) for root in allowed_roots):
                continue
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def do_GET(self) -> None:
        sync_tracked_path_overrides_if_needed()
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/api/maintenance/manual-prefetch":
            params = parse_qs(parsed.query)
            requested = str((params.get("path") or [""])[0]).strip()
            raw_pages = list(params.get("page") or [])
            raw_pages.extend(params.get("pages") or [])
            if not requested:
                self._send_json({"ok": False, "message": "Missing path."}, 400)
                return
            candidate = self._resolve_allowed_file(
                requested,
                roots=[ROOT_DIR, MAINTENANCE_DIR, MANUALS_DIR, EXTERNAL_MANUALS_DIR],
                fallback_names=[MANUALS_DIR, EXTERNAL_MANUALS_DIR, MAINTENANCE_DIR],
            )
            if candidate is None:
                self._send_json({"ok": False, "message": "File not found."}, 404)
                return
            page_numbers: list[int] = []
            for raw_value in raw_pages:
                for piece in str(raw_value or "").split(","):
                    text = piece.strip()
                    if not text:
                        continue
                    try:
                        page_number = int(text)
                    except ValueError:
                        continue
                    if page_number > 0:
                        page_numbers.append(page_number)
                    if len(page_numbers) >= 24:
                        break
                if len(page_numbers) >= 24:
                    break
            priority = str((params.get("priority") or [""])[0]).strip().lower() in {"1", "true", "yes", "priority"}
            scheduled = schedule_manual_page_prefetch(candidate, page_numbers, priority=priority)
            self._send_json({"ok": True, "scheduled": scheduled, "pages": page_numbers[:24], "priority": priority})
            return
        if route == "/api/maintenance/manual-page":
            params = parse_qs(parsed.query)
            requested = str((params.get("path") or [""])[0]).strip()
            page_number = int(str((params.get("page") or ["1"])[0]).strip() or "1")
            if not requested:
                self._send_json({"ok": False, "message": "Missing path."}, 400)
                return
            if manual_page_render_mode() != "image":
                self._send_json(
                    {
                        "ok": False,
                        "message": "Manual page image rendering is unavailable on this platform. Use the PDF viewer mode instead.",
                    },
                    409,
                )
                return
            candidate = self._resolve_allowed_file(
                requested,
                roots=[ROOT_DIR, MAINTENANCE_DIR, MANUALS_DIR, EXTERNAL_MANUALS_DIR],
                fallback_names=[MANUALS_DIR, EXTERNAL_MANUALS_DIR, MAINTENANCE_DIR],
            )
            if candidate is None:
                self._send_json({"ok": False, "message": "File not found."}, 404)
                return
            try:
                rendered_path = render_manual_page_image(candidate, page_number)
            except Exception as exc:
                self._send_json({"ok": False, "message": f"Manual page render failed: {exc}"}, 500)
                return
            self._send_file(rendered_path)
            return
        if route == "/api/maintenance/manual-page-pdf":
            params = parse_qs(parsed.query)
            requested = str((params.get("path") or [""])[0]).strip()
            page_number = int(str((params.get("page") or ["1"])[0]).strip() or "1")
            download_requested = str((params.get("download") or [""])[0]).strip().lower() in {"1", "true", "yes"}
            if not requested:
                self._send_json({"ok": False, "message": "Missing path."}, 400)
                return
            candidate = self._resolve_allowed_file(
                requested,
                roots=[ROOT_DIR, MAINTENANCE_DIR, MANUALS_DIR, EXTERNAL_MANUALS_DIR],
                fallback_names=[MANUALS_DIR, EXTERNAL_MANUALS_DIR, MAINTENANCE_DIR],
            )
            if candidate is None:
                self._send_json({"ok": False, "message": "File not found."}, 404)
                return
            try:
                exported_path = export_manual_page_pdf(candidate, page_number)
            except Exception as exc:
                self._send_json({"ok": False, "message": f"Manual page PDF export failed: {exc}"}, 500)
                return
            self._send_file(exported_path, exported_path.name if download_requested else None, inline=not download_requested)
            return
        if route == "/api/maintenance/manual":
            params = parse_qs(parsed.query)
            requested = str((params.get("path") or [""])[0]).strip()
            if not requested:
                self._send_json({"ok": False, "message": "Missing path."}, 400)
                return
            candidate = self._resolve_allowed_file(
                requested,
                roots=[ROOT_DIR, MAINTENANCE_DIR, MANUALS_DIR, EXTERNAL_MANUALS_DIR],
                fallback_names=[MANUALS_DIR, EXTERNAL_MANUALS_DIR, MAINTENANCE_DIR],
            )
            if candidate is None:
                self._send_json({"ok": False, "message": "File not found."}, 404)
                return
            self._send_file(candidate)
            return
        if route == "/api/development/media":
            params = parse_qs(parsed.query)
            requested = str((params.get("path") or [""])[0]).strip()
            if not requested:
                self._send_json({"ok": False, "message": "Missing path."}, 400)
                return
            candidate = self._resolve_allowed_file(
                requested,
                roots=[DEVELOPMENT_MEDIA_DIR, DATA_DIR / "development_media", ROOT_DIR],
                fallback_names=[DEVELOPMENT_MEDIA_DIR, DATA_DIR / "development_media", ROOT_DIR / "coating_scripts"],
            )
            if candidate is None:
                self._send_json({"ok": False, "message": "File not found."}, 404)
                return
            self._send_file(candidate)
            return
        if route == "/api/development/media-preview":
            params = parse_qs(parsed.query)
            requested = str((params.get("path") or [""])[0]).strip()
            if not requested:
                self._send_bytes(
                    development_media_placeholder_svg("Missing path", "No file path was provided for preview."),
                    "image/svg+xml; charset=utf-8",
                    400,
                )
                return
            candidate = self._resolve_allowed_file(
                requested,
                roots=[DEVELOPMENT_MEDIA_DIR, DATA_DIR / "development_media", ROOT_DIR],
                fallback_names=[DEVELOPMENT_MEDIA_DIR, DATA_DIR / "development_media", ROOT_DIR / "coating_scripts"],
            )
            if candidate is None:
                self._send_bytes(
                    development_media_placeholder_svg(Path(requested).name or "File missing", "Saved attachment path is not available on disk."),
                    "image/svg+xml; charset=utf-8",
                    404,
                )
                return
            suffix = candidate.suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
                self._send_file(candidate, inline=True)
                return
            if suffix == ".pdf":
                try:
                    preview_path = render_manual_page_image(candidate, 1)
                    self._send_file(preview_path, inline=True)
                    return
                except Exception as exc:
                    self._send_bytes(
                        development_media_placeholder_svg(candidate.name, f"PDF preview unavailable: {exc}"),
                        "image/svg+xml; charset=utf-8",
                        200,
                    )
                    return
            self._send_bytes(
                development_media_placeholder_svg(candidate.name, "Open file to inspect this attachment type."),
                "image/svg+xml; charset=utf-8",
                200,
            )
            return
        if route == "/api/dashboard/log":
            params = parse_qs(parsed.query)
            response = build_dashboard_log_payload((params.get("name") or [""])[0])
            self._send_json(response.body, response.status)
            return
        if route == "/api/dashboard/math-plot-export":
            params = parse_qs(parsed.query)
            requested = os.path.basename(str((params.get("name") or [""])[0]).strip())
            if not requested:
                self._send_json({"ok": False, "message": "Missing export name."}, 400)
                return
            candidate = (DASHBOARD_EXPORTS_DIR / requested).resolve()
            if DASHBOARD_EXPORTS_DIR.resolve() not in candidate.parents or not candidate.exists() or not candidate.is_file():
                self._send_json({"ok": False, "message": "Export not found."}, 404)
                return
            self._send_file(candidate, requested)
            return
        if route == "/api/report-center/project":
            params = parse_qs(parsed.query)
            response = build_report_center_project_payload((params.get("name") or [""])[0])
            self._send_json(response.body, response.status)
            return
        if route == "/api/report-center/file":
            params = parse_qs(parsed.query)
            candidate = build_report_center_file_payload((params.get("name") or [""])[0])
            if candidate is None:
                self._send_json({"ok": False, "message": "File not found."}, 404)
                return
            download_requested = str((params.get("download") or [""])[0]).strip().lower() in {"1", "true", "yes"}
            inline_requested = str((params.get("mode") or [""])[0]).strip().lower() == "inline"
            self._send_file(candidate, candidate.name if download_requested and not inline_requested else None, inline=inline_requested)
            return
        if route == "/api/sql-lab/dataset":
            params = parse_qs(parsed.query)
            response = build_sql_lab_dataset_payload((params.get("name") or [""])[0])
            self._send_json(response.body, response.status)
            return
        if route == "/api/draw-finalize":
            params = parse_qs(parsed.query)
            response = build_draw_finalize_payload((params.get("name") or [""])[0])
            self._send_json(response.body, response.status)
            return
        if route == "/api/development/project":
            params = parse_qs(parsed.query)
            response = build_development_project_payload((params.get("name") or [""])[0])
            self._send_json(response.body, response.status)
            return
        if route in API_ROUTES:
            response = API_ROUTES[route]()
            self._send_json(response.body, response.status)
            return

        if route in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html")
            return

        static_path = (STATIC_DIR / route.lstrip("/")).resolve()
        if STATIC_DIR in static_path.parents and static_path.exists() and static_path.is_file():
            self._send_file(static_path)
            return

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        sync_tracked_path_overrides_if_needed()
        parsed = urlparse(self.path)
        route = parsed.path
        if route not in POST_API_ROUTES:
            self._send_json({"ok": False, "message": "Not found"}, 404)
            return
        payload = self._read_json_body()
        try:
            with hold_request_locks(resolve_post_route_lock_paths(route)):
                response = POST_API_ROUTES[route](payload)
        except TimeoutError as exc:
            self._send_json({"ok": False, "message": str(exc)}, 503)
            return
        self._send_json(response.body, response.status)


def run(host: str | None = None, port: int | None = None) -> None:
    ensure_runtime_directories()
    ensure_container_logger_process(force_restart=True)
    bind_host = str(host or DEFAULT_BIND_HOST).strip() or "127.0.0.1"
    bind_port = int(port or DEFAULT_BIND_PORT or 8010)
    server = ThreadingHTTPServer((bind_host, bind_port), TowerRebuildHandler)
    print(f"Tower rebuild running on http://{bind_host}:{bind_port}")
    server.serve_forever()


atexit.register(stop_container_logger_process)


if __name__ == "__main__":
    run()
