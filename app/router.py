from __future__ import annotations

import streamlit as st

from helpers.constants import STATUS_COL, STATUS_UPDATED_COL
from helpers.orders_status import parse_dt_safe
from helpers.text_utils import now_str, safe_str
from renders.components.home_sections import (
    render_done_home_section,
    render_home_draw_orders_overview,
    render_parts_orders_home_all,
    render_schedule_home_minimal,
)
from renders.tabs.consumables_tab import render_consumables_tab
from renders.tabs.dashboard_tab import render_dashboard_tab
from renders.tabs.data_diagnostics_tab import render_data_diagnostics_tab
from renders.tabs.development_process_tab import render_development_process_tab
from renders.tabs.draw_finalize_tab import render_draw_finalize_tab
from renders.tabs.home_tab import render_home_tab
from renders.tabs.home_tab_command_deck import render_home_tab_command_deck
from renders.tabs.maintenance_tab import render_maintenance_tab
from renders.tabs.order_draw_tab import render_order_draw_tab
from renders.tabs.process_setup_tab import render_process_setup_tab_main
from renders.tabs.report_center_tab import render_report_center_tab
from renders.tabs.schedule_tab import render_schedule_tab
from renders.tabs.sql_lab import render_sql_lab_tab
from renders.tabs.tower_parts_tab import render_tower_parts_tab


def render_selected_tab(tab_selection: str, P, image_base64: str, failed_reason_col: str, orders_file: str) -> None:
    if tab_selection == "🏠 Home":
        render_home_tab(
            P=P,
            image_base64=image_base64,
            STATUS_COL=STATUS_COL,
            STATUS_UPDATED_COL=STATUS_UPDATED_COL,
            FAILED_REASON_COL=failed_reason_col,
            parse_dt_safe=parse_dt_safe,
            now_str=now_str,
            safe_str=safe_str,
            render_home_draw_orders_overview=render_home_draw_orders_overview,
            render_done_home_section=render_done_home_section,
            render_schedule_home_minimal=render_schedule_home_minimal,
            render_parts_orders_home_all=render_parts_orders_home_all,
        )
    elif tab_selection == "🛸 Home Command Deck":
        render_home_tab_command_deck(
            P=P,
            image_base64=image_base64,
            STATUS_COL=STATUS_COL,
            STATUS_UPDATED_COL=STATUS_UPDATED_COL,
            FAILED_REASON_COL=failed_reason_col,
            parse_dt_safe=parse_dt_safe,
            now_str=now_str,
            safe_str=safe_str,
            render_home_draw_orders_overview=render_home_draw_orders_overview,
            render_schedule_home_minimal=render_schedule_home_minimal,
            render_parts_orders_home_all=render_parts_orders_home_all,
        )
    elif tab_selection == "⚙️ Process Setup":
        render_process_setup_tab_main(P, orders_file)
    elif tab_selection == "📊 Dashboard":
        render_dashboard_tab(P)
    elif tab_selection == "✅ Draw Finalize":
        render_draw_finalize_tab(P)
    elif tab_selection == "🍃 Tower state - Consumables and dies":
        render_consumables_tab(P)
    elif tab_selection == "🗂️ Report Center":
        render_report_center_tab(P)
    elif tab_selection == "📅 Schedule":
        render_schedule_tab(P)
    elif tab_selection == "📦 Order Draw":
        render_order_draw_tab(P)
    elif tab_selection == "🛠️ Tower Parts":
        render_tower_parts_tab(P)
    elif tab_selection == "🧪 Development Process":
        render_development_process_tab(P)
    elif tab_selection == "🧰 Maintenance":
        render_maintenance_tab(P)
    elif tab_selection == "🩺 Data Diagnostics":
        render_data_diagnostics_tab(P)
    elif tab_selection == "🧪 SQL Lab":
        render_sql_lab_tab(P)
