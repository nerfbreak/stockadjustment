
import asyncio
import csv
import html
import os
import subprocess
import sys
import time
import traceback
import zipfile
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd
import streamlit as st
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# =============================================================================
# Configuration
# =============================================================================

APP_TITLE = "Stock Adjustment Newspage"
APP_ICON = "icon.png"
URL_LOGIN = "https://rb-id.np.accenture.com/RB_ID/Logon.aspx"
CREDENTIALS_FILE = "users_2.csv"
REASON_CODE = "SA2"
WAREHOUSE = "GOOD_WHS"
TIMEOUT_MS = 30_000
TABLE_UPDATE_INTERVAL = 5


@dataclass(frozen=True)
class Account:
    distributor: str
    user_id: str
    raw: dict

    @property
    def label(self) -> str:
        return f"{self.distributor} ({self.user_id})"


# =============================================================================
# App bootstrap and styling
# =============================================================================

st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")


def inject_css() -> None:
    """Centralized UI theme: simple, solid, and clean."""
    st.markdown(
        """
        <style>
        .stApp {
            background: #f6f8fb;
            color: #111827;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1280px;
        }

        h1, h2, h3 {
            color: #111827;
            letter-spacing: -0.02em;
        }

        p, label, span {
            color: #374151;
        }

        .app-subtitle {
            color: #6b7280;
            margin-top: -0.75rem;
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }

        .live-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 999px;
            background: #dcfce7;
            color: #166534;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            border: 1px solid #bbf7d0;
        }

        .live-badge::before {
            content: "";
            width: 8px;
            height: 8px;
            background: #22c55e;
            border-radius: 999px;
        }

        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stExpander"] {
            background: #ffffff;
            border: 1px solid #e5e7eb !important;
            border-radius: 18px !important;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
        }

        .stTextInput input,
        .stSelectbox div[data-baseweb="select"] > div,
        .stFileUploader section {
            border-radius: 12px !important;
            border-color: #d1d5db !important;
            background-color: #ffffff !important;
        }

        .stTextInput input:focus {
            border-color: #2563eb !important;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12) !important;
        }

        .stButton > button {
            border-radius: 12px;
            border: 1px solid #d1d5db;
            background: #ffffff;
            color: #111827;
            font-weight: 750;
            min-height: 44px;
            transition: all 0.15s ease-in-out;
        }

        .stButton > button:hover {
            border-color: #2563eb;
            color: #2563eb;
            background: #eff6ff;
        }

        .stButton > button[kind="primary"] {
            background: #2563eb;
            color: #ffffff;
            border-color: #2563eb;
        }

        .stButton > button[kind="primary"]:hover {
            background: #1d4ed8;
            border-color: #1d4ed8;
            color: #ffffff;
        }

        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
        }

        [data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid #e5e7eb;
        }

        [data-testid="stAlert"] {
            border-radius: 14px;
            border: 1px solid #e5e7eb;
        }

        hr {
            margin: 1.5rem 0;
            border-color: #e5e7eb;
        }

        .solid-box {
            padding: 12px 14px;
            border-radius: 14px;
            font-weight: 750;
            margin-top: 10px;
            margin-bottom: 10px;
            border: 1px solid rgba(255,255,255,0.16);
        }

        .log-box {
            background: #0f172a;
            color: #e5e7eb;
            border-radius: 16px;
            padding: 16px;
            font-family: Consolas, Monaco, monospace;
            font-size: 13px;
            line-height: 1.6;
            max-height: 320px;
            overflow-y: auto;
            border: 1px solid #1e293b;
        }

        .log-cursor {
            color: #38bdf8;
            font-weight: 800;
        }

        #MainMenu, footer {
            visibility: hidden;
        }

        header {
            background: transparent;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    defaults = {
        "logged_in": False,
        "app_page": "Reconcile",
        "reconcile_result": None,
        "reconcile_summary": None,
        "np_df": None,
        "selected_distributor_str": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def make_solid_box(text: str, bg_color: str, text_color: str) -> str:
    safe_text = html.escape(str(text)).replace("\n", "<br>")
    return f"<div class='solid-box' style='background:{bg_color}; color:{text_color};'>{safe_text}</div>"


def render_page_header(title: str, subtitle: str = "Inspired by Kopi Mang Toni...") -> None:
    st.markdown("<div class='live-badge'>Live</div>", unsafe_allow_html=True)
    st.markdown(f"## {title}")
    st.markdown(f"<div class='app-subtitle'>{html.escape(subtitle)}</div>", unsafe_allow_html=True)


# =============================================================================
# Data loading and cleaning
# =============================================================================


def read_csv_with_fallback(file_or_path, *, dtype=str) -> Optional[pd.DataFrame]:
    for encoding in ["utf-8-sig", "utf-8", "cp1252", "iso-8859-1"]:
        for separator in ["\t", ",", ";", "|"]:
            try:
                if hasattr(file_or_path, "seek"):
                    file_or_path.seek(0)
                df = pd.read_csv(
                    file_or_path,
                    sep=separator,
                    dtype=dtype,
                    encoding=encoding,
                    on_bad_lines="skip",
                )
                if df is not None and df.shape[1] > 1:
                    return df
            except Exception:
                continue
    return None


def load_data(uploaded_file) -> Optional[pd.DataFrame]:
    if uploaded_file is None:
        return None

    filename = uploaded_file.name.lower()
    try:
        if filename.endswith(".csv"):
            df = read_csv_with_fallback(uploaded_file)
        elif filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(uploaded_file, dtype=str)
        elif filename.endswith(".zip"):
            df = load_dataframe_from_zip(uploaded_file)
        else:
            st.error("Unsupported file format.")
            return None

        if df is not None:
            df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as exc:
        st.error(f"Error reading file: {exc}")
        return None


def load_dataframe_from_zip(file_or_path) -> Optional[pd.DataFrame]:
    with zipfile.ZipFile(file_or_path) as archive:
        target = next(
            (
                name
                for name in archive.namelist()
                if "INVT_MASTER" in name and name.lower().endswith((".csv", ".txt"))
            ),
            None,
        )
        if target is None:
            target = next(
                (name for name in archive.namelist() if name.lower().endswith((".csv", ".txt"))),
                None,
            )
        if target is None:
            return None
        with archive.open(target) as handle:
            df = pd.read_csv(handle, sep="\t", dtype=str, on_bad_lines="skip")
            if df.shape[1] <= 1:
                handle.seek(0)
                df = pd.read_csv(handle, sep=",", dtype=str, on_bad_lines="skip")
            return df


@st.cache_data(ttl=300)
def load_accounts() -> list[Account]:
    accounts: list[Account] = []
    if not os.path.exists(CREDENTIALS_FILE):
        return accounts

    for encoding in ["utf-8-sig", "cp1252", "iso-8859-1"]:
        try:
            with open(CREDENTIALS_FILE, mode="r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    return accounts
                reader.fieldnames = [name.strip() for name in reader.fieldnames if name]
                for row in reader:
                    cleaned = {str(k).strip(): str(v).strip() for k, v in row.items() if k}
                    if "user_id" in cleaned and "Distributor" in cleaned:
                        accounts.append(
                            Account(
                                distributor=cleaned["Distributor"],
                                user_id=cleaned["user_id"],
                                raw=cleaned,
                            )
                        )
                return accounts
        except (UnicodeDecodeError, TypeError):
            continue
    return accounts


def get_account_by_label(accounts: list[Account], label: Optional[str]) -> Optional[Account]:
    if not label:
        return None
    return next((account for account in accounts if account.label == label), None)


def default_index(columns, preferred_names: list[str], fallback: int = 0) -> int:
    column_list = list(columns)
    normalized = {str(col).strip().lower(): idx for idx, col in enumerate(column_list)}
    for name in preferred_names:
        idx = normalized.get(name.strip().lower())
        if idx is not None:
            return idx
    return fallback if len(column_list) > fallback else 0


def clean_sku(series: pd.Series) -> pd.Series:
    return series.astype(str).str.split(".").str[0].str.strip()


def normalize_qty(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def build_reconciliation(
    df_np: pd.DataFrame,
    df_dist: pd.DataFrame,
    sku_col_np: str,
    desc_col_np: str,
    qty_col_np: str,
    sku_col_dist: str,
    qty_col_dist: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    np_data = df_np[[sku_col_np, desc_col_np, qty_col_np]].copy()
    np_data = np_data.dropna(subset=[sku_col_np])
    np_data[sku_col_np] = clean_sku(np_data[sku_col_np])
    np_data = np_data[~np_data[sku_col_np].str.lower().isin(["nan", "none", "", "total", "grand total"])]
    np_data[qty_col_np] = normalize_qty(np_data[qty_col_np])

    np_agg = (
        np_data.groupby(sku_col_np)
        .agg({desc_col_np: "first", qty_col_np: "sum"})
        .reset_index()
        .rename(columns={sku_col_np: "SKU", desc_col_np: "Description", qty_col_np: "Newspage"})
    )

    dist_data = df_dist[[sku_col_dist, qty_col_dist]].copy()
    dist_data = dist_data.dropna(subset=[sku_col_dist])
    dist_data[sku_col_dist] = clean_sku(dist_data[sku_col_dist])
    dist_data = dist_data[~dist_data[sku_col_dist].str.lower().isin(["nan", "none", "", "total", "grand total"])]
    dist_data[sku_col_dist] = dist_data[sku_col_dist].replace({"373103": "0373103", "373100": "0373100"})
    dist_data[qty_col_dist] = normalize_qty(dist_data[qty_col_dist])

    dist_agg = (
        dist_data.groupby(sku_col_dist)[qty_col_dist]
        .sum()
        .reset_index()
        .rename(columns={sku_col_dist: "SKU", qty_col_dist: "Distributor"})
    )

    merged = pd.merge(np_agg, dist_agg, on="SKU", how="outer")
    merged[["Newspage", "Distributor"]] = merged[["Newspage", "Distributor"]].fillna(0)
    merged["Description"] = merged["Description"].fillna("ITEM NOT IN MASTER")
    merged["Selisih"] = merged["Distributor"] - merged["Newspage"]
    merged["Status"] = merged["Selisih"].apply(lambda value: "Match" if value == 0 else "Mismatch")

    mismatches = merged[merged["Selisih"] != 0].sort_values("Selisih")
    valid_mismatches = mismatches[mismatches["Description"] != "ITEM NOT IN MASTER"].copy()
    valid_mismatches["qty"] = valid_mismatches["Selisih"].astype(int)
    transfer_df = valid_mismatches[["SKU", "qty"]].rename(columns={"SKU": "sku"})
    return merged, transfer_df


# =============================================================================
# Playwright and logging helpers
# =============================================================================

@st.cache_resource
def ensure_playwright() -> None:
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as exc:
        st.error(f"Failed to install browser engine: {exc}")


def configure_event_loop_for_windows() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.set_event_loop(asyncio.new_event_loop())


def make_logger(placeholder) -> Callable[[str, str], None]:
    history: list[str] = []
    last_log_time = [time.time()]

    def log(module: str, message: str) -> None:
        now = time.time()
        diff_ms = int((now - last_log_time[0]) * 1000)
        last_log_time[0] = now
        timestamp = time.strftime("%H:%M:%S")
        history.append(f"[{timestamp}][+{diff_ms}ms][{module}] {message}")
        display_logs = "<br>".join(html.escape(item) for item in history[-100:])
        placeholder.markdown(
            f"<div class='log-box'>{display_logs}<br><span class='log-cursor'>█</span></div>",
            unsafe_allow_html=True,
        )

    return log


def login_newspage(page, user_id: str, password: str, log: Callable[[str, str], None]) -> None:
    log("AUTH", f"Connecting to {URL_LOGIN}...")
    page.goto(URL_LOGIN, wait_until="domcontentloaded")
    log("AUTH", "DOM ready. Filling credentials...")
    page.locator("id=txtUserid").fill(user_id)
    page.locator("id=txtPasswd").fill(password)
    page.locator("id=btnLogin").click(force=True)

    try:
        continue_button = page.locator("id=SYS_ASCX_btnContinue")
        continue_button.wait_for(state="visible", timeout=5_000)
        log("AUTH", "Active session interceptor detected. Bypassing...")
        continue_button.click(force=True)
    except Exception:
        log("SYS", "No interceptor detected. Clean session acquired.")

    page.wait_for_url("**/Default.aspx", timeout=TIMEOUT_MS, wait_until="domcontentloaded")
    log("AUTH", "Login successful. Session established.")
    log("SUCCESS", "Handshake verified.")


# =============================================================================
# Authentication
# =============================================================================


def render_login_gate() -> None:
    if st.session_state.logged_in:
        return

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("### Login")
        st.markdown("<div class='app-subtitle'>Enter credentials to access the engine</div>", unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if username == st.secrets["admin_user"] and password == st.secrets["admin_pass"]:
                st.session_state.logged_in = True
                st.rerun()
            st.error("Access Denied! Incorrect username or password.")
    st.stop()


# =============================================================================
# Reconcile page
# =============================================================================


def extract_inventory_from_server(user_id: str, password: str, log: Callable[[str, str], None]) -> Optional[pd.DataFrame]:
    log("SYS", "Allocating memory and initializing Chromium headless core...")
    ensure_playwright()
    configure_event_loop_for_windows()

    with sync_playwright() as playwright:
        log("SYS", "Spawning browser context with isolated session...")
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        login_newspage(page, user_id, password, log)

        log("NAV", "Navigating to System > Import/Export Job module...")
        time.sleep(3)
        page.locator("id=pag_Sys_Root_tab_Detail_itm_Job").wait_for(state="attached", timeout=15_000)
        page.locator("id=pag_Sys_Root_tab_Detail_itm_Job").dispatch_event("click")
        time.sleep(4)

        log("NAV", "Opening new job [Add Value]...")
        page.locator("id=pag_FW_SYS_INTF_JOB_btn_Add_Value").click(force=True)
        time.sleep(3)

        log("INJECT", "Setting job type: Export [E], desc: Text Inventory Master...")
        page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_TYPE_Value").select_option("E")
        time.sleep(2)
        page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_DESC_Value").fill("Text Inventory Master")
        page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_JOB_TIMEOUT_Value").fill("9999999")
        page.locator("id=pag_FW_SYS_INTF_JOB_NewGeneral_EXE_TYPE_Value").select_option("M")
        time.sleep(2)

        log("NAV", "Proceeding to next step...")
        page.locator("id=pag_FW_SYS_INTF_JOB_RootNew_btn_Next_Value").click(force=True)
        time.sleep(3)

        log("SYS", "Bypassing disclaimer prompt...")
        page.locator("id=pag_FW_DisclaimerMessage_btn_okay_Value").click(force=True)
        time.sleep(2)

        log("NAV", "Opening interface selection popup...")
        page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_INTF_ID_SelectButton").click(force=True)
        time.sleep(3)

        log("INJECT", "Searching target interface: E_20150315090000028...")
        page.locator("id=pop_Dynamic_gft_List_2_FilterField_Value").fill("E_20150315090000028")
        page.locator("id=pop_Dynamic_grd_Main_SearchForm_ButtonSearch_Value").click(force=True)
        time.sleep(2)

        log("INJECT", "Selecting target interface from results...")
        page.get_by_text("E_20150315090000028", exact=True).click(force=True)
        time.sleep(2)

        log("INJECT", "Setting file type: Delimited [D], separator: standard...")
        page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_FILE_TYPE_Value").select_option("D")
        time.sleep(1)
        page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_FLD_SEPARATOR_STD_Value_0").check()
        time.sleep(3)

        log("INJECT", f"Applying warehouse filter: [{WAREHOUSE}]...")
        page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_grd_DynamicFilter_ctl02_dyn_Field_txt_Value").fill(WAREHOUSE)
        time.sleep(2)

        log("INJECT", "Setting dynamic parameter: 1...")
        page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_grd_DynamicFilter_ctl08_dyn_Field_txt_Value").fill("1")

        log("SYS", "Committing parameters to job definition...")
        page.locator("id=pag_FW_SYS_INTF_JOB_DTL_PopupNew_btn_Add_Value").click(force=True)
        time.sleep(3)

        log("SERVER", "Saving job and dispatching execution to server...")
        page.locator("id=pag_FW_SYS_INTF_JOB_RootNew_btn_Save_Value").click(force=True)

        log("SERVER", "Awaiting server confirmation prompt...")
        page.locator("id=TF_Prompt_btn_Ok_Value").wait_for(state="visible", timeout=15_000)
        page.locator("id=TF_Prompt_btn_Ok_Value").click(force=True)
        log("SERVER", "Job dispatched. Waiting for export to complete...")

        log("SERVER", "Intercepting download link — this may take up to 4 minutes...")
        with page.expect_download(timeout=240_000) as download_info:
            download_button = page.locator("id=pag_FW_SYS_INTF_STATUS_JOB_btn_Download_Value")
            download_button.wait_for(state="visible", timeout=240_000)
            download_button.click(force=True)

        download = download_info.value
        real_filename = download.suggested_filename
        file_path = f"temp_ext_{real_filename}"
        log("SUCCESS", f"Download captured: {real_filename}. Saving to environment...")
        download.save_as(file_path)
        browser.close()
        log("SYS", "Browser closed. Releasing session memory...")

    log("SYS", f"Parsing payload file: {real_filename}...")
    if real_filename.lower().endswith(".zip"):
        df = load_dataframe_from_zip(file_path)
    elif real_filename.lower().endswith((".xls", ".xlsx")):
        df = pd.read_excel(file_path, dtype=str)
    else:
        df = read_csv_with_fallback(file_path)

    if df is not None and not df.empty and df.shape[1] > 1:
        df.columns = [str(c).strip() for c in df.columns]
        log("SUCCESS", f"Payload Secured! {len(df)} items loaded. Flushing to session...")
        return df

    log("ERROR", "DataFrame validation failed — bad format or empty file.")
    return None


def render_np_source_panel():
    st.markdown("**Newspage Stock Data**")
    with st.expander("🔌 Extract from Master Server", expanded=st.session_state.np_df is None):
        np_user = st.text_input("NP User ID", placeholder="Enter Newspage user ID...")
        np_pass = st.text_input("NP Password", type="password", placeholder="Enter password...")
        extract_clicked = st.button(
            "Extract Inventory Master",
            type="primary",
            use_container_width=True,
            disabled=not (np_user and np_pass),
        )

        if extract_clicked:
            st.markdown("**Extraction Log:**")
            log = make_logger(st.empty())
            try:
                df = extract_inventory_from_server(np_user.strip(), np_pass.strip(), log)
                if df is None:
                    st.error("Gagal membaca file dari server, cek format ekstraksi.")
                else:
                    st.session_state.np_df = df
                    st.rerun()
            except PlaywrightTimeoutError:
                log("ERROR", "TIMEOUT: Server tidak merespon dalam batas waktu.")
                st.error("Operation Timeout. Server tidak merespon dalam batas waktu.")
            except Exception as exc:
                log("ERROR", f"SYSTEM FAILURE: {str(exc).split(chr(10))[0]}")
                st.error(f"System error: {exc}")

    if st.session_state.np_df is not None:
        st.markdown(
            make_solid_box(
                f"✅ Extracted — {len(st.session_state.np_df)} items loaded from server",
                "#082f49",
                "#38bdf8",
            ),
            unsafe_allow_html=True,
        )
        if st.button("🗑 Clear extracted data", use_container_width=True):
            st.session_state.np_df = None
            st.rerun()
        return None

    return st.file_uploader("Or upload Newspage stock file manually", type=["csv", "xlsx", "zip"])


def render_distributor_source_panel():
    st.markdown("**Distributor Stock Data**")
    file_dist = st.file_uploader("Upload Distributor stock file", type=["csv", "xlsx"])
    st.markdown("<br>", unsafe_allow_html=True)

    accounts = load_accounts()
    options = [account.label for account in accounts]
    locked = file_dist is None
    selected_index = options.index(st.session_state.selected_distributor_str) if st.session_state.selected_distributor_str in options else None
    picked = st.selectbox(
        "Select Distributor",
        options=options,
        index=selected_index,
        placeholder="-- Upload file first --" if locked else "-- Select distributor --",
        key="reconcile_dist_select",
        disabled=locked,
    )

    if picked and picked != st.session_state.selected_distributor_str:
        st.session_state.selected_distributor_str = picked
        st.rerun()

    if not locked and st.session_state.selected_distributor_str:
        st.markdown(
            make_solid_box(f"✔ {st.session_state.selected_distributor_str}", "#0f2f1d", "#4ade80"),
            unsafe_allow_html=True,
        )
    return file_dist


def render_compare_form(df_np: pd.DataFrame, df_dist: pd.DataFrame) -> None:
    st.divider()
    np_col, dist_col = st.columns(2)

    with np_col:
        st.subheader("Newspage setup")
        sku_col_np = st.selectbox("SKU column (NP)", df_np.columns, index=default_index(df_np.columns, ["Product Code"]))
        desc_col_np = st.selectbox(
            "Description column (NP)",
            df_np.columns,
            index=default_index(df_np.columns, ["Product Description", "Product Name"], fallback=1),
        )
        qty_col_np = st.selectbox(
            "Qty column (NP)",
            df_np.columns,
            index=default_index(df_np.columns, ["Stock Available"], fallback=2),
        )

    with dist_col:
        st.subheader("Distributor setup")
        qty_match = next((col for col in df_dist.columns if str(col).strip().lower().replace(" ", "") == "stokakhir"), None)
        sku_col_dist = st.selectbox("SKU column (Dist)", df_dist.columns, index=20 if len(df_dist.columns) > 20 else 0)
        qty_col_dist = st.selectbox(
            "Qty column (Dist)",
            df_dist.columns,
            index=df_dist.columns.get_loc(qty_match) if qty_match else (71 if len(df_dist.columns) > 71 else min(1, len(df_dist.columns) - 1)),
        )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Compare Stock", type="primary", use_container_width=True):
        merged, transfer_df = build_reconciliation(
            df_np,
            df_dist,
            sku_col_np,
            desc_col_np,
            qty_col_np,
            sku_col_dist,
            qty_col_dist,
        )
        mismatches = merged[merged["Selisih"] != 0].sort_values("Selisih")
        if mismatches.empty:
            st.success("Analysis complete: all items matched!")
            return

        st.session_state.reconcile_summary = {
            "total_match": len(merged[merged["Selisih"] == 0]),
            "total_mismatch": len(mismatches),
            "df_view": mismatches[["SKU", "Description", "Newspage", "Distributor", "Selisih", "Status"]],
        }
        st.session_state.reconcile_result = transfer_df
        st.session_state.app_page = "Bot"
        st.rerun()


def render_reconcile_page() -> None:
    render_page_header("Compare Stock")
    st.markdown("---")

    np_col, dist_col = st.columns(2)
    with np_col:
        with st.container(border=True):
            file_np = render_np_source_panel()

    with dist_col:
        with st.container(border=True):
            file_dist = render_distributor_source_panel()

    np_ready = st.session_state.np_df is not None or file_np is not None
    if np_ready and file_dist:
        df_np = st.session_state.np_df if st.session_state.np_df is not None else load_data(file_np)
        df_dist = load_data(file_dist)
        if df_np is not None and df_dist is not None:
            render_compare_form(df_np, df_dist)

    if st.button("Stock Adjustment"):
        st.session_state.reconcile_result = None
        st.session_state.reconcile_summary = None
        st.session_state.app_page = "Bot"
        st.rerun()


# =============================================================================
# Bot page
# =============================================================================


def render_review_summary() -> None:
    if st.session_state.reconcile_summary is None:
        return
    st.subheader("Stock review")
    metric_match, metric_diff = st.columns(2)
    metric_match.metric("Match", st.session_state.reconcile_summary["total_match"])
    metric_diff.metric("Stock difference", st.session_state.reconcile_summary["total_mismatch"], delta_color="inverse")
    st.dataframe(st.session_state.reconcile_summary["df_view"], use_container_width=True, hide_index=True)
    st.markdown("---")


def load_uploaded_process_file(uploaded_file) -> Optional[pd.DataFrame]:
    if uploaded_file is None:
        return None
    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        df = pd.read_csv(uploaded_file, dtype=str)
    else:
        df = pd.read_excel(uploaded_file, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "sku" not in df.columns or "qty" not in df.columns:
        st.error("Invalid format — column headers must be named 'sku' and 'qty'.")
        return None
    return df


def render_bot_configuration():
    st.subheader("Configuration")
    accounts = load_accounts()
    if not accounts:
        st.error(f"No account data found. Ensure '{CREDENTIALS_FILE}' exists in the app directory.")
        st.stop()

    cfg_left, cfg_right = st.columns(2)
    selected_account = None
    user_password = ""
    df_to_process = None

    with cfg_left:
        with st.container(border=True):
            labels = [account.label for account in accounts]
            selected_index = labels.index(st.session_state.selected_distributor_str) if st.session_state.selected_distributor_str in labels else None
            selected_label = st.selectbox(
                "Select Distributor / User ID",
                options=labels,
                index=selected_index,
                placeholder="-- Select account --",
            )
            if selected_label and selected_label != st.session_state.selected_distributor_str:
                st.session_state.selected_distributor_str = selected_label

            selected_account = get_account_by_label(accounts, selected_label)
            if selected_account is not None:
                user_password = st.text_input(
                    f"Password for {selected_account.user_id}:",
                    type="password",
                    placeholder="Enter password...",
                )

            if len(user_password) > 3:
                st.markdown(
                    make_solid_box(
                        f"Password set — {selected_account.distributor} (validated on run)",
                        "#0f2f1d",
                        "#4ade80",
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(make_solid_box("Waiting for password...", "#1e1b4b", "#a5b4fc"), unsafe_allow_html=True)

    with cfg_right:
        with st.container(border=True):
            if st.session_state.reconcile_result is not None:
                st.text_input("Data source", value="Auto-loaded from Compare Stock", disabled=True)
                df_to_process = st.session_state.reconcile_result
                st.markdown(
                    make_solid_box(f"{len(df_to_process)} products ready to process", "#082f49", "#38bdf8"),
                    unsafe_allow_html=True,
                )
            else:
                uploaded_file = st.file_uploader("Data source (CSV / Excel)", type=["csv", "xlsx", "xls"])
                try:
                    df_to_process = load_uploaded_process_file(uploaded_file)
                    if df_to_process is not None:
                        st.markdown(
                            make_solid_box(f"{len(df_to_process)} products ready to process", "#082f49", "#38bdf8"),
                            unsafe_allow_html=True,
                        )
                except Exception as exc:
                    st.error(f"Failed to read file: {exc}")

    return selected_account, user_password, df_to_process


def run_stock_adjustment(
    selected_account: Account,
    user_password: str,
    df_view: pd.DataFrame,
    table_placeholder,
    log_placeholder,
) -> None:
    with st.spinner("Initializing Chromium engine..."):
        ensure_playwright()

    log = make_logger(log_placeholder)
    start_time = time.time()
    success_count = 0
    failed_count = 0

    log("SYS", "Allocating memory and initializing Chromium headless core...")

    try:
        configure_event_loop_for_windows()
        with sync_playwright() as playwright:
            log("SYS", "Spawning browser context with isolated session...")
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(no_viewport=True)
            page = context.new_page()

            login_newspage(page, selected_account.user_id, user_password, log)

            log("NAV", "Navigating to Inventory > Stock Adjustment...")
            page.locator("id=pag_InventoryRoot_tab_Main_itm_StkAdj").dispatch_event("click")
            add_button = page.locator("id=pag_I_StkAdj_btn_Add_Value")
            add_button.wait_for(state="attached", timeout=TIMEOUT_MS)
            log("NAV", "Opening new document [Add Value]...")
            add_button.click(force=True)

            warehouse_link = page.get_by_role("link", name=WAREHOUSE, exact=True)
            warehouse_link.wait_for(state="visible", timeout=TIMEOUT_MS)
            warehouse_link.click(force=True)

            page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value").wait_for(state="visible", timeout=TIMEOUT_MS)
            log("SYS", f"Applying adjustment protocol: code [{REASON_CODE}]...")
            dropdown = page.locator("id=pag_I_StkAdj_NewGeneral_drp_n_REASON_HDR_Value")
            if dropdown.is_enabled():
                dropdown.select_option(REASON_CODE)

            log("SYS", "Ready. Opening data stream for payload injection...")
            progress_bar = st.progress(0)
            total_rows = len(df_view)

            for row_number, (idx, row) in enumerate(df_view.iterrows(), start=1):
                sku = str(row["sku"]).strip()
                try:
                    qty = str(int(float(row["qty"])))
                except Exception:
                    qty = str(row["qty"]).strip()

                log("INJECT", f"Payload {row_number}/{total_rows} -> SKU [{sku}]")
                try:
                    sku_input = page.locator("id=pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value")
                    sku_input.fill(sku)
                    sku_input.press("Tab")
                    time.sleep(1)

                    page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").wait_for(state="visible", timeout=TIMEOUT_MS)
                    log("INJECT", f"Assigning qty: {qty}")
                    page.locator("id=pag_I_StkAdj_NewGeneral_txt_QTY1_Value").fill(qty)
                    page.locator("id=pag_I_StkAdj_NewGeneral_btn_Add_Value").click(force=True)

                    log("SYS", "Awaiting form reset...")
                    page.wait_for_function(
                        "document.getElementById('pag_I_StkAdj_NewGeneral_sel_PRD_CD_Value').value === ''",
                        timeout=TIMEOUT_MS,
                    )
                    df_view.at[idx, "Status"] = "Success"
                    df_view.at[idx, "Keterangan"] = f"Attached {qty} EA"
                    success_count += 1
                    log("SUCCESS", "Row committed.")
                except Exception:
                    df_view.at[idx, "Status"] = "Failed"
                    df_view.at[idx, "Keterangan"] = "Node Timeout"
                    failed_count += 1
                    log("ERROR", f"Timeout on SKU [{sku}]. Skipping.")

                progress_bar.progress(row_number / total_rows)
                if row_number % TABLE_UPDATE_INTERVAL == 0 or row_number == total_rows:
                    table_placeholder.dataframe(df_view, use_container_width=True)

            log("SERVER", "Saving document to server...")
            page.locator("id=pag_I_StkAdj_NewGeneral_btn_Save_Value").click()
            try:
                yes_button = page.locator("id=pag_PopUp_YesNo_btn_Yes_Value")
                yes_button.wait_for(state="visible", timeout=5_000)
                log("SERVER", "Confirming save dialog...")
                yes_button.click()
                log("SERVER", "Document physically written to database.")
            except Exception:
                log("SERVER", "Auto-save confirmed. Document written to database.")

            log("SYS", "Closing browser and releasing memory...")
            browser.close()

        elapsed = int(time.time() - start_time)
        log("SUCCESS", f"Complete. Total runtime: {elapsed // 60}m {elapsed % 60}s")
        st.markdown(
            make_solid_box(
                f"Done — Success: {success_count}\nFailed: {failed_count}\nTime: {elapsed // 60}m {elapsed % 60}s",
                "#166534",
                "#ffffff",
            ),
            unsafe_allow_html=True,
        )

        if success_count > 0:
            st.toast("Connection terminated")
            time.sleep(0.5)
            st.toast("Data injected successfully")
            time.sleep(0.5)
            st.toast("System override complete!")
        st.session_state.reconcile_result = None

    except PlaywrightTimeoutError:
        st.error("Login failed: incorrect password or server timeout (30s).")
        log("ERROR", "ACCESS DENIED: Handshake timeout. Invalid credentials or node unreachable.")
    except Exception as exc:
        st.error("System halted due to an unexpected error.")
        clean_error = str(exc).split("===")[0].strip()
        log("ERROR", f"SYSTEM FAILURE: {clean_error}")
        log("ERROR", traceback.format_exc().splitlines()[-1])


def render_bot_page() -> None:
    header_left, header_right = st.columns([5, 1])
    with header_left:
        render_page_header("Stock Adjustment")
    with header_right:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Compare Stock", use_container_width=True):
            st.session_state.app_page = "Reconcile"
            st.rerun()

    st.markdown("---")
    render_review_summary()

    selected_account, user_password, df_to_process = render_bot_configuration()
    st.markdown("<br>", unsafe_allow_html=True)

    is_ready = selected_account is not None and len(user_password) > 3 and df_to_process is not None
    run_clicked = st.button("PROCEED", use_container_width=True, type="primary", disabled=not is_ready)

    st.subheader("Product table")
    if not is_ready:
        st.warning("Select an account and ensure data is available before running the bot.")
        st.stop()

    df_view = df_to_process.copy()
    if "Status" not in df_view.columns:
        df_view["Status"] = "Pending"
    if "Keterangan" not in df_view.columns:
        df_view["Keterangan"] = "-"

    table_placeholder = st.dataframe(df_view, use_container_width=True)
    st.markdown("Log:")
    log_placeholder = st.empty()

    if run_clicked:
        run_stock_adjustment(selected_account, user_password, df_view, table_placeholder, log_placeholder)


# =============================================================================
# Main entrypoint
# =============================================================================


def main() -> None:
    init_state()
    inject_css()
    render_login_gate()

    if st.session_state.app_page == "Reconcile":
        render_reconcile_page()
    elif st.session_state.app_page == "Bot":
        render_bot_page()
    else:
        st.session_state.app_page = "Reconcile"
        st.rerun()


if __name__ == "__main__":
    main()
