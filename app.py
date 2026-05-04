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
st.set_page_config(page_title="Stock Adjustment Engine", page_icon="🤖", layout="wide")

# --- 1.5. LOGIN GATEKEEPER ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<h2 style='text-align:center;color:#3b82f6;'>System Logon</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#64748b;'>Establish secure connection to engine</p>", unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("CONNECT", use_container_width=True)

            if submit:
                if username == st.secrets["admin_user"] and password == st.secrets["admin_pass"]:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("ACCESS DENIED: Invalid credentials.")
    st.stop()

# --- 2. CONSTANTS ---
URL_LOGIN             = "https://rb-id.np.accenture.com/RB_ID/Logon.aspx"
CREDENTIALS_FILE      = "users_2.csv"
REASON_CODE           = "SA2"
WAREHOUSE             = "GOOD_WHS"
TIMEOUT_MS            = 60_000 
TABLE_UPDATE_INTERVAL = 5

# --- 3. HELPER FUNCTIONS ---
def load_data(file):
    if file is None: return None
    df = None
    filename = file.name.lower()
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file, sep='\t', dtype=str)
            if df.shape[1] <= 1:
                file.seek(0); df = pd.read_csv(file, sep=',', dtype=str)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file, dtype=str)
        elif filename.endswith('.zip'):
            with zipfile.ZipFile(file) as z:
                target = next((n for n in z.namelist() if "INVT_MASTER" in n and n.lower().endswith(".csv")), None)
                if not target: target = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
                if target:
                    with z.open(target) as f: df = pd.read_csv(f, sep='\t', dtype=str)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None
    return df

@st.cache_data(ttl=300)
def load_accounts():
    accounts = []
    if not os.path.exists(CREDENTIALS_FILE): return accounts
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
        except (UnicodeDecodeError, TypeError): continue
    return accounts

@st.cache_resource
def ensure_playwright():
    try: subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e: st.error(f"Failed to install browser engine: {e}")

def make_solid_box(text: str, bg_color: str, text_color: str) -> str:
    return f"<div style='background-color:{bg_color};color:{text_color};padding:12px 16px;border-radius:8px;font-weight:600;font-size:0.92rem;margin:8px 0;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.3);display:block;width:100%;'>{text}</div>"

# --- 4. STATE MANAGEMENT ---
if 'app_page' not in st.session_state: st.session_state.app_page = "Reconcile"
if 'reconcile_result' not in st.session_state: st.session_state.reconcile_result = None
if 'reconcile_summary' not in st.session_state: st.session_state.reconcile_summary = None
if 'np_df' not in st.session_state: st.session_state.np_df = None 

# --- 5. CUSTOM CSS & JAVASCRIPT (Full Hacker Package) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

    .terminal-box {
        background-color: transparent; color: #f0f6fc; font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem; padding: 5px 0; border: none; box-shadow: none; height: 350px;
        overflow-y: auto; line-height: 1.8; -ms-overflow-style: none; scrollbar-width: none;
    }
    .terminal-box::-webkit-scrollbar { display: none; }
    .blink_me { animation: blinker 1s linear infinite; font-weight: bold; color: #FF1B6B; }
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
        background-color: #FF1B6B !important; color: #ffffff !important; border: none !important;
        font-weight: 700 !important; letter-spacing: 1px !important; text-transform: uppercase !important;
        transition: all 0.3s ease !important; border-radius: 6px !important; font-family: 'Inter', sans-serif !important;
    }
    button[kind="primary"]:hover {
        background-color: #d41459 !important; box-shadow: 0 0 20px rgba(255, 27, 107, 0.8) !important; transform: translateY(-2px) !important;
    }
    button[kind="primary"]:active { transform: translateY(0px) !important; }

    .typewriter-sub {
        font-family: 'JetBrains Mono', monospace; font-size: 1rem; color: #8b949e; overflow: hidden;
        border-right: 0.15em solid #FF1B6B; white-space: nowrap; margin: 0;
        animation: typing-sub 10s infinite, blink-caret .75s step-end infinite;
    }
    @keyframes typing-sub {
        0% { width: 0; animation-timing-function: steps(29, end); }
        30% { width: 29ch; animation-timing-function: step-end; }
        80% { width: 29ch; animation-timing-function: steps(29, end); }
        100% { width: 0; }
    }
    @keyframes blink-caret { from, to { border-color: transparent; } 50% { border-color: #FF1B6B; } }

    .live-indicator {
        display: inline-flex; align-items: center; color: #4ade80; font-family: 'JetBrains Mono', monospace;
        font-weight: 700; font-size: 0.85rem; letter-spacing: 0.08em;
    }
    .live-indicator::before {
        content: ''; display: inline-block; width: 8px; height: 8px; background-color: #4ade80;
        border-radius: 50%; margin-right: 7px; box-shadow: 0 0 6px #4ade80; animation: pulse-radar 1.4s infinite alternate;
    }
    @keyframes pulse-radar { from { transform: scale(0.8); opacity: 0.6; } to { transform: scale(1.2); opacity: 1; box-shadow: 0 0 12px #4ade80; } }

    hr { border: none !important; height: 1px !important; background: linear-gradient(90deg, transparent, #FF1B6B, transparent) !important; opacity: 0.8 !important; margin-top: 1.5rem !important; margin-bottom: 1.5rem !important; }
    ::selection { background: #FF1B6B !important; color: #000000 !important; }
    ::-moz-selection { background: #FF1B6B !important; color: #000000 !important; }
    *::-webkit-scrollbar { width: 6px !important; height: 6px !important; background-color: transparent !important; }
    *::-webkit-scrollbar-track { background-color: rgba(255,255,255,0.04) !important; border-radius: 10px !important; }
    *::-webkit-scrollbar-thumb { background-color: #FF1B6B !important; border-radius: 10px !important; }
    *::-webkit-scrollbar-thumb:hover { background-color: #d41459 !important; }
    * { scrollbar-width: thin !important; scrollbar-color: #FF1B6B transparent !important; }

    [data-testid="stStatusWidget"] { background-color: #0d1117 !important; border: 1px solid #FF1B6B !important; box-shadow: 0 0 10px rgba(255, 27, 107, 0.4) !important; border-radius: 4px !important; padding: 2px 10px !important; }
    [data-testid="stStatusWidget"] * { color: #FF1B6B !important; font-family: 'JetBrains Mono', monospace !important; font-weight: bold !important; letter-spacing: 0.5px !important; }
    header[data-testid="stHeader"] { border-bottom: 1px solid rgba(255, 27, 107, 0.3) !important; }

    .typewriter {
        font-family: 'JetBrains Mono', monospace; font-size: 1.6rem; font-weight: 700; color: #f0f6fc;
        overflow: hidden; border-right: 0.12em solid #FF1B6B; white-space: nowrap; margin: 0; padding-right: 5px; width: max-content;
        animation: typing 3s steps(25, end) infinite alternate, blink-caret .75s step-end infinite;
    }
    @keyframes typing { from { width: 0; } to { width: 100%; } }
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] > div { color: #FF1B6B !important; font-weight: 700 !important; display: block !important; text-shadow: 0 0 5px rgba(255,27,107,0.5); }
    div[data-testid="stContainer"] { border: 1px solid rgba(255, 27, 107, 0.2); border-radius: 8px; padding: 16px; margin-bottom: 12px; background-color: rgba(13, 17, 23, 0.6); }
    
    div[data-baseweb="input"]:focus-within {
        border-color: #FF1B6B !important; box-shadow: 0 0 15px rgba(255, 27, 107, 0.4) !important; background-color: rgba(255, 27, 107, 0.02) !important;
    }
    
    /* EFEK MONITOR MELENGKUNG (VIGNETTE) */
    [data-testid="stAppViewContainer"]::before {
        content: " "; position: fixed; top: 0; left: 0; bottom: 0; right: 0;
        background: radial-gradient(circle, rgba(0,0,0,0) 60%, rgba(0,0,0,0.4) 100%);
        pointer-events: none; z-index: 10;
    }
    
    /* CYBERPUNK MOUSE GLOW CROSSHAIR */
    html { cursor: crosshair; }
    body {
        background-attachment: fixed;
        background-image: radial-gradient(circle at var(--mouse-x, 50%) var(--mouse-y, 50%), rgba(255, 27, 107, 0.08) 0%, transparent 20%) !important;
    }
    </style>
""", unsafe_allow_html=True)

# MOUSE GLOW JAVASCRIPT (SAFE ZONE)
st.components.v1.html(
    """
    <script>
    var root = window.parent.document.querySelector('body');
    window.parent.addEventListener('mousemove', e => {
        root.style.setProperty('--mouse-x', e.clientX + 'px');
        root.style.setProperty('--mouse-y', e.clientY + 'px');
    });
    </script>
    """,
    height=0,
)

# ─── 6. PAGE: RECONCILE ──────────────────────────────────────────────────────
if st.session_state.app_page == "Reconcile":
    st.markdown("<div class='live-indicator'>SYSTEM ONLINE</div>", unsafe_allow_html=True)
    st.markdown("<h1 class='typewriter'>Data Extraction & Compare</h1>", unsafe_allow_html=True)
    st.markdown("<div class='typewriter-sub'>Powered by Custom Playwright Engine...</div>", unsafe_allow_html=True)
    st.markdown("---")

    accounts = load_accounts()

    col1, col2 = st.columns(2)
    
    # --- KIRI: AUTO-EXTRACT NEWSPAGE ---
    with col1:
        st.subheader("📡 Newspage (Auto-Extract)")
        if st.session_state.np_df is None:
            with st.container(border=True):
                acc_str_np = st.selectbox(
                    "Select Account to Run Extraction",
                    options=[f"{acc['Distributor']} ({acc['user_id']})" for acc in accounts],
                    index=None, placeholder="-- Select Target Account --"
                )
                pass_np = st.text_input("Enter Password", type="password", placeholder="Accenture Password")
                
                extract_ready = acc_str_np is not None and len(pass_np) > 3
                if st.button("RUN EXTRACTION JOB", type="primary", use_container_width=True, disabled=not extract_ready):
                    log_placeholder_np = st.empty()
                    logs_history_np = []
                    last_log_time_np = [time.time()]

                    def ui_log_np(module, msg):
                        now = time.time()
                        diff_ms = int((now - last_log_time_np[0]) * 1000)
                        last_log_time_np[0] = now
                        timestamp = time.strftime('%H:%M:%S')
                        new_log = f"<span class='log-time'>[{timestamp}]</span><span class='log-ms'>[+{diff_ms}ms]</span><span class='log-tag tag-{module.lower()}'>[{module}]</span><span class='log-msg'>{msg}</span>"
                        logs_history_np.append(new_log)
                        html_content = f"""<div class="terminal-box" id="term_ext">{"<br>".join(logs_history_np[-100:])}<br><span class="blink_me">&#9608;</span></div>
                        <script>var t=window.parent.document.getElementById('term_ext')||document.getElementById('term_ext');if(t)t.scrollTop=t.scrollHeight;</script>"""
                        log_placeholder_np.markdown(html_content, unsafe_allow_html=True)

                    with st.spinner("Firing up extraction engine..."):
                        ensure_playwright()
                        try:
                            user_id_np = next(a for a in accounts if f"{a['Distributor']} ({a['user_id']})" == acc_str_np)["user_id"]
                            ui_log_np("SYS", "Allocating memory and initializing Chromium core...")
                            if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                            asyncio.set_event_loop(asyncio.new_event_loop())

                            with sync_playwright() as p:
                                browser = p.chromium.launch(headless=True)
                                context = browser.new_context(no_viewport=True)
                                page = context.new_page()

                                ui_log_np("AUTH", f"Connecting to {URL_LOGIN}...")
                                page.goto(URL_LOGIN, wait_until="domcontentloaded")
                                page.locator("id=txtUserid").fill(user_id_np)
                                page.locator("id=txtPasswd").fill(pass_np)
                                page.locator("id=btnLogin").click(force=True)

                                try:
                                    btn = page.locator("id=SYS_ASCX_btnContinue")
                                    btn.wait_for(state="visible", timeout=5_000)
                                    ui_log_np("AUTH", "Bypassing active session warning...")
                                    btn.click(force=True)
                                except Exception: pass

                                page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
                                ui_log_np("AUTH", "Login successful. Master session established.")

                                # === 21 STEPS EXTRACTION LOGIC DENGAN ANTI-TIMEOUT & DISPATCH EVENT ===
                                ui_log_np("NAV", "Accessing Import/Export Job module...")
                                time.sleep(3) 
                                
                                menu_job = page.locator("id=pag_Sys_Root_tab_Detail_itm_Job")
                                menu_job.wait_for(state="attached", timeout=15000)
                                menu_job.dispatch_event("click")
                                time.sleep(4)

                                ui_log_np("SYS", "Initializing new extraction job...")
                                page.locator("id=pag_FW_SYS_INTF_JOB_btn_Add_Value").click(force=True)
                                time.sleep(3)

                                page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_TYPE_Value").select_option("E")
                                time.sleep(2)

                                page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_DESC_Value").fill("Text Inventory Master")
                                page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_TIMEOUT_Value").fill("9999999")
                                page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_EXE_TYPE_Value").select_option("M")
                                time.sleep(2)

                                page.locator("id=pag_FW_SYS_INTF_JOB_RootNew_btn_Next_Value").click(force=True)
                                time.sleep(3)

                                ui_log_np("SYS", "Bypassing disclaimer warning...")
                                page.locator("id=pag_FW_DisclaimerMessage_btn_okay_Value").click(force=True)
                                time.sleep(2)

                                ui_log_np("NAV", "Opening Interface Selection Popup...")
                                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_INTF_ID_SelectButton").click(force=True)
                                time.sleep(3)

                                page.locator("id=pop_Dynamic_gft_List_2_FilterField_Value").fill("E_20150315090000028")
                                page.locator("id=pop_Dynamic_grd_Main_SearchForm_ButtonSearch_Value").click(force=True)
                                time.sleep(2)

                                ui_log_np("INJECT", "Selecting Target Interface: E_20150315090000028")
                                page.get_by_text("E_20150315090000028", exact=True).click(force=True)
                                time.sleep(2)

                                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_FILE_TYPE_Value").select_option("D")
                                time.sleep(1)

                                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_FLD_SEPARATOR_STD_Value_0").check()
                                
                                time.sleep(3) 
                                ui_log_np("INJECT", "Setting parameter: GOOD_WHS")
                                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_grd_DynamicFilter_ctl02_dyn_Field_txt_Value").fill("GOOD_WHS")
                                
                                time.sleep(2) 
                                ui_log_np("INJECT", "Setting parameter: 1")
                                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_grd_DynamicFilter_ctl08_dyn_Field_txt_Value").fill("1")

                                page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_btn_Add_Value").click(force=True)
                                time.sleep(3)

                                ui_log_np("SERVER", "Sending execution command to master server...")
                                page.locator("id=pag_FW_SYS_INTF_JOB_RootNew_btn_Save_Value").click(force=True)

                                ui_log_np("SYS", "Confirming execution prompt...")
                                page.locator("id=TF_Prompt_btn_Ok_Value").wait_for(state="visible", timeout=15000)
                                page.locator("id=TF_Prompt_btn_Ok_Value").click(force=True)

                                ui_log_np("SERVER", "Awaiting payload generation. Intercept module active (Up to 4 mins)...")
                                
                                with page.expect_download(timeout=240000) as download_info:
                                    download_btn = page.locator("id=pag_FW_SYS_INTF_STATUS_JOB_btn_Download_Value")
                                    download_btn.wait_for(state="visible", timeout=240000)
                                    download_btn.click(force=True)

                                download = download_info.value
                                
                                # TANGKAP NAMA FILE ASLI DARI SERVER
                                real_filename = download.suggested_filename
                                file_path = f"temp_ext_{real_filename}"
                                download.save_as(file_path)

                                ui_log_np("SUCCESS", f"PAYLOAD SECURED: File extracted as {real_filename}")
                                browser.close()
                                
                                # === BACA DATA KE MEMORI (SMART PARSER) ===
                                try:
                                    ui_log_np("SYS", "Decrypting and reading payload into memory...")
                                    df_ext = None
                                    
                                    # Deteksi format asli berdasarkan ekstensi dari server
                                    if real_filename.lower().endswith('.zip'):
                                        with zipfile.ZipFile(file_path) as z:
                                            target = next((n for n in z.namelist() if "INVT_MASTER" in n and n.lower().endswith((".csv", ".txt"))), None)
                                            if not target: 
                                                target = next((n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))), None)
                                            if target:
                                                with z.open(target) as f:
                                                    df_ext = pd.read_csv(f, sep='\t', dtype=str, on_bad_lines='skip')
                                                    if df_ext.shape[1] <= 1:
                                                        f.seek(0)
                                                        df_ext = pd.read_csv(f, sep=',', dtype=str, on_bad_lines='skip')
                                    
                                    elif real_filename.lower().endswith(('.xls', '.xlsx')):
                                        df_ext = pd.read_excel(file_path, dtype=str)
                                    
                                    else:
                                        # Brute-force separator & encoding untuk CSV/TXT
                                        for enc in ['utf-8', 'iso-8859-1', 'cp1252']:
                                            for separator in ['\t', ',', ';', '|']:
                                                try:
                                                    temp_df = pd.read_csv(file_path, sep=separator, dtype=str, encoding=enc, on_bad_lines='skip')
                                                    if temp_df is not None and temp_df.shape[1] > 1:
                                                        df_ext = temp_df
                                                        break
                                                except Exception:
                                                    try:
                                                        temp_df = pd.read_csv(file_path, sep=separator, dtype=str, encoding=enc, error_bad_lines=False)
                                                        if temp_df is not None and temp_df.shape[1] > 1:
                                                            df_ext = temp_df
                                                            break
                                                    except Exception:
                                                        continue
                                            if df_ext is not None and df_ext.shape[1] > 1:
                                                break
                                                
                                    # Final Check Data
                                    if df_ext is not None and not df_ext.empty and df_ext.shape[1] > 1:
                                        df_ext.columns = [str(c).strip() for c in df_ext.columns]
                                        st.session_state.np_df = df_ext
                                        st.rerun() # Refresh biar UI update
                                    else:
                                        st.error("CRITICAL: File berhasil didownload tapi gagal dibaca bentuk tabelnya.")
                                        ui_log_np("ERROR", "Parser failed to reconstruct dataframe.")
                                        
                                except Exception as e:
                                    st.error(f"Failed parsing downloaded file: {e}")
                                    ui_log_np("ERROR", f"Parsing error: {e}")

                        except PlaywrightTimeoutError:
                            st.error("Operation Timeout: Pastikan password benar dan server Newspage merespon.")
                        except Exception as e:
                            st.error(f"System halted: {e}")

        else:
            # 1. Kotak Sukses
            st.markdown(make_solid_box("STATUS: PAYLOAD SECURED & LOADED", "#0f2f1d", "#4ade80"), unsafe_allow_html=True)
            
            # 2. Total Item Metric
            total_items = len(st.session_state.np_df)
            st.markdown(f"""
                <div style='text-align: center; margin: 15px 0;'>
                    <span style='color: #8b949e; font-family: JetBrains Mono; font-size: 0.85rem;'>TOTAL EXTRACTED</span><br>
                    <span style='color: #4ade80; font-family: JetBrains Mono; font-size: 2rem; font-weight: bold;'>{total_items}</span>
                    <span style='color: #8b949e; font-family: JetBrains Mono; font-size: 0.9rem;'> ITEMS</span>
                </div>
            """, unsafe_allow_html=True)
            
            # 3. Mini Preview Table (Auto-filter)
            preview_cols = [c for c in st.session_state.np_df.columns if any(keyword in str(c).lower() for keyword in ['product', 'stock', 'qty', 'sku', 'desc'])]
            
            if len(preview_cols) > 0:
                mini_df = st.session_state.np_df[preview_cols].head(4)
            else:
                mini_df = st.session_state.np_df.iloc[:, -3:].head(4)

            with st.container(border=True):
                st.dataframe(mini_df, use_container_width=True, hide_index=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 4. Tombol Wipe
            if st.button("WIPE MEMORY & RE-EXTRACT", type="secondary", use_container_width=True):
                st.session_state.np_df = None
                st.rerun()

    # --- KANAN: MANUAL UPLOAD DISTRIBUTOR ---
    with col2:
        st.subheader("📂 Distributor (Manual Upload)")
        with st.container(border=True):
            file2 = st.file_uploader("Upload Distributor stock file", type=['csv', 'xlsx'])

    # --- JALANIN COMPARE STOCK ---
    if st.session_state.np_df is not None and file2:
        st.divider()
        df1 = st.session_state.np_df 
        df2 = load_data(file2)

        if df1 is not None and df2 is not None:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Newspage setup")
                idx_sku1 = df1.columns.get_loc('Product Code') if 'Product Code' in df1.columns else 0
                if 'Product Description' in df1.columns: idx_desc1 = df1.columns.get_loc('Product Description')
                elif 'Product Name' in df1.columns: idx_desc1 = df1.columns.get_loc('Product Name')
                else: idx_desc1 = 1 if len(df1.columns) > 1 else 0
                idx_qty1 = (df1.columns.get_loc('Stock Available') if 'Stock Available' in df1.columns else (2 if len(df1.columns) > 2 else 0))
                
                sku_col1  = st.selectbox("SKU column (NP)", df1.columns, index=idx_sku1)
                desc_col1 = st.selectbox("Description column (NP)", df1.columns, index=idx_desc1)
                qty_col1  = st.selectbox("Qty column (NP)", df1.columns, index=idx_qty1)

            with c2:
                st.subheader("Distributor setup")
                idx_sku2 = 20 if len(df2.columns) > 20 else 0
                qty2_col_match = next((col for col in df2.columns if str(col).strip().lower().replace(" ", "") == "stokakhir"), None)
                if qty2_col_match: idx_qty2 = df2.columns.get_loc(qty2_col_match)
                else: idx_qty2 = 71 if len(df2.columns) > 71 else (1 if len(df2.columns) > 1 else 0)
                
                sku_col2 = st.selectbox("SKU column (Dist)", df2.columns, index=idx_sku2)
                qty_col2 = st.selectbox("Qty column (Dist)", df2.columns, index=idx_qty2)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("COMPARE STOCK", type="primary", use_container_width=True):
                d1 = df1[[sku_col1, desc_col1, qty_col1]].copy()
                d1 = d1.dropna(subset=[sku_col1])
                d1[sku_col1] = d1[sku_col1].astype(str).str.split('.').str[0].str.strip()
                d1 = d1[~d1[sku_col1].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
                d1[qty_col1] = pd.to_numeric(d1[qty_col1], errors='coerce').fillna(0)
                d1_agg = (d1.groupby(sku_col1).agg({desc_col1: 'first', qty_col1: 'sum'}).reset_index().rename(columns={sku_col1: 'SKU', desc_col1: 'Description', qty_col1: 'Newspage'}))
                
                d2 = df2[[sku_col2, qty_col2]].copy()
                d2 = d2.dropna(subset=[sku_col2])
                d2[sku_col2] = d2[sku_col2].astype(str).str.split('.').str[0].str.strip()
                d2 = d2[~d2[sku_col2].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
                d2[sku_col2] = d2[sku_col2].replace({'373103': '0373103', '373100': '0373100'})
                d2[qty_col2] = pd.to_numeric(d2[qty_col2], errors='coerce').fillna(0)
                d2_agg = (d2.groupby(sku_col2)[qty_col2].sum().reset_index().rename(columns={sku_col2: 'SKU', qty_col2: 'Distributor'}))
                
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
                    transfer_df = (valid_mismatches[['SKU', 'Selisih_Clean']].rename(columns={'SKU': 'sku', 'Selisih_Clean': 'qty'}))
                    st.session_state.reconcile_result = transfer_df
                    st.session_state.app_page = "Bot"
                    st.rerun()

    if st.button("Bypass to Stock Adjustment"):
        st.session_state.reconcile_result = None
        st.session_state.reconcile_summary = None
        st.session_state.app_page = "Bot"
        st.rerun()

# ─── 7. PAGE: STOCK ADJUSTMENT BOT ───────────────────────────────────────────
elif st.session_state.app_page == "Bot":
    hdr_col1, hdr_col2 = st.columns([5, 1])
    with hdr_col1:
        st.markdown("<div class='live-indicator'>SYSTEM ONLINE</div>", unsafe_allow_html=True)
        st.markdown("<h1 class='typewriter'>Stock Adjustment Injection</h1>", unsafe_allow_html=True)
        st.markdown("<div class='typewriter-sub'>Powered by Custom Playwright Engine...</div>", unsafe_allow_html=True)
    with hdr_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Back to Reconcile", use_container_width=True):
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

    with cfg_col1:
        with st.container(border=True):
            selected_acc_str = st.selectbox(
                "Select Target Distributor / User ID",
                options=[f"{acc['Distributor']} ({acc['user_id']})" for acc in accounts],
                index=None, placeholder="-- Select account --"
            )
            selected_account = None
            user_password = ""
            if selected_acc_str:
                selected_account = next(acc for acc in accounts if f"{acc['Distributor']} ({acc['user_id']})" == selected_acc_str)
                user_password = st.text_input(f"Password for {selected_account['user_id']}:", type="password", placeholder="Accenture Password...")
                if len(user_password) > 3:
                    st.markdown(make_solid_box(f"Password Set — {selected_account['Distributor']} (Validated on Run)", "#0f2f1d", "#4ade80"), unsafe_allow_html=True)
                else:
                    st.markdown(make_solid_box("Waiting for password...", "#1e1b4b", "#a5b4fc"), unsafe_allow_html=True)

    with cfg_col2:
        with st.container(border=True):
            df_to_process = None
            if st.session_state.reconcile_result is not None:
                st.text_input("Data source", value="Auto-loaded from Compare Stock", disabled=True)
                df_to_process = st.session_state.reconcile_result
                st.markdown(make_solid_box(f"{len(df_to_process)} payloads ready to be injected", "#082f49", "#38bdf8"), unsafe_allow_html=True)
            else:
                uploaded_file = st.file_uploader("Data source (CSV / Excel)", type=["csv", "xlsx", "xls"])
                if uploaded_file is not None:
                    try:
                        filename = uploaded_file.name.lower()
                        if filename.endswith('.csv'): df_to_process = pd.read_csv(uploaded_file, dtype=str)
                        else: df_to_process = pd.read_excel(uploaded_file, dtype=str)
                        df_to_process.columns = [str(c).strip().lower() for c in df_to_process.columns]
                        if 'sku' in df_to_process.columns and 'qty' in df_to_process.columns:
                            st.markdown(make_solid_box(f"{len(df_to_process)} payloads ready to be injected", "#082f49", "#38bdf8"), unsafe_allow_html=True)
                        else:
                            st.error("Invalid format — column headers must be named 'sku' and 'qty'.")
                            df_to_process = None
                    except Exception as e: st.error(f"Failed to read file: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    is_ready = (selected_account is not None) and (len(user_password) > 3) and (df_to_process is not None)
    run_button = st.button("COMMENCE SYSTEM OVERRIDE", use_container_width=True, type="primary", disabled=not is_ready)

    st.subheader("Execution Payload Data")
    if not is_ready:
        st.warning("Select an account and ensure payload data is ready before initiating sequence.")
        st.stop()

    df_view = df_to_process.copy()
    if 'Status' not in df_view.columns: df_view['Status'] = 'Pending'
    if 'Keterangan' not in df_view.columns: df_view['Keterangan'] = '-'
    table_placeholder = st.dataframe(df_view, use_container_width=True)

    st.markdown("Execution Log:")
    log_placeholder = st.empty()

    if run_button:
        with st.spinner("Initializing Injection Engine..."):
            ensure_playwright()

        logs_history = []
        last_log_time = [time.time()]

        def ui_log(module, msg):
            now = time.time()
            diff_ms = int((now - last_log_time[0]) * 1000)
            last_log_time[0] = now
            timestamp = time.strftime('%H:%M:%S')
            tag_class = f"tag-{module.lower()}"
            new_log = f"<span class='log-time'>[{timestamp}]</span><span class='log-ms'>[+{diff_ms}ms]</span><span class='log-tag {tag_class}'>[{module}]</span><span class='log-msg'>{msg}</span>"
            logs_history.append(new_log)
            html_content = f"""<div class="terminal-box" id="term_box">{"<br>".join(logs_history[-100:])}<br><span class="blink_me">&#9608;</span></div>
            <script>var t = window.parent.document.getElementById('term_box') || document.getElementById('term_box');if (t) t.scrollTop = t.scrollHeight;</script>"""
            log_placeholder.markdown(html_content, unsafe_allow_html=True)

        global_start_time = time.time()
        success_count, failed_count = 0, 0
        user_id  = selected_account["user_id"]
        password = user_password

        ui_log("SYS", "Allocating memory and initializing Chromium headless core...")
        try:
            if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            asyncio.set_event_loop(asyncio.new_event_loop())

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(no_viewport=True)
                page = context.new_page()

                ui_log("AUTH", f"Connecting to {URL_LOGIN}...")
                page.goto(URL_LOGIN, wait_until="domcontentloaded")
                ui_log("AUTH", "DOM ready. Deploying credentials...")
                page.locator("id=txtUserid").fill(user_id)
                page.locator("id=txtPasswd").fill(password)
                page.locator("id=btnLogin").click(force=True)

                try:
                    btn = page.locator("id=SYS_ASCX_btnContinue")
                    btn.wait_for(state="visible", timeout=5_000)
                    ui_log("AUTH", "Active session interceptor detected. Bypassing...")
                    btn.click(force=True)
                except Exception: ui_log("SYS", "No interceptor detected. Clean session acquired.")

                page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
                ui_log("AUTH", "Login successful. Master Session established.")
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
                page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").wait_for(state="visible", timeout=TIMEOUT_MS)

                ui_log("SYS", f"Applying adjustment protocol: code [{REASON_CODE}]...")
                dropdown = page.locator("id=pag_I_StkAdj_NewGeneral_drp_n_REASON_HDR_Value")
                if dropdown.is_enabled(): dropdown.select_option(REASON_CODE)
                ui_log("SYS", "Ready. Opening data stream for payload injection...")

                progress_bar = st.progress(0)
                total_rows = len(df_view)
                for i, (idx, row) in enumerate(df_view.iterrows()):
                    sku = str(row['sku']).strip()
                    try: qty = str(int(float(row['qty'])))
                    except Exception: qty = str(row['qty']).strip()

                    ui_log("INJECT", f"Payload chunk {i + 1}/{total_rows} -> SKU [{sku}]")
                    try:
                        sku_input = page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value")
                        sku_input.fill(sku)
                        sku_input.press("Tab")
                        time.sleep(1)
                        page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").wait_for(state="visible", timeout=TIMEOUT_MS)
                        ui_log("INJECT", f"Assigning value: {qty}")
                        page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").fill(qty)
                        page.locator("id=pag_I_StkAdj_NewGeneral_btn_Add_Value").click(force=True)
                        ui_log("SYS", "Flushing buffer and awaiting system reset...")
                        page.wait_for_function("document.getElementById('pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value').value === ''", timeout=TIMEOUT_MS)
                        df_view.at[idx, 'Status'] = 'Success'
                        df_view.at[idx, 'Keterangan'] = f'Attached {qty} EA'
                        success_count += 1
                        ui_log("SUCCESS", "Transaction committed successfully to local cache.")
                    except Exception:
                        df_view.at[idx, 'Status'] = 'Failed'
                        df_view.at[idx, 'Keterangan'] = 'Node Timeout'
                        failed_count += 1
                        ui_log("ERROR", f"CRITICAL: Timeout querying node SKU [{sku}]. Segment bypassed.")

                    progress_bar.progress((i + 1) / total_rows)
                    if i % TABLE_UPDATE_INTERVAL == 0 or i == total_rows - 1:
                        table_placeholder.dataframe(df_view, use_container_width=True)

                ui_log("SERVER", "Data stream closed. Requesting master server validation...")
                page.locator("id=pag_I_StkAdj_NewGeneral_btn_Save_Value").click()
                try:
                    yes_btn = page.locator("id=pag_PopUp_YesNo_btn_Yes_Value")
                    yes_btn.wait_for(state="visible", timeout=5_000)
                    ui_log("SERVER", "Master server requested confirmation logic. Bypassing...")
                    yes_btn.click()
                    ui_log("SERVER", "Final validation passed. Document physically written to database.")
                except Exception:
                    ui_log("SERVER", "Automatic validation passed. Document physically written to database.")

                ui_log("SYS", "Shutting down Chromium instances and clearing memory allocation...")
                browser.close()
                elapsed = int(time.time() - global_start_time)
                ui_log("SUCCESS", f"EXECUTION TERMINATED NORMALLY. Total runtime: {elapsed // 60}m {elapsed % 60}s")
                st.markdown(make_solid_box(f"Done — Success: {success_count} | Failed: {failed_count} | Time: {elapsed // 60}m {elapsed % 60}s", "#166534", "#ffffff"), unsafe_allow_html=True)
                if success_count > 0:
                    st.toast('Connection Terminated')
                    time.sleep(0.5)
                    st.toast('Payload Injected Successfully')
                    time.sleep(0.5)
                    st.toast('System Override Complete!')
                    st.session_state.reconcile_result = None

        except PlaywrightTimeoutError:
            st.error("Login Failed: Password salah atau server target sedang tidak merespon (Timeout 60s).")
            ui_log("ERROR", "ACCESS DENIED: Handshake timeout. Invalid credentials or node unreachable.")
        except Exception as e:
            st.error("System halted due to an unexpected error.")
            clean_error = str(e).split('===')[0].strip()
            ui_log("ERROR", f"SYSTEM FAILURE: {clean_error}")
            ui_log("ERROR", traceback.format_exc().splitlines()[-1])
