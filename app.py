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
import sqlite3
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Stock Adjustment Newspage", layout="wide")

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
DB_PATH               = "accounts.db"
REASON_CODE           = "SA2"
WAREHOUSE             = "GOOD_WHS"
TIMEOUT_MS            = 30_000
TABLE_UPDATE_INTERVAL = 5

# --- 3. HELPER FUNCTIONS ---

def init_db():
    """
    Initialize SQLite database.
    Auto-migrates from users_2.csv on first run if the table is empty.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            user_id     TEXT PRIMARY KEY,
            distributor TEXT NOT NULL
        )
    """)
    conn.commit()

    # Migrate from CSV if DB is empty
    count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    if count == 0 and os.path.exists(CREDENTIALS_FILE):
        for enc in ['utf-8-sig', 'cp1252', 'iso-8859-1']:
            try:
                with open(CREDENTIALS_FILE, mode="r", encoding=enc) as f:
                    reader = csv.DictReader(f)
                    reader.fieldnames = [name.strip() for name in reader.fieldnames if name]
                    rows = []
                    for row in reader:
                        cleaned = {str(k).strip(): str(v).strip() for k, v in row.items() if k}
                        if "user_id" in cleaned and "Distributor" in cleaned:
                            rows.append((cleaned["user_id"], cleaned["Distributor"]))
                    if rows:
                        conn.executemany(
                            "INSERT OR IGNORE INTO accounts (user_id, distributor) VALUES (?, ?)",
                            rows
                        )
                        conn.commit()
                break
            except (UnicodeDecodeError, TypeError):
                continue

    conn.close()


@st.cache_data(ttl=300)
def load_accounts():
    """Load accounts from SQLite. Returns list of dicts with user_id and Distributor."""
    init_db()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    rows = conn.execute(
        "SELECT user_id, distributor FROM accounts ORDER BY distributor"
    ).fetchall()
    conn.close()
    return [{"user_id": r[0], "Distributor": r[1]} for r in rows]


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


def render_terminal(placeholder, logs_history: list):
    display_logs = "<br>".join(logs_history[-100:])
    html_content = f"""
    <div class="terminal-box" id="ext_term_box">
        {display_logs}
        <br><span class="blink_me">&#9608;</span>
    </div>
    <script>
        var t = window.parent.document.getElementById('ext_term_box') || document.getElementById('ext_term_box');
        if (t) t.scrollTop = t.scrollHeight;
    </script>
    """
    placeholder.markdown(html_content, unsafe_allow_html=True)


# --- 4. STATE MANAGEMENT ---
if 'app_page' not in st.session_state:
    st.session_state.app_page = "Reconcile"
if 'reconcile_result' not in st.session_state:
    st.session_state.reconcile_result = None
if 'reconcile_summary' not in st.session_state:
    st.session_state.reconcile_summary = None
if 'np_df' not in st.session_state:
    st.session_state.np_df = None
if 'selected_distributor_str' not in st.session_state:
    st.session_state.selected_distributor_str = None

# --- 5. CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

    .terminal-box {
        background-color: #0d1117;
        color: #f0f6fc;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem;
        padding: 14px 18px;
        border: 1px solid #30363d;
        border-radius: 8px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.4);
        height: 320px;
        overflow-y: auto;
        line-height: 1.8;
        -ms-overflow-style: none;
        scrollbar-width: none;
        margin-top: 8px;
        margin-bottom: 32px;
    }
    .terminal-box::-webkit-scrollbar { display: none; }

    .terminal-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        color: #8b949e;
        text-transform: uppercase;
        margin-bottom: 4px;
    }

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
    hdr_col1, hdr_col2 = st.columns([5, 1])
    with hdr_col1:
        st.markdown("<div class='live-indicator'>LIVE</div>", unsafe_allow_html=True)
        st.markdown("<h1>Compare Stock</h1>", unsafe_allow_html=True)
        st.markdown("<div class='typewriter-sub'>Inspired by Kopi Mang Toni...</div>", unsafe_allow_html=True)
    with hdr_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Stock Adjustment", use_container_width=True):
            st.session_state.reconcile_result = None
            st.session_state.reconcile_summary = None
            st.session_state.app_page = "Bot"
            st.rerun()
    st.markdown("---")

    col1, col2 = st.columns(2)

    # ── Kiri: Newspage Stock Data ─────────────────────────────────────────────
    with col1:
        with st.container(border=True):
            st.markdown("**Newspage Stock Data**")

            with st.expander("Extract from Master Server", expanded=st.session_state.np_df is None):
                np_user = st.text_input("NP User ID", placeholder="Enter Newspage user ID...")
                np_pass = st.text_input("NP Password", type="password", placeholder="Enter password...")
                extract_btn = st.button(
                    "Extract Inventory Master",
                    type="primary",
                    use_container_width=True,
                    disabled=not (np_user and np_pass)
                )

            if st.session_state.np_df is not None:
                st.markdown(make_solid_box(
                    f"Extracted — {len(st.session_state.np_df)} items loaded from server",
                    "#082f49", "#38bdf8"
                ), unsafe_allow_html=True)
                if st.button("Clear extracted data", use_container_width=True):
                    st.session_state.np_df = None
                    st.rerun()
                file1 = None
            else:
                file1 = st.file_uploader("Or upload Newspage stock file manually", type=['csv', 'xlsx', 'zip'])

    # ── Kanan: Distributor Stock Data ─────────────────────────────────────────
    with col2:
        with st.container(border=True):
            st.markdown("**Distributor Stock Data**")
            file2 = st.file_uploader("Upload Distributor stock file", type=['csv', 'xlsx'])

            st.markdown("<br>", unsafe_allow_html=True)
            _dist_locked = file2 is None
            _accounts    = load_accounts()
            _acc_options = [f"{acc['Distributor']} ({acc['user_id']})" for acc in _accounts]
            _auto_idx    = (
                _acc_options.index(st.session_state.selected_distributor_str)
                if st.session_state.selected_distributor_str in _acc_options
                else None
            )
            _picked = st.selectbox(
                "Select Distributor",
                options=_acc_options,
                index=_auto_idx,
                placeholder="-- Upload file first --" if _dist_locked else "-- Select distributor --",
                key="reconcile_dist_select",
                disabled=_dist_locked
            )
            if _picked and _picked != st.session_state.selected_distributor_str:
                st.session_state.selected_distributor_str = _picked
                st.rerun()
            if not _dist_locked and st.session_state.selected_distributor_str:
                st.markdown(make_solid_box(
                    f"{st.session_state.selected_distributor_str}",
                    "#0f2f1d", "#4ade80"
                ), unsafe_allow_html=True)

    # ── Extraction Terminal
    ext_log_placeholder = st.empty()

    # ── Extraction Logic
    if extract_btn:
        user_id_np = np_user.strip()
        pass_np    = np_pass.strip()

        ext_logs_history  = []
        ext_last_log_time = [time.time()]

        def ext_ui_log(module, msg):
            now      = time.time()
            diff_ms  = int((now - ext_last_log_time[0]) * 1000)
            ext_last_log_time[0] = now
            timestamp = time.strftime('%H:%M:%S')
            tag_class = f"tag-{module.lower()}"
            new_log = (
                f"<span class='log-time'>[{timestamp}]</span>"
                f"<span class='log-ms'>[+{diff_ms}ms]</span>"
                f"<span class='log-tag {tag_class}'>[{module}]</span>"
                f"<span class='log-msg'>{msg}</span>"
            )
            ext_logs_history.append(new_log)
            render_terminal(ext_log_placeholder, ext_logs_history)

        ext_ui_log("SYS", "Allocating memory and initializing Chromium headless core...")
        ensure_playwright()

        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            asyncio.set_event_loop(asyncio.new_event_loop())

            with sync_playwright() as p:
                ext_ui_log("SYS", "Spawning browser context with isolated session...")
                browser = p.chromium.launch(headless=True)
                
                context_options = {"no_viewport": True}
                if os.path.exists("np_state.json"):
                    context_options["storage_state"] = "np_state.json"
                    ext_ui_log("SYS", "Loading saved session state...")
                    
                context = browser.new_context(**context_options)
                page    = context.new_page()

                logged_in = False
                if os.path.exists("np_state.json"):
                    ext_ui_log("AUTH", "Verifying saved session...")
                    page.goto("https://rb-id.np.accenture.com/RB_ID/Default.aspx", wait_until="domcontentloaded")
                    if "Logon.aspx" not in page.url:
                        logged_in = True
                        ext_ui_log("AUTH", "Session resumed successfully.")
                        ext_ui_log("SUCCESS", "Handshake verified.")
                    else:
                        ext_ui_log("AUTH", "Session expired. Falling back to manual login...")

                if not logged_in:
                    ext_ui_log("AUTH", f"Connecting to {URL_LOGIN}...")
                    page.goto(URL_LOGIN, wait_until="domcontentloaded")
                    ext_ui_log("AUTH", "DOM ready. Filling credentials...")
                    page.locator("id=txtUserid").fill(user_id_np)
                    page.locator("id=txtPasswd").fill(pass_np)
                    page.locator("id=btnLogin").click(force=True)

                    try:
                        btn = page.locator("id=SYS_ASCX_btnContinue")
                        btn.wait_for(state="visible", timeout=5_000)
                        ext_ui_log("AUTH", "Active session interceptor detected. Bypassing...")
                        btn.click(force=True)
                    except Exception:
                        ext_ui_log("SYS", "No interceptor detected. Clean session acquired.")

                    page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
                    context.storage_state(path="np_state.json")
                    ext_ui_log("AUTH", "Login successful. Session established & saved.")
                    ext_ui_log("SUCCESS", "Handshake verified.")

                ext_ui_log("NAV", "Navigating to System > Import/Export Job module...")
                time.sleep(3)
                menu_job = page.locator("id=pag_Sys_Root_tab_Detail_itm_Job")
                menu_job.wait_for(state="attached", timeout=15000)
                menu_job.dispatch_event("click")
                time.sleep(4)

                ext_ui_log("NAV", "Opening new job [Add Value]...")
                page.locator("id=pag_FW_SYS_INTF_JOB_btn_Add_Value").click(force=True)
                time.sleep(3)

                ext_ui_log("INJECT", "Setting job type: Export [E], desc: Text Inventory Master...")
                page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_TYPE_Value").select_option("E")
                time.sleep(2)
                page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_DESC_Value").fill("Text Inventory Master")
                page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_TIMEOUT_Value").fill("9999999")
                page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_EXE_TYPE_Value").select_option("M")
                time.sleep(2)

                ext_ui_log("NAV", "Proceeding to next step...")
                page.locator("id=pag_FW_SYS_INTF_JOB_RootNew_btn_Next_Value").click(force=True)
                time.sleep(3)

                ext_ui_log("SYS", "Bypassing disclaimer prompt...")
                page.locator("id=pag_FW_DisclaimerMessage_btn_okay_Value").click(force=True)
                time.sleep(2)

                ext_ui_log("NAV", "Opening interface selection popup...")
                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_INTF_ID_SelectButton").click(force=True)
                time.sleep(3)

                ext_ui_log("INJECT", "Searching target interface: E_20150315090000028...")
                page.locator("id=pop_Dynamic_gft_List_2_FilterField_Value").fill("E_20150315090000028")
                page.locator("id=pop_Dynamic_grd_Main_SearchForm_ButtonSearch_Value").click(force=True)
                time.sleep(2)

                ext_ui_log("INJECT", "Selecting target interface from results...")
                page.get_by_text("E_20150315090000028", exact=True).click(force=True)
                time.sleep(2)

                ext_ui_log("INJECT", "Setting file type: Delimited [D], separator: standard...")
                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_FILE_TYPE_Value").select_option("D")
                time.sleep(1)
                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_FLD_SEPARATOR_STD_Value_0").check()
                time.sleep(3)

                ext_ui_log("INJECT", f"Applying warehouse filter: [{WAREHOUSE}]...")
                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_grd_DynamicFilter_ctl02_dyn_Field_txt_Value").fill("GOOD_WHS")
                time.sleep(2)

                ext_ui_log("SYS", "Committing parameters to job definition...")
                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_btn_Add_Value").click(force=True)
                time.sleep(3)

                ext_ui_log("SERVER", "Saving job and dispatching execution to server...")
                page.locator("id=pag_FW_SYS_INTF_JOB_RootNew_btn_Save_Value").click(force=True)

                ext_ui_log("SERVER", "Awaiting server confirmation prompt...")
                page.locator("id=TF_Prompt_btn_Ok_Value").wait_for(state="visible", timeout=15000)
                page.locator("id=TF_Prompt_btn_Ok_Value").click(force=True)
                ext_ui_log("SERVER", "Job dispatched. Waiting for export to complete...")

                ext_ui_log("SERVER", "Intercepting download link — this may take up to 4 minutes...")
                with page.expect_download(timeout=240000) as download_info:
                    download_btn = page.locator("id=pag_FW_SYS_INTF_STATUS_JOB_btn_Download_Value")
                    download_btn.wait_for(state="visible", timeout=240000)
                    download_btn.click(force=True)

                download      = download_info.value
                real_filename = download.suggested_filename
                file_path     = f"temp_ext_{real_filename}"
                ext_ui_log("SUCCESS", f"Download captured: {real_filename}. Saving to environment...")
                download.save_as(file_path)

                browser.close()
                ext_ui_log("SYS", "Browser closed. Releasing session memory...")

                ext_ui_log("SYS", f"Parsing payload file: {real_filename}...")
                df_ext = None
                if real_filename.lower().endswith('.zip'):
                    with zipfile.ZipFile(file_path) as z:
                        target = next((n for n in z.namelist() if "INVT_MASTER" in n and n.lower().endswith((".csv", ".txt"))), None)
                        if not target:
                            target = next((n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))), None)
                        if target:
                            ext_ui_log("SYS", f"ZIP target identified: {target}")
                            with z.open(target) as f:
                                df_ext = pd.read_csv(f, sep='\t', dtype=str, on_bad_lines='skip')
                                if df_ext.shape[1] <= 1:
                                    f.seek(0)
                                    df_ext = pd.read_csv(f, sep=',', dtype=str, on_bad_lines='skip')
                elif real_filename.lower().endswith(('.xls', '.xlsx')):
                    df_ext = pd.read_excel(file_path, dtype=str)
                else:
                    for enc in ['utf-8', 'iso-8859-1', 'cp1252']:
                        for separator in ['\t', ',', ';', '|']:
                            try:
                                temp_df = pd.read_csv(file_path, sep=separator, dtype=str, encoding=enc, on_bad_lines='skip')
                                if temp_df is not None and temp_df.shape[1] > 1:
                                    df_ext = temp_df
                                    ext_ui_log("SYS", f"Parser success — enc: {enc}, sep: '{separator}'")
                                    break
                            except Exception:
                                continue
                        if df_ext is not None and df_ext.shape[1] > 1:
                            break

                if df_ext is not None and not df_ext.empty and df_ext.shape[1] > 1:
                    df_ext.columns = [str(c).strip() for c in df_ext.columns]
                    ext_ui_log("SUCCESS", f"Payload Secured! {len(df_ext)} items loaded. Flushing to session...")
                    st.session_state.np_df = df_ext
                    st.rerun()
                else:
                    ext_ui_log("ERROR", "DataFrame validation failed — bad format or empty file.")
                    st.error("Gagal membaca file dari server, cek format ekstraksi.")

        except PlaywrightTimeoutError:
            ext_ui_log("ERROR", "TIMEOUT: Server tidak merespon dalam batas waktu.")
            st.error("Operation Timeout. Server tidak merespon dalam batas waktu.")
        except Exception as e:
            ext_ui_log("ERROR", f"SYSTEM FAILURE: {str(e).split(chr(10))[0]}")
            st.error(f"System error: {e}")

    # ── Column mapping & compare
    np_source_ready = (st.session_state.np_df is not None) or (file1 is not None)

    if np_source_ready and file2:
        st.divider()
        df1 = st.session_state.np_df if st.session_state.np_df is not None else load_data(file1)
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
                
                # Tambahan replace untuk data Newspage (Otomatis prefix 0 untuk 373100, 373103, 373104)
                d1[sku_col1] = d1[sku_col1].replace({'373100': '0373100', '373103': '0373103', '373104': '0373104'})
                
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
                
                # Update replace untuk data Distributor (tambah 373104)
                d2[sku_col2] = d2[sku_col2].replace({'373100': '0373100', '373103': '0373103', '373104': '0373104'})
                
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



# ─── 7. PAGE: STOCK ADJUSTMENT BOT
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
        st.error(f"No account data found. Ensure '{CREDENTIALS_FILE}' exists or accounts.db is populated.")
        st.stop()

    cfg_col1, cfg_col2 = st.columns(2)

    with cfg_col1:
        with st.container(border=True):
            has_session = os.path.exists("np_state.json")
            
            _bot_acc_options = [f"{acc['Distributor']} ({acc['user_id']})" for acc in accounts]
            _bot_auto_idx    = (
                _bot_acc_options.index(st.session_state.selected_distributor_str)
                if st.session_state.selected_distributor_str in _bot_acc_options
                else None
            )
            selected_acc_str = st.selectbox(
                "Select Distributor / User ID",
                options=_bot_acc_options,
                index=_bot_auto_idx,
                placeholder="-- Select account --"
            )
            if selected_acc_str and selected_acc_str != st.session_state.selected_distributor_str:
                st.session_state.selected_distributor_str = selected_acc_str
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
                    placeholder="Session active (password optional)" if has_session else "Enter password..."
                )
                if len(user_password) > 3 or has_session:
                    msg = "Session Active (Ready)" if has_session and len(user_password) <= 3 else f"Password set — {selected_account['Distributor']} (validated on run)"
                    st.markdown(make_solid_box(msg, "#0f2f1d", "#4ade80"), unsafe_allow_html=True)
                else:
                    st.markdown(make_solid_box("Waiting for password...", "#1e1b4b", "#a5b4fc"), unsafe_allow_html=True)

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
    is_ready   = (selected_account is not None) and (len(user_password) > 3 or has_session) and (df_to_process is not None)
    run_button = st.button("PROCEED", use_container_width=True, type="primary", disabled=not is_ready)

    st.subheader("Product Table")
    if not is_ready:
        st.warning("Select an account and ensure data is available before running the bot.")
        st.stop()

    df_view = df_to_process.copy()
    if 'Status' not in df_view.columns:
        df_view['Status'] = 'Pending'
    if 'Keterangan' not in df_view.columns:
        df_view['Keterangan'] = '-'
    table_placeholder = st.dataframe(df_view, use_container_width=True)

    # ── Bot Terminal
    st.markdown("<div class='terminal-label'>Execution Log</div>", unsafe_allow_html=True)
    log_placeholder = st.empty()

    if run_button:
        with st.spinner("Initializing Chromium engine..."):
            ensure_playwright()

        bot_logs_history  = []
        bot_last_log_time = [time.time()]

        def ui_log(module, msg):
            now      = time.time()
            diff_ms  = int((now - bot_last_log_time[0]) * 1000)
            bot_last_log_time[0] = now
            timestamp = time.strftime('%H:%M:%S')
            tag_class = f"tag-{module.lower()}"
            new_log = (
                f"<span class='log-time'>[{timestamp}]</span>"
                f"<span class='log-ms'>[+{diff_ms}ms]</span>"
                f"<span class='log-tag {tag_class}'>[{module}]</span>"
                f"<span class='log-msg'>{msg}</span>"
            )
            bot_logs_history.append(new_log)
            render_terminal(log_placeholder, bot_logs_history)

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
                
                context_options = {"no_viewport": True}
                if os.path.exists("np_state.json"):
                    context_options["storage_state"] = "np_state.json"
                    ui_log("SYS", "Loading saved session state...")
                    
                context = browser.new_context(**context_options)
                page    = context.new_page()

                logged_in = False
                if os.path.exists("np_state.json"):
                    ui_log("AUTH", "Verifying saved session...")
                    page.goto("https://rb-id.np.accenture.com/RB_ID/Default.aspx", wait_until="domcontentloaded")
                    if "Logon.aspx" not in page.url:
                        logged_in = True
                        ui_log("AUTH", "Session resumed successfully.")
                        ui_log("SUCCESS", "Handshake verified.")
                    else:
                        ui_log("AUTH", "Session expired. Falling back to manual login...")

                if not logged_in:
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
                    context.storage_state(path="np_state.json")
                    ui_log("AUTH", "Login successful. Session established & saved.")
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
                total_rows   = len(df_view)
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
                        df_view.at[idx, 'Status']     = 'Success'
                        df_view.at[idx, 'Keterangan'] = f'Attached {qty} EA'
                        success_count += 1
                        ui_log("SUCCESS", "Row committed.")
                    except Exception:
                        df_view.at[idx, 'Status']     = 'Failed'
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
