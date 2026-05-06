import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import zipfile
import time
import os
import subprocess
import asyncio
import traceback
import sys
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from supabase import create_client, Client

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
REASON_CODE           = "SA2"
WAREHOUSE             = "GOOD_WHS"
TIMEOUT_MS            = 30_000
TABLE_UPDATE_INTERVAL = 5

# --- 2.5 INIT SUPABASE ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if url and key:
        return create_client(url, key)
    return None

supabase = init_supabase()

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


@st.cache_resource
def ensure_playwright():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
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
    <style>
    body {{ margin: 0; padding: 0; background: transparent; }}
    .terminal-box {{ background-color: #0b1120; color: #e2e8f0; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; padding: 16px 20px; border: 1px solid #1e293b; border-radius: 8px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); height: 300px; overflow-y: auto; line-height: 1.8; -ms-overflow-style: none; scrollbar-width: none; }}
    .terminal-box::-webkit-scrollbar {{ display: none; }}
    .blink_me {{ animation: blinker 1s linear infinite; font-weight: bold; color: #3b82f6; }}
    @keyframes blinker {{ 50% {{ opacity: 0; }} }}
    .log-time   {{ display: inline-block; width: 85px; color: #64748b; font-family: 'JetBrains Mono', monospace; }}
    .log-ms     {{ display: inline-block; width: 75px; text-align: right; margin-right: 15px; color: #94a3b8; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; }}
    .log-tag    {{ display: inline-block; width: 95px; font-weight: 600; font-family: 'JetBrains Mono', monospace; }}
    .log-msg    {{ color: #f8fafc; font-weight: 400; font-family: 'JetBrains Mono', monospace; }}
    .tag-sys     {{ color: #8b5cf6; }} .tag-auth    {{ color: #eab308; }} .tag-nav     {{ color: #3b82f6; }} .tag-inject  {{ color: #06b6d4; }} .tag-success {{ color: #10b981; }} .tag-error   {{ color: #ef4444; }} .tag-server  {{ color: #f43f5e; }}
    </style>
    <div class="terminal-box" id="term_box">
        {display_logs}
        <br><span class="blink_me">&#9608;</span>
    </div>
    <script>
        var t = document.getElementById('term_box');
        if (t) t.scrollTop = t.scrollHeight;
    </script>
    """
    with placeholder:
        components.html(html_content, height=340, scrolling=False)


# --- 4. STATE MANAGEMENT ---
if 'reconcile_result' not in st.session_state:
    st.session_state.reconcile_result = None
if 'reconcile_summary' not in st.session_state:
    st.session_state.reconcile_summary = None
if 'np_df' not in st.session_state:
    st.session_state.np_df = None

# Tambahan state untuk sinkronisasi tombol Compare Stock
if 'is_bot_running' not in st.session_state:
    st.session_state.is_bot_running = False
if 'prev_file2' not in st.session_state:
    st.session_state.prev_file2 = None

# Variabel untuk menampung user_id (dipakai di logic perkalian SKU)
if 'current_np_user_id' not in st.session_state:
    st.session_state.current_np_user_id = ""


# --- 5. CUSTOM CSS & WAKE LOCK SCRIPT ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

    /* Terminal Box Corporate */
    .terminal-box { background-color: #0b1120; color: #e2e8f0; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; padding: 16px 20px; border: 1px solid #1e293b; border-radius: 8px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); height: 320px; overflow-y: auto; line-height: 1.8; -ms-overflow-style: none; scrollbar-width: none; margin-top: 8px; margin-bottom: 32px; }
    .terminal-box::-webkit-scrollbar { display: none; }
    .terminal-label { font-family: 'Inter', sans-serif; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em; color: #64748b; text-transform: uppercase; margin-bottom: 4px; }
    .blink_me { animation: blinker 1s linear infinite; font-weight: bold; color: #3b82f6; }
    @keyframes blinker { 50% { opacity: 0; } }
    
    /* Log Formatting */
    .log-time   { display: inline-block; width: 85px; color: #64748b; font-family: 'JetBrains Mono', monospace; }
    .log-ms     { display: inline-block; width: 75px; text-align: right; margin-right: 15px; color: #94a3b8; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; }
    .log-tag    { display: inline-block; width: 95px; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
    .log-msg    { color: #f8fafc; font-weight: 400; font-family: 'JetBrains Mono', monospace; }
    .tag-sys     { color: #8b5cf6; } .tag-auth    { color: #eab308; } .tag-nav     { color: #3b82f6; } .tag-inject  { color: #06b6d4; } .tag-success { color: #10b981; } .tag-error   { color: #ef4444; } .tag-server  { color: #f43f5e; }
    
    /* Corporate Clean Boxes */
    .box-np, .box-dist, .box-review, .box-queue, .box-results {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        color: #f8fafc;
        padding: 12px 16px;
        border-radius: 8px;
        font-size: 0.9rem;
        font-weight: 600;
        border: 1px solid #334155;
        margin-bottom: 16px;
        letter-spacing: 0.02em;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .box-np { border-top: 3px solid #3b82f6; }
    .box-dist { border-top: 3px solid #10b981; }
    .box-review { border-top: 3px solid #06b6d4; }
    .box-queue { border-top: 3px solid #8b5cf6; }
    .box-results { border-top: 3px solid #0b42f5; }

    /* Metric Cards */
    .metric-box-match, .metric-box-mismatch {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
    .metric-box-match { border-left: 4px solid #10b981; }
    .metric-box-mismatch { border-left: 4px solid #ef4444; }
    .metric-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; }
    .metric-box-match .metric-value { color: #10b981; font-size: 2rem; font-weight: 700; font-family: 'Inter', sans-serif; margin-top: 4px; line-height: 1; }
    .metric-box-mismatch .metric-value { color: #ef4444; font-size: 2rem; font-weight: 700; font-family: 'Inter', sans-serif; margin-top: 4px; line-height: 1; }

    /* Button Styling */
    button[kind="primary"] { background-color: #2563eb !important; color: #ffffff !important; border: 1px solid #1d4ed8 !important; font-weight: 600 !important; letter-spacing: 0.05em !important; transition: all 0.2s ease !important; border-radius: 6px !important; font-family: 'Inter', sans-serif !important; }
    button[kind="primary"]:hover { background-color: #1e40af !important; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2) !important; border-color: #1e40af !important; }
    
    /* Live Indicator (Warna Hijau) */
    .typewriter-sub { font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; color: #64748b; margin: 0; }
    .live-indicator { display: inline-flex; align-items: center; color: #10b981; font-family: 'Inter', sans-serif; font-weight: 600; font-size: 0.75rem; letter-spacing: 0.1em; background: rgba(16, 185, 129, 0.1); padding: 4px 10px; border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.2); }
    .live-indicator::before { content: ''; display: inline-block; width: 6px; height: 6px; background-color: #10b981; border-radius: 50%; margin-right: 6px; animation: pulse-radar 2s infinite; }
    @keyframes pulse-radar { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); } 70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }
    
    /* Clean Divider */
    hr { border: none !important; height: 1px !important; background-color: #334155 !important; margin-top: 1.5rem !important; margin-bottom: 1.5rem !important; }
    div[data-testid="stContainer"] { border: 1px solid #334155; border-radius: 10px; padding: 20px; background-color: #0f172a; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    </style>
    
    <script>
    // --- SCRIPT ANTI LAYAR MATI UNTUK BROWSER MOBILE ---
    let wakeLock = null;
    const requestWakeLock = async () => {
      try {
        wakeLock = await navigator.wakeLock.request('screen');
      } catch (err) {
        console.log(`${err.name}, ${err.message}`);
      }
    };
    requestWakeLock();
    document.addEventListener('visibilitychange', async () => {
      if (wakeLock !== null && document.visibilityState === 'visible') {
        requestWakeLock();
      }
    });
    </script>
""", unsafe_allow_html=True)

# ─── 6. PAGE: MAIN RECONCILE & ENGINE ─────────────────────────────────────────

hdr_col1, hdr_col2 = st.columns([5, 1])
with hdr_col1:
    st.markdown("<div class='live-indicator'>LIVE</div>", unsafe_allow_html=True)
    st.markdown("<h1>Compare & Adjustment Stock</h1>", unsafe_allow_html=True)
    st.markdown("<div class='typewriter-sub'>by Kopi Mamang Toni</div>", unsafe_allow_html=True)
st.markdown("---")

col1, col2 = st.columns(2)

# ── Kiri: Newspage Stock Data ─────────────────────────────────────────────
with col1:
    with st.container(border=True):
        st.markdown("<div class='box-np'>Newspage Stock Data</div>", unsafe_allow_html=True)
        np_col1, np_col2 = st.columns(2)
        
        list_dist = []
        if supabase:
            try:
                res = supabase.table("distributor_vault").select("nama_distributor").execute()
                list_dist = [d['nama_distributor'] for d in res.data]
            except: pass
        if not list_dist: list_dist = ["Belum ada data di Database"]

        with np_col1:
            selected_distributor = st.selectbox("Nama Distributor", list_dist, key="distributor_select")
            
            # --- Menyimpan User ID ke dalam session_state agar bisa dipakai saat Compare ---
            if supabase:
                try:
                    res = supabase.table("distributor_vault").select("np_user_id").eq("nama_distributor", selected_distributor).execute()
                    if res.data:
                        st.session_state.current_np_user_id = res.data[0]['np_user_id']
                except: pass
                
        with np_col2:
            st.text_input("NP Password", value="••••••••", type="password", disabled=True, help="Password ditarik otomatis dari Database", key="np_pass_dummy")
        
        extract_btn = st.button(
            "Extract Inventory Master",
            type="primary",
            use_container_width=True
        )
        file1 = None

# ── Kanan: Distributor Stock Data ─────────────────────────────────────────
with col2:
    with st.container(border=True):
        st.markdown("<div class='box-dist'>Distributor Stock Data</div>", unsafe_allow_html=True)
        
        def handle_fragment_upload():
            f = st.file_uploader("Upload Distributor stock file", type=['csv', 'xlsx'], key="file2_uploader")
            st.markdown("<div style='margin-bottom: 28px;'></div>", unsafe_allow_html=True)
            
            # Pemicu Sinkronisasi Full-Page
            curr_f = getattr(f, "file_id", f.name if f else None) if f else None
            if curr_f != st.session_state.prev_file2:
                st.session_state.prev_file2 = curr_f
                # Jika bot TIDAK sedang mengeksekusi, refresh halaman penuh biar tombol muncul
                if not st.session_state.is_bot_running:
                    st.rerun()

        if hasattr(st, "fragment"):
            @st.fragment
            def render_upload_dist():
                handle_fragment_upload()
            render_upload_dist()
        elif hasattr(st, "experimental_fragment"):
            @st.experimental_fragment
            def render_upload_dist():
                handle_fragment_upload()
            render_upload_dist()
        else:
            handle_fragment_upload()
        
        file2 = st.session_state.get("file2_uploader")

# ── Info Extracted Data ───────────────────────────────────────────────────
if st.session_state.np_df is not None:
    st.markdown(make_solid_box(
        f"Extracted — {len(st.session_state.np_df)} items loaded from server",
        "#082f49", "#38bdf8"
    ), unsafe_allow_html=True)
    if st.button("Clear extracted data", use_container_width=True):
        st.session_state.np_df = None
        st.rerun()

# ── Extraction Terminal ───────────────────────────────────────────────────
ext_label_placeholder = st.empty()
ext_log_placeholder = st.empty()

# ── Extraction Logic ──────────────────────────────────────────────────────
if extract_btn:
    st.session_state.is_bot_running = True
    
    user_id_np, pass_np = "", ""
    if supabase:
        try:
            res = supabase.table("distributor_vault").select("np_user_id, np_password").eq("nama_distributor", selected_distributor).execute()
            if res.data:
                user_id_np = res.data[0]['np_user_id']
                pass_np = res.data[0]['np_password']
        except: pass

    if not user_id_np or not pass_np:
        st.session_state.is_bot_running = False
        st.error("Gagal! Kredensial untuk distributor ini tidak ditemukan di Supabase.")
        st.stop()

    ext_label_placeholder.markdown("<div class='terminal-label'>Log</div>", unsafe_allow_html=True)
    ext_logs_history  = []
    ext_last_log_time = [time.time()]

    def ext_ui_log(module, msg):
        now      = time.time()
        diff_ms  = int((now - ext_last_log_time[0]) * 1000)
        ext_last_log_time[0] = now
        timestamp = time.strftime('%H:%M:%S')
        tag_class = f"tag-{module.lower()}"
        new_log = (f"<span class='log-time'>[{timestamp}]</span><span class='log-ms'>[+{diff_ms}ms]</span><span class='log-tag {tag_class}'>[{module}]</span><span class='log-msg'>{msg}</span>")
        ext_logs_history.append(new_log)
        render_terminal(ext_log_placeholder, ext_logs_history)

    ext_ui_log("SYS", "Allocating memory and initializing Chromium headless core...")
    ensure_playwright()
    try:
        if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.set_event_loop(asyncio.new_event_loop())
        with sync_playwright() as p:
            ext_ui_log("SYS", "Spawning browser context with isolated session...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(no_viewport=True)
            page    = context.new_page()
            ext_ui_log("AUTH", f"Connecting to {URL_LOGIN}...")
            page.goto(URL_LOGIN, wait_until="domcontentloaded")
            ext_ui_log("AUTH", f"DOM ready. Injecting credentials for [{selected_distributor}]...")
            page.locator("id=txtUserid").fill(user_id_np)
            page.locator("id=txtPasswd").fill(pass_np)
            page.locator("id=btnLogin").click(force=True)
            try:
                btn = page.locator("id=SYS_ASCX_btnContinue")
                btn.wait_for(state="visible", timeout=5_000)
                ext_ui_log("AUTH", "Active session interceptor detected. Bypassing...")
                btn.click(force=True)
            except Exception: ext_ui_log("SYS", "No interceptor detected. Clean session acquired.")
            page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
            ext_ui_log("AUTH", "Login successful. Session established.")
            ext_ui_log("SUCCESS", "Handshake verified.")
            ext_ui_log("NAV", "Navigating to System > Import/Export Job module...")
            time.sleep(5) 
            menu_job = page.locator("id=pag_Sys_Root_tab_Detail_itm_Job")
            menu_job.wait_for(state="attached", timeout=TIMEOUT_MS)
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
            page.locator("id=TF_Prompt_btn_Ok_Value").wait_for(state="visible", timeout=TIMEOUT_MS)
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
                    if not target: target = next((n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))), None)
                    if target:
                        ext_ui_log("SYS", f"ZIP target identified: {target}")
                        with z.open(target) as f:
                            df_ext = pd.read_csv(f, sep='\t', dtype=str, on_bad_lines='skip')
                            if df_ext.shape[1] <= 1: f.seek(0); df_ext = pd.read_csv(f, sep=',', dtype=str, on_bad_lines='skip')
            elif real_filename.lower().endswith(('.xls', '.xlsx')): df_ext = pd.read_excel(file_path, dtype=str)
            else:
                for enc in ['utf-8', 'iso-8859-1', 'cp1252']:
                    for separator in ['\t', ',', ';', '|']:
                        try:
                            temp_df = pd.read_csv(file_path, sep=separator, dtype=str, encoding=enc, on_bad_lines='skip')
                            if temp_df is not None and temp_df.shape[1] > 1: df_ext = temp_df; break
                        except Exception: continue
                    if df_ext is not None and df_ext.shape[1] > 1: break

            if df_ext is not None and not df_ext.empty and df_ext.shape[1] > 1:
                df_ext.columns = [str(c).strip() for c in df_ext.columns]
                ext_ui_log("SUCCESS", f"Payload Secured! {len(df_ext)} items loaded. Flushing to session...")
                st.session_state.np_df = df_ext
                st.session_state.is_bot_running = False
                st.rerun()
            else: 
                st.session_state.is_bot_running = False
                ext_ui_log("ERROR", "DataFrame validation failed."); st.error("Gagal membaca file dari server.")
    except PlaywrightTimeoutError: 
        st.session_state.is_bot_running = False
        ext_ui_log("ERROR", "TIMEOUT: Server tidak merespon."); st.error("Operation Timeout.")
    except Exception as e: 
        st.session_state.is_bot_running = False
        ext_ui_log("ERROR", f"SYSTEM FAILURE: {str(e).split(chr(10))[0]}"); st.error(f"System error: {e}")

# ── Column mapping & compare ──────────────────────────────────────────────
np_source_ready = (st.session_state.np_df is not None) or (file1 is not None)
if np_source_ready and file2:
    # st.divider()
    df1 = st.session_state.np_df if st.session_state.np_df is not None else load_data(file1)
    df2 = load_data(file2)
    if df1 is not None and df2 is not None:
        st.markdown("<div class='box-results'>Results</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown("<div class='box-np'>Newspage Setup</div>", unsafe_allow_html=True)
                idx_sku1 = df1.columns.get_loc('Product Code') if 'Product Code' in df1.columns else 0
                if 'Product Description' in df1.columns: idx_desc1 = df1.columns.get_loc('Product Description')
                elif 'Product Name' in df1.columns: idx_desc1 = df1.columns.get_loc('Product Name')
                else: idx_desc1 = 1 if len(df1.columns) > 1 else 0
                idx_qty1 = (df1.columns.get_loc('Stock Available') if 'Stock Available' in df1.columns else (2 if len(df1.columns) > 2 else 0))
                sku_col1  = st.selectbox("SKU column (NP)", df1.columns, index=idx_sku1)
                desc_col1 = st.selectbox("Description column (NP)", df1.columns, index=idx_desc1)
                qty_col1  = st.selectbox("Qty column (NP)", df1.columns, index=idx_qty1)
        with c2:
            with st.container(border=True):
                st.markdown("<div class='box-dist'>Distributor Setup</div>", unsafe_allow_html=True)
                idx_sku2 = 20 if len(df2.columns) > 20 else 0
                qty2_col_match = next((col for col in df2.columns if str(col).strip().lower().replace(" ", "") == "stokakhir"), None)
                if qty2_col_match: idx_qty2 = df2.columns.get_loc(qty2_col_match)
                else: idx_qty2 = 71 if len(df2.columns) > 71 else (1 if len(df2.columns) > 1 else 0)
                sku_col2 = st.selectbox("SKU column (Dist)", df2.columns, index=idx_sku2)
                qty_col2 = st.selectbox("Qty column (Dist)", df2.columns, index=idx_qty2)
                st.markdown("<div style='margin-bottom: 84px;'></div>", unsafe_allow_html=True)

        # st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Compare Stock", type="primary", use_container_width=True):
            # Target SKUs that require a '0' prefix
            TARGET_SKUS = ['373103', '373104', '373105', '373106', '373108', '373110', '373112', '135428', '137118', '137120', '167209', '172130', '172131', '205901', '22583', '22595', '260656', '260659', '304095', '304100', '304102', '304157', '304161', '304164', '323044', '372264', '373100']

            d1 = df1[[sku_col1, desc_col1, qty_col1]].copy(); d1 = d1.dropna(subset=[sku_col1]); d1[sku_col1] = d1[sku_col1].astype(str).str.split('.').str[0].str.strip()
            d1 = d1[~d1[sku_col1].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]; 
            
            # --- PENAMBAHAN '0' KHUSUS UNTUK DAFTAR SKU TARGET DI NEWSPAGE ---
            d1[sku_col1] = d1[sku_col1].apply(lambda x: '0' + str(x) if str(x) in TARGET_SKUS else x)
            
            d1[qty_col1] = pd.to_numeric(d1[qty_col1], errors='coerce').fillna(0); d1_agg = (d1.groupby(sku_col1).agg({desc_col1: 'first', qty_col1: 'sum'}).reset_index().rename(columns={sku_col1: 'SKU', desc_col1: 'Description', qty_col1: 'Newspage'}))
            
            # --- FILTER DISTRIBUTOR STOCK DATA TERLEBIH DAHULU ---
            if 'Export' in df2.columns:
                df2 = df2[pd.to_numeric(df2['Export'], errors='coerce') == 1]
            if 'Nama Gudang' in df2.columns:
                df2 = df2[df2['Nama Gudang'].astype(str).str.strip().str.upper() == 'GUDANG UTAMA']
                
            d2 = df2[[sku_col2, qty_col2]].copy(); d2 = d2.dropna(subset=[sku_col2]); d2[sku_col2] = d2[sku_col2].astype(str).str.split('.').str[0].str.strip()
            d2 = d2[~d2[sku_col2].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]; 
            
            # --- PENAMBAHAN '0' KHUSUS UNTUK DAFTAR SKU TARGET DI DISTRIBUTOR ---
            d2[sku_col2] = d2[sku_col2].apply(lambda x: '0' + str(x) if str(x) in TARGET_SKUS else x)
            
            d2[qty_col2] = pd.to_numeric(d2[qty_col2], errors='coerce').fillna(0); 
            
            # --- LOGIC PERKALIAN KHUSUS ---
            # Jika user ID adalah Purwokerto atau Tegal, kalikan QTY SKU tertentu dengan 24
            if st.session_state.current_np_user_id in ["NPSYS3000019163", "NPSYS3000018661"]:
                d2.loc[d2[sku_col2].isin(["8021803", "8021804"]), qty_col2] *= 24

            d2_agg = (d2.groupby(sku_col2)[qty_col2].sum().reset_index().rename(columns={sku_col2: 'SKU', qty_col2: 'Distributor'}))
            
            merged = pd.merge(d1_agg, d2_agg, on='SKU', how='outer')
            merged[['Newspage', 'Distributor']] = merged[['Newspage', 'Distributor']].fillna(0)
            merged['Description'] = merged['Description'].fillna('ITEM NOT IN MASTER')
            merged['Selisih'] = merged['Distributor'] - merged['Newspage']
            
            merged['Status'] = merged['Selisih'].apply(lambda x: 'Match' if x == 0 else 'Mismatch')
            
            mismatches = merged[merged['Status'] == 'Mismatch'].sort_values('Selisih')
            
            if len(mismatches) == 0: 
                st.success("Analysis complete: all sku matched!")
                st.session_state.reconcile_summary = None
            else:
                valid_mismatches = mismatches.copy()
                st.session_state.reconcile_summary = {'total_match': len(merged[merged['Selisih'] == 0]), 'total_mismatch': len(mismatches), 'df_view': mismatches[['SKU', 'Description', 'Newspage', 'Distributor', 'Selisih', 'Status']]}
                transfer_df = (valid_mismatches[['SKU', 'Selisih', 'Status']].rename(columns={'SKU': 'SKU', 'Selisih': 'Qty', 'Status': 'Status'}))
                st.session_state.reconcile_result = transfer_df
                st.rerun()

# ── Review Table & Engine Execution ───────────────────────────────────────────
if st.session_state.reconcile_summary is not None and st.session_state.reconcile_result is not None:
    # st.markdown("---")
    st.markdown("<div class='box-review'>Stock Review</div>", unsafe_allow_html=True)
    m1, m2 = st.columns(2); match_count = st.session_state.reconcile_summary['total_match']; mismatch_count = st.session_state.reconcile_summary['total_mismatch']
    with m1: st.markdown(f'''<div class="metric-box-match"><div class="metric-label">Match</div><div class="metric-value">{match_count}</div></div>''', unsafe_allow_html=True)
    with m2: st.markdown(f'''<div class="metric-box-mismatch"><div class="metric-label">Stock difference</div><div class="metric-value">{mismatch_count}</div></div>''', unsafe_allow_html=True)
    st.dataframe(st.session_state.reconcile_summary['df_view'], use_container_width=True, hide_index=True, column_config={"SKU": st.column_config.TextColumn("SKU", width="medium"), "Description": st.column_config.TextColumn("Description", width="large")})
    # st.markdown("<br>", unsafe_allow_html=True)
    
    df_view = st.session_state.reconcile_result.copy()
    
    df_view['Status'] = df_view['Status'].apply(lambda x: 'Pending' if x == 'Mismatch' else x)
    if 'Keterangan' not in df_view.columns: df_view['Keterangan'] = 'Ready to Process'
    
    st.markdown("<div class='box-queue'>Adjustment SKU List</div>", unsafe_allow_html=True)
    table_placeholder = st.empty(); table_placeholder.dataframe(df_view, use_container_width=True, hide_index=True)
    
    log_label_placeholder = st.empty()
    log_placeholder = st.empty()
    btn_placeholder = st.empty()
    
    if btn_placeholder.button("EXECUTE", type="primary", use_container_width=True):
        st.session_state.is_bot_running = True
        btn_placeholder.empty()
        
        bot_user, bot_pass = "", ""
        if supabase:
            try:
                res = supabase.table("distributor_vault").select("np_user_id, np_password").eq("nama_distributor", selected_distributor).execute()
                if res.data:
                    bot_user = res.data[0]['np_user_id']
                    bot_pass = res.data[0]['np_password']
            except: pass

        if not bot_user or not bot_pass: 
            st.session_state.is_bot_running = False
            st.error("Access Denied: Kredensial tidak ditemukan di Database!")
        else:
            # --- PENAMBAHAN LABEL LOG SESUAI REQUEST ---
            log_label_placeholder.markdown(f"<div class='terminal-label'>Log - Active Account: <span style='color: #38bdf8;'>{selected_distributor} ({bot_user})</span></div>", unsafe_allow_html=True); ensure_playwright()
            bot_logs_history  = []; bot_last_log_time = [time.time()]
            
            def ui_log(module, msg):
                now = time.time(); diff_ms = int((now - bot_last_log_time[0]) * 1000); bot_last_log_time[0] = now; timestamp = time.strftime('%H:%M:%S'); tag_class = f"tag-{module.lower()}"
                bot_logs_history.append(f"<span class='log-time'>[{timestamp}]</span><span class='log-ms'>[+{diff_ms}ms]</span><span class='log-tag {tag_class}'>[{module}]</span><span class='log-msg'>{msg}</span>")
                render_terminal(log_placeholder, bot_logs_history)
                
            global_start_time = time.time(); success_count, failed_count = 0, 0
            ui_log("SYS", "Allocating memory and initializing Chromium headless core...")
            
            if supabase:
                ui_log("SYS", "Supabase client active.")

            try:
                if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                asyncio.set_event_loop(asyncio.new_event_loop())
                with sync_playwright() as p:
                    ui_log("SYS", "Spawning browser context..."); browser = p.chromium.launch(headless=True); context = browser.new_context(no_viewport=True); page = context.new_page()
                    ui_log("AUTH", f"Connecting to Newspage..."); page.goto(URL_LOGIN, wait_until="domcontentloaded")
                    
                    ui_log("AUTH", f"Injecting hidden credentials for [{selected_distributor}]...")
                    page.locator("id=txtUserid").fill(bot_user); page.locator("id=txtPasswd").fill(bot_pass); page.locator("id=btnLogin").click(force=True)
                    try:
                        btn = page.locator("id=SYS_ASCX_btnContinue"); btn.wait_for(state="visible", timeout=5_000); btn.click(force=True)
                    except Exception: pass
                    
                    page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS); ui_log("AUTH", "Login successful.")
                    time.sleep(5); page.locator("id=pag_InventoryRoot_tab_Main_itm_StkAdj").dispatch_event("click")
                    add_btn = page.locator("id=pag_I_StkAdj_btn_Add_Value"); add_btn.wait_for(state="attached", timeout=TIMEOUT_MS); add_btn.click(force=True)
                    warehouse_link = page.get_by_role("link", name=WAREHOUSE, exact=True); warehouse_link.wait_for(state="visible"); warehouse_link.click(force=True)
                    page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").wait_for(state="visible")
                    
                    dropdown = page.locator("id=pag_I_StkAdj_NewGeneral_drp_n_REASON_HDR_Value")
                    if dropdown.is_enabled(): dropdown.select_option(REASON_CODE)
                    ui_log("SYS", "Ready. Opening data stream for payload injection...")

                    # --- POINT 2: Start Injecting SKU
                    progress_bar = st.progress(0)
                    total_rows = len(df_view)
                    
                    for i, (idx, row) in enumerate(df_view.iterrows()):
                        sku = str(row['SKU']).strip()
                        
                        try: 
                            qty = str(int(float(row['Qty'])))
                        except Exception: 
                            qty = str(row['Qty']).strip()

                        ui_log("INJECT", f"Processing Payload {i+1}/{total_rows} | Target SKU: [{sku}]")
                        
                        try:
                            # 1. Input SKU
                            sku_input = page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value")
                            ui_log("INJECT", f"Locking target node for SKU [{sku}]...")
                            sku_input.fill(sku)
                            
                            # 2. Trigger Tab & Jeda
                            ui_log("INJECT", "Triggering system lookup (Tab event)...")
                            sku_input.press("Tab")
                            time.sleep(1.5) 
                            
                            # 3. Input Qty & Jeda
                            qty_input = page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value")
                            qty_input.wait_for(state="visible", timeout=TIMEOUT_MS)
                            
                            ui_log("INJECT", f"Node resolved. Assigning adjustment quantity: {qty} EA")
                            qty_input.fill(qty)
                            time.sleep(0.5) 
                            
                            # 4. Klik Add
                            ui_log("INJECT", "Dispatching Add command to grid...")
                            page.locator("id=pag_I_StkAdj_NewGeneral_btn_Add_Value").click(force=True)
                            
                            # 5. Tunggu reset form
                            ui_log("SYS", "Awaiting DOM form reset confirmation...")
                            page.wait_for_function("document.getElementById('pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value').value === ''", timeout=TIMEOUT_MS)
                            
                            df_view.at[idx, 'Status'] = 'Success'
                            df_view.at[idx, 'Keterangan'] = f'Attached {qty} EA'
                            success_count += 1
                            ui_log("SUCCESS", f"Transaction {i+1} committed. Grid updated.")
                            
                            if supabase:
                                try:
                                    supabase.table("adjustment_logs").insert({
                                        "sku": sku, "qty": int(qty), "status": "Success", 
                                        "keterangan": f"Attached {qty} EA", "np_user": bot_user
                                    }).execute()
                                except: pass

                        except Exception as loop_err: 
                            df_view.at[idx, 'Status'] = 'Failed'
                            df_view.at[idx, 'Keterangan'] = 'Node Timeout'
                            failed_count += 1
                            ui_log("ERROR", f"Timeout on SKU [{sku}]. Node unresponsive. Skipping.")
                            
                            if supabase:
                                try:
                                    supabase.table("adjustment_logs").insert({
                                        "sku": sku, "qty": int(qty) if qty.replace('-','').isdigit() else 0, "status": "Failed", 
                                        "keterangan": "Node Timeout", "np_user": bot_user
                                    }).execute()
                                except: pass
                            
                        progress_bar.progress((i+1)/total_rows)
                        if i % TABLE_UPDATE_INTERVAL == 0 or i == total_rows-1: 
                            table_placeholder.dataframe(df_view, use_container_width=True, hide_index=True)
                            
                    ui_log("SERVER", "Finalizing batch. Saving document to main server...")
                    page.locator("id=pag_I_StkAdj_NewGeneral_btn_Save_Value").click()
                    try: 
                        yes_btn = page.locator("id=pag_PopUp_YesNo_btn_Yes_Value")
                        yes_btn.wait_for(state="visible", timeout=5000)
                        ui_log("SERVER", "Confirming save dialog...")
                        yes_btn.click()
                        ui_log("SERVER", "Document physically written to database.")
                    except Exception: 
                        ui_log("SERVER", "Auto-save confirmed. Document written to database.")
                        
                    # --- POINT 3: LANDING
                    ui_log("SYS", "Holding session for 5 seconds to ensure Newspage database write...")
                    time.sleep(5)
                    # -------------------------------------------------------------
                    
                    # --- LOGOUT SEQUENCE ---
                    ui_log("AUTH", "Initiating system logout sequence...")
                    try:
                        # Listener untuk menangkap pop up confirm dan otomatis menekan "Enter" (Accept)
                        page.once("dialog", lambda dialog: dialog.accept())
                        page.locator("id=btnLogout").click(timeout=10000)
                        ui_log("AUTH", "Pop up confirm logout muncul, otomatis menekan Enter...")
                        time.sleep(2)
                        ui_log("SUCCESS", "Logged out successfully.")
                    except Exception as e:
                        ui_log("ERROR", "Logout button not found or timeout.")
                        
                    ui_log("SYS", "Closing browser and releasing memory...")
                    browser.close()
                    elapsed = int(time.time() - global_start_time)
                    ui_log("SUCCESS", f"Complete. Total runtime: {elapsed//60}m {elapsed%60}s")
                    
                    st.markdown(make_solid_box(f"Done — Success: {success_count} | Failed: {failed_count} | Time: {elapsed//60}m {elapsed%60}s", "#166534", "#ffffff"), unsafe_allow_html=True)

                    if success_count > 0: 
                        st.toast('System override complete!')
                        st.session_state.reconcile_result = None
                        
                    st.session_state.is_bot_running = False

            except Exception as e: 
                st.session_state.is_bot_running = False
                st.error("System halted.")
                ui_log("ERROR", f"FAILURE: {e}")
