from __future__ import annotations

import streamlit as st


# Sidebar groups are the single source of truth for navigation structure.
NAV_GROUPS = {
    "🏠 Home & Project Management": [
        "🏠 Home",
        "🛸 Home Command Deck",
        "📅 Schedule",
        "📦 Order Draw",
        "🛠️ Tower Parts",
    ],
    "⚙️ Operations": [
        "🍃 Tower state - Consumables and dies",
        "⚙️ Process Setup",
        "🧰 Maintenance",
        "📊 Dashboard",
        "✅ Draw Finalize",
        "🛠️ Tower Parts",
        "🩺 Data Diagnostics",
        "🗂️ Report Center",
    ],
    "📚 Monitoring &  Research": [
        "🧪 SQL Lab",
        "🧪 Development Process",
    ],
}

SAFE_NAV_GROUPS = {
    "🛡 Safe Mode": [
        "🏠 Home",
        "🛸 Home Command Deck",
        "🩺 Data Diagnostics",
        "🧪 SQL Lab",
    ]
}

TAB_TO_GROUPS = {}
for group_name, tabs in NAV_GROUPS.items():
    for tab_name in tabs:
        TAB_TO_GROUPS.setdefault(tab_name, []).append(group_name)
GROUPS = list(NAV_GROUPS.keys())


def init_session_state() -> None:
    st.session_state.setdefault("selected_tab", None)
    st.session_state.setdefault("tab_select", "🏠 Home")
    st.session_state.setdefault("last_tab", "🏠 Home")
    st.session_state.setdefault("nav_last_tab_by_group", {})
    st.session_state.setdefault("good_zones", [])


def resolve_group_for_tab(tab: str, tab_to_groups=None, fallback: str = "🏠 Home & Project Management") -> str:
    tab_to_groups = tab_to_groups or TAB_TO_GROUPS
    groups_for_tab = tab_to_groups.get(tab, [])
    current_group = st.session_state.get("nav_group_select")
    if current_group in groups_for_tab:
        return current_group
    if fallback in groups_for_tab:
        return fallback
    if groups_for_tab:
        return groups_for_tab[0]
    return fallback


def _build_groups(safe_mode: bool):
    groups = SAFE_NAV_GROUPS if safe_mode else NAV_GROUPS
    tab_to_groups = {}
    for group_name, tabs in groups.items():
        for tab_name in tabs:
            tab_to_groups.setdefault(tab_name, []).append(group_name)
    return groups, tab_to_groups, list(groups.keys())


def render_sidebar_navigation(safe_mode: bool = False) -> str:
    nav_groups, tab_to_groups, groups = _build_groups(safe_mode)

    with st.sidebar:
        st.markdown(
            """
            <style>
            /* Sidebar base: light blue gradient, compact density */
            [data-testid="stSidebar"] {
                background:
                    radial-gradient(120% 60% at 0% 0%, rgba(86, 180, 255, 0.20) 0%, rgba(86, 180, 255, 0) 55%),
                    linear-gradient(180deg, #0a111b 0%, #0c1a2a 42%, #070d15 100%);
            }
            [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
                font-size: 1.05rem;
                margin-bottom: 0.25rem;
            }
            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] p,
            [data-testid="stSidebar"] div,
            [data-testid="stSidebar"] span {
                font-size: 0.90rem;
            }

            /* Group select: compact */
            [data-testid="stSidebar"] [data-testid="stSelectbox"] > div {
                margin-bottom: 0.2rem;
            }
            [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] {
                min-height: 34px;
                border: 0 !important;
                border-radius: 0 !important;
                box-shadow: none !important;
                background: transparent !important;
                background-image: none !important;
            }
            [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
            [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"] {
                border: 0 !important;
                border-radius: 0 !important;
                box-shadow: none !important;
                background: transparent !important;
                background-image: none !important;
            }
            [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] *:focus,
            [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] *:focus-visible {
                outline: none !important;
                box-shadow: none !important;
            }
            /* Hard override specifically for Group select widget (nav_group_select) */
            [data-testid="stSidebar"] .st-key-nav_group_select,
            [data-testid="stSidebar"] .st-key-nav_group_select * {
                box-shadow: none !important;
                outline: none !important;
            }
            [data-testid="stSidebar"] .st-key-nav_group_select div[data-baseweb="select"],
            [data-testid="stSidebar"] .st-key-nav_group_select div[data-baseweb="select"] > div,
            [data-testid="stSidebar"] .st-key-nav_group_select div[data-baseweb="select"] [role="combobox"],
            [data-testid="stSidebar"] .st-key-nav_group_select div[data-baseweb="input"] > div,
            [data-testid="stSidebar"] .st-key-nav_group_select div[data-baseweb="tag"],
            [data-testid="stSidebar"] .st-key-nav_group_select span[data-baseweb="tag"] {
                background: transparent !important;
                background-image: none !important;
                border: 0 !important;
                border-color: transparent !important;
                border-radius: 0 !important;
                box-shadow: none !important;
                color: #d7e8f8 !important;
            }

            /* Radio list: plain/compact with strong selected state */
            [data-testid="stSidebar"] [role="radiogroup"] {
                gap: 0.18rem !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] > label {
                background: transparent !important;
                border: 0 !important;
                border-radius: 0;
                padding: 0.12rem 0.08rem;
                min-height: 1.55rem;
                box-shadow: none !important;
                backdrop-filter: none;
                -webkit-backdrop-filter: none;
                user-select: none !important;
                -webkit-user-select: none !important;
                transition: all 140ms ease;
            }
            [data-testid="stSidebar"] [role="radiogroup"] > label > div {
                background: transparent !important;
                box-shadow: none !important;
                border: 0 !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] [data-baseweb="radio"],
            [data-testid="stSidebar"] [role="radiogroup"] [data-baseweb="radio"] > div,
            [data-testid="stSidebar"] [role="radiogroup"] [data-baseweb="radio"] div {
                background: transparent !important;
                box-shadow: none !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] > label:hover {
                background: transparent !important;
                box-shadow: none !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] > label:active {
                background: transparent !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] > label[data-checked="true"],
            [data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
                background: transparent !important;
                box-shadow: inset 2px 0 0 rgba(130, 210, 255, 0.95) !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] > label[data-checked="true"] p,
            [data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) p,
            [data-testid="stSidebar"] [role="radiogroup"] > label[data-checked="true"] span,
            [data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) span {
                color: #eaf6ff !important;
                font-weight: 700 !important;
                text-shadow: 0 0 8px rgba(101, 196, 255, 0.38) !important;
            }

            /* Radio marker: clean white ring + dot */
            [data-testid="stSidebar"] [data-baseweb="radio"] input + div {
                border-color: rgba(238, 246, 255, 0.80) !important;
                background: transparent !important;
            }
            [data-testid="stSidebar"] [data-baseweb="radio"] input:checked + div {
                border-color: rgba(255, 255, 255, 1) !important;
                background: transparent !important;
                box-shadow: inset 0 0 0 4px rgba(255, 255, 255, 1) !important;
            }
            [data-testid="stSidebar"] [data-baseweb="radio"] input:focus + div,
            [data-testid="stSidebar"] [data-baseweb="radio"] input:active + div {
                background: transparent !important;
                box-shadow: none !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] input:focus,
            [data-testid="stSidebar"] [role="radiogroup"] input:focus-visible,
            [data-testid="stSidebar"] [role="radiogroup"] input:active {
                outline: none !important;
                box-shadow: none !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] > label:focus,
            [data-testid="stSidebar"] [role="radiogroup"] > label:focus-visible,
            [data-testid="stSidebar"] [role="radiogroup"] > label *:focus,
            [data-testid="stSidebar"] [role="radiogroup"] > label *:focus-visible {
                outline: none !important;
                box-shadow: none !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] ::selection {
                background: transparent !important;
                color: inherit !important;
            }
            /* Hard focus reset for BaseWeb/Streamlit internals to prevent white jump box */
            [data-testid="stSidebar"] [role="radiogroup"] [tabindex]:focus,
            [data-testid="stSidebar"] [role="radiogroup"] [tabindex]:focus-visible,
            [data-testid="stSidebar"] [role="radiogroup"] [aria-checked]:focus,
            [data-testid="stSidebar"] [role="radiogroup"] [aria-checked]:focus-visible,
            [data-testid="stSidebar"] [role="radiogroup"] div:focus,
            [data-testid="stSidebar"] [role="radiogroup"] div:focus-visible,
            [data-testid="stSidebar"] [role="radiogroup"] span:focus,
            [data-testid="stSidebar"] [role="radiogroup"] span:focus-visible,
            [data-testid="stSidebar"] [role="radiogroup"] p:focus,
            [data-testid="stSidebar"] [role="radiogroup"] p:focus-visible {
                outline: none !important;
                box-shadow: none !important;
                background: transparent !important;
                border-color: transparent !important;
            }
            [data-testid="stSidebar"] [role="radiogroup"] * {
                -webkit-tap-highlight-color: transparent !important;
            }
            /* Global sidebar focus/selection hard reset (fallback for browser/user-agent styles) */
            [data-testid="stSidebar"] *:focus,
            [data-testid="stSidebar"] *:focus-visible,
            [data-testid="stSidebar"] *:active {
                outline: none !important;
                box-shadow: none !important;
            }
            [data-testid="stSidebar"] *::selection {
                background: transparent !important;
                color: inherit !important;
            }
            [data-testid="stSidebar"] *::-moz-selection {
                background: transparent !important;
                color: inherit !important;
            }

            /* Custom page list buttons (replaces radio to avoid focus artifact) */
            [data-testid="stSidebar"] [data-testid="stButton"] > button {
                width: 100%;
                justify-content: flex-start;
                background: transparent !important;
                background-image: none !important;
                border: 0 !important;
                border-color: transparent !important;
                box-shadow: none !important;
                color: #b9cce0 !important;
                font-size: 0.90rem !important;
                line-height: 1.15 !important;
                min-height: 1.52rem !important;
                height: 1.52rem !important;
                padding: 0.08rem 0.12rem !important;
                text-align: left !important;
                border-radius: 0 !important;
                user-select: none !important;
                -webkit-user-select: none !important;
                text-shadow: none !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] [data-baseweb="button"],
            [data-testid="stSidebar"] [data-testid="stButton"] [data-baseweb="button"]:hover,
            [data-testid="stSidebar"] [data-testid="stButton"] [data-baseweb="button"]:active,
            [data-testid="stSidebar"] [data-testid="stButton"] [data-baseweb="button"]:focus,
            [data-testid="stSidebar"] [data-testid="stButton"] [data-baseweb="button"]:focus-visible {
                background: transparent !important;
                background-image: none !important;
                border: 0 !important;
                border-color: transparent !important;
                border-radius: 0 !important;
                box-shadow: none !important;
                outline: none !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"]:focus-within {
                outline: none !important;
                box-shadow: none !important;
                border: 0 !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] > button:hover {
                background: transparent !important;
                color: #d8e9fb !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"] {
                color: #eef7ff !important;
                font-weight: 740 !important;
                background: transparent !important;
                background-image: none !important;
                border: 0 !important;
                border-color: transparent !important;
                text-shadow: none !important;
                box-shadow: inset 2px 0 0 rgba(125, 205, 255, 0.95) !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"]:hover {
                background: transparent !important;
                background-image: none !important;
                border: 0 !important;
                border-color: transparent !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"] *,
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"] span,
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"] p,
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"] div {
                font-weight: 740 !important;
                color: #eef7ff !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] > button:disabled {
                opacity: 1 !important;
                color: #eef7ff !important;
                font-weight: 740 !important;
                background: transparent !important;
                background-image: none !important;
                border: 0 !important;
                border-color: transparent !important;
                box-shadow: inset 2px 0 0 rgba(125, 205, 255, 0.95) !important;
                cursor: default !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] > button:disabled * {
                color: #eef7ff !important;
                font-weight: 740 !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] > button:focus,
            [data-testid="stSidebar"] [data-testid="stButton"] > button:focus-visible,
            [data-testid="stSidebar"] [data-testid="stButton"] > button:active {
                outline: none !important;
                box-shadow: none !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"]:focus,
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"]:focus-visible,
            [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"]:active {
                background: transparent !important;
                background-image: none !important;
                box-shadow: inset 2px 0 0 rgba(125, 205, 255, 0.95) !important;
            }
            [data-testid="stSidebar"] [data-testid="stButton"] {
                margin-left: 0.32rem !important;
                margin-right: 0.06rem !important;
                margin-top: 0 !important;
                margin-bottom: 0 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("### 📌 Navigation")

        had_shortcut = st.session_state.get("selected_tab") is not None
        desired_tab = (
            st.session_state.get("selected_tab")
            or st.session_state.get("tab_select")
            or st.session_state.get("last_tab")
            or "🏠 Home"
        )
        st.session_state["selected_tab"] = None

        if desired_tab not in tab_to_groups:
            desired_tab = list(nav_groups.values())[0][0]

        desired_group = resolve_group_for_tab(desired_tab, tab_to_groups=tab_to_groups)
        jump_tab = desired_tab
        jump_group = resolve_group_for_tab(jump_tab, tab_to_groups=tab_to_groups, fallback=desired_group)

        # Only force-sync when arriving via shortcut or first init.
        if had_shortcut or "nav_group_select" not in st.session_state:
            st.session_state["nav_group_select"] = jump_group
            st.session_state["tab_select"] = jump_tab
            st.session_state["last_tab"] = jump_tab
            st.session_state["nav_last_tab_by_group"][jump_group] = jump_tab

        def _on_group_change():
            group = st.session_state.get("nav_group_select")
            last_by_group = st.session_state.get("nav_last_tab_by_group", {})
            next_tab = last_by_group.get(group, nav_groups.get(group, [None])[0])
            if next_tab:
                st.session_state["tab_select"] = next_tab
                st.session_state["last_tab"] = next_tab
                st.session_state["nav_last_tab_by_group"][group] = next_tab

        def _on_page_change():
            tab = st.session_state.get("tab_select")
            group = st.session_state.get("nav_group_select", "🏠 Home & Project Management")
            if tab not in nav_groups.get(group, []):
                group = resolve_group_for_tab(tab, tab_to_groups=tab_to_groups, fallback=group)
                st.session_state["nav_group_select"] = group
            st.session_state["last_tab"] = tab
            st.session_state["nav_last_tab_by_group"][group] = tab

        group = st.selectbox(
            "📁 Group",
            groups,
            key="nav_group_select",
            on_change=_on_group_change,
        )

        current_tab = st.session_state.get("tab_select", desired_tab)
        if current_tab not in nav_groups[group]:
            current_tab = st.session_state.get("nav_last_tab_by_group", {}).get(group, nav_groups[group][0])
            st.session_state["tab_select"] = current_tab

        st.markdown("**📄 Page**")
        for i, tab_option in enumerate(nav_groups[group]):
            is_selected = st.session_state.get("tab_select") == tab_option
            if st.button(
                tab_option,
                key=f"nav_page_btn_{group}_{i}",
                type="secondary",
                disabled=is_selected,
                use_container_width=True,
            ):
                st.session_state["tab_select"] = tab_option
                _on_page_change()
                st.rerun()

        tab_selection = st.session_state.get("tab_select", current_tab)

        st.session_state["last_tab"] = tab_selection
        st.session_state["nav_last_tab_by_group"][group] = tab_selection
        return tab_selection
