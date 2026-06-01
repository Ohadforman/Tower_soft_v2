# Tower Soft V2

Tower Soft V2 is the current Tower operations workspace. It contains the live data folders, support scripts, legacy Streamlit tooling, and the newer browser-based rebuild app used for deployment.

The current deploy target is:

- `/Users/ohadformanair/PycharmProjects/Tower_work/tower_rebuild`

That rebuild serves the app UI from `static/` and the Python API from `server.py`, while reading and writing the live Tower runtime folders in this repo.

## What This Repo Contains

- `tower_rebuild/`
  The current deployable app (`server.py` + browser UI).
- `data/`
  Core live CSV state such as draw orders, schedule, consumables, SQL inputs, and experiment tables.
- `data_set_csv/`
  Full draw datasets used by SQL Lab.
- `config/`
  App configuration files for coatings, dies, heaters, containers, and related runtime setup.
- `maintenance/`
  Maintenance tasks, work packages, and fault logs.
- `reports/`
  Generated reports, exports, and diagnostics outputs.
- `state/`
  App-managed runtime state and caches.
- `manuals/`
  PDFs and operator manuals used by maintenance and parts flows.
- `app/`, `renders/`, `helpers/`, `scripts/`
  Legacy Streamlit app and supporting utilities that are still kept in the workspace.

## Recommended Run Modes

### 1. Rebuild app (recommended)

```bash
cd tower_rebuild
python3 -m pip install -r requirements.txt
python3 server.py
```

Default URL:

- [http://127.0.0.1:8010/#/home](http://127.0.0.1:8010/#/home)

### 2. Full repo environment

Use this when you want the broader mixed workspace, including legacy Streamlit tools and supporting scripts:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Dataset Save Hierarchy

The full draw datasets used by SQL Lab are saved under `data_set_csv/` in the newer foldered format:

```text
data_set_csv/
  <preform-or-draw-folder>/
    <draw>.csv
    <draw>_Z1/
      <draw>_Z1.csv
    <draw>_Z2/
      <draw>_Z2.csv
```

Example:

```text
data_set_csv/FLOWP4045/FLOWP4045F1.csv
data_set_csv/FLOWP4045/FLOWP4045F1_Z1/FLOWP4045F1_Z1.csv
```

Meaning:

- the top-level CSV inside the draw folder is the full dataset
- nested `_Z*` folders contain zone snapshots
- SQL Lab reads the full dataset CSVs, not the zone snapshots, unless explicitly extended to do so

## Where SQL Lab Reads From

SQL Lab reads recursively from the dataset workspace root:

- default root: `data_set_csv/`
- one full draw CSV file = one draw
- zone snapshot CSVs are excluded from the normal draw scan
- maintenance and fault overlays come from the maintenance logs, not from the draw CSVs

## Path Management

Runtime roots can be changed from:

- `Data Diagnostics -> Full path manager`

Important managed roots include:

- Dataset Workspace
- Logs
- Reports
- Backups
- Manuals
- Tower containers feed / logger paths

For the rebuild app, the main environment variables are:

- `TOWER_REBUILD_ROOT_DIR`
- `TOWER_REBUILD_DATA_DIR`
- `TOWER_REBUILD_HOST`
- `TOWER_REBUILD_PORT`
- `TOWER_REBUILD_HELPER_PYTHON`
- `TOWER_REBUILD_MANUAL_PAGE_MODE`

## Pre-deploy Checks

From the repo root:

```bash
python3 tower_rebuild/tools/release_preflight.py
python3 tower_rebuild/tools/network_smoke_test.py
python3 tower_rebuild/tools/full_flow_smoke_test.py
```

If you are validating the legacy app side too:

```bash
python3 scripts/cli/run_v2_deploy_protocol.py
```

Helpful docs:

- [Architecture](docs/ARCHITECTURE.md)
- [Operations](docs/OPERATIONS.md)
- [V2 Deployment Protocol](docs/V2_DEPLOY_PROTOCOL.md)
- [Path Map](docs/path_map.md)
- [Maintenance Operator Guide](docs/MAINTENANCE_OPERATOR_GUIDE.md)

## Dependency Notes

- `requirements.txt`
  Full workspace environment for this repo, including legacy Streamlit tooling and rebuild support.
- `tower_rebuild/requirements.txt`
  Leaner dependency set for the rebuild app only.

## Repository Notes

- This repo intentionally contains live runtime folders because the app works directly against them.
- Generated diagnostics and backup artifacts are partly ignored by `.gitignore`, but some operational data is intentionally tracked.
- If you deploy only `tower_rebuild/`, make sure the runtime root folders (`data/`, `config/`, `maintenance/`, `data_set_csv/`, `logs/`, `reports/`, `state/`, `manuals/`) are available to it.

## Release Notes

### v2.0.0

This release is the first clean Tower Soft V2 snapshot prepared for the new repository.

Included in this release:

- the rebuild app in `tower_rebuild/`
- the updated repo-root setup and dependency docs
- foldered `data_set_csv/` hierarchy for full draw datasets and zone snapshots
- SQL Lab / maintenance / consumables / draw-finalize changes from the current V2 app line
- migration and smoke-test tooling used to validate save paths and deploy readiness

Intentionally not bundled as part of the curated release snapshot:

- volatile runtime churn such as active logs, caches, transient exports, and backup byproducts
- smoke-only generated dataset folders used just for verification
- machine-local temporary outputs that are not part of the intended source snapshot

Recommended release verification:

```bash
python3 tower_rebuild/tools/release_preflight.py
python3 tower_rebuild/tools/network_smoke_test.py
python3 tower_rebuild/tools/full_flow_smoke_test.py
```
