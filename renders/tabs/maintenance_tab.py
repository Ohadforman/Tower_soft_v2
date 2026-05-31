def render_maintenance_tab(P):
    import os, json, glob, time, math
    import datetime as dt
    
    import numpy as np
    import pandas as pd
    import streamlit as st
    import plotly.graph_objects as go
    from renders.tabs.corr_outliers import render_corr_outliers_tab
    from helpers.activity_indicator import record_activity_start
    from helpers.duckdb_io import get_duckdb_conn
    from helpers.maintenance_status import NORMALIZE_MAP, compute_maintenance_status_df
    from helpers.maintenance_readiness import compute_readiness, is_parts_conditional
    from helpers.maintenance_state import merge_state_into_df, set_task_state, set_tasks_state
    from helpers.maintenance_parts_reservation import (
        list_task_reservations,
        reserve_parts_for_task,
        release_task_reservations,
        consume_task_reservations,
    )
    from helpers.orders_io import count_dataset_draws

    st.markdown(
        """
        <style>
          .maint-title{
            font-size: 1.62rem;
            font-weight: 900;
            margin: 0 0 2px 0;
            padding-top: 6px;
            line-height: 1.2;
            color: rgba(236,248,255,0.98);
            text-shadow: 0 0 14px rgba(86,178,255,0.22);
          }
          .maint-sub{
            margin: 0 0 8px 0;
            font-size: 0.90rem;
            color: rgba(188,224,248,0.88);
          }
          .maint-top-spacer{
            height: 6px;
          }
          .maint-line{
            height: 1px;
            margin: 0 0 12px 0;
            background: linear-gradient(90deg, rgba(120,200,255,0.58), rgba(120,200,255,0.0));
          }
          .maint-help{
            border: 1px solid rgba(128,206,255,0.22);
            border-radius: 12px;
            background: linear-gradient(180deg, rgba(14,32,56,0.30), rgba(8,16,28,0.22));
            padding: 8px 10px;
            margin: 4px 0 12px 0;
            color: rgba(201,230,249,0.90);
            font-size: 0.84rem;
          }
          .maint-help b{
            color: rgba(226,245,255,0.97);
          }
          .maint-help-green{
            border: 1px solid rgba(92,226,146,0.42);
            border-radius: 12px;
            background: linear-gradient(180deg, rgba(18,44,32,0.42), rgba(10,26,20,0.30));
            padding: 10px 12px;
            margin: 4px 0 12px 0;
            color: rgba(170,255,206,0.98);
            font-size: 0.86rem;
            line-height: 1.45;
          }
          .maint-help-green b{
            color: rgba(214,255,232,0.99);
          }
          .maint-lane-shell{
            padding: 6px 0 4px 0;
            margin: 8px 0 10px 0;
            border: 0;
            background: transparent;
          }
          .maint-lane-title{
            font-size: 0.94rem;
            font-weight: 840;
            color: rgba(232,246,255,0.98);
            margin: 0 0 1px 0;
          }
          .maint-lane-sub{
            font-size: 0.78rem;
            color: rgba(170,204,228,0.74);
            margin: 0 0 6px 0;
          }
          .maint-section-title{
            margin: 10px 0 8px 0;
            padding-left: 8px;
            border-left: 3px solid rgba(120,200,255,0.62);
            font-size: 1.22rem;
            font-weight: 850;
            color: rgba(230,246,255,0.98);
            text-shadow: 0 0 10px rgba(84,174,255,0.18);
          }
          .st-key-maint_focus_status div[data-baseweb="tag"],
          .st-key-maint_focus_status span[data-baseweb="tag"],
          .st-key-maint_focus_components div[data-baseweb="tag"],
          .st-key-maint_focus_components span[data-baseweb="tag"],
          .st-key-maint_focus_groups div[data-baseweb="tag"],
          .st-key-maint_focus_groups span[data-baseweb="tag"]{
            background: linear-gradient(180deg, rgba(70,160,238,0.94), rgba(32,96,168,0.92)) !important;
            background-color: rgba(44,124,206,0.94) !important;
            border: 1px solid rgba(170,232,255,0.82) !important;
            color: rgba(244,252,255,0.99) !important;
            box-shadow: 0 0 0 1px rgba(108,198,255,0.26), 0 4px 10px rgba(10,46,84,0.32) !important;
          }
          .st-key-maint_focus_status div[data-baseweb="tag"] > *,
          .st-key-maint_focus_status span[data-baseweb="tag"] > *,
          .st-key-maint_focus_components div[data-baseweb="tag"] > *,
          .st-key-maint_focus_components span[data-baseweb="tag"] > *,
          .st-key-maint_focus_groups div[data-baseweb="tag"] > *,
          .st-key-maint_focus_groups span[data-baseweb="tag"] > *{
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            color: rgba(244,252,255,0.99) !important;
          }
          .st-key-maint_focus_status div[data-baseweb="tag"] svg,
          .st-key-maint_focus_status span[data-baseweb="tag"] svg,
          .st-key-maint_focus_components div[data-baseweb="tag"] svg,
          .st-key-maint_focus_components span[data-baseweb="tag"] svg,
          .st-key-maint_focus_groups div[data-baseweb="tag"] svg,
          .st-key-maint_focus_groups span[data-baseweb="tag"] svg{
            fill: rgba(238,250,255,0.98) !important;
          }
          div[data-testid="stButton"] > button{
            border-radius: 12px !important;
            border: 1px solid rgba(138,214,255,0.58) !important;
            background: linear-gradient(180deg, rgba(28,74,120,0.72), rgba(12,36,68,0.66)) !important;
            color: rgba(236,248,255,0.98) !important;
            box-shadow: 0 8px 18px rgba(8,30,58,0.32), 0 0 12px rgba(74,170,255,0.18) !important;
          }
          div[data-testid="stButton"] > button:hover{
            border-color: rgba(188,238,255,0.86) !important;
            box-shadow: 0 12px 24px rgba(8,30,58,0.36), 0 0 16px rgba(96,194,255,0.30) !important;
          }
          div[data-testid="stButton"] > button[kind="primary"]{
            border-color: rgba(170,232,255,0.84) !important;
            background: linear-gradient(180deg, rgba(76,168,255,0.90), rgba(32,98,172,0.88)) !important;
            box-shadow: 0 14px 24px rgba(12, 68, 124, 0.40), 0 0 18px rgba(96,194,255,0.34) !important;
          }
          div[data-testid="stButton"] > button:disabled{
            opacity: 0.78 !important;
            color: rgba(212,238,255,0.92) !important;
            border-color: rgba(128,206,255,0.32) !important;
            background: linear-gradient(180deg, rgba(24,62,102,0.52), rgba(12,34,64,0.48)) !important;
          }
          div[data-testid="stExpander"] details{
            border: 1px solid rgba(132,214,255,0.22) !important;
            border-radius: 12px !important;
            background: linear-gradient(165deg, rgba(12,24,42,0.56), rgba(10,18,30,0.40)) !important;
          }
          div[data-testid="stDataFrame"]{
            border: 1px solid rgba(132,214,255,0.22) !important;
            border-radius: 12px !important;
            overflow: hidden !important;
          }
          /* Force blue style for multi-select tags in this tab (remove red default chips). */
          div[data-testid="stMultiSelect"] div[data-baseweb="tag"],
          div[data-testid="stMultiSelect"] span[data-baseweb="tag"]{
            background: linear-gradient(180deg, rgba(70,160,238,0.94), rgba(32,96,168,0.92)) !important;
            background-color: rgba(44,124,206,0.94) !important;
            border: 1px solid rgba(170,232,255,0.82) !important;
            color: rgba(244,252,255,0.99) !important;
            box-shadow: 0 0 0 1px rgba(108,198,255,0.26), 0 4px 10px rgba(10,46,84,0.32) !important;
          }
          div[data-testid="stMultiSelect"] div[data-baseweb="tag"] > *,
          div[data-testid="stMultiSelect"] span[data-baseweb="tag"] > *{
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            color: rgba(244,252,255,0.99) !important;
          }
          div[data-testid="stMultiSelect"] div[data-baseweb="tag"] svg,
          div[data-testid="stMultiSelect"] span[data-baseweb="tag"] svg{
            fill: rgba(238,250,255,0.98) !important;
          }
          /* Blue controls instead of red accents. */
          .stRadio input[type="radio"],
          .stCheckbox input[type="checkbox"],
          .stSlider input[type="range"]{
            accent-color: #56b8ff !important;
          }
          /* Blue input/select shells. */
          div[data-baseweb="select"] > div,
          div[data-testid="stTextInput"] input,
          div[data-testid="stTextArea"] textarea,
          div[data-testid="stNumberInput"] input{
            border-color: rgba(132,214,255,0.40) !important;
            box-shadow: none !important;
          }
          div[data-baseweb="select"] > div:hover,
          div[data-testid="stTextInput"] input:hover,
          div[data-testid="stTextArea"] textarea:hover,
          div[data-testid="stNumberInput"] input:hover{
            border-color: rgba(176,232,255,0.72) !important;
          }
          .maint-prep-grid{
            display:grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin: 8px 0 12px 0;
          }
          .maint-prep-card{
            border-radius: 14px;
            padding: 12px 14px;
            border: 1px solid rgba(128,206,255,0.20);
            background: linear-gradient(180deg, rgba(14,32,56,0.30), rgba(8,16,28,0.22));
          }
          .maint-prep-card.k-blue{
            border-color: rgba(116,194,255,0.35);
          }
          .maint-prep-card.k-green{
            border-color: rgba(98,228,152,0.34);
            background: linear-gradient(180deg, rgba(16,42,30,0.34), rgba(10,24,18,0.24));
          }
          .maint-prep-card.k-amber{
            border-color: rgba(255,196,98,0.34);
            background: linear-gradient(180deg, rgba(52,40,12,0.34), rgba(28,22,10,0.24));
          }
          .maint-prep-card.k-red{
            border-color: rgba(255,112,112,0.34);
            background: linear-gradient(180deg, rgba(48,18,18,0.34), rgba(26,10,10,0.24));
          }
          .maint-prep-k{
            font-size: 0.76rem;
            font-weight: 760;
            color: rgba(188,224,248,0.90);
            margin-bottom: 5px;
          }
          .maint-prep-v{
            font-size: 1.9rem;
            line-height: 1.0;
            font-weight: 900;
            margin-bottom: 4px;
          }
          .maint-prep-note{
            font-size: 0.76rem;
            color: rgba(184,214,234,0.78);
          }
          .maint-board-shell{
            border: 1px solid rgba(132,214,255,0.18);
            border-radius: 14px;
            padding: 10px 12px;
            background: linear-gradient(180deg, rgba(10,22,38,0.22), rgba(7,14,24,0.14));
            margin: 6px 0 12px 0;
          }
          .maint-board-title{
            font-size: 0.88rem;
            font-weight: 780;
            color: rgba(232,246,255,0.96);
            margin: 0 0 6px 0;
          }
          @media (max-width: 1100px){
            .maint-prep-grid{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="maint-top-spacer"></div>', unsafe_allow_html=True)
    st.markdown('<div class="maint-title">🧰 Maintenance</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="maint-sub">Maintenance planning, fault handling, usage analytics, and manuals in one place.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="maint-line"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="maint-help"><b>Tip:</b> Update status inputs first, then use Dashboard/Future Schedule and mark tasks done.</div>',
        unsafe_allow_html=True,
    )
    
    # =========================================================
    # Small utils
    # =========================================================
    def safe_str(x) -> str:
        try:
            if x is None:
                return ""
            if isinstance(x, float) and np.isnan(x):
                return ""
            return str(x)
        except Exception:
            return ""

    def split_task_groups(v) -> list:
        s = safe_str(v).strip()
        if not s:
            return []
        out = []
        for p in s.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
            pv = p.strip()
            if pv:
                out.append(pv)
        uniq = []
        seen = set()
        for p in out:
            lk = p.lower()
            if lk not in seen:
                uniq.append(p)
                seen.add(lk)
        return uniq

    def is_tool_like_part_name(part_name: str) -> bool:
        p = safe_str(part_name).strip().lower()
        if not p:
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
        return any(tok in p for tok in tool_tokens)

    def row_task_groups(row) -> list:
        groups = []
        groups.extend(split_task_groups(row.get("Task_Group", "")))
        groups.extend(split_task_groups(row.get("Task_Groups", "")))
        uniq = []
        seen = set()
        for g in groups:
            lk = g.lower()
            if lk not in seen:
                uniq.append(g)
                seen.add(lk)
        return uniq

    def row_has_any_group(row, selected_groups) -> bool:
        if not selected_groups:
            return True
        row_set = {g.lower() for g in row_task_groups(row)}
        return any(safe_str(g).strip().lower() in row_set for g in selected_groups)

    def build_group_key(groups) -> str:
        if not groups:
            return ""
        seen = set()
        out = []
        for g in groups:
            gv = safe_str(g).strip().lower()
            if not gv or gv in seen:
                continue
            out.append(gv)
            seen.add(gv)
        return "|" + "|".join(out) + "|" if out else ""

    def filter_df_by_groups(df: pd.DataFrame, selected_groups) -> pd.DataFrame:
        if df is None or df.empty or not selected_groups:
            return df
        if "Task_Groups_Key" not in df.columns:
            return df[df.apply(lambda r: row_has_any_group(r, selected_groups), axis=1)].copy()
        needles = [f"|{safe_str(g).strip().lower()}|" for g in selected_groups if safe_str(g).strip()]
        if not needles:
            return df
        key_series = df["Task_Groups_Key"].astype(str)
        mask = pd.Series(False, index=df.index)
        for needle in needles:
            mask = mask | key_series.str.contains(needle, regex=False, na=False)
        return df[mask].copy()

    def _clean_txt(s):
        import re
        return re.sub(r"\s+", " ", str(s or "")).strip()

    def _is_num_line(s: str) -> bool:
        import re
        return bool(re.fullmatch(r"\d+(\.\d+)?", _clean_txt(s)))

    def _is_part_num_line(s: str) -> bool:
        import re
        t = _clean_txt(s).upper().rstrip(".")
        if not t or " " in t:
            return False
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._/\\-]*", t):
            return False
        if not re.search(r"\d", t):
            return False
        if re.fullmatch(r"\d{1,2}", t):
            return False
        return True

    def _looks_like_desc(s: str) -> bool:
        import re
        t = _clean_txt(s)
        if not t:
            return False
        if _is_num_line(t) or _is_part_num_line(t):
            return False
        if re.fullmatch(r"[A-Z]-[A-Z]", t):
            return False
        return len(t) >= 3

    def _extract_parts_rows_from_lines(lines, manual_name: str, page_no: int):
        rows = []
        start = 0
        for i, l in enumerate(lines):
            if "PARTS LIST" in _clean_txt(l).upper():
                start = i + 1
                break

        tokens = []
        for raw in lines[start:]:
            t = _clean_txt(raw)
            if not t:
                continue
            up = t.upper()
            if up in {"DESCRIPTION", "PART NUMBER", "PART", "NUMBER", "QTY", "ITEM"}:
                continue
            if up.startswith("THIS DOCUMENT BELONGS"):
                break
            if up in {"SG CONTROLS", "DRAWN", "DATE"}:
                continue
            tokens.append(t)

        cleaned = []
        for idx, tok in enumerate(tokens):
            up = tok.upper()
            if up in {"RH", "LH"}:
                prev_tok = tokens[idx - 1] if idx > 0 else ""
                next_tok = tokens[idx + 1] if idx + 1 < len(tokens) else ""
                if _is_part_num_line(prev_tok) and _is_num_line(next_tok):
                    continue
            cleaned.append(tok)
        tokens = cleaned

        i = 0
        while i + 3 < len(tokens):
            d, pn, qty, item = tokens[i], tokens[i + 1], tokens[i + 2], tokens[i + 3]
            # Layout A: DESCRIPTION, PART NUMBER, QTY, ITEM
            if _looks_like_desc(d) and _is_part_num_line(pn) and _is_num_line(qty) and _is_num_line(item):
                rows.append(
                    {
                        "Manual": manual_name,
                        "Page": int(page_no),
                        "Item": item,
                        "Part": d,
                        "Part Number": pn.rstrip("."),
                        "Qty/Asm": qty,
                    }
                )
                i += 4
                continue
            # Layout B: ITEM, QTY, PART NUMBER, DESCRIPTION
            item2, qty2, pn2, d2 = tokens[i], tokens[i + 1], tokens[i + 2], tokens[i + 3]
            if _is_num_line(item2) and _is_num_line(qty2) and _is_part_num_line(pn2) and _looks_like_desc(d2):
                rows.append(
                    {
                        "Manual": manual_name,
                        "Page": int(page_no),
                        "Item": item2,
                        "Part": d2,
                        "Part Number": pn2.rstrip("."),
                        "Qty/Asm": qty2,
                    }
                )
                i += 4
                continue
            if i + 4 < len(tokens):
                d2 = f"{d} {pn}"
                pn2, qty2, item2 = tokens[i + 2], tokens[i + 3], tokens[i + 4]
                if _looks_like_desc(d2) and _is_part_num_line(pn2) and _is_num_line(qty2) and _is_num_line(item2):
                    rows.append(
                        {
                            "Manual": manual_name,
                            "Page": int(page_no),
                            "Item": item2,
                            "Part": _clean_txt(d2),
                            "Part Number": pn2.rstrip("."),
                            "Qty/Asm": qty2,
                        }
                    )
                    i += 5
                    continue
            i += 1
        return rows

    @st.cache_data(show_spinner=False)
    def _build_manual_bom_index_for_maintenance(manuals_dir: str, signature: tuple):
        import glob
        import fitz
        import re
        key_pat = re.compile(r"PARTS?\s+LIST|BILL OF MATERIALS|BOM|PART NUMBER|ITEM", re.IGNORECASE)
        rows = []
        for pdf in sorted(glob.glob(os.path.join(manuals_dir, "*.pdf"))):
            mname = os.path.basename(pdf)
            try:
                doc = fitz.open(pdf)
            except Exception:
                continue
            for pidx in range(len(doc)):
                txt = doc.load_page(pidx).get_text("text") or ""
                if not key_pat.search(txt):
                    continue
                lines = [x for x in txt.splitlines() if _clean_txt(x)]
                rows.extend(_extract_parts_rows_from_lines(lines, mname, pidx + 1))
            doc.close()
        if not rows:
            return pd.DataFrame(columns=["Manual", "Page", "Item", "Part", "Part Number", "Qty/Asm"])
        out = pd.DataFrame(rows)
        out = out.drop_duplicates(subset=["Manual", "Page", "Item", "Part Number", "Part"]).reset_index(drop=True)
        return out

    @st.cache_data(show_spinner=False)
    def _manual_pdf_signature(manuals_dir: str):
        sig = []
        try:
            for fn in sorted(os.listdir(manuals_dir)):
                if fn.lower().endswith(".pdf"):
                    fp = os.path.join(manuals_dir, fn)
                    sig.append((fn, os.path.getmtime(fp)))
        except Exception:
            return tuple()
        return tuple(sig)

    @st.cache_data(show_spinner=False)
    def _manual_pdf_files(manuals_dir: str, signature: tuple):
        return [fn for fn, _ in signature]

    @st.cache_data(show_spinner=False)
    def _render_manual_page_png_for_maintenance(path: str, page_no: int, zoom: float = 1.5):
        import fitz
        doc = fitz.open(path)
        pidx = max(0, min(int(page_no) - 1, len(doc) - 1))
        page = doc.load_page(pidx)
        pix = page.get_pixmap(matrix=fitz.Matrix(float(zoom), float(zoom)), alpha=False)
        doc.close()
        return pix.tobytes("png")

    def _resolve_task_manual_and_pages(task_row, fallback_df=None) -> tuple:
        """Return (manual_name_or_document, page_text) with fallback from related task rows."""
        manual_raw = safe_str(task_row.get("Manual_Name", "")).strip() or safe_str(task_row.get("Document", "")).strip()
        page_raw = safe_str(task_row.get("Page", "")).strip()
        if manual_raw and page_raw:
            return manual_raw, page_raw
        if fallback_df is None or getattr(fallback_df, "empty", True):
            return manual_raw, page_raw

        task_id = safe_str(task_row.get("Task_ID", "")).strip().lower()
        comp = safe_str(task_row.get("Component", "")).strip().lower()
        task = safe_str(task_row.get("Task", "")).strip().lower()
        cand = fallback_df.copy()
        for c in ["Task_ID", "Component", "Task", "Manual_Name", "Document", "Page"]:
            if c not in cand.columns:
                cand[c] = ""

        hit = cand.iloc[0:0].copy()
        if task_id:
            hit = cand[cand["Task_ID"].astype(str).str.strip().str.lower().eq(task_id)].copy()
        if hit.empty and (comp or task):
            hit = cand[
                cand["Component"].astype(str).str.strip().str.lower().eq(comp)
                & cand["Task"].astype(str).str.strip().str.lower().eq(task)
            ].copy()
        if hit.empty:
            return manual_raw, page_raw

        hit["__manual"] = (
            hit["Manual_Name"].astype(str).str.strip().where(
                hit["Manual_Name"].astype(str).str.strip().ne(""),
                hit["Document"].astype(str).str.strip(),
            )
        )
        hit["__page"] = hit["Page"].astype(str).str.strip()
        hit = hit[hit["__manual"].astype(str).str.strip().ne("")].copy()
        if hit.empty:
            return manual_raw, page_raw
        if not page_raw:
            hp = hit[hit["__page"].astype(str).str.strip().ne("")].copy()
            if not hp.empty:
                page_raw = safe_str(hp.iloc[0].get("__page", "")).strip()
        if not manual_raw:
            manual_raw = safe_str(hit.iloc[0].get("__manual", "")).strip()
        return manual_raw, page_raw

    def _resolve_task_manual_file(task_row, fallback_df=None) -> str:
        import re

        manuals_dir = os.path.join(P.root_dir, "manuals")
        if not os.path.isdir(manuals_dir):
            return ""

        def _norm_name(v: str) -> str:
            return re.sub(r"[^a-z0-9]+", " ", safe_str(v).lower()).strip()

        def _resolve_candidate_name(name_raw: str, files: list[str]) -> str:
            raw = os.path.basename(safe_str(name_raw).strip())
            if not raw:
                return ""
            if os.path.exists(os.path.join(manuals_dir, raw)):
                return raw
            raw_n = _norm_name(os.path.splitext(raw)[0])
            if not raw_n:
                return ""
            raw_tokens = {t for t in raw_n.split() if t}
            best = ("", 0)
            for fn in files:
                fn_n = _norm_name(os.path.splitext(fn)[0])
                fn_tokens = {t for t in fn_n.split() if t}
                if not fn_n:
                    continue
                # Strong normalized contains.
                if raw_n in fn_n or fn_n in raw_n:
                    score = 100 + min(len(raw_tokens), len(fn_tokens))
                else:
                    # Token overlap fallback.
                    inter = len(raw_tokens & fn_tokens)
                    score = inter
                if score > best[1]:
                    best = (fn, score)
            # Require at least a minimal overlap to avoid wrong manual.
            return best[0] if best[1] >= 2 else ""

        signature = _manual_pdf_signature(manuals_dir)
        manual_files = _manual_pdf_files(manuals_dir, signature)
        if not manual_files:
            return ""

        task_manual, _ = _resolve_task_manual_and_pages(task_row, fallback_df=fallback_df)
        candidates = []
        if task_manual:
            candidates.append(task_manual)

        # Add related-row aliases (Manual_Name and Document) for robust mapping.
        if fallback_df is not None and not getattr(fallback_df, "empty", True):
            cand = fallback_df.copy()
            for c in ["Task_ID", "Component", "Task", "Manual_Name", "Document"]:
                if c not in cand.columns:
                    cand[c] = ""
            task_id = safe_str(task_row.get("Task_ID", "")).strip().lower()
            comp = safe_str(task_row.get("Component", "")).strip().lower()
            task = safe_str(task_row.get("Task", "")).strip().lower()
            hit = cand.iloc[0:0].copy()
            if task_id:
                hit = cand[cand["Task_ID"].astype(str).str.strip().str.lower().eq(task_id)].copy()
            if hit.empty and (comp or task):
                hit = cand[
                    cand["Component"].astype(str).str.strip().str.lower().eq(comp)
                    & cand["Task"].astype(str).str.strip().str.lower().eq(task)
                ].copy()
            if not hit.empty:
                for _, hr in hit.iterrows():
                    mv = safe_str(hr.get("Manual_Name", "")).strip()
                    dv = safe_str(hr.get("Document", "")).strip()
                    if mv:
                        candidates.append(mv)
                    if dv:
                        candidates.append(dv)

        # Deduplicate and resolve first valid match.
        seen = set()
        for name in candidates:
            lk = _norm_name(name)
            if not lk or lk in seen:
                continue
            seen.add(lk)
            resolved = _resolve_candidate_name(name, manual_files)
            if resolved:
                return resolved

        # As a final heuristic, if the task/component text strongly matches one manual, use it.
        task_text = _norm_name(f"{safe_str(task_row.get('Component',''))} {safe_str(task_row.get('Task',''))}")
        task_tokens = {t for t in task_text.split() if len(t) >= 3}
        if task_tokens:
            best = ("", 0)
            for fn in manual_files:
                fn_tokens = {t for t in _norm_name(os.path.splitext(fn)[0]).split() if len(t) >= 3}
                score = len(task_tokens & fn_tokens)
                if score > best[1]:
                    best = (fn, score)
            if best[1] >= 2:
                return best[0]

        if len(manual_files) == 1:
            return manual_files[0]
        return ""

    def _parse_task_pages(page_raw: str) -> list:
        import re
        vals = []
        for tok in re.findall(r"\d+", safe_str(page_raw)):
            try:
                v = int(tok)
                if v > 0 and v not in vals:
                    vals.append(v)
            except Exception:
                pass
        return vals or [1]

    def _norm_part_text(v: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", " ", safe_str(v).lower()).strip()

    def _is_required_part_match(required_part: str, bom_part: str, bom_pn: str) -> bool:
        rp = _norm_part_text(required_part)
        bp = _norm_part_text(bom_part)
        pn = safe_str(bom_pn).lower().strip()
        if not rp:
            return False
        # Exact / strong contains first.
        if rp == bp:
            return True
        if len(rp) >= 4 and rp in bp:
            return True
        if len(bp) >= 4 and bp in rp:
            return True
        if pn and rp == pn:
            return True
        # Token overlap fallback (strict enough to avoid broad noise).
        rt = {t for t in rp.split() if len(t) >= 3}
        bt = {t for t in bp.split() if len(t) >= 3}
        if not rt or not bt:
            return False
        inter = rt & bt
        return len(inter) >= max(1, min(len(rt), len(bt)) // 2)

    @st.cache_data(show_spinner=False)
    def _build_manual_context_cached(manuals_dir: str, signature: tuple, task_manual_file: str, req_parts_tuple: tuple) -> pd.DataFrame:
        bom_df = _build_manual_bom_index_for_maintenance(manuals_dir, signature)
        if bom_df is None or bom_df.empty:
            return pd.DataFrame(columns=["Manual", "Page", "Item", "Part", "Part Number", "Qty/Asm", "Required Part"])
        work = bom_df.copy()
        if task_manual_file:
            work = work[work["Manual"].astype(str).str.lower().eq(task_manual_file.lower())].copy()
        req_clean = []
        seen = set()
        for p in req_parts_tuple or ():
            pv = safe_str(p).strip()
            if not pv:
                continue
            lk = pv.lower()
            if lk in seen:
                continue
            req_clean.append(pv)
            seen.add(lk)
        if not req_clean:
            return pd.DataFrame(columns=["Manual", "Page", "Item", "Part", "Part Number", "Qty/Asm", "Required Part"])

        rows = []
        for _, r in work.iterrows():
            part_txt = safe_str(r.get("Part", ""))
            pn_txt = safe_str(r.get("Part Number", ""))
            matched_req = []
            for req in req_clean:
                if _is_required_part_match(req, part_txt, pn_txt):
                    matched_req.append(req)
            if matched_req:
                x = r.copy()
                x["Required Part"] = ", ".join(matched_req)
                rows.append(x)
        if not rows:
            return pd.DataFrame(columns=["Manual", "Page", "Item", "Part", "Part Number", "Qty/Asm", "Required Part"])

        out = pd.DataFrame(rows)
        out = out.drop_duplicates(subset=["Manual", "Page", "Item", "Part Number", "Part"]).reset_index(drop=True)
        keep = ["Manual", "Page", "Item", "Part", "Part Number", "Qty/Asm", "Required Part"]
        out = out[keep].sort_values(["Page", "Item", "Part Number"], ascending=[True, True, True]).reset_index(drop=True)
        return out.head(120)

    def _build_manual_context_for_task(task_row, req_parts: list[str], fallback_df=None) -> pd.DataFrame:
        manuals_dir = os.path.join(P.root_dir, "manuals")
        if not os.path.isdir(manuals_dir):
            return pd.DataFrame()
        signature = _manual_pdf_signature(manuals_dir)
        task_manual_file = _resolve_task_manual_file(task_row, fallback_df=fallback_df)
        req_parts_tuple = tuple(req_parts or [])
        return _build_manual_context_cached(manuals_dir, signature, task_manual_file, req_parts_tuple)

    def _maintenance_active_order_mask(
        orders_df: pd.DataFrame,
        *,
        part_name: str,
        maintenance_task_id: str = "",
        wait_id: str = "",
    ) -> pd.Series:
        active_status = {"opened", "wait for approval", "approved", "ordered", "received"}
        if orders_df is None or orders_df.empty:
            return pd.Series(dtype=bool)
        for col in ["Part Name", "Status", "Maintenance Task ID", "Wait ID"]:
            if col not in orders_df.columns:
                orders_df[col] = ""
        base = (
            orders_df["Part Name"].astype(str).str.strip().str.lower().eq(safe_str(part_name).strip().lower())
            & orders_df["Status"].astype(str).str.strip().str.lower().isin(active_status)
        )
        wait_id_s = safe_str(wait_id).strip()
        task_id_s = safe_str(maintenance_task_id).strip()
        if wait_id_s:
            wait_mask = orders_df["Wait ID"].astype(str).str.strip().eq(wait_id_s)
            if (base & wait_mask).any():
                return base & wait_mask
        if task_id_s:
            task_mask = orders_df["Maintenance Task ID"].astype(str).str.strip().eq(task_id_s)
            if (base & task_mask).any():
                return base & task_mask
            # Maintenance-linked requests should not be blocked by unrelated tasks that need the same part name.
            return base & task_mask
        return base

    def _maintenance_received_ready_mask(
        orders_df: pd.DataFrame,
        *,
        part_name: str,
        maintenance_task_id: str = "",
        wait_id: str = "",
    ) -> pd.Series:
        if orders_df is None or orders_df.empty:
            return pd.Series(dtype=bool)
        for col in ["Inventory Synced"]:
            if col not in orders_df.columns:
                orders_df[col] = ""
        linked_mask = _maintenance_active_order_mask(
            orders_df,
            part_name=part_name,
            maintenance_task_id=maintenance_task_id,
            wait_id=wait_id,
        )
        if linked_mask.any():
            return linked_mask & orders_df["Status"].astype(str).str.strip().str.lower().eq("received") & orders_df["Inventory Synced"].astype(str).str.strip().str.lower().eq("yes")
        # Fallback for older rows that predate maintenance linkage.
        return (
            orders_df["Part Name"].astype(str).str.strip().str.lower().eq(safe_str(part_name).strip().lower())
            & orders_df["Status"].astype(str).str.strip().str.lower().eq("received")
            & orders_df["Inventory Synced"].astype(str).str.strip().str.lower().eq("yes")
        )

    def _maintenance_linked_ready_count(
        orders_df: pd.DataFrame,
        *,
        part_name: str,
        maintenance_task_id: str = "",
        wait_id: str = "",
    ) -> int:
        return int(
            _maintenance_received_ready_mask(
                orders_df,
                part_name=part_name,
                maintenance_task_id=maintenance_task_id,
                wait_id=wait_id,
            ).sum()
        )

    def _parse_part_qty_plan(raw_text: str) -> dict[str, int]:
        plan: dict[str, int] = {}
        raw = safe_str(raw_text).strip()
        if not raw:
            return plan
        chunks = []
        for piece in raw.replace("\n", ",").split(","):
            pv = safe_str(piece).strip()
            if pv:
                chunks.append(pv)
        for piece in chunks:
            name = piece
            qty = 1
            for sep in ["=", " x", " X", "*"]:
                if sep in piece:
                    left, right = piece.rsplit(sep, 1)
                    try:
                        qv = int(float(safe_str(right).strip()))
                    except Exception:
                        qv = None
                    if qv and qv > 0:
                        name = safe_str(left).strip()
                        qty = qv
                        break
            if not name:
                continue
            plan[name] = int(plan.get(name, 0)) + int(qty)
        return plan

    def _load_wait_part_plan(wait_row) -> dict[str, int]:
        raw_json = safe_str(wait_row.get("requested_part_plan_json", "")).strip()
        if raw_json:
            try:
                parsed = json.loads(raw_json)
                if isinstance(parsed, dict):
                    plan = {}
                    for k, v in parsed.items():
                        name = safe_str(k).strip()
                        try:
                            qty = int(float(v))
                        except Exception:
                            qty = 0
                        if name and qty > 0:
                            plan[name] = qty
                    if plan:
                        return plan
            except Exception:
                pass
        fallback = {}
        for name, qty in _parse_part_qty_plan(safe_str(wait_row.get("requested_part_name", ""))).items():
            fallback[name] = int(fallback.get(name, 0)) + int(qty)
        return fallback

    def _split_required_parts(parts_raw: str) -> list[str]:
        s = safe_str(parts_raw).strip()
        if not s:
            return []
        out = []
        seen = set()
        for p in s.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
            pv = safe_str(p).strip()
            if not pv:
                continue
            lk = pv.lower()
            if lk not in seen:
                out.append(pv)
                seen.add(lk)
        return out

    def _legacy_required_parts_are_conditional(row) -> bool:
        task_text = " ".join(
            [
                safe_str(row.get("Task", "")),
                safe_str(row.get("Task Name", "")),
                safe_str(row.get("Procedure_Summary", "")),
                safe_str(row.get("Safety/Notes", "")),
                safe_str(row.get("Notes", "")),
            ]
        ).strip().lower()
        if not task_text:
            return False
        conditional_markers = [
            "if needed",
            "replace if needed",
            "if worn",
            "if wear",
            "if damaged",
            "if damage",
            "if inspection requires",
            "if required",
            "if condition met",
            "on-condition",
            "replace when",
            "replace if",
            "inspect and replace if needed",
            "inspect for",
        ]
        return any(marker in task_text for marker in conditional_markers)

    def _task_mandatory_parts(row) -> list[str]:
        mandatory_raw = safe_str(row.get("Mandatory_Parts", "")).strip()
        conditional_raw = safe_str(row.get("Conditional_Parts", "")).strip()
        mandatory = _split_required_parts(mandatory_raw)
        conditional = _split_required_parts(conditional_raw)
        if mandatory:
            return mandatory
        if conditional:
            return []
        legacy_required = _split_required_parts(row.get("Required_Parts", ""))
        if not legacy_required:
            return []
        if _legacy_required_parts_are_conditional(row):
            return []
        return legacy_required

    def _task_conditional_parts(row) -> list[str]:
        conditional_raw = safe_str(row.get("Conditional_Parts", "")).strip()
        conditional = _split_required_parts(conditional_raw)
        if conditional:
            return conditional
        mandatory_raw = safe_str(row.get("Mandatory_Parts", "")).strip()
        if mandatory_raw:
            return []
        legacy_required = _split_required_parts(row.get("Required_Parts", ""))
        if legacy_required and _legacy_required_parts_are_conditional(row):
            return legacy_required
        return []

    def _task_preparation_lead_days(row) -> int:
        try:
            val = int(float(pd.to_numeric(row.get("Preparation_Lead_Days", np.nan), errors="coerce")))
            return max(0, val)
        except Exception:
            return 7

    def _task_parts_check_lead_days(row) -> int:
        try:
            val = int(float(pd.to_numeric(row.get("Parts_Check_Lead_Days", np.nan), errors="coerce")))
            return max(0, val)
        except Exception:
            return 21

    def _task_auto_order_mandatory(row) -> bool:
        raw = safe_str(row.get("Auto_Order_Mandatory_Parts", "")).strip().lower()
        if raw in {"", "yes", "true", "1", "auto", "y"}:
            return True
        if raw in {"no", "false", "0", "n"}:
            return False
        return True

    def _load_inventory_effective_qty_map() -> dict[str, float]:
        try:
            inv_df = load_inventory_cached(P.parts_inventory_csv)
        except Exception:
            inv_df = pd.DataFrame()
        if inv_df.empty:
            return {}
        inv_df["Part Name"] = inv_df["Part Name"].astype(str).str.strip().str.lower()
        inv_df["Item Type"] = inv_df.get("Item Type", "").astype(str).str.strip().str.lower()
        inv_df["Location"] = inv_df.get("Location", "").astype(str).str.strip().str.lower()
        inv_df["Quantity"] = pd.to_numeric(inv_df.get("Quantity", 0), errors="coerce").fillna(0.0)
        stock_df = inv_df[inv_df["Location"].ne("mounted")].copy()
        mounted_df = inv_df[inv_df["Location"].eq("mounted")].copy()
        inv_qty = stock_df.groupby("Part Name")["Quantity"].sum().to_dict()
        inv_mounted_qty = mounted_df.groupby("Part Name")["Quantity"].sum().to_dict()
        inv_tool_map = (
            inv_df.groupby("Part Name")
            .apply(
                lambda g: bool(
                    g["Item Type"].astype(str).str.strip().str.lower().eq("tool").any()
                    or is_tool_like_part_name(g.name)
                )
            )
            .to_dict()
        )
        eff = {}
        for pn in set(inv_qty.keys()) | set(inv_mounted_qty.keys()) | set(inv_tool_map.keys()):
            stock_q = float(inv_qty.get(pn, 0.0))
            mounted_q = float(inv_mounted_qty.get(pn, 0.0))
            eff[pn] = stock_q + mounted_q if bool(inv_tool_map.get(pn, False)) else stock_q
        return eff

    def _load_inventory_lead_time_map() -> dict[str, float]:
        try:
            inv_df = load_inventory_cached(P.parts_inventory_csv)
        except Exception:
            inv_df = pd.DataFrame()
        if inv_df.empty:
            return {}
        inv_df["Part Name"] = inv_df["Part Name"].astype(str).str.strip().str.lower()
        if "Lead Time Days" not in inv_df.columns:
            inv_df["Lead Time Days"] = 0.0
        inv_df["Lead Time Days"] = pd.to_numeric(inv_df["Lead Time Days"], errors="coerce").fillna(0.0)
        lead_map = inv_df.groupby("Part Name")["Lead Time Days"].max().to_dict()
        return {str(k).strip().lower(): float(v) for k, v in lead_map.items()}

    def _build_maintenance_parts_watch_df(
        df_rows: pd.DataFrame,
        *,
        current_date,
        current_draw_count,
    ) -> pd.DataFrame:
        if df_rows is None or df_rows.empty:
            return pd.DataFrame()
        inv_effective_qty = _load_inventory_effective_qty_map()
        lead_time_map = _load_inventory_lead_time_map()
        if os.path.exists(P.parts_orders_csv):
            try:
                odf = _read_csv_keepna(P.parts_orders_csv)
            except Exception:
                odf = pd.DataFrame()
        else:
            odf = pd.DataFrame()
        out_rows = []
        today_ts = pd.Timestamp(current_date)
        for _, rr in df_rows.iterrows():
            req_parts = _task_mandatory_parts(rr)
            if not req_parts:
                continue
            mode = mode_norm(rr.get("Tracking_Mode_norm", rr.get("Tracking_Mode", "")))
            parts_check_days = _task_parts_check_lead_days(rr)
            missing_parts = []
            unordered_parts = []
            late_parts = []
            conditional_missing = []
            task_id = safe_str(rr.get("Task_ID", "")).strip()
            component = safe_str(rr.get("Component", "")).strip()
            task_name = safe_str(rr.get("Task", "")).strip()
            days_left = None
            inside_parts_window = safe_str(rr.get("Status", "")).strip().upper() in {"OVERDUE", "DUE SOON"}
            if mode == "calendar":
                nd = pd.to_datetime(rr.get("Next_Due_Date", None), errors="coerce")
                if pd.notna(nd):
                    days_left = float((nd.normalize() - today_ts.normalize()).days)
                    inside_parts_window = bool(days_left <= float(parts_check_days))
            elif mode == "hours":
                nh = pd.to_numeric(rr.get("Next_Due_Hours", None), errors="coerce")
                cur_h = pd.to_numeric(pick_current_hours(rr.get("Hours_Source", "")), errors="coerce")
                if pd.notna(nh) and pd.notna(cur_h):
                    hours_left = float(nh) - float(cur_h)
                    inside_parts_window = bool(hours_left <= float(max(1, parts_check_days * 24)))
            elif mode == "draws":
                nd = pd.to_numeric(rr.get("Next_Due_Draw", None), errors="coerce")
                if pd.notna(nd):
                    draws_left = float(nd) - float(current_draw_count)
                    inside_parts_window = bool(draws_left <= float(max(1, parts_check_days)))

            if not inside_parts_window:
                continue
            for part_name in req_parts:
                if float(inv_effective_qty.get(part_name.lower(), 0.0)) > 0:
                    continue
                missing_parts.append(part_name)
                lead_days = float(lead_time_map.get(part_name.lower(), 0.0))
                has_active = _maintenance_active_order_mask(
                    odf,
                    part_name=part_name,
                    maintenance_task_id=task_id,
                    wait_id="",
                ).any()
                if not has_active:
                    unordered_parts.append(part_name)
                    if lead_days > 0:
                        if days_left is None or lead_days >= max(0.0, float(days_left)):
                            late_parts.append(part_name)
            for part_name in _task_conditional_parts(rr):
                if float(inv_effective_qty.get(part_name.lower(), 0.0)) <= 0:
                    conditional_missing.append(part_name)
            if not missing_parts:
                if not conditional_missing:
                    continue
                risk_label = "Conditional part not in stock"
            elif late_parts:
                risk_label = "Late mandatory order"
            elif unordered_parts:
                risk_label = "Mandatory order should already be open"
            else:
                risk_label = "Mandatory part waiting on open order"
            out_rows.append(
                {
                    "Status": safe_str(rr.get("Status", "")),
                    "Component": component,
                    "Task": task_name,
                    "Task_ID": task_id,
                    "Task_Group": safe_str(rr.get("Task_Group", "")),
                    "Required_Parts": ", ".join(req_parts),
                    "Conditional_Parts": ", ".join(_task_conditional_parts(rr)),
                    "Missing Parts": ", ".join(missing_parts),
                    "Conditional Missing": ", ".join(conditional_missing),
                    "Needs Order": ", ".join(unordered_parts),
                    "Late Order Risk": ", ".join(late_parts),
                    "Has Active Orders": "Yes" if len(unordered_parts) < len(missing_parts) else "No",
                    "Parts Risk": risk_label,
                    "Problem Now": "Yes" if bool(late_parts) else "No",
                    "Auto Order": "Yes" if _task_auto_order_mandatory(rr) else "No",
                    "Source_File": safe_str(rr.get("Source_File", "")),
                }
            )
        return pd.DataFrame(out_rows)

    def _create_or_open_parts_order_for_context(
        *,
        part_name: str,
        details: str,
        actor_name: str,
        task_row,
    ) -> str:
        base_cols = [
            "Status", "Part Name", "Serial Number",
            "Project Name", "Details",
            "Opened By",
            "Approval Requested From",
            "Approved", "Approved By", "Approval Date",
            "Received Date", "Received State",
            "Ordered By", "Date Ordered", "Company",
            "Inventory Synced",
            "Maintenance Component", "Maintenance Task", "Maintenance Task ID", "Wait ID",
        ]
        os.makedirs(os.path.dirname(PARTS_ORDERS_CSV), exist_ok=True)
        if os.path.exists(PARTS_ORDERS_CSV):
            try:
                orders_df = _read_csv_keepna(PARTS_ORDERS_CSV)
            except Exception:
                orders_df = pd.DataFrame(columns=base_cols)
        else:
            orders_df = pd.DataFrame(columns=base_cols)
        for c in base_cols:
            if c not in orders_df.columns:
                orders_df[c] = ""

        exists_active = _maintenance_active_order_mask(
            orders_df,
            part_name=part_name,
            maintenance_task_id=safe_str(task_row.get("Task_ID", "")).strip(),
            wait_id="",
        ).any()
        if exists_active:
            return "exists"

        row = {
            "Status": "Opened",
            "Part Name": safe_str(part_name).strip(),
            "Serial Number": "",
            "Project Name": "Maintenance",
            "Details": safe_str(details).strip(),
            "Opened By": safe_str(actor_name).strip(),
            "Approval Requested From": "",
            "Approved": "No",
            "Approved By": "",
            "Approval Date": "",
            "Received Date": "",
            "Received State": "",
            "Ordered By": "",
            "Date Ordered": "",
            "Company": "SG",
            "Inventory Synced": "",
            "Maintenance Component": safe_str(task_row.get("Component", "")).strip(),
            "Maintenance Task": safe_str(task_row.get("Task", "")).strip(),
            "Maintenance Task ID": safe_str(task_row.get("Task_ID", "")).strip(),
            "Wait ID": "",
        }
        orders_df = pd.concat([orders_df[base_cols], pd.DataFrame([row])[base_cols]], ignore_index=True)
        orders_df.to_csv(PARTS_ORDERS_CSV, index=False)
        return "created"

    def _render_task_manual_context(task_row, req_parts: list[str], *, key_prefix: str, actor_name: str, fallback_df=None, forced_pages=None):
        st.markdown("#### 📚 Manual Context")
        st.caption("Separated view: task procedure pages first, then strictly relevant BOM part pages.")

        manuals_dir = os.path.join(P.root_dir, "manuals")
        task_manual_raw, task_page_raw = _resolve_task_manual_and_pages(task_row, fallback_df=fallback_df)
        task_manual_file = _resolve_task_manual_file(task_row, fallback_df=fallback_df)
        page_vals = _parse_task_pages(task_page_raw)
        force_pages_vals = []
        for p in (forced_pages or []):
            try:
                iv = int(p)
                if iv > 0 and iv not in force_pages_vals:
                    force_pages_vals.append(iv)
            except Exception:
                pass
        merged_pages = list(page_vals)
        for p in force_pages_vals:
            if p not in merged_pages:
                merged_pages.append(p)
        merged_pages = sorted([int(x) for x in merged_pages if int(x) > 0]) if merged_pages else [1]

        st.markdown("##### 🧭 Task Procedure Pages")
        if task_manual_file and os.path.isdir(manuals_dir):
            sel_idx = 0
            task_page = st.selectbox(
                "Task-described page",
                options=merged_pages,
                index=sel_idx,
                key=f"{key_prefix}_task_page_pick",
            )
            st.caption(f"Task manual: `{task_manual_file}`")
            if force_pages_vals:
                st.caption("Pinned manual pages: " + ", ".join([str(x) for x in sorted(force_pages_vals)]))
            try:
                png0 = _render_manual_page_png_for_maintenance(os.path.join(manuals_dir, task_manual_file), int(task_page), 1.35)
                st.image(png0, caption=f"{task_manual_file} — page {int(task_page)}", use_container_width=True)
            except Exception as e:
                st.warning(f"Task manual preview failed: {e}")
        else:
            if safe_str(task_manual_raw).strip():
                st.caption(f"Task manual reference: `{safe_str(task_manual_raw).strip()}` (preview file not resolved).")
            else:
                st.caption("Task manual file not resolved from `Manual_Name/Document`.")

        st.markdown("##### 🧩 Relevant BOM Parts Pages")
        ctx_df = _build_manual_context_for_task(task_row, req_parts, fallback_df=fallback_df)
        if force_pages_vals and not ctx_df.empty:
            filtered = ctx_df[ctx_df["Page"].astype(int).isin(force_pages_vals)].copy()
            if not filtered.empty:
                ctx_df = filtered
        if ctx_df.empty:
            if force_pages_vals and task_manual_file and os.path.isdir(manuals_dir):
                st.caption("No strict BOM matches; showing pinned manual pages.")
                bom_page_pick = st.selectbox(
                    "Pinned manual page",
                    options=sorted(force_pages_vals),
                    index=0,
                    key=f"{key_prefix}_bom_page_pick_pinned",
                )
                try:
                    png = _render_manual_page_png_for_maintenance(os.path.join(manuals_dir, task_manual_file), int(bom_page_pick), 1.45)
                    st.image(png, caption=f"{task_manual_file} — page {int(bom_page_pick)}", use_container_width=True)
                except Exception as e:
                    st.warning(f"BOM page preview failed: {e}")
                return
            st.caption("No strict BOM part matches for this task Required_Parts.")
            return

        bom_pages = sorted(ctx_df["Page"].astype(int).unique().tolist())
        bom_page_pick = st.selectbox(
            "Relevant BOM page",
            options=bom_pages,
            index=0,
            key=f"{key_prefix}_bom_page_pick",
        )
        page_df = ctx_df[ctx_df["Page"].astype(int).eq(int(bom_page_pick))].copy()
        st.dataframe(
            page_df[["Manual", "Page", "Part", "Part Number", "Qty/Asm", "Required Part"]],
            use_container_width=True,
            height=220,
            hide_index=True,
        )

        # Preview selected BOM page.
        mfile = safe_str(page_df.iloc[0].get("Manual", "")).strip() if not page_df.empty else ""
        if mfile and os.path.exists(os.path.join(manuals_dir, mfile)):
            try:
                png = _render_manual_page_png_for_maintenance(os.path.join(manuals_dir, mfile), int(bom_page_pick), 1.45)
                st.image(png, caption=f"{mfile} — BOM page {int(bom_page_pick)}", use_container_width=True)
            except Exception as e:
                st.warning(f"BOM page preview failed: {e}")

        labels = []
        row_map = {}
        for i, rr in page_df.iterrows():
            lb = f"{rr.get('Part','')} | PN:{rr.get('Part Number','')}"
            labels.append(lb)
            row_map[lb] = int(i)
        pick = st.selectbox("Pick BOM part row for action", options=[""] + labels, key=f"{key_prefix}_manual_pick")
        if pick:
            rr = page_df.loc[row_map[pick]]
            if st.button("🧾 Create/Open Order For Selected Part", key=f"{key_prefix}_manual_order_btn", use_container_width=True):
                part_name = safe_str(rr.get("Part", "")).strip()
                if not part_name:
                    st.error("Selected manual row has no part name.")
                else:
                    details = (
                        f"From manual context: {safe_str(rr.get('Manual',''))} p.{int(bom_page_pick)} | "
                        f"{safe_str(task_row.get('Component',''))} — {safe_str(task_row.get('Task',''))} "
                        f"(Task ID:{safe_str(task_row.get('Task_ID',''))})"
                    )
                    state = _create_or_open_parts_order_for_context(
                        part_name=part_name,
                        details=details,
                        actor_name=actor_name,
                        task_row=task_row,
                    )
                    if state == "created":
                        st.success("Part order created.")
                    else:
                        st.info("Active order already exists for this part.")

    def infer_group_policy(row):
        """
        Infer cadence policy from task groups.
        Safe rule: apply only when exactly one cadence family is selected.
        """
        groups_l = {safe_str(g).strip().lower() for g in row_task_groups(row)}
        if not groups_l:
            return None

        # Calendar cadence groups.
        cal_hits = []
        if "daily" in groups_l:
            cal_hits.append(("calendar", 1, "days", "Daily"))
        if "weekly" in groups_l:
            cal_hits.append(("calendar", 1, "weeks", "Weekly"))
        if "monthly" in groups_l:
            cal_hits.append(("calendar", 1, "months", "Monthly"))
        if "3-month" in groups_l:
            cal_hits.append(("calendar", 3, "months", "3-Month"))
        if "6-month" in groups_l:
            cal_hits.append(("calendar", 6, "months", "6-Month"))

        draw_hit = None
        if ("draw-count" in groups_l) or ("per-draw/startup" in groups_l):
            draw_hit = ("draws", 1, "draws", "Draw-Count")

        hours_hit = None
        if "hours" in groups_l:
            # Conservative default only when no explicit interval exists.
            hours_hit = ("hours", None, "hours", "Hours")

        family_count = int(bool(cal_hits)) + int(draw_hit is not None) + int(hours_hit is not None)
        if family_count != 1:
            return None
        if cal_hits:
            # If more than one calendar cadence exists, skip to avoid overriding with wrong policy.
            if len(cal_hits) != 1:
                return None
            mode, val, unit, name = cal_hits[0]
            return {"tracking_mode": mode, "interval_value": val, "interval_unit": unit, "policy_name": name}
        if draw_hit is not None:
            mode, val, unit, name = draw_hit
            return {"tracking_mode": mode, "interval_value": val, "interval_unit": unit, "policy_name": name}
        if hours_hit is not None:
            mode, val, unit, name = hours_hit
            return {"tracking_mode": mode, "interval_value": val, "interval_unit": unit, "policy_name": name}
        return None
    
    # =========================================================
    # Paths
    # =========================================================
    BASE_DIR = P.root_dir
    MAINT_FOLDER = P.maintenance_dir
    DRAW_FOLDER = P.dataset_dir   # dataset CSVs (summary)
    LOGS_FOLDER = P.logs_dir      # ✅ LOG CSVs (MFC actual)
    STATE_PATH = os.path.join(MAINT_FOLDER, "_app_state.json")
    os.makedirs(MAINT_FOLDER, exist_ok=True)
    
    # ✅ Append-only CSV logs (for SQL Lab line-search)
    MAINT_ACTIONS_CSV = os.path.join(MAINT_FOLDER, "maintenance_actions_log.csv")
    MAINT_WAIT_PARTS_CSV = os.path.join(MAINT_FOLDER, "maintenance_wait_parts_log.csv")
    MAINT_TASK_STATE_CSV = os.path.join(MAINT_FOLDER, "maintenance_task_state.csv")
    MAINT_RESERVATIONS_CSV = os.path.join(MAINT_FOLDER, "maintenance_parts_reservations.csv")
    MAINT_CONDITIONS_LOG_CSV = os.path.join(MAINT_FOLDER, "maintenance_conditions_log.csv")
    MAINT_TEST_RECORDS_CSV = os.path.join(MAINT_FOLDER, "maintenance_test_records.csv")
    MAINT_TEST_PRESETS_JSON = os.path.join(MAINT_FOLDER, "maintenance_test_presets.json")
    FAULTS_CSV = os.path.join(MAINT_FOLDER, "faults_log.csv")
    FAULTS_ACTIONS_CSV = os.path.join(MAINT_FOLDER, "faults_actions_log.csv")
    PARTS_ORDERS_CSV = P.parts_orders_csv
    
    MAINT_ACTIONS_COLS = [
        "maintenance_id",
        "maintenance_ts",
        "maintenance_component",
        "maintenance_task",
        "maintenance_task_id",
        "maintenance_mode",
        "maintenance_hours_source",
        "maintenance_done_date",
        "maintenance_done_hours",
        "maintenance_done_draw",
        "maintenance_source_file",
        "maintenance_actor",
        "maintenance_note",
    ]
    MAINT_WAIT_PARTS_COLS = [
        "wait_id",
        "wait_ts",
        "maintenance_component",
        "maintenance_task",
        "maintenance_task_id",
        "maintenance_source_file",
        "requested_part_name",
        "requested_part_plan_json",
        "requested_project_name",
        "requested_company",
        "wait_reason",
        "actor",
        "resolved_ts",
        "resolution_note",
    ]
    
    FAULTS_COLS = [
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
    
    # ✅ Fault actions (close/reopen/notes) — append-only
    FAULTS_ACTIONS_COLS = [
        "fault_action_id",
        "fault_id",
        "action_ts",
        "action_type",     # close / reopen / note
        "actor",
        "note",
        "fix_summary",
    ]
    
    # =========================================================
    # DuckDB connection (shared with SQL Lab)
    # =========================================================
    con = st.session_state.get("sql_duck_con")
    if con is None:
        try:
            con = get_duckdb_conn(P.duckdb_path)
            st.session_state["sql_duck_con"] = con
        except Exception as e:
            msg = str(e)
            if "Could not set lock on file" in msg:
                st.warning(
                    "DuckDB is locked by another Tower process on this computer. "
                    "Close the other running app instance and retry this tab."
                )
                st.caption(f"DB path: `{P.duckdb_path}`")
                return
            raise
    try:
        con.execute("PRAGMA threads=4;")
    except Exception:
        pass
    
    # =========================================================
    # Create DB tables
    # =========================================================
    con.execute("""
    CREATE TABLE IF NOT EXISTS maintenance_tasks (
        task_key            VARCHAR,
        task_id             VARCHAR,
        component           VARCHAR,
        task                VARCHAR,
        tracking_mode       VARCHAR,
        hours_source        VARCHAR,
        interval_value      VARCHAR,
        interval_unit       VARCHAR,
        due_threshold_days  VARCHAR,
        manual_name         VARCHAR,
        page                VARCHAR,
        document            VARCHAR,
        procedure_summary   VARCHAR,
        notes               VARCHAR,
        owner               VARCHAR,
        source_file         VARCHAR,
        loaded_at           TIMESTAMP
    );
    """)
    
    con.execute("""
    CREATE TABLE IF NOT EXISTS maintenance_actions (
        action_id       BIGINT,
        action_ts       TIMESTAMP,
        component       VARCHAR,
        task            VARCHAR,
        task_id         VARCHAR,
        tracking_mode   VARCHAR,
        hours_source    VARCHAR,
        done_date       DATE,
        done_hours      DOUBLE,
        done_draw       INTEGER,
        source_file     VARCHAR,
        actor           VARCHAR,
        note            VARCHAR
    );
    """)
    
    con.execute("""
    CREATE TABLE IF NOT EXISTS faults_events (
        fault_id        BIGINT,
        fault_ts        TIMESTAMP,
        component       VARCHAR,
        title           VARCHAR,
        description     VARCHAR,
        severity        VARCHAR,
        actor           VARCHAR,
        source_file     VARCHAR,
        related_draw    VARCHAR
    );
    """)
    
    con.execute("""
    CREATE TABLE IF NOT EXISTS faults_actions (
        fault_action_id  BIGINT,
        fault_id         BIGINT,
        action_ts        TIMESTAMP,
        action_type      VARCHAR,
        actor            VARCHAR,
        note             VARCHAR,
        fix_summary      VARCHAR
    );
    """)
    
    # =========================================================
    # Persistent state helpers
    # =========================================================
    def load_state(path: str) -> dict:
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def save_state(path: str, state: dict) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    
        def _sanitize(o):
            if isinstance(o, (dt.date, dt.datetime)):
                return o.isoformat()
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            return o
    
        clean = {k: _sanitize(v) for k, v in state.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2)
    
    state = load_state(STATE_PATH)
    
    # =========================================================
    # CSV helpers (append-only)
    # =========================================================
    def _ensure_csv(path: str, cols: list):
        if not os.path.isfile(path):
            pd.DataFrame(columns=cols).to_csv(path, index=False)
    
    def _append_csv(path: str, cols: list, df_rows: pd.DataFrame):
        _ensure_csv(path, cols)
        df = df_rows.copy()
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        df = df[cols]
    
        # stringify time fields to avoid dtype crash
        for tcol in [c for c in cols if c.endswith("_ts")]:
            df[tcol] = pd.to_datetime(df[tcol], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        for dcol in [c for c in cols if c.endswith("_date")]:
            df[dcol] = pd.to_datetime(df[dcol], errors="coerce").dt.strftime("%Y-%m-%d")

        df.to_csv(path, mode="a", header=False, index=False)

    def _mtime(path: str) -> float:
        try:
            return float(os.path.getmtime(path))
        except Exception:
            return 0.0

    @st.cache_data(show_spinner=False)
    def _read_csv_safe_cached(path: str, mtime: float, cols_tuple: tuple) -> pd.DataFrame:
        cols = list(cols_tuple)
        if not os.path.isfile(path):
            return pd.DataFrame(columns=cols)
        try:
            df = pd.read_csv(path)
            if df is None:
                return pd.DataFrame(columns=cols)
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            return df[cols].copy()
        except Exception:
            return pd.DataFrame(columns=cols)

    def _read_csv_safe(path: str, cols: list) -> pd.DataFrame:
        return _read_csv_safe_cached(path, _mtime(path), tuple(cols))

    @st.cache_data(show_spinner=False)
    def _read_csv_keepna_cached(path: str, mtime: float) -> pd.DataFrame:
        if not os.path.isfile(path):
            return pd.DataFrame()
        try:
            return pd.read_csv(path, keep_default_na=False)
        except Exception:
            return pd.DataFrame()

    def _read_csv_keepna(path: str) -> pd.DataFrame:
        return _read_csv_keepna_cached(path, _mtime(path))
    
    def _latest_fault_state(actions_df: pd.DataFrame) -> dict:
        """
        fault_id -> last action (close/reopen/note) ; closed if last action is 'close'
        """
        out = {}
        if actions_df is None or actions_df.empty:
            return out
    
        a = actions_df.copy()
        a["action_ts"] = pd.to_datetime(a["action_ts"], errors="coerce")
        a["fault_id"] = pd.to_numeric(a["fault_id"], errors="coerce")
        a = a.dropna(subset=["fault_id"]).copy()
        a["fault_id"] = a["fault_id"].astype(int)
    
        a = a.sort_values(["fault_id", "action_ts"], ascending=[True, True])
        last = a.groupby("fault_id").tail(1)
    
        for _, r in last.iterrows():
            fid = int(r["fault_id"])
            typ = safe_str(r.get("action_type", "")).strip().lower()
            out[fid] = {
                "is_closed": (typ == "close"),
                "last_ts": r.get("action_ts", None),
                "last_note": safe_str(r.get("note", "")),
                "last_fix": safe_str(r.get("fix_summary", "")),
                "last_type": typ,
                "last_actor": safe_str(r.get("actor", "")),
            }
        return out
    
    def _write_fault_action(con, *, fault_id: int, action_type: str, actor: str, note: str = "", fix_summary: str = ""):
        now_dt = dt.datetime.now()
        aid = int(time.time() * 1000)
    
        # DuckDB
        try:
            con.execute("""
                INSERT INTO faults_actions
                (fault_action_id, fault_id, action_ts, action_type, actor, note, fix_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [aid, int(fault_id), now_dt, str(action_type), str(actor), str(note), str(fix_summary)])
        except Exception as e:
            st.warning(f"Fault action DB insert failed (still saving CSV): {e}")
    
        # CSV
        row = pd.DataFrame([{
            "fault_action_id": aid,
            "fault_id": int(fault_id),
            "action_ts": now_dt,
            "action_type": str(action_type),
            "actor": str(actor),
            "note": str(note),
            "fix_summary": str(fix_summary),
        }])
        _append_csv(FAULTS_ACTIONS_CSV, FAULTS_ACTIONS_COLS, row)
    
    # =========================================================
    # Draw count helper
    # =========================================================
    def get_draw_orders_count() -> int:
        return int(count_dataset_draws(P.dataset_dir))

    current_draw_count = get_draw_orders_count()
    
    # =========================================================
    # Maintenance file loading
    # =========================================================
    ignore_maint_source_files = {
        "faults_actions_log.csv",
        "faults_log.csv",
        "maintenance_actions_log.csv",
        "maintenance_task_state.csv",
        "maintenance_work_packages.csv",
        "_app_state.json",
        "maintenance_test_presets.json",
        "tm_step_checklists.json",
    }
    files = [
        f for f in os.listdir(MAINT_FOLDER)
        if f.lower().endswith((".xlsx", ".xls", ".csv")) and f not in ignore_maint_source_files
    ]
    if not files:
        st.warning("No maintenance files found in /maintenance folder.")
        st.stop()
    
    normalize_map = dict(NORMALIZE_MAP)
    inverse_map = {v: k for k, v in normalize_map.items()}
    
    REQUIRED = ["Component", "Task", "Tracking_Mode"]
    OPTIONAL = [
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
    
    @st.cache_data(show_spinner=False)
    def _read_file_cached(path: str, mtime: float) -> pd.DataFrame:
        if path.lower().endswith(".csv"):
            return pd.read_csv(path)
        return pd.read_excel(path)

    def read_file(path: str) -> pd.DataFrame:
        try:
            mtime = float(os.path.getmtime(path))
        except Exception:
            mtime = 0.0
        return _read_file_cached(path, mtime)
    
    def write_file(path: str, df: pd.DataFrame):
        if path.lower().endswith(".csv"):
            df.to_csv(path, index=False)
        else:
            df.to_excel(path, index=False)

    @st.cache_data(show_spinner=False)
    def _load_inventory_cached(path: str, mtime: float) -> pd.DataFrame:
        from helpers.parts_inventory import load_inventory

        return load_inventory(path)

    def load_inventory_cached(path: str) -> pd.DataFrame:
        return _load_inventory_cached(path, _mtime(path))

    def default_maintenance_test_presets() -> dict:
        return {
            "Furnace Heating Element Voltage Trend": {
                "fields": "Voltage (V); Current (A); Temperature (degC)",
                "thresholds": [
                    {"Field": "Voltage (V)", "Rule": ">", "Value": "2.0", "Trigger Label": "Voltage drift above expected baseline"},
                ],
                "condition": "If voltage trend increases above normal baseline, investigate element aging / replacement.",
                "action": "Set PREP_NEEDED and schedule replacement/inspection.",
            },
            "Pyrometer Alignment + Window Cleanliness": {
                "fields": "Window cleanliness score; Alignment note; Furnace temp stability note",
                "thresholds": [
                    {"Field": "Window cleanliness score", "Rule": "<", "Value": "7", "Trigger Label": "Pyrometer window needs cleaning"},
                ],
                "condition": "If pyrometer alignment drifts or the window is dirty, clean and re-check before running.",
                "action": "Set PREP_NEEDED and inspect pyrometer alignment/window.",
            },
            "Storage Vacuum Rise": {
                "fields": "Vacuum (bar); Pressure Rise (bar); Leak note",
                "thresholds": [
                    {"Field": "Pressure Rise (bar)", "Rule": ">", "Value": "0.03", "Trigger Label": "Vacuum rise indicates purge/leak maintenance"},
                ],
                "condition": "If storage vacuum rises above the allowed limit, trigger purge / leak maintenance.",
                "action": "Set PREP_NEEDED and schedule purge/leak check.",
            },
            "Clean-Air Velocity": {
                "fields": "Airflow (m/s); Intake Temp (degC); Fibre position note",
                "thresholds": [
                    {"Field": "Airflow (m/s)", "Rule": "<", "Value": "0.25", "Trigger Label": "Airflow too low"},
                    {"Field": "Airflow (m/s)", "Rule": ">", "Value": "0.50", "Trigger Label": "Airflow too high"},
                ],
                "condition": "If clean-air velocity is outside the allowed window, correct airflow and inspect filters.",
                "action": "Set PREP_NEEDED and schedule airflow/filter maintenance.",
            },
            "Interlocks Test": {
                "fields": "Water flow interlock; Gas flow interlock; Alarm note",
                "thresholds": [
                    {"Field": "Water flow interlock", "Rule": "!=", "Value": "PASS", "Trigger Label": "Water interlock failed"},
                    {"Field": "Gas flow interlock", "Rule": "!=", "Value": "PASS", "Trigger Label": "Gas interlock failed"},
                ],
                "condition": "If any furnace water/gas interlock fails, maintenance must be triggered before operation.",
                "action": "Set PREP_NEEDED and block operation until interlock issue is resolved.",
            },
            "X-Y Alignment": {
                "fields": "X offset (mm); Y offset (mm); Fibre position note",
                "thresholds": [
                    {"Field": "X offset (mm)", "Rule": ">", "Value": "0.5", "Trigger Label": "X offset too large"},
                    {"Field": "Y offset (mm)", "Rule": ">", "Value": "0.5", "Trigger Label": "Y offset too large"},
                ],
                "condition": "If X/Y offset grows beyond alignment tolerance, launch alignment maintenance.",
                "action": "Set PREP_NEEDED and schedule alignment correction.",
            },
            "Fibre Position Centering": {
                "fields": "Fibre position note; Window center error (mm); Line speed note",
                "thresholds": [
                    {"Field": "Window center error (mm)", "Rule": ">", "Value": "0.5", "Trigger Label": "Fibre moved too close to measurement window edge"},
                ],
                "condition": "If fibre position drifts from center when clean-air starts, correct airflow and alignment before running.",
                "action": "Set PREP_NEEDED and inspect fibre position / airflow settings.",
            },
            "Tension Gauge Calibration": {
                "fields": "Tare error; Span error; Calibration note",
                "thresholds": [
                    {"Field": "Tare error", "Rule": ">", "Value": "0.2", "Trigger Label": "Tare error above tolerance"},
                    {"Field": "Span error", "Rule": ">", "Value": "0.2", "Trigger Label": "Span error above tolerance"},
                ],
                "condition": "If the tension gauge will not calibrate or drifts outside tolerance, trigger calibration service / replacement path.",
                "action": "Set PREP_NEEDED and inspect/return load cell as required.",
            },
            "Bearing Play + Rotation": {
                "fields": "Bearing play (mm); Rotation feel; Cleanliness note",
                "thresholds": [
                    {"Field": "Bearing play (mm)", "Rule": ">", "Value": "0.2", "Trigger Label": "Bearing play above tolerance"},
                    {"Field": "Rotation feel", "Rule": "contains", "Value": "rough", "Trigger Label": "Rotation feels rough"},
                ],
                "condition": "If pulley rotation is rough or bearing play is significant, launch bearing maintenance.",
                "action": "Set PREP_NEEDED and schedule pulley/bearing maintenance.",
            },
            "Top Cap Erosion": {
                "fields": "Top cap length reduction (mm); Erosion note; Fibre strength note",
                "thresholds": [
                    {"Field": "Top cap length reduction (mm)", "Rule": ">", "Value": "3", "Trigger Label": "Top cap erosion exceeds 3 mm"},
                ],
                "condition": "If bottom sleeve top cap erosion exceeds the allowed range, replace it.",
                "action": "Set PREP_NEEDED and schedule top cap replacement.",
            },
            "Bottom Door Distortion": {
                "fields": "Door distortion note; Gas curtain note; Fibre contact note",
                "thresholds": [
                    {"Field": "Door distortion note", "Rule": "contains", "Value": "damage", "Trigger Label": "Bottom door damaged/distorted"},
                ],
                "condition": "If bottom door distortion or damage is found, replace before further running.",
                "action": "Set PREP_NEEDED and schedule bottom door replacement.",
            },
        }

    @st.cache_data(show_spinner=False)
    def _load_maintenance_test_presets_cached(path: str, mtime: float) -> dict:
        presets = default_maintenance_test_presets()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    clean = {}
                    for name, payload in raw.items():
                        if not isinstance(payload, dict):
                            continue
                        clean[safe_str(name).strip() or "Custom"] = {
                            "fields": safe_str(payload.get("fields", "")).strip(),
                            "thresholds": payload.get("thresholds", []) if isinstance(payload.get("thresholds", []), list) else [],
                            "condition": safe_str(payload.get("condition", "")).strip(),
                            "action": safe_str(payload.get("action", "")).strip(),
                        }
                    presets.update(clean)
            except Exception:
                pass
        presets.setdefault("Custom", {"fields": "", "thresholds": [], "condition": "", "action": ""})
        return presets

    def load_maintenance_test_presets() -> dict:
        return _load_maintenance_test_presets_cached(MAINT_TEST_PRESETS_JSON, _mtime(MAINT_TEST_PRESETS_JSON))

    def save_maintenance_test_presets(presets: dict) -> bool:
        try:
            with open(MAINT_TEST_PRESETS_JSON, "w", encoding="utf-8") as f:
                json.dump(presets, f, ensure_ascii=True, indent=2)
            return True
        except Exception:
            return False
    
    def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.rename(columns={c: normalize_map.get(str(c).strip().lower(), c) for c in df.columns}, inplace=True)
        if df.columns.duplicated().any():
            merged = pd.DataFrame(index=df.index)
            ordered_cols = list(dict.fromkeys(df.columns.tolist()))
            for col in ordered_cols:
                same_name = df.loc[:, df.columns == col]
                if isinstance(same_name, pd.Series):
                    merged[col] = same_name
                else:
                    # Coalesce legacy/new duplicate headers after normalization.
                    merged[col] = same_name.bfill(axis=1).iloc[:, 0]
            df = merged
        for r in REQUIRED:
            if r not in df.columns:
                df[r] = np.nan
        for c in OPTIONAL:
            if c not in df.columns:
                df[c] = np.nan
        return df
    
    def templateize_df(df_internal: pd.DataFrame, original_cols: list) -> pd.DataFrame:
        df = df_internal.copy()
        rename_back = {}
        for internal_col, template_key_lower in inverse_map.items():
            match = None
            for oc in original_cols:
                if str(oc).strip().lower() == template_key_lower:
                    match = oc
                    break
            if match is not None and internal_col in df.columns:
                rename_back[internal_col] = match
        df.rename(columns=rename_back, inplace=True)
        return df
    
    frames = []
    load_errors = []
    for fname in sorted(files):
        fpath = os.path.join(MAINT_FOLDER, fname)
        try:
            raw = read_file(fpath)
            if raw is None or raw.empty:
                continue
            df = normalize_df(raw)
            df["Source_File"] = fname
            frames.append(df)
        except ImportError as e:
            st.error("Excel engine missing. Install openpyxl in your .venv:")
            st.code("pip install openpyxl", language="bash")
            st.exception(e)
            st.stop()
        except Exception as e:
            load_errors.append((fname, str(e)))
    
    if not frames:
        st.error("No valid maintenance data could be loaded.")
        if load_errors:
            st.dataframe(pd.DataFrame(load_errors, columns=["File", "Error"]), use_container_width=True)
        st.stop()
    
    dfm = pd.concat(frames, ignore_index=True)
    # Remove placeholder rows coming from template tails (prevents "[OK] — (ID:)" ghost tasks).
    comp_s = dfm.get("Component", pd.Series([""] * len(dfm))).astype(str).str.strip()
    task_s = dfm.get("Task", pd.Series([""] * len(dfm))).astype(str).str.strip()
    mode_s = dfm.get("Tracking_Mode", pd.Series([""] * len(dfm))).astype(str).str.strip()
    tid_s = dfm.get("Task_ID", pd.Series([""] * len(dfm))).astype(str).str.strip()
    placeholder_mask = (
        comp_s.eq("")
        & task_s.eq("")
        & mode_s.eq("")
        & tid_s.eq("")
    )
    placeholder_count = int(placeholder_mask.sum())
    if placeholder_count > 0:
        dfm = dfm.loc[~placeholder_mask].copy()
        st.caption(f"Filtered empty template rows: {placeholder_count}")
    # Additional guard: a maintenance task must have both Component and Task.
    comp_s = dfm.get("Component", pd.Series([""] * len(dfm))).astype(str).str.strip()
    task_s = dfm.get("Task", pd.Series([""] * len(dfm))).astype(str).str.strip()
    invalid_task_mask = comp_s.eq("") | task_s.eq("")
    invalid_task_count = int(invalid_task_mask.sum())
    if invalid_task_count > 0:
        dfm = dfm.loc[~invalid_task_mask].copy()
        st.caption(f"Filtered invalid task rows (missing Component/Task): {invalid_task_count}")
    
    # =========================================================
    # Persisted inputs (hours + settings)
    # =========================================================
    def _persist_inputs():
        state["current_date"] = dt.date.today().isoformat()
        state["furnace_hours"] = float(st.session_state.get("maint_furnace_hours", 0.0))
        state["uv1_hours"] = float(st.session_state.get("maint_uv1_hours", 0.0))
        state["uv2_hours"] = float(st.session_state.get("maint_uv2_hours", 0.0))
        state["warn_days"] = int(st.session_state.get("maint_warn_days", 14))
        state["warn_hours"] = float(st.session_state.get("maint_warn_hours", 50.0))
        save_state(STATE_PATH, state)
        st.session_state["furnace_hours"] = state["furnace_hours"]
        st.session_state["uv1_hours"] = state["uv1_hours"]
        st.session_state["uv2_hours"] = state["uv2_hours"]
    
    default_furnace = float(state.get("furnace_hours", 0.0) or 0.0)
    default_uv1 = float(state.get("uv1_hours", 0.0) or 0.0)
    default_uv2 = float(state.get("uv2_hours", 0.0) or 0.0)
    default_warn_days = int(state.get("warn_days", 14) or 14)
    default_warn_hours = float(state.get("warn_hours", 50.0) or 50.0)

    # Compact weekly status view + folded editor.
    # Keep editor defaults synced with last saved weekly snapshot (without overriding active unsaved typing every rerun).
    saved_stamp = safe_str(state.get("status_weekly_updated_at", ""))
    if st.session_state.get("maint_weekly_loaded_stamp", None) != saved_stamp:
        st.session_state["maint_furnace_hours"] = default_furnace
        st.session_state["maint_uv1_hours"] = default_uv1
        st.session_state["maint_uv2_hours"] = default_uv2
        st.session_state["maint_warn_days"] = default_warn_days
        st.session_state["maint_warn_hours"] = default_warn_hours
        st.session_state["maint_weekly_loaded_stamp"] = saved_stamp
    else:
        st.session_state.setdefault("maint_furnace_hours", default_furnace)
        st.session_state.setdefault("maint_uv1_hours", default_uv1)
        st.session_state.setdefault("maint_uv2_hours", default_uv2)
        st.session_state.setdefault("maint_warn_days", default_warn_days)
        st.session_state.setdefault("maint_warn_hours", default_warn_hours)

    current_date = dt.date.today()
    weekly_updated_raw = safe_str(state.get("status_weekly_updated_at", ""))
    weekly_updated_dt = pd.to_datetime(weekly_updated_raw, errors="coerce")
    is_weekly_fresh = pd.notna(weekly_updated_dt) and ((pd.Timestamp(current_date) - weekly_updated_dt.normalize()).days <= 7)

    st.markdown('<div class="maint-section-title">📌 Current Tower Status (Weekly)</div>', unsafe_allow_html=True)
    draw_orders_count = get_draw_orders_count()
    c0, c1, c2, c3, c4, c5, c6 = st.columns(7)
    c0.metric("Today", str(current_date))
    c1.metric("Furnace h", f"{float(st.session_state.get('maint_furnace_hours', 0.0)):.1f}")
    c2.metric("UV1 h", f"{float(st.session_state.get('maint_uv1_hours', 0.0)):.1f}")
    c3.metric("UV2 h", f"{float(st.session_state.get('maint_uv2_hours', 0.0)):.1f}")
    c4.metric("Draws (dataset CSVs)", int(draw_orders_count))
    c5.metric("Warn days", int(st.session_state.get("maint_warn_days", 14)))
    c6.metric("Warn hours", f"{float(st.session_state.get('maint_warn_hours', 50.0)):.1f}")

    if is_weekly_fresh:
        st.success(f"Weekly status updated: {weekly_updated_dt.strftime('%Y-%m-%d %H:%M')}")
    else:
        show_ts = weekly_updated_dt.strftime("%Y-%m-%d %H:%M") if pd.notna(weekly_updated_dt) else "never"
        st.warning(f"Weekly status update is due. Last update: {show_ts}")

    with st.expander("🛠️ Edit Weekly Status Inputs", expanded=False):
        c2, c3, c4, c5 = st.columns([1, 1, 1, 1])
        with c2:
            st.number_input(
                "Furnace hours", min_value=0.0, step=1.0,
                key="maint_furnace_hours"
            )
        with c3:
            st.number_input(
                "UV System 1 hours", min_value=0.0, step=1.0,
                key="maint_uv1_hours"
            )
        with c4:
            st.number_input(
                "UV System 2 hours", min_value=0.0, step=1.0,
                key="maint_uv2_hours"
            )
        with c5:
            st.number_input(
                "Warn if due within (days)", min_value=0, step=1,
                key="maint_warn_days"
            )

        st.number_input(
            "Warn if due within (hours)", min_value=0.0, step=1.0,
            key="maint_warn_hours"
        )
        if st.button("💾 Save Weekly Status", key="maint_save_weekly_status_btn", type="primary", use_container_width=True):
            state["status_weekly_updated_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _persist_inputs()
            st.session_state["maint_weekly_loaded_stamp"] = safe_str(state.get("status_weekly_updated_at", ""))
            st.success("Weekly status saved.")
            st.rerun()

    furnace_hours = float(st.session_state.get("maint_furnace_hours", default_furnace))
    uv1_hours = float(st.session_state.get("maint_uv1_hours", default_uv1))
    uv2_hours = float(st.session_state.get("maint_uv2_hours", default_uv2))
    warn_days = int(st.session_state.get("maint_warn_days", default_warn_days))
    warn_hours = float(st.session_state.get("maint_warn_hours", default_warn_hours))
    st.caption("Hours-based tasks use **Hours Source**: FURNACE / UV1 / UV2. If empty -> defaults to FURNACE.")
    
    # =========================================================
    # Actor
    # =========================================================
    st.session_state.setdefault("maint_actor", "operator")
    st.text_input("Actor / operator name (for history)", key="maint_actor")
    actor = st.session_state.get("maint_actor", "operator")
    
    # =========================================================
    # Helpers
    # =========================================================
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
        if isinstance(s, pd.Series):
            s = s.iloc[0] if len(s) else ""
        s = "" if s is None or pd.isna(s) else str(s)
        return s.strip().lower()
    
    def pick_current_hours(hours_source: str) -> float:
        hs = norm_source(hours_source)
        if hs in ("uv2", "uv 2", "uv_system_2", "uv system 2", "uv-system-2", "system2", "system 2"):
            return float(uv2_hours)
        if hs in ("uv1", "uv 1", "uv_system_1", "uv system 1", "uv-system-1", "system1", "system 1"):
            return float(uv1_hours)
        return float(furnace_hours)
    
    def mode_norm(x: str) -> str:
        s = "" if x is None or pd.isna(x) else str(x).strip().lower()
        if s in ("draw", "draws", "draws_count", "draw_count"):
            return "draws"
        if s in ("either", "any", "both"):
            return "hours"
        return s

    def _split_trigger_modes(row) -> list:
        raw = safe_str(row.get("Trigger_Modes", "")).strip()
        out = []
        if raw:
            for p in raw.replace(";", ",").replace("|", ",").split(","):
                mv = mode_norm(p)
                if mv in ("hours", "draws", "calendar", "event") and mv not in out:
                    out.append(mv)
        if not out:
            mv = mode_norm(row.get("Tracking_Mode", ""))
            if mv:
                out = [mv]
        return out

    def _split_hours_sources(row) -> list:
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

    def _get_hours_baseline(row, src: str):
        if src == "uv1":
            b = parse_float(row.get("Last_Done_Hours_UV1", None))
            return b if b is not None else parse_float(row.get("Last_Done_Hours", None))
        if src == "uv2":
            b = parse_float(row.get("Last_Done_Hours_UV2", None))
            return b if b is not None else parse_float(row.get("Last_Done_Hours", None))
        b = parse_float(row.get("Last_Done_Hours_Furnace", None))
        return b if b is not None else parse_float(row.get("Last_Done_Hours", None))
    
    # =========================================================
    # Compute Next Due + Status
    # =========================================================
    dfm = compute_maintenance_status_df(
        dfm,
        current_draw_count=current_draw_count,
        furnace_hours=furnace_hours,
        uv1_hours=uv1_hours,
        uv2_hours=uv2_hours,
        warn_days=warn_days,
        warn_hours=warn_hours,
        current_date=current_date,
    )
    dfm["Task_Groups_List"] = dfm.apply(row_task_groups, axis=1)
    dfm["Task_Groups_Key"] = dfm["Task_Groups_List"].apply(build_group_key)
    
    st.session_state["maint_overdue"] = int((dfm["Status"] == "OVERDUE").sum())
    st.session_state["maint_due_soon"] = int((dfm["Status"] == "DUE SOON").sum())

    # =========================================================
    # Dashboard metrics + Open Critical Faults
    # =========================================================
    def get_open_faults_counts():
        faults_csv = _read_csv_safe(FAULTS_CSV, FAULTS_COLS)
        actions_csv = _read_csv_safe(FAULTS_ACTIONS_CSV, FAULTS_ACTIONS_COLS)
        smap = _latest_fault_state(actions_csv)
    
        if faults_csv.empty:
            return 0, 0
    
        faults_csv["fault_id"] = pd.to_numeric(faults_csv["fault_id"], errors="coerce")
        faults_csv = faults_csv.dropna(subset=["fault_id"]).copy()
        faults_csv["fault_id"] = faults_csv["fault_id"].astype(int)
    
        faults_csv["_is_closed"] = faults_csv["fault_id"].apply(lambda fid: bool(smap.get(int(fid), {}).get("is_closed", False)))
        open_df = faults_csv[~faults_csv["_is_closed"]].copy()
    
        crit_open = int((open_df["fault_severity"].astype(str).str.lower() == "critical").sum()) if not open_df.empty else 0
        open_total = int(len(open_df))
        return open_total, crit_open
    
    def render_maintenance_dashboard_metrics(dfm, current_date, current_draw_count):
        st.markdown(
            """
            <style>
              .maint-dash-band{
                padding: 4px 0 2px 0;
                margin: 10px 0 8px 0;
                border: 0;
                background: transparent;
              }
              .maint-dash-band-title{
                font-size: 0.98rem;
                font-weight: 860;
                color: rgba(232,246,255,0.98);
                margin: 0 0 1px 0;
              }
              .maint-dash-band-sub{
                font-size: 0.78rem;
                color: rgba(170,204,228,0.76);
                margin: 0 0 6px 0;
              }
              .maint-metrics-grid{
                display:grid;
                grid-template-columns: repeat(6, minmax(0, 1fr));
                gap: 10px;
                margin: 8px 0 10px 0;
              }
              .maint-metric-card{
                border-radius: 12px;
                padding: 10px 12px;
                border: 1px solid rgba(128,206,255,0.24);
                background: linear-gradient(180deg, rgba(14,32,56,0.36), rgba(8,16,28,0.26));
              }
              .maint-metric-k{
                font-size: 0.78rem;
                color: rgba(188,224,248,0.92);
                margin-bottom: 4px;
                font-weight: 700;
                letter-spacing: 0.2px;
              }
              .maint-metric-v{
                font-size: 2.0rem;
                line-height: 1.0;
                font-weight: 900;
              }
              .maint-v-red{ color:#ff5f5f; text-shadow:0 0 12px rgba(255,72,72,0.26); }
              .maint-v-orange{ color:#ffb84d; text-shadow:0 0 12px rgba(255,168,48,0.24); }
              .maint-v-green{ color:#6dff95; text-shadow:0 0 12px rgba(88,246,126,0.22); }
              .maint-v-blue{ color:#7ec6ff; text-shadow:0 0 12px rgba(86,180,255,0.22); }
              .maint-status-sentence{
                padding: 4px 0 0 0;
                margin: 2px 0 2px 0;
                color: rgba(194,224,242,0.86);
                font-size: 0.80rem;
                border: 0;
                background: transparent;
              }
              .maint-status-sentence b{
                color: rgba(238,249,255,0.98);
              }
              .maint-action-strip{
                display:grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 8px;
                margin: 4px 0 0 0;
              }
              .maint-action-card{
                border-radius: 10px;
                border: 1px solid rgba(128,206,255,0.10);
                background: rgba(8,16,28,0.08);
                padding: 8px 10px;
              }
              .maint-action-card b{
                color: rgba(238,249,255,0.98);
              }
              .maint-action-card span{
                display:block;
                color: rgba(176,210,232,0.78);
                font-size: 0.75rem;
                margin-top: 2px;
              }
              @media (max-width: 1100px){
                .maint-metrics-grid{ grid-template-columns: repeat(3, minmax(0, 1fr)); }
                .maint-action-strip{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
              }
            </style>
            """,
            unsafe_allow_html=True,
        )
        overdue = int((dfm["Status"] == "OVERDUE").sum())
        due_soon = int((dfm["Status"] == "DUE SOON").sum())
        routine = int((dfm["Status"] == "ROUTINE").sum())
        ok = int((dfm["Status"] == "OK").sum())
        open_faults, crit_faults = get_open_faults_counts()
        overdue_cls = "maint-v-red" if overdue > 0 else "maint-v-green"
        due_cls = "maint-v-orange" if due_soon > 0 else "maint-v-green"
        routine_cls = "maint-v-blue"
        ok_cls = "maint-v-green"
        open_cls = "maint-v-orange" if open_faults > 0 else "maint-v-green"
        crit_cls = "maint-v-red" if crit_faults > 0 else "maint-v-green"

        st.markdown(
            """
            <div class="maint-dash-band">
              <div class="maint-dash-band-title">Maintenance Health</div>
              <div class="maint-dash-band-sub">See overall task urgency and fault pressure first.</div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="maint-metrics-grid">
              <div class="maint-metric-card">
                <div class="maint-metric-k">OVERDUE</div>
                <div class="maint-metric-v {overdue_cls}">{overdue}</div>
              </div>
              <div class="maint-metric-card">
                <div class="maint-metric-k">DUE SOON</div>
                <div class="maint-metric-v {due_cls}">{due_soon}</div>
              </div>
              <div class="maint-metric-card">
                <div class="maint-metric-k">ROUTINE</div>
                <div class="maint-metric-v {routine_cls}">{routine}</div>
              </div>
              <div class="maint-metric-card">
                <div class="maint-metric-k">OK</div>
                <div class="maint-metric-v {ok_cls}">{ok}</div>
              </div>
              <div class="maint-metric-card">
                <div class="maint-metric-k">🚨 Open Faults</div>
                <div class="maint-metric-v {open_cls}">{open_faults}</div>
              </div>
              <div class="maint-metric-card">
                <div class="maint-metric-k">🟥 Critical Open</div>
                <div class="maint-metric-v {crit_cls}">{crit_faults}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="maint-status-sentence">
              <b>Picture now:</b> {overdue} overdue task(s), {due_soon} due soon, {open_faults} open fault(s), and {crit_faults} critical fault(s) still open.
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            "Use `1) Plan + Prepare` for scheduling and procurement, `2) Execute + Resolve Blocks` for waits, and the faults section for fault detail."
        )

    def render_maintenance_test_monitor():
        cols = [
            "test_ts",
            "task_id",
            "component",
            "task",
            "test_preset",
            "result_mode",
            "condition_met",
            "auto_threshold_met",
            "threshold_hits",
            "values_json",
            "condition_text",
            "action_text",
            "notes",
            "actor",
        ]
        tests_df = _read_csv_safe(MAINT_TEST_RECORDS_CSV, cols)
        if tests_df.empty:
            st.caption("No maintenance test records yet.")
            return
        tests_df["test_ts"] = pd.to_datetime(tests_df["test_ts"], errors="coerce")
        tests_df = tests_df.dropna(subset=["test_ts"]).copy()
        if tests_df.empty:
            st.caption("No valid maintenance test timestamps found.")
            return
        recent_df = tests_df.sort_values("test_ts", ascending=False).copy()
        last_7 = recent_df[recent_df["test_ts"] >= (pd.Timestamp.now().tz_localize(None) - pd.Timedelta(days=7))].copy()
        hit_mask = recent_df["auto_threshold_met"].astype(str).str.strip().str.lower().eq("yes")
        fail_mask = recent_df["condition_met"].astype(str).str.strip().str.lower().eq("yes")

        st.markdown("#### 🧪 Test Monitor")
        m1, m2, m3 = st.columns(3)
        m1.metric("Saved tests (7d)", int(len(last_7)))
        m2.metric("Threshold hits (7d)", int(last_7["auto_threshold_met"].astype(str).str.strip().str.lower().eq("yes").sum()) if not last_7.empty else 0)
        m3.metric("Condition met (7d)", int(last_7["condition_met"].astype(str).str.strip().str.lower().eq("yes").sum()) if not last_7.empty else 0)

        focus_df = recent_df[hit_mask | fail_mask].copy()
        if focus_df.empty:
            st.caption("No recent failed/triggered maintenance tests.")
            return
        focus_df["When"] = focus_df["test_ts"].dt.strftime("%Y-%m-%d %H:%M")
        view_cols = [c for c in ["When", "component", "task_id", "test_preset", "threshold_hits", "notes", "actor"] if c in focus_df.columns]
        st.dataframe(focus_df[view_cols].head(12), use_container_width=True, hide_index=True, height=min(340, 80 + 34 * len(focus_df.head(12))))
    
    # =========================================================
    # Horizon selector + roadmaps
    # =========================================================
    def render_maintenance_horizon_selector(current_draw_count: int):
        st.markdown("#### Horizon Setup")
    
        st.markdown(
            """
            <style>
            div.stButton > button {
                width: 100%;
                height: 44px;
                border-radius: 12px;
                font-weight: 600;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
    
        st.session_state.setdefault("maint_horizon_hours", 10)
        st.session_state.setdefault("maint_horizon_days", 7)
        st.session_state.setdefault("maint_horizon_draws", 5)
    
        def button_group(title, options, value, key):
            st.caption(title)
            cols = st.columns(len(options))
            for col, (label, v) in zip(cols, options):
                if col.button(label, key=f"{key}_{v}", type="primary" if v == value else "secondary"):
                    return v
            return value
    
        c1, c2, c3 = st.columns(3)
    
        with c1:
            st.session_state["maint_horizon_hours"] = button_group(
                "Hours horizon",
                [("10", 10), ("50", 50), ("100", 100)],
                st.session_state["maint_horizon_hours"],
                "mh"
            )
    
        with c2:
            st.session_state["maint_horizon_days"] = button_group(
                "Calendar horizon",
                [("Week", 7), ("Month", 30), ("3 Months", 90)],
                st.session_state["maint_horizon_days"],
                "md"
            )
    
        with c3:
            st.session_state["maint_horizon_draws"] = button_group(
                "Draw horizon",
                [("5", 5), ("10", 10), ("50", 50)],
                st.session_state["maint_horizon_draws"],
                "mD"
            )
    
        st.caption(
            f"📦 Now: **{current_draw_count}** → "
            f"Horizon: **{st.session_state['maint_horizon_draws']}** → "
            f"Up to draw **#{current_draw_count + st.session_state['maint_horizon_draws']}**"
        )
    
        return (
            st.session_state["maint_horizon_hours"],
            st.session_state["maint_horizon_days"],
            st.session_state["maint_horizon_draws"],
        )

    def render_future_schedule_focus_selector():
        st.session_state.setdefault("maint_future_focus", "all")
        st.caption("Focus by type")
        picked = st.radio(
            "Timeline type",
            options=["all", "hours", "draws", "calendar"],
            format_func=lambda v: {
                "all": "🌐 All",
                "hours": "🔥 Hours",
                "draws": "🧵 Draws",
                "calendar": "🗓️ Calendar",
            }.get(v, v),
            horizontal=True,
            key="maint_future_focus",
            label_visibility="collapsed",
        )
        return picked
    
    def render_maintenance_roadmaps(
        dfm: pd.DataFrame,
        current_date,
        current_draw_count: int,
        furnace_hours: float,
        uv1_hours: float,
        uv2_hours: float,
        horizon_hours: int,
        horizon_days: int,
        horizon_draws: int,
        focus: str = "all",
    ):
        def status_color(s):
            s = str(s).upper()
            if s == "OVERDUE":
                return "#ff4d4d"
            if s == "DUE SOON":
                return "#ffcc00"
            return "#66ff99"
    
        def roadmap(x0, x1, title, xlabel, df, xcol, hover):
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[0, 0], mode="lines",
                line=dict(width=6, color="rgba(180,180,180,0.2)"),
                hoverinfo="skip"
            ))
            fig.add_vline(x=x0, line_dash="dash")
    
            if df is not None and not df.empty:
                fig.add_trace(go.Scatter(
                    x=df[xcol],
                    y=[0] * len(df),
                    mode="markers",
                    marker=dict(
                        size=13,
                        color=[status_color(s) for s in df["Status"]],
                        line=dict(width=1, color="rgba(255,255,255,0.5)")
                    ),
                    text=df[hover],
                    hovertemplate="%{text}<extra></extra>",
                ))
            else:
                mid = x0 + (x1 - x0) / 2
                fig.add_annotation(x=mid, y=0, text="No tasks in horizon", showarrow=False)
    
            fig.update_layout(
                title=title,
                height=220,
                yaxis=dict(visible=False),
                xaxis=dict(title=xlabel),
                margin=dict(l=10, r=10, t=40, b=10),
            )
            return fig
    
        def norm_group(src):
            s = str(src).lower()
            if "uv1" in s:
                return "UV1"
            if "uv2" in s:
                return "UV2"
            return "FURNACE"
    
        hours_df = dfm[dfm["Tracking_Mode_norm"] == "hours"].copy()
        hours_df["Due"] = pd.to_numeric(hours_df["Next_Due_Hours"], errors="coerce")
        hours_df = hours_df.dropna(subset=["Due"])
        hours_df["Group"] = hours_df["Hours_Source"].apply(norm_group)
        hours_df["Hover"] = hours_df["Component"] + " — " + hours_df["Task"] + "<br>Status: " + hours_df["Status"]
    
        cal_df = dfm[dfm["Tracking_Mode_norm"] == "calendar"].copy()
        cal_df["Due"] = pd.to_datetime(cal_df["Next_Due_Date"], errors="coerce")
        cal_df = cal_df.dropna(subset=["Due"])
        cal_df["Hover"] = cal_df["Component"] + " — " + cal_df["Task"] + "<br>Status: " + cal_df["Status"]
    
        draw_df = dfm[dfm["Tracking_Mode_norm"] == "draws"].copy()
        draw_df["Due"] = pd.to_numeric(draw_df["Next_Due_Draw"], errors="coerce")
        draw_df = draw_df.dropna(subset=["Due"])
        draw_df["Hover"] = draw_df["Component"] + " — " + draw_df["Task"] + "<br>Status: " + draw_df["Status"]
    
        if focus in ("all", "hours"):
            st.markdown("### 🔥 Furnace / 💡 UV timelines")
            c1, c2, c3 = st.columns(3)

            with c1:
                x0, x1 = furnace_hours, furnace_hours + horizon_hours
                st.plotly_chart(
                    roadmap(x0, x1, "FURNACE", "Hours",
                            hours_df[(hours_df["Group"] == "FURNACE") & hours_df["Due"].between(x0, x1)],
                            "Due", "Hover"),
                    use_container_width=True
                )

            with c2:
                x0, x1 = uv1_hours, uv1_hours + horizon_hours
                st.plotly_chart(
                    roadmap(x0, x1, "UV1", "Hours",
                            hours_df[(hours_df["Group"] == "UV1") & hours_df["Due"].between(x0, x1)],
                            "Due", "Hover"),
                    use_container_width=True
                )

            with c3:
                x0, x1 = uv2_hours, uv2_hours + horizon_hours
                st.plotly_chart(
                    roadmap(x0, x1, "UV2", "Hours",
                            hours_df[(hours_df["Group"] == "UV2") & hours_df["Due"].between(x0, x1)],
                            "Due", "Hover"),
                    use_container_width=True
                )

        if focus in ("all", "draws"):
            st.markdown("### 🧵 Draw timeline")
            d0, d1 = current_draw_count, current_draw_count + horizon_draws
            st.plotly_chart(
                roadmap(d0, d1, "Draw-based tasks", "Draw #",
                        draw_df[draw_df["Due"].between(d0, d1)],
                        "Due", "Hover"),
                use_container_width=True
            )

        if focus in ("all", "calendar"):
            st.markdown("### 🗓️ Calendar timeline")
            t0 = pd.Timestamp(current_date)
            t1 = t0 + pd.Timedelta(days=horizon_days)
            st.plotly_chart(
                roadmap(t0, t1, "Calendar tasks", "Date",
                        cal_df[(cal_df["Due"] >= t0) & (cal_df["Due"] <= t1)],
                        "Due", "Hover"),
                use_container_width=True
            )
    
    # =========================================================
    # Done editor + apply done (updates + logs DB + CSV)
    # =========================================================
    def render_maintenance_done_editor(dfm, current_date, current_draw_count, furnace_hours, uv1_hours, uv2_hours, actor):
        focus_default = ["OVERDUE", "DUE SOON", "ROUTINE"]
        focus_status = st.multiselect(
            "Work on these statuses",
            ["OVERDUE", "DUE SOON", "ROUTINE", "OK"],
            default=focus_default,
            key="maint_focus_status"
        )
        q0, q1, q2, q3 = st.columns([1.3, 1.0, 1.0, 1.0])
        with q0:
            queue_mode = st.selectbox(
                "Execution queue",
                ["Status filter", "Due by date window", "Hours horizon", "Draw horizon", "Group package"],
                key="maint_exec_queue_mode",
            )
        with q1:
            window_days = st.number_input("Date window (days)", min_value=1, max_value=365, value=14, step=1, key="maint_exec_window_days")
        with q2:
            window_hours = st.number_input("Hours window", min_value=1.0, max_value=5000.0, value=50.0, step=1.0, key="maint_exec_window_hours")
        with q3:
            window_draws = st.number_input("Draw window", min_value=1, max_value=5000, value=20, step=1, key="maint_exec_window_draws")

        # Extra filters for large task lists.
        c_f1, c_f2, c_f3, c_f4 = st.columns([1.1, 1.1, 0.95, 1.0])
        all_components = sorted(
            [x for x in dfm.get("Component", pd.Series([], dtype=str)).astype(str).str.strip().unique().tolist() if x]
        )
        all_groups = sorted({g for groups in dfm.get("Task_Groups_List", pd.Series([], dtype=object)) for g in (groups or [])})
        with c_f1:
            focus_components = st.multiselect(
                "Filter by component",
                options=all_components,
                default=[],
                key="maint_focus_components",
            )
        with c_f2:
            focus_groups = st.multiselect(
                "Filter by group",
                options=all_groups,
                default=[],
                key="maint_focus_groups",
            )
        with c_f3:
            task_search = st.text_input(
                "Search task",
                value="",
                key="maint_focus_task_search",
                placeholder="type task text...",
            )
        with c_f4:
            focus_hours_source = st.selectbox(
                "Hours source focus",
                options=["All", "FURNACE", "UV1", "UV2"],
                index=0,
                key="maint_focus_hours_source",
            )
    
        base = dfm[dfm["Status"].isin(focus_status)].copy()
        work = base.copy()
        if queue_mode == "Due by date window":
            nd = pd.to_datetime(base.get("Next_Due_Date"), errors="coerce")
            horizon = pd.Timestamp(current_date) + pd.Timedelta(days=int(window_days))
            work = base[(base["Status"].astype(str).eq("OVERDUE")) | (nd.notna() & (nd <= horizon))].copy()
        elif queue_mode == "Hours horizon":
            src = st.selectbox("Hours source", ["FURNACE", "UV1", "UV2"], key="maint_exec_hours_src")
            cur_h = float(furnace_hours if src == "FURNACE" else uv1_hours if src == "UV1" else uv2_hours)
            nh = pd.to_numeric(base.get("Next_Due_Hours"), errors="coerce")
            hs = base.get("Hours_Source", pd.Series([""] * len(base))).astype(str).str.lower()
            hs_map = {"FURNACE": ["furnace", ""], "UV1": ["uv1", "uv 1", "system1"], "UV2": ["uv2", "uv 2", "system2"]}
            accepted = hs_map.get(src, ["furnace", ""])
            match_src = hs.isin(accepted) | (src == "FURNACE")
            work = base[match_src & nh.notna() & (nh <= (cur_h + float(window_hours)))].copy()
        elif queue_mode == "Draw horizon":
            ndraw = pd.to_numeric(base.get("Next_Due_Draw"), errors="coerce")
            work = base[ndraw.notna() & (ndraw <= (float(current_draw_count) + float(window_draws)))].copy()
        elif queue_mode == "Group package":
            pack_groups = st.multiselect("Package group(s)", options=all_groups, default=[g for g in ["3-Month"] if g in all_groups], key="maint_exec_pack_groups")
            if pack_groups:
                work = filter_df_by_groups(base, pack_groups)
            include_ok_group = st.checkbox("Include OK in package queue", value=False, key="maint_exec_pack_include_ok")
            if include_ok_group:
                work = filter_df_by_groups(dfm, pack_groups) if pack_groups else dfm.copy()
        work = work.sort_values(["Status", "Component", "Task"]).copy()
        if focus_hours_source != "All":
            hs = work.get("Hours_Source", pd.Series([""] * len(work))).astype(str).str.upper().str.strip()
            if focus_hours_source == "FURNACE":
                work = work[(hs.eq("FURNACE")) | hs.eq("")].copy()
            else:
                work = work[hs.eq(focus_hours_source)].copy()
        if focus_components:
            work = work[work["Component"].astype(str).isin(focus_components)].copy()
        if focus_groups:
            work = filter_df_by_groups(work, focus_groups)
        if task_search.strip():
            q = task_search.strip().lower()
            work = work[
                work["Task"].astype(str).str.lower().str.contains(q, na=False)
                | work["Task_ID"].astype(str).str.lower().str.contains(q, na=False)
            ].copy()
        # Parts status for execution readiness.
        inv_qty = {}
        inv_mounted_qty = {}
        inv_tool_map = {}
        inv_effective_qty = {}
        try:
            inv_df = load_inventory_cached(P.parts_inventory_csv)
            if not inv_df.empty:
                inv_df["Part Name"] = inv_df["Part Name"].astype(str).str.strip().str.lower()
                inv_df["Item Type"] = inv_df.get("Item Type", "").astype(str).str.strip().str.lower()
                inv_df["Location"] = inv_df.get("Location", "").astype(str).str.strip().str.lower()
                inv_df["Quantity"] = pd.to_numeric(inv_df.get("Quantity", 0), errors="coerce").fillna(0.0)
                stock_df = inv_df[inv_df["Location"].ne("mounted")].copy()
                inv_qty = stock_df.groupby("Part Name")["Quantity"].sum().to_dict()
                mounted_df = inv_df[inv_df["Location"].eq("mounted")].copy()
                inv_mounted_qty = mounted_df.groupby("Part Name")["Quantity"].sum().to_dict()
                inv_tool_map = (
                    inv_df.groupby("Part Name")
                    .apply(
                        lambda g: bool(
                            g["Item Type"].astype(str).str.strip().str.lower().eq("tool").any()
                            or is_tool_like_part_name(g.name)
                        )
                    )
                    .to_dict()
                )
                all_parts = set(inv_qty.keys()) | set(inv_mounted_qty.keys()) | set(inv_tool_map.keys())
                for pn in all_parts:
                    stock_q = float(inv_qty.get(pn, 0.0))
                    mounted_q = float(inv_mounted_qty.get(pn, 0.0))
                    inv_effective_qty[pn] = stock_q + mounted_q if bool(inv_tool_map.get(pn, False)) else stock_q
        except Exception:
            inv_qty = {}
            inv_mounted_qty = {}
            inv_tool_map = {}
            inv_effective_qty = {}

        def _parts_list(v):
            s = safe_str(v).strip()
            if not s:
                return []
            out = []
            for p in s.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
                pv = p.strip()
                if pv:
                    out.append(pv)
            uniq = []
            seen = set()
            for p in out:
                lk = p.lower()
                if lk not in seen:
                    uniq.append(p)
                    seen.add(lk)
            return uniq

        def _parts_status(req):
            parts = _parts_list(req)
            if not parts:
                return "No parts"
            miss = [p for p in parts if float(inv_effective_qty.get(p.lower(), 0.0)) <= 0]
            return "Ready" if not miss else f"Missing: {', '.join(miss)}"

        def _reschedule_task_by_policy(task_row):
            pol = infer_group_policy(task_row)
            if pol is None:
                return False, "No unambiguous group policy found for this task."
            src = safe_str(task_row.get("Source_File", "")).strip()
            if not src:
                return False, "Task has no Source_File."
            path = os.path.join(MAINT_FOLDER, src)
            if not os.path.exists(path):
                return False, f"Source file missing: {path}"
            try:
                raw = read_file(path)
                df_src = normalize_df(raw)
                mask = pd.Series([False] * len(df_src), index=df_src.index)
                task_id = safe_str(task_row.get("Task_ID", "")).strip()
                if "Task_ID" in df_src.columns and task_id:
                    mask = df_src["Task_ID"].astype(str).str.strip().eq(task_id)
                if not mask.any():
                    mask = (
                        df_src["Component"].astype(str).str.strip().eq(safe_str(task_row.get("Component", "")).strip())
                        & df_src["Task"].astype(str).str.strip().eq(safe_str(task_row.get("Task", "")).strip())
                    )
                if not mask.any():
                    return False, "Task row not found in source file."

                for c in [
                    "Tracking_Mode",
                    "Interval_Value",
                    "Interval_Unit",
                    "Last_Done_Date",
                    "Last_Done_Hours",
                    "Last_Done_Draw",
                    "Last_Done_Hours_UV1",
                    "Last_Done_Hours_UV2",
                    "Last_Done_Hours_Furnace",
                    "Trigger_Modes",
                ]:
                    if c not in df_src.columns:
                        df_src[c] = ""

                tm = safe_str(pol.get("tracking_mode", "")).strip()
                iv = pol.get("interval_value", None)
                iu = safe_str(pol.get("interval_unit", "")).strip()

                df_src.loc[mask, "Tracking_Mode"] = tm
                if iv is not None:
                    df_src.loc[mask, "Interval_Value"] = iv
                else:
                    cur_iv = pd.to_numeric(df_src.loc[mask, "Interval_Value"], errors="coerce")
                    if cur_iv.isna().all():
                        df_src.loc[mask, "Interval_Value"] = float(warn_hours)
                df_src.loc[mask, "Interval_Unit"] = iu

                mode = mode_norm(tm)
                trig_modes_raw = safe_str(task_row.get("Trigger_Modes", "")).strip()
                trig_modes = [
                    mode_norm(x) for x in trig_modes_raw.replace(";", ",").replace("|", ",").split(",")
                    if mode_norm(x) in ("hours", "draws", "calendar")
                ]
                if not trig_modes:
                    trig_modes = [mode]
                if "calendar" in trig_modes:
                    df_src.loc[mask, "Last_Done_Date"] = current_date.isoformat()
                if "hours" in trig_modes:
                    df_src.loc[mask, "Last_Done_Hours_Furnace"] = float(furnace_hours)
                    df_src.loc[mask, "Last_Done_Hours_UV1"] = float(uv1_hours)
                    df_src.loc[mask, "Last_Done_Hours_UV2"] = float(uv2_hours)
                    df_src.loc[mask, "Last_Done_Hours"] = float(pick_current_hours(task_row.get("Hours_Source", "")))
                if "draws" in trig_modes:
                    df_src.loc[mask, "Last_Done_Draw"] = int(current_draw_count)

                out = templateize_df(df_src, list(raw.columns))
                write_file(path, out)
                return True, safe_str(pol.get("policy_name", "policy"))
            except Exception as e:
                return False, str(e)

        work["Parts Status"] = work.get("Required_Parts", "").apply(_parts_status)
        # Work package lookup for readiness + execution.
        pkg_path = os.path.join(MAINT_FOLDER, "maintenance_work_packages.csv")
        pkg_df = pd.DataFrame()
        if os.path.exists(pkg_path):
            try:
                pkg_df = _read_csv_keepna(pkg_path)
            except Exception:
                pkg_df = pd.DataFrame()

        pkg_by_id = {}
        pkg_by_ct = {}
        if not pkg_df.empty:
            for _, pr in pkg_df.iterrows():
                tid = safe_str(pr.get("Task_ID", "")).strip().lower()
                comp = safe_str(pr.get("Component", "")).strip().lower()
                task = safe_str(pr.get("Task", "")).strip().lower()
                if tid:
                    pkg_by_id[tid] = pr
                if comp or task:
                    pkg_by_ct[(comp, task)] = pr

        def _pkg_for_row(row):
            tid = safe_str(row.get("Task_ID", "")).strip().lower()
            comp = safe_str(row.get("Component", "")).strip().lower()
            task = safe_str(row.get("Task", "")).strip().lower()
            if tid and tid in pkg_by_id:
                return pkg_by_id[tid]
            return pkg_by_ct.get((comp, task), None)

        # Load active reservation keys once (avoid per-row file read).
        active_res_keys = set()
        try:
            if os.path.exists(MAINT_RESERVATIONS_CSV):
                rsv_all = _read_csv_keepna(MAINT_RESERVATIONS_CSV)
            else:
                rsv_all = pd.DataFrame()
            if not rsv_all.empty:
                for c in ["state", "task_id", "component", "task"]:
                    if c not in rsv_all.columns:
                        rsv_all[c] = ""
                rsv_active = rsv_all[rsv_all["state"].astype(str).str.upper().eq("ACTIVE")].copy()
                for _, rrsv in rsv_active.iterrows():
                    active_res_keys.add(
                        (
                            safe_str(rrsv.get("task_id", "")).strip().lower(),
                            safe_str(rrsv.get("component", "")).strip().lower(),
                            safe_str(rrsv.get("task", "")).strip().lower(),
                        )
                    )
        except Exception:
            active_res_keys = set()

        readiness_cache = {}
        parts_missing_vals = []
        cond_parts_vals = []
        readiness_vals = []
        score_vals = []
        blockers_vals = []
        reserved_vals = []
        for i, r in work.iterrows():
            prow = _pkg_for_row(r)
            pkg_row = prow.to_dict() if prow is not None else {}
            rd = compute_readiness(task_row=r, package_row=pkg_row, stock_qty_map=inv_effective_qty)
            readiness_cache[int(i)] = {"pkg_row": pkg_row, "readiness": rd}
            parts_missing_vals.append(bool(rd.get("missing_parts")))
            cond_parts_vals.append(bool(rd.get("conditional_parts")))
            readiness_vals.append(safe_str(rd.get("readiness_label", "")))
            score_vals.append(int(rd.get("score", 0)))
            blockers_vals.append("YES" if not bool(rd.get("ready_to_start", False)) else "NO")
            rk = (
                safe_str(r.get("Task_ID", "")).strip().lower(),
                safe_str(r.get("Component", "")).strip().lower(),
                safe_str(r.get("Task", "")).strip().lower(),
            )
            reserved_vals.append("YES" if rk in active_res_keys else "NO")

        work["Parts Conditional"] = cond_parts_vals
        work["Parts Missing"] = parts_missing_vals
        work["Readiness"] = readiness_vals
        work["Readiness Score"] = score_vals
        work["Start Blocked"] = blockers_vals
        work["Reserved"] = reserved_vals
        work["Policy"] = work.apply(
            lambda r: safe_str((infer_group_policy(r) or {}).get("policy_name", "")) or "Manual",
            axis=1,
        )
        work = merge_state_into_df(
            work,
            MAINT_TASK_STATE_CSV,
            status_col="Status",
            parts_missing_col="Parts Missing",
            conditional_col="Parts Conditional",
        )
        work["Done_Now"] = False

        cols = [
            "Done_Now",
            "Lifecycle_State",
            "Status", "Component", "Task_Group", "Task", "Task_ID",
            "Policy", "Readiness", "Readiness Score", "Start Blocked", "Reserved", "Parts Status",
            "Tracking_Mode", "Hours_Source", "Current_Hours_For_Task",
            "Last_Done_Date", "Last_Done_Hours", "Last_Done_Draw",
            "Next_Due_Date", "Next_Due_Hours", "Next_Due_Draw",
            "Manual_Name", "Page", "Document",
            "Owner", "Source_File"
        ]
        cols = [c for c in cols if c in work.columns]

        st.caption(
            f"Filtered tasks: {len(work)} | Queue: {queue_mode} | "
            f"Date({int(window_days)}d) Hours({float(window_hours):.0f}) Draws({int(window_draws)})"
        )
    
        edited = st.data_editor(
            work[cols],
            use_container_width=True,
            height=420,
            column_config={
                "Done_Now": st.column_config.CheckboxColumn("Done now", help="Tick tasks you completed")
            },
            disabled=[c for c in cols if c != "Done_Now"],
            key="maint_editor"
        )

        # Export the current Mark Tasks Done table (including Done_Now selections).
        try:
            export_df = edited.copy()
        except Exception:
            export_df = work[cols].copy()
        csv_bytes = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download table (CSV)",
            data=csv_bytes,
            file_name="maintenance_mark_tasks_done.csv",
            mime="text/csv",
            key="maint_done_table_download",
            use_container_width=True,
        )
        # Execution workspace: selected task + work package + safety indicator + start action.
        st.markdown("##### 🧩 Execution Workspace (Work Package + Safety + Start)")
        opts = []
        idx_map = {}
        for i, r in work.iterrows():
            label = f"[{safe_str(r.get('Status',''))}] {safe_str(r.get('Component',''))} — {safe_str(r.get('Task',''))} (ID:{safe_str(r.get('Task_ID',''))})"
            opts.append(label)
            idx_map[label] = i
        if opts:
            jump_task_id = safe_str(st.session_state.get("maint_open_task_id", "")).strip()
            if jump_task_id:
                for label, row_idx in idx_map.items():
                    rr0 = work.loc[row_idx]
                    if safe_str(rr0.get("Task_ID", "")).strip() == jump_task_id:
                        st.session_state["maint_exec_workspace_pick"] = label
                        break
                st.session_state["maint_open_task_id"] = ""
            pick = st.selectbox("Open task workspace", options=opts, key="maint_exec_workspace_pick")
            rr = work.loc[idx_map[pick]]
            cached = readiness_cache.get(int(idx_map[pick]), {})
            rd = cached.get("readiness", {})
            pkg_row_cached = cached.get("pkg_row", {})
            task_id = safe_str(rr.get("Task_ID", "")).strip()
            req_parts_raw = ", ".join(_task_mandatory_parts(rr))
            req_parts = _parts_list(req_parts_raw)
            cond_parts_raw = ", ".join(_task_conditional_parts(rr))
            req_tools_raw = safe_str(pkg_row_cached.get("Required_Tools", "")).strip()
            req_tools = _parts_list(req_tools_raw)
            st.markdown(f"**Required parts:** {req_parts_raw if req_parts_raw else '_none_'}")
            if cond_parts_raw:
                st.markdown(f"**Conditional parts:** {cond_parts_raw}")
            st.markdown(f"**Required tools:** {req_tools_raw if req_tools_raw else '_none_'}")
            st.caption(
                f"Lifecycle: {safe_str(rr.get('Lifecycle_State',''))} | "
                f"Readiness: {safe_str(rd.get('readiness_label',''))} ({int(rd.get('score', 0))}/100)"
            )
            pol = infer_group_policy(rr)
            if pol is not None:
                st.success(
                    f"Auto policy on done/reschedule: {safe_str(pol.get('policy_name',''))} "
                    f"-> {safe_str(pol.get('tracking_mode',''))} "
                    f"({safe_str(pol.get('interval_value',''))} {safe_str(pol.get('interval_unit',''))})"
                )
            else:
                st.caption("Auto policy: manual (mixed/none group cadence).")
            if rd.get("blockers"):
                st.error("Start blockers: " + " | ".join([safe_str(x) for x in rd.get("blockers", []) if safe_str(x)]))
            elif rd.get("warnings"):
                st.info("Warnings: " + " | ".join([safe_str(x) for x in rd.get("warnings", []) if safe_str(x)]))
            if bool(rd.get("conditional_parts", False)):
                st.success("Conditional parts task: inspection first, replacement only if needed.")
                c_cond1, c_cond2 = st.columns([1.0, 1.0])
                with c_cond1:
                    if st.button("✅ Mark Inspection Only", key="maint_exec_conditional_inspection_only_btn", use_container_width=True):
                        ok, msg = set_task_state(
                            MAINT_TASK_STATE_CSV,
                            rr,
                            "DONE",
                            actor=safe_str(actor),
                            note="Conditional task closed as inspection-only (no replacement).",
                            force=True,
                        )
                        if ok:
                            st.success("Inspection-only step marked as DONE.")
                            st.rerun()
                        else:
                            st.warning(msg)
                with c_cond2:
                    if st.button("🔁 Mark Replacement Needed", key="maint_exec_conditional_replacement_needed_btn", use_container_width=True):
                        next_state = "PREP_READY" if safe_str(rr.get("Parts Status", "")).strip().lower() == "ready" else "BLOCKED_PARTS"
                        ok, msg = set_task_state(
                            MAINT_TASK_STATE_CSV,
                            rr,
                            next_state,
                            actor=safe_str(actor),
                            note="Conditional task requires replacement after inspection.",
                            force=True,
                        )
                        if ok:
                            if next_state == "BLOCKED_PARTS":
                                st.warning("Replacement needed and parts missing -> BLOCKED_PARTS.")
                            else:
                                st.info("Replacement needed and parts ready -> PREP_READY.")
                            st.rerun()
                        else:
                            st.warning(msg)
            if req_parts or req_tools:
                parts_rows = []
                tools_rows = []
                for p in req_parts:
                    lk = p.lower()
                    stock_q = float(inv_qty.get(lk, 0.0))
                    mounted_q = float(inv_mounted_qty.get(lk, 0.0))
                    is_tool = bool(inv_tool_map.get(lk, False) or is_tool_like_part_name(p))
                    if is_tool:
                        tools_rows.append(
                            {
                                "Tool": p,
                                "Stock (not mounted)": round(stock_q, 3),
                                "Mounted": round(mounted_q, 3),
                                "Ready": "YES" if (stock_q + mounted_q) > 0 else "NO",
                            }
                        )
                        continue
                    parts_rows.append(
                        {
                            "Part": p,
                            "Stock (not mounted)": round(stock_q, 3),
                            "Mounted": round(mounted_q, 3),
                            "Ready": "YES" if stock_q > 0 else "NO",
                        }
                    )
                for t in req_tools:
                    if any(str(r.get("Tool", "")).strip().lower() == t.lower() for r in tools_rows):
                        continue
                    lk = t.lower()
                    stock_q = float(inv_qty.get(lk, 0.0))
                    mounted_q = float(inv_mounted_qty.get(lk, 0.0))
                    tools_rows.append(
                        {
                            "Tool": t,
                            "Stock (not mounted)": round(stock_q, 3),
                            "Mounted": round(mounted_q, 3),
                            "Ready": "YES" if (stock_q + mounted_q) > 0 else "NO",
                        }
                    )
                if parts_rows:
                    st.markdown("##### 🔩 Parts needed")
                    st.dataframe(pd.DataFrame(parts_rows), use_container_width=True, height=min(200, 80 + 36 * len(parts_rows)))
                if tools_rows:
                    st.markdown("##### 🧰 Tools needed")
                    st.dataframe(pd.DataFrame(tools_rows), use_container_width=True, height=min(200, 80 + 36 * len(tools_rows)))
            show_exec_manual_ctx = st.toggle(
                "📘 Show manual context (on-demand, heavier)",
                value=False,
                key="maint_exec_show_manual_context",
            )
            if show_exec_manual_ctx:
                _render_task_manual_context(
                    rr,
                    req_parts + req_tools,
                    key_prefix="maint_exec_ctx",
                    actor_name=actor,
                    fallback_df=dfm,
                )
            else:
                st.caption("Manual context hidden for faster execution. Toggle on when needed.")

            test_fields_raw = safe_str(rr.get("Test_Fields", "")).strip()
            test_preset_raw = safe_str(rr.get("Test_Preset", "")).strip()
            test_thresholds_raw = safe_str(rr.get("Test_Thresholds", "")).strip()
            test_condition_raw = safe_str(rr.get("Test_Condition", "")).strip()
            test_action_raw = safe_str(rr.get("Test_Action", "")).strip()

            def _parse_test_fields(text: str):
                out = []
                for token in safe_str(text).replace("\n", ";").split(";"):
                    lbl = token.strip()
                    if lbl:
                        out.append(lbl)
                uniq = []
                seen = set()
                for lbl in out:
                    lk = lbl.lower()
                    if lk not in seen:
                        uniq.append(lbl)
                        seen.add(lk)
                return uniq

            test_fields = _parse_test_fields(test_fields_raw)
            def _parse_exec_threshold_rows(text: str):
                raw = safe_str(text).strip()
                if not raw:
                    return []
                try:
                    data = json.loads(raw)
                except Exception:
                    return []
                out = []
                if isinstance(data, list):
                    for row in data:
                        if not isinstance(row, dict):
                            continue
                        out.append(
                            {
                                "Field": safe_str(row.get("Field", "")).strip(),
                                "Rule": safe_str(row.get("Rule", "")).strip(),
                                "Value": safe_str(row.get("Value", "")).strip(),
                                "Trigger Label": safe_str(row.get("Trigger Label", "")).strip(),
                            }
                        )
                return out

            def _threshold_hit(rule_row: dict, values_map: dict):
                field = safe_str(rule_row.get("Field", "")).strip()
                rule = safe_str(rule_row.get("Rule", "")).strip()
                expect = safe_str(rule_row.get("Value", "")).strip()
                actual = safe_str(values_map.get(field, "")).strip()
                if not field or not rule:
                    return False, ""
                if rule == "contains":
                    ok = expect.lower() in actual.lower() if actual and expect else False
                else:
                    try:
                        actual_num = float(actual)
                        expect_num = float(expect)
                        if rule == ">":
                            ok = actual_num > expect_num
                        elif rule == ">=":
                            ok = actual_num >= expect_num
                        elif rule == "<":
                            ok = actual_num < expect_num
                        elif rule == "<=":
                            ok = actual_num <= expect_num
                        elif rule == "=":
                            ok = actual_num == expect_num
                        elif rule == "!=":
                            ok = actual_num != expect_num
                        else:
                            ok = False
                    except Exception:
                        if rule == "=":
                            ok = actual == expect
                        elif rule == "!=":
                            ok = actual != expect
                        else:
                            ok = False
                label = safe_str(rule_row.get("Trigger Label", "")).strip() or f"{field} {rule} {expect}"
                return bool(ok), label

            threshold_rows = _parse_exec_threshold_rows(test_thresholds_raw)
            test_log_cols = [
                "test_ts",
                "task_id",
                "component",
                "task",
                "test_preset",
                "result_mode",
                "condition_met",
                "auto_threshold_met",
                "threshold_hits",
                "values_json",
                "condition_text",
                "action_text",
                "notes",
                "actor",
            ]
            if test_fields or test_condition_raw or test_action_raw:
                st.markdown("##### 🧪 Test + Condition Capture")
                st.markdown(
                    """
                    <div class="maint-help-green">
                      <b>Use this inside execution</b><br/>
                      Capture the measured values for this maintenance task, then decide whether the condition was met.<br/>
                      This keeps monitoring data inside the same task workflow instead of a separate condition screen.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if test_fields:
                    st.caption("Fields to record: " + " | ".join(test_fields))
                if test_preset_raw:
                    st.caption(f"Preset: {test_preset_raw}")
                if test_condition_raw:
                    st.markdown(f"**Condition to watch:** {test_condition_raw}")
                if test_action_raw:
                    st.caption(f"Action if met: {test_action_raw}")
                if threshold_rows:
                    st.dataframe(pd.DataFrame(threshold_rows), use_container_width=True, hide_index=True, height=min(220, 80 + 34 * len(threshold_rows)))

                with st.form(f"maint_exec_test_form_{task_id or idx_map[pick]}"):
                    test_values = {}
                    field_cols = st.columns(2) if len(test_fields) > 1 else [st.container()]
                    for idx_field, field_lbl in enumerate(test_fields):
                        holder = field_cols[idx_field % len(field_cols)]
                        with holder:
                            test_values[field_lbl] = st.text_input(
                                field_lbl,
                                value="",
                                key=f"maint_exec_test_val_{task_id}_{idx_field}",
                                placeholder="enter measured value",
                            )
                    result_mode = st.radio(
                        "Test result",
                        options=["Auto from thresholds", "Monitor only", "Condition met", "Condition not met"],
                        horizontal=True,
                        key=f"maint_exec_test_result_{task_id}",
                    )
                    test_notes = st.text_area(
                        "Test notes",
                        height=90,
                        key=f"maint_exec_test_notes_{task_id}",
                        placeholder="What was measured, what was seen, and what should happen next.",
                    )
                    ta1, ta2, ta3 = st.columns(3)
                    with ta1:
                        apply_schedule_now = st.checkbox("Schedule now if met", value=False, key=f"maint_exec_test_sched_now_{task_id}")
                    with ta2:
                        apply_prep_needed = st.checkbox("Set PREP_NEEDED if met", value=True, key=f"maint_exec_test_prep_needed_{task_id}")
                    with ta3:
                        planned_duration_min = st.number_input(
                            "Duration if scheduled",
                            min_value=15,
                            max_value=600,
                            value=60,
                            step=15,
                            key=f"maint_exec_test_duration_{task_id}",
                        )
                    save_test = st.form_submit_button("💾 Save test result", use_container_width=True, type="primary")

                if save_test:
                    test_ts = pd.Timestamp.now().tz_localize(None)
                    threshold_hits = []
                    for tr in threshold_rows:
                        hit, label = _threshold_hit(tr, test_values)
                        if hit:
                            threshold_hits.append(label)
                    auto_cond_met = bool(threshold_hits)
                    if result_mode == "Condition met":
                        cond_met = True
                    elif result_mode == "Condition not met":
                        cond_met = False
                    elif result_mode == "Auto from thresholds":
                        cond_met = auto_cond_met
                    else:
                        cond_met = False
                    _append_csv(
                        MAINT_TEST_RECORDS_CSV,
                        test_log_cols,
                        pd.DataFrame([{
                            "test_ts": test_ts,
                            "task_id": task_id,
                            "component": safe_str(rr.get("Component", "")),
                            "task": safe_str(rr.get("Task", "")),
                            "test_preset": test_preset_raw,
                            "result_mode": result_mode,
                            "condition_met": "Yes" if cond_met else "No",
                            "auto_threshold_met": "Yes" if auto_cond_met else "No",
                            "threshold_hits": " | ".join(threshold_hits),
                            "values_json": json.dumps(test_values, ensure_ascii=True),
                            "condition_text": test_condition_raw,
                            "action_text": test_action_raw,
                            "notes": safe_str(test_notes).strip(),
                            "actor": safe_str(actor),
                        }]),
                    )
                    if cond_met and apply_prep_needed:
                        set_task_state(
                            MAINT_TASK_STATE_CSV,
                            rr,
                            "PREP_NEEDED",
                            actor=safe_str(actor),
                            note=f"Test condition met. {safe_str(test_notes).strip()}",
                            force=True,
                        )
                    if cond_met and apply_schedule_now:
                        sched_path = P.schedule_csv
                        try:
                            if os.path.exists(sched_path):
                                sched_df = _read_csv_keepna(sched_path)
                            else:
                                sched_df = pd.DataFrame()
                        except Exception:
                            sched_df = pd.DataFrame()
                        for c in ["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]:
                            if c not in sched_df.columns:
                                sched_df[c] = ""
                        sched_start = pd.Timestamp.now().tz_localize(None).replace(second=0, microsecond=0)
                        sched_end = sched_start + pd.Timedelta(minutes=int(planned_duration_min))
                        desc = (
                            f"[TEST] {safe_str(rr.get('Component',''))} - {safe_str(rr.get('Task',''))} "
                            f"(ID:{task_id}) | condition met"
                        )
                        sched_df = pd.concat(
                            [
                                sched_df[["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]],
                                pd.DataFrame([{
                                    "Event Type": "Maintenance",
                                    "Start DateTime": sched_start.strftime("%Y-%m-%d %H:%M:%S"),
                                    "End DateTime": sched_end.strftime("%Y-%m-%d %H:%M:%S"),
                                    "Description": desc,
                                    "Recurrence": "",
                                }]),
                            ],
                            ignore_index=True,
                        )
                        sched_df.to_csv(sched_path, index=False)
                    if cond_met:
                        if threshold_hits:
                            st.success("Test result saved. Condition met workflow was applied. Hits: " + " | ".join(threshold_hits))
                        else:
                            st.success("Test result saved. Condition met workflow was applied.")
                    else:
                        st.success("Test result saved.")
                    st.rerun()

                test_hist = _read_csv_safe(MAINT_TEST_RECORDS_CSV, test_log_cols)
                if not test_hist.empty:
                    task_hist = test_hist[test_hist["task_id"].astype(str).str.strip().eq(task_id)].copy()
                    if not task_hist.empty:
                        st.caption("Recent saved test results for this task")
                        st.dataframe(
                            task_hist.sort_values("test_ts", ascending=False).head(10)[["test_ts", "test_preset", "result_mode", "condition_met", "auto_threshold_met", "threshold_hits", "notes", "actor"]],
                            use_container_width=True,
                            hide_index=True,
                            height=min(210, 80 + 34 * len(task_hist.head(10))),
                        )
            active_res = list_task_reservations(
                MAINT_RESERVATIONS_CSV,
                task_id=task_id,
                component=safe_str(rr.get("Component", "")),
                task=safe_str(rr.get("Task", "")),
                active_only=True,
            )
            if not active_res.empty:
                show_res_cols = [c for c in ["part_name", "qty", "state", "reservation_ts", "updated_ts"] if c in active_res.columns]
                st.caption(f"Active reservations: {len(active_res)}")
                st.dataframe(active_res[show_res_cols], use_container_width=True, height=min(170, 80 + 32 * len(active_res)))
            else:
                st.caption("Active reservations: 0")

            prow = None
            if pkg_row_cached:
                prow = pd.Series(pkg_row_cached)
            if prow is not None:
                st.caption(f"Safety indicator: {safe_str(prow.get('Safety_TnM_Presence','Standard access'))}")
                st.markdown(f"**Preparation**\n\n{safe_str(prow.get('Preparation_Checklist','')) or '_empty_'}")
                st.markdown(f"**Safety**\n\n{safe_str(prow.get('Safety_Protocol','')) or '_empty_'}")
                st.markdown(f"**Procedure**\n\n{safe_str(prow.get('Procedure_Steps','')) or '_empty_'}")
            r1, r2 = st.columns([1.0, 2.0])
            with r1:
                reserve_qty = st.number_input("Reserve qty/part", min_value=0.1, max_value=1000.0, value=1.0, step=0.1, key="maint_exec_reserve_qty")
            with r2:
                reserve_note = st.text_input("Reservation note", value="", key="maint_exec_reserve_note", placeholder="optional")
            rb1, rb2 = st.columns([1.0, 1.0])
            with rb1:
                if st.button("📦 Reserve Required Parts", key="maint_exec_reserve_btn", use_container_width=True):
                    if not req_parts:
                        st.info("No required parts to reserve.")
                    else:
                        res = reserve_parts_for_task(
                            reservations_csv_path=MAINT_RESERVATIONS_CSV,
                            inventory_csv_path=P.parts_inventory_csv,
                            task_id=task_id,
                            component=safe_str(rr.get("Component", "")),
                            task=safe_str(rr.get("Task", "")),
                            parts=req_parts,
                            qty_per_part=float(reserve_qty),
                            actor=safe_str(actor),
                            note=safe_str(reserve_note),
                        )
                        created = int(res.get("created", 0))
                        missing = res.get("missing", []) or []
                        skipped_existing = int(res.get("skipped_existing", 0))
                        if created > 0:
                            st.success(f"Reserved {created} part row(s).")
                            set_task_state(
                                MAINT_TASK_STATE_CSV,
                                rr,
                                "PREP_READY",
                                actor=safe_str(actor),
                                note="Parts reserved for execution",
                                force=True,
                            )
                        if skipped_existing > 0:
                            st.info(f"Skipped existing active reservations: {skipped_existing}")
                        if missing:
                            st.warning("Missing for reservation: " + ", ".join([safe_str(x) for x in missing]))
                        st.rerun()
            with rb2:
                if st.button("↩️ Release Reservations", key="maint_exec_release_res_btn", use_container_width=True):
                    rel = release_task_reservations(
                        reservations_csv_path=MAINT_RESERVATIONS_CSV,
                        inventory_csv_path=P.parts_inventory_csv,
                        task_id=task_id,
                        component=safe_str(rr.get("Component", "")),
                        task=safe_str(rr.get("Task", "")),
                        actor=safe_str(actor),
                        note="Released from execution workspace",
                    )
                    if int(rel.get("released", 0)) > 0:
                        st.success(f"Released {int(rel.get('released', 0))} reservation(s).")
                        set_task_state(
                            MAINT_TASK_STATE_CSV,
                            rr,
                            "PREP_NEEDED",
                            actor=safe_str(actor),
                            note="Reservation released",
                            force=True,
                        )
                    else:
                        st.info("No active reservations to release.")
                    st.rerun()

            a1, a2, a3 = st.columns([1.0, 1.0, 1.25])
            with a1:
                if st.button("🧪 Set PREP_READY", key="maint_exec_set_prep_ready_btn", use_container_width=True):
                    ok, msg = set_task_state(
                        MAINT_TASK_STATE_CSV,
                        rr,
                        "PREP_READY",
                        actor=safe_str(actor),
                        note="Set from execution workspace",
                    )
                    if ok:
                        st.success("Task state set to PREP_READY.")
                        st.rerun()
                    else:
                        st.warning(msg)
            with a2:
                if st.button("⛔ Set BLOCKED_PARTS", key="maint_exec_set_blocked_parts_btn", use_container_width=True):
                    ok, msg = set_task_state(
                        MAINT_TASK_STATE_CSV,
                        rr,
                        "BLOCKED_PARTS",
                        actor=safe_str(actor),
                        note="Blocked in execution workspace",
                        force=True,
                    )
                    if ok:
                        st.warning("Task state set to BLOCKED_PARTS.")
                        st.rerun()
                    else:
                        st.warning(msg)
            with a3:
                if st.button("🗓️ Reschedule By Group Policy", key="maint_exec_resched_policy_btn", use_container_width=True):
                    ok, msg = _reschedule_task_by_policy(rr)
                    if ok:
                        set_task_state(
                            MAINT_TASK_STATE_CSV,
                            rr,
                            "PREP_NEEDED",
                            actor=safe_str(actor),
                            note=f"Rescheduled by group policy: {safe_str(msg)}",
                            force=True,
                        )
                        st.success(f"Rescheduled using policy: {safe_str(msg)}")
                        st.rerun()
                    else:
                        st.warning(msg)
            if st.button("🚦 Start Selected Task", key="maint_exec_start_task_btn", use_container_width=True, type="primary"):
                try:
                    if not bool(rd.get("ready_to_start", True)):
                        set_task_state(
                            MAINT_TASK_STATE_CSV,
                            rr,
                            "BLOCKED_PARTS",
                            actor=safe_str(actor),
                            note="Auto blocked by readiness gate",
                            force=True,
                        )
                        st.error("Cannot start: readiness gate failed. Resolve blockers first.")
                        return edited
                    safety_access = safe_str(prow.get("Safety_TnM_Presence", "")) if prow is not None else ""
                    safety_no_entry = str(safety_access).strip().lower().startswith("no entry")
                    record_activity_start(
                        indicator_json_path=P.activity_indicator_json,
                        events_csv_path=P.activity_events_csv,
                        activity_type="maintenance",
                        title=f"Maintenance Start | {safe_str(rr.get('Component',''))} — {safe_str(rr.get('Task',''))}",
                        actor=safe_str(actor),
                        source="maintenance_execute_workspace",
                        meta={
                            "task_id": task_id,
                            "component": safe_str(rr.get("Component", "")),
                            "task": safe_str(rr.get("Task", "")),
                            "parts_status": safe_str(rr.get("Parts Status", "")),
                            "safety_access": safety_access,
                            "safety_no_entry": bool(safety_no_entry),
                        },
                    )
                    set_task_state(
                        MAINT_TASK_STATE_CSV,
                        rr,
                        "IN_PROGRESS",
                        actor=safe_str(actor),
                        note="Started from execution workspace",
                    )
                    if safety_no_entry:
                        st.error("NO ENTRY indicator set for this started task.")
                    else:
                        st.success("Task started and activity indicator updated.")
                except Exception as e:
                    st.warning(f"Start indicator update failed: {e}")
        return edited

    def render_smart_maintenance_todo(
        *,
        dfm,
        current_date,
        current_draw_count,
        actor,
        con,
        read_file,
        write_file,
        normalize_df,
        templateize_df,
        pick_current_hours,
        mode_norm,
    ):
        st.markdown('<div class="maint-section-title">🧠 Smart Maintenance TODO</div>', unsafe_allow_html=True)
        st.caption("Worker board: open a queue (weekly / 3M / 6M / schedule / dataset group), then execute actions.")

        base_todo = (
            dfm[dfm["Status"].isin(["OVERDUE", "DUE SOON", "ROUTINE"])]
            .copy()
            .sort_values(["Status", "Component", "Task"])
        )
        if base_todo.empty:
            st.info("No pending maintenance TODO items.")
            return

        def _task_key(row):
            return (
                safe_str(row.get("Task_ID", "")).strip().lower(),
                safe_str(row.get("Component", "")).strip().lower(),
                safe_str(row.get("Task", "")).strip().lower(),
            )

        def _task_duration_minutes(row):
            est = pd.to_numeric(row.get("Est_Duration_Min", np.nan), errors="coerce")
            if pd.isna(est) or float(est) <= 0:
                est = 60.0
            slot = 15
            rounded = int(math.ceil(float(est) / float(slot)) * slot)
            return max(slot, rounded)

        def _parse_parts(parts_raw: str):
            s = safe_str(parts_raw).strip()
            if not s:
                return []
            chunks = []
            for p in s.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
                v = p.strip()
                if v:
                    chunks.append(v)
            out = []
            seen = set()
            for p in chunks:
                lk = p.lower()
                if lk not in seen:
                    out.append(p)
                    seen.add(lk)
            return out

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pending tasks", int(len(base_todo)))
        c2.metric("Overdue", int((base_todo["Status"] == "OVERDUE").sum()))
        c3.metric("Due soon", int((base_todo["Status"] == "DUE SOON").sum()))
        c4.metric("Routine", int((base_todo["Status"] == "ROUTINE").sum()))
        # Keep Smart TODO aligned with Mark Tasks Done filters (lighter + one flow).
        all_components = sorted(
            [x for x in dfm.get("Component", pd.Series([], dtype=str)).astype(str).str.strip().unique().tolist() if x]
        )
        all_groups = sorted({g for groups in dfm.get("Task_Groups_List", pd.Series([], dtype=object)) for g in (groups or [])})
        default_status = st.session_state.get("maint_focus_status", ["OVERDUE", "DUE SOON", "ROUTINE"])
        default_components = st.session_state.get("maint_focus_components", [])
        default_groups = st.session_state.get("maint_focus_groups", [])
        default_search = st.session_state.get("maint_focus_task_search", "")

        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.2, 1.2])
        with f1:
            smart_status = st.multiselect(
                "Statuses",
                ["OVERDUE", "DUE SOON", "ROUTINE", "OK"],
                default=default_status,
                key="maint_smart_status",
            )
        with f2:
            smart_components = st.multiselect(
                "Components",
                options=all_components,
                default=default_components,
                key="maint_smart_components",
            )
        with f3:
            smart_groups = st.multiselect(
                "Groups",
                options=all_groups,
                default=default_groups,
                key="maint_smart_groups",
            )
        with f4:
            smart_search = st.text_input(
                "Search task",
                value=default_search,
                key="maint_smart_search",
                placeholder="task / id...",
            )

        todo = base_todo.copy()
        if smart_status:
            todo = todo[todo["Status"].astype(str).isin(smart_status)].copy()
        if smart_components:
            todo = todo[todo["Component"].astype(str).isin(smart_components)].copy()
        if smart_groups:
            todo = filter_df_by_groups(todo, smart_groups)
        if smart_search.strip():
            q = smart_search.strip().lower()
            todo = todo[
                todo["Task"].astype(str).str.lower().str.contains(q, na=False)
                | todo["Task_ID"].astype(str).str.lower().str.contains(q, na=False)
            ].copy()

        if todo.empty:
            st.info("No tasks match the selected filters.")
            return

        cols_show = [
            "Status", "Task_Group", "Component", "Task", "Task_ID",
            "Required_Parts", "Tracking_Mode", "Hours_Source",
            "Next_Due_Date", "Next_Due_Hours", "Next_Due_Draw",
            "Owner", "Source_File",
        ]
        cols_show = [c for c in cols_show if c in todo.columns]
        st.markdown(
            """
            <div class="maint-lane-shell">
              <div class="maint-lane-title">Task Queue</div>
              <div class="maint-lane-sub">Choose the task that needs action now. This is the live operator queue, filtered by status, component, group, and search.</div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(todo[cols_show], use_container_width=True, height=320)
        st.markdown("</div>", unsafe_allow_html=True)

        # Waiting-for-parts tracker (auto-ready when parts are received + intake synced).
        st.markdown(
            """
            <div class="maint-lane-shell">
              <div class="maint-lane-title">Blocked Tasks Tracker</div>
              <div class="maint-lane-sub">Track tasks already on wait for part, see linked order progress, and resolve them when all requested parts are ready.</div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("##### ⏳ Waiting Parts Tracker")
        wait_df = _read_csv_safe(MAINT_WAIT_PARTS_CSV, MAINT_WAIT_PARTS_COLS)
        if not wait_df.empty:
            open_wait = wait_df[wait_df["resolved_ts"].fillna("").astype(str).str.strip().eq("")].copy()
            if not open_wait.empty:
                if os.path.exists(P.parts_orders_csv):
                    try:
                        odf = _read_csv_keepna(P.parts_orders_csv)
                    except Exception:
                        odf = pd.DataFrame()
                else:
                    odf = pd.DataFrame()
                for col in ["Part Name", "Status", "Inventory Synced"]:
                    if col not in odf.columns:
                        odf[col] = ""
                odf["_part"] = odf["Part Name"].astype(str).str.strip().str.lower()
                odf["_st"] = odf["Status"].astype(str).str.strip().str.lower()
                odf["_inv"] = odf["Inventory Synced"].astype(str).str.strip().str.lower()

                def _wait_ready(wait_row) -> bool:
                    req_plan = _load_wait_part_plan(wait_row)
                    if not req_plan:
                        return False
                    wait_id_v = safe_str(wait_row.get("wait_id", "")).strip()
                    task_id_v = safe_str(wait_row.get("maintenance_task_id", "")).strip()
                    for p, req_qty in req_plan.items():
                        ready_qty = _maintenance_linked_ready_count(
                            odf,
                            part_name=p,
                            maintenance_task_id=task_id_v,
                            wait_id=wait_id_v,
                        )
                        if int(ready_qty) < int(req_qty):
                            return False
                    return True

                def _wait_progress_text(wait_row) -> str:
                    req_plan = _load_wait_part_plan(wait_row)
                    if not req_plan:
                        return ""
                    wait_id_v = safe_str(wait_row.get("wait_id", "")).strip()
                    task_id_v = safe_str(wait_row.get("maintenance_task_id", "")).strip()
                    parts_progress = []
                    for p, req_qty in req_plan.items():
                        ready_qty = _maintenance_linked_ready_count(
                            odf,
                            part_name=p,
                            maintenance_task_id=task_id_v,
                            wait_id=wait_id_v,
                        )
                        parts_progress.append(f"{p}: {int(ready_qty)}/{int(req_qty)}")
                    return " | ".join(parts_progress)

                open_wait["ready_now"] = open_wait.apply(_wait_ready, axis=1)
                open_wait["linked_progress"] = open_wait.apply(_wait_progress_text, axis=1)
                ready_n = int(open_wait["ready_now"].sum())
                st.caption(f"Waiting parts tracker: {len(open_wait)} open wait item(s), ready now: {ready_n}.")
                wait_show_cols = [
                    c for c in [
                        "wait_id",
                        "maintenance_component",
                        "maintenance_task",
                        "requested_part_name",
                        "linked_progress",
                        "ready_now",
                    ] if c in open_wait.columns
                ]
                st.dataframe(
                    open_wait[wait_show_cols],
                    use_container_width=True,
                    hide_index=True,
                    height=min(240, 80 + 34 * len(open_wait)),
                )
                if ready_n > 0:
                    ready_rows = open_wait[open_wait["ready_now"]].copy()
                    show_cols = [c for c in ["wait_id", "maintenance_component", "maintenance_task", "requested_part_name", "linked_progress"] if c in ready_rows.columns]
                    st.dataframe(ready_rows[show_cols], use_container_width=True, height=120)
                    ready_opts = [str(x) for x in ready_rows["wait_id"].tolist()]
                    pick_ready = st.selectbox("Mark ready wait item as resolved", options=[""] + ready_opts, key="maint_wait_ready_pick")
                    if st.button("✅ Resolve Wait Item", key="maint_wait_resolve_btn", use_container_width=True):
                        if pick_ready:
                            wait_df2 = wait_df.copy()
                            mask = wait_df2["wait_id"].astype(str).eq(str(pick_ready))
                            wait_df2.loc[mask, "resolved_ts"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            wait_df2.loc[mask, "resolution_note"] = "Auto-ready: all requested parts are received and intake-synced."
                            wait_df2.to_csv(MAINT_WAIT_PARTS_CSV, index=False)
                            st.success("Wait item resolved.")
                            st.rerun()
            else:
                st.caption("No open wait-for-part items yet.")
        else:
            st.caption("No wait-for-part items created yet.")
        st.markdown("</div>", unsafe_allow_html=True)

        def _task_label(r):
            return (
                f"[{safe_str(r.get('Status',''))}] "
                f"{safe_str(r.get('Component',''))} — {safe_str(r.get('Task',''))} "
                f"(ID: {safe_str(r.get('Task_ID',''))})"
            )

        options = { _task_label(r): i for i, r in todo.iterrows() }
        pick = st.selectbox("Pick task", list(options.keys()), key="maint_smart_pick")
        sel_idx = options.get(pick)
        if sel_idx is None:
            return
        sel = todo.loc[sel_idx]
        st.markdown(
            """
            <div class="maint-lane-shell">
              <div class="maint-lane-title">Task Action + Execution Workspace</div>
              <div class="maint-lane-sub">Choose the active task, decide whether to complete it or block it on parts, then work inside the execution package with safety, manuals, tests, and reservations.</div>
            """,
            unsafe_allow_html=True,
        )

        if safe_str(sel.get("Required_Parts", "")).strip():
            st.caption(f"Required parts from dataset: {safe_str(sel.get('Required_Parts', '')).strip()}")

        action = st.radio(
            "Action",
            ["Mark Done", "Wait for Part"],
            horizontal=True,
            key="maint_smart_action",
        )

        if action == "Mark Done":
            if st.button("✅ Apply Done For Selected Task", key="maint_smart_done_btn", type="primary", use_container_width=True):
                try:
                    record_activity_start(
                        indicator_json_path=P.activity_indicator_json,
                        events_csv_path=P.activity_events_csv,
                        activity_type="maintenance",
                        title=f"Maintenance Start | {safe_str(sel.get('Component',''))} — {safe_str(sel.get('Task',''))}",
                        actor=safe_str(actor),
                        source="maintenance_smart_todo",
                        meta={
                            "task_id": safe_str(sel.get("Task_ID", "")),
                            "component": safe_str(sel.get("Component", "")),
                            "task": safe_str(sel.get("Task", "")),
                            "status": safe_str(sel.get("Status", "")),
                        },
                    )
                except Exception:
                    pass
                done_rows = sel.to_frame().T.copy()
                done_rows["Done_Now"] = True
                _apply_done_rows(
                    done_rows,
                    dfm=dfm,
                    used_parts_map={},
                    auto_consume_required=False,
                    current_date=current_date,
                    current_draw_count=current_draw_count,
                    actor=actor,
                    con=con,
                    read_file=read_file,
                    write_file=write_file,
                    normalize_df=normalize_df,
                    templateize_df=templateize_df,
                    pick_current_hours=pick_current_hours,
                    mode_norm=mode_norm,
                )
        else:
            default_parts = _parse_parts(safe_str(sel.get("Required_Parts", "")))
            c1, c2 = st.columns(2)
            with c1:
                selected_parts = st.multiselect(
                    "Parts to order",
                    options=default_parts,
                    default=default_parts,
                    key="maint_wait_parts_selected",
                )
                extra_parts = st.text_input(
                    "Add extra part(s) (comma separated)",
                    key="maint_wait_parts_extra",
                    placeholder="bearing A x2, valve B",
                )
                req_project = st.text_input("Project (optional)", key="maint_wait_project")
            with c2:
                req_company = st.text_input("Company (optional)", key="maint_wait_company")
                wait_reason = st.text_area("Reason", key="maint_wait_reason", height=110)

            part_qty_plan: dict[str, int] = {}
            if selected_parts:
                st.markdown("##### Requested quantities")
                qty_cols = st.columns(3)
                for idx_part, part_name in enumerate(selected_parts):
                    with qty_cols[idx_part % 3]:
                        qty_val = st.number_input(
                            f"{part_name}",
                            min_value=1,
                            step=1,
                            value=1,
                            key=f"maint_wait_qty_{safe_str(sel.get('Task_ID',''))}_{idx_part}_{part_name}",
                        )
                        part_qty_plan[safe_str(part_name).strip()] = int(qty_val)

            if st.button("🧾 Mark Wait For Part + Create Parts Order", key="maint_wait_create_btn", type="primary", use_container_width=True):
                extra_plan = _parse_part_qty_plan(extra_parts)
                for p_name, p_qty in extra_plan.items():
                    part_qty_plan[p_name] = int(part_qty_plan.get(p_name, 0)) + int(p_qty)
                if not part_qty_plan:
                    comp_fallback = safe_str(sel.get("Component", "")).strip()
                    if comp_fallback:
                        part_qty_plan = {comp_fallback: 1}
                if not part_qty_plan:
                    st.error("Required part(s) are mandatory.")
                    return
                details = (
                    f"Maintenance hold: {safe_str(sel.get('Component',''))} — {safe_str(sel.get('Task',''))} "
                    f"(Task ID: {safe_str(sel.get('Task_ID',''))}). "
                    f"Reason: {safe_str(wait_reason).strip() or 'waiting for part'}"
                )
                wait_id = int(time.time() * 1000)
                try:
                    release_task_reservations(
                        reservations_csv_path=MAINT_RESERVATIONS_CSV,
                        inventory_csv_path=P.parts_inventory_csv,
                        task_id=safe_str(sel.get("Task_ID", "")),
                        component=safe_str(sel.get("Component", "")),
                        task=safe_str(sel.get("Task", "")),
                        actor=safe_str(actor),
                        note="Released automatically on WAIT FOR PART",
                    )
                except Exception:
                    pass
                pretty_parts = []
                for req_part_name, req_qty in part_qty_plan.items():
                    pretty_parts.append(f"{req_part_name} x{int(req_qty)}")
                    for idx_qty in range(int(req_qty)):
                        order_details = details
                        if int(req_qty) > 1:
                            order_details = f"{details} | Request {idx_qty + 1}/{int(req_qty)}"
                        _append_parts_order_from_maintenance(
                            part_name=req_part_name,
                            details=order_details,
                            actor=actor,
                            project_name=req_project,
                            company=req_company,
                            maintenance_component=safe_str(sel.get("Component", "")),
                            maintenance_task=safe_str(sel.get("Task", "")),
                            maintenance_task_id=safe_str(sel.get("Task_ID", "")),
                            wait_id=str(wait_id),
                        )
                wait_row = pd.DataFrame([{
                    "wait_id": wait_id,
                    "wait_ts": dt.datetime.now(),
                    "maintenance_component": safe_str(sel.get("Component", "")),
                    "maintenance_task": safe_str(sel.get("Task", "")),
                    "maintenance_task_id": safe_str(sel.get("Task_ID", "")),
                    "maintenance_source_file": safe_str(sel.get("Source_File", "")),
                    "requested_part_name": ", ".join(pretty_parts),
                    "requested_part_plan_json": json.dumps(part_qty_plan, ensure_ascii=True),
                    "requested_project_name": safe_str(req_project).strip(),
                    "requested_company": safe_str(req_company).strip(),
                    "wait_reason": safe_str(wait_reason).strip(),
                    "actor": safe_str(actor),
                    "resolved_ts": "",
                    "resolution_note": "",
                }])
                _append_csv(MAINT_WAIT_PARTS_CSV, MAINT_WAIT_PARTS_COLS, wait_row)
                try:
                    set_task_state(
                        MAINT_TASK_STATE_CSV,
                        sel,
                        "BLOCKED_PARTS",
                        actor=safe_str(actor),
                        note=f"Wait for part: {safe_str(wait_reason).strip() or 'waiting for parts'}",
                        force=True,
                    )
                except Exception:
                    pass
                st.success(f"Task marked as WAIT FOR PART and {sum(int(v) for v in part_qty_plan.values())} parts order(s) created.")
        st.markdown("</div>", unsafe_allow_html=True)

    def render_quick_reschedule_panel(
        *,
        dfm,
        MAINT_FOLDER,
        current_draw_count,
        furnace_hours,
        uv1_hours,
        uv2_hours,
        read_file,
        write_file,
        normalize_df,
        templateize_df,
    ):
        st.caption("Push a maintenance task quickly: +draws or +hours, without editing full tables.")

        def _task_label(r: dict) -> str:
            return (
                f"[{safe_str(r.get('Status',''))}] "
                f"{safe_str(r.get('Component',''))} — {safe_str(r.get('Task',''))} "
                f"(ID: {safe_str(r.get('Task_ID',''))})"
            )

        def _update_task_in_source(task_row: dict, *, by_mode: str, shift_value: float):
            src = safe_str(task_row.get("Source_File", ""))
            if not src:
                st.error("Task has no Source_File; cannot update.")
                return
            path = os.path.join(MAINT_FOLDER, src)
            if not os.path.exists(path):
                st.error(f"Source file missing: {path}")
                return

            raw = read_file(path)
            df_src = normalize_df(raw)
            mask = (
                df_src["Component"].astype(str).eq(str(task_row.get("Component", "")))
                & df_src["Task"].astype(str).eq(str(task_row.get("Task", "")))
            )
            if not mask.any():
                st.warning("Task not found in source file.")
                return

            if by_mode == "draws":
                base = parse_int(task_row.get("Last_Done_Draw", None))
                if base is None:
                    base = int(current_draw_count)
                df_src.loc[mask, "Last_Done_Draw"] = int(base + int(shift_value))
            elif by_mode == "hours":
                hs = norm_source(task_row.get("Hours_Source", ""))
                current_ref = float(furnace_hours)
                if hs in ("uv1", "uv 1", "uv_system_1", "uv system 1", "uv-system-1", "system1", "system 1"):
                    current_ref = float(uv1_hours)
                elif hs in ("uv2", "uv 2", "uv_system_2", "uv system 2", "uv-system-2", "system2", "system 2"):
                    current_ref = float(uv2_hours)

                base = parse_float(task_row.get("Last_Done_Hours", None))
                if base is None:
                    base = current_ref
                df_src.loc[mask, "Last_Done_Hours"] = float(base + float(shift_value))
            else:
                return

            out = templateize_df(df_src, list(raw.columns))
            write_file(path, out)
            st.success(f"Rescheduled: {safe_str(task_row.get('Component',''))} — {safe_str(task_row.get('Task',''))}")
            st.rerun()

        # Draw-based quick push
        draw_tasks = (
            dfm[dfm["Tracking_Mode_norm"] == "draws"]
            .copy()
            .sort_values(["Status", "Component", "Task"])
        )
        hour_tasks = (
            dfm[dfm["Tracking_Mode_norm"] == "hours"]
            .copy()
            .sort_values(["Status", "Component", "Task"])
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🧵 Draw-based tasks**")
            if draw_tasks.empty:
                st.info("No draw-based tasks found.")
            else:
                d_opts = draw_tasks.to_dict("records")
                d_pick = st.selectbox(
                    "Select draw task",
                    options=d_opts,
                    format_func=_task_label,
                    key="maint_resched_draw_pick",
                )
                d_shift = st.number_input(
                    "Push by draws",
                    min_value=1,
                    value=5,
                    step=1,
                    key="maint_resched_draw_shift",
                )
                if st.button("⏩ Schedule +Draws", use_container_width=True, type="primary", key="maint_resched_draw_apply"):
                    _update_task_in_source(d_pick, by_mode="draws", shift_value=float(d_shift))

        with c2:
            st.markdown("**🔥 Hour-based tasks**")
            if hour_tasks.empty:
                st.info("No hour-based tasks found.")
            else:
                h_opts = hour_tasks.to_dict("records")
                h_pick = st.selectbox(
                    "Select hours task",
                    options=h_opts,
                    format_func=_task_label,
                    key="maint_resched_hours_pick",
                )
                h_shift = st.number_input(
                    "Push by hours",
                    min_value=1.0,
                    value=5.0,
                    step=1.0,
                    key="maint_resched_hours_shift",
                )
                if st.button("⏩ Schedule +Hours", use_container_width=True, type="primary", key="maint_resched_hours_apply"):
                    _update_task_in_source(h_pick, by_mode="hours", shift_value=float(h_shift))

    def render_maintenance_scheduler_bridge(
        *,
        dfm,
        current_date,
        current_draw_count,
        furnace_hours,
        uv1_hours,
        uv2_hours,
    ):
        st.caption("Automatic flow: check the summary, fix real problems only if they exist, then review the next preparation batch.")

        def _parse_parts(parts_raw: str):
            s = safe_str(parts_raw).strip()
            if not s:
                return []
            out = []
            for p in s.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
                v = p.strip()
                if v:
                    out.append(v)
            uniq = []
            seen = set()
            for p in out:
                lk = p.lower()
                if lk not in seen:
                    uniq.append(p)
                    seen.add(lk)
            return uniq

        def _task_key(row):
            return (
                safe_str(row.get("Task_ID", "")).strip().lower(),
                safe_str(row.get("Component", "")).strip().lower(),
                safe_str(row.get("Task", "")).strip().lower(),
            )

        if False:
            with st.expander("Advanced automatic rules", expanded=False):
                pass

        horizon_days = int(st.session_state.get("maint_sched_horizon_days", 14))
        schedule_grid_min = 15
        day_start_h = int(st.session_state.get("maint_sched_day_start", 8))
        day_end_h = int(st.session_state.get("maint_sched_day_end", 18))
        include_overdue = bool(st.session_state.get("maint_sched_include_overdue", True))
        include_due_soon = bool(st.session_state.get("maint_sched_include_due_soon", True))
        include_routine = bool(st.session_state.get("maint_sched_include_routine", False))
        include_ok = bool(st.session_state.get("maint_sched_include_ok", False))
        use_days_window = bool(st.session_state.get("maint_sched_use_days_window", True))
        days_window = int(st.session_state.get("maint_sched_days_window", 7))
        use_hours_window = bool(st.session_state.get("maint_sched_use_hours_window", True))
        hours_window = float(st.session_state.get("maint_sched_hours_window", 10.0))
        use_draws_window = bool(st.session_state.get("maint_sched_use_draws_window", True))
        draws_window = int(st.session_state.get("maint_sched_draws_window", 5))
        planning_strategy = st.session_state.get("maint_sched_strategy", "Urgency first")
        component_priority = st.session_state.get("maint_sched_component_priority", [])

        group_options_set = set()
        component_options_set = set()
        for _, rr in dfm.iterrows():
            for g in row_task_groups(rr):
                group_options_set.add(g)
            comp_name = safe_str(rr.get("Component", "")).strip()
            if comp_name:
                component_options_set.add(comp_name)
        group_options = sorted(group_options_set)
        component_options = sorted(component_options_set)
        selected_task_groups = st.session_state.get("maint_sched_task_groups_focus", [])
        selected_component_focus = st.session_state.get("maint_sched_component_focus", [])

        weekday_to_idx = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Sunday": 6}
        preferred_days = st.session_state.get("maint_sched_preferred_days", ["Thursday"])
        add_parts_check_event = bool(st.session_state.get("maint_sched_add_parts_check", True))
        parts_check_days_before = int(st.session_state.get("maint_sched_parts_check_days_before", 7))
        if not preferred_days:
            preferred_days = ["Thursday"]
        preferred_idx = [weekday_to_idx[d] for d in preferred_days if d in weekday_to_idx]

        if int(day_end_h) <= int(day_start_h):
            st.warning("Day end must be after day start.")
            return

        # ---- Build candidate queue from status + timing windows + optional focus
        base = dfm.copy()
        status_mask = pd.Series(False, index=base.index)
        if include_overdue:
            status_mask = status_mask | base["Status"].astype(str).str.upper().eq("OVERDUE")
        if include_due_soon:
            status_mask = status_mask | base["Status"].astype(str).str.upper().eq("DUE SOON")
        if include_routine:
            status_mask = status_mask | base["Status"].astype(str).str.upper().eq("ROUTINE")
        if include_ok:
            status_mask = status_mask | base["Status"].astype(str).str.upper().eq("OK")

        tracking_mode_series = base.get("Tracking_Mode_norm", base.get("Tracking_Mode", pd.Series([""] * len(base), index=base.index))).astype(str).str.lower()
        due_ts = pd.to_datetime(base.get("Next_Due_Date"), errors="coerce")
        next_hours = pd.to_numeric(base.get("Next_Due_Hours"), errors="coerce")
        cur_hours = pd.to_numeric(base.get("Current_Hours_For_Task", 0), errors="coerce")
        next_draws = pd.to_numeric(base.get("Next_Due_Draw"), errors="coerce")

        days_mask = pd.Series(False, index=base.index)
        if use_days_window:
            days_mask = (
                tracking_mode_series.eq("calendar")
                & due_ts.notna()
                & (due_ts <= pd.Timestamp(current_date) + pd.Timedelta(days=int(days_window)))
            )

        hours_mask = pd.Series(False, index=base.index)
        if use_hours_window:
            hours_gap = next_hours - cur_hours
            hours_mask = (
                tracking_mode_series.eq("hours")
                & next_hours.notna()
                & cur_hours.notna()
                & (hours_gap <= float(hours_window))
            )

        draws_mask = pd.Series(False, index=base.index)
        if use_draws_window:
            draws_gap = next_draws - float(current_draw_count)
            draws_mask = (
                tracking_mode_series.eq("draws")
                & next_draws.notna()
                & (draws_gap <= float(draws_window))
            )

        selected_mask = status_mask | days_mask | hours_mask | draws_mask
        cand = base[selected_mask].copy()

        if selected_task_groups:
            cand = filter_df_by_groups(cand, selected_task_groups)

        if selected_component_focus:
            focus_norm = {safe_str(v).strip().lower() for v in selected_component_focus if safe_str(v).strip()}
            cand = cand[
                cand.get("Component", pd.Series([""] * len(cand), index=cand.index))
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(focus_norm)
            ].copy()

        if cand.empty:
            st.info("No candidate tasks match the current status/timing rules.")
            return

        watch_df = _build_maintenance_parts_watch_df(
            dfm,
            current_date=current_date,
            current_draw_count=current_draw_count,
        )
        parts_risk_n = int(len(watch_df))
        problem_now_n = int(watch_df["Problem Now"].astype(str).str.strip().str.lower().eq("yes").sum()) if not watch_df.empty and "Problem Now" in watch_df.columns else 0
        need_order_n = int(watch_df["Needs Order"].astype(str).str.strip().ne("").sum()) if not watch_df.empty else 0
        waiting_orders_n = int(watch_df["Has Active Orders"].astype(str).str.strip().str.lower().eq("yes").sum()) if not watch_df.empty else 0

        if not watch_df.empty:
            auto_watch_df = watch_df[watch_df["Auto Order"].astype(str).str.strip().str.lower().eq("yes")].copy()
        else:
            auto_watch_df = pd.DataFrame()
        auto_order_df = auto_watch_df[auto_watch_df["Needs Order"].astype(str).str.strip().ne("")].copy() if not auto_watch_df.empty else pd.DataFrame()
        if not auto_order_df.empty:
            if os.path.exists(P.parts_orders_csv):
                try:
                    odf_live = _read_csv_keepna(P.parts_orders_csv)
                except Exception:
                    odf_live = pd.DataFrame()
            else:
                odf_live = pd.DataFrame()
            created_auto = 0
            for _, r in auto_order_df.iterrows():
                task_name = safe_str(r.get("Task", ""))
                task_id = safe_str(r.get("Task_ID", ""))
                component = safe_str(r.get("Component", ""))
                for part_name in _split_required_parts(r.get("Needs Order", "")):
                    if _maintenance_active_order_mask(
                        odf_live,
                        part_name=part_name,
                        maintenance_task_id=task_id,
                        wait_id="",
                    ).any():
                        continue
                    details = (
                        f"Auto maintenance planning: {component} — {task_name} "
                        f"(Task ID: {task_id}). Mandatory part missing inside the task parts-check window."
                    )
                    _append_parts_order_from_maintenance(
                        part_name=part_name,
                        details=details,
                        actor=actor,
                        project_name="Maintenance",
                        company="",
                        maintenance_component=component,
                        maintenance_task=task_name,
                        maintenance_task_id=task_id,
                        wait_id="",
                    )
                    created_auto += 1
            if created_auto > 0:
                st.info(f"Automatic maintenance ordering opened {created_auto} linked order(s) for missing mandatory parts.")
                st.rerun()

        plan_view_df = cand.copy()
        if "Required_Parts" not in plan_view_df.columns:
            plan_view_df["Required_Parts"] = ""
        plan_view_df["Required_Parts"] = plan_view_df.apply(lambda r: ", ".join(_task_mandatory_parts(r)), axis=1)
        if "Conditional_Parts" not in plan_view_df.columns:
            plan_view_df["Conditional_Parts"] = ""
        plan_view_df["Conditional_Parts"] = plan_view_df.apply(lambda r: ", ".join(_task_conditional_parts(r)), axis=1)
        inv_effective_qty_preview = _load_inventory_effective_qty_map()
        def _pack_parts_state(req_raw):
            req_parts = _split_required_parts(req_raw)
            if not req_parts:
                return "No parts"
            missing = [p for p in req_parts if float(inv_effective_qty_preview.get(str(p).strip().lower(), 0.0)) <= 0]
            if missing:
                return "Missing: " + ", ".join(missing)
            return "Ready"
        plan_view_df["Pack Parts State"] = plan_view_df["Required_Parts"].apply(_pack_parts_state)
        day_pack_ready_n = int(plan_view_df["Pack Parts State"].astype(str).eq("Ready").sum())
        day_pack_missing_n = int(plan_view_df["Pack Parts State"].astype(str).str.startswith("Missing:").sum())
        suggested_pack_date = current_date
        due_dates_pack = pd.to_datetime(plan_view_df.get("Next_Due_Date"), errors="coerce")
        future_due = due_dates_pack[due_dates_pack.notna()]
        if not future_due.empty:
            suggested_pack_date = future_due.min().date()

        problems_n = int(problem_now_n)
        st.markdown(
            f"""
            <div class="maint-prep-grid">
              <div class="maint-prep-card k-blue">
                <div class="maint-prep-k">Upcoming tasks</div>
                <div class="maint-prep-v maint-v-blue">{int(len(plan_view_df))}</div>
                <div class="maint-prep-note">Automatic planning queue</div>
              </div>
              <div class="maint-prep-card {'k-red' if problems_n else 'k-green'}">
                <div class="maint-prep-k">Problems</div>
                <div class="maint-prep-v {'maint-v-red' if problems_n else 'maint-v-green'}">{problems_n}</div>
                <div class="maint-prep-note">Late mandatory orders or blocked follow-up</div>
              </div>
              <div class="maint-prep-card {'k-green' if day_pack_ready_n else 'k-blue'}">
                <div class="maint-prep-k">Ready to prepare</div>
                <div class="maint-prep-v {'maint-v-green' if day_pack_ready_n else 'maint-v-blue'}">{day_pack_ready_n}</div>
                <div class="maint-prep-note">Tasks already clear for preparation</div>
              </div>
              <div class="maint-prep-card {'k-amber' if waiting_orders_n else 'k-blue'}">
                <div class="maint-prep-k">Waiting on orders</div>
                <div class="maint-prep-v {'maint-v-orange' if waiting_orders_n else 'maint-v-blue'}">{waiting_orders_n}</div>
                <div class="maint-prep-note">Linked orders already opened</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.session_state["maint_day_todo_date_prefill"] = suggested_pack_date
        problem_watch_df = (
            watch_df[watch_df["Problem Now"].astype(str).str.strip().str.lower().eq("yes")].copy()
            if not watch_df.empty and "Problem Now" in watch_df.columns
            else pd.DataFrame()
        )
        waiting_watch_df = (
            watch_df[
                watch_df["Parts Risk"].astype(str).str.strip().eq("Mandatory part waiting on open order")
            ].copy()
            if not watch_df.empty and "Parts Risk" in watch_df.columns
            else pd.DataFrame()
        )

        if parts_risk_n == 0 and day_pack_missing_n == 0 and need_order_n == 0:
            st.success(
                f"The automatic flow is clear. {len(plan_view_df)} upcoming task(s) are already under control."
            )
        else:
            alert_bits = []
            if problem_now_n:
                alert_bits.append(f"{problem_now_n} task(s) have late mandatory-part ordering")
            if waiting_orders_n:
                alert_bits.append(f"{waiting_orders_n} task(s) are waiting on already-open mandatory orders")
            if problem_now_n:
                st.warning("Needs attention: " + " | ".join(alert_bits))
            elif waiting_orders_n:
                st.caption("Background follow-up: " + " | ".join(alert_bits))

        if problem_now_n > 0:
            with st.expander(f"Problems to solve ({problem_now_n})", expanded=True):
                if not problem_watch_df.empty:
                    show_watch_cols = [c for c in ["Status", "Component", "Task", "Task_ID", "Missing Parts", "Conditional Missing", "Needs Order", "Parts Risk"] if c in watch_df.columns]
                    st.dataframe(
                        problem_watch_df[show_watch_cols].sort_values(["Status", "Component", "Task"]),
                        use_container_width=True,
                        hide_index=True,
                        height=min(260, 80 + 34 * len(problem_watch_df)),
                    )
                order_now_df = problem_watch_df[problem_watch_df["Needs Order"].astype(str).str.strip().ne("")].copy() if not problem_watch_df.empty else pd.DataFrame()
                if not order_now_df.empty and st.button("🧾 Open missing parts orders now", key="maint_parts_watch_create_orders", use_container_width=True):
                    if os.path.exists(P.parts_orders_csv):
                        try:
                            odf_live = _read_csv_keepna(P.parts_orders_csv)
                        except Exception:
                            odf_live = pd.DataFrame()
                    else:
                        odf_live = pd.DataFrame()
                    created = 0
                    for _, r in order_now_df.iterrows():
                        task_name = safe_str(r.get("Task", ""))
                        task_id = safe_str(r.get("Task_ID", ""))
                        component = safe_str(r.get("Component", ""))
                        for part_name in _split_required_parts(r.get("Needs Order", "")):
                            if _maintenance_active_order_mask(
                                odf_live,
                                part_name=part_name,
                                maintenance_task_id=task_id,
                                wait_id="",
                            ).any():
                                continue
                            details = (
                                f"Procurement watch: {component} — {task_name} "
                                f"(Task ID: {task_id}). Missing ahead of planned maintenance."
                            )
                            _append_parts_order_from_maintenance(
                                part_name=part_name,
                                details=details,
                                actor=actor,
                                project_name="Maintenance",
                                company="",
                                maintenance_component=component,
                                maintenance_task=task_name,
                                maintenance_task_id=task_id,
                                wait_id="",
                            )
                            created += 1
                    if created > 0:
                        st.success(f"Created {created} parts order(s) from the automatic watch list.")
                        st.rerun()
                    else:
                        st.info("No new watch-list orders were needed.")

        # ---- Parts readiness check (tool-aware: tools can be mounted and stay non-consumable)
        inv_qty = {}
        inv_mounted_qty = {}
        inv_tool_map = {}
        inv_effective_qty = {}
        try:
            inv_df = load_inventory_cached(P.parts_inventory_csv)
            if not inv_df.empty:
                inv_df["Part Name"] = inv_df["Part Name"].astype(str).str.strip().str.lower()
                inv_df["Item Type"] = inv_df.get("Item Type", "").astype(str).str.strip().str.lower()
                inv_df["Location"] = inv_df.get("Location", "").astype(str).str.strip().str.lower()
                inv_df["Quantity"] = pd.to_numeric(inv_df.get("Quantity", 0), errors="coerce").fillna(0.0)
                stock_df = inv_df[inv_df["Location"].ne("mounted")].copy()
                inv_qty = stock_df.groupby("Part Name")["Quantity"].sum().to_dict()
                mounted_df = inv_df[inv_df["Location"].eq("mounted")].copy()
                inv_mounted_qty = mounted_df.groupby("Part Name")["Quantity"].sum().to_dict()
                inv_tool_map = (
                    inv_df.groupby("Part Name")
                    .apply(
                        lambda g: bool(
                            g["Item Type"].astype(str).str.strip().str.lower().eq("tool").any()
                            or is_tool_like_part_name(g.name)
                        )
                    )
                    .to_dict()
                )
                all_parts = set(inv_qty.keys()) | set(inv_mounted_qty.keys()) | set(inv_tool_map.keys())
                for pn in all_parts:
                    stock_q = float(inv_qty.get(pn, 0.0))
                    mounted_q = float(inv_mounted_qty.get(pn, 0.0))
                    inv_effective_qty[pn] = stock_q + mounted_q if bool(inv_tool_map.get(pn, False)) else stock_q
        except Exception:
            inv_effective_qty = {}

        def _parts_status(row):
            req = _parse_parts(row.get("Required_Parts", ""))
            if not req:
                return ("No parts defined", True, "")
            missing = []
            for p in req:
                if float(inv_effective_qty.get(p.lower(), 0.0)) <= 0:
                    missing.append(p)
            if missing:
                return ("Missing", False, ", ".join(missing))
            return ("Ready", True, "")

        parts_eval = cand.apply(_parts_status, axis=1)
        cand["Parts Status"] = [x[0] for x in parts_eval]
        cand["Parts Ready"] = [x[1] for x in parts_eval]
        cand["Missing Parts"] = [x[2] for x in parts_eval]

        comp_priority_norm = [safe_str(v).strip().lower() for v in component_priority if safe_str(v).strip()]
        comp_priority_rank = {name: idx for idx, name in enumerate(comp_priority_norm)}

        def _urgency_score(row):
            score = 0.0
            status = str(row.get("Status", "")).upper()
            mode = str(row.get("Tracking_Mode_norm", "")).lower()
            if status == "OVERDUE":
                score += 100.0
            elif status == "DUE SOON":
                score += 50.0

            if mode == "calendar":
                nd = row.get("Next_Due_Date", None)
                if nd is not None and not pd.isna(nd):
                    try:
                        dd = (pd.Timestamp(current_date) - pd.Timestamp(nd)).days
                        score += max(0.0, float(dd))
                    except Exception:
                        pass
            elif mode == "hours":
                nh = row.get("Next_Due_Hours", None)
                cur = float(row.get("Current_Hours_For_Task", 0.0) or 0.0)
                try:
                    if nh is not None and not pd.isna(nh):
                        score += max(0.0, cur - float(nh))
                except Exception:
                    pass
            elif mode == "draws":
                nd = row.get("Next_Due_Draw", None)
                try:
                    if nd is not None and not pd.isna(nd):
                        score += max(0.0, float(current_draw_count) - float(nd))
                except Exception:
                    pass
            return score

        def _component_rank(row):
            comp_key = safe_str(row.get("Component", "")).strip().lower()
            return int(comp_priority_rank.get(comp_key, 999))

        cand["_urgency"] = cand.apply(_urgency_score, axis=1)
        cand["_component_rank"] = cand.apply(_component_rank, axis=1)
        if planning_strategy == "Component priority first":
            cand = cand.sort_values(
                ["_component_rank", "_urgency", "Component", "Task"],
                ascending=[True, False, True, True],
            ).reset_index(drop=True)
        elif planning_strategy == "Group same component work":
            cand = cand.sort_values(
                ["_component_rank", "Component", "_urgency", "Task"],
                ascending=[True, True, False, True],
            ).reset_index(drop=True)
        elif planning_strategy == "Balanced urgency + component priority":
            cand["_balanced_score"] = cand["_urgency"] - (cand["_component_rank"].clip(upper=50) * 3.0)
            cand = cand.sort_values(
                ["_balanced_score", "_urgency", "Component", "Task"],
                ascending=[False, False, True, True],
            ).reset_index(drop=True)
        else:
            cand = cand.sort_values(["_urgency", "Component", "Task"], ascending=[False, True, True]).reset_index(drop=True)

        max_tasks = int(st.session_state.get("maint_sched_max_tasks", min(12, len(cand))))
        cand = cand.head(int(max_tasks)).copy()

        # ---- Read schedule and build busy intervals
        sched_path = P.schedule_csv
        if os.path.exists(sched_path):
            try:
                sched_df = _read_csv_keepna(sched_path)
            except Exception:
                sched_df = pd.DataFrame()
        else:
            sched_df = pd.DataFrame()

        for col in ["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]:
            if col not in sched_df.columns:
                sched_df[col] = ""

        start_window = pd.Timestamp(current_date)
        end_window = start_window + pd.Timedelta(days=int(horizon_days))
        sched_df["_start"] = pd.to_datetime(sched_df["Start DateTime"], errors="coerce")
        sched_df["_end"] = pd.to_datetime(sched_df["End DateTime"], errors="coerce")

        busy = []
        for _, r in sched_df.iterrows():
            s = r.get("_start")
            e = r.get("_end")
            if pd.isna(s) or pd.isna(e):
                continue
            if e < start_window or s > end_window:
                continue
            busy.append((pd.Timestamp(s), pd.Timestamp(e)))

        def _overlaps(a0, a1, b0, b1):
            return (a0 < b1) and (a1 > b0)

        # ---- Build free slots
        slots = []
        slot_delta = pd.Timedelta(minutes=int(schedule_grid_min))
        d = start_window.normalize()
        while d < end_window:
            # Friday/Saturday are non-working days.
            if d.weekday() in (4, 5):
                d = d + pd.Timedelta(days=1)
                continue
            day_s = d + pd.Timedelta(hours=int(day_start_h))
            day_e = d + pd.Timedelta(hours=int(day_end_h))
            t = day_s
            while t + slot_delta <= day_e:
                t2 = t + slot_delta
                conflict = any(_overlaps(t, t2, b0, b1) for b0, b1 in busy)
                if not conflict:
                    # Priority: preferred selected days first, then other working days.
                    # weekday(): Monday=0 ... Thursday=3, Sunday=6.
                    if d.weekday() in preferred_idx:
                        # keep user-selected preferred day order
                        pref_rank = preferred_idx.index(d.weekday())
                        slots.append((0, pref_rank, t, t2))
                    else:
                        slots.append((1, 999, t, t2))
                t = t + slot_delta
            d = d + pd.Timedelta(days=1)

        if not slots:
            st.warning("No free slots found in selected horizon/day window.")
            return

        slots.sort(key=lambda x: (x[0], x[1], x[2]))

        def _build_plan_df(slot_rows):
            plan_rows = []
            scheduled = []
            for _, task in cand.iterrows():
                est = pd.to_numeric(task.get("Est_Duration_Min", np.nan), errors="coerce")
                if pd.isna(est) or float(est) <= 0:
                    est = 60.0
                slot = max(1, int(schedule_grid_min))
                duration_min = max(slot, int(math.ceil(float(est) / float(slot)) * slot))
                duration_td = pd.Timedelta(minutes=int(duration_min))
                chosen = None
                for pref_class, pref_rank, s, _ in slot_rows:
                    e = s + duration_td
                    day_end = s.normalize() + pd.Timedelta(hours=int(day_end_h))
                    if e > day_end:
                        continue
                    if any(_overlaps(s, e, b0, b1) for b0, b1 in busy):
                        continue
                    if any(_overlaps(s, e, x0, x1) for x0, x1 in scheduled):
                        continue
                    chosen = (pref_class, pref_rank, s, e)
                    scheduled.append((s, e))
                    break
                if chosen is None:
                    continue
                pref_class, pref_rank, s, e = chosen
                comp = safe_str(task.get("Component", "")).strip()
                tname = safe_str(task.get("Task", "")).strip()
                tid = safe_str(task.get("Task_ID", "")).strip()
                status = safe_str(task.get("Status", "")).strip()
                mode = safe_str(task.get("Tracking_Mode", "")).strip()
                hs = safe_str(task.get("Hours_Source", "")).strip()
                desc = f"[AUTO-MAINT] {comp} - {tname} (ID:{tid}) | status={status} | mode={mode} | source={hs or 'FURNACE'}"
                plan_rows.append(
                    {
                        "Event Type": "Maintenance",
                        "Start DateTime": s.strftime("%Y-%m-%d %H:%M:%S"),
                        "End DateTime": e.strftime("%Y-%m-%d %H:%M:%S"),
                        "Description": desc,
                        "Recurrence": "",
                        "Component": comp,
                        "Task": tname,
                        "Task_ID": tid,
                        "Status": status,
                        "Urgency": float(task.get("_urgency", 0.0)),
                        "Task_Group": safe_str(task.get("Task_Group", "")),
                        "Duration_Min": int(duration_min),
                        "Required_Parts": ", ".join(_task_mandatory_parts(task)),
                        "Conditional_Parts": ", ".join(_task_conditional_parts(task)),
                        "Preparation_Lead_Days": _task_preparation_lead_days(task),
                        "Parts_Check_Lead_Days": _task_parts_check_lead_days(task),
                        "Parts Status": safe_str(task.get("Parts Status", "")),
                        "Missing Parts": safe_str(task.get("Missing Parts", "")),
                        "_pref_class": int(pref_class),
                        "_pref_rank": int(pref_rank),
                    }
                )
            return pd.DataFrame(plan_rows)

        def _plan_score(df_plan):
            if df_plan is None or df_plan.empty:
                return 1e9
            dfx = df_plan.copy()
            dfx["_st"] = pd.to_datetime(dfx["Start DateTime"], errors="coerce")
            day_counts = dfx["_st"].dt.date.value_counts().to_dict()
            # Lower is better.
            pref_penalty = float(dfx["_pref_class"].sum() * 10 + dfx["_pref_rank"].sum())
            spread_penalty = float(sum(max(0, int(v) - 1) for v in day_counts.values()) * 6)
            component_day_penalty = 0.0
            if "Component" in dfx.columns:
                component_day_counts = dfx.groupby([dfx["_st"].dt.date, "Component"]).size().to_dict()
                if planning_strategy == "Group same component work":
                    component_day_penalty = float(
                        -2.0 * sum(max(0, int(v) - 1) for v in component_day_counts.values())
                    )
                elif planning_strategy == "Balanced urgency + component priority":
                    component_day_penalty = float(
                        -1.0 * sum(max(0, int(v) - 1) for v in component_day_counts.values())
                    )
            urgency_credit = float(pd.to_numeric(dfx.get("Urgency", 0), errors="coerce").fillna(0.0).sum() * 0.01)
            priority_penalty = 0.0
            if "Component" in dfx.columns and comp_priority_rank:
                ranks = dfx["Component"].astype(str).str.strip().str.lower().map(lambda x: comp_priority_rank.get(x, 999))
                priority_penalty = float(pd.to_numeric(ranks, errors="coerce").fillna(999).sum() * 0.02)
                if planning_strategy == "Component priority first":
                    priority_penalty *= 2.5
                elif planning_strategy == "Balanced urgency + component priority":
                    priority_penalty *= 1.25
                else:
                    priority_penalty *= 0.5
            return pref_penalty + spread_penalty + priority_penalty + component_day_penalty - urgency_credit

        # Candidate plan variants (ranked).
        plan_variants = []
        for offset in range(min(8, max(1, len(slots)))):
            slot_variant = slots[offset:] + slots[:offset]
            pdf = _build_plan_df(slot_variant)
            if pdf.empty:
                continue
            starts_sig = tuple(pdf["Start DateTime"].astype(str).tolist())
            plan_variants.append(
                {
                    "name": f"Option {chr(65 + offset)}",
                    "score": _plan_score(pdf),
                    "plan_df": pdf,
                    "sig": starts_sig,
                }
            )

        # Dedupe and keep top 3.
        uniq = {}
        for p in plan_variants:
            sig = p["sig"]
            if sig not in uniq or p["score"] < uniq[sig]["score"]:
                uniq[sig] = p
        ranked = sorted(list(uniq.values()), key=lambda x: x["score"])[:3]
        if not ranked:
            st.warning("Could not build schedule options for this queue.")
            return

        plan_df = ranked[0]["plan_df"].copy()

        planning_details_label = "Schedule now"
        planning_details_help = f"Rules first: the planner uses the current task state and preferred workday order: {', '.join(preferred_days)}."
        with st.expander(planning_details_label, expanded=False):
            st.caption(planning_details_help)
            st.markdown("**What is next now**")
            st.caption("This is the current maintenance queue before you change any scheduling rules.")
            coming_df = cand.copy()
            if "Tracking_Mode_norm" not in coming_df.columns:
                coming_df["Tracking_Mode_norm"] = coming_df.get("Tracking_Mode", "")
            coming_df["Next by date"] = pd.to_datetime(coming_df.get("Next_Due_Date"), errors="coerce").dt.strftime("%Y-%m-%d")
            coming_df["Next by date"] = coming_df["Next by date"].fillna("")
            coming_df["Next by hours"] = pd.to_numeric(coming_df.get("Next_Due_Hours"), errors="coerce").round(1)
            coming_df["Next by draws"] = pd.to_numeric(coming_df.get("Next_Due_Draw"), errors="coerce").round(1)
            coming_view_cols = [c for c in ["Status", "Component", "Task", "Tracking_Mode_norm", "Next by date", "Next by hours", "Next by draws"] if c in coming_df.columns]
            st.dataframe(
                coming_df[coming_view_cols].head(12),
                use_container_width=True,
                hide_index=True,
                height=260,
            )
            try:
                import plotly.graph_objects as go

                coming_plot_df = coming_df.copy()
                coming_plot_df["Task Label"] = (
                    coming_plot_df["Component"].astype(str).str.strip()
                    + " - "
                    + coming_plot_df["Task"].astype(str).str.strip()
                )

                def _norm_hours_group(v: str) -> str:
                    s = safe_str(v).strip().upper()
                    if s in {"UV1", "UV 1", "SYSTEM1"}:
                        return "UV1"
                    if s in {"UV2", "UV 2", "SYSTEM2"}:
                        return "UV2"
                    return "FURNACE"

                def _status_color(s):
                    s = safe_str(s).strip().upper()
                    if s == "OVERDUE":
                        return "#ff5a5f"
                    if s == "DUE SOON":
                        return "#ffb347"
                    return "#69d2e7"

                def _roadmap(x0, x1, title, xlabel, df_plot, xcol, hover_col):
                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=[x0, x1],
                            y=[0, 0],
                            mode="lines",
                            line=dict(width=8, color="rgba(120,170,220,0.18)"),
                            hoverinfo="skip",
                            showlegend=False,
                        )
                    )
                    fig.add_vline(x=x0, line_dash="dash", line_color="rgba(255,255,255,0.35)")
                    if df_plot is not None and not df_plot.empty:
                        fig.add_trace(
                            go.Scatter(
                                x=df_plot[xcol],
                                y=[0] * len(df_plot),
                                mode="markers",
                                marker=dict(
                                    size=14,
                                    color=[_status_color(v) for v in df_plot["Status"]],
                                    line=dict(width=1, color="rgba(255,255,255,0.65)"),
                                ),
                                text=df_plot[hover_col],
                                hovertemplate="%{text}<extra></extra>",
                                showlegend=False,
                            )
                        )
                    else:
                        mid = x0 + (x1 - x0) / 2
                        fig.add_annotation(x=mid, y=0, text="No tasks in view", showarrow=False)
                    fig.update_layout(
                        title=title,
                        height=210,
                        yaxis=dict(visible=False),
                        xaxis=dict(title=xlabel),
                        margin=dict(l=8, r=8, t=36, b=8),
                    )
                    return fig

                coming_plot_df["Hours Group"] = coming_plot_df.get("Hours_Source", "").apply(_norm_hours_group)
                coming_plot_df["Next Date TS"] = pd.to_datetime(coming_plot_df.get("Next_Due_Date"), errors="coerce")
                coming_plot_df["Next Hours"] = pd.to_numeric(coming_plot_df.get("Next_Due_Hours"), errors="coerce")
                coming_plot_df["Next Draws"] = pd.to_numeric(coming_plot_df.get("Next_Due_Draw"), errors="coerce")
                coming_plot_df["Hover"] = (
                    coming_plot_df["Task Label"].astype(str)
                    + "<br>Status: "
                    + coming_plot_df["Status"].astype(str)
                )

                st.markdown("**Visual timeline**")

                date_df = coming_plot_df[coming_plot_df["Next Date TS"].notna()].copy()
                d0 = pd.Timestamp(current_date)
                if not date_df.empty:
                    d1 = max(d0 + pd.Timedelta(days=14), date_df["Next Date TS"].max())
                else:
                    d1 = d0 + pd.Timedelta(days=14)

                dc1, dc2 = st.columns([1.2, 1.8])
                with dc1:
                    st.markdown(
                        f"""
                        <div class="maint-board-shell" style="padding:12px 14px; min-height: 120px;">
                          <div class="maint-board-title">Calendar tasks</div>
                          <div class="maint-prep-v maint-v-blue" style="font-size: 28px; margin-bottom: 6px;">{int(date_df.shape[0])}</div>
                          <div class="maint-prep-note">Tasks with due dates on the calendar timeline</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with dc2:
                    st.plotly_chart(
                        _roadmap(d0, d1, "Next by date", "Date", date_df, "Next Date TS", "Hover"),
                        use_container_width=True,
                    )

                hours_df = coming_plot_df[coming_plot_df["Next Hours"].notna()].copy()
                hc1, hc2, hc3 = st.columns(3)
                hour_groups = [
                    ("FURNACE", furnace_hours, hc1),
                    ("UV1", uv1_hours, hc2),
                    ("UV2", uv2_hours, hc3),
                ]
                for group_name, current_h, col in hour_groups:
                    group_df = hours_df[hours_df["Hours Group"].eq(group_name)].copy()
                    x0 = float(current_h)
                    x1 = max(x0 + 100.0, float(group_df["Next Hours"].max())) if not group_df.empty else x0 + 100.0
                    with col:
                        st.markdown(
                            f"""
                            <div class="maint-board-shell" style="padding:10px 12px; min-height: 100px; margin-bottom: 8px;">
                              <div class="maint-board-title">{group_name}</div>
                              <div class="maint-prep-v maint-v-blue" style="font-size: 24px; margin-bottom: 4px;">{int(group_df.shape[0])}</div>
                              <div class="maint-prep-note">Upcoming hours-based tasks in this source</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.plotly_chart(
                            _roadmap(x0, x1, group_name, "Hours", group_df, "Next Hours", "Hover"),
                            use_container_width=True,
                        )

                draws_df = coming_plot_df[coming_plot_df["Next Draws"].notna()].copy()
                x0_draw = float(current_draw_count)
                x1_draw = max(x0_draw + 20.0, float(draws_df["Next Draws"].max())) if not draws_df.empty else x0_draw + 20.0
                st.markdown(
                    f"""
                    <div class="maint-board-shell" style="padding:10px 12px; min-height: 100px; margin-bottom: 8px;">
                      <div class="maint-board-title">Draw tasks</div>
                      <div class="maint-prep-v maint-v-blue" style="font-size: 24px; margin-bottom: 4px;">{int(draws_df.shape[0])}</div>
                      <div class="maint-prep-note">Upcoming draw-based tasks on the timeline</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.plotly_chart(
                    _roadmap(x0_draw, x1_draw, "Next by draws", "Draw count", draws_df, "Next Draws", "Hover"),
                    use_container_width=True,
                )
            except Exception:
                pass

            st.markdown("**Schedule rules**")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                st.number_input("Plan horizon (days)", min_value=3, max_value=90, value=int(st.session_state.get("maint_sched_horizon_days", 14)), step=1, key="maint_sched_horizon_days")
            with c2:
                st.number_input("Day start (hour)", min_value=0, max_value=23, value=int(st.session_state.get("maint_sched_day_start", 8)), step=1, key="maint_sched_day_start")
            with c3:
                st.number_input("Day end (hour)", min_value=1, max_value=23, value=int(st.session_state.get("maint_sched_day_end", 18)), step=1, key="maint_sched_day_end")
            st.caption("Task duration comes from Builder. The scheduler places tasks on an internal 15-minute planning grid.")

            st.caption("Choose which tasks enter the scheduling queue. You can combine status and timing windows together.")
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                st.checkbox("Include OVERDUE", value=bool(st.session_state.get("maint_sched_include_overdue", True)), key="maint_sched_include_overdue")
            with s2:
                st.checkbox("Include DUE SOON", value=bool(st.session_state.get("maint_sched_include_due_soon", True)), key="maint_sched_include_due_soon")
            with s3:
                st.checkbox("Include ROUTINE", value=bool(st.session_state.get("maint_sched_include_routine", False)), key="maint_sched_include_routine")
            with s4:
                st.checkbox("Include OK", value=bool(st.session_state.get("maint_sched_include_ok", False)), key="maint_sched_include_ok")

            st.markdown("**Bring in near-term tasks**")
            w1, w2, w3 = st.columns(3)
            with w1:
                st.checkbox("Calendar window", value=bool(st.session_state.get("maint_sched_use_days_window", True)), key="maint_sched_use_days_window")
                st.number_input("Days ahead", min_value=1, max_value=180, value=int(st.session_state.get("maint_sched_days_window", 7)), step=1, key="maint_sched_days_window")
            with w2:
                st.checkbox("Hours window", value=bool(st.session_state.get("maint_sched_use_hours_window", True)), key="maint_sched_use_hours_window")
                st.number_input("Hours ahead", min_value=1.0, max_value=5000.0, value=float(st.session_state.get("maint_sched_hours_window", 10.0)), step=1.0, key="maint_sched_hours_window")
            with w3:
                st.checkbox("Draw window", value=bool(st.session_state.get("maint_sched_use_draws_window", True)), key="maint_sched_use_draws_window")
                st.number_input("Draws ahead", min_value=1, max_value=500, value=int(st.session_state.get("maint_sched_draws_window", 5)), step=1, key="maint_sched_draws_window")

            f1, f2 = st.columns(2)
            with f1:
                st.multiselect(
                    "Focus components (optional)",
                    options=component_options,
                    default=st.session_state.get("maint_sched_component_focus", []),
                    key="maint_sched_component_focus",
                    help="Leave empty to allow all components.",
                )
            with f2:
                st.multiselect(
                    "Focus task groups (optional)",
                    options=group_options,
                    default=st.session_state.get("maint_sched_task_groups_focus", []),
                    key="maint_sched_task_groups_focus",
                    help="Leave empty to allow all task groups.",
                )

            strat1, strat2 = st.columns([1.2, 1.8])
            strategy_options = [
                "Urgency first",
                "Balanced urgency + component priority",
                "Component priority first",
                "Group same component work",
            ]
            strategy_value = st.session_state.get("maint_sched_strategy", "Urgency first")
            strategy_index = strategy_options.index(strategy_value) if strategy_value in strategy_options else 0
            with strat1:
                st.selectbox(
                    "Planning strategy",
                    strategy_options,
                    index=strategy_index,
                    key="maint_sched_strategy",
                    help="Choose whether the scheduler should focus mostly on timing urgency, component priority, or grouping related work.",
                )
            with strat2:
                st.multiselect(
                    "Component priority order",
                    options=component_options,
                    default=st.session_state.get("maint_sched_component_priority", []),
                    key="maint_sched_component_priority",
                    help="Selected components are preferred first, in the order you choose them.",
                )

            weekday_options = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
            preferred_default = st.session_state.get("maint_sched_preferred_days", ["Thursday"])
            st.multiselect(
                "Preferred maintenance day(s)",
                options=weekday_options,
                default=preferred_default,
                key="maint_sched_preferred_days",
                help="Planner prefers these days first, then other working days.",
            )
            cpc1, cpc2 = st.columns([1, 1])
            with cpc1:
                st.checkbox(
                    "Auto add Parts Check events",
                    value=bool(st.session_state.get("maint_sched_add_parts_check", True)),
                    key="maint_sched_add_parts_check",
                    help="Create a pre-maintenance event to verify required parts in inventory.",
                )
            with cpc2:
                st.number_input(
                    "Fallback parts-check days before",
                    min_value=1,
                    max_value=30,
                    value=int(st.session_state.get("maint_sched_parts_check_days_before", 7)),
                    step=1,
                    key="maint_sched_parts_check_days_before",
                )

            st.markdown("**Automatic schedule result**")
            selected_status_bits = []
            if st.session_state.get("maint_sched_include_overdue", True):
                selected_status_bits.append("OVERDUE")
            if st.session_state.get("maint_sched_include_due_soon", True):
                selected_status_bits.append("DUE SOON")
            if st.session_state.get("maint_sched_include_routine", False):
                selected_status_bits.append("ROUTINE")
            if st.session_state.get("maint_sched_include_ok", False):
                selected_status_bits.append("OK")
            selected_window_bits = []
            if st.session_state.get("maint_sched_use_days_window", True):
                selected_window_bits.append(f"{int(st.session_state.get('maint_sched_days_window', 7))} days")
            if st.session_state.get("maint_sched_use_hours_window", True):
                selected_window_bits.append(f"{float(st.session_state.get('maint_sched_hours_window', 10.0)):.0f} hours")
            if st.session_state.get("maint_sched_use_draws_window", True):
                selected_window_bits.append(f"{int(st.session_state.get('maint_sched_draws_window', 5))} draws")
            queue_rule_text = ", ".join(selected_status_bits) if selected_status_bits else "No status scope selected"
            if selected_window_bits:
                queue_rule_text += " | timing windows: " + ", ".join(selected_window_bits)
            priority_rule_text = "No component priority set"
            if component_priority:
                priority_rule_text = " -> ".join(component_priority[:5]) + (" -> ..." if len(component_priority) > 5 else "")
            st.caption(f"Window: {queue_rule_text} | Strategy: {planning_strategy} | Component priority: {priority_rule_text}")

            opt_labels = [
                f"{p['name']} • score {p['score']:.1f} • tasks {len(p['plan_df'])}"
                for p in ranked
            ]
            pick_idx = st.selectbox("Select option", options=list(range(len(opt_labels))), format_func=lambda i: opt_labels[int(i)], key="maint_sched_option_pick")
            plan_df = ranked[int(pick_idx)]["plan_df"].copy()
            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            try:
                p_ts = pd.to_datetime(plan_df["Start DateTime"], errors="coerce")
                valid_ts = p_ts.dropna()
                days_used = int(valid_ts.dt.date.nunique()) if not valid_ts.empty else 0
                earliest = valid_ts.min().strftime("%Y-%m-%d %H:%M") if not valid_ts.empty else "-"
                latest = valid_ts.max().strftime("%Y-%m-%d %H:%M") if not valid_ts.empty else "-"
            except Exception:
                days_used, earliest, latest = 0, "-", "-"
            om1, om2, om3, om4 = st.columns(4)
            om1.metric("Option Score", f"{ranked[int(pick_idx)]['score']:.1f}")
            om2.metric("Tasks Planned", int(len(plan_df)))
            om3.metric("Days Used", days_used)
            om4.metric("Window", f"{earliest} → {latest}")

            if not plan_df.empty:
                try:
                    import plotly.express as px

                    vis = plan_df.copy()
                    vis["start_ts"] = pd.to_datetime(vis["Start DateTime"], errors="coerce")
                    vis["end_ts"] = pd.to_datetime(vis["End DateTime"], errors="coerce")
                    vis["Task Label"] = vis["Component"].astype(str) + " - " + vis["Task"].astype(str)
                    vis = vis.dropna(subset=["start_ts", "end_ts"]).copy()

                    if not vis.empty:
                        fig = px.timeline(
                            vis,
                            x_start="start_ts",
                            x_end="end_ts",
                            y="Task Label",
                            color="Status",
                            hover_data=["Task_ID", "Urgency", "Start DateTime", "End DateTime"],
                            title="Suggested Maintenance Timeline",
                        )
                        fig.update_yaxes(autorange="reversed")
                        fig.update_layout(height=360, margin=dict(l=8, r=8, t=42, b=8))
                        st.plotly_chart(fig, use_container_width=True)
                except Exception:
                    pass

            st.dataframe(plan_df.drop(columns=[c for c in ["_pref_class", "_pref_rank"] if c in plan_df.columns]), use_container_width=True, hide_index=True, height=280)
            st.caption(f"Current state used: draw_count={current_draw_count}, furnace={furnace_hours:.1f}, uv1={uv1_hours:.1f}, uv2={uv2_hours:.1f}")

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            apply_schedule_inside = st.button(
                "💾 Apply automatic schedule",
                key="maint_sched_apply_btn",
                type="primary",
                use_container_width=True,
            )

        if apply_schedule_inside:
            if plan_df.empty:
                st.info("No suggestions to save.")
                return

            to_save = plan_df[["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]].copy()
            if add_parts_check_event:
                check_rows = []
                for _, rr in plan_df.iterrows():
                    st_ts = pd.to_datetime(rr.get("Start DateTime", ""), errors="coerce")
                    en_ts = pd.to_datetime(rr.get("End DateTime", ""), errors="coerce")
                    if pd.isna(st_ts) or pd.isna(en_ts):
                        continue
                    dur = en_ts - st_ts
                    req_parts = safe_str(rr.get("Required_Parts", "")).strip()
                    cond_parts = safe_str(rr.get("Conditional_Parts", "")).strip()
                    if req_parts:
                        row_parts_check_days = pd.to_numeric(rr.get("Parts_Check_Lead_Days", parts_check_days_before), errors="coerce")
                        chk_days = int(row_parts_check_days) if pd.notna(row_parts_check_days) else int(parts_check_days_before)
                        chk_start = st_ts - pd.Timedelta(days=max(0, chk_days))
                        chk_end = chk_start + dur
                        check_rows.append({
                            "Event Type": "Maintenance Parts Check",
                            "Start DateTime": chk_start.strftime("%Y-%m-%d %H:%M:%S"),
                            "End DateTime": chk_end.strftime("%Y-%m-%d %H:%M:%S"),
                            "Description": (
                                f"[AUTO-PARTS-CHECK] {safe_str(rr.get('Component',''))} - {safe_str(rr.get('Task',''))} "
                                f"(ID:{safe_str(rr.get('Task_ID',''))}) | mandatory={req_parts}"
                            ),
                            "Recurrence": "",
                        })
                    row_prep_days = pd.to_numeric(rr.get("Preparation_Lead_Days", 7), errors="coerce")
                    prep_days = int(row_prep_days) if pd.notna(row_prep_days) else 7
                    prep_start = st_ts - pd.Timedelta(days=max(0, prep_days))
                    prep_end = prep_start + dur
                    check_rows.append({
                        "Event Type": "Maintenance Preparation",
                        "Start DateTime": prep_start.strftime("%Y-%m-%d %H:%M:%S"),
                        "End DateTime": prep_end.strftime("%Y-%m-%d %H:%M:%S"),
                        "Description": (
                            f"[AUTO-PREP] {safe_str(rr.get('Component',''))} - {safe_str(rr.get('Task',''))} "
                            f"(ID:{safe_str(rr.get('Task_ID',''))})"
                            + (f" | mandatory={req_parts}" if req_parts else "")
                            + (f" | conditional={cond_parts}" if cond_parts else "")
                        ),
                        "Recurrence": "",
                    })
                if check_rows:
                    to_save = pd.concat([to_save, pd.DataFrame(check_rows)], ignore_index=True)

            existing_keys = set(
                zip(
                    sched_df["Event Type"].astype(str),
                    sched_df["Start DateTime"].astype(str),
                    sched_df["End DateTime"].astype(str),
                    sched_df["Description"].astype(str),
                    sched_df["Recurrence"].astype(str),
                )
            )
            add_rows = []
            for _, r in to_save.iterrows():
                k = (
                    str(r["Event Type"]),
                    str(r["Start DateTime"]),
                    str(r["End DateTime"]),
                    str(r["Description"]),
                    str(r["Recurrence"]),
                )
                if k not in existing_keys:
                    add_rows.append(r)
                    existing_keys.add(k)

            if not add_rows:
                st.info("All suggested events already exist in schedule.")
                return

            out = pd.concat([sched_df[["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]], pd.DataFrame(add_rows)], ignore_index=True)
            out.to_csv(sched_path, index=False)
            st.success(f"Added {len(add_rows)} maintenance event(s) to schedule.")
            st.rerun()


    def render_maintenance_work_package_builder(tasks_df, actor, header_md="### 🧩 Maintenance Work Package"):
        st.markdown(header_md)
        st.markdown(
            """
            <div class="maint-help-green">
              <b>Build once per task, execute many times</b><br/>
              Define <b>Preparation</b>, <b>Safety</b>, <b>Procedure</b>, and draw-stop plan per task.<br/>
              You can also append task BOM parts directly from inventory.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if tasks_df is None or tasks_df.empty:
            st.info("No tasks found for work package builder.")
            return
        
        def _valid_task_text(v: str) -> bool:
            s = safe_str(v).strip()
            if not s:
                return False
            if s.lower() in {"-", "--", "nan", "none", "null", "(blank)"}:
                return False
            # require at least one letter/number so separators-only rows are ignored
            return any(ch.isalnum() for ch in s)

        pkg_file = os.path.join(MAINT_FOLDER, "maintenance_work_packages.csv")
        pkg_cols = [
            "Task_ID",
            "Component",
            "Task",
            "Task_Group",
            "Required_Parts",
            "Required_Tools",
            "Preparation_Checklist",
            "Safety_Protocol",
            "Safety_Fall_Risk",
            "Safety_TnM_Presence",
            "Procedure_Steps",
            "Procedure_Photos",
            "Draw_Stop_Plan",
            "Est_Stop_Min",
            "Completion_Criteria",
            "Last_Updated",
            "Updated_By",
        ]
        if os.path.exists(pkg_file):
            try:
                pkg_df = _read_csv_keepna(pkg_file)
            except Exception:
                pkg_df = pd.DataFrame(columns=pkg_cols)
        else:
            pkg_df = pd.DataFrame(columns=pkg_cols)
        for c in pkg_cols:
            if c not in pkg_df.columns:
                pkg_df[c] = ""

        def _pkg_exists_for_task(task_row: pd.Series) -> bool:
            tid_local = safe_str(task_row.get("Task_ID", "")).strip()
            comp_local = safe_str(task_row.get("Component", "")).strip().lower()
            task_local = safe_str(task_row.get("Task", "")).strip().lower()
            if pkg_df.empty:
                return False
            if tid_local:
                mask = pkg_df["Task_ID"].astype(str).str.strip().eq(tid_local)
                if mask.any():
                    return True
            mask = (
                pkg_df["Component"].astype(str).str.strip().str.lower().eq(comp_local)
                & pkg_df["Task"].astype(str).str.strip().str.lower().eq(task_local)
            )
            return bool(mask.any())

        task_opts = []
        task_map = {}
        for i, r in tasks_df.sort_values(["Status", "Component", "Task"]).iterrows():
            comp_v = safe_str(r.get("Component", "")).strip()
            task_v = safe_str(r.get("Task", "")).strip()
            if not (_valid_task_text(comp_v) and _valid_task_text(task_v)):
                continue
            tid = safe_str(r.get("Task_ID", "")).strip()
            pkg_state = "PKG SAVED" if _pkg_exists_for_task(r) else "NEEDS PKG"
            lbl = f"[{pkg_state}] [{safe_str(r.get('Status',''))}] {comp_v} - {task_v} (ID:{tid})"
            task_opts.append(lbl)
            task_map[lbl] = int(i)
        if not task_opts:
            st.info("No valid tasks to show in Work Package selector.")
            return
        st.caption("Choose list shows package progress: `PKG SAVED` means this task already has a saved work package.")
        pkg_pick = st.selectbox("Select maintenance task", options=[""] + task_opts, key="maint_pkg_task_pick")
        if not pkg_pick:
            return

        rr = tasks_df.loc[task_map[pkg_pick]]
        task_id = safe_str(rr.get("Task_ID", "")).strip()
        task_component = safe_str(rr.get("Component", "")).strip()
        task_name = safe_str(rr.get("Task", "")).strip()
        task_group = safe_str(rr.get("Task_Group", "")).strip()
        required_parts_txt = safe_str(rr.get("Required_Parts", "")).strip()

        def _parts_list(v):
            s = safe_str(v).strip()
            if not s:
                return []
            out = []
            for p in s.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
                pv = p.strip()
                if pv:
                    out.append(pv)
            uniq = []
            seen = set()
            for p in out:
                lk = p.lower()
                if lk not in seen:
                    uniq.append(p)
                    seen.add(lk)
            return uniq

        def _save_required_parts_for_task(new_required_parts: str):
            src = safe_str(rr.get("Source_File", "")).strip()
            if not src:
                st.error("Task has no Source_File, cannot update Required_Parts.")
                return False
            path = os.path.join(MAINT_FOLDER, src)
            if not os.path.exists(path):
                st.error(f"Source file missing: {path}")
                return False
            try:
                raw_src = read_file(path)
                df_src = normalize_df(raw_src)
                mask = pd.Series([False] * len(df_src), index=df_src.index)
                if "Task_ID" in df_src.columns and task_id:
                    mask = df_src["Task_ID"].astype(str).str.strip().eq(task_id)
                if not mask.any():
                    mask = (
                        df_src["Component"].astype(str).str.strip().eq(task_component)
                        & df_src["Task"].astype(str).str.strip().eq(task_name)
                    )
                if not mask.any():
                    st.error("Task row was not found in source file.")
                    return False
                if "Required_Parts" not in df_src.columns:
                    df_src["Required_Parts"] = ""
                if "Mandatory_Parts" not in df_src.columns:
                    df_src["Mandatory_Parts"] = ""
                df_src.loc[mask, "Required_Parts"] = safe_str(new_required_parts).strip()
                df_src.loc[mask, "Mandatory_Parts"] = safe_str(new_required_parts).strip()
                out_src = templateize_df(df_src, list(raw_src.columns))
                write_file(path, out_src)
                return True
            except Exception as e:
                st.error(f"Failed to update Required_Parts: {e}")
                return False

        def _save_automatic_flow_for_task(
            mandatory_parts_txt: str,
            conditional_parts_txt: str,
            prep_lead_days: int,
            parts_check_lead_days: int,
            auto_order_enabled: bool,
        ):
            src = safe_str(rr.get("Source_File", "")).strip()
            if not src:
                st.error("Task has no Source_File, cannot update automatic flow.")
                return False
            path = os.path.join(MAINT_FOLDER, src)
            if not os.path.exists(path):
                st.error(f"Source file missing: {path}")
                return False
            try:
                raw_src = read_file(path)
                df_src = normalize_df(raw_src)
                mask = pd.Series([False] * len(df_src), index=df_src.index)
                if "Task_ID" in df_src.columns and task_id:
                    mask = df_src["Task_ID"].astype(str).str.strip().eq(task_id)
                if not mask.any():
                    mask = (
                        df_src["Component"].astype(str).str.strip().eq(task_component)
                        & df_src["Task"].astype(str).str.strip().eq(task_name)
                    )
                if not mask.any():
                    st.error("Task row was not found in source file.")
                    return False
                for c in [
                    "Required_Parts",
                    "Mandatory_Parts",
                    "Conditional_Parts",
                    "Preparation_Lead_Days",
                    "Parts_Check_Lead_Days",
                    "Auto_Order_Mandatory_Parts",
                ]:
                    if c not in df_src.columns:
                        df_src[c] = ""
                mand_txt = safe_str(mandatory_parts_txt).strip()
                cond_txt = safe_str(conditional_parts_txt).strip()
                df_src.loc[mask, "Required_Parts"] = mand_txt
                df_src.loc[mask, "Mandatory_Parts"] = mand_txt
                df_src.loc[mask, "Conditional_Parts"] = cond_txt
                df_src.loc[mask, "Preparation_Lead_Days"] = int(max(0, int(prep_lead_days)))
                df_src.loc[mask, "Parts_Check_Lead_Days"] = int(max(0, int(parts_check_lead_days)))
                df_src.loc[mask, "Auto_Order_Mandatory_Parts"] = "Yes" if auto_order_enabled else "No"
                out_src = templateize_df(df_src, list(raw_src.columns))
                write_file(path, out_src)
                return True
            except Exception as e:
                st.error(f"Failed to update automatic flow: {e}")
                return False

        def _save_est_duration_for_task(new_est_duration_min: float):
            src = safe_str(rr.get("Source_File", "")).strip()
            if not src:
                return False
            path = os.path.join(MAINT_FOLDER, src)
            if not os.path.exists(path):
                return False
            try:
                raw_src = read_file(path)
                df_src = normalize_df(raw_src)
                mask = pd.Series([False] * len(df_src), index=df_src.index)
                if "Task_ID" in df_src.columns and task_id:
                    mask = df_src["Task_ID"].astype(str).str.strip().eq(task_id)
                if not mask.any():
                    mask = (
                        df_src["Component"].astype(str).str.strip().eq(task_component)
                        & df_src["Task"].astype(str).str.strip().eq(task_name)
                    )
                if not mask.any():
                    return False
                if "Est_Duration_Min" not in df_src.columns:
                    df_src["Est_Duration_Min"] = ""
                df_src.loc[mask, "Est_Duration_Min"] = float(max(0.0, float(new_est_duration_min)))
                out_src = templateize_df(df_src, list(raw_src.columns))
                write_file(path, out_src)
                return True
            except Exception:
                return False

        def _save_required_tools_for_task(new_required_tools: str):
            nonlocal pkg_df
            try:
                now_ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                row_data = {
                    "Task_ID": task_id,
                    "Component": task_component,
                    "Task": task_name,
                    "Task_Group": task_group,
                    "Required_Parts": safe_str(rr.get("Required_Parts", "")).strip(),
                    "Required_Tools": safe_str(new_required_tools).strip(),
                    "Preparation_Checklist": safe_str(pkg_row.get("Preparation_Checklist", "")).strip() if has_pkg else "",
                    "Safety_Protocol": safe_str(pkg_row.get("Safety_Protocol", "")).strip() if has_pkg else "",
                    "Safety_Fall_Risk": safe_str(pkg_row.get("Safety_Fall_Risk", "")).strip() if has_pkg else "",
                    "Safety_TnM_Presence": safe_str(pkg_row.get("Safety_TnM_Presence", "")).strip() if has_pkg else "",
                    "Procedure_Steps": safe_str(pkg_row.get("Procedure_Steps", "")).strip() if has_pkg else "",
                    "Procedure_Photos": safe_str(pkg_row.get("Procedure_Photos", "")).strip() if has_pkg else "",
                    "Draw_Stop_Plan": safe_str(pkg_row.get("Draw_Stop_Plan", "")).strip() if has_pkg else "",
                    "Est_Stop_Min": pd.to_numeric(pkg_row.get("Est_Stop_Min", 0), errors="coerce") if has_pkg else 0,
                    "Completion_Criteria": safe_str(pkg_row.get("Completion_Criteria", "")).strip() if has_pkg else "",
                    "Last_Updated": now_ts,
                    "Updated_By": safe_str(actor).strip(),
                }
                if task_id and (pkg_df["Task_ID"].astype(str).str.strip() == task_id).any():
                    idx = pkg_df[pkg_df["Task_ID"].astype(str).str.strip() == task_id].index[0]
                    for k, v in row_data.items():
                        pkg_df.at[idx, k] = v
                else:
                    pkg_df = pd.concat([pkg_df, pd.DataFrame([row_data])], ignore_index=True)
                pkg_df.to_csv(pkg_file, index=False)
                return True
            except Exception as e:
                st.error(f"Failed to update Required_Tools: {e}")
                return False

        def _save_task_groups_for_task(new_groups_txt: str):
            src = safe_str(rr.get("Source_File", "")).strip()
            if not src:
                st.error("Task has no Source_File, cannot update groups.")
                return False
            path = os.path.join(MAINT_FOLDER, src)
            if not os.path.exists(path):
                st.error(f"Source file missing: {path}")
                return False
            try:
                raw_src = read_file(path)
                df_src = normalize_df(raw_src)
                mask = pd.Series([False] * len(df_src), index=df_src.index)
                if "Task_ID" in df_src.columns and task_id:
                    mask = df_src["Task_ID"].astype(str).str.strip().eq(task_id)
                if not mask.any():
                    mask = (
                        df_src["Component"].astype(str).str.strip().eq(task_component)
                        & df_src["Task"].astype(str).str.strip().eq(task_name)
                    )
                if not mask.any():
                    st.error("Task row was not found in source file.")
                    return False
                if "Task_Groups" not in df_src.columns:
                    df_src["Task_Groups"] = ""
                if "Task_Group" not in df_src.columns:
                    df_src["Task_Group"] = ""
                # Keep both fields synchronized for backward compatibility.
                df_src.loc[mask, "Task_Groups"] = safe_str(new_groups_txt).strip()
                df_src.loc[mask, "Task_Group"] = safe_str(new_groups_txt).strip()
                out_src = templateize_df(df_src, list(raw_src.columns))
                write_file(path, out_src)
                return True
            except Exception as e:
                st.error(f"Failed to update task groups: {e}")
                return False

        def _save_timing_for_task(
            trigger_modes: list,
            hours_sources: list,
            hours_interval: float,
            draws_interval: int,
            cal_value: int,
            cal_unit: str,
        ):
            src = safe_str(rr.get("Source_File", "")).strip()
            if not src:
                st.error("Task has no Source_File, cannot update timing.")
                return False
            path = os.path.join(MAINT_FOLDER, src)
            if not os.path.exists(path):
                st.error(f"Source file missing: {path}")
                return False
            try:
                raw_src = read_file(path)
                df_src = normalize_df(raw_src)
                mask = pd.Series([False] * len(df_src), index=df_src.index)
                if "Task_ID" in df_src.columns and task_id:
                    mask = df_src["Task_ID"].astype(str).str.strip().eq(task_id)
                if not mask.any():
                    mask = (
                        df_src["Component"].astype(str).str.strip().eq(task_component)
                        & df_src["Task"].astype(str).str.strip().eq(task_name)
                    )
                if not mask.any():
                    st.error("Task row was not found in source file.")
                    return False
                for c in [
                    "Tracking_Mode",
                    "Hours_Source",
                    "Interval_Value",
                    "Interval_Unit",
                    "Trigger_Modes",
                    "Trigger_Hours_Source",
                    "Trigger_Hours_Interval",
                    "Trigger_Draws_Interval",
                    "Trigger_Calendar_Value",
                    "Trigger_Calendar_Unit",
                    "Last_Done_Date",
                    "Last_Done_Draw",
                    "Last_Done_Hours",
                    "Last_Done_Hours_UV1",
                    "Last_Done_Hours_UV2",
                    "Last_Done_Hours_Furnace",
                ]:
                    if c not in df_src.columns:
                        df_src[c] = ""

                clean_modes = []
                for m in trigger_modes:
                    mv = mode_norm(m)
                    if mv in ("hours", "draws", "calendar") and mv not in clean_modes:
                        clean_modes.append(mv)
                if not clean_modes:
                    clean_modes = [mode_norm(rr.get("Tracking_Mode", "")) or "calendar"]
                primary = clean_modes[0]

                src_tokens = []
                for hs in hours_sources:
                    h = norm_source(hs)
                    if h in ("uv", "uv both", "uv-both", "uv1+uv2", "uv2+uv1"):
                        if "uv" not in src_tokens:
                            src_tokens.append("uv")
                    elif h in ("uv1", "uv 1", "uv_system_1", "uv system 1", "uv-system-1", "system1", "system 1"):
                        if "uv1" not in src_tokens:
                            src_tokens.append("uv1")
                    elif h in ("uv2", "uv 2", "uv_system_2", "uv system 2", "uv-system-2", "system2", "system 2"):
                        if "uv2" not in src_tokens:
                            src_tokens.append("uv2")
                    elif h:
                        if "furnace" not in src_tokens:
                            src_tokens.append("furnace")
                if not src_tokens:
                    src_tokens = ["furnace"]

                primary_hours_source = "Furnace"
                if "uv" in src_tokens or ("uv1" in src_tokens and "uv2" in src_tokens):
                    primary_hours_source = "UV"
                elif "uv1" in src_tokens:
                    primary_hours_source = "UV1"
                elif "uv2" in src_tokens:
                    primary_hours_source = "UV2"

                df_src.loc[mask, "Tracking_Mode"] = primary
                df_src.loc[mask, "Trigger_Modes"] = ", ".join(clean_modes)
                df_src.loc[mask, "Trigger_Hours_Source"] = ", ".join(src_tokens)
                df_src.loc[mask, "Trigger_Hours_Interval"] = float(max(0.1, float(hours_interval)))
                df_src.loc[mask, "Trigger_Draws_Interval"] = int(max(1, int(draws_interval)))
                df_src.loc[mask, "Trigger_Calendar_Value"] = int(max(1, int(cal_value)))
                df_src.loc[mask, "Trigger_Calendar_Unit"] = safe_str(cal_unit).strip().lower() or "days"
                if primary == "hours":
                    df_src.loc[mask, "Hours_Source"] = primary_hours_source
                    df_src.loc[mask, "Interval_Value"] = float(max(0.1, float(hours_interval)))
                    df_src.loc[mask, "Interval_Unit"] = "hours"
                elif primary == "draws":
                    df_src.loc[mask, "Interval_Value"] = int(max(1, int(draws_interval)))
                    df_src.loc[mask, "Interval_Unit"] = "draws"
                elif primary == "calendar":
                    df_src.loc[mask, "Interval_Value"] = int(max(1, int(cal_value)))
                    df_src.loc[mask, "Interval_Unit"] = safe_str(cal_unit).strip().lower() or "days"

                # Reset all baselines at save, so dual triggers restart together.
                df_src.loc[mask, "Last_Done_Date"] = current_date.isoformat()
                df_src.loc[mask, "Last_Done_Draw"] = int(current_draw_count)
                df_src.loc[mask, "Last_Done_Hours_Furnace"] = float(furnace_hours)
                df_src.loc[mask, "Last_Done_Hours_UV1"] = float(uv1_hours)
                df_src.loc[mask, "Last_Done_Hours_UV2"] = float(uv2_hours)
                df_src.loc[mask, "Last_Done_Hours"] = float(furnace_hours)

                out_src = templateize_df(df_src, list(raw_src.columns))
                write_file(path, out_src)
                return True
            except Exception as e:
                st.error(f"Failed to update timing: {e}")
                return False

        def _save_test_config_for_task(
            test_preset_txt: str,
            test_fields_txt: str,
            test_thresholds_txt: str,
            test_condition_txt: str,
            test_action_txt: str,
        ):
            src = safe_str(rr.get("Source_File", "")).strip()
            if not src:
                st.error("Task has no Source_File, cannot update test config.")
                return False
            path = os.path.join(MAINT_FOLDER, src)
            if not os.path.exists(path):
                st.error(f"Source file missing: {path}")
                return False
            try:
                raw_src = read_file(path)
                df_src = normalize_df(raw_src)
                mask = pd.Series([False] * len(df_src), index=df_src.index)
                if "Task_ID" in df_src.columns and task_id:
                    mask = df_src["Task_ID"].astype(str).str.strip().eq(task_id)
                if not mask.any():
                    mask = (
                        df_src["Component"].astype(str).str.strip().eq(task_component)
                        & df_src["Task"].astype(str).str.strip().eq(task_name)
                    )
                if not mask.any():
                    st.error("Task row was not found in source file.")
                    return False
                for c in ["Test_Preset", "Test_Fields", "Test_Thresholds", "Test_Condition", "Test_Action"]:
                    if c not in df_src.columns:
                        df_src[c] = ""
                df_src.loc[mask, "Test_Preset"] = safe_str(test_preset_txt).strip()
                df_src.loc[mask, "Test_Fields"] = safe_str(test_fields_txt).strip()
                df_src.loc[mask, "Test_Thresholds"] = safe_str(test_thresholds_txt).strip()
                df_src.loc[mask, "Test_Condition"] = safe_str(test_condition_txt).strip()
                df_src.loc[mask, "Test_Action"] = safe_str(test_action_txt).strip()
                out_src = templateize_df(df_src, list(raw_src.columns))
                write_file(path, out_src)
                return True
            except Exception as e:
                st.error(f"Failed to update test config: {e}")
                return False

        def _manual_page_override_file() -> str:
            return os.path.join(MAINT_FOLDER, "manual_page_overrides.csv")

        def _load_task_manual_page_overrides() -> pd.DataFrame:
            cols = ["Task_ID", "Component", "Task", "Item", "Manual", "Page", "Updated_By", "Updated_At"]
            fp = _manual_page_override_file()
            if os.path.exists(fp):
                try:
                    dfp = _read_csv_keepna(fp)
                except Exception:
                    dfp = pd.DataFrame(columns=cols)
            else:
                dfp = pd.DataFrame(columns=cols)
            for c in cols:
                if c not in dfp.columns:
                    dfp[c] = ""
            task_id_l = safe_str(task_id).strip().lower()
            comp_l = safe_str(task_component).strip().lower()
            task_l = safe_str(task_name).strip().lower()
            m = pd.Series([False] * len(dfp), index=dfp.index)
            if task_id_l:
                m = dfp["Task_ID"].astype(str).str.strip().str.lower().eq(task_id_l)
            if not bool(m.any()):
                m = (
                    dfp["Component"].astype(str).str.strip().str.lower().eq(comp_l)
                    & dfp["Task"].astype(str).str.strip().str.lower().eq(task_l)
                )
            return dfp[m].copy()

        def _save_task_manual_page_overrides(rows_df: pd.DataFrame) -> bool:
            cols = ["Task_ID", "Component", "Task", "Item", "Manual", "Page", "Updated_By", "Updated_At"]
            fp = _manual_page_override_file()
            if os.path.exists(fp):
                try:
                    all_df = _read_csv_keepna(fp)
                except Exception:
                    all_df = pd.DataFrame(columns=cols)
            else:
                all_df = pd.DataFrame(columns=cols)
            for c in cols:
                if c not in all_df.columns:
                    all_df[c] = ""
            task_id_l = safe_str(task_id).strip().lower()
            comp_l = safe_str(task_component).strip().lower()
            task_l = safe_str(task_name).strip().lower()
            keep_mask = ~(
                all_df["Task_ID"].astype(str).str.strip().str.lower().eq(task_id_l)
                if task_id_l
                else (
                    all_df["Component"].astype(str).str.strip().str.lower().eq(comp_l)
                    & all_df["Task"].astype(str).str.strip().str.lower().eq(task_l)
                )
            )
            out_df = all_df[keep_mask].copy()
            now_ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            add_df = rows_df.copy()
            for c in cols:
                if c not in add_df.columns:
                    add_df[c] = ""
            add_df["Task_ID"] = safe_str(task_id).strip()
            add_df["Component"] = safe_str(task_component).strip()
            add_df["Task"] = safe_str(task_name).strip()
            add_df["Updated_By"] = safe_str(actor).strip()
            add_df["Updated_At"] = now_ts
            add_df = add_df[cols].copy()
            out_df = pd.concat([out_df[cols], add_df], ignore_index=True)
            out_df.to_csv(fp, index=False)
            return True

        pkg_match = pkg_df[pkg_df["Task_ID"].astype(str).str.strip().eq(task_id)].copy() if task_id else pd.DataFrame()
        has_pkg = not pkg_match.empty
        pkg_row = pkg_match.iloc[0] if has_pkg else pd.Series(dtype=object)
        required_tools_txt = safe_str(pkg_row.get("Required_Tools", "")).strip() if "Required_Tools" in pkg_row.index else ""
        mandatory_parts_txt = ", ".join(_task_mandatory_parts(rr))
        conditional_parts_txt = ", ".join(_task_conditional_parts(rr))
        prep_lead_default = _task_preparation_lead_days(rr)
        parts_check_lead_default = _task_parts_check_lead_days(rr)
        auto_order_default = _task_auto_order_mandatory(rr)
        existing_photo_rel = []
        if has_pkg:
            raw_photos = safe_str(pkg_row.get("Procedure_Photos", "")).strip()
            if raw_photos:
                for p in raw_photos.split(";"):
                    pv = safe_str(p).strip()
                    if pv:
                        existing_photo_rel.append(pv)

        inv_now = pd.DataFrame()
        try:
            inv_now = load_inventory_cached(P.parts_inventory_csv)
            inv_now["Part Name"] = inv_now["Part Name"].astype(str).fillna("")
            inv_now["Location"] = inv_now["Location"].astype(str).fillna("")
            inv_now["Quantity"] = pd.to_numeric(inv_now["Quantity"], errors="coerce").fillna(0.0)
        except Exception:
            pass

        parts = _parts_list(required_parts_txt)
        tools = _parts_list(required_tools_txt)
        current_task_key = f"{task_id}|{task_component}|{task_name}"
        if st.session_state.get("maint_pkg_required_parts_task_key", "") != current_task_key:
            st.session_state["maint_pkg_required_parts_task_key"] = current_task_key
            st.session_state["maint_pkg_required_parts_working"] = list(parts)
            st.session_state["maint_pkg_required_tools_working"] = list(tools)

        parts_working = [
            safe_str(x).strip()
            for x in st.session_state.get("maint_pkg_required_parts_working", list(parts))
            if safe_str(x).strip()
        ]
        tools_working = [
            safe_str(x).strip()
            for x in st.session_state.get("maint_pkg_required_tools_working", list(tools))
            if safe_str(x).strip()
        ]

        ready_parts_rows = []
        ready_tools_rows = []
        if (parts_working or tools_working) and not inv_now.empty:
            for p in parts_working:
                m = inv_now[inv_now["Part Name"].astype(str).str.strip().str.lower().eq(p.lower())].copy()
                mounted = float(m[m["Location"].astype(str).str.strip().str.lower().eq("mounted")]["Quantity"].sum()) if not m.empty else 0.0
                stock = float(m[m["Location"].astype(str).str.strip().str.lower().ne("mounted")]["Quantity"].sum()) if not m.empty else 0.0
                is_tool = (
                    bool((m.get("Item Type", pd.Series([], dtype=str)).astype(str).str.strip().str.lower().eq("tool")).any())
                    if not m.empty
                    else False
                ) or is_tool_like_part_name(p)
                if is_tool:
                    ready_tools_rows.append({"Tool": p, "Stock (not mounted)": round(stock, 3), "Mounted": round(mounted, 3), "Ready": "YES" if (stock + mounted) > 0 else "NO"})
                else:
                    ready_parts_rows.append({"Part": p, "Stock (not mounted)": round(stock, 3), "Mounted": round(mounted, 3), "Ready": "YES" if stock > 0 else "NO"})
            for t in tools_working:
                if any(str(r.get("Tool", "")).strip().lower() == t.lower() for r in ready_tools_rows):
                    continue
                m = inv_now[inv_now["Part Name"].astype(str).str.strip().str.lower().eq(t.lower())].copy()
                mounted = float(m[m["Location"].astype(str).str.strip().str.lower().eq("mounted")]["Quantity"].sum()) if not m.empty else 0.0
                stock = float(m[m["Location"].astype(str).str.strip().str.lower().ne("mounted")]["Quantity"].sum()) if not m.empty else 0.0
                ready_tools_rows.append({"Tool": t, "Stock (not mounted)": round(stock, 3), "Mounted": round(mounted, 3), "Ready": "YES" if (stock + mounted) > 0 else "NO"})

        with st.expander("🔩 Parts needed", expanded=False):
            st.caption("Live readiness preview from inventory for current BOM.")
            if ready_parts_rows:
                st.dataframe(pd.DataFrame(ready_parts_rows), use_container_width=True, height=min(180, 80 + 34 * len(ready_parts_rows)))
            else:
                st.caption("No parts in current BOM draft.")
            if ready_tools_rows:
                st.markdown("##### 🧰 Tools needed")
                st.dataframe(pd.DataFrame(ready_tools_rows), use_container_width=True, height=min(180, 80 + 34 * len(ready_tools_rows)))

        with st.expander("✍️ BOM Editor (Parts + Tools)", expanded=False):
            st.caption("Build the task BOM from inventory and manual edits.")
            if not inv_now.empty and "Part Name" in inv_now.columns:
                inv_pick = inv_now.copy()
                inv_pick["Part Name"] = inv_pick["Part Name"].astype(str).fillna("").str.strip()
                inv_pick["Component"] = inv_pick.get("Component", "").astype(str).fillna("").str.strip()
                inv_pick["Item Type"] = inv_pick.get("Item Type", "").astype(str).fillna("").str.strip().str.lower()
                pc1, pc2, pc3 = st.columns([1.0, 1.2, 0.9])
                with pc1:
                    inv_comp_opts = sorted([x for x in inv_pick["Component"].unique().tolist() if x])
                    inv_comp_filter = st.multiselect(
                        "Inventory component",
                        options=inv_comp_opts,
                        default=[task_component] if task_component in inv_comp_opts else [],
                        key="maint_pkg_inv_pick_component",
                    )
                with pc2:
                    inv_parts_opts = inv_pick[~inv_pick["Item Type"].eq("tool")].copy()
                    if inv_comp_filter:
                        inv_parts_opts = inv_parts_opts[inv_parts_opts["Component"].isin(inv_comp_filter)].copy()
                    inv_parts_q = st.text_input(
                        "Search parts",
                        value="",
                        key="maint_pkg_inv_pick_parts_q",
                        placeholder="type part name...",
                    ).strip().lower()
                    if inv_parts_q:
                        inv_parts_opts = inv_parts_opts[
                            inv_parts_opts["Part Name"].astype(str).str.lower().str.contains(inv_parts_q, na=False)
                        ].copy()
                    inv_name_opts = []
                    seen_inv = set()
                    for p in inv_parts_opts["Part Name"].tolist():
                        if not p:
                            continue
                        lk = p.lower()
                        if lk in seen_inv:
                            continue
                        seen_inv.add(lk)
                        inv_name_opts.append(p)
                    pick_inventory_parts = st.multiselect(
                        "Pick from inventory",
                        options=inv_name_opts,
                        default=[],
                        key="maint_pkg_inv_pick_parts",
                        placeholder="Choose inventory part(s) to append...",
                    )
                with pc3:
                    if st.button("➕ Add all filtered parts", key="maint_pkg_add_all_filtered_parts_btn", use_container_width=True):
                        merged = list(parts_working)
                        seen_merge = {safe_str(x).strip().lower() for x in merged if safe_str(x).strip()}
                        for p in inv_name_opts:
                            pv = safe_str(p).strip()
                            if not pv:
                                continue
                            lk = pv.lower()
                            if lk in seen_merge:
                                continue
                            merged.append(pv)
                            seen_merge.add(lk)
                        st.session_state["maint_pkg_required_parts_working"] = merged
                        st.rerun()
                if st.button("➕ Add selected inventory parts", key="maint_pkg_add_inventory_parts_btn", use_container_width=True):
                    merged = list(parts_working)
                    seen_merge = {safe_str(x).strip().lower() for x in merged if safe_str(x).strip()}
                    for p in pick_inventory_parts:
                        pv = safe_str(p).strip()
                        if not pv:
                            continue
                        lk = pv.lower()
                        if lk in seen_merge:
                            continue
                        merged.append(pv)
                        seen_merge.add(lk)
                    st.session_state["maint_pkg_required_parts_working"] = merged
                    st.rerun()

            parts_edit_df = pd.DataFrame({"Part": parts_working if parts_working else [""]})
            parts_edit = st.data_editor(
                parts_edit_df,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={"Part": st.column_config.TextColumn("Part", help="Part name exactly as used in inventory/manuals.")},
                key="maint_pkg_required_parts_editor",
            )
            if st.button("💾 Save Required Parts List", key="maint_pkg_required_parts_save_btn", use_container_width=True):
                new_parts = []
                seen_parts = set()
                for v in parts_edit.get("Part", pd.Series([], dtype=str)).tolist():
                    pv = safe_str(v).strip()
                    if not pv:
                        continue
                    lk = pv.lower()
                    if lk in seen_parts:
                        continue
                    new_parts.append(pv)
                    seen_parts.add(lk)
                new_required = ", ".join(new_parts)
                if _save_required_parts_for_task(new_required):
                    st.session_state["maint_pkg_required_parts_working"] = list(new_parts)
                    st.success("Required parts list saved.")
                    st.rerun()
            else:
                live_parts = []
                seen_live = set()
                for v in parts_edit.get("Part", pd.Series([], dtype=str)).tolist():
                    pv = safe_str(v).strip()
                    if not pv:
                        continue
                    lk = pv.lower()
                    if lk in seen_live:
                        continue
                    live_parts.append(pv)
                    seen_live.add(lk)
                st.session_state["maint_pkg_required_parts_working"] = list(live_parts)

        with st.expander("🧰 Edit Required Tools List", expanded=False):
            st.caption("Pick tools from inventory and keep them separated from parts.")
            if not inv_now.empty and "Part Name" in inv_now.columns:
                inv_tool_pick = inv_now.copy()
                inv_tool_pick["Part Name"] = inv_tool_pick["Part Name"].astype(str).fillna("").str.strip()
                inv_tool_pick["Component"] = inv_tool_pick.get("Component", "").astype(str).fillna("").str.strip()
                inv_tool_pick["Item Type"] = inv_tool_pick.get("Item Type", "").astype(str).fillna("").str.strip().str.lower()
                inv_tool_pick = inv_tool_pick[
                    inv_tool_pick["Item Type"].eq("tool")
                    | inv_tool_pick["Part Name"].apply(is_tool_like_part_name)
                ].copy()
                tc1, tc2, tc3 = st.columns([1.0, 1.2, 0.9])
                with tc1:
                    tool_comp_opts = sorted([x for x in inv_tool_pick["Component"].unique().tolist() if x])
                    tool_default = [x for x in ["General Tools", task_component] if x in tool_comp_opts]
                    inv_tool_comp_filter = st.multiselect(
                        "Tool component",
                        options=tool_comp_opts,
                        default=tool_default,
                        key="maint_pkg_inv_tool_component",
                    )
                with tc2:
                    inv_tools_opts = inv_tool_pick.copy()
                    if inv_tool_comp_filter:
                        inv_tools_opts = inv_tools_opts[inv_tools_opts["Component"].isin(inv_tool_comp_filter)].copy()
                    inv_tools_q = st.text_input(
                        "Search tools",
                        value="",
                        key="maint_pkg_inv_pick_tools_q",
                        placeholder="type tool name...",
                    ).strip().lower()
                    if inv_tools_q:
                        inv_tools_opts = inv_tools_opts[
                            inv_tools_opts["Part Name"].astype(str).str.lower().str.contains(inv_tools_q, na=False)
                        ].copy()
                    tool_name_opts = []
                    seen_tool = set()
                    for p in inv_tools_opts["Part Name"].tolist():
                        if not p:
                            continue
                        lk = p.lower()
                        if lk in seen_tool:
                            continue
                        seen_tool.add(lk)
                        tool_name_opts.append(p)
                    pick_inventory_tools = st.multiselect(
                        "Pick tools from inventory",
                        options=tool_name_opts,
                        default=[],
                        key="maint_pkg_inv_pick_tools",
                        placeholder="Choose tool(s) to append...",
                    )
                with tc3:
                    if st.button("➕ Add all filtered tools", key="maint_pkg_add_all_filtered_tools_btn", use_container_width=True):
                        merged = list(tools_working)
                        seen_merge = {safe_str(x).strip().lower() for x in merged if safe_str(x).strip()}
                        for t in tool_name_opts:
                            tv = safe_str(t).strip()
                            if not tv:
                                continue
                            lk = tv.lower()
                            if lk in seen_merge:
                                continue
                            merged.append(tv)
                            seen_merge.add(lk)
                        st.session_state["maint_pkg_required_tools_working"] = merged
                        st.rerun()
                if st.button("➕ Add selected inventory tools", key="maint_pkg_add_inventory_tools_btn", use_container_width=True):
                    merged = list(tools_working)
                    seen_merge = {safe_str(x).strip().lower() for x in merged if safe_str(x).strip()}
                    for t in pick_inventory_tools:
                        tv = safe_str(t).strip()
                        if not tv:
                            continue
                        lk = tv.lower()
                        if lk in seen_merge:
                            continue
                        merged.append(tv)
                        seen_merge.add(lk)
                    st.session_state["maint_pkg_required_tools_working"] = merged
                    st.rerun()

            tools_edit_df = pd.DataFrame({"Tool": tools_working if tools_working else [""]})
            tools_edit = st.data_editor(
                tools_edit_df,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={"Tool": st.column_config.TextColumn("Tool", help="Tool name exactly as used in inventory.")},
                key="maint_pkg_required_tools_editor",
            )
            if st.button("💾 Save Required Tools List", key="maint_pkg_required_tools_save_btn", use_container_width=True):
                new_tools = []
                seen_tools = set()
                for v in tools_edit.get("Tool", pd.Series([], dtype=str)).tolist():
                    tv = safe_str(v).strip()
                    if not tv:
                        continue
                    lk = tv.lower()
                    if lk in seen_tools:
                        continue
                    new_tools.append(tv)
                    seen_tools.add(lk)
                new_required_tools = ", ".join(new_tools)
                if _save_required_tools_for_task(new_required_tools):
                    st.session_state["maint_pkg_required_tools_working"] = list(new_tools)
                    st.success("Required tools list saved.")
                    st.rerun()
            else:
                live_tools = []
                seen_live_tools = set()
                for v in tools_edit.get("Tool", pd.Series([], dtype=str)).tolist():
                    tv = safe_str(v).strip()
                    if not tv:
                        continue
                    lk = tv.lower()
                    if lk in seen_live_tools:
                        continue
                    live_tools.append(tv)
                    seen_live_tools.add(lk)
                st.session_state["maint_pkg_required_tools_working"] = list(live_tools)

        bsave1, bsave2, bsave3 = st.columns([1.2, 1.2, 1.0])
        with bsave1:
            if st.button("💾 Save BOM (Parts + Tools)", key="maint_pkg_required_bom_save_btn", use_container_width=True, type="primary"):
                merged_parts = ", ".join(st.session_state.get("maint_pkg_required_parts_working", []))
                merged_tools = ", ".join(st.session_state.get("maint_pkg_required_tools_working", []))
                ok_parts = _save_required_parts_for_task(merged_parts)
                ok_tools = _save_required_tools_for_task(merged_tools)
                if ok_parts and ok_tools:
                    st.success("Saved Required Parts + Required Tools.")
                    st.rerun()
        with bsave2:
            if st.button("🧹 Clear BOM Draft", key="maint_pkg_required_bom_clear_btn", use_container_width=True):
                st.session_state["maint_pkg_required_parts_working"] = []
                st.session_state["maint_pkg_required_tools_working"] = []
                st.rerun()
        with bsave3:
            st.caption(
                f"Draft: parts={len(st.session_state.get('maint_pkg_required_parts_working', []))} | "
                f"tools={len(st.session_state.get('maint_pkg_required_tools_working', []))}"
            )

        with st.expander("🏷️ Task Group Editor", expanded=False):
            st.markdown("#### 🏷️ Task Groups")
            current_groups = row_task_groups(rr)
            st.caption("Assign one or more groups for this task (example: `3-Month, Hours`).")
            group_presets = [
                "Weekly", "Monthly", "3-Month", "6-Month",
                "Routine", "On-Condition", "Per-Draw/Startup",
                "Draw-Count", "Hours", "Test",
            ]
            known_groups = set(group_presets)
            for _, r in tasks_df.iterrows():
                for g in row_task_groups(r):
                    known_groups.add(g)
            g1, g2 = st.columns([1.2, 1.0])
            with g1:
                pkg_groups_sel = st.multiselect(
                    "Groups",
                    options=sorted(known_groups),
                    default=current_groups,
                    key="maint_pkg_groups_sel",
                )
            with g2:
                pkg_groups_custom = st.text_input(
                    "Custom group(s)",
                    value="",
                    placeholder="comma separated",
                    key="maint_pkg_groups_custom",
                )
            auto_group_tags = st.checkbox(
                "Auto add mode tags (draw -> Draw-Count, hours -> Hours)",
                value=True,
                key="maint_pkg_groups_auto_tags",
            )
            if st.button("💾 Save groups for this task", key="maint_pkg_groups_save_btn", use_container_width=True):
                merged, seen = [], set()
                for g in pkg_groups_sel + split_task_groups(pkg_groups_custom):
                    gv = safe_str(g).strip()
                    if not gv:
                        continue
                    lk = gv.lower()
                    if lk in seen:
                        continue
                    merged.append(gv)
                    seen.add(lk)
                if auto_group_tags:
                    tm = safe_str(rr.get("Tracking_Mode", "")).strip().lower()
                    if "draw" in tm and "draw-count" not in seen:
                        merged.append("Draw-Count")
                        seen.add("draw-count")
                    if "hour" in tm and "hours" not in seen:
                        merged.append("Hours")
                        seen.add("hours")
                new_groups_txt = ", ".join(merged)
                if _save_task_groups_for_task(new_groups_txt):
                    st.success("Task groups updated.")
                    st.rerun()

        with st.expander("⏱️ Timing & Triggers", expanded=False):
            st.caption("Pick up to 2 triggers. Task becomes due by the first trigger that reaches due.")
            timing_modes_opts = ["hours", "draws", "calendar"]
            default_modes = [m for m in _split_trigger_modes(rr) if m in timing_modes_opts]
            if len(default_modes) > 2:
                default_modes = default_modes[:2]
            if not default_modes:
                fallback_mode = mode_norm(rr.get("Tracking_Mode", ""))
                default_modes = [fallback_mode] if fallback_mode in timing_modes_opts else ["calendar"]
            trig_modes = st.multiselect(
                "Trigger modes (choose 1-2)",
                options=timing_modes_opts,
                default=default_modes,
                max_selections=2,
                key="maint_pkg_timing_modes",
            )
            if not trig_modes:
                trig_modes = default_modes

            ctm1, ctm2, ctm3 = st.columns(3)
            with ctm1:
                hs_default_raw = safe_str(rr.get("Trigger_Hours_Source", "")).strip() or safe_str(rr.get("Hours_Source", "")).strip()
                hs_default = []
                hr = hs_default_raw.lower()
                if "uv" in hr and ("1" not in hr and "2" not in hr):
                    hs_default = ["UV (both)"]
                elif "uv1" in hr or "uv 1" in hr:
                    hs_default = ["UV1"]
                elif "uv2" in hr or "uv 2" in hr:
                    hs_default = ["UV2"]
                elif hr:
                    hs_default = ["Furnace"]
                trig_hours_sources = st.multiselect(
                    "Hours source(s)",
                    options=["Furnace", "UV (both)", "UV1", "UV2"],
                    default=hs_default or ["Furnace"],
                    key="maint_pkg_timing_hours_sources",
                    disabled=("hours" not in trig_modes),
                )
            with ctm2:
                h_default = pd.to_numeric(rr.get("Trigger_Hours_Interval", rr.get("Interval_Value", 100.0)), errors="coerce")
                if pd.isna(h_default):
                    h_default = 100.0
                trig_hours_interval = st.number_input(
                    "Hours interval",
                    min_value=0.1,
                    max_value=100000.0,
                    value=float(h_default),
                    step=1.0,
                    key="maint_pkg_timing_hours_interval",
                    disabled=("hours" not in trig_modes),
                )
            with ctm3:
                d_default = pd.to_numeric(rr.get("Trigger_Draws_Interval", rr.get("Interval_Value", 1)), errors="coerce")
                if pd.isna(d_default):
                    d_default = 1
                trig_draws_interval = st.number_input(
                    "Draws interval",
                    min_value=1,
                    max_value=100000,
                    value=int(max(1, int(d_default))),
                    step=1,
                    key="maint_pkg_timing_draws_interval",
                    disabled=("draws" not in trig_modes),
                )

            ctm4, ctm5 = st.columns([1.0, 1.0])
            with ctm4:
                c_default = pd.to_numeric(rr.get("Trigger_Calendar_Value", rr.get("Interval_Value", 7)), errors="coerce")
                if pd.isna(c_default):
                    c_default = 7
                trig_cal_val = st.number_input(
                    "Calendar interval value",
                    min_value=1,
                    max_value=100000,
                    value=int(max(1, int(c_default))),
                    step=1,
                    key="maint_pkg_timing_cal_val",
                    disabled=("calendar" not in trig_modes),
                )
            with ctm5:
                iu_default = safe_str(rr.get("Trigger_Calendar_Unit", rr.get("Interval_Unit", "days"))).strip().lower()
                if iu_default not in ("days", "weeks", "months"):
                    iu_default = "days"
                trig_cal_unit = st.selectbox(
                    "Calendar unit",
                    options=["days", "weeks", "months"],
                    index=["days", "weeks", "months"].index(iu_default),
                    key="maint_pkg_timing_cal_unit",
                    disabled=("calendar" not in trig_modes),
                )
            if st.button("💾 Save timing + reset baselines", key="maint_pkg_timing_save_btn", use_container_width=True):
                ok = _save_timing_for_task(
                    trigger_modes=trig_modes,
                    hours_sources=trig_hours_sources,
                    hours_interval=trig_hours_interval,
                    draws_interval=trig_draws_interval,
                    cal_value=trig_cal_val,
                    cal_unit=trig_cal_unit,
                )
                if ok:
                    st.success("Timing updated. Triggers reset from current baseline.")
                    st.rerun()

        with st.expander("🤖 Automatic Parts + Preparation Flow", expanded=False):
            st.caption("Define the automatic flow once. Mandatory parts drive automatic ordering. Conditional parts stay visible for inspection/execution, but do not auto-order.")
            af1, af2 = st.columns(2)
            with af1:
                auto_mandatory = st.text_area(
                    "Mandatory parts",
                    value=mandatory_parts_txt,
                    height=120,
                    key="maint_pkg_auto_mandatory_parts",
                    help="These parts are always required for the task and are used for automatic parts checks and ordering.",
                )
            with af2:
                auto_conditional = st.text_area(
                    "Conditional parts",
                    value=conditional_parts_txt,
                    height=120,
                    key="maint_pkg_auto_conditional_parts",
                    help="These parts may be needed after inspection or fault correlation. They stay visible, but do not auto-order.",
                )
            af3, af4, af5 = st.columns([1, 1, 1.1])
            with af3:
                prep_lead_days = st.number_input(
                    "Preparation lead (days)",
                    min_value=0,
                    max_value=365,
                    value=int(prep_lead_default),
                    step=1,
                    key="maint_pkg_auto_prep_lead_days",
                )
            with af4:
                parts_check_lead_days = st.number_input(
                    "Parts-check lead (days)",
                    min_value=0,
                    max_value=365,
                    value=int(parts_check_lead_default),
                    step=1,
                    key="maint_pkg_auto_parts_check_lead_days",
                )
            with af5:
                auto_order_enabled = st.checkbox(
                    "Auto-order mandatory parts",
                    value=bool(auto_order_default),
                    key="maint_pkg_auto_order_enabled",
                    help="If mandatory parts are missing inside the parts-check window, open linked orders automatically.",
                )
            if st.button("💾 Save Automatic Flow", key="maint_pkg_auto_flow_save_btn", use_container_width=True, type="primary"):
                if _save_automatic_flow_for_task(
                    mandatory_parts_txt=auto_mandatory,
                    conditional_parts_txt=auto_conditional,
                    prep_lead_days=int(prep_lead_days),
                    parts_check_lead_days=int(parts_check_lead_days),
                    auto_order_enabled=bool(auto_order_enabled),
                ):
                    st.success("Automatic task flow saved.")
                    st.rerun()

        with st.expander("🧪 Test + Condition Capture", expanded=False):
            st.markdown(
                """
                <div class="maint-help-green">
                  <b>Optional task-level monitoring</b><br/>
                  Use this when the task needs measured values or a pass/fail check during execution.<br/>
                  Example fields: <b>Voltage (V); Temperature (degC); X offset (mm); Y offset (mm)</b>.<br/>
                  If the task is only a regular maintenance task, leave this blank.
                </div>
                """,
                unsafe_allow_html=True,
            )
            def _suggest_test_preset(row) -> str:
                text = " ".join(
                    [
                        safe_str(row.get("Task", "")).strip().lower(),
                        safe_str(row.get("Procedure_Summary", "")).strip().lower(),
                        safe_str(row.get("Notes", "")).strip().lower(),
                    ]
                )
                if "voltage trend" in text or ("heating element" in text and "voltage" in text):
                    return "Furnace Heating Element Voltage Trend"
                if "pyrometer" in text:
                    return "Pyrometer Alignment + Window Cleanliness"
                if "vacuum rose" in text or ("vacuum" in text and "purge" in text):
                    return "Storage Vacuum Rise"
                if "clean air velocity" in text or "airflow" in text or "anemometer" in text:
                    return "Clean-Air Velocity"
                if "interlock" in text or "alarm" in text:
                    return "Interlocks Test"
                if "top cap" in text and ("eroded" in text or "erosion" in text):
                    return "Top Cap Erosion"
                if "bottom doors" in text or ("distortion" in text and "door" in text):
                    return "Bottom Door Distortion"
                if "fibre position" in text and "center" in text:
                    return "Fibre Position Centering"
                if "x/y" in text or "x-y" in text or "offset" in text or "alignment" in text:
                    return "X-Y Alignment"
                if "tension gauge calibration" in text or "will not calibrate" in text or "erratic" in text or "load cell" in text:
                    return "Tension Gauge Calibration"
                if "bearing play" in text or "rotates freely" in text:
                    return "Bearing Play + Rotation"
                return "Custom"

            def _parse_threshold_rows(text: str):
                raw = safe_str(text).strip()
                if not raw:
                    return []
                try:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        out = []
                        for row in data:
                            if not isinstance(row, dict):
                                continue
                            out.append(
                                {
                                    "Field": safe_str(row.get("Field", "")).strip(),
                                    "Rule": safe_str(row.get("Rule", "")).strip(),
                                    "Value": safe_str(row.get("Value", "")).strip(),
                                    "Trigger Label": safe_str(row.get("Trigger Label", "")).strip(),
                                }
                            )
                        return out
                except Exception:
                    return []
                return []

            st.markdown("##### ⚙️ Preset Library (central)")
            st.caption("Edit the central test preset library once. All tasks can reuse these presets.")
            preset_library = load_maintenance_test_presets()
            library_names = sorted(list(preset_library.keys()))
            lib_pick = st.selectbox("Preset to edit", options=library_names, key="maint_test_library_pick")
            lib_row = preset_library.get(lib_pick, {"fields": "", "thresholds": [], "condition": "", "action": ""})
            lib_fields = st.text_area(
                "Preset fields",
                value=safe_str(lib_row.get("fields", "")).strip(),
                height=90,
                key="maint_test_library_fields",
            )
            lib_condition = st.text_area(
                "Preset condition",
                value=safe_str(lib_row.get("condition", "")).strip(),
                height=90,
                key="maint_test_library_condition",
            )
            lib_action = st.text_input(
                "Preset action",
                value=safe_str(lib_row.get("action", "")).strip(),
                key="maint_test_library_action",
            )
            lib_thresholds = st.data_editor(
                pd.DataFrame(lib_row.get("thresholds", []) or [{"Field": "", "Rule": ">", "Value": "", "Trigger Label": ""}]),
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "Field": st.column_config.TextColumn("Field"),
                    "Rule": st.column_config.SelectboxColumn("Rule", options=[">", ">=", "<", "<=", "=", "!=", "contains"]),
                    "Value": st.column_config.TextColumn("Value"),
                    "Trigger Label": st.column_config.TextColumn("Trigger Label"),
                },
                key="maint_test_library_thresholds",
            )
            lp1, lp2 = st.columns(2)
            with lp1:
                new_preset_name = st.text_input("New preset name", value="", key="maint_test_library_new_name", placeholder="optional")
            with lp2:
                if st.button("💾 Save preset library item", key="maint_test_library_save_btn", use_container_width=True):
                    target_name = safe_str(new_preset_name).strip() or lib_pick
                    clean_thresholds = []
                    for _, tr in lib_thresholds.iterrows():
                        row = {
                            "Field": safe_str(tr.get("Field", "")).strip(),
                            "Rule": safe_str(tr.get("Rule", "")).strip(),
                            "Value": safe_str(tr.get("Value", "")).strip(),
                            "Trigger Label": safe_str(tr.get("Trigger Label", "")).strip(),
                        }
                        if row["Field"] and row["Rule"] and row["Value"]:
                            clean_thresholds.append(row)
                    preset_library[target_name] = {
                        "fields": safe_str(lib_fields).strip(),
                        "thresholds": clean_thresholds,
                        "condition": safe_str(lib_condition).strip(),
                        "action": safe_str(lib_action).strip(),
                    }
                    if save_maintenance_test_presets(preset_library):
                        st.success(f"Saved preset: {target_name}")
                        st.rerun()
                    else:
                        st.error("Failed to save preset library.")

            test_fields_default = safe_str(rr.get("Test_Fields", "")).strip()
            test_preset_default = safe_str(rr.get("Test_Preset", "")).strip() or _suggest_test_preset(rr)
            test_thresholds_default = safe_str(rr.get("Test_Thresholds", "")).strip()
            test_condition_default = safe_str(rr.get("Test_Condition", "")).strip()
            test_action_default = safe_str(rr.get("Test_Action", "")).strip()
            preset_map = load_maintenance_test_presets()
            preset_options = list(preset_map.keys())
            if test_preset_default not in preset_options:
                test_preset_default = "Custom"
            if st.session_state.get("maint_pkg_test_task_key", "") != current_task_key:
                st.session_state["maint_pkg_test_task_key"] = current_task_key
                st.session_state["maint_pkg_test_preset"] = test_preset_default
                st.session_state["maint_pkg_test_fields"] = test_fields_default
                st.session_state["maint_pkg_test_condition"] = test_condition_default
                st.session_state["maint_pkg_test_action"] = test_action_default
                st.session_state["maint_pkg_test_threshold_rows"] = _parse_threshold_rows(test_thresholds_default)
            p1, p2 = st.columns([1.1, 1.0])
            with p1:
                selected_preset = st.selectbox(
                    "Preset",
                    options=preset_options,
                    index=preset_options.index(st.session_state.get("maint_pkg_test_preset", test_preset_default)),
                    key="maint_pkg_test_preset",
                )
            with p2:
                if st.button("✨ Apply preset", key="maint_pkg_test_apply_preset", use_container_width=True):
                    preset = preset_map.get(selected_preset, preset_map["Custom"])
                    st.session_state["maint_pkg_test_fields"] = safe_str(preset.get("fields", "")).strip()
                    st.session_state["maint_pkg_test_condition"] = safe_str(preset.get("condition", "")).strip()
                    st.session_state["maint_pkg_test_action"] = safe_str(preset.get("action", "")).strip()
                    st.session_state["maint_pkg_test_threshold_rows"] = list(preset.get("thresholds", []))
                    st.rerun()
            tf1, tf2 = st.columns(2)
            with tf1:
                test_fields_txt = st.text_area(
                    "Fields to capture",
                    key="maint_pkg_test_fields",
                    height=110,
                    placeholder="Voltage (V); Temperature (degC); X offset (mm); Y offset (mm)",
                )
            with tf2:
                test_condition_txt = st.text_area(
                    "If / condition text",
                    key="maint_pkg_test_condition",
                    height=110,
                    placeholder="If voltage trend increases or fibre strength drops, prepare replacement maintenance.",
                )
            test_action_txt = st.text_input(
                "Action if condition is met",
                key="maint_pkg_test_action",
                placeholder="Set PREP_NEEDED and schedule replacement task",
            )
            st.caption("Thresholds can auto-evaluate the measured values in Execute + Records.")
            threshold_rows = st.data_editor(
                pd.DataFrame(
                    st.session_state.get("maint_pkg_test_threshold_rows", _parse_threshold_rows(test_thresholds_default))
                    or [{"Field": "", "Rule": ">", "Value": "", "Trigger Label": ""}]
                ),
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "Field": st.column_config.TextColumn("Field"),
                    "Rule": st.column_config.SelectboxColumn("Rule", options=[">", ">=", "<", "<=", "=", "!=", "contains"]),
                    "Value": st.column_config.TextColumn("Value"),
                    "Trigger Label": st.column_config.TextColumn("Trigger Label"),
                },
                key="maint_pkg_test_threshold_editor",
            )
            if st.button("💾 Save test + condition config", key="maint_pkg_test_cfg_save_btn", use_container_width=True):
                clean_rows = []
                for _, tr in threshold_rows.iterrows():
                    row = {
                        "Field": safe_str(tr.get("Field", "")).strip(),
                        "Rule": safe_str(tr.get("Rule", "")).strip(),
                        "Value": safe_str(tr.get("Value", "")).strip(),
                        "Trigger Label": safe_str(tr.get("Trigger Label", "")).strip(),
                    }
                    if row["Field"] and row["Rule"] and row["Value"]:
                        clean_rows.append(row)
                thresholds_txt = json.dumps(clean_rows, ensure_ascii=True)
                if _save_test_config_for_task(selected_preset, test_fields_txt, thresholds_txt, test_condition_txt, test_action_txt):
                    st.success("Test + condition config saved for this task.")
                    st.rerun()

        with st.expander("📘 Manual Context + Page Pinning", expanded=False):
            task_manual_file_for_pin = _resolve_task_manual_file(rr, fallback_df=tasks_df)
            base_page_vals = _parse_task_pages(safe_str(rr.get("Page", "")))
            page_max = max(base_page_vals) if base_page_vals else 1
            if task_manual_file_for_pin:
                try:
                    import fitz
                    doc = fitz.open(os.path.join(P.root_dir, "manuals", task_manual_file_for_pin))
                    page_max = max(page_max, int(len(doc)))
                    doc.close()
                except Exception:
                    pass
            overrides_df = _load_task_manual_page_overrides()
            ov_map = {}
            for _, ov in overrides_df.iterrows():
                item = safe_str(ov.get("Item", "")).strip()
                pg = pd.to_numeric(ov.get("Page", 0), errors="coerce")
                if item and pd.notna(pg) and int(pg) > 0:
                    ov_map[item.lower()] = int(pg)
            item_list = []
            for it in st.session_state.get("maint_pkg_required_parts_working", list(parts)) + st.session_state.get("maint_pkg_required_tools_working", list(tools)):
                iv = safe_str(it).strip()
                if iv and iv.lower() not in {x.lower() for x in item_list}:
                    item_list.append(iv)
            default_page = int(base_page_vals[0]) if base_page_vals else 1
            map_rows = []
            for it in item_list:
                map_rows.append(
                    {
                        "Item": it,
                        "Manual": task_manual_file_for_pin or safe_str(rr.get("Manual_Name", "")).strip(),
                        "Page": int(ov_map.get(it.lower(), default_page)),
                    }
                )
            st.caption("Set exact manual page per BOM item (for stable, accurate context).")
            map_edit = st.data_editor(
                pd.DataFrame(map_rows if map_rows else [{"Item": "", "Manual": task_manual_file_for_pin or "", "Page": default_page}]),
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "Item": st.column_config.TextColumn("Item"),
                    "Manual": st.column_config.TextColumn("Manual"),
                    "Page": st.column_config.NumberColumn("Page", min_value=1, max_value=max(1, int(page_max)), step=1, format="%d"),
                },
                key="maint_pkg_manual_page_map_editor",
            )
            if st.button("💾 Save page mapping", key="maint_pkg_manual_page_map_save_btn", use_container_width=True):
                clean_rows = []
                for _, mr in map_edit.iterrows():
                    item_v = safe_str(mr.get("Item", "")).strip()
                    man_v = safe_str(mr.get("Manual", "")).strip() or task_manual_file_for_pin
                    page_v = pd.to_numeric(mr.get("Page", 0), errors="coerce")
                    if not item_v or pd.isna(page_v) or int(page_v) <= 0:
                        continue
                    clean_rows.append({"Item": item_v, "Manual": man_v, "Page": int(page_v)})
                _save_task_manual_page_overrides(pd.DataFrame(clean_rows))
                st.success("Manual page mapping saved.")
                st.rerun()
            forced_pages = []
            for _, mr in map_edit.iterrows():
                page_v = pd.to_numeric(mr.get("Page", 0), errors="coerce")
                if pd.notna(page_v) and int(page_v) > 0 and int(page_v) not in forced_pages:
                    forced_pages.append(int(page_v))
            _render_task_manual_context(
                rr,
                st.session_state.get("maint_pkg_required_parts_working", list(parts))
                + st.session_state.get("maint_pkg_required_tools_working", list(tools)),
                key_prefix="maint_builder_ctx",
                actor_name=actor,
                fallback_df=tasks_df,
                forced_pages=forced_pages,
            )

        with st.expander("🧾 Work Package Details (Prep/Safety/Procedure)", expanded=False):

            default_prep = "Confirm required parts availability (stock not mounted)."
            if has_pkg and safe_str(pkg_row.get("Preparation_Checklist", "")).strip():
                default_prep = safe_str(pkg_row.get("Preparation_Checklist", "")).strip()
            def _build_safety_template(row) -> str:
                comp = safe_str(row.get("Component", "")).strip().lower()
                task = safe_str(row.get("Task", "")).strip().lower()
                notes = safe_str(row.get("Notes", "")).strip().lower()
                proc = safe_str(row.get("Procedure_Summary", "")).strip().lower()
                text = f"{comp} {task} {notes} {proc}"
    
                blocks = []
                blocks.append(
                    "Warning - PPE:\n"
                    "- Correct Personal Protective Equipment (PPE) must be worn at all times.\n"
                    "- Minimum: safety glasses, gloves, and closed shoes."
                )
    
                if any(k in text for k in ["height", "fall", "tower", "platform", "top"]):
                    blocks.append(
                        "Warning - Working at height:\n"
                        "- Stay behind guard rails where applicable.\n"
                        "- Use approved fall-protection harness when required.\n"
                        "- Keep strict housekeeping to prevent dropped objects from the tower."
                    )
    
                if any(k in text for k in ["methanol", "solvent", "ipa", "chemical", "coating", "cleaner"]):
                    chem_name = "Methanol" if "methanol" in text else "Chemicals / solvents"
                    blocks.append(
                        f"Warning - {chem_name}:\n"
                        "- Avoid skin/eye exposure and inhalation.\n"
                        "- Use impermeable chemical-resistant gloves.\n"
                        "- Ensure local ventilation and clean spills immediately."
                    )
    
                if any(k in text for k in ["furnace", "heater", "hot", "uv", "burn", "thermal"]):
                    blocks.append(
                        "Warning - Hot surfaces / thermal hazard:\n"
                        "- Verify cool-down state before touch.\n"
                        "- Use heat-rated PPE and tools where needed."
                    )
    
                if any(k in text for k in ["transformer", "psu", "elect", "power", "panel", "mains"]):
                    blocks.append(
                        "Warning - Electrical hazard:\n"
                        "- Isolate power before opening or servicing.\n"
                        "- Apply lockout/tagout and verify zero-energy state."
                    )
    
                if any(k in text for k in ["belt", "pulley", "capstan", "winder", "drive", "rotation", "motor"]):
                    blocks.append(
                        "Warning - Moving parts:\n"
                        "- Stop motion before hands/tools enter work zone.\n"
                        "- Keep clear of pinch points during test/restart."
                    )
    
                blocks.append(
                    "General:\n"
                    "- Assign one responsible operator for start/stop approval.\n"
                    "- Confirm required parts/tools are ready before opening the system.\n"
                    "- Keep work area marked and controlled."
                )
                blocks.append(
                    "Routine:\n"
                    "- Execute inspection/service steps in sequence.\n"
                    "- Record findings and any replaced parts.\n"
                    "- Verify safe restart and update maintenance record."
                )
                return "\n\n".join(blocks)
    
            default_safety = safe_str(pkg_row.get("Safety_Protocol", "")).strip() if has_pkg else ""
            if not default_safety:
                default_safety = _build_safety_template(rr)
            default_proc = safe_str(pkg_row.get("Procedure_Steps", "")).strip() if has_pkg else ""
            if not default_proc:
                default_proc = safe_str(rr.get("Procedure_Summary", "")).strip()
            if not default_proc:
                # Some legacy templates put procedural hints in Notes.
                default_proc = safe_str(rr.get("Notes", "")).strip()
            default_stop = safe_str(pkg_row.get("Draw_Stop_Plan", "")).strip() if has_pkg else "Pause draw, isolate subsystem, perform checks, resume after verification."
            est_stop_default = pd.to_numeric(pkg_row.get("Est_Stop_Min", rr.get("Est_Duration_Min", 30) if has_pkg else rr.get("Est_Duration_Min", 30)), errors="coerce")
            est_stop_default = 30.0 if pd.isna(est_stop_default) else float(est_stop_default)
            done_criteria_default = safe_str(pkg_row.get("Completion_Criteria", "")).strip() if has_pkg else "Task completed, system verified, safe restart confirmed."
            legacy_notes_text = safe_str(rr.get("Notes", "")).strip()
            fall_risk_default = safe_str(pkg_row.get("Safety_Fall_Risk", "")).strip().lower() in {"1", "true", "yes", "y"}
            access_default = safe_str(pkg_row.get("Safety_TnM_Presence", "")).strip() if has_pkg else ""
            valid_access = ["Standard access", "Controlled access", "NO ENTRY (high fall risk)"]
            if not access_default:
                access_default = "NO ENTRY (high fall risk)" if fall_risk_default else "Standard access"
            if access_default not in valid_access:
                access_default = "Standard access"
    
            # Reset widget-bound values when switching task, so fields follow selected task.
            if st.session_state.get("maint_pkg_active_task_key", "") != current_task_key:
                st.session_state["maint_pkg_active_task_key"] = current_task_key
                st.session_state["maint_pkg_prep_txt"] = default_prep
                st.session_state["maint_pkg_stop_txt"] = default_stop
                st.session_state["maint_pkg_safety_txt"] = default_safety
                st.session_state["maint_pkg_proc_txt"] = default_proc
                st.session_state["maint_pkg_est_stop_min"] = float(max(0.0, est_stop_default))
                st.session_state["maint_pkg_done_criteria"] = done_criteria_default
                st.session_state["maint_pkg_fall_risk"] = bool(fall_risk_default)
                st.session_state["maint_pkg_tnm_presence"] = access_default
    
                w1, w2 = st.columns(2)
                with w1:
                    prep_text = st.text_area("Preparation checklist", height=120, key="maint_pkg_prep_txt")
                    stop_plan = st.text_area("Draw stop / prep plan", height=90, key="maint_pkg_stop_txt")
                with w2:
                    safety_text = st.text_area("Safety protocol", height=120, key="maint_pkg_safety_txt")
                    proc_text = st.text_area("Procedure steps (final execution)", height=90, key="maint_pkg_proc_txt")
                st.caption("Safety protocol is auto-tailored by task/component on first load, then fully editable.")
                s1, s2 = st.columns([1.1, 1.4])
                with s1:
                    fall_risk_flag = st.checkbox(
                        "⚠️ High fall risk in this maintenance",
                        key="maint_pkg_fall_risk",
                    )
                with s2:
                    if fall_risk_flag:
                        st.session_state["maint_pkg_tnm_presence"] = "NO ENTRY (high fall risk)"
                    tnm_presence = st.selectbox(
                        "Access indicator",
                        options=valid_access,
                        key="maint_pkg_tnm_presence",
                        disabled=bool(fall_risk_flag),
                    )
                if fall_risk_flag:
                    st.error("NO ENTRY indicator active: high fall risk. T&M presence is NOT allowed during execution.")
                elif tnm_presence == "Controlled access":
                    st.info("Access indicator: Controlled access (authorized staff only).")
    
                if legacy_notes_text:
                    st.markdown(
                        """
                        <div class="maint-help-green">
                          <b>Legacy task notes (operation/procedure hints)</b><br/>
                          Kept visible for procedure context. Safety remains a dedicated safety protocol block.
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.text_area("Legacy operation notes", value=legacy_notes_text, height=90, key="maint_pkg_legacy_notes_ro", disabled=True)
    
                st.markdown("#### 📷 Procedure Photos")
                st.caption("Attach step photos for this task procedure (saved under maintenance/work_package_photos).")
                if existing_photo_rel:
                    st.caption(f"Saved photos: {len(existing_photo_rel)}")
                    cols = st.columns(3)
                    for i, rel in enumerate(existing_photo_rel[:9]):
                        pth = os.path.join(MAINT_FOLDER, rel)
                        if os.path.isfile(pth):
                            with cols[i % 3]:
                                st.image(pth, caption=os.path.basename(rel), use_container_width=True)
                uploaded_proc_photos = st.file_uploader(
                    "Upload procedure photos",
                    type=["png", "jpg", "jpeg", "webp"],
                    accept_multiple_files=True,
                    key="maint_pkg_photo_uploader",
                )
                c1, c2 = st.columns(2)
                with c1:
                    est_stop_min = st.number_input("Estimated stop time (min)", min_value=0.0, max_value=1440.0, step=5.0, key="maint_pkg_est_stop_min")
                with c2:
                    done_criteria = st.text_input("Completion criteria", key="maint_pkg_done_criteria")
                if st.button("💾 Save Work Package", key="maint_pkg_save_btn", use_container_width=True, type="primary"):
                    # Save uploaded procedure photos and persist relative paths.
                    def _safe_name(v: str) -> str:
                        out = []
                        for ch in safe_str(v):
                            if ch.isalnum() or ch in ("-", "_", "."):
                                out.append(ch)
                            else:
                                out.append("_")
                        return "".join(out).strip("._") or "file"
                    task_folder_key = _safe_name(task_id if task_id else f"{task_component}_{task_name}")
                    photos_dir = os.path.join(MAINT_FOLDER, "work_package_photos", task_folder_key)
                    os.makedirs(photos_dir, exist_ok=True)
                    photo_rel_paths = list(existing_photo_rel)
                    seen_photo = {p.lower() for p in photo_rel_paths}
                    for up in (uploaded_proc_photos or []):
                        try:
                            base = _safe_name(up.name)
                            stem, ext = os.path.splitext(base)
                            ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
                            final_name = f"{stem}_{ts}{ext or '.png'}"
                            abs_path = os.path.join(photos_dir, final_name)
                            with open(abs_path, "wb") as f:
                                f.write(up.getbuffer())
                            rel_path = os.path.relpath(abs_path, MAINT_FOLDER)
                            if rel_path.lower() not in seen_photo:
                                photo_rel_paths.append(rel_path)
                                seen_photo.add(rel_path.lower())
                        except Exception:
                            pass
                        now_ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                        new_row = {
                            "Task_ID": task_id,
                            "Component": task_component,
                            "Task": task_name,
                            "Task_Group": task_group,
                            "Required_Parts": safe_str(rr.get("Required_Parts", "")).strip(),
                            "Required_Tools": ", ".join(st.session_state.get("maint_pkg_required_tools_working", list(tools_working))),
                            "Preparation_Checklist": prep_text.strip(),
                            "Safety_Protocol": safety_text.strip(),
                            "Safety_Fall_Risk": "Yes" if bool(fall_risk_flag) else "No",
                            "Safety_TnM_Presence": safe_str(tnm_presence).strip(),
                            "Procedure_Steps": proc_text.strip(),
                            "Procedure_Photos": ";".join(photo_rel_paths),
                            "Draw_Stop_Plan": stop_plan.strip(),
                            "Est_Stop_Min": float(est_stop_min),
                            "Completion_Criteria": done_criteria.strip(),
                            "Last_Updated": now_ts,
                            "Updated_By": safe_str(actor).strip(),
                        }
                        if task_id and (pkg_df["Task_ID"].astype(str).str.strip() == task_id).any():
                            idx = pkg_df[pkg_df["Task_ID"].astype(str).str.strip() == task_id].index[0]
                            for k, v in new_row.items():
                                pkg_df.at[idx, k] = v
                        else:
                            pkg_df = pd.concat([pkg_df, pd.DataFrame([new_row])], ignore_index=True)
                        pkg_df.to_csv(pkg_file, index=False)
                        _save_est_duration_for_task(float(est_stop_min))
                        st.success("Work package saved.")
                        st.rerun()
        
    def render_maintenance_day_todo_pack(dfm, current_date, actor):
        st.markdown("**🗓️ Next Preparation Batch**")
        st.caption("This shows the next scheduled maintenance tasks the shift should prepare for automatically.")
        base_day = pd.Timestamp(current_date).normalize()

        sched_path = P.schedule_csv
        if os.path.exists(sched_path):
            try:
                sched_df = _read_csv_keepna(sched_path)
            except Exception:
                sched_df = pd.DataFrame()
        else:
            sched_df = pd.DataFrame()
        for col in ["Event Type", "Start DateTime", "End DateTime", "Description", "Recurrence"]:
            if col not in sched_df.columns:
                sched_df[col] = ""
        sched_df["_start"] = pd.to_datetime(sched_df["Start DateTime"], errors="coerce")
        prep_events = sched_df[
            sched_df["Event Type"].astype(str).str.strip().eq("Maintenance Preparation")
            & sched_df["_start"].notna()
            & (sched_df["_start"].dt.normalize() >= base_day)
        ].copy()

        if prep_events.empty:
            st.info("No automatic preparation events are scheduled yet. Apply the automatic plan first, then return here.")
            return

        next_prep_day = prep_events["_start"].dt.normalize().min()
        prep_events = prep_events[prep_events["_start"].dt.normalize().eq(next_prep_day)].copy()
        st.caption(f"Next preparation batch date: {pd.Timestamp(next_prep_day).date()}")

        def _parse_sched_task(desc: str):
            body = safe_str(desc).strip()
            if "] " in body:
                body = body.split("] ", 1)[1]
            left = body.split(" | ", 1)[0].strip()
            comp = ""
            task = ""
            task_id_local = ""
            if " - " in left:
                comp, task = left.split(" - ", 1)
            if "(ID:" in body:
                task_id_local = body.split("(ID:", 1)[1].split(")", 1)[0].strip()
            return comp.strip(), task.strip(), task_id_local.strip()

        selected_rows = []
        if not prep_events.empty:
            for _, er in prep_events.sort_values("_start").iterrows():
                comp, task, task_id_local = _parse_sched_task(er.get("Description", ""))
                match = pd.DataFrame()
                if task_id_local and "Task_ID" in dfm.columns:
                    match = dfm[dfm["Task_ID"].astype(str).str.strip().eq(task_id_local)].copy()
                if match.empty:
                    match = dfm[
                        dfm["Component"].astype(str).str.strip().eq(comp)
                        & dfm["Task"].astype(str).str.strip().eq(task)
                    ].copy()
                if match.empty:
                    continue
                row = match.iloc[0].copy()
                row["Prep Event Start"] = safe_str(er.get("Start DateTime", "")).strip()
                selected_rows.append(row)
        day_df = pd.DataFrame(selected_rows)
        if day_df.empty:
            st.info("No maintenance tasks were matched for the next scheduled preparation batch.")
            return

        try:
            inv_df = load_inventory_cached(P.parts_inventory_csv)
            inv_df["Part Name"] = inv_df["Part Name"].astype(str).str.strip().str.lower()
            inv_df["Item Type"] = inv_df.get("Item Type", "").astype(str).str.strip().str.lower()
            inv_df["Location"] = inv_df.get("Location", "").astype(str).str.strip().str.lower()
            inv_df["Quantity"] = pd.to_numeric(inv_df.get("Quantity", 0), errors="coerce").fillna(0.0)
            stock_df = inv_df[inv_df["Location"].ne("mounted")].copy()
            mounted_df = inv_df[inv_df["Location"].eq("mounted")].copy()
            inv_qty = stock_df.groupby("Part Name")["Quantity"].sum().to_dict()
            inv_mounted_qty = mounted_df.groupby("Part Name")["Quantity"].sum().to_dict()
            inv_tool_map = (
                inv_df.groupby("Part Name")
                .apply(
                    lambda g: bool(
                        g["Item Type"].astype(str).str.strip().str.lower().eq("tool").any()
                        or is_tool_like_part_name(g.name)
                    )
                )
                .to_dict()
            )
            inv_effective_qty = {}
            for pn in (set(inv_qty.keys()) | set(inv_mounted_qty.keys()) | set(inv_tool_map.keys())):
                stock_q = float(inv_qty.get(pn, 0.0))
                mounted_q = float(inv_mounted_qty.get(pn, 0.0))
                inv_effective_qty[pn] = stock_q + mounted_q if bool(inv_tool_map.get(pn, False)) else stock_q
        except Exception:
            inv_effective_qty = {}

        def _parts_list(v):
            s = safe_str(v).strip()
            if not s:
                return []
            out = []
            for p in s.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
                pv = p.strip()
                if pv:
                    out.append(pv)
            uniq = []
            seen = set()
            for p in out:
                lk = p.lower()
                if lk not in seen:
                    uniq.append(p)
                    seen.add(lk)
            return uniq

        def _parts_ready(row):
            parts = _task_mandatory_parts(row)
            if not parts:
                return "No parts"
            missing = []
            for p in parts:
                if float(inv_effective_qty.get(p.lower(), 0.0)) <= 0:
                    missing.append(p)
            if not missing:
                return "Ready"
            return "Missing: " + ", ".join(missing)

        if os.path.exists(P.parts_orders_csv):
            try:
                day_orders_df = _read_csv_keepna(P.parts_orders_csv)
            except Exception:
                day_orders_df = pd.DataFrame()
        else:
            day_orders_df = pd.DataFrame()
        for col in ["Part Name", "Status", "Maintenance Task ID", "Wait ID", "Inventory Synced", "Received State"]:
            if col not in day_orders_df.columns:
                day_orders_df[col] = ""

        def _task_parts_flow_state(row) -> str:
            req_parts = _task_mandatory_parts(row)
            cond_parts = _task_conditional_parts(row)
            if not req_parts:
                cond_missing = [
                    p for p in cond_parts
                    if float(inv_effective_qty.get(p.lower(), 0.0)) <= 0
                ]
                if cond_missing:
                    return "Ready to run: conditional part is not in stock if inspection requires it"
                return "Ready to run: no mandatory parts required"
            task_id = safe_str(row.get("Task_ID", "")).strip()
            linked_rows = day_orders_df[
                day_orders_df["Maintenance Task ID"].astype(str).str.strip().eq(task_id)
            ].copy() if task_id and not day_orders_df.empty else pd.DataFrame()
            missing_parts = [
                p for p in req_parts
                if float(inv_effective_qty.get(p.lower(), 0.0)) <= 0
            ]
            if not missing_parts:
                return "Ready to run: required parts are already available"
            if linked_rows.empty:
                return "Missing parts, no linked order yet"
            linked_open = linked_rows[
                linked_rows["Status"].astype(str).str.strip().isin(["Opened", "Wait for Approval", "Approved", "Ordered"])
            ].copy()
            linked_recv_pending = linked_rows[
                linked_rows["Status"].astype(str).str.strip().eq("Received")
                & linked_rows["Inventory Synced"].astype(str).str.strip().str.lower().ne("yes")
            ].copy()
            linked_ready = linked_rows[
                linked_rows["Status"].astype(str).str.strip().eq("Received")
                & linked_rows["Inventory Synced"].astype(str).str.strip().str.lower().eq("yes")
            ].copy()
            if not linked_recv_pending.empty:
                return "Received, waiting inventory action"
            if not linked_open.empty:
                return "Missing parts, linked order already open"
            if not linked_ready.empty:
                return "Linked parts received and inventory-synced"
            return "Missing parts, review linked orders"

        day_df["Required_Parts"] = day_df.apply(lambda r: ", ".join(_task_mandatory_parts(r)), axis=1)
        day_df["Conditional_Parts"] = day_df.apply(lambda r: ", ".join(_task_conditional_parts(r)), axis=1)
        day_df["Parts Readiness"] = day_df.apply(_parts_ready, axis=1)
        day_df["Task Flow State"] = day_df.apply(_task_parts_flow_state, axis=1)
        def _parts_signal(pr: str) -> str:
            s = str(pr).strip()
            if s == "Ready":
                return "🟢 Ready"
            if s == "No parts":
                return "🔵 No parts"
            if s.startswith("Missing:"):
                return "🟠 Missing"
            return "⚪ Review"
        def _flow_signal(flow: str) -> str:
            s = str(flow).strip()
            if "Ready to run" in s or "inventory-synced" in s:
                return "🟢 Ready"
            if "no linked order yet" in s:
                return "🔴 Need order"
            if "already open" in s:
                return "🟠 Order open"
            if "waiting inventory action" in s:
                return "🟡 Pending inventory"
            return "⚪ Review"
        def _next_action(flow: str) -> str:
            s = str(flow).strip()
            if "no linked order yet" in s:
                return "Open parts order"
            if "already open" in s:
                return "Wait for order"
            if "waiting inventory action" in s:
                return "Do inventory action"
            if "conditional part is not in stock" in s:
                return "Inspect first, then decide"
            return "Prepare task"
        day_df["Parts Signal"] = day_df["Parts Readiness"].apply(_parts_signal)
        day_df["Flow Signal"] = day_df["Task Flow State"].apply(_flow_signal)
        day_df["Next Action"] = day_df["Task Flow State"].apply(_next_action)
        ready_n = int(day_df["Parts Readiness"].astype(str).eq("Ready").sum())
        need_order_n = int(day_df["Task Flow State"].astype(str).eq("Missing parts, no linked order yet").sum())
        pending_inventory_n = int(day_df["Task Flow State"].astype(str).eq("Received, waiting inventory action").sum())
        problems_n = int(max(need_order_n, pending_inventory_n))
        st.markdown(
            f"""
            <div class="maint-prep-grid">
              <div class="maint-prep-card k-blue">
                <div class="maint-prep-k">Tasks to prepare</div>
                <div class="maint-prep-v maint-v-blue">{int(len(day_df))}</div>
                <div class="maint-prep-note">Maintenance tasks coming in the next prep batch</div>
              </div>
              <div class="maint-prep-card {'k-green' if ready_n else 'k-blue'}">
                <div class="maint-prep-k">Ready</div>
                <div class="maint-prep-v {'maint-v-green' if ready_n else 'maint-v-blue'}">{ready_n}</div>
                <div class="maint-prep-note">Can be prepared without waiting</div>
              </div>
              <div class="maint-prep-card {'k-red' if need_order_n else 'k-blue'}">
                <div class="maint-prep-k">Need order</div>
                <div class="maint-prep-v {'maint-v-red' if need_order_n else 'maint-v-blue'}">{need_order_n}</div>
                <div class="maint-prep-note">Missing mandatory parts with no order yet</div>
              </div>
              <div class="maint-prep-card {'k-amber' if pending_inventory_n else 'k-blue'}">
                <div class="maint-prep-k">Pending inventory</div>
                <div class="maint-prep-v {'maint-v-orange' if pending_inventory_n else 'maint-v-blue'}">{pending_inventory_n}</div>
                <div class="maint-prep-note">Received items still need inventory action</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        out_cols = ["Prep Event Start", "Task", "Parts Signal", "Flow Signal", "Next Action"]
        out_cols = [c for c in out_cols if c in day_df.columns]
        sort_cols = [c for c in ["Prep Event Start", "Component", "Task"] if c in day_df.columns]
        day_view = day_df[out_cols].sort_values(sort_cols).copy()
        st.dataframe(
            day_view,
            use_container_width=True,
            height=240,
        )
        if problems_n == 0:
            st.success("Preparation is clear for this day. The shift can prepare and move on.")
        else:
            st.warning("Some preparation items still need action before the shift is fully ready.")
        dp_act1, dp_act2, dp_act3 = st.columns(3)
        with dp_act1:
            if st.button("🛠️ Open Tower Parts", key="maint_day_open_tower_parts", use_container_width=True):
                st.session_state["selected_tab"] = "🛠️ Tower Parts"
                st.rerun()
        with dp_act2:
            if st.button("📦 Open Planning Lane", key="maint_day_open_planning_lane", use_container_width=True):
                st.session_state["maint_flow_step"] = "1) Plan + Prepare"
                st.rerun()
        with dp_act3:
            if st.button("🧰 Open Execution Lane", key="maint_day_open_exec_lane", use_container_width=True):
                st.session_state["maint_flow_step"] = "2) Execute + Resolve Blocks"
                st.rerun()

        # Quick missing-parts order creation from scheduled preparation day.
        missing_df = day_df[day_df["Parts Readiness"].astype(str).str.startswith("Missing:")].copy()
        if not missing_df.empty:
            st.caption(f"Missing parts tasks on selected day: {len(missing_df)}")
            task_opts = []
            task_map = {}
            for i, r in missing_df.iterrows():
                lbl = f"{safe_str(r.get('Component',''))} — {safe_str(r.get('Task',''))} (ID:{safe_str(r.get('Task_ID',''))})"
                task_opts.append(lbl)
                task_map[lbl] = int(i)
            selected_tasks = st.multiselect(
                "Create orders for tasks",
                options=task_opts,
                default=[],
                key="maint_day_missing_tasks_pick",
            )

            def _load_active_orders_df():
                if os.path.exists(P.parts_orders_csv):
                    try:
                        odf_local = _read_csv_keepna(P.parts_orders_csv)
                    except Exception:
                        odf_local = pd.DataFrame()
                else:
                    odf_local = pd.DataFrame()
                for col in ["Part Name", "Status"]:
                    if col not in odf_local.columns:
                        odf_local[col] = ""
                return odf_local

            def _build_orders_preview(rows_df: pd.DataFrame, odf_local: pd.DataFrame) -> pd.DataFrame:
                out_rows = []
                for _, rr in rows_df.iterrows():
                    req_parts = _parts_list(rr.get("Required_Parts", ""))
                    task_name = safe_str(rr.get("Task", ""))
                    task_id = safe_str(rr.get("Task_ID", ""))
                    component = safe_str(rr.get("Component", ""))
                    for part_name in req_parts:
                        exists_active = _maintenance_active_order_mask(
                            odf_local,
                            part_name=part_name,
                            maintenance_task_id=task_id,
                            wait_id="",
                        ).any()
                        out_rows.append(
                            {
                                "Order?": (not exists_active),
                                "Part": part_name,
                                "Component": component,
                                "Task": task_name,
                                "Task_ID": task_id,
                                "Action": "Skip (already active)" if exists_active else "Create order",
                                "_row_key": f"{component}|{task_id}|{task_name}|{part_name}",
                            }
                        )
                return pd.DataFrame(out_rows)

            if selected_tasks:
                pick_idx = [task_map[x] for x in selected_tasks if x in task_map]
                preview_src = missing_df.loc[pick_idx].copy() if pick_idx else missing_df.iloc[0:0].copy()
                preview_odf = _load_active_orders_df()
                preview_df = _build_orders_preview(preview_src, preview_odf)
                if not preview_df.empty:
                    will_create = int((preview_df["Action"] == "Create order").sum())
                    will_skip = int((preview_df["Action"] != "Create order").sum())
                    st.caption(f"Order preview: create={will_create} | skip={will_skip}")
                    preview_edit = st.data_editor(
                        preview_df[["Order?", "Part", "Component", "Task", "Task_ID", "Action", "_row_key"]],
                        hide_index=True,
                        use_container_width=True,
                        height=190,
                        disabled=["Part", "Component", "Task", "Task_ID", "Action", "_row_key"],
                        column_order=["Order?", "Part", "Component", "Task", "Task_ID", "Action"],
                        column_config={
                            "Order?": st.column_config.CheckboxColumn(
                                "Order?",
                                help="Check only parts you want to order now.",
                                default=True,
                            ),
                            "Part": st.column_config.TextColumn("Part"),
                            "Component": st.column_config.TextColumn("Component"),
                            "Task": st.column_config.TextColumn("Task"),
                            "Task_ID": st.column_config.TextColumn("Task_ID"),
                            "Action": st.column_config.TextColumn("Action"),
                            "_row_key": st.column_config.TextColumn("_row_key"),
                        },
                        key="maint_day_order_preview_editor",
                    )
                    checked_keys = set(
                        preview_edit.loc[
                            preview_edit["Order?"].fillna(False).astype(bool)
                            & preview_edit["Action"].astype(str).eq("Create order"),
                            "_row_key",
                        ].astype(str).tolist()
                    )
                else:
                    checked_keys = set()
            else:
                checked_keys = set()

            def _create_orders_for_rows(rows_df):
                created = 0
                odf = _load_active_orders_df()
                for _, rr in rows_df.iterrows():
                    req_parts = _parts_list(rr.get("Required_Parts", ""))
                    for part_name in req_parts:
                        exists_active = _maintenance_active_order_mask(
                            odf,
                            part_name=part_name,
                            maintenance_task_id=safe_str(rr.get("Task_ID", "")),
                            wait_id="",
                        ).any()
                        if exists_active:
                            continue
                        details = (
                            f"Auto from {package_context_label}: "
                            f"{safe_str(rr.get('Component',''))} — {safe_str(rr.get('Task',''))} "
                            f"(Task ID:{safe_str(rr.get('Task_ID',''))})"
                        )
                        _append_parts_order_from_maintenance(
                            part_name=part_name,
                            details=details,
                            actor=actor,
                            project_name="Maintenance",
                            company="",
                            maintenance_component=safe_str(rr.get("Component", "")),
                            maintenance_task=safe_str(rr.get("Task", "")),
                            maintenance_task_id=safe_str(rr.get("Task_ID", "")),
                            wait_id="",
                        )
                        created += 1
                return created

            def _create_orders_from_preview(preview_rows_df: pd.DataFrame, selected_row_keys: set[str]):
                created = 0
                if preview_rows_df is None or preview_rows_df.empty:
                    return created
                if not selected_row_keys:
                    return created

                odf = _load_active_orders_df()
                picked = preview_rows_df[
                    preview_rows_df["_row_key"].astype(str).isin(selected_row_keys)
                    & preview_rows_df["Action"].astype(str).eq("Create order")
                ].copy()
                for _, rr in picked.iterrows():
                    part_name = safe_str(rr.get("Part", "")).strip()
                    if not part_name:
                        continue
                    exists_active = _maintenance_active_order_mask(
                        odf,
                        part_name=part_name,
                        maintenance_task_id=safe_str(rr.get("Task_ID", "")),
                        wait_id="",
                    ).any()
                    if exists_active:
                        continue

                    details = (
                        f"Auto from {package_context_label}: "
                        f"{safe_str(rr.get('Component',''))} — {safe_str(rr.get('Task',''))} "
                        f"(Task ID:{safe_str(rr.get('Task_ID',''))})"
                    )
                    _append_parts_order_from_maintenance(
                        part_name=part_name,
                        details=details,
                        actor=actor,
                        project_name="Maintenance",
                        company="",
                        maintenance_component=safe_str(rr.get("Component", "")),
                        maintenance_task=safe_str(rr.get("Task", "")),
                        maintenance_task_id=safe_str(rr.get("Task_ID", "")),
                        wait_id="",
                    )
                    created += 1
                return created

            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("🧾 Order Checked (Preview)", key="maint_day_order_missing_selected", use_container_width=True):
                    if not selected_tasks:
                        st.error("Select at least one task.")
                    else:
                        pick_idx = [task_map[x] for x in selected_tasks if x in task_map]
                        preview_src = missing_df.loc[pick_idx].copy() if pick_idx else missing_df.iloc[0:0].copy()
                        preview_df = _build_orders_preview(preview_src, _load_active_orders_df())
                        created = _create_orders_from_preview(preview_df, checked_keys)
                        if created > 0:
                            st.success(f"Created {created} part order(s).")
                        else:
                            st.info("No new orders created (none checked / already active).")
                        st.rerun()
            with b2:
                if st.button("🧾 Order Missing (All)", key="maint_day_order_missing_all", use_container_width=True):
                    created = _create_orders_for_rows(missing_df)
                    if created > 0:
                        st.success(f"Created {created} part order(s).")
                    else:
                        st.info("No new orders created (already active or none).")
                    st.rerun()
            with b3:
                if st.button("📦 Open Tower Parts Intake", key="maint_open_tower_parts_intake", use_container_width=True):
                    st.session_state["selected_tab"] = "🛠️ Tower Parts"
                    st.rerun()
        else:
            st.success("All selected-day tasks are parts-ready.")

    def _append_parts_order_from_maintenance(
        *,
        part_name: str,
        details: str,
        actor: str,
        project_name: str = "",
        company: str = "",
        maintenance_component: str = "",
        maintenance_task: str = "",
        maintenance_task_id: str = "",
        wait_id: str = "",
    ) -> None:
        base_cols = [
            "Status", "Part Name", "Serial Number",
            "Project Name", "Details",
            "Opened By",
            "Approval Requested From",
            "Approved", "Approved By", "Approval Date",
            "Received Date", "Received State",
            "Ordered By", "Date Ordered", "Company",
            "Inventory Synced",
            "Maintenance Component", "Maintenance Task", "Maintenance Task ID", "Wait ID",
        ]
        os.makedirs(os.path.dirname(PARTS_ORDERS_CSV), exist_ok=True)
        if os.path.exists(PARTS_ORDERS_CSV):
            try:
                orders_df = _read_csv_keepna(PARTS_ORDERS_CSV)
            except Exception:
                orders_df = pd.DataFrame(columns=base_cols)
        else:
            orders_df = pd.DataFrame(columns=base_cols)

        for c in base_cols:
            if c not in orders_df.columns:
                orders_df[c] = ""

        row = {
            "Status": "Opened",
            "Part Name": safe_str(part_name).strip(),
            "Serial Number": "",
            "Project Name": safe_str(project_name).strip(),
            "Details": safe_str(details).strip(),
            "Opened By": safe_str(actor).strip(),
            "Approval Requested From": "",
            "Approved": "No",
            "Approved By": "",
            "Approval Date": "",
            "Received Date": "",
            "Received State": "",
            "Ordered By": "",
            "Date Ordered": "",
            "Company": safe_str(company).strip(),
            "Inventory Synced": "",
            "Maintenance Component": safe_str(maintenance_component).strip(),
            "Maintenance Task": safe_str(maintenance_task).strip(),
            "Maintenance Task ID": safe_str(maintenance_task_id).strip(),
            "Wait ID": safe_str(wait_id).strip(),
        }
        orders_df = pd.concat([orders_df[base_cols], pd.DataFrame([row])[base_cols]], ignore_index=True)
        orders_df.to_csv(PARTS_ORDERS_CSV, index=False)

    def _apply_done_rows(
        done_rows,
        *,
        dfm=None,
        used_parts_map=None,
        auto_consume_required=False,
        current_date,
        current_draw_count,
        actor,
        con,
        read_file,
        write_file,
        normalize_df,
        templateize_df,
        pick_current_hours,
        mode_norm,
    ):
        if done_rows is None or done_rows.empty:
            st.info("No tasks selected.")
            return

        updated = 0
        policy_updates = 0
        problems = []
    
        # ---- Update source files ----
        for src, grp in done_rows.groupby("Source_File"):
            path = os.path.join(MAINT_FOLDER, src)
            try:
                raw = read_file(path)
                df_src = normalize_df(raw)
    
                for _, r in grp.iterrows():
                    mask = (
                        df_src["Component"].astype(str).eq(str(r.get("Component", ""))) &
                        df_src["Task"].astype(str).eq(str(r.get("Task", "")))
                    )
                    if not mask.any():
                        continue

                    # Auto cadence policy by groups (safe, only when unambiguous).
                    pol = infer_group_policy(r)
                    if pol is not None:
                        for c in [
                            "Tracking_Mode",
                            "Interval_Value",
                            "Interval_Unit",
                            "Last_Done_Hours_UV1",
                            "Last_Done_Hours_UV2",
                            "Last_Done_Hours_Furnace",
                            "Trigger_Modes",
                        ]:
                            if c not in df_src.columns:
                                df_src[c] = ""
                        df_src.loc[mask, "Tracking_Mode"] = safe_str(pol.get("tracking_mode", "")).strip()
                        p_val = pol.get("interval_value", None)
                        if p_val is not None:
                            df_src.loc[mask, "Interval_Value"] = p_val
                        else:
                            # Hours policy: only fill if missing.
                            cur_iv = pd.to_numeric(df_src.loc[mask, "Interval_Value"], errors="coerce")
                            if cur_iv.isna().all():
                                df_src.loc[mask, "Interval_Value"] = float(warn_hours)
                        df_src.loc[mask, "Interval_Unit"] = safe_str(pol.get("interval_unit", "")).strip()
                        policy_updates += int(mask.sum())

                    mode_src = safe_str(pol.get("tracking_mode", "")) if pol is not None else safe_str(r.get("Tracking_Mode", ""))
                    mode = mode_norm(mode_src)
                    trig_modes_raw = safe_str(r.get("Trigger_Modes", "")).strip()
                    trig_modes = [
                        mode_norm(x) for x in trig_modes_raw.replace(";", ",").replace("|", ",").split(",")
                        if mode_norm(x) in ("hours", "draws", "calendar")
                    ]
                    if not trig_modes:
                        trig_modes = [mode]

                    if "calendar" in trig_modes:
                        df_src.loc[mask, "Last_Done_Date"] = current_date.isoformat()
                    if "hours" in trig_modes:
                        df_src.loc[mask, "Last_Done_Hours_Furnace"] = float(furnace_hours)
                        df_src.loc[mask, "Last_Done_Hours_UV1"] = float(uv1_hours)
                        df_src.loc[mask, "Last_Done_Hours_UV2"] = float(uv2_hours)
                        df_src.loc[mask, "Last_Done_Hours"] = float(pick_current_hours(r.get("Hours_Source", "")))
                    if "draws" in trig_modes:
                        df_src.loc[mask, "Last_Done_Draw"] = int(current_draw_count)
    
                    updated += int(mask.sum())
    
                out = templateize_df(df_src, list(raw.columns))
                write_file(path, out)
    
            except Exception as e:
                problems.append((src, str(e)))
    
        st.success(f"Updated {updated} task(s).")
        if policy_updates > 0:
            st.caption(f"🔁 Auto cadence policy applied for {policy_updates} task row(s) from task groups.")
    
        # ---- Log to DuckDB + CSV line log ----
        now_dt = dt.datetime.now()
        csv_rows = []
    
        for _, r in done_rows.iterrows():
            action_id = int(time.time() * 1000)
            mode = mode_norm(r.get("Tracking_Mode", ""))
    
            hs_raw = r.get("Hours_Source", "")
            hs_str = "" if hs_raw is None or (isinstance(hs_raw, float) and np.isnan(hs_raw)) else str(hs_raw).strip()
            if hs_str == "":
                hs_str = "FURNACE"
    
            # ALWAYS snapshot hours (for filtering/search)
            hours_snapshot = float(pick_current_hours(hs_str))
    
            done_hours_db = None
            done_draw = None
            if mode == "hours":
                done_hours_db = hours_snapshot
            elif mode == "draws":
                done_draw = int(current_draw_count)
    
            try:
                con.execute("""
                    INSERT INTO maintenance_actions
                    (action_id, action_ts, component, task, task_id, tracking_mode, hours_source,
                     done_date, done_hours, done_draw, source_file, actor, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    action_id,
                    now_dt,
                    str(r.get("Component", "")),
                    str(r.get("Task", "")),
                    str(r.get("Task_ID", "")),
                    str(r.get("Tracking_Mode", "")),
                    hs_str,
                    current_date,
                    done_hours_db,
                    done_draw,
                    str(r.get("Source_File", "")),
                    str(actor),
                    "",
                ])
            except Exception as e:
                st.warning(f"DuckDB insert failed (still saving CSV log): {e}")
    
            csv_rows.append({
                "maintenance_id": action_id,
                "maintenance_ts": now_dt,
                "maintenance_component": str(r.get("Component", "")),
                "maintenance_task": str(r.get("Task", "")),
                "maintenance_task_id": str(r.get("Task_ID", "")),
                "maintenance_mode": str(r.get("Tracking_Mode", "")),
                "maintenance_hours_source": hs_str,
                "maintenance_done_date": current_date,
                "maintenance_done_hours": hours_snapshot,  # ✅ always filled
                "maintenance_done_draw": done_draw if done_draw is not None else "",
                "maintenance_source_file": str(r.get("Source_File", "")),
                "maintenance_actor": str(actor),
                "maintenance_note": "",
            })
    
        if csv_rows:
            try:
                _append_csv(MAINT_ACTIONS_CSV, MAINT_ACTIONS_COLS, pd.DataFrame(csv_rows))
                st.caption("✅ Logged maintenance lines to maintenance_actions_log.csv")
            except Exception as e:
                st.error(f"Failed writing maintenance_actions_log.csv: {e}")
    
        if problems:
            st.warning("Some files had issues:")
            st.dataframe(pd.DataFrame(problems, columns=["File", "Error"]), use_container_width=True)

        # Optional inventory consume:
        # - preferred: explicit used_parts_map per task ("part=qty; part2=qty")
        # - fallback (if enabled): 1x each Required_Parts item
        try:
            from helpers.parts_inventory import decrement_part, is_non_consumable_part

            def _parts_list(v):
                s = safe_str(v).strip()
                if not s:
                    return []
                parts = []
                for p in s.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
                    pv = p.strip()
                    if pv:
                        parts.append(pv)
                uniq = []
                seen = set()
                for p in parts:
                    lk = p.lower()
                    if lk not in seen:
                        uniq.append(p)
                        seen.add(lk)
                return uniq

            def _task_key_from_row(r):
                return (
                    safe_str(r.get("Component", "")).strip().lower(),
                    safe_str(r.get("Task", "")).strip().lower(),
                    safe_str(r.get("Task_ID", "")).strip().lower(),
                )

            def _parse_used_parts_text(txt: str):
                """
                Format examples:
                - bearing A=2
                - grease tube=0.5; filter=1
                - valve, o-ring=3
                """
                s = safe_str(txt).strip()
                if not s:
                    return []
                out = []
                for token in s.replace("\n", ";").split(";"):
                    t = token.strip()
                    if not t:
                        continue
                    name = t
                    qty = 1.0
                    if "=" in t:
                        name, q = t.split("=", 1)
                        name = name.strip()
                        try:
                            qty = float(str(q).strip())
                        except Exception:
                            qty = 1.0
                    elif ":" in t:
                        name, q = t.split(":", 1)
                        name = name.strip()
                        try:
                            qty = float(str(q).strip())
                        except Exception:
                            qty = 1.0
                    if name and qty > 0:
                        out.append((name, float(qty)))
                return out

            consumed = 0
            tools_used = 0
            missing = []
            used_parts_map = used_parts_map or {}
            for _, r in done_rows.iterrows():
                key = _task_key_from_row(r)
                # If task has active reservation, consume reservation and skip extra auto decrement.
                try:
                    c_res = consume_task_reservations(
                        reservations_csv_path=MAINT_RESERVATIONS_CSV,
                        task_id=safe_str(r.get("Task_ID", "")),
                        component=safe_str(r.get("Component", "")),
                        task=safe_str(r.get("Task", "")),
                        actor=safe_str(actor),
                        note="Consumed on maintenance DONE",
                    )
                    if int(c_res.get("consumed", 0)) > 0:
                        continue
                except Exception:
                    pass
                explicit = _parse_used_parts_text(used_parts_map.get(key, ""))
                parts_to_use = []
                if explicit:
                    parts_to_use = explicit
                elif auto_consume_required:
                    # For conditional tasks ("if needed"), require explicit used-parts input.
                    if is_parts_conditional(safe_str(r.get("Task", ""))):
                        continue
                    required = safe_str(r.get("Required_Parts", "")).strip()
                    if not required and dfm is not None and not dfm.empty:
                        m = dfm[
                            dfm["Component"].astype(str).eq(str(r.get("Component", "")))
                            & dfm["Task"].astype(str).eq(str(r.get("Task", "")))
                        ]
                        if not m.empty:
                            required = safe_str(m.iloc[0].get("Required_Parts", "")).strip()
                    parts_to_use = [(p, 1.0) for p in _parts_list(required)]

                for p, q in parts_to_use:
                    if is_non_consumable_part(P.parts_inventory_csv, p):
                        tools_used += 1
                        continue
                    ok = decrement_part(P.parts_inventory_csv, p, qty=float(q))
                    if ok:
                        consumed += float(q)
                    else:
                        missing.append(p)

            if consumed > 0:
                st.caption(f"📦 Inventory consumed from maintenance usage: {consumed:.2f}.")
            if tools_used > 0:
                st.caption(f"🛠️ Tools used (non-consumable): {tools_used}.")
            if missing:
                miss = sorted(set(missing))
                st.warning("Inventory missing rows for required parts: " + ", ".join(miss))
        except Exception as e:
            st.warning(f"Inventory auto-consume skipped: {e}")

        try:
            ok_n, fail_n = set_tasks_state(
                MAINT_TASK_STATE_CSV,
                done_rows,
                "DONE",
                actor=safe_str(actor),
                note="Completed in maintenance apply-done",
                force=True,
            )
            if ok_n > 0:
                st.caption(f"Lifecycle updated to DONE for {ok_n} task(s).")
            if fail_n > 0:
                st.warning(f"Lifecycle update failed for {fail_n} task(s).")
        except Exception as e:
            st.warning(f"Lifecycle update skipped: {e}")

        st.rerun()

    def render_maintenance_apply_done(
        edited,
        *,
        dfm,
        current_date,
        current_draw_count,
        actor,
        MAINT_FOLDER,
        con,
        read_file,
        write_file,
        normalize_df,
        templateize_df,
        pick_current_hours,
        mode_norm,
    ):
        done_preview = edited[edited["Done_Now"] == True].copy()
        if done_preview.empty:
            st.info("Select at least one task with `Done now`.")
            return

        st.caption("Optional parts usage append (recommended): use `part=qty; part2=qty` per task.")
        usage_df = done_preview[["Component", "Task", "Task_ID"]].copy()
        usage_df["Used Parts (optional)"] = ""
        usage_edited = st.data_editor(
            usage_df,
            use_container_width=True,
            height=min(220, 80 + 36 * len(usage_df)),
            num_rows="fixed",
            disabled=["Component", "Task", "Task_ID"],
            key="maint_done_used_parts_editor",
        )
        auto_fallback = st.checkbox(
            "If no usage entered, consume 1x each Required_Parts",
            value=False,
            key="maint_done_auto_consume_required",
        )

        if not st.button("✅ Apply 'Done Now' updates", type="primary"):
            return
        try:
            first_row = done_preview.iloc[0] if not done_preview.empty else {}
            record_activity_start(
                indicator_json_path=P.activity_indicator_json,
                events_csv_path=P.activity_events_csv,
                activity_type="maintenance",
                title=f"Maintenance Start | batch {len(done_preview)} task(s)",
                actor=safe_str(actor),
                source="maintenance_done_apply",
                meta={
                    "batch_count": int(len(done_preview)),
                    "first_task_id": safe_str(first_row.get("Task_ID", "")) if hasattr(first_row, "get") else "",
                    "first_component": safe_str(first_row.get("Component", "")) if hasattr(first_row, "get") else "",
                },
            )
        except Exception:
            pass

        done_rows = done_preview.copy()
        used_parts_map = {}
        for _, rr in usage_edited.iterrows():
            k = (
                safe_str(rr.get("Component", "")).strip().lower(),
                safe_str(rr.get("Task", "")).strip().lower(),
                safe_str(rr.get("Task_ID", "")).strip().lower(),
            )
            used_parts_map[k] = safe_str(rr.get("Used Parts (optional)", "")).strip()

        _apply_done_rows(
            done_rows,
            dfm=dfm,
            used_parts_map=used_parts_map,
            auto_consume_required=bool(auto_fallback),
            current_date=current_date,
            current_draw_count=current_draw_count,
            actor=actor,
            con=con,
            read_file=read_file,
            write_file=write_file,
            normalize_df=normalize_df,
            templateize_df=templateize_df,
            pick_current_hours=pick_current_hours,
            mode_norm=mode_norm,
        )
    
    # =========================================================
    # History viewer (DuckDB + CSV)
    # =========================================================
    def render_maintenance_history(con, limit: int = 200, height: int = 320):
        with st.expander("🗃️ Maintenance history (DuckDB)", expanded=False):
            try:
                recent = con.execute(f"""
                    SELECT action_ts, component, task, tracking_mode, hours_source,
                           done_date, done_hours, done_draw, actor, source_file
                    FROM maintenance_actions
                    ORDER BY action_ts DESC
                    LIMIT {int(limit)}
                """).fetchdf()
    
                if not recent.empty:
                    recent["done_date"] = pd.to_datetime(recent["done_date"], errors="coerce").dt.date
                    recent["action_ts"] = pd.to_datetime(recent["action_ts"], errors="coerce")
    
                st.dataframe(recent, use_container_width=True, height=int(height))
            except Exception as e:
                st.warning(f"DB read failed: {e}")
    
        with st.expander("🧾 Maintenance lines (CSV log)", expanded=False):
            if not os.path.isfile(MAINT_ACTIONS_CSV):
                st.info("No maintenance_actions_log.csv yet (mark something done first).")
            else:
                try:
                    df = pd.read_csv(MAINT_ACTIONS_CSV)
                    st.dataframe(df.tail(250), use_container_width=True, height=360)
                except Exception as e:
                    st.warning(f"CSV read failed: {e}")
    
    def render_gas_report(LOGS_FOLDER: str):
        """
        Gas usage report (MFC ACTUAL)
        Assumptions:
        - MFC columns contain BOTH 'MFC' and 'Actual'
        - Units are SLM (Standard Liters per Minute)
        - Integration: SL = Σ(SLM × dt_minutes)
        """
    
        st.markdown("---")
        st.subheader("🧪 Gas usage report (MFC actual, SLM)")
    
        show = st.toggle("Show gas report", value=False, key="gasrep_show")
        if not show:
            st.caption("(Hidden by default to keep UI light)")
            return
    
        if not os.path.isdir(LOGS_FOLDER):
            st.warning(f"Logs folder not found: {LOGS_FOLDER}")
            return
    
        # --------------------------------------------------
        # Collect log files
        # --------------------------------------------------
        csv_files = sorted(
            [os.path.join(LOGS_FOLDER, f)
             for f in os.listdir(LOGS_FOLDER)
             if f.lower().endswith(".csv") and not f.startswith("~$")],
            key=lambda p: os.path.getmtime(p),
        )
    
        if not csv_files:
            st.info("No log CSV files found.")
            return
    
        st.caption(f"Found {len(csv_files)} log files.")
    
        # --------------------------------------------------
        # Reports folder (auto-save)
        # --------------------------------------------------
        REPORT_DIR = P.gas_reports_dir
        os.makedirs(REPORT_DIR, exist_ok=True)
        st.caption(f"Reports folder: {REPORT_DIR}")
    
        # --------------------------------------------------
        # Time window selector
        # --------------------------------------------------
        st.markdown("#### Time window")
        c1, c2, c3, c4 = st.columns([1,1,1,2])
    
        st.session_state.setdefault("gasrep_window_days", 30)
    
        with c1:
            if st.button("Last 7 days", key="gasrep_btn_7", use_container_width=True):
                st.session_state["gasrep_window_days"] = 7
        with c2:
            if st.button("Last 30 days", key="gasrep_btn_30", use_container_width=True):
                st.session_state["gasrep_window_days"] = 30
        with c3:
            if st.button("Last 90 days", key="gasrep_btn_90", use_container_width=True):
                st.session_state["gasrep_window_days"] = 90
        with c4:
            st.caption(f"Selected: {st.session_state['gasrep_window_days']} days")
    
        window_days = int(st.session_state.get("gasrep_window_days", 30))
    
        # --------------------------------------------------
        # Helpers
        # --------------------------------------------------
        def _norm(s):
            return str(s).strip().lower()
    
        def _find_time_col(cols):
            for c in cols:
                if _norm(c) in {"date/time","datetime","timestamp","date time"}:
                    return c
            for c in cols:
                if "date" in _norm(c) and "time" in _norm(c):
                    return c
            return None
    
        def _is_mfc_actual(c):
            s = _norm(c)
            return ("mfc" in s) and ("actual" in s)
    
        # --------------------------------------------------
        # Scan logs and integrate usage
        # --------------------------------------------------
        rows = []
    
        for p in csv_files:
            try:
                df = pd.read_csv(p)
                if df is None or df.empty:
                    continue
    
                time_col = _find_time_col(df.columns)
                if not time_col:
                    continue
    
                t = pd.to_datetime(df[time_col], errors="coerce", dayfirst=True)
                if t.isna().all():
                    continue
    
                df["__t"] = t
                df = df.dropna(subset=["__t"]).sort_values("__t").reset_index(drop=True)
                if len(df) < 2:
                    continue
    
                # dt in minutes
                dt_min = df["__t"].diff().dt.total_seconds() / 60.0
                dt_min = dt_min.fillna(0.0).clip(lower=0.0)
    
                mfc_cols = [c for c in df.columns if _is_mfc_actual(c)]
                if not mfc_cols:
                    continue
    
                total_sl = 0.0
                for c in mfc_cols:
                    flow_slm = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                    total_sl += float((flow_slm * dt_min).sum())
    
                rows.append({
                    "log_file": os.path.basename(p),
                    "start_time": df["__t"].iloc[0],
                    "end_time": df["__t"].iloc[-1],
                    "duration_min": float(dt_min.sum()),
                    "Total SL": total_sl,
                })
            except Exception:
                continue
    
        if not rows:
            st.info("No usable MFC ACTUAL data detected in logs.")
            return
    
        usage = pd.DataFrame(rows)
        usage["start_time"] = pd.to_datetime(usage["start_time"], errors="coerce")
        usage = usage.sort_values("start_time").reset_index(drop=True)
    
        # --------------------------------------------------
        # Apply time window
        # --------------------------------------------------
        latest = usage["start_time"].max()
        if pd.isna(latest):
            latest = pd.Timestamp.now()
    
        t0 = latest - pd.Timedelta(days=window_days)
        usage = usage[usage["start_time"] >= t0]
    
        if usage.empty:
            st.warning("No logs in selected window.")
            return
    
        # --------------------------------------------------
        # Summary metrics
        # --------------------------------------------------
        total_sl = float(usage["Total SL"].sum())
        total_hours = float(usage["duration_min"].sum()) / 60.0
        avg_slm = (total_sl / usage["duration_min"].sum()) if usage["duration_min"].sum() > 0 else 0.0
    
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Gas Used (SL)", f"{total_sl:,.2f}")
        m2.metric("Total Duration (hours)", f"{total_hours:,.2f}")
        m3.metric("Average Flow (SLM)", f"{avg_slm:,.3f}")
    
        # --------------------------------------------------
        # Period reports
        # --------------------------------------------------
        tmp = usage.copy()
        tmp["Week"] = tmp["start_time"].dt.to_period("W").astype(str)
        tmp["Month"] = tmp["start_time"].dt.to_period("M").astype(str)
        tmp["Quarter"] = tmp["start_time"].dt.to_period("Q").astype(str)
    
        week_rep = tmp.groupby("Week", as_index=False)["Total SL"].sum().sort_values("Week")
        month_rep = tmp.groupby("Month", as_index=False)["Total SL"].sum().sort_values("Month")
        quarter_rep = tmp.groupby("Quarter", as_index=False)["Total SL"].sum().sort_values("Quarter")
    
        t1, t2, t3 = st.tabs(["Weekly", "Monthly", "3 Months"])
        with t1:
            st.dataframe(week_rep, use_container_width=True, hide_index=True)
        with t2:
            st.dataframe(month_rep, use_container_width=True, hide_index=True)
        with t3:
            st.dataframe(quarter_rep, use_container_width=True, hide_index=True)
    
        # --------------------------------------------------
        # Per log breakdown
        # --------------------------------------------------
        st.markdown("#### Per log file breakdown")
        st.dataframe(usage.tail(250), use_container_width=True, height=350)
    
        # --------------------------------------------------
        # Auto-save reports (FULL history from folder, not only selected window)
        # --------------------------------------------------
        try:
            full_usage = pd.DataFrame(rows)
            full_usage["start_time"] = pd.to_datetime(full_usage["start_time"], errors="coerce")
            full_usage["end_time"] = pd.to_datetime(full_usage["end_time"], errors="coerce")
            full_usage = full_usage.dropna(subset=["start_time"]).sort_values("start_time").reset_index(drop=True)
    
            if not full_usage.empty:
                full_usage["Week"] = full_usage["start_time"].dt.to_period("W").astype(str)
                full_usage["Month"] = full_usage["start_time"].dt.to_period("M").astype(str)
                full_usage["Quarter"] = full_usage["start_time"].dt.to_period("Q").astype(str)
    
                # 1) Per-log summary
                out_all_logs = full_usage[[
                    "log_file", "start_time", "end_time", "duration_min", "Total SL", "Week", "Month", "Quarter"
                ]].copy()
                p1 = os.path.join(REPORT_DIR, "gas_summary_all_logs.csv")
                out_all_logs.to_csv(p1, index=False)
    
                # 2) Weekly totals
                week_agg = full_usage.groupby("Week", as_index=False).agg(total_sl=("Total SL", "sum"))
                week_agg = week_agg.sort_values("Week").reset_index(drop=True)
                p2 = os.path.join(REPORT_DIR, "gas_weekly_totals.csv")
                week_agg.to_csv(p2, index=False)
    
                # 3) Monthly totals + avg SLM for month
                month_agg = full_usage.groupby("Month", as_index=False).agg(
                    total_sl=("Total SL", "sum"),
                    total_minutes=("duration_min", "sum"),
                    n_logs=("log_file", "count"),
                    first_start=("start_time", "min"),
                    last_end=("end_time", "max"),
                )
                month_agg["avg_slm"] = month_agg.apply(
                    lambda r: (float(r["total_sl"]) / float(r["total_minutes"])) if float(r["total_minutes"]) > 0 else 0.0,
                    axis=1,
                )
                month_agg = month_agg.sort_values("Month").reset_index(drop=True)
                p3 = os.path.join(REPORT_DIR, "gas_monthly_totals.csv")
                month_agg.to_csv(p3, index=False)
    
                # 4) Quarterly totals
                q_agg = full_usage.groupby("Quarter", as_index=False).agg(total_sl=("Total SL", "sum"))
                q_agg = q_agg.sort_values("Quarter").reset_index(drop=True)
                p4 = os.path.join(REPORT_DIR, "gas_quarterly_totals.csv")
                q_agg.to_csv(p4, index=False)
    
                # Missing months detection (between first and last month)
                first_m = pd.Period(full_usage["start_time"].min(), freq="M")
                last_m = pd.Period(full_usage["start_time"].max(), freq="M")
                expected = [str(p) for p in pd.period_range(first_m, last_m, freq="M")]
                present = set(month_agg["Month"].astype(str).tolist())
                missing = [m for m in expected if m not in present]
    
                st.success("✅ Gas reports saved automatically")
                st.code("\n".join([p1, p2, p3, p4]))
    
                if missing:
                    st.warning("Missing months (no logs found): " + ", ".join(missing))
                else:
                    st.caption("No missing months detected between first and last log month.")
            else:
                st.info("No full-history rows available to save reports.")
        except Exception as e:
            st.warning(f"Auto-save failed: {e}")
    
        st.caption("Units: MFC Actual assumed SLM. Integrated to SL via SLM × dt(minutes).")
    
    # =========================================================
    # ✅ Faults section
    def render_faults_section(con, MAINT_FOLDER, actor):
        st.subheader("🚨 Faults / Incidents")
    
        faults_csv = _read_csv_safe(FAULTS_CSV, FAULTS_COLS)
        actions_csv = _read_csv_safe(FAULTS_ACTIONS_CSV, FAULTS_ACTIONS_COLS)
        state_map = _latest_fault_state(actions_csv)
    
        if not faults_csv.empty:
            faults_csv["fault_id"] = pd.to_numeric(faults_csv["fault_id"], errors="coerce")
            faults_csv = faults_csv.dropna(subset=["fault_id"]).copy()
            faults_csv["fault_id"] = faults_csv["fault_id"].astype(int)
            faults_csv["fault_ts"] = pd.to_datetime(faults_csv["fault_ts"], errors="coerce")
    
            faults_csv["_is_closed"] = faults_csv["fault_id"].apply(
                lambda fid: bool(state_map.get(int(fid), {}).get("is_closed", False))
            )
            faults_csv["_last_action_ts"] = faults_csv["fault_id"].apply(
                lambda fid: state_map.get(int(fid), {}).get("last_ts", None)
            )
            faults_csv["_last_action_type"] = faults_csv["fault_id"].apply(
                lambda fid: state_map.get(int(fid), {}).get("last_type", "")
            )
            faults_csv["_last_action_actor"] = faults_csv["fault_id"].apply(
                lambda fid: state_map.get(int(fid), {}).get("last_actor", "")
            )
            faults_csv["_last_fix"] = faults_csv["fault_id"].apply(
                lambda fid: state_map.get(int(fid), {}).get("last_fix", "")
            )
        else:
            faults_csv = pd.DataFrame(columns=FAULTS_COLS + ["_is_closed", "_last_action_ts", "_last_action_type", "_last_action_actor", "_last_fix"])
    
        # ---- Log a new fault ----
        with st.expander("➕ Log a new fault", expanded=False):
            c1, c2, c3 = st.columns([1.2, 1, 1])
            with c1:
                comp_list = (
                    dfm["Component"]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .unique()
                    .tolist()
                )
                comp_list = sorted([c for c in comp_list if c])
                comp_options = comp_list + ["Other (custom)"]
    
                selected_comp = st.selectbox(
                    "Fault component",
                    options=comp_options,
                    key="fault_component_select"
                )
    
                if selected_comp == "Other (custom)":
                    fault_component = st.text_input(
                        "Custom component name",
                        key="fault_component_custom"
                    )
                else:
                    fault_component = selected_comp
            with c2:
                severity = st.selectbox("Severity", ["low", "medium", "high", "critical"], index=1, key="fault_sev_in")
            with c3:
                related_draw = st.text_input("Related draw (optional)", placeholder="e.g. FP0888_1", key="fault_draw_in")
    
            title = st.text_input("Fault title", placeholder="Short title", key="fault_title_in")
            desc = st.text_area("Fault description", placeholder="What happened? what did you do? what to check next time?", height=120, key="fault_desc_in")
    
            cA, cB = st.columns([1, 1])
            with cA:
                src_file = st.text_input("Source file (optional)", placeholder="e.g. faults.xlsx / email.pdf / photo.jpg", key="fault_src_in")
            with cB:
                st.caption("Saved as BOTH DuckDB + faults_log.csv")
    
            if st.button("➕ Log fault", type="primary", use_container_width=True, key="fault_add_btn"):
                if not str(fault_component).strip():
                    st.warning("Fault component is required.")
                    st.stop()
                if not str(title).strip() and not str(desc).strip():
                    st.warning("Give at least a title or description.")
                    st.stop()
    
                now_dt = dt.datetime.now()
                fid = int(time.time() * 1000)
    
                try:
                    con.execute("""
                        INSERT INTO faults_events
                        (fault_id, fault_ts, component, title, description, severity, actor, source_file, related_draw)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        fid, now_dt,
                        str(fault_component), str(title), str(desc),
                        str(severity), str(actor), str(src_file), str(related_draw)
                    ])
                except Exception as e:
                    st.warning(f"DuckDB insert failed (still saving CSV log): {e}")
    
                row = pd.DataFrame([{
                    "fault_id": fid,
                    "fault_ts": now_dt,
                    "fault_component": str(fault_component),
                    "fault_title": str(title),
                    "fault_description": str(desc),
                    "fault_severity": str(severity),
                    "fault_actor": str(actor),
                    "fault_source_file": str(src_file),
                    "fault_related_draw": str(related_draw),
                }])
                try:
                    _append_csv(FAULTS_CSV, FAULTS_COLS, row)
                    st.success("Fault logged.")
                except Exception as e:
                    st.error(f"Failed writing faults_log.csv: {e}")
    
                st.rerun()
    
        # ---- Open faults list ----
        with st.expander("🔓 Open faults", expanded=False):
            open_df = faults_csv[faults_csv["_is_closed"] == False].copy()
            open_df = open_df.sort_values("fault_ts", ascending=False)

            if open_df.empty:
                st.success("No open faults 👍")
            else:
                for _, r in open_df.iterrows():
                    fid = int(r["fault_id"])
                    comp = safe_str(r.get("fault_component", ""))
                    sev = safe_str(r.get("fault_severity", ""))
                    title = safe_str(r.get("fault_title", "")) or "Fault"
                    ts = safe_str(r.get("fault_ts", ""))

                    c1, c2, c3 = st.columns([3.4, 1.1, 1.1])
                    with c1:
                        st.markdown(f"**[{sev.upper()}] {comp} — {title}**")
                        st.caption(f"ID: `{fid}`  |  Time: {ts}")

                    with c2:
                        @st.dialog(f"Close fault: {comp} — {title} (#{fid})")
                        def _dlg_close():
                            fix = st.text_input("Fix summary (short)", key=f"fix_sum__{fid}")
                            note = st.text_area("Closure notes", height=120, key=f"fix_note__{fid}")
                            if st.button("✅ Close fault", type="primary", use_container_width=True, key=f"close_do__{fid}"):
                                _write_fault_action(con, fault_id=fid, action_type="close", actor=actor, note=note, fix_summary=fix)
                                st.success("Closed.")
                                st.rerun()

                        if st.button("✅ Close", use_container_width=True, key=f"btn_close__{fid}"):
                            _dlg_close()

                    with c3:
                        @st.dialog(f"Add note: #{fid}")
                        def _dlg_note():
                            note = st.text_area("Note", height=120, key=f"note_txt__{fid}")
                            if st.button("➕ Save note", type="primary", use_container_width=True, key=f"note_do__{fid}"):
                                _write_fault_action(con, fault_id=fid, action_type="note", actor=actor, note=note, fix_summary="")
                                st.success("Saved note.")
                                st.rerun()

                        if st.button("📝 Note", use_container_width=True, key=f"btn_note__{fid}"):
                            _dlg_note()

                    desc_txt = safe_str(r.get("fault_description", "")) or "—"
                    st.caption(f"Details: {desc_txt}")
                    st.caption(f"Source file: {safe_str(r.get('fault_source_file',''))} | Related draw: {safe_str(r.get('fault_related_draw',''))}")

                    st.divider()
    
        # ---- All faults table + reopen ----
        with st.expander("📜 All faults (table)", expanded=False):
            df_all = faults_csv.copy()
            if df_all.empty:
                st.info("No faults yet.")
            else:
                df_all["Status"] = np.where(df_all["_is_closed"], "Closed", "Open")
                df_all["Last Action"] = df_all["_last_action_type"]
                df_all["Last Action By"] = df_all["_last_action_actor"]
                df_all["Last Fix Summary"] = df_all["_last_fix"]
                show = df_all[[
                    "fault_ts", "Status", "fault_id", "fault_component", "fault_severity",
                    "fault_title", "fault_actor", "fault_related_draw",
                    "Last Action", "Last Action By", "Last Fix Summary"
                ]].copy()
                st.dataframe(show, use_container_width=True, height=360, hide_index=True)
    
                closed_ids = df_all[df_all["_is_closed"] == True]["fault_id"].astype(int).tolist()
                if closed_ids:
                    st.markdown("##### Reopen a fault")
                    pick = st.selectbox("Closed fault ID", options=[""] + [str(x) for x in closed_ids], key="reopen_pick")
                    if pick and st.button("♻️ Reopen", use_container_width=True, key="reopen_btn"):
                        _write_fault_action(con, fault_id=int(pick), action_type="reopen", actor=actor, note="Reopened", fix_summary="")
                        st.success("Reopened.")
                        st.rerun()
    
        with st.expander("🧾 Fault actions (CSV log)", expanded=False):
            if not os.path.isfile(FAULTS_ACTIONS_CSV):
                st.info("No faults_actions_log.csv yet (close/reopen/note first).")
            else:
                try:
                    df = pd.read_csv(FAULTS_ACTIONS_CSV)
                    st.dataframe(df.tail(300), use_container_width=True, height=360)
                except Exception as e:
                    st.warning(f"Fault actions CSV read failed: {e}")
    
    # =========================================================
    # Load report + tasks editor
    # =========================================================
    def render_maintenance_load_report(files, load_errors):
        with st.expander("Load report", expanded=False):
            try:
                st.write("Loaded files:", sorted(list(files or [])))
            except Exception:
                st.write("Loaded files:", files)
    
            if load_errors:
                st.warning("Some files failed to load:")
                st.dataframe(pd.DataFrame(load_errors, columns=["File", "Error"]), use_container_width=True)
    
    def render_maintenance_tasks_editor(
        MAINT_FOLDER,
        files,
        read_file,
        write_file,
        normalize_df,
        templateize_df,
    ):
        with st.expander("📝 Maintenance tasks editor (source files)", expanded=False):
            st.caption("Edits the selected maintenance file (Excel/CSV) and saves back.")
            pick = st.selectbox("Select maintenance file", options=sorted(files), key="maint_edit_file_pick")
            if not pick:
                return
            path = os.path.join(MAINT_FOLDER, pick)
            try:
                raw = read_file(path)
                if raw is None or raw.empty:
                    st.info("File is empty.")
                    return
                df = normalize_df(raw)

                show_cols = [c for c in df.columns if c != "Source_File"]
                base_for_editor = df[show_cols].copy()
                if "Required_Parts" not in base_for_editor.columns:
                    base_for_editor["Required_Parts"] = ""
                if "Mandatory_Parts" not in base_for_editor.columns:
                    base_for_editor["Mandatory_Parts"] = base_for_editor["Required_Parts"]
                if "Conditional_Parts" not in base_for_editor.columns:
                    base_for_editor["Conditional_Parts"] = ""
                if "Preparation_Lead_Days" not in base_for_editor.columns:
                    base_for_editor["Preparation_Lead_Days"] = 7
                if "Parts_Check_Lead_Days" not in base_for_editor.columns:
                    base_for_editor["Parts_Check_Lead_Days"] = 21
                if "Auto_Order_Mandatory_Parts" not in base_for_editor.columns:
                    base_for_editor["Auto_Order_Mandatory_Parts"] = "Yes"
                if "Task_Groups" not in base_for_editor.columns:
                    base_for_editor["Task_Groups"] = ""

                # Keep pending BOM updates across reruns until file save.
                st.session_state.setdefault("maint_editor_pending_required_parts", {})
                st.session_state.setdefault("maint_editor_pending_task_groups", {})
                pending_map = st.session_state.get("maint_editor_pending_required_parts", {})
                pending_groups_map = st.session_state.get("maint_editor_pending_task_groups", {})
                file_prefix = f"{pick}::"
                for k, v in list(pending_map.items()):
                    if not str(k).startswith(file_prefix):
                        continue
                    try:
                        row_idx = int(str(k).split("::", 1)[1])
                    except Exception:
                        continue
                    if row_idx in base_for_editor.index:
                        base_for_editor.at[row_idx, "Required_Parts"] = safe_str(v).strip()
                        if "Mandatory_Parts" in base_for_editor.columns:
                            base_for_editor.at[row_idx, "Mandatory_Parts"] = safe_str(v).strip()
                for k, v in list(pending_groups_map.items()):
                    if not str(k).startswith(file_prefix):
                        continue
                    try:
                        row_idx = int(str(k).split("::", 1)[1])
                    except Exception:
                        continue
                    if row_idx in base_for_editor.index:
                        groups_txt = safe_str(v).strip()
                        base_for_editor.at[row_idx, "Task_Groups"] = groups_txt
                        if "Task_Group" in base_for_editor.columns:
                            # Keep backward compatibility while preserving multi-group membership.
                            base_for_editor.at[row_idx, "Task_Group"] = groups_txt

                edited = st.data_editor(
                    base_for_editor,
                    use_container_width=True,
                    height=420,
                    key="maint_tasks_editor_grid",
                )

                st.markdown("##### 📦 Add Mandatory Parts From Inventory")
                st.caption("Pick a task row, filter inventory, then append selected parts to the task mandatory parts list.")

                task_labels = []
                task_idx_map = {}
                for i, r in edited.iterrows():
                    comp = safe_str(r.get("Component", "")).strip()
                    task = safe_str(r.get("Task", "")).strip()
                    tid = safe_str(r.get("Task_ID", "")).strip()
                    tg = safe_str(r.get("Task_Group", "")).strip()
                    lbl = f"{comp} — {task} (ID:{tid or '-'}, Group:{tg or '-'})"
                    task_labels.append(lbl)
                    task_idx_map[lbl] = i

                if not task_labels:
                    st.info("No task rows available in this file.")
                else:
                    t1, t2 = st.columns([1.2, 1.0])
                    with t1:
                        picked_task_label = st.selectbox(
                            "Task row",
                            options=task_labels,
                            key="maint_editor_parts_task_pick",
                        )
                    with t2:
                        inv_search = st.text_input(
                            "Search inventory part",
                            value="",
                            placeholder="type part name...",
                            key="maint_editor_parts_search",
                        ).strip().lower()

                    inv_rows = pd.DataFrame()
                    try:
                        inv_rows = load_inventory_cached(P.parts_inventory_csv)
                    except Exception:
                        inv_rows = pd.DataFrame()

                    if inv_rows.empty:
                        st.info("Inventory list is empty or unavailable.")
                    else:
                        for col in ["Part Name", "Component", "Location", "Quantity"]:
                            if col not in inv_rows.columns:
                                inv_rows[col] = ""

                        c1, c2 = st.columns([1.2, 1.0])
                        with c1:
                            inv_comp_opts = sorted(
                                [x for x in inv_rows["Component"].astype(str).str.strip().unique().tolist() if x]
                            )
                            inv_comp_filter = st.multiselect(
                                "Inventory component filter",
                                options=inv_comp_opts,
                                default=[],
                                key="maint_editor_parts_comp_filter",
                            )
                        with c2:
                            only_stock = st.checkbox(
                                "Only stock > 0 (not mounted)",
                                value=True,
                                key="maint_editor_parts_only_stock",
                            )

                        if inv_comp_filter:
                            inv_rows = inv_rows[inv_rows["Component"].astype(str).isin(inv_comp_filter)].copy()
                        if inv_search:
                            inv_rows = inv_rows[
                                inv_rows["Part Name"].astype(str).str.lower().str.contains(inv_search, na=False)
                            ].copy()
                        if only_stock:
                            inv_rows = inv_rows[
                                inv_rows["Location"].astype(str).str.strip().str.lower().ne("mounted")
                                & (pd.to_numeric(inv_rows["Quantity"], errors="coerce").fillna(0.0) > 0)
                            ].copy()

                        inv_show = inv_rows[["Part Name", "Component", "Location", "Quantity"]].copy()
                        inv_show = inv_show.sort_values(["Component", "Part Name", "Location"]).reset_index(drop=True)
                        st.dataframe(inv_show, use_container_width=True, height=150)

                        part_opts = [safe_str(x).strip() for x in inv_show["Part Name"].tolist() if safe_str(x).strip()]
                        uniq_part_opts = []
                        seen_part_opts = set()
                        for p in part_opts:
                            lk = p.lower()
                            if lk not in seen_part_opts:
                                uniq_part_opts.append(p)
                                seen_part_opts.add(lk)

                        picked_parts = st.multiselect(
                            "Inventory parts to append",
                            options=uniq_part_opts,
                            default=[],
                            key="maint_editor_parts_pick",
                        )

                        if st.button(
                            "➕ Append to task mandatory parts",
                            key="maint_editor_parts_append_btn",
                            use_container_width=True,
                        ):
                            if not picked_parts:
                                st.error("Select at least one inventory part.")
                            else:
                                row_idx = task_idx_map.get(picked_task_label)
                                if row_idx is None or row_idx not in edited.index:
                                    st.error("Selected task row not found.")
                                else:
                                    base_col = "Mandatory_Parts" if "Mandatory_Parts" in edited.columns else "Required_Parts"
                                    cur_txt = safe_str(edited.at[row_idx, base_col]).strip()
                                    merged_parts = []
                                    seen_merge = set()
                                    for token in (cur_txt.replace("\n", ",").replace(";", ",").replace("|", ",").split(",")):
                                        pv = token.strip()
                                        if not pv:
                                            continue
                                        lk = pv.lower()
                                        if lk in seen_merge:
                                            continue
                                        merged_parts.append(pv)
                                        seen_merge.add(lk)
                                    for p in picked_parts:
                                        pv = safe_str(p).strip()
                                        if not pv:
                                            continue
                                        lk = pv.lower()
                                        if lk in seen_merge:
                                            continue
                                        merged_parts.append(pv)
                                        seen_merge.add(lk)

                                    new_required = ", ".join(merged_parts)
                                    st.session_state["maint_editor_pending_required_parts"][f"{pick}::{row_idx}"] = new_required
                                    st.success("Added to task mandatory parts. Save file to persist.")
                                    st.rerun()

                st.caption("Task groups are managed in Work Package Builder to keep one unified flow.")

                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("💾 Save file", type="primary", use_container_width=True, key="maint_save_file_btn"):
                        out = templateize_df(edited, list(raw.columns))
                        write_file(path, out)
                        # Clear pending patches for this file after save.
                        pending_map = st.session_state.get("maint_editor_pending_required_parts", {})
                        to_del = [k for k in list(pending_map.keys()) if str(k).startswith(f"{pick}::")]
                        for k in to_del:
                            pending_map.pop(k, None)
                        st.session_state["maint_editor_pending_required_parts"] = pending_map
                        pending_groups_map = st.session_state.get("maint_editor_pending_task_groups", {})
                        to_del_g = [k for k in list(pending_groups_map.keys()) if str(k).startswith(f"{pick}::")]
                        for k in to_del_g:
                            pending_groups_map.pop(k, None)
                        st.session_state["maint_editor_pending_task_groups"] = pending_groups_map
                        st.success("Saved.")
                        st.rerun()
                with c2:
                    st.caption("Saved back in the original template columns.")

                # Optional cleanup to physically remove empty placeholder rows from selected source file.
                if st.button("🧹 Remove empty rows + Save", key="maint_clean_empty_rows_btn", use_container_width=True):
                    clean_df = edited.copy()
                    c_s = clean_df.get("Component", pd.Series([""] * len(clean_df))).astype(str).str.strip()
                    t_s = clean_df.get("Task", pd.Series([""] * len(clean_df))).astype(str).str.strip()
                    m_s = clean_df.get("Tracking_Mode", pd.Series([""] * len(clean_df))).astype(str).str.strip()
                    id_s = clean_df.get("Task_ID", pd.Series([""] * len(clean_df))).astype(str).str.strip()
                    rm_mask = (c_s.eq("") & t_s.eq("") & m_s.eq("") & id_s.eq("")) | c_s.eq("") | t_s.eq("")
                    removed = int(rm_mask.sum())
                    clean_df = clean_df.loc[~rm_mask].copy()
                    out = templateize_df(clean_df, list(raw.columns))
                    write_file(path, out)
                    st.success(f"Saved and removed invalid rows: {removed}")
                    st.rerun()
            except Exception as e:
                st.warning(f"Tasks editor failed: {e}")
    
    # =========================================================
    # Manuals / Documents browser (same preview style)
    # =========================================================
    def render_manuals_browser(BASE_DIR):
        MANUALS_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
    
        def _ext(p: str) -> str:
            return os.path.splitext(str(p).lower())[1]
    
        def _is_pdf(p: str) -> bool:
            return str(p).lower().endswith(".pdf")
    
        def _is_img(p: str) -> bool:
            return _ext(p) in MANUALS_IMG_EXTS
    
        def _short_name(fn: str, max_len: int = 42) -> str:
            fn = str(fn)
            if len(fn) <= max_len:
                return fn
            keep_tail = 16
            head = max_len - keep_tail - 3
            return fn[:head] + "..." + fn[-keep_tail:]
    
        @st.cache_data(show_spinner=False)
        def _read_bytes(path: str) -> bytes:
            with open(path, "rb") as f:
                return f.read()
    
        def _download_btn(path: str, label: str, key: str):
            if not os.path.exists(path):
                st.warning(f"Missing file: {os.path.basename(path)}")
                return
            data = _read_bytes(path)
            st.download_button(
                label=label,
                data=data,
                file_name=os.path.basename(path),
                mime=None,
                key=key,
                use_container_width=True,
            )
    
        @st.cache_data(show_spinner=False)
        def _pdf_render_pages(path: str, max_pages: int = 1, zoom: float = 1.6):
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            n = min(len(doc), int(max_pages))
            out = []
            mat = fitz.Matrix(float(zoom), float(zoom))
            for i in range(n):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                out.append(pix.tobytes("png"))
            doc.close()
            return out
    
        def _render_pdf_preview(path: str, *, key_prefix: str):
            if not os.path.exists(path):
                st.warning("PDF file not found.")
                return
    
            state_key = f"{key_prefix}__show_all"
            st.session_state.setdefault(state_key, False)
    
            c1, c2, c3 = st.columns([1.6, 1.0, 1.0])
            with c1:
                st.markdown("**PDF preview (rendered)**")
                st.caption("Default shows page 1. Click to render more pages.")
            with c2:
                zoom = st.selectbox("Quality", [1.3, 1.6, 2.0], index=1, key=f"{key_prefix}__zoom")
            with c3:
                max_pages = st.number_input(
                    "Pages (when expanded)", min_value=1, max_value=200, value=30, step=1, key=f"{key_prefix}__pages"
                )
    
            b1, b2 = st.columns([1, 1])
            with b1:
                if not st.session_state[state_key]:
                    if st.button("📄 Render more pages", use_container_width=True, key=f"{key_prefix}__more"):
                        st.session_state[state_key] = True
                        st.rerun()
                else:
                    if st.button("⬅️ Back to page 1", use_container_width=True, key=f"{key_prefix}__less"):
                        st.session_state[state_key] = False
                        st.rerun()
            with b2:
                _download_btn(path, "⬇️ Download PDF", key=f"{key_prefix}__dl")
    
            try:
                if st.session_state[state_key]:
                    imgs = _pdf_render_pages(path, max_pages=int(max_pages), zoom=float(zoom))
                    st.caption(f"Showing **{len(imgs)}** page(s).")
                    for i, b in enumerate(imgs, start=1):
                        st.image(b, caption=f"Page {i}", use_container_width=True)
                else:
                    imgs = _pdf_render_pages(path, max_pages=1, zoom=float(zoom))
                    if imgs:
                        st.image(imgs[0], caption="Page 1", use_container_width=True)
            except Exception as e:
                st.error(f"PDF render failed. Install PyMuPDF: `pip install pymupdf`  |  Error: {e}")
    
        with st.expander("📚 Manuals / Documents browser", expanded=False):
            st.caption("Tight checklist view: select manuals, then preview one.")
    
            candidate_dirs = [
                os.path.join(BASE_DIR, "manuals"),
                os.path.join(BASE_DIR, "docs"),
                os.path.join(BASE_DIR, "maintenance", "manuals"),
                os.path.join(BASE_DIR, "maintenance", "docs"),
            ]
            existing = [d for d in candidate_dirs if os.path.isdir(d)]
            if not existing:
                st.info("No manuals/docs folder found. (Create /manuals or /docs).")
                return
    
            root = st.selectbox("Folder", existing, key="maint_manuals_root_pick")
    
            paths = sorted(glob.glob(os.path.join(root, "**", "*.*"), recursive=True))
            paths = [p for p in paths if os.path.isfile(p)]
            if not paths:
                st.info("No files found.")
                return
    
            c1, c2, c3 = st.columns([1.6, 1.0, 1.0])
            with c1:
                q = st.text_input("Search", placeholder="type filename…", key="maint_manuals_search")
            with c2:
                kind = st.selectbox("Type", ["All", "PDF", "Images", "Other"], key="maint_manuals_type")
            with c3:
                limit = st.number_input("Show (max)", 10, 500, 120, 10, key="maint_manuals_limit")
    
            def _match(p):
                fn = os.path.basename(p).lower()
                if q and q.lower().strip() not in fn:
                    return False
                if kind == "PDF" and not _is_pdf(p):
                    return False
                if kind == "Images" and not _is_img(p):
                    return False
                if kind == "Other" and (_is_pdf(p) or _is_img(p)):
                    return False
                return True
    
            shown = [p for p in paths if _match(p)]
            st.caption(f"Files found: **{len(shown)}** (total in folder: {len(paths)})")
            shown = shown[: int(limit)]
    
            st.session_state.setdefault("maint_manuals_checked", [])
            st.session_state.setdefault("maint_manuals_active", "")
    
            st.markdown("#### ✅ Select manuals")
            checked = set(st.session_state.get("maint_manuals_checked", []))
    
            for i, p in enumerate(shown):
                fn = os.path.basename(p)
                col0, col1, col2 = st.columns([0.35, 5.0, 1.0], gap="small")
                with col0:
                    is_on = st.checkbox("", value=(p in checked), key=f"maint_manuals_chk__{i}")
                with col1:
                    st.markdown(f"**{_short_name(fn)}**")
                with col2:
                    _download_btn(p, "⬇️", key=f"maint_manuals_dl__{i}__{fn}")
    
                if is_on:
                    checked.add(p)
                else:
                    checked.discard(p)
    
            st.session_state["maint_manuals_checked"] = sorted(list(checked))
    
            st.divider()
    
            picked_list = st.session_state["maint_manuals_checked"]
            if not picked_list:
                st.info("Select at least one manual to preview.")
                return
    
            if st.session_state["maint_manuals_active"] not in picked_list:
                st.session_state["maint_manuals_active"] = picked_list[0]
    
            labels = {p: os.path.basename(p) for p in picked_list}
            active = st.selectbox(
                "👁️ Preview selected manual",
                options=picked_list,
                format_func=lambda p: labels.get(p, p),
                key="maint_manuals_active",
            )
    
            st.markdown("### Preview")
            st.caption(os.path.basename(active))
    
            if _is_pdf(active):
                _render_pdf_preview(active, key_prefix=f"maint_manuals_pdf__{os.path.basename(active)}")
            elif _is_img(active):
                st.image(active, use_container_width=True)
            else:
                st.info("No preview for this file type (use Download).")
    
            cA, cB = st.columns([1, 1])
            with cA:
                if st.button("🧹 Clear selection", use_container_width=True, key="maint_manuals_clear"):
                    st.session_state["maint_manuals_checked"] = []
                    st.session_state["maint_manuals_active"] = ""
                    st.rerun()
            with cB:
                _download_btn(active, "⬇️ Download active", key="maint_manuals_dl_active")
    
    # =========================================================
    # UI flow
    # =========================================================
    st.markdown('<div class="maint-section-title">📊 Dashboard</div>', unsafe_allow_html=True)
    render_maintenance_dashboard_metrics(dfm, current_date, current_draw_count)
    show_test_monitor = st.toggle("Show Test Monitor", value=False, key="maint_show_test_monitor")
    if show_test_monitor:
        render_maintenance_test_monitor()
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    st.session_state.setdefault("maint_main_group", "maintenance")
    if st.session_state.get("maint_main_group") == "gas":
        st.session_state["maint_main_group"] = "maintenance"
    g1, g2, g3 = st.columns(3)
    if g1.button("🧰 Maintenance", key="maint_group_btn_maint", use_container_width=True, type="primary" if st.session_state["maint_main_group"] == "maintenance" else "secondary"):
        st.session_state["maint_main_group"] = "maintenance"
        st.rerun()
    if g2.button("🚨 Faults", key="maint_group_btn_faults", use_container_width=True, type="primary" if st.session_state["maint_main_group"] == "faults" else "secondary"):
        st.session_state["maint_main_group"] = "faults"
        st.rerun()
    if g3.button("📈 Correlation & Outliers", key="maint_group_btn_corr", use_container_width=True, type="primary" if st.session_state["maint_main_group"] == "corr" else "secondary"):
        st.session_state["maint_main_group"] = "corr"
        st.rerun()

    group = st.session_state.get("maint_main_group", "maintenance")

    if group == "maintenance":
        st.caption("Flow: Builder -> Plan + Prepare -> Execute + Resolve Blocks")
        flow_options = [
            "0) Builder (Tasks + BOM)",
            "1) Plan + Prepare",
            "2) Execute + Resolve Blocks",
        ]
        st.session_state.setdefault("maint_flow_step", flow_options[0])
        if st.session_state.get("maint_flow_step") not in flow_options:
            st.session_state["maint_flow_step"] = flow_options[0]
        f1, f2, f3 = st.columns(3)
        if f1.button(
            flow_options[0],
            key="maint_flow_btn_0",
            use_container_width=True,
            type="primary" if st.session_state["maint_flow_step"] == flow_options[0] else "secondary",
        ):
            st.session_state["maint_flow_step"] = flow_options[0]
            st.rerun()
        if f2.button(
            flow_options[1],
            key="maint_flow_btn_1",
            use_container_width=True,
            type="primary" if st.session_state["maint_flow_step"] == flow_options[1] else "secondary",
        ):
            st.session_state["maint_flow_step"] = flow_options[1]
            st.rerun()
        if f3.button(
            flow_options[2],
            key="maint_flow_btn_2",
            use_container_width=True,
            type="primary" if st.session_state["maint_flow_step"] == flow_options[2] else "secondary",
        ):
            st.session_state["maint_flow_step"] = flow_options[2]
            st.rerun()
        flow_step = st.session_state.get("maint_flow_step", flow_options[0])

        if flow_step == "0) Builder (Tasks + BOM)":
            st.caption("Edit tasks, groups, BOM, and work package here.")
            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 1) 🧩 Task + Group + BOM + Work Package")
            show_builder = st.toggle("Open Unified Builder", value=False, key="maint_open_unified_builder")
            if show_builder:
                render_maintenance_work_package_builder(dfm, actor, header_md="### 🧩 Unified Maintenance Builder")
            else:
                st.caption("Builder folded. Turn on `Open Unified Builder` to edit tasks/BOM/work package.")

            st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 2) 📚 Manuals + Source QA (optional)")
            qa1, qa2 = st.columns(2)
            with qa1:
                show_load_report = st.toggle("Open Load Report", value=False, key="maint_open_load_report")
            with qa2:
                show_manuals_browser = st.toggle("Open Manuals Browser", value=False, key="maint_open_manuals_browser")
            if show_load_report:
                render_maintenance_load_report(files, load_errors)
            else:
                st.caption("Load report folded.")
            if show_manuals_browser:
                render_manuals_browser(BASE_DIR)
            else:
                st.caption("Manuals browser folded.")

        elif flow_step == "1) Plan + Prepare":
            st.caption("Mostly automatic. Use this lane to monitor the plan, solve real problems, and review the automatic preparation list.")
            render_maintenance_scheduler_bridge(
                dfm=dfm,
                current_date=current_date,
                current_draw_count=current_draw_count,
                furnace_hours=furnace_hours,
                uv1_hours=uv1_hours,
                uv2_hours=uv2_hours,
            )
            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
            render_maintenance_day_todo_pack(dfm, current_date, actor)
            with st.expander("Long-range view", expanded=False):
                st.caption("Optional future timeline view.")
                horizon_hours, horizon_days, horizon_draws = render_maintenance_horizon_selector(current_draw_count)
                focus = render_future_schedule_focus_selector()
                render_maintenance_roadmaps(
                    dfm,
                    current_date,
                    current_draw_count,
                    furnace_hours,
                    uv1_hours,
                    uv2_hours,
                    horizon_hours,
                    horizon_days,
                    horizon_draws,
                    focus=focus,
                )

        else:
            st.caption("Choose the live task, act on it now, and keep waits, execution records, and history together.")
            st.markdown('<div class="maint-lane-shell"><div class="maint-lane-title">Task Action Center</div><div class="maint-lane-sub">Pick the task that needs action now. This lane includes the live queue, blocked-task tracker, and execution workspace.</div>', unsafe_allow_html=True)
            show_smart_todo = st.toggle("Open Task Action Center", value=False, key="maint_open_smart_todo")
            if show_smart_todo:
                render_smart_maintenance_todo(
                    dfm=dfm,
                    current_date=current_date,
                    current_draw_count=current_draw_count,
                    actor=actor,
                    con=con,
                    read_file=read_file,
                    write_file=write_file,
                    normalize_df=normalize_df,
                    templateize_df=templateize_df,
                    pick_current_hours=pick_current_hours,
                    mode_norm=mode_norm,
                )
            else:
                st.caption("Task Action Center folded.")
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown('<div class="maint-lane-shell"><div class="maint-lane-title">Batch Completion</div><div class="maint-lane-sub">Use this when several tasks were completed and you want to update source files, logs, and consumption in one batch.</div>', unsafe_allow_html=True)
            show_mark_done = st.toggle("Open Mark Tasks Done", value=False, key="maint_open_mark_done")
            if show_mark_done:
                edited = render_maintenance_done_editor(
                    dfm,
                    current_date=current_date,
                    current_draw_count=current_draw_count,
                    furnace_hours=furnace_hours,
                    uv1_hours=uv1_hours,
                    uv2_hours=uv2_hours,
                    actor=actor,
                )
                render_maintenance_apply_done(
                    edited,
                    dfm=dfm,
                    current_date=current_date,
                    current_draw_count=current_draw_count,
                    actor=actor,
                    MAINT_FOLDER=MAINT_FOLDER,
                    con=con,
                    read_file=read_file,
                    write_file=write_file,
                    normalize_df=normalize_df,
                    templateize_df=templateize_df,
                    pick_current_hours=pick_current_hours,
                    mode_norm=mode_norm,
                )
            else:
                st.caption("Mark Tasks Done folded.")
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown('<div class="maint-lane-shell"><div class="maint-lane-title">Execution History</div><div class="maint-lane-sub">Use this lane to review what was done, check traceability, and verify the quality of recent execution records.</div>', unsafe_allow_html=True)
            show_exec_history = st.toggle("Open Execution History", value=False, key="maint_open_exec_history")
            if show_exec_history:
                render_maintenance_history(con)
            else:
                st.caption("Execution History folded.")
            st.markdown("</div>", unsafe_allow_html=True)

    elif group == "faults":
        show_faults = st.toggle("Open Faults workspace", value=False, key="maint_open_faults_workspace")
        if show_faults:
            render_faults_section(
                con=con,
                MAINT_FOLDER=MAINT_FOLDER,
                actor=actor,
            )
        else:
            st.caption("Faults workspace folded.")
    elif group == "corr":
        st.markdown('<div class="maint-section-title">📈 Correlation & Outliers</div>', unsafe_allow_html=True)
        st.caption("Rolling correlation and outlier tracking from draw logs + maintenance events.")
        show_corr = st.toggle("Open Correlation & Outliers", value=False, key="maint_open_corr_outliers")
        if show_corr:
            render_corr_outliers_tab(draw_folder=P.logs_dir, maint_folder=P.maintenance_dir)
        else:
            st.caption("Correlation & Outliers folded.")
    # ------------------ Correlation & Outliers ------------------
