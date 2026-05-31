# helpers/process_setup_state.py
import streamlit as st
import pandas as pd


def _safe_float(x, default=None):
    try:
        s = str(x).strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default


def apply_dataset_process_rows_to_state(df_params: pd.DataFrame, overwrite: bool = True) -> int:
    """
    Load saved Process__ rows from a dataset CSV back into canonical session_state keys.
    Returns number of keys updated.
    """
    if df_params is None or df_params.empty or "Parameter Name" not in df_params.columns:
        return 0

    if "Value" not in df_params.columns:
        return 0

    # CSV row name -> (state_key, caster)
    mapping = {
        "Process__Entry Fiber Diameter": ("order_fiber_diam", float),
        "Process__Furnace Temperature": ("order_furnace_temp_c", float),
        "Process__Entry Fiber Diameter Tol": ("order_fiber_diam_tol", float),
        "Process__Target First Coating Diameter": ("order_main_diam", float),
        "Process__Target First Coating Diameter Tol": ("order_main_diam_tol", float),
        "Process__Target Second Coating Diameter": ("order_sec_diam", float),
        "Process__Target Second Coating Diameter Tol": ("order_sec_diam_tol", float),
        "Process__Primary Coating": ("order_coating_main", str),
        "Process__Secondary Coating": ("order_coating_secondary", str),
        "Process__Primary Coating Temperature": ("order_main_coat_temp_c", float),
        "Process__Secondary Coating Temperature": ("order_sec_coat_temp_c", float),
        "Process__Primary Die Name": ("coating_primary_die", str),
        "Process__Secondary Die Name": ("coating_secondary_die", str),
        "Process__Coating Die Selection Mode": ("coating_die_mode", str),
        "Process__Draw Speed": ("order_speed", float),
        "Process__First Coating Diameter (Theoretical)": ("coating_pred_fc_um", float),
        "Process__Second Coating Diameter (Theoretical)": ("coating_pred_sc_um", float),
        "Process__Ideal Primary Die (µm)": ("coating_ideal_primary_die_um", float),
        "Process__Ideal Secondary Die (µm)": ("coating_ideal_secondary_die_um", float),
        "Process__Pred @ Ideal FC (µm)": ("coating_fc_at_ideal_primary_um", float),
        "Process__Pred @ Ideal SC (µm)": ("coating_sc_at_ideal_secondary_um", float),
    }

    def _is_empty(v) -> bool:
        return str(v).strip().lower() in ("", "none", "nan")

    changed = 0
    by_name = {}
    for _, row in df_params.iterrows():
        name = str(row.get("Parameter Name", "")).strip()
        if not name:
            continue
        by_name[name] = row.get("Value", "")

    for param_name, (state_key, caster) in mapping.items():
        if param_name not in by_name:
            continue
        raw = by_name.get(param_name, "")
        val = _safe_float(raw, default="") if caster is float else str(raw).strip()
        if overwrite or _is_empty(st.session_state.get(state_key, "")):
            st.session_state[state_key] = val
            changed += 1

    return changed

def apply_order_row_to_process_setup_state(order_row: dict, overwrite: bool = True):
    """
    Canonical mapping: Order row -> session_state keys used by BOTH Order tab and Process Setup.
    """
    mapping = {
        "Main Coating": ("order_coating_main", str),
        "Secondary Coating": ("order_coating_secondary", str),
        "Main Coating Temperature (°C)": ("order_main_coat_temp_c", float),
        "Secondary Coating Temperature (°C)": ("order_sec_coat_temp_c", float),

        "Fiber Diameter (µm)": ("order_fiber_diam", float),
        "Fiber Diameter Tol (± µm)": ("order_fiber_diam_tol", float),
        "Main Coating Diameter (µm)": ("order_main_diam", float),
        "Main Coating Diameter Tol (± µm)": ("order_main_diam_tol", float),
        "Secondary Coating Diameter (µm)": ("order_sec_diam", float),
        "Secondary Coating Diameter Tol (± µm)": ("order_sec_diam_tol", float),
        "Tension (g)": ("order_tension", float),
        "Draw Speed (m/min)": ("order_speed", float),

        "Fiber Geometry Type": ("order_fiber_geometry_required", str),
        "Preform Diameter (mm)": ("process_setup_prefill_preform_diameter_mm", float),
        "Tiger Cut (%)": ("order_tiger_cut_pct", float),
        "Octagonal F2F (mm)": ("order_oct_f2f_mm", float),
        "Furnace Temperature (°C)": ("order_furnace_temp_c", float),

        "Preform Number": ("process_setup_prefill_preform_number", str),
        "Fiber Project": ("process_setup_prefill_fiber_project", str),
        "Notes": ("process_setup_prefill_notes", str),
        "Priority": ("process_setup_prefill_priority", str),
        "Order Opener": ("process_setup_prefill_opener", str),
        "Required Length (m) (for T&M+costumer)": ("process_setup_prefill_required_length_m", float),
        "Good Zones Count (required length zones)": ("process_setup_prefill_good_zones_count", float),
    }

    def is_empty(v):
        return str(v).strip().lower() in ("", "0", "0.0", "none", "nan")

    for order_col, (key, caster) in mapping.items():
        raw = order_row.get(order_col, "")
        if caster is float:
            val = _safe_float(raw, default="")
        else:
            val = str(raw).strip()

        if overwrite:
            st.session_state[key] = val
        else:
            cur = st.session_state.get(key, "")
            if is_empty(cur):
                st.session_state[key] = val
