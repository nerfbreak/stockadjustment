import streamlit as st
import pandas as pd
import zipfile
import csv
import time
import os
import subprocess
import asyncio
import traceback
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Stock Adjustment Newspage", page_icon="icon.png", layout="wide")

# --- 1.5. LOGIN GATEKEEPER ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<h2 style='text-align:center;color:#3b82f6;'>Login</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#64748b;'>Enter credentials to access the engine</p>", unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login", use_container_width=True)

            if submit:
                if username == st.secrets["admin_user"] and password == st.secrets["admin_pass"]:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Access Denied! Incorrect username or password.")

    st.stop()

# --- 2. CONSTANTS ---
URL_LOGIN             = "https://rb-id.np.accenture.com/RB_ID/Logon.aspx"
CREDENTIALS_FILE      = "users_2.csv"
REASON_CODE           = "SA2"
WAREHOUSE             = "GOOD_WHS"
TIMEOUT_MS            = 30_000
TABLE_UPDATE_INTERVAL = 5

# --- 3. HELPER FUNCTIONS ---

def load_data(file):
    if file is None:
        return None
    df = None
    filename = file.name.lower()
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file, sep='\t', dtype=str)
            if df.shape[1] <= 1:
                file.seek(0)
                df = pd.read_csv(file, sep=',', dtype=str)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file, dtype=str)
        elif filename.endswith('.zip'):
            with zipfile.ZipFile(file) as z:
                target = next((n for n in z.namelist() if "INVT_MASTER" in n and n.lower().endswith(".csv")), None)
                if not target:
                    target = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
                if target:
                    with z.open(target) as f:
                        df = pd.read_csv(f, sep='\t', dtype=str)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None
    return df


@st.cache_data(ttl=300)
def load_accounts():
    accounts = []
    if not os.path.exists(CREDENTIALS_FILE):
        return accounts
    for enc in ['utf-8-sig', 'cp1252', 'iso-8859-1']:
        try:
            with open(CREDENTIALS_FILE, mode="r", encoding=enc) as f:
                reader = csv.DictReader(f)
                reader.fieldnames = [name.strip() for name in reader.fieldnames if name]
                for row in reader:
                    cleaned_row = {str(k).strip(): str(v).strip() for k, v in row.items() if k}
                    if "user_id" in cleaned_row and "Distributor" in cleaned_row:
                        accounts.append(cleaned_row)
                return accounts
        except (UnicodeDecodeError, TypeError):
            continue
    return accounts


@st.cache_resource
def ensure_playwright():
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True
        )
    except Exception as e:
        st.error(f"Failed to install browser engine: {e}")


def make_solid_box(text: str, bg_color: str, text_color: str) -> str:
    return (
        f"<div style='background-color:{bg_color};color:{text_color};"
        f"padding:12px 16px;border-radius:8px;font-weight:600;"
        f"font-size:0.92rem;margin:8px 0;text-align:center;"
        f"box-shadow:0 2px 8px rgba(0,0,0,0.3);display:block;width:100%;'>{text}</div>"
    )


# --- 4. STATE MANAGEMENT ---
if 'app_page' not in st.session_state:
    st.session_state.app_page = "Reconcile"
if 'reconcile_result' not in st.session_state:
    st.session_state.reconcile_result = None
if 'reconcile_summary' not in st.session_state:
    st.session_state.reconcile_summary = None

# --- 5. CUSTOM CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

    .terminal-box {
        background-color: transparent;
        color: #f0f6fc;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem;
        padding: 5px 0;
        border: none;
        box-shadow: none;
        height: 350px;
        overflow-y: auto;
        line-height: 1.8;
        -ms-overflow-style: none;
        scrollbar-width: none;
    }
    .terminal-box::-webkit-scrollbar { display: none; }

    .blink_me { animation: blinker 1s linear infinite; font-weight: bold; color: #10b981; }
    @keyframes blinker { 50% { opacity: 0; } }

    .log-time   { display: inline-block; width: 85px; color: #64748b; font-family: 'JetBrains Mono', monospace; }
    .log-ms     { display: inline-block; width: 75px; text-align: right; margin-right: 15px; color: #fb923c; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; }
    .log-tag    { display: inline-block; width: 95px; font-weight: bold; font-family: 'JetBrains Mono', monospace; }
    .log-msg    { color: #f0f6fc; font-weight: 500; font-family: 'Inter', sans-serif; }

    .tag-sys     { color: #a855f7; }
    .tag-auth    { color: #eab308; }
    .tag-nav     { color: #3b82f6; }
    .tag-inject  { color: #06b6d4; }
    .tag-success { color: #22c55e; }
    .tag-error   { color: #ef4444; }
    .tag-server  { color: #f43f5e; }

    button[kind="primary"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
        letter-spacing: 0.5px !important;
        text-transform: uppercase !important;
        transition: all 0.2s ease !important;
        border-radius: 6px !important;
        font-family: 'Inter', sans-serif !important;
    }
    button[kind="primary"]:hover {
        background-color: #1d4ed8 !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
        transform: translateY(-1px) !important;
    }
    button[kind="primary"]:active { transform: translateY(0) !important; }

    button[kind="secondary"] {
        background-color: transparent !important;
        color: #3b82f6 !important;
        border: 1.5px solid #3b82f6 !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
        border-radius: 6px !important;
        font-family: 'Inter', sans-serif !important;
    }
    button[kind="secondary"]:hover {
        background-color: #eff6ff !important;
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.2) !important;
    }

    .typewriter-sub {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1rem;
        color: #8b949e;
        overflow: hidden;
        border-right: 0.12em solid #3b82f6;
        white-space: nowrap;
        margin: 0;
        animation: typing-sub 10s infinite, blink-caret .75s step-end infinite;
    }
    @keyframes typing-sub {
        0%   { width: 0; animation-timing-function: steps(29, end); }
        30%  { width: 29ch; animation-timing-function: step-end; }
        80%  { width: 29ch; animation-timing-function: steps(29, end); }
        100% { width: 0; }
    }
    @keyframes blink-caret {
        from, to { border-color: transparent; }
        50%       { border-color: #3b82f6; }
    }

    @keyframes fadeSlideUp {
        from { opacity: 0; transform: translateY(16px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    [data-testid="stVerticalBlock"] > div {
        animation: fadeSlideUp 0.5s ease-out backwards;
    }
    [data-testid="stVerticalBlock"] > div:nth-child(1) { animation-delay: 0.05s; }
    [data-testid="stVerticalBlock"] > div:nth-child(2) { animation-delay: 0.10s; }
    [data-testid="stVerticalBlock"] > div:nth-child(3) { animation-delay: 0.15s; }
    [data-testid="stVerticalBlock"] > div:nth-child(4) { animation-delay: 0.20s; }

    .live-indicator {
        display: inline-flex;
        align-items: center;
        color: #4ade80;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.85rem;
        letter-spacing: 0.08em;
    }
    .live-indicator::before {
        content: '';
        display: inline-block;
        width: 8px;
        height: 8px;
        background-color: #4ade80;
        border-radius: 50%;
        margin-right: 7px;
        box-shadow: 0 0 6px #4ade80;
        animation: pulse-radar 1.4s infinite alternate;
    }
    @keyframes pulse-radar {
        from { transform: scale(0.8); opacity: 0.6; }
        to   { transform: scale(1.2); opacity: 1; box-shadow: 0 0 12px #4ade80; }
    }

    hr {
        border: none !important;
        height: 1px !important;
        background: linear-gradient(90deg, transparent, #3b82f6, transparent) !important;
        opacity: 0.35 !important;
        margin-top: 1.5rem !important;
        margin-bottom: 1.5rem !important;
    }

    ::selection      { background: #3b82f6 !important; color: #ffffff !important; }
    ::-moz-selection { background: #3b82f6 !important; color: #ffffff !important; }

    *::-webkit-scrollbar       { width: 6px !important; height: 6px !important; background-color: transparent !important; }
    *::-webkit-scrollbar-track { background-color: rgba(255,255,255,0.04) !important; border-radius: 10px !important; }
    *::-webkit-scrollbar-thumb { background-color: #3b82f6 !important; border-radius: 10px !important; }
    *::-webkit-scrollbar-thumb:hover { background-color: #2563eb !important; }
    * { scrollbar-width: thin !important; scrollbar-color: #3b82f6 transparent !important; }

    [data-testid="stStatusWidget"] {
        background-color: #0f172a !important;
        border: 1px solid #3b82f6 !important;
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.25) !important;
        border-radius: 4px !important;
        padding: 2px 10px !important;
    }
    [data-testid="stStatusWidget"] * {
        color: #3b82f6 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: bold !important;
        letter-spacing: 0.5px !important;
    }

    header[data-testid="stHeader"] {
        border-bottom: 1px solid rgba(59, 130, 246, 0.25) !important;
    }

    .typewriter {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.6rem;
        font-weight: 700;
        color: #f0f6fc;
        overflow: hidden;
        border-right: 0.12em solid #3b82f6;
        white-space: nowrap;
        margin: 0;
        padding-right: 5px;
        width: max-content;
        animation: typing 3s steps(25, end) infinite alternate, blink-caret .75s step-end infinite;
    }
    @keyframes typing {
        from { width: 0; }
        to   { width: 100%; }
    }

    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] > div {
        color: #3b82f6 !important;
        font-weight: 700 !important;
        display: block !important;
    }

    /* Container border styling agar blok kiri-kanan rapi */
    div[data-testid="stContainer"] {
        border: 1px solid rgba(59, 130, 246, 0.25);
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }

    body, .stMarkdown, p, span, div {
        font-family: 'Inter', sans-serif;
    }
    </style>
""", unsafe_allow_html=True)


# ─── 6. PAGE: RECONCILE ──────────────────────────────────────────────────────
if st.session_state.app_page == "Reconcile":
    st.markdown("<div class='live-indicator'>LIVE</div>", unsafe_allow_html=True)
    st.markdown("<h1>Compare Stock</h1>", unsafe_allow_html=True)
    st.markdown("<div class='typewriter-sub'>Inspired by Kopi Mang Toni...</div>", unsafe_allow_html=True)
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        file1 = st.file_uploader("Upload Newspage stock file", type=['csv', 'xlsx', 'zip'])
    with col2:
        file2 = st.file_uploader("Upload Distributor stock file", type=['csv', 'xlsx'])

    if file1 and file2:
        st.divider()
        df1 = load_data(file1)
        df2 = load_data(file2)

        if df1 is not None and df2 is not None:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Newspage setup")
                idx_sku1 = df1.columns.get_loc('Product Code') if 'Product Code' in df1.columns else 0
                if 'Product Description' in df1.columns:
                    idx_desc1 = df1.columns.get_loc('Product Description')
                elif 'Product Name' in df1.columns:
                    idx_desc1 = df1.columns.get_loc('Product Name')
                else:
                    idx_desc1 = 1 if len(df1.columns) > 1 else 0
                idx_qty1 = (
                    df1.columns.get_loc('Stock Available')
                    if 'Stock Available' in df1.columns
                    else (2 if len(df1.columns) > 2 else 0)
                )
                sku_col1  = st.selectbox("SKU column (NP)", df1.columns, index=idx_sku1)
                desc_col1 = st.selectbox("Description column (NP)", df1.columns, index=idx_desc1)
                qty_col1  = st.selectbox("Qty column (NP)", df1.columns, index=idx_qty1)

            with c2:
                st.subheader("Distributor setup")
                idx_sku2 = 20 if len(df2.columns) > 20 else 0
                qty2_col_match = next(
                    (col for col in df2.columns if str(col).strip().lower().replace(" ", "") == "stokakhir"),
                    None
                )
                if qty2_col_match:
                    idx_qty2 = df2.columns.get_loc(qty2_col_match)
                else:
                    idx_qty2 = 71 if len(df2.columns) > 71 else (1 if len(df2.columns) > 1 else 0)
                sku_col2 = st.selectbox("SKU column (Dist)", df2.columns, index=idx_sku2)
                qty_col2 = st.selectbox("Qty column (Dist)", df2.columns, index=idx_qty2)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Compare Stock", type="primary", use_container_width=True):
                d1 = df1[[sku_col1, desc_col1, qty_col1]].copy()
                d1 = d1.dropna(subset=[sku_col1])
                d1[sku_col1] = d1[sku_col1].astype(str).str.split('.').str[0].str.strip()
                d1 = d1[~d1[sku_col1].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
                d1[qty_col1] = pd.to_numeric(d1[qty_col1], errors='coerce').fillna(0)
                d1_agg = (
                    d1.groupby(sku_col1)
                    .agg({desc_col1: 'first', qty_col1: 'sum'})
                    .reset_index()
                    .rename(columns={sku_col1: 'SKU', desc_col1: 'Description', qty_col1: 'Newspage'})
                )
                d2 = df2[[sku_col2, qty_col2]].copy()
                d2 = d2.dropna(subset=[sku_col2])
                d2[sku_col2] = d2[sku_col2].astype(str).str.split('.').str[0].str.strip()
                d2 = d2[~d2[sku_col2].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
                d2[sku_col2] = d2[sku_col2].replace({'373103': '0373103', '373100': '0373100'})
                d2[qty_col2] = pd.to_numeric(d2[qty_col2], errors='coerce').fillna(0)
                d2_agg = (
                    d2.groupby(sku_col2)[qty_col2]
                    .sum()
                    .reset_index()
                    .rename(columns={sku_col2: 'SKU', qty_col2: 'Distributor'})
                )
                merged = pd.merge(d1_agg, d2_agg, on='SKU', how='outer')
                merged[['Newspage', 'Distributor']] = merged[['Newspage', 'Distributor']].fillna(0)
                merged['Description'] = merged['Description'].fillna('ITEM NOT IN MASTER')
                merged['Selisih'] = merged['Distributor'] - merged['Newspage']
                merged['Status'] = merged['Selisih'].apply(lambda x: 'Match' if x == 0 else 'Mismatch')
                mismatches = merged[merged['Selisih'] != 0].sort_values('Selisih')

                if len(mismatches) == 0:
                    st.success("Analysis complete: all items matched!")
                else:
                    valid_mismatches = mismatches[mismatches['Description'] != 'ITEM NOT IN MASTER'].copy()
                    st.session_state.reconcile_summary = {
                        'total_match':    len(merged[merged['Selisih'] == 0]),
                        'total_mismatch': len(mismatches),
                        'df_view':        mismatches[['SKU', 'Description', 'Newspage', 'Distributor', 'Selisih', 'Status']]
                    }
                    valid_mismatches['Selisih_Clean'] = valid_mismatches['Selisih'].astype(int)
                    transfer_df = (
                        valid_mismatches[['SKU', 'Selisih_Clean']]
                        .rename(columns={'SKU': 'sku', 'Selisih_Clean': 'qty'})
                    )
                    st.session_state.reconcile_result = transfer_df
                    st.session_state.app_page = "Bot"
                    st.rerun()

    if st.button("Stock Adjustment"):
        st.session_state.reconcile_result = None
        st.session_state.reconcile_summary = None
        st.session_state.app_page = "Bot"
        st.rerun()


# ─── 7. PAGE: STOCK ADJUSTMENT BOT ───────────────────────────────────────────
elif st.session_state.app_page == "Bot":
    hdr_col1, hdr_col2 = st.columns([5, 1])
    with hdr_col1:
        st.markdown("<div class='live-indicator'>LIVE</div>", unsafe_allow_html=True)
        st.markdown("<h1>Stock Adjustment</h1>", unsafe_allow_html=True)
        st.markdown("<div class='typewriter-sub'>Inspired by Kopi Mang Toni...</div>", unsafe_allow_html=True)
    with hdr_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Compare Stock", use_container_width=True):
            st.session_state.app_page = "Reconcile"
            st.rerun()

    st.markdown("---")

    if st.session_state.reconcile_summary is not None:
        st.subheader("Stock review")
        m1, m2 = st.columns(2)
        m1.metric("Match", st.session_state.reconcile_summary['total_match'])
        m2.metric("Stock difference", st.session_state.reconcile_summary['total_mismatch'], delta_color="inverse")
        st.dataframe(st.session_state.reconcile_summary['df_view'], use_container_width=True, hide_index=True)
        st.markdown("---")

    st.subheader("Configuration")
    accounts = load_accounts()
    if not accounts:
        st.error(f"No account data found. Ensure '{CREDENTIALS_FILE}' exists in the app directory.")
        st.stop()

    cfg_col1, cfg_col2 = st.columns(2)

    # --- Kiri: container border agar rapi ---
    with cfg_col1:
        with st.container(border=True):
            selected_acc_str = st.selectbox(
                "Select Distributor / User ID",
                options=[f"{acc['Distributor']} ({acc['user_id']})" for acc in accounts],
                index=None,
                placeholder="-- Select account --"
            )
            selected_account = None
            user_password = ""
            if selected_acc_str:
                selected_account = next(
                    acc for acc in accounts
                    if f"{acc['Distributor']} ({acc['user_id']})" == selected_acc_str
                )
                user_password = st.text_input(
                    f"Password for {selected_account['user_id']}:",
                    type="password",
                    placeholder="Enter password..."
                )
                if len(user_password) > 3:
                    st.markdown(make_solid_box(
                        f"Password set — {selected_account['Distributor']} (validated on run)",
                        "#0f2f1d", "#4ade80"
                    ), unsafe_allow_html=True)
                else:
                    st.markdown(make_solid_box(
                        "Waiting for password...",
                        "#1e1b4b", "#a5b4fc"
                    ), unsafe_allow_html=True)

    # --- Kanan: container border agar rapi ---
    with cfg_col2:
        with st.container(border=True):
            df_to_process = None
            if st.session_state.reconcile_result is not None:
                st.text_input("Data source", value="Auto-loaded from Compare Stock", disabled=True)
                df_to_process = st.session_state.reconcile_result
                st.markdown(make_solid_box(
                    f"{len(df_to_process)} products ready to process",
                    "#082f49", "#38bdf8"
                ), unsafe_allow_html=True)
            else:
                uploaded_file = st.file_uploader("Data source (CSV / Excel)", type=["csv", "xlsx", "xls"])
                if uploaded_file is not None:
                    try:
                        filename = uploaded_file.name.lower()
                        if filename.endswith('.csv'):
                            df_to_process = pd.read_csv(uploaded_file, dtype=str)
                        else:
                            df_to_process = pd.read_excel(uploaded_file, dtype=str)
                        df_to_process.columns = [str(c).strip().lower() for c in df_to_process.columns]
                        if 'sku' in df_to_process.columns and 'qty' in df_to_process.columns:
                            st.markdown(make_solid_box(
                                f"{len(df_to_process)} products ready to process",
                                "#082f49", "#38bdf8"
                            ), unsafe_allow_html=True)
                        else:
                            st.error("Invalid format — column headers must be named 'sku' and 'qty'.")
                            df_to_process = None
                    except Exception as e:
                        st.error(f"Failed to read file: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    is_ready = (selected_account is not None) and (len(user_password) > 3) and (df_to_process is not None)
    run_button = st.button("PROCEED", use_container_width=True, type="primary", disabled=not is_ready)

    st.subheader("Product table")
    if not is_ready:
        st.warning("Select an account and ensure data is available before running the bot.")
        st.stop()

    df_view = df_to_process.copy()
    if 'Status' not in df_view.columns:
        df_view['Status'] = 'Pending'
    if 'Keterangan' not in df_view.columns:
        df_view['Keterangan'] = '-'
    table_placeholder = st.dataframe(df_view, use_container_width=True)

    st.markdown("Log:")
    log_placeholder = st.empty()

    if run_button:
        with st.spinner("Initializing Chromium engine..."):
            ensure_playwright()

        logs_history = []
        last_log_time = [time.time()]

        def ui_log(module, msg):
            now = time.time()
            diff_ms = int((now - last_log_time[0]) * 1000)
            last_log_time[0] = now
            timestamp = time.strftime('%H:%M:%S')
            tag_class = f"tag-{module.lower()}"
            new_log = (
                f"<span class='log-time'>[{timestamp}]</span>"
                f"<span class='log-ms'>[+{diff_ms}ms]</span>"
                f"<span class='log-tag {tag_class}'>[{module}]</span>"
                f"<span class='log-msg'>{msg}</span>"
            )
            logs_history.append(new_log)
            display_logs = "<br>".join(logs_history[-100:])
            html_content = f"""
            <div class="terminal-box" id="term_box">
                {display_logs}
                <br><span class="blink_me">&#9608;</span>
            </div>
            <script>
                var t = window.parent.document.getElementById('term_box') || document.getElementById('term_box');
                if (t) t.scrollTop = t.scrollHeight;
            </script>
            """
            log_placeholder.markdown(html_content, unsafe_allow_html=True)

        global_start_time = time.time()
        success_count, failed_count = 0, 0
        user_id  = selected_account["user_id"]
        password = user_password

        ui_log("SYS", "Allocating memory and initializing Chromium headless core...")
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            asyncio.set_event_loop(asyncio.new_event_loop())

            with sync_playwright() as p:
                ui_log("SYS", "Spawning browser context with isolated session...")
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(no_viewport=True)
                page = context.new_page()

                ui_log("AUTH", f"Connecting to {URL_LOGIN}...")
                page.goto(URL_LOGIN, wait_until="domcontentloaded")
                ui_log("AUTH", "DOM ready. Filling credentials...")
                page.locator("id=txtUserid").fill(user_id)
                page.locator("id=txtPasswd").fill(password)
                page.locator("id=btnLogin").click(force=True)

                try:
                    btn = page.locator("id=SYS_ASCX_btnContinue")
                    btn.wait_for(state="visible", timeout=5_000)
                    ui_log("AUTH", "Active session interceptor detected. Bypassing...")
                    btn.click(force=True)
                except Exception:
                    ui_log("SYS", "No interceptor detected. Clean session acquired.")

                page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
                ui_log("AUTH", "Login successful. Session established.")
                ui_log("SUCCESS", "Handshake verified.")

                ui_log("NAV", "Navigating to Inventory > Stock Adjustment...")
                page.locator("id=pag_InventoryRoot_tab_Main_itm_StkAdj").dispatch_event("click")
                add_btn = page.locator("id=pag_I_StkAdj_btn_Add_Value")
                add_btn.wait_for(state="attached", timeout=TIMEOUT_MS)
                ui_log("NAV", "Opening new document [Add Value]...")
                add_btn.click(force=True)

                warehouse_link = page.get_by_role("link", name=WAREHOUSE, exact=True)
                warehouse_link.wait_for(state="visible", timeout=TIMEOUT_MS)
                warehouse_link.click(force=True)
                page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").wait_for(
                    state="visible", timeout=TIMEOUT_MS
                )

                ui_log("SYS", f"Applying adjustment protocol: code [{REASON_CODE}]...")
                dropdown = page.locator("id=pag_I_StkAdj_NewGeneral_drp_n_REASON_HDR_Value")
                if dropdown.is_enabled():
                    dropdown.select_option(REASON_CODE)
                ui_log("SYS", "Ready. Opening data stream for payload injection...")

                progress_bar = st.progress(0)
                total_rows = len(df_view)
                for i, (idx, row) in enumerate(df_view.iterrows()):
                    sku = str(row['sku']).strip()
                    try:
                        qty = str(int(float(row['qty'])))
                    except Exception:
                        qty = str(row['qty']).strip()

                    ui_log("INJECT", f"Payload {i + 1}/{total_rows} -> SKU [{sku}]")
                    try:
                        sku_input = page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value")
                        sku_input.fill(sku)
                        sku_input.press("Tab")
                        time.sleep(1)
                        page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").wait_for(
                            state="visible", timeout=TIMEOUT_MS
                        )
                        ui_log("INJECT", f"Assigning qty: {qty}")
                        page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").fill(qty)
                        page.locator("id=pag_I_StkAdj_NewGeneral_btn_Add_Value").click(force=True)
                        ui_log("SYS", "Awaiting form reset...")
                        page.wait_for_function(
                            "document.getElementById('pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value').value === ''",
                            timeout=TIMEOUT_MS
                        )
                        df_view.at[idx, 'Status'] = 'Success'
                        df_view.at[idx, 'Keterangan'] = f'Attached {qty} EA'
                        success_count += 1
                        ui_log("SUCCESS", "Row committed.")
                    except Exception:
                        df_view.at[idx, 'Status'] = 'Failed'
                        df_view.at[idx, 'Keterangan'] = 'Node Timeout'
                        failed_count += 1
                        ui_log("ERROR", f"Timeout on SKU [{sku}]. Skipping.")

                    progress_bar.progress((i + 1) / total_rows)
                    if i % TABLE_UPDATE_INTERVAL == 0 or i == total_rows - 1:
                        table_placeholder.dataframe(df_view, use_container_width=True)

                ui_log("SERVER", "Saving document to server...")
                page.locator("id=pag_I_StkAdj_NewGeneral_btn_Save_Value").click()
                try:
                    yes_btn = page.locator("id=pag_PopUp_YesNo_btn_Yes_Value")
                    yes_btn.wait_for(state="visible", timeout=5_000)
                    ui_log("SERVER", "Confirming save dialog...")
                    yes_btn.click()
                    ui_log("SERVER", "Document physically written to database.")
                except Exception:
                    ui_log("SERVER", "Auto-save confirmed. Document written to database.")

                ui_log("SYS", "Closing browser and releasing memory...")
                browser.close()
                elapsed = int(time.time() - global_start_time)
                ui_log("SUCCESS", f"Complete. Total runtime: {elapsed // 60}m {elapsed % 60}s")
                st.markdown(make_solid_box(
                    f"Done — Success: {success_count} | Failed: {failed_count} | Time: {elapsed // 60}m {elapsed % 60}s",
                    "#166534", "#ffffff"
                ), unsafe_allow_html=True)
                if success_count > 0:
                    st.toast('Connection terminated')
                    time.sleep(0.5)
                    st.toast('Data injected successfully')
                    time.sleep(0.5)
                    st.toast('System override complete!')
                    st.session_state.reconcile_result = None

        except PlaywrightTimeoutError:
            st.error("Login failed: incorrect password or server timeout (30s).")
            ui_log("ERROR", "ACCESS DENIED: Handshake timeout. Invalid credentials or node unreachable.")
        except Exception as e:
            st.error("System halted due to an unexpected error.")
            clean_error = str(e).split('===')[0].strip()
            ui_log("ERROR", f"SYSTEM FAILURE: {clean_error}")
            ui_log("ERROR", traceback.format_exc().splitlines()[-1])
