# Tower Rebuild

Tower Rebuild is the custom web-app version of the Tower control system. It serves a browser UI from `static/` and a Python API from `server.py`.

## What belongs in git

Commit the rebuild source:

- `server.py`
- `static/`
- `tools/`
- `requirements.txt`
- docs like this `README.md`

Do not commit runtime output:

- backups
- reports
- state caches
- logs
- uploaded local media

Those are ignored by the local `.gitignore` in this folder.

## Python dependencies

```bash
cd tower_rebuild
python3 -m pip install -r requirements.txt
```

## Run locally

```bash
cd tower_rebuild
python3 server.py
```

Default app URL:

[http://127.0.0.1:8010/#/home](http://127.0.0.1:8010/#/home)

## Deployment shape

This app expects a runtime root that contains the live Tower folders such as:

- `data/`
- `config/`
- `maintenance/`
- `data_set_csv/`
- `logs/`
- `reports/`
- `backups/`
- `state/`
- `manuals/`

If you deploy the whole `Tower_work` repo together, the default relative paths work as-is.

If you deploy `tower_rebuild` separately, configure the runtime root with environment variables instead of editing code.

If no runtime root is supplied and the app is not sitting inside a full Tower workspace already, the rebuild now falls back to an OS-standard user-local runtime root automatically:

- Windows: `%LOCALAPPDATA%\\TowerRebuild`
- macOS: `~/Library/Application Support/TowerRebuild`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/TowerRebuild`

That local runtime becomes the app's primary save lane. Optional global mirror paths can then be configured from the Diagnostics page.

## Environment variables

- `TOWER_REBUILD_HOST`
  Default: `127.0.0.1`
- `TOWER_REBUILD_PORT`
  Default: `8010`
- `TOWER_REBUILD_ROOT_DIR`
  Absolute path to the Tower runtime root that contains `data`, `config`, `maintenance`, `logs`, and the other live folders. Use this only for a direct-root deployment where the app should read and write in one shared place.
- `TOWER_REBUILD_LOCAL_ROOT_DIR`
  Optional explicit override for the user-local runtime root used when `TOWER_REBUILD_ROOT_DIR` is not set.
- `TOWER_REBUILD_GLOBAL_ROOT_DIR`
  Optional shared parent folder for local-first deployments. When this is set, the app keeps its primary runtime under the user-local root and mirrors matching runtime folders such as `data`, `maintenance`, `logs`, `reports`, and `state` into the shared root in the background.
- `TOWER_REBUILD_LOCAL_FIRST`
  Optional switch for local-first startup even when the code is sitting inside a full Tower workspace. Use `1`, `true`, `yes`, or `on`.
- `TOWER_REBUILD_DATA_DIR`
  Optional explicit override for the `data` folder if it is not under `ROOT_DIR/data`.
- `TOWER_REBUILD_HELPER_PYTHON`
  Optional Python path for helper scripts like manual indexing.
- `TOWER_REBUILD_MANUAL_PAGE_MODE`
  Optional override for manual rendering mode. Use `image` or `pdf-inline`.

Example:

Direct-root deployment:

```bash
export TOWER_REBUILD_ROOT_DIR="/absolute/path/to/Tower_work"
export TOWER_REBUILD_HOST="0.0.0.0"
export TOWER_REBUILD_PORT="8010"
cd tower_rebuild
python3 server.py
```

Recommended local-first deployment with shared mirror:

```bash
export TOWER_REBUILD_GLOBAL_ROOT_DIR="/absolute/path/to/shared/Tower_work"
export TOWER_REBUILD_HOST="0.0.0.0"
export TOWER_REBUILD_PORT="8010"
cd tower_rebuild
python3 server.py
```

## Local-first storage + global mirror

The rebuild now saves to the local runtime first, then mirrors the same save into optional global targets configured from `#/data-diagnostics`.

- Local saves stay authoritative so the app can keep working even if a shared/network path is down.
- The cleanest setup is one local runtime root per user and one shared global root for the same Tower folder tree.
- Global mirror paths are optional and are stored in `state/global_mirror_path_overrides.json`.
- A single shared root can also be set with `TOWER_REBUILD_GLOBAL_ROOT_DIR`, or later from the Diagnostics page. Matching runtime folders are derived automatically from that one parent path.
- If a global mirror path is unavailable, the save still completes locally and the app retries the global sync in the background.
- Diagnostics shows mirror state per lane, including `LOCAL ONLY`, `READY`, `SYNCING`, `SYNCED`, `WAITING`, `RETRYING`, or `BLOCKED`.
- If the local runtime is empty but a configured global mirror already contains data, the app seeds the local lane from that global copy on startup.

Configuration scope:

- Local path overrides are per user and are stored under the local runtime state folder.
- Global mirror root and explicit global mirror path overrides are shared deployment settings and are stored under the shared deployment state folder.
- In a local-first deployment, this means each operator can keep a different local runtime path while everyone still mirrors to the same shared global Tower tree.

## Cross-platform notes

- On macOS, the manual browser can render page images through the Swift helper when available.
- On Windows and other non-mac environments, the manual browser falls back to inline PDF mode.
- Full backups are app-driven. The app can create them from the Diagnostics page, and the weekly backup policy runs only while the app is active.

## Release preflight

Run the preflight before pushing or deploying:

```bash
cd tower_rebuild
python3 tools/release_preflight.py
```

This checks:

- path leakage / hardcoded workstation paths
- helper runtime resolution
- manual render mode
- folder structure
- bootstrap and diagnostics payloads
- route wiring
- project paper export
- backup source coverage

## Suggested git push flow

From the repo root:

```bash
cd <repo-root>
git status --short
git add tower_rebuild
git commit -m "Add Tower rebuild deployment-ready app"
git push origin <branch-name>
```

Because this repo already has other tracked live-data changes outside `tower_rebuild`, keep the commit scoped to the rebuild folder unless you intentionally want to deploy those runtime data changes too.
