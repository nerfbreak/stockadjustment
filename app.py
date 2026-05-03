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

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Stock Adjustment Newspage", page_icon="icon.png", layout="wide")
# os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

# ==========================================
# --- 1.5. SISTEM KEMANAN LOGIN (GATEKEEPER) ---
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    # Bikin tampilan form login agak ke tengah biar rapi
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<h2 style='text-align: center; color: #FF1B6B;'>Login</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #64748b;'>Enter credentials to access the engine</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login", use_container_width=True)
            
            if submit:
                # Validasi ngecek ke Streamlit Secrets
                if username == st.secrets["admin_user"] and password == st.secrets["admin_pass"]:
                    st.session_state.logged_in = True
                    st.rerun()  # Refresh halaman biar masuk ke aplikasi
                else:
                    st.error("Access Denied! Incorrect username or password.")
                    
    # HENTIKAN EKSEKUSI DI SINI JIKA BELUM LOGIN
    st.stop() 
# ==========================================

# --- 2. CONSTANTS ---
URL_LOGIN        = "https://rb-id.np.accenture.com/RB_ID/Logon.aspx"
CREDENTIALS_FILE = "users_2.csv"
REASON_CODE      = "SA2"
WAREHOUSE        = "GOOD_WHS"
TIMEOUT_MS       = 30_000

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
        st.error(f"Error reading file: {e}"); return None
    return df

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
                    
                    # ---> YANG DIUBAH DI SINI: Nggak perlu ngecek kolom password lagi
                    if "user_id" in cleaned_row and "Distributor" in cleaned_row:
                        accounts.append(cleaned_row)
                        
                return accounts
        except (UnicodeDecodeError, TypeError):
            continue
    return accounts

@st.cache_resource
def ensure_playwright():
    try: 
        # Panggil installer pakai sys.executable biar sistem nggak nyasar nyari path-nya
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"], 
            check=True
        )
    except Exception as e: 
        st.error(f"Gagal install engine browser: {e}")

# --- 4. STATE MANAGEMENT & CUSTOM CSS ANIMATION ---
if 'app_page' not in st.session_state: st.session_state.app_page = "Reconcile"
if 'reconcile_result' not in st.session_state: st.session_state.reconcile_result = None
if 'reconcile_summary' not in st.session_state: st.session_state.reconcile_summary = None

# CSS SUPER LOG: Update dengan warna teks #f0f6fc
st.markdown("""
    <style>
    .terminal-box {
        background-color: transparent; 
        color: #f0f6fc; /* Teks default terminal (kalau ada yang bocor dari class) */
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 0.85rem;
        padding: 5px 0px; 
        border: none; 
        box-shadow: none; 
        height: 350px;
        overflow-y: auto;
        line-height: 1.7;
        -ms-overflow-style: none;  
        scrollbar-width: none;  
    }
    .terminal-box::-webkit-scrollbar { display: none; }
    .blink_me { animation: blinker 1s linear infinite; font-weight: bold; color: #10b981; }
    @keyframes blinker { 50% { opacity: 0; } }
    
    /* Log Styling Details (Aligned Columns) */
    .log-time { display: inline-block; width: 85px; color: #64748b; }
    .log-ms { display: inline-block; width: 75px; text-align: right; margin-right: 15px; color: #fb923c; font-size: 0.75rem;}
    .log-tag { display: inline-block; width: 95px; font-weight: bold; }
    
    .tag-sys { color: #a855f7; }
    .tag-auth { color: #eab308; }
    .tag-nav { color: #3b82f6; }
    .tag-inject { color: #06b6d4; }
    .tag-success { color: #22c55e; }
    .tag-error { color: #ef4444; }
    .tag-server { color: #f43f5e; }
    
    /* Request Warna Teks Custom #f0f6fc */
    .log-msg { color: #f0f6fc; font-weight: 500; }
    
    /* TOMBOL BYPASS (Secondary Button) NEON PINK */
    button[kind="secondary"] {
        background-color: #FF1B6B !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    button[kind="secondary"]:hover {
        background-color: #d41459 !important;
        box-shadow: 0 0 15px rgba(255, 27, 107, 0.6) !important;
    }
    </style>
""", unsafe_allow_html=True)

# ─── 5. HALAMAN STEP 1: RECONCILE ───────────────────────────────────────────
if st.session_state.app_page == "Reconcile":
    st.title("Compare Stock")
    st.markdown("Inspired by Kopi Mang Toni")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1: file1 = st.file_uploader("Upload File Stock Newspage", type=['csv', 'xlsx', 'zip'])
    with col2: file2 = st.file_uploader("Upload File Stock Distributor", type=['csv', 'xlsx'])

    if file1 and file2:
        st.divider()
        df1 = load_data(file1)
        df2 = load_data(file2)

        if df1 is not None and df2 is not None:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Newspage Setup")
                idx_sku1 = df1.columns.get_loc('Product Code') if 'Product Code' in df1.columns else 0
                
                if 'Product Description' in df1.columns: idx_desc1 = df1.columns.get_loc('Product Description')
                elif 'Product Name' in df1.columns: idx_desc1 = df1.columns.get_loc('Product Name')
                else: idx_desc1 = 1 if len(df1.columns) > 1 else 0
                    
                idx_qty1 = df1.columns.get_loc('Stock Available') if 'Stock Available' in df1.columns else (2 if len(df1.columns) > 2 else 0)
                
                sku_col1 = st.selectbox("Kolom SKU (NP)", df1.columns, index=idx_sku1)
                desc_col1 = st.selectbox("Kolom Deskripsi (NP)", df1.columns, index=idx_desc1)
                qty_col1 = st.selectbox("Kolom Qty (NP)", df1.columns, index=idx_qty1)
            
            with c2:
                st.subheader("Distributor Setup")
                idx_sku2 = 20 if len(df2.columns) > 20 else 0
                qty2_col_match = next((col for col in df2.columns if str(col).strip().lower().replace(" ", "") == "stokakhir"), None)
                if qty2_col_match: idx_qty2 = df2.columns.get_loc(qty2_col_match)
                else: idx_qty2 = 71 if len(df2.columns) > 71 else (1 if len(df2.columns) > 1 else 0)
                
                sku_col2 = st.selectbox("Kolom SKU (Dist)", df2.columns, index=idx_sku2)
                qty_col2 = st.selectbox("Kolom Qty (Dist)", df2.columns, index=idx_qty2)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Compare Stock", type="primary", use_container_width=True):
                d1 = df1[[sku_col1, desc_col1, qty_col1]].copy()
                d1 = d1.dropna(subset=[sku_col1])
                d1[sku_col1] = d1[sku_col1].astype(str).str.split('.').str[0].str.strip()
                d1 = d1[~d1[sku_col1].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
                d1[qty_col1] = pd.to_numeric(d1[qty_col1], errors='coerce').fillna(0)
                
                d1_agg = d1.groupby(sku_col1).agg({desc_col1: 'first', qty_col1: 'sum'}).reset_index().rename(columns={sku_col1: 'SKU', desc_col1: 'Deskripsi', qty_col1: 'Newspage'})

                d2 = df2[[sku_col2, qty_col2]].copy()
                d2 = d2.dropna(subset=[sku_col2])
                d2[sku_col2] = d2[sku_col2].astype(str).str.split('.').str[0].str.strip()
                d2 = d2[~d2[sku_col2].str.lower().isin(['nan', 'none', '', 'total', 'grand total'])]
                d2[sku_col2] = d2[sku_col2].replace({'373103': '0373103', '373100': '0373100'})
                d2[qty_col2] = pd.to_numeric(d2[qty_col2], errors='coerce').fillna(0)
                
                d2_agg = d2.groupby(sku_col2)[qty_col2].sum().reset_index().rename(columns={sku_col2: 'SKU', qty_col2: 'Distributor'})

                merged = pd.merge(d1_agg, d2_agg, on='SKU', how='outer')
                merged[['Newspage', 'Distributor']] = merged[['Newspage', 'Distributor']].fillna(0)
                merged['Deskripsi'] = merged['Deskripsi'].fillna('ITEM NOT IN MASTER')
                merged['Selisih'] = merged['Distributor'] - merged['Newspage']
                merged['Status'] = merged['Selisih'].apply(lambda x: 'Match' if x == 0 else 'Mismatch')

                mismatches = merged[merged['Selisih'] != 0].sort_values('Selisih')
                
                if len(mismatches) == 0:
                    st.success("Analysis Complete: Semua data Match!")
                else:
                    valid_mismatches = mismatches[mismatches['Deskripsi'] != 'ITEM NOT IN MASTER'].copy()
                    st.session_state.reconcile_summary = {
                        'total_match': len(merged[merged['Selisih'] == 0]),
                        'total_mismatch': len(mismatches),
                        'df_view': mismatches[['SKU', 'Deskripsi', 'Newspage', 'Distributor', 'Selisih', 'Status']]
                    }
                    
                    valid_mismatches['Selisih_Clean'] = valid_mismatches['Selisih'].astype(int)
                    transfer_df = valid_mismatches[['SKU', 'Selisih_Clean']].rename(columns={'SKU': 'sku', 'Selisih_Clean': 'qty'})
                    st.session_state.reconcile_result = transfer_df
                    st.session_state.app_page = "Bot"
                    st.rerun()

    # st.markdown("---")
    if st.button("Stock Adjustment"):
        st.session_state.reconcile_result = None
        st.session_state.reconcile_summary = None
        st.session_state.app_page = "Bot"
        st.rerun()

# ─── 6. HALAMAN STEP 2: STOCK ADJUSTMENT BOT ────────────────────────────────
elif st.session_state.app_page == "Bot":
    hdr_col1, hdr_col2 = st.columns([5, 1])
    with hdr_col1:
        st.title("Stock Adjustment")
        st.markdown("Inspired by Kopi Mang Toni")
    with hdr_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Compare Stock", use_container_width=True):
            st.session_state.app_page = "Reconcile"
            st.rerun()
            
    st.markdown("---")

    if st.session_state.reconcile_summary is not None:
        st.subheader("Review Data Stock")
        m1, m2 = st.columns(2)
        m1.metric("Match", st.session_state.reconcile_summary['total_match'])
        m2.metric("Stock Difference", st.session_state.reconcile_summary['total_mismatch'], delta_color="inverse")
        st.dataframe(st.session_state.reconcile_summary['df_view'], use_container_width=True, hide_index=True)
        st.markdown("---")

    st.subheader("Configuration")
    accounts = load_accounts()
    
    if not accounts:
        st.error(f"Data akun kosong. Pastikan file '{CREDENTIALS_FILE}' ada di sistem.")
        st.stop()

    cfg_col1, cfg_col2 = st.columns(2)

    with cfg_col1:
        selected_acc_str = st.selectbox(
            "Select Distributor / User ID",
            options=[f"{acc['Distributor']} ({acc['user_id']})" for acc in accounts],
            index=None, placeholder="-- Select Account --"
        )
        
        selected_account = None
        user_password = "" # Bikin variabel nampung password

        if selected_acc_str:
            selected_account = next(acc for acc in accounts if f"{acc['Distributor']} ({acc['user_id']})" == selected_acc_str)
            
            # --- TAMBAHAN BARU: INPUT PASSWORD MUNCUL SETELAH AKUN DIPILIH ---
            user_password = st.text_input(
                f"Enter Password for {selected_account['user_id']}:", 
                type="password", 
                placeholder="Password Accenture..."
            )
            
            # Badge Account Active muncul kalau password udah diisi (minimal 3 karakter)
            if len(user_password) > 3:
                st.markdown(f"<div style='background-color: #4ade80; color: #143521; padding: 8px 12px; border-radius: 6px; font-weight: 600; font-size: 0.9rem; margin-top: 4px;'>Password Set (Validation on Run): {selected_account['Distributor']}</div>", unsafe_allow_html=True)
            else:
                 st.markdown(f"<div style='background-color: #fbbf24; color: #713f12; padding: 8px 12px; border-radius: 6px; font-weight: 600; font-size: 0.9rem; margin-top: 4px;'>Waiting for Password to be entered...</div>", unsafe_allow_html=True)

    with cfg_col2:
        df_to_process = None
        if st.session_state.reconcile_result is not None:
            st.text_input("Data Source", value="Data is automatically loaded from Compare Stock", disabled=True)
            df_to_process = st.session_state.reconcile_result
            st.markdown(f"<div style='background-color: #082f49; color: #38bdf8; padding: 8px 12px; border-radius: 6px; font-weight: 500; font-size: 0.9rem; margin-top: 4px;'>Total Item: {len(df_to_process)} Product is ready to be processed</div>", unsafe_allow_html=True)
        else:
            uploaded_file = st.file_uploader("Data Source (Upload CSV/Excel)", type=["csv", "xlsx", "xls"])
            if uploaded_file is not None:
                try: 
                    # Baca format sesuai ekstensi file
                    filename = uploaded_file.name.lower()
                    if filename.endswith('.csv'):
                        df_to_process = pd.read_csv(uploaded_file, dtype=str)
                    else:
                        df_to_process = pd.read_excel(uploaded_file, dtype=str)
                    
                    # Auto-fix: paksa semua nama kolom jadi huruf kecil & buang spasi
                    df_to_process.columns = [str(c).strip().lower() for c in df_to_process.columns]
                    
                    # Validasi wajib ada kolom sku & qty
                    if 'sku' in df_to_process.columns and 'qty' in df_to_process.columns:
                        st.markdown(f"<div style='background-color: #082f49; color: #38bdf8; padding: 8px 12px; border-radius: 6px; font-weight: 500; font-size: 0.9rem; margin-top: 4px;'>Total Item: {len(df_to_process)} Product is ready to be processed</div>", unsafe_allow_html=True)
                    else:
                        st.error("Format salah! Header kolom harus bernama 'sku' dan 'qty'.")
                        df_to_process = None
                        
                except Exception as e: 
                    st.error(f"Gagal membaca file: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    # Tambahin syarat user_password nggak boleh kosong
    is_ready = (selected_account is not None) and (len(user_password) > 3) and (df_to_process is not None)
    run_button = st.button("PROCEED", use_container_width=True, type="primary", disabled=not is_ready)

    # st.markdown("---")
    st.subheader("Product Table")

    if not is_ready:
        st.warning("Select an account and make sure the data is available before running the bot.")
        st.stop()

    df_view = df_to_process.copy()
    if 'Status' not in df_view.columns: df_view['Status'] = 'Pending'
    if 'Keterangan' not in df_view.columns: df_view['Keterangan'] = '-'

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
            
            new_log = f"<span class='log-time'>[{timestamp}]</span><span class='log-ms'>[+{diff_ms}ms]</span><span class='log-tag {tag_class}'>[{module}]</span><span class='log-msg'>{msg}</span>"
            
            logs_history.append(new_log)
            display_logs = "<br>".join(logs_history[-100:])
            
            html_content = f"""
            <div class="terminal-box" id="term_box">
                {display_logs}
                <br><span class="blink_me">█</span>
            </div>
            <script>
                var termBox = window.parent.document.getElementById('term_box');
                if (!termBox) termBox = document.getElementById('term_box');
                if (termBox) {{
                    termBox.scrollTop = termBox.scrollHeight;
                }}
            </script>
            """
            log_placeholder.markdown(html_content, unsafe_allow_html=True)

        global_start_time = time.time()
        success_count, failed_count = 0, 0
        user_id = selected_account["user_id"]
        password = user_password  # Tarik password dari input teks, bukan dari file CSV lagi!

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
                
                # --- Login ---
                ui_log("AUTH", f"Resolving DNS and establishing connection to {URL_LOGIN}...")
                page.goto(URL_LOGIN, wait_until="domcontentloaded")
                
                ui_log("AUTH", "DOM State: interactive. Parsing login nodes...")
                page.locator("id=txtUserid").fill(user_id)
                ui_log("AUTH", f"Injected credential payload for user ID: {user_id}")
                page.locator("id=txtPasswd").fill(password)
                page.locator("id=btnLogin").click(force=True)
                
                try:
                    ui_log("SYS", "Awaiting potential active-session interceptor...")
                    btn = page.locator("id=SYS_ASCX_btnContinue")
                    btn.wait_for(state="visible", timeout=5_000)
                    ui_log("AUTH", "Interceptor triggered. Bypassing active session warning...")
                    btn.click(force=True)
                except: 
                    ui_log("SYS", "No interceptor detected. Clean session acquired.")
                    
                page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
                ui_log("SUCCESS", "Handshake verified. Access token granted.")

                # --- Navigasi ---
                ui_log("NAV", "Dispatching click event to [Inventory -> Stock Adjustment] module...")
                page.locator("id=pag_InventoryRoot_tab_Main_itm_StkAdj").dispatch_event("click")
                time.sleep(5)
                
                ui_log("NAV", "Requesting new document interface [Add Value]...")
                add_btn = page.locator("id=pag_I_StkAdj_btn_Add_Value")
                add_btn.wait_for(state="attached", timeout=TIMEOUT_MS)
                add_btn.click(force=True)
                time.sleep(2)
                
                ui_log("NAV", f"Targeting localized routing: {WAREHOUSE} node...")
                page.get_by_role("link", name=WAREHOUSE, exact=True).wait_for(state="visible", timeout=TIMEOUT_MS)
                page.get_by_role("link", name=WAREHOUSE, exact=True).click(force=True)
                page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").wait_for(state="visible", timeout=TIMEOUT_MS)
                
                ui_log("SYS", f"Applying internal adjustment protocol: Code [{REASON_CODE}]")
                dropdown = page.locator("id=pag_I_StkAdj_NewGeneral_drp_n_REASON_HDR_Value")
                if dropdown.is_enabled(): dropdown.select_option(REASON_CODE)
                ui_log("SYS", "DOM fully rendered. Opening data stream for payload injection...")

                # --- Looping Input ---
                progress_bar = st.progress(0)
                total_rows = len(df_view)
                
                for i, (idx, row) in enumerate(df_view.iterrows()):
                    sku = str(row['sku']).strip()
                    try: qty = str(int(float(row['qty'])))
                    except: qty = str(row['qty']).strip()
                        
                    ui_log("INJECT", f"Fetching payload chunk {i+1}/{total_rows} -> Targeting Node: SKU [{sku}]")
                    try:
                        page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").fill(sku)
                        page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").press("Tab")
                        time.sleep(1) 
                        
                        page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").wait_for(state="visible", timeout=TIMEOUT_MS)
                        ui_log("INJECT", f"Node resolved. Assigning Value: {qty}")
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
                    table_placeholder.dataframe(df_view, use_container_width=True)

                ui_log("SERVER", "Data stream closed. Requesting master server validation...")
                page.locator("id=pag_I_StkAdj_NewGeneral_btn_Save_Value").click()
                try:
                    yes_btn = page.locator("id=pag_PopUp_YesNo_btn_Yes_Value")
                    yes_btn.wait_for(state="visible", timeout=5_000)
                    ui_log("SERVER", "Master server requested confirmation logic. Bypassing...")
                    yes_btn.click()
                    ui_log("SERVER", "Final validation passed. Document physically written to database.")
                except: 
                    ui_log("SERVER", "Automatic validation passed. Document physically written to database.")
                
                ui_log("SYS", "Shutting down Chromium instances and clearing memory allocation...")
                browser.close()
                elapsed = int(time.time() - global_start_time)
                ui_log("SUCCESS", f"EXECUTION TERMINATED NORMALLY. Total runtime: {elapsed//60}m {elapsed%60}s")
                st.success(f"Success: {success_count} - Failed: {failed_count} - Elapsed Time: {elapsed//60}m {elapsed%60}s")

                st.session_state.reconcile_result = None

        except PlaywrightTimeoutError as e:
            # Error khusus kalau nunggu loading kelamaan (biasanya karena password salah)
            st.error("Login Gagal: Password salah atau server target sedang tidak merespon (Timeout 30s).")
            ui_log("ERROR", "ACCESS DENIED: Handshake timeout. Invalid credentials or node unreachable.")
            
        except Exception as e:
            error_detail = traceback.format_exc()
            st.error("System halted due to an unexpected error.")
            
            # Bersihin pesan error bawaan Playwright biar nggak kepanjangan
            clean_error = str(e).split('===')[0].strip()
            ui_log("ERROR", f"SYSTEM FAILURE: {clean_error}")
