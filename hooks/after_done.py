import os
import platform
import subprocess
from datetime import datetime
import re
from pathlib import Path

import pandas as pd


def run_after_done_hook(
    target_csv: str,
    done_desc: str,
    preform_len_after_cm: float,
    hook_dir: str = "hooks",
    timeout_sec: int = 120,
):

    os.makedirs(hook_dir, exist_ok=True)

    log_path = os.path.join(hook_dir, "after_done_last_run.txt")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    dataset_dir = os.path.join(os.getcwd(), "data_set_csv")
    csv_path = os.path.join(dataset_dir, target_csv)

    # ---------------------------------------------------------
    # SMART ROUNDING (3 decimals)
    # ---------------------------------------------------------
    def fmt(value, units=""):
        try:
            num = float(value)
            if num.is_integer():
                return f"{int(num)} {units}".strip()
            return f"{round(num, 3)} {units}".strip()
        except Exception:
            return f"{value} {units}".strip()

    # ---------------------------------------------------------
    # Logging helper
    # ---------------------------------------------------------
    def log(msg):
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    def current_default_printer():
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

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== AFTER DONE PRINT ===\n")
        f.write(f"{now_str}\n\n")

    if not os.path.exists(csv_path):
        return False, f"CSV not found: {csv_path}"

    df = pd.read_csv(csv_path, keep_default_na=False)

    if "Parameter Name" not in df.columns:
        return False, "Invalid CSV format"

    def get(name):
        m = df["Parameter Name"] == name
        if not m.any():
            return ""
        val = df.loc[m, "Value"].iloc[-1]
        units = df.loc[m, "Units"].iloc[-1]
        return fmt(val, units)

    # ---------------------------------------------------------
    # IDENTITY SECTION
    # ---------------------------------------------------------
    identity = [
        ("Project", get("Order__Fiber Project")),
        ("Draw Name", get("Order__Draw Name")),
        ("Preform", get("Order__Preform Number")),
        ("Geometry", get("Order__Fiber Geometry Type")),
        ("Fiber Diameter", get("Order__Fiber Diameter (µm)")),
        ("Main Coating", get("Order__Main Coating")),
        ("Main Coat Dia", get("Order__Main Coating Diameter (µm)")),
        ("Secondary Coating", get("Order__Secondary Coating")),
        ("Secondary Coat Dia", get("Order__Secondary Coating Diameter (µm)")),
    ]

    # ---------------------------------------------------------
    # T&M SECTION
    # ---------------------------------------------------------
    drum = get("Drum | Selected") or get("Process__Selected Drum")

    tm_section = [
        ("Drum", drum),
        ("Total Saved", get("Total Saved Length")),
        ("Total Cut", get("Total Cut Length")),
        ("Good Zones", get("Good Zones Count")),
        ("Fiber Length End (log end)", get("Fiber Length End (log end)")),
    ]

    # Good Zone Length
    gz_lengths = df[df["Parameter Name"].str.match(r"^Good Zone \d+ Length$", na=False)]
    for _, r in gz_lengths.iterrows():
        tm_section.append((r["Parameter Name"], fmt(r["Value"], r["Units"])))

    # Good Zone Fibre Min/Max
    gz_minmax = df[df["Parameter Name"].str.contains(r"Good Zone .*Fibre Length (?:Min|Max)", regex=True, na=False)]
    for _, r in gz_minmax.iterrows():
        tm_section.append((r["Parameter Name"], fmt(r["Value"], r["Units"])))

    # ---------------------------------------------------------
    # T&M STEP INSTRUCTIONS
    # ---------------------------------------------------------
    steps = []
    step_rows = df[df["Parameter Name"].str.startswith("T&M Step", na=False)]

    step_dict = {}
    for _, r in step_rows.iterrows():
        name = r["Parameter Name"]
        val = r["Value"]
        units = r["Units"]

        m = re.match(r"T&M Step (\d+) (.*)", name)
        if not m:
            continue

        step_num = int(m.group(1))
        label = m.group(2)

        if step_num not in step_dict:
            step_dict[step_num] = {}

        step_dict[step_num][label] = fmt(val, units)

    for s in sorted(step_dict.keys()):
        data = step_dict[s]
        line = f"Step {s}: {data.get('Action','')}"
        if "Length" in data:
            line += f"  →  {data['Length']}"
        if "Zone" in data:
            line += f"  ({data['Zone']})"
        steps.append(line)

        for key in data:
            if "Fibre Length Min" in key or "Fibre Length Max" in key:
                steps.append(f"    {key}: {data[key]}")

    # ---------------------------------------------------------
    # ZONE DATA FILTERING
    # ---------------------------------------------------------
    REMOVE = [
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

    def remove_line(name):
        return any(r in name for r in REMOVE)

    zone_lines = []

    for _, row in df.iterrows():
        name = row["Parameter Name"]
        if not name.startswith("Zone "):
            continue
        if remove_line(name):
            continue

        val = row["Value"]
        units = row["Units"]

        # Pf Process Position → Min/Max only
        if "Pf Process Position" in name:
            if "| Min" in name or "| Max" in name:
                zone_lines.append((name, fmt(val, units)))
            continue

        # Fibre Length → Min/Max only
        if "Fibre Length" in name:
            if "| Min" in name or "| Max" in name:
                zone_lines.append((name, fmt(val, units)))
            continue

        # Others → Avg only
        if "| Avg" in name:
            zone_lines.append((name, fmt(val, units)))

    # ---------------------------------------------------------
    # WRITE FILE
    # ---------------------------------------------------------
    safe_name = target_csv.replace(".csv", "")
    out_file = os.path.join(hook_dir, f"{safe_name}_PRINT.txt")

    with open(out_file, "w", encoding="utf-8") as f:

        f.write("============================================================\n")
        f.write("DRAW REPORT — CLEAN SUMMARY\n")
        f.write("============================================================\n")
        f.write(f"Time: {now_str}\n")
        f.write(f"CSV: {target_csv}\n")
        f.write(f"Preform Length After Draw: {fmt(preform_len_after_cm, 'cm')}\n")
        if done_desc:
            f.write(f"Done Description: {done_desc}\n")
        f.write("\n")

        f.write("******************* T&M SECTION ***************************\n")
        for k, v in tm_section:
            if v:
                f.write(f"{k}: {v}\n")
        f.write("\n")

        if steps:
            f.write("T&M INSTRUCTIONS:\n")
            for s in steps:
                f.write(f"{s}\n")
            f.write("\n")

        f.write("******************* IDENTITY *******************************\n")
        for k, v in identity:
            if v:
                f.write(f"{k}: {v}\n")
        f.write("\n")

        f.write("******************* ZONE DATA ******************************\n")
        for k, v in zone_lines:
            f.write(f"{k}: {v}\n")

        f.write("\n============================================================\n")

    log(f"Wrote file: {out_file}")

    if platform.system().lower().startswith("darwin"):
        default_printer = current_default_printer()
        lp_command = ["lp"]
        if default_printer:
            lp_command.extend(["-d", default_printer])
        lp_command.append(out_file)
        result = subprocess.run(
            lp_command,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode == 0:
            log(f"Sent to printer: {default_printer or 'system default'}")
            if stdout:
                log(stdout)
            return True, f"Printed clean summary: {out_file}"
        detail = stderr or stdout or "Unknown CUPS print error."
        log(f"Printer handoff failed: {detail}")
        if not default_printer:
            return False, f"Snapshot created but no default printer is configured: {out_file}"
        return False, f"Snapshot created but printer handoff failed ({default_printer}): {detail}"

    return True, f"Created clean summary: {out_file}"
