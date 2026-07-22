def render_home_tab_command_deck(
    P,
    image_base64,
    STATUS_COL,
    STATUS_UPDATED_COL,
    FAILED_REASON_COL,
    parse_dt_safe,
    now_str,
    safe_str,
    render_home_draw_orders_overview,
    render_schedule_home_minimal,
    render_parts_orders_home_all,
):
    import os
    import json
    import pandas as pd
    import streamlit as st
    from helpers.maintenance_status import (
        compute_maintenance_status_df,
        load_maintenance_folder_df,
    )
    from helpers.orders_io import count_dataset_draws

    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
              radial-gradient(900px 420px at 50% 0%, rgba(40, 218, 255, 0.18), rgba(40, 218, 255, 0) 70%),
              linear-gradient(180deg, rgba(3, 7, 13, 0.88), rgba(4, 12, 20, 0.92)),
              url("data:image/jpg;base64,{image_base64}") no-repeat center center fixed;
            background-size: auto, auto, cover;
        }}
        .stApp::before {{
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            background:
              linear-gradient(rgba(114,255,231,0.03) 1px, transparent 1px),
              linear-gradient(90deg, rgba(114,255,231,0.03) 1px, transparent 1px);
            background-size: 44px 44px;
            opacity: 0.28;
        }}
        .stApp::after {{
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            background:
              radial-gradient(1200px 720px at 50% 36%, rgba(4,10,18,0.02), rgba(4,10,18,0.52) 64%, rgba(4,10,18,0.82) 100%);
        }}
        [data-testid="stAppViewContainer"] .main {{
            position: relative;
            z-index: 1;
        }}
        .tower-bridge {{
            position: relative;
            overflow: hidden;
            margin-top: 28px;
            padding: 34px 34px 26px;
            border-radius: 38px 38px 18px 18px;
            border: 1px solid rgba(114,255,231,0.14);
            background:
              radial-gradient(circle at 70% 22%, rgba(47,216,255,0.12), transparent 18%),
              radial-gradient(circle at 18% 78%, rgba(114,255,231,0.09), transparent 16%),
              linear-gradient(180deg, rgba(9,18,28,0.62), rgba(4,10,16,0.90));
            box-shadow: 0 30px 80px rgba(0,0,0,0.42);
            backdrop-filter: blur(12px);
        }}
        .tower-bridge::before {{
            content: "";
            position: absolute;
            inset: 16px;
            border-radius: 30px 30px 10px 10px;
            border: 1px solid rgba(114,255,231,0.08);
            pointer-events: none;
        }}
        .tower-eyebrow {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            color: #72ffe7;
            text-transform: uppercase;
            letter-spacing: 0.22em;
            font-size: 0.72rem;
            font-weight: 700;
            margin-bottom: 16px;
        }}
        .tower-eyebrow::before {{
            content: "";
            width: 28px;
            height: 1px;
            background: currentColor;
            opacity: 0.7;
        }}
        .tower-headline {{
            margin: 0;
            max-width: 10ch;
            color: #ebfff9;
            font-size: clamp(2.9rem, 6vw, 5.6rem);
            line-height: 0.92;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            text-shadow: 0 0 18px rgba(114,255,231,0.08);
        }}
        .tower-copy {{
            max-width: 44ch;
            margin: 18px 0 0;
            color: rgba(234,255,249,0.78);
            font-size: 1.08rem;
            line-height: 1.6;
        }}
        .tower-stage {{
            position: relative;
            height: 280px;
            margin-top: 28px;
            overflow: hidden;
        }}
        .tower-horizon {{
            position: absolute;
            inset: auto 0 0 0;
            height: 74%;
            background:
              radial-gradient(circle at 50% 0%, rgba(47,216,255,0.12), transparent 34%),
              linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(4,10,16,0.45) 18%, rgba(4,10,16,0.92) 100%);
            clip-path: polygon(6% 14%, 94% 14%, 100% 100%, 0 100%);
        }}
        .tower-lane {{
            position: absolute;
            inset: auto 10% 0 10%;
            height: 80%;
            clip-path: polygon(12% 0, 88% 0, 100% 100%, 0 100%);
            border-top: 1px solid rgba(114,255,231,0.16);
            background:
              linear-gradient(90deg, transparent 0%, rgba(114,255,231,0.08) 20%, transparent 21%, transparent 79%, rgba(114,255,231,0.08) 80%, transparent 100%),
              linear-gradient(180deg, rgba(114,255,231,0.04), rgba(114,255,231,0.01));
        }}
        .tower-radar {{
            position: absolute;
            right: 4%;
            top: 6%;
            width: 230px;
            height: 230px;
            border-radius: 50%;
            border: 1px solid rgba(114,255,231,0.16);
            background:
              radial-gradient(circle, rgba(114,255,231,0.12), rgba(114,255,231,0.03) 35%, transparent 60%),
              linear-gradient(180deg, rgba(114,255,231,0.03), rgba(114,255,231,0.01));
            box-shadow: inset 0 0 34px rgba(114,255,231,0.05);
        }}
        .tower-radar::before {{
            content: "";
            position: absolute;
            inset: 0;
            border-radius: 50%;
            background: conic-gradient(from 40deg, rgba(114,255,231,0.22), transparent 18%, transparent 72%, rgba(114,255,231,0.1));
            mix-blend-mode: screen;
            animation: towerSpin 14s linear infinite;
        }}
        .tower-radar::after {{
            content: "";
            position: absolute;
            inset: 16%;
            border-radius: 50%;
            border: 1px dashed rgba(114,255,231,0.10);
        }}
        .tower-float {{
            position: absolute;
            padding: 12px 14px;
            border: 1px solid rgba(114,255,231,0.08);
            background: rgba(5,12,20,0.46);
            backdrop-filter: blur(14px);
            color: rgba(234,255,249,0.74);
        }}
        .tower-float strong {{
            display: block;
            color: #ebfff9;
            margin-bottom: 4px;
        }}
        .tower-float.top {{
            top: 6%;
            left: 3%;
            border-radius: 18px 18px 18px 4px;
            max-width: 220px;
        }}
        .tower-float.mid {{
            top: 40%;
            right: 0;
            border-radius: 18px 4px 18px 18px;
            max-width: 190px;
        }}
        .tower-float.low {{
            bottom: 8%;
            left: 10%;
            border-radius: 4px 18px 18px 18px;
            max-width: 220px;
        }}
        .tower-chip-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 22px;
        }}
        .tower-chip {{
            min-width: 124px;
            padding: 11px 14px;
            border-radius: 999px;
            border: 1px solid rgba(114,255,231,0.1);
            background: rgba(6,13,20,0.55);
            color: rgba(234,255,249,0.78);
            backdrop-filter: blur(14px);
        }}
        .tower-chip span {{
            display: block;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.7rem;
            color: rgba(234,255,249,0.58);
            margin-bottom: 5px;
        }}
        .tower-chip strong {{
            font-size: 1rem;
            color: #ebfff9;
        }}
        .tower-surface {{
            margin-top: 28px;
            padding-top: 24px;
            border-top: 1px solid rgba(114,255,231,0.08);
        }}
        .tower-surface-copy {{
            max-width: 58ch;
            color: rgba(234,255,249,0.76);
            line-height: 1.55;
            font-size: 1rem;
        }}
        .tower-section-title {{
            margin: 0 0 8px;
            color: #72ffe7;
            text-transform: uppercase;
            letter-spacing: 0.18em;
            font-size: 0.76rem;
            font-weight: 700;
        }}
        .tower-ribbon {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 22px;
            padding: 28px 8px 0;
        }}
        .tower-ribbon article {{
            padding-top: 10px;
            border-top: 1px solid rgba(114,255,231,0.08);
        }}
        .tower-ribbon h3 {{
            margin: 0 0 8px;
            color: #72ffe7;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.9rem;
        }}
        .tower-ribbon p {{
            margin: 0;
            color: rgba(234,255,249,0.76);
            line-height: 1.55;
        }}
        .tower-deck {{
            margin-top: 34px;
            padding-top: 30px;
            border-top: 1px solid rgba(114,255,231,0.14);
        }}
        .tower-deck-header h2 {{
            margin: 0;
            color: #ebfff9;
            font-size: clamp(2rem, 3.5vw, 3.2rem);
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .tower-deck-header p {{
            max-width: 52ch;
            margin: 12px 0 0;
            color: rgba(234,255,249,0.76);
            line-height: 1.6;
        }}
        .tower-mode-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 22px 0 0;
        }}
        div[data-testid="stButton"] > button.tower-nav-btn,
        div[data-testid="stButton"] > button.tower-nav-btn-active {{
            border-radius: 999px !important;
            min-height: 42px !important;
            padding: 0.4rem 1rem !important;
            text-transform: uppercase !important;
            letter-spacing: 0.08em !important;
            font-weight: 700 !important;
            border: 1px solid rgba(114,255,231,0.12) !important;
            background: rgba(255,255,255,0.02) !important;
            color: rgba(234,255,249,0.74) !important;
            box-shadow: none !important;
        }}
        div[data-testid="stButton"] > button.tower-nav-btn-active {{
            color: #071016 !important;
            border-color: transparent !important;
            background: linear-gradient(135deg, #72ffe7, #2fd8ff) !important;
            box-shadow: 0 0 22px rgba(47,216,255,0.22) !important;
        }}
        .tower-content {{
            margin-top: 22px;
            display: grid;
            grid-template-columns: 1.04fr 0.96fr;
            gap: 26px;
            align-items: start;
        }}
        .tower-content-main {{
            min-width: 0;
        }}
        .tower-content-side {{
            min-width: 0;
        }}
        .tower-side-rail {{
            position: sticky;
            top: 92px;
            padding-left: 18px;
        }}
        .tower-side-rail::before {{
            content: "";
            position: absolute;
            left: 0;
            top: 10px;
            bottom: 10px;
            width: 1px;
            background: linear-gradient(180deg, transparent, rgba(114,255,231,0.16), transparent);
        }}
        .tower-side-shell {{
            padding: 12px 0 0;
        }}
        .tower-side-shell h3 {{
            margin: 0;
            color: #ebfff9;
            font-size: 1.4rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}
        .tower-side-shell p {{
            margin: 10px 0 0;
            color: rgba(234,255,249,0.74);
            line-height: 1.55;
        }}
        .tower-side-shell .tower-side-note {{
            margin-top: 18px;
            padding-top: 14px;
            border-top: 1px solid rgba(114,255,231,0.08);
            color: rgba(234,255,249,0.62);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.84rem;
        }}
        @keyframes towerSpin {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}
        @media (max-width: 1100px) {{
            .tower-ribbon,
            .tower-content {{
                grid-template-columns: 1fr;
            }}
            .tower-side-rail {{
                position: relative;
                top: 0;
                padding-left: 0;
            }}
            .tower-side-rail::before {{
                display: none;
            }}
        }}
        @media (max-width: 760px) {{
            .tower-bridge {{
                padding: 24px 20px 20px;
                border-radius: 30px 30px 14px 14px;
            }}
            .tower-radar {{
                width: 170px;
                height: 170px;
            }}
            .tower-float.top,
            .tower-float.mid,
            .tower-float.low {{
                max-width: 160px;
                font-size: 0.86rem;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    orders_file = P.orders_csv
    faults_csv = os.path.join(P.maintenance_dir, "faults_log.csv")

    def _mtime(path: str) -> float:
        try:
            return float(os.path.getmtime(path))
        except Exception:
            return 0.0

    @st.cache_data(show_spinner=False)
    def _read_orders_cached(path: str, file_mtime: float):
        return pd.read_csv(path)

    def _ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
        if STATUS_COL not in df.columns:
            df[STATUS_COL] = "Pending"
        if STATUS_UPDATED_COL not in df.columns:
            df[STATUS_UPDATED_COL] = ""
        if FAILED_REASON_COL not in df.columns:
            df[FAILED_REASON_COL] = ""
        return df

    def _auto_move_failed_to_pending(days: int = 4) -> None:
        if not os.path.exists(orders_file):
            return
        try:
            df = _read_orders_cached(orders_file, _mtime(orders_file))
        except Exception:
            return
        df = _ensure_cols(df)
        if df.empty:
            return
        now = pd.Timestamp.now()
        cutoff = now - pd.Timedelta(days=days)
        changed = False
        for i in range(len(df)):
            if str(df.at[i, STATUS_COL]).strip().lower() != "failed":
                continue
            stamp = parse_dt_safe(df.at[i, STATUS_UPDATED_COL])
            if stamp is None:
                df.at[i, STATUS_UPDATED_COL] = now_str()
                changed = True
                continue
            if stamp < cutoff:
                df.at[i, STATUS_COL] = "Pending"
                df.at[i, STATUS_UPDATED_COL] = now_str()
                changed = True
        if changed:
            df.to_csv(orders_file, index=False)

    @st.cache_data(show_spinner=False, ttl=20)
    def _compute_open_critical_faults(faults_path: str) -> int:
        if not os.path.isfile(faults_path):
            return 0
        try:
            df = pd.read_csv(faults_path)
        except Exception:
            return 0
        if df.empty:
            return 0
        cols = {c.lower().strip(): c for c in df.columns}
        sev_col = cols.get("fault_severity")
        if not sev_col:
            return 0
        status_col = cols.get("fault_status")
        closed_col = cols.get("fault_closed")
        sev = df[sev_col].astype(str).str.strip().str.lower()
        is_open = pd.Series(True, index=df.index)
        if status_col:
            stt = df[status_col].astype(str).str.strip().str.lower()
            is_open = ~stt.isin(["closed", "done", "resolved", "fixed"])
        elif closed_col:
            closed = df[closed_col].astype(str).str.strip().str.lower()
            is_open = ~closed.isin(["true", "1", "yes", "y", "closed"])
        return int((sev == "critical")[is_open].sum())

    @st.cache_data(show_spinner=False, ttl=10)
    def _compute_maintenance_in_progress() -> int:
        state_file = os.path.join(P.maintenance_dir, "maintenance_task_state.csv")
        in_progress = 0
        try:
            if os.path.isfile(state_file):
                sdf = pd.read_csv(state_file, keep_default_na=False)
                if "state" in sdf.columns:
                    in_progress = int(sdf["state"].astype(str).str.upper().eq("IN_PROGRESS").sum())
        except Exception:
            in_progress = 0
        try:
            if os.path.isfile(P.activity_indicator_json):
                with open(P.activity_indicator_json, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                if bool(payload.get("active", False)) and str(payload.get("activity_type", "")).strip().lower() == "maintenance":
                    in_progress = max(in_progress, 1)
        except Exception:
            pass
        return int(max(0, in_progress))

    @st.cache_data(show_spinner=False, ttl=20)
    def _compute_maintenance_counts(maint_folder: str, dataset_dir: str) -> tuple[int, int]:
        def _load_state(path: str) -> dict:
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as fh:
                        return json.load(fh)
            except Exception:
                pass
            return {}

        current_draw_count = int(count_dataset_draws(P.dataset_dir))
        state_path = os.path.join(maint_folder, "_app_state.json")
        state = _load_state(state_path)
        furnace_hours = float(state.get("furnace_hours", 0.0) or 0.0)
        uv1_hours = float(state.get("uv1_hours", 0.0) or 0.0)
        uv2_hours = float(state.get("uv2_hours", 0.0) or 0.0)
        warn_days = int(state.get("warn_days", 14) or 14)
        warn_hours = float(state.get("warn_hours", 50.0) or 50.0)
        dfm = load_maintenance_folder_df(maint_folder)
        if dfm.empty:
            return 0, 0
        dfm = compute_maintenance_status_df(
            dfm,
            current_draw_count=current_draw_count,
            furnace_hours=furnace_hours,
            uv1_hours=uv1_hours,
            uv2_hours=uv2_hours,
            warn_days=warn_days,
            warn_hours=warn_hours,
        )
        overdue = int((dfm["Status"] == "OVERDUE").sum())
        due_soon = int((dfm["Status"] == "DUE SOON").sum())
        return overdue, due_soon

    def _render_done_failed_compact(days_visible: int = 4) -> None:
        if not os.path.exists(orders_file):
            st.info("No orders file found.")
            return
        try:
            df = _read_orders_cached(orders_file, _mtime(orders_file))
        except Exception as exc:
            st.error(f"Failed to read {orders_file}: {exc}")
            return
        df = _ensure_cols(df)
        if df.empty:
            st.info("No orders.")
            return
        done_df = df[df[STATUS_COL].astype(str).str.strip().str.lower().eq("done")].copy()
        failed_df = df[df[STATUS_COL].astype(str).str.strip().str.lower().eq("failed")].copy()
        done_df["_ts"] = pd.to_datetime(done_df.get(STATUS_UPDATED_COL, ""), errors="coerce")
        failed_df["_ts"] = pd.to_datetime(failed_df.get(STATUS_UPDATED_COL, ""), errors="coerce")
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days_visible)
        done_recent = done_df[(done_df["_ts"].isna()) | (done_df["_ts"] >= cutoff)].copy().sort_values("_ts", ascending=False).head(6)
        failed_recent = failed_df[(failed_df["_ts"].isna()) | (failed_df["_ts"] >= cutoff)].copy().sort_values("_ts", ascending=False).head(6)

        st.markdown("### Recent draw outcomes")
        c_done, c_failed = st.columns(2, gap="large")
        with c_done:
            st.markdown(f"**Done in last {days_visible} days: {len(done_recent)}**")
            if done_recent.empty:
                st.caption("No recent done draws.")
            else:
                for _, row in done_recent.head(5).iterrows():
                    project = safe_str(row.get("Fiber Project")) or "—"
                    preform = safe_str(row.get("Preform Number")) or "—"
                    when = row.get("_ts")
                    when_s = when.strftime("%Y-%m-%d %H:%M") if pd.notna(when) else "—"
                    st.markdown(f"- `{project}` | Preform `{preform}` | Done `{when_s}`")
        with c_failed:
            st.markdown(f"**Failed in last {days_visible} days: {len(failed_recent)}**")
            if failed_recent.empty:
                st.caption("No recent failed draws.")
            else:
                for _, row in failed_recent.head(5).iterrows():
                    project = safe_str(row.get("Fiber Project")) or "—"
                    preform = safe_str(row.get("Preform Number")) or "—"
                    reason = safe_str(row.get(FAILED_REASON_COL)) or "No reason"
                    st.markdown(f"- `{project}` | Preform `{preform}` | {reason[:92]}")

    def _render_maintenance_faults() -> None:
        overdue, due_soon = _compute_maintenance_counts(P.maintenance_dir, P.dataset_dir)
        in_progress = _compute_maintenance_in_progress()
        open_critical = _compute_open_critical_faults(faults_csv)

        st.markdown("### Maintenance and faults")
        c1, c2, c3, c4 = st.columns(4, gap="medium")
        c1.metric("Overdue", overdue)
        c2.metric("Due soon", due_soon)
        c3.metric("In progress", in_progress)
        c4.metric("Critical faults", open_critical)
        if open_critical:
            st.warning("Open `Maintenance -> Faults / Incidents` to review critical faults.")
        else:
            st.success("No critical faults are currently open.")

    _auto_move_failed_to_pending(days=4)
    st.session_state.setdefault("home_command_focus_panel", "🚀 Draws Monitor")
    selected_panel = st.session_state["home_command_focus_panel"]

    st.markdown(
        """
        <div class="tower-bridge">
          <div class="tower-eyebrow">Flight Computation Interface</div>
          <h1 class="tower-headline">Tower command deck duplicate home</h1>
          <p class="tower-copy">
            This is a real-project duplicate of the home page, rebuilt with a smoother command-deck language.
            It keeps the real Tower content and photo, but presents them as a flowing technical surface instead of boxed panels.
          </p>
          <div class="tower-chip-row">
            <div class="tower-chip"><span>Source</span><strong>Real Tower Home</strong></div>
            <div class="tower-chip"><span>Photo</span><strong>Original Asset</strong></div>
            <div class="tower-chip"><span>Theme</span><strong>Tech Command Deck</strong></div>
          </div>
          <div class="tower-stage">
            <div class="tower-horizon"></div>
            <div class="tower-lane"></div>
            <div class="tower-radar"></div>
            <div class="tower-float top"><strong>Mission scope</strong>Same operational sections as the original home page, presented in a new flight-control language.</div>
            <div class="tower-float mid"><strong>Live system</strong>Schedule, maintenance, parts, and draws still come from the actual Tower app data.</div>
            <div class="tower-float low"><strong>Design goal</strong>More smooth flow, less stacked cards, stronger visual hierarchy.</div>
          </div>
          <div class="tower-surface">
            <div class="tower-section-title">Bridge doctrine</div>
            <div class="tower-surface-copy">
              The hero and navigation now behave like one continuous cockpit plane. Section switching stays intuitive,
              but the page breathes more and lets the background image participate in the interface.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="tower-ribbon">
          <article><h3>Real content</h3><p>The duplicate keeps the actual Tower home sections instead of replacing them with fake demo content.</p></article>
          <article><h3>Smoother flow</h3><p>The structure relies on ribbons, overlays, and rails, not repeated glass rectangles around every block.</p></article>
          <article><h3>Operator-first</h3><p>The page still prioritizes orientation and access to monitoring sections while feeling more technical and cinematic.</p></article>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="tower-deck">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="tower-deck-header">
          <div class="panel-tag">Control Console</div>
          <h2>Switch through the real home sections</h2>
          <p>
            This duplicate keeps the same operational surfaces from Home: draws monitor, done and failed overview,
            schedule, maintenance and faults, and parts orders.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_options = [
        "🚀 Draws Monitor",
        "✅ Done + ❌ Failed",
        "📅 Schedule",
        "🧰 Maintenance + 🚨 Faults",
        "🧩 Parts Orders",
    ]
    nav_cols = st.columns(len(nav_options), gap="small")
    for idx, option in enumerate(nav_options):
        with nav_cols[idx]:
            is_active = selected_panel == option
            if st.button(
                option,
                key=f"home_command_nav_{idx}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state["home_command_focus_panel"] = option
                st.rerun()

    selected_panel = st.session_state["home_command_focus_panel"]
    st.markdown('<div class="tower-content">', unsafe_allow_html=True)
    main_col, side_col = st.columns([1.04, 0.96], gap="large")
    with main_col:
        st.markdown('<div class="tower-content-main">', unsafe_allow_html=True)
        if selected_panel == "🚀 Draws Monitor":
            render_home_draw_orders_overview()
        elif selected_panel == "✅ Done + ❌ Failed":
            _render_done_failed_compact(days_visible=4)
        elif selected_panel == "📅 Schedule":
            render_schedule_home_minimal()
        elif selected_panel == "🧰 Maintenance + 🚨 Faults":
            _render_maintenance_faults()
        elif selected_panel == "🧩 Parts Orders":
            render_parts_orders_home_all()
        st.markdown("</div>", unsafe_allow_html=True)
    with side_col:
        st.markdown('<div class="tower-content-side"><div class="tower-side-rail"><div class="tower-side-shell">', unsafe_allow_html=True)
        st.markdown(f"### {selected_panel}")
        st.markdown(
            """
            <p>
              The right rail acts like a systems note instead of another heavy card.
              It keeps context nearby while the real section content stays the focus.
            </p>
            <div class="tower-side-note">Duplicate home route using the real Tower photo and data sources.</div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("</div></div></div>", unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)
