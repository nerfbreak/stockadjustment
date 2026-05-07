import streamlit as st
import time
import requests
import database
import data_processor
import playwright_engine

# --- 1. CONFIG & UI HELPERS ---
st.set_page_config(page_title="Stock Adjustment Newspage", layout="wide")
st.markdown("""
    <style>
    /* 1. Kontainer Label Judul dibikin full width biar bisa ditengahin */
    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextInput"] label,
    div[data-testid="stFileUploader"] label {
        width: 100% !important;
        justify-content: center !important;
        display: flex !important;
    }

    /* 2. Style Teks Label (Nama Distributor, NP Password, Upload) dibikin Center */
    div[data-testid="stSelectbox"] label p, 
    div[data-testid="stTextInput"] label p,
    div[data-testid="stFileUploader"] label p {
        font-family: "Inter", sans-serif !important;
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        color: #94a3b8 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
        text-align: center !important;
        width: 100% !important;
        margin-bottom: 8px !important; /* Kasih jarak dikit ke inputnya */
    }

    /* 3. Samakan semua font di dalam area kotak dropzone */
    div[data-testid="stFileUploadDropzone"] * {
        font-family: "Inter", sans-serif !important;
    }

    /* 4. Rapihkan tombol "Browse files" biar masuk tema corporate */
    div[data-testid="stFileUploader"] button {
        background-color: #1e293b !important;
        color: #3b82f6 !important;
        border: 1px solid #334155 !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        padding: 4px 16px !important;
    }

    /* Efek hover pas tombolnya disentuh */
    div[data-testid="stFileUploader"] button:hover {
        border-color: #3b82f6 !important;
        background-color: rgba(59, 130, 246, 0.1) !important;
        color: #38bdf8 !important;
    }

    /* 5. Hilangkan teks "Press Enter to submit" yang nabrak icon mata */
    div[data-testid="InputInstructions"] {
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)
st.markdown("""
    <style>
    /* Import font Inter */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    /* 1. Label Judul (Nama Distributor, Upload, NP Password) */
    div[data-testid="stSelectbox"] label p, 
    div[data-testid="stFileUploader"] label p,
    div[data-testid="stTextInput"] label p {
        font-family: "Inter", sans-serif !important;
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        color: #94a3b8 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
    }

    /* 2. Isi Dropdown List */
    div[data-baseweb="select"] * {
        font-family: "Inter", sans-serif !important;
    }

    /* 3. Area Dropzone Uploader (Teks Drag & Drop, 200MB limit, dan tombol) */
    [data-testid="stFileUploadDropzone"] * {
        font-family: "Inter", sans-serif !important;
    }
    
    /* Paksa teks kecil (200MB CSV XLSX) biar nggak terlalu mencolok */
    [data-testid="stFileUploadDropzone"] small {
        font-size: 0.7rem !important;
        color: #64748b !important;
        text-transform: none !important;
        letter-spacing: normal !important;
    }

    /* 4. Semua Tombol Utama (Extract, Clear, Execute, Browse Files) dan teks di dalamnya */
    div[data-testid="stButton"] button, 
    div[data-testid="stButton"] button p,
    div[data-testid="stFileUploader"] button,
    div[data-testid="stFileUploader"] button p {
        font-family: "Inter", sans-serif !important;
        font-size: 0.85rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
    }
    </style>
""", unsafe_allow_html=True)
URL_LOGIN             = "https://rb-id.np.accenture.com/RB_ID/Logon.aspx"
TIMEOUT_MS            = 30_000
TABLE_UPDATE_INTERVAL = 5

supabase = database.init_supabase()
REASON_CODE, WAREHOUSE = database.get_system_config(supabase)

def send_telegram_alert(message: str):
    bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try: requests.post(url, json=payload, timeout=5)
        except: pass

def make_solid_box(text: str, bg_color: str, text_color: str) -> str:
    return (f"<div style='background-color:{bg_color};color:{text_color};padding:12px 16px;border-radius:8px;font-weight:600;font-size:0.92rem;margin:8px 0;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.3);display:block;width:100%;'>{text}</div>")

def render_terminal(placeholder, logs_history: list):
    display_logs = "<br>".join(logs_history[-100:])
    html_content = f"""
    <div class="terminal-box" id="ext_term_box">{display_logs}<br><span class="blink_me">&#9608;</span></div>
    <script>
        var t = window.parent.document.getElementById('ext_term_box') || document.getElementById('ext_term_box');
        if (t) t.scrollTop = t.scrollHeight;
    </script>
    """
    placeholder.markdown(html_content, unsafe_allow_html=True)

# --- FUNGSI FOOTER COPYRIGHT ---
def render_footer():
    st.markdown("""
    <div style='text-align: center; margin-top: 80px; margin-bottom: 20px;'>
        <span style='font-family: "Inter", sans-serif; font-size: 0.6rem; color: #64748b; letter-spacing: 0.05em; text-transform: uppercase;'>
            &copy; 2026 IT Support Newspage. by kopi mang toni.
        </span>
    </div>
    """, unsafe_allow_html=True)

# --- 2. AUTHENTICATION GATEKEEPER ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "current_user" not in st.session_state: st.session_state.current_user = "unknown"

if not st.session_state.logged_in:
    # CSS KHUSUS LOGIN CARD (MODERN LOOK)
    st.markdown("""
        <style>
        /* Hilangkan instruksi 'Press Enter' */
        div[data-testid="InputInstructions"] { display: none !important; }

        /* Bikin Kotak Login (Card) */
        div[data-testid="stForm"] {
            border: 1px solid #334155 !important;
            border-radius: 16px !important;
            background-color: #0f172a !important;
            padding: 40px !important;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.04) !important;
        }

        /* Rapihkan Label */
        div[data-testid="stTextInput"] label p {
            font-family: "Inter", sans-serif !important;
            font-size: 0.7rem !important;
            font-weight: 700 !important;
            color: #94a3b8 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.1em !important;
            text-align: center !important;
            width: 100% !important;
        }

        /* Input Field Styling */
        div[data-testid="stTextInput"] input {
            background-color: #1e293b !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            color: #f8fafc !important;
            text-align: center !important;
        }

        div[data-testid="stTextInput"] input:focus {
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 1px #3b82f6 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Layouting ke Tengah
    _, col_mid, _ = st.columns([1, 1.2, 1])
    
    with col_mid:
        st.markdown("<div style='margin-top: 80px;'></div>", unsafe_allow_html=True)
        
        # Header di atas Card
        st.markdown("""
            <div style='text-align: center; margin-bottom: 30px;'>
                <h2 style='color: #f8fafc; font-family: "Inter", sans-serif; margin-bottom: 0;'></h2>
                <p style='color: #64748b; font-family: "Inter", sans-serif; font-size: 0.85rem;'>Bot Engine V.20</p>
            </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="")
            password = st.text_input("Password", type="password", placeholder="")
            
            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
            
            submit = st.form_submit_button("LOGIN", use_container_width=True)
            
            if submit:
                if database.authenticate_user(supabase, username, password):
                    st.session_state.logged_in = True
                    st.session_state.current_user = username
                    st.rerun()
                else:
                    st.markdown("<p style='color: #ef4444; font-size: 0.8rem; text-align: center;'>Invalid credentials. Access denied.</p>", unsafe_allow_html=True)

    render_footer()
    st.stop()

# --- 3. STATE MANAGEMENT & STYLING ---
if 'reconcile_result' not in st.session_state: st.session_state.reconcile_result = None
if 'reconcile_summary' not in st.session_state: st.session_state.reconcile_summary = None
if 'np_df' not in st.session_state: st.session_state.np_df = None
if 'is_bot_running' not in st.session_state: st.session_state.is_bot_running = False
if 'prev_file2' not in st.session_state: st.session_state.prev_file2 = None
if 'current_np_user_id' not in st.session_state: st.session_state.current_np_user_id = ""
if 'execute_done' not in st.session_state: st.session_state.execute_done = False

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
    .terminal-box { background-color: #0b1120; color: #e2e8f0; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; padding: 16px 20px; border: 1px solid #1e293b; border-radius: 8px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); height: 320px; overflow-y: auto; line-height: 1.8; -ms-overflow-style: none; scrollbar-width: none; margin-top: 8px; margin-bottom: 32px; }
    .terminal-box::-webkit-scrollbar { display: none; }
    .terminal-label { font-family: 'Inter', sans-serif; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em; color: #64748b; text-transform: uppercase; margin-bottom: 4px; }
    .blink_me { animation: blinker 1s linear infinite; font-weight: bold; color: #3b82f6; }
    @keyframes blinker { 50% { opacity: 0; } }
    .log-time   { display: inline-block; width: 85px; color: #64748b; font-family: 'JetBrains Mono', monospace; }
    .log-ms     { display: inline-block; width: 75px; text-align: right; margin-right: 15px; color: #94a3b8; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; }
    .log-tag    { display: inline-block; width: 95px; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
    .log-msg    { color: #f8fafc; font-weight: 400; font-family: 'JetBrains Mono', monospace; }
    .tag-sys     { color: #8b5cf6; } .tag-auth    { color: #eab308; } .tag-nav     { color: #3b82f6; } .tag-inject  { color: #06b6d4; } .tag-success { color: #10b981; } .tag-error   { color: #ef4444; } .tag-server  { color: #f43f5e; }
    .box-np, .box-dist, .box-review, .box-queue, .box-results { background: linear-gradient(145deg, #1e293b, #0f172a); color: #f8fafc; padding: 12px 16px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; border: 1px solid #334155; margin-bottom: 16px; letter-spacing: 0.02em; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }
    .box-np { border-top: 3px solid #3b82f6; } .box-dist { border-top: 3px solid #10b981; } .box-review { border-top: 3px solid #06b6d4; } .box-queue { border-top: 3px solid #8b5cf6; } .box-results { border-top: 3px solid #0b42f5; }
    .metric-box-match, .metric-box-mismatch { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1); }
    .metric-box-match { border-left: 4px solid #10b981; } .metric-box-mismatch { border-left: 4px solid #ef4444; }
    .metric-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; }
    .metric-box-match .metric-value { color: #10b981; font-size: 2rem; font-weight: 700; font-family: 'Inter', sans-serif; margin-top: 4px; line-height: 1; }
    .metric-box-mismatch .metric-value { color: #ef4444; font-size: 2rem; font-weight: 700; font-family: 'Inter', sans-serif; margin-top: 4px; line-height: 1; }
    button[kind="primary"] { background-color: #2563eb !important; color: #ffffff !important; border: 1px solid #1d4ed8 !important; font-weight: 600 !important; letter-spacing: 0.05em !important; transition: all 0.2s ease !important; border-radius: 6px !important; font-family: 'Inter', sans-serif !important; }
    button[kind="primary"]:hover { background-color: #1e40af !important; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2) !important; border-color: #1e40af !important; }
    .typewriter-sub { font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; color: #64748b; margin: 0; }
    .live-indicator { display: inline-flex; align-items: center; color: #10b981; font-family: 'Inter', sans-serif; font-weight: 600; font-size: 0.75rem; letter-spacing: 0.1em; background: rgba(16, 185, 129, 0.1); padding: 4px 10px; border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.2); }
    .live-indicator::before { content: ''; display: inline-block; width: 6px; height: 6px; background-color: #10b981; border-radius: 50%; margin-right: 6px; animation: pulse-radar 2s infinite; }
    @keyframes pulse-radar { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); } 70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }
    hr { border: none !important; height: 1px !important; background-color: #334155 !important; margin-top: 1.5rem !important; margin-bottom: 1.5rem !important; }
    div[data-testid="stContainer"] { border: 1px solid #334155; border-radius: 10px; padding: 20px; background-color: #0f172a; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    </style>
    <script>
    let wakeLock = null;
    const requestWakeLock = async () => { try { wakeLock = await navigator.wakeLock.request('screen'); } catch (err) { console.log(`${err.name}, ${err.message}`); } };
    requestWakeLock();
    document.addEventListener('visibilitychange', async () => { if (wakeLock !== null && document.visibilityState === 'visible') { requestWakeLock(); } });
    </script>
""", unsafe_allow_html=True)

# --- 4. MAIN UI LAYOUT ---
st.markdown("<div class='live-indicator'>LIVE</div>", unsafe_allow_html=True)
st.markdown("<h1>Compare & Adjustment Stock</h1>", unsafe_allow_html=True)
st.markdown(f"""
    <div style='display: inline-block; margin-top: -4px;'>
        <span style='font-family: "Inter", sans-serif; font-size: 0.65rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin-right: 8px;'>Active Session</span>
        <span style='font-family: "Inter", sans-serif; font-size: 0.65rem; font-weight: 700; color: #3b82f6; text-transform: uppercase; letter-spacing: 0.1em;'>{st.session_state.current_user}</span>
    </div>
""", unsafe_allow_html=True)

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    with st.container(border=True):
        st.markdown("<div class='box-np'>Newspage Stock Data</div>", unsafe_allow_html=True)
        np_col1, np_col2 = st.columns(2)
        
        list_dist = database.get_distributor_list(supabase)

        with np_col1:
            selected_distributor = st.selectbox("Nama Distributor", list_dist, key="distributor_select")
            bot_user, bot_pass = database.get_distributor_creds(supabase, selected_distributor)
            if bot_user: st.session_state.current_np_user_id = bot_user
                
        with np_col2:
            st.text_input("NP Password", value="••••••••", type="password", disabled=True, key="np_pass_dummy")
        
        extract_btn = st.button("Extract Inventory Master", type="primary", use_container_width=True)
        file1 = None

with col2:
    with st.container(border=True):
        st.markdown("<div class='box-dist'>Distributor Stock Data</div>", unsafe_allow_html=True)
        def handle_fragment_upload():
            f = st.file_uploader("Upload Distributor stock file", type=['csv', 'xlsx'], key="file2_uploader")
            st.markdown("<div style='margin-bottom: 28px;'></div>", unsafe_allow_html=True)
            curr_f = getattr(f, "file_id", f.name if f else None) if f else None
            if curr_f != st.session_state.prev_file2:
                st.session_state.prev_file2 = curr_f
                if not st.session_state.is_bot_running: st.rerun()

        if hasattr(st, "fragment"):
            @st.fragment
            def render_upload_dist(): handle_fragment_upload()
            render_upload_dist()
        elif hasattr(st, "experimental_fragment"):
            @st.experimental_fragment
            def render_upload_dist(): handle_fragment_upload()
            render_upload_dist()
        else:
            handle_fragment_upload()
        file2 = st.session_state.get("file2_uploader")

if st.session_state.np_df is not None:
    st.markdown(make_solid_box(f"Extracted — {len(st.session_state.np_df)} items loaded from server", "#082f49", "#38bdf8"), unsafe_allow_html=True)
    if st.button("Clear extracted data", use_container_width=True):
        st.session_state.np_df = None
        st.rerun()

ext_label_placeholder = st.empty()
ext_log_placeholder = st.empty()

# --- 5. TRIGGER EXTRACTION ---
if extract_btn:
    if not bot_user or not bot_pass:
        st.error("Gagal! Kredensial untuk distributor ini tidak ditemukan di Supabase.")
        st.stop()

    st.session_state.is_bot_running = True
    ext_label_placeholder.markdown("""
        <div style='display: inline-block; margin-bottom: 4px;'>
            <span style='font-family: "Inter", sans-serif; font-size: 0.65rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin-right: 8px;'>System Activity</span>
            <span style='font-family: "Inter", sans-serif; font-size: 0.65rem; font-weight: 700; color: #3b82f6; text-transform: uppercase; letter-spacing: 0.1em;'>EXTRACT_LOG</span>
        </div>
    """, unsafe_allow_html=True)
    ext_logs_history  = []
    ext_last_log_time = [time.time()]

    def ext_ui_log(module, msg):
        now = time.time(); diff_ms = int((now - ext_last_log_time[0]) * 1000); ext_last_log_time[0] = now
        timestamp = time.strftime('%H:%M:%S'); tag_class = f"tag-{module.lower()}"
        ext_logs_history.append(f"<span class='log-time'>[{timestamp}]</span><span class='log-ms'>[+{diff_ms}ms]</span><span class='log-tag {tag_class}'>[{module}]</span><span class='log-msg'>{msg}</span>")
        render_terminal(ext_log_placeholder, ext_logs_history)

    playwright_engine.run_extract(
        bot_user, bot_pass, selected_distributor, URL_LOGIN, TIMEOUT_MS, WAREHOUSE, 
        ext_ui_log, send_telegram_alert, supabase, st.session_state.current_user
    )


# --- 6. DATA COMPARISON ---
np_source_ready = (st.session_state.np_df is not None) or (file1 is not None)
if np_source_ready and file2:
    df1 = st.session_state.np_df if st.session_state.np_df is not None else data_processor.load_data(file1)
    df2 = data_processor.load_data(file2)
    
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

        if st.button("Compare Stock", type="primary", use_container_width=True):
            TARGET_SKUS = database.get_target_skus(supabase)
            multipliers = database.get_multiplier_rules(supabase, st.session_state.current_np_user_id)
            
            merged, mismatches = data_processor.process_compare(
                df1, df2, sku_col1, desc_col1, qty_col1, sku_col2, qty_col2, TARGET_SKUS, multipliers
            )
            
            if len(mismatches) == 0: 
                st.success("Analysis complete: all sku matched!")
                st.session_state.reconcile_summary = None
            else:
                valid_mismatches = mismatches.copy()
                st.session_state.reconcile_summary = {'total_match': len(merged[merged['Selisih'] == 0]), 'total_mismatch': len(mismatches), 'df_view': mismatches[['SKU', 'Description', 'Newspage', 'Distributor', 'Selisih', 'Status']]}
                transfer_df = (valid_mismatches[['SKU', 'Selisih', 'Status']].rename(columns={'SKU': 'SKU', 'Selisih': 'Qty', 'Status': 'Status'}))
                st.session_state.reconcile_result = transfer_df
                st.rerun()


# --- 7. EXECUTION / INJECTION ---
if st.session_state.reconcile_summary is not None and st.session_state.reconcile_result is not None:
    st.markdown("<div class='box-review'>Stock Review</div>", unsafe_allow_html=True)
    m1, m2 = st.columns(2); match_count = st.session_state.reconcile_summary['total_match']; mismatch_count = st.session_state.reconcile_summary['total_mismatch']
    with m1: st.markdown(f'''<div class="metric-box-match"><div class="metric-label">Match</div><div class="metric-value">{match_count}</div></div>''', unsafe_allow_html=True)
    with m2: st.markdown(f'''<div class="metric-box-mismatch"><div class="metric-label">Stock difference</div><div class="metric-value">{mismatch_count}</div></div>''', unsafe_allow_html=True)
    st.dataframe(st.session_state.reconcile_summary['df_view'], use_container_width=True, hide_index=True, column_config={"SKU": st.column_config.TextColumn("SKU", width="medium"), "Description": st.column_config.TextColumn("Description", width="large")})
    
    df_view = st.session_state.reconcile_result.copy()
    df_view['Status'] = df_view['Status'].apply(lambda x: 'Pending' if x == 'Mismatch' else x)
    if 'Keterangan' not in df_view.columns: df_view['Keterangan'] = 'Ready to Process'
    
    st.markdown("<div class='box-queue'>Adjustment SKU List</div>", unsafe_allow_html=True)
    table_placeholder = st.empty(); table_placeholder.dataframe(df_view, use_container_width=True, hide_index=True)
    
    log_label_placeholder = st.empty()
    log_placeholder = st.empty()
    btn_placeholder = st.empty()
            
    if btn_placeholder.button("EXECUTE", type="primary", use_container_width=True):
        if not bot_user or not bot_pass: 
            st.error("Access Denied: Kredensial tidak ditemukan di Database!")
        else:
            st.session_state.is_bot_running = True
            st.session_state.execute_done = False
            btn_placeholder.empty()
            
            log_label_placeholder.markdown(f"""
                <div style='display: inline-block; margin-bottom: 4px;'>
                    <span style='font-family: "Inter", sans-serif; font-size: 0.65rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin-right: 8px;'>Active Account</span>
                    <span style='font-family: "Inter", sans-serif; font-size: 0.65rem; font-weight: 700; color: #10b981; text-transform: uppercase; letter-spacing: 0.1em;'>{selected_distributor} ({bot_user})</span>
                </div>
            """, unsafe_allow_html=True)
            bot_logs_history  = []; bot_last_log_time = [time.time()]
            
            def bot_ui_log(module, msg):
                now = time.time(); diff_ms = int((now - bot_last_log_time[0]) * 1000); bot_last_log_time[0] = now
                timestamp = time.strftime('%H:%M:%S'); tag_class = f"tag-{module.lower()}"
                bot_logs_history.append(f"<span class='log-time'>[{timestamp}]</span><span class='log-ms'>[+{diff_ms}ms]</span><span class='log-tag {tag_class}'>[{module}]</span><span class='log-msg'>{msg}</span>")
                render_terminal(log_placeholder, bot_logs_history)

            playwright_engine.run_execution(
                df_view, bot_user, bot_pass, selected_distributor, URL_LOGIN, TIMEOUT_MS, WAREHOUSE, 
                REASON_CODE, TABLE_UPDATE_INTERVAL, bot_ui_log, send_telegram_alert, table_placeholder, log_label_placeholder, supabase
            )

# --- Panggil footer di paling bawah halaman aplikasi utama ---
render_footer()
